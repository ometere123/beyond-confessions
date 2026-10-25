"""Validate Milestone 2 study artifacts without interpreting them as findings."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from beyond_confessions.artifacts import validate_experiment_root
from beyond_confessions.auditor import validate_auditor_output
from beyond_confessions.budget import PersistentBudgetLedger
from beyond_confessions.evidence import extract_evidence_views, validate_evidence_bundle
from beyond_confessions.study import load_protocol

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"OPENAI_API_KEY\s*[=:]\s*[^\s]+", re.IGNORECASE),
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_secret(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def validate(root: str | Path, *, expected_per_condition: int | None = None) -> dict:
    root_path = Path(root).resolve()
    issues: list[str] = []
    manifest_path = root_path / "study_manifest.json"
    if not manifest_path.is_file():
        return {"status": "fail", "root": str(root_path), "issues": ["missing study_manifest.json"]}
    try:
        manifest = _read_json(manifest_path)
        protocol = load_protocol(PROJECT_ROOT / "configs" / "milestone2_conditions.yaml")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"status": "fail", "root": str(root_path), "issues": [f"cannot load manifest/protocol: {type(exc).__name__}"]}
    if manifest.get("protocol_version") != protocol["protocol_version"]:
        issues.append("manifest protocol version differs from frozen protocol")
    if manifest.get("model") != "gpt-6-luna" or manifest.get("auditor_model") != "gpt-6-luna":
        issues.append("manifest model is not the frozen gpt-6-luna model")
    if _contains_secret(manifest):
        issues.append("secret-like value found in manifest")
    episodes = [record for record in manifest.get("episodes") or [] if record.get("status") == "complete"]
    seen_keys: set[str] = set()
    condition_counts = {condition: 0 for condition in ("A", "B", "C", "D")}
    audit_count = 0
    for record in episodes:
        key = str(record.get("episode_key"))
        if key in seen_keys:
            issues.append(f"duplicate episode key: {key}")
        seen_keys.add(key)
        condition = str(record.get("condition"))
        if condition not in condition_counts:
            issues.append(f"unknown condition in episode: {key}")
        else:
            condition_counts[condition] += 1
        marker_path = Path(record.get("episode_marker", ""))
        evidence_dir = Path(record.get("evidence_dir", ""))
        if not marker_path.is_file():
            issues.append(f"{key}: missing completion marker")
            continue
        try:
            marker = _read_json(marker_path)
            adjudication = _read_json(marker_path.parent / "adjudication.json")
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"{key}: invalid marker/adjudication: {type(exc).__name__}")
            continue
        raw_root = marker.get("raw_result_root")
        if not raw_root:
            issues.append(f"{key}: missing raw result root")
        else:
            report = validate_experiment_root(raw_root)
            if report.status != "pass":
                issues.extend(f"{key}: raw artifact: {issue}" for issue in report.issues)
        try:
            bundle = extract_evidence_views(raw_root, case_id=str(record["case_id"]))
            validation = validate_evidence_bundle(bundle)
            if validation.get("sha256") != (marker.get("evidence_validation") or {}).get("sha256"):
                issues.append(f"{key}: evidence hashes do not match completion marker")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            issues.append(f"{key}: evidence extraction/validation failed: {type(exc).__name__}")
            continue
        if adjudication.get("case_id") != record.get("case_id"):
            issues.append(f"{key}: adjudication case id mismatch")
        audit_dir = marker_path.parent / "audits"
        for view in ("messages", "actions", "combined", "structured"):
            audit_path = audit_dir / f"{view}.json"
            if not audit_path.is_file():
                issues.append(f"{key}: missing auditor output for {view}")
                continue
            try:
                audit = _read_json(audit_path)
                evidence = _read_json(evidence_dir / f"{view}.json")
                if audit.get("case_id") != record.get("case_id") or audit.get("evidence_view") != view:
                    raise ValueError("audit metadata mismatch")
                evidence_ids = set()
                stack = [evidence]
                while stack:
                    item = stack.pop()
                    if isinstance(item, dict):
                        if isinstance(item.get("evidence_id"), str):
                            evidence_ids.add(item["evidence_id"])
                        stack.extend(item.values())
                    elif isinstance(item, list):
                        stack.extend(item)
                validate_auditor_output(audit["result"], evidence_ids=evidence_ids)
                if _contains_secret(audit):
                    issues.append(f"{key}: secret-like value found in auditor output {view}")
                audit_count += 1
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                issues.append(f"{key}: invalid auditor output {view}: {type(exc).__name__}")
        for view in ("messages", "actions", "combined", "structured"):
            packet = _read_json(evidence_dir / f"{view}.json")
            if _contains_secret(packet):
                issues.append(f"{key}: secret-like value found in evidence packet {view}")
            metadata_keys = set(packet)
            if metadata_keys & {"condition", "coalition", "colluders", "roles", "ground_truth"}:
                issues.append(f"{key}: privileged metadata key leaked in {view}")

    if expected_per_condition is not None:
        for condition, count in condition_counts.items():
            if count != expected_per_condition:
                issues.append(f"condition {condition}: expected {expected_per_condition} complete episodes, found {count}")
    budget_path = root_path / "budget.json"
    budget_summary = None
    if not budget_path.is_file():
        issues.append("missing shared budget.json")
    else:
        try:
            budget = PersistentBudgetLedger(
                budget_path,
                budget_usd=2.0,
                model="gpt-6-luna",
                per_request_cap_usd=0.02,
                max_input_tokens=16000,
                max_output_tokens=512,
            )
            budget_summary = budget.summary()
            if budget_summary["committed_upper_bound_usd"] > 2.0 + 1e-8:
                issues.append("shared conservative budget bound exceeds $2.00")
            if budget_summary["unsettled_request_count"]:
                issues.append("shared budget has unsettled requests; resume/reconcile before analysis")
        except Exception as exc:  # noqa: BLE001 - validator must report malformed ledger safely
            issues.append(f"invalid budget ledger: {type(exc).__name__}")
    return {
        "status": "pass" if not issues else "fail",
        "root": str(root_path),
        "completed_episode_count": len(episodes),
        "episodes_per_condition": condition_counts,
        "auditor_assessment_count": audit_count,
        "budget_summary": budget_summary,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-per-condition", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        result = validate(args.root, expected_per_condition=args.expected_per_condition)
    except Exception as exc:  # noqa: BLE001 - CLI must convert validation failures into a report
        print(json.dumps({"status": "fail", "issues": [f"validator error: {type(exc).__name__}: {exc}"]}, indent=2))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

