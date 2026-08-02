#!/usr/bin/env python3
"""Anchor the reviewer-heterogeneity parameter of the assignment simulation.

Reviewer A objected that ``sigma_r`` in the assignment-mismatch simulation is
"a sensitivity parameter, not an estimate", so the reported rejection rates
"carry no information about any real study".  This script replaces the
arbitrary choice with two evidence-based anchors and, crucially, quantifies how
wide the remaining uncertainty is *because* of the reporting gaps documented by
the published-study audit.

Anchor 1 (point estimate, crossed design).
    The retained 80-claim development diagnostic has three coders who each
    labelled the same 80 comparison claims, adjudicated independently.  This is
    a crossed rater-by-item design, so a between-rater logit standard deviation
    is estimable.  We use a method-of-moments estimator that removes the
    binomial sampling component and bootstrap it over items (clustered by
    source) for an interval.  With three raters the variance is imprecise; the
    interval is reported rather than hidden.

Anchor 2 (partial identification from published agreement statistics).
    Two audited papers report a rater-agreement quantity: RAGTruth reports a
    91.8% response-level consistency rate between two annotators, and FaithEval
    reports over 98% agreement under majority voting.  Under the latent-logit
    model used by the simulation, an observed pairwise agreement identifies the
    *total* logit dispersion but not its split between raters and items.  We
    therefore report the sigma_r implied by each admissible rater share of that
    dispersion.  The width of the resulting interval is a direct cost of the
    missing item-by-annotator assignment: had the assignment been reported, the
    two components would be separately identified.

Outputs a JSON record consumed by the simulation and the manuscript tables.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[2]
DEFAULT_PREDICTIONS = REPO / "manuscript" / "supplement" / "claim_rule_predictions.csv"
DEFAULT_OUTPUT = (
    REPO / "manuscript" / "supplement" / "reviewer_heterogeneity_anchor.json"
)
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 2026072705
CODER_COLUMNS = ("coder_A_verdict", "coder_B_verdict", "coder_C_verdict")
REFERENCE_COLUMN = "human_adjudicated_verdict"
RATER_SHARES = (0.0, 0.25, 0.50, 0.75, 1.0)

# Reported agreement quantities located in the locally extracted full texts of
# the audited papers.  Each entry records the exact source line so the anchor is
# checkable.
PUBLISHED_AGREEMENT = (
    {
        "cite_key": "ragTruth2024",
        "source_file": "manuscript/citation_audit/expanded_texts/ragTruth2024.txt",
        "source_lines": "366-369",
        "quotation": (
            "each response is independently labeled by two annotators. The "
            "consistency rate of two annotators was 91.8% at the response level"
        ),
        "raters_per_item": 2,
        "pairwise_agreement": 0.918,
    },
    {
        "cite_key": "rrag040",
        "source_file": "manuscript/citation_audit/expanded_texts/rrag040.txt",
        "source_lines": "341-343",
        "quotation": (
            "determined by majority agreement. This yields 1.5K samples. ... "
            "achieving over 98% agreement"
        ),
        "raters_per_item": 3,
        "pairwise_agreement": 0.98,
    },
)


def logit(probability: float) -> float:
    return math.log(probability / (1.0 - probability))


def logistic(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def coder_correctness(rows: Sequence[Mapping[str, str]]) -> np.ndarray:
    """Return an ``items x raters`` binary correctness matrix."""
    matrix = np.zeros((len(rows), len(CODER_COLUMNS)), dtype=np.int8)
    for row_index, row in enumerate(rows):
        reference = row[REFERENCE_COLUMN].strip()
        for coder_index, column in enumerate(CODER_COLUMNS):
            matrix[row_index, coder_index] = int(row[column].strip() == reference)
    return matrix


def moment_sigma_r(matrix: np.ndarray) -> tuple[float, list[float]]:
    """Between-rater logit SD with the binomial sampling component removed."""
    items, raters = matrix.shape
    accuracies = matrix.mean(axis=0)
    clipped = np.clip(accuracies, 0.5 / items, 1.0 - 0.5 / items)
    logits = np.log(clipped / (1.0 - clipped))
    observed_variance = float(np.var(logits, ddof=1)) if raters > 1 else 0.0
    # Delta-method sampling variance of an empirical logit.
    sampling = float(np.mean(1.0 / (items * clipped * (1.0 - clipped))))
    corrected = max(0.0, observed_variance - sampling)
    return math.sqrt(corrected), [float(value) for value in accuracies]


def bootstrap_sigma_r(
    matrix: np.ndarray, clusters: Sequence[str], draws: int, seed: int
) -> dict[str, float]:
    rng = random.Random(seed)
    unique = sorted(set(clusters))
    index_by_cluster: dict[str, list[int]] = {name: [] for name in unique}
    for position, name in enumerate(clusters):
        index_by_cluster[name].append(position)
    estimates = []
    for _ in range(draws):
        chosen: list[int] = []
        for _ in range(len(unique)):
            chosen.extend(index_by_cluster[unique[rng.randrange(len(unique))]])
        estimate, _ = moment_sigma_r(matrix[chosen, :])
        estimates.append(estimate)
    estimates.sort()

    def quantile(probability: float) -> float:
        position = (len(estimates) - 1) * probability
        low = math.floor(position)
        high = math.ceil(position)
        if low == high:
            return estimates[low]
        weight = position - low
        return estimates[low] * (1.0 - weight) + estimates[high] * weight

    return {
        "bootstrap_draws": draws,
        "p025": quantile(0.025),
        "p250": quantile(0.25),
        "p500": quantile(0.50),
        "p750": quantile(0.75),
        "p975": quantile(0.975),
    }


def marginal_and_agreement(
    intercept: float, rater_sd: float, item_sd: float, nodes: int = 41
) -> tuple[float, float]:
    """Marginal positive-label rate and two-rater agreement under the model.

    A label (not a correctness indicator) is Bernoulli with success probability
    ``logistic(intercept + a_r - d_i)``, where ``a_r`` and ``d_i`` are the rater
    and item random effects of the simulation model.
    """
    grid, weights = np.polynomial.hermite_e.hermegauss(nodes)
    weights = weights / weights.sum()
    rater_offsets = rater_sd * grid
    item_offsets = item_sd * grid
    marginal = 0.0
    agreement = 0.0
    for item_weight, item_offset in zip(weights, item_offsets):
        probabilities = 1.0 / (1.0 + np.exp(-(intercept + rater_offsets - item_offset)))
        mean_positive = float(np.dot(weights, probabilities))
        mean_square = float(np.dot(weights, probabilities**2))
        marginal += item_weight * mean_positive
        agreement += item_weight * (mean_square + 1.0 - 2.0 * mean_positive + mean_square)
    return marginal, agreement


def calibrate_intercept(prevalence: float, rater_sd: float, item_sd: float) -> float:
    """Choose the intercept that reproduces a target positive-label rate."""
    low, high = -12.0, 12.0
    for _ in range(120):
        middle = 0.5 * (low + high)
        marginal, _ = marginal_and_agreement(middle, rater_sd, item_sd)
        if marginal < prevalence:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def item_sd_matching_agreement(
    prevalence: float, rater_sd: float, agreement: float
) -> float | None:
    """Item SD reproducing an observed pairwise agreement, if one exists."""

    def agreement_at(item_sd: float) -> float:
        intercept = calibrate_intercept(prevalence, rater_sd, item_sd)
        return marginal_and_agreement(intercept, rater_sd, item_sd)[1]

    low, high = 0.0, 10.0
    if agreement_at(low) > agreement:
        return None
    if agreement_at(high) < agreement:
        return None
    for _ in range(60):
        middle = 0.5 * (low + high)
        if agreement_at(middle) < agreement:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def identified_region(
    agreement: float, prevalences: Sequence[float], rater_grid: Sequence[float]
) -> list[dict[str, object]]:
    """Which reviewer heterogeneities are consistent with a reported agreement."""
    rows = []
    for prevalence in prevalences:
        admissible = []
        for rater_sd in rater_grid:
            item_sd = item_sd_matching_agreement(prevalence, rater_sd, agreement)
            if item_sd is not None:
                admissible.append(
                    {"sigma_r": round(rater_sd, 3), "matching_sigma_item": round(item_sd, 3)}
                )
        rows.append(
            {
                "assumed_positive_label_prevalence": prevalence,
                "admissible_sigma_r_count": len(admissible),
                "admissible_sigma_r_min": admissible[0]["sigma_r"] if admissible else None,
                "admissible_sigma_r_max": admissible[-1]["sigma_r"] if admissible else None,
                "solutions": admissible,
            }
        )
    return rows


PREVALENCE_GRID = (0.50, 0.70, 0.90)
RATER_SD_GRID = tuple(round(0.05 * step, 2) for step in range(0, 25))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline-accuracy", type=float, default=0.75)
    parser.add_argument("--draws", type=int, default=BOOTSTRAP_DRAWS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_rows(args.predictions)
    matrix = coder_correctness(rows)
    clusters = [row["source_key"] for row in rows]
    point, accuracies = moment_sigma_r(matrix)
    interval = bootstrap_sigma_r(matrix, clusters, args.draws, BOOTSTRAP_SEED)

    published = []
    for record in PUBLISHED_AGREEMENT:
        published.append(
            {
                **record,
                "identified_region": identified_region(
                    float(record["pairwise_agreement"]), PREVALENCE_GRID, RATER_SD_GRID
                ),
            }
        )
    feasible = [
        entry["admissible_sigma_r_count"] / len(RATER_SD_GRID)
        for record in published
        for entry in record["identified_region"]
        if entry["admissible_sigma_r_count"] > 0
    ]
    widest_admissible_fraction = max(feasible) if feasible else 0.0

    payload = {
        "schema_version": "reviewer-heterogeneity-anchor-v1",
        "direct_estimate": {
            "source": str(args.predictions.relative_to(REPO)),
            "design": "three coders crossed with 80 adjudicated comparison claims",
            "items": int(matrix.shape[0]),
            "raters": int(matrix.shape[1]),
            "coder_accuracy_against_adjudicated_reference": [
                round(value, 4) for value in accuracies
            ],
            "sigma_r_point": round(point, 4),
            "sigma_r_bootstrap": {
                key: (round(value, 4) if isinstance(value, float) else value)
                for key, value in interval.items()
            },
            "bootstrap_unit": "source_key cluster",
            "caveat": (
                "Three raters give an imprecise variance; the interval is the "
                "estimate, not the point."
            ),
        },
        "published_agreement_anchors": published,
        "partial_identification_note": (
            "A reported pairwise agreement rate constrains total latent "
            "dispersion but not its split between rater and item components: for "
            "every reviewer heterogeneity on the grid there is an item "
            "dispersion that reproduces the reported agreement. Separating the "
            "two components requires the item-by-annotator assignment, which "
            "none of the nine audited papers reports."
        ),
        "widest_admissible_sigma_r_fraction_of_grid": round(widest_admissible_fraction, 3),
        "sigma_r_point_identified_by_published_reporting": False,
        "rater_sd_grid": list(RATER_SD_GRID),
        "recommended_simulation_grid": sorted(
            {
                0.0,
                round(interval["p250"], 2),
                round(point, 2),
                round(interval["p975"], 2),
            }
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
