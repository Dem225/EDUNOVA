import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import asyncio as redis_asyncio
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.applications import router as applications_router
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import settings
from app.core.rate_limit import (
    IpRateLimitMiddleware,
    MemoryBackend,
    RateLimiter,
    RedisBackend,
    secret_hmac_depuis_settings,
)
from app.core.readiness import RUNTIME_READINESS


# Readiness : bornes courtes, réponses génériques, aucun détail technique exposé.
# DELAI_READY_SECONDS est conservé pour la sonde Redis existante. Le délai
# global couvre les deux sondes lancées en parallèle.
DELAI_READY_SECONDS = 2.0
DELAI_SONDE_REDIS_SECONDS = DELAI_READY_SECONDS
DELAI_GLOBAL_READY_SECONDS = 2.5
MESSAGE_PAS_PRET = "Le service n'est pas prêt. Veuillez réessayer plus tard."
ENTETES_READY = {"Cache-Control": "no-store"}
COMPOSANT_OK = "ok"
COMPOSANT_INDISPONIBLE = "unavailable"
COMPOSANT_NON_REQUIS = "not_required"


def _appliquer_resultat_thread(
    future_asyncio: asyncio.Future[bool],
    attente: asyncio.Future[bool],
) -> None:
    """Applique le résultat sur la boucle asyncio, jamais depuis le worker."""
    if attente.done():
        return
    try:
        valeur = False if future_asyncio.cancelled() else bool(future_asyncio.result())
    except Exception:
        valeur = False
    if not attente.done():
        attente.set_result(valeur)


def _programmer_resultat(
    future_db: concurrent.futures.Future[bool],
    loop: asyncio.AbstractEventLoop,
    attente: asyncio.Future[bool],
) -> None:
    """Uniquement planifier le transfert : aucune lecture de attente ici."""
    try:
        loop.call_soon_threadsafe(_appliquer_resultat_thread, future_db, attente)
    except RuntimeError:
        # Boucle déjà fermée : l'appelant n'est plus là pour recevoir le résultat.
        pass


async def verifier_postgresql() -> bool:
    """Vérifie PostgreSQL sans jamais annuler le Future concurrent partagé."""
    future_db = RUNTIME_READINESS.soumettre()
    if future_db is None:
        return False

    loop = asyncio.get_running_loop()
    attente: asyncio.Future[bool] = loop.create_future()
    future_db.add_done_callback(
        lambda future: _programmer_resultat(future, loop, attente)
    )

    try:
        return await asyncio.shield(attente)
    except (SQLAlchemyError, TimeoutError, OSError):
        # Uniquement les pannes attendues. asyncio.CancelledError remonte.
        return False


async def verifier_redis(client: Any) -> bool:
    """Vérifie le client Redis existant, sans en instancier un nouveau."""
    if client is None:
        return False
    try:
        async with asyncio.timeout(DELAI_SONDE_REDIS_SECONDS):
            await client.ping()
        return True
    except (RedisError, TimeoutError, OSError):
        return False


def _resultat_tache(tache: "asyncio.Task[bool]") -> bool:
    """Lit une tache terminée en marquant son exception comme récupérée."""
    if tache.cancelled() or not tache.done():
        return False
    exception = tache.exception()
    if exception is not None:
        return False
    return bool(tache.result())


async def _annuler_et_consommer(taches: list["asyncio.Task[bool]"]) -> None:
    """Annule puis consomme les tâches Redis encore actives après un timeout."""
    for tache in taches:
        if not tache.done():
            tache.cancel()
    if taches:
        await asyncio.gather(*taches, return_exceptions=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise le backend de limitation et le runtime de readiness."""
    client_redis = None

    if settings.RATE_LIMIT_BACKEND == "redis":
        url_redis = settings.REDIS_URL
        if hasattr(url_redis, "get_secret_value"):
            url_redis = url_redis.get_secret_value()
        client_redis = redis_asyncio.Redis.from_url(
            str(url_redis),
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            health_check_interval=settings.REDIS_HEALTH_CHECK_INTERVAL,
        )
        backend = RedisBackend(client_redis)
    else:
        backend = MemoryBackend()

    app.state.redis = client_redis
    app.state.rate_limiter = RateLimiter(
        backend=backend,
        secret=secret_hmac_depuis_settings(settings),
        ip_max=settings.RATE_LIMIT_IP_MAX,
        ip_fenetre_secondes=settings.RATE_LIMIT_IP_WINDOW_SECONDS,
        email_max=settings.RATE_LIMIT_EMAIL_MAX,
        email_fenetre_secondes=settings.RATE_LIMIT_EMAIL_WINDOW_SECONDS,
    )

    RUNTIME_READINESS.demarrer(settings.DATABASE_URL)

    try:
        yield
    finally:
        RUNTIME_READINESS.arreter()
        if client_redis is not None:
            await client_redis.aclose()


app = FastAPI(
    title="EDUNOVA API",
    description="API du projet éducatif EDUNOVA",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
)


# Starlette construit la pile en sens inverse de l'enregistrement. Pour obtenir
# CORSMiddleware → BodyLimitMiddleware → IpRateLimitMiddleware → routage,
# on enregistre dans l'ordre inverse.
app.add_middleware(IpRateLimitMiddleware)

app.add_middleware(
    BodyLimitMiddleware,
    limit=settings.MAX_REQUEST_BODY_BYTES,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
async def accueil():
    return {
        "message": "Bienvenue sur EDUNOVA",
        "projet": "EDUNOVA",
        "statut": "API opérationnelle",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Vérifie les dépendances nécessaires au fonctionnement de l'API."""
    taches: dict[str, asyncio.Task[bool]] = {
        "database": asyncio.create_task(
            verifier_postgresql(), name="ready-database"
        )
    }

    if settings.RATE_LIMIT_BACKEND == "redis":
        taches["redis"] = asyncio.create_task(
            verifier_redis(getattr(request.app.state, "redis", None)),
            name="ready-redis",
        )

    try:
        async with asyncio.timeout(DELAI_GLOBAL_READY_SECONDS):
            valeurs = await asyncio.gather(*taches.values(), return_exceptions=True)
        disponibilites = {
            nom: False if isinstance(valeur, BaseException) else bool(valeur)
            for nom, valeur in zip(taches, valeurs)
        }
    except TimeoutError:
        # gather a annulé les tâches enfants. Le Future concurrent DB partagé
        # n'est pas touché : asyncio.shield a absorbé l'annulation locale.
        disponibilites = {
            nom: _resultat_tache(tache) for nom, tache in taches.items()
        }
        taches_redis = [
            tache
            for nom, tache in taches.items()
            if nom == "redis" and not tache.done()
        ]
        await _annuler_et_consommer(taches_redis)

    composants: dict[str, str] = {
        "database": (
            COMPOSANT_OK
            if disponibilites.get("database", False)
            else COMPOSANT_INDISPONIBLE
        ),
        "redis": COMPOSANT_NON_REQUIS,
    }
    if "redis" in taches:
        composants["redis"] = (
            COMPOSANT_OK
            if disponibilites.get("redis", False)
            else COMPOSANT_INDISPONIBLE
        )

    pret = all(disponibilites.get(nom, False) for nom in taches)

    if pret:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "components": composants},
            headers=ENTETES_READY,
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_ready",
            "detail": MESSAGE_PAS_PRET,
            "components": composants,
        },
        headers=ENTETES_READY,
    )


app.include_router(applications_router)
