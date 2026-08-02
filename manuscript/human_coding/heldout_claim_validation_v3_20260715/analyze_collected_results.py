#!/usr/bin/env python3
"""Run the preregistered held-out analysis using only the Python standard library."""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import math
import random
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PACKAGE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PACKAGE / "analysis_outputs"
ARMS = ("A", "B", "C", "D")
OUTPUTS = ("evidence_support", "comparability")
BOOTSTRAP_SEED = 2026071504
BOOTSTRAP_REPLICATES = 100_000
ALPHA = 0.05
EQUIVALENCE_MARGIN = 0.10
MISSINGNESS_THRESHOLD = 0.05
EVIDENCE_LABELS = {
    "supported_as_written",
    "supported_after_narrowing",
    "contradicted",
    "insufficient_source_evidence",
}
COMPARABILITY_LABELS = {
    "same_estimand",
    "comparable_with_declared_scope",
    "different_estimand",
    "missing_comparison_assumption",
    "not_a_comparability_claim",
}
CLAIM_LEVEL_HEADER = (
    "claim_id",
    "source_key",
    "primary_stratum",
    "gold_evidence_support_status",
    "gold_evidence_support_label",
    "gold_comparability_status",
    "gold_comparability_label",
    "arm_A_evidence_support_majority",
    "arm_A_evidence_support_accuracy",
    "arm_A_evidence_support_no_consensus",
    "arm_A_comparability_majority",
    "arm_A_comparability_accuracy",
    "arm_A_comparability_no_consensus",
    "arm_B_evidence_support_majority",
    "arm_B_evidence_support_accuracy",
    "arm_B_evidence_support_no_consensus",
    "arm_B_comparability_majority",
    "arm_B_comparability_accuracy",
    "arm_B_comparability_no_consensus",
    "arm_C_evidence_support_majority",
    "arm_C_evidence_support_accuracy",
    "arm_C_evidence_support_no_consensus",
    "arm_C_comparability_majority",
    "arm_C_comparability_accuracy",
    "arm_C_comparability_no_consensus",
    "arm_D_evidence_support_majority",
    "arm_D_evidence_support_accuracy",
    "arm_D_evidence_support_no_consensus",
    "arm_D_comparability_majority",
    "arm_D_comparability_accuracy",
    "arm_D_comparability_no_consensus",
)
PAIRWISE_HEADER = (
    "family",
    "outcome",
    "contrast",
    "stratum",
    "claims",
    "sources",
    "difference",
    "cr1_se",
    "degrees_freedom",
    "p_two_sided",
    "ci95_low",
    "ci95_high",
    "holm_adjusted_p",
)
FIELD_DIAGNOSTIC_HEADER = (
    "arm_or_role",
    "field",
    "completed_rows",
    "nonempty_rows",
    "nonempty_rate",
)
GOLD_RESOLUTION_HEADER = (
    "claim_id",
    "source_key",
    "output",
    "status",
    "resolved_label",
    "resolution_method",
)
INDIVIDUAL_RATER_HEADER = (
    "participant_id",
    "arm",
    "output",
    "completed_ratings",
    "accuracy_denominator",
    "correct",
    "accuracy",
)
RATER_SENSITIVITY_HEADER = (
    "analysis",
    "status",
    "arm",
    "output",
    "participant_id",
    "n",
    "estimate",
    "minimum",
    "median",
    "maximum",
    "standard_error",
    "degrees_freedom",
    "p_two_sided",
    "permutations",
    "reason",
)
AGREEMENT_HEADER = (
    "arm",
    "output",
    "status",
    "complete_three_vote_claims",
    "raw_pairwise_agreement",
    "fleiss_kappa",
    "reason",
)
CONFUSION_HEADER = (
    "row_type",
    "arm",
    "output",
    "gold_label",
    "arm_label",
    "count",
    "denominator",
    "rate",
)
RESPONSE_DIAGNOSTIC_HEADER = (
    "diagnostic",
    "arm",
    "stage",
    "value",
    "count",
    "denominator",
    "rate",
    "n_valid",
    "median_seconds",
    "q1_seconds",
    "q3_seconds",
    "iqr_seconds",
    "missing_count",
    "invalid_count",
    "negative_count",
)
MISSINGNESS_PATTERN_HEADER = (
    "source_key",
    "primary_stratum",
    "output",
    "resolution_method",
    "arm",
    "claims",
    "unresolved_gold_count",
    "arm_missing_count",
)
PUBLIC_ARM_HEADER = (
    "claim_id",
    "source_key",
    "release_participant_id",
    "arm",
    "role",
    "response_status",
    "missing_reason_code",
    "evidence_support_label",
    "comparability_label",
)
PUBLIC_GOLD_HEADER = (
    "claim_id",
    "source_key",
    "release_participant_id",
    "arm",
    "role",
    "response_status",
    "missing_reason_code",
    "evidence_support_label",
    "comparability_label",
)
PUBLIC_ADJUDICATION_HEADER = (
    "claim_id",
    "source_key",
    "release_participant_id",
    "arm",
    "role",
    "response_status",
    "missing_reason_code",
    "adjudicated_evidence_support_label",
    "adjudicated_comparability_label",
    "disputed_outputs",
)


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def write_csv(
    path: Path, header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    with staging.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    staging.replace(path)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    staging.replace(path)


def beta_continued_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations = 300
    epsilon = 3.0e-14
    floor = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < floor:
        d = floor
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        m2 = 2 * iteration
        numerator = (
            iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        )
        d = 1.0 + numerator * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + numerator / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        result *= d * c
        numerator = -(
            (a + iteration)
            * (qab + iteration)
            * x
            / ((a + m2) * (qap + m2))
        )
        d = 1.0 + numerator * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + numerator / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            return result
    raise ArithmeticError("incomplete beta continued fraction did not converge")


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_term = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    factor = math.exp(log_term)
    if x < (a + 1.0) / (a + b + 2.0):
        return factor * beta_continued_fraction(a, b, x) / a
    return 1.0 - factor * beta_continued_fraction(b, a, 1.0 - x) / b


def student_t_cdf(value: float, degrees_freedom: int) -> float:
    if degrees_freedom <= 0:
        raise ValueError("degrees of freedom must be positive")
    if value == 0.0:
        return 0.5
    x = degrees_freedom / (degrees_freedom + value * value)
    tail = 0.5 * regularized_incomplete_beta(
        degrees_freedom / 2.0, 0.5, x
    )
    return 1.0 - tail if value > 0 else tail


def student_t_quantile(probability: float, degrees_freedom: int) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must lie in (0,1)")
    if probability == 0.5:
        return 0.0
    if probability < 0.5:
        return -student_t_quantile(1.0 - probability, degrees_freedom)
    low = 0.0
    high = 1.0
    while student_t_cdf(high, degrees_freedom) < probability:
        high *= 2.0
        if high > 1.0e6:
            raise ArithmeticError("t quantile bracket failed")
    for _ in range(100):
        midpoint = (low + high) / 2.0
        if student_t_cdf(midpoint, degrees_freedom) < probability:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot take percentile of an empty sequence")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def cr1_intercept_statistics(
    observations: Sequence[tuple[str, float]]
) -> dict[str, float | int]:
    if not observations:
        raise ValueError("no observations for cluster-robust estimate")
    values = [value for _source, value in observations]
    estimate = sum(values) / len(values)
    cluster_residual_sums: dict[str, float] = defaultdict(float)
    for source, value in observations:
        cluster_residual_sums[source] += value - estimate
    clusters = len(cluster_residual_sums)
    if clusters < 2:
        raise ValueError("CR1 inference requires at least two source clusters")
    meat = sum(value * value for value in cluster_residual_sums.values())
    cr1_factor = clusters / (clusters - 1)
    variance = cr1_factor * meat / (len(values) * len(values))
    standard_error = math.sqrt(max(variance, 0.0))
    degrees_freedom = clusters - 1
    if standard_error == 0.0:
        t_statistic = (
            0.0 if estimate == 0.0 else math.copysign(math.inf, estimate)
        )
        p_value = 1.0 if estimate == 0.0 else 0.0
    else:
        t_statistic = estimate / standard_error
        p_value = 2.0 * (
            1.0 - student_t_cdf(abs(t_statistic), degrees_freedom)
        )
    critical_95 = student_t_quantile(0.975, degrees_freedom)
    critical_90 = student_t_quantile(0.95, degrees_freedom)
    return {
        "claims": len(values),
        "sources": clusters,
        "estimate": estimate,
        "cr1_se": standard_error,
        "degrees_freedom": degrees_freedom,
        "t_statistic": t_statistic,
        "p_two_sided": max(0.0, min(1.0, p_value)),
        "ci95_low": estimate - critical_95 * standard_error,
        "ci95_high": estimate + critical_95 * standard_error,
        "ci90_low": estimate - critical_90 * standard_error,
        "ci90_high": estimate + critical_90 * standard_error,
    }


def source_cluster_bootstrap(
    observations: Sequence[tuple[str, float]],
    replicates: int,
    seed: int,
) -> tuple[float, float]:
    by_source: dict[str, list[float]] = defaultdict(list)
    for source, value in observations:
        by_source[source].append(value)
    clusters = sorted(by_source)
    cluster_sums = [sum(by_source[source]) for source in clusters]
    cluster_counts = [len(by_source[source]) for source in clusters]
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        total = 0.0
        count = 0
        for _cluster in clusters:
            index = rng.randrange(len(clusters))
            total += cluster_sums[index]
            count += cluster_counts[index]
        estimates.append(total / count)
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def exact_label_set(output: str) -> set[str]:
    return EVIDENCE_LABELS if output == "evidence_support" else COMPARABILITY_LABELS


def unique_adjudicator_claim_map(
    rows: Sequence[Mapping[str, str]], name: str
) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        claim_id = (row.get("claim_id") or "").strip()
        if not claim_id:
            raise ValueError(f"{name} row {index} has an empty claim_id")
        if claim_id in result:
            raise ValueError(
                f"{name} contains duplicate claim {claim_id}; "
                "last-row-wins adjudication is forbidden"
            )
        result[claim_id] = row
    return result


def adjudication_eligible_claims(
    gold_by_claim: Mapping[str, Sequence[Mapping[str, str]]],
) -> set[str]:
    eligible: set[str] = set()
    for claim_id, experts in gold_by_claim.items():
        completed = [
            row
            for row in experts
            if (row.get("response_status") or "").strip() == "completed"
        ]
        if len(completed) < 3:
            continue
        if len(completed) != 3 or len(
            {
                (row.get("participant_id") or "").strip()
                for row in completed
            }
        ) != 3:
            raise ValueError(
                f"claim {claim_id} has invalid completed gold multiplicity"
            )
        disputed = False
        for output in OUTPUTS:
            label_field = (
                "evidence_support_label"
                if output == "evidence_support"
                else "comparability_label"
            )
            labels = [
                (row.get(label_field) or "").strip() for row in completed
            ]
            if any(label not in exact_label_set(output) for label in labels):
                raise ValueError(f"claim {claim_id} has an invalid gold label")
            disputed = disputed or len(set(labels)) > 1
        if disputed:
            eligible.add(claim_id)
    return eligible


