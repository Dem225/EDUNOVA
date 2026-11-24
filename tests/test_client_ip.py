import asyncio
import json

from fastapi.testclient import TestClient
import pytest

from app.core.client_ip import ClientIPError, normaliser_ip, obtenir_ip_client


def test_normalisation_ipv4():
    assert normaliser_ip("203.0.113.7") == "203.0.113.7"


def test_normalisation_ipv6():
    assert normaliser_ip("2001:0DB8:0000::0001") == "2001:db8::1"


def test_ip_absente_leve_une_erreur():
    with pytest.raises(ClientIPError):
        normaliser_ip(None)


def test_ip_invalide_leve_une_erreur():
    with pytest.raises(ClientIPError):
        normaliser_ip("pas-une-ip")


def test_ip_invalide_donne_503(client_ip, payload):
    reponse = client_ip("adresse-invalide").post(
        "/applications/", json=payload()
    )
    assert reponse.status_code == 503
    assert reponse.json()["detail"].startswith(
        "Le service de candidature est temporairement indisponible"
    )


def test_client_absent_donne_503(application, payload):
    corps = json.dumps(payload()).encode("utf-8")

    async def appel():
        evenements = []

        async def receive():
            return {
                "type": "http.request",
                "body": corps,
                "more_body": False,
            }

        async def send(message):
            evenements.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/applications/",
            "raw_path": b"/applications/",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "server": ("testserver", 80),
        }
        await application(scope, receive, send)
        return evenements

    with TestClient(application, client=("127.0.0.1", 12345)):
        evenements = asyncio.run(appel())

    assert evenements[0]["status"] == 503


def test_x_forwarded_for_falsifie_est_ignore(client_ip, payload):
    client_a = client_ip("203.0.113.40")
    client_b = client_ip("203.0.113.41")
    headers = {"X-Forwarded-For": "198.51.100.99"}

    for i in range(5):
        assert (
            client_a.post(
                "/applications/",
                json=payload(f"xff-{i}@exemple.com"),
                headers=headers,
            ).status_code
            == 202
        )

    assert (
        client_a.post(
            "/applications/",
            json=payload("xff-5@exemple.com"),
            headers=headers,
        ).status_code
        == 429
    )
    assert (
        client_b.post(
            "/applications/",
            json=payload("autre-xff@exemple.com"),
            headers=headers,
        ).status_code
        == 202
    )


def test_ipv6_evolve_avec_sa_propre_limite(client_ip, payload):
    client = client_ip("2001:db8::1")

    for i in range(5):
        assert (
            client.post(
                "/applications/", json=payload(f"ipv6-{i}@exemple.com")
            ).status_code
            == 202
        )
    assert (
        client.post("/applications/", json=payload("ipv6-5@exemple.com")).status_code
        == 429
    )
