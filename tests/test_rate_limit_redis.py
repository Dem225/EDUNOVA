import asyncio
import os

from fastapi.testclient import TestClient
import pytest
from redis import asyncio as redis_asyncio
from redis.exceptions import RedisError

from conftest import ORIGINE_AUTORISEE, construire_application
from app.core.rate_limit import (
    MESSAGE_SERVICE_INDISPONIBLE,
    PREFIXE_EMAIL,
    PREFIXE_IP,
    SCRIPT_LUA_FENETRE_GLISSANTE,
    MemoryBackend,
    RateLimiter,
    RateLimitUnavailable,
    RedisBackend,
    cle_limitation_ip,
)


URL_REDIS_TEST = os.environ.get("EDUNOVA_TEST_REDIS_URL")
SECRET_TEST = b"secret-hmac-de-test-0123456789abcdef0123456789"


class ClientRedisEnPanne:
    async def eval(self, *args, **kwargs):
        raise RedisError("panne Redis simulée")

    async def aclose(self):
        return None


class BackendPanneEmail:
    def __init__(self) -> None:
        self.memoire = MemoryBackend()

    async def check_and_increment(self, cle, limite, fenetre):
        if cle.startswith(PREFIXE_EMAIL):
            raise RateLimitUnavailable()
        return await self.memoire.check_and_increment(cle, limite, fenetre)


def test_script_lua_contient_les_operations_atomiques():
    for operation in [
        "TIME",
        "ZREMRANGEBYSCORE",
        "ZCARD",
        "ZRANGE",
        "ZADD",
        "PEXPIRE",
    ]:
        assert operation in SCRIPT_LUA_FENETRE_GLISSANTE


def test_panne_redis_donne_503_sur_limite_ip(application, payload):
    with TestClient(
        application, client=("127.0.0.1", 12345)
    ) as client:
        application.state.rate_limiter = RateLimiter(
            RedisBackend(ClientRedisEnPanne()),
            SECRET_TEST,
            5,
            60,
            3,
            900,
        )
        reponse = client.post(
            "/applications/",
            json=payload(),
            headers={"Origin": ORIGINE_AUTORISEE},
        )

    assert reponse.status_code == 503
    assert reponse.json() == {"detail": MESSAGE_SERVICE_INDISPONIBLE}
    assert (
        reponse.headers.get("access-control-allow-origin") == ORIGINE_AUTORISEE
    )


def test_panne_redis_donne_503_sur_limite_email(application, payload):
    with TestClient(
        application, client=("127.0.0.1", 12345)
    ) as client:
        application.state.rate_limiter = RateLimiter(
            BackendPanneEmail(), SECRET_TEST, 5, 60, 3, 900
        )
        reponse = client.post(
            "/applications/",
            json=payload(),
            headers={"Origin": ORIGINE_AUTORISEE},
        )

    assert reponse.status_code == 503
    assert reponse.json() == {"detail": MESSAGE_SERVICE_INDISPONIBLE}
    assert (
        reponse.headers.get("access-control-allow-origin") == ORIGINE_AUTORISEE
    )


def test_aucun_repli_memoire_silencieux(application, payload):
    with TestClient(application, client=("127.0.0.1", 12345)) as client:
        backend = RedisBackend(ClientRedisEnPanne())
        application.state.rate_limiter = RateLimiter(
            backend, SECRET_TEST, 5, 60, 3, 900
        )

        for i in range(8):
            assert (
                client.post(
                    "/applications/", json=payload(f"panne-{i}@exemple.com")
                ).status_code
                == 503
            )

    assert isinstance(application.state.rate_limiter.backend, RedisBackend)


def test_redis_est_ferme_proprement_a_l_arret(reglages, monkeypatch):
    reglages.RATE_LIMIT_BACKEND = "redis"
    reglages.REDIS_URL = "redis://localhost:6379/0"

    fermetures = []

    class FauxClientRedis:
        async def aclose(self):
            fermetures.append(True)

    monkeypatch.setattr(
        redis_asyncio.Redis,
        "from_url",
        lambda *args, **kwargs: FauxClientRedis(),
    )

    app, _ = construire_application(reglages, monkeypatch)
    with TestClient(app, client=("127.0.0.1", 12345)):
        assert app.state.redis is not None

    assert fermetures == [True]


@pytest.mark.skipif(
    not URL_REDIS_TEST,
    reason="Aucun serveur Redis de test (définir EDUNOVA_TEST_REDIS_URL).",
)
def test_atomicite_et_limite_avec_vrai_redis():
    async def scenario():
        client = redis_asyncio.Redis.from_url(URL_REDIS_TEST)
        try:
            await client.flushdb()
            backend = RedisBackend(client)
            cle = "rl:app:ip:test-atomicite"

            resultat = await asyncio.gather(
                *[
                    backend.check_and_increment(cle, 5, 60)
                    for _ in range(12)
                ]
            )
            autorises = [d.autorise for d in resultat]
            assert autorises.count(True) == 5
            assert autorises.count(False) == 7
            await client.flushdb()
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not URL_REDIS_TEST,
    reason="Aucun serveur Redis de test (définir EDUNOVA_TEST_REDIS_URL).",
)
def test_ttl_et_retry_after_avec_vrai_redis():
    async def scenario():
        client = redis_asyncio.Redis.from_url(URL_REDIS_TEST)
        try:
            await client.flushdb()
            backend = RedisBackend(client)
            cle = "rl:app:ip:test-ttl"

            await backend.check_and_increment(cle, 2, 3)
            await backend.check_and_increment(cle, 2, 3)
            refus = await backend.check_and_increment(cle, 2, 3)

            assert refus.autorise is False
            assert refus.retry_after >= 1
            assert await client.pttl(cle) > 0
            await client.flushdb()
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not URL_REDIS_TEST,
    reason="Aucun serveur Redis de test (définir EDUNOVA_TEST_REDIS_URL).",
)
def test_deux_clients_partagent_le_compteur():
    async def scenario():
        client_a = redis_asyncio.Redis.from_url(URL_REDIS_TEST)
        client_b = redis_asyncio.Redis.from_url(URL_REDIS_TEST)
        try:
            await client_a.flushdb()
            backend_a = RedisBackend(client_a)
            backend_b = RedisBackend(client_b)
            cle = cle_limitation_ip("203.0.113.99", SECRET_TEST)

            for _ in range(3):
                assert (await backend_a.check_and_increment(cle, 5, 60)).autorise
            for _ in range(2):
                assert (await backend_b.check_and_increment(cle, 5, 60)).autorise
            assert not (await backend_b.check_and_increment(cle, 5, 60)).autorise
            await client_a.flushdb()
        finally:
            await client_a.aclose()
            await client_b.aclose()

    asyncio.run(scenario())
