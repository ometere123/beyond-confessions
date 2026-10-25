"""Run the official Colosseum preflight/control through a direct OpenAI-compatible endpoint.

The default process only launches a child interpreter in a separately cloned starter checkout. The
child monkey-patches the OpenAI Chat Completions boundary to count actual requests and token usage;
request bodies, prompts, and credentials are never persisted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from beyond_confessions.config import DEFAULT_OPENAI_BASE_URL, OPENAI_CAP_USD, api_key_from_environment
from beyond_confessions.costs import price_for_model
from beyond_confessions.ledger import TimedCall, UsageLedger, redact_secret

EXPECTED_STARTER_COMMIT = "e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8"


def _default_starter_root() -> Path:
    configured = os.getenv("COLLOSSEUM_STARTER_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = [
        PROJECT_ROOT / "third_party" / "collusion_hackathon",
        PROJECT_ROOT.parent / "collusion_hackathon-sparse",
        PROJECT_ROOT.parent / "collusion_hackathon-reference",
    ]
    for candidate in candidates:
        if (candidate / "colosseum" / "pyproject.toml").is_file():
            return candidate.resolve()
    return candidates[0].resolve()


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


def _verify_starter(starter_root: Path, *, allow_unpinned: bool = False) -> str:
    if not (starter_root / "colosseum" / "experiments" / "preflight.py").is_file():
        raise RuntimeError(f"missing Colosseum preflight at {starter_root}")
    revision = _starter_revision(starter_root)
    if not allow_unpinned and revision != EXPECTED_STARTER_COMMIT:
        raise RuntimeError(
            f"starter revision {revision} is not the pinned milestone revision {EXPECTED_STARTER_COMMIT}; "
            "pass --allow-unpinned only after recording the new revision"
        )
    return revision


def _prepare_config(model: str) -> Path:
    source = PROJECT_ROOT / "configs" / "colosseum_positive_control_openai.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    for item in data.get("llm_models", []):
        llm = item.setdefault("llm", {})
        block = llm.setdefault("openrouter", {})
        block["model"] = model
        params = dict(block.get("params") or {})
        # The OpenAI API's current completion-token field is explicit and avoids silently ignoring a
        # budget. GPT-6 Luna additionally needs reasoning_effort=none for Chat Completions tool calls.
        params.pop("max_tokens", None)
        params["max_completion_tokens"] = min(int(params.get("max_completion_tokens", 1500)), 1500)
        if model.lower() == "gpt-6-luna":
            params.pop("temperature", None)
            params["reasoning_effort"] = "none"
        block["params"] = params
    temp_dir = PROJECT_ROOT / ".tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".yaml", prefix="positive-control-", dir=temp_dir, delete=False
    ) as handle:
        yaml.safe_dump(data, handle, sort_keys=False)
        path = Path(handle.name)
    return path


def _install_openai_counter(ledger: UsageLedger, *, model: str, max_requests: int = 80) -> None:
    """Instrument the actual Chat Completions method used by Terrarium's TogetherClient."""

    try:
        from openai.resources.chat.completions import Completions
    except ImportError as exc:
        raise RuntimeError("starter environment does not expose the OpenAI Chat Completions client") from exc

    original = Completions.create
    if getattr(original, "_beyond_confessions_wrapped", False):
        return

    def counted(self: Any, *args: Any, **kwargs: Any) -> Any:
        if len(ledger.records) >= max_requests:
            raise RuntimeError(f"OpenAI request guard reached {max_requests} calls; run stopped")
        requested_model = str(kwargs.get("model") or model)
        timed = TimedCall(ledger, model=requested_model, operation="colosseum.chat_completion")
        try:
            response = original(self, *args, **kwargs)
        except Exception as exc:
            timed.error(exc)
            raise
        timed.success(response)
        estimated = ledger.summary().get("estimated_cost_usd")
        if estimated is not None and estimated > OPENAI_CAP_USD:
            raise RuntimeError(
                f"estimated OpenAI spend ${estimated:.6f} exceeded the ${OPENAI_CAP_USD:.2f} milestone cap"
            )
        return response

    counted._beyond_confessions_wrapped = True
    Completions.create = counted


