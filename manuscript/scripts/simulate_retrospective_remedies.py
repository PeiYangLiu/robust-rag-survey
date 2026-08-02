#!/usr/bin/env python3
"""Executable retrospective analyses for a reviewer-assigned claim audit.

Reviewer A's two objections to the original assignment simulation were that
(i) the reported false-positive rates depend on a hand-chosen reviewer
heterogeneity, and (ii) the only remedy offered -- an oracle randomization test
over the complete reviewer-by-claim vote matrix -- "cannot be applied
retrospectively", so the section ends without actionable advice.

This script answers both.

*   The reviewer-heterogeneity grid is taken from
    ``supplement/reviewer_heterogeneity_anchor.json``, which estimates it from
    the only crossed reviewer-by-item design available in this project.
*   Two of the four analyses compared here are executable by any author who
    releases pre-aggregation votes with reviewer identifiers: a two-sample test
    on the twelve individual reviewer accuracies, and its exact 924-assignment
    permutation counterpart.  Neither needs an oracle vote matrix or an
    arm-independent panel schedule.
*   A third analysis, ``votes_source_se``, uses individual votes but keeps a
    source-level standard error.  It isolates the cause: the failure is the
    unit of uncertainty, not the majority aggregation.
*   Both a sharp null and a genuine prompt effect are simulated, so the valid
    analyses are shown to retain power rather than merely to be conservative.
*   Reviewer abilities are either fixed population quantiles (as in the
    original simulation) or redrawn per replicate.  Redrawing makes the target
    an explicit reviewer-population effect, so the source-only test cannot be
    defended as answering a realized-panel estimand.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[2]
DEFAULT_ANCHOR = REPO / "manuscript" / "supplement" / "reviewer_heterogeneity_anchor.json"
DEFAULT_OUTPUT = (
    REPO / "manuscript" / "supplement" / "retrospective_remedy_simulation.json"
)

SEED = 2026072706
ALPHA = 0.05
REVIEWERS_PER_ARM = 6
TOTAL_REVIEWERS = 2 * REVIEWERS_PER_ARM
CLAIMS_PER_SOURCE = 6
BASELINE_ACCURACY = 0.75
SOURCE_LOGIT_SD = 0.15
CLAIM_LOGIT_SD = 0.35
TRIPLES = tuple(itertools.combinations(range(REVIEWERS_PER_ARM), 3))
ASSIGNMENTS = tuple(itertools.combinations(range(TOTAL_REVIEWERS), REVIEWERS_PER_ARM))
ASSIGNMENT_MASK = np.zeros((len(ASSIGNMENTS), TOTAL_REVIEWERS), dtype=bool)
for _row, _assignment in enumerate(ASSIGNMENTS):
    ASSIGNMENT_MASK[_row, list(_assignment)] = True

ANALYSES = (
    "panel_majority_source_se",
    "votes_source_se",
    "reviewer_mean_t",
    "reviewer_permutation",
)


def logit(probability: float) -> float:
    return math.log(probability / (1.0 - probability))


def student_t_quantile(degrees: int, probability: float) -> float:
    """Two-sided critical value by bisection on the Student-t CDF."""
    from scipy import stats

    return float(stats.t.ppf(probability, degrees))


def fixed_quantile_abilities(rater_sd: float) -> np.ndarray:
    normal = NormalDist()
    return np.array(
        [
            logit(BASELINE_ACCURACY)
            + rater_sd * normal.inv_cdf((index + 0.5) / TOTAL_REVIEWERS)
            for index in range(TOTAL_REVIEWERS)
        ]
    )


def panel_matrix() -> np.ndarray:
    """``claims_per_cycle x reviewers_per_arm`` indicator of panel membership."""
    matrix = np.zeros((len(TRIPLES), REVIEWERS_PER_ARM), dtype=bool)
    for row, triple in enumerate(TRIPLES):
        matrix[row, list(triple)] = True
    return matrix


PANEL = panel_matrix()


def simulate_scenario(
    *,
    rng: np.random.Generator,
    replicates: int,
    source_count: int,
    rater_sd: float,
    effect_logit: float,
    resample_abilities: bool,
    t_critical_source: float,
    t_critical_reviewer: float,
) -> dict[str, float]:
    claim_count = source_count * CLAIMS_PER_SOURCE
    schedule = np.arange(claim_count) % len(TRIPLES)
    panel_membership = PANEL[schedule]  # claims x reviewers_per_arm
    rated_per_reviewer = panel_membership.sum(axis=0)  # per arm slot
    rejections = {name: 0 for name in ANALYSES}

    block = max(1, min(replicates, max(1, 1_500_000 // max(claim_count, 1))))
    done = 0
    while done < replicates:
        size = min(block, replicates - done)
        done += size

        # Reviewer abilities: either fixed population quantiles, or a fresh
        # sample from the reviewer population in every replicate.
        if resample_abilities:
            abilities = logit(BASELINE_ACCURACY) + rng.normal(
                0.0, rater_sd, size=(size, TOTAL_REVIEWERS)
            )
        else:
            abilities = np.tile(fixed_quantile_abilities(rater_sd), (size, 1))
            for row in range(size):
                rng.shuffle(abilities[row])

        # Arm assignment: the first six shuffled reviewers take the D prompt.
        assignment_index = rng.integers(0, len(ASSIGNMENTS), size=size)
        in_d = ASSIGNMENT_MASK[assignment_index]  # size x reviewers

        source_shift = rng.normal(0.0, SOURCE_LOGIT_SD, size=(size, source_count))
        claim_shift = source_shift.repeat(CLAIMS_PER_SOURCE, axis=1) + rng.normal(
            0.0, CLAIM_LOGIT_SD, size=(size, claim_count)
        )

        arm_bonus = np.where(in_d, effect_logit, 0.0)
        latent = (
            abilities[:, None, :] + arm_bonus[:, None, :] - claim_shift[:, :, None]
        ).astype(np.float32)
        probability = 1.0 / (1.0 + np.exp(-latent))
        votes = rng.random(probability.shape, dtype=np.float32) < probability

        d_slots = np.argsort(~in_d, axis=1, kind="stable")[:, :REVIEWERS_PER_ARM]
        c_slots = np.argsort(in_d, axis=1, kind="stable")[:, :REVIEWERS_PER_ARM]
        rows = np.arange(size)[:, None, None]
        claims = np.arange(claim_count)[None, :, None]
        d_votes = votes[rows, claims, d_slots[:, None, :]]
        c_votes = votes[rows, claims, c_slots[:, None, :]]

        panel_mask = panel_membership[None, :, :]
        d_panel_correct = (d_votes & panel_mask).sum(axis=2) >= 2
        c_panel_correct = (c_votes & panel_mask).sum(axis=2) >= 2

        # Analysis 1: panel-majority difference with a source-level SE.
        difference = d_panel_correct.astype(np.float64) - c_panel_correct.astype(
            np.float64
        )
        by_source = difference.reshape(size, source_count, CLAIMS_PER_SOURCE).mean(axis=2)
        rejections["panel_majority_source_se"] += _reject_t(
            by_source, t_critical_source
        )

        # Analysis 2: individual votes, still with a source-level SE.
        d_vote_rate = np.where(panel_mask, d_votes, 0).sum(axis=2) / PANEL[schedule].sum(
            axis=1
        )
        c_vote_rate = np.where(panel_mask, c_votes, 0).sum(axis=2) / PANEL[schedule].sum(
            axis=1
        )
        vote_difference = d_vote_rate - c_vote_rate
        by_source_votes = vote_difference.reshape(
            size, source_count, CLAIMS_PER_SOURCE
        ).mean(axis=2)
        rejections["votes_source_se"] += _reject_t(by_source_votes, t_critical_source)

        # Analyses 3 and 4 operate on the twelve individual reviewer accuracies.
        d_correct_counts = np.where(panel_mask, d_votes, False).sum(axis=1)
        c_correct_counts = np.where(panel_mask, c_votes, False).sum(axis=1)
        d_accuracy = d_correct_counts / rated_per_reviewer
        c_accuracy = c_correct_counts / rated_per_reviewer
        accuracies = np.empty((size, TOTAL_REVIEWERS))
        np.put_along_axis(accuracies, d_slots, d_accuracy, axis=1)
        np.put_along_axis(accuracies, c_slots, c_accuracy, axis=1)

        rejections["reviewer_mean_t"] += _reject_two_sample(
            d_accuracy, c_accuracy, t_critical_reviewer
        )
        rejections["reviewer_permutation"] += _reject_permutation(accuracies, in_d)

    return {name: rejections[name] / replicates for name in ANALYSES}


def _reject_t(by_cluster: np.ndarray, t_critical: float) -> int:
    count = by_cluster.shape[1]
    mean = by_cluster.mean(axis=1)
    sd = by_cluster.std(axis=1, ddof=1)
    se = sd / math.sqrt(count)
    statistic = np.divide(mean, se, out=np.zeros_like(mean), where=se > 0.0)
    statistic[(se == 0.0) & (mean != 0.0)] = np.inf
    return int(np.count_nonzero(np.abs(statistic) > t_critical))


def _reject_two_sample(
    treated: np.ndarray, control: np.ndarray, t_critical: float
) -> int:
    n = treated.shape[1]
    mean_difference = treated.mean(axis=1) - control.mean(axis=1)
    pooled = ((treated.var(axis=1, ddof=1) + control.var(axis=1, ddof=1)) / 2.0) ** 0.5
    se = pooled * math.sqrt(2.0 / n)
    statistic = np.divide(
        mean_difference, se, out=np.zeros_like(mean_difference), where=se > 0.0
    )
    statistic[(se == 0.0) & (mean_difference != 0.0)] = np.inf
    return int(np.count_nonzero(np.abs(statistic) > t_critical))


def _reject_permutation(accuracies: np.ndarray, in_d: np.ndarray) -> int:
    total = accuracies.sum(axis=1, keepdims=True)
    treated_sums = accuracies @ ASSIGNMENT_MASK.T.astype(np.float64)
    estimates = (2.0 * treated_sums - total) / REVIEWERS_PER_ARM
    observed_sum = (accuracies * in_d).sum(axis=1, keepdims=True)
    observed = (2.0 * observed_sum - total) / REVIEWERS_PER_ARM
    extreme = (np.abs(estimates) >= np.abs(observed) - 1.0e-12).sum(axis=1)
    return int(np.count_nonzero(extreme / len(ASSIGNMENTS) < ALPHA))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor", type=Path, default=DEFAULT_ANCHOR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replicates", type=int, default=5_000)
    parser.add_argument("--sources", type=int, nargs="*", default=[20, 40, 80, 160])
    parser.add_argument("--effects", type=float, nargs="*", default=[0.0, 0.4])
    parser.add_argument("--sigma-max", type=float, default=1.0)
    parser.add_argument(
        "--extra-anchors",
        type=Path,
        nargs="*",
        default=[
            REPO / "manuscript" / "supplement" / "sigma_r_multi_anchor.json",
            REPO
            / "manuscript"
            / "supplement"
            / "sigma_anchors"
            / "sigma_r_human_anchors.json",
        ],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    anchor = json.loads(args.anchor.read_text(encoding="utf-8"))
    direct = anchor["direct_estimate"]
    grid_values = {
        0.0,
        round(float(direct["sigma_r_bootstrap"]["p250"]), 2),
        round(float(direct["sigma_r_point"]), 2),
        round(float(direct["sigma_r_bootstrap"]["p750"]), 2),
        round(float(direct["sigma_r_bootstrap"]["p975"]), 2),
    }
    # Extend the grid to every additional crossed design we can estimate, so the
    # reported rejection rates cover the whole empirically anchored range rather
    # than one three-rater point estimate.
    for extra_path in args.extra_anchors:
        if not extra_path.exists():
            continue
        payload_extra = json.loads(extra_path.read_text(encoding="utf-8"))
        for entry in payload_extra.get("anchors", {}).values():
            value = entry.get("sigma_r")
            if value is None:
                continue
            grid_values.add(round(float(value), 2))
    grid = sorted(v for v in grid_values if v <= args.sigma_max)
    rows = []
    for resample in (False, True):
        for rater_sd in grid:
            for source_count in args.sources:
                for effect in args.effects:
                    rng = np.random.default_rng(
                        [
                            SEED,
                            int(resample),
                            int(round(rater_sd * 100)),
                            source_count,
                            int(round(effect * 100)),
                        ]
                    )
                    rates = simulate_scenario(
                        rng=rng,
                        replicates=args.replicates,
                        source_count=source_count,
                        rater_sd=rater_sd,
                        effect_logit=effect,
                        resample_abilities=resample,
                        t_critical_source=student_t_quantile(
                            source_count - 1, 1.0 - ALPHA / 2.0
                        ),
                        t_critical_reviewer=student_t_quantile(
                            TOTAL_REVIEWERS - 2, 1.0 - ALPHA / 2.0
                        ),
                    )
                    rows.append(
                        {
                            "reviewer_abilities": "resampled"
                            if resample
                            else "fixed_quantiles",
                            "sigma_r": rater_sd,
                            "sources": source_count,
                            "claims": source_count * CLAIMS_PER_SOURCE,
                            "true_prompt_effect_logit": effect,
                            "quantity": "power" if effect else "size",
                            **{name: round(rates[name], 4) for name in ANALYSES},
                        }
                    )
                    print(json.dumps(rows[-1], sort_keys=True), flush=True)
    payload = {
        "schema_version": "retrospective-remedy-simulation-v1",
        "seed": SEED,
        "replicates": args.replicates,
        "alpha": ALPHA,
        "reviewers": TOTAL_REVIEWERS,
        "reviewers_per_arm": REVIEWERS_PER_ARM,
        "claims_per_source": CLAIMS_PER_SOURCE,
        "baseline_accuracy": BASELINE_ACCURACY,
        "source_logit_sd": SOURCE_LOGIT_SD,
        "claim_logit_sd": CLAIM_LOGIT_SD,
        "sigma_r_grid": grid,
        "sigma_r_grid_source": [str(args.anchor.relative_to(REPO))]
        + [str(p.relative_to(REPO)) for p in args.extra_anchors if p.exists()],
        "analyses": {
            "panel_majority_source_se": (
                "Paired source t test on panel-majority correctness. The status "
                "quo analysis; requires only released majority labels."
            ),
            "votes_source_se": (
                "Same source-level standard error applied to individual votes "
                "rather than majority labels. Isolates aggregation from unit."
            ),
            "reviewer_mean_t": (
                "Two-sample t test on the twelve individual reviewer "
                "accuracies. Executable retrospectively from released "
                "pre-aggregation votes with reviewer identifiers."
            ),
            "reviewer_permutation": (
                "Exact test referring the same reviewer-accuracy contrast to "
                "all 924 arm assignments. Executable retrospectively from the "
                "same released votes."
            ),
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "rows": len(rows), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
