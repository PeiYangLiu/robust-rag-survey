#!/usr/bin/env python3
"""Compute reviewer-requested diagnostics from the public v3 release."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE = (
    REPO / "manuscript" / "supplement" / "v3_human_reanalysis_20260725"
)
DEFAULT_OUTPUT = REPO / "manuscript" / "supplement"
DEFAULT_TABLES = REPO / "manuscript" / "tables"
BOOTSTRAP_SEED = 2026072501
BOOTSTRAP_REPLICATES = 50_000
ARMS = ("A", "B", "C", "D")
OUTPUT_LABELS = {
    "evidence_support": (
        "supported_as_written",
        "supported_after_narrowing",
        "contradicted",
        "insufficient_source_evidence",
    ),
    "comparability": (
        "same_estimand",
        "comparable_with_declared_scope",
        "different_estimand",
        "missing_comparison_assumption",
        "not_a_comparability_claim",
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    with staging.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    staging.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(text, encoding="utf-8")
    staging.replace(path)


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot take a percentile of an empty sequence")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def fleiss_kappa(votes: Sequence[Sequence[str]], labels: Sequence[str]) -> float:
    if not votes:
        raise ValueError("Fleiss kappa requires at least one item")
    ratings_per_item = len(votes[0])
    if ratings_per_item < 2 or any(len(row) != ratings_per_item for row in votes):
        raise ValueError("Fleiss kappa requires a fixed number of ratings per item")
    totals: Counter[str] = Counter()
    observed = []
    for row in votes:
        counts = Counter(row)
        totals.update(row)
        observed.append(
            (
                sum(count * count for count in counts.values())
                - ratings_per_item
            )
            / (ratings_per_item * (ratings_per_item - 1))
        )
    mean_observed = sum(observed) / len(observed)
    denominator = len(votes) * ratings_per_item
    expected = sum((totals[label] / denominator) ** 2 for label in labels)
    if expected == 1.0:
        return float("nan")
    return (mean_observed - expected) / (1.0 - expected)


def pairwise_agreement(votes: Sequence[Sequence[str]]) -> float:
    agreed = 0
    total = 0
    for row in votes:
        for left in range(len(row)):
            for right in range(left + 1, len(row)):
                agreed += int(row[left] == row[right])
                total += 1
    return agreed / total


def positive_agreement(votes: Sequence[Sequence[str]], label: str) -> float:
    numerator = 0
    denominator = 0
    for row in votes:
        positive = sum(value == label for value in row)
        numerator += positive * (positive - 1)
        denominator += positive * (len(row) - 1)
    return numerator / denominator if denominator else float("nan")


def reference_reliability(
    gold_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for output, labels in OUTPUT_LABELS.items():
        field = (
            "evidence_support_label"
            if output == "evidence_support"
            else "comparability_label"
        )
        by_claim: dict[str, list[str]] = defaultdict(list)
        for row in gold_rows:
            by_claim[row["claim_id"]].append(row[field])
        if any(len(votes) != 3 for votes in by_claim.values()):
            raise ValueError(f"{output} reference does not have three votes per claim")
        votes = list(by_claim.values())
        total_ratings = len(votes) * 3
        rows.append(
            {
                "output": output,
                "class_label": "ALL",
                "claims": len(votes),
                "ratings": total_ratings,
                "rating_prevalence": "",
                "claims_with_any_label": "",
                "unanimous_claims": sum(len(set(row)) == 1 for row in votes),
                "raw_pairwise_agreement": pairwise_agreement(votes),
                "fleiss_kappa": fleiss_kappa(votes, labels),
                "positive_agreement": "",
            }
        )
        for label in labels:
            binary_votes = [
                [label if value == label else "other" for value in row]
                for row in votes
            ]
            label_ratings = sum(value == label for row in votes for value in row)
            rows.append(
                {
                    "output": output,
                    "class_label": label,
                    "claims": len(votes),
                    "ratings": total_ratings,
                    "rating_prevalence": label_ratings / total_ratings,
                    "claims_with_any_label": sum(
                        label in row for row in votes
                    ),
                    "unanimous_claims": sum(
                        set(row) == {label} for row in votes
                    ),
                    "raw_pairwise_agreement": pairwise_agreement(binary_votes),
                    "fleiss_kappa": fleiss_kappa(
                        binary_votes, (label, "other")
                    ),
                    "positive_agreement": positive_agreement(votes, label),
                }
            )
    return rows


def classification_metrics(
    rows: Sequence[Mapping[str, str]],
    output: str,
    arm: str,
) -> tuple[float, dict[str, dict[str, float | int]]]:
    labels = OUTPUT_LABELS[output]
    gold_field = f"gold_{output}_label"
    prediction_field = f"arm_{arm}_{output}_majority"
    confusion = Counter(
        (row[gold_field], row[prediction_field])
        for row in rows
    )
    per_class: dict[str, dict[str, float | int]] = {}
    f1_values = []
    for label in labels:
        true_positive = confusion[(label, label)]
        support = sum(
            count
            for (gold, _prediction), count in confusion.items()
            if gold == label
        )
        predicted = sum(
            count
            for (_gold, prediction), count in confusion.items()
            if prediction == label
        )
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / support if support else float("nan")
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if support and precision + recall
            else 0.0
        )
        per_class[label] = {
            "support": support,
            "predicted": predicted,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        f1_values.append(f1)
    return sum(f1_values) / len(f1_values), per_class


def source_bootstrap_metrics(
    rows: Sequence[Mapping[str, str]],
    output: str,
    arm: str,
    replicates: int,
    seed: int,
) -> list[float]:
    by_source: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row["source_key"]].append(row)
    sources = sorted(by_source)
    rng = random.Random(seed)
    macro_f1: list[float] = []
    for _ in range(replicates):
        sampled: list[Mapping[str, str]] = []
        for _source in sources:
            sampled.extend(by_source[sources[rng.randrange(len(sources))]])
        macro, _per_class = classification_metrics(sampled, output, arm)
        macro_f1.append(macro)
    return macro_f1


def positive_source_bootstrap_recall(
    rows: Sequence[Mapping[str, str]],
    output: str,
    arm: str,
    label: str,
    replicates: int,
    seed: int,
) -> tuple[int, list[float]]:
    gold_field = f"gold_{output}_label"
    prediction_field = f"arm_{arm}_{output}_majority"
    by_source: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        if row[gold_field] == label:
            by_source[row["source_key"]].append(row)
    sources = sorted(by_source)
    if len(sources) < 2:
        return len(sources), []
    rng = random.Random(seed)
    estimates = []
    for _ in range(replicates):
        correct = 0
        total = 0
        for _source in sources:
            sampled = by_source[sources[rng.randrange(len(sources))]]
            correct += sum(row[prediction_field] == label for row in sampled)
            total += len(sampled)
        estimates.append(correct / total)
    return len(sources), estimates


def per_class_performance(
    claim_rows: Sequence[Mapping[str, str]],
    replicates: int,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for output, labels in OUTPUT_LABELS.items():
        resolved = [
            row
            for row in claim_rows
            if row[f"gold_{output}_status"] == "resolved"
        ]
        for arm_index, arm in enumerate(ARMS):
            macro, per_class = classification_metrics(resolved, output, arm)
            macro_bootstrap = source_bootstrap_metrics(
                resolved,
                output,
                arm,
                replicates,
                BOOTSTRAP_SEED + 100 * arm_index + (0 if output == "evidence_support" else 10),
            )
            macro_low = percentile(macro_bootstrap, 0.025)
            macro_high = percentile(macro_bootstrap, 0.975)
            for label_index, label in enumerate(labels):
                positive_sources, values = positive_source_bootstrap_recall(
                    resolved,
                    output,
                    arm,
                    label,
                    replicates,
                    BOOTSTRAP_SEED
                    + 1000 * arm_index
                    + 100 * label_index
                    + (0 if output == "evidence_support" else 10),
                )
                metrics = per_class[label]
                result.append(
                    {
                        "output": output,
                        "arm": arm,
                        "class_label": label,
                        "support": metrics["support"],
                        "predicted": metrics["predicted"],
                        "precision": metrics["precision"],
                        "recall": metrics["recall"],
                        "recall_ci95_low": (
                            percentile(values, 0.025) if values else ""
                        ),
                        "recall_ci95_high": (
                            percentile(values, 0.975) if values else ""
                        ),
                        "f1": metrics["f1"],
                        "macro_f1": macro,
                        "macro_f1_ci95_low": macro_low,
                        "macro_f1_ci95_high": macro_high,
                        "bootstrap_replicates": replicates,
                        "valid_recall_replicates": len(values),
                        "positive_source_clusters": positive_sources,
                        "recall_interval_method": (
                            "positive-source-cluster bootstrap"
                            if values
                            else "not estimable: fewer than two positive source clusters"
                        ),
                    }
                )
    return result


def strict_majority(values: Sequence[str]) -> str | None:
    counts = Counter(values)
    label, count = counts.most_common(1)[0]
    return label if count >= 2 else None


def d_minus_c(
    claim_rows: Sequence[Mapping[str, str]],
    reference: Mapping[str, str | set[str]],
    *,
    no_consensus_score: float = 0.0,
    require_both_consensus: bool = False,
) -> tuple[int, float]:
    differences = []
    for row in claim_rows:
        claim_id = row["claim_id"]
        if claim_id not in reference:
            continue
        c_label = row["arm_C_comparability_majority"]
        d_label = row["arm_D_comparability_majority"]
        if require_both_consensus and "no_consensus" in {c_label, d_label}:
            continue
        accepted = reference[claim_id]

        def score(label: str) -> float:
            if label == "no_consensus":
                return no_consensus_score
            if isinstance(accepted, set):
                return float(label in accepted)
            return float(label == accepted)

        differences.append(score(d_label) - score(c_label))
    if not differences:
        raise ValueError("reference sensitivity has no eligible claims")
    return len(differences), sum(differences) / len(differences)


def reference_sensitivity(
    gold_rows: Sequence[Mapping[str, str]],
    adjudication_rows: Sequence[Mapping[str, str]],
    claim_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    experts: dict[str, list[str]] = defaultdict(list)
    for row in gold_rows:
        experts[row["claim_id"]].append(row["comparability_label"])
    adjudicators: dict[str, dict[str, str]] = defaultdict(dict)
    for row in adjudication_rows:
        label = row["adjudicated_comparability_label"]
        if label:
            adjudicators[row["release_participant_id"]][row["claim_id"]] = label
    if len(adjudicators) != 2:
        raise ValueError("expected exactly two public adjudicators")

    final_reference = {
        row["claim_id"]: row["gold_comparability_label"]
        for row in claim_rows
        if row["gold_comparability_status"] == "resolved"
    }
    unanimous = {
        claim_id: labels[0]
        for claim_id, labels in experts.items()
        if len(set(labels)) == 1
    }
    expert_majority = {
        claim_id: majority
        for claim_id, labels in experts.items()
        if (majority := strict_majority(labels)) is not None
    }
    any_expert = {
        claim_id: set(labels) for claim_id, labels in experts.items()
    }

    analyses: list[tuple[str, Mapping[str, str | set[str]], str]] = [
        (
            "final_resolved_reference",
            final_reference,
            "Final reference; unanimous experts or two agreeing adjudicators.",
        ),
        (
            "three_experts_unanimous",
            unanimous,
            "Claims on which all three reference experts agreed before adjudication.",
        ),
        (
            "three_experts_majority",
            expert_majority,
            "Pre-adjudication two-of-three expert majority; all-different claims omitted.",
        ),
        (
            "compatible_with_any_expert",
            any_expert,
            "Prediction counted compatible when any reference expert selected it.",
        ),
    ]
    for index, (participant, decisions) in enumerate(
        sorted(adjudicators.items()), start=1
    ):
        composite = dict(unanimous)
        composite.update(decisions)
        analyses.append(
            (
                f"adjudicator_{index}_composite",
                composite,
                "Unanimous expert labels plus this adjudicator on every disputed claim.",
            )
        )

    rows: list[dict[str, object]] = []
    for name, reference, description in analyses:
        count, estimate = d_minus_c(claim_rows, reference)
        rows.append(
            {
                "analysis": name,
                "claims": count,
                "d_minus_c": estimate,
                "description": description,
            }
        )

    count, estimate = d_minus_c(
        claim_rows,
        final_reference,
        require_both_consensus=True,
    )
    rows.append(
        {
            "analysis": "final_reference_both_arms_consensus",
            "claims": count,
            "d_minus_c": estimate,
            "description": "Final reference, excluding claims with no consensus in C or D.",
        }
    )
    count, estimate = d_minus_c(
        claim_rows,
        final_reference,
        no_consensus_score=0.5,
    )
    rows.append(
        {
            "analysis": "final_reference_half_credit_no_consensus",
            "claims": count,
            "d_minus_c": estimate,
            "description": "Final reference, scoring a no-consensus panel as 0.5.",
        }
    )

    adjudicator_ids = sorted(adjudicators)
    disputed_claims = sorted(set(adjudicators[adjudicator_ids[0]]))
    if set(disputed_claims) != set(adjudicators[adjudicator_ids[1]]):
        raise ValueError("adjudicators do not cover the same disputed claims")
    agreed = {
        claim_id: adjudicators[adjudicator_ids[0]][claim_id]
        for claim_id in disputed_claims
        if adjudicators[adjudicator_ids[0]][claim_id]
        == adjudicators[adjudicator_ids[1]][claim_id]
    }
    count, estimate = d_minus_c(claim_rows, agreed)
    rows.append(
        {
            "analysis": "adjudicator_agreement_subset",
            "claims": count,
            "d_minus_c": estimate,
            "description": "Only disputed claims on which both adjudicators agreed.",
        }
    )
    agreement = {
        "disputed_comparability_claims": len(disputed_claims),
        "adjudicators_agree": len(agreed),
        "adjudicators_disagree": len(disputed_claims) - len(agreed),
        "adjudicator_agreement_rate": len(agreed) / len(disputed_claims),
    }
    return rows, agreement


def sampling_mismatch(
    claim_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    resolved = [
        row
        for row in claim_rows
        if row["gold_comparability_status"] == "resolved"
    ]
    strata = ("c2_decisive", "c5_decisive", "all")
    rows = []
    for stratum in strata:
        selected = (
            resolved
            if stratum == "all"
            else [row for row in resolved if row["primary_stratum"] == stratum]
        )
        mismatches = [
            row
            for row in selected
            if row["gold_comparability_label"] == "not_a_comparability_claim"
        ]
        rows.append(
            {
                "sampling_stratum": stratum,
                "resolved_claims": len(selected),
                "not_a_comparability_claim": len(mismatches),
                "rate": len(mismatches) / len(selected),
                "affected_sources": len(
                    {row["source_key"] for row in mismatches}
                ),
            }
        )
    return rows


def participant_permutation(
    arm_rows: Sequence[Mapping[str, str]],
    claim_rows: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    reference = {
        row["claim_id"]: row["gold_comparability_label"]
        for row in claim_rows
        if row["gold_comparability_status"] == "resolved"
    }
    scores: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in arm_rows:
        if row["arm"] not in {"C", "D"} or row["claim_id"] not in reference:
            continue
        scores[(row["arm"], row["release_participant_id"])].append(
            int(row["comparability_label"] == reference[row["claim_id"]])
        )
    participant_rows = [
        (arm, participant, sum(values) / len(values), len(values))
        for (arm, participant), values in sorted(scores.items())
    ]
    if Counter(arm for arm, _participant, _score, _n in participant_rows) != {
        "C": 6,
        "D": 6,
    }:
        raise ValueError("participant analysis requires six C and six D auditors")
    values = [score for _arm, _participant, score, _n in participant_rows]
    observed = (
        sum(score for arm, _participant, score, _n in participant_rows if arm == "D")
        / 6
        - sum(
            score
            for arm, _participant, score, _n in participant_rows
            if arm == "C"
        )
        / 6
    )
    extreme = 0
    assignments = 0
    from itertools import combinations

    for d_indices in combinations(range(12), 6):
        selected = set(d_indices)
        estimate = (
            sum(values[index] for index in selected) / 6
            - sum(values[index] for index in range(12) if index not in selected)
            / 6
        )
        assignments += 1
        extreme += int(abs(estimate) >= abs(observed) - 1.0e-15)
    return {
        "auditors": 12,
        "auditors_per_arm": 6,
        "estimate": observed,
        "exact_conditional_p_two_sided": extreme / assignments,
        "assignments": assignments,
        "arm_C_minimum": min(
            score for arm, _participant, score, _n in participant_rows if arm == "C"
        ),
        "arm_C_maximum": max(
            score for arm, _participant, score, _n in participant_rows if arm == "C"
        ),
        "arm_D_minimum": min(
            score for arm, _participant, score, _n in participant_rows if arm == "D"
        ),
        "arm_D_maximum": max(
            score for arm, _participant, score, _n in participant_rows if arm == "D"
        ),
    }


def format_percent(value: float, digits: int = 1) -> str:
    return f"{100.0 * value:.{digits}f}\\%"


def render_reference_table(
    reliability: Sequence[Mapping[str, object]],
    sensitivity: Sequence[Mapping[str, object]],
    adjudicator_agreement: Mapping[str, object],
) -> str:
    overall = {
        row["output"]: row
        for row in reliability
        if row["class_label"] == "ALL"
    }
    selected = {
        row["analysis"]: row
        for row in sensitivity
    }
    return rf"""\begin{{table*}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{5pt}}
