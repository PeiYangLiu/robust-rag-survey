#!/usr/bin/env python3
"""Coordinator-side schemas and canonical hashes for staged review v2."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


WORKFLOW_VERSION = "v3.0.0-staged-review-v2"
STAGE1_CONFIG_SCHEMA_VERSION = "staged-review-stage1-config-v2"
PACKET_REGISTRY_SCHEMA_VERSION = "coordinator-packet-registry-v2"
EXTRACTION_HASH_SCHEMA_VERSION = "coordinator-extraction-row-v2"
ISSUANCE_REGISTRY_SCHEMA_VERSION = "composition-issuance-registry-v2.1"
ISSUANCE_RECORD_SCHEMA_VERSION = "composition-issuance-record-v2"
ISSUANCE_ROW_SCHEMA_VERSION = "composition-issuance-row-v2"
STAGE2_CONFIG_SCHEMA_VERSION = "staged-review-stage2-config-v2"
CORRECTION_SCHEMA_VERSION = "coordinator-extraction-correction-v2.1"
INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION = (
    "coordinator-invalidated-composition-archive-v1"
)
INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY = (
    "coordinator_invalidated_composition_archive"
)
RECEIPT_SCHEMA_VERSION = "coordinator-final-response-receipt-v2"
COLLECTION_RECEIPT_SCHEMA_VERSION = "coordinator-collection-receipt-v2"

SHA256_RE = re.compile(r"[0-9a-f]{64}")

EVIDENCE_LABELS = frozenset(
    {
        "supported_as_written",
        "supported_after_narrowing",
        "contradicted",
        "insufficient_source_evidence",
    }
)
COMPARABILITY_LABELS = frozenset(
    {
        "same_estimand",
        "comparable_with_declared_scope",
        "different_estimand",
        "missing_comparison_assumption",
        "not_a_comparability_claim",
    }
)
MISSING_REASON_CODES = frozenset(
    {
        "SOURCE_FILE_UNAVAILABLE",
        "ASSIGNED_AUDITOR_WITHDREW",
        "TECHNICAL_FAILURE",
        "CONFLICT_DISCLOSED",
        "UNABLE_TO_DETERMINE",
        "OTHER_WITH_TEXT",
    }
)
EXPLICIT_EXTRACTION_VALUES = frozenset({"not_applicable", "unknown"})

AUDITOR_IMMUTABLE_FIELDS = (
    "assignment_id",
    "claim_id",
    "source_key",
    "participant_id",
    "arm",
    "claim_text",
    "context_before",
    "context_after",
    "source_title",
    "source_section",
    "source_locator",
    "source_url_or_doi",
    "source_evidence_excerpt",
    "source_file_sha256",
    "packet_version",
    "display_order",
)
GOLD_IMMUTABLE_FIELDS = (
    "gold_response_id",
    "claim_id",
    "source_key",
    "participant_id",
    "claim_text",
    "context_before",
    "context_after",
    "source_title",
    "source_section",
    "source_locator",
    "source_url_or_doi",
    "source_evidence_excerpt",
    "source_file_sha256",
    "packet_version",
    "display_order",
)
ARM_EXTRACTION_FIELDS = {
    "A": (
        "reported_result_facts",
        "number_and_direction_check",
        "quantifier_scope_check",
        "causal_basis_check",
        "compared_items",
        "measured_quantity_and_unit",
        "ordinary_control_notes",
        "source_location_checked",
    ),
    "B": (
        "population_or_setting",
        "intervention",
        "comparison",
        "outcome",
        "outcome_unit_and_aggregation",
        "standard_controls_reported",
        "standard_controls_missing",
        "source_location_checked",
    ),
    "C": (
        "evidence_condition_side_1",
        "evidence_condition_side_2",
        "evidence_condition_relation",
        "intervention_side_1",
        "intervention_side_2",
        "intervention_relation",
        "outcome_side_1",
        "outcome_side_2",
        "outcome_relation",
        "required_controls",
        "control_findings",
        "source_location_checked",
    ),
    "D": (
        "evidence_condition_side_1",
        "evidence_condition_side_2",
        "evidence_condition_relation",
        "origin_or_capability_side_1",
        "origin_or_capability_side_2",
        "origin_or_capability_relation",
        "intervention_side_1",
        "intervention_side_2",
        "intervention_relation",
        "outcome_side_1",
        "outcome_side_2",
        "outcome_relation",
        "policy_or_utility_side_1",
        "policy_or_utility_side_2",
        "policy_or_utility_relation",
        "required_controls",
        "control_findings",
        "source_location_checked",
    ),
}
GOLD_EXTRACTION_FIELDS = (
    "reported_result_facts",
    "compared_items",
    "studied_setting",
    "measured_quantity_and_unit",
    "decision_or_recommendation_context",
    "controls_needed_for_claim",
    "controls_found",
)

LOCK_FIELDS = (
    "extraction_version",
    "prior_extraction_snapshot_sha256",
    "extraction_snapshot_sha256",
)
COMPOSITION_FIELDS = (
    "response_status",
    "missing_reason_code",
    "composition_started_utc",
    "evidence_support_label",
    "evidence_support_reason",
    "narrower_supported_wording",
    "comparability_label",
    "comparability_reason",
    "supported_comparison_scope",
    "unresolved_information",
    "completed_utc",
)
COMPOSITION_AFTER_MISSING_FIELDS = COMPOSITION_FIELDS[2:]

ISSUANCE_ROW_HEADER = (
    "issuance_id",
    "packet_id",
    "participant_id",
    "participant_role",
    "assigned_arm",
    "extraction_response_id",
    "extraction_version",
    "prior_extraction_snapshot_sha256",
    "extraction_snapshot_sha256",
    "locked_row_sha256",
    "display_order",
    "record_sha256",
)
CORRECTION_HEADER = (
    "correction_id",
    "packet_id",
    "participant_id",
    "participant_role",
    "assigned_arm",
    "old_issuance_id",
    "old_issuance_record_sha256",
    "old_extraction_version",
    "old_extraction_rows_root_sha256",
    "new_issuance_id",
    "new_issuance_record_sha256",
    "new_extraction_version",
    "new_extraction_rows_root_sha256",
    "correction_reason",
    "issued_utc",
    "invalidated_composition_archive_relative_path",
    "invalidated_composition_sha256",
    "invalidated_composition_returned",
    "record_sha256",
)
RECEIPT_HEADER = (
    "receipt_id",
    "issuance_id",
    "packet_id",
    "participant_id",
    "participant_role",
    "assigned_arm",
    "extraction_response_id",
    "extraction_snapshot_sha256",
    "canonical_response_file",
    "final_row_sha256",
    "received_utc",
    "record_sha256",
)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def csv_bytes(
    header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> bytes:
    import io

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=header, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def write_csv(
    path: Path,
    header: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_bytes(csv_bytes(header, rows))
    staging.replace(path)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_bytes(json_bytes(value))
    staging.replace(path)


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if not text or not (text.endswith("Z") or text.endswith("+00:00")):
        raise ValueError(f"not an explicit UTC timestamp: {value!r}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid UTC timestamp: {value!r}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"timestamp is not UTC: {value!r}")
    return parsed


def participant_slug(role: str, participant_id: str) -> str:
    prefix = "auditor" if role == "auditor" else "gold_expert"
    digest = hashlib.sha256(
        f"staged-review-v2|{role}|{participant_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{prefix}_{digest}"


def packet_id(role: str, participant_id: str) -> str:
    return "srp_" + hashlib.sha256(
        f"{WORKFLOW_VERSION}|{role}|{participant_id}".encode("utf-8")
    ).hexdigest()[:24]


def packet_spec(role: str, arm: str) -> dict[str, Any]:
    if role == "auditor":
        if arm not in ARM_EXTRACTION_FIELDS:
            raise ValueError(f"invalid auditor arm: {arm}")
        return {
            "participant_role": role,
            "assigned_arm": arm,
            "response_id_field": "assignment_id",
            "immutable_fields": AUDITOR_IMMUTABLE_FIELDS,
            "extraction_fields": ARM_EXTRACTION_FIELDS[arm],
            "extraction_start_field": "extraction_started_utc",
            "extraction_completed_field": "extraction_completed_utc",
            "source_location_field": "source_location_checked",
        }
    if role == "gold_expert":
        if arm:
            raise ValueError("gold packet cannot have an arm")
        return {
            "participant_role": role,
            "assigned_arm": arm,
            "response_id_field": "gold_response_id",
            "immutable_fields": GOLD_IMMUTABLE_FIELDS,
            "extraction_fields": GOLD_EXTRACTION_FIELDS,
            "extraction_start_field": "review_started_utc",
            "extraction_completed_field": "extraction_completed_utc",
            "source_location_field": "",
        }
    raise ValueError(f"unsupported staged role: {role}")


def stage1_header(spec: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        *tuple(spec["immutable_fields"]),
        str(spec["extraction_start_field"]),
        *tuple(spec["extraction_fields"]),
        str(spec["extraction_completed_field"]),
    )


def locked_header(spec: Mapping[str, Any]) -> tuple[str, ...]:
    return (*stage1_header(spec), *LOCK_FIELDS)


def composition_header(spec: Mapping[str, Any]) -> tuple[str, ...]:
    return (*locked_header(spec), *COMPOSITION_FIELDS)


def final_header(spec: Mapping[str, Any]) -> tuple[str, ...]:
    immutable = tuple(spec["immutable_fields"])
    extraction = tuple(spec["extraction_fields"])
    start = str(spec["extraction_start_field"])
    completed = str(spec["extraction_completed_field"])
    if spec["participant_role"] == "auditor":
        return (
            *immutable,
            "response_status",
            "missing_reason_code",
            start,
            completed,
            "extraction_snapshot_sha256",
            *extraction,
            *COMPOSITION_AFTER_MISSING_FIELDS,
        )
    return (
        *immutable,
        "response_status",
        "missing_reason_code",
        start,
        *extraction,
        completed,
        "extraction_snapshot_sha256",
        *COMPOSITION_AFTER_MISSING_FIELDS,
    )


def make_stage1_config(
    *,
    packet: str,
    participant_id: str,
    role: str,
    arm: str,
    expected_rows: int,
) -> dict[str, Any]:
    spec = packet_spec(role, arm)
    return {
        "schema_version": STAGE1_CONFIG_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "packet_id": packet,
        "participant_id": participant_id,
        "participant_role": role,
        "assigned_arm": arm,
        "response_id_field": spec["response_id_field"],
        "immutable_fields": list(spec["immutable_fields"]),
        "extraction_fields": list(spec["extraction_fields"]),
        "extraction_start_field": spec["extraction_start_field"],
        "extraction_completed_field": spec["extraction_completed_field"],
        "source_location_field": spec["source_location_field"],
        "expected_rows": expected_rows,
    }


def immutable_rows_sha256(
    rows: Sequence[Mapping[str, str]], immutable_fields: Sequence[str]
) -> str:
    return canonical_sha256(
        {
            "schema_version": "coordinator-immutable-rows-v2",
            "rows": [
                {field: (row.get(field) or "") for field in immutable_fields}
                for row in rows
            ],
        }
    )


def ordered_response_ids_sha256(
    rows: Sequence[Mapping[str, str]], response_id_field: str
) -> str:
    return canonical_sha256(
        {
            "schema_version": "coordinator-response-order-v2",
            "ids": [(row.get(response_id_field) or "") for row in rows],
        }
    )


def registry_entry_sha256(entry: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            "schema_version": "coordinator-packet-registry-entry-v2",
            "entry": {
                key: value
                for key, value in entry.items()
                if key != "entry_sha256"
            },
        }
    )


def packet_registry_sha256(registry: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            key: value
            for key, value in registry.items()
            if key != "registry_sha256"
        }
    )


def issuance_record_sha256(record: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            "schema_version": ISSUANCE_RECORD_SCHEMA_VERSION,
            "record": {
                key: value
                for key, value in record.items()
                if key != "record_sha256"
            },
        }
    )


def issuance_registry_sha256(registry: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            key: value
            for key, value in registry.items()
            if key != "registry_sha256"
        }
    )


def issuance_row_record_sha256(row: Mapping[str, str]) -> str:
    return canonical_sha256(
        {
            "schema_version": ISSUANCE_ROW_SCHEMA_VERSION,
            "record": {
                field: (row.get(field) or "")
                for field in ISSUANCE_ROW_HEADER
                if field != "record_sha256"
            },
        }
    )


def correction_record_sha256(row: Mapping[str, str]) -> str:
    return canonical_sha256(
        {
            "schema_version": CORRECTION_SCHEMA_VERSION,
            "record": {
                field: (row.get(field) or "")
                for field in CORRECTION_HEADER
                if field != "record_sha256"
            },
        }
    )


def receipt_record_sha256(row: Mapping[str, str]) -> str:
    return canonical_sha256(
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "record": {
                field: (row.get(field) or "")
                for field in RECEIPT_HEADER
                if field != "record_sha256"
            },
        }
    )


def collection_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            key: value
            for key, value in receipt.items()
            if key != "receipt_sha256"
        }
    )


def extraction_snapshot_sha256(
    row: Mapping[str, str],
    *,
    coordinator_registry_sha256: str,
    issuance_id: str,
    packet: str,
    participant_id: str,
    participant_role: str,
    assigned_arm: str,
    response_id_field: str,
    extraction_hash_fields: Sequence[str],
    extraction_version: int,
    prior_extraction_snapshot_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "schema_version": EXTRACTION_HASH_SCHEMA_VERSION,
            "workflow_version": WORKFLOW_VERSION,
            "coordinator_packet_registry_sha256": coordinator_registry_sha256,
            "issuance_id": issuance_id,
            "packet_id": packet,
            "participant_id": participant_id,
            "participant_role": participant_role,
            "assigned_arm": assigned_arm,
            "response_id_field": response_id_field,
            "extraction_response_id": (row.get(response_id_field) or ""),
            "extraction_version": extraction_version,
            "prior_extraction_snapshot_sha256": (
                prior_extraction_snapshot_sha256
            ),
            "fields": {
                field: (row.get(field) or "")
                for field in extraction_hash_fields
            },
        }
    )


def locked_row_sha256(
    row: Mapping[str, str], header: Sequence[str]
) -> str:
    return canonical_sha256(
        {
            "schema_version": "coordinator-locked-row-v2",
            "row": {field: (row.get(field) or "") for field in header},
        }
    )


def issuance_rows_root_sha256(rows: Sequence[Mapping[str, str]]) -> str:
    return canonical_sha256(
        {
            "schema_version": "composition-issuance-rows-root-v2",
            "record_sha256": [(row.get("record_sha256") or "") for row in rows],
        }
    )


def final_row_sha256(
    row: Mapping[str, str], header: Sequence[str], canonical_file: str
) -> str:
    return canonical_sha256(
        {
            "schema_version": "coordinator-final-response-row-v2",
            "canonical_response_file": canonical_file,
            "row": {field: (row.get(field) or "") for field in header},
        }
    )


def validate_stage1_submission(
    header: Sequence[str],
    rows: list[dict[str, str]],
    expected_rows: Sequence[Mapping[str, str]],
    spec: Mapping[str, Any],
    issued_utc: str,
) -> None:
    if tuple(header) != stage1_header(spec):
        raise ValueError("returned extraction has the wrong schema")
    if len(rows) != len(expected_rows):
        raise ValueError("returned extraction has the wrong row count")
    completion = parse_utc(issued_utc)
    response_id_field = str(spec["response_id_field"])
    for index, (row, expected) in enumerate(
        zip(rows, expected_rows), start=1
    ):
        for field in spec["immutable_fields"]:
            if (row.get(field) or "") != (expected.get(field) or ""):
                raise ValueError(
                    f"returned extraction row {index} changed immutable field "
                    f"{field}"
                )
        if (row.get(response_id_field) or "") != (
            expected.get(response_id_field) or ""
        ):
            raise ValueError(
                f"returned extraction row {index} changed response ID"
            )
        started = parse_utc(
            (row.get(spec["extraction_start_field"]) or "").strip()
        )
        if started > completion:
            raise ValueError(
                f"returned extraction row {index} starts after issuance"
            )
        completed_field = str(spec["extraction_completed_field"])
        if (row.get(completed_field) or "").strip():
            raise ValueError(
                f"returned extraction row {index} prepopulates coordinator "
                "completion time"
            )
        for field in spec["extraction_fields"]:
            if not (row.get(field) or "").strip():
                raise ValueError(
                    f"returned extraction row {index} leaves {field} blank"
                )
        location = str(spec["source_location_field"])
        if location and (row.get(location) or "").strip().lower() not in {
            "yes",
            *EXPLICIT_EXTRACTION_VALUES,
        }:
            raise ValueError(
                f"returned extraction row {index} has invalid {location}"
            )
        row[completed_field] = issued_utc


def validate_composition_row(row: Mapping[str, str], context: str) -> None:
    status = (row.get("response_status") or "").strip()
    missing_reason = (row.get("missing_reason_code") or "").strip()
    started = parse_utc((row.get("composition_started_utc") or "").strip())
    completed = parse_utc((row.get("completed_utc") or "").strip())
    extraction_completed = parse_utc(
        (row.get("extraction_completed_utc") or "").strip()
    )
    if started < extraction_completed:
        raise ValueError(f"{context} starts before coordinator extraction lock")
    if completed < started:
        raise ValueError(f"{context} completes before it starts")
    substantive = (
        "evidence_support_label",
        "evidence_support_reason",
        "narrower_supported_wording",
        "comparability_label",
        "comparability_reason",
        "supported_comparison_scope",
    )
    unresolved = (row.get("unresolved_information") or "").strip()
    if status == "unable_to_determine":
        if missing_reason not in MISSING_REASON_CODES:
            raise ValueError(f"{context} has an invalid missing reason")
        if any((row.get(field) or "").strip() for field in substantive):
            raise ValueError(f"{context} supplies labels despite missing status")
        if (missing_reason == "OTHER_WITH_TEXT") != bool(unresolved):
            raise ValueError(
                f"{context} must supply text only for OTHER_WITH_TEXT"
            )
        return
    if status != "completed":
        raise ValueError(f"{context} has an invalid response status")
    if missing_reason:
        raise ValueError(f"{context} has a missing code despite completion")
    evidence = (row.get("evidence_support_label") or "").strip()
    comparability = (row.get("comparability_label") or "").strip()
    if evidence not in EVIDENCE_LABELS:
        raise ValueError(f"{context} has an invalid evidence label")
    if comparability not in COMPARABILITY_LABELS:
        raise ValueError(f"{context} has an invalid comparability label")
    if not (row.get("evidence_support_reason") or "").strip():
        raise ValueError(f"{context} has a blank evidence reason")
    if not (row.get("comparability_reason") or "").strip():
        raise ValueError(f"{context} has a blank comparability reason")
    narrower = (row.get("narrower_supported_wording") or "").strip()
    if (evidence == "supported_after_narrowing") != bool(narrower):
        raise ValueError(f"{context} has inconsistent narrower wording")
    scope = (row.get("supported_comparison_scope") or "").strip()
    if (comparability == "comparable_with_declared_scope") != bool(scope):
        raise ValueError(f"{context} has inconsistent comparison scope")
    needs_unresolved = (
        evidence == "insufficient_source_evidence"
        or comparability == "missing_comparison_assumption"
    )
    if needs_unresolved and not unresolved:
        raise ValueError(f"{context} lacks unresolved information")
    if not needs_unresolved and unresolved:
        raise ValueError(f"{context} has inapplicable unresolved information")
