"""Runtime settings loaded from environment variables and the local .env file.

Secrets are stored as SecretStr so they never appear in repr() or logs.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LAB1_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = LAB1_DIR.parent

# Secrets the pipeline needs. Names follow the official SDK conventions.
SECRET_VARS = (
    "GEMINI_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "VOYAGE_API_KEY",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", LAB1_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: SecretStr | None = None
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    voyage_api_key: SecretStr | None = None
    github_token: SecretStr | None = None

    qdrant_url: str | None = None
    qdrant_path: Path = Field(default=LAB1_DIR / "data" / "index" / "qdrant")
    data_dir: Path = Field(default=LAB1_DIR / "data")

    @field_validator(
        "gemini_api_key",
        "langfuse_public_key",
        "langfuse_secret_key",
        "voyage_api_key",
        "github_token",
        mode="before",
    )
    @classmethod
    def _blank_secret_is_missing(cls, value):
        """`KEY=` copied from .env.example means "not set", not an empty key (review F4)."""
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def secret_status(self) -> dict[str, bool]:
        """Report which secrets are present without exposing their values."""
        return {name: getattr(self, name.lower()) is not None for name in SECRET_VARS}


def load_settings() -> Settings:
    return Settings()
