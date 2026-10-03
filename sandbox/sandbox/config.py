"""Sandbox settings. Secrets and locations are required from the environment (no defaults);
chaos knobs are operational tunables with documented defaults."""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChaosSettings(BaseModel):
    enabled: bool = False
    seed: int = 0
    error_rate: float = 0.15
    slow_rate: float = 0.2
    slow_ms: int = 1500
    render_delay_ms: int = 1200
    session_max_requests: int = 25
    alt_labels: bool = True
    # First successful create is committed but answered with a 502, so a naive retry duplicates.
    duplicate_trap: bool = False


class AppSettings(BaseModel):
    session_secret: SecretStr
    portal_username: str
    portal_password: SecretStr
    erp_username: str
    erp_password: SecretStr
    erp_api_token: SecretStr
    data_dir: Path


class SandboxSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="__", extra="ignore", env_file_encoding="utf-8"
    )

    sandbox: AppSettings
    chaos: ChaosSettings = Field(default_factory=ChaosSettings)


@lru_cache
def get_settings() -> SandboxSettings:
    return SandboxSettings()  # required fields come from the environment
