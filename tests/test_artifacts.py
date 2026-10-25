from __future__ import annotations

import json

from beyond_confessions.artifacts import extract_observations, validate_experiment_root


def _write_json(path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_result_validation_requires_usage_ledger(tmp_path) -> None:
    for name in ("config.json", "summary.json", "progress.json"):
        _write_json(tmp_path / name, {})
    (tmp_path / "summary.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "summary.csv").write_text("run_id,coalition_advantage_mean\nr1,0.0\n", encoding="utf-8")
    (tmp_path / "experiment.log").write_text("RUN END\n", encoding="utf-8")
    run_dir = tmp_path / "runs" / "m" / "s" / "r1"
    run_dir.mkdir(parents=True)
    for name in (
        "run_config.json",
        "final_summary.json",
        "agent_turns.json",
        "tool_events.json",
        "blackboards.json",
        "metrics.json",
    ):
        _write_json(run_dir / name, {})

    report = validate_experiment_root(tmp_path)
    assert report.status == "fail"
    assert any("usage" in issue for issue in report.issues)

    _write_json(tmp_path / "usage.json", {"summary": {"request_count": 1}})
    report = validate_experiment_root(tmp_path)
    assert report.status == "pass"


def test_observation_extraction_does_not_assign_labels(tmp_path) -> None:
    (tmp_path / "summary.csv").write_text(
        "run_id,model,coalition_advantage_mean,status\nr1,gpt-6-luna,2.5,success\n", encoding="utf-8"
    )
    observations = extract_observations(tmp_path)
    assert observations == [
        {
            "run_id": "r1",
            "model": "gpt-6-luna",
            "provider": None,
            "seed": None,
            "status": "success",
            "coalition_advantage_mean": 2.5,
            "coalition_mean_reward": None,
            "noncoalition_mean_reward": None,
            "mean_regret": None,
            "violations": None,
            "colluder_posts_secret_rate": None,
        }
    ]
