"""Extraction sécurisée de l'adresse IP client.

L'adresse de référence est uniquement ``request.client.host`` : l'application
ne parse jamais ``X-Forwarded-For``. La prise en compte des proxies est
configurée au niveau d'Uvicorn avec ``--proxy-headers`` et
``--forwarded-allow-ips``, dont la liste doit être explicitement déclarée dans
la configuration de déploiement (jamais ``*``).
"""

import ipaddress
from typing import Any


class ClientIPError(Exception):
    """Adresse client absente ou invalide."""


def normaliser_ip(valeur: Any) -> str:
    """Normalise une adresse IP (IPv4 ou IPv6) sous forme compressée."""
    if not isinstance(valeur, str) or not valeur.strip():
        raise ClientIPError("Adresse IP absente.")

    try:
        return ipaddress.ip_address(valeur.strip()).compressed
    except ValueError as exc:
        raise ClientIPError("Adresse IP invalide.") from exc


def obtenir_ip_client(request: Any) -> str:
    """Retourne l'IP normalisée depuis ``request.client.host`` uniquement."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return normaliser_ip(host)
