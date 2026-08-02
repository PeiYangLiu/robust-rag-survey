#!/usr/bin/env python3
"""Build the minimal reviewer-facing data package."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


V3_ROOT = "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
PUBLIC_V3_ROOT = "manuscript/supplement/v3_human_reanalysis_20260725/"
ORIGINAL_PARTICIPANT_ID_RE = re.compile(r"\b(?:AUD|GLD|ADJ)-[0-9A-F]{12}\b")
PRIVATE_V3_ARTIFACT_BASENAMES = {
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
    "candidate_claims_model_prescreen.csv",
    "composition_issuance_rows.csv",
    "composition_packet_issuance_registry.json",
    "coordinator_collection_receipt.json",
    "coordinator_packet_registry.json",
    "coordinator_response_receipts.csv",
    "gold_responses.csv",
    "participant_metadata_private_template.csv",
    "participant_metadata_public_template.csv",
    "review_extraction_corrections.csv",
    "sampling_exclusion_replacement_ledger.csv",
    "sampling_screen_response_template.csv",
    "sampling_screener_provenance.json",
    "source_replacement_exclusions.csv",
}
PRIVATE_FIELD_NAMES = {"participant_id", "legal_name", "email"}
PRIVATE_FREE_TEXT_FIELD_RE = re.compile(r"(?:^|_)(?:reason|rationale)(?:$|_)")
PRIVATE_TIMESTAMP_FIELD_RE = re.compile(
    r"(?:^|_)(?:start|started|completion|completed)(?:$|_)"
)
ALLOWED_CATEGORICAL_REASON_FIELDS = {
    "missing_reason_code",
    "exclusion_reason_code",
}
ALLOWED_NONPARTICIPANT_DESIGN_FIELDS = {
    "exclusion_reason_detail",
}
ALLOWED_NONPARTICIPANT_REASON_FIELDS = {
    f"{V3_ROOT}power_analysis.json": {"reason"},
    f"{V3_ROOT}source_sampling_frame.csv": ALLOWED_NONPARTICIPANT_DESIGN_FIELDS,
}
PUBLIC_PARTICIPANT_SCHEMAS = {
    "public_arm_ratings.csv": {
        "claim_id",
        "source_key",
        "release_participant_id",
        "arm",
        "role",
        "response_status",
        "missing_reason_code",
        "evidence_support_label",
        "comparability_label",
    },
    "public_gold_ratings.csv": {
        "claim_id",
        "source_key",
        "release_participant_id",
        "arm",
        "role",
        "response_status",
        "missing_reason_code",
        "evidence_support_label",
        "comparability_label",
    },
    "public_adjudications.csv": {
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
    },
}


PUBLIC_V3_FILES: tuple[str, ...] = ()


FILES = (
    "LICENSE",
    "DATA_LICENSE.md",
    "manuscript/supplement/RELEASE_VERSION.txt",
    "manuscript/supplement/evidence_map_venue_expanded_adjudicated.csv",
    "manuscript/supplement/corpus_snapshot.json",
    "manuscript/supplement/taxonomy_codebook.csv",
    "manuscript/supplement/search_protocol.json",
    "manuscript/supplement/search_source_ledger.csv",
    "manuscript/supplement/screening_provenance.csv",
    "manuscript/supplement/exclusion_log.csv",
    "manuscript/supplement/post_freeze_recall_audit.csv",
    "manuscript/supplement/prisma_scr_checklist.csv",
    "manuscript/supplement/observed_comparison_claim_audit.csv",
    "manuscript/supplement/observed_comparison_claim_audit_summary.json",
    "manuscript/supplement/observed_claim_audit_codebook.md",
    "manuscript/supplement/observed_claim_audit_codebook_v3_draft.md",
    "manuscript/supplement/observed_claim_audit_protocol.md",
    "manuscript/supplement/observed_claim_audit_corrections.csv",
    "manuscript/supplement/observed_claim_audit_corrections_manifest.json",
    "manuscript/supplement/observed_claim_source_manifest.json",
    "manuscript/supplement/claim_rule_reliability.csv",
    "manuscript/supplement/claim_rule_reliability_by_archetype.csv",
    "manuscript/supplement/human_validation_sampling_audit.csv",
    "manuscript/supplement/validation_pair_provenance.csv",
    "manuscript/supplement/human_validation_field_agreement_summary.csv",
    "manuscript/supplement/claim_error_type_audit.csv",
    "manuscript/supplement/claim_reliability_summary.json",
    "manuscript/supplement/claim_rule_predictions.csv",
    "manuscript/supplement/claim_rule_cluster_intervals.csv",
    "manuscript/supplement/claim_source_sensitivity.csv",
    "manuscript/supplement/claim_reference_sensitivity.csv",
    "manuscript/supplement/model_human_field_alignment.csv",
    "manuscript/supplement/claim_archetype_cluster_intervals.csv",
    "manuscript/supplement/claim_source_sensitivity_summary.json",
    "manuscript/supplement/cross_paper_comparability_cases.csv",
    "manuscript/supplement/cross_paper_comparability_cases.json",
    "manuscript/supplement/cross_paper_comparability_cases_summary.json",
    "manuscript/supplement/cross_paper_comparability_cases_codebook.md",
    "manuscript/supplement/cross_paper_comparability_cases_report.md",
    "manuscript/supplement/reviewer_heterogeneity_anchor.json",
    "manuscript/supplement/retrospective_remedy_simulation.json",
    "manuscript/supplement/claim_rule_baselines.json",
    "manuscript/supplement/controlled_claim_audit_benchmark_v2.jsonl",
    "manuscript/supplement/controlled_claim_audit_benchmark_v2_summary.json",
    "manuscript/supplement/controlled_claim_audit_benchmark_v2_protocol.md",
    "manuscript/supplement/controlled_model_judge_results_v2.json",
    "manuscript/supplement/controlled_model_judge_results_v2.csv",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen25-7b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen25-7b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen25-14b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen25-14b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen3-8b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen3-8b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen3-14b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/qwen3-14b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/phi-4-mini.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/phi-4-mini-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/olmo2-7b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/olmo2-7b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/olmo2-13b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/olmo2-13b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/granite-31-8b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/granite-31-8b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw_v2/falcon3-7b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw_v2/falcon3-7b-summary.json",
    "manuscript/supplement/assignment_mismatch_simulation.json",
    "manuscript/supplement/controlled_claim_audit_benchmark.jsonl",
    "manuscript/supplement/controlled_claim_audit_benchmark_summary.json",
    "manuscript/supplement/controlled_claim_audit_benchmark_protocol.md",
    "manuscript/supplement/controlled_model_judge_results.json",
    "manuscript/supplement/controlled_model_judge_results.csv",
    "manuscript/supplement/controlled_model_judge_raw/qwen2.5-7b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw/qwen2.5-7b-summary.json",
    "manuscript/supplement/controlled_model_judge_raw/phi-4-mini.jsonl",
    "manuscript/supplement/controlled_model_judge_raw/phi-4-mini-summary.json",
    "manuscript/supplement/controlled_model_judge_raw/olmo-2-7b.jsonl",
    "manuscript/supplement/controlled_model_judge_raw/olmo-2-7b-summary.json",
    "manuscript/supplement/published_human_evaluation_audit.json",
    "manuscript/supplement/published_human_evaluation_screen_manifest.csv",
    "manuscript/supplement/published_human_evaluation_audit_summary.json",
    "manuscript/supplement/claim_audit_components/general_candidates.csv",
    "manuscript/supplement/claim_audit_components/general_adjudicated_structured.csv",
    "manuscript/supplement/claim_audit_components/action_candidates.csv",
    "manuscript/supplement/claim_audit_components/action_adjudicated_structured.csv",
    "manuscript/supplement/claim_audit_components/threat_candidates.csv",
    "manuscript/supplement/claim_audit_components/threat_adjudicated_structured.csv",
    "manuscript/supplement/bibliography_integrity_report.csv",
    "manuscript/supplement/bibliography_integrity_summary.json",
    "manuscript/scripts/build_observed_claim_audit.py",
    "manuscript/scripts/derive_observed_claim_verdicts.py",
    "manuscript/scripts/analyze_claim_rule_reliability.py",
    "manuscript/scripts/analyze_claim_source_sensitivity.py",
    "manuscript/scripts/simulate_assignment_unit_mismatch.py",
    "manuscript/scripts/build_controlled_claim_audit_benchmark.py",
    "manuscript/scripts/run_controlled_model_judges.py",
    "manuscript/scripts/analyze_controlled_model_judges.py",
    "manuscript/scripts/analyze_published_human_evaluation_audit.py",
    "manuscript/scripts/rerun_recoverable_search.py",
    "manuscript/scripts/verify_bibliography_integrity.py",
    "files/v3_invalidated_shared_answer_run_20260719/invalidation_report.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/README_REVIEWER_PACKAGE.md",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/.gitignore",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/preregistered_protocol.md",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/codebook_v3_frozen.md",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/study_config.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/power_analysis.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/power_analysis.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_development_source_keys.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/DEVELOPMENT_SOURCE_KEYS.txt",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/DEVELOPMENT_SOURCES.csv",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/prepare_candidate_pool.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/source_sampling_frame.csv",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/candidate_claims_deterministic.csv",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/candidate_pool_summary.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_sampling_screen_packets.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/sampling_screen_summary.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/sampling_screen_summary_schema.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/apply_source_replacements.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/source_replacement_summary.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/source_replacement_summary_schema.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/freeze_human_sample.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/sampling_freeze_summary_schema.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/sampling_freeze_summary.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/frozen_test_claims.csv",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_assignments.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_items.csv",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_answer_key.csv",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_materials.md",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_calibration_packets.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/score_calibration.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/frozen_text_corrections.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/staged_review_core.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/staged_review_schema.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_staged_review_packets.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/issue_composition_packets.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/collect_final_responses.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_review_packets.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_offline_analysis_release.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/analyze_collected_results.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/analysis_output_schema.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/poststudy_analysis_addendum.md",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/validate_package.py",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/annotator_A_claims_completed.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/annotator_B_claims_completed.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/annotator_C_claims_completed.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/adjudicated_consensus.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/sample_key.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/human_annotation_provenance.json",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/human_validation_report.md",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/pre_adjudication/pairwise_agreement.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/pre_adjudication/majority_consensus.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/final/human_final_consensus.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/final/human_validation_summary.json",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/final/human_vs_model_confusion.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/final/human_vs_model_per_class.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/human_validation_protocol.md",
    "manuscript/human_coding/observed_claim_human_validation_20260714/analysis/analyze_human_annotations.py",
    "manuscript/human_coding/observed_claim_human_validation_20260714/analysis/finalize_human_validation.py",
) + PUBLIC_V3_FILES
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_private_field(name: str, archive_name: str) -> bool:
    normalized = name.strip().lower()
    if normalized in PRIVATE_FIELD_NAMES:
        return True
    if normalized in ALLOWED_CATEGORICAL_REASON_FIELDS:
        return False
    if normalized in ALLOWED_NONPARTICIPANT_REASON_FIELDS.get(archive_name, set()):
        return False
    return bool(
        PRIVATE_FREE_TEXT_FIELD_RE.search(normalized)
        or PRIVATE_TIMESTAMP_FIELD_RE.search(normalized)
    )


def json_fields_and_values(value: object) -> tuple[list[str], list[str]]:
    fields: list[str] = []
    values: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                fields.append(str(key))
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)
        elif isinstance(item, str):
            values.append(item)

    visit(value)
    return fields, values


def validate_v3_data_entry(archive_name: str, data: bytes) -> None:
    if not archive_name.startswith((V3_ROOT, PUBLIC_V3_ROOT)):
        return
    suffix = Path(archive_name).suffix.lower()
    if suffix in {".py", ".md"}:
        return

    fields: list[str] = []
    values: list[str] = []
    text = data.decode("utf-8-sig")
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        fields = list(reader.fieldnames or ())
        rows = list(reader)
        values = [value for row in rows for value in row.values() if value]
        basename = Path(archive_name).name
        if basename in PUBLIC_PARTICIPANT_SCHEMAS:
            expected = PUBLIC_PARTICIPANT_SCHEMAS[basename]
            if set(fields) != expected:
                raise ValueError(
                    f"unexpected public participant schema in {archive_name}"
                )
    elif suffix == ".json":
        fields, values = json_fields_and_values(json.loads(text))
    else:
        values = [text]

    forbidden = sorted(
        {field for field in fields if is_private_field(field, archive_name)}
    )
    if forbidden:
        raise ValueError(
            f"private v3 field(s) in {archive_name}: {', '.join(forbidden)}"
        )
    for value in values:
        match = ORIGINAL_PARTICIPANT_ID_RE.search(value)
        if match:
            raise ValueError(
                f"original participant ID {match.group(0)} in {archive_name}"
            )


def validate_file(path: Path) -> None:
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            next(csv.reader(handle))
    elif path.suffix == ".json":
        json.loads(path.read_text(encoding="utf-8"))


def add_bytes(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(2026, 7, 15, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    output = repo / "manuscript" / "review_data_package.zip"
    subprocess.run(
        [
            sys.executable,
            "manuscript/scripts/analyze_published_human_evaluation_audit.py",
        ],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            sys.executable,
            "manuscript/scripts/analyze_controlled_model_judges.py",
            "--input",
            "manuscript/supplement/controlled_model_judge_raw/qwen2.5-7b.jsonl",
            "--input",
            "manuscript/supplement/controlled_model_judge_raw/phi-4-mini.jsonl",
            "--input",
            "manuscript/supplement/controlled_model_judge_raw/olmo-2-7b.jsonl",
        ],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    paths = [repo / relative for relative in FILES]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        validate_file(path)

    readme = """# Minimal reviewer data package

