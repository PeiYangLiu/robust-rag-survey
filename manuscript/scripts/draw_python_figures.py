#!/usr/bin/env python3
"""Generate reproducible Python figures for the Robust RAG survey."""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures" / "generated"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#1F3A6B"
BLUE = "#3D6FC3"
TEAL = "#4D8786"
BRICK = "#A06058"
SAGE = "#5E8466"
PLUM = "#836B91"
OCHRE = "#A98552"
GRAY = "#6B7280"
LIGHT_GRID = "#EEF4FA"

plt.rcParams.update(
    {
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.family": "DejaVu Sans",
    }
)


def wrap(label: str, width: int) -> str:
    return "\n".join(textwrap.wrap(label, width=width, break_long_words=False))


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight", pad_inches=0.18)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight", pad_inches=0.18)
    print(OUT / f"{name}.png")
    print(OUT / f"{name}.pdf")


def draw_failure_intervention_matrix() -> None:
    cols = [
        "Noisy\nRetrieval",
        "Distraction",
        "Knowledge\nConflict",
        "Adversarial\nCorruption",
        "OOD /\nUncertainty",
        "Calibration /\nAbstention",
    ]
    rows = [
        "Corpus / KB",
        "Retriever",
        "Context\nAssembly",
        "Generator",
        "System\nControl",
        "Evaluation",
    ]
    # Literature coverage, 0=sparse, 1=moderate, 2=dense.
    coverage = np.array(
        [
            [1, 0, 1, 2, 0, 0],
            [2, 1, 1, 2, 1, 1],
            [2, 2, 2, 1, 1, 1],
            [1, 1, 2, 2, 1, 2],
            [1, 1, 2, 1, 2, 2],
            [2, 2, 2, 2, 2, 2],
        ]
    )
    tags = [
        ["chunking\nprovenance", "", "freshness\nsources", "PoisonedRAG\nBadRAG", "", ""],
        ["RAAT\nUDCG", "LC-RAG", "SourcePref", "ProGRank\nRobustRAG", "retrieval\nconfidence", "NAACL-Cal"],
        ["FILCO\nRECOMP", "CUB\nFirstDrop", "FaithfulRAG\nAstuteRAG", "TrustRAG\nSeCon-RAG", "SuffCtx", "SURE-RAG"],
        ["CoN", "context\nutilization", "CoRect\nParamMute", "Phantom\nAIP", "FaithUQ", "CalibRAG"],
        ["re-query", "filter / ask", "SABER\nAstuteRAG", "traceback\nquarantine", "Self-RAG\nCRAG", "abstain\nclarify"],
        ["RGB\nMagicMushroom", "CUB\nUDCG", "MAGIC\nWikiContradict", "SafeRAG\nPoisonArena", "URAG\nMTRAG-UN", "ECE\nselective risk"],
    ]

    cmap = LinearSegmentedColormap.from_list("coverage", ["#F3F6FA", "#AFC6DE", NAVY])
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.imshow(coverage, cmap=cmap, vmin=0, vmax=2, aspect="auto")

    for i in range(coverage.shape[0]):
        for j in range(coverage.shape[1]):
            color = "white" if coverage[i, j] == 2 else "#172033"
            ax.text(j, i, tags[i][j], ha="center", va="center", fontsize=12.5, color=color, weight="semibold")

    ax.set_xticks(np.arange(len(cols)))
    ax.set_xticklabels(cols, fontsize=15, weight="bold", color=NAVY)
    ax.set_yticks(np.arange(len(rows)))
    ax.set_yticklabels(rows, fontsize=15, weight="bold", color=NAVY)
    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False, length=0)

    # Cell borders.
    ax.set_xticks(np.arange(-0.5, len(cols), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(rows), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=3)
    ax.tick_params(which="minor", bottom=False, left=False)

    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_title("Failure Mode × Intervention Matrix for Robust RAG", fontsize=27, weight="bold", color=NAVY, pad=52)
    fig.text(
        0.5,
        0.925,
        "Darker cells indicate denser research coverage; light cells indicate under-explored opportunities.",
        ha="center",
        fontsize=15,
        color=GRAY,
    )

    legend_elements = [
        Rectangle((0, 0), 1, 1, facecolor="#F3F6FA", edgecolor="#B7C3D0", label="Sparse"),
        Rectangle((0, 0), 1, 1, facecolor="#AFC6DE", edgecolor="#B7C3D0", label="Moderate"),
        Rectangle((0, 0), 1, 1, facecolor=NAVY, edgecolor=NAVY, label="Dense"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=3,
        frameon=False,
        fontsize=14,
    )

    ax.set_xlabel("Failure Modes", fontsize=16, weight="bold", color=NAVY, labelpad=20)
    ax.xaxis.set_label_position("top")
    ax.set_ylabel("Intervention Points", fontsize=16, weight="bold", color=NAVY, labelpad=18)

    plt.subplots_adjust(left=0.13, right=0.98, top=0.82, bottom=0.17)
    save(fig, "fig5_failure_intervention_matrix_py_4k")
    plt.close(fig)


def draw_benchmark_landscape() -> None:
    fig, ax = plt.subplots(figsize=(19.2, 10.8))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Quadrant backgrounds.
    ax.add_patch(Rectangle((0, 0), 0.5, 0.5, color="#EAF3FF", alpha=0.85, zorder=0))
    ax.add_patch(Rectangle((0, 0.5), 0.5, 0.5, color="#EAF8F0", alpha=0.85, zorder=0))
    ax.add_patch(Rectangle((0.5, 0), 0.5, 0.5, color="#FFF0EF", alpha=0.85, zorder=0))
    ax.add_patch(Rectangle((0.5, 0.5), 0.5, 0.5, color="#F5F0FF", alpha=0.85, zorder=0))

    ax.text(0.25, 0.06, "Retrieval Noise", ha="center", fontsize=17, weight="bold", color="#2D5F9A", alpha=0.65)
    ax.text(0.25, 0.94, "Answerability & Calibration", ha="center", fontsize=17, weight="bold", color=SAGE, alpha=0.72)
    ax.text(0.75, 0.06, "Attack / Defense", ha="center", fontsize=17, weight="bold", color=BRICK, alpha=0.72)
    ax.text(0.75, 0.94, "End-to-End Robust Control", ha="center", fontsize=17, weight="bold", color=PLUM, alpha=0.72)

    points = [
        ("RGB", 0.24, 0.42, 760, BLUE),
        ("RAGTruth", 0.28, 0.72, 620, SAGE),
        ("MagicMushroom", 0.18, 0.28, 620, BLUE),
        ("QueryRobust", 0.12, 0.36, 520, BLUE),
        ("URAG", 0.36, 0.76, 560, PLUM),
        ("MTRAG-UN", 0.43, 0.86, 560, PLUM),
        ("CRUMQs", 0.42, 0.64, 500, PLUM),
        ("SURE-RAG", 0.56, 0.72, 540, PLUM),
        ("PoisonedRAG", 0.78, 0.29, 640, BRICK),
        ("PoisonArena", 0.70, 0.37, 650, BRICK),
        ("SafeRAG", 0.86, 0.41, 620, BRICK),
        ("RAG-QA Arena", 0.34, 0.51, 540, BLUE),
    ]

    # Draw bubbles first, then place dark labels with small offsets so text remains
    # readable on light quadrant backgrounds.
    label_offsets = {
        "RGB": (0.000, 0.045),
        "RAGTruth": (0.000, 0.050),
        "MagicMushroom": (0.000, -0.055),
        "QueryRobust": (0.000, 0.052),
        "URAG": (0.000, 0.050),
        "MTRAG-UN": (0.000, 0.050),
        "CRUMQs": (0.000, -0.055),
        "SURE-RAG": (0.000, 0.052),
        "PoisonedRAG": (0.000, -0.055),
        "PoisonArena": (0.000, 0.052),
        "SafeRAG": (0.000, 0.052),
        "RAG-QA Arena": (0.000, -0.055),
    }
    for name, x, y, size, color in points:
        ax.scatter([x], [y], s=size, color=color, alpha=0.88, edgecolor="white", linewidth=2.8, zorder=3)
    for name, x, y, size, color in points:
        dx, dy = label_offsets.get(name, (0, 0.045))
        ax.text(
            x + dx,
            y + dy,
            name,
            ha="center",
            va="center",
            fontsize=12.5,
            weight="bold",
            color=NAVY,
            zorder=5,
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.78),
        )

    ax.annotate("", xy=(1.02, 0), xytext=(-0.02, 0), arrowprops=dict(arrowstyle="->", color=NAVY, lw=2.4))
    ax.annotate("", xy=(0, 1.02), xytext=(0, -0.02), arrowprops=dict(arrowstyle="->", color=NAVY, lw=2.4))
    ax.set_xlim(-0.04, 1.04)
    ax.set_ylim(-0.04, 1.04)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.text(0.5, -0.085, "Evidence Risk: Benign Noise  →  Adversarial Corruption", ha="center", fontsize=17, weight="bold", color=NAVY)
    ax.text(-0.095, 0.5, "Evaluation Target: Retrieval-Level  →  System-Action-Level", ha="center", va="center", rotation=90, fontsize=17, weight="bold", color=NAVY)

    ax.set_title("Evaluation Landscape for Robust RAG Benchmarks", fontsize=28, weight="bold", color=NAVY, pad=28)
    fig.text(0.5, 0.91, "Benchmarks differ by evidence risk and required system behavior.", ha="center", fontsize=15.5, color=GRAY)

    legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BLUE, markersize=12, label="Noise / retrieval"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=SAGE, markersize=12, label="Faithfulness / answerability"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BRICK, markersize=12, label="Attack / security"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PLUM, markersize=12, label="Calibration / control"),
    ]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=4, frameon=False, fontsize=13)

    note = "Open gap: few benchmarks jointly cover noise, conflict, poisoning, uncertainty, and action quality."
    fig.text(0.5, 0.035, note, ha="center", fontsize=14.5, color=BRICK, weight="semibold")

    plt.subplots_adjust(left=0.10, right=0.98, top=0.84, bottom=0.18)
    save(fig, "fig4_benchmark_landscape_py_4k")
    plt.close(fig)


