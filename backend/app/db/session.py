
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


# Moteur de connexion PostgreSQL
engine = create_engine(
    settings.DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
)


# Gestion des sessions
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# Classe de base des modèles SQLAlchemy
class Base(DeclarativeBase):
    pass


# Dépendance pour les routes FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