def resolve_gold(
    frozen_rows: Sequence[Mapping[str, str]],
    gold_rows: Sequence[Mapping[str, str]],
    adjudicator_1_rows: Sequence[Mapping[str, str]],
    adjudicator_2_rows: Sequence[Mapping[str, str]],
) -> tuple[
    dict[tuple[str, str], dict[str, str]], list[dict[str, object]]
]:
    gold_by_claim: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in gold_rows:
        gold_by_claim[(row.get("claim_id") or "").strip()].append(row)
    adjudicator_maps = [
        unique_adjudicator_claim_map(
            adjudicator_1_rows, "adjudicator_1_responses.csv"
        ),
        unique_adjudicator_claim_map(
            adjudicator_2_rows, "adjudicator_2_responses.csv"
        ),
    ]
    eligible_claims = adjudication_eligible_claims(gold_by_claim)
    for number, adjudicator_map in enumerate(adjudicator_maps, start=1):
        if set(adjudicator_map) != eligible_claims:
            raise ValueError(
                f"adjudicator_{number}_responses.csv must contain exactly "
                "one row for every complete-gold disagreement and none for "
                "incomplete or non-disputed claims"
            )
    result: dict[tuple[str, str], dict[str, str]] = {}
    audit_rows: list[dict[str, object]] = []
    for frozen in frozen_rows:
        claim_id = (frozen.get("claim_id") or "").strip()
        source_key = (frozen.get("source_key") or "").strip()
        experts = gold_by_claim.get(claim_id, [])
        completed_experts = [
            row
            for row in experts
            if (row.get("response_status") or "").strip() == "completed"
        ]
        for output in OUTPUTS:
            label_field = (
                "evidence_support_label"
                if output == "evidence_support"
                else "comparability_label"
            )
            valid_labels = exact_label_set(output)
            expert_labels = [
                (row.get(label_field) or "").strip()
                for row in completed_experts
            ]
            independent_experts = (
                len(completed_experts) == 3
                and len(
                    {
                        (row.get("participant_id") or "").strip()
                        for row in completed_experts
                    }
                )
                == 3
            )
            status = (
                "unresolved_incomplete_gold"
                if len(completed_experts) < 3
                else "unresolved"
            )
            label = ""
            method = (
                "unresolved_incomplete_gold"
                if len(completed_experts) < 3
                else "unresolved_invalid_gold"
            )
            if (
                independent_experts
                and len(expert_labels) == 3
                and all(value in valid_labels for value in expert_labels)
                and len(set(expert_labels)) == 1
            ):
                status = "resolved"
                label = expert_labels[0]
                method = "unanimous_three_experts"
            elif (
                independent_experts
                and len(expert_labels) == 3
                and all(value in valid_labels for value in expert_labels)
            ):
                adjudicated_field = (
                    "adjudicated_evidence_support_label"
                    if output == "evidence_support"
                    else "adjudicated_comparability_label"
                )
                decisions: list[str] = []
                complete = True
                for adjudicator_map in adjudicator_maps:
                    row = adjudicator_map.get(claim_id)
                    if (
                        row is None
                        or (row.get("response_status") or "").strip() != "completed"
                    ):
                        complete = False
                        continue
                    decision = (row.get(adjudicated_field) or "").strip()
                    if decision not in valid_labels:
                        complete = False
                    decisions.append(decision)
                if complete and len(decisions) == 2 and len(set(decisions)) == 1:
                    status = "resolved"
                    label = decisions[0]
                    method = "two_independent_adjudicators_agree"
                else:
                    method = "adjudicators_disagree_or_unable"
            result[(claim_id, output)] = {
                "status": status,
                "label": label,
                "method": method,
            }
            audit_rows.append(
                {
                    "claim_id": claim_id,
                    "source_key": source_key,
                    "output": output,
                    "status": status,
                    "resolved_label": label,
                    "resolution_method": method,
                }
            )
    return result, audit_rows


def strict_majority(
    rows: Sequence[Mapping[str, str]], output: str
) -> dict[str, object]:
    label_field = (
        "evidence_support_label"
        if output == "evidence_support"
        else "comparability_label"
    )
    valid = exact_label_set(output)
    if len(rows) != 3:
        return {"status": "missing", "label": "", "no_consensus": False}
    labels = []
    for row in rows:
        if (row.get("response_status") or "").strip() != "completed":
            return {"status": "missing", "label": "", "no_consensus": False}
        label = (row.get(label_field) or "").strip()
        if label not in valid:
            return {"status": "missing", "label": "", "no_consensus": False}
        labels.append(label)
    counts = Counter(labels)
    label, count = counts.most_common(1)[0]
    if count >= 2:
        return {"status": "majority", "label": label, "no_consensus": False}
    return {"status": "no_consensus", "label": "", "no_consensus": True}


