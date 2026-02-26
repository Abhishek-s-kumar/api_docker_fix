"""
WRD API v2.0.0 — Application Configuration
All settings loaded from environment variables or Docker Secrets files.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret_file(path: str | None) -> str | None:
    """Read a Docker Secret from a file path."""
    if path and Path(path).exists():
        return Path(path).read_text().strip()
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    environment: str = Field(default="development")
    app_name: str = Field(default="Wazuh Rules Distribution API")
    app_version: str = Field(default="2.0.0")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # ── API Server ───────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    workers: int = Field(default=4)
    reload: bool = Field(default=False)

    # ── Database ─────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://api:password@postgres:5432/wazuh_api"
    )
    database_pool_size: int = Field(default=20)
    database_max_overflow: int = Field(default=10)

    # ── Security ─────────────────────────────────────────────
    secret_key: str = Field(default="changeme-replace-in-production")
    jwt_secret: str = Field(default="changeme-replace-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60)
    admin_key_file: str = Field(default="/data/admin_key.txt")

    # ── Secret file paths (Docker Secrets) ───────────────────
    secret_key_file: str | None = Field(default=None)
    jwt_secret_file: str | None = Field(default=None)
    db_password_file: str | None = Field(default=None)

    # ── Git ──────────────────────────────────────────────────
    git_repo_path: str = Field(default="/app/git-repo")
    git_remote_url: str = Field(default="")
    git_branch: str = Field(default="main")
    git_sync_interval: int = Field(default=300)
    git_verify_signatures: bool = Field(default=False)

    # ── Rules ────────────────────────────────────────────────
    rules_base_path: str = Field(default="/app/git-repo")
    rules_package_dir: str = Field(default="/tmp/rule-packages")
    max_package_size_mb: int = Field(default=50)

    # ── CORS ─────────────────────────────────────────────────
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://localhost:8000"]
    )
    cors_allow_credentials: bool = Field(default=True)

    # ── Rate Limiting ────────────────────────────────────────
    rate_limit_per_minute: int = Field(default=60)
    rate_limit_burst: int = Field(default=20)

    @model_validator(mode="after")
    def load_docker_secrets(self) -> "Settings":
        """Override settings from Docker Secrets files if present."""
        if secret := _read_secret_file(self.secret_key_file):
            self.secret_key = secret
        if secret := _read_secret_file(self.jwt_secret_file):
            self.jwt_secret = secret
        if db_pass := _read_secret_file(self.db_password_file):
            # Replace password in DATABASE_URL
            if "changeme" in self.database_url or "password" in self.database_url:
                import re
                self.database_url = re.sub(
                    r"(?<=://[^:]+:)[^@]+(?=@)", db_pass, self.database_url
                )
        return self

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
