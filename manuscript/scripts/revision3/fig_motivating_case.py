#!/usr/bin/env python3
"""Figure 1: the motivating case, drawn as PowerPoint shapes.

The introduction currently spends about a page establishing that PoisonedRAG's
0.01 for corpus poisoning and corpus poisoning's own 84.2% are both correct and
still cannot be compared.  That argument is spatial -- two numbers, two counted
events, one shared corpus and retriever -- so it reads better as a figure than
as prose, and moving it into one frees the text it replaces.

Every number and every quoted string here is the one the released verifier
re-opens at its cited line range; nothing is drawn that the manuscript does not
also state.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pptx_kit import (  # noqa: E402
    BLACK, BLUE, Deck, GREEN, GREY, MUTED, NAVY, ORANGE, RED, TITLE,
    WARMGREY, WHITE,
)
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN  # noqa: E402
from pptx.util import Pt  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "figures" / "generated"


def build() -> Path:
    H = 3.98
    d = Deck(13.4, H, g=0.4701)
    # every stacked group must clear the white cover its own border label
    # paints above its top edge, or it is drawn over whatever sits above
    GAP = max(d.label_clearance(), 0.22)
    PH = H - 0.20

    # ================================================== panel 1: the table
    px, py, pw, ph = d.panel(0.10, 0.10, 4.10, PH, "What the Table Shows")

    rh = 0.225
    gh = 5 * rh + 0.33
    gx, gy, gw, _ = d.group(px, py, pw, gh, "PoisonedRAG, Table 4 (NQ)", fill=WHITE)
    rows = [
        ("PoisonedRAG (Black-Box)", "0.97", BLUE, True),
        ("Prompt Injection Attack", "0.62", WHITE, False),
        ("Disinformation Attack", "0.69", WHITE, False),
        ("Naive Attack", "0.03", WHITE, False),
        ("Corpus Poisoning Attack", "0.01", ORANGE, True),
    ]
    for i, (name, val, fill, bold) in enumerate(rows):
        yy = gy + 0.05 + i * rh
        d.box(gx + 0.04, yy, gw - 1.00, rh - 0.04, fill=fill, line=MUTED, line_w=0.6)
        d.text(gx + 0.12, yy, gw - 1.16, rh - 0.04, name, size=6.0,
               bold=bold, align=PP_ALIGN.LEFT, color=BLACK)
        d.box(gx + gw - 0.94, yy, 0.60, rh - 0.04, fill=fill, line=MUTED, line_w=0.6)
        d.text(gx + gw - 0.94, yy, 0.60, rh - 0.04, val, size=6.0, bold=bold,
               color=RED if bold and val == "0.01" else BLACK)

    cur = py + gh
    d.chevron_down(px + pw / 2, cur + 0.06)
    cur += 0.30 + GAP

    gx, gy, gw, gh = d.group(px, cur, pw, 0.66,
                             "The sentence a reader forms", fill=WHITE)
    d.text(gx, gy - 0.02, gw, gh,
           [("\u201cCorpus poisoning does not work.\u201d", {"size": 8.1, "bold": True})],
           color=BLACK)
    cur += 0.66 + 0.16

    d.text(px, cur, pw, 0.40,
           [("Both numbers are correct. Neither supports that sentence.",
             {"size": 6.4, "bold": True, "color": NAVY})])

    # ============================================ panel 2: what is counted
    px, py, pw, ph = d.panel(4.42, 0.10, 4.52, PH, "What Each Number Counts")

    gx, gy, gw, gh = d.group(px, py, pw, 0.58, "Shared by both", fill=WHITE)
    d.text(gx, gy - 0.03, gw, gh,
           [("Natural Questions corpus \u2022 pre-trained Contriever retriever",
             {"size": 6.3, "bold": True})])
    cur = py + 0.58 + GAP

    colw = (pw - 0.20) / 2
    lx, rx = px, px + colw + 0.20
    col_h = 1.66

    for x, label, fill, lines in (
        (lx, "PoisonedRAG: 0.01", BLUE, [
            ("counts", "a target question answered with the attacker's answer"),
            ("over", "5 retrieved texts"),
            ("unit", "fraction of targets"),
        ]),
        (rx, "Corpus Poisoning: 84.2%", ORANGE, [
            ("counts", "an adversarial passage entering the retrieved set"),
            ("over", "top-20 retrieved"),
            ("unit", "percentage of queries"),
        ]),
    ):
        cx, cy, cw, ch = d.group(x, cur, colw, col_h, label, fill=fill)
        yy = cy + 0.08
        for tag, body in lines:
            nlines = 1 + (len(tag) + 2 + len(body)) // 22
            h = 0.15 * nlines + 0.08
            d.text(cx + 0.05, yy, cw - 0.10, h,
                   [(tag + "  ", {"bold": True, "color": NAVY, "size": 5.8}),
                    (body, {"size": 5.8})],
                   align=PP_ALIGN.LEFT, line_spacing=0.92, anchor=MSO_ANCHOR.TOP)
            yy += h

    cur += col_h + GAP
    d.box(px, cur, pw, 0.62, fill=WHITE, line=RED, line_w=1.0)
    d.text(px + 0.06, cur, pw - 0.12, 0.62,
           [("Corpus poisoning never chooses an answer, so it cannot score on an "
             "answer-manipulation metric.", {"size": 6.3, "bold": True, "color": RED})])

    # ============================================== panel 3: what survives
    px, py, pw, ph = d.panel(9.16, 0.10, 4.14, PH, "What the Audit Returns")

    coords = [
        ("C1", "evidence state", "match", WHITE),
        ("C2", "origin / capability", "match", WHITE),
        ("C4", "outcome / unit", "mismatch", ORANGE),
        ("C5", "policy / utility", "match", WHITE),
    ]
    crh = 0.225
    gh = len(coords) * crh + 0.33
    gx, gy, gw, _ = d.group(px, py, pw, gh, "Coordinates, both sides", fill=WHITE)
    for i, (tag, name, state, fill) in enumerate(coords):
        yy = gy + 0.04 + i * crh
        d.box(gx, yy, 0.34, crh - 0.04, fill=fill, line=MUTED, line_w=0.5)
        d.text(gx, yy, 0.34, crh - 0.04, tag, size=5.8, bold=True)
        d.text(gx + 0.42, yy, 1.70, crh - 0.04, name, size=5.8, align=PP_ALIGN.LEFT)
        d.box(gx + gw - 0.80, yy, 0.78, crh - 0.04, fill=fill,
              line=MUTED if state == "mismatch" else None, line_w=0.5)
        d.text(gx + gw - 0.80, yy, 0.78, crh - 0.04, state, size=5.6,
               bold=state == "mismatch",
               color=RED if state == "mismatch" else GREY)

    cur = py + gh
    d.chevron_down(px + pw / 2, cur + 0.04)
    cur += 0.22 + 0.18

    gx, gy, gw, gh = d.group(px, cur, pw, 0.74, "Verdict", fill=WHITE)
    d.text(gx, gy - 0.04, gw, gh,
           [("undefined", {"size": 8.6, "bold": True, "color": RED}),
            ("\nno operating point makes 1% and 84.2%\nanswer one question",
             {"size": 6.0, "bold": False, "color": BLACK})])
    cur += 0.74 + 0.18

    gx, gy, gw, gh = d.group(px, cur, pw, 0.70, "What may be reported", fill=WHITE)
    d.text(gx + 0.04, gy - 0.02, gw - 0.08, gh,
           [("These two attacks cannot be ranked by these two numbers, and "
             "the benchmarked paper said so.",
             {"size": 6.0, "align": PP_ALIGN.LEFT})], align=PP_ALIGN.LEFT)

    # cross-panel flow
    d.connector([(4.20, 1.50), (4.42, 1.50)])
    d.connector([(8.94, 1.50), (9.16, 1.50)])

    OUT.mkdir(parents=True, exist_ok=True)
    return d.save(OUT / "fig_motivating_case.pptx")


if __name__ == "__main__":
    print(build())
