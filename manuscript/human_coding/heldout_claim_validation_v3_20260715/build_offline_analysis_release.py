#!/usr/bin/env python3
"""Validate an offline blind package, analyze it, and build safe release files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from analyze_collected_results import (
    ARMS,
    BOOTSTRAP_REPLICATES,
    COMPARABILITY_LABELS,
    EVIDENCE_LABELS,
    OUTPUTS,
    adjudication_eligible_claims,
    analyze,
    build_public_tables,
    load_deidentification_key,
    sanitize_public_object,
    student_t_quantile,
    write_analysis_outputs,
)
from build_review_packets import (
    ADJUDICATOR_PACKET_HEADER,
    ADJUDICATOR_PACKET_VERSION,
    ADJUDICATOR_REGISTRY_SCHEMA_VERSION,
    adjudication_id as deterministic_adjudication_id,
    build_adjudicator_packets,
    build_adjudicator_registry,
    csv_bytes,
    public_role_roster_sha256,
)
from staged_review_core import MISSING_REASON_CODES


PACKAGE = Path(__file__).resolve().parent
DEFAULT_FROZEN = PACKAGE / "frozen_test_claims.csv"
FREEZE_SUMMARY = PACKAGE / "sampling_freeze_summary.json"
FREEZE_MANIFEST = PACKAGE / "MANIFEST.sha256"
EXPECTED_FROZEN_SHA256 = (
    "36b2d0d2c29836e04be8be192f8542cb1acd736a5c5d4148498c7358574677ce"
)
EXPECTED_FREEZE_SUMMARY_SHA256 = (
    "815e8af476cc696f825dbb47f5ae5e6f45b908beff2525153f8c0e49c79436a1"
)
EXPECTED_FREEZE_VERSION = "v3.0.0-test-freeze"
EXPECTED_LABEL_COLLECTION_STATUS = "NO_TEST_LABELS_COLLECTED"
FROZEN_SCHEMA_ID = "heldout-v3-frozen-claims-v1"
EXPECTED_FROZEN_HEADER = (
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
    "coordinator_only_primary_stratum",
    "sampling_record_sha256",
    "freeze_version",
    "freeze_utc",
    "label_collection_status",
)
INPUT_MANIFEST_SCHEMA = "heldout-v3-offline-input-manifest-v1"
PARTICIPANT_INDEX_HEADER = ("participant_id", "role", "arm", "file_path")
VALID_PACKAGE_STATUSES = {"VALID", "COMPLETE", "COMPLETE_VALID"}
NEGATIVE_STATUS_VALUES = {
    "SUPERSEDED",
    "INVALIDATED",
    "DO NOT USE",
    "NOT FOR ANALYSIS",
    "NOT FOR PUBLICATION",
    "NOT FOR ANALYSIS/PUBLICATION",
    "NOT VALID",
    "NO LONGER VALID",
}
OBVIOUS_INVALID_STATUS_NAMES = (
    re.compile(r"^README_SUPERSEDED.*\.md$", re.IGNORECASE),
    re.compile(r"^INVALIDATION_REPORT.*\.json$", re.IGNORECASE),
)
KNOWN_LEGACY_ROOT_NAMES = {
    "collected_responses",
    "coordinator_collected",
    "generated_packets",
    "generated_staged_review_packets",
    "generated_staged_review_packets_v2",
}
MISSING_STATUSES = {"unable_to_determine"}
REQUIRED_FROZEN = {
    "claim_id",
    "source_key",
    "coordinator_only_primary_stratum",
}
REQUIRED_AUDITOR = {
    "assignment_id",
    "claim_id",
    "source_key",
    "participant_id",
    "arm",
    "extraction_started_utc",
    "extraction_completed_utc",
    "response_status",
    "missing_reason_code",
    "composition_started_utc",
    "evidence_support_label",
    "comparability_label",
    "completed_utc",
}
REQUIRED_GOLD = {
    "gold_response_id",
    "claim_id",
    "source_key",
    "participant_id",
    "response_status",
    "missing_reason_code",
    "review_started_utc",
    "extraction_completed_utc",
    "composition_started_utc",
    "evidence_support_label",
    "comparability_label",
    "completed_utc",
}
REQUIRED_ADJUDICATION = {
    "adjudication_id",
    "claim_id",
    "source_key",
    "participant_id",
    "disputed_outputs",
    "blinded_gold_response_ids",
    "raw_materials_sha256",
    "response_status",
    "missing_reason_code",
}


def fail(message: str) -> None:
    raise ValueError(message)


def read_csv_strict(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    if not path.is_file() or path.is_symlink():
        fail(f"required CSV is absent or is a symlink: {path.name}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header_row = next(reader)
        except StopIteration:
            fail(f"CSV is empty: {path.name}")
        if not header_row or any(not value.strip() for value in header_row):
            fail(f"CSV has an empty header name: {path.name}")
        header = tuple(value.strip() for value in header_row)
        if len(set(header)) != len(header):
            fail(f"CSV has duplicate header names: {path.name}")
        rows: list[dict[str, str]] = []
        for line_number, values in enumerate(reader, start=2):
            if len(values) != len(header):
                fail(f"{path.name} row {line_number} has the wrong column count")
            rows.append(dict(zip(header, values)))
    return header, rows


def require_headers(
    header: Sequence[str], required: set[str], context: str
) -> None:
    missing = sorted(required - set(header))
    if missing:
        fail(f"{context} is missing required headers: {', '.join(missing)}")


def _load_input_manifest(root: Path) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        fail("blind package root must be a real directory")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        fail("blind package root requires a regular manifest.json")
    try:
        text = manifest_path.read_text(encoding="utf-8-sig")
        manifest = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        fail("manifest.json must be readable valid JSON")
    if not isinstance(manifest, dict):
        fail("manifest.json must contain a JSON object")
    status = manifest.get("status")
    if not isinstance(status, str) or status.strip() not in VALID_PACKAGE_STATUSES:
        fail(
            "manifest.json status must exactly equal VALID, COMPLETE, or "
            "COMPLETE_VALID"
        )
    if status != status.strip() or status != status.upper():
        fail("manifest.json status must use an exact canonical value")
    if manifest.get("schema_version") != INPUT_MANIFEST_SCHEMA:
        fail(f"manifest.json schema_version must equal {INPUT_MANIFEST_SCHEMA}")
    _validate_structured_status_markers(root)
    return manifest


def _validate_structured_status_markers(root: Path) -> None:
    for name in KNOWN_LEGACY_ROOT_NAMES:
        if (root / name).exists():
            fail(f"known legacy package path is not accepted: {name}")
    for child in root.iterdir():
        if any(pattern.fullmatch(child.name) for pattern in OBVIOUS_INVALID_STATUS_NAMES):
            fail(f"invalid package status filename is present: {child.name}")
        if (
            "status" not in child.name.lower()
            or child.suffix.lower() != ".json"
        ):
            continue
        if not child.is_file() or child.is_symlink():
            fail(f"structured status file must be a regular file: {child.name}")
        try:
            value = json.loads(child.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            fail(f"structured status file is unreadable: {child.name}")
        statuses: list[object] = []

        def collect_status_fields(node: object) -> None:
            if isinstance(node, dict):
                for key, nested in node.items():
                    normalized = str(key).strip().lower()
                    if normalized == "status" or normalized.endswith("_status"):
                        statuses.append(nested)
                    collect_status_fields(nested)
            elif isinstance(node, list):
                for nested in node:
                    collect_status_fields(nested)

        collect_status_fields(value)
        if any(
            isinstance(status, str)
            and status.strip().upper() in NEGATIVE_STATUS_VALUES
            for status in statuses
        ):
            fail(f"structured status file marks package invalid: {child.name}")


def validate_package_status(root: Path) -> None:
    _load_input_manifest(root)


def _validate_response(
    row: Mapping[str, str],
    context: str,
    evidence_field: str = "evidence_support_label",
    comparability_field: str = "comparability_label",
    disputed: set[str] | None = None,
) -> None:
    status = (row.get("response_status") or "").strip()
    reason = (row.get("missing_reason_code") or "").strip()
    evidence = (row.get(evidence_field) or "").strip()
    comparability = (row.get(comparability_field) or "").strip()
    if status == "completed":
        if reason:
            fail(f"{context}: completed response has a missing reason")
        required_outputs = disputed if disputed is not None else set(OUTPUTS)
        if "evidence_support" in required_outputs and evidence not in EVIDENCE_LABELS:
            fail(f"{context}: invalid completed evidence-support label")
        if "comparability" in required_outputs and comparability not in COMPARABILITY_LABELS:
            fail(f"{context}: invalid completed comparability label")
        if "evidence_support" not in required_outputs and evidence and evidence not in EVIDENCE_LABELS:
            fail(f"{context}: invalid optional evidence-support label")
        if "comparability" not in required_outputs and comparability and comparability not in COMPARABILITY_LABELS:
            fail(f"{context}: invalid optional comparability label")
        return
    if status not in MISSING_STATUSES:
        fail(f"{context}: response_status must be completed or unable_to_determine")
    if reason not in MISSING_REASON_CODES:
        fail(f"{context}: missing response has an invalid missing reason")
    if evidence or comparability:
        fail(f"{context}: missing response must not contain output labels")


def _require_claim_source(
    row: Mapping[str, str],
    claims: Mapping[str, Mapping[str, str]],
    context: str,
) -> str:
    claim_id = (row.get("claim_id") or "").strip()
    source_key = (row.get("source_key") or "").strip()
    if claim_id not in claims:
        fail(f"{context}: response references a non-frozen claim")
    if source_key != (claims[claim_id].get("source_key") or "").strip():
        fail(f"{context}: response source does not match frozen claims")
    return claim_id


def _participant(row: Mapping[str, str], context: str) -> str:
    value = (row.get("participant_id") or "").strip()
    if not value:
        fail(f"{context}: participant_id is empty")
    return value


def validate_authoritative_frozen_metadata() -> None:
    if sha256(FREEZE_SUMMARY) != EXPECTED_FREEZE_SUMMARY_SHA256:
        fail("authoritative sampling_freeze_summary.json hash does not match code")
    try:
        summary = json.loads(FREEZE_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        fail("authoritative sampling_freeze_summary.json is unreadable")
    expected_summary = {
        "status": "FROZEN_NO_TEST_LABELS",
        "claims": 480,
        "sources": 80,
        "c2_claims": 240,
        "c5_claims": 240,
        "frozen_claims_sha256": EXPECTED_FROZEN_SHA256,
    }
    if not isinstance(summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        fail("authoritative freeze metadata does not match the canonical cohort")
    correction = summary.get("pre_test_text_correction")
    if (
        not isinstance(correction, dict)
        or correction.get("schema_version") != "frozen-text-corrections-v1"
        or not isinstance(correction.get("post_correction"), dict)
        or correction["post_correction"].get("frozen_test_claims_sha256")
        != EXPECTED_FROZEN_SHA256
    ):
        fail("post-correction freeze metadata does not anchor the canonical cohort")
    try:
        manifest_lines = FREEZE_MANIFEST.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        fail("authoritative MANIFEST.sha256 is unreadable")
    manifest_hashes = {
        name: digest
        for line in manifest_lines
        if "  " in line
        for digest, name in [line.split("  ", 1)]
    }
    if manifest_hashes.get("frozen_test_claims.csv") != EXPECTED_FROZEN_SHA256:
        fail("MANIFEST.sha256 does not anchor the canonical frozen cohort")


def _validate_frozen_cohort(
    frozen_path: Path,
    expected_sha256: str = EXPECTED_FROZEN_SHA256,
) -> list[dict[str, str]]:
    if sha256(frozen_path) != expected_sha256:
        fail("frozen claims SHA-256 does not match the fixed canonical cohort")
    frozen_header, frozen = read_csv_strict(frozen_path)
    if frozen_header != EXPECTED_FROZEN_HEADER:
        fail(f"frozen claims schema must exactly equal {FROZEN_SCHEMA_ID}")
    if len(frozen) != 480:
        fail("frozen cohort must contain exactly 480 rows")
    claims: set[str] = set()
    source_counts: Counter[str] = Counter()
    strata: Counter[str] = Counter()
    for index, row in enumerate(frozen, start=2):
        claim_id = (row.get("claim_id") or "").strip()
        source = (row.get("source_key") or "").strip()
        stratum = (row.get("coordinator_only_primary_stratum") or "").strip()
        if not claim_id or claim_id in claims or not source:
            fail(f"frozen claims row {index} has an empty or duplicate identifier")
        if stratum not in {"c2_decisive", "c5_decisive"}:
            fail(f"frozen claims row {index} has an invalid primary stratum")
        if (row.get("freeze_version") or "").strip() != EXPECTED_FREEZE_VERSION:
            fail(f"frozen claims row {index} has the wrong freeze version")
        if (
            row.get("label_collection_status") or ""
        ).strip() != EXPECTED_LABEL_COLLECTION_STATUS:
            fail(f"frozen claims row {index} has the wrong label-free status")
        claims.add(claim_id)
        source_counts[source] += 1
        strata[stratum] += 1
    if len(source_counts) != 80 or set(source_counts.values()) != {6}:
        fail("frozen cohort must contain 80 sources with exactly 6 claims each")
    if strata != Counter({"c2_decisive": 240, "c5_decisive": 240}):
        fail("frozen cohort must contain exactly 240 claims in each allowed stratum")
    return frozen


def _validate_manifest_files(
    root: Path, manifest: Mapping[str, Any], paths: Sequence[Path]
) -> None:
    entries = manifest.get("files")
    if not isinstance(entries, list):
        fail("manifest.json files must be an array")
    declared: dict[str, tuple[str, int]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            fail("each manifest.json file entry must be an object")
        relative = entry.get("path")
        digest = entry.get("sha256")
        rows = entry.get("rows")
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or Path(relative).is_absolute()
            or Path(relative).as_posix() != relative
            or ".." in Path(relative).parts
        ):
            fail("manifest.json contains an unsafe or non-canonical file path")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(rows, int)
            or isinstance(rows, bool)
            or rows < 0
        ):
            fail(f"manifest.json has an invalid hash/rows entry for {relative}")
        if relative in declared:
            fail(f"manifest.json repeats file path {relative}")
        declared[relative] = (digest, rows)
    observed = {path.relative_to(root).as_posix(): path for path in paths}
    if set(declared) != set(observed):
        missing = sorted(set(observed) - set(declared))
        extra = sorted(set(declared) - set(observed))
        fail(f"manifest file set mismatch (unlisted={missing}, unused={extra})")
    for relative, path in observed.items():
        digest, expected_rows = declared[relative]
        if path.is_symlink() or not path.is_file():
            fail(f"manifested input must be a regular file: {relative}")
        if sha256(path) != digest:
            fail(f"manifest SHA-256 mismatch: {relative}")
        _header, rows = read_csv_strict(path)
        if len(rows) != expected_rows:
            fail(f"manifest row-count mismatch: {relative}")


def _load_participant_index(root: Path) -> dict[str, dict[str, str]]:
    path = root / "participant_index.csv"
    header, rows = read_csv_strict(path)
    if header != PARTICIPANT_INDEX_HEADER:
        fail("participant_index.csv must use the exact documented schema")
    if len(rows) != 29:
        fail("participant_index.csv must list 24 auditors, 3 gold, and 2 adjudicators")
    indexed: dict[str, dict[str, str]] = {}
    participants: set[str] = set()
    role_counts: Counter[str] = Counter()
    arm_counts: Counter[str] = Counter()
    for index, row in enumerate(rows, start=2):
        participant = (row.get("participant_id") or "").strip()
        role = (row.get("role") or "").strip()
        arm = (row.get("arm") or "").strip()
        file_path = (row.get("file_path") or "").strip()
        if not participant or participant in participants:
            fail(f"participant_index.csv row {index} has an empty/duplicate participant")
        if role not in {"auditor", "gold", "adjudicator"}:
            fail(f"participant_index.csv row {index} has an invalid role")
        if (role == "auditor" and arm not in ARMS) or (
            role != "auditor" and arm
        ):
            fail(f"participant_index.csv row {index} has an invalid arm for its role")
        if (
            not file_path
            or "\\" in file_path
            or Path(file_path).is_absolute()
            or Path(file_path).as_posix() != file_path
            or ".." in Path(file_path).parts
            or file_path in indexed
        ):
            fail(f"participant_index.csv row {index} has an invalid/duplicate file_path")
        participants.add(participant)
        role_counts[role] += 1
        if role == "auditor":
            arm_counts[arm] += 1
        indexed[file_path] = dict(row)
    if role_counts != Counter({"auditor": 24, "gold": 3, "adjudicator": 2}):
        fail("participant_index.csv role cardinalities are invalid")
    if arm_counts != Counter({arm: 6 for arm in ARMS}):
        fail("participant_index.csv must list six auditors in each arm")
    return indexed


def _load_and_validate_adjudicator_registry(
    root: Path,
    manifest: Mapping[str, Any],
    participant_index: Mapping[str, Mapping[str, str]],
    frozen: Sequence[Mapping[str, str]],
    frozen_path: Path,
    gold_rows: Sequence[Mapping[str, str]],
    gold_header: Sequence[str],
) -> tuple[
    dict[str, Any],
    dict[str, str],
    dict[str, dict[str, Mapping[str, object]]],
]:
    if (root / "adjudicator_registry.json").exists():
        fail("noncanonical adjudicator_registry.json is not accepted")
    path = root / "adjudicator_packet_registry.json"
    if not path.is_file() or path.is_symlink():
        fail("formal adjudicator_packet_registry.json is required")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        fail("adjudicator registry is unreadable")
    binding = manifest.get("adjudicator_packet_registry")
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != ADJUDICATOR_REGISTRY_SCHEMA_VERSION
        or payload.get("packet_version") != ADJUDICATOR_PACKET_VERSION
        or payload.get("status") != "COORDINATOR_ADJUDICATOR_PACKETS_ISSUED"
        or not isinstance(payload.get("packets"), list)
        or not isinstance(payload.get("rows"), list)
    ):
        fail("adjudicator registry must use the formal coordinator schema")
    if (
        not isinstance(binding, dict)
        or binding.get("path") != path.name
        or binding.get("sha256") != sha256(path)
        or binding.get("registry_sha256") != payload.get("registry_sha256")
    ):
        fail("manifest does not bind the formal adjudicator registry file/root")
    packets = payload["packets"]
    rows = payload["rows"]
    if (
        len(packets) != 2
        or payload.get("packet_count") != 2
        or payload.get("row_count") != len(rows)
    ):
        fail("formal adjudicator registry must contain exactly two issued packets")
    role_participants: dict[str, str] = {}
    for packet in packets:
        if not isinstance(packet, dict):
            fail("adjudicator registry contains an invalid packet record")
        role = packet.get("adjudicator_role")
        participant = packet.get("participant_id")
        if (
            role not in {"adjudicator_1", "adjudicator_2"}
            or not isinstance(participant, str)
            or not participant.strip()
            or role in role_participants
        ):
            fail("adjudicator registry packet participant/role is invalid")
        role_participants[role] = participant.strip()
    if set(role_participants) != {"adjudicator_1", "adjudicator_2"}:
        fail("adjudicator registry lacks the two named adjudicator roles")
    indexed_adjudicators = {
        row["participant_id"].strip()
        for row in participant_index.values()
        if row["role"].strip() == "adjudicator"
    }
    if set(role_participants.values()) != indexed_adjudicators:
        fail("adjudicator registry participants do not match participant_index.csv")

    roster: list[dict[str, str]] = []
    role_by_participant = {
        participant: role for role, participant in role_participants.items()
    }
    for indexed in participant_index.values():
        role = indexed["role"].strip()
        participant = indexed["participant_id"].strip()
        roster.append(
            {
                "participant_id": participant,
                "role": (
                    "gold_expert"
                    if role == "gold"
                    else role_by_participant.get(participant, role)
                ),
                "assigned_arm": indexed["arm"].strip(),
                "replacement_status": "primary",
            }
        )
    try:
        blank_packets = build_adjudicator_packets(frozen, roster, gold_rows)
        expected = build_adjudicator_registry(
            blank_packets,
            frozen_claims_sha256=sha256(frozen_path),
            gold_responses_sha256=hashlib.sha256(
                csv_bytes(gold_header, gold_rows)
            ).hexdigest(),
            public_role_roster_sha256=public_role_roster_sha256(roster),
        )
    except (KeyError, TypeError, ValueError) as exc:
        fail(f"cannot reconstruct formal adjudicator packets: {exc}")
    if payload != expected:
        fail(
            "formal adjudicator registry/row roots or issued blank packet "
            "hashes do not match frozen claims, gold material, and participants"
        )
    blank_rows_by_role: dict[str, dict[str, Mapping[str, object]]] = {}
    for role in ("adjudicator_1", "adjudicator_2"):
        matching = [
            packet_rows
            for relative, (_header, packet_rows) in blank_packets.items()
            if Path(relative).name.startswith(f"{role}_")
        ]
        if len(matching) != 1:
            fail(f"cannot identify reconstructed blank packet for {role}")
        blank_rows_by_role[role] = {
            str(row["claim_id"]): row for row in matching[0]
        }
    return payload, role_by_participant, blank_rows_by_role


def _load_and_validate_inputs(
    blind_root: Path,
    frozen_path: Path,
    expected_frozen_sha256: str,
) -> tuple[
    list[dict[str, str]],
    dict[str, list[dict[str, str]]],
    dict[str, tuple[str, ...]],
    list[dict[str, str]],
    tuple[str, ...],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    manifest = _load_input_manifest(blind_root)
    frozen = _validate_frozen_cohort(frozen_path, expected_frozen_sha256)
    claims: dict[str, dict[str, str]] = {}
    for row in frozen:
        claim_id = (row.get("claim_id") or "").strip()
        claims[claim_id] = row

    stage2 = blind_root / "stage2"
    adjudication = blind_root / "adjudication"
    if not stage2.is_dir() or not adjudication.is_dir():
        fail("blind package requires stage2/ and adjudication/ directories")
    stage2_files = sorted(stage2.glob("*.csv"))
    adjudication_files = sorted(adjudication.glob("*.csv"))
    if len(stage2_files) != 27:
        fail("stage2/ must contain exactly 24 auditor and 3 gold CSV files")
    if len(adjudication_files) != 2:
        fail("adjudication/ must contain exactly 2 CSV files")
    all_input_files = [*stage2_files, *adjudication_files]
    _validate_manifest_files(blind_root, manifest, all_input_files)
    participant_index = _load_participant_index(blind_root)
    if set(participant_index) != {
        path.relative_to(blind_root).as_posix() for path in all_input_files
    }:
        fail("participant_index.csv file set does not match manifested response files")
    observed_file_identities: dict[str, tuple[str, str, str]] = {}

    arm_rows: dict[str, list[dict[str, str]]] = {arm: [] for arm in ARMS}
    arm_headers: dict[str, tuple[str, ...]] = {}
    gold_rows: list[dict[str, str]] = []
    gold_header: tuple[str, ...] | None = None
    role_ids: dict[str, set[str]] = {
        **{f"auditor_{arm}": set() for arm in ARMS},
        "gold": set(),
        "adjudicator_1": set(),
        "adjudicator_2": set(),
    }
    assignment_ids: set[str] = set()
    gold_response_ids: set[str] = set()
    auditor_files = gold_files = 0

    for path in stage2_files:
        header, rows = read_csv_strict(path)
        header_set = set(header)
        is_gold = "gold_response_id" in header_set
        is_auditor = "assignment_id" in header_set and "arm" in header_set
        if is_gold == is_auditor:
            fail(f"{path.name} cannot be classified as exactly one stage2 role")
        if is_gold:
            gold_files += 1
            require_headers(header, REQUIRED_GOLD, path.name)
            if header[0] != "gold_response_id":
                fail(f"{path.name} must begin with gold_response_id")
            if len(rows) != 480:
                fail(f"{path.name} must contain exactly 480 gold rows")
            if gold_header is None:
                gold_header = header
            elif header != gold_header:
                fail("all gold stage2 files must use the same ordered header")
            participants = {_participant(row, path.name) for row in rows}
            if len(participants) != 1:
                fail(f"{path.name} must contain exactly one gold participant")
            participant = next(iter(participants))
            if participant in role_ids["gold"]:
                fail("one gold participant appears in multiple files")
            role_ids["gold"].add(participant)
            observed_file_identities[path.relative_to(blind_root).as_posix()] = (
                participant,
                "gold",
                "",
            )
            file_claims: set[str] = set()
            for index, row in enumerate(rows, start=2):
                claim_id = _require_claim_source(row, claims, f"{path.name} row {index}")
                if claim_id in file_claims:
                    fail(f"{path.name} repeats a claim")
                file_claims.add(claim_id)
                response_id = (row.get("gold_response_id") or "").strip()
                if not response_id or response_id in gold_response_ids:
                    fail("gold_response_id values must be nonempty and globally unique")
                gold_response_ids.add(response_id)
                _validate_response(row, f"{path.name} row {index}")
            gold_rows.extend(rows)
            continue

        auditor_files += 1
        require_headers(header, REQUIRED_AUDITOR, path.name)
        if header[0] != "assignment_id":
            fail(f"{path.name} must begin with assignment_id")
        if len(rows) != 240:
            fail(f"{path.name} must contain exactly 240 auditor rows")
        participants = {_participant(row, path.name) for row in rows}
        arms = {(row.get("arm") or "").strip() for row in rows}
        if len(participants) != 1 or len(arms) != 1:
            fail(f"{path.name} must contain one participant in one arm")
        participant = next(iter(participants))
        arm = next(iter(arms))
        if arm not in ARMS:
            fail(f"{path.name} has an invalid arm")
        if participant in role_ids[f"auditor_{arm}"]:
            fail("one auditor appears in multiple stage2 files")
        role_ids[f"auditor_{arm}"].add(participant)
        observed_file_identities[path.relative_to(blind_root).as_posix()] = (
            participant,
            "auditor",
            arm,
        )
        if arm in arm_headers and arm_headers[arm] != header:
            fail(f"all arm {arm} files must use the same ordered header")
        arm_headers[arm] = header
        file_claims = set()
        for index, row in enumerate(rows, start=2):
            claim_id = _require_claim_source(row, claims, f"{path.name} row {index}")
            if claim_id in file_claims:
                fail(f"{path.name} repeats a claim")
            file_claims.add(claim_id)
            assignment_id = (row.get("assignment_id") or "").strip()
            if not assignment_id or assignment_id in assignment_ids:
                fail("assignment_id values must be nonempty and globally unique")
            assignment_ids.add(assignment_id)
            _validate_response(row, f"{path.name} row {index}")
        arm_rows[arm].extend(rows)

    if auditor_files != 24 or gold_files != 3 or gold_header is None:
        fail("stage2 role cardinality must be exactly 24 auditors and 3 gold")
    for arm in ARMS:
        if len(role_ids[f"auditor_{arm}"]) != 6:
            fail(f"arm {arm} must contain exactly six unique auditors")
        by_claim = Counter((row.get("claim_id") or "").strip() for row in arm_rows[arm])
        if set(by_claim) != set(claims) or set(by_claim.values()) != {3}:
            fail(f"every frozen claim must have exactly three arm {arm} ratings")
        by_participant = Counter(
            (row.get("participant_id") or "").strip() for row in arm_rows[arm]
        )
        if set(by_participant.values()) != {240}:
            fail(f"every arm {arm} auditor must have exactly 240 rows")
    gold_by_claim = Counter((row.get("claim_id") or "").strip() for row in gold_rows)
    gold_by_participant = Counter(
        (row.get("participant_id") or "").strip() for row in gold_rows
    )
    if set(gold_by_claim) != set(claims) or set(gold_by_claim.values()) != {3}:
        fail("every frozen claim must have exactly three gold ratings")
    if len(gold_by_participant) != 3 or set(gold_by_participant.values()) != {480}:
        fail("gold must contain three unique participants with 480 rows each")
    (
        registry,
        role_by_adjudicator,
        blank_rows_by_role,
    ) = _load_and_validate_adjudicator_registry(
        blind_root,
        manifest,
        participant_index,
        frozen,
        frozen_path,
        gold_rows,
        gold_header,
    )
    registry_rows_by_role = {
        role: {
            str(row["claim_id"]): row
            for row in registry["rows"]
            if row["adjudicator_role"] == role
        }
        for role in ("adjudicator_1", "adjudicator_2")
    }
    expected_disputes: dict[str, set[str]] = defaultdict(set)
    gold_rows_by_claim: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in gold_rows:
        gold_rows_by_claim[(row.get("claim_id") or "").strip()].append(row)
    for claim_id, rows in gold_rows_by_claim.items():
        completed = [
            row
            for row in rows
            if (row.get("response_status") or "").strip() == "completed"
        ]
        if len(completed) != 3:
            continue
        for output in OUTPUTS:
            field = f"{output}_label"
            if len({(row.get(field) or "").strip() for row in completed}) > 1:
                expected_disputes[claim_id].add(output)

    adjudicator_rows_by_role: dict[str, list[dict[str, str]]] = {}
    adjudication_ids: set[str] = set()
    for path in adjudication_files:
        header, rows = read_csv_strict(path)
        if header != ADJUDICATOR_PACKET_HEADER:
            fail(f"{path.name} must retain the exact formal adjudicator packet schema")
        participants = {_participant(row, path.name) for row in rows}
        if len(participants) != 1:
            fail(f"{path.name} must contain exactly one adjudicator")
        participant = next(iter(participants))
        role = role_by_adjudicator.get(participant)
        if role is None or role in adjudicator_rows_by_role:
            fail(f"{path.name} is not bound to one unique registry adjudicator role")
        role_ids[role] = participants
        observed_file_identities[path.relative_to(blind_root).as_posix()] = (
            participant,
            "adjudicator",
            "",
        )
        mapped_rows: list[dict[str, str]] = []
        for index, original in enumerate(rows, start=2):
            row = dict(original)
            claim_id = _require_claim_source(row, claims, f"{path.name} row {index}")
            disputed_raw = (row.get("disputed_outputs") or "").strip()
            disputed = {value for value in disputed_raw.split("|") if value}
            if not disputed or not disputed.issubset(set(OUTPUTS)):
                fail(f"{path.name} row {index}: invalid disputed_outputs")
            if disputed != expected_disputes.get(claim_id, set()):
                fail(
                    f"{path.name} row {index}: disputed_outputs does not match gold"
                )
            registry_row = registry_rows_by_role[role].get(claim_id)
            if registry_row is None:
                fail(f"{path.name} row {index}: claim is absent from registry")
            blank_row = blank_rows_by_role[role].get(claim_id)
            if blank_row is None:
                fail(f"{path.name} row {index}: claim is absent from issued packet")
            for field in ADJUDICATOR_PACKET_HEADER[
                : ADJUDICATOR_PACKET_HEADER.index("response_status")
            ]:
                if (row.get(field) or "").strip() != str(blank_row[field]).strip():
                    fail(
                        f"{path.name} row {index}: issued packet field {field} "
                        "was changed"
                    )
            if (row.get("other_adjudicator_response_seen") or "").strip().lower() not in {
                "false",
                "0",
                "no",
            }:
                fail(
                    f"{path.name} row {index}: other adjudicator response was seen"
                )
            expected_outputs = str(registry_row["disputed_outputs"])
            if disputed_raw != expected_outputs:
                fail(f"{path.name} row {index}: disputed_outputs order was changed")
            for field in (
                "adjudication_id",
                "claim_id",
                "source_key",
                "participant_id",
                "disputed_outputs",
                "blinded_gold_response_ids",
                "raw_materials_sha256",
            ):
                if (row.get(field) or "").strip() != str(registry_row[field]):
                    fail(
                        f"{path.name} row {index}: {field} differs from the "
                        "coordinator registry"
                    )
            expected_id = deterministic_adjudication_id(
                role, participant, claim_id, expected_outputs.split("|")
            )
            if (row.get("adjudication_id") or "").strip() != expected_id:
                fail(f"{path.name} row {index}: adjudication_id is non-deterministic")
            _validate_response(
                row,
                f"{path.name} row {index}",
                "adjudicated_evidence_support_label",
                "adjudicated_comparability_label",
                disputed,
            )
            adjudication_id = (row.get("adjudication_id") or "").strip()
            if not adjudication_id:
                fail(f"{path.name} row {index}: adjudication_id is empty")
            if adjudication_id in adjudication_ids:
                fail("adjudication_id values must be globally unique")
            adjudication_ids.add(adjudication_id)
            mapped_rows.append(row)
        if len({(row.get("claim_id") or "").strip() for row in mapped_rows}) != len(
            mapped_rows
        ):
            fail(f"{path.name} contains duplicate claims")
        adjudicator_rows_by_role[role] = mapped_rows

    if any(len(role_ids[f"adjudicator_{number}"]) != 1 for number in (1, 2)):
        fail("exactly two unique adjudicators are required")
    for file_path, observed in observed_file_identities.items():
        indexed = participant_index[file_path]
        expected = (
            indexed["participant_id"].strip(),
            indexed["role"].strip(),
            indexed["arm"].strip(),
        )
        if observed != expected:
            fail(f"participant_index.csv identity/role/arm mismatch for {file_path}")
    _validate_in_memory_role_sets(
        arm_rows,
        gold_rows,
        adjudicator_rows_by_role["adjudicator_1"],
        adjudicator_rows_by_role["adjudicator_2"],
    )

    gold_grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in gold_rows:
        gold_grouped[(row.get("claim_id") or "").strip()].append(row)
    eligible = adjudication_eligible_claims(gold_grouped)
    for number, rows in enumerate(
        (
            adjudicator_rows_by_role["adjudicator_1"],
            adjudicator_rows_by_role["adjudicator_2"],
        ),
        start=1,
    ):
        covered = {(row.get("claim_id") or "").strip() for row in rows}
        if covered != eligible:
            fail(
                f"adjudicator {number} must cover exactly all complete-gold disagreements"
            )

    return (
        frozen,
        arm_rows,
        arm_headers,
        gold_rows,
        gold_header,
        adjudicator_rows_by_role["adjudicator_1"],
        adjudicator_rows_by_role["adjudicator_2"],
    )


def load_and_validate_inputs(
    blind_root: Path, frozen_path: Path
) -> tuple[
    list[dict[str, str]],
    dict[str, list[dict[str, str]]],
    dict[str, tuple[str, ...]],
    list[dict[str, str]],
    tuple[str, ...],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    return _load_and_validate_inputs(
        blind_root, frozen_path, EXPECTED_FROZEN_SHA256
    )


def tex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def fmt_pct(value: object) -> str:
    number = _number(value)
    return "n/e" if number is None else f"{100.0 * number:.1f}\\%"


def fmt_decimal(value: object) -> str:
    number = _number(value)
    return "n/e" if number is None else f"{number:.3f}"


def fmt_p(value: object) -> str:
    number = _number(value)
    if number is None:
        return "n/e"
    return "$<0.001$" if number < 0.001 else f"{number:.3f}"


def fmt_int(value: object) -> str:
    number = _number(value)
    return "n/e" if number is None else str(int(number))


def fmt_ci(low: object, high: object, percent: bool = True) -> str:
    if _number(low) is None or _number(high) is None:
        return "n/e"
    formatter = fmt_pct if percent else fmt_decimal
    return f"[{formatter(low)}, {formatter(high)}]"


def _macro(name: str, value: object) -> str:
    return rf"\providecommand{{\{name}}}{{{value}}}"


def _read_private_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_paper_results(
    paper_dir: Path,
    results: Mapping[str, Any],
    pairwise: Sequence[Mapping[str, str]],
    agreement: Sequence[Mapping[str, str]],
    sensitivity: Sequence[Mapping[str, str]],
    gold_resolution: Sequence[Mapping[str, str]],
) -> None:
    if (
        sum(row["family"] == "secondary_11_pairwise" for row in pairwise) != 11
        or sum(row["family"] == "secondary_c2_c5" for row in pairwise) != 2
    ):
        fail("analysis did not produce exactly 11 pairwise and 2 subgroup rows")
    paper_dir.mkdir()
    primary = results["primary"]
    missingness = results["missingness"]
    gate_passed = bool(missingness["confirmatory_missingness_rule_passed"])
    macros: list[str] = [
        "% Generated by build_offline_analysis_release.py; do not edit.",
        _macro("VThreeMissingnessGatePassed", "yes" if gate_passed else "no"),
    ]
    for output, title in (
        ("evidence_support", "EvidenceSupport"),
        ("comparability", "Comparability"),
    ):
        rows = [row for row in gold_resolution if row["output"] == output]
        resolved = sum(row["status"] == "resolved" for row in rows)
        macros.extend(
            [
                _macro(f"VThreeResolved{title}", resolved),
                _macro(f"VThreeUnresolved{title}", len(rows) - resolved),
            ]
        )
    for arm in ARMS:
        for output, title in (
            ("evidence_support", "EvidenceSupport"),
            ("comparability", "Comparability"),
        ):
            accuracy = results["arm_accuracy"][arm][output]
            no_consensus = results["no_consensus"][arm][output]
            macros.extend(
                [
                    _macro(
                        f"VThreeArm{arm}{title}Accuracy",
                        fmt_pct(accuracy["accuracy"]),
                    ),
                    _macro(
                        f"VThreeArm{arm}{title}Denominator",
                        fmt_int(accuracy["accuracy_denominator"]),
                    ),
                    _macro(
                        f"VThreeArm{arm}{title}NoConsensus",
                        fmt_pct(no_consensus["rate"]),
                    ),
                ]
            )
    primary_status = str(primary.get("status", "estimated"))
    primary_estimated = _number(primary.get("estimate")) is not None
    equivalence = primary["equivalence"]
    equivalence_flag = (
        "met"
        if equivalence.get("statistical_equivalence_criterion_met") is True
        else "not met"
        if equivalence.get("performed")
        else "n/e"
    )
    bounds = primary["missingness_bounds"]
    macros.extend(
        [
            _macro("VThreePrimaryStatus", tex_escape(primary_status)),
            _macro("VThreePrimaryClaims", fmt_int(primary.get("claims"))),
            _macro("VThreePrimarySources", fmt_int(primary.get("sources"))),
            _macro("VThreePrimaryEffect", fmt_pct(primary.get("estimate"))),
            _macro(
                "VThreePrimaryCRoneCI",
                fmt_ci(primary.get("ci95_low"), primary.get("ci95_high")),
            ),
            _macro(
                "VThreePrimaryBootstrapCI",
                fmt_ci(
                    primary.get("bootstrap_percentile_ci95_low"),
                    primary.get("bootstrap_percentile_ci95_high"),
                ),
            ),
            _macro("VThreePrimaryP", fmt_p(primary.get("p_two_sided"))),
            _macro(
                "VThreePrimaryNinetyCI",
                fmt_ci(
                    equivalence.get("ci90_low"),
                    equivalence.get("ci90_high"),
                ),
            ),
            _macro("VThreePrimaryEquivalenceFlag", equivalence_flag),
            _macro("VThreePrimaryConclusion", tex_escape(primary["conclusion"])),
            _macro("VThreeMissingnessWorstCase", fmt_pct(bounds["worst_case"])),
            _macro("VThreeMissingnessBestCase", fmt_pct(bounds["best_case"])),
            _macro("VThreeMissingnessBoundClaims", fmt_int(bounds["missing_claims"])),
        ]
    )
    agreement_index = {
        (row["arm"], row["output"]): row for row in agreement
    }
    for arm in ARMS:
        for output, title in (
            ("evidence_support", "EvidenceSupport"),
            ("comparability", "Comparability"),
        ):
            row = agreement_index[(arm, output)]
            macros.extend(
                [
                    _macro(
                        f"VThreeArm{arm}{title}Agreement",
                        fmt_pct(row["raw_pairwise_agreement"]),
                    ),
                    _macro(
                        f"VThreeArm{arm}{title}Kappa",
                        fmt_decimal(row["fleiss_kappa"]),
                    ),
                ]
            )
    participant_rows = {
        (row["arm"], row["output"]): row
        for row in sensitivity
        if row["analysis"] == "participant_accuracy_summary"
    }
    for arm in ARMS:
        for output, title in (
            ("evidence_support", "EvidenceSupport"),
            ("comparability", "Comparability"),
        ):
            row = participant_rows[(arm, output)]
            macros.extend(
                [
                    _macro(
                        f"VThreeArm{arm}{title}ParticipantMean",
                        fmt_pct(row["estimate"]),
                    ),
                    _macro(
                        f"VThreeArm{arm}{title}ParticipantMinimum",
                        fmt_pct(row["minimum"]),
                    ),
                    _macro(
                        f"VThreeArm{arm}{title}ParticipantMaximum",
                        fmt_pct(row["maximum"]),
                    ),
                ]
            )
    rater = results["post_hoc_exploratory_rater_sensitivity"]
    permutation = rater["conditional_arm_label_permutation"]
    cgm = rater["individual_rating_two_way_cluster_ols"]
    loao = rater["leave_one_auditor_out"]["summary"]
    cgm_low: object = ""
    cgm_high: object = ""
    if (
        cgm.get("status") == "estimated"
        and _number(cgm.get("estimate")) is not None
        and _number(cgm.get("standard_error")) is not None
        and _number(cgm.get("degrees_freedom")) is not None
    ):
        critical = student_t_quantile(0.975, int(cgm["degrees_freedom"]))
        cgm_low = float(cgm["estimate"]) - critical * float(cgm["standard_error"])
        cgm_high = float(cgm["estimate"]) + critical * float(cgm["standard_error"])
    macros.extend(
        [
            _macro("VThreeConditionalPermutationStatus", tex_escape(permutation["status"])),
            _macro("VThreeConditionalPermutationEffect", fmt_pct(permutation.get("estimate"))),
            _macro("VThreeConditionalPermutationP", fmt_p(permutation.get("p_two_sided"))),
            _macro("VThreeConditionalPermutationCount", fmt_int(permutation.get("permutations"))),
            _macro("VThreeCGMStatus", tex_escape(cgm["status"])),
            _macro("VThreeCGMEffect", fmt_pct(cgm.get("estimate"))),
            _macro("VThreeCGMCI", fmt_ci(cgm_low, cgm_high)),
            _macro("VThreeCGMP", fmt_p(cgm.get("p_two_sided"))),
            _macro("VThreeCGMDegreesFreedom", fmt_int(cgm.get("degrees_freedom"))),
            _macro("VThreeLOAOStatus", tex_escape(loao["status"])),
            _macro("VThreeLOAOMinimum", fmt_pct(loao.get("minimum"))),
            _macro("VThreeLOAOMaximum", fmt_pct(loao.get("maximum"))),
        ]
    )
    for number, number_word in ((1, "One"), (2, "Two")):
        row = results["adjudicator_sensitivity"][f"adjudicator_{number}"]
        macros.extend(
            [
                _macro(
                    f"VThreeAdjudicator{number_word}Status",
                    "estimated" if _number(row.get("estimate")) is not None else "n/e",
                ),
                _macro(
                    f"VThreeAdjudicator{number_word}Effect",
                    fmt_pct(row.get("estimate")),
                ),
                _macro(
                    f"VThreeAdjudicator{number_word}CI",
                    fmt_ci(row.get("ci95_low"), row.get("ci95_high")),
                ),
                _macro(
                    f"VThreeAdjudicator{number_word}P",
                    fmt_p(row.get("p_two_sided")),
                ),
            ]
        )
    (paper_dir / "v3_result_macros.tex").write_text(
        "\n".join(macros) + "\n", encoding="utf-8"
    )

    full_lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\caption{Complete arm results. Accuracy is exact strict-majority agreement with the resolved reference. If the predeclared missingness gate failed, all inferential results are descriptive and non-confirmatory; rater analyses are post hoc.}",
        r"\label{tab:v3-full-results}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Arm & Evidence acc. & Comparability acc. & Comp. no consensus & Evidence $\kappa$ & Comp. $\kappa$ \\",
        r"\midrule",
    ]
    for arm in ARMS:
        full_lines.append(
            "{} & {} & {} & {} & {} & {} \\\\".format(
                arm,
                fmt_pct(results["arm_accuracy"][arm]["evidence_support"]["accuracy"]),
                fmt_pct(results["arm_accuracy"][arm]["comparability"]["accuracy"]),
                fmt_pct(results["no_consensus"][arm]["comparability"]["rate"]),
                fmt_decimal(agreement_index[(arm, "evidence_support")]["fleiss_kappa"]),
                fmt_decimal(agreement_index[(arm, "comparability")]["fleiss_kappa"]),
            )
        )
    full_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    (paper_dir / "main_v3_full_results.tex").write_text(
        "\n".join(full_lines) + "\n", encoding="utf-8"
    )

    primary_ci = fmt_ci(primary.get("ci95_low"), primary.get("ci95_high"))
    cgm_ci = fmt_ci(cgm_low, cgm_high)
    rater_lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\caption{Frozen source-cluster primary analysis and rater sensitivity analyses. Because the predeclared missingness gate failed, every inferential row is descriptive and non-confirmatory. Participant permutation, CGM two-way clustering, and LOAO are explicitly post hoc.}",
        r"\label{tab:v3-rater-sensitivity}",
        r"\begin{tabular}{p{0.34\linewidth}lrrrr}",
        r"\toprule",
        r"Analysis & Status & $n$ & D--C & 95\% CI & $p$ \\",
        r"\midrule",
        "Frozen source-cluster CR1 & {} & {} & {} & {} & {} \\\\".format(
            tex_escape(primary_status if primary_estimated else "not_estimable"),
            fmt_int(primary.get("claims")),
            fmt_pct(primary.get("estimate")),
            primary_ci,
            fmt_p(primary.get("p_two_sided")),
        ),
        "Post hoc participant permutation & {} & {} & {} & n/e & {} \\\\".format(
            tex_escape(permutation["status"]),
            fmt_int(permutation.get("n")),
            fmt_pct(permutation.get("estimate")),
            fmt_p(permutation.get("p_two_sided")),
        ),
        "Post hoc individual-rating CGM & {} & {} & {} & {} & {} \\\\".format(
            tex_escape(cgm["status"]),
            fmt_int(cgm.get("n")),
            fmt_pct(cgm.get("estimate")),
            cgm_ci,
            fmt_p(cgm.get("p_two_sided")),
        ),
        "Post hoc LOAO range & {} & {} & {}--{} & n/e & n/e \\\\".format(
            tex_escape(loao["status"]),
            fmt_int(loao.get("n")),
            fmt_pct(loao.get("minimum")),
            fmt_pct(loao.get("maximum")),
        ),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    (paper_dir / "main_v3_rater_sensitivity.tex").write_text(
        "\n".join(rater_lines) + "\n", encoding="utf-8"
    )

    secondary_lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\caption{All 11 predeclared secondary pairwise contrasts and C2/C5 subgroup contrasts with Holm adjustment. Because the predeclared missingness gate failed, all inferential rows are descriptive and non-confirmatory; all rater analyses reported elsewhere are post hoc.}",
        r"\label{tab:v3-secondary-results}",
        r"\begin{tabular}{llccrrcc}",
        r"\toprule",
        r"Set & Outcome & Contrast & Subset & $n$ & $G$ & Difference [95\% CI] & $p$ / $p_{\mathrm{Holm}}$ \\",
        r"\midrule",
    ]
    for row in pairwise:
        family = (
            "Pairwise"
            if row["family"] == "secondary_11_pairwise"
            else "Stratum"
        )
        outcome = (
            "Support" if row["outcome"] == "evidence_support" else "Compar."
        )
        subset = {
            "all": "All",
            "c2_decisive": "C2",
            "c5_decisive": "C5",
        }.get(str(row["stratum"]), str(row["stratum"]))
        estimable = _number(row.get("difference")) is not None
        effect_ci = (
            f"{fmt_pct(row['difference'])} {fmt_ci(row['ci95_low'], row['ci95_high'])}"
            if estimable
            else "n/e"
        )
        p_values = (
            f"{fmt_p(row['p_two_sided'])} / {fmt_p(row['holm_adjusted_p'])}"
            if estimable
            else "n/e / n/e"
        )
        secondary_lines.append(
            "{} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                family,
                outcome,
                tex_escape(row["contrast"]),
                subset,
                fmt_int(row["claims"]),
                fmt_int(row["sources"]),
                effect_ci,
                p_values,
            )
        )
    secondary_lines.extend(
        [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    )
    (paper_dir / "v3_secondary_results.tex").write_text(
        "\n".join(secondary_lines) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_hashes(output: Path, exclude: Iterable[Path] = ()) -> dict[str, str]:
    excluded = {path.resolve() for path in exclude}
    hashes: dict[str, str] = {}
    for directory in (output / "public_release", output / "paper_results"):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.resolve() not in excluded:
                hashes[path.relative_to(output).as_posix()] = sha256(path)
    return hashes


def write_release_summary(
    output: Path,
    results: Mapping[str, Any],
    agreement: Sequence[Mapping[str, str]],
    pairwise: Sequence[Mapping[str, str]],
) -> None:
    summary_path = output / "paper_results" / "release_summary.json"
    payload = {
        "schema_version": "heldout-v3-offline-paper-results-v1",
        "analysis_status": results["status"],
        "frozen_cohort": {
            "schema_id": FROZEN_SCHEMA_ID,
            "freeze_version": EXPECTED_FREEZE_VERSION,
            "sha256": EXPECTED_FROZEN_SHA256,
        },
        "primary": results["primary"],
        "missingness": results["missingness"],
        "arm_accuracy": results["arm_accuracy"],
        "no_consensus": results["no_consensus"],
        "agreement": list(agreement),
        "secondary_pairwise": list(pairwise),
        "adjudicator_sensitivity": results["adjudicator_sensitivity"],
        "post_hoc_exploratory_rater_sensitivity": results[
            "post_hoc_exploratory_rater_sensitivity"
        ],
        "file_sha256": _release_hashes(output, (summary_path,)),
        "file_hash_scope": (
            "Every existing file under public_release/ and paper_results/ "
            "except this recursively self-referential summary."
        ),
        "privacy": (
            "Aggregate/public-safe fields only; original participant identifiers "
            "and deidentification secrets are excluded."
        ),
        "input_authentication_limitation": (
            "manifest authenticates package bytes but cannot by itself prove "
            "behavioral independence"
        ),
    }
    summary_path.write_text(
        json.dumps(sanitize_public_object(payload), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def write_transfer_notice(output: Path) -> None:
    (output / "TRANSFER_ONLY_THESE.txt").write_text(
        "TRANSFER ONLY THESE TWO DIRECTORIES TO THE NETWORKED PROJECT:\n"
        "  public_release/\n"
        "  paper_results/\n\n"
        "DO NOT TRANSFER private_analysis/, the deidentification key, the blind "
        "package, or any raw response file.\n"
        "SHA256SUMS is an offline integrity inventory and is not an additional "
        "transfer payload.\n",
        encoding="utf-8",
    )


def write_sha256_manifest(output: Path) -> None:
    manifest = output / "SHA256SUMS"
    lines = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path != manifest:
            lines.append(f"{sha256(path)}  {path.relative_to(output).as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_output(output: Path, blind_root: Path) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        fail("output must not exist or must be an empty directory")
    try:
        output.resolve().relative_to(blind_root.resolve())
    except ValueError:
        return
    fail("output must not be inside the blind package")


def _build_release(
    blind_root: Path,
    key_file: Path,
    output: Path,
    frozen_path: Path,
    bootstrap_replicates: int,
    expected_frozen_sha256: str,
) -> None:
    validate_output(output, blind_root)
    inputs = _load_and_validate_inputs(
        blind_root, frozen_path, expected_frozen_sha256
    )
    key = load_deidentification_key(key_file)
    output.mkdir(parents=True, exist_ok=True)
    try:
        results, tables = analyze(*inputs, bootstrap_replicates)
        public_tables = build_public_tables(
            key, inputs[0], inputs[1], inputs[3], inputs[5], inputs[6]
        )
        private = output / "private_analysis"
        write_analysis_outputs(private, results, tables, public_tables)
        nested_public = private / "public_release"
        nested_public.replace(output / "public_release")
        private_results = json.loads(
            (private / "analysis_results.json").read_text(encoding="utf-8")
        )
        private_pairwise = _read_private_csv(private / "analysis_pairwise.csv")
        private_agreement = _read_private_csv(private / "analysis_agreement.csv")
        private_sensitivity = _read_private_csv(
            private / "analysis_rater_sensitivity.csv"
        )
        private_gold_resolution = _read_private_csv(
            private / "analysis_gold_resolution.csv"
        )
        paper = output / "paper_results"
        build_paper_results(
            paper,
            private_results,
            private_pairwise,
            private_agreement,
            private_sensitivity,
            private_gold_resolution,
        )
        write_release_summary(
            output, private_results, private_agreement, private_pairwise
        )
        write_transfer_notice(output)
        write_sha256_manifest(output)
    except Exception:
        shutil.rmtree(output)
        raise
    finally:
        key = b""


def build_release(
    blind_root: Path,
    key_file: Path,
    output: Path,
    frozen_path: Path,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
) -> None:
    validate_authoritative_frozen_metadata()
    _build_release(
        blind_root,
        key_file,
        output,
        frozen_path,
        bootstrap_replicates,
        EXPECTED_FROZEN_SHA256,
    )


def _write_csv(path: Path, header: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _synthetic_package(root: Path) -> tuple[Path, list[str], bytes]:
    blind = root / "synthetic_blind_package"
    stage2 = blind / "stage2"
    adjudication = blind / "adjudication"
    stage2.mkdir(parents=True)
    adjudication.mkdir()
    frozen_header = EXPECTED_FROZEN_HEADER
    frozen = [
        {
            "claim_id": f"synthetic_claim_{index:03d}",
            "source_key": f"synthetic_source_{index // 6:02d}",
            "claim_text": "synthetic claim",
            "context_before": "",
            "context_after": "",
            "source_title": "synthetic source",
            "source_section": "synthetic section",
            "source_locator": "synthetic locator",
            "source_url_or_doi": "https://example.invalid/synthetic",
            "source_evidence_excerpt": "synthetic evidence",
            "source_file_sha256": "a" * 64,
            "coordinator_only_primary_stratum": (
                "c2_decisive" if index % 2 == 0 else "c5_decisive"
            ),
            "sampling_record_sha256": "b" * 64,
            "freeze_version": EXPECTED_FREEZE_VERSION,
            "freeze_utc": "2026-07-15T00:00:00Z",
            "label_collection_status": EXPECTED_LABEL_COLLECTION_STATUS,
        }
        for index in range(480)
    ]
    frozen_path = root / "synthetic_frozen_claims.csv"
    _write_csv(frozen_path, frozen_header, frozen)
    auditor_header = (
        "assignment_id",
        "claim_id",
        "source_key",
        "participant_id",
        "arm",
        "extraction_started_utc",
        "extraction_completed_utc",
        "response_status",
        "missing_reason_code",
        "composition_started_utc",
        "evidence_support_label",
        "comparability_label",
        "completed_utc",
    )
    original_ids: list[str] = []
    formal_roster: list[dict[str, str]] = []
    base_comparability = [
        "same_estimand" if index % 2 == 0 else "different_estimand"
        for index in range(480)
    ]
    for arm_index, arm in enumerate(ARMS):
        participants = [f"private_auditor_{arm}_{number}" for number in range(6)]
        original_ids.extend(participants)
        formal_roster.extend(
            {
                "participant_id": participant,
                "role": "auditor",
                "assigned_arm": arm,
                "replacement_status": "primary",
            }
            for participant in participants
        )
        rows_by_participant: dict[str, list[dict[str, str]]] = {
            participant: [] for participant in participants
        }
        for index, claim in enumerate(frozen):
            assigned = {(index + offset) % 6 for offset in range(3)}
            for number in assigned:
                participant = participants[number]
                correct = (index + arm_index * 3) % (9 - arm_index) != 0
                comp = base_comparability[index]
                if not correct:
                    comp = (
                        "different_estimand"
                        if comp == "same_estimand"
                        else "same_estimand"
                    )
                evidence = (
                    "contradicted"
                    if (index + number + arm_index) % 13 == 0
                    else "supported_as_written"
                )
                rows_by_participant[participant].append(
                    {
                        "assignment_id": f"assignment_{arm}_{index}_{number}",
                        "claim_id": claim["claim_id"],
                        "source_key": claim["source_key"],
                        "participant_id": participant,
                        "arm": arm,
                        "extraction_started_utc": "2026-07-20T00:00:00Z",
                        "extraction_completed_utc": "2026-07-20T00:01:00Z",
                        "response_status": "completed",
                        "missing_reason_code": "",
                        "composition_started_utc": "2026-07-20T00:01:00Z",
                        "evidence_support_label": evidence,
                        "comparability_label": comp,
                        "completed_utc": "2026-07-20T00:02:00Z",
                    }
                )
        for number, participant in enumerate(participants):
            _write_csv(
                stage2 / f"auditor_{arm}_{number}.csv",
                auditor_header,
                rows_by_participant[participant],
            )
    gold_header = (
        "gold_response_id",
        "claim_id",
        "source_key",
        "participant_id",
        "response_status",
        "missing_reason_code",
        "review_started_utc",
        "extraction_completed_utc",
        "composition_started_utc",
        "evidence_support_label",
        "comparability_label",
        "completed_utc",
    )
    disputed_claims: list[dict[str, str]] = []
    all_gold_rows: list[dict[str, str]] = []
    for expert in range(3):
        participant = f"private_gold_{expert}"
        original_ids.append(participant)
        formal_roster.append(
            {
                "participant_id": participant,
                "role": "gold_expert",
                "assigned_arm": "",
                "replacement_status": "primary",
            }
        )
        rows = []
        for index, claim in enumerate(frozen):
            comp = base_comparability[index]
            if index % 20 == 0 and expert == 2:
                comp = (
                    "different_estimand"
                    if comp == "same_estimand"
                    else "same_estimand"
                )
            gold_row = {
                    "gold_response_id": f"gold_{expert}_{index}",
                    "claim_id": claim["claim_id"],
                    "source_key": claim["source_key"],
                    "participant_id": participant,
                    "response_status": "completed",
                    "missing_reason_code": "",
                    "review_started_utc": "2026-07-20T00:00:00Z",
                    "extraction_completed_utc": "2026-07-20T00:01:00Z",
                    "composition_started_utc": "2026-07-20T00:01:00Z",
                    "evidence_support_label": (
                        "contradicted"
                        if index % 20 == 0 and expert == 2
                        else "supported_as_written"
                    ),
                    "comparability_label": comp,
                    "completed_utc": "2026-07-20T00:02:00Z",
                }
            rows.append(gold_row)
            all_gold_rows.append(gold_row)
            if expert == 0 and index % 20 == 0:
                disputed_claims.append(claim)
        _write_csv(stage2 / f"gold_{expert}.csv", gold_header, rows)
    formal_roster.extend(
        {
            "participant_id": f"private_adjudicator_{number}",
            "role": f"adjudicator_{number}",
            "assigned_arm": "",
            "replacement_status": "primary",
        }
        for number in (1, 2)
    )
    blank_packets = build_adjudicator_packets(frozen, formal_roster, all_gold_rows)
    registry = build_adjudicator_registry(
        blank_packets,
        frozen_claims_sha256=sha256(frozen_path),
        gold_responses_sha256=hashlib.sha256(
            csv_bytes(gold_header, all_gold_rows)
        ).hexdigest(),
        public_role_roster_sha256=public_role_roster_sha256(formal_roster),
    )
    (blind / "adjudicator_packet_registry.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for number in (1, 2):
        participant = f"private_adjudicator_{number}"
        original_ids.append(participant)
        packet = next(
            (header, rows)
            for relative, (header, rows) in blank_packets.items()
            if Path(relative).name.startswith(f"adjudicator_{number}_")
        )
        adjudication_header, blank_rows = packet
        rows = []
        for blank in blank_rows:
            row = dict(blank)
            claim_index = int(row["claim_id"].rsplit("_", 1)[1])
            row["response_status"] = "completed"
            row["adjudicated_evidence_support_label"] = "supported_as_written"
            row["evidence_support_rationale"] = "synthetic rationale"
            row["adjudicated_comparability_label"] = base_comparability[claim_index]
            row["comparability_rationale"] = "synthetic rationale"
            row["completed_utc"] = "2026-07-20T00:03:00Z"
            rows.append(row)
        _write_csv(
            adjudication / f"adjudicator_{number}.csv",
            adjudication_header,
            rows,
        )
    _refresh_synthetic_identity_files(blind)
    secret = b"synthetic-self-test-HMAC-key-material-32-bytes-minimum"
    key_path = root / "synthetic_secret_key"
    key_path.write_bytes(secret)
    return frozen_path, original_ids, secret


def _refresh_synthetic_identity_files(
    blind: Path, status: str = "COMPLETE_VALID"
) -> None:
    entries: list[dict[str, object]] = []
    participant_rows: list[dict[str, str]] = []
    for path in sorted(
        [*(blind / "stage2").glob("*.csv"), *(blind / "adjudication").glob("*.csv")]
    ):
        header, rows = read_csv_strict(path)
        relative = path.relative_to(blind).as_posix()
        entries.append(
            {"path": relative, "sha256": sha256(path), "rows": len(rows)}
        )
        participants = {
            (row.get("participant_id") or "").strip() for row in rows
        }
        if len(participants) != 1:
            continue
        if "assignment_id" in header:
            role = "auditor"
            arms = {(row.get("arm") or "").strip() for row in rows}
            arm = next(iter(arms)) if len(arms) == 1 else ""
        elif "gold_response_id" in header:
            role = "gold"
            arm = ""
        else:
            role = "adjudicator"
            arm = ""
        participant_rows.append(
            {
                "participant_id": next(iter(participants)),
                "role": role,
                "arm": arm,
                "file_path": relative,
            }
        )
    manifest: dict[str, object] = {
        "schema_version": INPUT_MANIFEST_SCHEMA,
        "status": status,
        "files": entries,
    }
    registry_path = blind / "adjudicator_packet_registry.json"
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry_root = registry.get("registry_sha256", "")
        except (OSError, json.JSONDecodeError, AttributeError):
            registry_root = ""
        manifest["adjudicator_packet_registry"] = {
            "path": registry_path.name,
            "sha256": sha256(registry_path),
            "registry_sha256": registry_root,
        }
    (blind / "manifest.json").write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_csv(
        blind / "participant_index.csv",
        PARTICIPANT_INDEX_HEADER,
        participant_rows,
    )


def self_test() -> None:
    with tempfile.TemporaryDirectory(
        prefix=".offline_reanalysis_selftest_", dir=PACKAGE
    ) as temporary:
        root = Path(temporary)
        frozen_path, original_ids, secret = _synthetic_package(root)
        blind = root / "synthetic_blind_package"
        key_path = root / "synthetic_secret_key"
        output = root / "release"
        synthetic_frozen_sha256 = sha256(frozen_path)
        short_key = root / "one_byte.key"
        short_key.write_bytes(b"x")
        try:
            load_deidentification_key(short_key)
        except ValueError:
            pass
        else:
            raise AssertionError("offline CLI accepted a one-byte key")

        (root / "README.md").write_text(
            "Parent marker NOT VALID must not be scanned.\n", encoding="utf-8"
        )
        (blind / "README.md").write_text(
            "This valid export documents why an older package was superseded.\n",
            encoding="utf-8",
        )
        validate_package_status(blind)
        for invalid_status in (
            "SUPERSEDED",
            "NOT VALID",
            "NO LONGER VALID",
            "VALID_WITH_UNKNOWN_SUFFIX",
        ):
            _refresh_synthetic_identity_files(blind, invalid_status)
            try:
                validate_package_status(blind)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid status was accepted: {invalid_status}")
        _refresh_synthetic_identity_files(blind)
        mixed_status_manifest = json.loads(
            (blind / "manifest.json").read_text(encoding="utf-8")
        )
        mixed_status_manifest["legacy_status"] = "NOT VALID"
        (blind / "manifest.json").write_text(
            json.dumps(mixed_status_manifest) + "\n", encoding="utf-8"
        )
        validate_package_status(blind)
        _refresh_synthetic_identity_files(blind)
        invalidation_marker = blind / "README_SUPERSEDED_OLD.md"
        invalidation_marker.write_text("historical marker\n", encoding="utf-8")
        try:
            validate_package_status(blind)
        except ValueError:
            pass
        else:
            raise AssertionError("obvious invalid status filename was accepted")
        invalidation_marker.unlink()
        structured_status = blind / "package_status.json"
        structured_status.write_text(
            json.dumps({"status": "INVALIDATED"}) + "\n", encoding="utf-8"
        )
        try:
            validate_package_status(blind)
        except ValueError:
            pass
        else:
            raise AssertionError("structured invalid status was accepted")
        structured_status.unlink()

        registry_path = blind / "adjudicator_packet_registry.json"
        valid_registry_bytes = registry_path.read_bytes()
        registry_path.unlink()
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("missing formal adjudicator registry was accepted")
        registry_path.write_bytes(valid_registry_bytes)
        _refresh_synthetic_identity_files(blind)

        for field, value, message in (
            ("schema_version", "invented-adjudicator-registry-v1", "schema"),
            ("registry_sha256", "0" * 64, "registry root"),
        ):
            tampered_registry = json.loads(valid_registry_bytes)
            tampered_registry[field] = value
            registry_path.write_text(
                json.dumps(tampered_registry, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _refresh_synthetic_identity_files(blind)
            try:
                _load_and_validate_inputs(
                    blind, frozen_path, synthetic_frozen_sha256
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"tampered registry {message} was accepted")
        tampered_registry = json.loads(valid_registry_bytes)
        tampered_registry["packets"][0]["packet_sha256"] = "0" * 64
        registry_path.write_text(
            json.dumps(tampered_registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered issued blank packet hash was accepted")
        for field, value, message in (
            ("adjudication_id", "adj_1_tampered", "adjudication ID"),
            (
                "disputed_outputs",
                "comparability|evidence_support",
                "ordered disputed outputs",
            ),
        ):
            tampered_registry = json.loads(valid_registry_bytes)
            tampered_registry["rows"][0][field] = value
            registry_path.write_text(
                json.dumps(tampered_registry, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _refresh_synthetic_identity_files(blind)
            try:
                _load_and_validate_inputs(
                    blind, frozen_path, synthetic_frozen_sha256
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"tampered registry {message} was accepted")
        tampered_registry = json.loads(valid_registry_bytes)
        tampered_registry["packets"][0]["participant_id"] = "different_adjudicator"
        registry_path.write_text(
            json.dumps(tampered_registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered registry participant was accepted")
        tampered_registry = json.loads(valid_registry_bytes)
        tampered_registry["rows"][0]["record_sha256"] = "0" * 64
        registry_path.write_text(
            json.dumps(tampered_registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered registry row hash was accepted")
        registry_path.write_bytes(valid_registry_bytes)
        _refresh_synthetic_identity_files(blind)

        frozen_header, frozen_rows = read_csv_strict(frozen_path)
        valid_frozen_rows = [dict(row) for row in frozen_rows]
        frozen_rows[0]["coordinator_only_primary_stratum"] = ""
        _write_csv(frozen_path, frozen_header, frozen_rows)
        try:
            _validate_frozen_cohort(frozen_path, sha256(frozen_path))
        except ValueError:
            pass
        else:
            raise AssertionError("empty frozen primary stratum was accepted")
        frozen_rows[0]["coordinator_only_primary_stratum"] = "unknown_stratum"
        _write_csv(frozen_path, frozen_header, frozen_rows)
        try:
            _validate_frozen_cohort(frozen_path, sha256(frozen_path))
        except ValueError:
            pass
        else:
            raise AssertionError("unknown frozen primary stratum was accepted")
        _write_csv(frozen_path, frozen_header, valid_frozen_rows)
        frozen_rows = [dict(row) for row in valid_frozen_rows]
        frozen_rows[0]["claim_text"] = "hash mismatch"
        _write_csv(frozen_path, frozen_header, frozen_rows)
        try:
            _validate_frozen_cohort(frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("frozen cohort hash mismatch was accepted")
        _write_csv(frozen_path, frozen_header, valid_frozen_rows)

        auditor_path = blind / "stage2" / "auditor_A_0.csv"
        original_auditor_bytes = auditor_path.read_bytes()
        auditor_path.write_bytes(original_auditor_bytes + b"\n")
        try:
            _load_and_validate_inputs(
                blind, frozen_path, synthetic_frozen_sha256
            )
        except ValueError:
            pass
        else:
            raise AssertionError("replacement of a manifested response file was accepted")
        auditor_path.write_bytes(original_auditor_bytes)
        _refresh_synthetic_identity_files(blind)

        manifest_path = blind / "manifest.json"
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload["files"][0]["rows"] += 1
        manifest_path.write_text(
            json.dumps(manifest_payload) + "\n", encoding="utf-8"
        )
        try:
            _load_and_validate_inputs(
                blind, frozen_path, synthetic_frozen_sha256
            )
        except ValueError:
            pass
        else:
            raise AssertionError("manifest row-count mismatch was accepted")
        _refresh_synthetic_identity_files(blind)

        auditor_header, auditor_rows = read_csv_strict(auditor_path)
        valid_auditor_rows = [dict(row) for row in auditor_rows]
        for row in auditor_rows:
            row["participant_id"] = "private_gold_0"
        _write_csv(auditor_path, auditor_header, auditor_rows)
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("cross-role participant anomaly was accepted")
        _write_csv(auditor_path, auditor_header, valid_auditor_rows)
        _refresh_synthetic_identity_files(blind)

        index_path = blind / "participant_index.csv"
        index_header, index_rows = read_csv_strict(index_path)
        index_rows[0]["role"] = "gold"
        index_rows[0]["arm"] = ""
        _write_csv(index_path, index_header, index_rows)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("wrong participant-index role was accepted")
        _refresh_synthetic_identity_files(blind)

        adjudicator_path = blind / "adjudication" / "adjudicator_1.csv"
        adjudicator_header, adjudicator_rows = read_csv_strict(adjudicator_path)
        valid_adjudicator_rows = [dict(row) for row in adjudicator_rows]
        adjudicator_rows[0]["adjudication_id"] = "adj_1_tampered"
        _write_csv(adjudicator_path, adjudicator_header, adjudicator_rows)
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered adjudication_id was accepted")
        _write_csv(adjudicator_path, adjudicator_header, valid_adjudicator_rows)
        _refresh_synthetic_identity_files(blind)

        for field, value, message in (
            ("raw_materials_sha256", "0" * 64, "raw-material hash"),
            ("participant_id", "different_adjudicator", "participant"),
            (
                "disputed_outputs",
                "comparability|evidence_support",
                "ordered disputed_outputs",
            ),
        ):
            tampered_rows = [dict(row) for row in valid_adjudicator_rows]
            tampered_rows[0][field] = value
            _write_csv(adjudicator_path, adjudicator_header, tampered_rows)
            _refresh_synthetic_identity_files(blind)
            try:
                _load_and_validate_inputs(
                    blind, frozen_path, synthetic_frozen_sha256
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"tampered adjudicator {message} was accepted")
        _write_csv(adjudicator_path, adjudicator_header, valid_adjudicator_rows)
        _refresh_synthetic_identity_files(blind)

        mixed_header = (
            *adjudicator_header,
            "evidence_support_label",
            "comparability_label",
        )
        _write_csv(adjudicator_path, mixed_header, valid_adjudicator_rows)
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("mixed adjudication label schemas were accepted")
        _write_csv(adjudicator_path, adjudicator_header, valid_adjudicator_rows)
        _refresh_synthetic_identity_files(blind)

        _write_csv(adjudicator_path, adjudicator_header, adjudicator_rows[1:])
        _refresh_synthetic_identity_files(blind)
        try:
            _load_and_validate_inputs(blind, frozen_path, synthetic_frozen_sha256)
        except ValueError:
            pass
        else:
            raise AssertionError("adjudicator coverage anomaly was accepted")
        _write_csv(adjudicator_path, adjudicator_header, valid_adjudicator_rows)
        _refresh_synthetic_identity_files(blind)

        _build_release(
            blind,
            key_path,
            output,
            frozen_path,
            100,
            synthetic_frozen_sha256,
        )
        required = (
            output / "public_release" / "public_release_manifest.json",
            output / "paper_results" / "v3_result_macros.tex",
            output / "paper_results" / "main_v3_full_results.tex",
            output / "paper_results" / "main_v3_rater_sensitivity.tex",
            output / "paper_results" / "v3_secondary_results.tex",
            output / "paper_results" / "release_summary.json",
            output / "TRANSFER_ONLY_THESE.txt",
            output / "SHA256SUMS",
        )
        if not all(path.is_file() for path in required):
            raise AssertionError("release did not generate every required artifact")
        public_bytes = b"".join(
            path.read_bytes()
            for directory in (output / "public_release", output / "paper_results")
            for path in directory.rglob("*")
            if path.is_file()
        )
        if secret in public_bytes or any(
            participant.encode("utf-8") in public_bytes for participant in original_ids
        ):
            raise AssertionError("HMAC secret or original participant ID leaked")
        manifest_lines = (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        if not manifest_lines or any(len(line.split("  ", 1)[0]) != 64 for line in manifest_lines):
            raise AssertionError("SHA256SUMS is malformed")
        summary = json.loads(
            (output / "paper_results" / "release_summary.json").read_text(
                encoding="utf-8"
            )
        )
        if "file_sha256" not in summary:
            raise AssertionError("release summary lacks file hashes")
    print("offline release self-test: PASS")


def _validate_in_memory_role_sets(
    arm_rows: Mapping[str, Sequence[Mapping[str, str]]],
    gold_rows: Sequence[Mapping[str, str]],
    adjudicator_1_rows: Sequence[Mapping[str, str]],
    adjudicator_2_rows: Sequence[Mapping[str, str]],
) -> None:
    roles = [
        *[
            (
                f"auditor_{arm}",
                {(row.get("participant_id") or "").strip() for row in arm_rows[arm]},
            )
            for arm in ARMS
        ],
        (
            "gold",
            {(row.get("participant_id") or "").strip() for row in gold_rows},
        ),
        (
            "adjudicator_1",
            {(row.get("participant_id") or "").strip() for row in adjudicator_1_rows},
        ),
        (
            "adjudicator_2",
            {(row.get("participant_id") or "").strip() for row in adjudicator_2_rows},
        ),
    ]
    for index, (left_name, left) in enumerate(roles):
        for right_name, right in roles[index + 1 :]:
            if left & right:
                fail(f"participant ID crosses roles/arms: {left_name} and {right_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build private analysis, HMAC public release, and paper results."
    )
    parser.add_argument("--blind-package-root", type=Path)
    parser.add_argument("--deidentification-key-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--frozen-claims", type=Path, default=DEFAULT_FROZEN)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test and (
        args.blind_package_root is None
        or args.deidentification_key_file is None
        or args.output is None
    ):
        parser.error(
            "--blind-package-root, --deidentification-key-file, and --output "
            "are required unless --self-test is used"
        )
    return args


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        build_release(
            args.blind_package_root,
            args.deidentification_key_file,
            args.output,
            args.frozen_claims,
        )
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        "offline release complete; transfer only public_release/ and paper_results/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
