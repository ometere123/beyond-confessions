from __future__ import annotations

from types import SimpleNamespace

from beyond_confessions.ledger import UsageLedger, redact_secret


def test_ledger_records_usage_without_response_content() -> None:
    ledger = UsageLedger(secret="secret-value")
    response = SimpleNamespace(
        id="resp_test",
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2, total_tokens=6),
        choices=[],
    )
    record = ledger.record_response(response, model="gpt-6-luna", operation="test", elapsed_ms=1.2)
    assert record.response_id == "resp_test"
    assert record.usage["total_tokens"] == 6
    assert "choices" not in record.__dict__
    assert redact_secret("prefix secret-value suffix", "secret-value") == "prefix [REDACTED] suffix"
