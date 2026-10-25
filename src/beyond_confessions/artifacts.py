"""Extraction and validation for Colosseum experiment artifacts.

Validation checks structural evidence only. It does not interpret a positive coalition advantage as a
research finding, and it never substitutes missing evidence with a claim.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_EXPERIMENT_FILES = (
    "config.json",
    "summary.json",
    "summary.jsonl",
    "summary.csv",
    "experiment.log",
    "progress.json",
)
REQUIRED_RUN_FILES = (
    "run_config.json",
    "final_summary.json",
    "agent_turns.json",
    "tool_events.json",
    "blackboards.json",
    "metrics.json",
)


@dataclass
class ValidationReport:
    root: str
    status: str
    issues: list[str] = field(default_factory=list)
    run_count: int = 0
    summary_row_count: int = 0
    observed_models: list[str] = field(default_factory=list)
    observation_count: int = 0
    usage_summary: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "status": self.status,
            "issues": self.issues,
            "run_count": self.run_count,
            "summary_row_count": self.summary_row_count,
            "observed_models": self.observed_models,
            "observation_count": self.observation_count,
            "usage_summary": self.usage_summary,
        }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _summary_rows(root: Path) -> list[dict[str, Any]]:
    path = root / "summary.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def extract_observations(root: str | Path) -> list[dict[str, Any]]:
    """Extract reported observations without classifying them as collusion."""

    root_path = Path(root)
    rows = _summary_rows(root_path)
    observations: list[dict[str, Any]] = []
    for row in rows:
        observations.append(
            {
                "run_id": row.get("run_id"),
                "model": row.get("model"),
                "provider": row.get("provider"),
                "seed": _number(row.get("seed")),
                "status": row.get("status"),
                "coalition_advantage_mean": _number(row.get("coalition_advantage_mean")),
                "coalition_mean_reward": _number(row.get("coalition_mean_reward")),
                "noncoalition_mean_reward": _number(row.get("noncoalition_mean_reward")),
                "mean_regret": _number(row.get("mean_regret")),
                "violations": _number(row.get("violations")),
                "colluder_posts_secret_rate": _number(row.get("colluder_posts_secret_rate")),
            }
        )
    return observations


def load_usage_summary(root: str | Path) -> dict[str, Any] | None:
    root_path = Path(root)
    candidates = (root_path / "usage.json", root_path / "usage_ledger.json")
    for path in candidates:
        if path.exists():
            data = _read_json(path)
            if isinstance(data, dict):
                return data.get("summary", data)
    return None


def validate_experiment_root(
    root: str | Path,
    *,
    require_usage_ledger: bool = True,
) -> ValidationReport:
    root_path = Path(root).resolve()
    report = ValidationReport(root=str(root_path), status="pass")
    if not root_path.is_dir():
        report.status = "fail"
        report.issues.append("experiment root is not a directory")
        return report

    for name in REQUIRED_EXPERIMENT_FILES:
        if not (root_path / name).is_file():
            report.status = "fail"
            report.issues.append(f"missing experiment file: {name}")

    rows = _summary_rows(root_path)
    report.summary_row_count = len(rows)
    if rows:
        report.observed_models = sorted({str(row.get("model")) for row in rows if row.get("model")})
        for index, row in enumerate(rows, start=1):
            if "coalition_advantage_mean" not in row:
                report.status = "fail"
                report.issues.append(f"summary row {index} has no coalition_advantage_mean field")
    else:
        report.status = "fail"
        report.issues.append("summary.csv has no rows")

    run_configs = sorted(root_path.rglob("run_config.json"))
    report.run_count = len(run_configs)
    if not run_configs:
        report.status = "fail"
        report.issues.append("no run_config.json artifacts found")
    for run_config in run_configs:
        run_dir = run_config.parent
        for name in REQUIRED_RUN_FILES:
            if not (run_dir / name).is_file():
                report.status = "fail"
                report.issues.append(f"{run_dir.name}: missing run file {name}")
        for name in REQUIRED_RUN_FILES:
            path = run_dir / name
            if path.exists():
                try:
                    _read_json(path)
                except json.JSONDecodeError as exc:
                    report.status = "fail"
                    report.issues.append(f"invalid JSON {path}: {exc.msg}")

    report.usage_summary = load_usage_summary(root_path)
    if require_usage_ledger and report.usage_summary is None:
        report.status = "fail"
        report.issues.append("missing usage.json or usage_ledger.json; actual call accounting is required")
    report.observation_count = len(extract_observations(root_path))
    return report


def validate_json_result(path: str | Path) -> dict[str, Any]:
    """Validate a result or summary JSON file without making a scientific claim."""

    target = Path(path)
    data = _read_json(target)
    if not isinstance(data, (dict, list)):
        raise TypeError("result JSON must contain an object or array")
    return {"status": "pass", "path": str(target.resolve()), "top_level_type": type(data).__name__}
