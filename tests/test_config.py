import importlib.util
from pathlib import Path

import pytest


SOURCE_CONFIG = (
    Path(__file__).resolve().parents[1] / "backend" / "app" / "core" / "config.py"
)


@pytest.fixture
def module_config(tmp_path, monkeypatch):
    """Charge config.py depuis un arbre temporaire sans .env."""
    cible = tmp_path / "backend" / "app" / "core" / "config.py"
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(SOURCE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://utilisateur:mot_de_passe@localhost:5432/edunova"
    )
    spec = importlib.util.spec_from_file_location("config_isole", cible)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configuration_developpement_valide(module_config):
    reglages = module_config.Settings(
        RATE_LIMIT_HMAC_SECRET="secret-hmac-de-test-0123456789abcdef"
    )
    assert reglages.RATE_LIMIT_BACKEND == "memory"
    assert reglages.RATE_LIMIT_IP_MAX == 5
    assert reglages.RATE_LIMIT_EMAIL_MAX == 3


def test_hmac_obligatoire_en_production(module_config):
    with pytest.raises(ValueError, match="RATE_LIMIT_HMAC_SECRET"):
        module_config.Settings(
            APP_ENV="production",
            SECRET_KEY="a" * 32,
            INSTALLATION_TOKEN="b" * 32,
            REDIS_URL="redis://localhost:6379/0",
            RATE_LIMIT_BACKEND="redis",
        )


def test_hmac_trop_court_refuse(module_config):
    with pytest.raises(ValueError, match="32 caractères"):
        module_config.Settings(RATE_LIMIT_HMAC_SECRET="trop-court")


def test_hmac_distinct_des_autres_secrets(module_config):
    secret = "secret-hmac-de-test-0123456789abcdef"
    with pytest.raises(ValueError, match="distinct"):
        module_config.Settings(SECRET_KEY=secret, RATE_LIMIT_HMAC_SECRET=secret)

    with pytest.raises(ValueError, match="distinct"):
        module_config.Settings(
            INSTALLATION_TOKEN=secret, RATE_LIMIT_HMAC_SECRET=secret
        )


def test_redis_obligatoire_en_staging(module_config):
    with pytest.raises(ValueError, match="REDIS_URL"):
        module_config.Settings(
            APP_ENV="staging",
            SECRET_KEY="a" * 32,
            INSTALLATION_TOKEN="b" * 32,
            RATE_LIMIT_BACKEND="redis",
            RATE_LIMIT_HMAC_SECRET="secret-hmac-de-test-0123456789abcdef",
        )


def test_backend_memoire_interdit_en_production(module_config):
    with pytest.raises(ValueError, match="mémoire"):
        module_config.Settings(
            APP_ENV="production",
            SECRET_KEY="a" * 32,
            INSTALLATION_TOKEN="b" * 32,
            REDIS_URL="redis://localhost:6379/0",
            RATE_LIMIT_BACKEND="memory",
            RATE_LIMIT_HMAC_SECRET="secret-hmac-de-test-0123456789abcdef",
        )


def test_proxy_wildcard_refuse(module_config):
    with pytest.raises(ValueError, match="TRUSTED_PROXY_IPS"):
        module_config.Settings(TRUSTED_PROXY_IPS=["*"])


def test_erreurs_ne_revelent_pas_les_secrets(module_config):
    secret = "valeur-secrete-ne-pas-afficher-0123456789"
    with pytest.raises(ValueError) as erreur:
        module_config.Settings(SECRET_KEY=secret, RATE_LIMIT_HMAC_SECRET=secret)

    assert secret not in str(erreur.value)
