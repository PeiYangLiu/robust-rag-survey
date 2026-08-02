#!/usr/bin/env python3
"""Evaluate claim-audit rules against the adjudicated human validation labels."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from derive_observed_claim_verdicts import fim, five_coordinate, full


MANUSCRIPT = Path(__file__).resolve().parents[1]
SUPPLEMENT = MANUSCRIPT / "supplement"
HUMAN = (
    MANUSCRIPT
    / "human_coding"
    / "observed_claim_human_validation_20260714"
    / "annotated_20260714"
)
AUDIT = SUPPLEMENT / "observed_comparison_claim_audit.csv"
SAMPLE_KEY = HUMAN / "sample_key.csv"
ADJUDICATED = HUMAN / "adjudicated_consensus.csv"
MAJORITY = HUMAN / "analysis_results" / "pre_adjudication" / "majority_consensus.csv"
PAIRWISE = HUMAN / "analysis_results" / "pre_adjudication" / "pairwise_agreement.csv"

RULE_OUTPUT = SUPPLEMENT / "claim_rule_reliability.csv"
ARCHETYPE_OUTPUT = SUPPLEMENT / "claim_rule_reliability_by_archetype.csv"
SAMPLING_OUTPUT = SUPPLEMENT / "human_validation_sampling_audit.csv"
FIELD_OUTPUT = SUPPLEMENT / "human_validation_field_agreement_summary.csv"
ERROR_OUTPUT = SUPPLEMENT / "claim_error_type_audit.csv"
SUMMARY_OUTPUT = SUPPLEMENT / "claim_reliability_summary.json"
RULE_TABLE = MANUSCRIPT / "tables" / "main_rule_reliability.tex"
HUMAN_TABLE = MANUSCRIPT / "tables" / "main_human_validation.tex"
ARCHETYPE_TABLE = MANUSCRIPT / "tables" / "rule_reliability_by_archetype.tex"
FIELD_TABLE = MANUSCRIPT / "tables" / "human_field_agreement.tex"

VERDICTS = ("valid", "partial", "invalid", "under-specified")
MODEL_RULES = (
    "three_field_model",
    "evidence_control_baseline",
    "five_coordinate_model",
    "full_schema_model",
)
RULE_LABELS = {
    "three_field_model": "Three-field taxonomy",
    "evidence_control_baseline": "Evidence+controls (C2/C5 ablated)",
    "five_coordinate_model": "Five coordinates",
    "full_schema_model": "Five coordinates + controls",
    "three_field_human_coordinates": "Three-field rule on adjudicated coordinates",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def agreement_metrics(
    predicted: dict[str, str], gold: dict[str, str]
) -> dict[str, object]:
    if set(predicted) != set(gold):
        raise ValueError("prediction and gold IDs differ")
    ids = sorted(gold)
    n = len(ids)
    exact = sum(predicted[item] == gold[item] for item in ids) / n
    expected = sum(
        sum(predicted[item] == label for item in ids)
        * sum(gold[item] == label for item in ids)
        for label in VERDICTS
    ) / (n * n)
    kappa = (exact - expected) / (1 - expected) if expected < 1 else 1.0

    per_class: dict[str, dict[str, float | int]] = {}
    f1_values = []
    for label in VERDICTS:
        true_positive = sum(
            predicted[item] == label and gold[item] == label for item in ids
        )
        predicted_n = sum(predicted[item] == label for item in ids)
        gold_n = sum(gold[item] == label for item in ids)
        precision = true_positive / predicted_n if predicted_n else 0.0
        recall = true_positive / gold_n if gold_n else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        f1_values.append(f1)
        per_class[label] = {
            "true_positive": true_positive,
            "predicted_n": predicted_n,
            "gold_n": gold_n,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    return {
        "n": n,
        "exact_accuracy": exact,
        "cohen_kappa": kappa,
        "macro_f1": sum(f1_values) / len(f1_values),
        "per_class": per_class,
        "prediction_distribution": dict(Counter(predicted.values())),
        "gold_distribution": dict(Counter(gold.values())),
    }


def exact_mcnemar(
    first: dict[str, str], second: dict[str, str], gold: dict[str, str]
) -> dict[str, float | int]:
    first_only = sum(
        first[item] == gold[item] and second[item] != gold[item] for item in gold
    )
    second_only = sum(
        first[item] != gold[item] and second[item] == gold[item] for item in gold
    )
    discordant = first_only + second_only
    if not discordant:
        p_value = 1.0
    else:
        tail = sum(
            math.comb(discordant, value)
            for value in range(min(first_only, second_only) + 1)
        ) / (2**discordant)
        p_value = min(1.0, 2 * tail)
    return {
        "first_only_correct": first_only,
        "second_only_correct": second_only,
        "discordant": discordant,
        "two_sided_exact_p": p_value,
    }


def evidence_control_verdict(row: dict[str, str]) -> str:
    """A stronger baseline that omits only capability and policy coordinates."""

    changed = dict(row)
    changed["c2_relation"] = "aligned"
    changed["c5_relation"] = "not_applicable"
    changed["utility_required"] = "no"
    changed["utility_reported"] = "no"
    semantic = five_coordinate(changed)
    return full(changed, semantic)


def model_predictions(
    audit_by_id: dict[str, dict[str, str]],
    sample_by_id: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    predictions = {rule: {} for rule in MODEL_RULES}
    for annotation_id, sample in sample_by_id.items():
        row = audit_by_id[sample["candidate_id"]]
        predictions["three_field_model"][annotation_id] = row["verdict_fim"]
        predictions["evidence_control_baseline"][
            annotation_id
        ] = evidence_control_verdict(row)
        predictions["five_coordinate_model"][annotation_id] = row[
            "verdict_5coord_no_controls"
        ]
        predictions["full_schema_model"][annotation_id] = row["verdict_full"]
    return predictions


def human_coordinate_fim(
    adjudicated_by_id: dict[str, dict[str, str]],
) -> dict[str, str]:
    predictions = {}
    for annotation_id, row in adjudicated_by_id.items():
        predictions[annotation_id] = fim(
            {
                "unit_status": "include",
                "c1_relation": row["final_c1_relation"],
                "c3_relation": row["final_c3_relation"],
                "c4_relation": row["final_c4_relation"],
            }
        )
    return predictions


def metric_row(
    rule: str,
    field_source: str,
    metrics: dict[str, object],
) -> dict[str, object]:
    per_class = metrics["per_class"]
    return {
        "rule": rule,
        "rule_label": RULE_LABELS[rule],
        "field_source": field_source,
        "n": metrics["n"],
        "exact_accuracy": metrics["exact_accuracy"],
        "cohen_kappa": metrics["cohen_kappa"],
        "macro_f1": metrics["macro_f1"],
        "valid_precision": per_class["valid"]["precision"],
        "valid_recall": per_class["valid"]["recall"],
        "partial_precision": per_class["partial"]["precision"],
        "partial_recall": per_class["partial"]["recall"],
        "invalid_precision": per_class["invalid"]["precision"],
        "invalid_recall": per_class["invalid"]["recall"],
        "under_specified_precision": per_class["under-specified"]["precision"],
        "under_specified_recall": per_class["under-specified"]["recall"],
        "calibration": "not_estimable_hard_labels_without_probabilities",
    }


def trigger_flags(row: dict[str, str]) -> set[str]:
    triggers = set()
    if row["factual_match"] == "no" or row["counterexample_status"] == "found":
        triggers.add("ordinary_factual_or_counterexample")
    if (
        row["archetype"] == "D_causal_mechanistic"
        and row["manipulation_or_ablation"] != "yes"
    ):
        triggers.add("ordinary_causal_without_isolation")
    if row["archetype"] == "E_field_meta":
        triggers.add("field_meta")
    if row["evidence_state_decisive"] == "1":
        triggers.add("c1_evidence_state")
    if row["origin_decisive"] == "1":
        triggers.add("c2_origin_capability")
    if row["policy_decisive"] == "1":
        triggers.add("c5_policy_utility")
    if row["controls_decisive"] == "1":
        triggers.add("second_stage_controls")
    return triggers


def render_rule_table(metrics_by_rule: dict[str, dict[str, object]]) -> str:
    rows = []
    for rule in MODEL_RULES:
        result = metrics_by_rule[rule]
        rows.append(
            f"{RULE_LABELS[rule]} & "
            f"{result['exact_accuracy']:.3f} & "
            f"{result['cohen_kappa']:.3f} & "
            f"{result['macro_f1']:.3f} \\\\"
        )
    body = "\n".join(rows)
    return rf"""\begin{{table}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{4pt}}
