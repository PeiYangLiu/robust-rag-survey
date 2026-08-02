#!/usr/bin/env python3
"""Estimate the between-reviewer heterogeneity ``sigma_r`` from several
genuinely crossed reviewer-by-item designs.

Why this script exists
----------------------
The previous version of the paper anchored ``sigma_r`` on a single design with
three coders and eighty claims.  A variance component estimated from three
raters has two degrees of freedom, and the bootstrap interval was
``[0.00, 0.53]``: it contained both "reviewers are interchangeable" and
"reviewers differ a lot".  Since the simulated type-I inflation is zero at
``sigma_r = 0``, that interval could not distinguish "the status-quo analysis
is broken" from "the status-quo analysis is fine".

The fix is to stop relying on one small design.  This script applies one
estimator to every crossed design we can obtain:

*   ``census_verdict_panel`` -- the nine-judge cross-paper census, the
    adjudication task this paper is actually about, scored against a
    leave-one-out majority of the other eight judges.
*   ``instrument_benchmark`` -- the constructed comparability benchmark,
    where the reference verdict is fixed when the item is written and is
    therefore independent of every reviewer.
*   ``human_<corpus>``    -- public human annotation corpora that release
    per-annotator labels with stable identifiers and cross annotators with
    items (prepared under ``supplement/sigma_anchors/``).
*   ``model_panel``       -- the controlled benchmark of this paper, which is
    itself a fully crossed reviewer-by-item design: every model answers every
    one of the 600 items and the reference is the unique minimiser of a
    displayed loss rule, i.e. a reference that no reviewer supplied.

Estimator
---------
For reviewer ``j`` with accuracy ``a_j`` against the reference over ``n_j``
items, let ``l_j = logit(a_j)``.  ``Var(l_j)`` overstates the between-reviewer
variance because each ``a_j`` is itself measured with binomial error, whose
delta-method variance is ``1 / (n_j a_j (1 - a_j))``.  The moment estimator
subtracts that component and floors the result at zero.  This is the estimator
the paper already used; keeping it fixed means the anchors are comparable to
the previously published value.

Uncertainty is a nonparametric bootstrap that resamples **items** (clustered by
source where a cluster is available) and, separately, **reviewers**, since the
reviewer dimension is the one with few units in the small designs.

A parametric self-check simulates from the fitted two-way logit model and
re-estimates, so the reader can see the estimator's bias and spread at the
realised design size rather than assuming it is unbiased.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from sigma_r_core import (
    moment_sigma_from_lists,
    parametric_bootstrap,
    percentile_interval,
    reviewer_bootstrap_dense,
    summarise_bootstrap,
)

REPO = Path(__file__).resolve().parents[2]
SUPPLEMENT = REPO / "manuscript" / "supplement"
BOOTSTRAP_DRAWS = 4_000
SEED = 2026072809


def logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def moment_sigma_r(
    correct: Sequence[Sequence[int]],
) -> tuple[float, float, list[float], list[int]]:
    """Delegate to shared implementation."""
    return moment_sigma_from_lists(correct)


def matrix_from_long(
    rows: Sequence[Mapping[str, str]],
) -> tuple[list[str], list[str], dict[tuple[str, str], int], dict[str, str]]:
    reviewers = sorted({r["annotator_id"] for r in rows})
    items = sorted({r["item_id"] for r in rows})
    cell: dict[tuple[str, str], int] = {}
    cluster: dict[str, str] = {}
    for r in rows:
        cell[(r["annotator_id"], r["item_id"])] = int(
            str(r["label"]).strip() == str(r["reference_label"]).strip()
        )
        cluster[r["item_id"]] = r.get("cluster_id") or r["item_id"]
    return reviewers, items, cell, cluster


def estimate(
    reviewers: Sequence[str],
    items: Sequence[str],
    cell: Mapping[tuple[str, str], int],
    cluster: Mapping[str, str],
    draws: int,
    seed: int,
) -> dict[str, object]:
    per_reviewer_data = [[cell[(j, i)] for i in items if (j, i) in cell] for j in reviewers]
    point, mu_logit, accuracies, counts = moment_sigma_r(per_reviewer_data)

    # 1. Reviewer bootstrap (headline interval)
    rev_boot = reviewer_bootstrap_dense(per_reviewer_data, draws, seed)
    rev_summary = summarise_bootstrap(rev_boot, point, "reviewers")

    # 2. Item/cluster bootstrap (supplementary)
    by_cluster: dict[str, list[str]] = defaultdict(list)
    for item in items:
        by_cluster[cluster.get(item, item)].append(item)
    clusters = sorted(by_cluster)

    rng = random.Random(seed + 2)
    item_boot = []
    for _ in range(draws):
        picked = [rng.choice(clusters) for _ in clusters]
        subset = [i for c in picked for i in by_cluster[c]]
        per_reviewer = [[cell[(j, i)] for i in subset if (j, i) in cell] for j in reviewers]
        item_boot.append(moment_sigma_from_lists(per_reviewer)[0])
    item_boot_arr = np.array(item_boot)
    item_summary = summarise_bootstrap(item_boot_arr, point, "items")

    # 3. Parametric bootstrap
    counts_arr = np.array(counts, dtype=np.int64)
    para_boot = parametric_bootstrap(
        point, mu_logit, counts_arr, min(draws, 400), seed + 1
    )
    para_summary = summarise_bootstrap(para_boot, point, "parametric")

    n_items_per_reviewer = sorted(counts)

    # Legacy item bootstrap interval (percentile) preserved for backward compat
    item_ci = percentile_interval(item_boot_arr)

    return {
        "sigma_r": point,
        "mu_logit": mu_logit,
        "n_reviewers": len(reviewers),
        "n_items": len(items),
        "n_judgments": len(cell),
        "reviewer_accuracies": sorted(round(a, 4) for a in accuracies),
        "min_items_per_reviewer": n_items_per_reviewer[0] if n_items_per_reviewer else 0,
        "median_items_per_reviewer": (
            n_items_per_reviewer[len(n_items_per_reviewer) // 2]
            if n_items_per_reviewer
            else 0
        ),
        "crossing_density": (
            len(cell) / (len(reviewers) * len(items)) if reviewers and items else 0.0
        ),
        # New unambiguous keys
        **rev_summary,
        **para_summary,
        **item_summary,
        # Legacy key preserved
        "bootstrap_items_ci95": item_ci,
        "bootstrap_items_ci50": [
            float(np.quantile(item_boot_arr, 0.25)),
            float(np.quantile(item_boot_arr, 0.75)),
        ],
        "bootstrap_reviewers_ci95": rev_summary["boot_reviewers_ci95"],
        "bootstrap_draws": draws,
    }


def parametric_check(
    sigma_r: float,
    n_reviewers: int,
    n_items: int,
    base_accuracy: float,
    sigma_item: float,
    replicates: int,
    seed: int,
) -> dict[str, float]:
    """Simulate from the fitted two-way logit model and re-estimate sigma_r."""
    mu = logit(min(max(base_accuracy, 1e-4), 1 - 1e-4))
    counts = np.full(n_reviewers, n_items, dtype=np.int64)
    arr = parametric_bootstrap(
        sigma_r, mu, counts, replicates, seed, sigma_item=sigma_item
    )
    return {
        "truth": sigma_r,
        "mean_estimate": float(arr.mean()),
        "bias": float(arr.mean() - sigma_r),
        "sd_estimate": float(arr.std(ddof=1)),
        "q025": float(np.quantile(arr, 0.025)),
        "q975": float(np.quantile(arr, 0.975)),
        "share_exactly_zero": float((arr <= 0).mean()),
        "replicates": replicates,
    }


def load_census_panel(
    coding_dir: Path, candidates: Path, min_coverage: float = 0.95,
    pool_path: Path | None = None,
) -> list[dict[str, str]]:
    """Reviewer = census judge; item = frame window; reference = leave-one-out
    majority of the *other* judges, so no judge is graded against a reference
    containing its own vote.

    The judge set is the tier-control pool, read from
    ``cross_paper_tier_control.json`` when it is available, so that this anchor
    and the crossed pool analysed in the census section are the *same* design.
    An earlier version took every coding file that met the coverage threshold,
    which silently added a tenth judge and changed the majority-eligible item
    population; the two sections then reported different reviewer and item
    counts for what the text described as one pool.
    """
    ids = set()
    for line in candidates.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(json.loads(line)["candidate_id"])
    allowed: set[str] | None = None
    if pool_path is not None and pool_path.exists():
        pool = json.loads(pool_path.read_text(encoding="utf-8")).get("pool", {})
        if pool.get("judges"):
            allowed = set(pool["judges"])
    tables: dict[str, dict[str, dict]] = {}
    for path in sorted(coding_dir.glob("*.jsonl")):
        if path.stem.startswith("smoke"):
            continue
        if allowed is not None and path.stem not in allowed:
            continue
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed") and row["candidate_id"] in ids:
                table[row["candidate_id"]] = row
        if len(table) / max(len(ids), 1) >= min_coverage:
            tables[path.stem] = table
    if len(tables) < 3:
        return []
    judges = sorted(tables)
    common = set.intersection(*(set(t) for t in tables.values()))
    eligible = [
        cid
        for cid in sorted(common)
        if sum(bool(tables[j][cid]["parsed"].get("eligible")) for j in judges) * 2
        > len(judges)
    ]
    out: list[dict[str, str]] = []
    for cid in eligible:
        votes = {
            j: str(tables[j][cid]["parsed"].get("verdict", "")).lower() or "missing"
            for j in judges
        }
        for j in judges:
            others = Counter(v for k, v in votes.items() if k != j)
            top, n_top = others.most_common(1)[0]
            if sum(1 for _, v in others.items() if v == n_top) > 1:
                continue  # no leave-one-out majority; the item is undefined for j
            out.append(
                {
                    "annotator_id": j,
                    "item_id": cid,
                    "cluster_id": tables[j][cid].get("cite_key") or cid,
                    "label": votes[j],
                    "reference_label": top,
                }
            )
    return out


def load_instrument_panel(runs_dir: Path, items_path: Path, arm: str = "five") -> list[dict[str, str]]:
    """Reviewer = judge; item = constructed comparability item; reference = the
    verdict fixed when the item was written, which no reviewer supplies."""
    if not items_path.exists():
        return []
    truth = {}
    for line in items_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            truth[row["item_id"]] = row["truth_verdict"]
    arm_dir = runs_dir / arm
    if not arm_dir.exists():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(arm_dir.glob("*.jsonl")):
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("parsed"):
                continue
            iid = record["item_id"]
            if iid not in truth:
                continue
            rows.append(
                {
                    "annotator_id": path.stem,
                    "item_id": iid,
                    "cluster_id": iid,
                    "label": str(record["parsed"].get("verdict", "")).lower(),
                    "reference_label": truth[iid],
                }
            )
        if len(rows) >= 0.9 * len(truth):
            out.extend(rows)
    return out


def load_diagnostic(path: Path) -> list[dict[str, str]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    out = []
    for row in rows:
        reference = row["human_adjudicated_verdict"].strip()
        for column in ("coder_A_verdict", "coder_B_verdict", "coder_C_verdict"):
            out.append(
                {
                    "annotator_id": column.replace("_verdict", ""),
                    "item_id": row["annotation_id"],
                    "cluster_id": row.get("source_key") or row["annotation_id"],
                    "label": row[column].strip(),
                    "reference_label": reference,
                }
            )
    return out


def load_model_panel(
    directories: Sequence[Path], arm: str, paraphrase: str | None
) -> list[dict[str, str]]:
    """Reviewer = model checkpoint; item = benchmark item; reference = target."""
    out: list[dict[str, str]] = []
    seen_models: set[str] = set()
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            if path.name.endswith(".tok24.jsonl"):
                continue
            model = None
            records = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record["arm"] != arm:
                    continue
                if paraphrase and record["paraphrase"] != paraphrase:
                    continue
                model = record["model"]
                records.append(record)
            if not model or model in seen_models or not records:
                continue
            seen_models.add(model)
            for record in records:
                reviewer = model if paraphrase else f"{model}::{record['paraphrase']}"
                out.append(
                    {
                        "annotator_id": reviewer,
                        "item_id": str(record["item_id"]),
                        "cluster_id": str(record["pair_id"]),
                        "label": str(record["parsed_decision"]),
                        "reference_label": str(record["target_decision"]),
                    }
                )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--census-coding", type=Path, default=SUPPLEMENT / "cross_paper_coding"
    )
    parser.add_argument(
        "--census-candidates",
        type=Path,
        default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl",
    )
    parser.add_argument(
        "--instrument-runs", type=Path, default=SUPPLEMENT / "comparability_instrument_runs_v2"
    )
    parser.add_argument(
        "--instrument-items",
        type=Path,
        default=SUPPLEMENT / "comparability_instrument_benchmark_v2.jsonl",
    )
    parser.add_argument(
        "--human-anchor-dir", type=Path, default=SUPPLEMENT / "sigma_anchors"
    )
    parser.add_argument(
        "--model-raw",
        type=Path,
        nargs="+",
        default=[
            SUPPLEMENT / "controlled_model_judge_raw_v3",
            SUPPLEMENT / "controlled_model_judge_raw_v2",
        ],
    )
    parser.add_argument("--panel-arm", default="ablated")
    parser.add_argument("--draws", type=int, default=BOOTSTRAP_DRAWS)
    parser.add_argument("--paraphrase-panel", action="store_true")
    parser.add_argument("--include-human-corpora", action="store_true")
    parser.add_argument("--paraphrase-draws", type=int, default=200)
    parser.add_argument(
        "--output", type=Path, default=SUPPLEMENT / "sigma_r_multi_anchor.json"
    )
    args = parser.parse_args()

    anchors: dict[str, dict[str, object]] = {}

    # The nine-judge census panel: the adjudication task of this paper, on a
    # design that is crossed by construction.
    rows = load_census_panel(
        args.census_coding, args.census_candidates,
        pool_path=SUPPLEMENT / "cross_paper_tier_control.json")
    if rows:
        reviewers, items, cell, cluster = matrix_from_long(rows)
        entry = estimate(reviewers, items, cell, cluster, args.draws, SEED)
        entry["design"] = (
            "fully crossed: every judge codes every frame window; reference is a "
            "leave-one-out majority of the other judges"
        )
        entry["reviewer_kind"] = "model"
        entry["task"] = "cross-paper comparability verdict on published text"
        entry["reference_source"] = "leave-one-out majority of the other judges"
        entry["estimand_caveat"] = (
            "The reference here is a leave-one-out majority of judges who agree "
            "on this task at kappa 0.06, so it is close to noise, and the same "
            "section shows the judges hold different thresholds rather than "
            "differing in ability around a shared one. This estimate therefore "
            "mixes threshold dispersion into what the simulation treats as "
            "ability variance. The constructed-benchmark anchor, whose reference "
            "is fixed before any judge sees the item, is the one to read as an "
            "ability estimate."
        )
        anchors["census_verdict_panel"] = entry

    # The constructed benchmark: the same task with a reference that is fixed
    # before any reviewer sees the item.
    rows = load_instrument_panel(args.instrument_runs, args.instrument_items)
    if rows:
        reviewers, items, cell, cluster = matrix_from_long(rows)
        entry = estimate(reviewers, items, cell, cluster, args.draws, SEED)
        entry["design"] = (
            "fully crossed: every judge answers every constructed item; the "
            "reference verdict is fixed when the item is written"
        )
        entry["reviewer_kind"] = "model"
        entry["task"] = "cross-paper comparability verdict, constructed reference"
        entry["reference_source"] = "verdict fixed by construction"
        anchors["instrument_benchmark"] = entry

    manifest_path = args.human_anchor_dir / "manifest.json"
    # The public human corpora have up to 1.6 M judgments; they are estimated by
    # the vectorised ``estimate_sigma_r_human_anchors.py`` and merged at table
    # build time, so this loop is off unless explicitly requested.
    if args.include_human_corpora and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in manifest:
            slug = record["dataset"]
            long_path = args.human_anchor_dir / f"{slug}_long.csv"
            if not long_path.exists():
                continue
            rows = list(csv.DictReader(long_path.open(encoding="utf-8")))
            if not rows:
                continue
            reviewers, items, cell, cluster = matrix_from_long(rows)
            if len(reviewers) < 3 or len(items) < 50:
                continue
            entry = estimate(reviewers, items, cell, cluster, min(args.draws, 1000), SEED)
            entry["design"] = record.get("crossing", "")
            entry["reviewer_kind"] = "human"
            entry["task"] = record.get("task_type", "")
            entry["source_url"] = record.get("source_url", "")
            entry["reference_source"] = record.get("reference_source", "")
            anchors[f"human_{slug}"] = entry

    rows = load_model_panel(args.model_raw, args.panel_arm, "p1")
    if rows:
        reviewers, items, cell, cluster = matrix_from_long(rows)
        entry = estimate(reviewers, items, cell, cluster, args.draws, SEED)
        entry["design"] = (
            f"fully crossed: every model answers every benchmark item "
            f"(arm={args.panel_arm}, paraphrase=p1)"
        )
        entry["reviewer_kind"] = "model"
        entry["task"] = "deployment decision under a displayed loss rule"
        entry["reference_source"] = "deterministic minimum of displayed losses"
        anchors["model_panel_checkpoints"] = entry

    rows = load_model_panel(args.model_raw, args.panel_arm, None) if args.paraphrase_panel else []
    if rows:
        reviewers, items, cell, cluster = matrix_from_long(rows)
        entry = estimate(reviewers, items, cell, cluster, args.paraphrase_draws, SEED)
        entry["design"] = (
            f"fully crossed, reviewer = checkpoint x paraphrase (arm={args.panel_arm})"
        )
        entry["reviewer_kind"] = "model"
        entry["task"] = "deployment decision under a displayed loss rule"
        entry["reference_source"] = "deterministic minimum of displayed losses"
        anchors["model_panel_checkpoint_by_paraphrase"] = entry

    # Parametric self-check at each anchor's realised design size.
    for name, entry in anchors.items():
        accuracies = entry["reviewer_accuracies"]
        base = sum(accuracies) / len(accuracies) if accuracies else 0.75
        entry["parametric_check"] = parametric_check(
            float(entry["sigma_r"]),
            int(entry["n_reviewers"]),
            int(entry["median_items_per_reviewer"]) or int(entry["n_items"]),
            base,
            0.35,
            400,
            SEED + 1,
        )

    values = [
        float(entry["sigma_r"]) for entry in anchors.values() if entry["n_reviewers"] >= 3
    ]
    human_values = [
        float(entry["sigma_r"])
        for entry in anchors.values()
        if entry.get("reviewer_kind") == "human"
    ]
    payload = {
        "schema_version": "sigma-r-multi-anchor-v1",
        "estimator": "moment estimator on logit accuracies, binomial component removed",
        "anchors": anchors,
        "summary": {
            "n_anchors": len(anchors),
            "sigma_r_min": min(values) if values else None,
            "sigma_r_max": max(values) if values else None,
            "sigma_r_human_min": min(human_values) if human_values else None,
            "sigma_r_human_max": max(human_values) if human_values else None,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"{'anchor':<44}{'kind':<7}{'rev':>5}{'items':>7}{'sigma_r':>9}  95% CI (reviewers)")
    for name, entry in anchors.items():
        ci = entry["boot_reviewers_ci95"]
        print(
            f"{name:<44}{str(entry['reviewer_kind']):<7}{entry['n_reviewers']:>5}"
            f"{entry['n_items']:>7}{float(entry['sigma_r']):>9.3f}  "
            f"[{ci[0]:.3f}, {ci[1]:.3f}]"
        )
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
