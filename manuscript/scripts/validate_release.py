#!/usr/bin/env python3
"""Validate the canonical manuscript, claim audit, bibliography, and release indexes."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from build_review_data_package import (
    PRIVATE_V3_ARTIFACT_BASENAMES,
    PUBLIC_V3_ROOT,
    V3_ROOT,
    validate_v3_data_entry,
)


def _release_deny_list() -> list[bytes]:
    """Strings that must never appear inside a release archive.

    Read from ``RELEASE_DENY_LIST`` (comma separated) and extended with the
    local account name, so that internal cluster names and the author's account
    are checked without being written into a source file that ships publicly.
    """
    import getpass

    items = [s.strip() for s in os.environ.get("RELEASE_DENY_LIST", "").split(",")]
    try:
        items.append(getpass.getuser())
    except Exception:
        pass
    return [s.encode() for s in items if s]




def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def indexed_row_count(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return str(max(0, sum(1 for _ in csv.reader(handle)) - 1))
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return str(sum(1 for line in handle if line.strip()))
    return ""


def validate_index_rows(
    rows: list[dict[str, str]], repo: Path
) -> dict[str, dict[str, str]]:
    by_path = {row["path"]: row for row in rows}
    assert len(by_path) == len(rows)
    for relative_path, row in by_path.items():
        path = repo / relative_path
        assert row["exists"] == "true"
        assert path.is_file()
        assert row["sha256"] == sha256(path)
        assert row["rows"] == indexed_row_count(path)
    return by_path


def pdf_pages(path: Path) -> int:
    output = subprocess.check_output(["pdfinfo", str(path)], text=True)
    return int(re.search(r"^Pages:\s+(\d+)", output, re.M).group(1))


def pdf_text(path: Path, output: Path) -> None:
    subprocess.run(
        ["pdftotext", "-layout", str(path), str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def validate_public_v3_release() -> None:
    manuscript = Path(__file__).resolve().parents[1]
    repo = manuscript.parent
    public_v3 = manuscript / "supplement" / "v3_human_reanalysis_20260725"
    files = {path.name for path in public_v3.iterdir() if path.is_file()}
    assert len(files) == 13
    summary = json.loads((public_v3 / "release_summary.json").read_text())
    assert json.loads(
        (
            manuscript / "supplement" / "v3_preregistered_diagnostic_summary.json"
        ).read_text()
    ) == summary
    assert summary["missingness"]["gold_unresolved_comparability"] == 35
    assert summary["primary"]["claims"] == 445
    assert math.isclose(summary["primary"]["estimate"], 0.03146067415730337)
    reproducibility = summary["reproducibility"]
    entrypoint = repo / reproducibility["entrypoint"]
    analysis_module = repo / reproducibility["analysis_module"]
    assert reproducibility["entrypoint_sha256"] == sha256(entrypoint)
    assert reproducibility["analysis_module_sha256"] == sha256(analysis_module)
    assert reproducibility["dependencies"] == "Python standard library only"
    assert len(read_csv(public_v3 / "public_arm_ratings.csv")) == 5760
    assert len(read_csv(public_v3 / "public_gold_ratings.csv")) == 1440
    assert len(read_csv(public_v3 / "public_adjudications.csv")) == 410

    script = manuscript / "scripts" / "reanalyze_public_v3.py"
    with tempfile.TemporaryDirectory(
        prefix=".public-v3-release-validation-", dir=repo
    ) as directory:
        root = Path(directory)
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--verify-published",
                "--output",
                str(root / "repository-reanalysis"),
            ],
            cwd=repo,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with zipfile.ZipFile(manuscript / "review_data_package.zip") as archive:
            names = set(archive.namelist())
            prefix = PUBLIC_V3_ROOT
            assert {prefix + name for name in files} <= names
            assert len({name for name in names if name.startswith(prefix)}) == 13
            assert "manuscript/scripts/reanalyze_public_v3.py" in names
            assert (
                "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
                "analyze_collected_results.py"
            ) in names
            assert (
                "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
                "analysis_output_schema.json"
            ) in names
            assert (
                "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
                "poststudy_analysis_addendum.md"
            ) in names
            assert f"{V3_ROOT}.standalone-reviewer-package" in names
            assert f"{V3_ROOT}MANIFEST.sha256" in names
            assert not any(
                name.startswith(V3_ROOT)
                and Path(name).name in PRIVATE_V3_ARTIFACT_BASENAMES
                for name in names
            )
            for name in names:
                if name.startswith((V3_ROOT, PUBLIC_V3_ROOT)):
                    validate_v3_data_entry(name, archive.read(name))
            readme = archive.read("README_DATA.md").decode("utf-8")
            frozen_command = (
                "python manuscript/human_coding/"
                "heldout_claim_validation_v3_20260715/validate_package.py "
                "--mode frozen --portable"
            )
            assert frozen_command in readme
            extracted = root / "zip"
            archive.extractall(extracted)
        subprocess.run(
            [
                sys.executable,
                "manuscript/human_coding/"
                "heldout_claim_validation_v3_20260715/validate_package.py",
                "--mode",
                "frozen",
                "--portable",
            ],
            cwd=extracted,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                sys.executable,
                "manuscript/scripts/reanalyze_public_v3.py",
                "--verify-published",
                "--output",
                "zip-reanalysis",
            ],
            cwd=extracted,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    print(
        json.dumps(
            {
                "status": "public_v3_release_valid",
                "public_files": len(files),
                "comparability_resolved": summary["primary"]["claims"],
                "comparability_unresolved": summary["missingness"][
                    "gold_unresolved_comparability"
                ],
                "review_zip": "valid",
            },
            indent=2,
        )
    )


def validate_legacy_release() -> None:
    manuscript = Path(__file__).resolve().parents[1]
    repo = manuscript.parent
    supplement = manuscript / "supplement"

    audit = read_csv(supplement / "observed_comparison_claim_audit.csv")
    summary = json.loads(
        (supplement / "observed_comparison_claim_audit_summary.json").read_text()
    )
    assert len(audit) == 291
    assert len({row["candidate_id"] for row in audit}) == 291
    included = [row for row in audit if row["unit_status"] == "include"]
    assert len(included) == 289
    verdicts = Counter(row["verdict_full"] for row in included)
    assert dict(verdicts) == summary["distributions"]["full_verdict_included"]
    assert verdicts == Counter(
        {"partial": 134, "valid": 125, "invalid": 26, "under-specified": 4}
    )
    decisive = {
        "evidence_state": sum(
            int(row["evidence_state_decisive"]) for row in included
        ),
        "origin_capability": sum(int(row["origin_decisive"]) for row in included),
        "policy_utility": sum(int(row["policy_decisive"]) for row in included),
        "second_stage_controls": sum(
            int(row["controls_decisive"]) for row in included
        ),
        "origin_or_policy": sum(
            int(row["origin_decisive"]) or int(row["policy_decisive"])
            for row in included
        ),
        "intervention_difference_permitted": sum(
            row["verdict_fim"] == "partial"
            and row["verdict_5coord_no_controls"] == "valid"
            for row in included
        ),
    }
    assert decisive == summary["decisive_counts"]
    assert decisive == {
        "evidence_state": 1,
        "origin_capability": 7,
        "policy_utility": 12,
        "second_stage_controls": 23,
        "origin_or_policy": 19,
        "intervention_difference_permitted": 120,
    }
    assert summary["headline_use"] == (
        "prohibited_unvalidated_model_verdict_distribution_and_rule_transitions"
    )
    assert summary["balanced_packet"]["status"] == (
        "completed_as_16_claim_core_within_80_claim_human_validation"
    )
    assert summary["human_validation"]["status"] == (
        "completed_negative_reliability_study"
    )
    corrections = read_csv(supplement / "observed_claim_audit_corrections.csv")
    assert len(corrections) == 23
    source_manifest = json.loads(
        (supplement / "observed_claim_source_manifest.json").read_text()
    )
    assert sum(source["candidate_count"] for source in source_manifest["sources"]) == 291

    bibliography = json.loads(
        (supplement / "bibliography_integrity_summary.json").read_text()
    )
    bibliography_report = read_csv(
        supplement / "bibliography_integrity_report.csv"
    )
    report_keys = {row["key"] for row in bibliography_report}
    assert len(report_keys) == len(bibliography_report)
    aux_text = (manuscript / "main.aux").read_text()
    cited_keys = {
        key.strip()
        for group in re.findall(r"\\citation\{([^}]+)\}", aux_text)
        for key in group.split(",")
        if key.strip()
    }
    bibcite_keys = set(re.findall(r"\\bibcite\{([^}]+)\}", aux_text))
    assert report_keys == cited_keys == bibcite_keys
    bibliography_count = len(report_keys)
    assert bibliography["used_entries"] == bibliography_count
    assert bibliography["aux_key_sets_match"] is True
    assert bibliography["used_keys_sha256"] == hashlib.sha256(
        "\n".join(sorted(report_keys)).encode("utf-8")
    ).hexdigest()
    assert bibliography["structural_status"] == {"ok": bibliography_count}
    assert not bibliography["online_failures"]
    assert bibliography["verification"].get("not_run", 0) == 0
    assert sum(bibliography["verification"].values()) == bibliography_count
    bbl_text = (manuscript / "main.bbl").read_text(errors="replace")
    bbl_keys = set(
        re.findall(r"\\bibitem(?:\[.*?\])?\{([^}]+)\}", bbl_text, re.S)
    )
    assert bbl_keys == report_keys

    canonical = read_csv(supplement / "canonical_artifact_index.csv")
    release = read_csv(supplement / "artifact_release_manifest.csv")
    canonical_by_path = validate_index_rows(canonical, repo)
    release_by_path = validate_index_rows(release, repo)
    assert json.loads(
        (supplement / "canonical_artifact_index.json").read_text()
    ) == canonical
    assert json.loads(
        (supplement / "artifact_release_manifest.json").read_text()
    ) == release
    assert set(canonical_by_path) <= set(release_by_path)
    for relative_path, canonical_row in canonical_by_path.items():
        release_row = release_by_path[relative_path]
        assert release_row["artifact"] == canonical_row["artifact"]
        assert release_row["status"] == canonical_row["status"]
        assert release_row["exists"] == canonical_row["exists"]
        assert release_row["rows"] == canonical_row["rows"]
        assert release_row["sha256"] == canonical_row["sha256"]
    assert (repo / "LICENSE").is_file() and (repo / "DATA_LICENSE.md").is_file()
    assert (
        supplement / "RELEASE_VERSION.txt"
    ).read_text().strip() == "eacl27-two-layer-estimand-audit-2026.07.26"

    v3_diagnostic = json.loads(
        (supplement / "v3_preregistered_diagnostic_summary.json").read_text()
    )
    public_v3 = supplement / "v3_human_reanalysis_20260725"
    release_summary = json.loads((public_v3 / "release_summary.json").read_text())
    assert v3_diagnostic == release_summary
    assert v3_diagnostic["frozen_cohort"]["schema_id"] == (
        "heldout-v3-frozen-claims-v1"
    )
    assert v3_diagnostic["missingness"]["gold_unresolved_comparability"] == 35
    assert math.isclose(
        v3_diagnostic["missingness"]["gold_unresolved_comparability_rate"],
        35 / 480,
    )
    assert (
        v3_diagnostic["missingness"]["confirmatory_missingness_rule_passed"]
        is False
    )
    assert v3_diagnostic["arm_accuracy"]["A"]["comparability"][
        "accuracy_denominator"
    ] == 445
    assert math.isclose(
        v3_diagnostic["arm_accuracy"]["A"]["comparability"]["accuracy"],
        0.7775280898876404,
    )
    assert math.isclose(
        v3_diagnostic["arm_accuracy"]["B"]["comparability"]["accuracy"],
        0.7910112359550562,
    )
    assert math.isclose(
        v3_diagnostic["arm_accuracy"]["C"]["comparability"]["accuracy"],
        0.7617977528089888,
    )
    assert math.isclose(
        v3_diagnostic["arm_accuracy"]["D"]["comparability"]["accuracy"],
        0.7932584269662921,
    )
    assert math.isclose(
        v3_diagnostic["primary"]["estimate"],
        0.03146067415730337,
    )
    assert (
        v3_diagnostic["primary"]["conclusion"]
        == "inconclusive_nonconfirmatory_missingness"
    )
    assert len(read_csv(public_v3 / "public_arm_ratings.csv")) == 5760
    assert len(read_csv(public_v3 / "public_gold_ratings.csv")) == 1440
    assert len(read_csv(public_v3 / "public_adjudications.csv")) == 410
    assert canonical_by_path[
        "manuscript/supplement/v3_quality_gate_results.csv"
    ]["status"] == "historical_posthoc_excluded"
    assert canonical_by_path[
        "manuscript/supplement/v3_quality_gate_critical_errors.csv"
    ]["status"] == "historical_posthoc_excluded"

    human_root = (
        manuscript / "human_coding" / "observed_claim_human_validation_20260714"
    )
    completed = human_root / "annotated_20260714"
    hidden = read_csv(completed / "sample_key.csv")
    assert len(hidden) == 80
    assert Counter(row["model_adjudicated_verdict"] for row in hidden) == Counter(
        {"valid": 26, "partial": 25, "invalid": 25, "under-specified": 4}
    )
    assert Counter(
        row["model_adjudicated_verdict"]
        for row in hidden
        if row["balanced_core_16"] == "1"
    ) == Counter({"valid": 4, "partial": 4, "invalid": 4, "under-specified": 4})
    completed_rows = [
        read_csv(completed / f"annotator_{annotator}_claims_completed.csv")
        for annotator in ("A", "B", "C")
    ]
    assert all(len(rows) == 80 for rows in completed_rows)
    assert sum(len(rows) for rows in completed_rows) == 240
    assert all(len(rows[0]) == 43 for rows in completed_rows)
    adjudicated = read_csv(completed / "adjudicated_consensus.csv")
    assert len(adjudicated[0]) == 16
    adjudicated_by_id = {row["annotation_id"]: row for row in adjudicated}
    consensus = read_csv(
        completed / "analysis_results" / "final" / "human_final_consensus.csv"
    )
    assert len(consensus) == 80
    human_summary = json.loads(
        (
            completed
            / "analysis_results"
            / "final"
            / "human_validation_summary.json"
        ).read_text()
    )
    assert human_summary["adjudicated_distribution"] == {
        "partial": 29,
        "valid": 43,
        "under-specified": 2,
        "invalid": 6,
    }
    assert math.isclose(
        human_summary["human_vs_model_secondary"]["exact_agreement"], 0.5
    )
    assert math.isclose(
        human_summary["human_vs_model_secondary"]["cohen_kappa"],
        0.2725619458967948,
    )
    provenance = human_summary["human_provenance"]
    assert provenance["all_four_people_distinct"] is True
    assert provenance["generative_ai_used_for_annotation_or_adjudication"] is False
    assert provenance["consent"]["explicit"] is True
    assert provenance["ethics_review"]["formal_review_required"] is False
    assert provenance["work_time_hours"]["total_person_hours"] == 210
    assert (human_root / "human_validation_protocol.md").is_file()

    reliability = json.loads(
        (supplement / "claim_reliability_summary.json").read_text()
    )
    assert reliability["status"] == "negative_reliability_study"
    rule_metrics = reliability["rule_metrics"]
    assert math.isclose(
        rule_metrics["three_field_model"]["exact_accuracy"], 0.3
    )
    assert math.isclose(
        rule_metrics["evidence_control_baseline"]["exact_accuracy"], 0.5
    )
    assert math.isclose(
        rule_metrics["five_coordinate_model"]["exact_accuracy"], 0.55
    )
    assert math.isclose(
        rule_metrics["full_schema_model"]["exact_accuracy"], 0.5
    )
    assert reliability["paired_exact_tests"][
        "evidence_control_baseline_vs_full_schema"
    ] == {
        "first_only_correct": 3,
        "second_only_correct": 3,
        "discordant": 6,
        "two_sided_exact_p": 1.0,
    }
    assert reliability["calibration"]["status"] == "not_estimable"
    assert (
        reliability["sampling"]["paper_disjoint_from_codebook_development"]
        is False
    )
    assert reliability["model_inventory_boundary"][
        "c1_c2_c5_decisive_in_remainder"
    ] == 20

    sensitivity = json.loads(
        (supplement / "claim_source_sensitivity_summary.json").read_text()
    )
    assert sensitivity["sample"]["claims"] == 80
    assert sensitivity["sample"]["sources"] == 9
    exact_sensitivity = sensitivity["full_vs_evidence_control"][
        "cluster_bootstrap"
    ]["exact_accuracy"]
    assert math.isclose(exact_sensitivity["point_estimate"], 0.0)
    assert math.isclose(exact_sensitivity["ci_low"], -0.0641025641025641)
    assert math.isclose(exact_sensitivity["ci_high"], 0.0789473684210526)
    assert sensitivity["full_vs_evidence_control"]["equivalence_test"] == (
        "not_performed_no_prespecified_margin"
    )
    assert len(read_csv(supplement / "claim_rule_predictions.csv")) == 80

    heldout_root = (
        manuscript / "human_coding" / "heldout_claim_validation_v3_20260715"
    )
    heldout_summary = json.loads(
        (heldout_root / "candidate_pool_summary.json").read_text()
    )
    heldout_config = json.loads((heldout_root / "study_config.json").read_text())
    assert heldout_config["status"] == (
        "PRE-REGISTERED / NO TEST LABELS COLLECTED"
    )
    assert heldout_config["primary_test_claims"] == 480
    assert heldout_config["primary_test_sources"] == 80
    assert heldout_summary["selected_sources"] == 80
    assert heldout_summary["deterministic_candidates"] == 1568
    assert len(read_csv(heldout_root / "source_sampling_frame.csv")) == 342
    assert len(read_csv(heldout_root / "candidate_claims_deterministic.csv")) == 1582
    frozen_claims = read_csv(heldout_root / "frozen_test_claims.csv")
    assert len(frozen_claims) == 480
    assert len({row["source_key"] for row in frozen_claims}) == 80
    assert set(Counter(row["source_key"] for row in frozen_claims).values()) == {6}
    assert Counter(
        row["coordinator_only_primary_stratum"] for row in frozen_claims
    ) == Counter({"c2_decisive": 240, "c5_decisive": 240})
    assert all(
        row["label_collection_status"] == "NO_TEST_LABELS_COLLECTED"
        for row in frozen_claims
    )
    sampling_rows = read_csv(
        heldout_root / "candidate_claims_model_prescreen.csv"
    )
    assert len(sampling_rows) == 1582
    assert all(
        row["model_only_status"]
        == "MODEL_FREE_SCREENING_INPUT_NOT_MODEL_OR_HUMAN_LABEL"
        and not row["prescreen_system"]
        and not row["prescreen_c2_decisive_probability"]
        and not row["prescreen_c5_decisive_probability"]
        for row in sampling_rows
    )
    assert Counter(row["selection_status"] for row in sampling_rows) == Counter(
        {
            "human_screen_consensus": 1206,
            "human_screen_tiebreak": 376,
        }
    )
    assert Counter(
        row["human_sampling_eligibility"] for row in sampling_rows
    ) == Counter(
        {"eligible_c5": 552, "ineligible": 652, "eligible_c2": 378}
    )
    sampling_summary = json.loads(
        (heldout_root / "sampling_screen_summary.json").read_text()
    )
    assert sampling_summary["status"] == "human_sampling_screen_complete"
    assert sampling_summary["screening_complete"] is True
    replacement_summary = json.loads(
        (heldout_root / "source_replacement_summary.json").read_text()
    )
    assert replacement_summary["status"] == "APPLIED_AWAITING_REPLACEMENT_SCREEN"
    assert replacement_summary["current_batch_id"] == "RB-002"
    assert len(replacement_summary["batches"]) == 2
    replacement_batch = replacement_summary["batches"][-1]
    assert replacement_batch["invariants"][
        "candidate_ids_raw_hashes_human_fields_unchanged"
    ] is True
    assert replacement_batch["invariants"]["retained_sources"] == 79
    assert replacement_batch["outputs"][
        "candidate_claims_deterministic_rows"
    ] == 1582
    assert sum(
        replacement["new_candidates"]
        for replacement in replacement_batch["replacements"]
    ) == 20
    screener_provenance = json.loads(
        (heldout_root / "sampling_screener_provenance.json").read_text()
    )
    assert screener_provenance["status"] == (
        "coordinator_attested_independent_human_sampling_screens"
    )
    assert screener_provenance["generative_ai_used_for_screening"] is False
    assert screener_provenance["full_sources_checked_row_by_row"] is True
    assert len(screener_provenance["sampling_screener_ids"]) == 3
    freeze_summary = json.loads(
        (heldout_root / "sampling_freeze_summary.json").read_text()
    )
    assert freeze_summary["status"] == "FROZEN_NO_TEST_LABELS"
    assert freeze_summary["claims"] == 480
    assert freeze_summary["sources"] == 80
    assert freeze_summary["c2_claims"] == freeze_summary["c5_claims"] == 240
    assert freeze_summary["model_fields_used_for_selection"] is False
    assignments = read_csv(heldout_root / "auditor_assignments.csv")
    assert len(assignments) == 5760
    assert set(
        Counter((row["claim_id"], row["arm"]) for row in assignments).values()
    ) == {3}
    assert set(Counter(row["participant_id"] for row in assignments).values()) == {
        240
    }
    public_roster = read_csv(
        heldout_root / "participant_metadata_public_template.csv"
    )
    assert len(public_roster) == 29
    assert Counter(row["role"] for row in public_roster) == Counter(
        {"auditor": 24, "gold_expert": 3, "adjudicator_1": 1, "adjudicator_2": 1}
    )
    assert all(row["calibration_status"] == "passed_round_1" for row in public_roster)
    assert all(
        row["included_in_primary_analysis"] == "pending_test_completion"
        for row in public_roster
    )
    calibration_summary = json.loads(
        (heldout_root / "calibration_summary.json").read_text()
    )
    assert calibration_summary["status"] == (
        "FROZEN_CALIBRATION_PASSED_BEFORE_TEST"
    )
    assert calibration_summary["calibration_version"] == (
        "v3.0.1-calibration-freeze"
    )
    assert calibration_summary["item_count"] == 10
    assert calibration_summary["participant_status_counts"] == {
        "passed_round_1": 29
    }
    assert len(read_csv(heldout_root / "calibration_items.csv")) == 10
    assert len(read_csv(heldout_root / "calibration_answer_key.csv")) == 10
    assert len(read_csv(heldout_root / "calibration_responses.csv")) == 290
    text_corrections = read_csv(heldout_root / "frozen_text_corrections.csv")
    assert len(text_corrections) == 12
    assert any(row["claim_id"] == "H3-065-14" for row in text_corrections)
    for csv_name in (
        "candidate_claims_deterministic.csv",
        "candidate_claims_model_prescreen.csv",
        "frozen_test_claims.csv",
    ):
        for row in read_csv(heldout_root / csv_name):
            assert not any(
                ord(character) < 32 and character not in "\t\n\r"
                for value in row.values()
                for character in value
            )
    coordinator_registry = json.loads(
        (heldout_root / "coordinator_packet_registry.json").read_text()
    )
    assert coordinator_registry["status"] == (
        "COORDINATOR_STAGE1_REGISTRY_FROZEN"
    )
    assert len(coordinator_registry["packets"]) == 27
    assert len(read_csv(heldout_root / "composition_issuance_rows.csv")) == 7200
    assert not read_csv(heldout_root / "review_extraction_corrections.csv")
    assert not read_csv(heldout_root / "coordinator_response_receipts.csv")
    composition_registry = json.loads(
        (heldout_root / "composition_packet_issuance_registry.json").read_text()
    )
    assert composition_registry["status"] == (
        "COORDINATOR_COMPOSITION_PACKETS_ISSUED"
    )
    assert composition_registry["issuance_count"] == 27
    assert len(composition_registry["issuances"]) == 27
    assert sum(row["row_count"] for row in composition_registry["issuances"]) == 7200
    assert json.loads(
        (heldout_root / "coordinator_collection_receipt.json").read_text()
    )["status"] == "NO_FORMAL_RESPONSES"
    assert json.loads(
        (heldout_root / "adjudicator_packet_registry.json").read_text()
    )["status"] == "NO_ADJUDICATOR_PACKETS_ISSUED"
    for response_name in (
        "arm_A_responses.csv",
        "arm_B_responses.csv",
        "arm_C_responses.csv",
        "arm_D_responses.csv",
        "gold_responses.csv",
        "adjudicator_1_responses.csv",
        "adjudicator_2_responses.csv",
    ):
        assert not read_csv(heldout_root / response_name)

    sampling = read_csv(supplement / "human_validation_sampling_audit.csv")
    assert {
        row["model_stratum"]: (
            int(row["model_inventory_n"]),
            int(row["human_sample_n"]),
        )
        for row in sampling
    } == {
        "valid": (125, 26),
        "partial": (134, 25),
        "invalid": (26, 25),
        "under-specified": (4, 4),
    }
    majority = read_csv(
        completed
        / "analysis_results"
        / "pre_adjudication"
        / "majority_consensus.csv"
    )
    assert sum(row["verdict_unanimous"] == "1" for row in majority) == 39
    assert sum(bool(row["verdict_majority"]) for row in majority) == 78
    assert (
        sum(
            bool(row["verdict_majority"])
            and adjudicated_by_id[row["annotation_id"]]["final_verdict"]
            != row["verdict_majority"]
            for row in majority
        )
        == 9
    )
    subprocess.run(
        ["sha256sum", "-c", "MANIFEST.sha256"],
        cwd=completed,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    with zipfile.ZipFile(manuscript / "review_data_package.zip") as archive:
        names = set(archive.namelist())
        assert "README_DATA.md" in names
        assert "MANIFEST.sha256" in names
        assert (
            "manuscript/human_coding/observed_claim_human_validation_20260714/"
            "annotated_20260714/analysis_results/final/human_final_consensus.csv"
        ) in names
        assert "manuscript/supplement/claim_reliability_summary.json" in names
        assert (
            "manuscript/supplement/claim_source_sensitivity_summary.json"
            in names
        )
        assert "manuscript/scripts/analyze_claim_rule_reliability.py" in names
        assert "manuscript/scripts/analyze_claim_source_sensitivity.py" in names
        assert (
            "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
            "preregistered_protocol.md"
        ) in names
        assert (
            "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
            "analyze_collected_results.py"
        ) in names
        assert (
            "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
            "analysis_output_schema.json"
        ) in names
        assert (
            "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
            "poststudy_analysis_addendum.md"
        ) in names
        assert "manuscript/scripts/reanalyze_public_v3.py" in names
        public_prefix = (
            "manuscript/supplement/v3_human_reanalysis_20260725/"
        )
        expected_public_v3 = {
            public_prefix + path.name for path in public_v3.iterdir() if path.is_file()
        }
        assert len(expected_public_v3) == 13
        assert expected_public_v3 <= names
        assert len(
            {name for name in names if name.startswith(PUBLIC_V3_ROOT)}
        ) == 13
        assert not any(
            name.startswith(V3_ROOT)
            and Path(name).name in PRIVATE_V3_ARTIFACT_BASENAMES
            for name in names
        )
        for name in names:
            if name.startswith((V3_ROOT, PUBLIC_V3_ROOT)):
                validate_v3_data_entry(name, archive.read(name))
        frozen_command = (
            "python manuscript/human_coding/"
            "heldout_claim_validation_v3_20260715/validate_package.py "
            "--mode frozen --portable"
        )
        assert frozen_command in archive.read("README_DATA.md").decode("utf-8")
        assert (
            "manuscript/supplement/v3_preregistered_diagnostic_summary.json"
            in names
        )
        assert (
            "manuscript/human_coding/observed_claim_human_validation_20260714/"
            "human_validation_protocol.md"
        ) in names
        assert not any(
            token in name
            for name in names
            for token in (
                "annotator_packet",
                "coordinator_only",
                "synthetic_",
            )
        )
        assert not any("citation_audit/expanded_texts/" in name for name in names)
        with tempfile.TemporaryDirectory(
            prefix=".release-zip-validation-", dir=repo
        ) as directory:
            archive.extractall(directory)
            subprocess.run(
                [
                    sys.executable,
                    "manuscript/human_coding/"
                    "heldout_claim_validation_v3_20260715/validate_package.py",
                    "--mode",
                    "frozen",
                    "--portable",
                ],
                cwd=directory,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    sys.executable,
                    "manuscript/scripts/reanalyze_public_v3.py",
                    "--verify-published",
                    "--output",
                    ".validate-public-v3",
                ],
                cwd=directory,
                check=True,
                stdout=subprocess.DEVNULL,
            )

    main_pdf = manuscript / "main.pdf"
    all_in_one_pdf = manuscript / "main_all_in_one.pdf"
    assert pdf_pages(main_pdf) == pdf_pages(all_in_one_pdf)
    with tempfile.TemporaryDirectory(
        prefix=".release-pdf-validation-", dir=repo
    ) as directory:
        first = Path(directory) / "main.txt"
        second = Path(directory) / "all.txt"
        pdf_text(main_pdf, first)
        pdf_text(all_in_one_pdf, second)
        def normalized_pdf_text(path: Path) -> str:
            text = path.read_text()
            text = re.sub(r"\b\d+\b", "", text)
            text = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
            return re.sub(r"\s+", " ", text).strip()

        assert normalized_pdf_text(first) == normalized_pdf_text(second)

    reference_page = None
    for page in range(1, min(12, pdf_pages(main_pdf)) + 1):
        output = subprocess.check_output(
            ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(main_pdf), "-"],
            text=True,
        )
        if re.search(r"^\s*(?:\d+\s+)?References(?:\s|$)", output, re.M):
            reference_page = page
            break
    assert reference_page == 9
    page_eight = subprocess.check_output(
        ["pdftotext", "-f", "8", "-l", "8", "-layout", str(main_pdf), "-"],
        text=True,
    )
    assert "Ethics Statement" in page_eight
    assert len(re.findall(r"[A-Za-z]+", page_eight)) >= 150

    log = (manuscript / "main.log").read_text(errors="replace")
    forbidden = [
        "Citation `",
        "Reference `",
        "There were undefined references",
        "multiply defined",
        "Overfull \\hbox",
    ]
    assert not any(token in log for token in forbidden)

    overleaf_root = repo / "overleaf_package"
    manifest_paths = {
        line.split("  ", 1)[1]
        for line in (overleaf_root / "MANIFEST.sha256").read_text().splitlines()
        if line.strip()
    }
    actual_paths = {
        path.relative_to(overleaf_root).as_posix()
        for path in overleaf_root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    assert actual_paths == manifest_paths
    assert f"Release: {release_version}" in (
        overleaf_root / "README_OVERLEAF.txt"
    ).read_text()
    overleaf_archive = repo / "robust-rag-survey-overleaf.zip"
    expected_archive_names = actual_paths | {"MANIFEST.sha256"}
    with zipfile.ZipFile(overleaf_archive) as archive:
        assert set(archive.namelist()) == expected_archive_names
        for name in expected_archive_names:
            assert archive.read(name) == (overleaf_root / name).read_bytes()
        archive_payload = b"\n".join(
            archive.read(name) for name in sorted(expected_archive_names)
        )
        for forbidden in _release_deny_list():
            assert forbidden not in archive_payload
    subprocess.run(
        ["sha256sum", "-c", "MANIFEST.sha256"],
        cwd=overleaf_root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print(
        json.dumps(
            {
                "claim_candidates": len(audit),
                "included_claims": len(included),
                "verdicts": dict(verdicts),
                "bibliography_entries": bibliography_count,
                "canonical_artifacts": len(canonical),
                "release_artifacts": len(release),
                "pdf_pages": pdf_pages(main_pdf),
                "references_start_page": reference_page,
                "human_validation_claims": len(hidden),
                "human_validation_balanced_core": 16,
                "completed_human_judgments": 240,
                "adjudicated_human_consensus": len(consensus),
            },
            indent=2,
        )
    )


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    manuscript = repo / "manuscript"
    supplement = manuscript / "supplement"

    canonical = validate_index_rows(
        read_csv(supplement / "canonical_artifact_index.csv"), repo
    )
    release = validate_index_rows(
        read_csv(supplement / "artifact_release_manifest.csv"), repo
    )
    release_version = (supplement / "RELEASE_VERSION.txt").read_text().strip()
    assert release_version == "eacl27-two-layer-estimand-audit-2026.07.26"
    assert f"Version: `{release_version}`" in (repo / "DATA_LICENSE.md").read_text()
    assert (
        f"{len(canonical)} canonical paths"
        in (manuscript / "tables" / "artifact_release_manifest.tex").read_text()
    )
    assert canonical[
        "manuscript/supplement/assignment_mismatch_simulation.json"
    ]["status"] == "canonical_generated"
    assert canonical[
        "manuscript/supplement/controlled_claim_audit_benchmark.jsonl"
    ]["status"] == "canonical_target_specification"
    assert canonical[
        "manuscript/supplement/controlled_model_judge_results.json"
    ]["status"] == "canonical_generated"
    assert canonical[
        "manuscript/supplement/published_human_evaluation_audit.json"
    ]["status"] == "canonical_source_linked_audit"
    assert canonical[
        "manuscript/supplement/published_human_evaluation_screen_manifest.csv"
    ]["status"] == "canonical_frozen_manifest"
    assert canonical[
        "files/v3_invalidated_shared_answer_run_20260719/invalidation_report.json"
    ]["status"] == "canonical_exclusion_evidence"
    excluded_prefix = "manuscript/supplement/v3_human_reanalysis_20260725/"
    assert not any(
        path.startswith(
            (
                excluded_prefix,
                "manuscript/supplement/v3_",
                "manuscript/tables/v3_",
                "manuscript/tables/main_v3_",
                "manuscript/figures/v3_",
                "manuscript/figures/generated/fig4_v3_",
            )
        )
        for path in release
    )
    assert (
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/README.md"
        not in release
    )
    with zipfile.ZipFile(manuscript / "review_data_package.zip") as archive:
        reviewer_paths = set(archive.namelist())
    heldout_prefix = (
        "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
    )
    assert {
        path for path in release if path.startswith(heldout_prefix)
    }.issubset(reviewer_paths)

    simulation = json.loads(
        (supplement / "assignment_mismatch_simulation.json").read_text()
    )
    assert simulation["schema_version"] == "assignment-mismatch-simulation-v2"
    rows = simulation["rows"]
    assert len(rows) == 7
    assert all(row["replicates"] == 5000 for row in rows)
    assert all(math.isclose(row["true_prompt_effect"], 0.0) for row in rows)
    keyed = {
        (row["source_count"], row["rater_logit_sd"]): row for row in rows
    }
    assert math.isclose(keyed[(80, 0.0)]["source_only_rejection_rate"], 0.049)
    assert math.isclose(keyed[(80, 0.2)]["source_only_rejection_rate"], 0.17)
    assert math.isclose(
        keyed[(80, 0.2)]["same_statistic_permutation_rejection_rate"], 0.0528
    )
    assert math.isclose(
        keyed[(80, 0.2)]["participant_permutation_rejection_rate"], 0.0456
    )
    assert math.isclose(keyed[(160, 0.2)]["source_only_rejection_rate"], 0.2594)
    assert math.isclose(
        keyed[(160, 0.2)]["same_statistic_permutation_rejection_rate"], 0.0492
    )
    table = (
        manuscript / "tables" / "main_assignment_mismatch_simulation.tex"
    ).read_text()
    for text in ("4.9 (0.3)", "7.6 (0.4)", "17.0 (0.5)", "25.9 (0.6)"):
        assert text in table
    full_table = (
        manuscript / "tables" / "assignment_mismatch_simulation_full.tex"
    ).read_text()
    for text in ("4.9\\%", "8.0\\%", "17.0\\%", "28.3\\%", "25.9\\%"):
        assert text in full_table

    benchmark_path = supplement / "controlled_claim_audit_benchmark.jsonl"
    benchmark = [
        json.loads(line)
        for line in benchmark_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(benchmark) == 480
    assert Counter(row["stratum"] for row in benchmark) == Counter(
        {"c2_capability": 240, "c5_utility": 240}
    )
    assert Counter(row["target_decision"] for row in benchmark) == Counter(
        {"deploy_A": 180, "deploy_B": 180, "defer": 120}
    )
    assert len(Counter(row["pair_id"] for row in benchmark)) == 240
    for row in benchmark:
        losses = row["decision_losses"]
        assert row["target_decision"] == min(losses, key=losses.get)
    benchmark_summary = json.loads(
        (supplement / "controlled_claim_audit_benchmark_summary.json").read_text()
    )
    assert benchmark_summary["benchmark_sha256"] == sha256(benchmark_path)
    assert benchmark_summary["counterfactual_controls"] == {
        "c2_defer_cost_fixed_within_pair": True,
        "c2_out_of_envelope_penalty": 0.50,
        "c5_capability_fixed_within_pair": True,
    }
    subprocess.run(
        [
            sys.executable,
            "manuscript/scripts/build_controlled_claim_audit_benchmark.py",
            "--check",
        ],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    model_results = json.loads(
        (supplement / "controlled_model_judge_results.json").read_text()
    )
    assert model_results["schema_version"] == "controlled-model-judge-analysis-v2"
    assert model_results["benchmark_sha256"] == sha256(benchmark_path)
    assert len(model_results["models"]) == 3
    assert len(model_results["rows"]) == 9
    assert all(
        row["ablated_parse_failures"] == 0
        and row["full_parse_failures"] == 0
        for row in model_results["rows"]
    )
    model_all = {
        row["model"]: row
        for row in model_results["rows"]
        if row["stratum"] == "all"
    }
    assert math.isclose(
        model_all["Qwen/Qwen2.5-7B-Instruct"][
            "full_minus_ablated_accuracy"
        ],
        -0.02083333333333337,
    )
    assert math.isclose(
        model_all["microsoft/Phi-4-mini-instruct"][
            "full_minus_ablated_accuracy"
        ],
        0.033333333333333326,
    )
    assert math.isclose(
        model_all["allenai/OLMo-2-1124-7B-Instruct"][
            "full_minus_ablated_accuracy"
        ],
        0.0,
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

    published_audit = json.loads(
        (supplement / "published_human_evaluation_audit_summary.json").read_text()
    )
    assert published_audit["venue_linked_full_texts"] == 39
    assert published_audit["term_screened_candidates"] == 19
    assert published_audit["included_human_judgment_studies"] == 9
    assert published_audit["reporting_counts"]["item_assignment"][
        "not_reported"
    ] == 9
    assert published_audit["confirmed_assignment_unit_mismatches"] == 0
    subprocess.run(
        [
            sys.executable,
            "manuscript/scripts/analyze_published_human_evaluation_audit.py",
        ],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    invalidation = json.loads(
        (
            repo
            / "files"
            / "v3_invalidated_shared_answer_run_20260719"
            / "invalidation_report.json"
        ).read_text()
    )
    assert invalidation["status"] == "INVALIDATED_NOT_FOR_ANALYSIS_OR_PUBLICATION"
    assert invalidation["affected_return_files"] == 27
    assert invalidation["affected_rows"] == 7200
    assert set(
        invalidation["independence_audit"][
            "claims_with_three_identical_full_participant_response_payloads_per_group"
        ].values()
    ) == {480}

    source = (manuscript / "main.tex").read_text()
    included = source + (manuscript / "appendix_extended_survey.tex").read_text()
    assert "HUMAN COLLECTION EXCLUDED" not in source
    # The exclusion disclosure and the de-identification/auditability
    # distinction must survive any rewrite of the manuscript.
    assert "distinguish public de-identification from private auditability" in source
    assert re.search(
        r"exclude every\s+response,\s+contrast,\s+reference statistic",
        source,
        flags=re.IGNORECASE,
    )
    assert (
        "excluded, including from the reviewer-heterogeneity" in source
        or "no quantity derived from it appears" in source
    )
    assert "\\input{survey_main_sections}" in included
    assert "A Coordinate Audit of Published Comparisons" in source
    assert (
        "studentized panel-majority statistic"
        in (manuscript / "tables" / "main_assignment_mismatch_simulation.tex").read_text()
    )
    assert "\\input{tables/main_controlled_model_judges_v2}" in source
    assert "\\input{tables/main_cross_paper_cases}" in source
    assert "\\input{tables/main_retrospective_remedies}" in source
    assert "\\input{tables/main_published_human_evaluation_audit}" in source
    assert "main_v3_" not in source and "v3_secondary" not in source
    for forbidden in (
        "35/480",
        "7.3\\%",
        "+3.1",
        "negative methodological replication",
    ):
        assert forbidden not in source

    with zipfile.ZipFile(manuscript / "review_data_package.zip") as archive:
        names = set(archive.namelist())
        assert not any(name.startswith(excluded_prefix) for name in names)
        assert (
            "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
            "README.md"
            not in names
        )
        assert (
            "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
            "README_REVIEWER_PACKAGE.md"
            in names
        )
        for required in (
            "manuscript/scripts/simulate_assignment_unit_mismatch.py",
            "manuscript/supplement/assignment_mismatch_simulation.json",
            "manuscript/supplement/controlled_claim_audit_benchmark.jsonl",
            "manuscript/supplement/controlled_claim_audit_benchmark_protocol.md",
            "manuscript/supplement/controlled_model_judge_results.json",
            "manuscript/supplement/published_human_evaluation_audit.json",
            "manuscript/supplement/published_human_evaluation_screen_manifest.csv",
            "files/v3_invalidated_shared_answer_run_20260719/invalidation_report.json",
        ):
            assert required in names
        readme = archive.read("README_DATA.md").decode("utf-8")
        assert re.search(
            r"controlled internal\s+participant-response audit trail", readme
        )
        with tempfile.TemporaryDirectory(
            prefix=".review-package-validation-", dir=repo
        ) as directory:
            archive.extractall(directory)
            subprocess.run(
                [
                    sys.executable,
                    "manuscript/human_coding/"
                    "heldout_claim_validation_v3_20260715/"
                    "validate_package.py",
                    "--mode",
                    "frozen",
                    "--portable",
                ],
                cwd=directory,
                check=True,
                stdout=subprocess.DEVNULL,
            )

    main_pdf = manuscript / "main.pdf"
    all_in_one_pdf = manuscript / "main_all_in_one.pdf"
    assert pdf_pages(main_pdf) == pdf_pages(all_in_one_pdf)
    with tempfile.TemporaryDirectory(
        prefix=".release-pdf-validation-", dir=repo
    ) as directory:
        first = Path(directory) / "main.txt"
        second = Path(directory) / "all.txt"
        pdf_text(main_pdf, first)
        pdf_text(all_in_one_pdf, second)
        def normalized_pdf_text(path: Path) -> str:
            text = path.read_text()
            text = re.sub(r"\b\d+\b", "", text)
            text = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
            return re.sub(r"\s+", " ", text).strip()

        assert normalized_pdf_text(first) == normalized_pdf_text(second)

    reference_page = None
    pages_before_references = []
    for page in range(1, min(12, pdf_pages(main_pdf)) + 1):
        output = subprocess.check_output(
            [
                "pdftotext",
                "-f",
                str(page),
                "-l",
                str(page),
                "-layout",
                str(main_pdf),
                "-",
            ],
            text=True,
        )
        if re.search(r"^\s*(?:\d+\s+)?References(?:\s|$)", output, re.M):
            reference_page = page
            break
        pages_before_references.append(output)
    # ACL counts only the numbered body toward the page limit: Limitations,
    # Ethics and References are excluded. The body must therefore end by
    # page 8, i.e. "Limitations" must first appear on page 9 or earlier.
    limitations_page = next(
        (
            index + 1
            for index, text in enumerate(pages_before_references)
            if re.search(r"(?<![A-Za-z])Limitations(?![A-Za-z])", text)
        ),
        None,
    )
    assert limitations_page is not None, "Limitations section not found"
    assert limitations_page <= 9, f"body exceeds 8 pages (Limitations on {limitations_page})"
    assert reference_page is not None and reference_page > limitations_page
    assert len(re.findall(r"[A-Za-z]+", pages_before_references[7])) >= 400
    assert "Ethics Statement" in "\n".join(pages_before_references)

    log = (manuscript / "main.log").read_text(errors="replace")
    forbidden_log = [
        "Citation `",
        "Reference `",
        "There were undefined references",
        "multiply defined",
    ]
    assert not any(token in log for token in forbidden_log)
    overfull = [
        float(value)
        for value in re.findall(
            r"Overfull \\hbox \(([0-9.]+)pt too wide\)", log
        )
    ]
    assert not overfull or max(overfull) < 1.0
    overleaf_root = repo / "overleaf_package"
    manifest_paths = {
        line.split("  ", 1)[1]
        for line in (overleaf_root / "MANIFEST.sha256").read_text().splitlines()
        if line.strip()
    }
    actual_paths = {
        path.relative_to(overleaf_root).as_posix()
        for path in overleaf_root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    assert actual_paths == manifest_paths
    assert f"Release: {release_version}" in (
        overleaf_root / "README_OVERLEAF.txt"
    ).read_text()
    overleaf_archive = repo / "robust-rag-survey-overleaf.zip"
    expected_archive_names = actual_paths | {"MANIFEST.sha256"}
    with zipfile.ZipFile(overleaf_archive) as archive:
        assert set(archive.namelist()) == expected_archive_names
        for name in expected_archive_names:
            assert archive.read(name) == (overleaf_root / name).read_bytes()
        archive_payload = b"\n".join(
            archive.read(name) for name in sorted(expected_archive_names)
        )
        for forbidden in _release_deny_list():
            assert forbidden not in archive_payload
        with tempfile.TemporaryDirectory(
            prefix=".overleaf-import-validation-", dir=repo
        ) as directory:
            archive.extractall(directory)
            subprocess.run(
                [
                    "latexmk",
                    "-pdf",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "main.tex",
                ],
                cwd=directory,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            imported_pdf = Path(directory) / "main.pdf"
            assert pdf_pages(imported_pdf) == pdf_pages(main_pdf)
            imported_log = (Path(directory) / "main.log").read_text(
                errors="replace"
            )
            assert not any(token in imported_log for token in forbidden_log)
    subprocess.run(
        ["sha256sum", "-c", "MANIFEST.sha256"],
        cwd=overleaf_root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print(
        json.dumps(
            {
                "canonical_artifacts": len(canonical),
                "release_artifacts": len(release),
                "simulation_scenarios": len(rows),
                "controlled_benchmark_items": len(benchmark),
                "pdf_pages": pdf_pages(main_pdf),
                "references_start_page": reference_page,
                "excluded_outcome_export": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("usage: validate_release.py")
    main()
