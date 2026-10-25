"""Persistent, process-safe spend controls for Milestone 2 inference.

The Colosseum runner and the auditor are separate processes.  A process-local
counter is therefore insufficient: a crash or a second process could otherwise
start a new budget window.  This module keeps a small JSON ledger behind an
atomic directory lock.  Request bodies and credentials are never written.

The ledger deliberately reserves a conservative upper bound before every
request.  A successful request is settled with measured provider usage, but the
upper bound remains committed so that an error after a request reached a
provider cannot make the hard budget optimistic.
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from .costs import estimate_token_cost_usd, price_for_model, usage_to_dict


class BudgetError(RuntimeError):
    """Base class for hard budget and ledger errors."""


class BudgetExceeded(BudgetError):
    """Raised when a request cannot be admitted within the configured cap."""


class ModelMismatch(BudgetError):
    """Raised when a caller attempts silent model substitution."""


class _DirectoryLock:
    """Small cross-process lock based on atomic directory creation.

    The lock path is derived from the explicitly supplied ledger path.  A stale
    lock is removed only when it is older than the timeout and is still the
    exact lock directory owned by this ledger.
    """

    def __init__(self, path: Path, *, timeout_seconds: float = 30.0) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._held = False

    def acquire(self) -> None:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self.path.mkdir(parents=False, exist_ok=False)
                owner = self.path / "owner.json"
                owner.write_text(
                    json.dumps(
                        {
                            "pid": os.getpid(),
                            "created_at": datetime.now(UTC).isoformat(),
                        }
                    ),
                    encoding="utf-8",
                )
                self._held = True
                return
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > self.timeout_seconds * 4:
                    # This is a lock directory, not user data.  Only the
                    # owner file and the lock directory itself are removed.
                    owner = self.path / "owner.json"
                    if owner.exists():
                        owner.unlink()
                    try:
                        self.path.rmdir()
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise BudgetError(f"timed out waiting for budget ledger lock: {self.path}")
                time.sleep(0.05)

    def release(self) -> None:
        if not self._held:
            return
        owner = self.path / "owner.json"
        try:
            if owner.exists():
                owner.unlink()
            self.path.rmdir()
        finally:
            self._held = False

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def _payload_token_estimate(payload_chars: int) -> int:
    """Conservative, tokenizer-independent estimate used before a request.

    The provider's measured usage is authoritative for accounting.  This
    estimate is only an admission bound, so it intentionally overestimates
    ordinary JSON prompts and adds a fixed safety margin.
    """

    return max(1, math.ceil(max(0, int(payload_chars)) / 3) + 256)


class PersistentBudgetLedger:
    """A shared hard budget for multiple inference processes."""

    schema_version = 1

    def __init__(
        self,
        path: str | Path,
        *,
        budget_usd: float,
        model: str,
        per_request_cap_usd: float = 0.02,
        max_input_tokens: int = 16_000,
        max_output_tokens: int = 512,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self.budget_usd = float(budget_usd)
        self.model = str(model).strip()
        self.per_request_cap_usd = float(per_request_cap_usd)
        self.max_input_tokens = int(max_input_tokens)
        self.max_output_tokens = int(max_output_tokens)
        if self.budget_usd < 0:
            raise ValueError("budget_usd must be non-negative")
        if not self.model or price_for_model(self.model) is None:
            raise ValueError(f"no checked price for budget model {self.model!r}")
        if self.per_request_cap_usd <= 0:
            raise ValueError("per_request_cap_usd must be positive")
        if self.max_input_tokens <= 0 or self.max_output_tokens <= 0:
            raise ValueError("token limits must be positive")
        self._ensure_file()

    @contextmanager
    def _locked(self) -> Iterator[dict[str, Any]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _DirectoryLock(self.lock_path):
            data = self._read_unlocked()
            yield data

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _DirectoryLock(self.lock_path):
            if self.path.exists():
                data = self._read_unlocked()
                self._validate_header(data)
                return
            _atomic_write(
                self.path,
                {
                    "schema_version": self.schema_version,
                    "budget_usd": self.budget_usd,
                    "model": self.model,
                    "per_request_cap_usd": self.per_request_cap_usd,
                    "max_input_tokens": self.max_input_tokens,
                    "max_output_tokens": self.max_output_tokens,
                    "created_at": datetime.now(UTC).isoformat(),
                    "records": [],
                },
            )

    def _read_unlocked(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BudgetError(f"cannot read budget ledger {self.path}: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            raise BudgetError("budget ledger must contain a JSON object")
        self._validate_header(data)
        if not isinstance(data.get("records"), list):
            raise BudgetError("budget ledger records must be a JSON array")
        return data

    def _validate_header(self, data: dict[str, Any]) -> None:
        if data.get("schema_version") != self.schema_version:
            raise BudgetError("unsupported budget ledger schema version")
        if str(data.get("model")) != self.model:
            raise ModelMismatch(
                f"budget ledger is pinned to {data.get('model')!r}; requested {self.model!r}"
            )
        if not math.isclose(float(data.get("budget_usd", -1)), self.budget_usd, rel_tol=0, abs_tol=1e-12):
            raise BudgetError("budget ledger cap does not match the requested cap")

    @staticmethod
    def _committed_upper(data: dict[str, Any]) -> float:
        return sum(float(record.get("upper_bound_usd") or 0.0) for record in data.get("records", []))

    @staticmethod
    def _actual_cost(data: dict[str, Any]) -> float:
        return sum(float(record.get("actual_cost_usd") or 0.0) for record in data.get("records", []))

    def reserve(
        self,
        *,
        operation: str,
        model: str,
        payload_chars: int,
        max_output_tokens: int,
        process: str | None = None,
    ) -> str:
        """Reserve a conservative request bound before network I/O."""

        requested_model = str(model).strip()
        if requested_model != self.model:
            raise ModelMismatch(f"requested model {requested_model!r} does not match {self.model!r}")
        output_limit = int(max_output_tokens)
        if output_limit <= 0 or output_limit > self.max_output_tokens:
            raise BudgetExceeded(
                f"output token limit {output_limit} exceeds the configured maximum {self.max_output_tokens}"
            )
        estimated_input_tokens = _payload_token_estimate(payload_chars)
        if estimated_input_tokens > self.max_input_tokens:
            raise BudgetExceeded(
                f"estimated input {estimated_input_tokens} exceeds the configured maximum "
                f"{self.max_input_tokens} tokens"
            )
        price = price_for_model(self.model)
        assert price is not None
        upper = round(
            (
                estimated_input_tokens * price.input_usd_per_million
                + output_limit * price.output_usd_per_million
            )
            / 1_000_000,
            8,
        )
        if upper <= 0:
            raise BudgetExceeded("request upper bound is not positive")
        if upper > self.per_request_cap_usd:
            raise BudgetExceeded(
                f"request upper bound ${upper:.8f} exceeds per-request cap ${self.per_request_cap_usd:.8f}"
            )
        request_id = uuid.uuid4().hex
        with self._locked() as data:
            committed = self._committed_upper(data)
            if committed + upper > self.budget_usd + 1e-12:
                raise BudgetExceeded(
                    f"request would exceed cumulative budget: committed upper ${committed:.8f} + "
                    f"request ${upper:.8f} > cap ${self.budget_usd:.8f}"
                )
            data["records"].append(
                {
                    "request_id": request_id,
                    "operation": str(operation),
                    "model": self.model,
                    "process": str(process or "unknown"),
                    "status": "reserved",
                    "started_at": datetime.now(UTC).isoformat(),
                    "payload_chars": int(payload_chars),
                    "estimated_input_tokens": estimated_input_tokens,
                    "max_output_tokens": output_limit,
                    "upper_bound_usd": upper,
                    "actual_usage": {},
                    "actual_cost_usd": None,
                    "error_type": None,
                    "error_message": None,
                }
            )
            _atomic_write(self.path, data)
        return request_id

    def settle(
        self,
        request_id: str,
        *,
        status: str,
        usage: Any = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Persist success or failure immediately after a request returns."""

        if status not in {"success", "error"}:
            raise ValueError("status must be success or error")
        normalized = usage_to_dict(usage)
        with self._locked() as data:
            matching = [r for r in data["records"] if r.get("request_id") == request_id]
            if len(matching) != 1:
                raise BudgetError(f"unknown budget reservation {request_id}")
            record = matching[0]
            if record.get("status") != "reserved":
                raise BudgetError(f"budget reservation {request_id} is already settled")
            record["status"] = status
            record["finished_at"] = datetime.now(UTC).isoformat()
            record["actual_usage"] = normalized
            record["actual_cost_usd"] = estimate_token_cost_usd(self.model, normalized)
            record["error_type"] = str(error_type) if error_type else None
            record["error_message"] = str(error_message)[:500] if error_message else None
            _atomic_write(self.path, data)

    def summary(self) -> dict[str, Any]:
        with self._locked() as data:
            records = data.get("records", [])
            committed = self._committed_upper(data)
            actual = self._actual_cost(data)
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_input_tokens": 0}
            for record in records:
                for key, value in (record.get("actual_usage") or {}).items():
                    usage[key] = usage.get(key, 0) + int(value or 0)
            return {
                "budget_usd": self.budget_usd,
                "model": self.model,
                "request_count": len(records),
                "successful_request_count": sum(r.get("status") == "success" for r in records),
                "failed_request_count": sum(r.get("status") == "error" for r in records),
                "unsettled_request_count": sum(r.get("status") == "reserved" for r in records),
                "committed_upper_bound_usd": round(committed, 8),
                "actual_estimated_cost_usd": round(actual, 8),
                "remaining_conservative_budget_usd": round(max(0.0, self.budget_usd - committed), 8),
                "usage": usage,
            }

    def read(self) -> dict[str, Any]:
        """Return the sanitized ledger, primarily for validation and reporting."""

        with self._locked() as data:
            return json.loads(json.dumps(data))

