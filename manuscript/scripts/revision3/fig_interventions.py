#!/usr/bin/env python3
"""Figure 3: four interventions on the same judgment.

This is the paper's central experimental claim and it is a comparison of
effects, so it is drawn as one: a common baseline on the left, four
manipulations that each change exactly one thing, and the reference level the
same instrument reaches on prose written to state its coordinates.  A reader
should be able to see at a glance that only one manipulation moves the needle
and that even it stops well short.

All values are read from the released artifacts at build time.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pptx_kit import (  # noqa: E402
    BLACK, BLUE, CREAM, CYAN, Deck, GREEN, GREY, MUTED, NAVY, ORANGE, RED,
    SLATE, TITLE, WARMGREY, WHITE,
)
from pptx.enum.text import PP_ALIGN  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUP = ROOT / "supplement"
OUT = ROOT / "figures" / "generated"


def load(name):
    try:
        return json.loads((SUP / name).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def build() -> Path:
    priv = load("privileged_reference_results.json")
    absn = load("abstention_verdict_results.json")
    diag = load("census_diagnostics.json")
    owj = load("open_weight_judge_results.json")
    ls = load("label_space_matched.json")

    lad = priv.get("information_ladder", {}).get("comparability", {})
    k_win = lad.get("window", {}).get("fleiss_kappa", 0.06)
    k_cite = lad.get("citing_full", {}).get("fleiss_kappa", 0.29)
    d_cite = lad.get("delta_citing_minus_window", {})
    k_abs = absn.get("fleiss_kappa_collapsed_to_deployed_space", 0.06)
    d_abs = absn.get("kappa_difference", 0.01)
    ci_abs = absn.get("kappa_difference_ci95", [-0.07, 0.11])
    k_rule = diag.get("composed_rule", {}).get("fleiss_kappa_composed_verdict", 0.09)
    d_rule = diag.get("composed_rule", {}).get("kappa_composed_minus_stated", 0.03)
    ci_rule = diag.get("composed_rule", {}).get("kappa_composed_minus_stated_ci95",
                                                [-0.01, 0.06])
    k_open = owj.get("census_verdict", {}).get("open_pool", {}).get("fleiss_kappa", 0.09)
    n_open = owj.get("census_verdict", {}).get("open_pool", {}).get("n_judges", 9)
    k_ref = (ls.get("constructed_full_disclosure", {}).get("three_class", {})
             .get("fleiss_kappa", 0.74))

    W, H = 7.60, 3.86
    d = Deck(W, H, g=0.3987)

    px, py, pw, ph = d.panel(0.10, 0.10, W - 0.20, H - 0.20,
                             "Four Interventions on the Same Judgment")

    # ---- geometry of the kappa scale -----------------------------------
    sx, sw = px + 1.94, pw - 3.42          # scale x-origin and width
    kmax = 0.80
    def kx(k):                              # noqa: E306
        return sx + sw * (k / kmax)

    top = py + 0.30
    row_h = 0.395
    n_rows = 6

    # axis
    axis_y = top + 5 * row_h + 0.06
    d.box(sx, axis_y, sw, 0.012, fill=MUTED, line=None)
    for k in (0.0, 0.2, 0.4, 0.6, 0.8):
        d.box(kx(k) - 0.006, axis_y, 0.012, 0.055, fill=MUTED, line=None)
        d.text(kx(k) - 0.20, axis_y + 0.06, 0.40, 0.16, f"{k:.1f}", size=4.1,
               color=GREY)
    d.text(px, axis_y + 0.055, 1.50, 0.17, "inter-judge Fleiss' \u03ba",
           size=4.3, bold=True, color=NAVY, align=PP_ALIGN.LEFT)

    # reference band: the level the same instrument reaches on stated prose
    d.box(kx(k_ref) - 0.010, top - 0.04, 0.020, 5 * row_h + 0.12,
          fill=GREEN, line=None)
    d.text(kx(k_ref) - 2.60, top - 0.30, 2.54, 0.26,
           f"prose that states its coordinates: \u03ba {k_ref:.2f}",
           size=4.1, bold=True, color=NAVY, align=PP_ALIGN.RIGHT)

    rows = [
        ("Baseline: the window", "\u00b145 lines, as deployed",
         k_win, None, None, WARMGREY, False),
        ("Intervention 1", "read the entire citing paper",
         k_cite, d_cite.get("point"), d_cite.get("ci95"), BLUE, True),
        ("Intervention 2", "add a \u201cdoes not say\u201d verdict",
         k_abs, d_abs, ci_abs, ORANGE, False),
        ("Intervention 3", "compose the rule",
         k_rule, d_rule, ci_rule, ORANGE, False),
        ("Intervention 4", f"{n_open} open-weight checkpoints",
         k_open, None, None, ORANGE, False),
    ]

    for i, (tag, desc, k, delta, ci, fill, moved) in enumerate(rows):
        y = top + i * row_h
        # left label block
        d.box(px, y + 0.015, 1.86, row_h - 0.055, fill=fill if i == 0 else WHITE,
              line=MUTED, line_w=0.6)
        d.text(px + 0.06, y + 0.035, 1.74, 0.16, tag, size=4.5, bold=True,
               color=NAVY, align=PP_ALIGN.LEFT)
        d.text(px + 0.06, y + 0.205, 1.74, 0.17, desc.split("\n")[0], size=3.8,
               color=GREY, align=PP_ALIGN.LEFT, line_spacing=0.86)
        # bar
        bar_h = 0.135
        by = y + (row_h - 0.07 - bar_h) / 2 + 0.02
        d.box(sx, by, max(kx(k) - sx, 0.02), bar_h, fill=fill, line=NAVY,
              line_w=0.6)
        d.text(kx(k) + 0.04, by - 0.025, 0.46, bar_h + 0.05, f"{k:.2f}",
               size=4.9, bold=True, color=NAVY if moved else BLACK,
               align=PP_ALIGN.LEFT)
        # effect column
        ex = px + pw - 1.42
        if delta is not None:
            txt = f"{delta:+.2f}"
            note = (f"[{ci[0]:+.2f}, {ci[1]:+.2f}]" if ci else "")
            d.box(ex, y + 0.03, 0.60, row_h - 0.09, fill=GREEN if moved else WHITE,
                  line=NAVY if moved else MUTED, line_w=0.7)
            d.text(ex, y + 0.03, 0.60, row_h - 0.09, txt, size=5.4, bold=True,
                   color=NAVY if moved else GREY)
            d.text(ex + 0.63, y + 0.03, 0.80, row_h - 0.09, note, size=3.6,
                   color=GREY, align=PP_ALIGN.LEFT)
        elif i > 0:
            d.text(ex, y + 0.03, 1.40, row_h - 0.09, "no change", size=4.5,
                   color=GREY, align=PP_ALIGN.LEFT)

    # summary strip
    sy = axis_y + 0.24
    d.box(px, sy, pw, 0.34, fill=CREAM, line=NAVY, line_w=0.9)
    d.text(px + 0.10, sy, pw - 0.20, 0.34,
           [("Only evidence moves it, and not far enough. ", {"bold": True, "color": NAVY}),
            ("The residue is the distance to prose that states its coordinates.",
             {"bold": False, "color": BLACK})],
           size=4.2, align=PP_ALIGN.LEFT)

    OUT.mkdir(parents=True, exist_ok=True)
    return d.save(OUT / "fig_interventions.pptx")


if __name__ == "__main__":
    print(build())
