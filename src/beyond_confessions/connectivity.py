"""Bounded, secret-safe OpenAI compatibility probes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI

from .config import DEFAULT_OPENAI_BASE_URL, api_key_from_environment
from .ledger import TimedCall, UsageLedger, redact_secret

ProbeMode = Literal["text", "tool", "structured", "all"]


def load_local_environment(project_root: str | Path | None = None) -> Path | None:
    """Load an ignored .env if present; existing process variables win."""

    root = Path(project_root) if project_root else Path.cwd()
    candidate = root / ".env"
    if candidate.exists():
        load_dotenv(candidate, override=False)
        return candidate
    load_dotenv(override=False)
    return None


def _reasoning_none(model: str) -> dict[str, str]:
    # GPT-6 Luna documents Chat Completions function calling with reasoning_effort=none.
    return {"reasoning_effort": "none"} if model.lower() == "gpt-6-luna" else {}


def _tool_definition() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "record_probe",
                "description": "Record a successful compatibility probe.",
                "parameters": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
    ]


def _structured_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "compatibility_probe",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        },
    }


def _response_id(response: Any) -> str | None:
    value = getattr(response, "id", None)
    return str(value) if value else None


def _probe_one(client: OpenAI, model: str, mode: str, ledger: UsageLedger) -> dict[str, Any]:
    call = TimedCall(ledger, model=model, operation=f"connectivity:{mode}")
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only what the requested compatibility probe needs."},
            {"role": "user", "content": "Confirm this probe with the smallest valid response."},
        ],
        "max_completion_tokens": 32,
        "temperature": 0.0,
        **_reasoning_none(model),
    }
    # GPT-6 Luna's Chat Completions function-calling path is documented with
    # reasoning_effort=none; omit sampling controls that may be rejected on
    # that reasoning configuration.
    if model.lower() == "gpt-6-luna":
        kwargs.pop("temperature", None)
    if mode == "tool":
        kwargs.update(
            {
                "tools": _tool_definition(),
                "tool_choice": {"type": "function", "function": {"name": "record_probe"}},
            }
        )
    elif mode == "structured":
        kwargs["response_format"] = _structured_response_format()
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        call.error(exc)
        raise RuntimeError(
            redact_secret(f"{type(exc).__name__}: {exc}", os.getenv("OPENAI_API_KEY"))
        ) from exc
    record = call.success(response)
    choice = response.choices[0] if getattr(response, "choices", None) else None
    message = getattr(choice, "message", None)
    tool_calls = getattr(message, "tool_calls", None) or []
    result: dict[str, Any] = {
        "mode": mode,
        "status": "pass",
        "model": model,
        "response_id": _response_id(response),
        "tool_call_count": len(tool_calls),
        "usage": record.usage,
        "estimated_cost_usd": record.estimated_cost_usd,
        "elapsed_ms": record.elapsed_ms,
    }
    if mode == "tool" and not tool_calls:
        raise RuntimeError("tool probe returned no tool call")
    if mode == "structured":
        content = getattr(message, "content", None)
        try:
            parsed = json.loads(content or "")
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("structured probe returned invalid JSON") from exc
        if parsed != {"ok": True}:
            raise RuntimeError("structured probe did not satisfy the expected schema payload")
        result["schema_valid"] = True
    return result


def run_connectivity_probe(
    *,
    model: str,
    mode: ProbeMode = "tool",
    base_url: str | None = None,
    max_estimated_cost_usd: float = 0.50,
    ledger_path: str | Path | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run one or more probes with no automatic retry and a hard estimated-cost ceiling."""

    load_local_environment(project_root)
    key = api_key_from_environment()
    if max_estimated_cost_usd < 0 or max_estimated_cost_usd > 0.50:
        raise ValueError("connectivity probe cap must be between $0 and $0.50")
    client = OpenAI(
        api_key=key,
        base_url=base_url or os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
        max_retries=0,
        timeout=60.0,
    )
    ledger = UsageLedger(secret=key)
    modes = [mode] if mode != "all" else ["text", "tool", "structured"]
    results: list[dict[str, Any]] = []
    for current in modes:
        # The cap is deliberately checked before each call. Unknown model prices are not treated as free.
        if (
            ledger.summary()["estimated_cost_usd"] is not None
            and ledger.summary()["estimated_cost_usd"] >= max_estimated_cost_usd
        ):
            raise RuntimeError("connectivity probe estimated-cost ceiling reached before the next call")
        if current == "text":
            # Text is a transport sanity check; the other modes validate the research requirements.
            result = _probe_one(client, model, current, ledger)
        else:
            result = _probe_one(client, model, current, ledger)
        results.append(result)
    payload = {
        "status": "pass",
        "model": model,
        "base_url": base_url or os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
        "modes": modes,
        "results": results,
        "ledger": ledger.summary(),
    }
    if ledger_path:
        ledger.write(ledger_path)
    return payload