\begin{{tabular}}{{lrrrr}}
\toprule
\textbf{{Reference diagnostic}} & \textbf{{$n$}} &
\textbf{{Unanimous}} & \textbf{{Pair agree.}} & \textbf{{$\kappa$}} \\
\midrule
Evidence-support experts & 480 &
{overall['evidence_support']['unanimous_claims']} &
{format_percent(float(overall['evidence_support']['raw_pairwise_agreement']))} &
{float(overall['evidence_support']['fleiss_kappa']):.3f} \\
Comparability experts & 480 &
{overall['comparability']['unanimous_claims']} &
{format_percent(float(overall['comparability']['raw_pairwise_agreement']))} &
{float(overall['comparability']['fleiss_kappa']):.3f} \\
Comparability adjudicators & {adjudicator_agreement['disputed_comparability_claims']} &
{adjudicator_agreement['adjudicators_agree']} &
{format_percent(float(adjudicator_agreement['adjudicator_agreement_rate']))} &
--- \\
\bottomrule
\end{{tabular}}

\vspace{{4pt}}
\begin{{tabular}}{{lrr}}
\toprule
\textbf{{Comparability reference/scoring rule}} & \textbf{{$n$}} &
\textbf{{D$-$C agreement}} \\
\midrule
Three experts unanimous &
{selected['three_experts_unanimous']['claims']} &
{format_percent(float(selected['three_experts_unanimous']['d_minus_c']))} \\
Three-expert majority &
{selected['three_experts_majority']['claims']} &
{format_percent(float(selected['three_experts_majority']['d_minus_c']))} \\
Final adjudicated reference &
{selected['final_resolved_reference']['claims']} &
{format_percent(float(selected['final_resolved_reference']['d_minus_c']))} \\
Adjudicator 1 composite &
{selected['adjudicator_1_composite']['claims']} &
{format_percent(float(selected['adjudicator_1_composite']['d_minus_c']))} \\
Adjudicator 2 composite &
{selected['adjudicator_2_composite']['claims']} &
{format_percent(float(selected['adjudicator_2_composite']['d_minus_c']))} \\
Both arm panels reach consensus &
{selected['final_reference_both_arms_consensus']['claims']} &
{format_percent(float(selected['final_reference_both_arms_consensus']['d_minus_c']))} \\
\bottomrule
\end{{tabular}}
\caption{{Pre-adjudication reference reliability and reference/scoring
sensitivity. ``Agreement'' is exact agreement with the indicated reference,
not criterion validity. The reference instructions contain capability and
policy concepts also made explicit in Arm D, so none of these rows identifies
a prompt effect. Class-specific reliability and source-bootstrap performance
intervals are reported in the appendix and release.}}
\label{{tab:main-v3-reference-diagnostics}}
\end{{table*}}
"""


def render_class_table(
    performance: Sequence[Mapping[str, object]],
) -> str:
    selected = [
        row for row in performance if row["output"] == "comparability"
    ]
    by_arm: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in selected:
        by_arm[str(row["arm"])].append(row)
    lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule",
        (
            r"Arm & Class & Support & Precision & Recall [source-bootstrap 95\% CI]"
            r" & F1 & Macro-F1 [95\% CI] \\"
        ),
        r"\midrule",
    ]
    display = {
        "same_estimand": "Same estimand",
        "comparable_with_declared_scope": "Scoped",
        "different_estimand": "Different",
        "missing_comparison_assumption": "Missing assumption",
        "not_a_comparability_claim": "Not comparison",
    }
    for arm in ARMS:
        for index, row in enumerate(by_arm[arm]):
            if row["recall_ci95_low"] == "":
                recall_interval = "---"
            else:
                recall_interval = (
                    f"[{float(row['recall_ci95_low']):.3f}, "
                    f"{float(row['recall_ci95_high']):.3f}]"
                )
            macro = (
                f"{float(row['macro_f1']):.3f} "
                f"[{float(row['macro_f1_ci95_low']):.3f}, "
                f"{float(row['macro_f1_ci95_high']):.3f}]"
                if index == 0
                else ""
            )
            lines.append(
                f"{arm if index == 0 else ''} & "
                f"{display[str(row['class_label'])]} & "
                f"{row['support']} & "
                f"{float(row['precision']):.3f} & "
                f"{float(row['recall']):.3f} {recall_interval} & "
                f"{float(row['f1']):.3f} & {macro} \\\\"
            )
        if arm != ARMS[-1]:
            lines.append(r"\addlinespace")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            (
                r"\caption{Comparability agreement with the final reference by "
                r"class. Undefined precision is set to zero when an arm never "
                r"predicts a class. Macro-F1 intervals resample all 80 source "
                r"clusters; recall intervals resample source clusters among "
                r"positive-reference claims. The rare-class intervals are "
                r"correspondingly wide, and the reference-incorporation "
                r"limitation applies to every row.}"
            ),
            r"\label{tab:v3-class-performance}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def render_reference_class_table(
    reliability: Sequence[Mapping[str, object]],
) -> str:
    display = {
        "supported_as_written": "Supported as written",
        "supported_after_narrowing": "Supported after narrowing",
        "contradicted": "Contradicted",
        "insufficient_source_evidence": "Insufficient evidence",
        "same_estimand": "Same estimand",
        "comparable_with_declared_scope": "Scoped",
        "different_estimand": "Different estimand",
        "missing_comparison_assumption": "Missing assumption",
        "not_a_comparability_claim": "Not comparison",
    }
    output_display = {
        "evidence_support": "Support",
        "comparability": "Comparability",
    }
    lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{llrrrrr}",
        r"\toprule",
        (
            r"Output & Reference class & Rating prevalence & Claims with class"
            r" & Unanimous class & Positive agreement & Binary $\kappa$ \\"
        ),
        r"\midrule",
    ]
    current_output = ""
    for row in reliability:
        if row["class_label"] == "ALL":
            continue
        output = str(row["output"])
        if current_output and output != current_output:
            lines.append(r"\addlinespace")
        lines.append(
            f"{output_display[output] if output != current_output else ''} & "
            f"{display[str(row['class_label'])]} & "
            f"{format_percent(float(row['rating_prevalence']))} & "
            f"{row['claims_with_any_label']} & "
            f"{row['unanimous_claims']} & "
            f"{float(row['positive_agreement']):.3f} & "
            f"{float(row['fleiss_kappa']):.3f} \\\\"
        )
        current_output = output
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            (
                r"\caption{Pre-adjudication class-specific reliability of the "
                r"three-expert reference panel. Positive agreement conditions "
                r"on a pair containing the class; binary $\kappa$ treats each "
                r"class against all other labels. Rare classes have few "
                r"positive ratings, so high overall negative agreement should "
                r"not be read as reliable positive identification.}"
            ),
            r"\label{tab:v3-reference-class-reliability}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tables-dir", type=Path, default=DEFAULT_TABLES)
    parser.add_argument(
        "--bootstrap-replicates",
        type=int,
        default=BOOTSTRAP_REPLICATES,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bootstrap_replicates < 1:
        raise ValueError("--bootstrap-replicates must be positive")
    gold = read_csv(args.release_root / "public_gold_ratings.csv")
    arms = read_csv(args.release_root / "public_arm_ratings.csv")
    adjudications = read_csv(args.release_root / "public_adjudications.csv")
    claims = read_csv(args.release_root / "analysis_claim_level.csv")

    reliability = reference_reliability(gold)
    performance = per_class_performance(
        claims, args.bootstrap_replicates
    )
    sensitivity, adjudicator_agreement = reference_sensitivity(
        gold, adjudications, claims
    )
    mismatch = sampling_mismatch(claims)
    participant = participant_permutation(arms, claims)

    write_csv(
        args.output_dir / "v3_reference_reliability.csv",
        (
            "output",
            "class_label",
            "claims",
            "ratings",
            "rating_prevalence",
            "claims_with_any_label",
            "unanimous_claims",
            "raw_pairwise_agreement",
            "fleiss_kappa",
            "positive_agreement",
        ),
        reliability,
    )
    write_csv(
        args.output_dir / "v3_per_class_performance.csv",
        (
            "output",
            "arm",
            "class_label",
            "support",
            "predicted",
            "precision",
            "recall",
            "recall_ci95_low",
            "recall_ci95_high",
            "f1",
            "macro_f1",
            "macro_f1_ci95_low",
            "macro_f1_ci95_high",
            "bootstrap_replicates",
            "valid_recall_replicates",
            "positive_source_clusters",
            "recall_interval_method",
        ),
        performance,
    )
    write_csv(
        args.output_dir / "v3_reference_sensitivity.csv",
        ("analysis", "claims", "d_minus_c", "description"),
        sensitivity,
    )
    write_csv(
        args.output_dir / "v3_sampling_mismatch.csv",
        (
            "sampling_stratum",
            "resolved_claims",
            "not_a_comparability_claim",
            "rate",
            "affected_sources",
        ),
        mismatch,
    )
    summary = {
        "schema_version": "v3-review-diagnostics-v1",
        "bootstrap": {
            "replicates": args.bootstrap_replicates,
            "seed": BOOTSTRAP_SEED,
            "unit": "source",
        },
        "reference_reliability": reliability,
        "reference_sensitivity": sensitivity,
        "adjudicator_agreement": adjudicator_agreement,
        "sampling_mismatch": mismatch,
        "participant_randomization_unit_analysis": participant,
        "interpretation": (
            "Agreement with the reference is not criterion validity because "
            "the reference rubric incorporates capability and policy concepts."
        ),
    }
    write_text(
        args.output_dir / "v3_review_diagnostics.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        args.tables_dir / "main_v3_reference_diagnostics.tex",
        render_reference_table(reliability, sensitivity, adjudicator_agreement),
    )
    write_text(
        args.tables_dir / "v3_class_performance.tex",
        render_class_table(performance),
    )
    write_text(
        args.tables_dir / "v3_reference_class_reliability.tex",
        render_reference_class_table(reliability),
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "bootstrap_replicates": args.bootstrap_replicates,
                "outputs": [
                    str(args.output_dir / "v3_review_diagnostics.json"),
                    str(args.tables_dir / "main_v3_reference_diagnostics.tex"),
                    str(args.tables_dir / "v3_class_performance.tex"),
                    str(
                        args.tables_dir
                        / "v3_reference_class_reliability.tex"
                    ),
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
