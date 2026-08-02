#!/usr/bin/env python3
"""Score the explicit-abstention verdict arm against the deployed arm.

The question is narrow and the design answers it directly: with a fourth
verdict value that says *the passage does not say*, and an instruction to prefer
it under uncertainty, do the same three judges on the same 704 windows

*   use it, and how often;
*   agree better than they did without it; and
*   agree better once the extra option is collapsed away, so the comparison is
    not just a relabelling of the same disagreement?

The third question is the one that identifies anything.  If judges simply move
mass from ``undefined`` into the new label, agreement can rise for arithmetic
reasons.  Collapsing the abstention label back onto ``undefined`` puts both arms
in the deployed label space and asks whether the *partition* of the items
changed.  Both are reported, with kappa read against the ceiling the judges'
own marginals impose.
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
# gpt-5-mini was run in two shards to raise throughput; the shards are
# disjoint by construction, since each skips ids already present in the other.
ABSTAIN = ["absA_gpt5mini", "absB_claudeopus46", "absC_gemini31pro"]
SHARDS = {"absA_gpt5mini": ["absA_gpt5mini", "absA2_gpt5mini"]}
NEW = "not_determinable_from_text"
BASE = {"survives", "narrows", "undefined"}


def norm(v) -> str:
    s = str(v or "").strip().lower()
    if s in BASE or s == NEW:
        return s
    if "determinable" in s or "does not say" in s:
        return NEW
    return "undefined"


def collapse(v: str) -> str:
    return "undefined" if v == NEW else v


def cluster_ci(items, stat, draws=3000, seed=20260731):
    groups = defaultdict(list)
    for key, payload in items:
        groups[key].append(payload)
    keys = sorted(groups)
    if len(keys) < 2:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        drawn = [x for k in pick for x in groups[k]]
        v = stat(drawn)
        if v == v:
            vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--abs-dir", type=Path, default=SUPPLEMENT / "abstention_verdict_runs")
    ap.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    ap.add_argument("--ledger", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv")
    ap.add_argument("--out", type=Path, default=SUPPLEMENT / "abstention_verdict_results.json")
    args = ap.parse_args()

    def read(directory: Path, names: list[str]) -> dict[str, dict[str, dict]]:
        out = {}
        for name in names:
            table = {}
            for shard in SHARDS.get(name, [name]) if directory == args.abs_dir else [name]:
                path = directory / f"{shard}.jsonl"
                if not path.exists():
                    continue
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        row = json.loads(line)
                        if row.get("parsed"):
                            table.setdefault(row["candidate_id"], row["parsed"])
            out[name] = table
        return out

    dep = read(args.coding_dir, DEPLOYED)
    abs_ = read(args.abs_dir, ABSTAIN)

    paper = {}
    for r in csv.DictReader(args.ledger.open(encoding="utf-8")):
        paper[r["candidate_id"]] = r["cite_key"]

    ids = sorted(
        cid
        for cid in paper
        if all(cid in dep[j] for j in DEPLOYED) and all(cid in abs_[j] for j in ABSTAIN)
    )
    if not ids:
        raise SystemExit("no items coded in both arms yet")

    abs_rows = [[norm(abs_[j][cid].get("verdict")) for j in ABSTAIN] for cid in ids]
    dep_rows = [[norm(dep[j][cid].get("verdict")) for j in DEPLOYED] for cid in ids]
    abs_coll = [[collapse(v) for v in r] for r in abs_rows]

    flat_abs = Counter(v for r in abs_rows for v in r)
    total = sum(flat_abs.values())
    per_judge_share = {
        j: sum(1 for cid in ids if norm(abs_[j][cid].get("verdict")) == NEW) / len(ids)
        for j in ABSTAIN
    }

    k_abs, k_dep, k_coll = fleiss(abs_rows), fleiss(dep_rows), fleiss(abs_coll)
    paired = [
        (paper[cid], (dep_rows[i], abs_coll[i], abs_rows[i])) for i, cid in enumerate(ids)
    ]

    def d_coll(rows):
        return fleiss([r[1] for r in rows]) - fleiss([r[0] for r in rows])

    def d_raw(rows):
        return fleiss([r[2] for r in rows]) - fleiss([r[0] for r in rows])

    ci_coll = cluster_ci(paired, d_coll)
    ci_raw = cluster_ci(paired, d_raw)
    ci_abs = cluster_ci([(paper[c], abs_rows[i]) for i, c in enumerate(ids)], fleiss)

    dep_share_survives = sum(1 for r in dep_rows for v in r if v == "survives") / total
    abs_share_survives = sum(1 for r in abs_rows for v in r if v == "survives") / total

    # Where did the abstention mass come from?
    moved = Counter()
    for i, cid in enumerate(ids):
        for a, d in zip(ABSTAIN, DEPLOYED):
            new = norm(abs_[a][cid].get("verdict"))
            old = norm(dep[d][cid].get("verdict"))
            if new == NEW:
                moved[old] += 1

    payload = {
        "schema_version": 1,
        "design_note": (
            "The abstention codebook is the deployed codebook with a fourth "
            "verdict value and an instruction to prefer it under uncertainty, "
            "and nothing else changed. Same judges, same windows, same context "
            "width, same item order."
        ),
        "n_items": len(ids),
        "n_papers": len(set(paper[c] for c in ids)),
        "judges_abstention": ABSTAIN,
        "judges_deployed": DEPLOYED,
        "label_distribution_abstention": dict(flat_abs),
        "label_distribution_deployed": dict(Counter(v for r in dep_rows for v in r)),
        "abstention_share": flat_abs.get(NEW, 0) / total,
        "abstention_share_by_judge": per_judge_share,
        "abstention_share_min": min(per_judge_share.values()),
        "abstention_share_max": max(per_judge_share.values()),
        "abstention_mass_came_from": dict(moved),
        "fleiss_kappa_deployed_arm": k_dep,
        "fleiss_kappa_four_class": k_abs,
        "fleiss_kappa_four_class_ci95": list(ci_abs),
        "fleiss_kappa_collapsed_to_deployed_space": k_coll,
        "kappa_difference": k_coll - k_dep,
        "kappa_difference_ci95": list(ci_coll),
        "kappa_difference_four_class_ci95": list(ci_raw),
        "kappa_difference_four_class": k_abs - k_dep,
        "max_attainable_kappa_four_class": max_attainable_kappa(abs_rows),
        "max_attainable_kappa_deployed": max_attainable_kappa(dep_rows),
        "max_attainable_kappa_collapsed": max_attainable_kappa(abs_coll),
        "observed_deployed": observed(dep_rows),
        "observed_four_class": observed(abs_rows),
        "observed_collapsed": observed(abs_coll),
        "gwet_ac1_four_class": gwet_ac1(abs_rows),
        "survives_share_deployed": dep_share_survives,
        "survives_share_abstention": abs_share_survives,
        "survives_share_change": abs_share_survives - dep_share_survives,
        "reading": (
            "If judges use the abstention label heavily and agreement rises "
            "once it is collapsed away, the deployed instrument was forcing a "
            "commitment the passage did not support, and the census result is "
            "partly a prompt-design finding. If they use it and agreement does "
            "not rise, the disagreement is about which passages are silent, "
            "not about whether silence can be reported."
        ),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "n_items": payload["n_items"],
        "abstention_share": round(payload["abstention_share"], 3),
        "by_judge": {k: round(v, 3) for k, v in per_judge_share.items()},
        "k_deployed": round(k_dep, 3),
        "k_four_class": round(k_abs, 3),
        "k_collapsed": round(k_coll, 3),
        "k_diff_collapsed": round(k_coll - k_dep, 3),
        "k_diff_ci": [round(x, 3) for x in ci_coll],
        "kmax_four_class": round(payload["max_attainable_kappa_four_class"], 3),
        "survives_change": round(payload["survives_share_change"], 3),
        "mass_from": payload["abstention_mass_came_from"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
