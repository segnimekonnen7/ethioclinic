"""
Centralized application settings.

Using typed settings keeps configuration explicit and safe across local/dev/prod.
"""

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ethioclinic",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    jwt_secret: str = Field(default="", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiry_minutes: int = Field(default=60, alias="JWT_EXPIRY_MINUTES")
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    auth_rate_limit_per_minute: int = Field(default=10, alias="AUTH_RATE_LIMIT_PER_MINUTE")

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        allowed = {"development", "test", "staging", "production"}
        normalized = value.lower().strip()
        if normalized not in allowed:
            raise ValueError(f"APP_ENV must be one of {sorted(allowed)}")
        return normalized

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_production_safety(self) -> None:
        if self.is_production and (not self.jwt_secret or self.jwt_secret == "dev-secret-change-in-production"):
            raise ValueError("JWT_SECRET must be set to a strong secret in production.")

        if self.is_production and not self.cors_origins_list:
            raise ValueError("CORS_ORIGINS must be configured in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