def _internal_preflight(model: str, *, ping: bool) -> int:
    from experiments import preflight

    argv = ["experiments.preflight.py"]
    if ping:
        argv.extend(["--ping", "--model", model])
    old_argv = sys.argv
    sys.argv = argv
    try:
        preflight.main()
    finally:
        sys.argv = old_argv
    return 0


def _internal_run(model: str, config_path: Path, out_dir: Path) -> int:
    from experiments.collusion.run import run_from_config

    key = api_key_from_environment()
    ledger = UsageLedger(secret=key)
    _install_openai_counter(ledger, model=model)
    result_root: Path | None = None
    try:
        result_root = asyncio.run(
            run_from_config(
                str(config_path),
                out_dir=str(out_dir),
                max_concurrent_runs=1,
                yes=True,
            )
        )
    except Exception as exc:
        failure_path = out_dir / "runner_failure_usage.json"
        ledger.write(failure_path)
        raise RuntimeError(redact_secret(f"Colosseum run failed: {exc}", key)) from exc
    usage_path = ledger.write(result_root / "usage.json")
    print(json.dumps({"status": "pass", "result_root": str(result_root), "usage_path": str(usage_path)}))
    return 0


def _run_child(
    *,
    starter_root: Path,
    action: str,
    model: str,
    config_path: Path | None,
    out_dir: Path | None,
    ping: bool,
) -> int:
    key = api_key_from_environment()
    env = os.environ.copy()
    env["LLM_BASE_URL"] = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)
    env["LLM_API_KEY"] = key
    # The starter preflight only recognizes its provider-key names. Keep the
    # actual request on the explicit custom endpoint above; this alias is only
    # a presence signal for the preflight check and is never printed.
    env["OPENROUTER_API_KEY"] = key
    env["LLM_MODEL"] = model
    env["PYTHONUTF8"] = "1"
    command = [
        "uv",
        "run",
        "--project",
        str(starter_root / "colosseum"),
        "python",
        str(Path(__file__).resolve()),
        "--internal",
        "--action",
        action,
        "--model",
        model,
    ]
    if config_path:
        command.extend(["--config", str(config_path)])
    if out_dir:
        command.extend(["--out-dir", str(out_dir)])
    if ping:
        command.append("--ping")
    result = subprocess.run(command, cwd=starter_root / "colosseum", env=env, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starter-root", type=Path, default=_default_starter_root())
    parser.add_argument("--model", default=os.getenv("BEYOND_CONFESSIONS_MODEL", "gpt-6-luna"))
    parser.add_argument("--allow-unpinned", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--ping", action="store_true")
    parser.add_argument("--internal", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--action", choices=("preflight", "run"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.internal:
        if args.action == "preflight":
            return _internal_preflight(args.model, ping=args.ping)
        if args.action == "run":
            if not args.config or not args.out_dir:
                raise SystemExit("internal run requires --config and --out-dir")
            return _internal_run(args.model, args.config, args.out_dir)
        raise SystemExit("internal action is required")

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key_from_environment()
    if price_for_model(args.model) is None:
        raise SystemExit(f"no checked price for model {args.model!r}; refusing an uncontrolled run")
    starter_root = args.starter_root.expanduser().resolve()
    revision = _verify_starter(starter_root, allow_unpinned=args.allow_unpinned)
    print(f"Starter verified at {revision}; credentials and prompts are not written to logs.")
    if args.preflight:
        return _run_child(
            starter_root=starter_root,
            action="preflight",
            model=args.model,
            config_path=None,
            out_dir=None,
            ping=args.ping,
        )

    config_path = _prepare_config(args.model)
    out_dir = (args.out_dir or PROJECT_ROOT / "artifacts" / "colosseum_positive_control").resolve()
    print("Running one bounded positive-control trial; no Modal deployment is attempted.")
    return _run_child(
        starter_root=starter_root,
        action="run",
        model=args.model,
        config_path=config_path,
        out_dir=out_dir,
        ping=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
