"""Extract the four preselected qualitative cases from the raw archive.

The output is a compact, exact, anonymised evidence index. It contains no API
requests and is intentionally generated from the committed archive rather than
from hand-written dialogue.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

CASE_SPECS = {
    "C-seed-1": {
        "purpose": "communication_heavy_without_task_harm",
        "message_refs": ["message-0016", "message-0017", "message-0018"],
        "action_refs": ["action-0024", "action-0025", "action-0026", "action-0027"],
    },
    "D-seed-3": {
        "purpose": "task_harm_without_designated_coalition",
        "message_refs": ["message-0001", "message-0002", "message-0013"],
        "action_refs": ["action-0020", "action-0021", "action-0022", "action-0023"],
    },
    "A-seed-1": {
        "purpose": "combined_view_false_positive_against_task_harm_proxy",
        "message_refs": ["message-0016", "message-0022", "message-0023", "message-0024"],
        "action_refs": ["action-0026", "action-0027", "action-0028", "action-0029"],
    },
    "B-seed-9": {
        "purpose": "combined_view_false_negative_against_task_harm_proxy",
        "message_refs": ["message-0015", "message-0017", "message-0006", "message-0008"],
        "action_refs": ["action-0023", "action-0025"],
    },
}


def _read_json(archive: zipfile.ZipFile, name: str) -> Any:
    return json.loads(archive.read(name).decode("utf-8"))


def _select(items: list[dict[str, Any]], refs: list[str]) -> list[dict[str, Any]]:
    by_id = {item.get("evidence_id"): item for item in items}
    missing = [ref for ref in refs if ref not in by_id]
    if missing:
        raise ValueError(f"missing evidence references: {missing}")
    return [by_id[ref] for ref in refs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("evidence/milestone2/raw_artifacts_20261025.zip"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/milestone3/case_studies.json"),
    )
    args = parser.parse_args()
    with zipfile.ZipFile(args.source) as archive:
        cases: list[dict[str, Any]] = []
        for episode_key, spec in CASE_SPECS.items():
            prefix = f"episodes/{episode_key}/"
            adjudication = _read_json(archive, prefix + "adjudication.json")
            messages = _read_json(archive, prefix + "evidence/messages.json")["messages"]
            combined = _read_json(archive, prefix + "evidence/combined.json")
            actions = combined["actions"]
            combined_audit = _read_json(archive, prefix + "audits/combined.json")
            structured_audit = _read_json(archive, prefix + "audits/structured.json")
            cases.append(
                {
                    "episode_key": episode_key,
                    "case_id": adjudication["case_id"],
                    "condition": adjudication["condition"],
                    "purpose": spec["purpose"],
                    "selected_message_refs": spec["message_refs"],
                    "selected_action_refs": spec["action_refs"],
                    "messages": _select(messages, spec["message_refs"]),
                    "actions": _select(actions, spec["action_refs"]),
                    "outcome": combined["outcome"],
                    "adjudication": adjudication,
                    "audits": {
                        "combined": combined_audit,
                        "structured": structured_audit,
                    },
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cases, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "cases": len(cases), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
