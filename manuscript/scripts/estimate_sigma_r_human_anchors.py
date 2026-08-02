#!/usr/bin/env python3
"""Estimate ``sigma_r`` on the prepared public human annotation corpora.

These corpora are large (up to 1.6 M judgments), so the estimator is
vectorised: correctness is stored as a sparse (reviewer, item) COO triple and
bootstraps are done via numpy bincount on per-reviewer sufficient statistics.

Three bootstrap procedures are computed via ``sigma_r_core``:
  1. Reviewer bootstrap (headline interval) — resample reviewers.
  2. Parametric bootstrap — simulate from fitted logit model.
  3. Item bootstrap (supplementary) — resample items.

Reviewers with fewer than ``--min-items`` judgments are dropped, because a
logit accuracy computed from a handful of items contributes almost pure
sampling noise to the between-reviewer variance.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from sigma_r_core import (
    item_bootstrap_vectorised,
    moment_sigma_from_sufficient,
    parametric_bootstrap,
    percentile_interval,
    reviewer_bootstrap_vectorised,
    summarise_bootstrap,
)

REPO = Path(__file__).resolve().parents[2]
ANCHOR_DIR = REPO / "manuscript" / "supplement" / "sigma_anchors"


def load(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[str]]:
    reviewers: dict[str, int] = {}
    items: dict[str, int] = {}
    rows_r, rows_i, rows_c = [], [], []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            reference = str(row["reference_label"]).strip()
            if reference == "" or reference.lower() in {"nan", "none", "tie"}:
                continue
            r = reviewers.setdefault(row["annotator_id"], len(reviewers))
            i = items.setdefault(row["item_id"], len(items))
            rows_r.append(r)
            rows_i.append(i)
            rows_c.append(int(str(row["label"]).strip() == reference))
    return (
        np.asarray(rows_r, dtype=np.int32),
        np.asarray(rows_i, dtype=np.int32),
        np.asarray(rows_c, dtype=np.int8),
        list(reviewers),
        list(items),
    )


def analyse(
    r: np.ndarray,
    i: np.ndarray,
    c: np.ndarray,
    n_reviewers: int,
    n_items: int,
    min_items: int,
    reviewer_draws: int,
    item_draws: int,
    parametric_draws: int,
    seed: int,
) -> dict[str, object]:
    counts = np.bincount(r, minlength=n_reviewers)
    keep_reviewer = counts >= min_items
    mask = keep_reviewer[r]
    r, i, c = r[mask], i[mask], c[mask]
    if r.size == 0:
        return {}
    remap = -np.ones(n_reviewers, dtype=np.int64)
    kept = np.flatnonzero(keep_reviewer)
    remap[kept] = np.arange(kept.size)
    r = remap[r].astype(np.int32)
    k = kept.size

    counts = np.bincount(r, minlength=k)
    sums = np.bincount(r, weights=c, minlength=k)
    point, mu_logit = moment_sigma_from_sufficient(sums, counts)

    accuracies = np.divide(sums, counts, out=np.zeros(k), where=counts > 0)

    # 1. Reviewer bootstrap (headline interval)
    rev_boot = reviewer_bootstrap_vectorised(sums, counts, reviewer_draws, seed)
    rev_summary = summarise_bootstrap(rev_boot, point, "reviewers")

    # 2. Parametric bootstrap
    para_boot = parametric_bootstrap(
        point, mu_logit, counts.astype(np.int64), parametric_draws, seed + 1
    )
    para_summary = summarise_bootstrap(para_boot, point, "parametric")

    # 3. Item bootstrap (supplementary — wrong resampling unit for sigma_r)
    item_boot = item_bootstrap_vectorised(r, i, c, k, n_items, item_draws, seed + 2)
    item_summary = summarise_bootstrap(item_boot, point, "items")

    # Legacy keys for backward compatibility (clearly labelled)
    q025 = float(np.quantile(item_boot, 0.025))
    q975 = float(np.quantile(item_boot, 0.975))

    return {
        "sigma_r": point,
        "mu_logit": mu_logit,
        "n_reviewers": int(k),
        "n_items": int(np.unique(i).size),
        "n_judgments": int(r.size),
        "min_items_per_reviewer": int(counts.min()),
        "median_items_per_reviewer": float(np.median(counts)),
        "accuracy_mean": float(accuracies.mean()),
        "accuracy_q10": float(np.quantile(accuracies, 0.10)),
        "accuracy_q90": float(np.quantile(accuracies, 0.90)),
        # New unambiguous keys
        **rev_summary,
        **para_summary,
        **item_summary,
        # Legacy keys preserved for any downstream consumers
        "bootstrap_percentile_ci95": [q025, q975],
        "bootstrap_mean": float(item_boot.mean()),
        "bootstrap_bias": float(item_boot.mean() - point),
        "bootstrap_items_ci95": [
            max(0.0, 2.0 * point - q975),
            max(0.0, 2.0 * point - q025),
        ],
        "bootstrap_draws": int(item_draws),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-dir", type=Path, default=ANCHOR_DIR)
    parser.add_argument("--min-items", type=int, default=30)
    parser.add_argument("--reviewer-draws", type=int, default=2000)
    parser.add_argument("--item-draws", type=int, default=200)
    parser.add_argument("--parametric-draws", type=int, default=400)
    parser.add_argument("--seed", type=int, default=2026072810)
    parser.add_argument(
        "--output", type=Path, default=ANCHOR_DIR / "sigma_r_human_anchors.json"
    )
    args = parser.parse_args()

    manifest = json.loads((args.anchor_dir / "manifest.json").read_text(encoding="utf-8"))
    results = {}
    for record in manifest:
        slug = record["dataset"]
        path = args.anchor_dir / f"{slug}_long.csv"
        if not path.exists():
            continue
        r, i, c, reviewers, items = load(path)
        if r.size == 0:
            continue
        entry = analyse(
            r, i, c, len(reviewers), len(items), args.min_items,
            args.reviewer_draws, args.item_draws, args.parametric_draws, args.seed
        )
        if not entry:
            continue
        entry["task_type"] = record.get("task_type", "")
        entry["source_url"] = record.get("source_url", "")
        entry["crossing"] = record.get("crossing", "")
        entry["reference_source"] = record.get("reference_source", "")
        entry["min_items_filter"] = args.min_items
        results[slug] = entry
        ci = entry["boot_reviewers_ci95"]
        print(
            f"{slug:<32} reviewers={entry['n_reviewers']:>5} items={entry['n_items']:>7} "
            f"sigma_r={entry['sigma_r']:.3f} "
            f"reviewer_CI[{ci[0]:.3f}, {ci[1]:.3f}] "
            f"acc={entry['accuracy_mean']:.3f}",
            flush=True,
        )

    values = [v["sigma_r"] for v in results.values()]
    payload = {
        "schema_version": "sigma-r-human-anchors-v1",
        "estimator": "moment estimator on logit accuracies, binomial component removed",
        "reviewer_inclusion": f">= {args.min_items} judgments",
        "anchors": results,
        "summary": {
            "n_corpora": len(results),
            "sigma_r_min": min(values) if values else None,
            "sigma_r_max": max(values) if values else None,
            "sigma_r_median": float(np.median(values)) if values else None,
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
