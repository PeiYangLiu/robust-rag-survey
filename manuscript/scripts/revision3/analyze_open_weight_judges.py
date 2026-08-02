#!/usr/bin/env python3
"""Fold the open-weight judges into the paper's three headline analyses.

The open checkpoints answer byte-identical prompts to the API judges, under
greedy decoding in one harness, so they can be pooled with them rather than
reported beside them.  Three things come out:

**A wider sigma_r.**  The submitted estimate uses six judges and its interval
spans a factor of four, which is the reviewer's objection to using it for a
power recommendation.  Adding the open judges roughly triples the pool on the
constructed benchmark, where the reference verdict is fixed before any judge
sees the item, so the variance component has a reference that is not a majority
of the judges being measured.

**A generalisation test for the negative result.**  If verdict agreement is low
among proprietary API judges but high among open ones, the census finding is a
property of a model class. We therefore report inter-judge agreement within the
API pool, within the open pool, and across the two, on identical items.

**A capability gradient.**  The open pool spans roughly 8B to 72B parameters
under one harness, which the API tier control cannot supply, so we can ask
whether verdict agreement improves with scale where provenance agreement does.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
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

API_CENSUS = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
VERDICTS = {"survives", "narrows", "undefined"}
NEW = "not_determinable_from_text"

# approximate parameter counts, for the capability gradient only
PARAMS_B = {
    "qwen3-8b": 8, "qwen3-14b": 14, "qwen3-32b": 32, "qwen25-72b": 72,
    "phi4": 14, "mistral-small-24b": 24, "olmo2-13b": 13,
    "ds-distill-qwen-32b": 32, "glm4-9b": 9, "internlm3-8b": 8,
}
DEVELOPER = {
    "qwen3-8b": "Alibaba", "qwen3-14b": "Alibaba", "qwen3-32b": "Alibaba",
    "qwen25-72b": "Alibaba", "phi4": "Microsoft",
    "mistral-small-24b": "Mistral", "olmo2-13b": "AI2",
    "ds-distill-qwen-32b": "DeepSeek", "glm4-9b": "Zhipu",
    "internlm3-8b": "Shanghai AI Lab",
}


def norm_verdict(v, allow_abstain: bool = False) -> str:
    s = str(v or "").strip().lower()
    if s in VERDICTS:
        return s
    if allow_abstain and ("determinable" in s or "does not say" in s):
        return NEW
    return "undefined"


def cluster_ci(items, stat, draws=2000, seed=20260731):
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


def load_open(
    root: Path, task: str, min_coverage: float = 0.5, n_expected: int | None = None
) -> tuple[dict[str, dict[str, dict]], dict[str, float]]:
    """judge -> id -> parsed, plus the parse rate of every judge considered.

    A judge whose output cannot be parsed on most items is not a judge on this
    task under the deployed generation budget, and including it would shrink the
    common item set for everyone else. We therefore drop judges below a declared
    coverage floor and report which, rather than letting one truncated
    reasoning model decide the sample size.
    """
    out: dict[str, dict[str, dict]] = {}
    coverage: dict[str, float] = {}
    if not root.exists():
        return out, coverage
    for judge_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        path = judge_dir / f"{task}.jsonl"
        if not path.exists():
            continue
        table, n_rows = {}, 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            n_rows += 1
            row = json.loads(line)
            if not row.get("parsed"):
                continue
            key = row.get("candidate_id") or row.get("item_id")
            table[key] = row["parsed"]
        denom = n_expected or n_rows or 1
        rate = len(table) / denom
        coverage[judge_dir.name] = rate
        if table and rate >= min_coverage:
            out[judge_dir.name] = table
    return out, coverage


def load_api_census(coding_dir: Path) -> dict[str, dict[str, dict]]:
    out = {}
    for name in API_CENSUS:
        path = coding_dir / f"{name}.jsonl"
        if not path.exists():
            continue
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row["parsed"]
        out[name] = table
    return out


def load_api_instrument(runs: Path, pack_runs: Path | None = None) -> dict[str, dict[str, dict]]:
    """API judges on the constructed benchmark.

    Two sources, both answering the same items: the original six-judge run under
    the five-coordinate arm, and the later pack-driven run that widens the pool.
    The pack run uses the rendered prompts the open-weight judges consume, so
    every judge in the widened pool answered byte-identical text.
    """
    out = {}
    for directory in (runs / "five", pack_runs):
        if directory is None or not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            table = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("parsed"):
                        key = row.get("item_id") or row.get("candidate_id")
                        table[key] = row["parsed"]
            if table:
                out[path.stem] = table
    return out


def sigma_r_from_accuracy(acc: list[float]) -> float:
    """Reviewer logit SD, matching scripts/sigma_r_core.py's estimand."""
    import math

    eps = 1e-3
    logits = [
        math.log(min(max(a, eps), 1 - eps) / (1 - min(max(a, eps), 1 - eps)))
        for a in acc
    ]
    if len(logits) < 2:
        return float("nan")
    mu = sum(logits) / len(logits)
    return (sum((x - mu) ** 2 for x in logits) / (len(logits) - 1)) ** 0.5


