"""Command-line entry point for bounded milestone checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifacts import validate_experiment_root
from .config import ProjectConfig
from .connectivity import run_connectivity_probe
from .modal import estimate_modal_gpu_cost, estimate_startup_scenarios, qwen_7b_compatibility


def _json_dump(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="beyond-confessions")
    sub = parser.add_subparsers(dest="command", required=True)

    connectivity = sub.add_parser("connectivity", help="run a bounded OpenAI compatibility probe")
    connectivity.add_argument("--model", default=None)
    connectivity.add_argument("--mode", choices=("text", "tool", "structured", "all"), default="tool")
    connectivity.add_argument("--ledger", default=None)

    modal = sub.add_parser("modal-estimate", help="estimate Modal GPU cost without deploying")
    modal.add_argument("--gpu", default="A10")
    modal.add_argument("--active-seconds", type=float, default=300)
    modal.add_argument("--idle-seconds", type=float, default=0)

    validate = sub.add_parser("validate-results", help="validate Colosseum artifact structure")
    validate.add_argument("root")
    validate.add_argument("--allow-missing-usage", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "connectivity":
        try:
            config = ProjectConfig.from_environment()
            config.validate_guardrails()
            payload = run_connectivity_probe(
                model=args.model or config.model,
                mode=args.mode,
                max_estimated_cost_usd=config.initial_test_cap_usd,
                ledger_path=args.ledger,
                project_root=Path.cwd(),
            )
        except (RuntimeError, ValueError) as exc:
            # Provider errors are already redacted at the boundary; keep the CLI failure concise and
            # avoid exposing a traceback that could contain a third-party SDK diagnostic.
            print(f"connectivity failed: {exc}", file=sys.stderr)
            return 1
        _json_dump(payload)
        return 0
    if args.command == "modal-estimate":
        estimate = estimate_modal_gpu_cost(
            gpu=args.gpu, active_seconds=args.active_seconds, idle_seconds=args.idle_seconds
        )
        _json_dump(
            {
                "estimate": estimate.__dict__,
                "compatibility": qwen_7b_compatibility(),
                "scenarios": estimate_startup_scenarios(),
            }
        )
        return 0
    if args.command == "validate-results":
        report = validate_experiment_root(args.root, require_usage_ledger=not args.allow_missing_usage)
        _json_dump(report.as_dict())
        return 0 if report.status == "pass" else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
