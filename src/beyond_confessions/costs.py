"""Conservative token-cost calculations.

Prices are recorded as constants so an artifact can state exactly which schedule was used. Unknown
models return ``None`` instead of inventing a cost.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelPrice:
    model: str
    input_usd_per_million: float
    output_usd_per_million: float
    cached_input_usd_per_million: float | None = None
    source: str = ""


# Checked against official model pages on 2026-10-25. These are standard-token rates; discounts,
# regional premiums, batch/flex rates, and provider-specific rounding are not assumed.
MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-6-luna": ModelPrice(
        model="gpt-6-luna",
        input_usd_per_million=0.10,
        output_usd_per_million=0.50,
        cached_input_usd_per_million=0.01,
        source="https://developers.openai.com/api/docs/models/gpt-6-luna",
    ),
    "gpt-4o-mini": ModelPrice(
        model="gpt-4o-mini",
        input_usd_per_million=0.15,
        output_usd_per_million=0.60,
        cached_input_usd_per_million=0.075,
        source="https://developers.openai.com/api/docs/models/gpt-4o-mini",
    ),
    "gpt-4.1-mini": ModelPrice(
        model="gpt-4.1-mini",
        input_usd_per_million=0.40,
        output_usd_per_million=1.60,
        cached_input_usd_per_million=0.10,
        source="https://developers.openai.com/api/docs/models/gpt-4.1-mini",
    ),
}


def _value(mapping_or_object: Any, name: str, default: Any = None) -> Any:
    if mapping_or_object is None:
        return default
    if isinstance(mapping_or_object, Mapping):
        return mapping_or_object.get(name, default)
    return getattr(mapping_or_object, name, default)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def usage_to_dict(usage: Any) -> dict[str, int]:
    """Normalize OpenAI usage objects without serializing response content."""

    prompt = _int(_value(usage, "prompt_tokens"))
    completion = _int(_value(usage, "completion_tokens"))
    total = _int(_value(usage, "total_tokens")) or prompt + completion
    prompt_details = _value(usage, "prompt_tokens_details", {})
    completion_details = _value(usage, "completion_tokens_details", {})
    cached = _int(_value(prompt_details, "cached_tokens"))
    reasoning = _int(_value(completion_details, "reasoning_tokens"))
    result = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }
    if cached:
        result["cached_input_tokens"] = cached
    if reasoning:
        result["reasoning_tokens"] = reasoning
    return result


def price_for_model(model: str) -> ModelPrice | None:
    return MODEL_PRICES.get(model.strip().lower())


def estimate_token_cost_usd(model: str, usage: Mapping[str, Any] | Any) -> float | None:
    """Estimate cost from usage; return ``None`` when the model price is unknown."""

    price = price_for_model(model)
    if price is None:
        return None
    normalized = usage_to_dict(usage)
    prompt = normalized["prompt_tokens"]
    cached = min(normalized.get("cached_input_tokens", 0), prompt)
    uncached = prompt - cached
    output = normalized["completion_tokens"]
    input_cost = uncached * price.input_usd_per_million
    if cached:
        cached_rate = price.cached_input_usd_per_million or price.input_usd_per_million
        input_cost += cached * cached_rate
    return round((input_cost + output * price.output_usd_per_million) / 1_000_000, 8)


def merge_usage(usages: list[Mapping[str, Any] | Any]) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for usage in usages:
        normalized = usage_to_dict(usage)
        for key, value in normalized.items():
            totals[key] = totals.get(key, 0) + value
    if totals["total_tokens"] == 0:
        totals["total_tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
    return totals
