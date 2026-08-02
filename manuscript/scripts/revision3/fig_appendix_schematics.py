"""Two schematic appendix figures, redrawn in the reference deck's idiom.

  fig_benchmark_landscape   where benchmarks sit on evidence risk x evaluation level
  fig_failure_matrix        literature family x intervention point

Both were previously matplotlib renders that baked a title and a subtitle into
the image, duplicating the caption, and carried legends in unreadably small
type.  Positions and shading are schematic in both, which the captions say.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402

from pptx_kit import (  # noqa: E402
    BLUE, CREAM, Deck, GREEN, GREY, NAVY, ORANGE, RED, TITLE, WARMGREY, WHITE,
)

OUT = Path(__file__).resolve().parents[2] / "figures" / "generated"


def _export(deck: Deck, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.pptx"
    deck.save(p)
    print(p)
    return p


# --------------------------------------------------------------------------
QUADRANTS = [
    ("Answerability & Calibration", GREEN, 0, 1,
     ["RAGTruth", "URAG", "MTRAG-UN", "CRUMQs", "RAG-QA Arena"]),
    ("End-to-End Robust Control", WARMGREY, 1, 1,
     ["SURE-RAG", "SafeRAG"]),
    ("Retrieval Noise", BLUE, 0, 0,
     ["RGB", "QueryRobust", "MagicMushroom", "LC-RAG"]),
    ("Attack / Defense", ORANGE, 1, 0,
     ["PoisonArena", "PoisonedRAG", "BadRAG"]),
]


def benchmark_landscape() -> Path:
    W, H = 10.4, 4.02
    d = Deck(W, H, g=0.6058)
    lx = 1.46
    pw, phh = (W - lx - 0.14) / 2, (H - 0.44 - 0.62) / 2

    for name, fill, cx, cy in [(q[0], q[1], q[2], q[3]) for q in QUADRANTS]:
        x = lx + cx * pw
        y = 0.44 + (1 - cy) * phh
        d.box(x, y, pw, phh, fill=fill, line=NAVY, line_w=0.8)
        d.text(x + 0.10, y + 0.07, pw - 0.20, 0.20, name, size=8.0, bold=True,
               color=NAVY, align=PP_ALIGN.LEFT)

    for name, fill, cx, cy, items in QUADRANTS:
        x = lx + cx * pw
        y = 0.44 + (1 - cy) * phh
        cols = 2 if len(items) > 3 else 1
        cwid = (pw - 0.30) / cols
        for k, it in enumerate(items):
            r, c = divmod(k, cols)
            d.box(x + 0.14 + c * cwid, y + 0.34 + r * 0.34, cwid - 0.10, 0.26,
                  fill=WHITE, line=NAVY, line_w=0.7,
                  shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.16)
            d.text(x + 0.14 + c * cwid, y + 0.34 + r * 0.34, cwid - 0.10, 0.26,
                   it, size=6.6, bold=True, color=NAVY)

    # axes: the two dimensions the quadrants are cut on
    d.box(lx, 0.44, 2 * pw, 2 * phh, fill=None, line=NAVY, line_w=1.3)
    d.text(0.04, 0.44, lx - 0.16, 2 * phh,
           "Evaluation target\n\u2191 system-action\n\u2193 retrieval",
           size=7.4, bold=True, color=TITLE, align=PP_ALIGN.RIGHT, line_spacing=1.05)
    d.text(lx, H - 0.54, 2 * pw, 0.22,
           "Evidence risk:   benign noise  \u2192  adversarial corruption",
           size=7.4, bold=True, color=TITLE)
    d.text(lx, H - 0.28, 2 * pw, 0.20,
           "Open gap: few benchmarks jointly cover noise, conflict, poisoning, "
           "uncertainty and action quality.",
           size=6.4, bold=True, color=RED)
    return _export(d, "fig_benchmark_landscape")


# --------------------------------------------------------------------------
FAILURES = ["Noisy\nretrieval", "Distraction", "Knowledge\nconflict",
            "Adversarial\ncorruption", "OOD /\nuncertainty",
            "Calibration /\nabstention"]
ROWS = [
    ("Corpus / KB", ["chunking\nprovenance", "", "freshness\nsources",
                     "PoisonedRAG\nBadRAG", "", ""]),
    ("Retriever", ["RAAT\nUDCG", "LC-RAG", "SourcePref", "ProGRank\nRobustRAG",
                   "retrieval\nconfidence", "NAACL-Cal"]),
    ("Context assembly", ["FILCO\nRECOMP", "CUB\nFirstDrop", "FaithfulRAG\nAstuteRAG",
                          "TrustRAG\nSeCon-RAG", "SuffCtx", "SURE-RAG"]),
    ("Generator", ["CoN", "context\nutilization", "CoRect\nParamMute",
                   "Phantom\nAIP", "FaithUQ", "CalibRAG"]),
    ("System control", ["re-query", "filter / ask", "SABER\nAstuteRAG",
                        "traceback\nquarantine", "Self-RAG\nCRAG", "abstain\nclarify"]),
    ("Evaluation", ["RGB\nMagicMushroom", "CUB\nUDCG", "MAGIC\nWikiContradict",
                    "SafeRAG\nPoisonArena", "URAG\nMTRAG-UN", "ECE\nselective risk"]),
]
DENSITY = {2: ORANGE, 1: CREAM, 0: WHITE}


def failure_matrix() -> Path:
    W, H = 11.6, 4.30
    d = Deck(W, H, g=0.5431)
    lx, ty = 1.72, 0.78
    cw = (W - lx - 0.14) / len(FAILURES)
    rh = (H - ty - 0.42) / len(ROWS)

    d.text(lx, 0.10, W - lx - 0.14, 0.22, "Failure modes", size=8.4, bold=True,
           color=TITLE)
    for j, f in enumerate(FAILURES):
        d.text(lx + j * cw, ty - 0.34, cw, 0.32, f, size=6.8, bold=True, color=NAVY,
               line_spacing=0.92)
    d.text(0.02, ty, 0.34, len(ROWS) * rh, "", size=8)
    d.text(0.06, ty - 0.44, lx - 0.20, 0.42, "Intervention\npoints", size=7.6,
           bold=True, color=TITLE, align=PP_ALIGN.RIGHT, line_spacing=0.95)

    for i, (row, cells) in enumerate(ROWS):
        y = ty + i * rh
        d.text(0.06, y, lx - 0.20, rh, row, size=7.0, bold=True, color=NAVY,
               align=PP_ALIGN.RIGHT)
        for j, c in enumerate(cells):
            dens = 0 if not c else (2 if "\n" in c else 1)
            d.box(lx + j * cw, y, cw - 0.04, rh - 0.04, fill=DENSITY[dens],
                  line=NAVY, line_w=0.7)
            if c:
                d.text(lx + j * cw, y, cw - 0.04, rh - 0.04, c, size=6.0,
                       bold=dens == 2, color=NAVY, line_spacing=0.92)

    ly = H - 0.30
    for k, (lab, fill) in enumerate([("sparse", WHITE), ("moderate", CREAM),
                                     ("dense", ORANGE)]):
        x = W / 2 - 1.75 + k * 1.20
        d.box(x, ly + 0.03, 0.26, 0.15, fill=fill, line=NAVY, line_w=0.7)
        d.text(x + 0.33, ly, 0.85, 0.20, lab, size=6.6, color=NAVY,
               align=PP_ALIGN.LEFT)
    return _export(d, "fig_failure_matrix")


if __name__ == "__main__":
    benchmark_landscape()
    failure_matrix()
