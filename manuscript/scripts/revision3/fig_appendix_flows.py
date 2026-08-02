"""Appendix flow figures, drawn in the reference deck's idiom.

Three diagrams that previously overlapped their own labels in TikZ, or carried
a title and legend baked into a raster image:

  fig_screening_flow   the sampling frame for the census (single column)
  fig_corpus_lineage   how the evidence maps were built (full width)
  fig_decision_flow    the operational state machine a deployed system runs
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402

from pptx_kit import (  # noqa: E402
    BLUE, CREAM, Deck, GREEN, GREY, MUTED, NAVY, ORANGE, RED, TITLE, WARMGREY, WHITE,
)

OUT = Path(__file__).resolve().parents[2] / "figures" / "generated"
PINK = RGBColor(0xFD, 0xE9, 0xE9)


def _export(deck: Deck, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.pptx"
    deck.save(p)
    print(p)
    return p


# --------------------------------------------------------------------------
# 1. sampling frame -- the stages, the losses, and where re-execution stops
# --------------------------------------------------------------------------
STAGES = [
    ("1,904 records retrieved", "55 arXiv queries + 5 venues", PINK, True),
    ("1,445 with an open PDF", None, BLUE, False),
    ("1,399 after de-duplication", None, BLUE, False),
    ("536 retained by the screen", None, BLUE, False),
    ("259 extracted full texts", "the census frame", BLUE, False),
    ("1,703 candidate windows", "in 171 papers", ORANGE, False),
]
LOSSES = [
    "\u2212459 no open PDF",
    "\u221246 duplicate title / ID",
    "\u2212863 off-topic",
    "\u2212277 not extractable",
    "deterministic screen",
]


def screening_flow() -> Path:
    W = 5.55
    H = 0.10 + sum(0.52 if st[1] else 0.32 for st in STAGES) \
        + 0.28 * len(LOSSES) + 0.44
    d = Deck(W, H, g=3.03 / W)
    bx, bw = 0.10, 3.24
    y = 0.10
    for i, (head, sub, fill, dashed) in enumerate(STAGES):
        h = 0.52 if sub else 0.32
        d.box(bx, y, bw, h, fill=fill, line=NAVY,
              line_w=1.5 if fill is ORANGE else 0.9,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.10,
              dash=6 if dashed else None)
        d.text(bx, y + (0.04 if sub else 0.0), bw, 0.26 if sub else h, head,
               size=7.2, bold=True)
        if sub:
            d.text(bx, y + 0.29, bw, 0.19, sub, size=6.2, color=GREY)
        y += h
        if i < len(LOSSES):
            d.connector([(bx + bw / 2, y), (bx + bw / 2, y + 0.28)], width=1.4,
                        color=GREY)
            d.text(bx + bw + 0.12, y, W - bx - bw - 0.20, 0.28, LOSSES[i],
                   size=6.2, color=NAVY, align=PP_ALIGN.LEFT, line_spacing=0.92)
            y += 0.28

    d.text(bx, y + 0.12, bw, 0.20, "dashed = not re-executable",
           size=6.2, bold=True, color=NAVY)
    return _export(d, "fig_screening_flow")


# --------------------------------------------------------------------------
# 2. corpus lineage -- three tracks, with every delta on its own connector
# --------------------------------------------------------------------------
def corpus_lineage() -> Path:
    W, H = 12.0, 3.98
    d = Deck(W, H, g=6.30 / 12.0)

    # top track: retrieval to inclusion
    top = [("1,904", "retrieved records"), ("1,445", "open PDFs"),
           ("1,399", "deduplicated"), ("536", "included")]
    bw, bh, gap = 1.74, 0.56, 0.62
    x0, ty = 0.55, 0.14
    for i, (n, lab) in enumerate(top):
        x = x0 + i * (bw + gap)
        d.box(x, ty, bw, bh, fill=BLUE, line=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
              radius=0.10)
        d.text(x, ty + 0.05, bw, 0.22, n, size=7.8, bold=True)
        d.text(x + 0.05, ty + 0.27, bw - 0.10, 0.22, lab, size=6.4, color=NAVY)
        if i:
            d.connector([(x - gap, ty + bh / 2), (x, ty + bh / 2)], width=1.4, color=GREY)
    inc_cx = x0 + 3 * (bw + gap) + bw / 2

    # three lanes, each on its own baseline so the geometry stays declarative
    lw, lh, lgap = 1.92, 0.72, 1.10
    lane_y = [1.00, 1.94, 2.88]
    lanes = [
        (GREEN, [("Base scoping\nset", None),
                 ("Venue-augmented\nscoping set", "+26 venue")]),
        (WARMGREY, [("250\nbase evidence records", None),
                    ("274\ndouble-coded records", "+24 venue"),
                    ("Map A: 268\nadjudicated seed", "\u22126 excl.")]),
        (CREAM, [("Venue + extension\nPDF collections", None),
                 ("Source-blind\ncitation audit", None),
                 ("416\ncandidate expansion", "+148 / +20"),
                 ("Map B: 342\nadjudicated synthesis map", "\u221274 bdry")]),
    ]

    for (fill, items), ly in zip(lanes, lane_y):
        for j, (txt, delta) in enumerate(items):
            x = 0.55 + j * (lw + lgap)
            final = txt.startswith("Map B")
            d.box(x, ly, lw, lh, fill=ORANGE if final else fill, line=NAVY,
                  line_w=1.5 if final else 0.9,
                  shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.10)
            d.text(x + 0.09, ly + 0.06, lw - 0.18, lh - 0.12, txt,
                   size=6.4, bold=True, line_spacing=0.95)
            if j:
                # the delta rides above its own connector, never over a box
                d.connector([(x - lgap, ly + lh / 2), (x, ly + lh / 2)],
                            width=1.4, color=GREY)
                if delta:
                    d.text(x - lgap, ly + lh / 2 - 0.26, lgap, 0.20, delta,
                           size=6.0, color=RED, bold=True)

    mid = 0.55 + lw / 2
    join = (ty + bh + lane_y[0]) / 2
    d.connector([(inc_cx, ty + bh), (inc_cx, join), (mid, join), (mid, lane_y[0])],
                width=1.4, color=GREY)
    d.connector([(mid, lane_y[0] + lh), (mid, lane_y[1])], width=1.4, color=GREY)
    seed_x = 0.55 + 2 * (lw + lgap) + lw / 2
    d.connector([(seed_x, lane_y[1] + lh), (seed_x, lane_y[2])], width=1.4, color=GREY)

    d.text(0.06, H - 0.26, W - 0.12, 0.20,
           [("Map B is the canonical synthesis map.", {"bold": True, "size": 6.6})],
           align=PP_ALIGN.CENTER)
    return _export(d, "fig_corpus_lineage")


# --------------------------------------------------------------------------
# 3. operational decision flow
# --------------------------------------------------------------------------
def decision_flow() -> Path:
    W, H = 12.0, 3.30
    d = Deck(W, H, g=0.5250)
    pad = 0.14

    ix, iw = pad, 3.30
    d.box(ix, 0.10, iw, 2.62, fill=None, line=NAVY, line_w=1.1)
    d.text(ix, 0.16, iw, 0.24, "Assemble", size=9.0, bold=True, color=TITLE)
    steps = [("User query + corpus / KB", BLUE),
             ("Retrieve & assemble\ncandidate evidence", BLUE),
             ("Detect risk signals\nretrieval \u00b7 provenance\nconflict \u00b7 uncertainty",
              ORANGE)]
    sy = 0.50
    for k, (t, fill) in enumerate(steps):
        h = 0.22 + 0.16 * t.count("\n") + 0.12
        d.box(ix + 0.16, sy, iw - 0.32, h, fill=fill, line=NAVY,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.10)
        d.text(ix + 0.20, sy + 0.02, iw - 0.40, h - 0.04, t, size=7.0, bold=True,
               line_spacing=0.94)
        sy += h
        if k < len(steps) - 1:
            d.chevron_down(ix + iw / 2, sy + 0.05)
            sy += 0.28

    gx, gw = ix + iw + 0.34, 2.42
    d.box(gx, 0.10, gw, 2.62, fill=None, line=NAVY, line_w=1.1)
    d.text(gx, 0.16, gw, 0.24, "Gate", size=9.0, bold=True, color=TITLE)
    for label, gy in (("Risk high?", 0.62), ("Diagnose\nfailure type", 1.62)):
        d.box(gx + 0.30, gy, gw - 0.60, 0.60, fill=CREAM, line=NAVY,
              shape=MSO_SHAPE.DIAMOND)
        d.text(gx + 0.30, gy + 0.06, gw - 0.60, 0.48, label, size=6.8, bold=True,
               line_spacing=0.94)
    d.connector([(gx + gw / 2, 1.22), (gx + gw / 2, 1.62)], width=1.4, color=GREY)
    d.text(gx + gw / 2 + 0.04, 1.26, 0.50, 0.16, "yes", size=6.2, bold=True,
           color=RED, align=PP_ALIGN.LEFT)
    d.connector([(ix + iw + 0.02, 1.30), (gx + 0.28, 1.30)], width=1.4, color=GREY)

    corr = 0.86
    ax, aw = gx + gw + corr, W - (gx + gw + corr) - pad
    d.box(ax, 0.10, aw, 2.62, fill=None, line=NAVY, line_w=1.1)
    d.text(ax, 0.16, aw, 0.24, "Act", size=9.0, bold=True, color=TITLE)
    actions = [("Answer with citations", GREEN, "risk low", 0.50),
               ("Repair evidence \u00b7 re-retrieve / filter", BLUE, "insufficient", 1.06),
               ("Verify risk \u00b7 compare / quarantine", MUTED, "conflict / attack", 1.62),
               ("Abstain \u00b7 clarify / escalate", PINK, "ambiguous / unsafe", 2.18)]
    for n, (t, fill, edge, ay) in enumerate(actions):
        h = 0.48
        d.box(ax + 0.16, ay, aw - 0.32, h, fill=fill, line=NAVY,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.10)
        # the branch condition rides inside its own box, so no label can ever
        # land on another branch's connector
        d.text(ax + 0.22, ay + 0.04, aw - 0.44, 0.15, edge, size=6.0, bold=True,
               color=RED, align=PP_ALIGN.LEFT)
        d.text(ax + 0.22, ay + 0.19, aw - 0.44, 0.25, t, size=7.2, bold=True,
               align=PP_ALIGN.LEFT)
        src_y = 0.92 if n == 0 else 1.92
        lane = gx + gw + 0.14 + 0.17 * n
        d.connector([(gx + gw - 0.28, src_y), (lane, src_y),
                     (lane, ay + h / 2), (ax + 0.14, ay + h / 2)],
                    width=1.3, color=GREY)

    my = 2.84
    d.box(pad, my, W - 2 * pad, 0.32, fill=WARMGREY, line=NAVY, line_w=0.9,
          shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.10)
    d.text(pad, my, W - 2 * pad, 0.32,
           [("Monitor over time:  ", {"bold": True, "size": 6.8}),
            ("traceback \u00b7 audit logs \u00b7 corpus updates \u00b7 retriever drift detection",
             {"size": 6.8, "color": NAVY})])
    return _export(d, "fig_decision_flow")




# --------------------------------------------------------------------------
# 4. the two layers a claim-review study confuses
# --------------------------------------------------------------------------
def two_layer() -> Path:
    W, H = 5.40, 3.24
    d = Deck(W, H, g=0.5611)
    pad = 0.10
    layers = [
        ("Substantive layer", "Cross-paper claim:", "\u201cA is more robust than B.\u201d",
         BLUE, 0.10,
         [("C1", "evidence state"), ("C2", "capability"), ("C3", "intervention"),
          ("C4", "outcome unit"), ("C5", "action set and loss")]),
        ("Measurement layer", "Claim-review study:", "\u201cprompt D improves review.\u201d",
         GREEN, 1.86,
         [("M1", "item"), ("M2", "reviewer"), ("M3", "assignment"),
          ("M4", "reference"), ("M5", "downstream loss")]),
    ]
    for title, kind, claim, fill, ly, cells in layers:
        d.box(pad, ly, W - 2 * pad, 1.08, fill=None, line=NAVY, line_w=1.0)
        d.label_on_border(pad + 0.12, ly, title, size=7.0, color=TITLE)
        d.box(pad + 0.14, ly + 0.16, W - 2 * pad - 0.28, 0.30, fill=fill, line=NAVY,
              line_w=0.8, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.10)
        d.text(pad + 0.14, ly + 0.16, W - 2 * pad - 0.28, 0.30,
               [(kind + "  ", {"bold": True, "size": 7.0}),
                (claim, {"size": 7.0, "color": NAVY})])
        cw = (W - 2 * pad - 0.28 - 4 * 0.06) / 5
        for j, (tag, name) in enumerate(cells):
            cx = pad + 0.14 + j * (cw + 0.06)
            d.box(cx, ly + 0.54, cw, 0.42, fill=None, line=NAVY, line_w=0.7)
            d.text(cx + 0.03, ly + 0.56, cw - 0.06, 0.15, tag, size=6.6, bold=True,
                   color=RED)
            d.text(cx + 0.03, ly + 0.70, cw - 0.06, 0.24, name, size=5.9, color=NAVY,
                   line_spacing=0.92)

    d.connector([(W / 2, 1.20), (W / 2, 1.84)], width=1.6, color=GREY)
    d.text(pad, 1.30, W / 2 - pad - 0.10, 0.42,
           "4 of 8 stated comparisons\nare undefined",
           size=6.0, color=NAVY, align=PP_ALIGN.RIGHT, line_spacing=0.94)
    d.text(W / 2 + 0.10, 1.30, W / 2 - pad - 0.10, 0.42,
           "an unmatched coordinate\nmakes the claim unanswerable",
           size=6.0, color=NAVY, align=PP_ALIGN.LEFT, line_spacing=0.94)

    d.text(pad, H - 0.20, W - 2 * pad, 0.18,
           "Passing one layer cannot repair failure in the other.",
           size=6.6, bold=True, color=NAVY)
    return _export(d, "fig_two_layer")


if __name__ == "__main__":
    screening_flow()
    corpus_lineage()
    decision_flow()
    two_layer()
