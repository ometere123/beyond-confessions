"""Modal compatibility and cost estimates; deliberately no deployment code."""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Modal public pricing checked on 2026-10-25. Units are USD per GPU-second.
GPU_USD_PER_SECOND: dict[str, float] = {
    "T4": 0.000164,
    "L4": 0.000222,
    "A10": 0.000306,
    "A100-40GB": 0.000583,
    "A100-80GB": 0.000694,
    "L40S": 0.000542,
    "H100": 0.001097,
    "H200": 0.001261,
}


@dataclass(frozen=True)
class ModalCostEstimate:
    gpu: str
    active_seconds: float
    idle_seconds: float
    gpu_cost_usd: float
    cpu_memory_cost_excluded: bool
    total_cost_usd_upper_bound: float
    pricing_source: str


def estimate_modal_gpu_cost(
    *,
    gpu: str = "A10",
    active_seconds: float = 300.0,
    idle_seconds: float = 0.0,
) -> ModalCostEstimate:
    normalized = gpu.upper().replace("A10G", "A10")
    if normalized not in GPU_USD_PER_SECOND:
        raise ValueError(f"unsupported GPU rate: {gpu}")
    if active_seconds < 0 or idle_seconds < 0:
        raise ValueError("active and idle seconds must be non-negative")
    total_seconds = float(active_seconds) + float(idle_seconds)
    cost = round(total_seconds * GPU_USD_PER_SECOND[normalized], 8)
    return ModalCostEstimate(
        gpu=normalized,
        active_seconds=float(active_seconds),
        idle_seconds=float(idle_seconds),
        gpu_cost_usd=cost,
        cpu_memory_cost_excluded=True,
        total_cost_usd_upper_bound=cost,
        pricing_source="https://modal.com/pricing",
    )


def qwen_7b_compatibility() -> dict[str, object]:
    """Static compatibility assessment for the starter's default open model."""

    return {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "weights_estimate": "about 14 GB in fp16 before runtime/KV-cache overhead",
        "recommended_gpu": "A10",
        "fit_assessment": "likely for a low-concurrency smoke run; must be verified in the target Modal image",
        "official_starter_note": "starter documents A10G (~24 GB) for up to 8B models",
        "current_modal_name_note": "current Modal GPU docs list A10; treat A10G as an old alias until verified",
        "deployment_status": "not attempted",
    }


def estimate_startup_scenarios() -> list[dict[str, object]]:
    """Return bounded scenarios based on documented startup ranges, not measurements."""

    scenarios = []
    for seconds in (120, 300, 600):
        estimate = estimate_modal_gpu_cost(gpu="A10", active_seconds=seconds)
        scenarios.append({"startup_seconds": seconds, **asdict(estimate)})
    return scenarios
