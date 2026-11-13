from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.application import Application
from app.schemas.application import ApplicationCreate, ApplicationResponse

from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationList,
)



router = APIRouter(
    prefix="/applications",
    tags=["Candidatures"],
)


@router.post(
    "/",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_application(
    application_data: ApplicationCreate,
    db: Session = Depends(get_db),
):
    existing_application = db.query(Application).filter(
        Application.email == application_data.email
    ).first()

    if existing_application:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une candidature existe déjà avec cette adresse e-mail.",
        )

    new_application = Application(
        **application_data.model_dump(),
    )

    db.add(new_application)
    db.commit()
    db.refresh(new_application)

    return new_application




@router.get(
    "/",
    response_model=ApplicationList,
)
def get_applications(
    db: Session = Depends(get_db),
):
    candidatures = db.query(Application).order_by(
        Application.date_candidature.desc()
    ).all()

    return {
        "total": len(candidatures),
        "candidatures": candidatures,
    }
