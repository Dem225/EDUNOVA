"""Protection ASGI contre les corps de requête HTTP excessivement volumineux.

Fonctionnement
--------------
* Un en-tête ``Content-Length`` supérieur à la limite est rejeté immédiatement,
  sans lire le corps.
* Sinon, les morceaux du corps sont comptés au fur et à mesure. Le premier
  morceau qui fait dépasser la limite provoque une réponse ``413`` ; les
  morceaux suivants ne sont pas lus.
* Une requête acceptée est mise en mémoire (au plus ``limit`` octets) puis
  rejouée à FastAPI avec un ``receive`` conforme au protocole ASGI.

Limites
-------
* Cette protection limite uniquement la taille du corps. Elle ne limite ni le
  nombre de requêtes, ni la durée d'une connexion (slowloris).
* ``Content-Length`` est indicatif : il peut être absent, invalide ou faux.
  Le comptage réel des octets reçus reste l'autorité.
* Le middleware doit être enregistré APRÈS ``CORSMiddleware`` dans ``main.py``
  afin que les réponses ``413`` reçoivent aussi les en-têtes CORS.
* Aucun corps, email ou autre donnée personnelle n'est journalisé.
"""

import json
from typing import Any


MESSAGE_TAILLE_MAXIMALE = "La requête dépasse la taille maximale autorisée."


class BodyLimitMiddleware:
    """Rejette les requêtes HTTP dont le corps dépasse ``limit`` octets."""

    def __init__(self, app: Any, limit: int) -> None:
        if limit <= 0:
            raise ValueError("La limite de taille doit être strictement positive.")
        self.app = app
        self.limit = limit

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        if self._content_length_depasse(scope):
            await self._rejet(send)
            return

        corps = bytearray()
        while True:
            message = await receive()
            type_message = message.get("type")

            if type_message == "http.disconnect":
                return
            if type_message != "http.request":
                continue

            morceau = message.get("body") or b""
            corps.extend(morceau)

            if len(corps) > self.limit:
                await self._rejet(send)
                return

            if not message.get("more_body", False):
                break

        corps_a_livrer = bytes(corps)
        deja_livre = False

        async def receive_limite() -> dict[str, Any]:
            nonlocal deja_livre
            if not deja_livre:
                deja_livre = True
                return {
                    "type": "http.request",
                    "body": corps_a_livrer,
                    "more_body": False,
                }
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, receive_limite, send)

    def _content_length_depasse(self, scope: dict[str, Any]) -> bool:
        for nom, valeur in scope.get("headers", []):
            if nom.lower() == b"content-length":
                try:
                    return int(valeur) > self.limit
                except (TypeError, ValueError):
                    return False
        return False

    async def _rejet(self, send: Any) -> None:
        corps = json.dumps(
            {"detail": MESSAGE_TAILLE_MAXIMALE},
            ensure_ascii=False,
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(corps)).encode("ascii")),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": corps})
