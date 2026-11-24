"""Runtime de readiness PostgreSQL, isolé du moteur métier.

Limites réelles conservées explicitement :

* ``connect_timeout`` borne la phase de connexion selon les possibilités de
  libpq (avec un plancher de 2 secondes côté psycopg/libpq) ;
* ``statement_timeout`` est une limite **côté serveur** : il ne peut annuler
  ``SELECT 1`` que si PostgreSQL a réellement reçu la requête ;
* un trou noir réseau après l'envoi de la requête peut donc encore bloquer le
  thread ; les keepalives éventuels ne sont pas une garantie stricte ;
* le délai global HTTP ne tue pas un thread PostgreSQL : il arrête seulement
  l'attente côté client ;
* ``concurrent.futures.ThreadPoolExecutor`` n'a pas de gestionnaire ``atexit``
  personnalisé ici. Le standard library enregistre déjà ``_python_exit()``,
  qui joint les threads workers à la sortie du processus. Un thread encore
  bloqué peut donc retarder cette sortie.
"""

from __future__ import annotations

import concurrent.futures
import threading
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool


DELAI_CONNEXION_SECONDS = 2
STATEMENT_TIMEOUT_MS = 2000

_PARAMETRES_IMPOSES = frozenset({"statement_timeout", "connect_timeout"})
_DRAPEAUX_GENERIQUES = frozenset({"-c", "--set"})


def _decouper_options(options: str) -> list[tuple[str, str]]:
    """Découpe ``options`` en (jeton brut, valeur décodée), citations incluses."""
    jetons: list[tuple[str, str]] = []
    index = 0
    taille = len(options)

    while index < taille:
        while index < taille and options[index].isspace():
            index += 1
        if index >= taille:
            break

        debut = index
        valeur: list[str] = []
        guillemet: str | None = None
        while index < taille:
            caractere = options[index]
            if caractere == "\\" and index + 1 < taille:
                valeur.append(options[index + 1])
                index += 2
                continue
            if guillemet is None:
                if caractere.isspace():
                    break
                if caractere in ("'", '"'):
                    guillemet = caractere
                    index += 1
                    continue
                valeur.append(caractere)
                index += 1
                continue
            if caractere == guillemet:
                guillemet = None
                index += 1
                continue
            valeur.append(caractere)
            index += 1

        jetons.append((options[debut:index], "".join(valeur)))

    return jetons


def _nom_parametre(valeur: str) -> str | None:
    """Renvoie le nom du paramètre visé par un jeton libpq, sinon ``None``."""
    texte = valeur.strip()
    if not texte:
        return None

    if texte.startswith("--set="):
        reste = texte[len("--set=") :]
        if "=" not in reste:
            return None
        return reste.split("=", 1)[0].strip().lower()

    if texte.startswith("--set "):
        texte = texte[len("--set ") :].strip()
    elif texte.startswith("-c "):
        texte = texte[len("-c ") :].strip()

    if "=" not in texte:
        return None

    gauche = texte.split("=", 1)[0].strip()
    for prefixe in ("--", "-c"):
        if gauche.startswith(prefixe):
            gauche = gauche[len(prefixe) :]
            break
    return gauche.strip().lower()


def _est_parametre_impose(valeur: str) -> bool:
    return _nom_parametre(valeur) in _PARAMETRES_IMPOSES


def _est_drapeau_generique(valeur: str) -> bool:
    return valeur.strip() in _DRAPEAUX_GENERIQUES


