from fastapi.testclient import TestClient

from conftest import ORIGINE_AUTORISEE, construire_application
from app.api.routes.applications import MESSAGE_ACCUSE_DE_RECEPTION, router as applications_router
from app.core.body_limit import MESSAGE_TAILLE_MAXIMALE


def test_limite_32_kio_et_cors(client):
    reponse = client.post(
        "/applications/",
        content=b"x" * 32_769,
        headers={
            "Content-Type": "application/json",
            "Origin": ORIGINE_AUTORISEE,
        },
    )

    assert reponse.status_code == 413
    assert reponse.json() == {"detail": MESSAGE_TAILLE_MAXIMALE}
    assert (
        reponse.headers.get("access-control-allow-origin") == ORIGINE_AUTORISEE
    )


def test_429_conserve_les_en_tetes_cors(client, payload):
    for _ in range(5):
        client.post(
            "/applications/",
            json=payload(),
            headers={"Origin": ORIGINE_AUTORISEE},
        )

    reponse = client.post(
        "/applications/",
        json=payload(),
        headers={"Origin": ORIGINE_AUTORISEE},
    )

    assert reponse.status_code == 429
    assert (
        reponse.headers.get("access-control-allow-origin") == ORIGINE_AUTORISEE
    )
    assert int(reponse.headers["retry-after"]) >= 1


def test_reponse_202_generique_inchangee(client, payload):
    reponse = client.post("/applications/", json=payload())

    assert reponse.status_code == 202
    assert reponse.json() == {"message": MESSAGE_ACCUSE_DE_RECEPTION}


def test_get_public_applications_absent(application):
    routes = [
        (route.path, getattr(route, "methods", set()) or set())
        for route in applications_router.routes
        if getattr(route, "path", None) == "/applications/"
    ]
    assert routes
    assert all("POST" in methodes and "GET" not in methodes for _, methodes in routes)

    with TestClient(application, client=("127.0.0.1", 12345)) as client:
        assert client.get("/applications/").status_code != 200


def test_swagger_selon_docs_enabled(reglages, monkeypatch):
    app_active, _ = construire_application(reglages, monkeypatch)
    with TestClient(app_active, client=("127.0.0.1", 12345)) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200

    reglages.DOCS_ENABLED = False
    app_inactive, _ = construire_application(reglages, monkeypatch)
    with TestClient(app_inactive, client=("127.0.0.1", 12345)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_chaine_effective_des_middlewares(application):
    # Starlette insère chaque middleware en tête de user_middleware :
    # cette liste est donc l'inverse de l'ordre d'enregistrement.
    noms_enregistres = [
        middleware.cls.__name__ for middleware in application.user_middleware
    ]
    assert noms_enregistres == [
        "CORSMiddleware",
        "BodyLimitMiddleware",
        "IpRateLimitMiddleware",
    ]

    chaine = []
    courant = application.build_middleware_stack()
    while courant is not None:
        chaine.append(type(courant).__name__)
        courant = getattr(courant, "app", None)

    index_cors = chaine.index("CORSMiddleware")
    index_taille = chaine.index("BodyLimitMiddleware")
    index_ip = chaine.index("IpRateLimitMiddleware")
    assert index_cors < index_taille < index_ip
