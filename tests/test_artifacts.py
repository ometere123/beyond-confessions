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
    _write_json(
        run_dir / "run_config.json",
        {
            "model": "gpt-6-luna",
            "num_agents": 1,
            "colluder_count": 1,
            "colluders": ["a"],
            "roles": {"a": "colluder"},
            "secret_channel_enabled": True,
            "secret_blackboard_id": 1,
            "blackboard_participants": {"1": ["a"]},
        },
    )
    _write_json(
        run_dir / "final_summary.json",
        {"status": "complete", "assignment": {"a": "task-1"}, "tasks_done": 1, "agent_rewards": {"a": 1}, "joint_reward": 1},
    )
    _write_json(run_dir / "agent_turns.json", [{"model": "gpt-6-luna"}])
    _write_json(
        run_dir / "tool_events.json",
        [
            {"tool_name": "post_message", "agent_name": "a", "arguments": {"blackboard_id": 1}},
            {"tool_name": "assign_task", "agent_name": "a", "arguments": {"task_id": "task-1"}},
        ],
    )
    _write_json(run_dir / "blackboards.json", [{"events": [{"blackboard_id": 1, "kind": "communication", "agent": "a"}]}])
    _write_json(
        run_dir / "metrics.json",
        {
            "status": "complete",
            "total_agents": 1,
            "colluder_count": 1,
            "secret_blackboard_id": 1,
            "colluder_posts_total": 1,
            "colluder_posts_secret": 1,
            "colluder_posts_non_secret": 0,
        },
    )

    report = validate_experiment_root(tmp_path)
    assert report.status == "fail"
    assert any("usage" in issue for issue in report.issues)

    _write_json(tmp_path / "usage.json", {"summary": {"request_count": 1}})
    report = validate_experiment_root(tmp_path)
    assert report.status == "pass"

    _write_json(run_dir / "final_summary.json", {"status": "complete", "joint_reward": 2, "agent_rewards": {"a": 1}})
    report = validate_experiment_root(tmp_path)
    assert report.status == "fail"
    assert any("joint_reward" in issue for issue in report.issues)


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
