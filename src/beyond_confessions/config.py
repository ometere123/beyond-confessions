"""Configuration and spend guardrails.

Only environment variable names are documented here. Secret values are loaded at runtime and are
never included in configuration objects, logs, or generated artifacts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
INITIAL_TEST_CAP_USD = 0.50
OPENAI_CAP_USD = 2.00
MODAL_CAP_USD = 5.00


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True)
class ProjectConfig:
    """Non-secret runtime configuration."""

    model: str = DEFAULT_MODEL
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    initial_test_cap_usd: float = INITIAL_TEST_CAP_USD
    openai_cap_usd: float = OPENAI_CAP_USD
    modal_cap_usd: float = MODAL_CAP_USD

    @classmethod
    def from_environment(cls, *, dotenv_path: str | Path | None = None) -> ProjectConfig:
        if dotenv_path is not None:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        return cls(
            model=os.getenv("BEYOND_CONFESSIONS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            openai_base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip()
            or DEFAULT_OPENAI_BASE_URL,
            initial_test_cap_usd=_float_env("BEYOND_CONFESSIONS_INITIAL_TEST_CAP_USD", INITIAL_TEST_CAP_USD),
            openai_cap_usd=_float_env("BEYOND_CONFESSIONS_OPENAI_CAP_USD", OPENAI_CAP_USD),
            modal_cap_usd=_float_env("BEYOND_CONFESSIONS_MODAL_CAP_USD", MODAL_CAP_USD),
        )

    def validate_guardrails(self) -> None:
        if self.initial_test_cap_usd < 0 or self.initial_test_cap_usd > INITIAL_TEST_CAP_USD:
            raise ValueError(f"initial test cap must be between $0 and ${INITIAL_TEST_CAP_USD:.2f}")
        if self.openai_cap_usd < 0 or self.openai_cap_usd > OPENAI_CAP_USD:
            raise ValueError(f"OpenAI cap must be between $0 and ${OPENAI_CAP_USD:.2f}")
        if self.modal_cap_usd < 0 or self.modal_cap_usd > MODAL_CAP_USD:
            raise ValueError(f"Modal cap must be between $0 and ${MODAL_CAP_USD:.2f}")


def api_key_from_environment() -> str:
    """Return the OpenAI key or fail without exposing its value."""

    value = os.getenv("OPENAI_API_KEY", "").strip()
    if not value:
        raise RuntimeError("OPENAI_API_KEY is not set; put it in the process environment or ignored .env")
    return value
