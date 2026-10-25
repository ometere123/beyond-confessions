from __future__ import annotations

import pytest

from beyond_confessions.config import ProjectConfig, api_key_from_environment


def test_guardrails_reject_caps_above_user_limits() -> None:
    config = ProjectConfig(openai_cap_usd=2.01)
    with pytest.raises(ValueError, match="OpenAI cap"):
        config.validate_guardrails()


def test_api_key_is_required_without_exposing_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY") as exc_info:
        api_key_from_environment()
    assert "sk-" not in str(exc_info.value)


def test_model_config_reads_non_secret_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEYOND_CONFESSIONS_MODEL", "gpt-4o-mini")
    config = ProjectConfig.from_environment()
    assert config.model == "gpt-4o-mini"
