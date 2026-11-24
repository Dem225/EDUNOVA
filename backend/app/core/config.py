import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Le fichier .env reste à la racine du dépôt, quelle que soit la commande lancée.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

APP_ENV_ALIASES = {
    "dev": "development",
    "development": "development",
    "local": "development",
    "stage": "staging",
    "staging": "staging",
    "prod": "production",
    "production": "production",
}


class Settings(BaseSettings):
    APP_NAME: str = "EDUNOVA"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DATABASE_URL: str

    SECRET_KEY: SecretStr | None = None
    INSTALLATION_TOKEN: SecretStr | None = None

    SQL_ECHO: bool = False
    DOCS_ENABLED: bool = True

    # Limite maximale du corps des requêtes HTTP, en octets (32 Kio).
    MAX_REQUEST_BODY_BYTES: int = 32_768

    # Rate limiting des candidatures.
    RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"
    RATE_LIMIT_IP_MAX: int = 5
    RATE_LIMIT_IP_WINDOW_SECONDS: int = 60
    RATE_LIMIT_EMAIL_MAX: int = 3
    RATE_LIMIT_EMAIL_WINDOW_SECONDS: int = 900

    REDIS_URL: SecretStr | None = None
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 0.5
    REDIS_SOCKET_TIMEOUT: float = 0.5
    REDIS_HEALTH_CHECK_INTERVAL: int = 30

    # Secret dédié au HMAC des identifiants de limitation.
    # La rotation de ce secret réinitialise les compteurs actifs.
    RATE_LIMIT_HMAC_SECRET: SecretStr | None = None
    # IP/CIDR des proxies autorisés à fournir X-Forwarded-* à Uvicorn.
    # Le joker "*" est interdit.
    TRUSTED_PROXY_IPS: list[str] = []

    CORS_ORIGINS: list[str] = [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
    ]

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    INVITATION_EXPIRE_HOURS: int = 24

    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_ISSUER: str = "edunova-api"
    JWT_AUDIENCE: str = "edunova-admin"
    JWT_LEEWAY_SECONDS: int = 30
    JWT_KEY_VERSION: int = 1

    ARGON2_MEMORY_COST: int = 65_536
    ARGON2_TIME_COST: int = 3
    ARGON2_PARALLELISM: int = 4
    PASSWORD_MIN_LENGTH: int = 14

    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    RATE_LIMIT_RESET_PER_HOUR: int = 3
    RATE_LIMIT_APPLICATIONS_PER_MINUTE: int = 5

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("APP_ENV", mode="before")
    @classmethod
    def normaliser_app_env(cls, valeur: object) -> object:
        if isinstance(valeur, str):
            normalisee = APP_ENV_ALIASES.get(valeur.strip().lower())
            if normalisee is not None:
                return normalisee
        return valeur

    @model_validator(mode="after")
    def valider_par_environnement(self) -> "Settings":
        if not self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS ne peut pas être vide.")

        if self.APP_ENV == "production" and "*" in self.CORS_ORIGINS:
            raise ValueError("Le joker CORS '*' est interdit en production.")

        for nom in (
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            "REFRESH_TOKEN_EXPIRE_DAYS",
            "PASSWORD_RESET_EXPIRE_MINUTES",
            "INVITATION_EXPIRE_HOURS",
            "ARGON2_MEMORY_COST",
            "ARGON2_TIME_COST",
            "ARGON2_PARALLELISM",
            "PASSWORD_MIN_LENGTH",
            "MAX_REQUEST_BODY_BYTES",
            "RATE_LIMIT_IP_MAX",
            "RATE_LIMIT_IP_WINDOW_SECONDS",
            "RATE_LIMIT_EMAIL_MAX",
            "RATE_LIMIT_EMAIL_WINDOW_SECONDS",
            "REDIS_SOCKET_CONNECT_TIMEOUT",
            "REDIS_SOCKET_TIMEOUT",
            "REDIS_HEALTH_CHECK_INTERVAL",
            "MAX_LOGIN_ATTEMPTS",
            "ACCOUNT_LOCKOUT_MINUTES",
            "RATE_LIMIT_LOGIN_PER_MINUTE",
            "RATE_LIMIT_RESET_PER_HOUR",
            "RATE_LIMIT_APPLICATIONS_PER_MINUTE",
        ):
            if getattr(self, nom) <= 0:
                raise ValueError(f"{nom} doit être strictement positif.")

        if self.PASSWORD_MIN_LENGTH < 12:
            raise ValueError("PASSWORD_MIN_LENGTH doit être au moins 12.")

        if "*" in self.TRUSTED_PROXY_IPS:
            raise ValueError("Le joker '*' est interdit dans TRUSTED_PROXY_IPS.")

        for valeur in self.TRUSTED_PROXY_IPS:
            try:
                ipaddress.ip_network(valeur, strict=False)
            except ValueError as exc:
                raise ValueError(
                    "TRUSTED_PROXY_IPS ne contient que des adresses IP ou des CIDR valides."
                ) from exc

        if self.RATE_LIMIT_HMAC_SECRET is not None:
            secret_hmac = self.RATE_LIMIT_HMAC_SECRET.get_secret_value()
            if len(secret_hmac) < 32:
                raise ValueError(
                    "RATE_LIMIT_HMAC_SECRET doit contenir au moins 32 caractères."
                )
            secrets_interdits = (
                self.SECRET_KEY.get_secret_value()
                if self.SECRET_KEY is not None
                else None,
                self.INSTALLATION_TOKEN.get_secret_value()
                if self.INSTALLATION_TOKEN is not None
                else None,
            )
            if secret_hmac in secrets_interdits:
                raise ValueError(
                    "RATE_LIMIT_HMAC_SECRET doit être distinct de SECRET_KEY "
                    "et de INSTALLATION_TOKEN."
                )

        if self.RATE_LIMIT_BACKEND == "redis" and self.REDIS_URL is None:
            raise ValueError(
                "REDIS_URL est obligatoire lorsque le backend de limitation est redis."
            )

        if not self.JWT_ISSUER.strip():
            raise ValueError("JWT_ISSUER ne peut pas être vide.")

        if not self.JWT_AUDIENCE.strip():
            raise ValueError("JWT_AUDIENCE ne peut pas être vide.")

        if self.JWT_LEEWAY_SECONDS < 0:
            raise ValueError("JWT_LEEWAY_SECONDS ne peut pas être négatif.")

        if self.JWT_KEY_VERSION < 1:
            raise ValueError("JWT_KEY_VERSION doit être au moins 1.")

        if self.APP_ENV in {"staging", "production"}:
            if self.SECRET_KEY is None or len(self.SECRET_KEY.get_secret_value()) < 32:
                raise ValueError(
                    "SECRET_KEY est obligatoire et doit contenir au moins 32 caractères "
                    "hors développement."
                )
            if (
                self.INSTALLATION_TOKEN is None
                or len(self.INSTALLATION_TOKEN.get_secret_value()) < 32
            ):
                raise ValueError(
                    "INSTALLATION_TOKEN est obligatoire et doit contenir au moins "
                    "32 caractères hors développement."
                )
            if self.REDIS_URL is None:
                raise ValueError(
                    "REDIS_URL est obligatoire en staging et en production."
                )
            if self.RATE_LIMIT_BACKEND != "redis":
                raise ValueError(
                    "Le backend mémoire est interdit en staging et en production."
                )
            if self.RATE_LIMIT_HMAC_SECRET is None:
                raise ValueError(
                    "RATE_LIMIT_HMAC_SECRET est obligatoire en staging et en production."
                )

            self.SQL_ECHO = False

        if self.APP_ENV == "production":
            self.DOCS_ENABLED = False

        return self


settings = Settings()