def _retirer_parametres_imposes(
    jetons: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    conserves: list[tuple[str, str]] = []
    index = 0
    while index < len(jetons):
        brut, valeur = jetons[index]
        if _est_parametre_impose(valeur):
            index += 1
            continue
        if _est_drapeau_generique(valeur):
            if index + 1 < len(jetons) and _est_parametre_impose(
                jetons[index + 1][1]
            ):
                index += 2
                continue
        conserves.append((brut, valeur))
        index += 1
    return conserves


def _fusionner_options(options_existantes: object) -> str:
    """Conserve les options libpq utiles et force nos deux paramètres imposés."""
    options = "" if options_existantes is None else str(options_existantes)
    conserves = _retirer_parametres_imposes(_decouper_options(options))
    parties = [brut for brut, _ in conserves]
    parties.append(f"-c statement_timeout={STATEMENT_TIMEOUT_MS}")
    return " ".join(parties)


def creer_moteur_readiness(database_url: str) -> Engine:
    """Crée le moteur dédié aux sondes, sans jamais toucher au moteur métier."""
    url = make_url(database_url)
    options_existantes: list[object] = []
    requete: dict[str, Any] = {}

    for cle, valeur in url.query.items():
        nom = str(cle).lower()
        if nom == "options":
            options_existantes.append(valeur)
        elif nom in _PARAMETRES_IMPOSES:
            continue
        else:
            requete[str(cle)] = valeur

    options_fusionnees = " ".join(str(valeur) for valeur in options_existantes)
    url = url.set(query=requete)
    connect_args = {
        "connect_timeout": DELAI_CONNEXION_SECONDS,
        "options": _fusionner_options(options_fusionnees),
    }
    return create_engine(
        url,
        poolclass=NullPool,
        connect_args=connect_args,
        echo=False,
    )


def _select_1_ready(moteur: Engine) -> bool:
    """Exécute SELECT 1 et renvoie toujours un booléen, jamais une exception."""
    try:
        with moteur.connect() as connexion:
            connexion.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _callback_disposition(moteur: Engine) -> Any:
    """Construit un callback idempotent qui ne propage pas d'erreur de dispose."""
    disposition_faite = False

    def disposer(_future: object) -> None:
        nonlocal disposition_faite
        if disposition_faite:
            return
        disposition_faite = True
        try:
            moteur.dispose()
        except Exception:
            # Une panne de dispose ne doit jamais fuir dans les callbacks.
            pass

    return disposer


class RuntimeReadiness:
    """État de concurrence process-level d'une sonde PostgreSQL de readiness."""

    def __init__(self) -> None:
        self._verrou = threading.Lock()
        # Un seul thread de sonde par processus, quel que soit le nombre de
        # boucles asyncio ou de cycles lifespan.
        self._executeur = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="edunova-ready-db",
        )
        self._moteur: Engine | None = None
        self._future_db: concurrent.futures.Future[bool] | None = None
        self._actif = False

    @property
    def executeur(self) -> concurrent.futures.ThreadPoolExecutor:
        return self._executeur

    @property
    def moteur(self) -> Engine | None:
        return self._moteur

    @property
    def future_db(self) -> concurrent.futures.Future[bool] | None:
        return self._future_db

    @property
    def actif(self) -> bool:
        return self._actif

    def demarrer(self, database_url: str) -> None:
        """Active le runtime et crée le moteur dédié au premier démarrage."""
        with self._verrou:
            if self._moteur is None:
                self._moteur = creer_moteur_readiness(database_url)
            self._actif = True

    def arreter(self) -> None:
        """Désactive les soumissions et dispose le moteur sans fermer l'executor."""
        with self._verrou:
            self._actif = False
            moteur, future = self._moteur, self._future_db
            self._moteur = None

        if moteur is None:
            return

        if future is None or future.done():
            moteur.dispose()
            return

        # Le thread utilise encore CE moteur : la disposition attend la fin
        # réelle du Future, pas la fin de la requête HTTP.
        future.add_done_callback(_callback_disposition(moteur))

    def soumettre(self) -> concurrent.futures.Future[bool] | None:
        """Crée ou réutilise l'unique Future de sonde DB réellement en cours."""
        with self._verrou:
            if not self._actif or self._moteur is None:
                return None

            future = self._future_db
            if future is None or future.done():
                moteur = self._moteur
                try:
                    future = self._executeur.submit(_select_1_ready, moteur)
                except RuntimeError:
                    # Executor fermé par la procédure de sortie de CPython.
                    return None
                self._future_db = future
            return future


RUNTIME_READINESS = RuntimeReadiness()
