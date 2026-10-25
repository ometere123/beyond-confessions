"""Secret-safe model-call ledger used by probes and the Colosseum runner."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .costs import estimate_token_cost_usd, usage_to_dict


def redact_secret(value: Any, secret: str | None) -> str:
    text = str(value)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    return text


def _response_value(response: Any, name: str, default: Any = None) -> Any:
    if response is None:
        return default
    if isinstance(response, dict):
        return response.get(name, default)
    return getattr(response, name, default)


@dataclass
class CallRecord:
    sequence: int
    operation: str
    model: str
    status: str
    started_at: str
    elapsed_ms: float
    response_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    estimated_cost_usd: float | None = None
    error_type: str | None = None
    error_message: str | None = None


class UsageLedger:
    """In-memory ledger; callers explicitly persist it to a chosen artifact path."""

    def __init__(self, *, secret: str | None = None) -> None:
        self._secret = secret
        self.started_at = datetime.now(UTC).isoformat()
        self.records: list[CallRecord] = []

    def record_response(
        self,
        response: Any,
        *,
        model: str,
        operation: str,
        elapsed_ms: float,
    ) -> CallRecord:
        usage = usage_to_dict(_response_value(response, "usage"))
        record = CallRecord(
            sequence=len(self.records) + 1,
            operation=operation,
            model=model,
            status="success",
            started_at=datetime.now(UTC).isoformat(),
            elapsed_ms=round(float(elapsed_ms), 3),
            response_id=_response_value(response, "id"),
            usage=usage,
            estimated_cost_usd=estimate_token_cost_usd(model, usage),
        )
        self.records.append(record)
        return record

    def record_error(
        self,
        error: BaseException,
        *,
        model: str,
        operation: str,
        elapsed_ms: float,
    ) -> CallRecord:
        record = CallRecord(
            sequence=len(self.records) + 1,
            operation=operation,
            model=model,
            status="error",
            started_at=datetime.now(UTC).isoformat(),
            elapsed_ms=round(float(elapsed_ms), 3),
            error_type=type(error).__name__,
            error_message=redact_secret(str(error), self._secret)[:500],
        )
        self.records.append(record)
        return record

    def summary(self) -> dict[str, Any]:
        successes = [r for r in self.records if r.status == "success"]
        errors = [r for r in self.records if r.status == "error"]
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for record in self.records:
            for key, value in record.usage.items():
                usage[key] = usage.get(key, 0) + int(value)
        costs = [r.estimated_cost_usd for r in successes if r.estimated_cost_usd is not None]
        return {
            "started_at": self.started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "request_count": len(self.records),
            "successful_request_count": len(successes),
            "failed_request_count": len(errors),
            "usage": usage,
            "estimated_cost_usd": round(sum(costs), 8) if costs else None,
            "cost_method": "standard token rates; measured response usage; provider billing not queried",
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "records": [asdict(record) for record in self.records],
        }

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(target)
        return target


class TimedCall:
    """Small helper for instrumenting a single call without logging request content."""

    def __init__(self, ledger: UsageLedger, *, model: str, operation: str) -> None:
        self.ledger = ledger
        self.model = model
        self.operation = operation
        self.started = time.perf_counter()

    def success(self, response: Any) -> CallRecord:
        return self.ledger.record_response(
            response,
            model=self.model,
            operation=self.operation,
            elapsed_ms=(time.perf_counter() - self.started) * 1000,
        )

    def error(self, error: BaseException) -> CallRecord:
        return self.ledger.record_error(
            error,
            model=self.model,
            operation=self.operation,
            elapsed_ms=(time.perf_counter() - self.started) * 1000,
        )
