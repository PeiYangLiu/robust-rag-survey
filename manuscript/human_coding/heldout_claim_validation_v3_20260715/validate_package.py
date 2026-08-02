#!/usr/bin/env python3
"""Validate the prepared, frozen, or collected held-out v3 package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from build_assignments import (
    ARMS,
    ASSIGNMENT_HEADER,
    DEFAULT_EXPECTED_CLAIMS,
    DEFAULT_EXPECTED_SOURCES,
    DEFAULT_MAX_PER_SOURCE,
    DEFAULT_SEED,
    Claim,
    build_assignments as construct_assignments,
    read_primary_auditor_ids,
    stable_digest,
    validate_assignment_rows,
    validate_claim_design,
)
from apply_source_replacements import (
    PROHIBITED_USE as SOURCE_REPLACEMENT_PROHIBITED_USE,
    SUMMARY_SCHEMA_VERSION as SOURCE_REPLACEMENT_SCHEMA_VERSION,
    SUMMARY_STATUS as SOURCE_REPLACEMENT_STATUS,
    extract_replacement_candidates,
    subset_sha256 as replacement_subset_sha256,
    verify_replacement_chain,
)
from build_development_source_keys import (
    DEVELOPMENT_SOURCES_HEADER,
    FIXED_V2_KEYS,
    V1_SCOPE,
    V2_SCOPE,
    build_key_set,
    build_source_rows,
    normalize_title,
    read_pair_sources,
    read_v2_sources,
    serialize_keys,
    serialize_sources,
)
from build_sampling_screen_packets import (
    HUMAN_FIELDS as SAMPLING_HUMAN_FIELDS,
    MODEL_FIELDS as SAMPLING_MODEL_FIELDS,
    MODEL_FREE_SCREENING_STATUS,
    PROHIBITED_USE as SAMPLING_SCREEN_PROHIBITED_USE,
    SCREEN_RESPONSE_HEADER,
    SUMMARY_SCHEMA_VERSION as SAMPLING_SCREEN_SCHEMA_VERSION,
)
from prepare_candidate_pool import (
    CANDIDATE_HEADER as DETERMINISTIC_CANDIDATE_HEADER,
    MODEL_FREE_STATUS,
    MODEL_PRESCREEN_HEADER,
    SOURCE_HEADER as PREPARED_SOURCE_HEADER,
    canonical_candidate_hash,
    expanded_text_snapshot,
    publication_status as map_publication_status,
)
from freeze_human_sample import (
    FROZEN_HEADER as FREEZER_FROZEN_HEADER,
    LEDGER_HEADER,
    REPLACEMENT_HEADER,
    canonical_json_sha256,
    sanitize_human_sampling_row,
    sampling_record_sha256,
    validate_human_screen_row,
)
from frozen_text_corrections import (
    AUTHORITATIVE_CLAIM_ID as TEXT_CORRECTION_CLAIM_ID,
    AUTHORITATIVE_NEW_TEXT as TEXT_CORRECTION_NEW_TEXT,
    AUTHORITATIVE_SOURCE_KEY as TEXT_CORRECTION_SOURCE_KEY,
    AUTHORITATIVE_SOURCE_URL as TEXT_CORRECTION_SOURCE_URL,
    CORRECTION_HEADER as FROZEN_TEXT_CORRECTION_HEADER,
    SCHEMA_VERSION as FROZEN_TEXT_CORRECTION_SCHEMA_VERSION,
    ReversedCorrectionState,
    c0_codepoints,
    serialize_csv as serialize_text_correction_csv,
    validate_and_reverse_corrections,
)
from build_calibration_packets import (
    ANSWER_KEY_HEADER as CALIBRATION_ANSWER_KEY_HEADER,
    ANSWER_KEY_STATUS as CALIBRATION_ANSWER_KEY_STATUS,
    CALIBRATION_ITEM_COUNT,
    CALIBRATION_VERSION,
    CONSTRUCTION_STATUS as CALIBRATION_CONSTRUCTION_STATUS,
    ITEM_HEADER as CALIBRATION_ITEM_HEADER,
    PUBLIC_ROSTER_HEADER as CALIBRATION_PUBLIC_ROSTER_HEADER,
    assert_test_disjoint as assert_calibration_test_disjoint,
    calibration_set_sha256,
    instructions_for as calibration_instructions_for,
    read_calibration_items,
    read_calibration_key,
    render_calibration_materials,
)
from score_calibration import (
    CALIBRATION_RESPONSE_HEADER,
    MAXIMUM_RETRAINING_ATTEMPTS,
    MINIMUM_CORRECT_PER_DIMENSION,
    build_summary as build_calibration_summary,
    csv_bytes,
    validate_calibration_state,
)
from build_review_packets import (
    ADJUDICATOR_PACKET_VERSION,
    ADJUDICATOR_REGISTRY_SCHEMA_VERSION,
    adjudication_id as deterministic_adjudication_id,
    build_adjudicator_packets,
    build_adjudicator_registry,
    public_role_roster_sha256,
)
from staged_review_core import (
    ARM_EXTRACTION_FIELDS as STAGED_ARM_EXTRACTION_FIELDS,
    AUDITOR_IMMUTABLE_FIELDS as STAGED_AUDITOR_IMMUTABLE_FIELDS,
    CORRECTION_HEADER as STAGED_CORRECTION_HEADER,
    CORRECTION_SCHEMA_VERSION as STAGED_CORRECTION_SCHEMA_VERSION,
    EXTRACTION_HASH_SCHEMA_VERSION as STAGED_EXTRACTION_HASH_SCHEMA_VERSION,
    GOLD_EXTRACTION_FIELDS as STAGED_GOLD_EXTRACTION_FIELDS,
    GOLD_IMMUTABLE_FIELDS as STAGED_GOLD_IMMUTABLE_FIELDS,
    INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY,
    INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION,
    ISSUANCE_REGISTRY_SCHEMA_VERSION as STAGED_ISSUANCE_REGISTRY_SCHEMA_VERSION,
    ISSUANCE_ROW_HEADER as STAGED_ISSUANCE_ROW_HEADER,
    PACKET_REGISTRY_SCHEMA_VERSION as STAGED_PACKET_REGISTRY_SCHEMA_VERSION,
    RECEIPT_HEADER as STAGED_RECEIPT_HEADER,
    RECEIPT_SCHEMA_VERSION as STAGED_RECEIPT_SCHEMA_VERSION,
    WORKFLOW_VERSION as STAGED_WORKFLOW_VERSION,
    correction_record_sha256,
    extraction_snapshot_sha256,
    parse_utc as parse_staged_utc,
    validate_composition_row as validate_staged_composition_row,
)
from collect_final_responses import (
    empty_issuance_registry,
    expected_zero_response_receipt,
    validate_collection_artifacts,
    validate_frozen_coordinator_state,
)


STATUS = "PRE-REGISTERED / NO TEST LABELS COLLECTED"
MODEL_ONLY_STATUS = "SYNTHETIC_OR_MODEL_ONLY_PRESCREEN_NOT_HUMAN_LABEL"
PRE_TEXT_CORRECTION_COORDINATOR_REGISTRY_SHA256 = (
    "fb65fcc8ee97bfb364b64c0e01c8b3150cbcdb8d926e38a8c84f7396877503a6"
)
EXPECTED_FIXED_V2_KEYS = frozenset(
    {
        "securityRAGSurvey2026",
        "alushi2026comparison",
        "joren2025sufficient",
        "ragComprehensive2025",
        "trustRAGCompass2024",
        "wen2025abstention",
        "liu2025donotabstain",
        "trustworthyRAGSurvey2025",
        "zhu2026trustabstain",
    }
)
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
TEST_RESPONSE_FILES = (
    "arm_A_responses.csv",
    "arm_B_responses.csv",
    "arm_C_responses.csv",
    "arm_D_responses.csv",
    "gold_responses.csv",
    "adjudicator_1_responses.csv",
    "adjudicator_2_responses.csv",
)
ARM_RESPONSE_FILES = {
    "A": "arm_A_responses.csv",
    "B": "arm_B_responses.csv",
    "C": "arm_C_responses.csv",
    "D": "arm_D_responses.csv",
}
REQUIRED_FILES = {
    ".gitignore",
    "README.md",
    "preregistered_protocol.md",
    "codebook_v3_frozen.md",
    "study_config.json",
    "staged_review_schema.json",
    "power_analysis.py",
    "power_analysis.json",
    "build_development_source_keys.py",
    "prepare_candidate_pool.py",
    "apply_source_replacements.py",
    "build_sampling_screen_packets.py",
    "freeze_human_sample.py",
    "frozen_text_corrections.py",
    "build_review_packets.py",
    "build_staged_review_packets.py",
    "staged_review_core.py",
    "issue_composition_packets.py",
    "collect_final_responses.py",
    "build_calibration_packets.py",
    "score_calibration.py",
    "analyze_collected_results.py",
    "build_assignments.py",
    "validate_package.py",
    "DEVELOPMENT_SOURCE_KEYS.txt",
    "DEVELOPMENT_SOURCES.csv",
    "source_sampling_frame.csv",
    "candidate_claims_deterministic.csv",
    "candidate_claims_model_prescreen.csv",
    "candidate_pool_summary.json",
    "sampling_screen_response_template.csv",
    "sampling_screen_summary_schema.json",
    "sampling_screen_summary.json",
    "source_replacement_summary_schema.json",
    "source_replacement_summary.json",
    "sampling_exclusion_replacement_ledger.csv",
    "source_replacement_exclusions.csv",
    "sampling_freeze_summary_schema.json",
    "analysis_output_schema.json",
    "frozen_test_claims.csv",
    "frozen_text_corrections.csv",
    "auditor_assignments.csv",
    "arm_A_responses.csv",
    "arm_B_responses.csv",
    "arm_C_responses.csv",
    "arm_D_responses.csv",
    "gold_responses.csv",
    "adjudicator_1_responses.csv",
    "adjudicator_2_responses.csv",
    "calibration_responses.csv",
    "calibration_items.csv",
    "calibration_answer_key.csv",
    "calibration_materials.md",
    "calibration_summary.json",
    "coordinator_packet_registry.json",
    "composition_packet_issuance_registry.json",
    "composition_issuance_rows.csv",
    "review_extraction_corrections.csv",
    "coordinator_response_receipts.csv",
    "coordinator_collection_receipt.json",
    "adjudicator_packet_registry.json",
    "participant_metadata_private_template.csv",
    "participant_metadata_public_template.csv",
    "MANIFEST.sha256",
}
PACKAGE_FILE_ALLOWLIST = frozenset(
    REQUIRED_FILES
    | {
        "README_REVIEWER_PACKAGE.md",
        "build_offline_analysis_release.py",
        "poststudy_analysis_addendum.md",
        "sampling_freeze_summary.json",
        "sampling_screener_provenance.json",
    }
)


def columns(text: str) -> tuple[str, ...]:
    return tuple(text.split(","))


SOURCE_HEADER = columns(
    "source_key,title,year,venue_family,publication_status,stable_url_or_doi,"
    "corpus_snapshot_id,full_text_sha256,license_or_access_note,sampling_stratum,"
    "eligible_candidate_count,eligibility_status,exclusion_reason_code,"
    "exclusion_reason_detail,development_source_flag,deterministic_source_rank,"
    "frame_frozen_utc"
)
CANDIDATE_HEADER = columns(
    "candidate_claim_id,source_key,claim_text,context_before,context_after,"
    "source_section,source_locator,source_url_or_doi,source_evidence_excerpt,"
    "source_file_sha256,candidate_extraction_method,prescreen_system,"
    "prescreen_system_version,prescreen_prompt_sha256,prescreen_seed,"
    "prescreen_c2_decisive_probability,prescreen_c5_decisive_probability,"
    "prescreen_rationale,model_only_status,human_sampling_reviewer_1_id,"
    "human_sampling_reviewer_2_id,human_sampling_tiebreak_reviewer_id,"
    "human_sampling_eligibility,human_sampling_stratum,selection_status,"
    "exclusion_reason_code,exclusion_reason_detail,deterministic_claim_rank"
)
FROZEN_CLAIM_HEADER = columns(
    "claim_id,source_key,claim_text,context_before,context_after,source_title,"
    "source_section,source_locator,source_url_or_doi,source_evidence_excerpt,"
    "source_file_sha256,coordinator_only_primary_stratum,sampling_record_sha256,"
    "freeze_version,freeze_utc,label_collection_status"
)
PRIVATE_PARTICIPANT_HEADER = columns(
    "participant_id,role,assigned_arm,legal_name,email,affiliation,"
    "expertise_description,recruitment_channel,consent_record_locator,"
    "consent_date,compensation_record_locator,conflict_of_interest_detail,"
    "replacement_status,notes_private"
)
PUBLIC_PARTICIPANT_HEADER = CALIBRATION_PUBLIC_ROSTER_HEADER
CALIBRATION_HEADER = CALIBRATION_RESPONSE_HEADER
ARM_A_HEADER = columns(
    "assignment_id,claim_id,source_key,participant_id,arm,claim_text,"
    "context_before,context_after,source_title,source_section,source_locator,"
    "source_url_or_doi,source_evidence_excerpt,source_file_sha256,packet_version,"
    "display_order,response_status,missing_reason_code,extraction_started_utc,"
    "extraction_completed_utc,extraction_snapshot_sha256,reported_result_facts,"
    "number_and_direction_check,quantifier_scope_check,causal_basis_check,"
    "compared_items,measured_quantity_and_unit,ordinary_control_notes,"
    "source_location_checked,composition_started_utc,evidence_support_label,"
    "evidence_support_reason,narrower_supported_wording,comparability_label,"
    "comparability_reason,supported_comparison_scope,unresolved_information,"
    "completed_utc"
)
ARM_B_HEADER = columns(
    "assignment_id,claim_id,source_key,participant_id,arm,claim_text,"
    "context_before,context_after,source_title,source_section,source_locator,"
    "source_url_or_doi,source_evidence_excerpt,source_file_sha256,packet_version,"
    "display_order,response_status,missing_reason_code,extraction_started_utc,"
    "extraction_completed_utc,extraction_snapshot_sha256,population_or_setting,"
    "intervention,comparison,outcome,outcome_unit_and_aggregation,"
    "standard_controls_reported,standard_controls_missing,source_location_checked,"
    "composition_started_utc,evidence_support_label,evidence_support_reason,"
    "narrower_supported_wording,comparability_label,comparability_reason,"
    "supported_comparison_scope,unresolved_information,completed_utc"
)
ARM_C_HEADER = columns(
    "assignment_id,claim_id,source_key,participant_id,arm,claim_text,"
    "context_before,context_after,source_title,source_section,source_locator,"
    "source_url_or_doi,source_evidence_excerpt,source_file_sha256,packet_version,"
    "display_order,response_status,missing_reason_code,extraction_started_utc,"
    "extraction_completed_utc,extraction_snapshot_sha256,evidence_condition_side_1,"
    "evidence_condition_side_2,evidence_condition_relation,intervention_side_1,"
    "intervention_side_2,intervention_relation,outcome_side_1,outcome_side_2,"
    "outcome_relation,required_controls,control_findings,source_location_checked,"
    "composition_started_utc,evidence_support_label,evidence_support_reason,"
    "narrower_supported_wording,comparability_label,comparability_reason,"
    "supported_comparison_scope,unresolved_information,completed_utc"
)
ARM_D_HEADER = columns(
    "assignment_id,claim_id,source_key,participant_id,arm,claim_text,"
    "context_before,context_after,source_title,source_section,source_locator,"
    "source_url_or_doi,source_evidence_excerpt,source_file_sha256,packet_version,"
    "display_order,response_status,missing_reason_code,extraction_started_utc,"
    "extraction_completed_utc,extraction_snapshot_sha256,evidence_condition_side_1,"
    "evidence_condition_side_2,evidence_condition_relation,"
    "origin_or_capability_side_1,origin_or_capability_side_2,"
    "origin_or_capability_relation,intervention_side_1,intervention_side_2,"
    "intervention_relation,outcome_side_1,outcome_side_2,outcome_relation,"
    "policy_or_utility_side_1,policy_or_utility_side_2,policy_or_utility_relation,"
    "required_controls,control_findings,source_location_checked,"
    "composition_started_utc,evidence_support_label,evidence_support_reason,"
    "narrower_supported_wording,comparability_label,comparability_reason,"
    "supported_comparison_scope,unresolved_information,completed_utc"
)
GOLD_HEADER = columns(
    "gold_response_id,claim_id,source_key,participant_id,claim_text,context_before,"
    "context_after,source_title,source_section,source_locator,source_url_or_doi,"
    "source_evidence_excerpt,source_file_sha256,packet_version,display_order,"
    "response_status,missing_reason_code,review_started_utc,reported_result_facts,"
    "compared_items,studied_setting,measured_quantity_and_unit,"
    "decision_or_recommendation_context,controls_needed_for_claim,controls_found,"
    "extraction_completed_utc,extraction_snapshot_sha256,composition_started_utc,"
    "evidence_support_label,evidence_support_reason,narrower_supported_wording,"
    "comparability_label,comparability_reason,supported_comparison_scope,"
    "unresolved_information,completed_utc"
)
ADJUDICATOR_HEADER = columns(
    "adjudication_id,claim_id,source_key,participant_id,disputed_outputs,"
    "blinded_gold_response_ids,raw_materials_sha256,response_status,"
    "missing_reason_code,independent_review_started_utc,source_facts_checked,"
    "adjudicated_evidence_support_label,evidence_support_rationale,"
    "adjudicated_comparability_label,comparability_rationale,"
    "supported_comparison_scope,other_adjudicator_response_seen,completed_utc"
)
EXPECTED_HEADERS = {
    "source_sampling_frame.csv": SOURCE_HEADER,
    "candidate_claims_deterministic.csv": DETERMINISTIC_CANDIDATE_HEADER,
    "candidate_claims_model_prescreen.csv": CANDIDATE_HEADER,
    "sampling_screen_response_template.csv": SCREEN_RESPONSE_HEADER,
    "frozen_test_claims.csv": FROZEN_CLAIM_HEADER,
    "frozen_text_corrections.csv": FROZEN_TEXT_CORRECTION_HEADER,
    "sampling_exclusion_replacement_ledger.csv": LEDGER_HEADER,
    "source_replacement_exclusions.csv": REPLACEMENT_HEADER,
    "auditor_assignments.csv": ASSIGNMENT_HEADER,
    "arm_A_responses.csv": ARM_A_HEADER,
    "arm_B_responses.csv": ARM_B_HEADER,
    "arm_C_responses.csv": ARM_C_HEADER,
    "arm_D_responses.csv": ARM_D_HEADER,
    "gold_responses.csv": GOLD_HEADER,
    "adjudicator_1_responses.csv": ADJUDICATOR_HEADER,
    "adjudicator_2_responses.csv": ADJUDICATOR_HEADER,
    "calibration_responses.csv": CALIBRATION_HEADER,
    "composition_issuance_rows.csv": STAGED_ISSUANCE_ROW_HEADER,
    "review_extraction_corrections.csv": STAGED_CORRECTION_HEADER,
    "coordinator_response_receipts.csv": STAGED_RECEIPT_HEADER,
    "calibration_items.csv": CALIBRATION_ITEM_HEADER,
    "calibration_answer_key.csv": CALIBRATION_ANSWER_KEY_HEADER,
    "participant_metadata_private_template.csv": PRIVATE_PARTICIPANT_HEADER,
    "participant_metadata_public_template.csv": PUBLIC_PARTICIPANT_HEADER,
}
RAW_PACKET_FIELDS = {
    "claim_id",
    "source_key",
    "claim_text",
    "context_before",
    "context_after",
    "source_title",
    "source_section",
    "source_locator",
    "source_url_or_doi",
    "source_evidence_excerpt",
    "source_file_sha256",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROVENANCE_RELATIVE_PATH = (
    "manuscript/supplement/validation_pair_provenance.csv"
)
V2_TITLE_RELATIVE_PATH = (
    "manuscript/human_coding/observed_claim_human_validation_20260714/"
    "annotated_20260714/analysis_results/final/human_final_consensus.csv"
)
MAP_RELATIVE_PATH = (
    "manuscript/supplement/evidence_map_venue_expanded_adjudicated.csv"
)
EXPANDED_TEXT_RELATIVE_PATH = "manuscript/citation_audit/expanded_texts/**"
PRIVATE_PARTICIPANT_VERIFICATION_INPUT = (
    "private participant legal-name/contact/consent/compensation locator "
    "verification"
)
STANDALONE_REVIEWER_MARKER = ".standalone-reviewer-package"
PUBLIC_ANONYMOUS_ID_RE = re.compile(r"^(?:AUD|GLD|ADJ)-[0-9A-F]{12}$")
ORIGINAL_PARTICIPANT_ID_SEARCH_RE = re.compile(
    r"\b(?:AUD|GLD|ADJ)-[0-9A-F]{12}\b"
)
REVIEWER_PRIVATE_BASENAMES = {
    "adjudicator_1_responses.csv",
    "adjudicator_2_responses.csv",
    "adjudicator_packet_registry.json",
    "arm_A_responses.csv",
    "arm_B_responses.csv",
    "arm_C_responses.csv",
    "arm_D_responses.csv",
    "auditor_assignments.csv",
    "calibration_responses.csv",
    "calibration_summary.json",
    "composition_issuance_rows.csv",
    "composition_packet_issuance_registry.json",
    "coordinator_collection_receipt.json",
    "coordinator_packet_registry.json",
    "coordinator_response_receipts.csv",
    "gold_responses.csv",
    "participant_metadata_private_template.csv",
    "participant_metadata_public_template.csv",
    "review_extraction_corrections.csv",
}
REVIEWER_REQUIRED_PUBLIC_FILES = {
    "MANIFEST.sha256",
    "README_REVIEWER_PACKAGE.md",
    "analysis_output_schema.json",
    "analyze_collected_results.py",
    "build_offline_analysis_release.py",
    "calibration_answer_key.csv",
    "calibration_items.csv",
    "codebook_v3_frozen.md",
    "frozen_test_claims.csv",
    "power_analysis.json",
    "power_analysis.py",
    "preregistered_protocol.md",
    "source_sampling_frame.csv",
    "study_config.json",
    "validate_package.py",
}
PUBLIC_PII_FIELD_TOKENS = (
    "legal_name",
    "email",
    "contact",
    "affiliation",
    "consent",
    "compensation",
    "conflict_of_interest",
    "notes_private",
)
IGNORED_WORKING_DIRECTORIES = {
    "generated_packets",
    "generated_calibration_packets",
    "generated_staged_review_packets",
    "generated_staged_review_packets_v2",
    "generated_composition_packets_v2",
    "collected_coordinator_responses_v2",
    "generated_internal_combined_packets",
    "generated_sampling_screen_packets",
    "analysis_outputs",
    ".analysis_selftest_workspace",
    ".packet_selftest_workspace",
    ".calibration_packet_selftest_workspace",
    ".calibration_score_selftest_workspace",
    ".validator_selftest_workspace",
    ".sampling_screen_selftest_workspace",
    ".source_replacement_selftest_workspace",
    ".review_packet_cli_selftest_workspace",
    ".staged_review_selftest_workspace",
    ".composition_issuer_selftest_workspace",
    ".response_collector_selftest_workspace",
}


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        return header, list(reader)


def add_check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def duplicate_values(rows: Iterable[Mapping[str, str]], field: str) -> list[str]:
    counts = Counter((row.get(field) or "").strip() for row in rows)
    return sorted(value for value, count in counts.items() if value and count > 1)


def read_text_or_error(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read {path.name}: {exc}")
        return ""


def resolve_repository_input(root: Path, relative_path: str) -> Path:
    """Resolve a repository-relative input without escaping a standalone package."""

    if (root / STANDALONE_REVIEWER_MARKER).is_file():
        return root / ".external-inputs-not-bundled" / relative_path
    for ancestor in (root, *root.parents):
        if ancestor.name == "manuscript":
            return ancestor.parent / relative_path
    return root / ".external-inputs-not-bundled" / relative_path


def record_external_skip(
    skips: list[dict[str, str]],
    input_path: str,
    reason: str,
    verification: str,
    frozen_sha256: str = "",
) -> None:
    record = {
        "input": input_path,
        "reason": reason,
        "verification": verification,
    }
    if frozen_sha256:
        record["frozen_sha256"] = frozen_sha256
    if record not in skips:
        skips.append(record)


def record_portable_private_verification_skip(
    skips: list[dict[str, str]],
) -> None:
    record_external_skip(
        skips,
        PRIVATE_PARTICIPANT_VERIFICATION_INPUT,
        "PII and access-controlled ethics records are intentionally absent "
        "from the public reviewer package",
        "NOT VERIFIED IN PORTABLE MODE; requires strict full-repository "
        "frozen validation with --participant-metadata",
    )


def validate_packaged_development_registry(
    root: Path,
    config: Mapping[str, Any],
    errors: list[str],
) -> tuple[
    set[str],
    set[str],
    list[dict[str, str]],
    dict[str, dict[str, str]],
]:
    keys_text = read_text_or_error(root / "DEVELOPMENT_SOURCE_KEYS.txt", errors)
    sources_text = read_text_or_error(root / "DEVELOPMENT_SOURCES.csv", errors)
    source_rows: list[dict[str, str]] = []
    sources_path = root / "DEVELOPMENT_SOURCES.csv"
    if sources_path.exists():
        header, source_rows = read_csv(sources_path)
        add_check(
            errors,
            header == DEVELOPMENT_SOURCES_HEADER,
            "DEVELOPMENT_SOURCES.csv header differs from the frozen schema",
        )

    add_check(
        errors,
        not duplicate_values(source_rows, "source_key"),
        "DEVELOPMENT_SOURCES.csv contains duplicate source keys",
    )
    allowed_scopes = {V1_SCOPE, V2_SCOPE}
    for index, row in enumerate(source_rows, start=2):
        source_key = (row.get("source_key") or "").strip()
        source_title = (row.get("source_title") or "").strip()
        normalized_title = (row.get("normalized_title") or "").strip()
        scopes = (row.get("provenance_scope") or "").strip().split("|")
        add_check(
            errors,
            bool(source_key) and bool(source_title) and bool(normalized_title),
            f"DEVELOPMENT_SOURCES.csv row {index} has an empty key/title",
        )
        add_check(
            errors,
            normalized_title == normalize_title(source_title),
            f"DEVELOPMENT_SOURCES.csv row {index} has a stale normalized title",
        )
        add_check(
            errors,
            bool(scopes)
            and len(scopes) == len(set(scopes))
            and set(scopes).issubset(allowed_scopes),
            f"DEVELOPMENT_SOURCES.csv row {index} has invalid provenance scope",
        )

    sorted_rows = sorted(source_rows, key=lambda row: row["source_key"])
    add_check(
        errors,
        sources_text == serialize_sources(sorted_rows),
        "DEVELOPMENT_SOURCES.csv is not in canonical frozen order",
    )
    source_keys = {row["source_key"].strip() for row in source_rows}
    add_check(
        errors,
        keys_text == serialize_keys(source_keys),
        "DEVELOPMENT_SOURCE_KEYS.txt and DEVELOPMENT_SOURCES.csv are inconsistent",
    )
    source_by_key = {row["source_key"].strip(): row for row in source_rows}
    normalized_titles = {
        row["normalized_title"].strip() for row in source_rows
    }
    title_to_keys: dict[str, set[str]] = defaultdict(set)
    for row in source_rows:
        title_to_keys[row["normalized_title"].strip()].add(
            row["source_key"].strip()
        )
    v1_keys = {
        row["source_key"].strip()
        for row in source_rows
        if V1_SCOPE in (row.get("provenance_scope") or "").split("|")
    }
    v2_keys = {
        row["source_key"].strip()
        for row in source_rows
        if V2_SCOPE in (row.get("provenance_scope") or "").split("|")
    }
    add_check(
        errors,
        v2_keys == set(FIXED_V2_KEYS),
        "packaged v2 development sources are not the frozen nine",
    )

    internal_expected = {
        "development_v1_pair_source_key_count": len(v1_keys),
        "development_v2_fixed_source_key_count": len(v2_keys),
        "development_source_key_input_overlap": len(v1_keys.intersection(v2_keys)),
        "development_source_key_count": len(source_keys),
        "development_source_title_count": len(normalized_titles),
        "development_source_title_alias_groups": sum(
            len(keys) > 1 for keys in title_to_keys.values()
        ),
    }
    for field, expected_value in internal_expected.items():
        add_check(
            errors,
            config.get(field) == expected_value,
            f"study config {field} is inconsistent with packaged DEVELOPMENT_*",
        )

    fixed_external_metadata = {
        "development_pair_provenance_path": PROVENANCE_RELATIVE_PATH,
        "development_v2_title_source_path": V2_TITLE_RELATIVE_PATH,
        "development_pair_provenance_row_count": 60,
        "development_v2_title_source_row_count": 80,
    }
    for field, expected_value in fixed_external_metadata.items():
        add_check(
            errors,
            config.get(field) == expected_value,
            f"study config {field} is not the frozen v3 value",
        )
    for field in (
        "development_pair_provenance_sha256",
        "development_v2_title_source_sha256",
    ):
        add_check(
            errors,
            bool(SHA256_RE.fullmatch(str(config.get(field, "")))),
            f"study config {field} is not a lowercase SHA-256",
        )
    return source_keys, normalized_titles, source_rows, source_by_key


def validate_development_sources(
    root: Path,
    config: Mapping[str, Any],
    errors: list[str],
    portable: bool,
    external_input_skips: list[dict[str, str]],
    provenance_path: Path | None = None,
    v2_title_path: Path | None = None,
) -> tuple[set[str], set[str]]:
    (
        packaged_keys,
        packaged_titles,
        packaged_rows,
        packaged_by_key,
    ) = validate_packaged_development_registry(root, config, errors)
    provenance_path = provenance_path or resolve_repository_input(
        root, PROVENANCE_RELATIVE_PATH
    )
    v2_title_path = v2_title_path or resolve_repository_input(
        root, V2_TITLE_RELATIVE_PATH
    )
    provenance_exists = provenance_path.is_file()
    v2_exists = v2_title_path.is_file()

    if not provenance_exists:
        if portable:
            record_external_skip(
                external_input_skips,
                PROVENANCE_RELATIVE_PATH,
                "external input absent in portable reviewer package",
                "frozen study_config hash/row metadata plus canonical packaged "
                "DEVELOPMENT_* registry",
                str(config.get("development_pair_provenance_sha256", "")),
            )
        else:
            errors.append(
                f"cannot reconstruct development-source exclusions: "
                f"{PROVENANCE_RELATIVE_PATH} is missing"
            )
    if not v2_exists:
        if portable:
            record_external_skip(
                external_input_skips,
                V2_TITLE_RELATIVE_PATH,
                "external input absent in portable reviewer package",
                "frozen study_config hash/row metadata plus canonical packaged "
                "DEVELOPMENT_* registry",
                str(config.get("development_v2_title_source_sha256", "")),
            )
        else:
            errors.append(
                f"cannot reconstruct development-source exclusions: "
                f"{V2_TITLE_RELATIVE_PATH} is missing"
            )

    if provenance_exists:
        try:
            v1_sources, pair_rows = read_pair_sources(provenance_path)
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read existing development provenance: {exc}")
        else:
            add_check(
                errors,
                sha256_file(provenance_path)
                == config.get("development_pair_provenance_sha256"),
                "actual development provenance hash differs from study_config.json",
            )
            add_check(
                errors,
                pair_rows == config.get("development_pair_provenance_row_count"),
                "actual development provenance row count differs from study_config.json",
            )
            packaged_v1 = {
                key
                for key, row in packaged_by_key.items()
                if V1_SCOPE in row["provenance_scope"].split("|")
            }
            add_check(
                errors,
                set(v1_sources) == packaged_v1,
                "existing v1 provenance keys differ from packaged DEVELOPMENT_*",
            )
            for key, title in v1_sources.items():
                packaged = packaged_by_key.get(key)
                if packaged is not None:
                    add_check(
                        errors,
                        normalize_title(title) == packaged["normalized_title"],
                        f"existing v1 provenance title differs for {key}",
                    )

    if v2_exists:
        try:
            v2_sources, v2_rows = read_v2_sources(v2_title_path)
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read existing v2 title source: {exc}")
        else:
            add_check(
                errors,
                sha256_file(v2_title_path)
                == config.get("development_v2_title_source_sha256"),
                "actual v2 title-source hash differs from study_config.json",
            )
            add_check(
                errors,
                v2_rows == config.get("development_v2_title_source_row_count"),
                "actual v2 title-source row count differs from study_config.json",
            )
            add_check(
                errors,
                set(v2_sources) == set(FIXED_V2_KEYS),
                "existing v2 title source does not cover the frozen nine",
            )
            for key, title in v2_sources.items():
                packaged = packaged_by_key.get(key)
                if packaged is not None:
                    add_check(
                        errors,
                        normalize_title(title) == packaged["normalized_title"],
                        f"existing v2 title differs for {key}",
                    )

    if provenance_exists and v2_exists:
        try:
            rebuilt_keys, development_metadata = build_key_set(provenance_path)
            rebuilt_rows, title_metadata = build_source_rows(
                provenance_path, v2_title_path
            )
        except (OSError, ValueError) as exc:
            errors.append(
                f"cannot strictly reconstruct development-source exclusions: {exc}"
            )
        else:
            add_check(
                errors,
                rebuilt_keys == packaged_keys,
                "DEVELOPMENT_SOURCE_KEYS.txt is not the exact generated v1/v2 union",
            )
            add_check(
                errors,
                serialize_sources(rebuilt_rows) == serialize_sources(packaged_rows),
                "DEVELOPMENT_SOURCES.csv is not the exact generated key/title union",
            )
            expected_config = {
                "development_pair_provenance_row_count": development_metadata[
                    "pair_rows"
                ],
                "development_pair_provenance_sha256": development_metadata[
                    "provenance_sha256"
                ],
                "development_v1_pair_source_key_count": development_metadata[
                    "unique_v1_pair_source_keys"
                ],
                "development_source_key_input_overlap": development_metadata[
                    "overlap_between_inputs"
                ],
                "development_source_key_count": development_metadata[
                    "combined_development_source_keys"
                ],
                "development_source_title_count": title_metadata[
                    "unique_development_titles"
                ],
                "development_source_title_alias_groups": title_metadata[
                    "development_title_alias_groups"
                ],
                "development_v2_title_source_row_count": title_metadata[
                    "v2_title_source_rows"
                ],
                "development_v2_title_source_sha256": title_metadata[
                    "v2_title_source_sha256"
                ],
            }
            for field, expected_value in expected_config.items():
                add_check(
                    errors,
                    config.get(field) == expected_value,
                    f"study config {field} does not match development provenance",
                )
    return packaged_keys, packaged_titles


def validate_no_csv_cell_controls(root: Path, errors: list[str]) -> None:
    """Reject every C0 character parsed inside a CSV header or data cell."""

    for path in sorted(root.rglob("*.csv")):
        relative = path.relative_to(root)
        if any(
            part in IGNORED_WORKING_DIRECTORIES for part in relative.parts
        ):
            continue
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                for row_number, cells in enumerate(csv.reader(handle), start=1):
                    for column_number, cell in enumerate(cells, start=1):
                        for codepoint in c0_codepoints(cell):
                            errors.append(
                                f"{path.name} row {row_number} column "
                                f"{column_number} contains C0 control "
                                f"U+{codepoint:04X} inside a CSV cell"
                            )
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            errors.append(f"cannot scan CSV controls in {path.name}: {exc}")


def validate_headers_and_load(
    root: Path, errors: list[str]
) -> dict[str, list[dict[str, str]]]:
    loaded: dict[str, list[dict[str, str]]] = {}
    validate_no_csv_cell_controls(root, errors)
    add_check(
        errors,
        PREPARED_SOURCE_HEADER == SOURCE_HEADER,
        "candidate-pool source schema differs from the frozen package schema",
    )
    add_check(
        errors,
        MODEL_PRESCREEN_HEADER == CANDIDATE_HEADER,
        "candidate-pool model import schema differs from the frozen schema",
    )
    add_check(
        errors,
        FREEZER_FROZEN_HEADER == FROZEN_CLAIM_HEADER,
        "sample freezer output schema differs from the frozen claim schema",
    )
    for name, expected_header in EXPECTED_HEADERS.items():
        path = root / name
        if not path.exists():
            errors.append(f"missing CSV template: {name}")
            continue
        header, rows = read_csv(path)
        add_check(
            errors,
            header == expected_header,
            f"{name} header differs from the frozen schema",
        )
        loaded[name] = rows

    for name in ARM_RESPONSE_FILES.values():
        header = set(EXPECTED_HEADERS[name])
        add_check(
            errors,
            RAW_PACKET_FIELDS.issubset(header),
            f"{name} does not contain the common raw evidence fields",
        )
        leaked = sorted(
            field
            for field in header
            if "model" in field
            or "prescreen" in field
            or "synthetic" in field
            or "coordinator_only" in field
        )
        add_check(errors, not leaked, f"{name} contains model/coordinator fields: {leaked}")

    c_header = set(EXPECTED_HEADERS["arm_C_responses.csv"])
    c_ablation_leaks = sorted(
        field
        for field in c_header
        if any(token in field for token in ("origin", "capability", "policy", "utility"))
    )
    add_check(
        errors,
        not c_ablation_leaks,
        f"Arm C contains ablated fields: {c_ablation_leaks}",
    )
    gold_header_lower = {field.lower() for field in EXPECTED_HEADERS["gold_responses.csv"]}
    gold_coordinate_leaks = sorted(
        field for field in gold_header_lower if re.search(r"(^|_)c[1-5]($|_)", field)
    )
    add_check(
        errors,
        not gold_coordinate_leaks,
        f"gold schema contains coordinate vocabulary: {gold_coordinate_leaks}",
    )
    return loaded


def validate_pre_registration_files(
    root: Path,
    errors: list[str],
    portable: bool,
    external_input_skips: list[dict[str, str]],
) -> tuple[dict[str, Any], set[str], set[str]]:
    existing = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    missing = sorted(REQUIRED_FILES - existing)
    add_check(errors, not missing, f"required package files missing: {missing}")

    config: dict[str, Any] = {}
    try:
        config = json.loads(read_text_or_error(root / "study_config.json", errors))
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read study_config.json: {exc}")
    if config:
        add_check(errors, config.get("status") == STATUS, "study config status is not frozen")
        add_check(
            errors,
            config.get("label_status") == "NO_TEST_LABELS_COLLECTED",
            "study config label status is not NO_TEST_LABELS_COLLECTED",
        )
        add_check(
            errors,
            config.get("primary_test_claims") == DEFAULT_EXPECTED_CLAIMS,
            "study config claim target is not 480",
        )
        add_check(
            errors,
            config.get("primary_test_sources") == DEFAULT_EXPECTED_SOURCES,
            "study config source target is not 80",
        )
        add_check(
            errors,
            config.get("assignment_seed") == DEFAULT_SEED,
            "study config assignment seed mismatch",
        )
        staged_expectations = {
            "staged_review_workflow_version": STAGED_WORKFLOW_VERSION,
            "staged_review_extraction_hash_schema_version": (
                STAGED_EXTRACTION_HASH_SCHEMA_VERSION
            ),
            "staged_review_correction_schema_version": (
                STAGED_CORRECTION_SCHEMA_VERSION
            ),
            "staged_review_participant_packet_count": 27,
            "staged_review_initial_status": (
                "COORDINATOR_STAGE1_PACKETS_NO_TEST_RESPONSES"
            ),
            "staged_review_frozen_substates": [
                "frozen_calibration_passed_before_composition_issuance",
                "composition_issued_no_responses",
            ],
            "staged_review_packet_registry_schema_version": (
                STAGED_PACKET_REGISTRY_SCHEMA_VERSION
            ),
            "staged_review_issuance_registry_schema_version": (
                STAGED_ISSUANCE_REGISTRY_SCHEMA_VERSION
            ),
            "staged_review_invalidated_composition_archive_schema_version": (
                INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION
            ),
            "staged_review_invalidated_composition_archive_status": (
                "COLLECTED_ONLY_ABSENT_IN_FROZEN_REVIEWER"
            ),
            "staged_review_receipt_schema_version": (
                STAGED_RECEIPT_SCHEMA_VERSION
            ),
            "staged_review_issued_packet_strict_verification": (
                "REQUIRES_EXTERNAL_COMPOSITION_PACKETS_ROOT"
            ),
            "staged_review_issued_packet_portable_verification": (
                "INTERNAL_CHAIN_ONLY_PACKET_BYTES_NOT_INCLUDED"
            ),
            "adjudicator_packet_version": ADJUDICATOR_PACKET_VERSION,
            "adjudicator_packet_registry_schema_version": (
                ADJUDICATOR_REGISTRY_SCHEMA_VERSION
            ),
            "adjudicator_packet_registry_initial_status": (
                "NO_ADJUDICATOR_PACKETS_ISSUED"
            ),
        }
        for field, expected in staged_expectations.items():
            add_check(
                errors,
                config.get(field) == expected,
                f"study config staged-review field {field} is inconsistent",
            )
    try:
        staged_schema = json.loads(
            read_text_or_error(root / "staged_review_schema.json", errors)
        )
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read staged_review_schema.json: {exc}")
        staged_schema = {}
    add_check(
        errors,
        staged_schema.get("workflow_version") == STAGED_WORKFLOW_VERSION
        and staged_schema.get("packet_registry_schema_version")
        == STAGED_PACKET_REGISTRY_SCHEMA_VERSION
        and staged_schema.get("issuance_registry_schema_version")
        == STAGED_ISSUANCE_REGISTRY_SCHEMA_VERSION
        and staged_schema.get("correction_schema_version")
        == STAGED_CORRECTION_SCHEMA_VERSION
        and staged_schema.get("response_receipt_schema_version")
        == STAGED_RECEIPT_SCHEMA_VERSION
        and staged_schema.get("adjudicator_packet_version")
        == ADJUDICATOR_PACKET_VERSION
        and staged_schema.get("adjudicator_packet_registry_schema_version")
        == ADJUDICATOR_REGISTRY_SCHEMA_VERSION,
        "staged review schema/version fields are inconsistent",
    )

    readme = read_text_or_error(root / "README.md", errors)
    add_check(errors, STATUS in readme, "README does not show the required status")
    lowered = readme.lower()
    add_check(
        errors,
        "synthetic" in lowered and "never a human label" in lowered,
        "README lacks the synthetic/model-only human-label prohibition",
    )

    add_check(
        errors,
        FIXED_V2_KEYS == EXPECTED_FIXED_V2_KEYS,
        "development-key builder does not contain the frozen nine v2 keys",
    )
    development_keys, development_titles = validate_development_sources(
        root,
        config,
        errors,
        portable,
        external_input_skips,
    )

    try:
        power = json.loads(read_text_or_error(root / "power_analysis.json", errors))
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read power_analysis.json: {exc}")
        power = {}
    if power:
        add_check(
            errors,
            power.get("status")
            == "PROSPECTIVE_POWER_APPROXIMATION_NOT_EMPIRICAL_RESULTS",
            "power output is not marked prospective/non-empirical",
        )
        add_check(
            errors,
            power.get("baseline_all_scenarios_meet_target") is False,
            "power output must disclose that the 360-claim design is insufficient",
        )
        chosen = power.get("chosen_design", {})
        conservative = power.get("conservative_minimum_superiority_design", {})
        add_check(errors, chosen.get("claims") == 480, "power chosen claim target mismatch")
        add_check(errors, chosen.get("sources") == 80, "power chosen source target mismatch")
        add_check(
            errors,
            chosen.get("all_superiority_scenarios_meet_target") is True,
            "chosen design does not meet every superiority scenario",
        )
        add_check(
            errors,
            float(chosen.get("worst_superiority_power", 0.0)) >= 0.80,
            "chosen design worst superiority power is below .80",
        )
        add_check(
            errors,
            int(conservative.get("claims", 10**9)) <= 480,
            "conservative minimum exceeds the chosen claim target",
        )
    return config, development_keys, development_titles


def validate_model_prescreen(
    rows: Sequence[Mapping[str, str]], errors: list[str], prescreen_seed: int
) -> str:
    duplicates = duplicate_values(rows, "candidate_claim_id")
    add_check(errors, not duplicates, f"duplicate candidate claim IDs: {duplicates[:5]}")
    selection_states: Counter[str] = Counter()
    for index, row in enumerate(rows, start=2):
        model_status = (row.get("model_only_status") or "").strip()
        if model_status == MODEL_ONLY_STATUS:
            for field in (
                "prescreen_c2_decisive_probability",
                "prescreen_c5_decisive_probability",
            ):
                try:
                    score = float((row.get(field) or "").strip())
                except ValueError:
                    score = -1.0
                add_check(
                    errors,
                    0.0 <= score <= 1.0,
                    f"candidate row {index} has {field} outside [0,1]",
                )
            add_check(
                errors,
                bool((row.get("prescreen_system") or "").strip())
                and bool((row.get("prescreen_system_version") or "").strip()),
                f"candidate row {index} lacks prescreen system/version",
            )
            add_check(
                errors,
                bool(
                    SHA256_RE.fullmatch(
                        (row.get("prescreen_prompt_sha256") or "").strip()
                    )
                ),
                f"candidate row {index} has an invalid prescreen prompt hash",
            )
            add_check(
                errors,
                bool((row.get("prescreen_rationale") or "").strip()),
                f"candidate row {index} lacks a model-only rationale",
            )
            add_check(
                errors,
                (row.get("prescreen_seed") or "").strip()
                == str(prescreen_seed),
                f"candidate row {index} has an unexpected prescreen seed",
            )
        elif model_status == MODEL_FREE_SCREENING_STATUS:
            add_check(
                errors,
                all(
                    not (row.get(field) or "").strip()
                    for field in SAMPLING_MODEL_FIELDS
                ),
                f"model-free candidate row {index} populates a model field",
            )
        else:
            errors.append(
                f"candidate row {index} has an unknown model/model-free status"
            )

        candidate_id = (row.get("candidate_claim_id") or "").strip()
        selection_status = (row.get("selection_status") or "").strip()
        selection_states[selection_status] += 1
        if selection_status == "awaiting_human_sampling_screen":
            add_check(
                errors,
                all(
                    not (row.get(field) or "").strip()
                    for field in SAMPLING_HUMAN_FIELDS
                ),
                f"awaiting candidate row {index} pre-populates human fields",
            )
        elif selection_status == "awaiting_human_sampling_tiebreak":
            reviewer_ids = [
                (row.get("human_sampling_reviewer_1_id") or "").strip(),
                (row.get("human_sampling_reviewer_2_id") or "").strip(),
            ]
            add_check(
                errors,
                all(reviewer_ids) and len(set(reviewer_ids)) == 2,
                f"disputed candidate row {index} lacks two independent screeners",
            )
            add_check(
                errors,
                all(
                    not (row.get(field) or "").strip()
                    for field in (
                        "human_sampling_tiebreak_reviewer_id",
                        "human_sampling_eligibility",
                        "human_sampling_stratum",
                        "exclusion_reason_code",
                        "exclusion_reason_detail",
                        "deterministic_claim_rank",
                    )
                ),
                f"disputed candidate row {index} contains a premature resolution",
            )
        elif selection_status in {
            "human_screen_consensus",
            "human_screen_tiebreak",
        }:
            try:
                validate_human_screen_row(row, candidate_id)
            except ValueError as exc:
                errors.append(str(exc))
        else:
            errors.append(
                f"candidate row {index} has invalid sampling merge status "
                f"{selection_status!r}"
            )

    observed_states = set(selection_states)
    if not rows:
        return "not_initialized"
    if observed_states == {"awaiting_human_sampling_screen"}:
        return "awaiting_human_sampling_screen"
    if (
        "awaiting_human_sampling_screen" in observed_states
        and observed_states.issubset(
            {
                "awaiting_human_sampling_screen",
                "human_screen_consensus",
                "human_screen_tiebreak",
            }
        )
        and all(
            (row.get("candidate_claim_id") or "").strip().startswith("H3R-")
            for row in rows
            if (row.get("selection_status") or "").strip()
            == "awaiting_human_sampling_screen"
        )
    ):
        return "awaiting_replacement_screen"
    if (
        "awaiting_human_sampling_tiebreak" in observed_states
        and observed_states.issubset(
            {
                "human_screen_consensus",
                "human_screen_tiebreak",
                "awaiting_human_sampling_tiebreak",
            }
        )
    ):
        waiting_ids = [
            (row.get("candidate_claim_id") or "").strip()
            for row in rows
            if (row.get("selection_status") or "").strip()
            == "awaiting_human_sampling_tiebreak"
        ]
        return (
            "awaiting_replacement_tiebreak"
            if waiting_ids
            and all(candidate_id.startswith("H3R-") for candidate_id in waiting_ids)
            else "awaiting_human_sampling_tiebreak"
        )
    if observed_states.issubset(
        {"human_screen_consensus", "human_screen_tiebreak"}
    ):
        return "human_sampling_screen_complete"
    errors.append(
        f"candidate rows mix incompatible sampling states: "
        f"{sorted(observed_states)}"
    )
    return "invalid_sampling_screen_state"


def validate_frozen_text_correction_state(
    root: Path,
    deterministic_rows: Sequence[Mapping[str, str]],
    candidate_rows: Sequence[Mapping[str, str]],
    frozen_rows: Sequence[Mapping[str, str]],
    errors: list[str],
) -> ReversedCorrectionState | None:
    ledger_path = root / "frozen_text_corrections.csv"
    ledger_header, correction_rows = read_csv(ledger_path)
    add_check(
        errors,
        ledger_header == FROZEN_TEXT_CORRECTION_HEADER,
        "frozen text-correction ledger schema mismatch",
    )
    try:
        reversed_state = validate_and_reverse_corrections(
            correction_rows,
            deterministic_rows,
            candidate_rows,
            frozen_rows,
        )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"frozen text-correction ledger validation failed: {exc}")
        return None

    def serialized_hash(
        header: Sequence[str], rows: Sequence[Mapping[str, str]]
    ) -> str:
        return hashlib.sha256(
            serialize_text_correction_csv(header, rows)
        ).hexdigest()

    pre_hashes = {
        "candidate_claims_deterministic_sha256": serialized_hash(
            DETERMINISTIC_CANDIDATE_HEADER,
            reversed_state.deterministic_rows,
        ),
        "candidate_claims_model_prescreen_sha256": serialized_hash(
            CANDIDATE_HEADER, reversed_state.human_rows
        ),
        "frozen_test_claims_sha256": serialized_hash(
            FROZEN_CLAIM_HEADER, reversed_state.frozen_rows
        ),
    }
    post_hashes = {
        "candidate_claims_deterministic_sha256": sha256_file(
            root / "candidate_claims_deterministic.csv"
        ),
        "candidate_claims_model_prescreen_sha256": sha256_file(
            root / "candidate_claims_model_prescreen.csv"
        ),
        "frozen_test_claims_sha256": sha256_file(
            root / "frozen_test_claims.csv"
        ),
    }
    ledger_sha256 = sha256_file(ledger_path)
    recorded_values = {
        str(row.get("recorded_utc", "")) for row in correction_rows
    }
    recorded_utc = next(iter(recorded_values), "")
    add_check(
        errors,
        len(correction_rows) == 12
        and len(reversed_state.affected_claim_ids) == 11
        and reversed_state.selected_claim_ids == (TEXT_CORRECTION_CLAIM_ID,)
        and recorded_values == {recorded_utc}
        and bool(recorded_utc),
        "frozen text-correction ledger count/timestamp mismatch",
    )

    try:
        screen_summary = json.loads(
            read_text_or_error(root / "sampling_screen_summary.json", errors)
        )
    except json.JSONDecodeError as exc:
        errors.append(f"cannot validate text-correction screen anchor: {exc}")
        screen_summary = {}
    stages = screen_summary.get("stages")
    correction_stages = (
        [
            stage
            for stage in stages
            if isinstance(stage, dict)
            and stage.get("stage") == "apply_pretest_text_corrections"
        ]
        if isinstance(stages, list)
        else []
    )
    add_check(
        errors,
        len(correction_stages) == 1
        and isinstance(stages, list)
        and stages[-1] is correction_stages[0],
        "pre-test text correction must be the final, unique sampling stage",
    )
    old_screen_sha256 = ""
    if len(correction_stages) == 1 and isinstance(stages, list):
        stage = correction_stages[0]

        def artifacts(direction: str) -> dict[str, tuple[object, object]]:
            values = stage.get(direction)
            return (
                {
                    str(item.get("artifact", "")): (
                        item.get("rows"),
                        item.get("sha256"),
                    )
                    for item in values
                    if isinstance(item, dict)
                }
                if isinstance(values, list)
                else {}
            )

        expected_inputs = {
            "candidate_claims_deterministic.csv": (
                len(deterministic_rows),
                pre_hashes["candidate_claims_deterministic_sha256"],
            ),
            "candidate_claims_model_prescreen.csv": (
                len(candidate_rows),
                pre_hashes["candidate_claims_model_prescreen_sha256"],
            ),
            "frozen_test_claims.csv": (
                len(frozen_rows),
                pre_hashes["frozen_test_claims_sha256"],
            ),
            "frozen_text_corrections.csv": (
                len(correction_rows),
                ledger_sha256,
            ),
        }
        expected_outputs = {
            "candidate_claims_deterministic.csv": (
                len(deterministic_rows),
                post_hashes["candidate_claims_deterministic_sha256"],
            ),
            "candidate_claims_model_prescreen.csv": (
                len(candidate_rows),
                post_hashes["candidate_claims_model_prescreen_sha256"],
            ),
            "frozen_test_claims.csv": (
                len(frozen_rows),
                post_hashes["frozen_test_claims_sha256"],
            ),
        }
        add_check(
            errors,
            artifacts("inputs") == expected_inputs
            and artifacts("outputs") == expected_outputs
            and stage.get("recorded_utc") == recorded_utc
            and stage.get("screener_ids") == []
            and stage.get("counts")
            == {
                "correction_records": 12,
                "affected_candidates": 11,
                "affected_frozen_claims": 1,
                "parsed_cells_corrected": 33,
                "test_outcomes_generated": 0,
            },
            "pre-test text-correction stage is stale",
        )
        pre_screen = dict(screen_summary)
        pre_screen["stages"] = stages[:-1]
        pre_screen["current_candidate_state"] = {
            "artifact": "candidate_claims_model_prescreen.csv",
            "rows": len(candidate_rows),
            "sha256": pre_hashes[
                "candidate_claims_model_prescreen_sha256"
            ],
        }
        old_screen_sha256 = hashlib.sha256(
            (
                json.dumps(
                    pre_screen,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest()

    target_old = next(
        (
            row
            for row in reversed_state.frozen_rows
            if row.get("claim_id") == TEXT_CORRECTION_CLAIM_ID
        ),
        {},
    )
    target_new = next(
        (
            row
            for row in frozen_rows
            if row.get("claim_id") == TEXT_CORRECTION_CLAIM_ID
        ),
        {},
    )
    expected_pre = {
        **pre_hashes,
        "sampling_screen_summary_sha256": old_screen_sha256,
        "authoritative_sampling_record_sha256": target_old.get(
            "sampling_record_sha256", ""
        ),
        "coordinator_packet_registry_sha256": (
            PRE_TEXT_CORRECTION_COORDINATOR_REGISTRY_SHA256
        ),
    }
    expected_post = {
        **post_hashes,
        "sampling_screen_summary_sha256": sha256_file(
            root / "sampling_screen_summary.json"
        ),
        "authoritative_sampling_record_sha256": target_new.get(
            "sampling_record_sha256", ""
        ),
        "coordinator_packet_registry_sha256": sha256_file(
            root / "coordinator_packet_registry.json"
        ),
    }
    try:
        freeze_summary = json.loads(
            read_text_or_error(root / "sampling_freeze_summary.json", errors)
        )
    except json.JSONDecodeError as exc:
        errors.append(f"cannot validate text-correction freeze anchor: {exc}")
        freeze_summary = {}
    audit = freeze_summary.get("pre_test_text_correction")
    expected_audit = {
        "schema_version": FROZEN_TEXT_CORRECTION_SCHEMA_VERSION,
        "status": "APPLIED_BEFORE_STAGE1_DISTRIBUTION_NO_TEST_RESPONSES",
        "recorded_utc": recorded_utc,
        "ledger_artifact": "frozen_text_corrections.csv",
        "ledger_rows": 12,
        "ledger_sha256": ledger_sha256,
        "affected_candidate_claims": 11,
        "affected_frozen_claims": 1,
        "parsed_cells_corrected": 33,
        "authoritative_claim_id": TEXT_CORRECTION_CLAIM_ID,
        "authoritative_source_key": TEXT_CORRECTION_SOURCE_KEY,
        "authoritative_source_url": TEXT_CORRECTION_SOURCE_URL,
        "assignments_sha256_unchanged": sha256_file(
            root / "auditor_assignments.csv"
        ),
        "claim_ids_sources_strata_assignments_unchanged": True,
        "formal_test_response_rows_at_correction": 0,
        "composition_issuance_rows_at_correction": 0,
        "coordinator_response_receipt_rows_at_correction": 0,
        "stage1_distribution_status": (
            "NOT_DISTRIBUTED_REBUILT_AFTER_CORRECTION"
        ),
        "rebuilt_stage1_participant_packets": 27,
        "rebuilt_stage1_extraction_rows": 7200,
        "test_labels_generated": 0,
        "pre_correction": expected_pre,
        "post_correction": expected_post,
    }
    add_check(
        errors,
        isinstance(audit, dict) and audit == expected_audit,
        "sampling freeze text-correction audit is stale",
    )
    add_check(
        errors,
        freeze_summary.get("frozen_claims_sha256")
        == post_hashes["frozen_test_claims_sha256"]
        and freeze_summary.get("sampling_screen_summary_sha256")
        == expected_post["sampling_screen_summary_sha256"],
        "sampling freeze summary does not anchor corrected artifacts",
    )

    try:
        replacement_summary = json.loads(
            read_text_or_error(root / "source_replacement_summary.json", errors)
        )
    except json.JSONDecodeError:
        replacement_summary = {}
    batches = replacement_summary.get("batches")
    add_check(
        errors,
        isinstance(batches, list)
        and bool(batches)
        and isinstance(batches[-1], dict)
        and isinstance(batches[-1].get("outputs"), dict)
        and batches[-1]["outputs"].get(
            "candidate_claims_deterministic_sha256"
        )
        == pre_hashes["candidate_claims_deterministic_sha256"],
        "text-correction preimage differs from the replacement-chain output",
    )
    add_check(
        errors,
        target_new.get("source_key") == TEXT_CORRECTION_SOURCE_KEY
        and target_new.get("claim_text") == TEXT_CORRECTION_NEW_TEXT
        and target_new.get("source_evidence_excerpt")
        == TEXT_CORRECTION_NEW_TEXT,
        "corrected frozen claim is not the authoritative record",
    )

    try:
        config = json.loads(read_text_or_error(root / "study_config.json", errors))
    except json.JSONDecodeError:
        config = {}
    expected_config = {
        "package_version": "v3.0.1-pretest-text-correction",
        "frozen_text_correction_schema_version": (
            FROZEN_TEXT_CORRECTION_SCHEMA_VERSION
        ),
        "frozen_text_correction_status": (
            "APPLIED_BEFORE_STAGE1_DISTRIBUTION_NO_TEST_RESPONSES"
        ),
        "frozen_text_correction_records": 12,
        "frozen_text_corrections_sha256": ledger_sha256,
        "frozen_text_correction_authoritative_claim_id": (
            TEXT_CORRECTION_CLAIM_ID
        ),
        "frozen_text_correction_authoritative_source_url": (
            TEXT_CORRECTION_SOURCE_URL
        ),
        "frozen_text_correction_recorded_utc": recorded_utc,
        "frozen_text_correction_pre_frozen_claims_sha256": (
            pre_hashes["frozen_test_claims_sha256"]
        ),
        "frozen_text_correction_post_frozen_claims_sha256": (
            post_hashes["frozen_test_claims_sha256"]
        ),
        "frozen_text_correction_pre_coordinator_registry_sha256": (
            PRE_TEXT_CORRECTION_COORDINATOR_REGISTRY_SHA256
        ),
        "frozen_text_correction_post_coordinator_registry_sha256": (
            sha256_file(root / "coordinator_packet_registry.json")
        ),
        "frozen_text_correction_stage1_rebuild_status": (
            "NOT_DISTRIBUTED_REBUILT_AFTER_CORRECTION"
        ),
    }
    add_check(
        errors,
        all(config.get(field) == value for field, value in expected_config.items()),
        "study config text-correction metadata is stale",
    )
    return reversed_state


def validate_sampling_screen_summary(
    root: Path,
    candidate_rows: Sequence[Mapping[str, str]],
    candidate_state: str,
    errors: list[str],
) -> dict[str, Any]:
    path = root / "sampling_screen_summary.json"
    _deterministic_header, deterministic_rows = read_csv(
        root / "candidate_claims_deterministic.csv"
    )
    deterministic_sha256 = sha256_file(
        root / "candidate_claims_deterministic.csv"
    )
    try:
        candidate_pool_summary = json.loads(
            (root / "candidate_pool_summary.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        candidate_pool_summary = {}
    allowed_deterministic_artifacts = {
        (deterministic_sha256, len(deterministic_rows))
    }
    parent_deterministic_sha = candidate_pool_summary.get(
        "candidate_claims_deterministic_sha256"
    )
    parent_deterministic_rows = candidate_pool_summary.get(
        "deterministic_candidates"
    )
    if isinstance(parent_deterministic_sha, str) and isinstance(
        parent_deterministic_rows, int
    ):
        allowed_deterministic_artifacts.add(
            (parent_deterministic_sha, parent_deterministic_rows)
        )
    try:
        replacement_summary = json.loads(
            (root / "source_replacement_summary.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        replacement_summary = {}
    for batch in replacement_summary.get("batches", []):
        if not isinstance(batch, dict):
            continue
        for record_name in ("parent", "outputs"):
            record = batch.get(record_name)
            if not isinstance(record, dict):
                continue
            artifact_hash = record.get(
                "candidate_claims_deterministic_sha256"
            )
            artifact_rows = record.get(
                "candidate_claims_deterministic_rows"
            )
            if isinstance(artifact_hash, str) and isinstance(
                artifact_rows, int
            ):
                allowed_deterministic_artifacts.add(
                    (artifact_hash, artifact_rows)
                )
    try:
        summary = json.loads(read_text_or_error(path, errors))
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read sampling_screen_summary.json: {exc}")
        return {}
    add_check(
        errors,
        summary.get("schema_version") == SAMPLING_SCREEN_SCHEMA_VERSION,
        "sampling screen summary schema version mismatch",
    )
    add_check(
        errors,
        summary.get("prohibited_use") == SAMPLING_SCREEN_PROHIBITED_USE,
        "sampling screen summary lacks the label-use prohibition",
    )
    current = summary.get("current_candidate_state")
    add_check(
        errors,
        isinstance(current, dict),
        "sampling screen summary lacks current candidate state",
    )
    if isinstance(current, dict):
        add_check(
            errors,
            current.get("artifact") == "candidate_claims_model_prescreen.csv",
            "sampling screen summary names the wrong current candidate artifact",
        )
        add_check(
            errors,
            current.get("rows") == len(candidate_rows),
            "sampling screen summary candidate row count mismatch",
        )
        add_check(
            errors,
            current.get("sha256")
            == sha256_file(root / "candidate_claims_model_prescreen.csv"),
            "sampling screen summary candidate hash mismatch",
        )

    status = summary.get("status")
    compatible_statuses = {
        "awaiting_human_sampling_screen": {
            "initialized_model_free_awaiting_initial_packets",
            "initial_packets_built_awaiting_responses",
        },
        "awaiting_human_sampling_tiebreak": {"awaiting_tiebreak"},
        "awaiting_replacement_screen": {
            "awaiting_replacement_screen",
            "replacement_packets_built_awaiting_responses",
        },
        "awaiting_replacement_tiebreak": {
            "awaiting_replacement_tiebreak"
        },
        "human_sampling_screen_complete": {
            "human_sampling_screen_complete"
        },
    }
    add_check(
        errors,
        status in compatible_statuses.get(candidate_state, set()),
        "sampling screen summary status does not match candidate merge state",
    )
    add_check(
        errors,
        summary.get("screening_complete")
        is (candidate_state == "human_sampling_screen_complete"),
        "sampling screen summary completion flag is inconsistent",
    )

    stages = summary.get("stages")
    add_check(
        errors,
        isinstance(stages, list) and bool(stages),
        "sampling screen summary must contain an ordered stage audit chain",
    )
    observed_stage_names: list[str] = []
    observed_stage_ids: list[list[str]] = []
    if isinstance(stages, list):
        for stage_index, stage in enumerate(stages, start=1):
            if not isinstance(stage, dict):
                errors.append(
                    f"sampling screen summary stage {stage_index} is not an object"
                )
                continue
            stage_name = str(stage.get("stage", ""))
            observed_stage_names.append(stage_name)
            add_check(
                errors,
                stage_name
                in {
                    "initialize",
                    "build_initial",
                    "merge_initial",
                    "merge_tiebreak",
                    "apply_replacements",
                    "build_replacement",
                    "merge_replacement_initial",
                    "merge_replacement_tiebreak",
                    "apply_pretest_text_corrections",
                },
                f"sampling screen summary stage {stage_index} has invalid name",
            )
            add_check(
                errors,
                bool(str(stage.get("recorded_utc", "")).strip()),
                f"sampling screen summary stage {stage_index} lacks timestamp",
            )
            for direction in ("inputs", "outputs"):
                artifacts = stage.get(direction)
                add_check(
                    errors,
                    isinstance(artifacts, list) and bool(artifacts),
                    f"sampling screen stage {stage_index} lacks {direction}",
                )
                if isinstance(artifacts, list):
                    for item in artifacts:
                        valid_item = (
                            isinstance(item, dict)
                            and bool(str(item.get("artifact", "")).strip())
                            and bool(
                                SHA256_RE.fullmatch(
                                    str(item.get("sha256", ""))
                                )
                            )
                            and isinstance(item.get("rows"), int)
                            and not isinstance(item.get("rows"), bool)
                            and item.get("rows", -1) >= 0
                        )
                        add_check(
                            errors,
                            valid_item,
                            f"sampling screen stage {stage_index} has an "
                            f"invalid {direction} artifact",
                        )
                        if (
                            isinstance(item, dict)
                            and item.get("artifact")
                            == "candidate_claims_deterministic.csv"
                        ):
                            add_check(
                                errors,
                                (
                                    item.get("sha256"),
                                    item.get("rows"),
                                )
                                in allowed_deterministic_artifacts,
                                f"sampling screen stage {stage_index} has a "
                                "stale deterministic-candidate input",
                            )
            expected_artifacts = {
                "initialize": {
                    "inputs": {"candidate_claims_deterministic.csv"},
                    "outputs": {"candidate_claims_model_prescreen.csv"},
                },
                "build_initial": {
                    "inputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                    },
                    "outputs": {
                        "initial_screener_1.csv",
                        "initial_screener_2.csv",
                    },
                },
                "merge_initial": {
                    "inputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "completed_initial_screener_1.csv",
                        "completed_initial_screener_2.csv",
                    },
                    "outputs": {
                        "candidate_claims_model_prescreen.csv",
                        "tiebreak_disputes.csv",
                    },
                },
                "merge_tiebreak": {
                    "inputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "completed_tiebreak_disputes.csv",
                    },
                    "outputs": {"candidate_claims_model_prescreen.csv"},
                },
                "apply_replacements": {
                    "inputs": {
                        "source_sampling_frame.csv",
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "sampling_exclusion_replacement_ledger.csv",
                        "sampling_screen_summary_parent.json",
                    },
                    "outputs": {
                        "source_sampling_frame.csv",
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                    },
                },
                "build_replacement": {
                    "inputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "source_replacement_summary.json",
                    },
                    "outputs": {
                        "replacement_initial_screener_1.csv",
                        "replacement_initial_screener_2.csv",
                    },
                },
                "merge_replacement_initial": {
                    "inputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "completed_replacement_initial_screener_1.csv",
                        "completed_replacement_initial_screener_2.csv",
                    },
                    "outputs": {
                        "candidate_claims_model_prescreen.csv",
                        "replacement_tiebreak_disputes.csv",
                    },
                },
                "merge_replacement_tiebreak": {
                    "inputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "completed_replacement_tiebreak_disputes.csv",
                    },
                    "outputs": {"candidate_claims_model_prescreen.csv"},
                },
                "apply_pretest_text_corrections": {
                    "inputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "frozen_test_claims.csv",
                        "frozen_text_corrections.csv",
                    },
                    "outputs": {
                        "candidate_claims_deterministic.csv",
                        "candidate_claims_model_prescreen.csv",
                        "frozen_test_claims.csv",
                    },
                },
            }.get(stage_name, {})
            for direction, required_names in expected_artifacts.items():
                artifacts = stage.get(direction)
                observed_names = (
                    {
                        str(item.get("artifact", ""))
                        for item in artifacts
                        if isinstance(item, dict)
                    }
                    if isinstance(artifacts, list)
                    else set()
                )
                add_check(
                    errors,
                    required_names.issubset(observed_names)
                    and (
                        observed_names - required_names
                        <= (
                            {"source_replacement_summary_parent.json"}
                            if stage_name == "apply_replacements"
                            else set()
                        )
                    ),
                    f"sampling screen stage {stage_index} has incomplete "
                    f"{direction} artifact accounting",
                )
            counts = stage.get("counts")
            valid_counts = (
                isinstance(counts, dict)
                and all(
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                    for value in counts.values()
                )
            )
            add_check(
                errors,
                valid_counts,
                f"sampling screen stage {stage_index} has invalid counts",
            )
            if isinstance(counts, dict):
                add_check(
                    errors,
                    counts.get("test_outcomes_generated") == 0,
                    f"sampling screen stage {stage_index} is not outcome-free",
                )
            screener_ids = stage.get("screener_ids")
            expected_id_count = {
                "initialize": 0,
                "build_initial": 2,
                "merge_initial": 3,
                "merge_tiebreak": 3,
                "apply_replacements": 3,
                "build_replacement": 3,
                "merge_replacement_initial": 3,
                "merge_replacement_tiebreak": 3,
                "apply_pretest_text_corrections": 0,
            }.get(stage_name, -1)
            add_check(
                errors,
                isinstance(screener_ids, list)
                and all(
                    isinstance(value, str) and bool(value.strip())
                    for value in screener_ids
                )
                and len(screener_ids) == len(set(screener_ids)),
                f"sampling screen stage {stage_index} has invalid screener IDs",
            )
            add_check(
                errors,
                isinstance(screener_ids, list)
                and len(screener_ids) == expected_id_count,
                f"sampling screen stage {stage_index} has the wrong screener count",
            )
            observed_stage_ids.append(
                list(screener_ids) if isinstance(screener_ids, list) else []
            )
            expected_stage_hash = canonical_json_sha256(
                {
                    key: value
                    for key, value in stage.items()
                    if key != "stage_record_sha256"
                }
            )
            add_check(
                errors,
                stage.get("stage_record_sha256") == expected_stage_hash,
                f"sampling screen stage {stage_index} has an invalid record hash",
            )

    valid_initial_sequences = {
        ("initialize",),
        ("initialize", "build_initial"),
        ("initialize", "build_initial", "merge_initial"),
        (
            "initialize",
            "build_initial",
            "merge_initial",
            "merge_tiebreak",
        ),
    }
    valid_sequences = set(valid_initial_sequences)
    for base in (
        ("initialize", "build_initial", "merge_initial"),
        (
            "initialize",
            "build_initial",
            "merge_initial",
            "merge_tiebreak",
        ),
    ):
        frontier = {base}
        for _batch in range(1, 100):
            next_frontier: set[tuple[str, ...]] = set()
            for prefix in frontier:
                applied = prefix + ("apply_replacements",)
                built = applied + ("build_replacement",)
                merged = built + ("merge_replacement_initial",)
                tied = merged + ("merge_replacement_tiebreak",)
                valid_sequences.update({applied, built, merged, tied})
                next_frontier.update({merged, tied})
            frontier = next_frontier
            if all(
                len(sequence) > len(observed_stage_names)
                for sequence in frontier
            ):
                break
    valid_sequences.update(
        {
            sequence + ("apply_pretest_text_corrections",)
            for sequence in tuple(valid_sequences)
            if sequence[-1]
            in {
                "merge_initial",
                "merge_tiebreak",
                "merge_replacement_initial",
                "merge_replacement_tiebreak",
            }
        }
    )
    add_check(
        errors,
        tuple(observed_stage_names) in valid_sequences,
        "sampling screen summary stage order is invalid",
    )
    if len(observed_stage_ids) >= 3:
        add_check(
            errors,
            observed_stage_ids[2][:2] == observed_stage_ids[1],
            "merge-initial screener IDs differ from the issued initial packets",
        )
    if (
        len(observed_stage_ids) >= 4
        and observed_stage_names[3] == "merge_tiebreak"
    ):
        add_check(
            errors,
            observed_stage_ids[3] == observed_stage_ids[2],
            "merge-tiebreak screener IDs differ from merge-initial",
        )
    if len(observed_stage_ids) >= 3 and len(observed_stage_ids[2]) == 3:
        original_ids = observed_stage_ids[2]
        for stage_name, stage_ids in zip(
            observed_stage_names[3:], observed_stage_ids[3:]
        ):
            if stage_name in {
                "apply_replacements",
                "build_replacement",
                "merge_replacement_initial",
                "merge_replacement_tiebreak",
            }:
                add_check(
                    errors,
                    stage_ids == original_ids,
                    f"{stage_name} changed the frozen screener identities",
                )
    if candidate_state in {
        "awaiting_human_sampling_tiebreak",
        "awaiting_replacement_tiebreak",
        "human_sampling_screen_complete",
    } and len(observed_stage_ids) >= 3 and len(observed_stage_ids[2]) == 3:
        initial_1, initial_2, tiebreak = observed_stage_ids[2]
        add_check(
            errors,
            {
                (row.get("human_sampling_reviewer_1_id") or "").strip()
                for row in candidate_rows
            }
            == {initial_1},
            "candidate reviewer-1 IDs differ from the packet audit chain",
        )
        add_check(
            errors,
            {
                (row.get("human_sampling_reviewer_2_id") or "").strip()
                for row in candidate_rows
            }
            == {initial_2},
            "candidate reviewer-2 IDs differ from the packet audit chain",
        )
        add_check(
            errors,
            all(
                (
                    (row.get("human_sampling_tiebreak_reviewer_id") or "").strip()
                    == tiebreak
                )
                if (row.get("selection_status") or "").strip()
                == "human_screen_tiebreak"
                else not (
                    row.get("human_sampling_tiebreak_reviewer_id") or ""
                ).strip()
                for row in candidate_rows
            ),
            "candidate tiebreak IDs differ from the packet audit chain",
        )
    if stages and isinstance(stages[-1], dict) and isinstance(current, dict):
        latest_artifacts = [
            item
            for direction in ("outputs", "inputs")
            for item in stages[-1].get(direction, [])
            if isinstance(item, dict)
            and item.get("artifact") == "candidate_claims_model_prescreen.csv"
        ]
        add_check(
            errors,
            any(
                item.get("sha256") == current.get("sha256")
                and item.get("rows") == current.get("rows")
                for item in latest_artifacts
            ),
            "latest sampling screen stage does not anchor current candidates",
        )
    return summary


def validate_source_replacement_summary(
    root: Path,
    source_rows: Sequence[Mapping[str, str]],
    deterministic_rows: Sequence[Mapping[str, str]],
    human_rows: Sequence[Mapping[str, str]],
    portable: bool,
    errors: list[str],
    *,
    expanded_text_root: Path | None = None,
    text_correction_state: ReversedCorrectionState | None = None,
) -> dict[str, Any]:
    if text_correction_state is None:
        _correction_header, correction_rows = read_csv(
            root / "frozen_text_corrections.csv"
        )
        _frozen_header, frozen_rows = read_csv(root / "frozen_test_claims.csv")
        if correction_rows and frozen_rows:
            text_correction_state = validate_frozen_text_correction_state(
                root,
                deterministic_rows,
                human_rows,
                frozen_rows,
                errors,
            )
    replacement_deterministic_rows = (
        text_correction_state.deterministic_rows
        if text_correction_state is not None
        else list(deterministic_rows)
    )
    replacement_human_rows = (
        text_correction_state.human_rows
        if text_correction_state is not None
        else list(human_rows)
    )
    path = root / "source_replacement_summary.json"
    try:
        summary = json.loads(read_text_or_error(path, errors))
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read source_replacement_summary.json: {exc}")
        return {}
    add_check(
        errors,
        summary.get("schema_version") == SOURCE_REPLACEMENT_SCHEMA_VERSION,
        "source replacement summary schema mismatch",
    )
    add_check(
        errors,
        summary.get("status") == SOURCE_REPLACEMENT_STATUS,
        "source replacement summary status mismatch",
    )
    add_check(
        errors,
        summary.get("prohibited_use") == SOURCE_REPLACEMENT_PROHIBITED_USE,
        "source replacement summary lacks prohibited-use text",
    )
    batches = summary.get("batches")
    add_check(
        errors,
        isinstance(batches, list) and bool(batches),
        "source replacement summary must contain at least one frozen batch",
    )
    if not isinstance(batches, list) or not batches:
        return summary
    add_check(
        errors,
        len(batches) == 2
        and all(
            isinstance(value, dict)
            and value.get("batch_id") == f"RB-{index:03d}"
            for index, value in enumerate(batches, start=1)
        ),
        "frozen v3 replacement summary must contain ordered RB-001/RB-002",
    )
    add_check(
        errors,
        summary.get("current_batch_id")
        == (
            batches[-1].get("batch_id")
            if isinstance(batches[-1], dict)
            else None
        ),
        "source replacement current_batch_id is stale",
    )
    batch = batches[-1]
    if not isinstance(batch, dict):
        errors.append("source replacement batch is not an object")
        return summary
    add_check(
        errors,
        batch.get("batch_record_sha256")
        == canonical_json_sha256(
            {
                key: value
                for key, value in batch.items()
                if key != "batch_record_sha256"
            }
        ),
        "source replacement batch record hash mismatch",
    )
    outputs = batch.get("outputs")
    parent = batch.get("parent")
    invariants = batch.get("invariants")
    replacements = batch.get("replacements")
    active_slots = batch.get("active_source_slots")
    for field_name, value in (
        ("outputs", outputs),
        ("parent", parent),
        ("invariants", invariants),
    ):
        add_check(
            errors,
            isinstance(value, dict),
            f"source replacement batch lacks {field_name}",
        )
    add_check(
        errors,
        isinstance(replacements, list) and bool(replacements),
        "source replacement batch lacks replacement records",
    )
    add_check(
        errors,
        isinstance(active_slots, list)
        and len(active_slots) == DEFAULT_EXPECTED_SOURCES,
        "source replacement batch lacks 80 active slots",
    )
    if not all(
        isinstance(value, dict) for value in (outputs, parent, invariants)
    ) or not isinstance(replacements, list) or not isinstance(active_slots, list):
        return summary

    current_outputs = {
        "source_sampling_frame_sha256": sha256_file(
            root / "source_sampling_frame.csv"
        ),
        "source_sampling_frame_rows": len(source_rows),
        "candidate_claims_deterministic_sha256": hashlib.sha256(
            serialize_text_correction_csv(
                DETERMINISTIC_CANDIDATE_HEADER,
                replacement_deterministic_rows,
            )
        ).hexdigest(),
        "candidate_claims_deterministic_rows": len(
            replacement_deterministic_rows
        ),
        "candidate_claims_model_prescreen_rows": len(replacement_human_rows),
    }
    add_check(
        errors,
        all(outputs.get(field) == value for field, value in current_outputs.items()),
        "source replacement static output hashes/counts are stale",
    )
    ledger_path = root / "sampling_exclusion_replacement_ledger.csv"
    ledger_header, ledger_rows = read_csv(ledger_path)
    add_check(
        errors,
        ledger_header == LEDGER_HEADER,
        "source replacement ledger schema mismatch",
    )
    for row_index, ledger_row in enumerate(ledger_rows, start=2):
        expected_ledger_hash = canonical_json_sha256(
            {
                field: (ledger_row.get(field) or "")
                for field in LEDGER_HEADER
                if field != "record_sha256"
            }
        )
        add_check(
            errors,
            (ledger_row.get("record_sha256") or "").strip()
            == expected_ledger_hash,
            f"source replacement ledger row {row_index} has an invalid hash",
        )
    add_check(
        errors,
        parent.get("sampling_exclusion_replacement_ledger_sha256")
        == sha256_file(ledger_path)
        and parent.get("sampling_exclusion_replacement_ledger_rows")
        == len(ledger_rows),
        "source replacement parent ledger hash/count mismatch",
    )
    try:
        pool_summary = json.loads(
            read_text_or_error(root / "candidate_pool_summary.json", errors)
        )
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read candidate_pool_summary.json: {exc}")
        pool_summary = {}
    if pool_summary:
        initial_parent = (
            batches[0].get("parent", {})
            if isinstance(batches[0], dict)
            else {}
        )
        add_check(
            errors,
            initial_parent.get("source_sampling_frame_sha256")
            == pool_summary.get("source_sampling_frame_sha256"),
            "replacement parent frame hash differs from frozen candidate pool",
        )
        add_check(
            errors,
            initial_parent.get("candidate_claims_deterministic_sha256")
            == pool_summary.get("candidate_claims_deterministic_sha256"),
            "replacement parent candidate hash differs from frozen candidate pool",
        )
    try:
        screen_summary = json.loads(
            read_text_or_error(root / "sampling_screen_summary.json", errors)
        )
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read sampling_screen_summary.json: {exc}")
        screen_summary = {}
    current_human_anchor = screen_summary.get("current_candidate_state", {})
    add_check(
        errors,
        isinstance(current_human_anchor, dict)
        and current_human_anchor.get("artifact")
        == "candidate_claims_model_prescreen.csv"
        and current_human_anchor.get("rows") == len(human_rows)
        and current_human_anchor.get("sha256")
        == sha256_file(root / "candidate_claims_model_prescreen.csv"),
        "source replacement chain does not anchor current human candidate rows",
    )
    chain_result: dict[str, Any] = {}
    strict_expanded_root = (
        None
        if portable
        else (
            expanded_text_root
            if expanded_text_root is not None
            else resolve_repository_input(
                root, "manuscript/citation_audit/expanded_texts"
            )
        )
    )
    try:
        chain_result = verify_replacement_chain(
            summary,
            {
                "frame_rows": list(source_rows),
                "deterministic_rows": list(replacement_deterministic_rows),
                "human_rows": list(replacement_human_rows),
                "ledger_rows": ledger_rows,
                "screen_summary": screen_summary,
            },
            expected_sources=DEFAULT_EXPECTED_SOURCES,
            text_root=strict_expanded_root,
        )
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"source replacement batch-chain validation failed: {exc}")
    apply_stages = [
        stage
        for stage in screen_summary.get("stages", [])
        if isinstance(stage, dict) and stage.get("stage") == "apply_replacements"
    ]
    add_check(
        errors,
        len(apply_stages) == len(batches),
        "sampling screen apply-stage count differs from replacement batches",
    )
    if len(apply_stages) == len(batches):
        apply_outputs = {
            item.get("artifact"): item
            for item in apply_stages[-1].get("outputs", [])
            if isinstance(item, dict)
        }
        candidate_anchor = apply_outputs.get(
            "candidate_claims_model_prescreen.csv", {}
        )
        add_check(
            errors,
            outputs.get(
                "candidate_claims_model_prescreen_after_apply_sha256"
            )
            == candidate_anchor.get("sha256")
            and outputs.get("candidate_claims_model_prescreen_rows")
            == candidate_anchor.get("rows"),
            "source replacement apply-stage candidate anchor mismatch",
        )
        parent_inputs = {
            item.get("artifact"): item
            for item in apply_stages[-1].get("inputs", [])
            if isinstance(item, dict)
        }
        add_check(
            errors,
            parent_inputs.get(
                "candidate_claims_model_prescreen.csv", {}
            ).get("sha256")
            == parent.get("candidate_claims_model_prescreen_sha256")
            and parent_inputs.get(
                "sampling_screen_summary_parent.json", {}
            ).get("sha256")
            == parent.get("sampling_screen_summary_sha256"),
            "source replacement apply stage does not anchor parent screening",
        )

    ordered_slots = sorted(
        active_slots, key=lambda row: int(row.get("slot", 0))
    )
    add_check(
        errors,
        [int(row.get("slot", 0)) for row in ordered_slots]
        == list(range(1, DEFAULT_EXPECTED_SOURCES + 1)),
        "source replacement active slots are not exactly 1..80",
    )
    active_order = [
        str(row.get("source_key", "")).strip() for row in ordered_slots
    ]
    add_check(
        errors,
        len(set(active_order)) == DEFAULT_EXPECTED_SOURCES
        and "" not in active_order,
        "source replacement active source keys are invalid",
    )
    selected_keys = {
        (row.get("source_key") or "").strip()
        for row in source_rows
        if (row.get("eligibility_status") or "").strip() == "eligible_selected"
    }
    add_check(
        errors,
        set(active_order) == selected_keys,
        "source replacement active slots differ from selected frame",
    )
    deficient_keys = {
        str(row.get("deficient_source_key", "")).strip()
        for row in replacements
        if isinstance(row, dict)
    }
    replacement_keys = {
        str(row.get("replacement_source_key", "")).strip()
        for row in replacements
        if isinstance(row, dict)
    }
    retained_keys = selected_keys - replacement_keys
    cumulative_replacements = [
        row
        for replacement_batch in batches
        if isinstance(replacement_batch, dict)
        for row in replacement_batch.get("replacements", [])
        if isinstance(row, dict)
    ]
    cumulative_deficient_keys = {
        str(row.get("deficient_source_key", "")).strip()
        for row in cumulative_replacements
    }
    current_event_ids = {
        str(row.get("ledger_event_id", "")).strip()
        for row in replacements
        if isinstance(row, dict)
    }
    current_ledger_rows = [
        row
        for row in ledger_rows
        if (row.get("ledger_event_id") or "").strip() in current_event_ids
    ]
    ledger_mappings = {
        (
            (row.get("ledger_event_id") or "").strip(),
            (row.get("source_key") or "").strip(),
            (row.get("replacement_source_key") or "").strip(),
            int((row.get("source_selection_rank") or "0").strip()),
        )
        for row in current_ledger_rows
    }
    summary_mappings = {
        (
            str(row.get("ledger_event_id", "")).strip(),
            str(row.get("deficient_source_key", "")).strip(),
            str(row.get("replacement_source_key", "")).strip(),
            int(row.get("source_slot", 0)),
        )
        for row in replacements
        if isinstance(row, dict)
    }
    add_check(
        errors,
        len(ledger_mappings) == len(current_ledger_rows)
        and len(summary_mappings) == len(replacements)
        and ledger_mappings == summary_mappings,
        "source replacement summary mappings differ from hashed ledger",
    )
    add_check(
        errors,
        len(deficient_keys) == len(replacement_keys)
        and len(retained_keys)
        == DEFAULT_EXPECTED_SOURCES - len(replacement_keys),
        "source replacement batch does not preserve the active source count",
    )
    frame_by_key = {
        (row.get("source_key") or "").strip(): row for row in source_rows
    }
    replacement_records = [
        replacement
        for replacement_batch in batches
        if isinstance(replacement_batch, dict)
        for replacement in replacement_batch.get("replacements", [])
        if isinstance(replacement, dict)
    ]
    for replacement in replacement_records:
        replacement_source = str(
            replacement.get("replacement_source_key", "")
        ).strip()
        frame_row = frame_by_key.get(replacement_source)
        add_check(
            errors,
            frame_row is not None
            and replacement.get("replacement_source_text_sha256")
            == (frame_row.get("full_text_sha256") or "").strip(),
            f"replacement source hash differs from frame for {replacement_source}",
        )
        if replacement_source not in set(active_order):
            continue
        source_deterministic = [
            row
            for row in replacement_deterministic_rows
            if (row.get("source_key") or "").strip() == replacement_source
        ]
        source_human = [
            row
            for row in replacement_human_rows
            if (row.get("source_key") or "").strip() == replacement_source
        ]
        prefix = str(replacement.get("new_id_prefix", ""))
        expected_count = int(replacement.get("new_candidates", -1))
        expected_source_hash = (
            (frame_row.get("full_text_sha256") or "").strip()
            if frame_row is not None
            else ""
        )
        add_check(
            errors,
            len(source_deterministic) == expected_count
            and len(source_human) == expected_count,
            f"active replacement candidate count mismatch for {replacement_source}",
        )
        add_check(
            errors,
            bool(prefix)
            and all(
                (row.get("candidate_claim_id") or "").startswith(prefix)
                and (row.get("source_text_sha256") or "").strip()
                == expected_source_hash
                for row in source_deterministic
            )
            and all(
                (row.get("candidate_claim_id") or "").startswith(prefix)
                and (row.get("source_file_sha256") or "").strip()
                == expected_source_hash
                for row in source_human
            ),
            f"active replacement candidate prefix/source hash mismatch for "
            f"{replacement_source}",
        )

    for replacement_batch in batches:
        if not isinstance(replacement_batch, dict):
            continue
        batch_id = str(replacement_batch.get("batch_id", ""))
        batch_slots = replacement_batch.get("active_source_slots", [])
        batch_replacements = replacement_batch.get("replacements", [])
        batch_invariants = replacement_batch.get("invariants", {})
        if (
            not isinstance(batch_slots, list)
            or not isinstance(batch_replacements, list)
            or not isinstance(batch_invariants, dict)
        ):
            continue
        batch_active_keys = {
            str(row.get("source_key", "")).strip()
            for row in batch_slots
            if isinstance(row, dict)
        }
        batch_replacement_keys = {
            str(row.get("replacement_source_key", "")).strip()
            for row in batch_replacements
            if isinstance(row, dict)
        }
        batch_retained_keys = batch_active_keys - batch_replacement_keys
        batch_retained_frame = [
            row
            for row in source_rows
            if (row.get("source_key") or "").strip() in batch_retained_keys
        ]
        batch_retained_deterministic = [
            row
            for row in replacement_deterministic_rows
            if (row.get("source_key") or "").strip() in batch_retained_keys
        ]
        batch_retained_human = [
            row
            for row in replacement_human_rows
            if (row.get("source_key") or "").strip() in batch_retained_keys
        ]
        batch_invariant_checks = {
            "retained_sources": len(batch_retained_keys),
            "retained_source_frame_rows_sha256": replacement_subset_sha256(
                SOURCE_HEADER, batch_retained_frame
            ),
            "retained_deterministic_rows": len(
                batch_retained_deterministic
            ),
            "retained_deterministic_rows_sha256": replacement_subset_sha256(
                DETERMINISTIC_CANDIDATE_HEADER,
                batch_retained_deterministic,
            ),
            "retained_human_rows": len(batch_retained_human),
            "retained_human_rows_sha256": replacement_subset_sha256(
                CANDIDATE_HEADER, batch_retained_human
            ),
            "candidate_ids_raw_hashes_human_fields_unchanged": True,
        }
        for field, expected in batch_invariant_checks.items():
            add_check(
                errors,
                batch_invariants.get(field) == expected,
                f"{batch_id} retained invariant failed: {field}",
            )
    for deficient in cumulative_deficient_keys:
        frame_row = frame_by_key.get(deficient)
        add_check(
            errors,
            frame_row is not None
            and (frame_row.get("eligibility_status") or "").strip()
            == "excluded"
            and (frame_row.get("exclusion_reason_code") or "").strip()
            == "FEWER_THAN_SIX_ELIGIBLE_CLAIMS",
            f"deficient source {deficient} is not fully excluded",
        )
    for replacement in replacement_keys:
        frame_row = frame_by_key.get(replacement)
        add_check(
            errors,
            frame_row is not None
            and (frame_row.get("eligibility_status") or "").strip()
            == "eligible_selected",
            f"replacement source {replacement} is not selected",
        )

    retained_frame = [
        row for row in source_rows if row["source_key"] in retained_keys
    ]
    retained_deterministic = [
        row
        for row in replacement_deterministic_rows
        if row["source_key"] in retained_keys
    ]
    retained_human = [
        row
        for row in replacement_human_rows
        if row["source_key"] in retained_keys
    ]
    invariant_checks = {
        "retained_sources": len(retained_keys),
        "retained_source_frame_rows_sha256": replacement_subset_sha256(
            SOURCE_HEADER, retained_frame
        ),
        "retained_deterministic_rows": len(retained_deterministic),
        "retained_deterministic_rows_sha256": replacement_subset_sha256(
            DETERMINISTIC_CANDIDATE_HEADER, retained_deterministic
        ),
        "retained_human_rows": len(retained_human),
        "retained_human_rows_sha256": replacement_subset_sha256(
            CANDIDATE_HEADER, retained_human
        ),
        "candidate_ids_raw_hashes_human_fields_unchanged": True,
    }
    for field, expected in invariant_checks.items():
        add_check(
            errors,
            invariants.get(field) == expected,
            f"append-only retained invariant failed: {field}",
        )
    candidate_sources = {
        (row.get("source_key") or "").strip()
        for row in replacement_deterministic_rows
    }
    human_ids = {
        (row.get("candidate_claim_id") or "").strip()
        for row in replacement_human_rows
    }
    deterministic_ids = {
        (row.get("candidate_claim_id") or "").strip()
        for row in replacement_deterministic_rows
    }
    add_check(
        errors,
        candidate_sources == selected_keys
        and deterministic_ids == human_ids
        and not candidate_sources.intersection(deficient_keys),
        "post-replacement candidates do not exactly cover active sources",
    )
    new_rows = [
        row
        for row in replacement_deterministic_rows
        if (row.get("source_key") or "").strip() in replacement_keys
    ]
    add_check(
        errors,
        all(
            (row.get("candidate_claim_id") or "").startswith("H3R-")
            for row in new_rows
        ),
        "replacement candidates do not use the H3R namespace",
    )
    if not portable:
        if strict_expanded_root is None:
            raise AssertionError("strict replacement validation lost expanded texts")
        expanded_root = strict_expanded_root
        ledger_by_id = {
            (row.get("ledger_event_id") or "").strip(): row
            for row in ledger_rows
        }
        final_active_keys = set(active_order)
        for replacement_batch in batches:
            if not isinstance(replacement_batch, dict):
                continue
            batch_id = str(replacement_batch.get("batch_id", ""))
            batch_replacements = [
                row
                for row in replacement_batch.get("replacements", [])
                if isinstance(row, dict)
            ]
            batch_ledger_rows = [
                ledger_by_id.get(
                    str(row.get("ledger_event_id", "")).strip()
                )
                for row in batch_replacements
            ]
            if any(row is None for row in batch_ledger_rows):
                errors.append(f"{batch_id} cannot reconstruct an unknown ledger event")
                continue
            try:
                regenerated = extract_replacement_candidates(
                    [
                        row
                        for row in batch_ledger_rows
                        if row is not None
                    ],
                    frame_by_key,
                    expanded_root,
                )
            except (KeyError, OSError, TypeError, ValueError) as exc:
                errors.append(
                    f"{batch_id} replacement full-text reconstruction failed: {exc}"
                )
                continue
            for replacement in batch_replacements:
                replacement_source = str(
                    replacement.get("replacement_source_key", "")
                ).strip()
                regenerated_source_rows = [
                    row
                    for row in regenerated
                    if (row.get("source_key") or "").strip()
                    == replacement_source
                ]
                prefix = str(replacement.get("new_id_prefix", ""))
                add_check(
                    errors,
                    len(regenerated_source_rows)
                    == int(replacement.get("new_candidates", -1))
                    and all(
                        (row.get("candidate_claim_id") or "").startswith(prefix)
                        for row in regenerated_source_rows
                    ),
                    f"{batch_id} regenerated replacement metadata mismatch for "
                    f"{replacement_source}",
                )
                if replacement_source not in final_active_keys:
                    continue
                actual_source_rows = [
                    row
                    for row in replacement_deterministic_rows
                    if (row.get("source_key") or "").strip()
                    == replacement_source
                ]
                add_check(
                    errors,
                    replacement_subset_sha256(
                        DETERMINISTIC_CANDIDATE_HEADER,
                        actual_source_rows,
                    )
                    == replacement_subset_sha256(
                        DETERMINISTIC_CANDIDATE_HEADER,
                        regenerated_source_rows,
                    ),
                    f"{batch_id} active replacement candidates do not reproduce "
                    f"from expanded text for {replacement_source}",
                )
    return {
        "active_source_order": active_order,
        "batches": len(batches),
        "deficient_source_keys": sorted(cumulative_deficient_keys),
        "replacement_source_keys": chain_result.get(
            "active_replacement_source_keys", sorted(replacement_keys)
        ),
        "retained_source_keys": sorted(retained_keys),
        "verification": (
            "frozen internal chain/hash verification; no full-text regeneration"
            if portable
            else "frozen internal chain/hash verification plus per-batch "
            "full-text regeneration"
        ),
        "summary": summary,
    }


def validate_source_frame(
    rows: Sequence[Mapping[str, str]],
    errors: list[str],
    development_source_keys: set[str],
    development_normalized_titles: set[str],
) -> dict[str, Mapping[str, str]]:
    duplicates = duplicate_values(rows, "source_key")
    add_check(errors, not duplicates, f"duplicate source keys in frame: {duplicates[:5]}")
    by_key: dict[str, Mapping[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        source_key = (row.get("source_key") or "").strip()
        add_check(errors, bool(source_key), f"source frame row {index} has empty source_key")
        if source_key:
            by_key[source_key] = row
        normalized = normalize_title((row.get("title") or "").strip())
        add_check(
            errors,
            bool(normalized),
            f"source frame row {index} has an empty normalized title",
        )
        eligibility = (row.get("eligibility_status") or "").strip()
        if eligibility == "excluded":
            add_check(
                errors,
                bool((row.get("exclusion_reason_code") or "").strip()),
                f"excluded source row {index} lacks a reason code",
            )
        matches_development = (
            source_key in development_source_keys
            or normalized in development_normalized_titles
        )
        if matches_development:
            add_check(
                errors,
                eligibility == "excluded",
                f"development source key/title is not excluded at source row {index}",
            )
            add_check(
                errors,
                (row.get("exclusion_reason_code") or "").strip()
                in {"DEV_SOURCE_OR_COMPANION", "DUPLICATE_REPORT"},
                f"development source row {index} lacks the correct exclusion reason",
            )
            add_check(
                errors,
                (row.get("development_source_flag") or "").strip().lower()
                in {"true", "1", "yes"},
                f"development source row {index} is not flagged",
            )
        source_hash = (row.get("full_text_sha256") or "").strip()
        hash_required = eligibility in {"eligible_selected", "eligible_reserve"}
        add_check(
            errors,
            (not hash_required and not source_hash)
            or bool(SHA256_RE.fullmatch(source_hash)),
            f"source row {index} has a missing or invalid full-text SHA-256",
        )
    return by_key


def validate_source_selection_order(
    rows: Sequence[Mapping[str, str]],
    test_source_keys: set[str],
    development_source_keys: set[str],
    development_normalized_titles: set[str],
    sampling_seed: int,
    errors: list[str],
    active_source_order: Sequence[str] | None = None,
) -> list[str]:
    eligible_statuses = {"eligible_selected", "eligible_reserve"}
    eligible_by_stratum: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    eligible_title_keys: dict[str, set[str]] = defaultdict(set)
    selected_keys: set[str] = set()
    for index, row in enumerate(rows, start=2):
        status = (row.get("eligibility_status") or "").strip()
        source_key = (row.get("source_key") or "").strip()
        if status == "eligible_selected":
            selected_keys.add(source_key)
        administratively_replaced = (
            status == "excluded"
            and (row.get("exclusion_reason_code") or "").strip()
            == "FEWER_THAN_SIX_ELIGIBLE_CLAIMS"
        )
        if status not in eligible_statuses and not administratively_replaced:
            continue
        normalized = normalize_title((row.get("title") or "").strip())
        eligible_title_keys[normalized].add(source_key)
        add_check(
            errors,
            source_key not in development_source_keys,
            f"development source {source_key} is marked rankable",
        )
        add_check(
            errors,
            normalized not in development_normalized_titles,
            f"development title alias for {source_key} is marked rankable",
        )
        add_check(
            errors,
            (row.get("development_source_flag") or "").strip().lower()
            in {"false", "0", "no"},
            f"rankable source {source_key} has a development-source flag",
        )
        stratum = (row.get("sampling_stratum") or "").strip()
        expected_stratum = (
            (row.get("venue_family") or "").strip()
            + "::"
            + (row.get("publication_status") or "").strip()
        )
        add_check(
            errors,
            bool(stratum) and stratum == expected_stratum,
            f"eligible source row {index} has an invalid sampling stratum",
        )
        try:
            eligible_count = int((row.get("eligible_candidate_count") or "").strip())
        except ValueError:
            eligible_count = -1
        add_check(
            errors,
            eligible_count >= 6,
            f"eligible source row {index} has fewer than six eligible candidates",
        )
        eligible_by_stratum[stratum].append(row)

    duplicate_titles = {
        title: sorted(keys)
        for title, keys in eligible_title_keys.items()
        if title and len(keys) > 1
    }
    add_check(
        errors,
        not duplicate_titles,
        f"eligible candidate sources have duplicate normalized titles: "
        f"{list(duplicate_titles.items())[:5]}",
    )

    ranked_by_stratum: dict[str, list[Mapping[str, str]]] = {}
    for stratum, stratum_rows in eligible_by_stratum.items():
        ranked = sorted(
            stratum_rows,
            key=lambda row: stable_digest(
                sampling_seed, "source", (row.get("source_key") or "").strip()
            ),
        )
        ranked_by_stratum[stratum] = ranked
        for expected_rank, row in enumerate(ranked, start=1):
            try:
                observed_rank = int(
                    (row.get("deterministic_source_rank") or "").strip()
                )
            except ValueError:
                observed_rank = -1
            add_check(
                errors,
                observed_rank == expected_rank,
                "deterministic source rank does not match the frozen seed",
            )

    round_robin: list[str] = []
    pass_index = 0
    ordered_strata = sorted(ranked_by_stratum)
    while len(round_robin) < DEFAULT_EXPECTED_SOURCES:
        added = False
        for stratum in ordered_strata:
            ranked = ranked_by_stratum[stratum]
            if pass_index < len(ranked):
                round_robin.append(
                    (ranked[pass_index].get("source_key") or "").strip()
                )
                added = True
                if len(round_robin) == DEFAULT_EXPECTED_SOURCES:
                    break
        if not added:
            break
        pass_index += 1
    add_check(
        errors,
        len(round_robin) >= DEFAULT_EXPECTED_SOURCES,
        "source frame does not contain 80 eligible sources",
    )
    initial_selected_order = round_robin[:DEFAULT_EXPECTED_SOURCES]
    expected_selected = (
        set(active_source_order)
        if active_source_order is not None
        else set(initial_selected_order)
    )
    add_check(
        errors,
        selected_keys == expected_selected,
        "eligible_selected sources do not match the active source selection",
    )
    add_check(
        errors,
        selected_keys == test_source_keys,
        "eligible_selected sources do not exactly match the expected selected set",
    )
    if active_source_order is not None:
        add_check(
            errors,
            len(active_source_order) == DEFAULT_EXPECTED_SOURCES
            and len(set(active_source_order)) == DEFAULT_EXPECTED_SOURCES,
            "replacement active source order is not 80 unique sources",
        )
        return list(active_source_order)
    return initial_selected_order


def validate_candidate_selection_order(
    rows: Sequence[Mapping[str, str]],
    sampling_seed: int,
    errors: list[str],
) -> None:
    eligible_by_group: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(
        list
    )
    for row in rows:
        eligibility = (row.get("human_sampling_eligibility") or "").strip()
        if eligibility not in {"eligible_c2", "eligible_c5"}:
            continue
        expected_stratum = {
            "eligible_c2": "c2_decisive",
            "eligible_c5": "c5_decisive",
        }[eligibility]
        add_check(
            errors,
            (row.get("human_sampling_stratum") or "").strip() == expected_stratum,
            "eligible candidate has an inconsistent human sampling stratum",
        )
        group = (
            (row.get("source_key") or "").strip(),
            eligibility,
        )
        eligible_by_group[group].append(row)
    for group, group_rows in eligible_by_group.items():
        ranked = sorted(
            group_rows,
            key=lambda row: stable_digest(
                sampling_seed,
                "claim",
                (row.get("candidate_claim_id") or "").strip(),
            ),
        )
        selected_count = sum(
            (row.get("selection_status") or "").strip() == "selected"
            for row in ranked
        )
        expected_selected = {
            (row.get("candidate_claim_id") or "").strip()
            for row in ranked[:selected_count]
        }
        observed_selected = {
            (row.get("candidate_claim_id") or "").strip()
            for row in ranked
            if (row.get("selection_status") or "").strip() == "selected"
        }
        add_check(
            errors,
            observed_selected == expected_selected,
            f"selected candidates are not the deterministic prefix for {group}",
        )
        for expected_rank, row in enumerate(ranked, start=1):
            raw_rank = (row.get("deterministic_claim_rank") or "").strip()
            if not raw_rank:
                continue
            try:
                observed_rank = int(raw_rank)
            except ValueError:
                observed_rank = -1
            add_check(
                errors,
                observed_rank == expected_rank,
                f"candidate rank does not match the frozen seed for {group}",
            )


def validate_prepared_candidate_pool(
    root: Path,
    loaded: Mapping[str, Sequence[Mapping[str, str]]],
    config: Mapping[str, Any],
    development_source_keys: set[str],
    development_normalized_titles: set[str],
    errors: list[str],
    portable: bool,
    external_input_skips: list[dict[str, str]],
    map_path_override: Path | None = None,
) -> dict[str, Any]:
    source_rows = loaded["source_sampling_frame.csv"]
    deterministic_rows = loaded["candidate_claims_deterministic.csv"]
    model_rows = loaded["candidate_claims_model_prescreen.csv"]
    add_check(
        errors,
        bool(source_rows) == bool(deterministic_rows),
        "source frame and deterministic candidates must be populated together",
    )
    if not source_rows:
        add_check(
            errors,
            not model_rows,
            "model prescreen cannot precede the deterministic candidate pool",
        )
        return {
            "state": "prepared_for_source-frame_population",
            "source_frame_rows": 0,
            "eligible_sources": 0,
            "selected_sources": 0,
            "deterministic_candidates": 0,
            "model_prescreen_rows": 0,
        }

    source_frame = validate_source_frame(
        source_rows,
        errors,
        development_source_keys,
        development_normalized_titles,
    )
    replacement_info = validate_source_replacement_summary(
        root,
        source_rows,
        deterministic_rows,
        model_rows,
        portable,
        errors,
    )
    active_source_order = replacement_info.get("active_source_order")
    selected_keys = {
        (row.get("source_key") or "").strip()
        for row in source_rows
        if (row.get("eligibility_status") or "").strip() == "eligible_selected"
    }
    selected_order = validate_source_selection_order(
        source_rows,
        selected_keys,
        development_source_keys,
        development_normalized_titles,
        int(config.get("sampling_source_seed", 2026071501)),
        errors,
        active_source_order=active_source_order,
    )
    expected_selection_rank = {
        source_key: rank for rank, source_key in enumerate(selected_order, start=1)
    }
    replacement_prefix_by_source: dict[str, str] = {}
    replacement_batches = (
        replacement_info.get("summary", {}).get("batches", [])
        if replacement_info
        else []
    )
    if replacement_batches:
        for replacement_batch in replacement_batches:
            if not isinstance(replacement_batch, dict):
                continue
            for replacement in replacement_batch.get("replacements", []):
                if isinstance(replacement, dict):
                    replacement_prefix_by_source[
                        str(
                            replacement.get(
                                "replacement_source_key", ""
                            )
                        ).strip()
                    ] = str(replacement.get("new_id_prefix", ""))
    add_check(
        errors,
        len(source_rows) == int(config.get("candidate_pool_map_row_count", -1)),
        "source frame row count does not match the frozen Map snapshot",
    )
    eligible_count = sum(
        (row.get("eligibility_status") or "").strip()
        in {"eligible_selected", "eligible_reserve"}
        for row in source_rows
    )
    expected_eligible_count = int(
        config.get("candidate_pool_eligible_source_count", -1)
    ) - len(replacement_info.get("deficient_source_keys", []))
    add_check(
        errors,
        eligible_count == expected_eligible_count,
        "eligible source count does not match stable replacement state",
    )
    add_check(
        errors,
        len(selected_keys)
        == int(config.get("candidate_pool_selected_source_count", -1)),
        "selected source count does not match study_config.json",
    )
    configured_map_hash = str(config.get("candidate_pool_map_sha256", ""))
    add_check(
        errors,
        bool(SHA256_RE.fullmatch(configured_map_hash)),
        "study config candidate-pool Map hash is not a lowercase SHA-256",
    )
    add_check(
        errors,
        config.get("candidate_pool_map_path") == MAP_RELATIVE_PATH,
        "study config candidate-pool Map path is not the frozen v3 path",
    )
    map_path = map_path_override or resolve_repository_input(
        root, MAP_RELATIVE_PATH
    )
    map_by_key: dict[str, dict[str, str]] = {}
    if map_path.is_file():
        try:
            _map_header, map_rows = read_csv(map_path)
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read existing Map B input: {exc}")
        else:
            map_by_key = {
                (row.get("cite_key") or "").strip(): row for row in map_rows
            }
            add_check(
                errors,
                len(map_rows)
                == int(config.get("candidate_pool_map_row_count", -1)),
                "actual Map B row count differs from study_config.json",
            )
            add_check(
                errors,
                set(source_frame) == set(map_by_key),
                "source frame keys do not exactly cover the frozen Map B snapshot",
            )
            add_check(
                errors,
                sha256_file(map_path) == configured_map_hash,
                "actual Map B hash differs from study_config.json",
            )
    elif portable:
        record_external_skip(
            external_input_skips,
            MAP_RELATIVE_PATH,
            "external input absent in portable reviewer package",
            "frozen study_config Map hash/row metadata, package source-frame "
            "structure, candidate linkage, summary hashes, and MANIFEST",
            configured_map_hash,
        )
    else:
        errors.append(f"required Map B input is missing: {MAP_RELATIVE_PATH}")

    snapshot_id = str(config.get("candidate_pool_corpus_snapshot_id", ""))
    frame_frozen_utc = str(config.get("candidate_pool_frame_frozen_utc", ""))
    expanded_text_root = resolve_repository_input(
        root, "manuscript/citation_audit/expanded_texts"
    )
    text_hashes: dict[str, str] = {}
    if portable:
        record_external_skip(
            external_input_skips,
            EXPANDED_TEXT_RELATIVE_PATH,
            "portable mode intentionally does not read third-party expanded texts",
            "lowercase frame SHA-256 inventory, candidate-to-frame hash linkage, "
            "recomputed corpus snapshot, summary hashes, and MANIFEST",
            str(config.get("candidate_pool_expanded_text_snapshot_sha256", "")),
        )
    for index, row in enumerate(source_rows, start=2):
        source_key = (row.get("source_key") or "").strip()
        map_row = map_by_key.get(source_key)
        if map_row is not None:
            expected_map_fields = {
                "title": (map_row.get("title") or "").strip(),
                "year": (map_row.get("year") or "").strip(),
                "venue_family": (map_row.get("source_or_venue") or "").strip(),
                "publication_status": map_publication_status(map_row),
                "stable_url_or_doi": (map_row.get("url") or "").strip(),
            }
            for field, expected_value in expected_map_fields.items():
                add_check(
                    errors,
                    (row.get(field) or "").strip() == expected_value,
                    f"source frame row {index} mis-maps Map B field {field}",
                )
        observed_text_hash = (row.get("full_text_sha256") or "").strip()
        text_path = expanded_text_root / f"{source_key}.txt"
        if observed_text_hash:
            if not portable:
                add_check(
                    errors,
                    text_path.is_file()
                    and sha256_file(text_path) == observed_text_hash,
                    f"source frame row {index} has a stale expanded-text hash",
                )
            text_hashes[source_key] = observed_text_hash
        add_check(
            errors,
            (row.get("corpus_snapshot_id") or "").strip() == snapshot_id,
            f"source frame row {index} has the wrong corpus snapshot",
        )
        add_check(
            errors,
            (row.get("frame_frozen_utc") or "").strip() == frame_frozen_utc,
            f"source frame row {index} has the wrong frame freeze time",
        )
    recomputed_snapshot_id, recomputed_snapshot_sha256 = expanded_text_snapshot(
        str(config.get("candidate_pool_map_sha256", "")), text_hashes
    )
    add_check(
        errors,
        recomputed_snapshot_id == snapshot_id
        and recomputed_snapshot_sha256
        == config.get("candidate_pool_expanded_text_snapshot_sha256"),
        "expanded-text corpus snapshot does not match study_config.json",
    )
    add_check(
        errors,
        bool(SHA256_RE.fullmatch(recomputed_snapshot_sha256)),
        "recomputed expanded-text snapshot is not a lowercase SHA-256",
    )
    add_check(
        errors,
        len(text_hashes)
        == int(config.get("candidate_pool_expanded_text_file_count", -1)),
        "expanded-text file count does not match study_config.json",
    )

    duplicate_ids = duplicate_values(deterministic_rows, "candidate_claim_id")
    add_check(
        errors,
        not duplicate_ids,
        f"deterministic candidate IDs are duplicated: {duplicate_ids[:5]}",
    )
    candidates_by_source: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    candidate_title_keys: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(deterministic_rows, start=2):
        candidate_id = (row.get("candidate_claim_id") or "").strip()
        source_key = (row.get("source_key") or "").strip()
        frame_row = source_frame.get(source_key)
        add_check(
            errors,
            frame_row is not None and source_key in selected_keys,
            f"deterministic candidate row {index} is not from a selected source",
        )
        if frame_row is None:
            continue
        normalized = normalize_title((row.get("source_title") or "").strip())
        candidate_title_keys[normalized].add(source_key)
        add_check(
            errors,
            source_key not in development_source_keys
            and normalized not in development_normalized_titles,
            f"deterministic candidate row {index} leaks a development source",
        )
        add_check(
            errors,
            (row.get("source_title") or "").strip()
            == (frame_row.get("title") or "").strip(),
            f"deterministic candidate row {index} has a source-title mismatch",
        )
        add_check(
            errors,
            (row.get("source_url_or_doi") or "").strip()
            == (frame_row.get("stable_url_or_doi") or "").strip(),
            f"deterministic candidate row {index} has a source-URL mismatch",
        )
        add_check(
            errors,
            (row.get("source_text_sha256") or "").strip()
            == (frame_row.get("full_text_sha256") or "").strip(),
            f"deterministic candidate row {index} has a source-hash mismatch",
        )
        add_check(
            errors,
            bool(
                SHA256_RE.fullmatch(
                    (row.get("source_text_sha256") or "").strip()
                )
            ),
            f"deterministic candidate row {index} has an invalid source hash",
        )
        add_check(
            errors,
            (row.get("corpus_snapshot_id") or "").strip() == snapshot_id,
            f"deterministic candidate row {index} has a snapshot mismatch",
        )
        add_check(
            errors,
            (row.get("model_free_status") or "").strip() == MODEL_FREE_STATUS,
            f"deterministic candidate row {index} is not marked model-free",
        )
        add_check(
            errors,
            (row.get("extraction_method") or "").strip()
            == "deterministic_comparative_cue_v1_model_free",
            f"deterministic candidate row {index} has an unknown extraction method",
        )
        try:
            source_selection_rank = int(
                (row.get("source_selection_rank") or "").strip()
            )
            source_candidate_rank = int(
                (row.get("source_candidate_rank") or "").strip()
            )
            pdf_page = int((row.get("pdf_page") or "").strip())
            score = int((row.get("cue_score") or "").strip())
        except ValueError:
            source_selection_rank = source_candidate_rank = pdf_page = score = -1
        add_check(
            errors,
            source_selection_rank == expected_selection_rank.get(source_key),
            f"deterministic candidate row {index} has a bad source selection rank",
        )
        expected_candidate_id = (
            f"{replacement_prefix_by_source[source_key]}"
            f"{source_candidate_rank:02d}"
            if source_key in replacement_prefix_by_source
            else f"H3-{source_selection_rank:03d}-{source_candidate_rank:02d}"
        )
        add_check(
            errors,
            candidate_id == expected_candidate_id,
            f"deterministic candidate row {index} has a noncanonical ID",
        )
        add_check(
            errors,
            1 <= source_candidate_rank <= 20 and pdf_page >= 1 and score >= 2,
            f"deterministic candidate row {index} has invalid ranks/page/cue score",
        )
        add_check(
            errors,
            bool((row.get("source_section") or "").strip())
            and 50 <= len((row.get("exact_quote") or "").strip()) <= 800,
            f"deterministic candidate row {index} lacks exact source evidence",
        )
        add_check(
            errors,
            canonical_candidate_hash(row)
            == (row.get("candidate_record_sha256") or "").strip(),
            f"deterministic candidate row {index} has a bad record hash",
        )
        candidates_by_source[source_key].append(row)

    duplicate_candidate_titles = {
        title: sorted(keys)
        for title, keys in candidate_title_keys.items()
        if title and len(keys) > 1
    }
    add_check(
        errors,
        not duplicate_candidate_titles,
        "deterministic candidate sources have duplicate normalized titles: "
        f"{list(duplicate_candidate_titles.items())[:5]}",
    )
    add_check(
        errors,
        set(candidates_by_source) == selected_keys,
        "deterministic candidates do not cover every selected source exactly",
    )
    for source_key, rows in candidates_by_source.items():
        observed_ranks = sorted(
            int((row.get("source_candidate_rank") or "0").strip()) for row in rows
        )
        frame_count = int(
            (source_frame[source_key].get("eligible_candidate_count") or "0").strip()
        )
        expected_count = min(frame_count, 20)
        add_check(
            errors,
            observed_ranks == list(range(1, expected_count + 1)),
            f"candidate ranks/count are incomplete for source {source_key}",
        )
    expected_candidate_count = (
        replacement_info.get("summary", {})
        .get("batches", [{}])[-1]
        .get("outputs", {})
        .get("candidate_claims_deterministic_rows", -1)
    )
    add_check(
        errors,
        len(deterministic_rows) == expected_candidate_count,
        "deterministic candidate count does not match replacement summary",
    )

    candidate_screen_state = "not_initialized"
    if model_rows:
        candidate_screen_state = validate_model_prescreen(
            model_rows, errors, int(config.get("prescreen_seed", 2026071505))
        )
        deterministic_by_id = {
            (row.get("candidate_claim_id") or "").strip(): row
            for row in deterministic_rows
        }
        model_ids = {
            (row.get("candidate_claim_id") or "").strip() for row in model_rows
        }
        add_check(
            errors,
            model_ids == set(deterministic_by_id),
            "model prescreen does not exactly cover deterministic candidates",
        )
        for index, row in enumerate(model_rows, start=2):
            candidate_id = (row.get("candidate_claim_id") or "").strip()
            deterministic = deterministic_by_id.get(candidate_id)
            if deterministic is None:
                continue
            expected_fields = {
                "source_key": deterministic["source_key"],
                "claim_text": deterministic["exact_quote"],
                "context_before": deterministic["context_before"],
                "context_after": deterministic["context_after"],
                "source_section": deterministic["source_section"],
                "source_locator": f"PDF page {deterministic['pdf_page']}",
                "source_url_or_doi": deterministic["source_url_or_doi"],
                "source_evidence_excerpt": deterministic["exact_quote"],
                "source_file_sha256": deterministic["source_text_sha256"],
                "candidate_extraction_method": deterministic["extraction_method"],
            }
            for field, expected_value in expected_fields.items():
                add_check(
                    errors,
                    (row.get(field) or "").strip()
                    == (expected_value or "").strip(),
                    f"model prescreen row {index} changed deterministic field {field}",
                )
        validate_sampling_screen_summary(
            root, model_rows, candidate_screen_state, errors
        )
    else:
        errors.append(
            "prepared package must initialize the model-free sampling candidate file"
        )

    summary_path = root / "candidate_pool_summary.json"
    try:
        summary = json.loads(read_text_or_error(summary_path, errors))
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read candidate_pool_summary.json: {exc}")
        summary = {}
    if summary:
        replacement_parent = (
            replacement_info.get("summary", {})
            .get("batches", [{}])[-1]
            .get("parent", {})
        )
        replacement_batches_for_pool = (
            replacement_info.get("summary", {}).get("batches", [])
        )
        if replacement_batches_for_pool:
            replacement_parent = replacement_batches_for_pool[0].get(
                "parent", {}
            )
        expected_summary = {
            "status": "MODEL_FREE_POOL_AWAITING_HUMAN_SAMPLING_SCREEN",
            "custom_source_quotas_used": False,
            "map_rows": len(source_rows),
            "eligible_sources": int(
                config.get("candidate_pool_eligible_source_count", -1)
            ),
            "selected_sources": int(
                config.get("candidate_pool_selected_source_count", -1)
            ),
            "deterministic_candidates": int(
                config.get("candidate_pool_deterministic_candidate_count", -1)
            ),
            "corpus_snapshot_id": snapshot_id,
            "source_sampling_frame_sha256": replacement_parent.get(
                "source_sampling_frame_sha256"
            ),
            "candidate_claims_deterministic_sha256": replacement_parent.get(
                "candidate_claims_deterministic_sha256"
            ),
            "expanded_text_files": len(text_hashes),
            "expanded_text_snapshot_sha256": recomputed_snapshot_sha256,
            "map_sha256": configured_map_hash,
        }
        for field, expected_value in expected_summary.items():
            add_check(
                errors,
                summary.get(field) == expected_value,
                f"candidate pool summary field {field} is inconsistent",
            )

    return {
        "state": candidate_screen_state,
        "source_frame_rows": len(source_rows),
        "eligible_sources": eligible_count,
        "selected_sources": len(selected_keys),
        "deterministic_candidates": len(deterministic_rows),
        "model_prescreen_rows": len(model_rows),
    }


def validate_calibration_workflow(
    root: Path,
    loaded: Mapping[str, Sequence[Mapping[str, str]]],
    config: Mapping[str, Any],
    public_roster_path: Path,
    summary_path: Path,
    errors: list[str],
) -> dict[str, Any]:
    try:
        items = read_calibration_items(root / "calibration_items.csv")
        key = read_calibration_key(root / "calibration_answer_key.csv", items)
    except (OSError, ValueError) as exc:
        errors.append(f"invalid frozen calibration materials: {exc}")
        return {
            "calibration_release_eligible": False,
            "calibration_response_rows": len(
                loaded.get("calibration_responses.csv", [])
            ),
        }

    try:
        assert_calibration_test_disjoint(
            items, root / "frozen_test_claims.csv"
        )
    except (OSError, ValueError) as exc:
        errors.append(str(exc))

    materials_path = root / "calibration_materials.md"
    materials = read_text_or_error(materials_path, errors)
    add_check(
        errors,
        materials == render_calibration_materials(items),
        "calibration materials are not the canonical answer-free rendering",
    )
    for item in items:
        item_id = item["calibration_item_id"]
        source_key = item["calibration_source_key"]
        add_check(
            errors,
            item_id in materials and source_key in materials,
            f"calibration materials omit {item_id} or its source key",
        )
        add_check(
            errors,
            item_id.startswith("CAL-V3-I")
            and source_key.startswith("CAL-INSTRUCTOR-S"),
            f"calibration item {item_id} lacks the instructor namespace",
        )
        add_check(
            errors,
            item["construction_status"] == CALIBRATION_CONSTRUCTION_STATUS,
            f"calibration item {item_id} is not marked instructor-constructed",
        )
    add_check(
        errors,
        CALIBRATION_ANSWER_KEY_STATUS not in materials,
        "participant-facing calibration materials expose answer-key status/content",
    )

    key_by_item = {row["calibration_item_id"]: row for row in key}
    evidence_distribution = Counter(
        row["evidence_support_label"] for row in key
    )
    comparability_distribution = Counter(
        row["comparability_label"] for row in key
    )
    expected_evidence = Counter(
        {
            "supported_as_written": 3,
            "supported_after_narrowing": 3,
            "contradicted": 2,
            "insufficient_source_evidence": 2,
        }
    )
    expected_comparability = Counter(
        {
            "same_estimand": 3,
            "comparable_with_declared_scope": 2,
            "different_estimand": 1,
            "missing_comparison_assumption": 2,
            "not_a_comparability_claim": 2,
        }
    )
    add_check(
        errors,
        evidence_distribution == expected_evidence,
        f"calibration evidence-label distribution changed: "
        f"{dict(evidence_distribution)}",
    )
    add_check(
        errors,
        comparability_distribution == expected_comparability,
        f"calibration comparability-label distribution changed: "
        f"{dict(comparability_distribution)}",
    )
    tags = "|".join(row["decisive_case_tags"] for row in key)
    for required_tag in (
        "C2_decisive",
        "C5_decisive",
        "causal_overclaim",
        "missing_control",
        "not_comparability",
        "ordinary_controls",
        "security_controls",
        "efficiency_controls",
    ):
        add_check(
            errors,
            required_tag in tags,
            f"calibration key lacks required case tag {required_tag}",
        )

    for role, arm in (
        ("auditor", "A"),
        ("auditor", "B"),
        ("auditor", "C"),
        ("auditor", "D"),
        ("gold_expert", ""),
        ("adjudicator_1", ""),
        ("adjudicator_2", ""),
    ):
        try:
            calibration_instructions_for(role, arm)
        except ValueError as exc:
            errors.append(f"calibration role-instruction isolation failed: {exc}")

    test_claim_rows = loaded.get("frozen_test_claims.csv", [])
    test_claim_ids = {
        (row.get("claim_id") or "").strip() for row in test_claim_rows
    } - {""}
    test_source_keys = {
        (row.get("source_key") or "").strip() for row in test_claim_rows
    } - {""}
    calibration_text = "\n".join(
        value
        for row in items
        for value in row.values()
    )
    for identifier in sorted(test_claim_ids | test_source_keys):
        add_check(
            errors,
            identifier not in calibration_text and identifier not in materials,
            f"frozen test identifier appears in calibration content: {identifier}",
        )
    ledger_rows = loaded.get("calibration_responses.csv", [])
    for index, row in enumerate(ledger_rows, start=2):
        item_id = (row.get("calibration_item_id") or "").strip()
        source_key = (row.get("calibration_source_key") or "").strip()
        add_check(
            errors,
            item_id in key_by_item,
            f"calibration ledger row {index} has an unknown item",
        )
        add_check(
            errors,
            source_key
            == (key_by_item.get(item_id, {}).get("calibration_source_key") or ""),
            f"calibration ledger row {index} has an unknown source key",
        )
        add_check(
            errors,
            item_id not in test_claim_ids and source_key not in test_source_keys,
            f"calibration ledger row {index} reuses a test identifier",
        )

    fixed_config = {
        "calibration_version": CALIBRATION_VERSION,
        "calibration_item_count": CALIBRATION_ITEM_COUNT,
        "calibration_initial_response_rows": 0,
        "calibration_initial_status": "AWAITING_FROZEN_CALIBRATION_RESPONSES",
        "calibration_evidence_minimum_correct": (
            MINIMUM_CORRECT_PER_DIMENSION
        ),
        "calibration_comparability_minimum_correct": (
            MINIMUM_CORRECT_PER_DIMENSION
        ),
        "calibration_maximum_retraining_attempts": (
            MAXIMUM_RETRAINING_ATTEMPTS
        ),
        "calibration_set_sha256": calibration_set_sha256(items),
        "calibration_items_sha256": sha256_file(
            root / "calibration_items.csv"
        ),
        "calibration_answer_key_sha256": sha256_file(
            root / "calibration_answer_key.csv"
        ),
        "calibration_materials_sha256": sha256_file(materials_path),
        "calibration_answer_key_status": CALIBRATION_ANSWER_KEY_STATUS,
        "formal_test_packet_gate": (
            "ALL_29_ITEMIZED_CALIBRATION_PASSES_REQUIRED"
        ),
        "prior_unitemized_calibration_passes_recognized": False,
    }
    for field, expected in fixed_config.items():
        add_check(
            errors,
            config.get(field) == expected,
            f"study config calibration field {field} is inconsistent",
        )

    if not public_roster_path.exists():
        errors.append(
            f"public participant metadata file does not exist: {public_roster_path}"
        )
        public_rows: list[dict[str, str]] = []
        public_sha256 = ""
    else:
        public_header, public_rows = read_csv(public_roster_path)
        add_check(
            errors,
            public_header == PUBLIC_PARTICIPANT_HEADER,
            "public participant metadata uses the wrong non-PII schema",
        )
        public_sha256 = sha256_file(public_roster_path)
    try:
        calibration_summary = json.loads(
            summary_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read calibration summary: {exc}")
        calibration_summary = {}

    release_eligible = False
    if calibration_summary:
        release_eligible, calibration_errors = validate_calibration_state(
            items=items,
            key=key,
            ledger_rows=ledger_rows,
            public_rows=public_rows,
            summary=calibration_summary,
            response_sha256=sha256_file(root / "calibration_responses.csv"),
            public_sha256=public_sha256,
            items_sha256=sha256_file(root / "calibration_items.csv"),
            key_sha256=sha256_file(root / "calibration_answer_key.csv"),
            materials_sha256=sha256_file(materials_path),
        )
        errors.extend(calibration_errors)
    return {
        "calibration_state_validation": "FULL_NON_PII_LEDGER_RECOMPUTATION",
        "calibration_release_eligible": release_eligible,
        "calibration_response_rows": len(ledger_rows),
        "calibration_summary_status": calibration_summary.get("status"),
        "calibration_label_distribution": {
            "evidence_support": dict(sorted(evidence_distribution.items())),
            "comparability": dict(sorted(comparability_distribution.items())),
        },
    }


def validate_participant_metadata(
    path: Path, errors: list[str], strict: bool
) -> tuple[list[dict[str, str]], dict[str, set[str]]]:
    if not path.exists():
        errors.append(f"participant metadata file does not exist: {path}")
        return [], {}
    header, rows = read_csv(path)
    add_check(
        errors,
        header == PRIVATE_PARTICIPANT_HEADER,
        "participant metadata must use the frozen private-template schema",
    )
    duplicates = duplicate_values(rows, "participant_id")
    add_check(errors, not duplicates, f"participant IDs are reused: {duplicates[:5]}")
    roles: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(rows, start=2):
        participant_id = (row.get("participant_id") or "").strip()
        role = (row.get("role") or "").strip().lower()
        add_check(errors, bool(participant_id), f"participant row {index} has an empty ID")
        add_check(errors, bool(role), f"participant row {index} has an empty role")
        if participant_id and role:
            roles[role].add(participant_id)

    if strict:
        add_check(
            errors,
            len(rows) == 29,
            f"strict freeze requires exactly 29 private participant rows, "
            f"found {len(rows)}",
        )
        required_private_verification_fields = (
            "legal_name",
            "email",
            "consent_record_locator",
            "consent_date",
            "compensation_record_locator",
        )
        for index, row in enumerate(rows, start=2):
            for field in required_private_verification_fields:
                add_check(
                    errors,
                    bool((row.get(field) or "").strip()),
                    f"strict private participant row {index} has empty {field}",
                )
        primary_auditors = {
            (row.get("participant_id") or "").strip()
            for row in rows
            if (row.get("role") or "").strip().lower() == "auditor"
            and (row.get("replacement_status") or "").strip().lower()
            not in {"reserve", "inactive"}
        }
        add_check(
            errors,
            len(primary_auditors) == 24,
            f"strict freeze requires 24 primary auditors, found {len(primary_auditors)}",
        )
        add_check(
            errors,
            len(roles.get("gold_expert", set())) == 3,
            "strict freeze requires exactly three gold experts",
        )
        add_check(
            errors,
            len(roles.get("adjudicator_1", set())) == 1,
            "strict freeze requires one adjudicator_1",
        )
        add_check(
            errors,
            len(roles.get("adjudicator_2", set())) == 1,
            "strict freeze requires one adjudicator_2",
        )
        protected_roles = (
            roles.get("gold_expert", set()),
            roles.get("adjudicator_1", set()),
            roles.get("adjudicator_2", set()),
            primary_auditors,
        )
        for left_index, left in enumerate(protected_roles):
            for right in protected_roles[left_index + 1 :]:
                add_check(
                    errors,
                    not left.intersection(right),
                    "auditor/gold/adjudicator identities overlap",
                )
    return rows, roles


def validate_private_public_participant_binding(
    private_rows: Sequence[Mapping[str, str]],
    public_path: Path,
    errors: list[str],
) -> None:
    if not public_path.exists():
        errors.append(f"public participant metadata file does not exist: {public_path}")
        return
    public_header, public_rows = read_csv(public_path)
    add_check(
        errors,
        public_header == PUBLIC_PARTICIPANT_HEADER,
        "strict private/public binding requires the exact public-roster schema",
    )
    private_by_id = {
        (row.get("participant_id") or "").strip(): row for row in private_rows
    }
    public_by_id = {
        (row.get("participant_id") or "").strip(): row for row in public_rows
    }
    add_check(
        errors,
        len(private_by_id) == len(private_rows)
        and len(public_by_id) == len(public_rows),
        "strict private/public participant IDs are empty or duplicated",
    )
    add_check(
        errors,
        set(private_by_id) == set(public_by_id),
        "strict private/public participant ID sets differ",
    )
    for participant_id in sorted(set(private_by_id).intersection(public_by_id)):
        private = private_by_id[participant_id]
        public = public_by_id[participant_id]
        comparisons = {
            "role": (
                (private.get("role") or "").strip().lower(),
                (public.get("role") or "").strip().lower(),
            ),
            "assigned_arm": (
                (private.get("assigned_arm") or "").strip().upper(),
                (public.get("assigned_arm") or "").strip().upper(),
            ),
            "replacement_status": (
                (private.get("replacement_status") or "").strip().lower(),
                (public.get("replacement_status") or "").strip().lower(),
            ),
        }
        for field, (private_value, public_value) in comparisons.items():
            add_check(
                errors,
                private_value == public_value,
                f"strict private/public {field} mismatch for {participant_id}",
            )


def validate_public_frozen_participant_rows(
    header: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    errors: list[str],
) -> tuple[list[dict[str, str]], dict[str, set[str]], list[str]]:
    """Validate the anonymous pretest roster without reading private metadata."""

    lowered_header = tuple(field.strip().lower() for field in header)
    leaked_fields = sorted(
        field
        for field in lowered_header
        if any(token in field for token in PUBLIC_PII_FIELD_TOKENS)
    )
    add_check(
        errors,
        tuple(header) == PUBLIC_PARTICIPANT_HEADER,
        "portable frozen public roster must use the exact non-PII schema",
    )
    add_check(
        errors,
        not leaked_fields,
        f"portable frozen public roster exposes private/PII fields: {leaked_fields}",
    )
    public_rows = [dict(row) for row in rows]
    add_check(
        errors,
        len(public_rows) == 29,
        f"portable frozen public roster requires 29 rows, found {len(public_rows)}",
    )
    participant_ids = [
        (row.get("participant_id") or "").strip() for row in public_rows
    ]
    add_check(
        errors,
        "" not in participant_ids and len(participant_ids) == len(set(participant_ids)),
        "portable frozen public participant IDs must be unique and nonempty",
    )
    roles: dict[str, set[str]] = defaultdict(set)
    primary_auditor_ids: list[str] = []
    auditor_arms: Counter[str] = Counter()
    calibration_states: Counter[tuple[str, str]] = Counter()
    allowed_calibration_states = {
        ("awaiting_calibration", "false"),
        ("passed_round_1", "pending_test_completion"),
    }
    expected_prefix = {
        "auditor": "AUD-",
        "gold_expert": "GLD-",
        "adjudicator_1": "ADJ-",
        "adjudicator_2": "ADJ-",
    }
    for index, row in enumerate(public_rows, start=2):
        participant_id = (row.get("participant_id") or "").strip()
        role = (row.get("role") or "").strip().lower()
        arm = (row.get("assigned_arm") or "").strip().upper()
        add_check(
            errors,
            bool(PUBLIC_ANONYMOUS_ID_RE.fullmatch(participant_id)),
            f"public roster row {index} does not use a frozen anonymous ID",
        )
        add_check(
            errors,
            role in expected_prefix,
            f"public roster row {index} has an invalid role",
        )
        if role in expected_prefix:
            roles[role].add(participant_id)
            add_check(
                errors,
                participant_id.startswith(expected_prefix[role]),
                f"public roster row {index} ID prefix disagrees with role",
            )
        if role == "auditor":
            add_check(
                errors,
                arm in ARMS,
                f"public auditor row {index} has an invalid assigned arm",
            )
            if arm in ARMS:
                auditor_arms[arm] += 1
            primary_auditor_ids.append(participant_id)
        else:
            add_check(
                errors,
                not arm,
                f"public non-auditor row {index} must not have an assigned arm",
            )
        add_check(
            errors,
            (row.get("replacement_status") or "").strip().lower() == "primary",
            f"public roster row {index} is not an active primary participant",
        )
        calibration_state = (
            (row.get("calibration_status") or "").strip(),
            (row.get("included_in_primary_analysis") or "").strip().lower(),
        )
        calibration_states[calibration_state] += 1
        add_check(
            errors,
            calibration_state in allowed_calibration_states,
            f"public roster row {index} has an invalid portable calibration state",
        )

    expected_role_counts = {
        "auditor": 24,
        "gold_expert": 3,
        "adjudicator_1": 1,
        "adjudicator_2": 1,
    }
    for role, expected_count in expected_role_counts.items():
        add_check(
            errors,
            len(roles.get(role, set())) == expected_count,
            f"portable frozen public roster requires {expected_count} {role} "
            f"participant(s)",
        )
    role_sets = [roles.get(role, set()) for role in expected_role_counts]
    for left_index, left in enumerate(role_sets):
        for right in role_sets[left_index + 1 :]:
            add_check(
                errors,
                not left.intersection(right),
                "portable public auditor/gold/adjudicator identities overlap",
            )
    add_check(
        errors,
        auditor_arms == Counter({"A": 6, "B": 6, "C": 6, "D": 6}),
        f"portable frozen auditor arms are not 6/6/6/6: {dict(auditor_arms)}",
    )
    add_check(
        errors,
        calibration_states
        in (
            Counter({("awaiting_calibration", "false"): 29}),
            Counter({("passed_round_1", "pending_test_completion"): 29}),
        ),
        "portable frozen public roster must be wholly awaiting or wholly "
        f"passed round 1: {dict(calibration_states)}",
    )
    return public_rows, roles, primary_auditor_ids


def validate_public_frozen_participant_metadata(
    path: Path, errors: list[str]
) -> tuple[list[dict[str, str]], dict[str, set[str]], list[str]]:
    if not path.exists():
        errors.append(f"public participant metadata file does not exist: {path}")
        return [], {}, []
    header, rows = read_csv(path)
    return validate_public_frozen_participant_rows(header, rows, errors)


def validate_portable_frozen_pretest_state(
    loaded: Mapping[str, Sequence[Mapping[str, str]]],
    calibration_info: Mapping[str, Any],
    summary_path: Path,
    errors: list[str],
) -> dict[str, Any]:
    calibration_rows = loaded.get("calibration_responses.csv", [])
    try:
        calibration_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read portable frozen calibration summary: {exc}")
        calibration_summary = {}
    awaiting_state = (
        len(calibration_rows) == 0
        and calibration_info.get("calibration_summary_status")
        == "AWAITING_FROZEN_CALIBRATION_RESPONSES"
        and calibration_info.get("calibration_release_eligible") is False
    )
    passed_state = (
        len(calibration_rows) == 29 * CALIBRATION_ITEM_COUNT
        and calibration_info.get("calibration_summary_status")
        == "FROZEN_CALIBRATION_PASSED_BEFORE_TEST"
        and calibration_info.get("calibration_release_eligible") is True
    )
    add_check(
        errors,
        awaiting_state != passed_state and (awaiting_state or passed_state),
        "portable frozen calibration must be either awaiting with an empty "
        "validated ledger or passed-before-test with a validated 29x10 ledger",
    )
    if calibration_summary and awaiting_state:
        add_check(
            errors,
            calibration_summary.get("response_rows") == 0,
            "portable frozen summary records calibration responses",
        )
        add_check(
            errors,
            calibration_summary.get("test_packet_release_eligible") is False,
            "portable frozen summary opens the formal test-packet gate",
        )
        add_check(
            errors,
            calibration_summary.get("participant_status_counts")
            == {"awaiting_calibration": 29},
            "portable frozen summary does not record 29 awaiting participants",
        )
        participants = calibration_summary.get("participants")
        add_check(
            errors,
            isinstance(participants, list)
            and len(participants) == 29
            and all(
                isinstance(record, dict)
                and record.get("final_status") == "awaiting_calibration"
                and record.get("rounds") == []
                for record in participants
            ),
            "portable frozen summary contains a pass or item response",
        )
    if calibration_summary and passed_state:
        add_check(
            errors,
            calibration_summary.get("response_rows")
            == 29 * CALIBRATION_ITEM_COUNT,
            "portable frozen passed summary does not record 290 responses",
        )
        add_check(
            errors,
            calibration_summary.get("test_packet_release_eligible") is True,
            "portable frozen passed summary does not open the calibration gate",
        )
        add_check(
            errors,
            calibration_summary.get("participant_status_counts")
            == {"passed_round_1": 29},
            "portable frozen passed summary does not record 29 round-1 passes",
        )
        participants = calibration_summary.get("participants")
        add_check(
            errors,
            isinstance(participants, list)
            and len(participants) == 29
            and all(
                isinstance(record, dict)
                and record.get("final_status") == "passed_round_1"
                and isinstance(record.get("rounds"), list)
                and len(record["rounds"]) == 1
                and record["rounds"][0].get("round") == 1
                and record["rounds"][0].get("passed") is True
                and len(record["rounds"][0].get("item_results", []))
                == CALIBRATION_ITEM_COUNT
                for record in participants
            ),
            "portable frozen passed summary lacks 29 complete round-1 records",
        )
    response_counts = {
        name: len(loaded.get(name, [])) for name in TEST_RESPONSE_FILES
    }
    correction_rows = len(loaded.get("review_extraction_corrections.csv", []))
    issuance_rows = len(loaded.get("composition_issuance_rows.csv", []))
    receipt_rows = len(loaded.get("coordinator_response_receipts.csv", []))
    add_check(
        errors,
        all(count == 0 for count in response_counts.values())
        and receipt_rows == 0,
        f"portable frozen reviewer package contains formal responses or "
        f"coordinator receipts: {response_counts}, receipts={receipt_rows}",
    )
    calibration_substate = (
        "calibration_passed_before_test" if passed_state else "awaiting"
    )
    return {
        "validation_scope": "PUBLIC_FROZEN_STRUCTURE_ONLY",
        "calibration_substate": calibration_substate,
        "formal_test_packet_gate": (
            "OPEN_CALIBRATION_PASSED_NO_TEST_RESPONSES"
            if passed_state
            else "CLOSED_AWAITING_CALIBRATION"
        ),
        "calibration_release_eligible": passed_state,
        "calibration_responses": len(calibration_rows),
        "formal_response_rows": sum(response_counts.values()),
        "extraction_correction_rows": correction_rows,
        "composition_issuance_rows": issuance_rows,
        "coordinator_response_receipts": receipt_rows,
        "public_participants_awaiting_calibration": 29 if awaiting_state else 0,
        "public_participants_passed_round_1": 29 if passed_state else 0,
        "private_ethics_records_verified": False,
    }


def validate_frozen_design(
    root: Path,
    loaded: Mapping[str, Sequence[Mapping[str, str]]],
    participant_path: Path | None,
    config: Mapping[str, Any],
    development_source_keys: set[str],
    development_normalized_titles: set[str],
    errors: list[str],
    *,
    portable_public: bool = False,
    public_participant_path: Path | None = None,
) -> dict[str, Any]:
    source_rows = loaded["source_sampling_frame.csv"]
    deterministic_rows = loaded["candidate_claims_deterministic.csv"]
    candidate_rows = loaded["candidate_claims_model_prescreen.csv"]
    claim_rows = loaded["frozen_test_claims.csv"]
    assignment_rows = loaded["auditor_assignments.csv"]
    text_correction_state = validate_frozen_text_correction_state(
        root,
        deterministic_rows,
        candidate_rows,
        claim_rows,
        errors,
    )
    source_frame = validate_source_frame(
        source_rows,
        errors,
        development_source_keys,
        development_normalized_titles,
    )
    replacement_info = validate_source_replacement_summary(
        root,
        source_rows,
        deterministic_rows,
        candidate_rows,
        portable_public,
        errors,
        text_correction_state=text_correction_state,
    )
    active_source_order = replacement_info.get("active_source_order")
    candidate_screen_state = validate_model_prescreen(
        candidate_rows, errors, int(config.get("prescreen_seed", 2026071505))
    )
    add_check(
        errors,
        candidate_screen_state == "human_sampling_screen_complete",
        "frozen mode requires the fully merged sampling-screen state",
    )
    validate_sampling_screen_summary(
        root, candidate_rows, candidate_screen_state, errors
    )
    validate_candidate_selection_order(
        candidate_rows,
        int(config.get("sampling_claim_seed", 2026071502)),
        errors,
    )
    candidate_title_keys: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(candidate_rows, start=2):
        source_key = (row.get("source_key") or "").strip()
        frame_row = source_frame.get(source_key)
        add_check(
            errors,
            frame_row is not None,
            f"candidate row {index} references a source absent from the frame",
        )
        if frame_row is None:
            continue
        normalized = normalize_title((frame_row.get("title") or "").strip())
        candidate_title_keys[normalized].add(source_key)
        add_check(
            errors,
            source_key not in development_source_keys,
            f"candidate row {index} reuses a development source key",
        )
        add_check(
            errors,
            normalized not in development_normalized_titles,
            f"candidate row {index} reuses a normalized development title",
        )
    duplicate_candidate_titles = {
        title: sorted(keys)
        for title, keys in candidate_title_keys.items()
        if title and len(keys) > 1
    }
    add_check(
        errors,
        not duplicate_candidate_titles,
        "candidate sources contain duplicate normalized titles: "
        f"{list(duplicate_candidate_titles.items())[:5]}",
    )

    claims = [
        Claim(
            claim_id=(row.get("claim_id") or "").strip(),
            source_key=(row.get("source_key") or "").strip(),
        )
        for row in claim_rows
    ]
    try:
        source_counts = validate_claim_design(
            claims,
            DEFAULT_EXPECTED_CLAIMS,
            DEFAULT_EXPECTED_SOURCES,
            DEFAULT_MAX_PER_SOURCE,
            development_source_keys,
        )
    except ValueError as exc:
        errors.append(str(exc))
        source_counts = {}
    validate_source_selection_order(
        source_rows,
        set(source_counts),
        development_source_keys,
        development_normalized_titles,
        int(config.get("sampling_source_seed", 2026071501)),
        errors,
        active_source_order=active_source_order,
    )

    strata = Counter(
        (row.get("coordinator_only_primary_stratum") or "").strip()
        for row in claim_rows
    )
    add_check(
        errors,
        strata == Counter({"c2_decisive": 240, "c5_decisive": 240}),
        f"frozen decisive strata are not 240/240: {dict(strata)}",
    )
    claim_ids = {(row.get("claim_id") or "").strip() for row in claim_rows}
    candidate_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row for row in candidate_rows
    }
    deterministic_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row
        for row in deterministic_rows
    }
    human_eligible_candidates: set[str] = set()
    for candidate_id, candidate_row in candidate_by_id.items():
        try:
            human_stratum, _human = validate_human_screen_row(
                candidate_row, candidate_id
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if human_stratum is not None:
            human_eligible_candidates.add(candidate_id)
    add_check(
        errors,
        claim_ids.issubset(human_eligible_candidates),
        "frozen claims include candidates not made eligible by human screeners",
    )

    test_title_keys: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(claim_rows, start=2):
        claim_id = (row.get("claim_id") or "").strip()
        source_key = (row.get("source_key") or "").strip()
        normalized_test_title = normalize_title(
            (row.get("source_title") or "").strip()
        )
        test_title_keys[normalized_test_title].add(source_key)
        add_check(
            errors,
            source_key not in development_source_keys,
            f"frozen claim {claim_id} reuses a development source key",
        )
        add_check(
            errors,
            normalized_test_title not in development_normalized_titles,
            f"frozen claim {claim_id} reuses a normalized development title",
        )
        required_text = (
            "claim_text",
            "source_title",
            "source_locator",
            "source_url_or_doi",
            "source_evidence_excerpt",
        )
        for field in required_text:
            add_check(
                errors,
                bool((row.get(field) or "").strip()),
                f"frozen claim row {index} has empty {field}",
            )
        add_check(
            errors,
            (row.get("label_collection_status") or "").strip()
            == "NO_TEST_LABELS_COLLECTED",
            f"frozen claim row {index} has an invalid label collection status",
        )
        add_check(
            errors,
            (row.get("freeze_version") or "").strip() == "v3.0.0-test-freeze",
            f"frozen claim row {index} has an invalid freeze version",
        )
        for field in ("source_file_sha256", "sampling_record_sha256"):
            add_check(
                errors,
                bool(SHA256_RE.fullmatch((row.get(field) or "").strip())),
                f"frozen claim row {index} has an invalid {field}",
            )
        frame_row = source_frame.get(source_key)
        add_check(
            errors,
            frame_row is not None,
            f"frozen claim {claim_id} references a source absent from the frame",
        )
        if frame_row is not None:
            add_check(
                errors,
                (frame_row.get("title") or "").strip()
                == (row.get("source_title") or "").strip(),
                f"source title changed between frame and freeze for {claim_id}",
            )
            add_check(
                errors,
                (frame_row.get("eligibility_status") or "").strip()
                == "eligible_selected",
                f"test source {source_key} is not marked eligible_selected",
            )
            add_check(
                errors,
                (frame_row.get("development_source_flag") or "").strip().lower()
                in {"false", "0", "no"},
                f"test source {source_key} is marked as a development source",
            )
            add_check(
                errors,
                (frame_row.get("full_text_sha256") or "").strip()
                == (row.get("source_file_sha256") or "").strip(),
                f"source hash mismatch for frozen claim {claim_id}",
            )
        candidate_row = candidate_by_id.get(claim_id)
        deterministic_row = deterministic_by_id.get(claim_id)
        add_check(
            errors,
            deterministic_row is not None,
            f"frozen claim {claim_id} is absent from deterministic candidates",
        )
        if candidate_row is not None and deterministic_row is not None:
            linked_fields = (
                "source_key",
                "claim_text",
                "context_before",
                "context_after",
                "source_section",
                "source_locator",
                "source_url_or_doi",
                "source_evidence_excerpt",
                "source_file_sha256",
            )
            for field in linked_fields:
                add_check(
                    errors,
                    (candidate_row.get(field) or "").strip()
                    == (row.get(field) or "").strip(),
                    f"candidate-to-freeze field {field} changed for {claim_id}",
                )
            add_check(
                errors,
                sampling_record_sha256(
                    deterministic_row,
                    candidate_row,
                    (row.get("coordinator_only_primary_stratum") or "").strip(),
                )
                == (row.get("sampling_record_sha256") or "").strip(),
                f"sampling-record hash mismatch for {claim_id}",
            )
            deterministic_links = {
                "source_key": "source_key",
                "claim_text": "exact_quote",
                "context_before": "context_before",
                "context_after": "context_after",
                "source_title": "source_title",
                "source_section": "source_section",
                "source_url_or_doi": "source_url_or_doi",
                "source_evidence_excerpt": "exact_quote",
                "source_file_sha256": "source_text_sha256",
            }
            for frozen_field, deterministic_field in deterministic_links.items():
                add_check(
                    errors,
                    (row.get(frozen_field) or "").strip()
                    == (deterministic_row.get(deterministic_field) or "").strip(),
                    f"deterministic-to-freeze field {frozen_field} changed for {claim_id}",
                )
            add_check(
                errors,
                (row.get("source_locator") or "").strip()
                == f"PDF page {(deterministic_row.get('pdf_page') or '').strip()}",
                f"deterministic-to-freeze source locator changed for {claim_id}",
            )
            add_check(
                errors,
                (candidate_row.get("human_sampling_eligibility") or "").strip()
                in {"eligible_c2", "eligible_c5"},
                f"selected candidate {claim_id} lacks human decisive eligibility",
            )
            expected_stratum = {
                "eligible_c2": "c2_decisive",
                "eligible_c5": "c5_decisive",
            }.get((candidate_row.get("human_sampling_eligibility") or "").strip())
            add_check(
                errors,
                expected_stratum
                == (row.get("coordinator_only_primary_stratum") or "").strip(),
                f"sampling stratum mismatch for {claim_id}",
            )
            add_check(
                errors,
                (candidate_row.get("human_sampling_stratum") or "").strip()
                == expected_stratum,
                f"candidate sampling metadata mismatch for {claim_id}",
            )

    duplicate_test_titles = {
        title: sorted(keys)
        for title, keys in test_title_keys.items()
        if title and len(keys) > 1
    }
    add_check(
        errors,
        not duplicate_test_titles,
        "frozen test sources contain duplicate normalized titles: "
        f"{list(duplicate_test_titles.items())[:5]}",
    )

    ledger_rows = loaded["sampling_exclusion_replacement_ledger.csv"]
    add_check(
        errors,
        not duplicate_values(ledger_rows, "ledger_event_id"),
        "sampling ledger contains duplicate event IDs",
    )
    for index, ledger_row in enumerate(ledger_rows, start=2):
        expected_hash = canonical_json_sha256(
            {
                field: (ledger_row.get(field) or "")
                for field in LEDGER_HEADER
                if field != "record_sha256"
            }
        )
        add_check(
            errors,
            expected_hash == (ledger_row.get("record_sha256") or "").strip(),
            f"sampling ledger row {index} has an invalid record hash",
        )
    replacement_rows = loaded["source_replacement_exclusions.csv"]
    add_check(
        errors,
        not duplicate_values(replacement_rows, "source_key"),
        "replacement exclusions contain duplicate source keys",
    )
    freeze_summary_path = root / "sampling_freeze_summary.json"
    try:
        freeze_summary = json.loads(
            read_text_or_error(freeze_summary_path, errors)
        )
    except json.JSONDecodeError as exc:
        errors.append(f"cannot read sampling_freeze_summary.json: {exc}")
        freeze_summary = {}
    if freeze_summary:
        expected_summary = {
            "status": "FROZEN_NO_TEST_LABELS",
            "replacement_required": False,
            "claims": 480,
            "sources": 80,
            "c2_claims": 240,
            "c5_claims": 240,
            "sampling_claim_seed": 2026071502,
            "model_fields_used_for_selection": False,
            "ledger_events": len(ledger_rows),
            "frozen_claims_sha256": sha256_file(
                root / "frozen_test_claims.csv"
            ),
            "sampling_screen_summary_sha256": sha256_file(
                root / "sampling_screen_summary.json"
            ),
            "source_replacement_summary_sha256": sha256_file(
                root / "source_replacement_summary.json"
            ),
            "human_sampling_input_sha256": canonical_json_sha256(
                {
                    "rows": sorted(
                        (
                            sanitize_human_sampling_row(row)
                            for row in candidate_rows
                        ),
                        key=lambda row: row["candidate_claim_id"],
                    )
                }
            ),
        }
        for field, expected_value in expected_summary.items():
            add_check(
                errors,
                freeze_summary.get(field) == expected_value,
                f"sampling freeze summary field {field} is inconsistent",
            )

    if portable_public:
        if public_participant_path is None:
            errors.append("portable frozen validation requires a public roster")
            metadata_rows: list[dict[str, str]] = []
            primary_auditor_ids: list[str] = []
        else:
            (
                metadata_rows,
                _roles,
                primary_auditor_ids,
            ) = validate_public_frozen_participant_metadata(
                public_participant_path, errors
            )
    else:
        if participant_path is None:
            errors.append("strict frozen validation requires private participant metadata")
            metadata_rows = []
            primary_auditor_ids = []
        else:
            metadata_rows, _roles = validate_participant_metadata(
                participant_path, errors, strict=True
            )
            if public_participant_path is None:
                errors.append(
                    "strict frozen validation requires the paired public roster"
                )
            else:
                validate_private_public_participant_binding(
                    metadata_rows, public_participant_path, errors
                )
            try:
                primary_auditor_ids = read_primary_auditor_ids(participant_path)
            except ValueError as exc:
                errors.append(str(exc))
                primary_auditor_ids = []
    if claims and assignment_rows and primary_auditor_ids:
        try:
            assignment_summary = validate_assignment_rows(
                assignment_rows, claims, primary_auditor_ids, DEFAULT_SEED
            )
            expected_assignments = construct_assignments(
                claims, primary_auditor_ids, DEFAULT_SEED
            )
            add_check(
                errors,
                [dict(row) for row in assignment_rows] == expected_assignments,
                "assignment file is balanced but does not match the frozen seed",
            )
        except ValueError as exc:
            errors.append(str(exc))
            assignment_summary = {}
    else:
        assignment_summary = {}
        if not assignment_rows:
            errors.append("frozen mode requires generated auditor assignments")

    if metadata_rows and assignment_rows:
        assigned_arms: dict[str, set[str]] = defaultdict(set)
        for row in assignment_rows:
            assigned_arms[(row.get("participant_id") or "").strip()].add(
                (row.get("arm") or "").strip()
            )
        for row in metadata_rows:
            participant_id = (row.get("participant_id") or "").strip()
            declared_arm = (row.get("assigned_arm") or "").strip()
            if participant_id in assigned_arms and declared_arm:
                add_check(
                    errors,
                    assigned_arms[participant_id] == {declared_arm},
                    f"declared arm does not match assignments for {participant_id}",
                )

    calibration_rows = loaded["calibration_responses.csv"]
    test_sources = set(source_counts)
    for index, row in enumerate(calibration_rows, start=2):
        add_check(
            errors,
            (row.get("calibration_item_id") or "").strip() not in claim_ids,
            f"calibration row {index} reuses a frozen test claim ID",
        )
        add_check(
            errors,
            (row.get("calibration_source_key") or "").strip() not in test_sources,
            f"calibration row {index} reuses a frozen test source",
        )
    participant_summary: dict[str, Any]
    if portable_public:
        participant_summary = {
            "participant_metadata_source": "public_anonymous_roster",
            "public_participant_metadata_sha256": (
                sha256_file(public_participant_path)
                if public_participant_path is not None
                and public_participant_path.exists()
                else None
            ),
            "private_participant_and_ethics_verification": (
                "NOT_PERFORMED_PORTABLE"
            ),
        }
    else:
        participant_summary = {
            "participant_metadata_source": "private_strict_roster",
            "private_participant_and_ethics_verification": (
                "STRICT_REQUIRED_FIELDS_CHECKED"
            ),
            "participant_metadata_sha256": (
                sha256_file(participant_path)
                if participant_path is not None and participant_path.exists()
                else None
            ),
        }
    return {
        "claims": len(claim_rows),
        "sources": len(source_counts),
        "assignments": len(assignment_rows),
        "assignment_summary": assignment_summary,
        "source_replacement_verification": replacement_info.get(
            "verification"
        ),
        "source_replacement_batches": replacement_info.get("batches"),
        "frozen_text_correction_verification": (
            "reversible preimage/hash-chain verification; "
            "authoritative H3-065-14 normalization"
        ),
        "frozen_text_correction_records": len(
            loaded["frozen_text_corrections.csv"]
        ),
        "frozen_text_corrections_sha256": sha256_file(
            root / "frozen_text_corrections.csv"
        ),
        **participant_summary,
    }


def validate_completed_response_labels(
    rows: Sequence[Mapping[str, str]],
    evidence_field: str,
    comparability_field: str,
    name: str,
    errors: list[str],
) -> None:
    for index, row in enumerate(rows, start=2):
        if (row.get("response_status") or "").strip() != "completed":
            continue
        evidence = (row.get(evidence_field) or "").strip()
        comparability = (row.get(comparability_field) or "").strip()
        if evidence:
            add_check(
                errors,
                evidence in EVIDENCE_LABELS,
                f"{name} row {index} has an invalid evidence-support label",
            )
        if comparability:
            add_check(
                errors,
                comparability in COMPARABILITY_LABELS,
                f"{name} row {index} has an invalid comparability label",
            )


def validate_staged_extraction_chains(
    loaded: Mapping[str, Sequence[Mapping[str, str]]],
    errors: list[str],
) -> None:
    corrections = loaded.get("review_extraction_corrections.csv", [])
    correction_ids = [
        (row.get("correction_id") or "").strip() for row in corrections
    ]
    add_check(
        errors,
        "" not in correction_ids and len(correction_ids) == len(set(correction_ids)),
        "staged correction IDs are empty or duplicated",
    )
    corrections_by_response: dict[
        tuple[str, str], list[Mapping[str, str]]
    ] = defaultdict(list)
    for index, row in enumerate(corrections, start=2):
        context = f"review_extraction_corrections.csv row {index}"
        add_check(
            errors,
            (row.get("record_sha256") or "").strip()
            == correction_record_sha256(row),
            f"{context} has an invalid record hash",
        )
        for field in (
            "old_extraction_snapshot_sha256",
            "new_extraction_snapshot_sha256",
            "invalidated_composition_sha256",
            "record_sha256",
        ):
            add_check(
                errors,
                bool(SHA256_RE.fullmatch((row.get(field) or "").strip())),
                f"{context} has an invalid {field}",
            )
        add_check(
            errors,
            bool((row.get("correction_reason") or "").strip()),
            f"{context} has an empty correction reason",
        )
        try:
            parse_staged_utc((row.get("amended_utc") or "").strip())
        except ValueError as exc:
            errors.append(f"{context} has invalid amended_utc: {exc}")
        add_check(
            errors,
            (row.get("composition_had_started") or "").strip()
            in {"true", "false"},
            f"{context} has invalid composition_had_started",
        )
        try:
            old_version = int((row.get("old_extraction_version") or "").strip())
            new_version = int((row.get("new_extraction_version") or "").strip())
        except ValueError:
            errors.append(f"{context} has a noninteger extraction version")
            continue
        add_check(
            errors,
            old_version >= 1 and new_version == old_version + 1,
            f"{context} breaks extraction version succession",
        )
        response_id = (row.get("extraction_response_id") or "").strip()
        participant_id = (row.get("participant_id") or "").strip()
        add_check(
            errors,
            bool(response_id and participant_id),
            f"{context} has an empty participant or response ID",
        )
        expected_correction_id = "corr_" + hashlib.sha256(
            f"{participant_id}|{new_version}|{response_id}".encode("utf-8")
        ).hexdigest()[:24]
        add_check(
            errors,
            (row.get("correction_id") or "").strip() == expected_correction_id,
            f"{context} has a noncanonical correction ID",
        )
        corrections_by_response[(participant_id, response_id)].append(row)

    response_specs: list[
        tuple[
            str,
            str,
            str,
            Sequence[str],
            Sequence[str],
            str,
            Sequence[Mapping[str, str]],
        ]
    ] = []
    for arm, name in ARM_RESPONSE_FILES.items():
        response_specs.append(
            (
                "auditor",
                arm,
                "assignment_id",
                STAGED_AUDITOR_IMMUTABLE_FIELDS,
                STAGED_ARM_EXTRACTION_FIELDS[arm],
                "extraction_started_utc",
                loaded.get(name, []),
            )
        )
    response_specs.append(
        (
            "gold_expert",
            "",
            "gold_response_id",
            STAGED_GOLD_IMMUTABLE_FIELDS,
            STAGED_GOLD_EXTRACTION_FIELDS,
            "review_started_utc",
            loaded.get("gold_responses.csv", []),
        )
    )

    seen_response_keys: set[tuple[str, str]] = set()
    final_ids_by_participant: dict[str, set[str]] = defaultdict(set)
    final_completion_by_participant: dict[str, set[str]] = defaultdict(set)
    for (
        participant_role,
        assigned_arm,
        response_id_field,
        immutable_fields,
        extraction_fields,
        start_field,
        rows,
    ) in response_specs:
        extraction_hash_fields = (
            *tuple(immutable_fields),
            start_field,
            *tuple(extraction_fields),
            "extraction_completed_utc",
        )
        for index, row in enumerate(rows, start=2):
            context = (
                f"{participant_role}/{assigned_arm or 'gold'} final row {index}"
            )
            response_id = (row.get(response_id_field) or "").strip()
            participant_id = (row.get("participant_id") or "").strip()
            key = (participant_id, response_id)
            add_check(
                errors,
                bool(participant_id and response_id) and key not in seen_response_keys,
                f"{context} has an empty or duplicate staged response ID",
            )
            seen_response_keys.add(key)
            final_ids_by_participant[participant_id].add(response_id)
            final_completion_by_participant[participant_id].add(
                (row.get("extraction_completed_utc") or "").strip()
            )
            add_check(
                errors,
                (row.get("packet_version") or "").strip()
                == "v3.0.0-test-freeze",
                f"{context} has an invalid packet version",
            )
            for field in extraction_fields:
                add_check(
                    errors,
                    bool((row.get(field) or "").strip()),
                    f"{context} has a blank extraction field {field}",
                )
            if participant_role == "auditor":
                add_check(
                    errors,
                    (row.get("source_location_checked") or "").strip().lower()
                    in {"yes", "not_applicable", "unknown"},
                    f"{context} has invalid source_location_checked",
                )
            try:
                started = parse_staged_utc((row.get(start_field) or "").strip())
                extraction_completed = parse_staged_utc(
                    (row.get("extraction_completed_utc") or "").strip()
                )
                add_check(
                    errors,
                    started <= extraction_completed,
                    f"{context} extraction starts after completion",
                )
            except ValueError as exc:
                errors.append(f"{context} has invalid extraction time: {exc}")
            try:
                validate_staged_composition_row(row, context)
            except ValueError as exc:
                errors.append(str(exc))

            chain = corrections_by_response.get(key, [])
            try:
                ordered_chain = sorted(
                    chain,
                    key=lambda value: int(
                        (value.get("new_extraction_version") or "").strip()
                    ),
                )
            except ValueError:
                ordered_chain = []
            extraction_version = 1
            prior_snapshot = ""
            prior_new_snapshot = ""
            for chain_index, correction in enumerate(ordered_chain, start=1):
                try:
                    old_version = int(correction["old_extraction_version"])
                    new_version = int(correction["new_extraction_version"])
                except (KeyError, ValueError):
                    continue
                add_check(
                    errors,
                    old_version == extraction_version
                    and new_version == extraction_version + 1,
                    f"{context} correction chain skips a version",
                )
                if chain_index > 1:
                    add_check(
                        errors,
                        correction["old_extraction_snapshot_sha256"]
                        == prior_new_snapshot,
                        f"{context} correction hash chain is discontinuous",
                    )
                add_check(
                    errors,
                    (correction.get("participant_role") or "").strip()
                    == participant_role
                    and (correction.get("assigned_arm") or "").strip()
                    == assigned_arm,
                    f"{context} correction role/arm mismatch",
                )
                extraction_version = new_version
                prior_snapshot = correction[
                    "old_extraction_snapshot_sha256"
                ]
                prior_new_snapshot = correction[
                    "new_extraction_snapshot_sha256"
                ]
            expected_snapshot = extraction_snapshot_sha256(
                row,
                workflow_version=STAGED_WORKFLOW_VERSION,
                participant_id=participant_id,
                participant_role=participant_role,
                assigned_arm=assigned_arm,
                response_id_field=response_id_field,
                extraction_hash_fields=extraction_hash_fields,
                extraction_version=extraction_version,
                prior_extraction_snapshot_sha256=prior_snapshot,
            )
            actual_snapshot = (
                row.get("extraction_snapshot_sha256") or ""
            ).strip()
            add_check(
                errors,
                actual_snapshot == expected_snapshot,
                f"{context} has an invalid extraction snapshot hash",
            )
            if ordered_chain:
                add_check(
                    errors,
                    prior_new_snapshot == actual_snapshot,
                    f"{context} does not match the final correction hash",
                )

    unused_corrections = sorted(
        key for key in corrections_by_response if key not in seen_response_keys
    )
    add_check(
        errors,
        not unused_corrections,
        f"correction ledger references unknown final responses: "
        f"{unused_corrections[:5]}",
    )
    correction_batches: dict[
        tuple[str, int], list[Mapping[str, str]]
    ] = defaultdict(list)
    for correction in corrections:
        try:
            new_version = int(
                (correction.get("new_extraction_version") or "").strip()
            )
        except ValueError:
            continue
        correction_batches[
            ((correction.get("participant_id") or "").strip(), new_version)
        ].append(correction)
    participants_with_corrections = {
        participant_id for participant_id, _version in correction_batches
    }
    for participant_id in sorted(participants_with_corrections):
        versions = sorted(
            version
            for candidate_id, version in correction_batches
            if candidate_id == participant_id
        )
        add_check(
            errors,
            versions == list(range(2, max(versions) + 1)),
            f"{participant_id} correction batches skip a packet version",
        )
        previous_amended = None
        for version in versions:
            batch = correction_batches[(participant_id, version)]
            batch_ids = {
                (row.get("extraction_response_id") or "").strip()
                for row in batch
            }
            add_check(
                errors,
                batch_ids == final_ids_by_participant.get(participant_id, set()),
                f"{participant_id} correction v{version} does not cover every "
                "final response exactly once",
            )
            shared_metadata = {
                (
                    (row.get("correction_reason") or "").strip(),
                    (row.get("amended_utc") or "").strip(),
                    (
                        row.get("invalidated_composition_sha256") or ""
                    ).strip(),
                    (row.get("composition_had_started") or "").strip(),
                )
                for row in batch
            }
            add_check(
                errors,
                len(shared_metadata) == 1,
                f"{participant_id} correction v{version} has inconsistent "
                "packet-level metadata",
            )
            amended_text = (
                next(iter(shared_metadata))[1] if shared_metadata else ""
            )
            try:
                amended = parse_staged_utc(amended_text)
            except ValueError:
                amended = None
            if previous_amended is not None and amended is not None:
                add_check(
                    errors,
                    amended >= previous_amended,
                    f"{participant_id} correction timestamps move backward",
                )
            if amended is not None:
                previous_amended = amended
        if versions:
            final_completion = final_completion_by_participant.get(
                participant_id, set()
            )
            last_metadata = {
                (
                    row.get("amended_utc") or ""
                ).strip()
                for row in correction_batches[(participant_id, versions[-1])]
            }
            add_check(
                errors,
                len(final_completion) == 1
                and final_completion == last_metadata,
                f"{participant_id} final extraction completion does not match "
                "the last correction batch",
            )


def staged_extraction_chain_self_test(errors: list[str]) -> None:
    row = {field: "" for field in ARM_A_HEADER}
    for field in STAGED_AUDITOR_IMMUTABLE_FIELDS:
        row[field] = f"synthetic-{field}"
    row.update(
        {
            "assignment_id": "asg_staged_validator",
            "claim_id": "claim_staged_validator",
            "source_key": "source_staged_validator",
            "participant_id": "AUD-STAGEDVALID",
            "arm": "A",
            "packet_version": "v3.0.0-test-freeze",
            "display_order": "1",
            "extraction_started_utc": "2026-07-18T09:00:00Z",
            "extraction_completed_utc": "2026-07-18T09:10:00Z",
            "response_status": "completed",
            "composition_started_utc": "2026-07-18T09:11:00Z",
            "evidence_support_label": "supported_as_written",
            "evidence_support_reason": "synthetic support reason",
            "comparability_label": "same_estimand",
            "comparability_reason": "synthetic comparison reason",
            "completed_utc": "2026-07-18T09:12:00Z",
        }
    )
    for field in STAGED_ARM_EXTRACTION_FIELDS["A"]:
        row[field] = "yes" if field == "source_location_checked" else "synthetic fact"
    hash_fields = (
        *STAGED_AUDITOR_IMMUTABLE_FIELDS,
        "extraction_started_utc",
        *STAGED_ARM_EXTRACTION_FIELDS["A"],
        "extraction_completed_utc",
    )
    row["extraction_snapshot_sha256"] = extraction_snapshot_sha256(
        row,
        workflow_version=STAGED_WORKFLOW_VERSION,
        participant_id=row["participant_id"],
        participant_role="auditor",
        assigned_arm="A",
        response_id_field="assignment_id",
        extraction_hash_fields=hash_fields,
        extraction_version=1,
        prior_extraction_snapshot_sha256="",
    )
    loaded: dict[str, list[dict[str, str]]] = {
        name: [] for name in (*TEST_RESPONSE_FILES, "review_extraction_corrections.csv")
    }
    loaded["arm_A_responses.csv"] = [row]
    valid_errors: list[str] = []
    validate_staged_extraction_chains(loaded, valid_errors)
    add_check(
        errors,
        not valid_errors,
        f"staged extraction v1 self-test failed: {valid_errors}",
    )

    old_snapshot = row["extraction_snapshot_sha256"]
    amended = dict(row)
    amended["reported_result_facts"] = "corrected synthetic fact"
    amended["extraction_completed_utc"] = "2026-07-18T09:20:00Z"
    amended["composition_started_utc"] = "2026-07-18T09:21:00Z"
    amended["completed_utc"] = "2026-07-18T09:22:00Z"
    amended["extraction_snapshot_sha256"] = extraction_snapshot_sha256(
        amended,
        workflow_version=STAGED_WORKFLOW_VERSION,
        participant_id=amended["participant_id"],
        participant_role="auditor",
        assigned_arm="A",
        response_id_field="assignment_id",
        extraction_hash_fields=hash_fields,
        extraction_version=2,
        prior_extraction_snapshot_sha256=old_snapshot,
    )
    correction: dict[str, str] = {
        "correction_id": "corr_"
        + hashlib.sha256(
            (
                f"{amended['participant_id']}|2|"
                f"{amended['assignment_id']}"
            ).encode("utf-8")
        ).hexdigest()[:24],
        "participant_id": amended["participant_id"],
        "participant_role": "auditor",
        "assigned_arm": "A",
        "extraction_response_id": amended["assignment_id"],
        "old_extraction_version": "1",
        "old_extraction_snapshot_sha256": old_snapshot,
        "new_extraction_version": "2",
        "new_extraction_snapshot_sha256": amended[
            "extraction_snapshot_sha256"
        ],
        "correction_reason": "synthetic correction",
        "amended_utc": "2026-07-18T09:20:00Z",
        "invalidated_composition_sha256": "b" * 64,
        "composition_had_started": "true",
        "record_sha256": "",
    }
    correction["record_sha256"] = correction_record_sha256(correction)
    loaded["arm_A_responses.csv"] = [amended]
    loaded["review_extraction_corrections.csv"] = [correction]
    amended_errors: list[str] = []
    validate_staged_extraction_chains(loaded, amended_errors)
    add_check(
        errors,
        not amended_errors,
        f"staged extraction amendment self-test failed: {amended_errors}",
    )

    tampered = dict(amended)
    tampered["reported_result_facts"] = "silent tamper"
    loaded["arm_A_responses.csv"] = [tampered]
    tamper_errors: list[str] = []
    validate_staged_extraction_chains(loaded, tamper_errors)
    add_check(
        errors,
        any("invalid extraction snapshot hash" in error for error in tamper_errors),
        "staged extraction validator accepted a silent final-row amendment",
    )


def expected_adjudicator_registry(
    root: Path,
    frozen_rows: Sequence[Mapping[str, str]],
    gold_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    public_header, public_rows = read_csv(
        root / "participant_metadata_public_template.csv"
    )
    if public_header != CALIBRATION_PUBLIC_ROSTER_HEADER:
        raise ValueError("public roster schema changed")
    packets = build_adjudicator_packets(
        frozen_rows,
        public_rows,
        gold_rows,
    )
    return build_adjudicator_registry(
        packets,
        frozen_claims_sha256=sha256_file(root / "frozen_test_claims.csv"),
        gold_responses_sha256=sha256_file(root / "gold_responses.csv"),
        public_role_roster_sha256=public_role_roster_sha256(public_rows),
    )


def load_and_validate_adjudicator_registry(
    root: Path,
    frozen_rows: Sequence[Mapping[str, str]],
    gold_rows: Sequence[Mapping[str, str]],
    errors: list[str],
) -> dict[str, Any]:
    try:
        expected = expected_adjudicator_registry(
            root, frozen_rows, gold_rows
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"cannot reconstruct adjudicator packet registry: {exc}")
        return {
            "status": "INVALID_ADJUDICATOR_PACKET_REGISTRY",
            "packet_count": 0,
            "row_count": 0,
            "packets": [],
            "rows": [],
        }
    try:
        actual = json.loads(
            (root / "adjudicator_packet_registry.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read adjudicator packet registry: {exc}")
        return expected
    validate_adjudicator_registry_value(actual, expected, errors)
    return expected


def validate_adjudicator_registry_value(
    actual: object,
    expected: Mapping[str, Any],
    errors: list[str],
) -> None:
    add_check(
        errors,
        actual == expected,
        "coordinator-issued adjudicator packet registry/hash differs from "
        "the frozen claims, completed gold disagreements, or public role roster",
    )


def validate_adjudicator_response_rows(
    rows_by_role: Mapping[str, Sequence[Mapping[str, str]]],
    registry: Mapping[str, Any],
    roles: Mapping[str, set[str]],
    errors: list[str],
) -> None:
    registry_rows_by_role: dict[
        str, dict[str, Mapping[str, object]]
    ] = {
        "adjudicator_1": {},
        "adjudicator_2": {},
    }
    packet_hash_by_role = {
        str(packet["adjudicator_role"]): str(packet["packet_sha256"])
        for packet in registry["packets"]
    }
    for record in registry["rows"]:
        role = str(record["adjudicator_role"])
        claim_id = str(record["claim_id"])
        if role not in registry_rows_by_role:
            errors.append("adjudicator registry contains an unknown role")
            continue
        if claim_id in registry_rows_by_role[role]:
            errors.append(
                f"adjudicator registry duplicates claim {claim_id} for {role}"
            )
            continue
        registry_rows_by_role[role][claim_id] = record
        add_check(
            errors,
            str(record["packet_sha256"]) == packet_hash_by_role.get(role, ""),
            f"adjudicator registry row {claim_id} has the wrong packet hash",
        )

    for role in ("adjudicator_1", "adjudicator_2"):
        name = f"{role}_responses.csv"
        rows = rows_by_role.get(role, ())
        expected_by_claim = registry_rows_by_role[role]
        claim_counts = Counter(
            (row.get("claim_id") or "").strip() for row in rows
        )
        expected_counts = {
            claim_id: 1 for claim_id in expected_by_claim
        }
        add_check(
            errors,
            dict(claim_counts) == expected_counts,
            f"{name} must contain exactly one row per coordinator-issued "
            "complete-gold disagreement and no other claims",
        )
        add_check(
            errors,
            not duplicate_values(rows, "adjudication_id"),
            f"{name} contains duplicate adjudication IDs",
        )
        for index, row in enumerate(rows, start=2):
            claim_id = (row.get("claim_id") or "").strip()
            expected = expected_by_claim.get(claim_id)
            participant_id = (row.get("participant_id") or "").strip()
            add_check(
                errors,
                participant_id in roles.get(role, set()),
                f"{name} row {index} has the wrong adjudicator identity",
            )
            if expected is None:
                continue
            outputs = str(expected["disputed_outputs"]).split("|")
            expected_id = deterministic_adjudication_id(
                role,
                str(expected["participant_id"]),
                claim_id,
                outputs,
            )
            add_check(
                errors,
                (row.get("adjudication_id") or "").strip() == expected_id,
                f"{name} row {index} has a non-deterministic adjudication_id",
            )
            for field in (
                "source_key",
                "participant_id",
                "disputed_outputs",
                "blinded_gold_response_ids",
                "raw_materials_sha256",
            ):
                add_check(
                    errors,
                    (row.get(field) or "").strip()
                    == str(expected[field]),
                    f"{name} row {index} differs from coordinator-issued "
                    f"adjudicator registry field {field}",
                )
            add_check(
                errors,
                str(expected["packet_sha256"])
                == packet_hash_by_role.get(role, ""),
                f"{name} row {index} is detached from the issued packet hash",
            )
            add_check(
                errors,
                (row.get("other_adjudicator_response_seen") or "")
                .strip()
                .lower()
                in {"false", "0", "no"},
                f"{name} row {index} indicates non-independent adjudication",
            )
        validate_completed_response_labels(
            rows,
            "adjudicated_evidence_support_label",
            "adjudicated_comparability_label",
            name,
            errors,
        )


def adjudicator_integrity_self_test(errors: list[str]) -> None:
    frozen = [
        {
            "claim_id": claim_id,
            "source_key": "source_1",
            "claim_text": f"Claim {claim_id}",
            "context_before": "before",
            "context_after": "after",
            "source_title": "Source",
            "source_section": "Results",
            "source_locator": "page 1",
            "source_url_or_doi": "https://example.invalid",
            "source_evidence_excerpt": "evidence",
            "source_file_sha256": "a" * 64,
        }
        for claim_id in ("claim_disputed", "claim_incomplete")
    ]
    roster = [
        {
            "participant_id": f"auditor_{index:02d}",
            "role": "auditor",
            "assigned_arm": "ABCD"[index // 6],
            "replacement_status": "primary",
        }
        for index in range(24)
    ]
    roster.extend(
        {
            "participant_id": f"gold_{index}",
            "role": "gold_expert",
            "assigned_arm": "",
            "replacement_status": "primary",
        }
        for index in range(3)
    )
    roster.extend(
        {
            "participant_id": f"adjudicator_{index}_participant",
            "role": f"adjudicator_{index}",
            "assigned_arm": "",
            "replacement_status": "primary",
        }
        for index in (1, 2)
    )
    gold_rows: list[dict[str, str]] = []
    for claim_id in ("claim_disputed", "claim_incomplete"):
        for expert in range(3):
            completed = not (
                claim_id == "claim_incomplete" and expert == 2
            )
            gold_rows.append(
                {
                    "claim_id": claim_id,
                    "participant_id": f"gold_{expert}",
                    "gold_response_id": f"{claim_id}_{expert}",
                    "response_status": (
                        "completed" if completed else "unable_to_determine"
                    ),
                    "evidence_support_label": (
                        "supported_as_written" if completed else ""
                    ),
                    "evidence_support_reason": "reason" if completed else "",
                    "comparability_label": (
                        (
                            "different_estimand"
                            if claim_id == "claim_disputed" and expert == 2
                            else "same_estimand"
                        )
                        if completed
                        else ""
                    ),
                    "comparability_reason": "reason" if completed else "",
                }
            )
    packets = build_adjudicator_packets(frozen, roster, gold_rows)
    registry = build_adjudicator_registry(
        packets,
        frozen_claims_sha256="a" * 64,
        gold_responses_sha256="b" * 64,
        public_role_roster_sha256="c" * 64,
    )
    roles = {
        f"adjudicator_{number}": {
            f"adjudicator_{number}_participant"
        }
        for number in (1, 2)
    }
    rows_by_role: dict[str, list[dict[str, str]]] = {
        "adjudicator_1": [],
        "adjudicator_2": [],
    }
    for record in registry["rows"]:
        role = str(record["adjudicator_role"])
        rows_by_role[role].append(
            {
                "adjudication_id": str(record["adjudication_id"]),
                "claim_id": str(record["claim_id"]),
                "source_key": str(record["source_key"]),
                "participant_id": str(record["participant_id"]),
                "disputed_outputs": str(record["disputed_outputs"]),
                "blinded_gold_response_ids": str(
                    record["blinded_gold_response_ids"]
                ),
                "raw_materials_sha256": str(
                    record["raw_materials_sha256"]
                ),
                "response_status": "completed",
                "adjudicated_evidence_support_label": (
                    "supported_as_written"
                ),
                "adjudicated_comparability_label": "same_estimand",
                "other_adjudicator_response_seen": "false",
            }
        )
    valid_errors: list[str] = []
    validate_adjudicator_response_rows(
        rows_by_role, registry, roles, valid_errors
    )
    add_check(
        errors,
        not valid_errors,
        f"exact-one adjudicator fixture failed: {valid_errors}",
    )

    duplicate_rows = {
        role: [dict(row) for row in rows]
        for role, rows in rows_by_role.items()
    }
    duplicate = dict(duplicate_rows["adjudicator_1"][0])
    duplicate["adjudication_id"] = "adj_1_different_id"
    duplicate_rows["adjudicator_1"].append(duplicate)
    duplicate_errors: list[str] = []
    validate_adjudicator_response_rows(
        duplicate_rows, registry, roles, duplicate_errors
    )
    add_check(
        errors,
        any("exactly one row" in error for error in duplicate_errors),
        "adjudicator validator accepted duplicate rows for one claim",
    )

    incomplete_rows = {
        role: [dict(row) for row in rows]
        for role, rows in rows_by_role.items()
    }
    incomplete = dict(incomplete_rows["adjudicator_1"][0])
    incomplete["claim_id"] = "claim_incomplete"
    incomplete["adjudication_id"] = "adj_1_ineligible"
    incomplete_rows["adjudicator_1"].append(incomplete)
    incomplete_errors: list[str] = []
    validate_adjudicator_response_rows(
        incomplete_rows, registry, roles, incomplete_errors
    )
    add_check(
        errors,
        any("exactly one row" in error for error in incomplete_errors),
        "adjudicator validator accepted an incomplete-gold claim",
    )

    wrong_id_rows = {
        role: [dict(row) for row in rows]
        for role, rows in rows_by_role.items()
    }
    wrong_id_rows["adjudicator_1"][0][
        "adjudication_id"
    ] = "adj_1_wrong"
    wrong_id_errors: list[str] = []
    validate_adjudicator_response_rows(
        wrong_id_rows, registry, roles, wrong_id_errors
    )
    add_check(
        errors,
        any("non-deterministic adjudication_id" in error for error in wrong_id_errors),
        "adjudicator validator accepted a wrong deterministic ID",
    )

    wrong_hash_rows = {
        role: [dict(row) for row in rows]
        for role, rows in rows_by_role.items()
    }
    wrong_hash_rows["adjudicator_2"][0][
        "raw_materials_sha256"
    ] = "0" * 64
    wrong_hash_errors: list[str] = []
    validate_adjudicator_response_rows(
        wrong_hash_rows, registry, roles, wrong_hash_errors
    )
    add_check(
        errors,
        any("raw_materials_sha256" in error for error in wrong_hash_errors),
        "adjudicator validator accepted a wrong materials hash",
    )

    tampered_registry = json.loads(json.dumps(registry))
    tampered_registry["packets"][0]["packet_sha256"] = "0" * 64
    packet_hash_errors: list[str] = []
    validate_adjudicator_registry_value(
        tampered_registry, registry, packet_hash_errors
    )
    add_check(
        errors,
        bool(packet_hash_errors),
        "adjudicator validator accepted a wrong issued-packet hash",
    )
    add_check(
        errors,
        all(
            row["claim_id"] == "claim_disputed"
            for rows in rows_by_role.values()
            for row in rows
        ),
        "incomplete gold claim incorrectly received adjudication",
    )


def validate_collected_data(
    root: Path,
    loaded: Mapping[str, Sequence[Mapping[str, str]]],
    participant_path: Path,
    errors: list[str],
) -> None:
    metadata_rows, roles = validate_participant_metadata(
        participant_path, errors, strict=True
    )
    del metadata_rows
    try:
        validate_collection_artifacts(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"coordinator collection/receipt validation failed: {exc}")
    assignment_rows = loaded["auditor_assignments.csv"]
    assignments_by_id = {
        (row.get("assignment_id") or "").strip(): row for row in assignment_rows
    }
    for arm, name in ARM_RESPONSE_FILES.items():
        rows = loaded[name]
        response_ids = [(row.get("assignment_id") or "").strip() for row in rows]
        add_check(
            errors,
            not duplicate_values(rows, "assignment_id"),
            f"{name} contains duplicate assignment responses",
        )
        expected_ids = {
            assignment_id
            for assignment_id, row in assignments_by_id.items()
            if (row.get("arm") or "").strip() == arm
        }
        add_check(
            errors,
            set(response_ids) == expected_ids,
            f"{name} does not contain exactly the assigned response IDs",
        )
        for index, row in enumerate(rows, start=2):
            assignment = assignments_by_id.get((row.get("assignment_id") or "").strip())
            if assignment is None:
                continue
            for field in ("claim_id", "source_key", "participant_id", "arm"):
                add_check(
                    errors,
                    (row.get(field) or "").strip()
                    == (assignment.get(field) or "").strip(),
                    f"{name} row {index} disagrees with assignment field {field}",
                )
            add_check(errors, (row.get("arm") or "").strip() == arm, f"{name} arm mismatch")
        validate_completed_response_labels(
            rows,
            "evidence_support_label",
            "comparability_label",
            name,
            errors,
        )

    gold_rows = loaded["gold_responses.csv"]
    add_check(
        errors,
        not duplicate_values(gold_rows, "gold_response_id"),
        "gold response IDs are duplicated",
    )
    gold_by_claim: dict[str, set[str]] = defaultdict(set)
    for row in gold_rows:
        participant_id = (row.get("participant_id") or "").strip()
        claim_id = (row.get("claim_id") or "").strip()
        gold_by_claim[claim_id].add(participant_id)
        add_check(
            errors,
            participant_id in roles.get("gold_expert", set()),
            "gold response participant does not have the gold_expert role",
        )
    claim_ids = {
        (row.get("claim_id") or "").strip()
        for row in loaded["frozen_test_claims.csv"]
    }
    add_check(
        errors,
        set(gold_by_claim) == claim_ids
        and all(len(participants) == 3 for participants in gold_by_claim.values()),
        "gold responses must contain three distinct experts for every claim",
    )
    validate_completed_response_labels(
        gold_rows,
        "evidence_support_label",
        "comparability_label",
        "gold_responses.csv",
        errors,
    )
    registry = load_and_validate_adjudicator_registry(
        root,
        loaded["frozen_test_claims.csv"],
        gold_rows,
        errors,
    )
    validate_adjudicator_response_rows(
        {
            "adjudicator_1": loaded["adjudicator_1_responses.csv"],
            "adjudicator_2": loaded["adjudicator_2_responses.csv"],
        },
        registry,
        roles,
        errors,
    )


def declared_collected_archive_paths(root: Path) -> set[str]:
    corrections_path = root / "review_extraction_corrections.csv"
    if not corrections_path.is_file():
        return set()
    try:
        header, rows = read_csv(corrections_path)
    except (OSError, UnicodeDecodeError, csv.Error):
        return set()
    if header != STAGED_CORRECTION_HEADER:
        return set()
    pattern = re.compile(
        rf"{re.escape(INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY)}/"
        r"srp_[0-9a-f]{24}/composition_v[0-9]{3}\.csv"
    )
    paths = {
        (row.get("invalidated_composition_archive_relative_path") or "").strip()
        for row in rows
    }
    return {
        relative
        for relative in paths
        if pattern.fullmatch(relative) is not None
    }


def iter_manifest_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.as_posix() == "MANIFEST.sha256":
            continue
        if relative.as_posix() == STANDALONE_REVIEWER_MARKER:
            continue
        if any(part in IGNORED_WORKING_DIRECTORIES for part in relative.parts):
            continue
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if path.name.endswith(".new"):
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def validate_portable_package_root(root: Path, errors: list[str]) -> None:
    unauthorized_files: list[str] = []
    unauthorized_directories: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if (
            path.is_file()
            and path.suffix == ".pyc"
            and "__pycache__" in relative.parts
        ):
            continue
        if path.is_dir():
            if relative.parts == ("__pycache__",):
                continue
            unauthorized_directories.append(relative_text)
            continue
        if relative_text == STANDALONE_REVIEWER_MARKER:
            continue
        if relative_text not in PACKAGE_FILE_ALLOWLIST:
            unauthorized_files.append(relative_text)
    add_check(
        errors,
        not unauthorized_files,
        "portable reviewer root contains unauthorized files: "
        f"{sorted(unauthorized_files)}",
    )
    add_check(
        errors,
        not unauthorized_directories,
        "portable reviewer root contains unauthorized directories, including "
        "private metadata or expanded_texts: "
        f"{sorted(unauthorized_directories)}",
    )
    private_template = root / "participant_metadata_private_template.csv"
    if not private_template.exists():
        errors.append("portable reviewer private metadata template is missing")
        return
    header, rows = read_csv(private_template)
    add_check(
        errors,
        header == PRIVATE_PARTICIPANT_HEADER,
        "portable reviewer private metadata template has the wrong schema",
    )
    add_check(
        errors,
        not rows,
        "portable reviewer private metadata template must be strictly header-only",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_csv_row_sha256(
    row: Mapping[str, str], header: Sequence[str]
) -> str:
    payload = {field: (row.get(field) or "") for field in header}
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def write_manifest(root: Path) -> None:
    authorized = set(PACKAGE_FILE_ALLOWLIST) | declared_collected_archive_paths(
        root
    )
    unauthorized = sorted(
        path.relative_to(root).as_posix()
        for path in iter_manifest_files(root)
        if path.relative_to(root).as_posix() not in authorized
    )
    if unauthorized:
        raise ValueError(
            "refusing to manifest unauthorized package files: "
            + ", ".join(unauthorized)
        )
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in iter_manifest_files(root)
    ]
    manifest = root / "MANIFEST.sha256"
    staging = root / "MANIFEST.sha256.new"
    staging.write_text("\n".join(lines) + "\n", encoding="utf-8")
    staging.replace(manifest)


def verify_manifest(root: Path, errors: list[str]) -> None:
    manifest = root / "MANIFEST.sha256"
    if not manifest.exists():
        errors.append("MANIFEST.sha256 is missing")
        return
    expected: dict[str, str] = {}
    for line_number, line in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            errors.append(f"invalid manifest line {line_number}")
            continue
        digest, relative = match.groups()
        if relative in expected:
            errors.append(f"duplicate manifest path: {relative}")
        expected[relative] = digest
    actual_paths = {
        path.relative_to(root).as_posix(): path for path in iter_manifest_files(root)
    }
    authorized = set(PACKAGE_FILE_ALLOWLIST) | declared_collected_archive_paths(
        root
    )
    add_check(
        errors,
        set(actual_paths).issubset(authorized),
        "package root contains unauthorized files",
    )
    add_check(
        errors,
        set(expected) == set(actual_paths),
        "manifest file set does not exactly match package files",
    )
    for relative in sorted(set(expected).intersection(actual_paths)):
        add_check(
            errors,
            sha256_file(actual_paths[relative]) == expected[relative],
            f"manifest hash mismatch: {relative}",
        )


def determine_mode(
    requested: str, loaded: Mapping[str, Sequence[Mapping[str, str]]]
) -> str:
    if requested != "auto":
        return requested
    if not loaded.get("frozen_test_claims.csv"):
        return "prepared"
    if any(loaded.get(name) for name in TEST_RESPONSE_FILES):
        return "collected"
    return "frozen"


def portable_mode_allowed(requested_mode: str) -> bool:
    return requested_mode in {"prepared", "frozen"}


def standalone_reviewer_replacement_self_test(
    root: Path, errors: list[str]
) -> None:
    workspace = root / ".validator_selftest_workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    reviewer_root = workspace / "reviewer_package"
    reviewer_root.mkdir(parents=True)
    try:
        for source in iter_manifest_files(root):
            relative = source.relative_to(root)
            destination = reviewer_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        shutil.copy2(root / "MANIFEST.sha256", reviewer_root / "MANIFEST.sha256")
        (reviewer_root / STANDALONE_REVIEWER_MARKER).write_text(
            "self-test standalone boundary\n", encoding="utf-8"
        )
        passed_fixture = {
            name: (reviewer_root / name).read_bytes()
            for name in (
                "calibration_responses.csv",
                "calibration_summary.json",
                "participant_metadata_public_template.csv",
                "composition_packet_issuance_registry.json",
                "composition_issuance_rows.csv",
                "review_extraction_corrections.csv",
                "coordinator_collection_receipt.json",
            )
        }

        def refresh_empty_adjudicator_registry() -> None:
            _frozen_header, frozen_rows = read_csv(
                reviewer_root / "frozen_test_claims.csv"
            )
            _gold_header, gold_rows = read_csv(
                reviewer_root / "gold_responses.csv"
            )
            registry = expected_adjudicator_registry(
                reviewer_root, frozen_rows, gold_rows
            )
            (reviewer_root / "adjudicator_packet_registry.json").write_text(
                json.dumps(registry, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        def reset_empty_composition_state() -> None:
            (reviewer_root / "composition_issuance_rows.csv").write_bytes(
                csv_bytes(STAGED_ISSUANCE_ROW_HEADER, [])
            )
            (
                reviewer_root / "review_extraction_corrections.csv"
            ).write_bytes(csv_bytes(STAGED_CORRECTION_HEADER, []))
            empty_registry = empty_issuance_registry(
                reviewer_root / "coordinator_packet_registry.json"
            )
            (
                reviewer_root / "composition_packet_issuance_registry.json"
            ).write_text(
                json.dumps(empty_registry, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            zero_receipt = expected_zero_response_receipt(
                reviewer_root,
                reviewer_root / "coordinator_packet_registry.json",
            )
            (
                reviewer_root / "coordinator_collection_receipt.json"
            ).write_text(
                json.dumps(zero_receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        add_check(
            errors,
            not any(
                path.name == "expanded_texts"
                for path in reviewer_root.rglob("*")
            ),
            "standalone reviewer self-test unexpectedly copied expanded_texts",
        )

        portable_process = subprocess.run(
            [
                sys.executable,
                "-B",
                str(reviewer_root / "validate_package.py"),
                "--mode",
                "frozen",
                "--portable",
            ],
            cwd=reviewer_root,
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            portable_result = json.loads(portable_process.stdout)
        except json.JSONDecodeError:
            portable_result = {}
        portable_skips = portable_result.get("external_input_skips", [])
        add_check(
            errors,
            portable_process.returncode == 0
            and portable_result.get("status") == "PASS"
            and portable_result.get("calibration_substate")
            == "calibration_passed_before_test"
            and portable_result.get("formal_test_packet_gate")
            == "OPEN_CALIBRATION_PASSED_NO_TEST_RESPONSES"
            and portable_result.get("calibration_release_eligible") is True
            and portable_result.get("calibration_responses") == 290
            and portable_result.get("formal_response_rows") == 0
            and portable_result.get("state")
            == "composition_issued_no_responses"
            and portable_result.get("coordinator_composition_issuances")
            == 27
            and portable_result.get("coordinator_active_composition_issuances")
            == 27
            and portable_result.get(
                "issued_composition_packet_byte_verification"
            )
            == "NOT_PERFORMED_PORTABLE_INTERNAL_CHAIN_ONLY"
            and isinstance(portable_skips, list)
            and any(
                isinstance(record, dict)
                and record.get("input")
                == "issued participant composition packets"
                and record.get("reason")
                == (
                    "issued participant composition packets not included/not "
                    "byte-verified portable"
                )
                for record in portable_skips
            )
            and portable_result.get("source_replacement_batches") == 2
            and portable_result.get("source_replacement_verification")
            == (
                "frozen internal chain/hash verification; "
                "no full-text regeneration"
            ),
            "standalone two-batch portable frozen validation failed without "
            "expanded_texts",
        )

        frozen_path = reviewer_root / "frozen_test_claims.csv"
        frozen_before = frozen_path.read_bytes()
        frozen_header, frozen_rows = read_csv(frozen_path)

        def require_c0_cell_failure(character: str, codepoint: str) -> None:
            injected_rows = [dict(row) for row in frozen_rows]
            injected_rows[0]["context_before"] += character
            frozen_path.write_bytes(csv_bytes(frozen_header, injected_rows))
            write_manifest(reviewer_root)
            process = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(reviewer_root / "validate_package.py"),
                    "--mode",
                    "frozen",
                    "--portable",
                ],
                cwd=reviewer_root,
                text=True,
                capture_output=True,
                check=False,
            )
            combined = process.stdout + process.stderr
            add_check(
                errors,
                process.returncode != 0
                and f"contains C0 control {codepoint} inside a CSV cell"
                in combined,
                f"standalone self-test did not reject injected {codepoint}",
            )
            frozen_path.write_bytes(frozen_before)
            write_manifest(reviewer_root)

        require_c0_cell_failure("\x00", "U+0000")
        require_c0_cell_failure("\x01", "U+0001")

        collected_process = subprocess.run(
            [
                sys.executable,
                "-B",
                str(reviewer_root / "validate_package.py"),
                "--mode",
                "collected",
                "--portable",
            ],
            cwd=reviewer_root,
            text=True,
            capture_output=True,
            check=False,
        )
        add_check(
            errors,
            collected_process.returncode != 0
            and "--portable is permitted only" in collected_process.stdout,
            "standalone self-test did not reject collected portable mode",
        )

        strict_process = subprocess.run(
            [
                sys.executable,
                "-B",
                str(reviewer_root / "validate_package.py"),
                "--mode",
                "frozen",
            ],
            cwd=reviewer_root,
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            strict_result = json.loads(strict_process.stdout)
        except json.JSONDecodeError:
            strict_result = {}
        strict_errors = strict_result.get("errors", [])
        add_check(
            errors,
            strict_process.returncode != 0
            and isinstance(strict_errors, list)
            and any(
                "replacement expanded text is missing" in str(error)
                or "replacement full-text reconstruction failed" in str(error)
                for error in strict_errors
            ),
            "standalone strict frozen validation did not fail on missing "
            "replacement expanded text",
        )

        manifest_before = (reviewer_root / "MANIFEST.sha256").read_bytes()

        def require_portable_privacy_failure(expected_text: str) -> None:
            process = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(reviewer_root / "validate_package.py"),
                    "--mode",
                    "frozen",
                    "--portable",
                    "--write-manifest",
                ],
                cwd=reviewer_root,
                text=True,
                capture_output=True,
                check=False,
            )
            combined = process.stdout + process.stderr
            add_check(
                errors,
                process.returncode != 0 and expected_text in combined,
                f"portable privacy self-test did not reject {expected_text}",
            )
            add_check(
                errors,
                (reviewer_root / "MANIFEST.sha256").read_bytes()
                == manifest_before,
                "failed portable validation rewrote MANIFEST.sha256",
            )

        private_template = (
            reviewer_root / "participant_metadata_private_template.csv"
        )
        private_template_before = private_template.read_bytes()
        with private_template.open("a", encoding="utf-8", newline="") as handle:
            handle.write(
                "SYNTHETIC-PII,auditor,A,Synthetic Name,"
                "synthetic@example.invalid,,,,,,,,primary,\n"
            )
        require_portable_privacy_failure("strictly header-only")
        private_template.write_bytes(private_template_before)

        expanded_dir = reviewer_root / "expanded_texts"
        expanded_dir.mkdir()
        (expanded_dir / "synthetic.txt").write_text(
            "synthetic privacy regression fixture\n", encoding="utf-8"
        )
        require_portable_privacy_failure("unauthorized directories")
        shutil.rmtree(expanded_dir)

        archive_dir = (
            reviewer_root / INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY
        )
        archive_dir.mkdir()
        (archive_dir / "synthetic.csv").write_text(
            "response_status\ncompleted\n", encoding="utf-8"
        )
        require_portable_privacy_failure("unauthorized directories")
        shutil.rmtree(archive_dir)

        unexpected = reviewer_root / "unexpected_private_metadata.csv"
        unexpected.write_text(
            "legal_name,email\nSynthetic,synthetic@example.invalid\n",
            encoding="utf-8",
        )
        require_portable_privacy_failure("unauthorized files")
        unexpected.unlink()

        items = read_calibration_items(reviewer_root / "calibration_items.csv")
        key = read_calibration_key(
            reviewer_root / "calibration_answer_key.csv", items
        )
        public_header, passed_public_rows = read_csv(
            reviewer_root / "participant_metadata_public_template.csv"
        )
        awaiting_public_rows: list[dict[str, str]] = []
        for source in passed_public_rows:
            row = dict(source)
            row["calibration_status"] = "awaiting_calibration"
            row["included_in_primary_analysis"] = "false"
            awaiting_public_rows.append(row)
        response_payload = csv_bytes(CALIBRATION_RESPONSE_HEADER, [])
        public_payload = csv_bytes(public_header, awaiting_public_rows)
        (reviewer_root / "calibration_responses.csv").write_bytes(
            response_payload
        )
        (
            reviewer_root / "participant_metadata_public_template.csv"
        ).write_bytes(public_payload)
        awaiting_states = {
            row["participant_id"]: "awaiting_calibration"
            for row in awaiting_public_rows
        }
        awaiting_details = {
            row["participant_id"]: [] for row in awaiting_public_rows
        }
        awaiting_summary = build_calibration_summary(
            items=items,
            key=key,
            public_rows=awaiting_public_rows,
            states=awaiting_states,
            details=awaiting_details,
            packet_hashes={},
            response_bytes=response_payload,
            public_bytes=public_payload,
            items_path=reviewer_root / "calibration_items.csv",
            key_path=reviewer_root / "calibration_answer_key.csv",
            materials_path=reviewer_root / "calibration_materials.md",
        )
        (reviewer_root / "calibration_summary.json").write_text(
            json.dumps(awaiting_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        reset_empty_composition_state()
        refresh_empty_adjudicator_registry()
        write_manifest(reviewer_root)
        awaiting_process = subprocess.run(
            [
                sys.executable,
                "-B",
                str(reviewer_root / "validate_package.py"),
                "--mode",
                "frozen",
                "--portable",
            ],
            cwd=reviewer_root,
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            awaiting_result = json.loads(awaiting_process.stdout)
        except json.JSONDecodeError:
            awaiting_result = {}
        add_check(
            errors,
            awaiting_process.returncode == 0
            and awaiting_result.get("status") == "PASS"
            and awaiting_result.get("calibration_substate") == "awaiting"
            and awaiting_result.get("formal_test_packet_gate")
            == "CLOSED_AWAITING_CALIBRATION"
            and awaiting_result.get("calibration_release_eligible") is False
            and awaiting_result.get("calibration_responses") == 0
            and awaiting_result.get("formal_response_rows") == 0,
            "standalone awaiting-calibration portable validation failed",
        )

        for name, payload in passed_fixture.items():
            (reviewer_root / name).write_bytes(payload)
        refresh_empty_adjudicator_registry()
        ledger_header, fabricated_rows = read_csv(
            reviewer_root / "calibration_responses.csv"
        )
        fabricated_rows[0]["calibration_response_id"] = "cal_" + "0" * 24
        (reviewer_root / "calibration_responses.csv").write_bytes(
            csv_bytes(ledger_header, fabricated_rows)
        )
        fabricated_summary = json.loads(
            (reviewer_root / "calibration_summary.json").read_text(
                encoding="utf-8"
            )
        )
        fabricated_summary["calibration_responses_sha256"] = sha256_file(
            reviewer_root / "calibration_responses.csv"
        )
        (reviewer_root / "calibration_summary.json").write_text(
            json.dumps(fabricated_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_manifest(reviewer_root)
        fabricated_process = subprocess.run(
            [
                sys.executable,
                "-B",
                str(reviewer_root / "validate_package.py"),
                "--mode",
                "frozen",
                "--portable",
            ],
            cwd=reviewer_root,
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            fabricated_result = json.loads(fabricated_process.stdout)
        except json.JSONDecodeError:
            fabricated_result = {}
        fabricated_errors = fabricated_result.get("errors", [])
        add_check(
            errors,
            fabricated_process.returncode != 0
            and isinstance(fabricated_errors, list)
            and any(
                "changed immutable field calibration_response_id" in str(error)
                for error in fabricated_errors
            ),
            "standalone portable validation accepted a fabricated ledger",
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def portable_self_test(root: Path) -> None:
    config = json.loads((root / "study_config.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    skips: list[dict[str, str]] = []
    absent_root = root / ".portable-self-test-inputs-not-present"
    development_keys, development_titles = validate_development_sources(
        root,
        config,
        errors,
        portable=True,
        external_input_skips=skips,
        provenance_path=absent_root / "validation_pair_provenance.csv",
        v2_title_path=absent_root / "human_final_consensus.csv",
    )
    loaded = validate_headers_and_load(root, errors)
    current_mode = determine_mode("auto", loaded)
    prepared_pool_files = {
        "source_sampling_frame.csv",
        "candidate_claims_deterministic.csv",
        "candidate_claims_model_prescreen.csv",
        "sampling_exclusion_replacement_ledger.csv",
        "source_replacement_exclusions.csv",
        "calibration_items.csv",
        "calibration_answer_key.csv",
    }
    if current_mode == "prepared":
        for name in EXPECTED_HEADERS:
            if name not in prepared_pool_files:
                add_check(
                    errors,
                    not loaded.get(name, []),
                    f"portable self-test found prepared-state leakage in {name}",
                )
    validate_prepared_candidate_pool(
        root,
        loaded,
        config,
        development_keys,
        development_titles,
        errors,
        portable=True,
        external_input_skips=skips,
        map_path_override=absent_root / "map.csv",
    )
    calibration_info = validate_calibration_workflow(
        root,
        loaded,
        config,
        root / "participant_metadata_public_template.csv",
        root / "calibration_summary.json",
        errors,
    )
    if current_mode == "frozen":
        record_portable_private_verification_skip(skips)
        public_path = root / "participant_metadata_public_template.csv"
        validate_frozen_design(
            root,
            loaded,
            None,
            config,
            development_keys,
            development_titles,
            errors,
            portable_public=True,
            public_participant_path=public_path,
        )
        validate_portable_frozen_pretest_state(
            loaded,
            calibration_info,
            root / "calibration_summary.json",
            errors,
        )
        public_header, public_rows = read_csv(public_path)
        private_probe = [dict(row) for row in public_rows]
        mismatched_gold = next(
            row
            for row in private_probe
            if (row.get("role") or "").strip().lower() == "gold_expert"
        )
        mismatched_gold["participant_id"] = "GLD-FFFFFFFFFFFF"
        binding_probe_errors: list[str] = []
        validate_private_public_participant_binding(
            private_probe, public_path, binding_probe_errors
        )
        add_check(
            errors,
            any(
                "participant ID sets differ" in error
                for error in binding_probe_errors
            ),
            "strict binding self-test did not reject a mismatched gold ID",
        )
        pii_probe_errors: list[str] = []
        validate_public_frozen_participant_rows(
            (*public_header, "email"),
            public_rows,
            pii_probe_errors,
        )
        add_check(
            errors,
            any("PII" in error for error in pii_probe_errors),
            "portable frozen self-test did not reject a PII-bearing roster schema",
        )
        if (root / "generated_calibration_packets").is_dir():
            full_root_probe_errors: list[str] = []
            validate_portable_package_root(root, full_root_probe_errors)
            add_check(
                errors,
                any(
                    "unauthorized directories" in error
                    and "generated_calibration_packets" in error
                    for error in full_root_probe_errors
                ),
                "portable full-root self-test did not reject generated packets",
            )
        standalone_reviewer_replacement_self_test(root, errors)
    adjudicator_integrity_self_test(errors)
    verify_manifest(root, errors)
    skipped_inputs = {record["input"] for record in skips}
    required_skips = {
        PROVENANCE_RELATIVE_PATH,
        V2_TITLE_RELATIVE_PATH,
        MAP_RELATIVE_PATH,
        EXPANDED_TEXT_RELATIVE_PATH,
    }
    if current_mode == "frozen":
        required_skips.add(PRIVATE_PARTICIPANT_VERIFICATION_INPUT)
    add_check(
        errors,
        required_skips.issubset(skipped_inputs),
        "portable self-test did not exercise every external-input fallback",
    )
    add_check(
        errors,
        portable_mode_allowed("prepared")
        and portable_mode_allowed("frozen")
        and not portable_mode_allowed("auto")
        and not portable_mode_allowed("collected"),
        "portable mode guard self-test failed",
    )
    if errors:
        raise AssertionError("portable self-test failed:\n- " + "\n- ".join(errors))
    print(
        "self-test passed; public frozen validation read no private metadata, "
        "external texts, or test labels"
    )


def validate_minimized_reviewer_package(root: Path) -> list[str]:
    errors: list[str] = []
    files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    missing = sorted(REVIEWER_REQUIRED_PUBLIC_FILES - files)
    add_check(errors, not missing, f"reviewer public files missing: {missing}")
    leaked_names = sorted(
        relative
        for relative in files
        if Path(relative).name in REVIEWER_PRIVATE_BASENAMES
    )
    add_check(
        errors,
        not leaked_names,
        f"private v3 artifacts present in reviewer package: {leaked_names}",
    )
    verify_manifest(root, errors)

    private_fields = {"participant_id", "legal_name", "email"}
    private_reason = re.compile(r"(?:^|_)(?:reason|rationale)(?:$|_)")
    private_timestamp = re.compile(
        r"(?:^|_)(?:start|started|completion|completed)(?:$|_)"
    )

    def inspect_field(field: str, relative: str) -> None:
        normalized = field.strip().lower()
        if normalized in {"missing_reason_code", "exclusion_reason_code"}:
            return
        if (
            relative == "source_sampling_frame.csv"
            and normalized == "exclusion_reason_detail"
        ):
            return
        if relative == "power_analysis.json" and normalized == "reason":
            return
        if (
            normalized in private_fields
            or private_reason.search(normalized)
            or private_timestamp.search(normalized)
        ):
            errors.append(f"private v3 field {field!r} in {relative}")

    def inspect_json(item: object, relative: str) -> None:
        if isinstance(item, dict):
            for key, value in item.items():
                inspect_field(str(key), relative)
                inspect_json(value, relative)
        elif isinstance(item, list):
            for value in item:
                inspect_json(value, relative)
        elif isinstance(item, str):
            match = ORIGINAL_PARTICIPANT_ID_SEARCH_RE.search(item)
            if match:
                errors.append(
                    f"original participant ID {match.group(0)} in {relative}"
                )

    for relative in sorted(files):
        path = root / relative
        if path.suffix.lower() in {".py", ".md"}:
            continue
        try:
            if path.suffix.lower() == ".csv":
                header, rows = read_csv(path)
                for field in header:
                    inspect_field(field, relative)
                for row in rows:
                    for value in row.values():
                        match = ORIGINAL_PARTICIPANT_ID_SEARCH_RE.search(value)
                        if match:
                            errors.append(
                                f"original participant ID {match.group(0)} "
                                f"in {relative}"
                            )
            elif path.suffix.lower() == ".json":
                inspect_json(json.loads(path.read_text(encoding="utf-8")), relative)
            else:
                match = ORIGINAL_PARTICIPANT_ID_SEARCH_RE.search(
                    path.read_text(encoding="utf-8")
                )
                if match:
                    errors.append(
                        f"original participant ID {match.group(0)} in {relative}"
                    )
        except (OSError, UnicodeDecodeError, csv.Error, json.JSONDecodeError) as exc:
            errors.append(f"cannot inspect reviewer artifact {relative}: {exc}")

    try:
        frozen_header, frozen_rows = read_csv(root / "frozen_test_claims.csv")
        calibration_header, calibration_rows = read_csv(
            root / "calibration_items.csv"
        )
        add_check(
            errors,
            frozen_header == FROZEN_CLAIM_HEADER and len(frozen_rows) == 480,
            "reviewer frozen claim frame is not the 480-row frozen cohort",
        )
        add_check(
            errors,
            calibration_header == CALIBRATION_ITEM_HEADER
            and len(calibration_rows) == CALIBRATION_ITEM_COUNT,
            "reviewer calibration items are not the frozen fictional set",
        )
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        errors.append(f"cannot validate reviewer frozen frames: {exc}")
    return errors


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--mode",
        choices=("auto", "prepared", "frozen", "collected"),
        default="auto",
    )
    parser.add_argument(
        "--participant-metadata",
        type=Path,
        default=root / "participant_metadata_private_template.csv",
        help="filled private metadata for strict frozen/collected validation; "
        "never read by portable frozen mode",
    )
    parser.add_argument(
        "--public-participant-metadata",
        type=Path,
        default=root / "participant_metadata_public_template.csv",
        help="exact non-PII roster used by calibration and portable frozen checks",
    )
    parser.add_argument(
        "--calibration-summary",
        type=Path,
        default=root / "calibration_summary.json",
        help="item-level calibration summary paired with the public roster",
    )
    parser.add_argument(
        "--composition-packets-root",
        type=Path,
        help="strict frozen byte-verification root for coordinator-issued "
        "stage-2 participant packets; never bundled or read in portable mode",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="write MANIFEST.sha256 only after all non-manifest checks pass",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="public prepared/frozen reviewer validation; never collected/PII",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="exercise portable missing-input validation without writing files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if args.self_test:
        portable_self_test(root)
        return 0
    if args.portable and not portable_mode_allowed(args.mode):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "errors": [
                        "--portable is permitted only with explicit "
                        "--mode prepared or --mode frozen"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    if args.portable and args.composition_packets_root is not None:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "errors": [
                        "--composition-packets-root is forbidden with "
                        "--portable; portable validation verifies only the "
                        "internal issuance chain"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    if (root / STANDALONE_REVIEWER_MARKER).is_file():
        if not args.portable or args.mode != "frozen":
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "errors": [
                            "privacy-minimized reviewer packages require "
                            "--mode frozen --portable"
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        reviewer_errors = validate_minimized_reviewer_package(root)
        if reviewer_errors:
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "mode": "frozen",
                        "portable": True,
                        "errors": reviewer_errors,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "mode": "frozen",
                    "portable": True,
                    "privacy_minimized_reviewer_package": True,
                    "frozen_claims": 480,
                    "manifest": "verified",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    errors: list[str] = []
    external_input_skips: list[dict[str, str]] = []
    if args.portable and args.mode == "frozen":
        validate_portable_package_root(root, errors)
    (
        config,
        development_source_keys,
        development_normalized_titles,
    ) = validate_pre_registration_files(
        root,
        errors,
        args.portable,
        external_input_skips,
    )
    loaded = validate_headers_and_load(root, errors)
    if set(loaded) != set(EXPECTED_HEADERS):
        failure: dict[str, Any] = {
            "status": "FAIL",
            "portable": args.portable,
            "errors": errors,
        }
        if args.portable:
            failure["external_input_skips"] = external_input_skips
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 1
    mode = determine_mode(args.mode, loaded)
    if args.portable and mode == "frozen":
        record_portable_private_verification_skip(external_input_skips)
    expected_sample_status = (
        "FROZEN_NO_TEST_LABELS"
        if mode in {"frozen", "collected"}
        else "PREPARED_NO_TEST_FREEZE"
    )
    add_check(
        errors,
        config.get("test_sample_status") == expected_sample_status,
        f"study config test_sample_status is not {expected_sample_status}",
    )

    summary: dict[str, Any] = {
        "mode": mode,
        "portable": args.portable,
        "development_source_exclusions": len(development_source_keys),
        "development_title_exclusions": len(development_normalized_titles),
    }
    if args.portable:
        summary["external_input_skips"] = external_input_skips
    calibration_info = validate_calibration_workflow(
        root,
        loaded,
        config,
        args.public_participant_metadata.resolve(),
        args.calibration_summary.resolve(),
        errors,
    )
    summary.update(calibration_info)
    if mode == "prepared":
        prepared_pool_files = {
            "source_sampling_frame.csv",
            "candidate_claims_deterministic.csv",
            "candidate_claims_model_prescreen.csv",
            "sampling_exclusion_replacement_ledger.csv",
            "source_replacement_exclusions.csv",
            "calibration_items.csv",
            "calibration_answer_key.csv",
        }
        for name in EXPECTED_HEADERS:
            if name in prepared_pool_files:
                continue
            add_check(
                errors,
                not loaded.get(name, []),
                f"prepared package must keep {name} header-only",
            )
        summary.update(
            validate_prepared_candidate_pool(
                root,
                loaded,
                config,
                development_source_keys,
                development_normalized_titles,
                errors,
                args.portable,
                external_input_skips,
            )
        )
        freeze_attempt_path = root / "sampling_freeze_summary.json"
        if freeze_attempt_path.exists():
            try:
                freeze_attempt = json.loads(
                    freeze_attempt_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError as exc:
                errors.append(f"cannot read sampling freeze attempt: {exc}")
                freeze_attempt = {}
            add_check(
                errors,
                freeze_attempt.get("status")
                == "REPLACEMENT_REQUIRED_NO_TEST_FREEZE"
                and freeze_attempt.get("replacement_required") is True
                and freeze_attempt.get("claims") == 0
                and freeze_attempt.get("sources") == 0
                and freeze_attempt.get("frozen_claims_sha256") == "",
                "prepared replacement state has an invalid freeze-attempt summary",
            )
            try:
                replacement_summary = json.loads(
                    (root / "source_replacement_summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                replacement_parent = replacement_summary["batches"][-1][
                    "parent"
                ]
            except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError):
                replacement_parent = {}
            add_check(
                errors,
                freeze_attempt.get("sampling_screen_summary_sha256")
                == replacement_parent.get("sampling_screen_summary_sha256"),
                "freeze-attempt summary does not anchor parent screening state",
            )
        summary["frozen_claims"] = 0
        summary["test_response_rows"] = 0
    else:
        if args.portable:
            summary["portable_candidate_pool"] = validate_prepared_candidate_pool(
                root,
                loaded,
                config,
                development_source_keys,
                development_normalized_titles,
                errors,
                True,
                external_input_skips,
            )
        if args.portable:
            summary.update(
                validate_frozen_design(
                    root,
                    loaded,
                    None,
                    config,
                    development_source_keys,
                    development_normalized_titles,
                    errors,
                    portable_public=True,
                    public_participant_path=(
                        args.public_participant_metadata.resolve()
                    ),
                )
            )
            summary.update(
                validate_portable_frozen_pretest_state(
                    loaded,
                    calibration_info,
                    args.calibration_summary.resolve(),
                    errors,
                )
            )
        else:
            summary.update(
                validate_frozen_design(
                    root,
                    loaded,
                    args.participant_metadata.resolve(),
                    config,
                    development_source_keys,
                    development_normalized_titles,
                    errors,
                    public_participant_path=(
                        args.public_participant_metadata.resolve()
                    ),
                )
            )
        if mode == "frozen":
            try:
                summary.update(
                    validate_frozen_coordinator_state(
                        root,
                        composition_packets_root=(
                            args.composition_packets_root.resolve()
                            if args.composition_packets_root is not None
                            else None
                        ),
                        portable=args.portable,
                    )
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(
                    f"frozen coordinator staged state validation failed: {exc}"
                )
            try:
                adjudicator_registry = load_and_validate_adjudicator_registry(
                    root,
                    loaded["frozen_test_claims.csv"],
                    loaded["gold_responses.csv"],
                    errors,
                )
                add_check(
                    errors,
                    adjudicator_registry["status"]
                    == "NO_ADJUDICATOR_PACKETS_ISSUED"
                    and adjudicator_registry["packet_count"] == 0
                    and adjudicator_registry["row_count"] == 0,
                    "frozen mode contains an issued adjudicator packet registry",
                )
                summary["coordinator_adjudicator_packets"] = 0
                summary["coordinator_adjudication_rows"] = 0
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(
                    f"frozen adjudicator registry validation failed: {exc}"
                )
            for name in TEST_RESPONSE_FILES:
                add_check(
                    errors,
                    not loaded.get(name, []),
                    f"test-label leakage: frozen mode requires {name} to be header-only",
                )
            add_check(
                errors,
                not loaded.get("coordinator_response_receipts.csv", []),
                "frozen mode requires the coordinator response-receipt "
                "ledger to be header-only",
            )
            if (
                args.portable
                and summary.get("composition_substate")
                == "composition_issued_no_responses"
            ):
                record_external_skip(
                    external_input_skips,
                    "issued participant composition packets",
                    "issued participant composition packets not included/not "
                    "byte-verified portable",
                    "internal issuance registry, issuance rows, correction "
                    "chain, active packet coverage, and zero-response state "
                    "verified; participant packet bytes NOT VERIFIED",
                )
                if summary.get("coordinator_corrections", 0):
                    record_external_skip(
                        external_input_skips,
                        "invalidated participant composition archives",
                        "pre-response correction archives not included/not "
                        "byte-verified portable",
                        "correction ledger and issuance-registry archive "
                        "path/SHA anchors verified; archive bytes NOT VERIFIED",
                    )
            summary["test_response_rows"] = 0
            if (
                summary.get("composition_substate")
                == "composition_issued_no_responses"
            ):
                add_check(
                    errors,
                    bool(calibration_info["calibration_release_eligible"]),
                    "composition issuance is forbidden before itemized "
                    "calibration passes",
                )
                summary["state"] = "composition_issued_no_responses"
            elif calibration_info["calibration_release_eligible"]:
                summary["state"] = (
                    "frozen_calibration_passed_before_composition_issuance"
                )
            else:
                summary["composition_substate"] = (
                    "awaiting_calibration_before_composition_issuance"
                )
                summary["state"] = "frozen_awaiting_itemized_calibration"
        else:
            add_check(
                errors,
                bool(calibration_info["calibration_release_eligible"]),
                "collected mode is forbidden until all 29 participants have "
                "itemized passing calibration records",
            )
            validate_collected_data(
                root,
                loaded,
                args.participant_metadata.resolve(),
                errors,
            )
            summary["test_response_rows"] = sum(
                len(loaded.get(name, [])) for name in TEST_RESPONSE_FILES
            )
            summary["state"] = "collected_data_validated"

    if not errors and args.write_manifest:
        try:
            write_manifest(root)
        except ValueError as exc:
            errors.append(str(exc))
    if not args.write_manifest or not errors:
        verify_manifest(root, errors)

    if errors:
        failure = {
            "status": "FAIL",
            "mode": mode,
            "portable": args.portable,
            "errors": errors,
        }
        if args.portable:
            failure["external_input_skips"] = external_input_skips
        print(
            json.dumps(
                failure,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    summary["status"] = "PASS"
    summary["manifest"] = "verified"
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
