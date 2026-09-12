# core/config.py - Validated environment configuration without committed secrets.
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Keep local demo and production timeouts explicitly separate."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")
    database_url: str = "sqlite:///./trail.db"
    jwt_secret: str = ""
    trail_agent_mode: Literal["mock", "bedrock"] = "mock"
    aws_region: str = "us-west-2"
    bedrock_model_id: str = "global.anthropic.claude-sonnet-4-6"
    demo_mode: bool = True
    checkin_timeout_seconds: int = Field(default=15, ge=3)
    production_checkin_timeout_seconds: int = Field(default=120, ge=60)
    stop_threshold_seconds: int = Field(default=120, ge=30)
    community_radius_km: float = Field(default=2, ge=0.5, le=10)
    community_risk_threshold: int = Field(default=60, ge=0, le=100)
    route_retention_days: int = Field(default=10, ge=1, le=10)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cookie_secure: bool = False

    @model_validator(mode="after")
    def validate_secret(self):
        """Fail closed when the signing key is missing or a known placeholder."""
        if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("change-me"):
            raise ValueError("Set JWT_SECRET to a randomly generated secret of at least 32 characters")
        return self


settings = Settings()