This package contains only data and code directly used by the paper:

1. the 342-row literature map and search/source ledgers;
2. the 289-claim model-generated index, frozen codebook, post-study redesign,
   source manifest, and deterministic rules;
3. three human response files, majority labels, adjudicated labels, sampling
   audit, rule baselines, and source/reference/field sensitivity analyses for
   the 80-claim reliability study;
4. the frozen paper-disjoint workflow as a design-audit case only;
5. the assignment-unit simulation and controlled consequence benchmark;
6. raw and analyzed outputs for three fixed open model judges;
7. the source-linked published human-evaluation reporting audit; and
8. bibliography integrity outputs and reproduction scripts.

Participant-facing extraction/composition packets, direct identifiers,
third-party full text, the 2026-07-25 export lacking a controlled internal
participant-response audit trail, historical pilots, synthetic dry runs, and
noncanonical packets are intentionally excluded.

Start with:
- `manuscript/supplement/observed_claim_audit_protocol.md`
- `manuscript/supplement/claim_reliability_summary.json`
- `manuscript/supplement/claim_source_sensitivity_summary.json`
- `manuscript/human_coding/heldout_claim_validation_v3_20260715/README_REVIEWER_PACKAGE.md`

The reviewer ZIP intentionally excludes third-party full text and private
identity/ethics records. Inside the extracted ZIP, validate the public frozen
design state from the ZIP root with:
`python manuscript/human_coding/heldout_claim_validation_v3_20260715/validate_package.py --mode frozen --portable`.

