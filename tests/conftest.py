"""Fixtures de test : configuration simulée, base factice, aucun .env lu."""

import copy
import importlib
from pathlib import Path
import sys
import types

import pytest
from fastapi.testclient import TestClient


# Rend ``uv run pytest -q`` autonome : les paquets ``app`` et ``conftest``
# doivent être importables sans définir PYTHONPATH à la main.
RACINE = Path(__file__).resolve().parents[1]
for dossier in (RACINE / "backend", RACINE / "tests"):
    if str(dossier) not in sys.path:
        sys.path.insert(0, str(dossier))


REGLAGES_BASE = types.SimpleNamespace(
    APP_NAME="EDUNOVA",
    APP_ENV="development",
    DATABASE_URL="postgresql+psycopg://utilisateur:mot_de_passe@localhost:5432/edunova",
    SECRET_KEY=None,
    INSTALLATION_TOKEN=None,
    SQL_ECHO=False,
    DOCS_ENABLED=True,
    MAX_REQUEST_BODY_BYTES=32_768,
    CORS_ORIGINS=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
    ],
    ACCESS_TOKEN_EXPIRE_MINUTES=15,
    REFRESH_TOKEN_EXPIRE_DAYS=7,
    PASSWORD_RESET_EXPIRE_MINUTES=30,
    INVITATION_EXPIRE_HOURS=24,
    JWT_ALGORITHM="HS256",
    JWT_ISSUER="edunova-api",
    JWT_AUDIENCE="edunova-admin",
    JWT_LEEWAY_SECONDS=30,
    JWT_KEY_VERSION=1,
    ARGON2_MEMORY_COST=65_536,
    ARGON2_TIME_COST=3,
    ARGON2_PARALLELISM=4,
    PASSWORD_MIN_LENGTH=14,
    MAX_LOGIN_ATTEMPTS=5,
    ACCOUNT_LOCKOUT_MINUTES=15,
    RATE_LIMIT_LOGIN_PER_MINUTE=5,
    RATE_LIMIT_RESET_PER_HOUR=3,
    RATE_LIMIT_APPLICATIONS_PER_MINUTE=5,
    RATE_LIMIT_BACKEND="memory",
    RATE_LIMIT_IP_MAX=5,
    RATE_LIMIT_IP_WINDOW_SECONDS=60,
    RATE_LIMIT_EMAIL_MAX=3,
    RATE_LIMIT_EMAIL_WINDOW_SECONDS=900,
    REDIS_URL=None,
    REDIS_SOCKET_CONNECT_TIMEOUT=0.5,
    REDIS_SOCKET_TIMEOUT=0.5,
    REDIS_HEALTH_CHECK_INTERVAL=30,
    RATE_LIMIT_HMAC_SECRET="secret-hmac-de-test-0123456789abcdef",
    TRUSTED_PROXY_IPS=[],
)


class FauxQuery:
    def __init__(self, base: "FauxDB") -> None:
        self.base = base

    def filter(self, *args, **kwargs) -> "FauxQuery":
        return self

    def first(self):
        return self.base.existant


class FauxDB:
    def __init__(self) -> None:
        self.existant = None
        self.ajouts: list = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, modele):
        return FauxQuery(self)

    def add(self, objet) -> None:
        self.ajouts.append(objet)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture
def reglages():
    """Copie indépendante des réglages simulés pour chaque test."""
    return copy.deepcopy(REGLAGES_BASE)


def construire_application(reglages, monkeypatch):
    """Construit une application neuve avec configuration simulée et base factice."""
    module_config = types.ModuleType("app.core.config")
    module_config.settings = reglages
    monkeypatch.setitem(sys.modules, "app.core.config", module_config)

    sys.modules.pop("app.main", None)
    module_principal = importlib.import_module("app.main")
    app = module_principal.app

    from app.db.session import get_db

    base_factice = FauxDB()
    app.dependency_overrides[get_db] = lambda: base_factice
    app.state.base_factice = base_factice
    return app, module_principal


@pytest.fixture
def application(reglages, monkeypatch):
    """Application FastAPI neuve, avec configuration simulée et base factice."""
    app, _ = construire_application(reglages, monkeypatch)
    return app


@pytest.fixture
def client(application):
    """Client HTTP avec une IP client valide et le cycle de vie exécuté."""
    with TestClient(application, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


@pytest.fixture
def client_ip(application, reglages):
    """Fabrique de clients HTTP avec une IP client contrôlée."""
    from app.core.rate_limit import (
        MemoryBackend,
        RateLimiter,
        secret_hmac_depuis_settings,
    )

    # Pas de contexte TestClient ici : on initialise le limiteur une seule fois
    # pour que plusieurs clients partagent le même backend mémoire.
    application.state.rate_limiter = RateLimiter(
        MemoryBackend(),
        secret_hmac_depuis_settings(reglages),
        reglages.RATE_LIMIT_IP_MAX,
        reglages.RATE_LIMIT_IP_WINDOW_SECONDS,
        reglages.RATE_LIMIT_EMAIL_MAX,
        reglages.RATE_LIMIT_EMAIL_WINDOW_SECONDS,
    )

    def fabrique(ip: str, port: int = 12345) -> TestClient:
        return TestClient(application, client=(ip, port))

    return fabrique


@pytest.fixture
def payload():
    """Candidature valide conforme à ApplicationCreate."""

    def fabrique(email: str = "jean.dupont@exemple.com") -> dict:
        return {
            "nom": "Jean",
            "prenom": "Dupont",
            "email": email,
            "telephone": None,
            "niveau": "college",
            "motivation": "x" * 20,
        }

    return fabrique


ORIGINE_AUTORISEE = "http://127.0.0.1:5501"
