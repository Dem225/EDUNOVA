from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.rate_limit import (
    RateLimitUnavailable,
    erreur_email,
    erreur_indisponible,
)
from app.db.session import get_db
from app.models.application import Application
from app.schemas.application import (
    ApplicationAcknowledgement,
    ApplicationCreate,
)


router = APIRouter(
    prefix="/applications",
    tags=["Candidatures"],
)

MESSAGE_ACCUSE_DE_RECEPTION = (
    "Votre demande a bien été prise en compte. "
    "Si nécessaire, notre équipe vous contactera."
)
CONTRAINTE_EMAIL_UNIQUE = "ix_applications_email"


def reponse_generique() -> dict[str, str]:
    return {"message": MESSAGE_ACCUSE_DE_RECEPTION}


def est_violation_unicite_email(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None) == CONTRAINTE_EMAIL_UNIQUE


@router.post(
    "/",
    response_model=ApplicationAcknowledgement,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_application(
    application_data: ApplicationCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    email_normalise = application_data.email.lower()

    limiteur = request.app.state.rate_limiter
    try:
        decision_email = await limiteur.verifier_email(email_normalise)
    except RateLimitUnavailable:
        raise erreur_indisponible()
    if not decision_email.autorise:
        raise erreur_email(decision_email)

    existing_application = db.query(Application).filter(
        func.lower(Application.email) == email_normalise
    ).first()

    if existing_application:
        return reponse_generique()

    donnees_application = application_data.model_dump()
    donnees_application["email"] = email_normalise

    new_application = Application(
        **donnees_application,
    )

    db.add(new_application)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if est_violation_unicite_email(exc):
            return reponse_generique()
        raise

    return reponse_generique()
