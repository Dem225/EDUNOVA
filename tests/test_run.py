"""Tests du point de lancement Uvicorn : aucun serveur réel n'est démarré."""

import importlib.util
from pathlib import Path
import sys
import types

import pytest


CHEMIN_RUN = Path(__file__).resolve().parents[1] / "backend" / "run.py"


@pytest.fixture
def module_run(monkeypatch):
    """Charge ``backend/run.py`` avec des paramètres EDUNOVA simulés."""
    reglages = types.SimpleNamespace(TRUSTED_PROXY_IPS=[])
    module_config = types.ModuleType("app.core.config")
    module_config.settings = reglages
    application_factice = object()
    module_main = types.ModuleType("app.main")
    module_main.app = application_factice

    for nom in ("app", "app.core"):
        if nom not in sys.modules:
            monkeypatch.setitem(sys.modules, nom, types.ModuleType(nom))
    monkeypatch.setitem(sys.modules, "app.core.config", module_config)
    monkeypatch.setitem(sys.modules, "app.main", module_main)

    spec = importlib.util.spec_from_file_location("edunova_run_test", CHEMIN_RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, reglages, application_factice


def test_liste_explicite_transmise_a_uvicorn(module_run):
    module, reglages, _ = module_run
    reglages.TRUSTED_PROXY_IPS = ["203.0.113.5"]

    parametres = module.parametres_uvicorn()

    assert parametres["forwarded_allow_ips"] == ["203.0.113.5"]
    assert parametres["proxy_headers"] is True


def test_plusieurs_ip_et_cidr_sont_transmis(module_run):
    module, reglages, _ = module_run
    attendu = ["10.0.0.1", "10.0.1.0/24", "2001:db8::1"]
    reglages.TRUSTED_PROXY_IPS = attendu

    parametres = module.parametres_uvicorn()

    assert parametres["forwarded_allow_ips"] == attendu
    assert parametres["proxy_headers"] is True


def test_proxy_headers_desactive_sans_proxy(module_run):
    module, reglages, _ = module_run
    reglages.TRUSTED_PROXY_IPS = []

    parametres = module.parametres_uvicorn()

    assert parametres["proxy_headers"] is False
    assert parametres["forwarded_allow_ips"] == []


def test_joker_est_refuse(module_run):
    module, reglages, _ = module_run
    reglages.TRUSTED_PROXY_IPS = ["*"]

    with pytest.raises(ValueError, match="joker"):
        module.parametres_uvicorn()


def test_joker_refuse_meme_accompagne_d_une_ip_valide(module_run):
    module, reglages, _ = module_run
    reglages.TRUSTED_PROXY_IPS = ["10.0.0.1", "*"]

    with pytest.raises(ValueError, match="joker"):
        module.parametres_uvicorn()


def test_parametres_proviennent_de_la_configuration_edunova(module_run):
    module, _, _ = module_run
    nouveau = types.SimpleNamespace(TRUSTED_PROXY_IPS=["192.0.2.44"])
    sys.modules["app.core.config"].settings = nouveau

    assert module.parametres_uvicorn()["forwarded_allow_ips"] == ["192.0.2.44"]


def test_main_utilise_l_application_existante_sans_serveur(monkeypatch, module_run):
    module, reglages, application = module_run
    reglages.TRUSTED_PROXY_IPS = ["10.0.0.1"]
    appels = []

    monkeypatch.setattr(module, "_application", lambda: application)
    monkeypatch.setattr(
        module.uvicorn,
        "run",
        lambda app, **kwargs: appels.append((app, kwargs)),
    )

    module.main([])

    assert len(appels) == 1
    assert appels[0][0] is application
    assert appels[0][1]["proxy_headers"] is True
    assert appels[0][1]["forwarded_allow_ips"] == ["10.0.0.1"]


def test_main_ne_demarre_pas_de_proxy_sans_liste(monkeypatch, module_run):
    module, reglages, application = module_run
    reglages.TRUSTED_PROXY_IPS = []
    appels = []

    monkeypatch.setattr(module, "_application", lambda: application)
    monkeypatch.setattr(
        module.uvicorn,
        "run",
        lambda app, **kwargs: appels.append((app, kwargs)),
    )

    module.main([])

    assert appels[0][1]["proxy_headers"] is False


def test_hote_et_port_par_defaut(module_run):
    module, _, _ = module_run

    parametres = module.parametres_uvicorn()

    assert parametres["host"] == "127.0.0.1"
    assert parametres["port"] == 8000


def test_main_sans_option_ecoute_en_local(monkeypatch, module_run):
    module, _, application = module_run
    appels = []

    monkeypatch.setattr(module, "_application", lambda: application)
    monkeypatch.setattr(
        module.uvicorn,
        "run",
        lambda app, **kwargs: appels.append((app, kwargs)),
    )

    module.main([])

    assert appels[0][1]["host"] == "127.0.0.1"
    assert appels[0][1]["port"] == 8000


def test_hote_explicite_toutes_interfaces(module_run):
    module, _, _ = module_run

    parametres = module.parametres_uvicorn(host="0.0.0.0")

    assert parametres["host"] == "0.0.0.0"
    assert parametres["port"] == 8000


def test_selection_explicite_via_cli_sans_serveur(monkeypatch, module_run):
    module, reglages, application = module_run
    reglages.TRUSTED_PROXY_IPS = ["10.0.0.1", "10.0.1.0/24"]
    appels = []

    monkeypatch.setattr(module, "_application", lambda: application)
    monkeypatch.setattr(
        module.uvicorn,
        "run",
        lambda app, **kwargs: appels.append((app, kwargs)),
    )

    module.main(["--host", "0.0.0.0"])

    assert appels[0][1]["host"] == "0.0.0.0"
    assert appels[0][1]["port"] == 8000


def test_port_explicite_via_cli(monkeypatch, module_run):
    module, _, application = module_run
    appels = []

    monkeypatch.setattr(module, "_application", lambda: application)
    monkeypatch.setattr(
        module.uvicorn,
        "run",
        lambda app, **kwargs: appels.append((app, kwargs)),
    )

    module.main(["--port", "9000"])

    assert appels[0][1]["port"] == 9000
    assert appels[0][1]["host"] == "127.0.0.1"


def test_configuration_des_proxies_preservee_avec_hote_explicite(module_run):
    module, reglages, _ = module_run
    proxies = ["10.0.0.1", "10.0.1.0/24"]
    reglages.TRUSTED_PROXY_IPS = proxies

    parametres = module.parametres_uvicorn(host="0.0.0.0")

    assert parametres["proxy_headers"] is True
    assert parametres["forwarded_allow_ips"] == proxies


def test_proxies_vides_restent_desactives_avec_hote_explicite(module_run):
    module, reglages, _ = module_run
    reglages.TRUSTED_PROXY_IPS = []

    parametres = module.parametres_uvicorn(host="0.0.0.0")

    assert parametres["proxy_headers"] is False
    assert parametres["forwarded_allow_ips"] == []
