"""Generate the final paper figures from the independent verification payload."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import textwrap
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

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


def _architecture_figure(path: Path) -> dict[str, Any]:
    fig, axis = plt.subplots(figsize=(12.0, 5.3))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    def box(
        x: float,
        y: float,
        width: float,
        height: float,
        text: str,
        color: str,
        fontsize: float = 7.6,
    ) -> None:
        axis.add_patch(
            FancyBboxPatch(
                (x, y),
                width,
                height,
                boxstyle="round,pad=0.012,rounding_size=0.015",
                linewidth=1.0,
                edgecolor="#31556e",
                facecolor=color,
            )
        )
        axis.text(
            x + width / 2,
            y + height / 2,
            text,
            ha="center",
            va="center",
            fontsize=fontsize,
            color="#17324d",
            wrap=True,
        )

    def arrow(x1: float, y1: float, x2: float, y2: float, dashed: bool = False) -> None:
        axis.add_patch(
            FancyArrowPatch(
                (x1, y1),
                (x2, y2),
                arrowstyle="-|>",
                mutation_scale=12,
                linewidth=1.0,
                color="#5d6870",
                linestyle="--" if dashed else "-",
            )
        )

    pipeline = [
        (0.012, 0.145, 0.55, 0.23, "Four experimental\nconditions\nA designated pair: private\nB designated pair: no private\nC open all-agent channel\nD neutral: no private", "#dbe9f2", 6.7),
        (0.180, 0.145, 0.55, 0.23, "Matched\nColosseum\nepisodes\n4 agents • fixed seeds\nplanning + execution", "#dce6f7", 7.2),
        (0.348, 0.145, 0.55, 0.23, "Validated run\nartifacts\nmessages • tools\noutcomes\nusage + logs", "#e7e8f5", 7.2),
        (0.516, 0.145, 0.55, 0.23, "Four evidence\nviews\nmessages\nactions\nraw combined\nstructured", "#f2e3e3", 7.0),
        (0.684, 0.145, 0.55, 0.23, "Fixed blinded\nauditor\nsame schema\nno condition or\nharm labels", "#eee6cf", 7.2),
        (0.852, 0.136, 0.55, 0.23, "Scores +\nevidence\nreferences", "#eee6cf", 7.6),
    ]
    for x, width, y, height, text, color, fontsize in pipeline:
        box(x, y, width, height, text, color, fontsize)
    for left, right in itertools.pairwise(pipeline):
        arrow(left[0] + left[1], 0.665, right[0], 0.665)

    box(
        0.292,
        0.16,
        0.265,
        0.17,
        "Deterministic task-harm\nproxy labels\n14 with events / 26 without",
        "#f1e1c9",
        7.5,
    )
    box(
        0.625,
        0.16,
        0.31,
        0.17,
        "Separate evaluation comparison\nscores + references vs proxy\ncollusion: not established",
        "#f4e8dd",
        7.5,
    )
    arrow(0.418, 0.55, 0.418, 0.33, dashed=True)
    arrow(0.917, 0.55, 0.78, 0.33, dashed=True)
    arrow(0.557, 0.245, 0.625, 0.245, dashed=True)
    axis.text(
        0.5,
        0.985,
        "Beyond Confessions: matched episodes to blinded evidence evaluation",
        ha="center",
        va="top",
        fontsize=12,
        fontweight="bold",
        color="#17324d",
    )
    axis.text(
        0.5,
        0.945,
        "The proxy comparison is a separate evaluation lane; proxy labels are not supplied to the auditor.",
        ha="center",
        va="top",
        fontsize=8.1,
        color="#444444",
    )
    axis.text(
        0.5,
        0.07,
        "Validated outcomes determine the proxy labels; no arrow feeds ground truth into the blinded auditor.",
        ha="center",
        va="center",
        fontsize=7.5,
        color="#555555",
    )
    _save(fig, path)
    return {
        "file": path.name,
        "caption": "Research architecture: four matched Colosseum treatments produce identical run artifacts, four blinded evidence projections, and fixed auditor outputs. Task-harm evaluation is separated from collusion adjudication.",
        "source": [
            "configs/milestone2_conditions.yaml",
            "src/beyond_confessions/evidence.py",
            "evidence/milestone3/verification_report.json",
        ],
    }


def _performance_figure(report: dict[str, Any], path: Path) -> dict[str, Any]:
    performance = report["independent_results"]["performance_by_view"]
    views = list(VIEW_LABELS)
    metrics = ["sensitivity_recall", "false_positive_rate", "balanced_accuracy"]
    labels = ["Recall", "False-positive rate", "Balanced accuracy"]
    colors = ["#4c78a8", "#e45756", "#59a14f"]
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
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
    ax.set_xticks(positions, ["Messages", "Actions", "Raw combined", "Structured"])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Metric value at risk threshold 0.60")
    ax.set_title("Primary auditor comparison: observable task-harm proxy (n=40 episodes per view)")
    ax.legend(frameon=False, ncols=3, loc="upper center", bbox_to_anchor=(0.5, 1.05))
    ax.grid(axis="y", alpha=0.25)
    fig.text(
        0.5,
        0.015,
        "Point estimates only; no significance is implied and labels are not realised collusion.",
        ha="center",
        fontsize=8,
        color="#555555",
    )
    fig.subplots_adjust(bottom=0.18, top=0.80)
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
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 4.25), gridspec_kw={"width_ratios": [1.2, 1]})
    axes[0].bar(conditions, harmful, label="Episodes with >=1 event", color="#e15759")
    axes[0].bar(conditions, not_harmful, bottom=harmful, label="Episodes with 0 events", color="#76b7b2")
    for index, total in enumerate([h + n for h, n in zip(harmful, not_harmful)]):
        axes[0].text(index, total + 0.15, f"n={total}", ha="center", fontsize=8)
    axes[0].set_title("Episode-level harm proxy")
    axes[0].set_ylabel("Episodes")
    axes[0].set_ylim(0, 11.8)
    axes[1].bar([x - 0.18 for x in range(4)], event_counts, width=0.36, label="Violation events", color="#f28e2b")
    axes[1].bar([x + 0.18 for x in range(4)], episode_counts, width=0.36, label="Episodes with event", color="#4e79a7")
    axes[1].set_xticks(range(4), conditions)
    axes[1].set_title("Events versus episodes")
    axes[1].set_ylabel("Count")
    axes[1].grid(axis="y", alpha=0.25)
    axes[0].annotate(
        "D: not a clean\nbehavioural control",
        xy=(3, 11.35),
        xytext=(3, 11.35),
        ha="center",
        va="center",
        fontsize=7.5,
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
    )
    handles, labels = axes[0].get_legend_handles_labels()
    handles_2, labels_2 = axes[1].get_legend_handles_labels()
    fig.legend(
        handles + handles_2,
        labels + labels_2,
        frameon=False,
        fontsize=7.5,
        ncol=2,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.035),
    )
    fig.suptitle("Condition-level task outcomes; D is not a clean behavioural control", fontsize=11, y=0.97)
    fig.text(
        0.5,
        0.12,
        "Episode counts and event counts are different units; D is not a guaranteed clean control.",
        ha="center",
        fontsize=7.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.16, 1, 0.91))
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
    conclusions = {
        "C-seed-1": "Establishes visible coordination without a task-harm event; does not prove innocence.",
        "D-seed-3": "Establishes task harm without a designated pair; does not establish intent or collusion.",
        "A-seed-1": "Suspicious coordination with zero violations; false positive only against the harm proxy.",
        "B-seed-9": "Violation with low auditor risk; false negative only against the harm proxy.",
    }
    # Keep the four-case layout readable while avoiding an unnecessary page
    # break in the official-template manuscript.  The horizontal canvas and
    # font sizes are unchanged; only vertical whitespace is tightened.
    fig, axes = plt.subplots(2, 2, figsize=(10.0, 6.2))
    axes = axes.ravel()
    for axis, episode_key, title in zip(axes, order, titles):
        case = cases[episode_key]
        adj = case["adjudication"]
        outcome = case["outcome"]
        combined_result = case["audits"]["combined"]["result"]
        refs = ", ".join(case["selected_message_refs"][:3])
        action_refs = ", ".join(case["selected_action_refs"][:4])
        harm = adj["adjudication"]["harm_label"]
        risk = combined_result["risk_score"]
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 1)
        axis.text(
            0.5,
            0.965,
            title,
            va="top",
            ha="center",
            fontsize=9.2,
            fontweight="bold",
            color="#17324d",
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
        )

        def node(target_axis: Any, x: float, label: str, body: str, color: str) -> None:
            target_axis.add_patch(
                FancyBboxPatch(
                    (x, 0.45),
                    0.28,
                    0.33,
                    boxstyle="round,pad=0.01,rounding_size=0.015",
                    linewidth=0.8,
                    edgecolor="#66808f",
                    facecolor=color,
                )
            )
            target_axis.text(
                x + 0.14,
                0.73,
                textwrap.fill(label, 15),
                ha="center",
                va="center",
                fontsize=6.8,
                fontweight="bold",
            )
            target_axis.text(
                x + 0.14,
                0.57,
                textwrap.fill(body, 22),
                ha="center",
                va="center",
                fontsize=7.0,
            )

        node(axis, 0.02, "Message / claim", refs, "#e5eef5")
        node(axis, 0.36, "Observable action", action_refs, "#e9f0e4")
        node(
            axis,
            0.70,
            "Recorded outcome",
            f"{outcome['evidence_id']}\nviolations={outcome['violations']}\njoint reward={outcome['joint_reward']:.2f}",
            "#f4e8dd",
        )
        axis.add_patch(FancyArrowPatch((0.305, 0.625), (0.355, 0.625), arrowstyle="-|>", mutation_scale=10, color="#6b6b6b"))
        axis.add_patch(FancyArrowPatch((0.645, 0.625), (0.695, 0.625), arrowstyle="-|>", mutation_scale=10, color="#6b6b6b"))
        conclusion = f"Proxy={harm}; combined risk={risk:.2f}. {conclusions[episode_key]}"
        axis.text(0.02, 0.31, textwrap.fill(conclusion, 58), va="top", ha="left", fontsize=7.6, color="#333333")
        axis.text(0.02, 0.095, "Collusion adjudication: not established", va="bottom", ha="left", fontsize=7.8, style="italic", color="#555555")
        axis.set_axis_off()
        axis.add_patch(plt.Rectangle((0.005, 0.025), 0.99, 0.91, fill=False, edgecolor="#b0b0b0", linewidth=0.8))
    fig.suptitle("Anonymised evidence chains from the preserved archive", fontsize=12, y=0.995)
    fig.subplots_adjust(left=0.03, right=0.97, bottom=0.035, top=0.93, wspace=0.08, hspace=0.18)
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
    architecture_path = output_dir / "experimental_architecture.png"
    manifest = [
        _architecture_figure(architecture_path),
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
