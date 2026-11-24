"""Rate limiting des candidatures : backends mémoire et Redis, HMAC et middleware IP.

Les identifiants stockés dans Redis sont des digests HMAC-SHA256 opaques. La
rotation de ``RATE_LIMIT_HMAC_SECRET`` réinitialise donc les compteurs actifs :
les clés changent et les anciennes expirent naturellement.

Aucune adresse IP, aucun e-mail et aucun digest n'est journalisé.
"""

import asyncio
from collections import deque
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import secrets
import time
from typing import Any

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError


MESSAGE_LIMITE_DEPASSSEE = (
    "Trop de demandes ont été envoyées. Veuillez réessayer plus tard."
)
MESSAGE_SERVICE_INDISPONIBLE = (
    "Le service de candidature est temporairement indisponible. "
    "Veuillez réessayer plus tard."
)

PREFIXE_IP = "rl:app:ip:"
PREFIXE_EMAIL = "rl:app:email:"


class RateLimitUnavailable(Exception):
    """Le stockage partagé de limitation n'est pas disponible."""


@dataclass(frozen=True)
class Decision:
    autorise: bool
    retry_after: int
    restant: int


def secret_hmac_depuis_settings(settings: Any) -> bytes:
    """Retourne le secret HMAC configuré, ou un secret éphémère en développement."""
    secret = getattr(settings, "RATE_LIMIT_HMAC_SECRET", None)
    if secret is None:
        return secrets.token_bytes(32)
    if hasattr(secret, "get_secret_value"):
        secret = secret.get_secret_value()
    return str(secret).encode("utf-8")


def _digest(domaine: bytes, valeur: str, secret: bytes) -> str:
    return hmac.new(secret, domaine + valeur.encode("utf-8"), hashlib.sha256).hexdigest()


def cle_limitation_ip(ip_normalisee: str, secret: bytes) -> str:
    """Clé Redis opaque pour une IP déjà normalisée."""
    return PREFIXE_IP + _digest(b"ip|", ip_normalisee, secret)


def cle_limitation_email(email_normalise: str, secret: bytes) -> str:
    """Clé Redis opaque pour un e-mail déjà normalisé."""
    return PREFIXE_EMAIL + _digest(b"email|", email_normalise, secret)


class MemoryBackend:
    """Backend local, réservé au développement et aux tests."""

    def __init__(self) -> None:
        self.evenements: dict[str, deque[float]] = {}
        self.verrou = asyncio.Lock()

    async def check_and_increment(
        self, cle: str, limite: int, fenetre_secondes: int
    ) -> Decision:
        async with self.verrou:
            maintenant = time.monotonic()
            borne = maintenant - fenetre_secondes
            file_evenements = self.evenements.setdefault(cle, deque())

            while file_evenements and file_evenements[0] <= borne:
                file_evenements.popleft()

            if len(file_evenements) >= limite:
                attente = math.ceil(
                    file_evenements[0] + fenetre_secondes - maintenant
                )
                return Decision(False, max(1, attente), 0)

            file_evenements.append(maintenant)
            return Decision(True, 0, limite - len(file_evenements))

    def effacer(self) -> None:
        """Utile uniquement aux tests."""
        self.evenements.clear()


SCRIPT_LUA_FENETRE_GLISSANTE = """
local key = KEYS[1]
local limite = tonumber(ARGV[1])
local fenetre_ms = tonumber(ARGV[2])
local membre = ARGV[3]

local horloge = redis.call('TIME')
local maintenant_ms = tonumber(horloge[1]) * 1000
    + math.floor(tonumber(horloge[2]) / 1000)
local borne_ms = maintenant_ms - fenetre_ms

redis.call('ZREMRANGEBYSCORE', key, 0, borne_ms)
local count = redis.call('ZCARD', key)

if count >= limite then
    local plus_ancien = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local attente_ms = math.ceil(
        tonumber(plus_ancien[2]) + fenetre_ms - maintenant_ms
    )
    if attente_ms < 1000 then
        attente_ms = 1000
    end
    return {0, math.ceil(attente_ms / 1000), 0}
end

redis.call('ZADD', key, maintenant_ms, membre)
redis.call('PEXPIRE', key, fenetre_ms)
return {1, 0, limite - count - 1}
"""


