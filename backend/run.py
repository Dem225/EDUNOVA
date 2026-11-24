"""Point de lancement programmatique d'Uvicorn pour EDUNOVA.

Depuis la racine du dépôt, en PowerShell ::

    uv run python backend/run.py

L'écoute par défaut est ``127.0.0.1:8000`` (développement local). Pour un
reverse proxy distant nécessitant toutes les interfaces ::

    uv run python backend/run.py --host 0.0.0.0 --port 8000

Les adresses autorisées à fournir ``X-Forwarded-*`` sont lues directement dans
les paramètres validés de ``backend/app/core/config.py`` (``TRUSTED_PROXY_IPS``)
et transmises à Uvicorn via ``forwarded_allow_ips``. Il n'y a donc aucune
recopie manuelle des IP dans la ligne de commande. ``proxy_headers`` n'est
activé que si cette liste est non vide : le développement local sans proxy
conserve son fonctionnement habituel.

Le joker ``*`` est refusé ici aussi, en défense en profondeur, même si la
configuration EDUNOVA l'interdit déjà. Aucun serveur n'est démarré lors de
l'importation : ``parametres_uvicorn`` est une fonction pure, utilisable par
les tests sans ouvrir de socket réseau.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import uvicorn


# Permet l'import des modules ``app.*`` quelle que soit la racine d'invocation.
RACINE_BACKEND = Path(__file__).resolve().parent
if str(RACINE_BACKEND) not in sys.path:
    sys.path.insert(0, str(RACINE_BACKEND))

HOTE_LOCAL = "127.0.0.1"
PORT_DEFAUT = 8000


def _settings() -> Any:
    """Retourne l'instance unique des paramètres validés d'EDUNOVA."""
    from app.core.config import settings

    return settings


def _application() -> Any:
    """Retourne l'instance FastAPI existante, sans en créer une seconde."""
    from app.main import app

    return app


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les options de lancement, sans modifier la configuration."""
    parseur = argparse.ArgumentParser(
        description="Lance l'API EDUNOVA avec Uvicorn."
    )
    parseur.add_argument(
        "--host",
        default=HOTE_LOCAL,
        help=(
            "Adresse d'écoute (127.0.0.1 par défaut ; 0.0.0.0 uniquement "
            "si un reverse proxy distant le nécessite)."
        ),
    )
    parseur.add_argument(
        "--port",
        type=int,
        default=PORT_DEFAUT,
        help="Port d'écoute (8000 par défaut).",
    )
    return parseur.parse_args(argv)


def parametres_uvicorn(
    reglages: Any | None = None,
    *,
    host: str = HOTE_LOCAL,
    port: int = PORT_DEFAUT,
) -> dict[str, Any]:
    """Construit les arguments Uvicorn depuis la configuration EDUNOVA."""
    if reglages is None:
        reglages = _settings()

    proxies = list(reglages.TRUSTED_PROXY_IPS)
    if "*" in proxies:
        raise ValueError("Le joker '*' est interdit dans TRUSTED_PROXY_IPS.")

    return {
        "host": host,
        "port": port,
        "proxy_headers": bool(proxies),
        "forwarded_allow_ips": proxies,
    }


def main(argv: list[str] | None = None) -> None:
    """Lance l'application FastAPI existante avec les paramètres EDUNOVA."""
    args = _arguments(argv)
    uvicorn.run(
        _application(),
        **parametres_uvicorn(host=args.host, port=args.port),
    )


if __name__ == "__main__":
    main()
