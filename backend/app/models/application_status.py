from enum import Enum


class ApplicationStatus(str, Enum):
    EN_ATTENTE = "en_attente"
    EN_EXAMEN = "en_examen"
    ACCEPTEE = "acceptee"
    LISTE_ATTENTE = "liste_attente"
    REFUSEE = "refusee"
