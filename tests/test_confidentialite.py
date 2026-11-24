from app.core.rate_limit import (
    PREFIXE_EMAIL,
    PREFIXE_IP,
    cle_limitation_email,
    cle_limitation_ip,
)


SECRET_TEST = b"secret-hmac-de-test-0123456789abcdef0123456789"


def test_cle_ip_ne_contient_pas_d_adresse_en_clair():
    cle = cle_limitation_ip("203.0.113.7", SECRET_TEST)
    assert cle.startswith(PREFIXE_IP)
    assert "203.0.113.7" not in cle


def test_cle_email_ne_contient_pas_d_adresse_en_clair():
    cle = cle_limitation_email("Jean.Dupont@Exemple.COM", SECRET_TEST)
    assert cle.startswith(PREFIXE_EMAIL)
    assert "Jean.Dupont@Exemple.COM" not in cle
    assert "jean.dupont@exemple.com" not in cle


def test_aucune_pii_ni_digest_dans_les_journaux(client, payload, caplog):
    email = "jean.dupont@exemple.com"
    digest = cle_limitation_email(email, SECRET_TEST).split(":", 3)[-1]

    with caplog.at_level("DEBUG"):
        for _ in range(6):
            client.post(
                "/applications/",
                json=payload(email),
                headers={"Origin": "http://127.0.0.1:5501"},
            )

    texte = caplog.text
    assert email not in texte
    assert "127.0.0.1" not in texte
    assert digest not in texte