class RedisBackend:
    """Backend partagé : script Lua atomique, ZSET et TTL."""

    def __init__(self, client: Any) -> None:
        self.client = client

    async def check_and_increment(
        self, cle: str, limite: int, fenetre_secondes: int
    ) -> Decision:
        membre = secrets.token_hex(16)
        try:
            resultat = await self.client.eval(
                SCRIPT_LUA_FENETRE_GLISSANTE,
                1,
                cle,
                limite,
                fenetre_secondes * 1000,
                membre,
            )
        except (RedisError, TimeoutError, OSError) as exc:
            raise RateLimitUnavailable from exc

        autorise = int(resultat[0]) == 1
        retry_after = max(1, int(resultat[1]))
        restant = int(resultat[2])
        return Decision(autorise, retry_after, restant)


class RateLimiter:
    """Applique les deux politiques de limitation avec des clés opaques."""

    def __init__(
        self,
        backend: Any,
        secret: bytes,
        ip_max: int,
        ip_fenetre_secondes: int,
        email_max: int,
        email_fenetre_secondes: int,
    ) -> None:
        self.backend = backend
        self.secret = secret
        self.ip_max = ip_max
        self.ip_fenetre_secondes = ip_fenetre_secondes
        self.email_max = email_max
        self.email_fenetre_secondes = email_fenetre_secondes

    async def verifier_ip(self, ip_normalisee: str) -> Decision:
        cle = cle_limitation_ip(ip_normalisee, self.secret)
        return await self.backend.check_and_increment(
            cle, self.ip_max, self.ip_fenetre_secondes
        )

    async def verifier_email(self, email_normalise: str) -> Decision:
        cle = cle_limitation_email(email_normalise.lower(), self.secret)
        return await self.backend.check_and_increment(
            cle, self.email_max, self.email_fenetre_secondes
        )


async def _reponse_json(
    send: Any,
    code_statut: int,
    detail: str,
    retry_after: int | None = None,
) -> None:
    corps = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    en_tetes = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(corps)).encode("ascii")),
    ]
    if retry_after is not None:
        en_tetes.append((b"retry-after", str(max(1, retry_after)).encode("ascii")))
    en_tetes.append((b"connection", b"close"))

    await send(
        {
            "type": "http.response.start",
            "status": code_statut,
            "headers": en_tetes,
        }
    )
    await send({"type": "http.response.body", "body": corps})


class IpRateLimitMiddleware:
    """Limite exclusivement ``POST /applications/`` par adresse IP."""

    CHEMIN_PROTEGE = "/applications/"

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != self.CHEMIN_PROTEGE
        ):
            await self.app(scope, receive, send)
            return

        from app.core.client_ip import ClientIPError, obtenir_ip_client

        try:
            ip_normalisee = obtenir_ip_client(Request(scope))
        except ClientIPError:
            await _reponse_json(send, 503, MESSAGE_SERVICE_INDISPONIBLE)
            return

        application = scope.get("app")
        limiteur = getattr(getattr(application, "state", None), "rate_limiter", None)
        if limiteur is None:
            await _reponse_json(send, 503, MESSAGE_SERVICE_INDISPONIBLE)
            return

        try:
            decision = await limiteur.verifier_ip(ip_normalisee)
        except RateLimitUnavailable:
            await _reponse_json(send, 503, MESSAGE_SERVICE_INDISPONIBLE)
            return

        if not decision.autorise:
            await _reponse_json(
                send,
                status.HTTP_429_TOO_MANY_REQUESTS,
                MESSAGE_LIMITE_DEPASSSEE,
                decision.retry_after,
            )
            return

        await self.app(scope, receive, send)


def erreur_email(decision: Decision) -> HTTPException:
    """Construit l'erreur 429 renvoyée par la route après validation."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=MESSAGE_LIMITE_DEPASSSEE,
        headers={"Retry-After": str(max(1, decision.retry_after))},
    )


def erreur_indisponible() -> HTTPException:
    """Construit l'erreur 503 neutre renvoyée par la route."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=MESSAGE_SERVICE_INDISPONIBLE,
    )