def block(rows, label):
    return {
        "label": label,
        "n_items": len(rows),
        "n_judges": len(rows[0]) if rows else 0,
        "observed": observed(rows),
        "fleiss_kappa": fleiss(rows),
        "max_attainable_kappa": max_attainable_kappa(rows),
        "gwet_ac1": gwet_ac1(rows),
        "label_distribution": dict(Counter(v for r in rows for v in r)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--open-root", type=Path, default=SUPPLEMENT / "open_weight_judges")
    ap.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    ap.add_argument(
        "--instrument-runs", type=Path,
        default=SUPPLEMENT / "comparability_instrument_runs_v2",
    )
    ap.add_argument(
        "--benchmark", type=Path,
        default=SUPPLEMENT / "comparability_instrument_benchmark_v2.jsonl",
    )
    ap.add_argument("--api-pack-runs", type=Path,
                    default=SUPPLEMENT / "api_pack_runs" / "instrument")
    ap.add_argument("--ledger", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv")
    ap.add_argument("--min-coverage", type=float, default=0.5,
                    help="declared parse-rate floor for a judge to enter a pool")
    ap.add_argument("--out", type=Path, default=SUPPLEMENT / "open_weight_judge_results.json")
    args = ap.parse_args()

    spec = {}
    for line in args.benchmark.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            spec[row["item_id"]] = row

    paper_of = {
        r["candidate_id"]: r["cite_key"]
        for r in csv.DictReader(args.ledger.open(encoding="utf-8"))
    }

    open_inst, cov_inst = load_open(args.open_root, "instrument", args.min_coverage, 432)
    open_cens, cov_cens = load_open(args.open_root, "census", args.min_coverage, 704)
    open_abst, cov_abst = load_open(args.open_root, "abstention", args.min_coverage, 704)
    api_inst = load_api_instrument(args.instrument_runs, args.api_pack_runs)
    api_cens = load_api_census(args.coding_dir)

    payload: dict = {
        "schema_version": 1,
        "open_judges_found": sorted(open_inst) or sorted(open_cens),
        "n_open_judges": len(set(open_inst) | set(open_cens)),
        "developers": {j: DEVELOPER.get(j, "unknown") for j in sorted(set(open_inst) | set(open_cens))},
        "min_coverage": args.min_coverage,
        "parse_coverage": {"instrument": cov_inst, "census": cov_cens, "abstention": cov_abst},
        "excluded_below_coverage": {
            task: sorted(k for k, v in cov.items() if v < args.min_coverage)
            for task, cov in (("instrument", cov_inst), ("census", cov_cens),
                              ("abstention", cov_abst))
        },
    }

    # ------------------------------------------------------------------
    # 1. sigma_r on the constructed benchmark, API + open pooled
    # ------------------------------------------------------------------
    if open_inst or api_inst:
        non_degenerate = [
            i for i, s in spec.items() if s.get("disclosure") != "partial_forcing"
        ]
        acc_by_judge, pools = {}, {}
        for pool_name, tables in (("api", api_inst), ("open", open_inst)):
            for judge, table in tables.items():
                hit = tot = 0
                for i in non_degenerate:
                    if i not in table:
                        continue
                    tot += 1
                    hit += int(
                        norm_verdict(table[i].get("verdict"))
                        == norm_verdict(spec[i]["truth_verdict"])
                    )
                if tot >= 50:
                    acc_by_judge[judge] = hit / tot
                    pools[judge] = pool_name
        api_acc = [a for j, a in acc_by_judge.items() if pools[j] == "api"]
        open_acc = [a for j, a in acc_by_judge.items() if pools[j] == "open"]
        all_acc = list(acc_by_judge.values())

        rng = random.Random(20260731)
        names = sorted(acc_by_judge)
        boots = []
        for _ in range(4000):
            pick = [names[rng.randrange(len(names))] for _ in names]
            v = sigma_r_from_accuracy([acc_by_judge[n] for n in pick])
            if v == v:
                boots.append(v)
        boots.sort()
        payload["sigma_r"] = {
            "reference": "constructed benchmark truth verdict, fixed before any judge sees the item",
            "n_judges_api": len(api_acc),
            "n_judges_open": len(open_acc),
            "n_judges_total": len(all_acc),
            "accuracy_by_judge": acc_by_judge,
            "pool_by_judge": pools,
            "sigma_r_api_only": sigma_r_from_accuracy(api_acc),
            "sigma_r_open_only": sigma_r_from_accuracy(open_acc),
            "sigma_r_pooled": sigma_r_from_accuracy(all_acc),
            "sigma_r_pooled_ci95": (
                [boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]]
                if boots else []
            ),
            "ci_width_ratio_pooled": (
                boots[int(0.975 * len(boots))] / boots[int(0.025 * len(boots))]
                if boots and boots[int(0.025 * len(boots))] > 0 else float("nan")
            ),
        }

    # ------------------------------------------------------------------
    # 2. verdict agreement within and across pools, on the census
    # ------------------------------------------------------------------
    if open_cens:
        common = set.intersection(
            *( [set(t) for t in open_cens.values()] + [set(t) for t in api_cens.values()] )
        )
        common &= set(paper_of)
        ids = sorted(common)
        open_names = sorted(open_cens)
        api_names = sorted(api_cens)

        def rows_for(names, tables):
            return [[norm_verdict(tables[j][c].get("verdict")) for j in names] for c in ids]

        open_rows = rows_for(open_names, open_cens)
        api_rows = rows_for(api_names, api_cens)
        merged_tables = {**api_cens, **open_cens}
        all_names = api_names + open_names
        all_rows = [[norm_verdict(merged_tables[j][c].get("verdict")) for j in all_names] for c in ids]

        payload["census_verdict"] = {
            "n_common_items": len(ids),
            "n_papers": len({paper_of[c] for c in ids}),
            "api_pool": block(api_rows, "API judges only"),
            "open_pool": block(open_rows, "open-weight judges only"),
            "pooled": block(all_rows, "API and open-weight judges pooled"),
            "api_kappa_ci95": list(
                cluster_ci([(paper_of[c], r) for c, r in zip(ids, api_rows)], fleiss)
            ),
            "open_kappa_ci95": list(
                cluster_ci([(paper_of[c], r) for c, r in zip(ids, open_rows)], fleiss)
            ),
        }

        # provenance is not asked in the census codebook pass, so the
        # generalisation check uses the coordinate labels the codebook does ask
        for coord in ("c1", "c2", "c4", "c5"):
            payload["census_verdict"][f"open_{coord}_kappa"] = fleiss(
                [[str(open_cens[j][c].get(coord, "not_determinable")).strip().lower()
                  for j in open_names] for c in ids]
            )

        # capability gradient: per-judge share calling a comparison sound
        payload["capability_gradient"] = {
            j: {
                "params_b": PARAMS_B.get(j),
                "developer": DEVELOPER.get(j),
                "survives_share": sum(
                    1 for c in ids if norm_verdict(open_cens[j][c].get("verdict")) == "survives"
                ) / max(1, len(ids)),
                "not_determinable_coord_share": sum(
                    1
                    for c in ids
                    for k in ("c1", "c2", "c4", "c5")
                    if str(open_cens[j][c].get(k, "")).strip().lower() == "not_determinable"
                ) / max(1, 4 * len(ids)),
            }
            for j in open_names
        }

    # ------------------------------------------------------------------
    # 3. abstention arm, open judges
    # ------------------------------------------------------------------
    if open_abst and open_cens:
        names = sorted(set(open_abst) & set(open_cens))
        ids = sorted(
            set.intersection(*([set(open_abst[j]) for j in names] + [set(open_cens[j]) for j in names]))
            & set(paper_of)
        )
        if names and ids:
            abst_rows = [[norm_verdict(open_abst[j][c].get("verdict"), True) for j in names] for c in ids]
            dep_rows = [[norm_verdict(open_cens[j][c].get("verdict")) for j in names] for c in ids]
            coll_rows = [[("undefined" if v == NEW else v) for v in r] for r in abst_rows]
            total = sum(len(r) for r in abst_rows)
            payload["abstention_open"] = {
                "n_items": len(ids),
                "judges": names,
                "abstention_share": sum(1 for r in abst_rows for v in r if v == NEW) / max(1, total),
                "deployed": block(dep_rows, "open judges, deployed codebook"),
                "four_class": block(abst_rows, "open judges, abstention codebook"),
                "collapsed": block(coll_rows, "open judges, collapsed to deployed space"),
                "kappa_difference_collapsed_minus_deployed": fleiss(coll_rows) - fleiss(dep_rows),
            }

    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "capability_gradient"},
                     indent=2, sort_keys=True)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
