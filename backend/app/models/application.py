
from datetime import datetime
from app.models.application_status import ApplicationStatus

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    prenom: Mapped[str] = mapped_column(String(150), nullable=False)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    telephone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    niveau: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    motivation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    statut: Mapped[str] = mapped_column(
   	 String(30),
   	 default=ApplicationStatus.EN_ATTENTE.value,
   	 nullable=False,
   )

    date_candidature: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
