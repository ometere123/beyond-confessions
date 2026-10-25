"""Analyze validated Milestone 2 episodes and generate publication figures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from beyond_confessions.analysis import write_analysis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    result = write_analysis(args.root)
    print(
        json.dumps(
            {
                "status": "pass",
                "completed_episode_count": result["dataset"]["completed_episode_count"],
                "assessment_count": result["dataset"]["assessment_count"],
                "figures": len(result.get("figures") or []),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

