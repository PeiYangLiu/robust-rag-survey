#!/usr/bin/env python3
"""Test whether the human anchor and the census sit on one population.

The human panel coded published comparative *claims*; the census codes 45-line
screen *windows*. Those are different populations, so the human result cannot
be transferred to the census number without an argument. This script tests
whether such an argument is available: the deployed census panel, under the
byte-identical census codebook, coded the same claims the humans saw.

The answer is that it is not. The census eligibility rule requires a passage to
juxtapose a result credited to a *different* paper, and almost none of the
human-coded claims satisfy it, so the two populations barely intersect. We
report that overlap as the reason the human anchor is scoped to the claim
population rather than transferred, and we do not report a kappa difference
across the two, because the near-total ineligibility of the claims drives their
agreement to a degenerate ceiling.

Reads ``supplement/population_bridge/*.jsonl`` (produced by
``run_population_bridge.py``) and ``supplement/cross_paper_census_ledger.csv``.
Writes ``supplement/population_bridge_results.json``,
``tables/population_bridge.tex`` and macros prefixed ``Brg``.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import random
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUP = ROOT / "supplement"
DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
COORDS = ["c1", "c2", "c3", "c4", "c5"]

from analyze_human_anchor import (  # noqa: E402
    chance,
    cluster_bootstrap,
    fleiss,
    gwet_ac1,
    kappa_max,
    observed,
)


def load_bridge(path):
    per_judge = {}
    for name in DEPLOYED:
        table = {}
        for line in (path / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed"):
                table[row["annotation_id"]] = row
        per_judge[name] = table
    return per_judge


def load_census(ledger):
    rows = list(csv.DictReader(ledger.open(encoding="utf-8-sig")))
    out = {"verdict": [], **{c: [] for c in COORDS}}
    for row in rows:
        labels = [
            (row.get(f"{j}_verdict") or "").strip().lower() for j in DEPLOYED
        ]
        if all(labels):
            out["verdict"].append(labels)
    return out, len(rows)


def load_sources():
    path = (
        ROOT
        / "human_coding"
        / "observed_claim_human_validation_20260714"
        / "annotated_20260714"
        / "human_final_consensus.csv"
    )
    if not path.exists():
        path = path.parent / "analysis_results" / "final" / "human_final_consensus.csv"
    return {
        r["annotation_id"].strip(): (r.get("source_key") or "").strip()
        for r in csv.DictReader(path.open(encoding="utf-8-sig"))
    }


def stats(rows, clusters=None):
    if not rows:
        return None
    out = {
        "n": len(rows),
        "fleiss_kappa": fleiss(rows),
        "observed_agreement": observed(rows),
        "kappa_max": kappa_max(rows),
        "gwet_ac1": gwet_ac1(rows),
        "modal_share": Counter(v for r in rows for v in r).most_common(1)[0][1]
        / sum(len(r) for r in rows),
    }
    if clusters:
        lo, hi = cluster_bootstrap(rows, clusters, fleiss)
        out["fleiss_kappa_ci95"] = [lo, hi]
    km = out["kappa_max"]
    out["share_of_ceiling"] = out["fleiss_kappa"] / km if km else float("nan")
    return out


def fmt(x, d=2):
    return "--" if x != x else f"{x:.{d}f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-dir", type=pathlib.Path, default=SUP / "population_bridge")
    parser.add_argument("--ledger", type=pathlib.Path, default=SUP / "cross_paper_census_ledger.csv")
    parser.add_argument("--out", type=pathlib.Path, default=SUP / "population_bridge_results.json")
    parser.add_argument("--table", type=pathlib.Path, default=ROOT / "tables" / "population_bridge.tex")
    parser.add_argument("--macros", type=pathlib.Path, default=ROOT / "tables" / "revision4_bridge_macros.tex")
    args = parser.parse_args()

    bridge = load_bridge(args.bridge_dir)
    sources = load_sources()
    ids = sorted(set.intersection(*(set(t) for t in bridge.values())))

    claim_rows, claim_clusters = [], []
    coord_rows = {c: [] for c in COORDS}
    for item_id in ids:
        labels = [bridge[j][item_id].get("verdict", "") for j in DEPLOYED]
        if all(labels):
            claim_rows.append(labels)
            claim_clusters.append(sources.get(item_id, item_id))
        for coord in COORDS:
            cl = [bridge[j][item_id].get(coord, "") for j in DEPLOYED]
            if all(cl):
                coord_rows[coord].append(cl)

    census, n_census = load_census(args.ledger)

    results = {
        "design": (
            "Same three deployed judges, same census codebook, two item "
            "populations: published comparative claims and 45-line screen windows."
        ),
        "claims": {
            "verdict": stats(claim_rows, claim_clusters),
            **{c: stats(coord_rows[c]) for c in COORDS},
        },
        "census_windows": {"verdict": stats(census["verdict"]), "n_rows": n_census},
        "eligibility_on_claims": {
            j: sum(1 for i in ids if bridge[j][i].get("eligible")) / len(ids)
            for j in DEPLOYED
        },
    }
    a = results["claims"]["verdict"]
    b = results["census_windows"]["verdict"]
    elig = results["eligibility_on_claims"]
    unanimous_eligible = sum(
        1 for i in ids if all(bridge[j][i].get("eligible") for j in DEPLOYED)
    )
    any_eligible = sum(
        1 for i in ids if any(bridge[j][i].get("eligible") for j in DEPLOYED)
    )
    results["commensurability"] = {
        "n_claims": len(ids),
        "per_judge_eligible_share": elig,
        "eligible_share_min": min(elig.values()),
        "eligible_share_max": max(elig.values()),
        "n_eligible_any_judge": any_eligible,
        "n_eligible_unanimous": unanimous_eligible,
        "claims_observed_agreement": a["observed_agreement"],
        "claims_modal_share": a["modal_share"],
        "claims_share_of_ceiling": a["share_of_ceiling"],
        "windows_observed_agreement": b["observed_agreement"],
        "windows_modal_share": b["modal_share"],
        "reading": (
            "Between "
            f"{100 * min(elig.values()):.0f}% and {100 * max(elig.values()):.0f}% "
            "of the human-coded claims are eligible under the census rule, which "
            "requires a number credited to a different paper. The two populations "
            "therefore barely intersect: the claims run agrees at "
            f"{a['observed_agreement']:.2f} only because judges call almost every "
            "claim ineligible and default to one label, which is a degenerate "
            "agreement and not a lower census difficulty. We conclude that the "
            "human anchor licenses a statement about adjudicating published "
            "comparative claims, and that transferring it to the census number is "
            "not supported. No kappa is compared across the two populations."
        ),
    }
    args.out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    com = results["commensurability"]
    lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{@{}lrrr@{}}",
        r"\toprule",
        r"Population & $N$ & census-eligible & obs.\ agr. \\",
        r"\midrule",
        f"Published claims & {a['n']} & "
        f"{100 * com['eligible_share_min']:.0f}--{100 * com['eligible_share_max']:.0f}\\% & "
        f"{fmt(a['observed_agreement'])} \\\\",
        f"Screen windows & {b['n']} & 100\\% (by selection) & "
        f"{fmt(b['observed_agreement'])} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Why the human anchor is not transferred to the census. The same "
        r"three deployed judges apply the same census codebook to the \BrgClaimN{} "
        r"published claims the human panel coded and to the \CensusEligible{} "
        r"eligible screen windows of \S\ref{sec:applied}. Only "
        r"\BrgEligLo--\BrgEligHi\% of the claims are eligible under the census rule, "
        r"which demands a number credited to a different paper, so the two "
        r"populations barely intersect and the high agreement in the first row is "
        r"judges defaulting to one label on ineligible items, not an easier task. "
        r"We therefore report the human result as evidence about adjudicating "
        r"published claims and compare no $\kappa$ across the two rows.}",
        r"\label{tab:population-bridge}",
        r"\end{table}",
    ]
    args.table.write_text("\n".join(lines) + "\n", encoding="utf-8")

    macro = [
        "% Generated by scripts/revision4/analyze_population_bridge.py -- do not edit by hand.",
        f"\\newcommand{{\\BrgClaimN}}{{{a['n']}}}",
        f"\\newcommand{{\\BrgClaimK}}{{{fmt(a['fleiss_kappa'])}}}",
        f"\\newcommand{{\\BrgClaimKmax}}{{{fmt(a['kappa_max'])}}}",
        f"\\newcommand{{\\BrgClaimObs}}{{{fmt(a['observed_agreement'])}}}",
        f"\\newcommand{{\\BrgWinK}}{{{fmt(b['fleiss_kappa'])}}}",
        f"\\newcommand{{\\BrgWinKmax}}{{{fmt(b['kappa_max'])}}}",
        f"\\newcommand{{\\BrgEligLo}}{{{100 * com['eligible_share_min']:.0f}}}",
        f"\\newcommand{{\\BrgEligHi}}{{{100 * com['eligible_share_max']:.0f}}}",
        f"\\newcommand{{\\BrgEligAny}}{{{com['n_eligible_any_judge']}}}",
        f"\\newcommand{{\\BrgEligUnan}}{{{com['n_eligible_unanimous']}}}",
        f"\\newcommand{{\\BrgWinObs}}{{{fmt(b['observed_agreement'])}}}",
    ]
    if "fleiss_kappa_ci95" in a:
        macro.append(
            f"\\newcommand{{\\BrgClaimKCI}}{{[{fmt(a['fleiss_kappa_ci95'][0])}, "
            f"{fmt(a['fleiss_kappa_ci95'][1])}]}}"
        )
    args.macros.write_text("\n".join(macro) + "\n", encoding="utf-8")

    print(json.dumps(results, indent=2, default=str)[:2200])
    print(f"\nwrote {args.out}\nwrote {args.table}\nwrote {args.macros}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
