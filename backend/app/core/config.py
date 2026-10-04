"""Application settings.

All configuration is read from the environment (12-factor) and validated once at boot.
Environment-specific values (DSNs, URLs, hosts, credentials, model names, directories) have no
defaults: if one is missing the process refuses to start. Only operational tunables (timeouts,
limits, budgets) carry defaults, and every one of them can be overridden.
Nested groups map to env vars with a double underscore, e.g. ``LLM__BACKENDS__GROQ__MODEL``.
"""

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_PREFIX = "/api/v1"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ApiSettings(BaseModel):
    cors_origins: list[str]
    bootstrap_api_key: SecretStr
    requests_per_minute: int = 120
    burst: int = 20
    key_cache_ttl_seconds: int = 300
    sse_ping_seconds: int = 15
    idempotency_ttl_seconds: int = 86_400
    page_size_default: int = 20
    page_size_max: int = 100


class DatabaseSettings(BaseModel):
    url: SecretStr
    pool_size: int = 10
    max_overflow: int = 5
    pool_timeout_seconds: float = 10.0
    # Fail fast when Postgres is unreachable instead of hanging on the TCP connect.
    connect_timeout_seconds: float = 5.0
    echo: bool = False


class RedisSettings(BaseModel):
    url: SecretStr
    queue_name: str = "operator:runs"
    connect_timeout_seconds: float = 5.0
    run_lock_ttl_seconds: int = 1200
    events_channel_prefix: str = "operator:run-events"


class LLMBackendSettings(BaseModel):
    """One OpenAI-compatible chat endpoint (Groq, Gemini and Ollama all expose one)."""

    base_url: str
    model: str
    api_key: SecretStr | None = None
    # Local servers (e.g. Ollama) need no key; hosted ones are skipped when the key is missing.
    requires_api_key: bool = True
    requests_per_minute: int = 30
    # Providers that cap tokens per minute (e.g. Groq free tier): reserve before sending.
    tokens_per_minute: int | None = None
    burst: int = 3
    max_concurrency: int = 2
    timeout_seconds: float = 60.0
    # Some local reasoning models emit a hidden chain of thought before the answer.
    strip_reasoning: bool = True
    # Provider-specific request fields, e.g. {"reasoning_effort": "none"} for Gemini.
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        return not self.requires_api_key or bool(self.api_key and self.api_key.get_secret_value())


class LLMSettings(BaseModel):
    backends: dict[str, LLMBackendSettings]
    # Failover order: first healthy backend wins. Every name must exist in ``backends``.
    providers: list[str]
    temperature: float = 0.0
    max_output_tokens: int = 2048
    max_repair_attempts: int = 2
    cache_ttl_seconds: int = 86_400
    rate_limit_wait_seconds: float = 5.0

    @model_validator(mode="after")
    def _providers_are_configured(self) -> "LLMSettings":
        missing = [name for name in self.providers if name not in self.backends]
        if missing:
            raise ValueError(f"LLM providers without backend settings: {missing}")
        if not self.providers:
            raise ValueError("At least one LLM provider must be configured")
        return self


class AgentSettings(BaseModel):
    max_steps: int = 40
    max_replans: int = 3
    max_llm_tokens: int = 250_000
    max_duration_seconds: int = 900
    action_timeout_seconds: float = 30.0
    history_window: int = 6
    max_identical_actions: int = 3
    max_consecutive_failures: int = 4
    observation_char_budget: int = 6_000
    context_top_k: int = 3
    memory_top_k: int = 5
    checkpoint_history_limit: int = 30
    llm_unavailable_retry_seconds: int = 30
    worker_grace_seconds: int = 60
    worker_max_tries: int = 5
    worker_concurrency: int = 2
    job_result_ttl_seconds: int = 3600
    # Formats the verifier accepts when comparing dates across systems (first match wins).
    date_formats: list[str] = Field(
        default_factory=lambda: ["%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y", "%d %B %Y", "%d %b %Y"]
    )


class BrowserSettings(BaseModel):
    headless: bool = True
    navigation_timeout_seconds: float = 20.0
    viewport_width: int = 1280
    viewport_height: int = 900
    max_snapshot_elements: int = 120
    # Late-rendering pages: poll until the interactive element count stops changing.
    settle_timeout_seconds: float = 6.0
    settle_interval_ms: int = 400


class ResilienceSettings(BaseModel):
    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 8.0
    breaker_failure_threshold: int = 5
    breaker_reset_seconds: float = 30.0
    host_requests_per_second: float = 5.0
    host_burst: int = 10
    host_rate_wait_seconds: float = 30.0


class SystemCredential(BaseModel):
    username: str
    password: SecretStr


class PathSettings(BaseModel):
    company_context_dir: Path
    evidence_dir: Path
    workspace_dir: Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Environment
    service_name: str = "operator-backend"
    log_level: str = "INFO"

    api: ApiSettings
    database: DatabaseSettings
    redis: RedisSettings
    llm: LLMSettings
    paths: PathSettings
    agent: AgentSettings = Field(default_factory=AgentSettings)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    # Keyed by the credential name referenced in company_context/profile.yaml.
    credentials: dict[str, SystemCredential] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _lock_outlives_run(self) -> "Settings":
        # A run lock that expires mid-run would let a second worker pick the run up.
        minimum = self.agent.max_duration_seconds + self.agent.worker_grace_seconds
        if self.redis.run_lock_ttl_seconds < minimum:
            raise ValueError(f"REDIS__RUN_LOCK_TTL_SECONDS must be >= {minimum}")
        return self

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        return value.upper()


def environment_variables(env_file: Path = Path(".env")) -> dict[str, str]:
    """Process environment layered over the .env file (process wins), for ${VAR} references
    in company_context files."""
    from_file = {key: value for key, value in dotenv_values(env_file).items() if value is not None}
    return {**from_file, **os.environ}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required fields come from the environment
