
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.application_status import ApplicationStatus


class ApplicationCreate(BaseModel):
    nom: str = Field(min_length=2, max_length=100)
    prenom: str = Field(min_length=2, max_length=150)
    email: EmailStr
    telephone: str | None = Field(default=None, max_length=30)

    niveau: Literal[
        "primaire",
        "college",
        "lycee",
        "universite",
        "formation_professionnelle",
    ]

    motivation: str = Field(min_length=20)


class ApplicationResponse(BaseModel):
    id: int
    nom: str
    prenom: str
    email: EmailStr
    telephone: str | None
    niveau: str
    motivation: str
    statut: str
    date_candidature: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationList(BaseModel):
    total: int
    candidatures: list[ApplicationResponse]


class ApplicationStatusUpdate(BaseModel):
    statut: ApplicationStatus