def primary_complete_case_rows(
    claims: Mapping[str, Mapping[str, str]],
    gold: Mapping[tuple[str, str], Mapping[str, str]],
    arm_results: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    for claim_id, claim in claims.items():
        reference = gold[(claim_id, "comparability")]
        c_accuracy = arm_results[(claim_id, "C", "comparability")]["accuracy"]
        d_accuracy = arm_results[(claim_id, "D", "comparability")]["accuracy"]
        if (
            reference["status"] == "resolved"
            and c_accuracy is not None
            and d_accuracy is not None
        ):
            rows.append(
                (
                    claim_id,
                    (claim.get("source_key") or "").strip(),
                    float(d_accuracy) - float(c_accuracy),
                )
            )
    return rows


def primary_missingness_bounds(
    claims: Mapping[str, Mapping[str, str]],
    gold: Mapping[tuple[str, str], Mapping[str, str]],
    arm_results: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> dict[str, float | int]:
    lower_sum = 0.0
    upper_sum = 0.0
    missing_claims = 0
    for claim_id in claims:
        reference = gold[(claim_id, "comparability")]
        c_accuracy = arm_results[(claim_id, "C", "comparability")]["accuracy"]
        d_accuracy = arm_results[(claim_id, "D", "comparability")]["accuracy"]
        if (
            reference["status"] != "resolved"
            or (c_accuracy is None and d_accuracy is None)
        ):
            lower, upper = -1.0, 1.0
        elif c_accuracy is None:
            lower, upper = float(d_accuracy) - 1.0, float(d_accuracy)
        elif d_accuracy is None:
            lower, upper = -float(c_accuracy), 1.0 - float(c_accuracy)
        else:
            lower = upper = float(d_accuracy) - float(c_accuracy)
        lower_sum += lower
        upper_sum += upper
        missing_claims += int(c_accuracy is None or d_accuracy is None)
    denominator = len(claims)
    return {
        "worst_case": lower_sum / denominator,
        "best_case": upper_sum / denominator,
        "missing_claims": missing_claims,
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (key, p_value) in enumerate(ordered):
        candidate = min(1.0, (total - index) * p_value)
        running = max(running, candidate)
        adjusted[key] = running
    return adjusted


def pairwise_row(
    family: str,
    output: str,
    contrast: str,
    stratum: str,
    observations: Sequence[tuple[str, float]],
) -> dict[str, object]:
    source_count = len({source for source, _value in observations})
    if not observations or source_count < 2:
        return {
            "family": family,
            "outcome": output,
            "contrast": contrast,
            "stratum": stratum,
            "claims": len(observations),
            "sources": source_count,
            "difference": "",
            "cr1_se": "",
            "degrees_freedom": "",
            "p_two_sided": 1.0,
            "ci95_low": "",
            "ci95_high": "",
            "holm_adjusted_p": "",
        }
    statistics = cr1_intercept_statistics(observations)
    return {
        "family": family,
        "outcome": output,
        "contrast": contrast,
        "stratum": stratum,
        "claims": statistics["claims"],
        "sources": statistics["sources"],
        "difference": statistics["estimate"],
        "cr1_se": statistics["cr1_se"],
        "degrees_freedom": statistics["degrees_freedom"],
        "p_two_sided": statistics["p_two_sided"],
        "ci95_low": statistics["ci95_low"],
        "ci95_high": statistics["ci95_high"],
        "holm_adjusted_p": "",
    }


def extraction_fields(header: Sequence[str], role: str) -> list[str]:
    if role in ARMS:
        start = header.index("extraction_completed_utc")
        end = header.index("composition_started_utc")
        return list(header[start:end])
    if role == "gold":
        start = header.index("review_started_utc") + 1
        end = header.index("composition_started_utc")
        return list(header[start:end])
    return []


def _summary(values: Sequence[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "median": percentile(values, 0.5),
        "maximum": max(values),
    }


def individual_rater_outputs(
    arm_rows: Mapping[str, Sequence[Mapping[str, str]]],
    gold: Mapping[tuple[str, str], Mapping[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    accumulators: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    completed: Counter[tuple[str, str, str]] = Counter()
    for arm in ARMS:
        for row in arm_rows[arm]:
            participant = (row.get("participant_id") or "").strip()
            if not participant:
                continue
            claim_id = (row.get("claim_id") or "").strip()
            for output in OUTPUTS:
                key = (participant, arm, output)
                label_field = (
                    "evidence_support_label"
                    if output == "evidence_support"
                    else "comparability_label"
                )
                label = (row.get(label_field) or "").strip()
                if (
                    (row.get("response_status") or "").strip() == "completed"
                    and label in exact_label_set(output)
                ):
                    completed[key] += 1
                    reference = gold.get((claim_id, output), {})
                    if reference.get("status") == "resolved":
                        accumulators[key].append(
                            int(label == reference.get("label"))
                        )
    keys = sorted(set(completed) | set(accumulators))
    individual: list[dict[str, object]] = []
    for participant, arm, output in keys:
        scores = accumulators[(participant, arm, output)]
        individual.append(
            {
                "participant_id": participant,
                "arm": arm,
                "output": output,
                "completed_ratings": completed[(participant, arm, output)],
                "accuracy_denominator": len(scores),
                "correct": sum(scores),
                "accuracy": sum(scores) / len(scores) if scores else "",
            }
        )
    sensitivity: list[dict[str, object]] = []
    for arm in ARMS:
        for output in OUTPUTS:
            values = [
                float(row["accuracy"])
                for row in individual
                if row["arm"] == arm
                and row["output"] == output
                and row["accuracy"] != ""
            ]
            row: dict[str, object] = {
                "analysis": "participant_accuracy_summary",
                "status": "estimated" if values else "not_estimable",
                "arm": arm,
                "output": output,
                "participant_id": "",
                "n": len(values),
                "estimate": sum(values) / len(values) if values else "",
                "minimum": "",
                "median": "",
                "maximum": "",
                "standard_error": "",
                "degrees_freedom": "",
                "p_two_sided": "",
                "permutations": "",
                "reason": "" if values else "no participant has resolved-gold ratings",
            }
            if values:
                row.update(_summary(values))
            sensitivity.append(row)
    return individual, sensitivity


def conditional_arm_label_permutation(
    individual_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    rows = [
        row
        for row in individual_rows
        if row["arm"] in {"C", "D"}
        and row["output"] == "comparability"
        and row["accuracy"] != ""
    ]
    participants = [str(row["participant_id"]) for row in rows]
    c_count = sum(row["arm"] == "C" for row in rows)
    d_count = sum(row["arm"] == "D" for row in rows)
    if len(rows) != 12 or c_count != 6 or d_count != 6:
        return {
            "status": "not_estimable",
            "n": len(rows),
            "reason": (
                "conditional sensitivity requires exactly 12 realized "
                "participants with six in each of C and D"
            ),
        }
    if len(set(participants)) != 12:
        return {
            "status": "not_estimable",
            "n": len(rows),
            "reason": "participant IDs are not unique across realized C/D auditors",
        }
    values = [float(row["accuracy"]) for row in rows]
    observed = (
        sum(float(row["accuracy"]) for row in rows if row["arm"] == "D") / 6
        - sum(float(row["accuracy"]) for row in rows if row["arm"] == "C") / 6
    )
    extreme = 0
    permutations = 0
    for d_indices in combinations(range(12), 6):
        selected = set(d_indices)
        difference = (
            sum(values[index] for index in selected) / 6
            - sum(values[index] for index in range(12) if index not in selected)
            / 6
        )
        permutations += 1
        if abs(difference) >= abs(observed) - 1.0e-15:
            extreme += 1
    return {
        "status": "estimated",
        "n": 12,
        "estimate": observed,
        "p_two_sided": extreme / permutations,
        "permutations": permutations,
        "reason": (
            "post hoc conditional arm-label permutation sensitivity; "
            "not the majority endpoint's exact design-based test"
        ),
    }


def _matrix_product_2(
    left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]
) -> list[list[float]]:
    return [
        [
            sum(left[i][k] * right[k][j] for k in range(2))
            for j in range(2)
        ]
        for i in range(2)
    ]


def two_way_cluster_ols(
    observations: Sequence[tuple[str, str, float, float]],
) -> dict[str, object]:
    n = len(observations)
    k = 2
    d_sum = sum(d for _source, _auditor, _y, d in observations)
    determinant = n * d_sum - d_sum * d_sum
    source_count = len({source for source, _auditor, _y, _d in observations})
    auditor_count = len(
        {auditor for _source, auditor, _y, _d in observations}
    )
    if (
        n <= k
        or determinant == 0.0
        or source_count < 2
        or auditor_count < 2
    ):
        return {
            "status": "not_estimable",
            "n": n,
            "sources": source_count,
            "auditors": auditor_count,
            "reason": (
                "OLS requires both arms, N>K, and at least two source and "
                "auditor clusters"
            ),
        }
    inverse = [
        [d_sum / determinant, -d_sum / determinant],
        [-d_sum / determinant, n / determinant],
    ]
    xy = [
        sum(y for _source, _auditor, y, _d in observations),
        sum(y * d for _source, _auditor, y, d in observations),
    ]
    beta = [
        sum(inverse[i][j] * xy[j] for j in range(2)) for i in range(2)
    ]
    scored: list[tuple[str, str, tuple[str, str], float, float]] = []
    for source, auditor, y, d in observations:
        residual = y - beta[0] - beta[1] * d
        scored.append((source, auditor, (source, auditor), residual, d * residual))

    def meat(group_index: int) -> tuple[list[list[float]], int, float]:
        grouped: dict[object, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for item in scored:
            group = item[group_index]
            grouped[group][0] += item[3]
            grouped[group][1] += item[4]
        groups = len(grouped)
        if groups < 2:
            raise ValueError("cluster meat requires at least two groups")
        factor = groups / (groups - 1) * (n - 1) / (n - k)
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        for score in grouped.values():
            for i in range(2):
                for j in range(2):
                    matrix[i][j] += score[i] * score[j] * factor
        return matrix, groups, factor

    source_meat, _g_source, source_factor = meat(0)
    auditor_meat, _g_auditor, auditor_factor = meat(1)
    intersection_meat, intersection_count, intersection_factor = meat(2)
    cgm_meat = [
        [
            source_meat[i][j]
            + auditor_meat[i][j]
            - intersection_meat[i][j]
            for j in range(2)
        ]
        for i in range(2)
    ]
    covariance = _matrix_product_2(
        _matrix_product_2(inverse, cgm_meat), inverse
    )
    variance = covariance[1][1]
    base = {
        "n": n,
        "sources": source_count,
        "auditors": auditor_count,
        "intersection_clusters": intersection_count,
        "estimate": beta[1],
        "variance": variance,
        "source_cr1_factor": source_factor,
        "auditor_cr1_factor": auditor_factor,
        "intersection_cr1_factor": intersection_factor,
        "cr1_definition": "G/(G-1) * (N-1)/(N-K), separately for each meat",
        "covariance_definition": "CGM V_source + V_auditor - V_intersection",
    }
    if not math.isfinite(variance):
        return {
            **base,
            "status": "not_estimable",
            "reason": "two-way cluster variance is non-finite",
        }
    if variance < 0.0:
        return {
            **base,
            "status": "negative_variance",
            "reason": (
                "CGM coefficient variance is negative; no standard error, "
                "test, or interval is reported"
            ),
        }
    standard_error = math.sqrt(variance)
    degrees_freedom = min(source_count - 1, auditor_count - 1)
    if standard_error == 0.0:
        p_value = 1.0 if beta[1] == 0.0 else 0.0
    else:
        p_value = 2.0 * (
            1.0
            - student_t_cdf(abs(beta[1] / standard_error), degrees_freedom)
        )
    return {
        **base,
        "status": "estimated",
        "standard_error": standard_error,
        "degrees_freedom": degrees_freedom,
        "p_two_sided": max(0.0, min(1.0, p_value)),
    }


def changed_aggregation_majority(
    rows: Sequence[Mapping[str, str]], output: str
) -> dict[str, object]:
    if len(rows) == 3:
        return strict_majority(rows, output)
    if len(rows) != 2:
        return {"status": "missing", "label": "", "no_consensus": False}
    label_field = (
        "evidence_support_label"
        if output == "evidence_support"
        else "comparability_label"
    )
    labels = []
    for row in rows:
        label = (row.get(label_field) or "").strip()
        if (
            (row.get("response_status") or "").strip() != "completed"
            or label not in exact_label_set(output)
        ):
            return {"status": "missing", "label": "", "no_consensus": False}
        labels.append(label)
    if labels[0] == labels[1]:
        return {"status": "majority", "label": labels[0], "no_consensus": False}
    return {"status": "no_consensus", "label": "", "no_consensus": True}


def leave_one_auditor_out(
    claims: Mapping[str, Mapping[str, str]],
    responses: Mapping[str, Mapping[str, Sequence[Mapping[str, str]]]],
    gold: Mapping[tuple[str, str], Mapping[str, str]],
) -> list[dict[str, object]]:
    participants = sorted(
        {
            ((row.get("participant_id") or "").strip(), arm)
            for arm in ("C", "D")
            for rows in responses[arm].values()
            for row in rows
            if (row.get("participant_id") or "").strip()
        },
        key=lambda item: (item[1], item[0]),
    )
    rows: list[dict[str, object]] = []
    design_ok = (
        len(participants) == 12
        and sum(arm == "C" for _participant, arm in participants) == 6
        and sum(arm == "D" for _participant, arm in participants) == 6
    )
    for omitted, omitted_arm in participants:
        differences: list[float] = []
        for claim_id in claims:
            reference = gold[(claim_id, "comparability")]
            if reference["status"] != "resolved":
                continue
            accuracies: dict[str, int] = {}
            usable = True
            for arm in ("C", "D"):
                retained = [
                    row
                    for row in responses[arm].get(claim_id, [])
                    if not (
                        arm == omitted_arm
                        and (row.get("participant_id") or "").strip() == omitted
                    )
                ]
                aggregate = changed_aggregation_majority(
                    retained, "comparability"
                )
                if aggregate["status"] == "missing":
                    usable = False
                    break
                accuracies[arm] = int(
                    aggregate["status"] == "majority"
                    and aggregate["label"] == reference["label"]
                )
            if usable:
                differences.append(float(accuracies["D"] - accuracies["C"]))
        rows.append(
            {
                "analysis": "leave_one_auditor_out_changed_aggregation",
                "status": "estimated" if differences and design_ok else "not_estimable",
                "arm": omitted_arm,
                "output": "comparability",
                "participant_id": omitted,
                "n": len(differences),
                "estimate": (
                    sum(differences) / len(differences)
                    if differences and design_ok
                    else ""
                ),
                "minimum": "",
                "median": "",
                "maximum": "",
                "standard_error": "",
                "degrees_freedom": "",
                "p_two_sided": "",
                "permutations": "",
                "reason": (
                    "post hoc changed-aggregation sensitivity: after deletion, "
                    "two retained votes label only when unanimous; disagreement "
                    "is no_consensus and accuracy 0"
                    if differences and design_ok
                    else "requires the realized six-auditor-per-arm C/D design"
                ),
            }
        )
    return rows


def agreement_outputs(
    responses: Mapping[str, Mapping[str, Sequence[Mapping[str, str]]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm in ARMS:
        for output in OUTPUTS:
            label_field = (
                "evidence_support_label"
                if output == "evidence_support"
                else "comparability_label"
            )
            claim_counts: list[Counter[str]] = []
            for claim_rows in responses[arm].values():
                if len(claim_rows) != 3:
                    continue
                labels = [
                    (row.get(label_field) or "").strip() for row in claim_rows
                ]
                if all(
                    (row.get("response_status") or "").strip() == "completed"
                    for row in claim_rows
                ) and all(label in exact_label_set(output) for label in labels):
                    claim_counts.append(Counter(labels))
            if not claim_counts:
                rows.append(
                    {
                        "arm": arm,
                        "output": output,
                        "status": "not_estimable",
                        "complete_three_vote_claims": 0,
                        "raw_pairwise_agreement": "",
                        "fleiss_kappa": "",
                        "reason": "no complete claims with exactly three valid votes",
                    }
                )
                continue
            agreements = [
                sum(count * (count - 1) for count in counts.values()) / 6
                for counts in claim_counts
            ]
            raw = sum(agreements) / len(agreements)
            totals: Counter[str] = Counter()
            for counts in claim_counts:
                totals.update(counts)
            denominator = 3 * len(claim_counts)
            expected = sum(
                (totals[label] / denominator) ** 2
                for label in exact_label_set(output)
            )
            if expected == 1.0:
                status = "not_estimable"
                kappa: float | str = ""
                reason = "all ratings occupy one category, so 1-P_e is zero"
            else:
                status = "estimated"
                kappa = (raw - expected) / (1.0 - expected)
                reason = ""
            rows.append(
                {
                    "arm": arm,
                    "output": output,
                    "status": status,
                    "complete_three_vote_claims": len(claim_counts),
                    "raw_pairwise_agreement": raw,
                    "fleiss_kappa": kappa,
                    "reason": reason,
                }
            )
    return rows


def strict_iso_utc(value: str) -> datetime | None:
    if not value or value != value.strip() or "T" not in value:
        return None
    if not (value.endswith("Z") or value.endswith("+00:00")):
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return parsed


def response_diagnostics(
    arm_rows: Mapping[str, Sequence[Mapping[str, str]]],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    abstention_statuses = {
        "unable",
        "unable_to_determine",
        "abstained",
        "declined_to_answer",
    }
    for arm in ARMS:
        rows = arm_rows[arm]
        denominator = len(rows)
        statuses = Counter(
            (row.get("response_status") or "").strip() or "(missing)"
            for row in rows
        )
        reasons = Counter(
            (row.get("missing_reason_code") or "").strip() or "(missing)"
            for row in rows
        )
        for diagnostic, counts in (
            ("response_status", statuses),
            ("missing_reason_code", reasons),
        ):
            for value, count in sorted(counts.items()):
                output.append(
                    {
                        "diagnostic": diagnostic,
                        "arm": arm,
                        "stage": "",
                        "value": value,
                        "count": count,
                        "denominator": denominator,
                        "rate": count / denominator if denominator else "",
                        "n_valid": "",
                        "median_seconds": "",
                        "q1_seconds": "",
                        "q3_seconds": "",
                        "iqr_seconds": "",
                        "missing_count": "",
                        "invalid_count": "",
                        "negative_count": "",
                    }
                )
        abstentions = sum(
            status.lower() in abstention_statuses
            for status in (
                (row.get("response_status") or "").strip() for row in rows
            )
        )
        output.append(
            {
                "diagnostic": "unable_or_abstention",
                "arm": arm,
                "stage": "",
                "value": "defined_status_set",
                "count": abstentions,
                "denominator": denominator,
                "rate": abstentions / denominator if denominator else "",
                "n_valid": "",
                "median_seconds": "",
                "q1_seconds": "",
                "q3_seconds": "",
                "iqr_seconds": "",
                "missing_count": "",
                "invalid_count": "",
                "negative_count": "",
            }
        )
        stages = (
            ("extraction", "extraction_started_utc", "extraction_completed_utc"),
            ("composition", "composition_started_utc", "completed_utc"),
            ("total", "extraction_started_utc", "completed_utc"),
        )
        for stage, start_field, end_field in stages:
            durations: list[float] = []
            missing = invalid = negative = 0
            for row in rows:
                start_raw = row.get(start_field) or ""
                end_raw = row.get(end_field) or ""
                if not start_raw or not end_raw:
                    missing += 1
                    continue
                start = strict_iso_utc(start_raw)
                end = strict_iso_utc(end_raw)
                if start is None or end is None:
                    invalid += 1
                    continue
                seconds = (end - start).total_seconds()
                if seconds < 0:
                    negative += 1
                else:
                    durations.append(seconds)
            q1 = percentile(durations, 0.25) if durations else ""
            q3 = percentile(durations, 0.75) if durations else ""
            output.append(
                {
                    "diagnostic": "row_elapsed_time",
                    "arm": arm,
                    "stage": stage,
                    "value": "seconds",
                    "count": "",
                    "denominator": denominator,
                    "rate": "",
                    "n_valid": len(durations),
                    "median_seconds": (
                        percentile(durations, 0.5) if durations else ""
                    ),
                    "q1_seconds": q1,
                    "q3_seconds": q3,
                    "iqr_seconds": q3 - q1 if durations else "",
                    "missing_count": missing,
                    "invalid_count": invalid,
                    "negative_count": negative,
                }
            )
    return output


def confusion_outputs(
    claims: Mapping[str, Mapping[str, str]],
    gold: Mapping[tuple[str, str], Mapping[str, str]],
    arm_results: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm in ARMS:
        for output in OUTPUTS:
            distributions: Counter[str] = Counter()
            confusion: Counter[tuple[str, str]] = Counter()
            for claim_id in claims:
                result = arm_results[(claim_id, arm, output)]
                arm_label = (
                    str(result["label"])
                    if result["status"] == "majority"
                    else str(result["status"])
                )
                distributions[arm_label] += 1
                reference = gold[(claim_id, output)]
                if reference["status"] == "resolved":
                    confusion[(str(reference["label"]), arm_label)] += 1
            distribution_n = sum(distributions.values())
            arm_categories = sorted(
                exact_label_set(output) | {"missing", "no_consensus"}
            )
            for arm_label in arm_categories:
                count = distributions[arm_label]
                rows.append(
                    {
                        "row_type": "class_distribution",
                        "arm": arm,
                        "output": output,
                        "gold_label": "",
                        "arm_label": arm_label,
                        "count": count,
                        "denominator": distribution_n,
                        "rate": count / distribution_n if distribution_n else "",
                    }
                )
            confusion_n = sum(confusion.values())
            for gold_label in sorted(exact_label_set(output)):
                for arm_label in arm_categories:
                    count = confusion[(gold_label, arm_label)]
                    rows.append(
                        {
                            "row_type": "resolved_gold_confusion",
                            "arm": arm,
                            "output": output,
                            "gold_label": gold_label,
                            "arm_label": arm_label,
                            "count": count,
                            "denominator": confusion_n,
                            "rate": (
                                count / confusion_n if confusion_n else ""
                            ),
                        }
                    )
    return rows


def missingness_pattern_outputs(
    claims: Mapping[str, Mapping[str, str]],
    gold: Mapping[tuple[str, str], Mapping[str, str]],
    arm_results: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str, str, str], list[int]] = defaultdict(
        lambda: [0, 0, 0]
    )
    for claim_id, claim in claims.items():
        source = (claim.get("source_key") or "").strip()
        stratum = (
            claim.get("coordinator_only_primary_stratum") or ""
        ).strip()
        for output in OUTPUTS:
            reference = gold[(claim_id, output)]
            for arm in ARMS:
                key = (
                    source,
                    stratum,
                    output,
                    str(reference["method"]),
                    arm,
                )
                groups[key][0] += 1
                groups[key][1] += int(reference["status"] != "resolved")
                groups[key][2] += int(
                    arm_results[(claim_id, arm, output)]["status"] == "missing"
                )
    return [
        {
            "source_key": key[0],
            "primary_stratum": key[1],
            "output": key[2],
            "resolution_method": key[3],
            "arm": key[4],
            "claims": counts[0],
            "unresolved_gold_count": counts[1],
            "arm_missing_count": counts[2],
        }
        for key, counts in sorted(groups.items())
    ]


def _release_id(key: bytes, role: str, arm: str, participant: str) -> str:
    digest = hmac.new(
        key,
        f"{role}|{arm}|{participant}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"release_{digest[:24]}"


def build_public_tables(
    key: bytes,
    frozen_rows: Sequence[Mapping[str, str]],
    arm_rows: Mapping[str, Sequence[Mapping[str, str]]],
    gold_rows: Sequence[Mapping[str, str]],
    adjudicator_1_rows: Sequence[Mapping[str, str]],
    adjudicator_2_rows: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, object]]]:
    if len(key) < 32:
        raise ValueError("deidentification key must contain at least 32 bytes")
    sources = {
        (row.get("claim_id") or "").strip(): (
            row.get("source_key") or ""
        ).strip()
        for row in frozen_rows
    }
    public_arms: list[dict[str, object]] = []
    for arm in ARMS:
        for row in arm_rows[arm]:
            participant = (row.get("participant_id") or "").strip()
            if not participant:
                raise ValueError("public arm release requires participant_id")
            claim_id = (row.get("claim_id") or "").strip()
            public_arms.append(
                {
                    "claim_id": claim_id,
                    "source_key": sources.get(claim_id, ""),
                    "release_participant_id": _release_id(
                        key, "auditor", arm, participant
                    ),
                    "arm": arm,
                    "role": "auditor",
                    "response_status": (
                        row.get("response_status") or ""
                    ).strip(),
                    "missing_reason_code": (
                        row.get("missing_reason_code") or ""
                    ).strip(),
                    "evidence_support_label": (
                        row.get("evidence_support_label") or ""
                    ).strip(),
                    "comparability_label": (
                        row.get("comparability_label") or ""
                    ).strip(),
                }
            )
    public_gold: list[dict[str, object]] = []
    for row in gold_rows:
        participant = (row.get("participant_id") or "").strip()
        if not participant:
            raise ValueError("public gold release requires participant_id")
        claim_id = (row.get("claim_id") or "").strip()
        public_gold.append(
            {
                "claim_id": claim_id,
                "source_key": sources.get(claim_id, ""),
                "release_participant_id": _release_id(
                    key, "gold", "", participant
                ),
                "arm": "",
                "role": "gold",
                "response_status": (row.get("response_status") or "").strip(),
                "missing_reason_code": (
                    row.get("missing_reason_code") or ""
                ).strip(),
                "evidence_support_label": (
                    row.get("evidence_support_label") or ""
                ).strip(),
                "comparability_label": (
                    row.get("comparability_label") or ""
                ).strip(),
            }
        )
    public_adjudications: list[dict[str, object]] = []
    for number, rows in (
        (1, adjudicator_1_rows),
        (2, adjudicator_2_rows),
    ):
        role = f"adjudicator_{number}"
        for row in rows:
            participant = (
                row.get("participant_id")
                or row.get("adjudicator_id")
                or role
            ).strip()
            claim_id = (row.get("claim_id") or "").strip()
            public_adjudications.append(
                {
                    "claim_id": claim_id,
                    "source_key": sources.get(claim_id, ""),
                    "release_participant_id": _release_id(
                        key, role, "", participant
                    ),
                    "arm": "",
                    "role": role,
                    "response_status": (
                        row.get("response_status") or ""
                    ).strip(),
                    "missing_reason_code": (
                        row.get("missing_reason_code") or ""
                    ).strip(),
                    "adjudicated_evidence_support_label": (
                        row.get("adjudicated_evidence_support_label") or ""
                    ).strip(),
                    "adjudicated_comparability_label": (
                        row.get("adjudicated_comparability_label") or ""
                    ).strip(),
                    "disputed_outputs": (
                        row.get("disputed_outputs") or ""
                    ).strip(),
                }
            )
    return {
        "public_arm_ratings": public_arms,
        "public_gold_ratings": public_gold,
        "public_adjudications": public_adjudications,
    }


def load_deidentification_key(path: Path) -> bytes:
    try:
        key = path.read_bytes()
    except OSError as exc:
        raise ValueError("deidentification key file cannot be read") from exc
    if len(key) < 32:
        raise ValueError("deidentification key must contain at least 32 bytes")
    return key


def analyze(
    frozen_rows: Sequence[Mapping[str, str]],
    arm_rows: Mapping[str, Sequence[Mapping[str, str]]],
    arm_headers: Mapping[str, Sequence[str]],
    gold_rows: Sequence[Mapping[str, str]],
    gold_header: Sequence[str],
    adjudicator_1_rows: Sequence[Mapping[str, str]],
    adjudicator_2_rows: Sequence[Mapping[str, str]],
    bootstrap_replicates: int,
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    if not frozen_rows:
        raise ValueError("no frozen claims")
    claims = {
        (row.get("claim_id") or "").strip(): row for row in frozen_rows
    }
    if len(claims) != len(frozen_rows):
        raise ValueError("duplicate frozen claim IDs")
    responses: dict[str, dict[str, list[Mapping[str, str]]]] = {}
    for arm in ARMS:
        grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
        for row in arm_rows[arm]:
            grouped[(row.get("claim_id") or "").strip()].append(row)
        responses[arm] = grouped

    gold, gold_audit = resolve_gold(
        frozen_rows, gold_rows, adjudicator_1_rows, adjudicator_2_rows
    )
    claim_rows: list[dict[str, object]] = []
    arm_results: dict[tuple[str, str, str], dict[str, object]] = {}
    for claim_id, claim in claims.items():
        output_row: dict[str, object] = {
            "claim_id": claim_id,
            "source_key": (claim.get("source_key") or "").strip(),
            "primary_stratum": (
                claim.get("coordinator_only_primary_stratum") or ""
            ).strip(),
        }
        for output in OUTPUTS:
            reference = gold[(claim_id, output)]
            output_row[f"gold_{output}_status"] = reference["status"]
            output_row[f"gold_{output}_label"] = reference["label"]
        for arm in ARMS:
            for output in OUTPUTS:
                majority = strict_majority(
                    responses[arm].get(claim_id, []), output
                )
                reference = gold[(claim_id, output)]
                accuracy: int | None = None
                if (
                    reference["status"] == "resolved"
                    and majority["status"] in {"majority", "no_consensus"}
                ):
                    accuracy = int(
                        majority["status"] == "majority"
                        and majority["label"] == reference["label"]
                    )
                arm_results[(claim_id, arm, output)] = {
                    **majority,
                    "accuracy": accuracy,
                }
                prefix = f"arm_{arm}_{output}"
                output_row[f"{prefix}_majority"] = (
                    majority["label"]
                    if majority["status"] == "majority"
                    else majority["status"]
                )
                output_row[f"{prefix}_accuracy"] = (
                    "" if accuracy is None else accuracy
                )
                output_row[f"{prefix}_no_consensus"] = int(
                    bool(majority["no_consensus"])
                )
        claim_rows.append(output_row)

    unresolved_gold = 0
    incomplete_gold = 0
    incomplete_cd = 0
    for claim_id, claim in claims.items():
        reference = gold[(claim_id, "comparability")]
        c_result = arm_results[(claim_id, "C", "comparability")]
        d_result = arm_results[(claim_id, "D", "comparability")]
        if reference["status"] != "resolved":
            unresolved_gold += 1
        if reference["method"] == "unresolved_incomplete_gold":
            incomplete_gold += 1
        if c_result["status"] == "missing" or d_result["status"] == "missing":
            incomplete_cd += 1
    primary_rows = primary_complete_case_rows(claims, gold, arm_results)
    primary_observations = [
        (source, difference)
        for _claim_id, source, difference in primary_rows
    ]
    unresolved_rate = unresolved_gold / len(claims)
    incomplete_gold_rate = incomplete_gold / len(claims)
    incomplete_rate = incomplete_cd / len(claims)
    missingness_ok = (
        unresolved_rate <= MISSINGNESS_THRESHOLD
        and incomplete_rate <= MISSINGNESS_THRESHOLD
    )
    bounds = primary_missingness_bounds(claims, gold, arm_results)
    primary_source_count = len(
        {source for source, _value in primary_observations}
    )
    primary_estimable = (
        bool(primary_observations) and primary_source_count >= 2
    )
    if primary_estimable:
        primary_stats = cr1_intercept_statistics(primary_observations)
        bootstrap_low, bootstrap_high = source_cluster_bootstrap(
            primary_observations, bootstrap_replicates, BOOTSTRAP_SEED
        )
        statistical_superiority = (
            float(primary_stats["estimate"]) > 0.0
            and float(primary_stats["p_two_sided"]) < ALPHA
        )
        equivalence: dict[str, object] = {
            "performed": not statistical_superiority,
            "margin": EQUIVALENCE_MARGIN,
        }
        if not statistical_superiority:
            estimate = float(primary_stats["estimate"])
            standard_error = float(primary_stats["cr1_se"])
            degrees_freedom = int(primary_stats["degrees_freedom"])
            if standard_error == 0.0:
                lower_p = 0.0 if estimate > -EQUIVALENCE_MARGIN else 1.0
                upper_p = 0.0 if estimate < EQUIVALENCE_MARGIN else 1.0
            else:
                lower_t = (estimate + EQUIVALENCE_MARGIN) / standard_error
                upper_t = (estimate - EQUIVALENCE_MARGIN) / standard_error
                lower_p = 1.0 - student_t_cdf(
                    lower_t, degrees_freedom
                )
                upper_p = student_t_cdf(upper_t, degrees_freedom)
            equivalence_pass = (
                lower_p < ALPHA
                and upper_p < ALPHA
                and float(primary_stats["ci90_low"])
                > -EQUIVALENCE_MARGIN
                and float(primary_stats["ci90_high"])
                < EQUIVALENCE_MARGIN
            )
            equivalence.update(
                {
                    "p_lower_margin": lower_p,
                    "p_upper_margin": upper_p,
                    "tost_p": max(lower_p, upper_p),
                    "ci90_low": primary_stats["ci90_low"],
                    "ci90_high": primary_stats["ci90_high"],
                    "statistical_equivalence_criterion_met": equivalence_pass,
                    "confirmatory_equivalence": (
                        equivalence_pass and missingness_ok
                    ),
                }
            )
        else:
            equivalence["reason_not_performed"] = (
                "pre-registered superiority criterion passed"
            )
        if not missingness_ok:
            conclusion = "inconclusive_nonconfirmatory_missingness"
        elif statistical_superiority:
            conclusion = "D_superior_to_C"
        elif bool(
            equivalence.get("statistical_equivalence_criterion_met")
        ):
            conclusion = "equivalent_within_plus_or_minus_0.10"
        else:
            conclusion = "inconclusive"
        bootstrap_performed = True
        reported_bootstrap_replicates = bootstrap_replicates
    else:
        primary_stats = {
            "status": "not_estimable",
            "claims": len(primary_observations),
            "sources": primary_source_count,
            "reason": (
                "primary observations are zero"
                if not primary_observations
                else "primary inference requires at least two sources"
            ),
        }
        bootstrap_low = ""
        bootstrap_high = ""
        bootstrap_performed = False
        reported_bootstrap_replicates = 0
        statistical_superiority = False
        equivalence = {
            "performed": False,
            "margin": EQUIVALENCE_MARGIN,
            "reason_not_performed": "primary estimate is not estimable",
            "confirmatory_equivalence": False,
        }
        conclusion = "inconclusive_nonconfirmatory_missingness"
    gold_by_claim: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in gold_rows:
        gold_by_claim[(row.get("claim_id") or "").strip()].append(row)
    adjudicator_sensitivity: dict[str, object] = {}
    for name, adjudicator_rows in (
        ("adjudicator_1", adjudicator_1_rows),
        ("adjudicator_2", adjudicator_2_rows),
    ):
        adjudicator_by_claim = unique_adjudicator_claim_map(
            adjudicator_rows, f"{name}_responses.csv"
        )
        observations: list[tuple[str, float]] = []
        for claim_id, claim in claims.items():
            expert_labels = [
                (row.get("comparability_label") or "").strip()
                for row in gold_by_claim.get(claim_id, [])
                if (row.get("response_status") or "").strip() == "completed"
            ]
            reference = ""
            if (
                len(expert_labels) == 3
                and all(label in COMPARABILITY_LABELS for label in expert_labels)
                and len(set(expert_labels)) == 1
            ):
                reference = expert_labels[0]
            elif len(expert_labels) == 3:
                adjudicator = adjudicator_by_claim.get(claim_id)
                if (
                    adjudicator is not None
                    and (adjudicator.get("response_status") or "").strip()
                    == "completed"
                ):
                    candidate = (
                        adjudicator.get("adjudicated_comparability_label") or ""
                    ).strip()
                    if candidate in COMPARABILITY_LABELS:
                        reference = candidate
            if not reference:
                continue
            c_result = arm_results[(claim_id, "C", "comparability")]
            d_result = arm_results[(claim_id, "D", "comparability")]
            if c_result["status"] == "missing" or d_result["status"] == "missing":
                continue
            c_accuracy = int(
                c_result["status"] == "majority"
                and c_result["label"] == reference
            )
            d_accuracy = int(
                d_result["status"] == "majority"
                and d_result["label"] == reference
            )
            observations.append(
                (
                    (claim.get("source_key") or "").strip(),
                    float(d_accuracy - c_accuracy),
                )
            )
        if observations and len({source for source, _value in observations}) >= 2:
            adjudicator_sensitivity[name] = cr1_intercept_statistics(observations)
        else:
            adjudicator_sensitivity[name] = {
                "claims": len(observations),
                "status": "not_estimable",
            }

    pairwise_rows: list[dict[str, object]] = []
    secondary_p: dict[str, float] = {}
    for output in OUTPUTS:
        for left, right in combinations(ARMS, 2):
            if output == "comparability" and (left, right) == ("C", "D"):
                continue
            observations = []
            for claim_id, claim in claims.items():
                left_accuracy = arm_results[(claim_id, left, output)]["accuracy"]
                right_accuracy = arm_results[(claim_id, right, output)]["accuracy"]
                if left_accuracy is None or right_accuracy is None:
                    continue
                observations.append(
                    (
                        (claim.get("source_key") or "").strip(),
                        float(right_accuracy) - float(left_accuracy),
                    )
                )
            key = f"{output}:{right}-{left}"
            row = pairwise_row(
                "secondary_11_pairwise",
                output,
                f"{right}-{left}",
                "all",
                observations,
            )
            pairwise_rows.append(row)
            secondary_p[key] = float(row["p_two_sided"])
    adjusted_secondary = holm_adjust(secondary_p)
    for row in pairwise_rows:
        key = f"{row['outcome']}:{row['contrast']}"
        row["holm_adjusted_p"] = adjusted_secondary[key]

    subgroup_rows: list[dict[str, object]] = []
    subgroup_p: dict[str, float] = {}
    for stratum in ("c2_decisive", "c5_decisive"):
        observations = []
        for claim_id, claim in claims.items():
            if (
                claim.get("coordinator_only_primary_stratum") or ""
            ).strip() != stratum:
                continue
            c_accuracy = arm_results[(claim_id, "C", "comparability")]["accuracy"]
            d_accuracy = arm_results[(claim_id, "D", "comparability")]["accuracy"]
            if c_accuracy is None or d_accuracy is None:
                continue
            observations.append(
                (
                    (claim.get("source_key") or "").strip(),
                    float(d_accuracy) - float(c_accuracy),
                )
            )
        row = pairwise_row(
            "secondary_c2_c5",
            "comparability",
            "D-C",
            stratum,
            observations,
        )
        subgroup_rows.append(row)
        subgroup_p[stratum] = float(row["p_two_sided"])
    adjusted_subgroups = holm_adjust(subgroup_p)
    for row in subgroup_rows:
        row["holm_adjusted_p"] = adjusted_subgroups[str(row["stratum"])]
    pairwise_rows.extend(subgroup_rows)

    arm_summary: dict[str, dict[str, object]] = {}
    no_consensus_summary: dict[str, dict[str, object]] = {}
    for arm in ARMS:
        arm_summary[arm] = {}
        no_consensus_summary[arm] = {}
        for output in OUTPUTS:
            results = [
                arm_results[(claim_id, arm, output)] for claim_id in claims
            ]
            accuracies = [
                int(result["accuracy"])
                for result in results
                if result["accuracy"] is not None
            ]
            complete = [
                result
                for result in results
                if result["status"] in {"majority", "no_consensus"}
            ]
            arm_summary[arm][output] = {
                "accuracy": sum(accuracies) / len(accuracies) if accuracies else None,
                "accuracy_denominator": len(accuracies),
            }
            no_consensus_count = sum(
                bool(result["no_consensus"]) for result in complete
            )
            no_consensus_summary[arm][output] = {
                "count": no_consensus_count,
                "denominator": len(complete),
                "rate": (
                    no_consensus_count / len(complete) if complete else None
                ),
            }

    field_rows: list[dict[str, object]] = []
    for arm in ARMS:
        completed = [
            row
            for row in arm_rows[arm]
            if (row.get("response_status") or "").strip() == "completed"
        ]
        for field in extraction_fields(arm_headers[arm], arm):
            nonempty = sum(bool((row.get(field) or "").strip()) for row in completed)
            field_rows.append(
                {
                    "arm_or_role": arm,
                    "field": field,
                    "completed_rows": len(completed),
                    "nonempty_rows": nonempty,
                    "nonempty_rate": nonempty / len(completed) if completed else "",
                }
            )
    completed_gold = [
        row
        for row in gold_rows
        if (row.get("response_status") or "").strip() == "completed"
    ]
    for field in extraction_fields(gold_header, "gold"):
        nonempty = sum(bool((row.get(field) or "").strip()) for row in completed_gold)
        field_rows.append(
            {
                "arm_or_role": "gold",
                "field": field,
                "completed_rows": len(completed_gold),
                "nonempty_rows": nonempty,
                "nonempty_rate": (
                    nonempty / len(completed_gold) if completed_gold else ""
                ),
            }
        )

    individual_rows, rater_sensitivity_rows = individual_rater_outputs(
        arm_rows, gold
    )
    c_participant_accuracies = [
        float(row["accuracy"])
        for row in individual_rows
        if row["arm"] == "C"
        and row["output"] == "comparability"
        and row["accuracy"] != ""
    ]
    d_participant_accuracies = [
        float(row["accuracy"])
        for row in individual_rows
        if row["arm"] == "D"
        and row["output"] == "comparability"
        and row["accuracy"] != ""
    ]
    participant_difference: dict[str, object] = {
        "analysis": "participant_mean_accuracy_D_minus_C",
        "status": (
            "estimated"
            if c_participant_accuracies and d_participant_accuracies
            else "not_estimable"
        ),
        "arm": "D-C",
        "output": "comparability",
        "participant_id": "",
        "n": len(c_participant_accuracies) + len(d_participant_accuracies),
        "estimate": (
            sum(d_participant_accuracies) / len(d_participant_accuracies)
            - sum(c_participant_accuracies) / len(c_participant_accuracies)
            if c_participant_accuracies and d_participant_accuracies
            else ""
        ),
        "minimum": "",
        "median": "",
        "maximum": "",
        "standard_error": "",
        "degrees_freedom": "",
        "p_two_sided": "",
        "permutations": "",
        "reason": (
            "post hoc participant-level descriptive contrast"
            if c_participant_accuracies and d_participant_accuracies
            else "one or both arms have no participant accuracy denominator"
        ),
    }
    rater_sensitivity_rows.append(participant_difference)
    permutation = conditional_arm_label_permutation(individual_rows)
    rater_sensitivity_rows.append(
        {
            "analysis": "conditional_arm_label_permutation",
            "status": permutation["status"],
            "arm": "D-C",
            "output": "comparability",
            "participant_id": "",
            "n": permutation.get("n", ""),
            "estimate": permutation.get("estimate", ""),
            "minimum": "",
            "median": "",
            "maximum": "",
            "standard_error": "",
            "degrees_freedom": "",
            "p_two_sided": permutation.get("p_two_sided", ""),
            "permutations": permutation.get("permutations", ""),
            "reason": permutation.get("reason", ""),
        }
    )
    individual_observations: list[tuple[str, str, float, float]] = []
    for arm in ("C", "D"):
        for row in arm_rows[arm]:
            if (row.get("response_status") or "").strip() != "completed":
                continue
            claim_id = (row.get("claim_id") or "").strip()
            participant = (row.get("participant_id") or "").strip()
            label = (row.get("comparability_label") or "").strip()
            reference = gold.get((claim_id, "comparability"), {})
            if (
                participant
                and claim_id in claims
                and label in COMPARABILITY_LABELS
                and reference.get("status") == "resolved"
            ):
                individual_observations.append(
                    (
                        (claims[claim_id].get("source_key") or "").strip(),
                        participant,
                        float(label == reference.get("label")),
                        float(arm == "D"),
                    )
                )
    two_way = two_way_cluster_ols(individual_observations)
    rater_sensitivity_rows.append(
        {
            "analysis": "individual_rating_ols_two_way_cluster_CGM",
            "status": two_way["status"],
            "arm": "D-C",
            "output": "comparability",
            "participant_id": "",
            "n": two_way.get("n", ""),
            "estimate": two_way.get("estimate", ""),
            "minimum": "",
            "median": "",
            "maximum": "",
            "standard_error": two_way.get("standard_error", ""),
            "degrees_freedom": two_way.get("degrees_freedom", ""),
            "p_two_sided": two_way.get("p_two_sided", ""),
            "permutations": "",
            "reason": two_way.get("reason", ""),
        }
    )
    loao_rows = leave_one_auditor_out(claims, responses, gold)
    rater_sensitivity_rows.extend(loao_rows)
    loao_estimates = [
        float(row["estimate"])
        for row in loao_rows
        if row["status"] == "estimated"
    ]
    loao_summary: dict[str, object] = {
        "analysis": "leave_one_auditor_out_range",
        "status": (
            "estimated"
            if len(loao_estimates) == 12
            else "not_estimable"
        ),
        "arm": "D-C",
        "output": "comparability",
        "participant_id": "",
        "n": len(loao_estimates),
        "estimate": "",
        "minimum": min(loao_estimates) if len(loao_estimates) == 12 else "",
        "median": (
            percentile(loao_estimates, 0.5)
            if len(loao_estimates) == 12
            else ""
        ),
        "maximum": max(loao_estimates) if len(loao_estimates) == 12 else "",
        "standard_error": "",
        "degrees_freedom": "",
        "p_two_sided": "",
        "permutations": "",
        "reason": (
            "range over 12 post hoc changed-aggregation deletions"
            if len(loao_estimates) == 12
            else "all 12 realized C/D auditor deletions must be estimable"
        ),
    }
    rater_sensitivity_rows.append(loao_summary)
    agreement_rows = agreement_outputs(responses)
    confusion_rows = confusion_outputs(claims, gold, arm_results)
    diagnostic_rows = response_diagnostics(arm_rows)
    missingness_pattern_rows = missingness_pattern_outputs(
        claims, gold, arm_results
    )

    results: dict[str, object] = {
        "status": "COLLECTED_RESULTS_ANALYZED",
        "analysis_dependencies": "Python standard library only",
        "separate_outputs": True,
        "input_authentication_limitation": (
            "manifest authenticates package bytes but cannot by itself prove "
            "behavioral independence"
        ),
        "primary": {
            "endpoint": "D-C comparability strict-majority exact accuracy",
            **primary_stats,
            "bootstrap_performed": bootstrap_performed,
            "bootstrap_replicates": reported_bootstrap_replicates,
            "bootstrap_replicates_planned": bootstrap_replicates,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_percentile_ci95_low": bootstrap_low,
            "bootstrap_percentile_ci95_high": bootstrap_high,
            "alpha_two_sided": ALPHA,
            "statistical_superiority_criterion_met": statistical_superiority,
            "confirmatory_superiority": statistical_superiority and missingness_ok,
            "equivalence": equivalence,
            "conclusion": conclusion,
            "missingness_bounds": bounds,
        },
        "missingness": {
            "gold_unresolved_comparability": unresolved_gold,
            "gold_unresolved_comparability_rate": unresolved_rate,
            "gold_incomplete_comparability": incomplete_gold,
            "gold_incomplete_comparability_rate": incomplete_gold_rate,
            "incomplete_c_or_d_comparability": incomplete_cd,
            "incomplete_c_or_d_comparability_rate": incomplete_rate,
            "threshold": MISSINGNESS_THRESHOLD,
            "confirmatory_missingness_rule_passed": missingness_ok,
        },
        "arm_accuracy": arm_summary,
        "no_consensus": no_consensus_summary,
        "adjudicator_sensitivity": adjudicator_sensitivity,
        "post_hoc_exploratory_rater_sensitivity": {
            "label": "reviewer-requested post hoc exploratory",
            "participant_mean_D_minus_C": participant_difference,
            "conditional_arm_label_permutation": permutation,
            "individual_rating_two_way_cluster_ols": two_way,
            "leave_one_auditor_out": {
                "aggregation": (
                    "after deletion, two votes produce a label only when "
                    "unanimous; disagreement is no_consensus with accuracy 0"
                ),
                "summary": loao_summary,
            },
            "limitations": (
                "each auditor observed only one arm; six auditors per arm; "
                "these sensitivities are not confirmatory prompt-effect tests"
            ),
        },
        "post_hoc_descriptive_outputs": {
            "label": "reviewer-requested post hoc exploratory/descriptive",
            "agreement": (
                "Fleiss nominal kappa and raw unordered-pair agreement on "
                "complete exactly-three-vote claims"
            ),
            "timing": (
                "row-level elapsed-time diagnostics only; not labor cost and "
                "not inferred from packet-wide timestamps"
            ),
        },
        "multiplicity": {
            "secondary_pairwise": "Holm over 11 nonprimary contrasts",
            "c2_c5_subgroups": "Holm over two D-C contrasts",
        },
        "field_diagnostics_interpretation": (
            "field/extraction completeness diagnostics; not extraction accuracy"
        ),
    }
    tables = {
        "claim_level": claim_rows,
        "pairwise": pairwise_rows,
        "field_diagnostics": field_rows,
        "gold_resolution": gold_audit,
        "individual_raters": individual_rows,
        "rater_sensitivity": rater_sensitivity_rows,
        "agreement": agreement_rows,
        "confusion": confusion_rows,
        "response_diagnostics": diagnostic_rows,
        "missingness_patterns": missingness_pattern_rows,
    }
    return results, tables


def public_field_allowed(field: str) -> bool:
    normalized = field.lower()
    return (
        normalized != "participant_id"
        and "rationale" not in normalized
        and normalized != "reason"
        and not normalized.endswith("_reason")
        and not re.search(
            r"(?:^|_)(?:start|started|completion|completed)(?:$|_)",
            normalized,
        )
    )


def sanitize_public_object(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: sanitize_public_object(nested)
            for key, nested in value.items()
            if public_field_allowed(str(key))
        }
    if isinstance(value, list):
        return [sanitize_public_object(nested) for nested in value]
    return value


def write_analysis_outputs(
    output: Path,
    results: Mapping[str, object],
    tables: Mapping[str, Sequence[Mapping[str, object]]],
    public_tables: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"analysis output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "analysis_results.json", results)
    write_csv(
        output / "analysis_claim_level.csv",
        CLAIM_LEVEL_HEADER,
        tables["claim_level"],
    )
    write_csv(
        output / "analysis_pairwise.csv",
        PAIRWISE_HEADER,
        tables["pairwise"],
    )
    write_csv(
        output / "analysis_field_diagnostics.csv",
        FIELD_DIAGNOSTIC_HEADER,
        tables["field_diagnostics"],
    )
    write_csv(
        output / "analysis_gold_resolution.csv",
        GOLD_RESOLUTION_HEADER,
        tables["gold_resolution"],
    )
    additional = (
        ("analysis_individual_raters.csv", INDIVIDUAL_RATER_HEADER, "individual_raters"),
        ("analysis_rater_sensitivity.csv", RATER_SENSITIVITY_HEADER, "rater_sensitivity"),
        ("analysis_agreement.csv", AGREEMENT_HEADER, "agreement"),
        ("analysis_confusion.csv", CONFUSION_HEADER, "confusion"),
        (
            "analysis_response_diagnostics.csv",
            RESPONSE_DIAGNOSTIC_HEADER,
            "response_diagnostics",
        ),
        (
            "analysis_missingness_patterns.csv",
            MISSINGNESS_PATTERN_HEADER,
            "missingness_patterns",
        ),
    )
    for filename, header, table_name in additional:
        write_csv(output / filename, header, tables[table_name])
    if public_tables is None:
        return
    public_release = output / "public_release"
    public_release.mkdir()
    public_specs = (
        ("public_arm_ratings.csv", PUBLIC_ARM_HEADER, "public_arm_ratings"),
        ("public_gold_ratings.csv", PUBLIC_GOLD_HEADER, "public_gold_ratings"),
        (
            "public_adjudications.csv",
            PUBLIC_ADJUDICATION_HEADER,
            "public_adjudications",
        ),
    )
    safe_private_files: dict[str, int] = {
        "analysis_results.json": 1,
        "analysis_claim_level.csv": len(tables["claim_level"]),
        "analysis_pairwise.csv": len(tables["pairwise"]),
        "analysis_gold_resolution.csv": len(tables["gold_resolution"]),
        "analysis_agreement.csv": len(tables["agreement"]),
        "analysis_confusion.csv": len(tables["confusion"]),
        "analysis_response_diagnostics.csv": len(tables["response_diagnostics"]),
        "analysis_missingness_patterns.csv": len(tables["missingness_patterns"]),
    }
    row_counts = dict(safe_private_files)
    for filename in safe_private_files:
        if filename == "analysis_results.json":
            write_json(public_release / filename, sanitize_public_object(results))
        elif filename == "analysis_agreement.csv":
            public_header = tuple(
                field for field in AGREEMENT_HEADER if public_field_allowed(field)
            )
            write_csv(
                public_release / filename,
                public_header,
                tables["agreement"],
            )
        else:
            shutil.copyfile(output / filename, public_release / filename)
    for filename, header, table_name in public_specs:
        write_csv(public_release / filename, header, public_tables[table_name])
        row_counts[filename] = len(public_tables[table_name])
    manifest_files = []
    for filename, row_count in sorted(row_counts.items()):
        payload = (public_release / filename).read_bytes()
        manifest_files.append(
            {
                "basename": filename,
                "row_count": row_count,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    write_json(
        public_release / "public_release_manifest.json",
        {
            "schema_version": "heldout-claim-validation-public-v1",
            "files": manifest_files,
            "manifest_self_exclusion": (
                "public_release_manifest.json cannot include its own SHA-256 "
                "without a recursive self-reference"
            ),
            "excluded_sensitive_fields_scope": (
                "every file listed in this manifest"
            ),
            "excluded_sensitive_fields": [
                "original participant_id and linkable response/assignment IDs",
                "rationale and all other free text",
                "claim text",
                "timestamps and packet-wide timing metadata",
                "demographics",
                "deidentification key, digest, and key-file path",
            ],
            "private_only_files": [
                "analysis_individual_raters.csv",
                "analysis_rater_sensitivity.csv",
            ],
            "release_id_method": (
                "fixed 24-hex-character opaque HMAC-SHA256-derived release ID; "
                "secret material is not released"
            ),
        },
    )


def load_inputs(root: Path, frozen_path: Path) -> tuple[
    list[dict[str, str]],
    dict[str, list[dict[str, str]]],
    dict[str, tuple[str, ...]],
    list[dict[str, str]],
    tuple[str, ...],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    from build_offline_analysis_release import (
        load_and_validate_inputs,
        validate_authoritative_frozen_metadata,
    )

    validate_authoritative_frozen_metadata()
    return load_and_validate_inputs(root, frozen_path)


def _assert_close(actual: object, expected: float, name: str) -> None:
    if abs(float(actual) - expected) > 1.0e-12:
        raise AssertionError(f"{name}: expected {expected}, got {actual}")


def _run_hand_checkable_self_tests() -> None:
    permutation_fixture = [
        {
            "participant_id": f"C_{index}",
            "arm": "C",
            "output": "comparability",
            "accuracy": 0.0,
        }
        for index in range(6)
    ] + [
        {
            "participant_id": f"D_{index}",
            "arm": "D",
            "output": "comparability",
            "accuracy": 1.0,
        }
        for index in range(6)
    ]
    permutation = conditional_arm_label_permutation(permutation_fixture)
    if permutation["permutations"] != 924:
        raise AssertionError("hand permutation fixture did not enumerate 924 labels")
    _assert_close(permutation["estimate"], 1.0, "permutation estimate")
    _assert_close(permutation["p_two_sided"], 1.0 / 462.0, "permutation p")

    cgm_fixture = [
        ("s1", "c1", 0.0, 0.0),
        ("s1", "d1", 1.0, 1.0),
        ("s2", "c1", 0.0, 0.0),
        ("s2", "d2", 0.0, 1.0),
        ("s3", "c2", 1.0, 0.0),
        ("s3", "d1", 1.0, 1.0),
        ("s4", "c2", 0.0, 0.0),
        ("s4", "d2", 1.0, 1.0),
    ]
    cgm = two_way_cluster_ols(cgm_fixture)
    if cgm["status"] != "estimated" or cgm["degrees_freedom"] != 3:
        raise AssertionError("hand CGM fixture status or df is incorrect")
    _assert_close(cgm["estimate"], 0.5, "CGM estimate")
    _assert_close(cgm["variance"], 5.0 / 72.0, "CGM variance")
    _assert_close(cgm["source_cr1_factor"], 14.0 / 9.0, "source CR1")
    _assert_close(cgm["auditor_cr1_factor"], 14.0 / 9.0, "auditor CR1")
    _assert_close(cgm["intersection_cr1_factor"], 4.0 / 3.0, "intersection CR1")

    loao_claims = {
        "loao_1": {"source_key": "s1"},
        "loao_2": {"source_key": "s2"},
    }
    loao_gold = {
        (claim_id, "comparability"): {
            "status": "resolved",
            "label": "same_estimand",
        }
        for claim_id in loao_claims
    }

    def vote(participant: str, label: str) -> dict[str, str]:
        return {
            "participant_id": participant,
            "response_status": "completed",
            "comparability_label": label,
        }

    loao_responses: dict[
        str, dict[str, list[Mapping[str, str]]]
    ] = {
        "C": {
            "loao_1": [
                vote(f"c{index}", "same_estimand") for index in range(3)
            ],
            "loao_2": [
                vote(f"c{index}", "different_estimand")
                for index in range(3, 6)
            ],
        },
        "D": {
            "loao_1": [
                vote(f"d{index}", "same_estimand") for index in range(3)
            ],
            "loao_2": [
                vote("d3", "same_estimand"),
                vote("d4", "same_estimand"),
                vote("d5", "different_estimand"),
            ],
        },
    }
    loao = leave_one_auditor_out(loao_claims, loao_responses, loao_gold)
    expected_loao = {
        **{f"c{index}": 0.5 for index in range(6)},
        **{f"d{index}": 0.5 for index in (0, 1, 2, 5)},
        "d3": 0.0,
        "d4": 0.0,
    }
    if len(loao) != 12:
        raise AssertionError("hand LOAO fixture did not produce 12 deletions")
    for row in loao:
        if row["status"] != "estimated" or row["n"] != 2:
            raise AssertionError("hand LOAO fixture was not fully estimable")
        _assert_close(
            row["estimate"],
            expected_loao[str(row["participant_id"])],
            f"LOAO {row['participant_id']}",
        )

    agreement_responses: dict[
        str, dict[str, list[Mapping[str, str]]]
    ] = {arm: {} for arm in ARMS}
    agreement_responses["A"] = {
        "agreement_1": [
            {
                **vote(f"a{index}", label),
                "evidence_support_label": "supported_as_written",
            }
            for index, label in enumerate(
                ("same_estimand", "same_estimand", "different_estimand")
            )
        ],
        "agreement_2": [
            {
                **vote(f"b{index}", label),
                "evidence_support_label": "supported_as_written",
            }
            for index, label in enumerate(
                ("same_estimand", "different_estimand", "different_estimand")
            )
        ],
    }
    agreement = next(
        row
        for row in agreement_outputs(agreement_responses)
        if row["arm"] == "A" and row["output"] == "comparability"
    )
    _assert_close(
        agreement["raw_pairwise_agreement"], 1.0 / 3.0, "raw agreement"
    )
    _assert_close(agreement["fleiss_kappa"], -1.0 / 3.0, "Fleiss kappa")

    diagnostic_claims = {
        "diag_1": {
            "source_key": "diag_source",
            "coordinator_only_primary_stratum": "c2_decisive",
        },
        "diag_2": {
            "source_key": "diag_source",
            "coordinator_only_primary_stratum": "c2_decisive",
        },
    }
    diagnostic_gold: dict[tuple[str, str], dict[str, str]] = {}
    diagnostic_arm_results: dict[
        tuple[str, str, str], dict[str, object]
    ] = {}
    for claim_id in diagnostic_claims:
        for output in OUTPUTS:
            resolved = not (
                claim_id == "diag_2" and output == "comparability"
            )
            diagnostic_gold[(claim_id, output)] = {
                "status": "resolved" if resolved else "unresolved_incomplete_gold",
                "label": (
                    "supported_as_written"
                    if output == "evidence_support"
                    else ("same_estimand" if resolved else "")
                ),
                "method": (
                    "unanimous_three_experts"
                    if resolved
                    else "unresolved_incomplete_gold"
                ),
            }
            for arm in ARMS:
                label = (
                    "supported_as_written"
                    if output == "evidence_support"
                    else "same_estimand"
                )
                diagnostic_arm_results[(claim_id, arm, output)] = {
                    "status": "majority",
                    "label": label,
                    "accuracy": 1 if resolved else None,
                }
    diagnostic_arm_results[("diag_1", "C", "comparability")] = {
        "status": "missing",
        "label": "",
        "accuracy": None,
    }
    diagnostic_arm_results[("diag_2", "C", "comparability")] = {
        "status": "majority",
        "label": "different_estimand",
        "accuracy": None,
    }
    confusion = confusion_outputs(
        diagnostic_claims, diagnostic_gold, diagnostic_arm_results
    )

    def confusion_row(row_type: str, gold_label: str, arm_label: str) -> Mapping[str, object]:
        return next(
            row
            for row in confusion
            if row["row_type"] == row_type
            and row["arm"] == "C"
            and row["output"] == "comparability"
            and row["gold_label"] == gold_label
            and row["arm_label"] == arm_label
        )

    distribution = confusion_row("class_distribution", "", "missing")
    if distribution["count"] != 1 or distribution["denominator"] != 2:
        raise AssertionError("hand confusion distribution counts are incorrect")
    _assert_close(distribution["rate"], 0.5, "confusion distribution rate")
    resolved_confusion = confusion_row(
        "resolved_gold_confusion", "same_estimand", "missing"
    )
    if resolved_confusion["count"] != 1 or resolved_confusion["denominator"] != 1:
        raise AssertionError("hand resolved confusion counts are incorrect")
    _assert_close(resolved_confusion["rate"], 1.0, "resolved confusion rate")

    missingness = missingness_pattern_outputs(
        diagnostic_claims, diagnostic_gold, diagnostic_arm_results
    )
    c_comparability = {
        str(row["resolution_method"]): row
        for row in missingness
        if row["arm"] == "C" and row["output"] == "comparability"
    }
    resolved_missingness = c_comparability["unanimous_three_experts"]
    unresolved_missingness = c_comparability["unresolved_incomplete_gold"]
    if (
        resolved_missingness["claims"],
        resolved_missingness["unresolved_gold_count"],
        resolved_missingness["arm_missing_count"],
    ) != (1, 0, 1):
        raise AssertionError("resolved hand missingness counts are incorrect")
    if (
        unresolved_missingness["claims"],
        unresolved_missingness["unresolved_gold_count"],
        unresolved_missingness["arm_missing_count"],
    ) != (1, 1, 0):
        raise AssertionError("unresolved hand missingness counts are incorrect")


def self_test() -> None:
    workspace = Path(
        tempfile.mkdtemp(prefix=".analysis_selftest_", dir=PACKAGE)
    )
    try:
        _run_hand_checkable_self_tests()
        frozen = []
        for source_index in range(8):
            for claim_index in range(4):
                index = source_index * 4 + claim_index
                frozen.append(
                    {
                        "claim_id": f"claim_{index:03d}",
                        "source_key": f"source_{source_index:02d}",
                        "coordinator_only_primary_stratum": (
                            "c2_decisive" if index % 2 == 0 else "c5_decisive"
                        ),
                    }
                )
        arm_headers = {
            arm: (
                "claim_id",
                "participant_id",
                "response_status",
                "missing_reason_code",
                "extraction_started_utc",
                "extraction_completed_utc",
                "extraction_snapshot_sha256",
                "extracted_fact",
                "composition_started_utc",
                "completed_utc",
                "evidence_support_label",
                "comparability_label",
                "rationale",
            )
            for arm in ARMS
        }
        arm_rows: dict[str, list[dict[str, str]]] = {arm: [] for arm in ARMS}
        for claim_number, claim in enumerate(frozen):
            for arm in ARMS:
                for rater in range(3):
                    c_label = "same_estimand"
                    if arm == "C" and claim_number % 4 == 0:
                        c_label = "different_estimand"
                    if arm == "D" and claim_number % 8 == 0 and rater == 2:
                        c_label = "different_estimand"
                    if arm == "A" and claim_number == 2:
                        c_label = (
                            "same_estimand",
                            "different_estimand",
                            "missing_comparison_assumption",
                        )[rater]
                    participant_number = (
                        rater + 3 * (claim_number % 2)
                        if arm in {"C", "D"}
                        else rater
                    )
                    extraction_start = "2026-07-15T12:00:00Z"
                    extraction_end = "2026-07-15T12:05:00Z"
                    completion = "2026-07-15T12:10:00+00:00"
                    if claim_number == 0 and rater == 0:
                        extraction_end = "2026-07-15T11:59:00Z"
                    if claim_number == 0 and rater == 1:
                        completion = ""
                    arm_rows[arm].append(
                        {
                            "claim_id": claim["claim_id"],
                            "participant_id": f"{arm}_{participant_number}",
                            "response_status": "completed",
                            "missing_reason_code": "",
                            "extraction_started_utc": extraction_start,
                            "extraction_completed_utc": extraction_end,
                            "extraction_snapshot_sha256": "a" * 64,
                            "extracted_fact": "fact",
                            "composition_started_utc": "2026-07-15T12:06:00Z",
                            "completed_utc": completion,
                            "evidence_support_label": "supported_as_written",
                            "comparability_label": c_label,
                            "rationale": "rationale-secret",
                        }
                    )
        for row in arm_rows["D"]:
            if row["claim_id"] == "claim_002":
                row["response_status"] = "unable_to_determine"
                row["missing_reason_code"] = "synthetic_single_arm_missing"
                row["evidence_support_label"] = ""
                row["comparability_label"] = ""
        gold_header = (
            "claim_id",
            "participant_id",
            "gold_response_id",
            "response_status",
            "review_started_utc",
            "reported_result_facts",
            "composition_started_utc",
            "evidence_support_label",
            "comparability_label",
        )
        gold_rows = []
        for claim in frozen:
            for expert in range(3):
                gold_rows.append(
                    {
                        "claim_id": claim["claim_id"],
                        "participant_id": f"gold_{expert}",
                        "gold_response_id": f"{claim['claim_id']}_{expert}",
                        "response_status": "completed",
                        "review_started_utc": "gold-private-timestamp-secret",
                        "reported_result_facts": "fact",
                        "composition_started_utc": "gold-private-timestamp-secret",
                        "evidence_support_label": "supported_as_written",
                        "comparability_label": "same_estimand",
                    }
                )
        for row in gold_rows:
            if (
                row["claim_id"] in {"claim_000", "claim_001"}
                and row["participant_id"] == "gold_2"
            ):
                row["comparability_label"] = "different_estimand"
        adjudicator_1 = [
            {
                "claim_id": claim_id,
                "adjudicator_id": "private_adjudicator_1",
                "response_status": "completed",
                "adjudicated_comparability_label": "same_estimand",
            }
            for claim_id in ("claim_000", "claim_001")
        ]
        adjudicator_2 = [
            {
                "claim_id": "claim_000",
                "adjudicator_id": "private_adjudicator_2",
                "response_status": "completed",
                "adjudicated_comparability_label": "same_estimand",
            },
            {
                "claim_id": "claim_001",
                "adjudicator_id": "private_adjudicator_2",
                "response_status": "completed",
                "adjudicated_comparability_label": "different_estimand",
            },
        ]
        results, tables = analyze(
            frozen,
            arm_rows,
            arm_headers,
            gold_rows,
            gold_header,
            adjudicator_1,
            adjudicator_2,
            2_000,
        )
        primary = results["primary"]
        if primary["claims"] != 30:  # type: ignore[index]
            raise AssertionError("single-arm missing fixture changed primary denominator")
        _assert_close(primary["estimate"], 4.0 / 15.0, "primary estimate")  # type: ignore[index]
        bounds = primary["missingness_bounds"]  # type: ignore[index]
        if bounds["missing_claims"] != 2:
            raise AssertionError("missingness bounds did not count both incomplete claims")
        _assert_close(bounds["worst_case"], 6.0 / 32.0, "lower bound")
        _assert_close(bounds["best_case"], 9.0 / 32.0, "upper bound")
        key_file = workspace / "selftest_deidentification.key"
        key_file.write_bytes(b"synthetic-self-test-key-material-32-bytes")
        short_key_file = workspace / "short.key"
        short_key_file.write_bytes(b"x")
        try:
            load_deidentification_key(short_key_file)
        except ValueError:
            pass
        else:
            raise AssertionError("one-byte deidentification key was accepted")
        try:
            build_public_tables(
                b"x",
                frozen,
                arm_rows,
                gold_rows,
                adjudicator_1,
                adjudicator_2,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("public-table boundary accepted a one-byte key")
        public_tables = build_public_tables(
            load_deidentification_key(key_file),
            frozen,
            arm_rows,
            gold_rows,
            adjudicator_1,
            adjudicator_2,
        )
        write_analysis_outputs(
            workspace / "outputs", results, tables, public_tables
        )
        if results["primary"]["bootstrap_replicates"] != 2_000:  # type: ignore[index]
            raise AssertionError("analysis self-test did not run bootstrap")
        if not (workspace / "outputs" / "analysis_results.json").is_file():
            raise AssertionError("analysis self-test did not write outputs")
        permutation_rows = [
            row
            for row in tables["rater_sensitivity"]
            if row["analysis"] == "conditional_arm_label_permutation"
        ]
        if (
            len(permutation_rows) != 1
            or permutation_rows[0]["status"] != "estimated"
            or permutation_rows[0]["permutations"] != 924
        ):
            raise AssertionError("924-way participant permutation was not exercised")
        loao_rows = [
            row
            for row in tables["rater_sensitivity"]
            if row["analysis"] == "leave_one_auditor_out_changed_aggregation"
        ]
        if len(loao_rows) != 12 or any(
            row["status"] != "estimated" for row in loao_rows
        ):
            raise AssertionError("12 leave-one-auditor-out analyses failed")
        cluster_rows = [
            row
            for row in tables["rater_sensitivity"]
            if row["analysis"] == "individual_rating_ols_two_way_cluster_CGM"
        ]
        if len(cluster_rows) != 1 or cluster_rows[0]["status"] not in {
            "estimated",
            "negative_variance",
        }:
            raise AssertionError("two-way clustered OLS did not fail explicitly")
        if len(tables["agreement"]) != 8 or not tables["confusion"]:
            raise AssertionError("agreement/confusion outputs were not generated")
        time_rows = [
            row
            for row in tables["response_diagnostics"]
            if row["diagnostic"] == "row_elapsed_time"
        ]
        stages_with_valid_time = {
            str(row["stage"])
            for row in time_rows
            if int(row["n_valid"]) > 0 and row["median_seconds"] != ""
        }
        if stages_with_valid_time != {"extraction", "composition", "total"}:
            raise AssertionError(
                "extraction/composition/total timing did not use completed_utc"
            )
        extraction_time_rows = [
            row for row in time_rows if row["stage"] == "extraction"
        ]
        if not extraction_time_rows or not all(
            int(row["negative_count"]) == 1 for row in extraction_time_rows
        ):
            raise AssertionError("negative row-level time was not separated")
        if strict_iso_utc("2026-07-15T12:00:00-07:00") is not None:
            raise AssertionError("strict UTC parser accepted a non-UTC offset")
        if strict_iso_utc("2026-07-15T12:00:00Z") is None:
            raise AssertionError("strict UTC parser rejected ISO Z time")
        output_directory = workspace / "outputs"
        public_directory = output_directory / "public_release"
        manifest = json.loads(
            (public_directory / "public_release_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        expected_public_files = {
            "analysis_results.json",
            "analysis_claim_level.csv",
            "analysis_pairwise.csv",
            "analysis_gold_resolution.csv",
            "analysis_agreement.csv",
            "analysis_confusion.csv",
            "analysis_response_diagnostics.csv",
            "analysis_missingness_patterns.csv",
            "public_arm_ratings.csv",
            "public_gold_ratings.csv",
            "public_adjudications.csv",
        }
        manifested_files = {
            str(entry["basename"]) for entry in manifest["files"]
        }
        if manifested_files != expected_public_files:
            raise AssertionError("public manifest is not the explicit safe allowlist")
        if (
            (public_directory / "analysis_individual_raters.csv").exists()
            or (public_directory / "analysis_rater_sensitivity.csv").exists()
        ):
            raise AssertionError("private participant-ID analysis entered public release")
        if not (
            (output_directory / "analysis_individual_raters.csv").is_file()
            and (output_directory / "analysis_rater_sensitivity.csv").is_file()
        ):
            raise AssertionError("private analysis tables were not retained")
        private_ids = {
            (
                row.get("participant_id")
                or row.get("adjudicator_id")
                or ""
            ).strip()
            for rows in [
                *arm_rows.values(),
                gold_rows,
                adjudicator_1,
                adjudicator_2,
            ]
            for row in rows
            if (
                row.get("participant_id")
                or row.get("adjudicator_id")
                or ""
            ).strip()
        }
        for entry in manifest["files"]:
            basename = str(entry["basename"])
            if Path(basename).name != basename:
                raise AssertionError("public manifest contains a path traversal")
            released_file = public_directory / basename
            payload = released_file.read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise AssertionError("public manifest SHA-256 is incorrect")
            released_text = payload.decode("utf-8")
            if any(private_id in released_text for private_id in private_ids):
                raise AssertionError(
                    f"{basename} leaked an original participant ID"
                )
            lowered = released_text.lower()
            forbidden = (
                "rationale",
                "_utc",
                "2026-07-15t12:",
                "gold-private-timestamp-secret",
                "synthetic-self-test-key",
                "selftest_deidentification.key",
                str(key_file).lower(),
                "/home/",
            )
            if any(value in lowered for value in forbidden):
                raise AssertionError(
                    f"{basename} leaked rationale, timestamp, key, or path"
                )
        _public_arm_header, reread_arms = read_csv(
            public_directory / "public_arm_ratings.csv"
        )
        _public_gold_header, reread_gold = read_csv(
            public_directory / "public_gold_ratings.csv"
        )
        _public_adj_header, reread_adjudications = read_csv(
            public_directory / "public_adjudications.csv"
        )
        reread_gold_for_analysis = [
            {**row, "participant_id": row["release_participant_id"]}
            for row in reread_gold
        ]
        public_frozen_by_claim = {
            row["claim_id"]: {
                "claim_id": row["claim_id"],
                "source_key": row["source_key"],
                "coordinator_only_primary_stratum": "",
            }
            for row in reread_arms
        }
        public_frozen = list(public_frozen_by_claim.values())
        reread_adjudicator_1 = [
            row for row in reread_adjudications if row["role"] == "adjudicator_1"
        ]
        reread_adjudicator_2 = [
            row for row in reread_adjudications if row["role"] == "adjudicator_2"
        ]
        public_gold, _public_gold_audit = resolve_gold(
            public_frozen,
            reread_gold_for_analysis,
            reread_adjudicator_1,
            reread_adjudicator_2,
        )
        internal_gold, _internal_gold_audit = resolve_gold(
            frozen, gold_rows, adjudicator_1, adjudicator_2
        )
        if public_gold != internal_gold:
            raise AssertionError("public tables did not reproduce gold resolution")
        public_by_arm_claim: dict[
            str, dict[str, list[Mapping[str, str]]]
        ] = {arm: defaultdict(list) for arm in ARMS}
        for row in reread_arms:
            public_by_arm_claim[row["arm"]][row["claim_id"]].append(row)
        public_complete_cases: list[tuple[str, int]] = []
        for claim in public_frozen:
            claim_id = claim["claim_id"]
            reference = public_gold[(claim_id, "comparability")]
            if reference["status"] != "resolved":
                continue
            accuracies: dict[str, int] = {}
            complete = True
            for arm in ("C", "D"):
                majority = strict_majority(
                    public_by_arm_claim[arm][claim_id], "comparability"
                )
                if majority["status"] == "missing":
                    complete = False
                    break
                accuracies[arm] = int(
                    majority["status"] == "majority"
                    and majority["label"] == reference["label"]
                )
            if complete:
                public_complete_cases.append(
                    (claim_id, accuracies["D"] - accuracies["C"])
                )
        public_claim_set = {
            claim_id for claim_id, _difference in public_complete_cases
        }
        expected_claim_set = {
            f"claim_{index:03d}"
            for index in range(32)
            if index not in {1, 2}
        }
        if public_claim_set != expected_claim_set:
            raise AssertionError("public complete-case claim set is incorrect")
        if len(public_complete_cases) != primary["claims"]:  # type: ignore[index]
            raise AssertionError("public complete-case denominator differs")
        public_primary = sum(
            difference for _claim_id, difference in public_complete_cases
        ) / len(public_complete_cases)
        _assert_close(public_primary, 4.0 / 15.0, "public primary estimate")
        if abs(public_primary - float(primary["estimate"])) > 1.0e-12:  # type: ignore[index]
            raise AssertionError("public tables did not reproduce primary estimate")
        manifest_text = json.dumps(manifest, sort_keys=True)
        if (
            "synthetic-self-test-key-material-32-bytes" in manifest_text
            or str(key_file) in manifest_text
        ):
            raise AssertionError("public manifest leaked key material or path")
        resolution = {
            (row["claim_id"], row["output"]): row["status"]
            for row in tables["gold_resolution"]
        }
        if resolution[("claim_000", "comparability")] != "resolved":
            raise AssertionError("agreeing adjudicators did not resolve gold")
        if resolution[("claim_001", "comparability")] != "unresolved":
            raise AssertionError("conflicting adjudicators did not remain unresolved")
        ordered_resolution = resolve_gold(
            frozen,
            gold_rows,
            adjudicator_1,
            adjudicator_2,
        )
        reversed_resolution = resolve_gold(
            frozen,
            gold_rows,
            list(reversed(adjudicator_1)),
            list(reversed(adjudicator_2)),
        )
        if ordered_resolution != reversed_resolution:
            raise AssertionError(
                "legal adjudicator row order changed gold resolution"
            )
        duplicate_adjudication = [
            *adjudicator_1,
            {
                **adjudicator_1[0],
                "adjudication_id": "different_but_same_claim",
            },
        ]
        try:
            resolve_gold(
                frozen,
                gold_rows,
                duplicate_adjudication,
                adjudicator_2,
            )
        except ValueError as exc:
            if "duplicate claim" not in str(exc):
                raise
        else:
            raise AssertionError(
                "analysis accepted duplicate adjudication for one claim"
            )
        if results["no_consensus"]["A"]["comparability"]["count"] < 1:  # type: ignore[index]
            raise AssertionError("strict-majority no-consensus rule was not exercised")
        unable_arm_rows = {
            arm: [
                {
                    **row,
                    "response_status": "unable_to_determine",
                    "evidence_support_label": "",
                    "comparability_label": "",
                }
                for row in rows
            ]
            for arm, rows in arm_rows.items()
        }
        unable_gold_rows = [
            {
                **row,
                "response_status": "unable_to_determine",
                "evidence_support_label": "",
                "comparability_label": "",
            }
            for row in gold_rows
        ]
        missing_results, missing_tables = analyze(
            frozen,
            unable_arm_rows,
            arm_headers,
            unable_gold_rows,
            gold_header,
            [],
            [],
            2_000,
        )
        missing_primary = missing_results["primary"]
        if (
            missing_primary["status"] != "not_estimable"  # type: ignore[index]
            or missing_primary["bootstrap_performed"] is not False  # type: ignore[index]
            or missing_primary["bootstrap_replicates"] != 0  # type: ignore[index]
            or missing_primary["equivalence"]["performed"] is not False  # type: ignore[index]
            or missing_primary["conclusion"]  # type: ignore[index]
            != "inconclusive_nonconfirmatory_missingness"
        ):
            raise AssertionError("zero-observation analysis was not fail-safe")
        if not all(
            row["status"] == "unresolved_incomplete_gold"
            and row["resolution_method"] == "unresolved_incomplete_gold"
            for row in missing_tables["gold_resolution"]
        ):
            raise AssertionError("incomplete gold resolution method is inconsistent")
        critical = student_t_quantile(0.975, 79)
        if abs(critical - 1.99045) > 0.0001:
            raise AssertionError(f"Student-t implementation check failed: {critical}")
    finally:
        shutil.rmtree(workspace)
    print("self-test passed; synthetic fixture removed from package")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument(
        "--frozen-claims",
        type=Path,
        default=PACKAGE / "frozen_test_claims.csv",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--deidentification-key-file",
        type=Path,
        help=(
            "secret key file of at least 32 bytes required to write deidentified public "
            "rating tables; omitted by default"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input_root is None:
        raise ValueError("--input-root is required outside --self-test")
    if args.bootstrap_replicates != BOOTSTRAP_REPLICATES:
        raise ValueError(
            "confirmatory analysis requires exactly 100,000 bootstrap replicates"
        )
    inputs = load_inputs(args.input_root, args.frozen_claims)
    results, tables = analyze(*inputs, args.bootstrap_replicates)
    public_tables = None
    if args.deidentification_key_file is not None:
        key = load_deidentification_key(args.deidentification_key_file)
        public_tables = build_public_tables(
            key,
            inputs[0],
            inputs[1],
            inputs[3],
            inputs[5],
            inputs[6],
        )
    write_analysis_outputs(args.output, results, tables, public_tables)
    print(json.dumps(results["primary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
