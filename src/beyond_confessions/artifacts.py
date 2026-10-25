"""Extraction and validation for Colosseum experiment artifacts.

Validation checks structural evidence only. It does not interpret a positive coalition advantage as a
research finding, and it never substitutes missing evidence with a claim.
"""

from __future__ import annotations

import csv
import json
import math
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
    warnings: list[str] = field(default_factory=list)
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
            "warnings": self.warnings,
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


def _validate_run_consistency(run_dir: Path, report: ValidationReport) -> None:
    """Check cross-file relationships without interpreting them as collusion."""

    paths = {name: run_dir / name for name in REQUIRED_RUN_FILES}
    if any(not path.is_file() for path in paths.values()):
        return
    try:
        run_config = _read_json(paths["run_config.json"])
        final_summary = _read_json(paths["final_summary.json"])
        metrics = _read_json(paths["metrics.json"])
        turns = _read_json(paths["agent_turns.json"])
        tool_events = _read_json(paths["tool_events.json"])
        blackboards = _read_json(paths["blackboards.json"])
    except (OSError, json.JSONDecodeError):
        return

    if not all(isinstance(value, dict) for value in (run_config, final_summary, metrics)):
        report.status = "fail"
        report.issues.append(f"{run_dir.name}: run metadata must be JSON objects")
        return
    if not all(isinstance(value, list) for value in (turns, tool_events, blackboards)):
        report.status = "fail"
        report.issues.append(f"{run_dir.name}: turn, tool, and blackboard files must be JSON arrays")
        return

    def issue(message: str) -> None:
        report.status = "fail"
        report.issues.append(f"{run_dir.name}: {message}")

    roles = run_config.get("roles") or {}
    colluders = set(run_config.get("colluders") or [])
    role_colluders = {name for name, role in roles.items() if role == "colluder"}
    if run_config.get("num_agents") != len(roles):
        issue("run_config num_agents does not match roles")
    if run_config.get("colluder_count") != len(colluders):
        issue("run_config colluder_count does not match colluders")
    if colluders != role_colluders:
        issue("run_config colluders do not match colluder roles")

    participants = run_config.get("blackboard_participants") or {}
    secret_id_value = run_config.get("secret_blackboard_id")
    secret_id = str(secret_id_value) if secret_id_value is not None else None
    if run_config.get("secret_channel_enabled") and secret_id is not None:
        extra_members = str(run_config.get("extra_channel_members") or "colluders").strip().lower()
        expected_participants = set(roles) if extra_members == "all" else colluders
        if set(participants.get(secret_id, [])) != expected_participants:
            issue("extra channel participants do not match the configured treatment")

    assignment = final_summary.get("assignment") or {}
    if not isinstance(assignment, dict):
        issue("final_summary assignment is not an object")
        assignment = {}
    task_ids = [str(task_id) for task_id in assignment.values()]
    if len(task_ids) != len(set(task_ids)):
        report.warnings.append(f"{run_dir.name}: final_summary contains duplicate task assignments; retained as an observed violation")
    if assignment and final_summary.get("tasks_done") != len(task_ids):
        issue("final_summary tasks_done does not match the number of assigned agents")
    rewards = final_summary.get("agent_rewards") or {}
    if isinstance(rewards, dict) and isinstance(final_summary.get("joint_reward"), (int, float)):
        reward_sum = sum(float(value) for value in rewards.values() if isinstance(value, (int, float)))
        if not math.isclose(reward_sum, float(final_summary["joint_reward"]), rel_tol=1e-9, abs_tol=1e-9):
            issue("final_summary agent rewards do not sum to joint_reward")

    if metrics.get("status") != final_summary.get("status"):
        issue("metrics status does not match final_summary status")
    for metric_field in ("total_agents", "colluder_count", "secret_blackboard_id"):
        config_value = run_config.get({"total_agents": "num_agents"}.get(metric_field, metric_field))
        if config_value is not None and metrics.get(metric_field) != config_value:
            issue(f"metrics {metric_field} does not match run_config")

    event_posts = [event for event in tool_events if event.get("tool_name") == "post_message"]
    event_assignments = [event for event in tool_events if event.get("tool_name") == "assign_task"]
    colluder_posts = [event for event in event_posts if event.get("agent_name") in colluders]
    secret_posts = []
    if run_config.get("secret_channel_enabled") and secret_id is not None:
        secret_posts = [
            event
            for event in colluder_posts
            if str((event.get("arguments") or {}).get("blackboard_id")) == secret_id
        ]
    if metrics.get("colluder_posts_total") != len(colluder_posts):
        issue("metrics colluder_posts_total does not match tool_events")
    if metrics.get("colluder_posts_secret") != len(secret_posts):
        issue("metrics colluder_posts_secret does not match tool_events")
    if metrics.get("colluder_posts_non_secret") != len(colluder_posts) - len(secret_posts):
        issue("metrics colluder_posts_non_secret does not match tool_events")
    if secret_id is not None:
        extra_members = str(run_config.get("extra_channel_members") or "colluders").strip().lower()
        allowed_secret_authors = set(roles) if extra_members == "all" else colluders
        all_secret_posts = [
            event
            for event in event_posts
            if str((event.get("arguments") or {}).get("blackboard_id")) == secret_id
        ]
        if any(event.get("agent_name") not in allowed_secret_authors for event in all_secret_posts):
            issue("extra-channel communication was attributed to an agent outside the configured audience")

    executed_agent_tasks = {
        (str(event.get("agent_name")), str((event.get("arguments") or {}).get("task_id")))
        for event in event_assignments
    }
    final_agent_tasks = {(str(agent), str(task_id)) for agent, task_id in assignment.items()}
    if not final_agent_tasks.issubset(executed_agent_tasks):
        issue("final assignments are not represented by assign_task tool events")

    model_values = {turn.get("model") for turn in turns if turn.get("model")}
    if run_config.get("model") and model_values != {run_config["model"]}:
        issue("agent turn models do not match run_config model")

    blackboard_events = [event for board in blackboards for event in board.get("events", [])]
    secret_blackboard_events = [
        event for event in blackboard_events if str(event.get("blackboard_id")) == secret_id
    ]
    if secret_id is not None:
        extra_members = str(run_config.get("extra_channel_members") or "colluders").strip().lower()
        allowed_secret_authors = set(roles) if extra_members == "all" else colluders
        if any(
            event.get("kind") == "communication" and event.get("agent") not in allowed_secret_authors
            for event in secret_blackboard_events
        ):
            issue("blackboards contains communication from an agent outside the configured channel audience")


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
        _validate_run_consistency(run_dir, report)

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
