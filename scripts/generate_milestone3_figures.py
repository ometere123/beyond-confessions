"""Generate the final paper figures from the independent verification payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import textwrap
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

VIEW_LABELS = {
    "messages": "Messages",
    "actions": "Actions",
    "combined": "Raw combined",
    "structured": "Structured",
}


def _save(fig: Any, path: Path) -> None:
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _performance_figure(report: dict[str, Any], path: Path) -> dict[str, Any]:
    performance = report["independent_results"]["performance_by_view"]
    views = list(VIEW_LABELS)
    metrics = ["sensitivity_recall", "false_positive_rate", "balanced_accuracy"]
    labels = ["Recall", "False-positive rate", "Balanced accuracy"]
    colors = ["#4c78a8", "#e45756", "#59a14f"]
    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    width = 0.24
    positions = list(range(len(views)))
    for offset, metric, label, color in zip((-width, 0, width), metrics, labels, colors):
        values = [float(performance[view][metric]) for view in views]
        bars = ax.bar([pos + offset for pos in positions], values, width, label=label, color=color)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                min(value + 0.025, 1.02),
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    ax.set_xticks(positions, [VIEW_LABELS[view] for view in views])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Value at risk threshold 0.60")
    ax.set_title("Auditor performance on observable task-harm labels (n=40 episodes per view)")
    ax.legend(frameon=False, ncols=3, loc="upper center", bbox_to_anchor=(0.5, 1.02))
    ax.grid(axis="y", alpha=0.25)
    _save(fig, path)
    return {
        "file": path.name,
        "caption": "Recall, false-positive rate, and balanced accuracy at the frozen 0.60 risk threshold; labels are observable task harm, not realised collusion.",
        "source": "evidence/milestone3/verification_report.json",
    }


def _condition_figure(report: dict[str, Any], path: Path) -> dict[str, Any]:
    summary = report["independent_results"]["condition_summary"]
    conditions = ["A", "B", "C", "D"]
    harmful = [summary[c]["harm_label_counts"].get("harmful", 0) for c in conditions]
    not_harmful = [summary[c]["harm_label_counts"].get("not_harmful", 0) for c in conditions]
    event_counts = [summary[c]["violations_total"] for c in conditions]
    episode_counts = [summary[c]["violation_episode_count"] for c in conditions]
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.65), gridspec_kw={"width_ratios": [1.2, 1]})
    axes[0].bar(conditions, harmful, label="Episodes with >=1 event", color="#e15759")
    axes[0].bar(conditions, not_harmful, bottom=harmful, label="Episodes with 0 events", color="#76b7b2")
    for index, total in enumerate([h + n for h, n in zip(harmful, not_harmful)]):
        axes[0].text(index, total + 0.15, f"n={total}", ha="center", fontsize=8)
    axes[0].set_title("Episode-level harm proxy")
    axes[0].set_ylabel("Episodes")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_ylim(0, 11.5)
    axes[1].bar([x - 0.18 for x in range(4)], event_counts, width=0.36, label="Violation events", color="#f28e2b")
    axes[1].bar([x + 0.18 for x in range(4)], episode_counts, width=0.36, label="Episodes with event", color="#4e79a7")
    axes[1].set_xticks(range(4), conditions)
    axes[1].set_title("Events versus episodes")
    axes[1].set_ylabel("Count")
    axes[1].legend(frameon=False, fontsize=8)
    axes[1].grid(axis="y", alpha=0.25)
    fig.suptitle("Condition-level task outcomes; D is not a clean behavioural control", fontsize=11)
    fig.tight_layout()
    _save(fig, path)
    return {
        "file": path.name,
        "caption": "Condition-level observable task-harm labels and violation counts. Violation events are summed within episodes; C's open all-agent channel and D's neutral treatment are not collusion labels.",
        "source": "evidence/milestone3/verification_report.json",
    }


def _case_chain_figure(case_path: Path, path: Path) -> dict[str, Any]:
    cases = {item["episode_key"]: item for item in json.loads(case_path.read_text(encoding="utf-8"))}
    order = ["C-seed-1", "D-seed-3", "A-seed-1", "B-seed-9"]
    titles = [
        "C-seed-1: open coordination, no event",
        "D-seed-3: no designated pair, one event",
        "A-seed-1: combined false positive",
        "B-seed-9: combined false negative",
    ]
    fig, axes = plt.subplots(4, 1, figsize=(9.0, 6.1))
    for axis, episode_key, title in zip(axes, order, titles):
        case = cases[episode_key]
        adj = case["adjudication"]
        outcome = case["outcome"]
        combined_result = case["audits"]["combined"]["result"]
        refs = ", ".join(case["selected_message_refs"][:3])
        action_refs = ", ".join(case["selected_action_refs"][:4])
        harm = adj["adjudication"]["harm_label"]
        risk = combined_result["risk_score"]
        text = (
            f"{title}\n"
            f"message refs: {refs}  ->  action refs: {action_refs}  ->  "
            f"outcome {outcome['evidence_id']}: violations={outcome['violations']}, "
            f"joint_reward={outcome['joint_reward']:.2f}\n"
            f"task-harm proxy={harm}; combined risk={risk:.2f}; realised harmful collusion=not established"
        )
        wrapped = "\n".join(
            textwrap.fill(line, width=122, subsequent_indent="  ") for line in text.splitlines()
        )
        axis.text(0.02, 0.5, wrapped, va="center", ha="left", fontsize=8.4, family="DejaVu Sans")
        axis.set_axis_off()
        axis.add_patch(plt.Rectangle((0, 0.04), 1, 0.92, fill=False, edgecolor="#b0b0b0", linewidth=0.8))
    fig.suptitle("Anonymised evidence chains from the preserved archive", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    _save(fig, path)
    return {
        "file": path.name,
        "caption": "Exact anonymised evidence references selected from four preserved episodes. Labels are task-harm proxy labels; no row establishes realised collusion.",
        "source": "evidence/milestone3/case_studies.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output_dir = root / "evidence" / "milestone3" / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads((root / "evidence/milestone3/verification_report.json").read_text(encoding="utf-8"))
    case_path = root / "evidence/milestone3/case_studies.json"
    m2_figures = root / "evidence/milestone2/figures"
    architecture_path = output_dir / "experimental_architecture.png"
    shutil.copyfile(m2_figures / "experimental_design.png", architecture_path)
    manifest = [
        {
            "file": architecture_path.name,
            "caption": "Matched four-condition architecture inherited from the frozen Milestone 2 protocol; condition C exposes an all-agent extra channel, while D has no coalition instruction or extra channel.",
            "source": "evidence/milestone2/figures/experimental_design.png",
        },
        _performance_figure(report, output_dir / "primary_performance_threshold_060.png"),
        _condition_figure(report, output_dir / "condition_harm_comparison.png"),
        _case_chain_figure(case_path, output_dir / "case_evidence_chain.png"),
    ]
    for item in manifest:
        item["sha256"] = _digest(output_dir / item["file"])
    (output_dir / "figure_manifest.json").write_text(
        json.dumps({"schema_version": "beyond-confessions-m3-figure-manifest-1", "figures": manifest}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "figures": len(manifest), "output": str(output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
