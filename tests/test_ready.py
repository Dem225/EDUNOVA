"""Tests de GET /ready : dépendances simulées, aucun service réel contacté."""

import asyncio
import concurrent.futures
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlencode

from fastapi.testclient import TestClient
from psycopg.errors import QueryCanceled
import pytest
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.core import readiness


RUNTIME = readiness.RUNTIME_READINESS
URL_DB_FAKE = "postgresql+psycopg://utilisateur:mot_de_passe@localhost:5432/edunova"


@pytest.fixture(autouse=True)
def runtime_propre():
    """Garantit un runtime inactif avant et après chaque test de ce module."""
    RUNTIME.arreter()
    yield RUNTIME
    RUNTIME.arreter()


@pytest.fixture
def module_principal(application):
    """Module app.main construit par la fixture de conftest."""
    return sys.modules["app.main"]


@pytest.fixture
def client_ready(application):
    """Client sans cycle de vie : les tests contrôlent le runtime explicitement."""
    return TestClient(application, client=("127.0.0.1", 12345))


class ConnexionFactice:
    def __init__(self, evenements):
        self.evenements = evenements

    def __enter__(self):
        self.evenements.append("ouverture")
        return self

    def __exit__(self, *args):
        self.evenements.append("fermeture")
        return False

    def execute(self, instruction):
        self.evenements.append(str(instruction))


class MoteurFactice:
    def __init__(self, *, blocage=None, demarre=None, erreur=None):
        self.blocage = blocage
        self.demarre = demarre
        self.erreur = erreur
        self.evenements = []
        self.dispositions = 0

    def connect(self):
        if self.demarre is not None:
            self.demarre.set()
        if self.blocage is not None:
            self.blocage.wait()
        if self.erreur is not None:
            raise self.erreur
        return ConnexionFactice(self.evenements)

    def dispose(self):
        self.dispositions += 1


def preparer_runtime(monkeypatch, moteur):
    """Active le runtime avec un moteur factice, sans créer de vraie connexion."""
    monkeypatch.setattr(readiness, "creer_moteur_readiness", lambda url: moteur)
    RUNTIME.demarrer(URL_DB_FAKE)
    return moteur


def instrumenter_submit(monkeypatch):
    """Compte les soumissions réelles à l'executor du runtime."""
    original = RUNTIME.executeur.submit
    appels = []

    def submit(fonction, *args, **kwargs):
        appels.append((fonction, args))
        return original(fonction, *args, **kwargs)

    monkeypatch.setattr(RUNTIME.executeur, "submit", submit)
    return appels


def requete_factice(application, redis=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))


def corps_json(reponse):
    return json.loads(reponse.body)


async def attendre_nouveau_future(future_initiale):
    """Attend que le runtime remplace effectivement le Future observé."""
    for _ in range(1000):
        if RUNTIME.future_db is not future_initiale:
            return RUNTIME.future_db
        await asyncio.sleep(0)
    raise AssertionError("Le runtime n'a pas renouvelé le Future concurrent.")


def forcer_verifications(monkeypatch, module, *, database=True, redis=True):
    """Remplace les deux sondes par des coroutines déterministes."""

    async def faux_postgresql():
        return database

    async def faux_redis(client):
        return redis

    monkeypatch.setattr(module, "verifier_postgresql", faux_postgresql)
    monkeypatch.setattr(module, "verifier_redis", faux_redis)


def test_delai_global_est_borne_a_2_5_secondes(module_principal):
    assert module_principal.DELAI_GLOBAL_READY_SECONDS == 2.5


