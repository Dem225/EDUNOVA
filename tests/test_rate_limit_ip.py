import asyncio

import httpx
from fastapi.testclient import TestClient

from app.core.rate_limit import MESSAGE_LIMITE_DEPASSSEE


def test_cinq_premieres_demandes_autorisees(client, payload):
    for i in range(5):
        assert (
            client.post(
                "/applications/", json=payload(f"ip-{i}@exemple.com")
            ).status_code
            == 202
        )


def test_sixieme_demande_bloquee_avec_retry_after(client, payload):
    for i in range(5):
        assert (
            client.post(
                "/applications/", json=payload(f"ip-{i}@exemple.com")
            ).status_code
            == 202
        )

    reponse = client.post("/applications/", json=payload("ip-5@exemple.com"))
    assert reponse.status_code == 429
    assert reponse.json() == {"detail": MESSAGE_LIMITE_DEPASSSEE}
    assert int(reponse.headers["retry-after"]) >= 1


def test_deux_ip_ont_des_compteurs_independants(client_ip, payload):
    client_a = client_ip("203.0.113.10")
    client_b = client_ip("203.0.113.11")

    for i in range(5):
        assert (
            client_a.post(
                "/applications/", json=payload(f"a-{i}@exemple.com")
            ).status_code
            == 202
        )
    assert (
        client_a.post("/applications/", json=payload("a-5@exemple.com")).status_code
        == 429
    )
    assert (
        client_b.post("/applications/", json=payload("b-0@exemple.com")).status_code
        == 202
    )


def test_health_ne_consomme_aucun_quota(client, payload):
    for _ in range(10):
        assert client.get("/health").status_code == 200
    for i in range(5):
        assert (
            client.post(
                "/applications/", json=payload(f"health-{i}@exemple.com")
            ).status_code
            == 202
        )
    assert (
        client.post("/applications/", json=payload("health-5@exemple.com")).status_code
        == 429
    )


def test_autres_routes_ne_consomment_aucun_quota(client, payload):
    for chemin in ["/", "/docs", "/openapi.json", "/health", "/applications/"]:
        assert client.get(chemin).status_code in (200, 405)

    for i in range(5):
        assert (
            client.post(
                "/applications/", json=payload(f"route-{i}@exemple.com")
            ).status_code
            == 202
        )
    assert (
        client.post("/applications/", json=payload("route-5@exemple.com")).status_code
        == 429
    )


def test_candidature_invalide_consomme_uniquement_le_quota_ip(client, payload):
    invalide = payload()
    invalide["email"] = "adresse-invalide"

    assert client.post("/applications/", json=invalide).status_code == 422

    for i in range(4):
        assert (
            client.post(
                "/applications/", json=payload(f"invalide-{i}@exemple.com")
            ).status_code
            == 202
        )
    assert (
        client.post(
            "/applications/", json=payload("invalide-4@exemple.com")
        ).status_code
        == 429
    )


def test_concurrence_aucun_depassement(application, payload):
    with TestClient(application, client=("127.0.0.1", 12345)):

        async def envoyer():
            transport = httpx.ASGITransport(
                app=application, client=("198.51.100.7", 12345)
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client_asynchrone:
                return await asyncio.gather(
                    *[
                        client_asynchrone.post(
                            "/applications/",
                            json=payload(f"concurrence-{i}@exemple.com"),
                        )
                        for i in range(12)
                    ]
                )

        reponses = asyncio.run(envoyer())

    statuts = [reponse.status_code for reponse in reponses]
    assert statuts.count(202) == 5
    assert statuts.count(429) == 7
