#!/usr/bin/env python3
"""Figure 2: the instrument and what it recovers.

Three panels that answer, left to right, the three questions a reader has about
the audit: where the corpus came from, what the instrument asks, and which of
its two judgments survives contact with published text.  Numbers are read from
the released artifacts at build time so the figure cannot drift from the tables.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pptx_kit import (  # noqa: E402
    BLACK, BLUE, Deck, GREEN, GREY, MUTED, NAVY, ORANGE, RED, TITLE,
    WARMGREY, WHITE,
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
    flow = load("screening_frame_flow.json")
    census = load("cross_paper_census.json")
    prev = load("coordinate_prevalence.json")
    priv = load("privileged_reference_results.json")

    stages = {s["stage"]: s for s in flow.get("stages", [])}
    n_ret = stages.get("Initial retrieval", {}).get("output_n", 1904)
    n_pdf = stages.get("Open-PDF filtering", {}).get("output_n", 1445)
    n_scr = stages.get("Broad relevance screening", {}).get("output_n", 536)
    n_txt = flow.get("screened_corpus", {}).get("n_full_texts", 259)
    n_cand = stages.get("Deterministic screen over extracted texts", {}).get("output_n", 1703)
    n_elig = census.get("frame", {}).get("n_eligible_majority", 704)

    kprov = census.get("provenance", {}).get("agreement", {}).get("fleiss_kappa", 0.55)
    kverd = prev.get("fields", {}).get("verdict", {}).get("fleiss_kappa", 0.06)
    kmaxv = prev.get("fields", {}).get("verdict", {}).get("max_attainable_kappa", 0.46)
    dep = priv.get("deployed_vs_reference", {})
    pv = dep.get("provenance__all", {})
    vd = dep.get("comparability__all", {})

    H = 4.34
    d = Deck(13.4, H, g=0.4701)
    GAP = max(d.label_clearance(), 0.22)
    PH = H - 0.20

    # ================================================= panel 1: the frame
    px, py, pw, ph = d.panel(0.10, 0.10, 3.62, PH, "Where the Frame Comes From")
    steps = [
        (f"{n_ret:,}", "records retrieved", WHITE, "55 queries, 5 venue sources"),
        (f"{n_pdf:,}", "with an open PDF", WHITE, None),
        (f"{n_scr:,}", "retained by screen", WHITE, None),
        (f"{n_txt}", "extracted full texts", WHITE, "the corpus audited"),
        (f"{n_cand:,}", "candidate windows", BLUE, f"{n_elig} eligible by majority"),
    ]
    yy = py + 0.04
    for i, (num, label, fill, note) in enumerate(steps):
        h = 0.50 if note else 0.34
        d.box(px + 0.30, yy, pw - 0.60, h, fill=fill, line=NAVY, line_w=0.8)
        d.text(px + 0.38, yy + (0.03 if note else 0), 0.95, 0.26, num,
               size=8.9, bold=True, color=NAVY, align=PP_ALIGN.LEFT)
        d.text(px + 1.34, yy + (0.03 if note else 0), pw - 1.70, 0.26, label,
               size=6.4, align=PP_ALIGN.LEFT)
        if note:
            d.text(px + 0.38, yy + 0.29, pw - 0.76, 0.18, note, size=5.4,
                   color=GREY, align=PP_ALIGN.LEFT)
        if i < len(steps) - 1:
            d.chevron_down(px + pw / 2, yy + h + 0.02, w=0.17, h=0.115)
        yy += h + 0.19

    yy += 0.10
    d.box(px + 0.30, yy, pw - 0.60, 0.46, fill=WHITE, line=RED, line_w=0.9)
    d.text(px + 0.38, yy, pw - 0.76, 0.46,
           [("Stage 1 is documented but not\nre-executable; everything below is.",
             {"size": 5.6, "color": RED, "align": PP_ALIGN.LEFT})],
           align=PP_ALIGN.LEFT, line_spacing=0.92)

    # ============================================ panel 2: the instrument
    px, py, pw, ph = d.panel(3.94, 0.10, 4.86, PH, "What the Instrument Asks")

    coords = [
        ("C1", "evidence state", "corpus, retriever, top-k", WHITE),
        ("C2", "origin / capability", "access, budget, scope", WHITE),
        ("C3", "intervention", "excluded from the rule", MUTED),
        ("C4", "outcome / unit", "what is measured, per what", WHITE),
        ("C5", "policy / utility", "action set and its prices", WHITE),
    ]
    crh = 0.245
    gh = len(coords) * crh + 0.33
    gx, gy, gw, _ = d.group(px, py, pw, gh, "Five coordinates, recorded on both sides",
                            fill=WHITE)
    for i, (tag, name, gloss, fill) in enumerate(coords):
        yy = gy + 0.03 + i * crh
        d.box(gx, yy, 0.34, crh - 0.05, fill=fill, line=MUTED, line_w=0.5)
        d.text(gx, yy, 0.34, crh - 0.05, tag, size=6.0, bold=True,
               color=GREY if tag == "C3" else BLACK)
        d.text(gx + 0.42, yy, 1.58, crh - 0.05, name, size=6.0, align=PP_ALIGN.LEFT,
               bold=True, color=GREY if tag == "C3" else BLACK)
        d.text(gx + 2.06, yy, gw - 2.08, crh - 0.05, gloss, size=5.6,
               align=PP_ALIGN.LEFT, color=RED if tag == "C3" else GREY,
               bold=tag == "C3")

    cur = py + gh
    d.chevron_down(px + pw / 2, cur + 0.06)
    cur += 0.30 + GAP

    branches = [
        ("1", "C1, C2, C4, C5 all match", "survives", GREEN),
        ("2", "a matched operating point exists", "narrows", WHITE),
        ("3", "otherwise", "undefined", ORANGE),
    ]
    brh = 0.26
    bgh = len(branches) * brh + 0.33
    gx, gy, gw, _ = d.group(px, cur, pw, bgh, "One decision rule", fill=WHITE)
    for i, (n, cond, out, fill) in enumerate(branches):
        yy = gy + 0.03 + i * brh
        d.box(gx, yy, 0.22, brh - 0.055, fill=WHITE, line=MUTED, line_w=0.5)
        d.text(gx, yy, 0.22, brh - 0.055, n, size=6.0, bold=True, color=NAVY)
        d.text(gx + 0.32, yy, gw - 1.44, brh - 0.055, cond, size=6.0,
               align=PP_ALIGN.LEFT)
        d.box(gx + gw - 1.06, yy, 1.04, brh - 0.055, fill=fill, line=NAVY, line_w=0.7)
        d.text(gx + gw - 1.06, yy, 1.04, brh - 0.055, out, size=6.0, bold=True)

    cur += bgh + 0.18
    d.text(px, cur, pw, 0.44,
           [("C3 always differs, which is what a comparison is for, so it is "
             "recorded and never decisive.", {"size": 6.0, "bold": True, "color": NAVY})])

    # ======================================== panel 3: what is recovered
    px, py, pw, ph = d.panel(9.02, 0.10, 4.28, PH, "Which Judgment Survives")

    block_h = 1.40
    cur = py
    for i, (title, kappa, acc, base, fill, ok) in enumerate([
        ("Provenance\ntransported or re-implemented?",
         kprov, pv.get("accuracy"), pv.get("majority_class_baseline"), GREEN, True),
        ("Verdict\ndoes the quoted gap survive?",
         kverd, vd.get("accuracy"), vd.get("majority_class_baseline"), ORANGE, False),
    ]):
        gx, gy, gw, gh = d.group(px, cur, pw, block_h, "", fill=WHITE, line=NAVY)
        # the tinted strips are insets, not the frame itself: keep them clear
        # of the border on all four sides
        d.box(gx + 0.05, gy - 0.08, gw - 0.10, 0.36, fill=fill, line=None)
        d.text(gx, gy - 0.09, gw, 0.36,
               [(title.split("\n")[0], {"size": 7.4, "bold": True}),
                ("\n" + title.split("\n")[1], {"size": 5.6, "bold": False, "color": GREY})],
               line_spacing=0.92)
        rows = [
            ("inter-judge \u03ba", f"{kappa:.2f}",
             f"ceiling {kmaxv:.2f}" if not ok else ""),
            ("vs. reference",
             f"{acc:.3f}" if acc is not None else "\u2013",
             f"baseline {base:.3f}" if base is not None else ""),
        ]
        for j, (name, val, note) in enumerate(rows):
            ry = gy + 0.38 + j * 0.31
            d.text(gx + 0.04, ry, 1.40, 0.26, name, size=6.0, align=PP_ALIGN.LEFT)
            d.box(gx + 1.48, ry, 0.62, 0.26, fill=WHITE, line=MUTED, line_w=0.5)
            d.text(gx + 1.48, ry, 0.62, 0.26, val, size=6.8, bold=True,
                   color=NAVY if ok else RED)
            if note:
                d.text(gx + 2.16, ry, gw - 2.18, 0.26, note, size=5.4,
                       color=GREY, align=PP_ALIGN.LEFT)
        d.box(gx + 0.05, gy + 0.96, gw - 0.10, 0.22, fill=fill, line=None)
        d.text(gx, gy + 0.96, gw, 0.22,
               "recovered, and validated on real windows" if ok else
               "not recovered, barely beats a constant",
               size=5.8, bold=True, color=NAVY if ok else RED)
        cur += block_h + GAP

    d.box(px + 0.10, cur, pw - 0.20, 0.50, fill=WHITE, line=NAVY, line_w=0.8)
    d.text(px + 0.14, cur, pw - 0.28, 0.50,
           "An automated screen can read a comparison.\nIt cannot adjudicate one.",
           size=5.8, bold=True, color=NAVY, line_spacing=0.95)

    d.connector([(3.72, 1.70), (3.94, 1.70)])
    d.connector([(8.80, 1.70), (9.02, 1.70)])

    OUT.mkdir(parents=True, exist_ok=True)
    return d.save(OUT / "fig_instrument.pptx")


if __name__ == "__main__":
    print(build())
