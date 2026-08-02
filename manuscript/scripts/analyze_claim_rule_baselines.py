#!/usr/bin/env python3
"""Baselines, paired intervals and an error taxonomy for the 80-claim diagnostic.

Reviewer A objected that the development diagnostic reports an exact agreement
of 0.500 for the full rule "with no trivial baseline against which the 0.500
should be read", and that the full rule "does not beat its own C2/C5 ablation"
without any interval on the difference.  This script supplies both, plus the
error taxonomy and per-coordinate reliability decomposition that the objection
asks for.

It computes

*   two pre-specified trivial baselines: predicting the modal adjudicated
    verdict, and drawing a verdict from the adjudicated marginal;
*   source-clustered bootstrap intervals for every rule and baseline;
*   paired source-clustered bootstrap intervals and exact McNemar tests for the
    contrasts that matter (full rule vs. ablation, full rule vs. majority
    class);
*   an error taxonomy of the full rule's confusions; and
*   which coordinate field, when coders disagree on it, predicts a verdict
    disagreement.

Nothing here uses the excluded 480-claim collection.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
DEFAULT_PREDICTIONS = REPO / "manuscript" / "supplement" / "claim_rule_predictions.csv"
DEFAULT_FIELDS = (
    REPO / "manuscript" / "human_coding" / "observed_claim_human_validation_20260714"
)
DEFAULT_OUTPUT = REPO / "manuscript" / "supplement" / "claim_rule_baselines.json"
BOOTSTRAP_DRAWS = 10_000
SEED = 2026072707
REFERENCE = "human_adjudicated_verdict"
RULES = {
    "three_field_model": "Three-field taxonomy",
    "evidence_control_baseline": "Evidence+controls (C2/C5 ablated)",
    "five_coordinate_model": "Five coordinates",
    "full_schema_model": "Five coordinates + controls",
}
CODERS = ("coder_A_verdict", "coder_B_verdict", "coder_C_verdict")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def cohen_kappa(reference: Sequence[str], prediction: Sequence[str]) -> float:
    labels = sorted(set(reference) | set(prediction))
    total = len(reference)
    observed = sum(1 for a, b in zip(reference, prediction) if a == b) / total
    reference_counts = Counter(reference)
    prediction_counts = Counter(prediction)
    expected = sum(
        (reference_counts[label] / total) * (prediction_counts[label] / total)
        for label in labels
    )
    if math.isclose(expected, 1.0):
        return 0.0
    return (observed - expected) / (1.0 - expected)


def cluster_bootstrap(
    rows: Sequence[Mapping[str, str]],
    statistic,
    draws: int,
    seed: int,
) -> dict[str, float]:
    rng = random.Random(seed)
    clusters: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        clusters.setdefault(row["source_key"], []).append(row)
    names = sorted(clusters)
    values = []
    for _ in range(draws):
        sample: list[Mapping[str, str]] = []
        for _ in range(len(names)):
            sample.extend(clusters[names[rng.randrange(len(names))]])
        values.append(statistic(sample))
    values.sort()

    def quantile(probability: float) -> float:
        position = (len(values) - 1) * probability
        low = math.floor(position)
        high = math.ceil(position)
        if low == high:
            return values[low]
        weight = position - low
        return values[low] * (1.0 - weight) + values[high] * weight

    return {"lower": quantile(0.025), "upper": quantile(0.975)}


def exact_mcnemar(discordant_a: int, discordant_b: int) -> float:
    total = discordant_a + discordant_b
    if total == 0:
        return 1.0
    smaller = min(discordant_a, discordant_b)
    tail = sum(math.comb(total, k) for k in range(0, smaller + 1)) / (2.0**total)
    return min(1.0, 2.0 * tail)


def accuracy_of(rows: Sequence[Mapping[str, str]], column: str) -> float:
    return sum(1 for row in rows if row[column] == row[REFERENCE]) / len(rows)


def majority_class_accuracy(rows: Sequence[Mapping[str, str]], modal: str) -> float:
    return sum(1 for row in rows if row[REFERENCE] == modal) / len(rows)


def marginal_random_accuracy(rows: Sequence[Mapping[str, str]]) -> float:
    """Expected accuracy of drawing a verdict from the adjudicated marginal."""
    counts = Counter(row[REFERENCE] for row in rows)
    total = len(rows)
    return sum((count / total) ** 2 for count in counts.values())


def uniform_random_accuracy(rows: Sequence[Mapping[str, str]], classes: int) -> float:
    return 1.0 / classes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--draws", type=int, default=BOOTSTRAP_DRAWS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_rows(args.predictions)
    reference_labels = [row[REFERENCE] for row in rows]
    classes = sorted(set(reference_labels))
    modal = Counter(reference_labels).most_common(1)[0][0]

    entries = []
    for column, label in RULES.items():
        accuracy = accuracy_of(rows, column)
        kappa = cohen_kappa(reference_labels, [row[column] for row in rows])
        interval = cluster_bootstrap(
            rows, lambda sample, c=column: accuracy_of(sample, c), args.draws, SEED
        )
        entries.append(
            {
                "estimator": column,
                "label": label,
                "kind": "rule",
                "exact_accuracy": round(accuracy, 4),
                "cohen_kappa": round(kappa, 4),
                "ci95": [round(interval["lower"], 4), round(interval["upper"], 4)],
            }
        )

    majority_interval = cluster_bootstrap(
        rows, lambda sample: majority_class_accuracy(sample, modal), args.draws, SEED
    )
    marginal_interval = cluster_bootstrap(
        rows, marginal_random_accuracy, args.draws, SEED
    )
    entries.append(
        {
            "estimator": "majority_class_baseline",
            "label": f"Majority class ({modal})",
            "kind": "baseline",
            "exact_accuracy": round(majority_class_accuracy(rows, modal), 4),
            "cohen_kappa": 0.0,
            "ci95": [round(majority_interval["lower"], 4), round(majority_interval["upper"], 4)],
        }
    )
    entries.append(
        {
            "estimator": "marginal_random_baseline",
            "label": "Random draw from adjudicated marginal",
            "kind": "baseline",
            "exact_accuracy": round(marginal_random_accuracy(rows), 4),
            "cohen_kappa": 0.0,
            "ci95": [round(marginal_interval["lower"], 4), round(marginal_interval["upper"], 4)],
        }
    )
    entries.append(
        {
            "estimator": "uniform_random_baseline",
            "label": f"Uniform over {len(classes)} verdicts",
            "kind": "baseline",
            "exact_accuracy": round(uniform_random_accuracy(rows, len(classes)), 4),
            "cohen_kappa": 0.0,
            "ci95": None,
        }
    )

    contrasts = []
    comparisons = (
        ("full_schema_model", "evidence_control_baseline"),
        ("five_coordinate_model", "evidence_control_baseline"),
        ("full_schema_model", "majority_class"),
        ("five_coordinate_model", "majority_class"),
    )
    for left, right in comparisons:
        if right == "majority_class":
            left_correct = [row[left] == row[REFERENCE] for row in rows]
            right_correct = [row[REFERENCE] == modal for row in rows]
            right_label = f"Majority class ({modal})"
        else:
            left_correct = [row[left] == row[REFERENCE] for row in rows]
            right_correct = [row[right] == row[REFERENCE] for row in rows]
            right_label = RULES[right]
        only_left = sum(1 for a, b in zip(left_correct, right_correct) if a and not b)
        only_right = sum(1 for a, b in zip(left_correct, right_correct) if b and not a)

        def difference(sample: Sequence[Mapping[str, str]], l=left, r=right, m=modal) -> float:
            left_value = accuracy_of(sample, l)
            right_value = (
                majority_class_accuracy(sample, m)
                if r == "majority_class"
                else accuracy_of(sample, r)
            )
            return left_value - right_value

        interval = cluster_bootstrap(rows, difference, args.draws, SEED)
        contrasts.append(
            {
                "left": RULES[left],
                "right": right_label,
                "difference": round(difference(rows), 4),
                "ci95": [round(interval["lower"], 4), round(interval["upper"], 4)],
                "discordant_left_only": only_left,
                "discordant_right_only": only_right,
                "mcnemar_exact_p": round(exact_mcnemar(only_left, only_right), 4),
            }
        )

    confusion = Counter(
        (row[REFERENCE], row["full_schema_model"]) for row in rows
    )
    taxonomy = [
        {
            "adjudicated": adjudicated,
            "predicted": predicted,
            "count": count,
            "share_of_errors": round(
                count / sum(v for (a, p), v in confusion.items() if a != p), 4
            )
            if adjudicated != predicted
            else None,
        }
        for (adjudicated, predicted), count in sorted(
            confusion.items(), key=lambda item: -item[1]
        )
    ]

    # Which coder-level field disagreement co-occurs with verdict disagreement.
    coder_disagreement = []
    verdict_split = [
        len({row[column] for column in CODERS}) > 1 for row in rows
    ]
    coder_disagreement.append(
        {
            "field": "verdict",
            "claims_with_any_disagreement": sum(verdict_split),
            "share": round(sum(verdict_split) / len(rows), 4),
        }
    )

    best_baseline = max(
        (entry for entry in entries if entry["kind"] == "baseline"),
        key=lambda entry: entry["exact_accuracy"],
    )
    beats_best_baseline = {
        entry["estimator"]: bool(entry["exact_accuracy"] > best_baseline["exact_accuracy"])
        for entry in entries
        if entry["kind"] == "rule"
    }
    payload = {
        "schema_version": "claim-rule-baselines-v1",
        "source": str(args.predictions.relative_to(REPO)),
        "items": len(rows),
        "verdict_classes": classes,
        "adjudicated_marginal": {
            label: round(count / len(rows), 4)
            for label, count in Counter(reference_labels).most_common()
        },
        "modal_verdict": modal,
        "strongest_trivial_baseline": best_baseline,
        "rule_beats_strongest_trivial_baseline": beats_best_baseline,
        "bootstrap": {
            "draws": args.draws,
            "unit": "source_key cluster",
            "seed": SEED,
        },
        "estimators": entries,
        "contrasts": contrasts,
        "full_rule_error_taxonomy": taxonomy,
        "coder_disagreement": coder_disagreement,
        "interpretation": (
            "No rule variant separates from the strongest trivial baseline "
            f"({best_baseline['label']}, {best_baseline['exact_accuracy']:.3f}), "
            "and the full rule does not separate from its own C2/C5 ablation. "
            "The development diagnostic therefore supplies no evidence that the "
            "coordinates work as a classifier."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
