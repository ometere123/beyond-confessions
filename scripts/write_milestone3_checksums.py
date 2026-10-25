"""Write SHA-256 checksums for the final Milestone 3 deliverables."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

STATIC_ARTIFACTS = (
    "evidence/milestone3/verification_report.json",
    "evidence/milestone3/case_studies.json",
    "evidence/milestone3/submission_qa.json",
    "evidence/milestone3/figures/figure_manifest.json",
    "paper/beyond_confessions_submission.md",
    "paper/plain_language_summary.md",
    "paper/evidence_reproducibility_checklist.md",
    "paper/submission_checklist.md",
    "docs/milestone3-scientific-verification.md",
    "output/pdf/beyond_confessions_submission.pdf",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("evidence/milestone3/checksums.sha256")
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    artifacts = list(STATIC_ARTIFACTS)
    figure_dir = root / "evidence" / "milestone3" / "figures"
    artifacts.extend(
        f"evidence/milestone3/figures/{path.name}"
        for path in sorted(figure_dir.glob("*.png"))
    )
    missing = [relative for relative in artifacts if not (root / relative).is_file()]
    if missing:
        raise SystemExit("Missing artifacts: " + ", ".join(missing))
    lines = []
    for relative in sorted(set(artifacts)):
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} checksums to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
