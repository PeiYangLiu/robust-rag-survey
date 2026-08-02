"""Figure: the four failure surfaces and the five reporting coordinates.

Replaces the earlier raster infographic, which was generated from an image
model, was stale (it showed an "Evaluation Layer" among the top-level
surfaces, where the survey's four surfaces are evidence, model, adversary and
system control) and carried a legend that only named its own colours.

Drawn in the same idiom as the reference deck: thin navy frames, bold blue
panel titles, group labels interrupting the top border, pastel cells.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pptx.enum.text import PP_ALIGN  # noqa: E402

from pptx_kit import (  # noqa: E402
    BLUE, CREAM, Deck, GREEN, GREY, MUTED, NAVY, ORANGE, RED, TITLE, WARMGREY,
)

W, H = 13.2, 5.82

SURFACES = [
    ("Evidence", "what enters the context", BLUE, [
        ("Noisy retrieval", "irrelevant passages, hard\nnegatives, missing positives"),
        ("Distraction", "negative marginal utility;\nordering, long-context erosion"),
        ("Insufficiency & conflict", "unanswerable queries, stale\nsources, source disagreement"),
    ]),
    ("Model", "how the generator uses it", GREEN, [
        ("Context utilisation", "filtering, compression,\nreranking, note-taking"),
        ("Knowledge conflict", "parametric vs. retrieved,\nsource preference"),
        ("Faithful generation", "grounding, citation,\nclaim-level verification"),
    ]),
    ("Adversary", "an adaptive attacker", ORANGE, [
        ("Corpus poisoning", "PoisonedRAG, BadRAG,\nbackdoors, triggers"),
        ("Indirect prompt injection", "instructions, not evidence;\nmust clear retrieval first"),
        ("Defences", "certified aggregation,\nreranking, filters, traceback"),
    ]),
    ("System Control", "which action is taken", CREAM, [
        ("Adaptive retrieval", "when to retrieve, re-retrieve,\nstop, decompose"),
        ("Uncertainty & calibration", "confidence, selective\nprediction, conformal risk"),
        ("Abstention & interaction", "refuse, clarify, expose\nconflict, answer with caveats"),
    ]),
]

# Which coordinate each surface collapses into, as argued in the body.
COORDS = [
    ("C1", "Evidence state", "corpus snapshot,\nretriever, top-k", 0),
    ("C2", "Origin / capability", "access, persistence,\nbudget denominator", 2),
    ("C3", "Intervention", "which component\nchanges", 1),
    ("C4", "Outcome & unit", "cross-cutting: what is\nmeasured, over what", None),
    ("C5", "Policy / utility", "action set and\nits prices", 3),
]


def main() -> Path:
    out = Path(__file__).resolve().parents[2] / "figures" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    d = Deck(W, H, g=0.4773)

    pad, gap = 0.16, 0.16
    pw = (W - 2 * pad - 3 * gap) / 4
    py, ph = 0.14, 3.16
    centres = []

    for i, (title, sub, fill, items) in enumerate(SURFACES):
        x = pad + i * (pw + gap)
        d.box(x, py, pw, ph, fill=None, line=NAVY, line_w=1.1)
        d.text(x, py + 0.06, pw, 0.24, title, size=10.0, bold=True, color=TITLE)
        d.text(x, py + 0.30, pw, 0.18, sub, size=6.6, color=GREY)
        centres.append(x + pw / 2)

        iy = py + 0.54
        ih = (ph - 0.66) / 3
        for name, body in items:
            d.box(x + 0.11, iy, pw - 0.22, ih - 0.08, fill=fill, line=NAVY, line_w=0.75)
            d.text(x + 0.23, iy + 0.06, pw - 0.46, 0.17, name,
                   size=7.6, bold=True, align=PP_ALIGN.LEFT)
            d.text(x + 0.23, iy + 0.24, pw - 0.46, ih - 0.38, body,
                   size=6.6, color=NAVY, align=PP_ALIGN.LEFT, line_spacing=0.92)
            iy += ih

    # ---- the reduction ------------------------------------------------
    band_y = py + ph + 0.52
    d.box(pad, band_y, W - 2 * pad, 1.20, fill=None, line=NAVY, line_w=1.1)
    d.text(pad, band_y + 0.05, W - 2 * pad, 0.22,
           "Five reporting coordinates a comparison must fix",
           size=9.2, bold=True, color=TITLE)

    cw = (W - 2 * pad - 0.28 - 4 * 0.10) / 5

    # each surface reduces to one coordinate; route an elbow to it, staggered
    # in height so the four connectors never share a horizontal run
    targets = {src: pad + 0.14 + j * (cw + 0.10) + cw / 2
               for j, (_, _, _, src) in enumerate(COORDS) if src is not None}
    for i, cx in enumerate(centres):
        tx = targets[i]
        lane = py + ph + 0.10 + 0.095 * i
        pts = ([(cx, py + ph + 0.02), (cx, lane), (tx, lane), (tx, band_y - 0.02)]
               if abs(tx - cx) > 0.02 else [(cx, py + ph + 0.02), (tx, band_y - 0.02)])
        d.connector(pts, width=1.4, color=GREY)

    for j, (tag, name, body, src) in enumerate(COORDS):
        cx0 = pad + 0.14 + j * (cw + 0.10)
        fill = WARMGREY if src is None else SURFACES[src][2]
        d.box(cx0, band_y + 0.32, cw, 0.76, fill=fill, line=NAVY, line_w=0.75)
        d.text(cx0 + 0.11, band_y + 0.38, cw - 0.22, 0.16,
               [(tag + "  ", {"bold": True, "color": RED, "size": 7.6}),
                (name, {"bold": True, "size": 7.4})], align=PP_ALIGN.LEFT)
        d.text(cx0 + 0.11, band_y + 0.57, cw - 0.22, 0.46, body,
               size=6.6, color=NAVY, align=PP_ALIGN.LEFT, line_spacing=0.92)

    d.text(pad, H - 0.30, W - 2 * pad, 0.22,
           [("C3 is recorded but excluded from the decision rule: ",
             {"bold": True, "size": 6.8}),
            ("comparing two different systems means the intervention differs by "
             "construction, so it is the thing compared, not a condition on it.",
             {"size": 6.8, "color": NAVY})],
           align=PP_ALIGN.CENTER)

    p = out / "fig_taxonomy_map.pptx"
    d.save(p)
    print(p)
    return p


if __name__ == "__main__":
    main()