\begin{{tabularx}}{{\columnwidth}}{{Xrrr}}
\toprule
\textbf{{Rule}} & \textbf{{Exact}} & \textbf{{$\kappa$}} & \textbf{{Macro-F1}} \\
\midrule
{body}
\bottomrule
\end{{tabularx}}
\caption{{Rule outputs against adjudicated human verdicts on the
model-stratified 80-claim sample. All rows use the same released model-coded
fields and rule family. The C2/C5 ablation retains factual, causal, field,
C1/C3/C4, and control checks; it is not an independently implemented audit
method. Hard rules emit no probabilities, so calibration is not estimable.}}
\label{{tab:main-rule-reliability}}
\end{{table}}
"""


def render_human_table(
    field_ranges: dict[str, tuple[float, float]],
    full_metrics: dict[str, object],
) -> str:
    invalid = full_metrics["per_class"]["invalid"]
    return rf"""\begin{{table}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{4pt}}
\begin{{tabularx}}{{\columnwidth}}{{Xr}}
\toprule
\textbf{{Human-validation diagnostic}} & \textbf{{Value}} \\
\midrule
Model-stratum coverage (V/P/I/U) & 26/125; 25/134; 25/26; 4/4 \\
Unanimous verdicts & 39/80 \\
Adjudicator changes to available majorities & 9/78 \\
Pairwise verdict $\kappa$ & 0.258--0.525 \\
C1 / C3 / control-status $\kappa$ &
{field_ranges['c1_relation'][0]:.3f}--{field_ranges['c1_relation'][1]:.3f} /
{field_ranges['c3_relation'][0]:.3f}--{field_ranges['c3_relation'][1]:.3f} /
{field_ranges['controls_status'][0]:.3f}--{field_ranges['controls_status'][1]:.3f} \\
Full-rule exact / $\kappa$ / macro-F1 &
{full_metrics['exact_accuracy']:.3f} / {full_metrics['cohen_kappa']:.3f} /
{full_metrics['macro_f1']:.3f} \\
Model \emph{{invalid}} precision &
{invalid['true_positive']}/{invalid['predicted_n']} =
{invalid['precision']:.3f} \\
\bottomrule
\end{{tabularx}}
\caption{{Reliability diagnostics for the 80-claim human sample. V/P/I/U
denote the model-valid, partial, invalid, and under-specified strata; unequal
coverage and development overlap make these descriptive sample results, not
held-out population performance.}}
\label{{tab:main-human-validation}}
\end{{table}}
"""


def render_archetype_table(
    rows: list[dict[str, object]],
) -> str:
    by_archetype = {
        (row["human_adjudicated_archetype"], row["rule"]): row for row in rows
    }
    labels = (
        ("A_self_baseline", "Self-baseline"),
        ("B_shared_harness", "Shared harness"),
        ("C_cross_source_synthesis", "Cross-source"),
        ("D_causal_mechanistic", "Causal/mechanistic"),
        ("E_field_meta", "Field-level"),
        ("F_policy_utility", "Policy/utility"),
    )
    body = []
    for archetype, label in labels:
        full_row = by_archetype[(archetype, "full_schema_model")]
        body.append(
            f"{label} & {full_row['n']} & "
            f"{by_archetype[(archetype, 'three_field_model')]['exact_accuracy']:.3f} & "
            f"{by_archetype[(archetype, 'evidence_control_baseline')]['exact_accuracy']:.3f} & "
            f"{by_archetype[(archetype, 'five_coordinate_model')]['exact_accuracy']:.3f} & "
            f"{full_row['exact_accuracy']:.3f} \\\\"
        )
    return rf"""\begin{{table*}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{6pt}}
