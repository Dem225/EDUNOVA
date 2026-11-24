import httpx
from fastapi.testclient import TestClient

from app.core.rate_limit import MESSAGE_LIMITE_DEPASSSEE


def test_trois_premieres_demandes_autorisees(client, payload):
    for _ in range(3):
        assert client.post("/applications/", json=payload()).status_code == 202


def test_quatrieme_demande_bloquee(client, payload):
    for _ in range(3):
        assert client.post("/applications/", json=payload()).status_code == 202

    reponse = client.post("/applications/", json=payload())
    assert reponse.status_code == 429
    assert reponse.json() == {"detail": MESSAGE_LIMITE_DEPASSSEE}
    assert int(reponse.headers["retry-after"]) >= 1


def test_normalisation_casse_partage_le_compteur(client_ip, payload):
    client = client_ip("203.0.113.20")

    variantes = [
        "Jean.Dupont@Exemple.COM",
        "JEAN.DUPONT@EXEMPLE.COM",
        "jean.dupont@exemple.com",
    ]
    for email in variantes:
        assert client.post("/applications/", json=payload(email)).status_code == 202

    assert client.post("/applications/", json=payload()).status_code == 429


def test_deux_emails_ont_des_compteurs_independants(client_ip, payload):
    client_a = client_ip("203.0.113.21")
    client_b = client_ip("203.0.113.22")

    for _ in range(3):
        assert (
            client_a.post(
                "/applications/", json=payload("premier@exemple.com")
            ).status_code
            == 202
        )

    for _ in range(3):
        assert (
            client_b.post(
                "/applications/", json=payload("second@exemple.com")
            ).status_code
            == 202
        )


def test_doublons_consomment_le_quota_email(application, payload):
    application.state.base_factice.existant = object()
    with TestClient(application, client=("127.0.0.1", 12345)) as client:
        for _ in range(3):
            reponse = client.post("/applications/", json=payload())
            assert reponse.status_code == 202

        assert client.post("/applications/", json=payload()).status_code == 429
