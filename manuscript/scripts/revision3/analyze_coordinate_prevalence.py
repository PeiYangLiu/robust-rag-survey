#!/usr/bin/env python3
"""Apply the near-constant-label argument to every coordinate, not just C3.

The manuscript excuses C3's negative kappa on the grounds that "a near-constant
label carries no information for kappa to find", and then reads all five
coordinate rows uniformly in Table 1's caption.  A reviewer pointed out that C4
is 90.5% a single label -- as near-constant as C3, in the opposite direction --
so the same artefact applies to it, and the interpretive rule was being applied
asymmetrically in the direction that favours the paper's thesis.

This script computes, for every coordinate and for the verdict, the quantities
that decide whether a low kappa is informative:

*   the majority-label share, which is how near-constant the field is;
*   observed agreement, which is prevalence-free in the sense that matters here;
*   chance agreement under the observed marginals, and the *maximum attainable*
    kappa given those marginals, which is the number that tells a reader whether
    kappa had room to be large;
*   the prevalence-and-bias-adjusted kappa (PABAK) and Gwet's AC1.

A field whose maximum attainable kappa is near zero cannot be read as evidence
of disagreement.  A field whose maximum attainable kappa is high and whose
observed kappa is low can.  The output separates the coordinates into those two
groups mechanically, so the caption can stop asserting one reading for all five.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
COORDS = ["c1", "c2", "c3", "c4", "c5"]
COORD_LABELS = ["match", "mismatch", "not_determinable"]
VERDICTS = ["survives", "narrows", "undefined"]


def fleiss(rows: list[list[str]]) -> float:
    rows = [r for r in rows if len(r) >= 2]
    if not rows:
        return float("nan")
    cats = sorted({v for r in rows for v in r})
    if len(cats) < 2:
        return float("nan")
    n = len(rows[0])
    counts = [[r.count(c) for c in cats] for r in rows]
    p_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in counts]
    p_bar = sum(p_i) / len(p_i)
    p_j = [sum(row[j] for row in counts) / (len(rows) * n) for j in range(len(cats))]
    p_e = sum(p * p for p in p_j)
    return (p_bar - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def observed(rows: list[list[str]]) -> float:
    if not rows:
        return float("nan")
    tot = 0.0
    for r in rows:
        n = len(r)
        pairs = n * (n - 1) / 2
        same = sum(v * (v - 1) / 2 for v in Counter(r).values())
        tot += same / pairs if pairs else 0.0
    return tot / len(rows)


def chance(rows: list[list[str]]) -> float:
    cats = sorted({v for r in rows for v in r})
    n = len(rows[0]) if rows else 0
    if not cats or not n:
        return float("nan")
    p_j = [
        sum(r.count(c) for r in rows) / (len(rows) * n) for c in cats
    ]
    return sum(p * p for p in p_j)


def max_attainable_kappa(rows: list[list[str]]) -> float:
    """Cohen's ``kappa_max``, averaged over rater pairs.

    Holding every rater's own label distribution fixed, the largest pairwise
    agreement two raters can reach is ``sum_c min(n_j(c), n_k(c)) / N``
    (Umesh et al., 1989; Sim and Wright, 2005).  Averaging that bound over all
    rater pairs bounds the mean pairwise agreement Fleiss' kappa is built from,
    so putting it through the kappa formula with the same chance term gives the
    largest kappa these raters could have attained without changing how often
    each of them uses each label.

    This is the number a low kappa has to be read against.  When raters hold
    different thresholds -- which is what this paper finds -- their marginals
    differ, the ceiling falls, and a kappa near zero is partly a statement about
    that difference rather than about item-level noise.
    """
    if not rows:
        return float("nan")
    n = len(rows[0])
    if n < 2:
        return float("nan")
    per_judge = [Counter(r[j] for r in rows) for j in range(n)]
    total = len(rows)
    bounds = []
    for a in range(n):
        for b in range(a + 1, n):
            cats = set(per_judge[a]) | set(per_judge[b])
            bounds.append(
                sum(min(per_judge[a].get(c, 0), per_judge[b].get(c, 0)) for c in cats) / total
            )
    p_o_max = sum(bounds) / len(bounds)
    p_e = chance(rows)
    return (p_o_max - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def pabak(rows: list[list[str]]) -> float:
    k = len({v for r in rows for v in r}) or 1
    p_o = observed(rows)
    return (k * p_o - 1) / (k - 1) if k > 1 else float("nan")


def gwet_ac1(rows: list[list[str]]) -> float:
    cats = sorted({v for r in rows for v in r})
    q = len(cats)
    if q < 2 or not rows:
        return float("nan")
    n = len(rows[0])
    p_j = [sum(r.count(c) for r in rows) / (len(rows) * n) for c in cats]
    p_e = sum(p * (1 - p) for p in p_j) / (q - 1)
    p_o = observed(rows)
    return (p_o - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    ap.add_argument("--ledger", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv")
    ap.add_argument("--out", type=Path, default=SUPPLEMENT / "coordinate_prevalence.json")
    ap.add_argument("--near-constant-threshold", type=float, default=0.85)
    args = ap.parse_args()

    per_judge = {}
    for name in DEPLOYED:
        table = {}
        for line in (args.coding_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row["parsed"]
        per_judge[name] = table

    eligible = [
        r["candidate_id"]
        for r in csv.DictReader(args.ledger.open(encoding="utf-8"))
        if all(r["candidate_id"] in per_judge[j] for j in DEPLOYED)
    ]

    fields = {}
    for coord in COORDS:
        rows = [
            [
                str(per_judge[j][cid].get(coord, "not_determinable")).strip().lower()
                for j in DEPLOYED
            ]
            for cid in eligible
        ]
        fields[coord] = rows
    fields["verdict"] = [
        [
            (str(per_judge[j][cid].get("verdict", "")).strip().lower()
             if str(per_judge[j][cid].get("verdict", "")).strip().lower() in VERDICTS
             else "undefined")
            for j in DEPLOYED
        ]
        for cid in eligible
    ]

    out = {}
    for name, rows in fields.items():
        flat = Counter(v for r in rows for v in r)
        total = sum(flat.values())
        top_label, top_n = flat.most_common(1)[0]
        share = top_n / total
        k = fleiss(rows)
        kmax = max_attainable_kappa(rows)
        out[name] = {
            "n_items": len(rows),
            "label_counts": dict(flat),
            "majority_label": top_label,
            "majority_label_share": share,
            "near_constant": share >= args.near_constant_threshold,
            "observed_agreement": observed(rows),
            "chance_agreement": chance(rows),
            "fleiss_kappa": k,
            "max_attainable_kappa": kmax,
            "kappa_as_share_of_attainable": (k / kmax) if kmax and kmax == kmax and abs(kmax) > 1e-9 else float("nan"),
            "pabak": pabak(rows),
            "gwet_ac1": gwet_ac1(rows),
        }

    informative = [
        n for n, v in out.items() if not v["near_constant"] and v["max_attainable_kappa"] > 0.5
    ]
    uninformative = [n for n, v in out.items() if n not in informative]

    payload = {
        "schema_version": 1,
        "n_eligible": len(eligible),
        "near_constant_threshold": args.near_constant_threshold,
        "fields": out,
        "kappa_is_interpretable_for": sorted(informative),
        "kappa_is_a_prevalence_artefact_for": sorted(uninformative),
        "reading": (
            "A low kappa is evidence of disagreement only where kappa had room "
            "to be high. For the fields listed as prevalence artefacts, the "
            "marginals cap kappa near zero regardless of how the judges behave, "
            "so the caption must not read their rows as disagreement. The "
            "submitted version made this argument for C3 alone; it applies "
            "identically wherever the majority-label share is above "
            f"{args.near_constant_threshold:.2f}."
        ),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name in COORDS + ["verdict"]:
        v = out[name]
        print(
            f"{name:8s} top={v['majority_label'][:16]:16s} share={v['majority_label_share']:.3f} "
            f"obs={v['observed_agreement']:.3f} k={v['fleiss_kappa']:+.3f} "
            f"kmax={v['max_attainable_kappa']:+.3f} "
            f"near_const={v['near_constant']}"
        )
    print("interpretable:", sorted(informative))
    print("artefact:", sorted(uninformative))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