\begin{{tabular}}{{lrrrrr}}
\toprule
\textbf{{Human-adjudicated archetype}} & \textbf{{$n$}} &
\textbf{{Three-field}} & \textbf{{Evidence+ctrl.}} &
\textbf{{Five-coordinate}} & \textbf{{Full}} \\
\midrule
{chr(10).join(body)}
\bottomrule
\end{{tabular}}
\caption{{Exact agreement with adjudicated human verdicts by audit-unit
archetype. The sample sizes are small and model-stratified, so these values are
descriptive diagnostics rather than comparative performance estimates.}}
\label{{tab:rule-reliability-by-archetype}}
\end{{table*}}
"""


def render_field_table(rows: list[dict[str, object]]) -> str:
    labels = {
        "archetype": "Claim archetype",
        "c1_relation": "C1 evidence state",
        "c2_relation": "C2 origin/capability",
        "c3_relation": "C3 intervention",
        "c4_relation": "C4 outcome/unit",
        "c5_relation": "C5 policy/utility",
        "controls_status": "Control status",
        "verdict": "Final verdict",
    }
    body = []
    for row in rows:
        body.append(
            f"{labels[row['field']]} & "
            f"{row['raw_agreement_min']:.3f}--{row['raw_agreement_max']:.3f} & "
            f"{row['cohen_kappa_min']:.3f}--{row['cohen_kappa_max']:.3f} & "
            f"{row['gwet_ac1_min']:.3f}--{row['gwet_ac1_max']:.3f} \\\\"
        )
    return rf"""\begin{{table*}}[t]