def test_ready_postgresql_disponible_avec_backend_memoire(
    reglages, module_principal, client_ready, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "memory"
    forcer_verifications(monkeypatch, module_principal, database=True)

    reponse = client_ready.get("/ready")

    assert reponse.status_code == 200
    assert reponse.json() == {
        "status": "ready",
        "components": {"database": "ok", "redis": "not_required"},
    }
    assert reponse.headers["cache-control"] == "no-store"


def test_ready_postgresql_indisponible(
    reglages, module_principal, client_ready, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "memory"
    forcer_verifications(monkeypatch, module_principal, database=False)

    reponse = client_ready.get("/ready")

    assert reponse.status_code == 503
    assert reponse.json() == {
        "status": "not_ready",
        "detail": module_principal.MESSAGE_PAS_PRET,
        "components": {"database": "unavailable", "redis": "not_required"},
    }
    assert reponse.headers["cache-control"] == "no-store"


def test_ready_redis_disponible(
    reglages, application, module_principal, client_ready, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "redis"
    application.state.redis = object()
    forcer_verifications(monkeypatch, module_principal, database=True, redis=True)

    reponse = client_ready.get("/ready")

    assert reponse.status_code == 200
    assert reponse.json() == {
        "status": "ready",
        "components": {"database": "ok", "redis": "ok"},
    }
    assert reponse.headers["cache-control"] == "no-store"


def test_ready_redis_indisponible(
    reglages, application, module_principal, client_ready, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "redis"
    application.state.redis = object()
    forcer_verifications(monkeypatch, module_principal, database=True, redis=False)

    reponse = client_ready.get("/ready")

    assert reponse.status_code == 503
    corps = reponse.json()
    assert corps["status"] == "not_ready"
    assert corps["detail"] == module_principal.MESSAGE_PAS_PRET
    assert corps["components"] == {"database": "ok", "redis": "unavailable"}
    assert reponse.headers["cache-control"] == "no-store"


def test_ready_echecs_postgresql_et_redis(
    reglages, application, module_principal, client_ready, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "redis"
    application.state.redis = object()
    forcer_verifications(monkeypatch, module_principal, database=False, redis=False)

    reponse = client_ready.get("/ready")

    assert reponse.status_code == 503
    assert reponse.json()["components"] == {
        "database": "unavailable",
        "redis": "unavailable",
    }


def test_ready_redis_non_requis_ne_pas_de_ping(
    reglages, application, module_principal, client_ready, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "memory"
    application.state.redis = object()
    appels = []

    async def postgresql_ok():
        return True

    async def redis_interdit(client):
        appels.append(client)
        return True

    monkeypatch.setattr(module_principal, "verifier_postgresql", postgresql_ok)
    monkeypatch.setattr(module_principal, "verifier_redis", redis_interdit)

    reponse = client_ready.get("/ready")

    assert appels == []
    assert reponse.status_code == 200
    assert reponse.json()["components"]["redis"] == "not_required"


def test_ready_ne_revele_pas_de_details_techniques(
    module_principal, client_ready, monkeypatch
):
    forcer_verifications(monkeypatch, module_principal, database=False)

    reponse = client_ready.get("/ready")
    texte = reponse.text.lower()

    assert reponse.status_code == 503
    assert "postgresql" not in texte
    assert "psycopg" not in texte
    assert "mot_de_passe" not in texte
    assert "redis://" not in texte


def test_health_reste_inchange_meme_en_panne(
    reglages, application, module_principal, client_ready, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "redis"
    application.state.redis = object()
    forcer_verifications(monkeypatch, module_principal, database=False, redis=False)

    reponse = client_ready.get("/health")

    assert reponse.status_code == 200
    assert reponse.json() == {"status": "healthy"}
    assert "cache-control" not in reponse.headers


def test_verifier_redis_appelle_ping_sur_le_client_existant(module_principal):
    class ClientFactice:
        def __init__(self):
            self.pings = 0

        async def ping(self):
            self.pings += 1

    client = ClientFactice()

    assert asyncio.run(module_principal.verifier_redis(client)) is True
    assert client.pings == 1


def test_verifier_redis_erreurs_sont_silencieuses(module_principal):
    class ClientEnPanne:
        async def ping(self):
            raise RedisError("panne simulée")

    assert asyncio.run(module_principal.verifier_redis(ClientEnPanne())) is False
    assert asyncio.run(module_principal.verifier_redis(None)) is False


def capturer_create_engine(monkeypatch):
    capture = {}

    def faux_create_engine(url, **arguments):
        capture["url"] = url
        capture["arguments"] = arguments
        return object()

    monkeypatch.setattr(readiness, "create_engine", faux_create_engine)
    return capture


def verifier_parametres_imposes(capture, *valeurs_interdites):
    arguments = capture["arguments"]
    assert arguments["poolclass"] is NullPool
    assert arguments["echo"] is False
    assert arguments["connect_args"]["connect_timeout"] == 2

    options = arguments["connect_args"]["options"]
    assert options.count("statement_timeout") == 1
    assert "-c statement_timeout=2000" in options
    for valeur in valeurs_interdites:
        assert valeur not in options

    cles = {str(cle).lower() for cle in capture["url"].query}
    assert not cles & {"connect_timeout", "statement_timeout", "options"}
    return options


def test_creation_moteur_readiness_avec_options_fusionnees(monkeypatch):
    capture = capturer_create_engine(monkeypatch)
    url = "postgresql+psycopg://u:p@localhost:5432/db?" + urlencode(
        {"options": "-c search_path=public -c work_mem=4MB", "connect_timeout": "10"}
    )

    readiness.creer_moteur_readiness(url)

    options = verifier_parametres_imposes(capture, "10")
    assert "-c search_path=public" in options
    assert "-c work_mem=4MB" in options


def test_creation_moteur_readiness_remplace_statement_timeout_existant(monkeypatch):
    capture = capturer_create_engine(monkeypatch)
    url = "postgresql+psycopg://u:p@localhost:5432/db?" + urlencode(
        {"options": "-c statement_timeout=500 -c search_path=public"}
    )

    readiness.creer_moteur_readiness(url)

    options = verifier_parametres_imposes(capture, "500")
    assert "-c search_path=public" in options


@pytest.mark.parametrize(
    "forme",
    [
        "-c statement_timeout=987",
        "-cstatement_timeout=987",
        "--set statement_timeout=987",
        "--set=statement_timeout=987",
        "--statement_timeout=987",
        "-c \"statement_timeout=987\"",
        "-c 'statement_timeout=987'",
        "\"-c statement_timeout=987\"",
        "\"--set statement_timeout=987\"",
        "statement_timeout=987",
        "--statement_timeout='987ms'",
        "-c \"statement_timeout=987ms\"",
    ],
)
def test_fusion_statement_timeout_formes_libpq(monkeypatch, forme):
    capture = capturer_create_engine(monkeypatch)
    options_initiales = (
        f"{forme} -c search_path=public -c application_name=\"mon application\""
    )
    url = "postgresql+psycopg://u:p@localhost:5432/db?" + urlencode(
        {"options": options_initiales}
    )

    readiness.creer_moteur_readiness(url)

    options = verifier_parametres_imposes(capture, "987")
    assert "-c search_path=public" in options
    assert "-c application_name=\"mon application\"" in options


def test_query_string_casse_et_doublons_sont_nettoyes(monkeypatch):
    capture = capturer_create_engine(monkeypatch)
    paires = [
        ("options", "-c search_path=public -c connect_timeout=33"),
        ("OPTIONS", "-c work_mem=8MB"),
        ("connect_timeout", "11"),
        ("CONNECT_TIMEOUT", "22"),
        ("statement_timeout", "700"),
        ("STATEMENT_TIMEOUT", "800"),
        ("sslmode", "require"),
    ]
    url = "postgresql+psycopg://u:p@localhost:5432/db?" + urlencode(paires)

    readiness.creer_moteur_readiness(url)

    options = verifier_parametres_imposes(capture, "700", "800", "11", "22", "33")
    assert "connect_timeout" not in options
    assert "-c search_path=public" in options
    assert "-c work_mem=8MB" in options
    assert capture["url"].query["sslmode"] == "require"


@pytest.mark.parametrize(
    "options_initiales",
    [
        None,
        "",
        "   ",
        "-c application_name='mon application -c search_path=public",
    ],
)
def test_options_vides_absentes_ou_malformees(monkeypatch, options_initiales):
    capture = capturer_create_engine(monkeypatch)
    url = "postgresql+psycopg://u:p@localhost:5432/db"
    if options_initiales is not None:
        url += "?" + urlencode({"options": options_initiales})

    readiness.creer_moteur_readiness(url)

    options = verifier_parametres_imposes(capture)
    if options_initiales is None or not options_initiales.strip():
        assert options == "-c statement_timeout=2000"
    else:
        assert options_initiales in options


def test_select_1_ready_execute_et_libere_la_connexion():
    moteur = MoteurFactice()

    assert readiness._select_1_ready(moteur) is True
    assert moteur.evenements == ["ouverture", "SELECT 1", "fermeture"]


@pytest.mark.parametrize(
    "erreur",
    [
        OperationalError("SELECT 1", {}, Exception("panne simulée")),
        QueryCanceled("SELECT 1", {}, Exception("annulé")),
        OSError("panne réseau simulée"),
    ],
)
def test_select_1_ready_erreurs_sont_silencieuses(erreur):
    assert readiness._select_1_ready(MoteurFactice(erreur=erreur)) is False


def test_verifier_postgresql_erreur_silencieuse(monkeypatch, module_principal):
    erreur = OperationalError("SELECT 1", {}, Exception("panne simulée"))
    preparer_runtime(monkeypatch, MoteurFactice(erreur=erreur))

    assert asyncio.run(module_principal.verifier_postgresql()) is False


def test_verifier_postgresql_sans_runtime_actif(module_principal):
    assert asyncio.run(module_principal.verifier_postgresql()) is False


def test_soumettre_cree_un_seul_future_pour_20_appels(monkeypatch, module_principal):
    blocage = threading.Event()
    demarre = threading.Event()
    preparer_runtime(monkeypatch, MoteurFactice(blocage=blocage, demarre=demarre))
    appels = instrumenter_submit(monkeypatch)

    appels_soumettre = []
    soumettre_original = RUNTIME.soumettre
    delai_max = 2.0
    tous_demandes = threading.Event()
    echecs_attente = []

    def soumettre_compte():
        appels_soumettre.append(True)
        if len(appels_soumettre) == 20:
            tous_demandes.set()
        return soumettre_original()

    monkeypatch.setattr(RUNTIME, "soumettre", soumettre_compte)

    def relacher_quand_tous_ont_demande():
        if not tous_demandes.wait(delai_max):
            echecs_attente.append(
                "Les 20 appels à soumettre() n'ont pas été observés "
                f"avant {delai_max} s."
            )
        blocage.set()

    thread = threading.Thread(target=relacher_quand_tous_ont_demande)

    async def scénario():
        return await asyncio.gather(
            *(module_principal.verifier_postgresql() for _ in range(20))
        )

    thread.start()
    try:
        assert all(asyncio.run(scénario()))
        thread.join(delai_max + 1)
        assert not echecs_attente, echecs_attente[0]
        assert len(appels_soumettre) == 20, (
            f"Seulement {len(appels_soumettre)} appels à soumettre() observés."
        )
        assert len(appels) == 1
    finally:
        tous_demandes.set()
        blocage.set()
        thread.join(delai_max + 1)


def test_future_pending_apres_annulation_et_cancelled_error_remonte(
    monkeypatch, module_principal
):
    blocage = threading.Event()
    demarre = threading.Event()
    preparer_runtime(
        monkeypatch, MoteurFactice(blocage=blocage, demarre=demarre)
    )
    future_initiale = RUNTIME.future_db

    async def scénario():
        tache = asyncio.create_task(module_principal.verifier_postgresql())
        future = await attendre_nouveau_future(future_initiale)
        tache.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tache
        return future

    try:
        future = asyncio.run(scénario())
        assert demarre.wait(2)
        assert future is RUNTIME.future_db
        assert future.cancelled() is False
        assert future.done() is False
    finally:
        blocage.set()

    assert future.result(timeout=2) is True


def test_timeout_produit_timeout_error_et_laisse_future_pending(
    monkeypatch, module_principal
):
    blocage = threading.Event()
    demarre = threading.Event()
    preparer_runtime(
        monkeypatch, MoteurFactice(blocage=blocage, demarre=demarre)
    )
    future_initiale = RUNTIME.future_db

    async def scénario():
        tache = asyncio.create_task(module_principal.verifier_postgresql())
        await attendre_nouveau_future(future_initiale)
        async with asyncio.timeout(0.01):
            await asyncio.gather(tache, return_exceptions=True)

    try:
        with pytest.raises(TimeoutError):
            asyncio.run(scénario())
        assert demarre.wait(2)
        future = RUNTIME.future_db
        assert future is not None
        assert future.done() is False
        assert future.cancelled() is False
    finally:
        blocage.set()

    assert future.result(timeout=2) is True


def test_plusieurs_boucles_asyncio_reutilisent_le_meme_future(
    monkeypatch, module_principal
):
    blocage = threading.Event()
    demarre = threading.Event()
    preparer_runtime(
        monkeypatch, MoteurFactice(blocage=blocage, demarre=demarre)
    )
    appels = instrumenter_submit(monkeypatch)
    appels_soumettre = []
    soumettre_original = RUNTIME.soumettre

    def soumettre_compte():
        appels_soumettre.append(True)
        return soumettre_original()

    monkeypatch.setattr(RUNTIME, "soumettre", soumettre_compte)

    async def annuler_appelant(nombre_attendu):
        tache = asyncio.create_task(module_principal.verifier_postgresql())
        for _ in range(1000):
            if len(appels_soumettre) >= nombre_attendu:
                break
            await asyncio.sleep(0)
        else:
            raise AssertionError("La sonde n'a pas été soumise.")
        tache.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tache

    try:
        asyncio.run(annuler_appelant(1))
        premier = RUNTIME.future_db

        asyncio.run(annuler_appelant(2))
        second = RUNTIME.future_db

        assert premier is second
        assert len(appels) == 1
        assert demarre.wait(2)
        assert premier.done() is False
    finally:
        blocage.set()

    assert premier.result(timeout=2) is True
    assert asyncio.run(module_principal.verifier_postgresql()) is True
    assert len(appels) == 2  # nouveau cycle après la fin réelle du thread


def test_future_deja_termine_au_moment_du_callback(
    monkeypatch, module_principal
):
    future = concurrent.futures.Future()
    future.set_result(True)
    appels = instrumenter_submit(monkeypatch)
    monkeypatch.setattr(RUNTIME, "soumettre", lambda: future)

    assert asyncio.run(module_principal.verifier_postgresql()) is True
    assert appels == []


def test_callback_thread_ne_touche_pas_attente_hors_boucle(module_principal):
    future = concurrent.futures.Future()
    future.set_result(True)
    loop = asyncio.new_event_loop()

    class AttenteFactice:
        def __init__(self):
            self.done_appels = 0
            self.threads_done = []
            self.resultats = []
            self.threads = []

        def done(self):
            self.done_appels += 1
            self.threads_done.append(threading.get_ident())
            return bool(self.resultats)

        def set_result(self, valeur):
            self.threads.append(threading.get_ident())
            self.resultats.append(valeur)

    attente = AttenteFactice()
    planifications = []
    planifier_original = loop.call_soon_threadsafe

    def planifier(callback, *args):
        planifications.append(threading.get_ident())
        return planifier_original(callback, *args)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(loop, "call_soon_threadsafe", planifier)
    threads_worker = []

    def worker():
        threads_worker.append(threading.get_ident())
        module_principal._programmer_resultat(future, loop, attente)

    try:
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(2)
        loop.run_until_complete(asyncio.sleep(0))

        identifiant_boucle = threading.get_ident()
        assert threads_worker and planifications == threads_worker
        assert attente.done_appels >= 1
        assert all(
            identifiant == identifiant_boucle
            for identifiant in attente.threads_done
        )
        assert attente.resultats == [True]
        assert attente.threads == [identifiant_boucle]
    finally:
        monkeypatch.undo()
        loop.close()


def test_callback_sur_boucle_fermee_est_ignore(module_principal):
    future = concurrent.futures.Future()
    future.set_result(True)
    loop = asyncio.new_event_loop()
    loop.close()

    module_principal._programmer_resultat(future, loop, object())


def test_ready_timeout_repond_503_et_reutilise_future(
    module_principal, client_ready, monkeypatch
):
    blocage = threading.Event()
    demarre = threading.Event()
    preparer_runtime(
        monkeypatch, MoteurFactice(blocage=blocage, demarre=demarre)
    )
    appels = instrumenter_submit(monkeypatch)
    monkeypatch.setattr(module_principal, "DELAI_GLOBAL_READY_SECONDS", 0.01)

    try:
        premiere = client_ready.get("/ready")
        assert premiere.status_code == 503
        assert premiere.json()["components"] == {
            "database": "unavailable",
            "redis": "not_required",
        }
        assert premiere.headers["cache-control"] == "no-store"
        assert demarre.wait(2)

        future = RUNTIME.future_db
        assert future is not None
        assert future.done() is False

        seconde = client_ready.get("/ready")
        assert seconde.status_code == 503
        assert RUNTIME.future_db is future
        assert len(appels) == 1
    finally:
        blocage.set()

    assert future.result(timeout=2) is True


def test_ready_lance_les_deux_sondes_en_parallele(
    reglages, application, module_principal, monkeypatch
):
    reglages.RATE_LIMIT_BACKEND = "redis"
    demarrees = []

    async def faux_postgresql():
        demarrees.append("database")
        database_prêt.set()
        await asyncio.sleep(0)
        await asyncio.wait_for(redis_prêt.wait(), 0.5)
        return True

    async def faux_redis(client):
        demarrees.append("redis")
        redis_prêt.set()
        await asyncio.sleep(0)
        await asyncio.wait_for(database_prêt.wait(), 0.5)
        return True

    database_prêt = asyncio.Event()
    redis_prêt = asyncio.Event()
    monkeypatch.setattr(module_principal, "verifier_postgresql", faux_postgresql)
    monkeypatch.setattr(module_principal, "verifier_redis", faux_redis)

    async def scénario():
        return await module_principal.ready(
            requete_factice(application, redis=object())
        )

    reponse = asyncio.run(scénario())

    assert sorted(demarrees) == ["database", "redis"]
    assert reponse.status_code == 200


def test_ready_timeout_annule_et_consomme_redis(
    reglages, application, module_principal, monkeypatch, caplog
):
    reglages.RATE_LIMIT_BACKEND = "redis"
    annulations = []

    async def postgresql_bloque():
        await asyncio.Event().wait()
        return True

    async def redis_bloque(client):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            annulations.append(True)
            raise

    monkeypatch.setattr(module_principal, "verifier_postgresql", postgresql_bloque)
    monkeypatch.setattr(module_principal, "verifier_redis", redis_bloque)
    monkeypatch.setattr(module_principal, "DELAI_GLOBAL_READY_SECONDS", 0.01)
    caplog.set_level("ERROR")

    async def scénario():
        return await module_principal.ready(
            requete_factice(application, redis=object())
        )

    reponse = asyncio.run(scénario())

    assert reponse.status_code == 503
    assert corps_json(reponse)["components"] == {
        "database": "unavailable",
        "redis": "unavailable",
    }
    assert annulations == [True]
    assert "never retrieved" not in caplog.text


def test_cycles_lifespan_reactivent_runtime_sans_fermer_executeur(
    reglages, application, monkeypatch
):
    moteurs = []

    def fabriquer_moteur(url):
        moteur = MoteurFactice()
        moteurs.append(moteur)
        return moteur

    monkeypatch.setattr(readiness, "creer_moteur_readiness", fabriquer_moteur)
    arrets_executeur = []
    monkeypatch.setattr(
        RUNTIME.executeur,
        "shutdown",
        lambda *args, **kwargs: arrets_executeur.append((args, kwargs)),
    )
    executeur_initial = RUNTIME.executeur

    with TestClient(application, client=("127.0.0.1", 12345)):
        assert RUNTIME.actif is True
        premier = RUNTIME.moteur

    assert RUNTIME.actif is False
    assert premier.dispositions == 1

    with TestClient(application, client=("127.0.0.1", 12345)):
        assert RUNTIME.actif is True
        second = RUNTIME.moteur

    assert second is not premier
    assert RUNTIME.executeur is executeur_initial
    assert arrets_executeur == []


def test_disposition_differee_du_moteur_quand_thread_actif(monkeypatch):
    blocage = threading.Event()
    demarre = threading.Event()
    moteur = preparer_runtime(
        monkeypatch, MoteurFactice(blocage=blocage, demarre=demarre)
    )

    future = RUNTIME.soumettre()
    assert demarre.wait(2)

    RUNTIME.arreter()

    assert RUNTIME.actif is False
    assert RUNTIME.moteur is None
    assert moteur.dispositions == 0

    blocage.set()
    assert future.result(timeout=2) is True
    assert moteur.dispositions == 1


def test_callback_dispose_en_panne_ne_propage_pas_et_reste_unique(monkeypatch):
    class MoteurEnPanneDisposition:
        def __init__(self):
            self.dispositions = 0

        def dispose(self):
            self.dispositions += 1
            raise RuntimeError("panne de disposition simulée")

    class FutureEnAttente:
        def __init__(self):
            self.callback = None

        def done(self):
            return False

        def add_done_callback(self, callback):
            self.callback = callback

    moteur = MoteurEnPanneDisposition()
    preparer_runtime(monkeypatch, moteur)
    future = FutureEnAttente()
    monkeypatch.setattr(RUNTIME, "_future_db", future)

    RUNTIME.arreter()

    assert RUNTIME.actif is False
    assert RUNTIME.moteur is None
    assert moteur.dispositions == 0
    assert future.callback is not None

    future.callback(future)
    future.callback(future)

    assert moteur.dispositions == 1

    RUNTIME.arreter()
    assert moteur.dispositions == 1


def test_redemarrage_pendant_sonde_utilise_encore_le_future_en_cours(monkeypatch):
    blocage = threading.Event()
    demarre = threading.Event()
    premier_moteur = preparer_runtime(
        monkeypatch, MoteurFactice(blocage=blocage, demarre=demarre)
    )
    appels = instrumenter_submit(monkeypatch)
    future = RUNTIME.soumettre()
    assert demarre.wait(2)

    RUNTIME.arreter()
    second_moteur = MoteurFactice()
    monkeypatch.setattr(readiness, "creer_moteur_readiness", lambda url: second_moteur)
    RUNTIME.demarrer(URL_DB_FAKE)

    assert RUNTIME.soumettre() is future
    assert len(appels) == 1
    assert second_moteur.evenements == []

    blocage.set()
    assert future.result(timeout=2) is True
    assert premier_moteur.dispositions == 1

    nouveau_future = RUNTIME.soumettre()
    assert nouveau_future is not future
    assert len(appels) == 2
    assert nouveaux_resultats(nouveau_future) is True


def nouveaux_resultats(future):
    return future.result(timeout=2)


def test_aucun_gestionnaire_atexit_personnalise():
    source = (Path(__file__).resolve().parents[1] / "backend" / "app" / "core" / "readiness.py").read_text(encoding="utf-8")
    assert "atexit.register" not in source


def test_moteur_metier_reste_inchange():
    from app.db.session import engine as moteur_metier

    assert "connect_timeout" not in moteur_metier.url.query
    assert "options" not in moteur_metier.url.query
    assert moteur_metier.pool.__class__.__name__ != "NullPool"
