from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.applications import router as applications_router


app = FastAPI(
    title="EDUNOVA API",
    description="API du projet éducatif EDUNOVA",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
async def accueil():
    return {
        "message": "Bienvenue sur EDUNOVA",
        "projet": "EDUNOVA",
        "statut": "API opérationnelle",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


app.include_router(applications_router)
