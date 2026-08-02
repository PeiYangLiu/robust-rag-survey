#!/usr/bin/env python3
"""Run source-cluster and reference-label sensitivity analyses for the claim audit."""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter
from pathlib import Path

from analyze_claim_rule_reliability import (
    ADJUDICATED,
    AUDIT,
    HUMAN,
    MAJORITY,
    MANUSCRIPT,
    MODEL_RULES,
    RULE_LABELS,
    SAMPLE_KEY,
    SUPPLEMENT,
    agreement_metrics,
    exact_mcnemar,
    model_predictions,
    read_csv,
    write_csv,
)


BOOTSTRAP_REPETITIONS = 50_000
BOOTSTRAP_SEED = 20260714

PREDICTION_OUTPUT = SUPPLEMENT / "claim_rule_predictions.csv"
INTERVAL_OUTPUT = SUPPLEMENT / "claim_rule_cluster_intervals.csv"
SOURCE_OUTPUT = SUPPLEMENT / "claim_source_sensitivity.csv"
REFERENCE_OUTPUT = SUPPLEMENT / "claim_reference_sensitivity.csv"
FIELD_OUTPUT = SUPPLEMENT / "model_human_field_alignment.csv"
ARCHETYPE_OUTPUT = SUPPLEMENT / "claim_archetype_cluster_intervals.csv"
SUMMARY_OUTPUT = SUPPLEMENT / "claim_source_sensitivity_summary.json"

RULE_TABLE = MANUSCRIPT / "tables" / "main_rule_reliability_clustered.tex"
SOURCE_TABLE = MANUSCRIPT / "tables" / "main_source_sensitivity.tex"
REFERENCE_TABLE = MANUSCRIPT / "tables" / "reference_label_sensitivity.tex"
FIELD_TABLE = MANUSCRIPT / "tables" / "model_human_field_alignment.tex"
ARCHETYPE_TABLE = MANUSCRIPT / "tables" / "rule_reliability_by_archetype_clustered.tex"

METRICS = ("exact_accuracy", "cohen_kappa", "macro_f1")
METRIC_LABELS = {
    "exact_accuracy": "Exact accuracy",
    "cohen_kappa": "Cohen's $\\kappa$",
    "macro_f1": "Macro-F1",
}