\centering
\small
\setlength{{\tabcolsep}}{{6pt}}
\begin{{tabular}}{{lrrr}}
\toprule
\textbf{{Field}} & \textbf{{Raw agreement}} &
\textbf{{Cohen's $\kappa$}} & \textbf{{Gwet's AC1}} \\
\midrule
{chr(10).join(body)}
\bottomrule
\end{{tabular}}
\caption{{Ranges over the three human-coder pairs on all 80 claims. Low C1,
C3, and control-status agreement localizes the main operational ambiguity.}}
\label{{tab:human-field-agreement}}
\end{{table*}}
"""


def main() -> None:
    audit_rows = read_csv(AUDIT)
    audit_by_id = {row["candidate_id"]: row for row in audit_rows}
    sample_rows = read_csv(SAMPLE_KEY)
    sample_by_id = {row["annotation_id"]: row for row in sample_rows}
    adjudicated_rows = read_csv(ADJUDICATED)
    adjudicated_by_id = {row["annotation_id"]: row for row in adjudicated_rows}

    if len(audit_rows) != 291 or len(sample_rows) != 80 or len(adjudicated_rows) != 80:
        raise ValueError("unexpected audit or human-validation row count")
    if set(sample_by_id) != set(adjudicated_by_id):
        raise ValueError("sample key and adjudication IDs differ")
    for sample in sample_rows:
        row = audit_by_id[sample["candidate_id"]]
        if row["verdict_full"] != sample["model_adjudicated_verdict"]:
            raise ValueError(f"stale sample key for {sample['candidate_id']}")

    gold = {
        annotation_id: row["final_verdict"]
        for annotation_id, row in adjudicated_by_id.items()
    }
    predictions = model_predictions(audit_by_id, sample_by_id)
    predictions["three_field_human_coordinates"] = human_coordinate_fim(
        adjudicated_by_id
    )
    metrics_by_rule = {
        rule: agreement_metrics(prediction, gold)
        for rule, prediction in predictions.items()
    }

    rule_rows = [
        metric_row(
            rule,
            (
                "adjudicated_human_c1_c3_c4"
                if rule == "three_field_human_coordinates"
                else "source_linked_model_coding"
            ),
            metrics_by_rule[rule],
        )
        for rule in (*MODEL_RULES, "three_field_human_coordinates")
    ]
    write_csv(RULE_OUTPUT, rule_rows)

    archetype_rows = []
    for rule in MODEL_RULES:
        for archetype in sorted(
            {row["final_archetype"] for row in adjudicated_rows}
        ):
            ids = {
                annotation_id
                for annotation_id, row in adjudicated_by_id.items()
                if row["final_archetype"] == archetype
            }
            subset_gold = {item: gold[item] for item in ids}
            subset_prediction = {item: predictions[rule][item] for item in ids}
            result = agreement_metrics(subset_prediction, subset_gold)
            archetype_rows.append(
                {
                    "rule": rule,
                    "human_adjudicated_archetype": archetype,
                    "n": result["n"],
                    "exact_accuracy": result["exact_accuracy"],
                    "cohen_kappa": result["cohen_kappa"],
                    "macro_f1_four_class": result["macro_f1"],
                    "interpretation": "descriptive_small_stratum",
                }
            )
    write_csv(ARCHETYPE_OUTPUT, archetype_rows)

    included = [row for row in audit_rows if row["unit_status"] == "include"]
    population = Counter(row["verdict_full"] for row in included)
    sampled = Counter(row["model_adjudicated_verdict"] for row in sample_rows)
    sampling_rows = []
    for label in VERDICTS:
        sampling_rows.append(
            {
                "model_stratum": label,
                "model_inventory_n": population[label],
                "human_sample_n": sampled[label],
                "sampling_fraction": sampled[label] / population[label],
                "selection_status": (
                    "deterministic_balanced_core_16_plus_unrecoverable_64_selection"
                ),
                "paper_disjoint_from_codebook_development": "false",
                "population_inference": "not_supported",
            }
        )
    write_csv(SAMPLING_OUTPUT, sampling_rows)

    pairwise_rows = [
        row
        for row in read_csv(PAIRWISE)
        if row["subset"] == "all_80"
        and row["field"]
        in {
            "archetype",
            "c1_relation",
            "c2_relation",
            "c3_relation",
            "c4_relation",
            "c5_relation",
            "controls_status",
            "verdict",
        }
    ]
    by_field: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in pairwise_rows:
        by_field[row["field"]].append(row)
    field_rows = []
    field_ranges = {}
    for field in sorted(by_field):
        rows = by_field[field]
        kappas = [float(row["cohen_kappa"]) for row in rows]
        raw = [float(row["raw_agreement"]) for row in rows]
        ac1 = [float(row["gwet_ac1"]) for row in rows]
        field_ranges[field] = (min(kappas), max(kappas))
        field_rows.append(
            {
                "field": field,
                "pairwise_comparisons": len(rows),
                "raw_agreement_min": min(raw),
                "raw_agreement_max": max(raw),
                "cohen_kappa_min": min(kappas),
                "cohen_kappa_max": max(kappas),
                "gwet_ac1_min": min(ac1),
                "gwet_ac1_max": max(ac1),
            }
        )
    write_csv(FIELD_OUTPUT, field_rows)

    majority_rows = read_csv(MAJORITY)
    majority_by_id = {row["annotation_id"]: row for row in majority_rows}
    majority_available = sum(
        bool(row["verdict_majority"]) for row in majority_rows
    )
    majority_overrides = sum(
        bool(row["verdict_majority"])
        and adjudicated_by_id[annotation_id]["final_verdict"]
        != row["verdict_majority"]
        for annotation_id, row in majority_by_id.items()
    )
    unanimous = sum(row["verdict_unanimous"] == "1" for row in majority_rows)

    inventory_error_rows = []
    for trigger in (
        "ordinary_factual_or_counterexample",
        "ordinary_causal_without_isolation",
        "field_meta",
        "c1_evidence_state",
        "c2_origin_capability",
        "c5_policy_utility",
        "second_stage_controls",
    ):
        inventory_error_rows.append(
            {
                "scope": "unvalidated_model_inventory_289",
                "error_or_trigger": trigger,
                "n": sum(trigger in trigger_flags(row) for row in included),
                "exact_human_agreement": "",
                "interpretation": "rule_trigger_count_not_validated_prevalence",
            }
        )

    ordinary = {
        "ordinary_factual_or_counterexample",
        "ordinary_causal_without_isolation",
        "field_meta",
    }
    comparability_remainder = [
        row for row in included if not (trigger_flags(row) & ordinary)
    ]
    inventory_error_rows.append(
        {
            "scope": "unvalidated_model_inventory_289",
            "error_or_trigger": "remainder_after_ordinary_audit_types",
            "n": len(comparability_remainder),
            "exact_human_agreement": "",
            "interpretation": "excludes_factual_causal_and_field_meta_types",
        }
    )
    inventory_error_rows.append(
        {
            "scope": "unvalidated_model_inventory_289",
            "error_or_trigger": "any_c1_c2_c5_decisive_in_remainder",
            "n": sum(
                bool(
                    trigger_flags(row)
                    & {"c1_evidence_state", "c2_origin_capability", "c5_policy_utility"}
                )
                for row in comparability_remainder
            ),
            "exact_human_agreement": "",
            "interpretation": "model_rule_transition_not_confirmed_human_error",
        }
    )

    for trigger in (
        "ordinary_factual_or_counterexample",
        "ordinary_causal_without_isolation",
        "field_meta",
        "c1_evidence_state",
        "c2_origin_capability",
        "c5_policy_utility",
        "second_stage_controls",
    ):
        ids = [
            annotation_id
            for annotation_id, sample in sample_by_id.items()
            if trigger in trigger_flags(audit_by_id[sample["candidate_id"]])
        ]
        if not ids:
            continue
        exact = sum(
            predictions["full_schema_model"][item] == gold[item] for item in ids
        ) / len(ids)
        inventory_error_rows.append(
            {
                "scope": "human_sample_80",
                "error_or_trigger": trigger,
                "n": len(ids),
                "exact_human_agreement": exact,
                "interpretation": "descriptive_model_trigger_subset",
            }
        )
    write_csv(ERROR_OUTPUT, inventory_error_rows)

    paired_tests = {
        "three_field_vs_five_coordinate": exact_mcnemar(
            predictions["three_field_model"],
            predictions["five_coordinate_model"],
            gold,
        ),
        "evidence_control_baseline_vs_full_schema": exact_mcnemar(
            predictions["evidence_control_baseline"],
            predictions["full_schema_model"],
            gold,
        ),
        "five_coordinate_vs_full_schema": exact_mcnemar(
            predictions["five_coordinate_model"],
            predictions["full_schema_model"],
            gold,
        ),
    }
    summary = {
        "status": "negative_reliability_study",
        "primary_evidence": "adjudicated_human_labels_on_model_stratified_80_claim_sample",
        "sampling": {
            "n": len(sample_rows),
            "balanced_core_n": sum(
                row["balanced_core_16"] == "1" for row in sample_rows
            ),
            "remaining_64_selection_algorithm": "not_retained",
            "paper_disjoint_from_codebook_development": False,
            "population_inference": "not_supported",
        },
        "human_adjudication": {
            "unanimous_verdicts": unanimous,
            "majority_available": majority_available,
            "no_majority": len(majority_rows) - majority_available,
            "adjudicator_changes_to_available_majority": majority_overrides,
        },
        "rule_metrics": metrics_by_rule,
        "paired_exact_tests": paired_tests,
        "calibration": {
            "status": "not_estimable",
            "reason": "deterministic rules emit hard labels without probabilities or confidence scores",
        },
        "model_inventory_boundary": {
            "n_included": len(included),
            "verdict_distribution": dict(population),
            "status": "unvalidated_model_generated_index_not_headline_evidence",
            "ordinary_audit_types_excluded_n": len(included)
            - len(comparability_remainder),
            "comparability_remainder_n": len(comparability_remainder),
            "c1_c2_c5_decisive_in_remainder": sum(
                bool(
                    trigger_flags(row)
                    & {"c1_evidence_state", "c2_origin_capability", "c5_policy_utility"}
                )
                for row in comparability_remainder
            ),
        },
    }
    SUMMARY_OUTPUT.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    RULE_TABLE.write_text(render_rule_table(metrics_by_rule), encoding="utf-8")
    HUMAN_TABLE.write_text(
        render_human_table(field_ranges, metrics_by_rule["full_schema_model"]),
        encoding="utf-8",
    )
    ARCHETYPE_TABLE.write_text(
        render_archetype_table(archetype_rows), encoding="utf-8"
    )
    FIELD_TABLE.write_text(render_field_table(field_rows), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
