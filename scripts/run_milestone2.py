"""Run the frozen Milestone 2 pilot/main study with resumable evidence capture."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from beyond_confessions.artifacts import validate_experiment_root
from beyond_confessions.auditor import BlindedAuditor, write_audit_result
from beyond_confessions.budget import BudgetError, PersistentBudgetLedger
from beyond_confessions.config import (
    DEFAULT_OPENAI_BASE_URL,
    ProjectConfig,
    api_key_from_environment,
)
from beyond_confessions.costs import price_for_model
from beyond_confessions.evidence import extract_evidence_views, write_evidence_bundle
from beyond_confessions.ledger import TimedCall, UsageLedger, redact_secret
from beyond_confessions.study import (
    EXPECTED_STARTER_REVISION,
    adjudicate_episode,
    completed_episode_is_resumable,
    condition_by_id,
    json_sha256,
    load_protocol,
    new_manifest,
    prepare_starter_config,
    sha256_file,
    write_json,
)


def _starter_revision(starter_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(starter_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"starter is not a readable git checkout: {starter_root}")
    return result.stdout.strip()


def _verify_starter(starter_root: Path) -> str:
    if not (starter_root / "colosseum" / "experiments" / "preflight.py").is_file():
        raise RuntimeError(f"missing Colosseum preflight at {starter_root}")
    revision = _starter_revision(starter_root)
    if revision != EXPECTED_STARTER_REVISION:
        raise RuntimeError(
            f"starter revision {revision} is not the pinned revision {EXPECTED_STARTER_REVISION}"
        )
    status = subprocess.run(
        ["git", "-C", str(starter_root), "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise RuntimeError("pinned starter checkout is not clean; refusing a non-reproducible run")
    return revision


def _json_line(output: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _install_openai_counter(
    ledger: UsageLedger,
    budget: PersistentBudgetLedger,
    *,
    model: str,
    max_requests: int,
    max_output_tokens: int,
    usage_path: Path,
    secret: str,
) -> None:
    """Instrument the pinned requests-based TogetherClient boundary."""

    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("starter environment does not expose requests") from exc

    original = requests.Session.post
    if getattr(original, "_beyond_confessions_m2_wrapped", False):
        return

    def persist() -> None:
        ledger.write(usage_path)

    def counted(self: Any, url: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(url, str) or not url.rstrip("/").endswith("/chat/completions"):
            return original(self, url, *args, **kwargs)
        if len(ledger.records) >= max_requests:
            error = RuntimeError(f"per-episode request guard reached {max_requests} calls")
            ledger.record_error(error, model=model, operation="colosseum.chat_completion", elapsed_ms=0)
            persist()
            raise error

        payload: dict[str, Any] = {}
        raw_json = kwargs.get("json")
        if isinstance(raw_json, dict):
            payload = dict(raw_json)
        else:
            raw_data = kwargs.get("data")
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8", errors="replace")
            if isinstance(raw_data, str):
                try:
                    parsed = json.loads(raw_data)
                except (TypeError, ValueError):
                    parsed = {}
                if isinstance(parsed, dict):
                    payload = parsed

        requested_model = str(payload.get("model") or "")
        if requested_model != model:
            error = RuntimeError(
                f"starter requested model {requested_model!r}; expected the explicitly selected {model!r}"
            )
            ledger.record_error(error, model=requested_model or model, operation="colosseum.chat_completion", elapsed_ms=0)
            persist()
            raise error
        if requested_model.lower() == "gpt-6-luna":
            if "max_tokens" in payload and "max_completion_tokens" not in payload:
                payload["max_completion_tokens"] = payload.pop("max_tokens")
            payload["max_completion_tokens"] = min(
                int(payload.get("max_completion_tokens") or max_output_tokens), max_output_tokens
            )
            payload.pop("temperature", None)
            payload.setdefault("reasoning_effort", "none")
            if isinstance(raw_json, dict):
                kwargs["json"] = payload
            else:
                kwargs["data"] = json.dumps(payload)
        payload_chars = len(json.dumps(payload, ensure_ascii=False, default=str))
        try:
            reservation = budget.reserve(
                operation="colosseum.chat_completion",
                model=requested_model,
                payload_chars=payload_chars,
                max_output_tokens=int(payload.get("max_completion_tokens") or max_output_tokens),
                process=f"colosseum:{os.getpid()}",
            )
        except Exception as exc:
            ledger.record_error(exc, model=requested_model, operation="colosseum.chat_completion", elapsed_ms=0)
            persist()
            raise

        timed = TimedCall(ledger, model=requested_model, operation="colosseum.chat_completion")
        try:
            response = original(self, url, *args, **kwargs)
        except Exception as exc:
            timed.error(exc)
            persist()
            budget.settle(
                reservation,
                status="error",
                error_type=type(exc).__name__,
                error_message=redact_secret(str(exc), secret),
            )
            raise

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 200 or status_code >= 300:
            error = RuntimeError(f"HTTP {status_code}")
            timed.error(error)
            persist()
            budget.settle(reservation, status="error", error_type=type(error).__name__, error_message=str(error))
            return response
        try:
            response_body = response.json()
        except ValueError as exc:
            error = RuntimeError(f"response JSON decode failed: {type(exc).__name__}")
            timed.error(error)
            persist()
            budget.settle(reservation, status="error", error_type=type(error).__name__, error_message=str(error))
            return response
        if not isinstance(response_body, dict):
            error = RuntimeError("response JSON was not an object")
            timed.error(error)
            persist()
            budget.settle(reservation, status="error", error_type=type(error).__name__, error_message=str(error))
            return response
        record = timed.success({"id": response_body.get("id"), "usage": response_body.get("usage")})
        persist()
        budget.settle(reservation, status="success", usage=record.usage)
        return response

    counted._beyond_confessions_m2_wrapped = True
    requests.Session.post = counted


def _internal_run(args: argparse.Namespace) -> int:
    from experiments.collusion.run import run_from_config

    key = api_key_from_environment()
    budget = PersistentBudgetLedger(
        args.budget_path,
        budget_usd=float(os.environ.get("BEYOND_CONFESSIONS_BUDGET_USD", "2.0")),
        model=args.model,
        per_request_cap_usd=float(os.environ.get("BEYOND_CONFESSIONS_PER_REQUEST_CAP_USD", "0.02")),
        max_input_tokens=int(os.environ.get("BEYOND_CONFESSIONS_MAX_INPUT_TOKENS", "16000")),
        max_output_tokens=int(os.environ.get("BEYOND_CONFESSIONS_MAX_OUTPUT_TOKENS", "512")),
    )
    usage_path = Path(args.usage_path)
    ledger = UsageLedger(secret=key)
    _install_openai_counter(
        ledger,
        budget,
        model=args.model,
        max_requests=int(args.max_requests),
        max_output_tokens=int(args.max_output_tokens),
        usage_path=usage_path,
        secret=key,
    )
    result_root: Path | None = None
    try:
        result_root = asyncio.run(
            run_from_config(str(args.config), out_dir=str(args.out_dir), max_concurrent_runs=1, yes=True)
        )
        ledger.write(Path(result_root) / "usage.json")
        print(json.dumps({"status": "pass", "result_root": str(result_root)}))
        return 0
    except Exception as exc:  # noqa: BLE001 - the child must persist every provider/runtime failure
        ledger.write(Path(result_root or args.out_dir) / "runner_failure_usage.json")
        safe = redact_secret(f"Colosseum run failed: {type(exc).__name__}: {exc}", key)
        print(json.dumps({"status": "fail", "error": safe}))
        return 1


def _run_child(
    *,
    starter_root: Path,
    model: str,
    config_path: Path,
    out_dir: Path,
    budget_path: Path,
    usage_path: Path,
    max_requests: int,
    max_output_tokens: int,
    budget_usd: float,
    per_request_cap_usd: float,
    max_input_tokens: int,
    secret: str,
) -> tuple[int, dict[str, Any] | None, str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["LLM_BASE_URL"] = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)
    env["LLM_API_KEY"] = secret
    env["OPENROUTER_API_KEY"] = secret
    env["LLM_MODEL"] = model
    env["BEYOND_CONFESSIONS_BUDGET_PATH"] = str(budget_path)
    env["BEYOND_CONFESSIONS_USAGE_PATH"] = str(usage_path)
    env["BEYOND_CONFESSIONS_BUDGET_USD"] = str(budget_usd)
    env["BEYOND_CONFESSIONS_PER_REQUEST_CAP_USD"] = str(per_request_cap_usd)
    env["BEYOND_CONFESSIONS_MAX_INPUT_TOKENS"] = str(max_input_tokens)
    env["BEYOND_CONFESSIONS_MAX_OUTPUT_TOKENS"] = str(max_output_tokens)
    env["PYTHONUTF8"] = "1"
    command = [
        "uv",
        "run",
        "--project",
        str(starter_root / "colosseum"),
        "python",
        str(Path(__file__).resolve()),
        "--internal",
        "--model",
        model,
        "--config",
        str(config_path),
        "--out-dir",
        str(out_dir),
        "--budget-path",
        str(budget_path),
        "--usage-path",
        str(usage_path),
        "--max-requests",
        str(max_requests),
        "--max-output-tokens",
        str(max_output_tokens),
    ]
    result = subprocess.run(
        command,
        cwd=starter_root / "colosseum",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    parsed = _json_line(result.stdout)
    safe_stdout = redact_secret(result.stdout[-4000:], secret)
    safe_stderr = redact_secret(result.stderr[-4000:], secret)
    return result.returncode, parsed, safe_stdout, safe_stderr


def _manifest_path(output_root: Path) -> Path:
    return output_root / "study_manifest.json"


def _load_or_create_manifest(
    output_root: Path, *, protocol: dict[str, Any], model: str, budget_path: Path
) -> dict[str, Any]:
    path = _manifest_path(output_root)
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("protocol_version") != protocol["protocol_version"]:
            raise RuntimeError("existing output root was created with a different protocol")
        if value.get("model") != model or value.get("auditor_model") != model:
            raise RuntimeError("existing output root is pinned to a different model")
        return value
    value = new_manifest(protocol, output_root=output_root, model=model, budget_path=budget_path)
    write_json(path, value)
    return value


def _save_manifest(output_root: Path, manifest: dict[str, Any]) -> None:
    write_json(_manifest_path(output_root), manifest)


def _episode_record(manifest: dict[str, Any], episode_key: str) -> dict[str, Any] | None:
    for record in manifest.get("episodes", []):
        if record.get("episode_key") == episode_key:
            return record
    return None


def _replace_episode_record(manifest: dict[str, Any], record: dict[str, Any]) -> None:
    episodes = manifest.setdefault("episodes", [])
    for index, existing in enumerate(episodes):
        if existing.get("episode_key") == record.get("episode_key"):
            episodes[index] = record
            return
    episodes.append(record)


def _record_failure(manifest: dict[str, Any], failure: dict[str, Any]) -> None:
    manifest.setdefault("failures", []).append(failure)


def _case_id(condition_id: str, seed: int) -> str:
    condition_number = {"A": 1, "B": 2, "C": 3, "D": 4}[condition_id]
    return f"case-{condition_number * 100 + int(seed):04d}"


def _run_one_episode(
    *,
    starter_root: Path,
    output_root: Path,
    protocol: dict[str, Any],
    condition: dict[str, Any],
    seed: int,
    model: str,
    budget_path: Path,
    secret: str,
    manifest: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any] | None:
    episode_key = f"{condition['id']}-seed-{seed}"
    existing = _episode_record(manifest, episode_key)
    if existing and completed_episode_is_resumable(
        existing, protocol_version=str(protocol["protocol_version"]), model=model
    ):
        return existing
    episode_dir = output_root / "episodes" / episode_key
    episode_dir.mkdir(parents=True, exist_ok=True)
    case_id = _case_id(str(condition["id"]), int(seed))
    if dry_run:
        print(json.dumps({"episode_key": episode_key, "condition": condition["id"], "seed": seed, "case_id": case_id}))
        return None
    attempts = sorted(episode_dir.glob("attempt-*"))
    attempt_number = len(attempts) + 1
    attempt_dir = episode_dir / f"attempt-{attempt_number:03d}"
    raw_out = attempt_dir / "colosseum"
    usage_path = attempt_dir / "usage.json"
    config_path = attempt_dir / "config.yaml"
    prepare_starter_config(
        starter_root,
        protocol=protocol,
        condition=condition,
        model=model,
        seed=seed,
        output_dir=raw_out,
        destination=config_path,
    )
    returncode, child_payload, child_stdout, child_stderr = _run_child(
        starter_root=starter_root,
        model=model,
        config_path=config_path,
        out_dir=raw_out,
        budget_path=budget_path,
        usage_path=usage_path,
        max_requests=int(protocol["simulation"]["max_requests_per_episode"]),
        max_output_tokens=int(protocol["simulation"]["max_output_tokens"]),
        budget_usd=float(protocol["budget"]["total_openai_usd"]),
        per_request_cap_usd=float(protocol["budget"]["per_request_upper_bound_usd"]),
        max_input_tokens=int(protocol["budget"]["max_input_tokens"]),
        secret=secret,
    )
    if returncode != 0 or not child_payload or child_payload.get("status") != "pass":
        failure = {
            "episode_key": episode_key,
            "condition": condition["id"],
            "seed": int(seed),
            "attempt": attempt_number,
            "status": "failed",
            "returncode": returncode,
            "stdout_tail": child_stdout,
            "stderr_tail": child_stderr,
            "usage_path": str(usage_path.resolve()) if usage_path.exists() else None,
        }
        write_json(attempt_dir / "failure.json", failure)
        _record_failure(manifest, failure)
        _save_manifest(output_root, manifest)
        print(json.dumps({"status": "failed", "episode_key": episode_key, "attempt": attempt_number}))
        return None
    result_root = Path(str(child_payload.get("result_root"))).resolve()
    report = validate_experiment_root(result_root)
    write_json(attempt_dir / "artifact_validation.json", report.as_dict())
    if report.status != "pass":
        failure = {
            "episode_key": episode_key,
            "condition": condition["id"],
            "seed": int(seed),
            "attempt": attempt_number,
            "status": "invalid_artifacts",
            "issues": report.issues,
            "raw_result_root": str(result_root),
        }
        write_json(attempt_dir / "failure.json", failure)
        _record_failure(manifest, failure)
        _save_manifest(output_root, manifest)
        return None

    bundle = extract_evidence_views(result_root, case_id=case_id)
    evidence_dir = episode_dir / "evidence"
    evidence_validation = write_evidence_bundle(bundle, evidence_dir)
    adjudication = adjudicate_episode(
        result_root,
        condition=condition,
        seed=seed,
        case_id=case_id,
        bundle=bundle,
    )
    write_json(episode_dir / "adjudication.json", adjudication)
    marker = {
        "schema_version": "beyond-confessions-episode-1",
        "status": "complete",
        "episode_key": episode_key,
        "condition": condition["id"],
        "condition_name": condition["name"],
        "seed": int(seed),
        "case_id": case_id,
        "model": model,
        "protocol_version": protocol["protocol_version"],
        "raw_result_root": str(result_root),
        "raw_result_sha256": sha256_file(result_root / "summary.json"),
        "artifact_validation": report.as_dict(),
        "evidence_validation": evidence_validation,
        "adjudication_file": str((episode_dir / "adjudication.json").resolve()),
        "complete_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
    }
    marker_path = episode_dir / "episode_complete.json"
    write_json(marker_path, marker)
    record = {
        "episode_key": episode_key,
        "status": "complete",
        "condition": condition["id"],
        "condition_name": condition["name"],
        "seed": int(seed),
        "case_id": case_id,
        "episode_marker": str(marker_path.resolve()),
        "raw_result_root": str(result_root),
        "evidence_dir": str(evidence_dir.resolve()),
        "adjudication_file": str((episode_dir / "adjudication.json").resolve()),
        "audit_dir": str((episode_dir / "audits").resolve()),
    }
    _replace_episode_record(manifest, record)
    _save_manifest(output_root, manifest)
    print(json.dumps({"status": "complete", "episode_key": episode_key, "raw_result_root": str(result_root)}))
    return record


def _audit_one_episode(
    *,
    output_root: Path,
    protocol: dict[str, Any],
    record: dict[str, Any],
    model: str,
    base_url: str,
    secret: str,
    budget_path: Path,
    manifest: dict[str, Any],
) -> None:
    episode_dir = Path(record["episode_marker"]).parent
    evidence_dir = Path(record["evidence_dir"])
    audit_dir = episode_dir / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    for view_name in ("messages", "actions", "combined", "structured"):
        result_path = audit_dir / f"{view_name}.json"
        failure_path = audit_dir / f"{view_name}.failure.json"
        evidence = json.loads((evidence_dir / f"{view_name}.json").read_text(encoding="utf-8"))
        expected_hash = json_sha256(evidence)
        if result_path.exists():
            try:
                existing = json.loads(result_path.read_text(encoding="utf-8"))
                if existing.get("input_sha256") == __import__("hashlib").sha256(
                    json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest():
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        usage_path = audit_dir / f"{view_name}.usage.json"
        auditor = BlindedAuditor(
            model=model,
            base_url=base_url,
            budget=PersistentBudgetLedger(
                budget_path,
                budget_usd=float(protocol["budget"]["total_openai_usd"]),
                model=model,
                per_request_cap_usd=float(protocol["budget"]["per_request_upper_bound_usd"]),
                max_input_tokens=int(protocol["budget"]["max_input_tokens"]),
                max_output_tokens=int(protocol["budget"]["max_output_tokens"]),
            ),
            secret=secret,
            usage_path=usage_path,
            max_output_tokens=384,
        )
        try:
            value = auditor.audit(case_id=str(record["case_id"]), view_name=view_name, evidence=evidence)
            write_audit_result(result_path, value)
            if failure_path.exists():
                failure_path.unlink()
        except Exception as exc:  # noqa: BLE001 - preserve malformed provider output for resume
            failure = {
                "status": "failed",
                "episode_key": record["episode_key"],
                "case_id": record["case_id"],
                "evidence_view": view_name,
                "input_sha256": expected_hash,
                "error": redact_secret(f"{type(exc).__name__}: {exc}", secret)[:1000],
            }
            write_json(failure_path, failure)
            manifest.setdefault("failures", []).append(failure)
            _save_manifest(output_root, manifest)
            print(json.dumps({"status": "audit_failed", "episode_key": record["episode_key"], "view": view_name}))
            if isinstance(exc, BudgetError):
                break
        else:
            print(json.dumps({"status": "audited", "episode_key": record["episode_key"], "view": view_name}))


def _parse_condition_ids(value: str) -> list[str]:
    ids = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not ids or any(item not in {"A", "B", "C", "D"} for item in ids):
        raise ValueError("conditions must be a comma-separated subset of A,B,C,D")
    return ids


def _run_external(args: argparse.Namespace) -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    config = ProjectConfig.from_environment(dotenv_path=PROJECT_ROOT / ".env")
    config.validate_guardrails()
    protocol = load_protocol(args.protocol)
    model = args.model or config.model
    if model != protocol["model"]["agent_model"]:
        raise RuntimeError(
            f"selected model {model!r} differs from frozen protocol model {protocol['model']['agent_model']!r}; "
            "no silent substitution is allowed"
        )
    if price_for_model(model) is None:
        raise RuntimeError(f"no checked price for model {model!r}")
    starter_root = Path(args.starter_root).expanduser().resolve()
    revision = _verify_starter(starter_root)
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    budget_path = output_root / "budget.json"
    PersistentBudgetLedger(
        budget_path,
        budget_usd=float(protocol["budget"]["total_openai_usd"]),
        model=model,
        per_request_cap_usd=float(protocol["budget"]["per_request_upper_bound_usd"]),
        max_input_tokens=int(protocol["budget"]["max_input_tokens"]),
        max_output_tokens=int(protocol["budget"]["max_output_tokens"]),
    )
    manifest = _load_or_create_manifest(output_root, protocol=protocol, model=model, budget_path=budget_path)
    manifest["starter_revision_verified"] = revision
    manifest["protocol_file_sha256"] = protocol.get("protocol_file_sha256")
    _save_manifest(output_root, manifest)
    secret = api_key_from_environment()
    condition_ids = _parse_condition_ids(args.conditions)
    if args.pilot and args.main:
        raise ValueError("choose --pilot or --main, not both")
    if args.main:
        seeds = list(protocol["seeds"]["main"])
    elif args.pilot:
        seeds = list(protocol["seeds"]["pilot"])
    elif args.audit_only:
        seeds = []
    else:
        raise ValueError("choose --pilot, --main, or --audit-only")
    if args.seeds:
        seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
    for condition_id in condition_ids:
        condition = condition_by_id(protocol, condition_id)
        for seed in seeds:
            _run_one_episode(
                starter_root=starter_root,
                output_root=output_root,
                protocol=protocol,
                condition=condition,
                seed=seed,
                model=model,
                budget_path=budget_path,
                secret=secret,
                manifest=manifest,
                dry_run=args.dry_run,
            )
    if not args.dry_run and not args.no_auditor:
        for record in list(manifest.get("episodes", [])):
            if record.get("status") != "complete":
                continue
            _audit_one_episode(
                output_root=output_root,
                protocol=protocol,
                record=record,
                model=model,
                base_url=config.openai_base_url,
                secret=secret,
                budget_path=budget_path,
                manifest=manifest,
            )
    manifest["budget_summary"] = PersistentBudgetLedger(
        budget_path,
        budget_usd=float(protocol["budget"]["total_openai_usd"]),
        model=model,
        per_request_cap_usd=float(protocol["budget"]["per_request_upper_bound_usd"]),
        max_input_tokens=int(protocol["budget"]["max_input_tokens"]),
        max_output_tokens=int(protocol["budget"]["max_output_tokens"]),
    ).summary()
    _save_manifest(output_root, manifest)
    print(json.dumps({"status": "pass", "output_root": str(output_root), "budget": manifest["budget_summary"]}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starter-root", type=Path, default=Path(os.getenv("COLLOSSEUM_STARTER_ROOT", "C:\\CH2")))
    parser.add_argument("--output-root", type=Path, default=Path("C:\\BCM2"))
    parser.add_argument("--protocol", type=Path, default=PROJECT_ROOT / "configs" / "milestone2_conditions.yaml")
    parser.add_argument("--model", default=None)
    parser.add_argument("--conditions", default="A,B,C,D")
    parser.add_argument("--seeds", default=None, help="override the frozen seed list, e.g. 1,2")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--main", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--no-auditor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--internal", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--out-dir", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--budget-path", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--usage-path", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--max-requests", type=int, default=40, help=argparse.SUPPRESS)
    parser.add_argument("--max-output-tokens", type=int, default=512, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.internal:
        if not all((args.config, args.out_dir, args.budget_path, args.usage_path)):
            raise SystemExit("internal run requires config, out-dir, budget-path, and usage-path")
        return _internal_run(args)
    try:
        return _run_external(args)
    except (RuntimeError, ValueError, BudgetError, FileNotFoundError) as exc:
        print(f"milestone2 failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

