#!/usr/bin/env python3
"""Reviewer Q6: bounds on deployed-panel accuracy over the excluded privileged windows.

Accuracy against the evidence-privileged reference is reported only where the
reference adjudicators reached a quote-verified majority: 114 of 180 windows for
the verdict pass, 170 of 180 for provenance.  A reviewer objected that the
excluded windows are the hardest, and that motivating an ``undecidable'' claim
with them while dropping them from the accuracy is having it both ways.

This script does three things and invents nothing.

1.  It states the *exact* accounting from the ledger: how the 180 windows split
    by whether the reference reached a majority and by whether the deployed
    panel itself produced a verdict.  The reviewer's implied ``165 = 114 + 51''
    denominator is checked against the data and corrected.
2.  It computes worst-case (panel wrong on every excluded window) and best-case
    (panel right on every excluded window) accuracy over each explicit
    denominator, for both the verdict and the provenance pass.
3.  It characterises the reference-no-majority windows against the
    reference-majority windows on the deployed panel's own labels, whether the
    deployed panel reached a majority, the reference adjudicators' vote-split
    entropy, window length, coordinate-term density, and stratum, with a
    Mann-Whitney U or chi-square test and an effect size for each.

Uses only the Python standard library.  The privileged-reference helper module
is imported read-only to reproduce the published 129/51 quote-verified split
exactly; if it is unavailable the quote-verified entropy is omitted rather than
approximated.  Writes ``supplement/privileged_reference_bounds.json``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
REVISION3 = REPO / "manuscript" / "scripts" / "revision3"

DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
REFERENCE = ["refA_claudeopus5", "refC_gemini31pro", "refD_claudeopus48", "refE_gpt55cli"]
COORDINATES = ("c1", "c2", "c3", "c4", "c5")

# Coordinate vocabulary taken verbatim from the C1--C5 codebook in
# scripts/code_cross_paper_frame.py; "coordinate terms mentioned" counts how
# many of these distinct terms occur in the window text.
COORD_LEXICON = [
    "corpus", "snapshot", "retriever", "retrieval", "distractor", "conflict",
    "noise", "passage", "gold", "irrelevant", "insufficient", "conflicting",
    "stale", "malicious", "adversary", "adversarial", "injection", "inject",
    "budget", "query access", "persistence", "trigger", "triggered", "backbone",
    "generator", "dataset", "benchmark", "metric", "exact match", "substring",
    "attack success", "hit rate", "certified", "accuracy", "abstention",
    "abstain", "defer", "deferral", "cost", "operating point",
]


# ----------------------------------------------------------------- statistics
def wilson(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def entropy(labels: list[str]) -> float:
    n = len(labels)
    if n == 0:
        return float("nan")
    counts = Counter(labels)
    return -sum((v / n) * math.log2(v / n) for v in counts.values())


def _rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def mann_whitney(x: list[float], y: list[float]) -> dict:
    """Two-sided Mann-Whitney U with tie-corrected normal approximation.

    Reports U for the first group and Cliff's delta as the effect size.
    """
    x = [v for v in x if v == v]
    y = [v for v in y if v == v]
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return {"u": float("nan"), "p_value": float("nan"), "cliffs_delta": float("nan"),
                "n1": n1, "n2": n2}
    ranks = _rankdata(x + y)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    N = n1 + n2
    tie = sum(c ** 3 - c for c in Counter(x + y).values())
    var = n1 * n2 / 12 * ((N + 1) - tie / (N * (N - 1)))
    if var <= 0:
        p = float("nan")
    else:
        z = (u1 - mu) / math.sqrt(var)
        p = math.erfc(abs(z) / math.sqrt(2))
    # Cliff's delta = P(x>y) - P(x<y)
    gt = lt = 0
    for a in x:
        for b in y:
            if a > b:
                gt += 1
            elif a < b:
                lt += 1
    delta = (gt - lt) / (n1 * n2)
    return {"u": u1, "p_value": p, "cliffs_delta": delta, "n1": n1, "n2": n2}


def _gammainc_upper_reg(s: float, x: float) -> float:
    """Regularised upper incomplete gamma Q(s, x); stdlib only."""
    if x < 0 or s <= 0:
        return float("nan")
    if x == 0:
        return 1.0
    if x < s + 1:
        term = 1.0 / s
        total = term
        n = 1
        while n < 10000:
            term *= x / (s + n)
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
            n += 1
        p_reg = total * math.exp(-x + s * math.log(x) - math.lgamma(s))
        return 1.0 - p_reg
    tiny = 1e-300
    b = x + 1 - s
    c = 1 / tiny
    d = 1 / b
    h = d
    i = 1
    while i < 10000:
        an = -i * (i - s)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
        i += 1
    return h * math.exp(-x + s * math.log(x) - math.lgamma(s))


def chi_square(table: list[list[int]]) -> dict:
    """Pearson chi-square test of independence with Cramer's V."""
    rows = len(table)
    cols = len(table[0])
    rowsum = [sum(r) for r in table]
    colsum = [sum(table[i][j] for i in range(rows)) for j in range(cols)]
    N = sum(rowsum)
    chi2 = 0.0
    for i in range(rows):
        for j in range(cols):
            e = rowsum[i] * colsum[j] / N if N else 0.0
            if e > 0:
                chi2 += (table[i][j] - e) ** 2 / e
    df = (rows - 1) * (cols - 1)
    p = _gammainc_upper_reg(df / 2.0, chi2 / 2.0) if df > 0 else float("nan")
    k = min(rows, cols)
    v = math.sqrt(chi2 / (N * (k - 1))) if k > 1 and N > 0 else float("nan")
    return {"chi2": chi2, "df": df, "p_value": p, "cramers_v": v, "n": N}


