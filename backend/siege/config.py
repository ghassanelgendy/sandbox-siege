"""Runtime configuration. All secrets come from .env (PRD NFR-5)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "runs"
SEEDED_DIR = RUNS_DIR / "seeded"
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", Path(".env")),
        extra="ignore",
        protected_namespaces=(),
    )

    # LocalStack
    aws_endpoint_url: str = "http://localhost:4566"
    aws_default_region: str = "us-east-1"
    localstack_auth_token: str = ""

    # Providers
    bynara_base_url: str = "https://router.bynara.id/v1"
    bynara_api_key: str = ""
    dahl_base_url: str = "https://inference.dahl.global/v1"
    dahl_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: str = ""

    # Runtime
    siege_max_steps: int = 25
    siege_scenario_timeout_s: int = 180
    siege_api_timeout_s: int = 60
    siege_threshold: float = 80.0

    # Carbon coefficients — displayed in the UI, never hidden (PRD FR-7.5)
    watts_per_vcpu: float = 12.0
    grid_gco2e_per_kwh: float = 462.0

    def provider_config(self, provider: str) -> tuple[str, str]:
        """Return (base_url, api_key) for a provider name."""
        table = {
            "bynara": (self.bynara_base_url, self.bynara_api_key),
            "dahl": (self.dahl_base_url, self.dahl_api_key),
            "groq": (self.groq_base_url, self.groq_api_key),
            "insecure": ("http://localhost", "mock-insecure-key"),
        }
        if provider not in table:
            raise ValueError(f"Unknown provider {provider!r}; expected one of {sorted(table)}")
        return table[provider]


settings = Settings()

RUNS_DIR.mkdir(parents=True, exist_ok=True)
SEEDED_DIR.mkdir(parents=True, exist_ok=True)
