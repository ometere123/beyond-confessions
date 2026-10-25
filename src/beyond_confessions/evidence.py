"""Leakage-resistant evidence views for Colosseum runs.

All four views are deterministic projections of the same run artifacts.  They
do not read condition names, coalition labels, or adjudication files.  The
auditor receives only the returned packet; the condition-to-episode mapping is
kept in the study manifest outside the auditor input.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TASK_ID_RE = re.compile(r"\b[A-Z][A-Z0-9_-]*-\d+::[A-Za-z0-9_.-]+\b")
VIEW_NAMES = ("messages", "actions", "combined", "structured")
FORBIDDEN_METADATA_KEYS = {
    "condition",
    "condition_id",
    "colluders",
    "colluder_count",
    "coalition",
    "roles",
    "secret_blackboard_id",
    "private_channel",
    "ground_truth",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def _agent_map(names: list[str]) -> dict[str, str]:
    return {name: f"agent-{index:02d}" for index, name in enumerate(sorted(set(names)), start=1)}


def _sort_board_key(value: Any) -> tuple[int, str]:
    text = str(value)
    try:
        return (0, f"{int(text):020d}")
    except ValueError:
        return (1, text)


def _safe_json_value(value: Any, *, drop_keys: set[str] | None = None) -> Any:
    """Keep observable task data while excluding prompts, credentials, and message bodies."""

    drop = {str(x).lower() for x in (drop_keys or set())}
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in drop:
                continue
            result[key_text] = _safe_json_value(item, drop_keys=drop)
        return result
    if isinstance(value, list):
        return [_safe_json_value(item, drop_keys=drop) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _summary_outcome(final_summary: dict[str, Any], agent_ids: dict[str, str]) -> dict[str, Any]:
    assignment = final_summary.get("assignment") or {}
    rewards = final_summary.get("agent_rewards") or {}
    return {
        "status": final_summary.get("status"),
        "tasks_done": final_summary.get("tasks_done"),
        "joint_reward": final_summary.get("joint_reward"),
        "total_cost": final_summary.get("total_cost"),
        "priority_sum": final_summary.get("priority_sum"),
        "violations": final_summary.get("violations"),
        "assignments": [
            {"agent": agent_ids.get(str(agent), "agent-unknown"), "task_id": str(task_id)}
            for agent, task_id in sorted(assignment.items())
        ],
        "agent_rewards": {
            agent_ids.get(str(agent), "agent-unknown"): reward
            for agent, reward in sorted(rewards.items())
        },
    }


@dataclass(frozen=True)
class EvidenceBundle:
    """Four views plus the anonymized agent map used only for validation."""

    views: dict[str, dict[str, Any]]
    agent_map: dict[str, str]
    source_run: str

    def hashes(self) -> dict[str, str]:
        return {
            name: hashlib.sha256(
                json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            for name, value in self.views.items()
        }


def extract_evidence_views(run_root: str | Path, *, case_id: str) -> EvidenceBundle:
    """Extract messages, actions, combined, and linked structured evidence."""

    root = Path(run_root).resolve()
    config_paths = sorted(root.rglob("run_config.json"))
    if len(config_paths) != 1:
        raise ValueError(f"expected exactly one run_config.json below {root}, found {len(config_paths)}")
    run_dir = config_paths[0].parent
    required = [
        "run_config.json",
        "agent_turns.json",
        "blackboards.json",
        "tool_events.json",
        "final_summary.json",
        "metrics.json",
    ]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"run is missing evidence files: {', '.join(missing)}")

    run_config = _read_json(run_dir / "run_config.json")
    blackboards = _read_json(run_dir / "blackboards.json")
    tool_events = _read_json(run_dir / "tool_events.json")
    final_summary = _read_json(run_dir / "final_summary.json")
    metrics = _read_json(run_dir / "metrics.json")
    if not all(isinstance(value, list) for value in (blackboards, tool_events)):
        raise TypeError("blackboards.json and tool_events.json must be arrays")
    if not all(isinstance(value, dict) for value in (run_config, final_summary, metrics)):
        raise TypeError("run_config.json, final_summary.json, and metrics.json must be objects")

    names = list((run_config.get("roles") or {}).keys())
    for event in tool_events:
        if isinstance(event, dict) and event.get("agent_name"):
            names.append(str(event["agent_name"]))
    for board in blackboards:
        if isinstance(board, dict):
            names.extend(str(x) for x in (board.get("participants") or []))
            for event in board.get("events") or []:
                if isinstance(event, dict) and event.get("agent"):
                    names.append(str(event["agent"]))
    agent_ids = _agent_map(names)

    board_ids = sorted(
        [str(board.get("blackboard_id")) for board in blackboards if isinstance(board, dict)],
        key=_sort_board_key,
    )
    channel_ids = {board_id: f"channel-{index:02d}" for index, board_id in enumerate(board_ids, start=1)}
    channel_audiences: dict[str, list[str]] = {}
    for board in blackboards:
        if not isinstance(board, dict):
            continue
        board_id = str(board.get("blackboard_id"))
        channel_audiences[channel_ids.get(board_id, "channel-unknown")] = [
            agent_ids.get(str(name), "agent-unknown") for name in sorted(board.get("participants") or [])
        ]

    messages: list[dict[str, Any]] = []
    for board in blackboards:
        if not isinstance(board, dict):
            continue
        board_id = str(board.get("blackboard_id"))
        channel_id = channel_ids.get(board_id, "channel-unknown")
        for index, event in enumerate(board.get("events") or [], start=1):
            if not isinstance(event, dict) or event.get("kind") != "communication":
                continue
            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            content = payload.get("content")
            if not isinstance(content, str):
                continue
            messages.append(
                {
                    "evidence_id": f"message-{len(messages) + 1:04d}",
                    "timestamp": event.get("ts"),
                    "phase": payload.get("phase") or event.get("phase"),
                    "agent": agent_ids.get(str(event.get("agent")), "agent-unknown"),
                    "channel": channel_id,
                    "audience": channel_audiences.get(channel_id, []),
                    "message": content,
                    "source_order": index,
                }
            )
    messages.sort(key=lambda item: (float(item.get("timestamp") or 0), str(item["evidence_id"])))

    actions: list[dict[str, Any]] = []
    for event_index, event in enumerate(tool_events, start=1):
        if not isinstance(event, dict):
            continue
        tool_name = str(event.get("tool_name") or "unknown")
        arguments = event.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        sanitized_args = _safe_json_value(
            arguments,
            drop_keys={"message", "content", "prompt", "api_key", "authorization", "token"},
        )
        if tool_name == "post_message":
            board_id = str(arguments.get("blackboard_id"))
            sanitized_args = {
                "blackboard": channel_ids.get(board_id, "channel-unknown"),
            }
        result = event.get("result") or {}
        result_summary: dict[str, Any] = {}
        if isinstance(result, dict):
            result_summary["event_id"] = result.get("event_id")
            result_summary["status"] = result.get("status")
            result_body = result.get("result")
            if isinstance(result_body, dict):
                for key in ("status", "task_id", "joint_reward", "remaining_agents", "total_assigned"):
                    if key in result_body:
                        result_summary[key] = _safe_json_value(result_body[key])
            if isinstance(result.get("details"), dict):
                details = result["details"]
                if isinstance(details.get("result"), dict):
                    for key in ("status", "task_id", "joint_reward", "remaining_agents", "total_assigned"):
                        if key in details["result"]:
                            result_summary[key] = _safe_json_value(details["result"][key])
        actions.append(
            {
                "evidence_id": f"action-{len(actions) + 1:04d}",
                "source_order": event_index,
                "phase": event.get("phase"),
                "planning_round": event.get("planning_round"),
                "agent": agent_ids.get(str(event.get("agent_name")), "agent-unknown"),
                "tool": tool_name,
                "arguments": sanitized_args,
                "result": result_summary,
            }
        )

    outcome = _summary_outcome(final_summary, agent_ids)
    packet_header = {
        "schema_version": "beyond-confessions-evidence-1",
        "case_id": str(case_id),
        "agents": sorted(set(agent_ids.values())),
    }
    message_view = {**packet_header, "messages": messages}
    action_view = {**packet_header, "actions": actions, "outcome": outcome}
    combined_view = {**packet_header, "messages": messages, "actions": actions, "outcome": outcome}

    structured_claims: list[dict[str, Any]] = []
    assign_actions_by_agent_task: dict[tuple[str, str], list[str]] = {}
    for action in actions:
        if action.get("tool") != "assign_task":
            continue
        task_id = (action.get("arguments") or {}).get("task_id")
        if task_id is not None:
            key = (str(action.get("agent")), str(task_id))
            assign_actions_by_agent_task.setdefault(key, []).append(str(action["evidence_id"]))
    for message in messages:
        text = str(message.get("message") or "")
        mentioned = sorted(set(TASK_ID_RE.findall(text)))
        links: list[dict[str, Any]] = []
        for task_id in mentioned:
            key = (str(message.get("agent")), task_id)
            links.append(
                {
                    "task_id": task_id,
                    "action_refs": assign_actions_by_agent_task.get(key, []),
                    "action_match": bool(assign_actions_by_agent_task.get(key)),
                }
            )
        structured_claims.append(
            {
                "evidence_id": f"claim-{len(structured_claims) + 1:04d}",
                "message_ref": message["evidence_id"],
                "timestamp": message.get("timestamp"),
                "agent": message.get("agent"),
                "channel": message.get("channel"),
                "claim_text": text,
                "mentioned_task_ids": mentioned,
                "linked_actions": links,
            }
        )
    structured_view = {
        **packet_header,
        "claims": structured_claims,
        "actions": actions,
        "outcome": outcome,
    }
    views = {
        "messages": message_view,
        "actions": action_view,
        "combined": combined_view,
        "structured": structured_view,
    }
    for view in views.values():
        _assert_no_privileged_metadata(view)
    return EvidenceBundle(views=views, agent_map=agent_ids, source_run=str(run_dir))


def _assert_no_privileged_metadata(value: Any, *, _key: str | None = None) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_METADATA_KEYS:
                raise ValueError(f"privileged metadata key leaked into evidence packet: {key}")
            _assert_no_privileged_metadata(item, _key=str(key))
    elif isinstance(value, list):
        for item in value:
            _assert_no_privileged_metadata(item, _key=_key)


def validate_evidence_bundle(bundle: EvidenceBundle) -> dict[str, Any]:
    if set(bundle.views) != set(VIEW_NAMES):
        raise ValueError("evidence bundle must contain exactly the four required views")
    hashes = bundle.hashes()
    for name, view in bundle.views.items():
        if view.get("schema_version") != "beyond-confessions-evidence-1":
            raise ValueError(f"{name} view has an unknown schema version")
        if not str(view.get("case_id", "")).startswith("case-"):
            raise ValueError(f"{name} view has a non-anonymized case id")
        _assert_no_privileged_metadata(view)
        if name in {"messages", "combined"} and not isinstance(view.get("messages"), list):
            raise ValueError(f"{name} view has no messages array")
        if name in {"actions", "combined", "structured"} and not isinstance(view.get("actions"), list):
            raise ValueError(f"{name} view has no actions array")
    return {"status": "pass", "views": list(VIEW_NAMES), "sha256": hashes}


def write_evidence_bundle(bundle: EvidenceBundle, destination: str | Path) -> dict[str, Any]:
    target = Path(destination)
    validation = validate_evidence_bundle(bundle)
    for name, view in bundle.views.items():
        _write_json(target / f"{name}.json", view)
    _write_json(target / "validation.json", validation)
    return validation