def percentile(values: list[float], quantile: float) -> float:
    clean = sorted(value for value in values if not math.isnan(value))
    if not clean:
        return math.nan
    index = (len(clean) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return clean[lower]
    fraction = index - lower
    return clean[lower] * (1.0 - fraction) + clean[upper] * fraction


def interval(values: list[float]) -> tuple[float, float]:
    return percentile(values, 0.025), percentile(values, 0.975)


def metrics_for_instances(
    predicted: dict[str, str],
    gold: dict[str, str],
    instances: list[str],
) -> dict[str, object]:
    expanded_prediction = {
        f"{index}:{annotation_id}": predicted[annotation_id]
        for index, annotation_id in enumerate(instances)
    }
    expanded_gold = {
        f"{index}:{annotation_id}": gold[annotation_id]
        for index, annotation_id in enumerate(instances)
    }
    return agreement_metrics(expanded_prediction, expanded_gold)


def source_clusters(
    sample_by_id: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = {}
    for annotation_id, row in sample_by_id.items():
        clusters.setdefault(row["source_key"], []).append(annotation_id)
    return {key: sorted(value) for key, value in sorted(clusters.items())}


def cluster_bootstrap(
    predictions: dict[str, dict[str, str]],
    gold: dict[str, str],
    clusters: dict[str, list[str]],
    repetitions: int,
    seed: int,
) -> tuple[list[dict[str, object]], dict[str, dict[str, list[float]]]]:
    cluster_names = sorted(clusters)
    samples = {
        rule: {metric: [] for metric in METRICS}
        for rule in MODEL_RULES
    }
    differences = {metric: [] for metric in METRICS}
    rng = random.Random(seed)

    for _ in range(repetitions):
        selected = rng.choices(cluster_names, k=len(cluster_names))
        instances = [
            annotation_id
            for source_key in selected
            for annotation_id in clusters[source_key]
        ]
        iteration = {}
        for rule in MODEL_RULES:
            result = metrics_for_instances(predictions[rule], gold, instances)
            iteration[rule] = result
            for metric in METRICS:
                samples[rule][metric].append(float(result[metric]))
        for metric in METRICS:
            differences[metric].append(
                float(iteration["full_schema_model"][metric])
                - float(iteration["evidence_control_baseline"][metric])
            )

    rows: list[dict[str, object]] = []
    point_metrics = {
        rule: agreement_metrics(predictions[rule], gold)
        for rule in MODEL_RULES
    }
    for rule in MODEL_RULES:
        for metric in METRICS:
            low, high = interval(samples[rule][metric])
            rows.append(
                {
                    "comparison": rule,
                    "comparison_label": RULE_LABELS[rule],
                    "metric": metric,
                    "point_estimate": point_metrics[rule][metric],
                    "ci_low": low,
                    "ci_high": high,
                    "clusters": len(cluster_names),
                    "bootstrap_repetitions": repetitions,
                    "seed": seed,
                    "resampling_unit": "source_key",
                }
            )

    baseline = point_metrics["evidence_control_baseline"]
    full_rule = point_metrics["full_schema_model"]
    for metric in METRICS:
        low, high = interval(differences[metric])
        rows.append(
            {
                "comparison": "full_minus_evidence_control",
                "comparison_label": "Full minus C2/C5 ablation",
                "metric": metric,
                "point_estimate": float(full_rule[metric]) - float(baseline[metric]),
                "ci_low": low,
                "ci_high": high,
                "clusters": len(cluster_names),
                "bootstrap_repetitions": repetitions,
                "seed": seed,
                "resampling_unit": "source_key",
            }
        )
    return rows, samples


def source_sensitivity_rows(
    predictions: dict[str, dict[str, str]],
    gold: dict[str, str],
    clusters: dict[str, list[str]],
) -> list[dict[str, object]]:
    rows = []
    all_ids = set(gold)
    baseline = predictions["evidence_control_baseline"]
    full_rule = predictions["full_schema_model"]
    for source_key, source_ids in clusters.items():
        within_gold = {item: gold[item] for item in source_ids}
        within_baseline = {item: baseline[item] for item in source_ids}
        within_full = {item: full_rule[item] for item in source_ids}
        within_baseline_metrics = agreement_metrics(within_baseline, within_gold)
        within_full_metrics = agreement_metrics(within_full, within_gold)

        remaining = sorted(all_ids - set(source_ids))
        remaining_gold = {item: gold[item] for item in remaining}
        remaining_baseline = {item: baseline[item] for item in remaining}
        remaining_full = {item: full_rule[item] for item in remaining}
        baseline_metrics = agreement_metrics(remaining_baseline, remaining_gold)
        full_metrics = agreement_metrics(remaining_full, remaining_gold)
        rows.append(
            {
                "source_key": source_key,
                "source_n": len(source_ids),
                "baseline_correct_within_source": sum(
                    baseline[item] == gold[item] for item in source_ids
                ),
                "full_correct_within_source": sum(
                    full_rule[item] == gold[item] for item in source_ids
                ),
                "within_source_exact_difference": (
                    float(within_full_metrics["exact_accuracy"])
                    - float(within_baseline_metrics["exact_accuracy"])
                ),
                "leave_one_source_out_n": len(remaining),
                "loso_baseline_exact": baseline_metrics["exact_accuracy"],
                "loso_full_exact": full_metrics["exact_accuracy"],
                "loso_exact_difference": (
                    float(full_metrics["exact_accuracy"])
                    - float(baseline_metrics["exact_accuracy"])
                ),
                "loso_kappa_difference": (
                    float(full_metrics["cohen_kappa"])
                    - float(baseline_metrics["cohen_kappa"])
                ),
                "loso_macro_f1_difference": (
                    float(full_metrics["macro_f1"])
                    - float(baseline_metrics["macro_f1"])
                ),
            }
        )
    return rows


def load_reference_labels(
    majority_rows: list[dict[str, str]],
    adjudicated_by_id: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    references = {
        "adjudicated_80": {
            annotation_id: row["final_verdict"]
            for annotation_id, row in adjudicated_by_id.items()
        }
    }
    for annotator in ("A", "B", "C"):
        references[f"coder_{annotator}_80"] = {
            row["annotation_id"]: row["verdict"]
            for row in read_csv(HUMAN / f"annotator_{annotator}_claims_completed.csv")
        }
    references["majority_78"] = {
        row["annotation_id"]: row["verdict_majority"]
        for row in majority_rows
        if row["verdict_majority"]
    }
    references["unanimous_39"] = {
        row["annotation_id"]: row["verdict_majority"]
        for row in majority_rows
        if row["verdict_unanimous"] == "1"
    }
    return references


def reference_sensitivity_rows(
    predictions: dict[str, dict[str, str]],
    references: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    rows = []
    for reference, gold in references.items():
        ids = sorted(gold)
        subset_predictions = {
            rule: {item: predictions[rule][item] for item in ids}
            for rule in ("evidence_control_baseline", "full_schema_model")
        }
        baseline = agreement_metrics(
            subset_predictions["evidence_control_baseline"], gold
        )
        full_rule = agreement_metrics(subset_predictions["full_schema_model"], gold)
        paired = exact_mcnemar(
            subset_predictions["evidence_control_baseline"],
            subset_predictions["full_schema_model"],
            gold,
        )
        rows.append(
            {
                "reference": reference,
                "n": len(ids),
                "baseline_exact": baseline["exact_accuracy"],
                "full_exact": full_rule["exact_accuracy"],
                "exact_difference": (
                    float(full_rule["exact_accuracy"])
                    - float(baseline["exact_accuracy"])
                ),
                "baseline_kappa": baseline["cohen_kappa"],
                "full_kappa": full_rule["cohen_kappa"],
                "kappa_difference": (
                    float(full_rule["cohen_kappa"])
                    - float(baseline["cohen_kappa"])
                ),
                "baseline_macro_f1": baseline["macro_f1"],
                "full_macro_f1": full_rule["macro_f1"],
                "macro_f1_difference": (
                    float(full_rule["macro_f1"])
                    - float(baseline["macro_f1"])
                ),
                **paired,
                "interpretation": (
                    "adjudicated_reference"
                    if reference == "adjudicated_80"
                    else "pre_adjudication_reference_sensitivity_not_gold"
                ),
            }
        )
    return rows


def categorical_agreement(
    first: list[str], second: list[str]
) -> tuple[float, float, float]:
    if len(first) != len(second) or not first:
        raise ValueError("categorical agreement inputs must be nonempty and aligned")
    labels = sorted(set(first) | set(second))
    n = len(first)
    observed = sum(left == right for left, right in zip(first, second)) / n
    expected = sum(
        first.count(label) / n * second.count(label) / n for label in labels
    )
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0
    if len(labels) == 1:
        ac1 = 1.0
    else:
        average_marginals = {
            label: (first.count(label) + second.count(label)) / (2 * n)
            for label in labels
        }
        chance_ac1 = sum(
            probability * (1 - probability)
            for probability in average_marginals.values()
        ) / (len(labels) - 1)
        ac1 = (
            (observed - chance_ac1) / (1 - chance_ac1)
            if chance_ac1 < 1
            else 1.0
        )
    return observed, kappa, ac1


def field_alignment_rows(
    audit_by_id: dict[str, dict[str, str]],
    sample_by_id: dict[str, dict[str, str]],
    adjudicated_by_id: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    fields = (
        ("archetype", "final_archetype"),
        ("c1_relation", "final_c1_relation"),
        ("c2_relation", "final_c2_relation"),
        ("c3_relation", "final_c3_relation"),
        ("c4_relation", "final_c4_relation"),
        ("c5_relation", "final_c5_relation"),
        ("controls_status", "final_controls_status"),
    )
    rows = []
    for model_field, human_field in fields:
        model_values = []
        human_values = []
        for annotation_id in sorted(sample_by_id):
            audit = audit_by_id[sample_by_id[annotation_id]["candidate_id"]]
            model_values.append(audit[model_field])
            human_values.append(adjudicated_by_id[annotation_id][human_field])
        raw, kappa, ac1 = categorical_agreement(model_values, human_values)
        rows.append(
            {
                "field": model_field,
                "n": len(model_values),
                "raw_agreement": raw,
                "cohen_kappa": kappa,
                "gwet_ac1": ac1,
                "model_distribution": json.dumps(
                    Counter(model_values), sort_keys=True
                ),
                "human_distribution": json.dumps(
                    Counter(human_values), sort_keys=True
                ),
                "interpretation": "model_coding_vs_adjudicated_human_field",
            }
        )
    return rows


def archetype_interval_rows(
    predictions: dict[str, dict[str, str]],
    gold: dict[str, str],
    cluster_by_id: dict[str, str],
    adjudicated_by_id: dict[str, dict[str, str]],
    repetitions: int,
    seed: int,
) -> list[dict[str, object]]:
    rows = []
    archetypes = sorted(
        {row["final_archetype"] for row in adjudicated_by_id.values()}
    )
    for archetype_index, archetype in enumerate(archetypes):
        ids = sorted(
            annotation_id
            for annotation_id, row in adjudicated_by_id.items()
            if row["final_archetype"] == archetype
        )
        clusters: dict[str, list[str]] = {}
        for annotation_id in ids:
            clusters.setdefault(cluster_by_id[annotation_id], []).append(annotation_id)
        cluster_names = sorted(clusters)
        rng = random.Random(seed + 1000 + archetype_index)
        full_values = []
        difference_values = []
        for _ in range(repetitions):
            selected = rng.choices(cluster_names, k=len(cluster_names))
            instances = [
                annotation_id
                for source_key in selected
                for annotation_id in clusters[source_key]
            ]
            baseline = metrics_for_instances(
                predictions["evidence_control_baseline"], gold, instances
            )
            full_rule = metrics_for_instances(
                predictions["full_schema_model"], gold, instances
            )
            full_values.append(float(full_rule["exact_accuracy"]))
            difference_values.append(
                float(full_rule["exact_accuracy"])
                - float(baseline["exact_accuracy"])
            )
        full_point = metrics_for_instances(
            predictions["full_schema_model"], gold, ids
        )["exact_accuracy"]
        baseline_point = metrics_for_instances(
            predictions["evidence_control_baseline"], gold, ids
        )["exact_accuracy"]
        full_low, full_high = interval(full_values)
        difference_low, difference_high = interval(difference_values)
        rows.append(
            {
                "human_adjudicated_archetype": archetype,
                "n": len(ids),
                "source_clusters": len(cluster_names),
                "full_exact_accuracy": full_point,
                "full_exact_ci_low": full_low,
                "full_exact_ci_high": full_high,
                "full_minus_baseline_exact": float(full_point)
                - float(baseline_point),
                "difference_ci_low": difference_low,
                "difference_ci_high": difference_high,
                "bootstrap_repetitions": repetitions,
                "resampling_unit": "source_key_within_archetype",
                "interpretation": "exploratory_small_stratum",
            }
        )
    return rows


def prediction_rows(
    audit_by_id: dict[str, dict[str, str]],
    sample_by_id: dict[str, dict[str, str]],
    adjudicated_by_id: dict[str, dict[str, str]],
    majority_by_id: dict[str, dict[str, str]],
    predictions: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    coder_labels = {}
    for annotator in ("A", "B", "C"):
        coder_labels[annotator] = {
            row["annotation_id"]: row["verdict"]
            for row in read_csv(HUMAN / f"annotator_{annotator}_claims_completed.csv")
        }
    rows = []
    for annotation_id in sorted(sample_by_id):
        sample = sample_by_id[annotation_id]
        audit = audit_by_id[sample["candidate_id"]]
        gold = adjudicated_by_id[annotation_id]["final_verdict"]
        row: dict[str, object] = {
            "annotation_id": annotation_id,
            "candidate_id": sample["candidate_id"],
            "source_key": sample["source_key"],
            "audit_slice": sample["audit_slice"],
            "balanced_core_16": sample["balanced_core_16"],
            "human_adjudicated_verdict": gold,
            "coder_A_verdict": coder_labels["A"][annotation_id],
            "coder_B_verdict": coder_labels["B"][annotation_id],
            "coder_C_verdict": coder_labels["C"][annotation_id],
            "coder_majority_verdict": majority_by_id[annotation_id][
                "verdict_majority"
            ],
            "coder_unanimous": majority_by_id[annotation_id]["verdict_unanimous"],
            "model_archetype": audit["archetype"],
            "human_archetype": adjudicated_by_id[annotation_id]["final_archetype"],
            "origin_decisive": audit["origin_decisive"],
            "policy_decisive": audit["policy_decisive"],
            "controls_decisive": audit["controls_decisive"],
        }
        for rule in MODEL_RULES:
            row[rule] = predictions[rule][annotation_id]
            row[f"{rule}_correct"] = str(
                predictions[rule][annotation_id] == gold
            ).lower()
        rows.append(row)
    return rows


def render_rule_table(rows: list[dict[str, object]]) -> str:
    by_key = {
        (row["comparison"], row["metric"]): row
        for row in rows
        if row["comparison"] in MODEL_RULES
    }
    body = []
    for rule in MODEL_RULES:
        values = []
        for metric in METRICS:
            row = by_key[(rule, metric)]
            values.append(
                f"{row['point_estimate']:.3f} "
                f"[{row['ci_low']:.3f}, {row['ci_high']:.3f}]"
            )
        body.append(f"{RULE_LABELS[rule]} & " + " & ".join(values) + r" \\")
    return rf"""\begin{{table*}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{5pt}}
\begin{{tabularx}}{{\linewidth}}{{Xccc}}
\toprule
\textbf{{Rule}} & \textbf{{Exact [95\% CI]}} &
\textbf{{$\kappa$ [95\% CI]}} & \textbf{{Macro-F1 [95\% CI]}} \\
\midrule
{chr(10).join(body)}
\bottomrule
\end{{tabularx}}
\caption{{Agreement with adjudicated human verdicts on the 80-claim sample.
Intervals use {BOOTSTRAP_REPETITIONS:,} source-cluster bootstrap resamples
over nine sources. The resampling respects within-source dependence but cannot
make a non-probability, development-overlapping sample representative. All
rows still reuse the same model-coded fields.}}
\label{{tab:main-rule-reliability}}
\end{{table*}}
"""


def render_source_table(
    interval_rows: list[dict[str, object]],
    source_rows: list[dict[str, object]],
) -> str:
    difference = {
        row["metric"]: row
        for row in interval_rows
        if row["comparison"] == "full_minus_evidence_control"
    }
    loso_ranges = {
        "exact_accuracy": (
            min(float(row["loso_exact_difference"]) for row in source_rows),
            max(float(row["loso_exact_difference"]) for row in source_rows),
        ),
        "cohen_kappa": (
            min(float(row["loso_kappa_difference"]) for row in source_rows),
            max(float(row["loso_kappa_difference"]) for row in source_rows),
        ),
        "macro_f1": (
            min(float(row["loso_macro_f1_difference"]) for row in source_rows),
            max(float(row["loso_macro_f1_difference"]) for row in source_rows),
        ),
    }
    body = []
    for metric in METRICS:
        row = difference[metric]
        low, high = loso_ranges[metric]
        body.append(
            f"{METRIC_LABELS[metric]} & {row['point_estimate']:+.3f} & "
            f"[{row['ci_low']:+.3f}, {row['ci_high']:+.3f}] & "
            f"[{low:+.3f}, {high:+.3f}] \\\\"
        )
    return rf"""\begin{{table}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{4pt}}
\begin{{tabularx}}{{\columnwidth}}{{Xrrr}}
\toprule
\textbf{{Full minus C2/C5 ablation}} & \textbf{{Point}} &
\textbf{{Cluster CI}} & \textbf{{LOSO range}} \\
\midrule
{chr(10).join(body)}
\bottomrule
\end{{tabularx}}
\caption{{Source sensitivity of the paired rule comparison. The interval and
leave-one-source-out (LOSO) ranges cross zero; with only nine purposively
selected sources they diagnose instability rather than establish equivalence.}}
\label{{tab:main-source-sensitivity}}
\end{{table}}
"""


def render_reference_table(rows: list[dict[str, object]]) -> str:
    labels = {
        "coder_A_80": "Coder A",
        "coder_B_80": "Coder B",
        "coder_C_80": "Coder C",
        "majority_78": "Available majority",
        "unanimous_39": "Unanimous subset",
        "adjudicated_80": "Adjudicated",
    }
    body = []
    for row in rows:
        body.append(
            f"{labels[row['reference']]} & {row['n']} & "
            f"{row['baseline_exact']:.3f} & {row['full_exact']:.3f} & "
            f"{row['exact_difference']:+.3f} & "
            f"{row['kappa_difference']:+.3f} & "
            f"{row['macro_f1_difference']:+.3f} \\\\"
        )
    return rf"""\begin{{table*}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{6pt}}
\begin{{tabular}}{{lrrrrrr}}
\toprule
\textbf{{Reference labels}} & \textbf{{$n$}} & \textbf{{Ablated exact}} &
\textbf{{Full exact}} & \textbf{{$\Delta$ exact}} &
\textbf{{$\Delta\kappa$}} & \textbf{{$\Delta$ macro-F1}} \\
\midrule
{chr(10).join(body)}
\bottomrule
\end{{tabular}}
\caption{{Sensitivity of the full-versus-ablated comparison to the reference
labels. Individual-coder, majority, and unanimous rows are pre-adjudication
diagnostics, not alternative gold standards. The sign of the exact-agreement
difference changes across references.}}
\label{{tab:reference-label-sensitivity}}
\end{{table*}}
"""


def render_field_table(rows: list[dict[str, object]]) -> str:
    labels = {
        "archetype": "Archetype",
        "c1_relation": "C1 evidence state",
        "c2_relation": "C2 origin/capability",
        "c3_relation": "C3 intervention",
        "c4_relation": "C4 outcome/unit",
        "c5_relation": "C5 policy/utility",
        "controls_status": "Control status",
    }
    body = [
        f"{labels[row['field']]} & {row['raw_agreement']:.3f} & "
        f"{row['cohen_kappa']:.3f} & {row['gwet_ac1']:.3f} \\\\"
        for row in rows
    ]
    return rf"""\begin{{table}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{4pt}}
\begin{{tabularx}}{{\columnwidth}}{{Xrrr}}
\toprule
\textbf{{Field}} & \textbf{{Exact}} & \textbf{{$\kappa$}} &
\textbf{{AC1}} \\
\midrule
{chr(10).join(body)}
\bottomrule
\end{{tabularx}}
\caption{{Agreement between model-coded fields and adjudicated human fields on
the same 80 claims. This separates field extraction/coding disagreement from
the later rule-composition step, although several intermediate rule flags were
not human-adjudicated.}}
\label{{tab:model-human-field-alignment}}
\end{{table}}
"""


def render_archetype_table(rows: list[dict[str, object]]) -> str:
    labels = {
        "A_self_baseline": "Self-baseline",
        "B_shared_harness": "Shared harness",
        "C_cross_source_synthesis": "Cross-source",
        "D_causal_mechanistic": "Causal/mechanistic",
        "E_field_meta": "Field-level",
        "F_policy_utility": "Policy/utility",
    }
    body = []
    for row in rows:
        body.append(
            f"{labels[row['human_adjudicated_archetype']]} & {row['n']} & "
            f"{row['source_clusters']} & {row['full_exact_accuracy']:.3f} "
            f"[{row['full_exact_ci_low']:.3f}, {row['full_exact_ci_high']:.3f}] & "
            f"{row['full_minus_baseline_exact']:+.3f} "
            f"[{row['difference_ci_low']:+.3f}, {row['difference_ci_high']:+.3f}] \\\\"
        )
    return rf"""\begin{{table*}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{6pt}}
\begin{{tabular}}{{lrrrr}}
\toprule
\textbf{{Human-adjudicated archetype}} & \textbf{{$n$}} &
\textbf{{Sources}} & \textbf{{Full exact [95\% CI]}} &
\textbf{{Full--ablated exact [95\% CI]}} \\
\midrule
{chr(10).join(body)}
\bottomrule
\end{{tabular}}
\caption{{Exploratory archetype breakdown with source-cluster intervals.
Small strata and few source clusters yield wide or discrete intervals; the
rows should not be ranked as stable performance estimates.}}
\label{{tab:rule-reliability-by-archetype}}
\end{{table*}}
"""


def main() -> None:
    audit_rows = read_csv(AUDIT)
    audit_by_id = {row["candidate_id"]: row for row in audit_rows}
    sample_rows = read_csv(SAMPLE_KEY)
    sample_by_id = {row["annotation_id"]: row for row in sample_rows}
    adjudicated_rows = read_csv(ADJUDICATED)
    adjudicated_by_id = {row["annotation_id"]: row for row in adjudicated_rows}
    majority_rows = read_csv(MAJORITY)
    majority_by_id = {row["annotation_id"]: row for row in majority_rows}

    if not (
        set(sample_by_id)
        == set(adjudicated_by_id)
        == set(majority_by_id)
    ):
        raise ValueError("human validation ID sets differ")
    gold = {
        annotation_id: row["final_verdict"]
        for annotation_id, row in adjudicated_by_id.items()
    }
    predictions = model_predictions(audit_by_id, sample_by_id)
    clusters = source_clusters(sample_by_id)
    cluster_by_id = {
        annotation_id: source_key
        for source_key, ids in clusters.items()
        for annotation_id in ids
    }

    prediction_detail = prediction_rows(
        audit_by_id,
        sample_by_id,
        adjudicated_by_id,
        majority_by_id,
        predictions,
    )
    write_csv(PREDICTION_OUTPUT, prediction_detail)

    interval_rows, _ = cluster_bootstrap(
        predictions,
        gold,
        clusters,
        BOOTSTRAP_REPETITIONS,
        BOOTSTRAP_SEED,
    )
    write_csv(INTERVAL_OUTPUT, interval_rows)

    source_rows = source_sensitivity_rows(predictions, gold, clusters)
    write_csv(SOURCE_OUTPUT, source_rows)

    references = load_reference_labels(majority_rows, adjudicated_by_id)
    reference_rows = reference_sensitivity_rows(predictions, references)
    write_csv(REFERENCE_OUTPUT, reference_rows)

    field_rows = field_alignment_rows(
        audit_by_id, sample_by_id, adjudicated_by_id
    )
    write_csv(FIELD_OUTPUT, field_rows)

    archetype_rows = archetype_interval_rows(
        predictions,
        gold,
        cluster_by_id,
        adjudicated_by_id,
        BOOTSTRAP_REPETITIONS,
        BOOTSTRAP_SEED,
    )
    write_csv(ARCHETYPE_OUTPUT, archetype_rows)

    difference_rows = {
        row["metric"]: row
        for row in interval_rows
        if row["comparison"] == "full_minus_evidence_control"
    }
    paired = exact_mcnemar(
        predictions["evidence_control_baseline"],
        predictions["full_schema_model"],
        gold,
    )
    reference_exact_differences = [
        float(row["exact_difference"]) for row in reference_rows
    ]
    summary = {
        "status": "source_cluster_and_reference_sensitivity",
        "sample": {
            "claims": len(gold),
            "sources": len(clusters),
            "source_sizes": {key: len(value) for key, value in clusters.items()},
            "probability_sample": False,
            "paper_disjoint_from_codebook_development": False,
        },
        "full_vs_evidence_control": {
            "paired_exact_test": paired,
            "cluster_bootstrap": {
                metric: {
                    "point_estimate": row["point_estimate"],
                    "ci_low": row["ci_low"],
                    "ci_high": row["ci_high"],
                }
                for metric, row in difference_rows.items()
            },
            "loso_exact_difference_range": [
                min(float(row["loso_exact_difference"]) for row in source_rows),
                max(float(row["loso_exact_difference"]) for row in source_rows),
            ],
            "reference_exact_difference_range": [
                min(reference_exact_differences),
                max(reference_exact_differences),
            ],
            "equivalence_test": "not_performed_no_prespecified_margin",
            "interpretation": (
                "underpowered_and_inconclusive; no detectable difference does not "
                "establish equivalence or absence of a practically meaningful effect"
            ),
        },
        "model_human_field_alignment": {
            row["field"]: {
                "raw_agreement": row["raw_agreement"],
                "cohen_kappa": row["cohen_kappa"],
                "gwet_ac1": row["gwet_ac1"],
            }
            for row in field_rows
        },
        "bootstrap": {
            "method": "nonparametric source-cluster bootstrap",
            "repetitions": BOOTSTRAP_REPETITIONS,
            "seed": BOOTSTRAP_SEED,
            "clusters": len(clusters),
            "caveat": "nine purposively selected sources yield unstable intervals",
        },
    }
    SUMMARY_OUTPUT.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    RULE_TABLE.write_text(render_rule_table(interval_rows), encoding="utf-8")
    SOURCE_TABLE.write_text(
        render_source_table(interval_rows, source_rows), encoding="utf-8"
    )
    REFERENCE_TABLE.write_text(
        render_reference_table(reference_rows), encoding="utf-8"
    )
    FIELD_TABLE.write_text(render_field_table(field_rows), encoding="utf-8")
    ARCHETYPE_TABLE.write_text(
        render_archetype_table(archetype_rows), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
