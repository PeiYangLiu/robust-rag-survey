#!/usr/bin/env python3
"""Merge both frozen claim slices and summarize coordinate contributions."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from derive_observed_claim_verdicts import fim, five_coordinate, full


MANUSCRIPT = Path(__file__).resolve().parents[1]
ROOT = MANUSCRIPT / "supplement"
COMPONENTS = ROOT / "claim_audit_components"
SLICES = {
    "general": (
        COMPONENTS / "general_candidates.csv",
        COMPONENTS / "general_adjudicated_structured.csv",
    ),
    "action_policy": (
        COMPONENTS / "action_candidates.csv",
        COMPONENTS / "action_adjudicated_structured.csv",
    ),
    "threat_model": (
        COMPONENTS / "threat_candidates.csv",
        COMPONENTS / "threat_adjudicated_structured.csv",
    ),
}
OUTPUT = ROOT / "observed_comparison_claim_audit.csv"
SUMMARY = ROOT / "observed_comparison_claim_audit_summary.json"
BALANCED = ROOT / "observed_comparison_claim_balanced_packet.csv"
BALANCED_KEY = ROOT / "observed_comparison_claim_balanced_key.csv"
HUMAN_ROOT = (
    MANUSCRIPT
    / "human_coding"
    / "observed_claim_human_validation_20260714"
    / "annotated_20260714"
)
HUMAN_SUMMARY = HUMAN_ROOT / "analysis_results" / "final" / "human_validation_summary.json"
SEED = 20260714
SEVERITY = {"valid": 0, "partial": 1, "under-specified": 2, "invalid": 3}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            value.update(block)
    return value.hexdigest()


def counterfactual(
    row: dict[str, str],
    *,
    remove_c1: bool = False,
    remove_c2: bool = False,
    remove_c5: bool = False,
) -> str:
    changed = dict(row)
    if remove_c1:
        changed["c1_relation"] = "aligned"
    if remove_c2:
        changed["c2_relation"] = "aligned"
    if remove_c5:
        changed["c5_relation"] = "not_applicable"
        changed["utility_required"] = "no"
        changed["utility_reported"] = "no"
    return five_coordinate(changed)


def main() -> None:
    combined: list[dict[str, str]] = []
    input_hashes = {}
    for slice_name, (candidate_path, coded_path) in SLICES.items():
        candidates = {row["candidate_id"]: row for row in read_rows(candidate_path)}
        coded = read_rows(coded_path)
        input_hashes[f"{slice_name}_candidates"] = sha256(candidate_path)
        input_hashes[f"{slice_name}_adjudicated"] = sha256(coded_path)
        for row in coded:
            row["verdict_fim"] = fim(row)
            row["verdict_5coord_no_controls"] = five_coordinate(row)
            row["verdict_full"] = full(row, row["verdict_5coord_no_controls"])
            candidate = candidates[row["candidate_id"]]
            merged = {**candidate, **row}
            merged["audit_slice"] = slice_name
            merged["verdict_without_c1"] = counterfactual(row, remove_c1=True)
            merged["verdict_without_c2"] = counterfactual(row, remove_c2=True)
            merged["verdict_without_c5"] = counterfactual(row, remove_c5=True)
            merged["evidence_state_decisive"] = int(
                merged["verdict_without_c1"] != row["verdict_5coord_no_controls"]
            )
            merged["origin_decisive"] = int(
                merged["verdict_without_c2"] != row["verdict_5coord_no_controls"]
            )
            merged["policy_decisive"] = int(
                merged["verdict_without_c5"] != row["verdict_5coord_no_controls"]
            )
            merged["controls_decisive"] = int(
                row["verdict_5coord_no_controls"] != row["verdict_full"]
            )
            combined.append(merged)

    combined.sort(key=lambda row: (row["audit_slice"], row["source_key"], int(row["extraction_order"])))
    fields = list(combined[0])
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(combined)

    included = [row for row in combined if row["unit_status"] == "include"]
    summary: dict[str, object] = {
        "version": "2026-07-14",
        "candidate_pool_frozen_before_adjudication": True,
        "adjudication_status": "source_verified_model_adjudication_not_human",
        "not_external_gold": True,
        "n_candidates": len(combined),
        "n_included_comparative_claims": len(included),
        "n_excluded_not_comparative": len(combined) - len(included),
        "n_sources": len({row["source_key"] for row in combined}),
        "input_sha256": input_hashes,
        "output_sha256": "",
        "distributions": {
            "full_verdict_included": dict(Counter(row["verdict_full"] for row in included)),
            "fim_verdict_included": dict(Counter(row["verdict_fim"] for row in included)),
            "five_coordinate_verdict_included": dict(
                Counter(row["verdict_5coord_no_controls"] for row in included)
            ),
            "archetype_included": dict(Counter(row["archetype"] for row in included)),
            "claim_strength_included": dict(
                Counter(row["claim_strength"] for row in included)
            ),
            "source": dict(Counter(row["source_key"] for row in included)),
            "slice": dict(Counter(row["audit_slice"] for row in included)),
        },
        "coordinate_coverage": {
            "c1_non_unknown": sum(row["c1_relation"] != "unknown" for row in included),
            "c2_non_unknown": sum(row["c2_relation"] != "unknown" for row in included),
            "c3_non_unknown": sum(row["c3_relation"] != "unknown" for row in included),
            "c4_non_unknown": sum(row["c4_relation"] != "unknown" for row in included),
            "c5_non_unknown_or_na": sum(
                row["c5_relation"] in {"aligned", "different", "mixed", "not_applicable"}
                for row in included
            ),
            "c5_action_applicable": sum(
                row["c5_relation"] != "not_applicable" for row in included
            ),
            "utility_required": sum(row["utility_required"] == "yes" for row in included),
        },
        "decisive_counts": {
            "evidence_state": sum(
                int(row["evidence_state_decisive"]) for row in included
            ),
            "origin_capability": sum(int(row["origin_decisive"]) for row in included),
            "policy_utility": sum(int(row["policy_decisive"]) for row in included),
            "second_stage_controls": sum(int(row["controls_decisive"]) for row in included),
            "intervention_difference_permitted": sum(
                row["verdict_fim"] == "partial"
                and row["verdict_5coord_no_controls"] == "valid"
                for row in included
            ),
            "origin_or_policy": sum(
                int(row["origin_decisive"]) or int(row["policy_decisive"])
                for row in included
            ),
        },
        "transitions": {
            "fim_to_five": dict(
                Counter(
                    f"{row['verdict_fim']}->{row['verdict_5coord_no_controls']}"
                    for row in included
                )
            ),
            "five_to_full": dict(
                Counter(
                    f"{row['verdict_5coord_no_controls']}->{row['verdict_full']}"
                    for row in included
                )
            ),
        },
        "by_slice": {},
        "by_source_full_verdict": {},
    }

    for slice_name in SLICES:
        rows = [row for row in included if row["audit_slice"] == slice_name]
        summary["by_slice"][slice_name] = {
            "n": len(rows),
            "full_verdict": dict(Counter(row["verdict_full"] for row in rows)),
            "c5_action_applicable": sum(
                row["c5_relation"] != "not_applicable" for row in rows
            ),
            "origin_decisive": sum(int(row["origin_decisive"]) for row in rows),
            "policy_decisive": sum(int(row["policy_decisive"]) for row in rows),
            "controls_decisive": sum(int(row["controls_decisive"]) for row in rows),
            "evidence_state_decisive": sum(
                int(row["evidence_state_decisive"]) for row in rows
            ),
        }
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in included:
        by_source[row["source_key"]][row["verdict_full"]] += 1
    summary["by_source_full_verdict"] = {
        source: dict(counts) for source, counts in by_source.items()
    }

    # Deterministic class-balanced packet for independent future validation.
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in included:
        groups[row["verdict_full"]].append(row)
    per_class = min(20, *(len(groups[label]) for label in sorted(groups)))
    rng = random.Random(SEED)
    balanced_rows = []
    for verdict in ["valid", "partial", "invalid", "under-specified"]:
        rows = list(groups[verdict])
        rng.shuffle(rows)
        balanced_rows.extend(rows[:per_class])
    rng.shuffle(balanced_rows)

    packet_fields = [
        "balanced_id",
        "exact_quote",
        "context_before",
        "context_after",
        "comparison_subjects",
        "source_title",
        "source_section",
        "pdf_page",
        "printed_page",
        "source_url",
    ]
    key_fields = ["balanced_id", "candidate_id", "verdict_full", "source_key", "audit_slice"]
    for index, row in enumerate(balanced_rows, 1):
        row["balanced_id"] = f"V{index:03d}"
    with BALANCED.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=packet_fields)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in packet_fields}
            for row in balanced_rows
        )
    with BALANCED_KEY.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=key_fields)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in key_fields}
            for row in balanced_rows
        )
    summary["balanced_packet"] = {
        "seed": SEED,
        "per_class": per_class,
        "n": len(balanced_rows),
        "status": (
            "completed_as_16_claim_core_within_80_claim_human_validation"
            if HUMAN_SUMMARY.is_file()
            else "prepared_for_independent_human_validation_not_completed"
        ),
        "packet_sha256": sha256(BALANCED),
        "key_sha256": sha256(BALANCED_KEY),
    }
    if HUMAN_SUMMARY.is_file():
        human = json.loads(HUMAN_SUMMARY.read_text(encoding="utf-8"))
        summary["human_validation"] = {
            "status": "completed_negative_reliability_study",
            "n": human["n_claims"],
            "balanced_core_n": human["balanced_core_n"],
            "adjudicated_distribution": human["adjudicated_distribution"],
            "exact_agreement": human["human_vs_model_secondary"]["exact_agreement"],
            "cohen_kappa": human["human_vs_model_secondary"]["cohen_kappa"],
            "macro_f1": human["human_vs_model_secondary"]["macro_f1"],
            "population_inference": "not_supported_model_stratified_sample",
        }
    summary["headline_use"] = (
        "prohibited_unvalidated_model_verdict_distribution_and_rule_transitions"
    )
    summary["output_sha256"] = sha256(OUTPUT)
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