Recompute the paper's primary simulation with:
`python manuscript/scripts/simulate_assignment_unit_mismatch.py --replicates 5000 --workers 7`.

Rebuild and byte-check the controlled target with:
`python manuscript/scripts/build_controlled_claim_audit_benchmark.py --check`.
The package includes the frozen published-audit key and text-hash manifest but
not third-party full text. Source-line revalidation with
`python manuscript/scripts/analyze_published_human_evaluation_audit.py`
therefore requires the full local repository and its unreleased
`manuscript/citation_audit/expanded_texts/` directory; it is intentionally not
portable from this ZIP alone.
Rebuild the controlled-model tables with:
`python manuscript/scripts/analyze_controlled_model_judges.py --input manuscript/supplement/controlled_model_judge_raw/qwen2.5-7b.jsonl --input manuscript/supplement/controlled_model_judge_raw/phi-4-mini.jsonl --input manuscript/supplement/controlled_model_judge_raw/olmo-2-7b.jsonl`.
- `manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/human_validation_report.md`
"""
    entries = {
        path.relative_to(repo).as_posix(): path.read_bytes() for path in paths
    }
    reviewer_entries = {
        name.removeprefix(V3_ROOT): data
        for name, data in entries.items()
        if name.startswith(V3_ROOT)
    }
    marker_name = f"{V3_ROOT}.standalone-reviewer-package"
    entries[marker_name] = b"privacy-minimized-v3-reviewer-package\n"
    reviewer_manifest = "\n".join(
        f"{sha256(data)}  {name}"
        for name, data in sorted(reviewer_entries.items())
    ) + "\n"
    entries[f"{V3_ROOT}MANIFEST.sha256"] = reviewer_manifest.encode("utf-8")
    entries["README_DATA.md"] = readme.encode("utf-8")
    leaked_names = sorted(
        name
        for name in entries
        if name.startswith(V3_ROOT)
        and Path(name).name in PRIVATE_V3_ARTIFACT_BASENAMES
    )
    if leaked_names:
        raise ValueError(f"private v3 artifacts selected: {leaked_names}")
    for name, data in entries.items():
        validate_v3_data_entry(name, data)
    manifest = "\n".join(
        f"{sha256(data)}  {name}" for name, data in sorted(entries.items())
    ) + "\n"
    entries["MANIFEST.sha256"] = manifest.encode("utf-8")

    with zipfile.ZipFile(output, "w") as archive:
        for name, data in sorted(entries.items()):
            add_bytes(archive, name, data)

    summary = {
        "output": output.relative_to(repo).as_posix(),
        "files": len(entries),
        "bytes": output.stat().st_size,
        "sha256": sha256(output.read_bytes()),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
