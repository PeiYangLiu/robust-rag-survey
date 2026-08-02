#!/usr/bin/env python3
"""Make the constructed/corpus kappa contrast like for like.

The paper's core diagnostic contrasts kappa 0.74 on constructed passages that
state their coordinates with kappa 0.06 on published windows, and attributes the
whole gap to the disclosure regime.  A reviewer noted that at least four things
differ between the two settings: the label space (the constructed items are a
balanced three-class problem, while ``narrows`` is essentially unreachable in
the census), item length, source, and the fact that census eligibility is itself
uncertain.

This script removes the differences that can be removed and reports what is
left.  For both settings it computes, on matched label spaces:

*   Fleiss' kappa and observed agreement;
*   the ceiling those judges' own marginals impose on kappa, so that a low kappa
    is read against what was attainable rather than against 1.0;
*   the same statistics after collapsing to the two-class space the census can
    actually reach.

The residual gap after all of this is what the disclosure account has to
explain, and it is smaller than the number the submitted abstract printed.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_coordinate_prevalence import (  # noqa: E402
    chance,
    fleiss,
    gwet_ac1,
    max_attainable_kappa,
    observed,
)

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
VERDICTS = {"survives", "narrows", "undefined"}


def norm_verdict(v) -> str:
    s = str(v or "").strip().lower()
    return s if s in VERDICTS else "undefined"


def collapse(v: str) -> str:
    return "survives" if v == "survives" else "not_survives"


def census_rows(coding_dir: Path, ledger: Path) -> tuple[list[list[str]], list[str]]:
    per_judge = {}
    for name in DEPLOYED:
        table = {}
        for line in (coding_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row["parsed"]
        per_judge[name] = table
    rows, papers = [], []
    for r in csv.DictReader(ledger.open(encoding="utf-8")):
        cid = r["candidate_id"]
        if all(cid in per_judge[j] for j in DEPLOYED):
            rows.append([norm_verdict(per_judge[j][cid].get("verdict")) for j in DEPLOYED])
            papers.append(r["cite_key"])
    return rows, papers


def instrument_rows(runs_dir: Path, benchmark: Path, arm: str, strata: set[str]):
    spec = {}
    for line in benchmark.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            spec[row["item_id"]] = row
    per_judge: dict[str, dict[str, str]] = {}
    for path in sorted((runs_dir / arm).glob("*.jsonl")):
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            parsed = row.get("parsed")
            if parsed:
                table[row["item_id"]] = norm_verdict(parsed.get("verdict"))
        per_judge[path.stem] = table
    judges = sorted(per_judge)
    items = [
        i
        for i in sorted(spec)
        if spec[i].get("disclosure") in strata and all(i in per_judge[j] for j in judges)
    ]
    rows = [[per_judge[j][i] for j in judges] for i in items]
    refs = [norm_verdict(spec[i].get("truth_verdict")) for i in items]
    return rows, refs, judges, items


def block(rows: list[list[str]], label: str) -> dict:
    return {
        "label_space": label,
        "n_items": len(rows),
        "n_judges": len(rows[0]) if rows else 0,
        "label_counts": dict(Counter(v for r in rows for v in r)),
        "observed_agreement": observed(rows),
        "chance_agreement": chance(rows),
        "fleiss_kappa": fleiss(rows),
        "max_attainable_kappa": max_attainable_kappa(rows),
        "kappa_share_of_attainable": (
            fleiss(rows) / max_attainable_kappa(rows)
            if max_attainable_kappa(rows) and abs(max_attainable_kappa(rows)) > 1e-9
            else float("nan")
        ),
        "gwet_ac1": gwet_ac1(rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    ap.add_argument("--ledger", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv")
    ap.add_argument(
        "--runs", type=Path, default=SUPPLEMENT / "comparability_instrument_runs_v2"
    )
    ap.add_argument(
        "--benchmark", type=Path, default=SUPPLEMENT / "comparability_instrument_benchmark_v2.jsonl"
    )
    ap.add_argument("--out", type=Path, default=SUPPLEMENT / "label_space_matched.json")
    args = ap.parse_args()

    cen_rows, cen_papers = census_rows(args.coding_dir, args.ledger)
    cen_bin = [[collapse(v) for v in r] for r in cen_rows]

    ins_rows, ins_refs, ins_judges, ins_items = instrument_rows(
        args.runs, args.benchmark, "five", {"full"}
    )
    ins_bin = [[collapse(v) for v in r] for r in ins_rows]

    # Restrict the constructed items to those whose reference is reachable in
    # the census, i.e. survives or undefined, so the two settings share both a
    # label space and a reference class set.
    keep = [i for i, ref in enumerate(ins_refs) if ref in {"survives", "undefined"}]
    ins_reachable = [ins_rows[i] for i in keep]
    ins_reachable_bin = [[collapse(v) for v in r] for r in ins_reachable]

    payload = {
        "schema_version": 1,
        "note": (
            "Every constructed row uses the five-coordinate arm on the "
            "fully-disclosed stratum, which is the cell the manuscript's "
            "kappa 0.74 comes from. Every census row uses the deployed three "
            "judges on the majority-eligible windows, which is the cell the "
            "kappa 0.06 comes from."
        ),
        "census": {
            "three_class": block(cen_rows, "survives|narrows|undefined"),
            "binary": block(cen_bin, "survives|not_survives"),
            "n_papers": len(set(cen_papers)),
            "narrows_reachability": {
                "n_items_any_judge_said_narrows": sum(1 for r in cen_rows if "narrows" in r),
                "share": sum(1 for r in cen_rows if "narrows" in r) / max(1, len(cen_rows)),
            },
        },
        "constructed_full_disclosure": {
            "judges": ins_judges,
            "three_class": block(ins_rows, "survives|narrows|undefined"),
            "binary": block(ins_bin, "survives|not_survives"),
            "reference_reachable_three_class": block(
                ins_reachable, "survives|undefined only"
            ),
            "reference_reachable_binary": block(ins_reachable_bin, "survives|not_survives"),
        },
    }

    gaps = {
        "three_class_kappa_gap": (
            payload["constructed_full_disclosure"]["three_class"]["fleiss_kappa"]
            - payload["census"]["three_class"]["fleiss_kappa"]
        ),
        "binary_kappa_gap": (
            payload["constructed_full_disclosure"]["binary"]["fleiss_kappa"]
            - payload["census"]["binary"]["fleiss_kappa"]
        ),
        "reachable_binary_kappa_gap": (
            payload["constructed_full_disclosure"]["reference_reachable_binary"]["fleiss_kappa"]
            - payload["census"]["binary"]["fleiss_kappa"]
        ),
        "observed_agreement_gap_binary": (
            payload["constructed_full_disclosure"]["binary"]["observed_agreement"]
            - payload["census"]["binary"]["observed_agreement"]
        ),
        "attainable_ceiling_census_binary": payload["census"]["binary"]["max_attainable_kappa"],
        "attainable_ceiling_constructed_binary": payload["constructed_full_disclosure"]["binary"][
            "max_attainable_kappa"
        ],
    }
    payload["gaps"] = gaps
    payload["reading"] = (
        "Matching the label space does not close the gap, and the census "
        "ceiling shows why the raw kappa contrast overstates it: the deployed "
        "judges' own marginals cap kappa at "
        f"{gaps['attainable_ceiling_census_binary']:.2f} on the binary space, "
        "so the census number should be read against that ceiling rather than "
        "against 1.0. The gap that survives matching is the quantity the "
        "disclosure account has to explain, and the manuscript now reports it "
        "instead of the unmatched one."
    )
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "census_three": {k: round(v, 3) for k, v in payload["census"]["three_class"].items()
                         if isinstance(v, float)},
        "census_binary": {k: round(v, 3) for k, v in payload["census"]["binary"].items()
                          if isinstance(v, float)},
        "constructed_three": {k: round(v, 3) for k, v in
                              payload["constructed_full_disclosure"]["three_class"].items()
                              if isinstance(v, float)},
        "constructed_binary": {k: round(v, 3) for k, v in
                               payload["constructed_full_disclosure"]["binary"].items()
                               if isinstance(v, float)},
        "gaps": {k: round(v, 3) for k, v in gaps.items() if v == v},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