def fisher_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for a 2x2 table."""
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c

    def hp(x: int) -> float:
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)

    lo, hi = max(0, c1 - r2), min(c1, r1)
    p_obs = hp(a)
    return sum(hp(x) for x in range(lo, hi + 1) if hp(x) <= p_obs * (1 + 1e-9))


# ----------------------------------------------------------------- data loading
def load_runs(directory: Path) -> dict:
    out: dict[tuple[str, str, str], dict[str, dict]] = {}
    for path in sorted(directory.glob("*.jsonl")):
        parts = path.stem.split("__")
        if len(parts) != 3:
            continue
        key = (parts[0], parts[1], parts[2])
        table = out.setdefault(key, {})
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row
    return out


def norm_verdict(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in {"survives", "narrows", "undefined"} else "undefined"


def majority(values: list[str]) -> str | None:
    if not values:
        return None
    top, n = Counter(values).most_common(1)[0]
    return top if n > len(values) / 2 else None


def best_tier(runs: dict, cid: str, pass_name: str, judge: str) -> str | None:
    for tier in ("both_full", "citing_full"):
        if cid in runs.get((pass_name, tier, judge), {}):
            return tier
    return None


def bounds_block(correct: int, scored: int, denominators: dict[str, dict]) -> dict:
    """worst/best-case accuracy for each named denominator.

    denominators[name] = {"n": int, "n_extra_scorable": int, "note": str}
    where n_extra_scorable is how many currently-unscored windows enter this
    denominator (best case adds them all as correct; worst case adds none).
    """
    base_lo, base_hi = wilson(correct, scored)
    out = {
        "n_scored": scored,
        "n_correct": correct,
        "accuracy": correct / scored if scored else float("nan"),
        "wilson_ci95": [base_lo, base_hi],
        "by_denominator": {},
    }
    for name, spec in denominators.items():
        n = spec["n"]
        extra = spec["n_extra_scorable"]
        out["by_denominator"][name] = {
            "denominator": n,
            "n_extra_beyond_scored": extra,
            "worst_case_accuracy": correct / n if n else float("nan"),
            "best_case_accuracy": (correct + extra) / n if n else float("nan"),
            "note": spec["note"],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, default=SUPPLEMENT / "privileged_reference_ledger.csv")
    ap.add_argument("--sample", type=Path, default=SUPPLEMENT / "privileged_reference_sample.jsonl")
    ap.add_argument("--runs", type=Path, default=SUPPLEMENT / "privileged_reference_runs")
    ap.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    ap.add_argument("--output", type=Path, default=SUPPLEMENT / "privileged_reference_bounds.json")
    args = ap.parse_args()

    ledger = {r["candidate_id"]: r for r in csv.DictReader(args.ledger.open(encoding="utf-8"))}
    sample = {}
    for line in args.sample.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            sample[row["candidate_id"]] = row
    runs = load_runs(args.runs)

    deployed_cod = {}
    for name in DEPLOYED:
        table = {}
        for line in (args.coding_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row["parsed"]
        deployed_cod[name] = table

    # ------------------------------------------------------------------
    # A. exact accounting and bounds for each pass
    # ------------------------------------------------------------------
    def accounting(pass_name: str) -> tuple[dict, dict]:
        ref_f, dep_f = f"reference_{pass_name}", f"deployed_{pass_name}"
        yy = yn = ny = nn = 0
        correct = 0
        for cid, lr in ledger.items():
            ref = lr[ref_f].strip()
            dep = lr[dep_f].strip()
            if ref and dep:
                yy += 1
                correct += int(ref == dep)
            elif ref and not dep:
                yn += 1
            elif not ref and dep:
                ny += 1
            else:
                nn += 1
        n_total = yy + yn + ny + nn
        n_ref_maj = yy + yn
        n_ref_nomaj = ny + nn
        n_dep_commit = yy + ny
        acct = {
            "n_total": n_total,
            "n_reference_majority": n_ref_maj,
            "n_reference_no_majority": n_ref_nomaj,
            "n_deployed_committed": n_dep_commit,
            "n_deployed_abstained": yn + nn,
            "n_scored": yy,
            "n_correct_scored": correct,
            "crosstab": {
                "ref_maj_and_deployed_committed": yy,
                "ref_maj_and_deployed_abstained": yn,
                "ref_no_maj_and_deployed_committed": ny,
                "ref_no_maj_and_deployed_abstained": nn,
            },
        }
        # denominators. "extra scorable" = currently-unscored windows folded in.
        denoms = {
            "full_sample": {
                "n": n_total,
                "n_extra_scorable": n_total - yy,
                "note": (
                    f"all {n_total} sampled windows; the {n_total - yy} beyond the "
                    f"{yy} scored are {ny + nn} with no reference majority plus "
                    f"{yn} with a reference majority but no deployed verdict"
                ),
            },
            "deployed_committed": {
                "n": n_dep_commit,
                "n_extra_scorable": ny,
                "note": (
                    f"only windows where the deployed panel produced a verdict "
                    f"({n_dep_commit} = {yy} scored + {ny} no-reference-majority "
                    f"but deployed-committed); the {yn + nn} deployed abstentions "
                    f"are excluded because the panel issued no verdict to score"
                ),
            },
            "reviewer_scored_plus_all_no_majority": {
                "n": yy + n_ref_nomaj,
                "n_extra_scorable": n_ref_nomaj,
                "note": (
                    f"the reviewer's implied denominator, scored + every "
                    f"no-reference-majority window ({yy} + {n_ref_nomaj} = "
                    f"{yy + n_ref_nomaj}); NOTE only {ny} of these "
                    f"{n_ref_nomaj} no-majority windows carry a deployed verdict, "
                    f"so the count of windows where the deployed panel actually "
                    f"committed is {n_dep_commit}, not {yy + n_ref_nomaj}"
                ),
            },
        }
        return acct, denoms

    passes = {}
    for pass_name in ("verdict", "provenance"):
        acct, denoms = accounting(pass_name)
        block = bounds_block(acct["n_correct_scored"], acct["n_scored"], denoms)
        block["accounting"] = acct
        # premise check for the reviewer's 114+51 (verdict) / 170+9 (provenance)
        block["reviewer_denominator_premise_holds"] = (
            acct["crosstab"]["ref_no_maj_and_deployed_committed"]
            == acct["n_reference_no_majority"]
        )
        passes[pass_name] = block

    # ------------------------------------------------------------------
    # B. characterise the reference-no-majority verdict windows vs the rest
    # ------------------------------------------------------------------
    # optional import to reproduce the published quote-verified split exactly
    verified_entropy_available = True
    try:
        import sys
        sys.path.insert(0, str(REVISION3))
        import analyze_privileged_reference as A  # noqa: E402
    except Exception:
        verified_entropy_available = False
        A = None

    def raw_reference_votes(cid: str) -> list[str]:
        out = []
        for judge in REFERENCE:
            tier = best_tier(runs, cid, "comparability", judge)
            if tier is not None:
                out.append(norm_verdict(runs[("comparability", tier, judge)][cid]["parsed"].get("verdict")))
        return out

    def verified_reference_votes(cid: str, row: dict) -> list[str]:
        out = []
        for judge in REFERENCE:
            tier = best_tier(runs, cid, "comparability", judge)
            if tier is None:
                continue
            parsed = runs[("comparability", tier, judge)][cid]["parsed"]
            ok = A.quote_ok(parsed.get("evidence_quote", ""), row["cite_key"])
            if tier == "both_full" and row["cited_papers"]:
                cited = [c["cite_key"] for c in row["cited_papers"][:2]]
                ok = ok and any(A.quote_ok(parsed.get("evidence_quote_cited", ""), k) for k in cited)
            if ok:
                out.append(norm_verdict(parsed.get("verdict")))
        return out

    def n_determinable(cid: str) -> int:
        n = 0
        for c in COORDINATES:
            labs = [str(deployed_cod[j].get(cid, {}).get(c, "")).lower() for j in DEPLOYED]
            if majority([x for x in labs if x]) in ("match", "mismatch"):
                n += 1
        return n

    def coord_terms(text: str) -> int:
        low = text.lower()
        return sum(1 for term in COORD_LEXICON if term in low)

    feats = []
    for cid, row in sample.items():
        lr = ledger[cid]
        group = "established" if lr["reference_verdict"].strip() else "no_majority"
        raw = raw_reference_votes(cid)
        rec = {
            "group": group,
            "deployed_label": lr["deployed_verdict"].strip() or "none",
            "deployed_majority": 1 if lr["deployed_verdict"].strip() else 0,
            "reference_vote_entropy_raw": entropy(raw),
            "n_verified_reference_votes": int(lr["n_verified_votes_verdict"]),
            "window_length_words": len(row["window_text"].split()),
            "window_length_chars": len(row["window_text"]),
            "coordinate_terms_mentioned": coord_terms(row["window_text"]),
            "n_determinable_coordinates": n_determinable(cid),
            "stratum": row["stratum"],
        }
        if verified_entropy_available:
            rec["reference_vote_entropy_verified"] = entropy(verified_reference_votes(cid, row))
        feats.append(rec)

    est = [f for f in feats if f["group"] == "established"]
    nom = [f for f in feats if f["group"] == "no_majority"]

    def summ(vals: list[float]) -> dict:
        clean = sorted(v for v in vals if v == v)
        if not clean:
            return {"n": 0, "mean": float("nan"), "median": float("nan")}
        n = len(clean)
        med = clean[n // 2] if n % 2 else (clean[n // 2 - 1] + clean[n // 2]) / 2
        return {"n": n, "mean": sum(clean) / n, "median": med}

    continuous_fields = [
        "reference_vote_entropy_raw",
        "n_verified_reference_votes",
        "window_length_words",
        "window_length_chars",
        "coordinate_terms_mentioned",
        "n_determinable_coordinates",
    ]
    if verified_entropy_available:
        continuous_fields.insert(1, "reference_vote_entropy_verified")

    continuous = {}
    for field in continuous_fields:
        x = [f[field] for f in est]
        y = [f[field] for f in nom]
        test = mann_whitney(x, y)
        continuous[field] = {
            "established": summ(x),
            "no_majority": summ(y),
            "mannwhitney_u": test["u"],
            "p_value": test["p_value"],
            "cliffs_delta": test["cliffs_delta"],
            "n_established_used": test["n1"],
            "n_no_majority_used": test["n2"],
        }

    categorical = {}
    # deployed verdict label
    labels = sorted({f["deployed_label"] for f in feats})
    table = [[sum(1 for f in g if f["deployed_label"] == l) for l in labels] for g in (est, nom)]
    categorical["deployed_verdict_label"] = {
        "levels": labels,
        "established_counts": table[0],
        "no_majority_counts": table[1],
        **chi_square(table),
    }
    # deployed reached majority (2x2)
    a = sum(f["deployed_majority"] for f in est)
    b = len(est) - a
    c = sum(f["deployed_majority"] for f in nom)
    d = len(nom) - c
    cat = chi_square([[a, b], [c, d]])
    cat["fisher_p_value"] = fisher_2x2(a, b, c, d)
    categorical["deployed_reached_majority"] = {
        "levels": ["committed", "abstained"],
        "established_counts": [a, b],
        "no_majority_counts": [c, d],
        "established_commit_rate": a / (a + b) if (a + b) else float("nan"),
        "no_majority_commit_rate": c / (c + d) if (c + d) else float("nan"),
        **cat,
    }
    # stratum
    strata = sorted({f["stratum"] for f in feats})
    table = [[sum(1 for f in g if f["stratum"] == s) for s in strata] for g in (est, nom)]
    categorical["stratum"] = {
        "levels": strata,
        "established_counts": table[0],
        "no_majority_counts": table[1],
        **chi_square(table),
    }

    payload = {
        "schema_version": "privileged-reference-bounds-v1",
        "question": (
            "Reviewer Q6: bounds on deployed-panel accuracy if the excluded "
            "no-reference-majority windows are counted, and how those windows differ."
        ),
        "sample": {
            "n_windows": len(sample),
            "n_papers": len({r["cite_key"] for r in sample.values()}),
        },
        "verdict": passes["verdict"],
        "provenance": passes["provenance"],
        "characterization_no_majority_vs_established": {
            "pass": "verdict (comparability)",
            "groups": {"established": len(est), "no_majority": len(nom)},
            "verified_entropy_available": verified_entropy_available,
            "coordinate_lexicon_size": len(COORD_LEXICON),
            "continuous": continuous,
            "categorical": categorical,
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # ------------------------------------------------------------------ console
    def show(pass_name: str) -> None:
        blk = passes[pass_name]
        ac = blk["accounting"]
        lo, hi = blk["wilson_ci95"]
        print(f"\n=== {pass_name.upper()} ===")
        print(f"  base accuracy {ac['n_correct_scored']}/{ac['n_scored']} = "
              f"{blk['accuracy']:.4f}  Wilson[{lo:.4f},{hi:.4f}]")
        ct = ac["crosstab"]
        print(f"  reference majority {ac['n_reference_majority']}  no-majority {ac['n_reference_no_majority']}"
              f"  |  deployed committed {ac['n_deployed_committed']}  abstained {ac['n_deployed_abstained']}")
        print(f"  crosstab yy={ct['ref_maj_and_deployed_committed']} "
              f"yn={ct['ref_maj_and_deployed_abstained']} "
              f"ny={ct['ref_no_maj_and_deployed_committed']} "
              f"nn={ct['ref_no_maj_and_deployed_abstained']}")
        print(f"  reviewer denominator premise holds: {blk['reviewer_denominator_premise_holds']}")
        for name, bd in blk["by_denominator"].items():
            print(f"    {name:<42} N={bd['denominator']:>3}  "
                  f"worst={bd['worst_case_accuracy']:.4f}  best={bd['best_case_accuracy']:.4f}")

    show("verdict")
    show("provenance")

    print("\n=== characterization: no-majority (51) vs established (129), verdict ===")
    for field, e in continuous.items():
        print(f"  {field:<34} est_med={e['established']['median']:.2f} "
              f"nom_med={e['no_majority']['median']:.2f}  p={e['p_value']:.3g} "
              f"delta={e['cliffs_delta']:+.3f}")
    for field, e in categorical.items():
        extra = f" fisher_p={e['fisher_p_value']:.3g}" if "fisher_p_value" in e else ""
        print(f"  {field:<34} chi2={e['chi2']:.3f} df={e['df']} "
              f"p={e['p_value']:.3g} V={e['cramers_v']:.3f}{extra}")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
