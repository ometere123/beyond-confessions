from __future__ import annotations

from types import SimpleNamespace

from beyond_confessions.costs import estimate_token_cost_usd, merge_usage, usage_to_dict
from beyond_confessions.modal import estimate_modal_gpu_cost


def test_usage_normalization_and_cost() -> None:
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details=SimpleNamespace(cached_tokens=200),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=50),
    )
    normalized = usage_to_dict(usage)
    assert normalized["cached_input_tokens"] == 200
    assert normalized["reasoning_tokens"] == 50
    assert estimate_token_cost_usd("gpt-6-luna", usage) == 0.000332


def test_unknown_model_cost_is_not_fabricated() -> None:
    assert estimate_token_cost_usd("unknown-model", {"prompt_tokens": 1, "completion_tokens": 1}) is None


def test_usage_merge() -> None:
    assert merge_usage([{"prompt_tokens": 2, "completion_tokens": 3}, {"prompt_tokens": 4}]) == {
        "prompt_tokens": 6,
        "completion_tokens": 3,
        "total_tokens": 9,
    }


def test_cached_input_cost_survives_normalization() -> None:
    usage = {"prompt_tokens": 1_000, "completion_tokens": 100, "cached_input_tokens": 600}
    assert estimate_token_cost_usd("gpt-6-luna", usage) == 0.000096


def test_modal_estimate_is_bounded() -> None:
    estimate = estimate_modal_gpu_cost(gpu="A10G", active_seconds=300)
    assert estimate.gpu == "A10"
    assert estimate.total_cost_usd_upper_bound == 0.0918