def rounded_box(ax, xy, w, h, text, fc, ec, fontsize=12.5, weight="bold", color=NAVY):
    x, y = xy
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.035",
        linewidth=1.8,
        edgecolor=ec,
        facecolor=fc,
        zorder=2,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, weight=weight, color=color, zorder=3)
    return box


def diamond(ax, center, w, h, text, fc="#FFF8E8", ec=OCHRE):
    cx, cy = center
    pts = np.array([[cx, cy + h / 2], [cx + w / 2, cy], [cx, cy - h / 2], [cx - w / 2, cy]])
    patch = Polygon(pts, closed=True, facecolor=fc, edgecolor=ec, linewidth=1.9, zorder=2)
    ax.add_patch(patch)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=11.5, weight="bold", color=NAVY, zorder=3)
    return patch


def arrow(ax, start, end, color=GRAY, label=None, rad=0.0):
    arr = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=16,
        linewidth=1.8,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        zorder=1,
    )
    ax.add_patch(arr)
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx, my + 0.025, label, ha="center", va="center", fontsize=10.5, color=color, weight="bold")
    return arr


def draw_operational_decision_flow() -> None:
    """Decision-flow state machine, visually distinct from the taxonomy figure."""
    fig, ax = plt.subplots(figsize=(19.2, 8.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(
        0.5,
        0.965,
        "Robust RAG Decision Flow under Unreliable Evidence",
        ha="center",
        va="center",
        fontsize=25,
        weight="bold",
        color=NAVY,
    )
    ax.text(
        0.5,
        0.915,
        "Figure 2 maps the research landscape; this state machine shows how a deployed system chooses actions.",
        ha="center",
        va="center",
        fontsize=14.5,
        color=GRAY,
    )

    # Core pipeline boxes.
    rounded_box(ax, (0.035, 0.64), 0.15, 0.16, "User query\n+\nCorpus / KB", "#F4F8FF", BLUE, fontsize=12.5)
    rounded_box(ax, (0.235, 0.64), 0.17, 0.16, "Retrieve & assemble\ncandidate evidence", "#F4F8FF", BLUE, fontsize=12.5)
    rounded_box(
        ax,
        (0.455, 0.64),
        0.17,
        0.16,
        "Detect risk signals\nretrieval • provenance\nconflict • uncertainty",
        "#FFF8F2",
        BRICK,
        fontsize=11.5,
    )

    # Decision nodes.
    diamond(ax, (0.72, 0.72), 0.15, 0.14, "Risk\nhigh?")
    diamond(ax, (0.72, 0.48), 0.17, 0.15, "Diagnose\nfailure type")

    # Output / actions.
    rounded_box(ax, (0.835, 0.75), 0.13, 0.11, "Answer with\ncitations", "#EEF8F2", SAGE, fontsize=11.8)
    rounded_box(ax, (0.835, 0.56), 0.13, 0.11, "Repair evidence\nre-retrieve / filter", "#F5F0FF", PLUM, fontsize=11.5)
    rounded_box(ax, (0.835, 0.39), 0.13, 0.11, "Verify risk\ncompare / quarantine", "#F5F0FF", PLUM, fontsize=11.5)
    rounded_box(ax, (0.835, 0.22), 0.13, 0.11, "Abstain or\nclarify / escalate", "#FFF0EF", BRICK, fontsize=11.5)

    # Monitoring / feedback band.
    rounded_box(
        ax,
        (0.235, 0.075),
        0.55,
        0.105,
        "Monitor over time: traceback • audit logs • corpus updates • retriever drift detection",
        "#F7F7F7",
        "#B8C0CC",
        fontsize=11.8,
        color="#2E3A4A",
    )

    # Main flow.
    arrow(ax, (0.185, 0.72), (0.235, 0.72), BLUE)
    arrow(ax, (0.405, 0.72), (0.455, 0.72), BLUE)
    arrow(ax, (0.625, 0.72), (0.645, 0.72), BLUE)

    # Risk decisions.
    arrow(ax, (0.795, 0.735), (0.835, 0.805), SAGE, label="no", rad=0.05)
    arrow(ax, (0.72, 0.65), (0.72, 0.56), OCHRE, label="yes")

    # Diagnose branches.
    arrow(ax, (0.805, 0.515), (0.835, 0.61), PLUM, label="insufficient", rad=0.08)
    arrow(ax, (0.805, 0.48), (0.835, 0.445), PLUM, label="conflict / attack", rad=0.02)
    arrow(ax, (0.805, 0.445), (0.835, 0.275), BRICK, label="ambiguous / unsafe", rad=-0.10)

    # Feedback to monitor.
    arrow(ax, (0.90, 0.22), (0.785, 0.13), "#9CA3AF", rad=0.05)
    arrow(ax, (0.90, 0.39), (0.785, 0.13), "#9CA3AF", rad=0.12)
    arrow(ax, (0.90, 0.56), (0.785, 0.13), "#9CA3AF", rad=0.20)
    arrow(ax, (0.455, 0.64), (0.455, 0.18), "#9CA3AF", label="log evidence state")
    arrow(ax, (0.235, 0.13), (0.235, 0.64), "#9CA3AF", rad=-0.35)

    # Legend.
    legend_items = [(BLUE, "evidence flow"), (OCHRE, "decision"), (PLUM, "repair / verify"), (BRICK, "safe fallback"), ("#9CA3AF", "monitoring")]
    x0 = 0.04
    for i, (c, t) in enumerate(legend_items):
        ax.add_patch(Rectangle((x0 + i * 0.13, 0.025), 0.018, 0.018, facecolor=c, edgecolor="none"))
        ax.text(x0 + i * 0.13 + 0.024, 0.034, t, fontsize=10.8, va="center", color=GRAY)

    plt.subplots_adjust(left=0.02, right=0.99, top=0.98, bottom=0.04)
    save(fig, "fig3_operational_decision_flow_py_4k")
    plt.close(fig)


def main() -> None:
    draw_operational_decision_flow()
    draw_failure_intervention_matrix()
    draw_benchmark_landscape()


if __name__ == "__main__":
    main()
