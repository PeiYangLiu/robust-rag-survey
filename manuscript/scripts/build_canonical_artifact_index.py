#!/usr/bin/env python3
"""Build the small authoritative index of canonical and noncanonical artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


RECORDS = [
    (
        "repository_readme",
        "README.md",
        "canonical",
        "Authoritative artifact status and reproduction entry point.",
    ),
    (
        "manuscript",
        "manuscript/main.tex",
        "canonical",
        "Current manuscript source.",
    ),
    (
        "manuscript_pdf",
        "manuscript/main.pdf",
        "canonical_generated",
        "Compiled canonical manuscript.",
    ),
    (
        "all_in_one_source",
        "manuscript/main_all_in_one.tex",
        "canonical_generated",
        "Recursively inlined source generated from manuscript/main.tex.",
    ),
    (
        "overleaf_package_manifest",
        "overleaf_package/MANIFEST.sha256",
        "canonical_generated",
        "Checksums for the clean self-contained Overleaf source package.",
    ),
    (
        "map_b",
        "manuscript/supplement/evidence_map_venue_expanded_adjudicated.csv",
        "canonical",
        "Frozen 342-row legacy literature-family/intervention evidence map.",
    ),
    (
        "corpus_snapshot",
        "manuscript/supplement/corpus_snapshot.json",
        "canonical",
        "Search cutoff, coding freeze, hash, strata, coordinate coverage, and update policy.",
    ),
    (
        "release_version",
        "manuscript/supplement/RELEASE_VERSION.txt",
        "canonical",
        "Canonical release identifier for the EACL 2027 two-layer estimand-audit revision.",
    ),
    (
        "software_license",
        "LICENSE",
        "canonical",
        "MIT license for repository software.",
    ),
    (
        "data_license",
        "DATA_LICENSE.md",
        "canonical",
        "CC BY 4.0 terms for original structured annotations and third-party exclusions.",
    ),
    (
        "observed_claim_audit",
        "manuscript/supplement/observed_comparison_claim_audit.csv",
        "canonical",
        "291 frozen candidates and 289 included comparison claims with model-coded fields; not human gold.",
    ),
    (
        "observed_claim_audit_summary",
        "manuscript/supplement/observed_comparison_claim_audit_summary.json",
        "canonical",
        "Model-index distribution and internal transitions, plus the completed human-validation status.",
    ),
    (
        "observed_claim_codebook",
        "manuscript/supplement/observed_claim_audit_codebook.md",
        "canonical",
        "Frozen v2 executable rules evaluated by the negative reliability study.",
    ),
    (
        "observed_claim_codebook_v3_draft",
        "manuscript/supplement/observed_claim_audit_codebook_v3_draft.md",
        "canonical_poststudy_draft",
        "Post-study separation of evidence support and comparability; not evaluated on the same labels.",
    ),
    (
        "observed_claim_protocol",
        "manuscript/supplement/observed_claim_audit_protocol.md",
        "canonical",
        "Source selection, extraction, adjudication, and model-only validation boundaries.",
    ),
    (
        "observed_claim_corrections",
        "manuscript/supplement/observed_claim_audit_corrections.csv",
        "canonical",
        "Post-adjudication source-challenge correction ledger.",
    ),
    (
        "observed_claim_build_script",
        "manuscript/scripts/build_observed_claim_audit.py",
        "canonical",
        "Deterministically rebuilds the combined claim audit and summary.",
    ),
    (
        "observed_claim_verdict_script",
        "manuscript/scripts/derive_observed_claim_verdicts.py",
        "canonical",
        "Derives three-field, five-coordinate, and control-aware verdicts.",
    ),
    (
        "claim_rule_reliability_script",
        "manuscript/scripts/analyze_claim_rule_reliability.py",
        "canonical",
        "Evaluates rule baselines, sampling, field agreement, archetypes, and error triggers.",
    ),
    (
        "claim_rule_reliability",
        "manuscript/supplement/claim_rule_reliability.csv",
        "canonical_generated",
        "Accuracy, kappa, macro-F1, and per-class metrics for all rule baselines.",
    ),
    (
        "claim_rule_reliability_archetypes",
        "manuscript/supplement/claim_rule_reliability_by_archetype.csv",
        "canonical_generated",
        "Descriptive rule agreement separated by human-adjudicated claim archetype.",
    ),
    (
        "human_validation_sampling_audit",
        "manuscript/supplement/human_validation_sampling_audit.csv",
        "canonical_generated",
        "Model-stratum population counts, sample coverage, and population-inference boundary.",
    ),
    (
        "human_validation_field_agreement",
        "manuscript/supplement/human_validation_field_agreement_summary.csv",
        "canonical_generated",
        "Pairwise reliability ranges for each core coordinate and control status.",
    ),
    (
        "claim_error_type_audit",
        "manuscript/supplement/claim_error_type_audit.csv",
        "canonical_generated",
        "Separates ordinary support triggers from comparability-coordinate transitions.",
    ),
    (
        "claim_reliability_summary",
        "manuscript/supplement/claim_reliability_summary.json",
        "canonical_generated",
        "Machine-readable primary negative reliability result and paired rule tests.",
    ),
    (
        "claim_source_sensitivity_script",
        "manuscript/scripts/analyze_claim_source_sensitivity.py",
        "canonical",
        "Builds source-cluster intervals, leave-one-source-out diagnostics, reference-label sensitivity, and field decomposition.",
    ),
    (
        "claim_rule_predictions",
        "manuscript/supplement/claim_rule_predictions.csv",
        "canonical_generated",
        "Per-claim rule outputs, source clusters, coder references, and paired correctness indicators.",
    ),
    (
        "claim_rule_cluster_intervals",
        "manuscript/supplement/claim_rule_cluster_intervals.csv",
        "canonical_generated",
        "Source-cluster bootstrap intervals for each rule and the full-minus-ablated contrasts.",
    ),
    (
        "claim_source_sensitivity",
        "manuscript/supplement/claim_source_sensitivity.csv",
        "canonical_generated",
        "Source contributions and leave-one-source-out paired differences.",
    ),
    (
        "claim_reference_sensitivity",
        "manuscript/supplement/claim_reference_sensitivity.csv",
        "canonical_generated",
        "Full-versus-ablated results under coder, majority, unanimous, and adjudicated reference labels.",
    ),
    (
        "model_human_field_alignment",
        "manuscript/supplement/model_human_field_alignment.csv",
        "canonical_generated",
        "Agreement between model-coded and adjudicated human fields.",
    ),
    (
        "claim_archetype_cluster_intervals",
        "manuscript/supplement/claim_archetype_cluster_intervals.csv",
        "canonical_generated",
        "Exploratory archetype estimates with source-cluster intervals.",
    ),
    (
        "claim_source_sensitivity_summary",
        "manuscript/supplement/claim_source_sensitivity_summary.json",
        "canonical_generated",
        "Machine-readable source-cluster, LOSO, reference, and field sensitivity summary.",
    ),
    (
        "assignment_mismatch_simulation_script",
        "manuscript/scripts/simulate_assignment_unit_mismatch.py",
        "canonical",
        "Primary parameterized null simulation comparing source-only and reviewer-randomization references for the same panel-majority statistic.",
    ),
    (
        "assignment_mismatch_simulation_results",
        "manuscript/supplement/assignment_mismatch_simulation.json",
        "canonical_generated",
        "Five-thousand-replicate results for all assignment-unit mismatch scenarios.",
    ),
    (
        "cross_paper_comparability_cases",
        "manuscript/supplement/cross_paper_comparability_cases.csv",
        "canonical",
        "Source-linked cross-paper comparability cases with verbatim values, line ranges, and coordinate-matched readings.",
    ),
    (
        "cross_paper_comparability_cases_json",
        "manuscript/supplement/cross_paper_comparability_cases.json",
        "canonical",
        "Machine-readable comparability cases with summary counts.",
    ),
    (
        "cross_paper_comparability_cases_summary",
        "manuscript/supplement/cross_paper_comparability_cases_summary.json",
        "canonical_generated",
        "Compact per-case table rendered into the main comparability table.",
    ),
    (
        "cross_paper_comparability_verifier",
        "manuscript/scripts/verify_cross_paper_cases.py",
        "canonical",
        "Re-opens every cited file and line range and fails on any quoted value that does not occur there.",
    ),
    (
        "reviewer_heterogeneity_estimator",
        "manuscript/scripts/estimate_reviewer_heterogeneity.py",
        "canonical",
        "Estimates the between-reviewer logit standard deviation from the crossed three-coder diagnostic and tests what published agreement rates identify.",
    ),
    (
        "reviewer_heterogeneity_anchor",
        "manuscript/supplement/reviewer_heterogeneity_anchor.json",
        "canonical_generated",
        "Reviewer-heterogeneity point estimate, bootstrap interval, and partial-identification region.",
    ),
    (
        "retrospective_remedy_simulation_script",
        "manuscript/scripts/simulate_retrospective_remedies.py",
        "canonical",
        "Compares the status-quo source-level analysis with two retrospectively executable reviewer-level analyses under size and power.",
    ),
    (
        "retrospective_remedy_simulation_results",
        "manuscript/supplement/retrospective_remedy_simulation.json",
        "canonical_generated",
        "Full grid of size and power for four analyses at the estimated reviewer heterogeneity.",
    ),
    (
        "claim_rule_baselines",
        "manuscript/supplement/claim_rule_baselines.json",
        "canonical_generated",
        "Trivial baselines, source-clustered intervals, paired contrasts, and error taxonomy for the development diagnostic.",
    ),
    (
        "claim_rule_baselines_script",
        "manuscript/scripts/analyze_claim_rule_baselines.py",
        "canonical",
        "Computes the development-diagnostic baselines and contrasts.",
    ),
    (
        "controlled_claim_audit_benchmark_v2",
        "manuscript/supplement/controlled_claim_audit_benchmark_v2.jsonl",
        "canonical_target_specification",
        "600 synthetic consequence-defined decisions in 300 counterfactual pairs across a competence probe and the C2 and C5 strata; no human labels.",
    ),
    (
        "controlled_claim_audit_benchmark_v2_summary",
        "manuscript/supplement/controlled_claim_audit_benchmark_v2_summary.json",
        "canonical_target_specification",
        "Version-2 benchmark counts, per-stratum target balance, and SHA-256.",
    ),
    (
        "controlled_claim_audit_benchmark_v2_builder",
        "manuscript/scripts/build_controlled_claim_audit_benchmark_v2.py",
        "canonical",
        "Deterministically rebuilds and byte-checks the version-2 controlled target.",
    ),
    (
        "controlled_model_judge_runner_v2",
        "manuscript/scripts/run_controlled_model_judges_v2.py",
        "canonical",
        "Runs one open model over three arms crossed with four paraphrases on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_analysis_v2",
        "manuscript/scripts/analyze_controlled_model_judges_v2.py",
        "canonical",
        "Pair-clustered bootstrap, Holm correction, validity gate, and random-effects combination for the version-2 experiment.",
    ),
    (
        "controlled_claim_audit_benchmark_v2_protocol",
        "manuscript/supplement/controlled_claim_audit_benchmark_v2_protocol.md",
        "canonical_target_specification",
        "Version-2 design, pre-declared validity gate, arm definitions, and interpretation boundary.",
    ),
    (
        "controlled_model_judge_results_v2",
        "manuscript/supplement/controlled_model_judge_results_v2.json",
        "canonical_generated",
        "Pair-clustered contrasts, validity-gate status, Holm values, and random-effects combination for the version-2 experiment.",
    ),
    (
        "controlled_model_judge_results_v2_csv",
        "manuscript/supplement/controlled_model_judge_results_v2.csv",
        "canonical_generated",
        "Flat per-model, per-stratum table backing the version-2 experiment.",
    ),
    (
        "controlled_model_judge_v2_qwen25_7b",
        "manuscript/supplement/controlled_model_judge_raw_v2/qwen25-7b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for Qwen2.5-7B-Instruct on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_qwen25_14b",
        "manuscript/supplement/controlled_model_judge_raw_v2/qwen25-14b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for Qwen2.5-14B-Instruct on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_qwen3_8b",
        "manuscript/supplement/controlled_model_judge_raw_v2/qwen3-8b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for Qwen3-8B on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_qwen3_14b",
        "manuscript/supplement/controlled_model_judge_raw_v2/qwen3-14b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for Qwen3-14B on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_phi4_mini",
        "manuscript/supplement/controlled_model_judge_raw_v2/phi-4-mini.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for Phi-4-mini-instruct on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_olmo2_7b",
        "manuscript/supplement/controlled_model_judge_raw_v2/olmo2-7b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for OLMo-2-1124-7B-Instruct on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_olmo2_13b",
        "manuscript/supplement/controlled_model_judge_raw_v2/olmo2-13b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for OLMo-2-1124-13B-Instruct on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_granite31_8b",
        "manuscript/supplement/controlled_model_judge_raw_v2/granite-31-8b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for Granite-3.1-8B-Instruct on the version-2 benchmark.",
    ),
    (
        "controlled_model_judge_v2_falcon3_7b",
        "manuscript/supplement/controlled_model_judge_raw_v2/falcon3-7b.jsonl",
        "canonical_generated",
        "Raw 7,200-record greedy output for Falcon3-7B-Instruct on the version-2 benchmark.",
    ),
    (
        "cross_paper_comparability_codebook",
        "manuscript/supplement/cross_paper_comparability_cases_codebook.md",
        "canonical",
        "Field definitions, inclusion rule, verdict vocabulary, and evidentiary standard for the comparability cases.",
    ),
    (
        "cross_paper_comparability_report",
        "manuscript/supplement/cross_paper_comparability_cases_report.md",
        "canonical_generated",
        "Narrative write-up of the comparability cases with the three strongest worked in full.",
    ),
    (
        "revision_table_builder",
        "manuscript/scripts/build_revision_tables.py",
        "canonical",
        "Regenerates every table and figure added in the revision from released artifacts.",
    ),
    (
        "controlled_claim_audit_benchmark",
        "manuscript/supplement/controlled_claim_audit_benchmark.jsonl",
        "canonical_target_specification",
        "480 synthetic consequence-defined decisions in 240 counterfactual pairs; no human labels.",
    ),
    (
        "controlled_claim_audit_benchmark_summary",
        "manuscript/supplement/controlled_claim_audit_benchmark_summary.json",
        "canonical_target_specification",
        "Benchmark counts, balance checks, target definition, and SHA-256.",
    ),
    (
        "controlled_claim_audit_benchmark_protocol",
        "manuscript/supplement/controlled_claim_audit_benchmark_protocol.md",
        "canonical_target_specification",
        "Prospective design and interpretation boundary for the controlled target.",
    ),
    (
        "controlled_claim_audit_benchmark_builder",
        "manuscript/scripts/build_controlled_claim_audit_benchmark.py",
        "canonical",
        "Deterministically rebuilds and byte-checks the controlled target.",
    ),
    (
        "controlled_model_judge_runner",
        "manuscript/scripts/run_controlled_model_judges.py",
        "canonical",
        "Crossed-prompt runner used for the three reported fixed open models.",
    ),
    (
        "controlled_model_judge_analyzer",
        "manuscript/scripts/analyze_controlled_model_judges.py",
        "canonical",
        "Rebuilds fixed-model exact agreement, regret, pair consistency, and C2/C5 tables.",
    ),
    (
        "controlled_model_judge_results",
        "manuscript/supplement/controlled_model_judge_results.json",
        "canonical_generated",
        "Machine-readable results for the three fixed open models and two crossed prompts.",
    ),
    (
        "controlled_model_judge_results_csv",
        "manuscript/supplement/controlled_model_judge_results.csv",
        "canonical_generated",
        "Tabular fixed-model results by all items, C2 capability, and C5 utility.",
    ),
    (
        "controlled_model_judge_qwen",
        "manuscript/supplement/controlled_model_judge_raw/qwen2.5-7b.jsonl",
        "canonical_model_output",
        "Raw and parsed deterministic Qwen2.5-7B outputs for all 960 item-condition records.",
    ),
    (
        "controlled_model_judge_phi",
        "manuscript/supplement/controlled_model_judge_raw/phi-4-mini.jsonl",
        "canonical_model_output",
        "Raw and parsed deterministic Phi-4-mini outputs for all 960 item-condition records.",
    ),
    (
        "controlled_model_judge_olmo",
        "manuscript/supplement/controlled_model_judge_raw/olmo-2-7b.jsonl",
        "canonical_model_output",
        "Raw and parsed deterministic OLMo-2-7B outputs for all 960 item-condition records.",
    ),
    (
        "published_human_evaluation_audit",
        "manuscript/supplement/published_human_evaluation_audit.json",
        "canonical_source_linked_audit",
        "Nine published robust-RAG human-judgment cases with full-text line locators and conservative reporting codes.",
    ),
    (
        "published_human_evaluation_audit_summary",
        "manuscript/supplement/published_human_evaluation_audit_summary.json",
        "canonical_generated",
        "Fixed-screen counts and reporting-field totals for the published audit.",
    ),
    (
        "published_human_evaluation_screen_manifest",
        "manuscript/supplement/published_human_evaluation_screen_manifest.csv",
        "canonical_frozen_manifest",
        "Exact 39-paper screen identities, full-text hashes, term-screen flags, inclusion flags, and included-case locator hashes.",
    ),
    (
        "published_human_evaluation_audit_analyzer",
        "manuscript/scripts/analyze_published_human_evaluation_audit.py",
        "canonical",
        "Validates the fixed screen, source locators, coding vocabulary, counts, and LaTeX tables.",
    ),
    (
        "v3_preregistered_diagnostic_summary",
        "manuscript/supplement/v3_preregistered_diagnostic_summary.json",
        "excluded_unverifiable_human_collection",
        "Historical derived outcome summary; excluded because no controlled internal participant-response provenance is available.",
    ),
    (
        "excluded_collection_invalidation_receipt",
        "files/v3_invalidated_shared_answer_run_20260719/invalidation_report.json",
        "canonical_exclusion_evidence",
        "Privacy-safe receipt documenting identical full response payloads across nominal participant IDs and anchoring the original return-manifest hash; contains no outcome estimate used by the paper.",
    ),
    (
        "v3_public_release_summary",
        "manuscript/supplement/v3_human_reanalysis_20260725/release_summary.json",
        "excluded_unverifiable_human_collection",
        "Historical deidentified export metadata; not evidence.",
    ),
    (
        "v3_public_analysis_results",
        "manuscript/supplement/v3_human_reanalysis_20260725/analysis_results.json",
        "excluded_unverifiable_human_collection",
        "Historical derived analyses; no result enters the manuscript.",
    ),
    (
        "v3_public_arm_ratings",
        "manuscript/supplement/v3_human_reanalysis_20260725/public_arm_ratings.csv",
        "excluded_unverifiable_human_collection",
        "Deidentified rows without a controlled internal participant-response audit trail; excluded.",
    ),
    (
        "v3_public_gold_ratings",
        "manuscript/supplement/v3_human_reanalysis_20260725/public_gold_ratings.csv",
        "excluded_unverifiable_human_collection",
        "Deidentified rows without a controlled internal participant-response audit trail; excluded.",
    ),
    (
        "v3_public_adjudications",
        "manuscript/supplement/v3_human_reanalysis_20260725/public_adjudications.csv",
        "excluded_unverifiable_human_collection",
        "Deidentified rows without a controlled internal participant-response audit trail; excluded.",
    ),
    (
        "v3_public_release_manifest",
        "manuscript/supplement/v3_human_reanalysis_20260725/public_release_manifest.json",
        "excluded_unverifiable_human_collection",
        "Byte manifest for the excluded export; hashes do not establish behavioral independence.",
    ),
    (
        "v3_public_reanalysis_script",
        "manuscript/scripts/reanalyze_public_v3.py",
        "historical_excluded_analysis",
        "Recomputes the excluded deidentified export; not a manuscript analysis.",
    ),
    (
        "v3_review_diagnostics_script",
        "manuscript/scripts/analyze_v3_review_diagnostics.py",
        "historical_excluded_analysis",
        "Historical diagnostics for the excluded export; not a manuscript analysis.",
    ),
    (
        "v3_review_diagnostics_summary",
        "manuscript/supplement/v3_review_diagnostics.json",
        "excluded_unverifiable_human_collection",
        "Historical diagnostics; no estimate enters the manuscript.",
    ),
    (
        "v3_reference_reliability",
        "manuscript/supplement/v3_reference_reliability.csv",
        "excluded_unverifiable_human_collection",
        "Historical derived table from the excluded export.",
    ),
    (
        "v3_reference_sensitivity",
        "manuscript/supplement/v3_reference_sensitivity.csv",
        "excluded_unverifiable_human_collection",
        "Historical derived table from the excluded export.",
    ),
    (
        "v3_per_class_performance",
        "manuscript/supplement/v3_per_class_performance.csv",
        "excluded_unverifiable_human_collection",
        "Historical derived table from the excluded export.",
    ),
    (
        "v3_sampling_mismatch",
        "manuscript/supplement/v3_sampling_mismatch.csv",
        "excluded_unverifiable_human_collection",
        "Historical derived table from the excluded export.",
    ),
    (
        "v3_quality_gate_results",
        "manuscript/supplement/v3_quality_gate_results.csv",
        "historical_posthoc_excluded",
        "Historical same-family post hoc screen; excluded from paper inference.",
    ),
    (
        "v3_quality_gate_critical_errors",
        "manuscript/supplement/v3_quality_gate_critical_errors.csv",
        "historical_posthoc_excluded",
        "Historical same-family post hoc critical-error counts; excluded from paper inference.",
    ),
    (
        "heldout_v3_readme",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/README_REVIEWER_PACKAGE.md",
        "design_audit_only",
        "Privacy-minimized entry point stating exactly what portable reviewer validation does and does not establish.",
    ),
    (
        "heldout_v3_protocol",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/preregistered_protocol.md",
        "design_audit_only",
        "Locally frozen 480-claim, 80-source, four-arm protocol used as a design case, not a completed human result.",
    ),
    (
        "heldout_v3_codebook",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/codebook_v3_frozen.md",
        "canonical_preregistered_no_test_labels",
        "Frozen v3 codebook separating evidence support from comparability.",
    ),
    (
        "heldout_v3_power",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/power_analysis.json",
        "canonical_preregistered_no_test_labels",
        "Prospective clustered power approximation and conditional-equivalence limits.",
    ),
    (
        "heldout_v3_source_frame",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/source_sampling_frame.csv",
        "canonical_preregistered_no_test_labels",
        "Complete 342-source frame with key/title exclusions and deterministic source ranks.",
    ),
    (
        "heldout_v3_candidate_pool",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/candidate_claims_deterministic.csv",
        "canonical_preregistered_no_test_labels",
        "Model-free 1,582-candidate nomination pool after four ledgered source replacements.",
    ),
    (
        "heldout_v3_candidate_summary",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/candidate_pool_summary.json",
        "canonical_preregistered_no_test_labels",
        "Hashes, counts, and composition of the deterministic held-out candidate pool.",
    ),
    (
        "heldout_v3_sampling_candidates",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/candidate_claims_model_prescreen.csv",
        "canonical_preregistered_no_test_labels",
        "Model-free initialized sampling rows; all model fields are blank and no test outcome is present.",
    ),
    (
        "heldout_v3_sampling_screen_script",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_sampling_screen_packets.py",
        "canonical_preregistered_no_test_labels",
        "Builds and merges two independent sampling screens plus a disagreement-only tie-break packet.",
    ),
    (
        "heldout_v3_sampling_screen_summary",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/sampling_screen_summary.json",
        "canonical_preregistered_no_test_labels",
        "Hash-linked administrative screening workflow state; not a test outcome.",
    ),
    (
        "heldout_v3_sampling_screener_provenance",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/sampling_screener_provenance.json",
        "canonical_human_sampling_provenance",
        "Coordinator attestation for three independent, source-checked, AI-free human sampling screeners.",
    ),
    (
        "heldout_v3_source_replacement_script",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/apply_source_replacements.py",
        "canonical_preregistered_no_test_labels",
        "Applies ledger-driven append-only source replacements without changing retained candidate IDs or human screens.",
    ),
    (
        "heldout_v3_source_replacement_summary",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/source_replacement_summary.json",
        "canonical_preregistered_no_test_labels",
        "Hash-linked two-batch append-only audit for four source replacements.",
    ),
    (
        "heldout_v3_sampling_freeze_summary",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/sampling_freeze_summary.json",
        "canonical_frozen_no_test_labels",
        "Successful 480-claim, 80-source, 240-C2/240-C5 sample freeze audit.",
    ),
    (
        "heldout_v3_development_sources",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/DEVELOPMENT_SOURCES.csv",
        "canonical_preregistered_no_test_labels",
        "Key and normalized-title registry for every identifiable v1/v2 development source.",
    ),
    (
        "heldout_v3_prepare_script",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/prepare_candidate_pool.py",
        "canonical_preregistered_no_test_labels",
        "Rebuilds the source frame and deterministic claim nominations.",
    ),
    (
        "heldout_v3_freeze_script",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/freeze_human_sample.py",
        "canonical_preregistered_no_test_labels",
        "Freezes the 480 claims using only independent human sampling fields and hash ordering.",
    ),
    (
        "heldout_v3_assignment_script",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_assignments.py",
        "canonical_preregistered_no_test_labels",
        "Builds balanced four-arm assignments with three independent ratings per claim and arm.",
    ),
    (
        "heldout_v3_packet_script",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_review_packets.py",
        "canonical_preregistered_no_test_labels",
        "Builds blinded per-participant auditor, gold, and post-disagreement adjudication packets.",
    ),
    (
        "heldout_v3_analysis_script",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/analyze_collected_results.py",
        "canonical_preregistered_no_test_labels",
        "Frozen standard-library CR1, cluster-bootstrap, conditional-TOST, and Holm analysis.",
    ),
    (
        "heldout_v3_validator",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/validate_package.py",
        "canonical_preregistered_no_test_labels",
        "Validates prepared, frozen, and collected package states without creating labels.",
    ),
    (
        "heldout_v3_frozen_claims",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/frozen_test_claims.csv",
        "canonical_frozen_no_test_labels",
        "Frozen 480-claim paper-disjoint sample with six claims per source and no test labels.",
    ),
    (
        "heldout_v3_assignments",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/auditor_assignments.csv",
        "canonical_frozen_no_test_labels",
        "5,760 balanced anonymous assignments: three ratings per claim and arm.",
    ),
    (
        "heldout_v3_public_roster",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/participant_metadata_public_template.csv",
        "excluded_unverifiable_roster",
        "Historical anonymous slots tied to an unverifiable/persona roster; no participant attribute is accepted.",
    ),
    (
        "heldout_v3_calibration_items",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_items.csv",
        "canonical_calibration_no_test_labels",
        "Ten self-contained instructor-constructed calibration dossiers.",
    ),
    (
        "heldout_v3_calibration_key",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_answer_key.csv",
        "canonical_calibration_no_test_labels",
        "Transparent instructor answer key; not human test gold and never included in participant packets.",
    ),
    (
        "heldout_v3_calibration_materials",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_materials.md",
        "canonical_calibration_no_test_labels",
        "Human-readable calibration dossiers and methodological boundaries.",
    ),
    (
        "heldout_v3_calibration_builder",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_calibration_packets.py",
        "canonical_calibration_no_test_labels",
        "Builds role- and arm-isolated ten-item calibration packets without answer-key leakage.",
    ),
    (
        "heldout_v3_calibration_scorer",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/score_calibration.py",
        "canonical_calibration_no_test_labels",
        "Scores two dimensions independently at the frozen 8/10 threshold and manages one retraining round.",
    ),
    (
        "heldout_v3_calibration_summary",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_summary.json",
        "excluded_unverifiable_roster",
        "Historical calibration state tied to the excluded roster; not human evidence.",
    ),
    (
        "heldout_v3_calibration_responses",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/calibration_responses.csv",
        "excluded_unverifiable_roster",
        "Historical calibration rows tied to the excluded roster; not human evidence.",
    ),
    (
        "heldout_v3_text_corrections",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/frozen_text_corrections.csv",
        "canonical_frozen_no_test_labels",
        "Reversible pre-test text-normalization ledger with authoritative source evidence.",
    ),
    (
        "heldout_v3_stage1_builder",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/build_staged_review_packets.py",
        "canonical_frozen_no_test_labels",
        "Builds extraction-only Stage 1 packets and the coordinator trust registry.",
    ),
    (
        "heldout_v3_stage2_issuer",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/issue_composition_packets.py",
        "canonical_frozen_no_test_labels",
        "Coordinator-only verifier and issuer for composition Stage 2 after extraction lock.",
    ),
    (
        "heldout_v3_response_collector",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/collect_final_responses.py",
        "canonical_frozen_no_test_labels",
        "Coordinator-only final-response validator and immutable receipt generator.",
    ),
    (
        "heldout_v3_coordinator_registry",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/coordinator_packet_registry.json",
        "canonical_frozen_no_test_labels",
        "Private-trust root for 27 extraction-only packets; contains no PII or labels.",
    ),
    (
        "heldout_v3_composition_registry",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/composition_packet_issuance_registry.json",
        "excluded_unverifiable_roster",
        "Historical issuance registry tied to the excluded roster; retained only for provenance.",
    ),
    (
        "heldout_v3_composition_issuance_rows",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/composition_issuance_rows.csv",
        "excluded_unverifiable_roster",
        "Historical issuance rows tied to the excluded roster; retained only for provenance.",
    ),
    (
        "heldout_v3_collection_receipt",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/coordinator_collection_receipt.json",
        "canonical_issued_no_composition_responses",
        "Zero-response sentinel: no Stage 2 composition response has been collected.",
    ),
    (
        "heldout_v3_staged_schema",
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/staged_review_schema.json",
        "canonical_frozen_no_test_labels",
        "Frozen schemas for staged issuance, corrections, receipts, and adjudication registry.",
    ),
    (
        "search_source_ledger",
        "manuscript/supplement/search_source_ledger.csv",
        "canonical",
        "Source-specific query reproducibility and unrecoverable initial-search gaps.",
    ),
    (
        "recoverable_search_rerun",
        "manuscript/scripts/rerun_recoverable_search.py",
        "canonical",
        "Reruns the recoverable arXiv, DBLP, OpenAlex, and ACL venue-pass query logic without changing the frozen corpus.",
    ),
    (
        "screening_provenance",
        "manuscript/supplement/screening_provenance.csv",
        "canonical",
        "Actor, duplication, and adjudication status for every review stage.",
    ),
    (
        "prisma_scr_crosswalk",
        "manuscript/supplement/prisma_scr_checklist.csv",
        "canonical",
        "Item-level PRISMA-ScR status and remaining gaps.",
    ),
    (
        "bibliography_integrity_report",
        "manuscript/supplement/bibliography_integrity_report.csv",
        "canonical_generated",
        "Structural and official-source verification for every bibliography entry used by the manuscript.",
    ),
    (
        "bibliography_integrity_summary",
        "manuscript/supplement/bibliography_integrity_summary.json",
        "canonical_generated",
        "Aggregate bibliography verification status and any remaining failures.",
    ),
    (
        "bibliography_integrity_script",
        "manuscript/scripts/verify_bibliography_integrity.py",
        "canonical",
        "Rebuilds the complete cited-reference integrity report.",
    ),
    (
        "release_validation_script",
        "manuscript/scripts/validate_release.py",
        "canonical",
        "Validates claim counts, bibliography status, PDF equivalence, page limits, hashes, and release indexes.",
    ),
    (
        "human_validation_annotator_a",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/annotator_A_claims_completed.csv",
        "canonical_human_validation",
        "Eighty independent human judgments from annotator A.",
    ),
    (
        "human_validation_annotator_b",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/annotator_B_claims_completed.csv",
        "canonical_human_validation",
        "Eighty independent human judgments from annotator B.",
    ),
    (
        "human_validation_annotator_c",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/annotator_C_claims_completed.csv",
        "canonical_human_validation",
        "Eighty independent human judgments from annotator C.",
    ),
    (
        "human_validation_adjudication",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/adjudicated_consensus.csv",
        "canonical_human_validation",
        "Separate human adjudication over the eighty validation claims.",
    ),
    (
        "human_validation_final_consensus",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/final/human_final_consensus.csv",
        "canonical_human_validation",
        "Canonical adjudicated human labels with source and sampling provenance.",
    ),
    (
        "human_validation_summary",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/final/human_validation_summary.json",
        "canonical_human_validation",
        "Pre-adjudication agreement, adjudicated distribution, and secondary model comparison.",
    ),
    (
        "human_validation_provenance",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/human_annotation_provenance.json",
        "canonical_human_validation",
        "Aggregate participant, consent, ethics, training, time, and adjudication provenance.",
    ),
    (
        "human_validation_protocol",
        "manuscript/human_coding/observed_claim_human_validation_20260714/human_validation_protocol.md",
        "canonical_human_validation",
        "Released human instructions, training, recruitment, consent, ethics, sampling, and adjudication protocol.",
    ),
    (
        "human_validation_pairwise",
        "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/analysis_results/pre_adjudication/pairwise_agreement.csv",
        "canonical_human_validation",
        "Pairwise raw agreement, Cohen kappa, Gwet AC1, and bootstrap intervals.",
    ),
    (
        "human_validation_finalizer",
        "manuscript/human_coding/observed_claim_human_validation_20260714/analysis/finalize_human_validation.py",
        "canonical",
        "Validates the adjudication and rebuilds final human-validation outputs.",
    ),
    (
        "review_data_package",
        "manuscript/review_data_package.zip",
        "canonical_submission_package",
        "Reviewer package containing the simulation, controlled target, retained development diagnostic, and design-audit artifacts; excluded v3 outcomes are omitted.",
    ),
    (
        "review_data_package_builder",
        "manuscript/scripts/build_review_data_package.py",
        "canonical",
        "Deterministically builds and validates the minimal reviewer data package.",
    ),
    (
        "post_freeze_recall_audit",
        "manuscript/supplement/post_freeze_recall_audit.csv",
        "canonical",
        "Known discoveries outside the frozen Map-B denominator.",
    ),
]


def row_count(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return str(max(0, sum(1 for _ in csv.reader(handle)) - 1))
    if suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return str(sum(1 for line in handle if line.strip()))
    return ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_csv = repo_root / "manuscript" / "supplement" / "canonical_artifact_index.csv"
    output_json = repo_root / "manuscript" / "supplement" / "canonical_artifact_index.json"
    rows: list[dict[str, str]] = []
    for artifact, relative_path, status, notes in RECORDS:
        path = repo_root / relative_path
        exists = path.is_file()
        rows.append(
            {
                "artifact": artifact,
                "path": relative_path,
                "status": status,
                "exists": str(exists).lower(),
                "rows": row_count(path) if exists else "",
                "sha256": sha256(path) if exists else "",
                "notes": notes,
            }
        )

    fields = ["artifact", "path", "status", "exists", "rows", "sha256", "notes"]
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with output_json.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"Wrote {len(rows)} records to {output_csv} and {output_json}")


if __name__ == "__main__":
    main()
