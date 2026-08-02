#!/usr/bin/env python3
"""Coordinator-only issuance of locked composition packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_staged_review_packets import (
    FORMAL_RESPONSE_FILES,
    initialize_empty_coordinator_state,
    validate_registry_against_package,
    write_stage1_packets,
)
from score_calibration import assert_calibration_release
from staged_review_core import (
    COMPOSITION_FIELDS,
    CORRECTION_HEADER,
    CORRECTION_SCHEMA_VERSION,
    INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY,
    INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION,
    ISSUANCE_RECORD_SCHEMA_VERSION,
    ISSUANCE_REGISTRY_SCHEMA_VERSION,
    ISSUANCE_ROW_HEADER,
    LOCK_FIELDS,
    STAGE2_CONFIG_SCHEMA_VERSION,
    WORKFLOW_VERSION,
    composition_header,
    correction_record_sha256,
    csv_bytes,
    extraction_snapshot_sha256,
    issuance_record_sha256,
    issuance_registry_sha256,
    issuance_row_record_sha256,
    issuance_rows_root_sha256,
    json_bytes,
    locked_header,
    locked_row_sha256,
    packet_spec,
    parse_utc,
    read_csv,
    sha256_bytes,
    sha256_file,
    stage1_header,
    validate_stage1_submission,
    write_csv,
    write_json,
)


PACKAGE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = PACKAGE / "coordinator_packet_registry.json"
DEFAULT_ISSUANCE_REGISTRY = (
    PACKAGE / "composition_packet_issuance_registry.json"
)
DEFAULT_ISSUANCE_ROWS = PACKAGE / "composition_issuance_rows.csv"
DEFAULT_CORRECTIONS = PACKAGE / "review_extraction_corrections.csv"
DEFAULT_OUTPUT = PACKAGE / "generated_composition_packets_v2"

STAGE2_INSTRUCTIONS = """# Final review submission

The coordinator has locked the source-linked extraction. Do not edit any raw,
extraction, version, or hash field in `composition.csv`.

For `response_status=completed`, provide both labels and both nonempty reasons.

Evidence-support label:
- `supported_as_written`
- `supported_after_narrowing`
- `contradicted`
- `insufficient_source_evidence`

Comparability label:
- `same_estimand`
- `comparable_with_declared_scope`
- `different_estimand`
- `missing_comparison_assumption`
- `not_a_comparability_claim`

Fill `narrower_supported_wording` only for
`supported_after_narrowing`. Fill `supported_comparison_scope` only for
`comparable_with_declared_scope`. Fill `unresolved_information` for
insufficient source evidence or a missing comparison assumption.

Use `response_status=unable_to_determine` only with a preregistered uppercase
missing-reason code. Leave substantive labels and reasons blank; only
`OTHER_WITH_TEXT` uses `unresolved_information`.

Fill `composition_started_utc` and `completed_utc` as explicit UTC timestamps,
then return `composition.csv` to the coordinator. Any extraction correction
must be requested through the coordinator; do not alter locked fields.
"""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return value


def verify_packet_registry_manifest_anchor(
    packet_registry_path: Path, manifest_path: Path
) -> None:
    expected = ""
    try:
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            digest, relative = line.split("  ", 1)
            if relative == "coordinator_packet_registry.json":
                expected = digest
                break
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read package manifest anchor: {exc}") from exc
    if not expected or sha256_file(packet_registry_path) != expected:
        raise ValueError(
            "coordinator packet registry is not anchored by MANIFEST.sha256"
        )


def invalidated_archive_relative_path(
    packet_id: str, extraction_version: int
) -> str:
    return (
        f"{INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY}/{packet_id}/"
        f"composition_v{extraction_version:03d}.csv"
    )


def resolve_invalidated_archive(
    coordinator_root: Path, relative_path: str
) -> Path:
    relative = Path(relative_path)
    if (
        not relative_path
        or relative.is_absolute()
        or relative.as_posix() != relative_path
        or not relative.parts
        or relative.parts[0] != INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("invalidated composition archive path is unsafe")
    root = coordinator_root.resolve()
    candidate = (coordinator_root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "invalidated composition archive escapes coordinator root"
        ) from exc
    return candidate


def invalidated_archive_index(
    corrections: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "correction_id": row["correction_id"],
            "packet_id": row["packet_id"],
            "old_issuance_id": row["old_issuance_id"],
            "new_issuance_id": row["new_issuance_id"],
            "relative_path": row[
                "invalidated_composition_archive_relative_path"
            ],
            "sha256": row["invalidated_composition_sha256"],
        }
        for row in corrections
    ]


def validate_issuance_state(
    packet_registry_path: Path,
    issuance_registry_path: Path,
    issuance_rows_path: Path,
    corrections_path: Path,
    *,
    verify_archive_files: bool = True,
) -> tuple[
    dict[str, Any],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    registry = load_json(issuance_registry_path)
    required = {
        "schema_version",
        "workflow_version",
        "status",
        "coordinator_packet_registry_sha256",
        "issuance_rows_sha256",
        "correction_ledger_sha256",
        "invalidated_composition_archive_schema_version",
        "invalidated_composition_archives",
        "issuance_count",
        "issuances",
        "registry_sha256",
    }
    if set(registry) != required:
        raise ValueError("composition issuance registry schema changed")
    if (
        registry["schema_version"] != ISSUANCE_REGISTRY_SCHEMA_VERSION
        or registry["workflow_version"] != WORKFLOW_VERSION
        or registry["invalidated_composition_archive_schema_version"]
        != INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION
        or registry["registry_sha256"] != issuance_registry_sha256(registry)
    ):
        raise ValueError("composition issuance registry hash/version is invalid")
    if registry["coordinator_packet_registry_sha256"] != sha256_file(
        packet_registry_path
    ):
        raise ValueError("issuance registry is detached from packet registry")
    row_header, rows = read_csv(issuance_rows_path)
    correction_header, corrections = read_csv(corrections_path)
    if row_header != ISSUANCE_ROW_HEADER:
        raise ValueError("composition issuance row schema changed")
    if correction_header != CORRECTION_HEADER:
        raise ValueError("coordinator correction schema changed")
    if registry["issuance_rows_sha256"] != sha256_file(issuance_rows_path):
        raise ValueError("issuance row ledger hash changed")
    if registry["correction_ledger_sha256"] != sha256_file(corrections_path):
        raise ValueError("coordinator correction ledger hash changed")
    if any(
        row["record_sha256"] != issuance_row_record_sha256(row)
        for row in rows
    ):
        raise ValueError("issuance row ledger contains an invalid record hash")
    for row in rows:
        try:
            version = int(row["extraction_version"])
            display_order = int(row["display_order"])
        except ValueError as exc:
            raise ValueError("issuance row version/order is invalid") from exc
        if version < 1 or display_order < 1:
            raise ValueError("issuance row version/order is invalid")
        for field in (
            "extraction_snapshot_sha256",
            "locked_row_sha256",
            "record_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", row[field]):
                raise ValueError(f"issuance row {field} is invalid")
        prior = row["prior_extraction_snapshot_sha256"]
        if prior and not re.fullmatch(r"[0-9a-f]{64}", prior):
            raise ValueError("issuance row prior hash is invalid")
    if any(
        row["record_sha256"] != correction_record_sha256(row)
        for row in corrections
    ):
        raise ValueError("correction ledger contains an invalid record hash")
    if registry["invalidated_composition_archives"] != (
        invalidated_archive_index(corrections)
    ):
        raise ValueError("issuance registry archive index is invalid")
    issuances = registry["issuances"]
    if not isinstance(issuances, list) or registry["issuance_count"] != len(
        issuances
    ):
        raise ValueError("issuance registry count is invalid")
    issuance_ids: set[str] = set()
    issuance_by_id: dict[str, Mapping[str, Any]] = {}
    issuance_times: dict[str, Any] = {}
    issuance_versions: dict[str, int] = {}
    rows_by_issuance: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        rows_by_issuance.setdefault(row["issuance_id"], []).append(row)
    issuance_required = {
        "schema_version",
        "issuance_id",
        "packet_id",
        "participant_id",
        "participant_role",
        "assigned_arm",
        "extraction_version",
        "prior_issuance_id",
        "issued_utc",
        "returned_extraction_sha256",
        "locked_extraction_sha256",
        "composition_template_sha256",
        "instructions_stage2_sha256",
        "stage2_config_sha256",
        "extraction_rows_root_sha256",
        "row_count",
        "relative_directory",
        "record_sha256",
    }
    for record in issuances:
        if not isinstance(record, dict):
            raise ValueError("issuance registry record is not an object")
        issuance_id = str(record.get("issuance_id") or "")
        if (
            set(record) != issuance_required
            or record.get("schema_version") != ISSUANCE_RECORD_SCHEMA_VERSION
            or not issuance_id
            or issuance_id in issuance_ids
            or record.get("record_sha256") != issuance_record_sha256(record)
        ):
            raise ValueError("issuance registry record ID/hash is invalid")
        try:
            issued_time = parse_utc(str(record.get("issued_utc") or ""))
            version = int(record.get("extraction_version"))
        except (ValueError, TypeError) as exc:
            raise ValueError("issuance record time/version is invalid") from exc
        if version < 1 or not isinstance(record.get("row_count"), int):
            raise ValueError("issuance record version/count is invalid")
        for field in (
            "returned_extraction_sha256",
            "locked_extraction_sha256",
            "composition_template_sha256",
            "instructions_stage2_sha256",
            "stage2_config_sha256",
            "extraction_rows_root_sha256",
            "record_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(record.get(field) or "")):
                raise ValueError(f"issuance record {field} is invalid")
        issuance_ids.add(issuance_id)
        issuance_by_id[issuance_id] = record
        issuance_times[issuance_id] = issued_time
        issuance_versions[issuance_id] = version
        record_rows = rows_by_issuance.get(issuance_id, [])
        if (
            len(record_rows) != record.get("row_count")
            or issuance_rows_root_sha256(record_rows)
            != record.get("extraction_rows_root_sha256")
        ):
            raise ValueError("issuance record row anchors are invalid")
    if set(rows_by_issuance) != issuance_ids:
        raise ValueError("issuance row ledger references an unknown issuance")
    for issuance_id, record in issuance_by_id.items():
        prior_id = str(record.get("prior_issuance_id") or "")
        version = issuance_versions[issuance_id]
        if version == 1:
            if prior_id:
                raise ValueError("first issuance unexpectedly has a prior")
            continue
        prior = issuance_by_id.get(prior_id)
        if (
            prior is None
            or prior["packet_id"] != record["packet_id"]
            or issuance_versions[prior_id] != version - 1
            or issuance_times[issuance_id] < issuance_times[prior_id]
        ):
            raise ValueError("issuance version/time chain is invalid")
    correction_ids: set[str] = set()
    correction_new_ids: set[str] = set()
    for correction in corrections:
        correction_id = correction["correction_id"]
        if not correction_id or correction_id in correction_ids:
            raise ValueError("coordinator correction IDs are empty or duplicated")
        correction_ids.add(correction_id)
        if correction["new_issuance_id"] in correction_new_ids:
            raise ValueError("multiple corrections create the same issuance")
        correction_new_ids.add(correction["new_issuance_id"])
        if (
            correction["old_issuance_id"] not in issuance_ids
            or correction["new_issuance_id"] not in issuance_ids
        ):
            raise ValueError("coordinator correction references unknown issuance")
        old = issuance_by_id[correction["old_issuance_id"]]
        new = issuance_by_id[correction["new_issuance_id"]]
        correction_time = parse_utc(correction["issued_utc"])
        expected_archive_relative = invalidated_archive_relative_path(
            correction["packet_id"], int(old["extraction_version"])
        )
        expected_correction_id = "corr_" + hashlib.sha256(
            (
                f"{correction['packet_id']}|{old['issuance_id']}|"
                f"{new['issuance_id']}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        if (
            correction_id != expected_correction_id
            or correction["packet_id"] != old["packet_id"]
            or correction["packet_id"] != new["packet_id"]
            or correction["participant_id"] != old["participant_id"]
            or correction["participant_id"] != new["participant_id"]
            or correction["participant_role"] != old["participant_role"]
            or correction["participant_role"] != new["participant_role"]
            or correction["assigned_arm"] != old["assigned_arm"]
            or correction["assigned_arm"] != new["assigned_arm"]
            or correction["old_issuance_record_sha256"]
            != old["record_sha256"]
            or correction["new_issuance_record_sha256"]
            != new["record_sha256"]
            or correction["old_extraction_version"]
            != str(old["extraction_version"])
            or correction["new_extraction_version"]
            != str(new["extraction_version"])
            or int(new["extraction_version"])
            != int(old["extraction_version"]) + 1
            or correction["old_extraction_rows_root_sha256"]
            != old["extraction_rows_root_sha256"]
            or correction["new_extraction_rows_root_sha256"]
            != new["extraction_rows_root_sha256"]
            or new["prior_issuance_id"] != old["issuance_id"]
            or not correction["correction_reason"].strip()
            or correction["issued_utc"] != new["issued_utc"]
            or correction_time != issuance_times[new["issuance_id"]]
            or issuance_times[new["issuance_id"]]
            < issuance_times[old["issuance_id"]]
            or correction[
                "invalidated_composition_archive_relative_path"
            ]
            != expected_archive_relative
            or correction["invalidated_composition_returned"] != "true"
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                correction["invalidated_composition_sha256"],
            )
        ):
            raise ValueError("coordinator correction linkage is invalid")
        if verify_archive_files:
            archive_path = resolve_invalidated_archive(
                corrections_path.parent,
                correction[
                    "invalidated_composition_archive_relative_path"
                ],
            )
            if (
                not archive_path.is_file()
                or sha256_file(archive_path)
                != correction["invalidated_composition_sha256"]
            ):
                raise ValueError(
                    "invalidated composition archive is missing or changed"
                )
    expected_status = (
        "NO_COMPOSITION_PACKETS_ISSUED"
        if not issuances
        else "COORDINATOR_COMPOSITION_PACKETS_ISSUED"
    )
    if registry["status"] != expected_status:
        raise ValueError("composition issuance registry status is invalid")
    return registry, rows, corrections


def active_issuances(
    registry: Mapping[str, Any],
    corrections: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, Any]]:
    invalidated = {row["old_issuance_id"] for row in corrections}
    active: dict[str, Mapping[str, Any]] = {}
    for issuance in registry["issuances"]:
        if issuance["issuance_id"] in invalidated:
            continue
        packet = issuance["packet_id"]
        if packet in active:
            raise ValueError(f"packet {packet} has multiple active issuances")
        active[packet] = issuance
    return active


def issuance_id(
    packet: str,
    version: int,
    returned_sha256: str,
    issued_utc: str,
) -> str:
    return "iss_" + hashlib.sha256(
        (
            f"{WORKFLOW_VERSION}|{packet}|{version}|"
            f"{returned_sha256}|{issued_utc}"
        ).encode("utf-8")
    ).hexdigest()[:24]


def prepare_issuance(
    *,
    material: Mapping[str, Any],
    returned_extraction_path: Path,
    issued_utc: str,
    coordinator_registry_file_sha256: str,
    version: int,
    prior_issuance: Mapping[str, Any] | None,
    prior_rows: Sequence[Mapping[str, str]],
    output_root: Path,
) -> tuple[dict[str, Any], list[dict[str, str]], Path]:
    parse_utc(issued_utc)
    spec = material["spec"]
    returned_header, returned_rows = read_csv(returned_extraction_path)
    validate_stage1_submission(
        returned_header,
        returned_rows,
        material["rows"],
        spec,
        issued_utc,
    )
    returned_hash = sha256_file(returned_extraction_path)
    identifier = issuance_id(
        material["packet_id"], version, returned_hash, issued_utc
    )
    response_id_field = spec["response_id_field"]
    previous_by_id = {
        row["extraction_response_id"]: row["extraction_snapshot_sha256"]
        for row in prior_rows
    }
    if version == 1 and previous_by_id:
        raise ValueError("first issuance unexpectedly has prior rows")
    if version > 1 and len(previous_by_id) != len(returned_rows):
        raise ValueError("correction prior rows do not cover the packet")
    extraction_hash_fields = stage1_header(spec)
    locked_rows: list[dict[str, str]] = []
    anchor_rows: list[dict[str, str]] = []
    for row in returned_rows:
        response_id = row[response_id_field]
        prior = previous_by_id.get(response_id, "")
        if version > 1 and not prior:
            raise ValueError("correction response ID has no prior coordinator lock")
        locked = {field: (row.get(field) or "") for field in stage1_header(spec)}
        locked["extraction_version"] = str(version)
        locked["prior_extraction_snapshot_sha256"] = prior
        locked["extraction_snapshot_sha256"] = extraction_snapshot_sha256(
            locked,
            coordinator_registry_sha256=coordinator_registry_file_sha256,
            issuance_id=identifier,
            packet=material["packet_id"],
            participant_id=material["participant_id"],
            participant_role=material["participant_role"],
            assigned_arm=material["assigned_arm"],
            response_id_field=response_id_field,
            extraction_hash_fields=extraction_hash_fields,
            extraction_version=version,
            prior_extraction_snapshot_sha256=prior,
        )
        locked_rows.append(locked)
        anchor: dict[str, str] = {
            "issuance_id": identifier,
            "packet_id": material["packet_id"],
            "participant_id": material["participant_id"],
            "participant_role": material["participant_role"],
            "assigned_arm": material["assigned_arm"],
            "extraction_response_id": response_id,
            "extraction_version": str(version),
            "prior_extraction_snapshot_sha256": prior,
            "extraction_snapshot_sha256": locked[
                "extraction_snapshot_sha256"
            ],
            "locked_row_sha256": locked_row_sha256(
                locked, locked_header(spec)
            ),
            "display_order": locked["display_order"],
            "record_sha256": "",
        }
        anchor["record_sha256"] = issuance_row_record_sha256(anchor)
        anchor_rows.append(anchor)
    rows_root = issuance_rows_root_sha256(anchor_rows)
    locked_payload = csv_bytes(locked_header(spec), locked_rows)
    blank_composition = [
        {
            **locked,
            **{field: "" for field in COMPOSITION_FIELDS},
        }
        for locked in locked_rows
    ]
    composition_payload = csv_bytes(
        composition_header(spec), blank_composition
    )
    instruction_payload = STAGE2_INSTRUCTIONS.encode("utf-8")
    relative_directory = (
        f"{material['relative_directory']}/v{version:03d}"
    )
    stage2_config = {
        "schema_version": STAGE2_CONFIG_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "issuance_id": identifier,
        "packet_id": material["packet_id"],
        "participant_id": material["participant_id"],
        "participant_role": material["participant_role"],
        "assigned_arm": material["assigned_arm"],
        "extraction_version": version,
        "response_id_field": response_id_field,
        "expected_rows": len(locked_rows),
        "coordinator_packet_registry_sha256": (
            coordinator_registry_file_sha256
        ),
        "locked_extraction_sha256": sha256_bytes(locked_payload),
        "extraction_rows_root_sha256": rows_root,
        "locked_fields": list(locked_header(spec)),
        "submission_fields": list(COMPOSITION_FIELDS),
    }
    config_payload = json_bytes(stage2_config)
    record: dict[str, Any] = {
        "schema_version": ISSUANCE_RECORD_SCHEMA_VERSION,
        "issuance_id": identifier,
        "packet_id": material["packet_id"],
        "participant_id": material["participant_id"],
        "participant_role": material["participant_role"],
        "assigned_arm": material["assigned_arm"],
        "extraction_version": version,
        "prior_issuance_id": (
            prior_issuance["issuance_id"] if prior_issuance else ""
        ),
        "issued_utc": issued_utc,
        "returned_extraction_sha256": returned_hash,
        "locked_extraction_sha256": sha256_bytes(locked_payload),
        "composition_template_sha256": sha256_bytes(composition_payload),
        "instructions_stage2_sha256": sha256_bytes(instruction_payload),
        "stage2_config_sha256": sha256_bytes(config_payload),
        "extraction_rows_root_sha256": rows_root,
        "row_count": len(locked_rows),
        "relative_directory": relative_directory,
        "record_sha256": "",
    }
    record["record_sha256"] = issuance_record_sha256(record)
    directory = output_root / relative_directory
    if directory.exists():
        raise ValueError(f"stage-2 issuance directory already exists: {directory}")
    directory.mkdir(parents=True)
    (directory / "locked_extraction.csv").write_bytes(locked_payload)
    (directory / "composition.csv").write_bytes(composition_payload)
    (directory / "instructions_stage2.md").write_bytes(instruction_payload)
    (directory / "stage2_config.json").write_bytes(config_payload)
    if sorted(path.name for path in directory.iterdir()) != [
        "composition.csv",
        "instructions_stage2.md",
        "locked_extraction.csv",
        "stage2_config.json",
    ]:
        raise AssertionError("stage-2 directory has an unauthorized file")
    return record, anchor_rows, directory


def save_issuance_state(
    *,
    registry: dict[str, Any],
    issuance_rows: Sequence[Mapping[str, str]],
    corrections: Sequence[Mapping[str, str]],
    issuance_registry_path: Path,
    issuance_rows_path: Path,
    corrections_path: Path,
) -> None:
    write_csv(issuance_rows_path, ISSUANCE_ROW_HEADER, issuance_rows)
    write_csv(corrections_path, CORRECTION_HEADER, corrections)
    registry["status"] = (
        "COORDINATOR_COMPOSITION_PACKETS_ISSUED"
        if registry["issuances"]
        else "NO_COMPOSITION_PACKETS_ISSUED"
    )
    registry["issuance_count"] = len(registry["issuances"])
    registry["issuance_rows_sha256"] = sha256_file(issuance_rows_path)
    registry["correction_ledger_sha256"] = sha256_file(corrections_path)
    registry["invalidated_composition_archive_schema_version"] = (
        INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION
    )
    registry["invalidated_composition_archives"] = (
        invalidated_archive_index(corrections)
    )
    registry["registry_sha256"] = issuance_registry_sha256(registry)
    write_json(issuance_registry_path, registry)


def issue_initial(
    *,
    returned_root: Path,
    output_root: Path,
    packet_registry_path: Path,
    issuance_registry_path: Path,
    issuance_rows_path: Path,
    corrections_path: Path,
    frozen_path: Path,
    assignments_path: Path,
    public_roster_path: Path,
    issued_utc: str,
    calibration_summary_path: Path = PACKAGE / "calibration_summary.json",
    calibration_responses_path: Path = PACKAGE / "calibration_responses.csv",
    manifest_path: Path = PACKAGE / "MANIFEST.sha256",
) -> dict[str, Any]:
    assert_calibration_release(
        public_roster_path,
        calibration_summary_path,
        calibration_responses_path,
    )
    verify_packet_registry_manifest_anchor(packet_registry_path, manifest_path)
    packet_registry, materials = validate_registry_against_package(
        packet_registry_path,
        frozen_path=frozen_path,
        assignments_path=assignments_path,
        public_roster_path=public_roster_path,
    )
    del packet_registry
    registry, existing_rows, corrections = validate_issuance_state(
        packet_registry_path,
        issuance_registry_path,
        issuance_rows_path,
        corrections_path,
    )
    if registry["issuances"] or existing_rows or corrections:
        raise ValueError("initial issuance requires empty coordinator state")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("initial stage-2 output must be absent or empty")
    output_root.mkdir(parents=True, exist_ok=True)
    packet_registry_file_hash = sha256_file(packet_registry_path)
    new_rows: list[dict[str, str]] = []
    for material in materials:
        returned = (
            returned_root / material["relative_directory"] / "extraction.csv"
        )
        record, anchors, _directory = prepare_issuance(
            material=material,
            returned_extraction_path=returned,
            issued_utc=issued_utc,
            coordinator_registry_file_sha256=packet_registry_file_hash,
            version=1,
            prior_issuance=None,
            prior_rows=[],
            output_root=output_root,
        )
        registry["issuances"].append(record)
        new_rows.extend(anchors)
    save_issuance_state(
        registry=registry,
        issuance_rows=new_rows,
        corrections=[],
        issuance_registry_path=issuance_registry_path,
        issuance_rows_path=issuance_rows_path,
        corrections_path=corrections_path,
    )
    return {
        "status": "COORDINATOR_COMPOSITION_PACKETS_ISSUED",
        "workflow_version": WORKFLOW_VERSION,
        "issued_packets": len(materials),
        "issued_rows": len(new_rows),
        "labels_first_visible": True,
        "issuance_registry_sha256": sha256_file(issuance_registry_path),
    }


def validate_invalidated_composition(
    path: Path,
    *,
    material: Mapping[str, Any],
    old_issuance: Mapping[str, Any],
    old_rows: Sequence[Mapping[str, str]],
    invalidated_utc: str,
) -> None:
    spec = material["spec"]
    header, rows = read_csv(path)
    if header != composition_header(spec) or len(rows) != len(old_rows):
        raise ValueError("invalidated composition schema/count changed")
    old_by_id = {
        row["extraction_response_id"]: row for row in old_rows
    }
    locked_rows: list[dict[str, str]] = []
    old_issued_time = parse_utc(str(old_issuance["issued_utc"]))
    invalidated_time = parse_utc(invalidated_utc)
    if invalidated_time < old_issued_time:
        raise ValueError("correction issuance predates invalidated issuance")
    for index, row in enumerate(rows, start=1):
        response_id = row[spec["response_id_field"]]
        anchor = old_by_id.get(response_id)
        if anchor is None:
            raise ValueError("invalidated composition has an unknown response ID")
        locked = {
            field: (row.get(field) or "") for field in locked_header(spec)
        }
        if locked_row_sha256(locked, locked_header(spec)) != anchor[
            "locked_row_sha256"
        ]:
            raise ValueError(
                f"invalidated composition row {index} changed a locked field"
            )
        started_text = (row.get("composition_started_utc") or "").strip()
        completed_text = (row.get("completed_utc") or "").strip()
        if started_text:
            started = parse_utc(started_text)
            if started < old_issued_time or started > invalidated_time:
                raise ValueError(
                    f"invalidated composition row {index} has an "
                    "out-of-order start time"
                )
        elif completed_text:
            raise ValueError(
                f"invalidated composition row {index} completes without start"
            )
        if completed_text:
            completed = parse_utc(completed_text)
            if completed < started or completed > invalidated_time:
                raise ValueError(
                    f"invalidated composition row {index} has an "
                    "out-of-order completion time"
                )
        locked_rows.append(locked)
    if sha256_bytes(csv_bytes(locked_header(spec), locked_rows)) != old_issuance[
        "locked_extraction_sha256"
    ]:
        raise ValueError("invalidated composition changed locked row order")


def issue_correction(
    *,
    participant_id: str,
    returned_extraction_path: Path,
    invalidated_composition_path: Path,
    correction_reason: str,
    output_root: Path,
    packet_registry_path: Path,
    issuance_registry_path: Path,
    issuance_rows_path: Path,
    corrections_path: Path,
    frozen_path: Path,
    assignments_path: Path,
    public_roster_path: Path,
    issued_utc: str,
    calibration_summary_path: Path = PACKAGE / "calibration_summary.json",
    calibration_responses_path: Path = PACKAGE / "calibration_responses.csv",
    manifest_path: Path = PACKAGE / "MANIFEST.sha256",
) -> dict[str, Any]:
    if not correction_reason.strip():
        raise ValueError("correction reason must be nonempty")
    assert_calibration_release(
        public_roster_path,
        calibration_summary_path,
        calibration_responses_path,
    )
    verify_packet_registry_manifest_anchor(packet_registry_path, manifest_path)
    _packet_registry, materials = validate_registry_against_package(
        packet_registry_path,
        frozen_path=frozen_path,
        assignments_path=assignments_path,
        public_roster_path=public_roster_path,
    )
    materials_by_participant = {
        material["participant_id"]: material for material in materials
    }
    material = materials_by_participant.get(participant_id)
    if material is None:
        raise ValueError("correction participant is not in packet registry")
    registry, issuance_rows, corrections = validate_issuance_state(
        packet_registry_path,
        issuance_registry_path,
        issuance_rows_path,
        corrections_path,
    )
    active = active_issuances(registry, corrections)
    old = active.get(material["packet_id"])
    if old is None:
        raise ValueError("participant has no active coordinator issuance")
    new_issued_time = parse_utc(issued_utc)
    if new_issued_time < parse_utc(str(old["issued_utc"])):
        raise ValueError("correction issuance time predates prior issuance")
    old_rows = [
        row
        for row in issuance_rows
        if row["issuance_id"] == old["issuance_id"]
    ]
    validate_invalidated_composition(
        invalidated_composition_path,
        material=material,
        old_issuance=old,
        old_rows=old_rows,
        invalidated_utc=issued_utc,
    )
    version = int(old["extraction_version"]) + 1
    record, anchors, _directory = prepare_issuance(
        material=material,
        returned_extraction_path=returned_extraction_path,
        issued_utc=issued_utc,
        coordinator_registry_file_sha256=sha256_file(packet_registry_path),
        version=version,
        prior_issuance=old,
        prior_rows=old_rows,
        output_root=output_root,
    )
    archive_relative = invalidated_archive_relative_path(
        material["packet_id"], version - 1
    )
    archive_path = resolve_invalidated_archive(
        corrections_path.parent, archive_relative
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        raise ValueError("invalidated composition archive already exists")
    shutil.copy2(invalidated_composition_path, archive_path)
    correction: dict[str, str] = {
        "correction_id": "corr_"
        + hashlib.sha256(
            (
                f"{material['packet_id']}|{old['issuance_id']}|"
                f"{record['issuance_id']}"
            ).encode("utf-8")
        ).hexdigest()[:24],
        "packet_id": material["packet_id"],
        "participant_id": material["participant_id"],
        "participant_role": material["participant_role"],
        "assigned_arm": material["assigned_arm"],
        "old_issuance_id": old["issuance_id"],
        "old_issuance_record_sha256": old["record_sha256"],
        "old_extraction_version": str(old["extraction_version"]),
        "old_extraction_rows_root_sha256": old[
            "extraction_rows_root_sha256"
        ],
        "new_issuance_id": record["issuance_id"],
        "new_issuance_record_sha256": record["record_sha256"],
        "new_extraction_version": str(record["extraction_version"]),
        "new_extraction_rows_root_sha256": record[
            "extraction_rows_root_sha256"
        ],
        "correction_reason": correction_reason.strip(),
        "issued_utc": issued_utc,
        "invalidated_composition_archive_relative_path": archive_relative,
        "invalidated_composition_sha256": sha256_file(archive_path),
        "invalidated_composition_returned": "true",
        "record_sha256": "",
    }
    correction["record_sha256"] = correction_record_sha256(correction)
    registry["issuances"].append(record)
    issuance_rows.extend(anchors)
    corrections.append(correction)
    save_issuance_state(
        registry=registry,
        issuance_rows=issuance_rows,
        corrections=corrections,
        issuance_registry_path=issuance_registry_path,
        issuance_rows_path=issuance_rows_path,
        corrections_path=corrections_path,
    )
    validate_issuance_state(
        packet_registry_path,
        issuance_registry_path,
        issuance_rows_path,
        corrections_path,
    )
    return {
        "status": "COORDINATOR_CORRECTION_REISSUED",
        "participant_id": participant_id,
        "old_issuance_id": old["issuance_id"],
        "new_issuance_id": record["issuance_id"],
        "new_extraction_version": version,
        "old_issuance_invalidated": True,
        "invalidated_composition_archive_relative_path": archive_relative,
        "invalidated_composition_sha256": sha256_file(archive_path),
        "issuance_registry_sha256": sha256_file(issuance_registry_path),
    }


def fill_extractions(root: Path, materials: Sequence[Mapping[str, Any]]) -> None:
    for material in materials:
        path = root / material["relative_directory"] / "extraction.csv"
        header, rows = read_csv(path)
        spec = material["spec"]
        for row in rows:
            row[spec["extraction_start_field"]] = "2026-07-18T09:00:00Z"
            for field in spec["extraction_fields"]:
                row[field] = (
                    "yes"
                    if field == spec["source_location_field"]
                    else f"extracted {field}"
                )
        write_csv(path, header, rows)


def self_test() -> None:
    workspace = PACKAGE / ".composition_issuer_selftest_workspace"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir()
    try:
        from build_staged_review_packets import expected_registry

        registry, materials = expected_registry(
            frozen_path=PACKAGE / "frozen_test_claims.csv",
            assignments_path=PACKAGE / "auditor_assignments.csv",
            public_roster_path=PACKAGE / "participant_metadata_public_template.csv",
        )
        registry_path = workspace / "coordinator_packet_registry.json"
        write_json(registry_path, registry)
        returned = workspace / "returned"
        write_stage1_packets(returned, materials)
        fill_extractions(returned, materials)
        state = workspace / "state"
        state.mkdir()
        for name in FORMAL_RESPONSE_FILES:
            shutil.copy2(PACKAGE / name, state / name)
        initialize_empty_coordinator_state(state, registry_path)
        first = materials[0]
        first_path = (
            returned / first["relative_directory"] / "extraction.csv"
        )
        header, rows = read_csv(first_path)
        original = rows[0]["claim_text"]
        rows[0]["claim_text"] = "tampered raw claim"
        write_csv(first_path, header, rows)
        try:
            issue_initial(
                returned_root=returned,
                output_root=workspace / "rejected",
                packet_registry_path=registry_path,
                issuance_registry_path=state
                / "composition_packet_issuance_registry.json",
                issuance_rows_path=state / "composition_issuance_rows.csv",
                corrections_path=state / "review_extraction_corrections.csv",
                frozen_path=PACKAGE / "frozen_test_claims.csv",
                assignments_path=PACKAGE / "auditor_assignments.csv",
                public_roster_path=PACKAGE
                / "participant_metadata_public_template.csv",
                issued_utc="2026-07-18T09:10:00Z",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("issuer accepted a changed raw field")
        shutil.rmtree(workspace / "rejected", ignore_errors=True)
        rows[0]["claim_text"] = original
        write_csv(first_path, header, rows)
        issued = workspace / "issued"
        summary = issue_initial(
            returned_root=returned,
            output_root=issued,
            packet_registry_path=registry_path,
            issuance_registry_path=state
            / "composition_packet_issuance_registry.json",
            issuance_rows_path=state / "composition_issuance_rows.csv",
            corrections_path=state / "review_extraction_corrections.csv",
            frozen_path=PACKAGE / "frozen_test_claims.csv",
            assignments_path=PACKAGE / "auditor_assignments.csv",
            public_roster_path=PACKAGE
            / "participant_metadata_public_template.csv",
            issued_utc="2026-07-18T09:10:00Z",
        )
        if summary["issued_packets"] != 27 or summary["issued_rows"] != 7200:
            raise AssertionError("initial coordinator issuance size is wrong")
        stage2 = issued / first["relative_directory"] / "v001"
        if "supported_as_written" not in (
            stage2 / "instructions_stage2.md"
        ).read_text(encoding="utf-8"):
            raise AssertionError("stage-2 label instructions were not issued")
        extraction_header, extraction_rows = read_csv(first_path)
        extraction_rows[0][first["spec"]["extraction_fields"][0]] += " corrected"
        extraction_rows[0][
            first["spec"]["extraction_completed_field"]
        ] = ""
        write_csv(first_path, extraction_header, extraction_rows)
        try:
            issue_correction(
                participant_id=first["participant_id"],
                returned_extraction_path=first_path,
                invalidated_composition_path=stage2 / "composition.csv",
                correction_reason="synthetic nonmonotonic rejection",
                output_root=issued,
                packet_registry_path=registry_path,
                issuance_registry_path=state
                / "composition_packet_issuance_registry.json",
                issuance_rows_path=state / "composition_issuance_rows.csv",
                corrections_path=state / "review_extraction_corrections.csv",
                frozen_path=PACKAGE / "frozen_test_claims.csv",
                assignments_path=PACKAGE / "auditor_assignments.csv",
                public_roster_path=PACKAGE
                / "participant_metadata_public_template.csv",
                issued_utc="2026-07-18T09:05:00Z",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("issuer accepted v2 earlier than v1")
        correction_summary = issue_correction(
            participant_id=first["participant_id"],
            returned_extraction_path=first_path,
            invalidated_composition_path=stage2 / "composition.csv",
            correction_reason="corrected extraction transcription",
            output_root=issued,
            packet_registry_path=registry_path,
            issuance_registry_path=state
            / "composition_packet_issuance_registry.json",
            issuance_rows_path=state / "composition_issuance_rows.csv",
            corrections_path=state / "review_extraction_corrections.csv",
            frozen_path=PACKAGE / "frozen_test_claims.csv",
            assignments_path=PACKAGE / "auditor_assignments.csv",
            public_roster_path=PACKAGE
            / "participant_metadata_public_template.csv",
            issued_utc="2026-07-18T09:20:00Z",
        )
        if (
            not correction_summary["old_issuance_invalidated"]
            or not (
                issued / first["relative_directory"] / "v001"
            ).is_dir()
            or not (
                issued / first["relative_directory"] / "v002"
            ).is_dir()
        ):
            raise AssertionError("coordinator correction did not preserve versions")

        issuance_registry_path = (
            state / "composition_packet_issuance_registry.json"
        )
        corrections_path = state / "review_extraction_corrections.csv"
        issuance_rows_path = state / "composition_issuance_rows.csv"

        def require_state_failure(message: str) -> None:
            try:
                validate_issuance_state(
                    registry_path,
                    issuance_registry_path,
                    issuance_rows_path,
                    corrections_path,
                )
            except ValueError:
                return
            raise AssertionError(message)

        archive_path = resolve_invalidated_archive(
            state,
            correction_summary[
                "invalidated_composition_archive_relative_path"
            ],
        )
        archive_payload = archive_path.read_bytes()
        archive_path.unlink()
        require_state_failure("issuance validator accepted a deleted archive")
        archive_path.write_bytes(archive_payload)
        archive_path.write_bytes(archive_payload + b"\n")
        require_state_failure("issuance validator accepted a changed archive")
        archive_path.write_bytes(archive_payload)

        registry_payload = issuance_registry_path.read_bytes()
        correction_payload = corrections_path.read_bytes()
        correction_header, correction_rows = read_csv(corrections_path)
        tampered_registry = load_json(issuance_registry_path)
        new_record = next(
            record
            for record in tampered_registry["issuances"]
            if record["issuance_id"]
            == correction_rows[0]["new_issuance_id"]
        )
        new_record["issued_utc"] = "2026-07-18T09:05:00Z"
        new_record["record_sha256"] = issuance_record_sha256(new_record)
        correction_rows[0]["issued_utc"] = new_record["issued_utc"]
        correction_rows[0]["new_issuance_record_sha256"] = new_record[
            "record_sha256"
        ]
        correction_rows[0]["record_sha256"] = correction_record_sha256(
            correction_rows[0]
        )
        write_csv(corrections_path, correction_header, correction_rows)
        tampered_registry["correction_ledger_sha256"] = sha256_file(
            corrections_path
        )
        tampered_registry["registry_sha256"] = issuance_registry_sha256(
            tampered_registry
        )
        write_json(issuance_registry_path, tampered_registry)
        require_state_failure(
            "issuance validator accepted a nonmonotonic version chain"
        )
        issuance_registry_path.write_bytes(registry_payload)
        corrections_path.write_bytes(correction_payload)

        correction_header, correction_rows = read_csv(corrections_path)
        correction_rows[0]["issued_utc"] = "2026-07-18T09:21:00Z"
        correction_rows[0]["record_sha256"] = correction_record_sha256(
            correction_rows[0]
        )
        write_csv(corrections_path, correction_header, correction_rows)
        tampered_registry = load_json(issuance_registry_path)
        tampered_registry["correction_ledger_sha256"] = sha256_file(
            corrections_path
        )
        tampered_registry["registry_sha256"] = issuance_registry_sha256(
            tampered_registry
        )
        write_json(issuance_registry_path, tampered_registry)
        require_state_failure(
            "issuance validator accepted correction/new issuance time mismatch"
        )
        issuance_registry_path.write_bytes(registry_payload)
        corrections_path.write_bytes(correction_payload)
        validate_issuance_state(
            registry_path,
            issuance_registry_path,
            issuance_rows_path,
            corrections_path,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print("self-test passed; coordinator issuance/correction fixture removed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    common: dict[str, Any] = {}
    del common
    initial = subparsers.add_parser("issue-initial")
    initial.add_argument("--returned-extractions", type=Path, required=True)
    correction = subparsers.add_parser("issue-correction")
    correction.add_argument("--participant-id", required=True)
    correction.add_argument("--returned-extraction", type=Path, required=True)
    correction.add_argument("--invalidated-composition", type=Path, required=True)
    correction.add_argument("--reason", required=True)
    for subparser in (initial, correction):
        subparser.add_argument("--recorded-utc", required=True)
        subparser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        subparser.add_argument(
            "--packet-registry", type=Path, default=DEFAULT_REGISTRY
        )
        subparser.add_argument(
            "--issuance-registry",
            type=Path,
            default=DEFAULT_ISSUANCE_REGISTRY,
        )
        subparser.add_argument(
            "--issuance-rows", type=Path, default=DEFAULT_ISSUANCE_ROWS
        )
        subparser.add_argument(
            "--corrections", type=Path, default=DEFAULT_CORRECTIONS
        )
        subparser.add_argument(
            "--frozen-claims",
            type=Path,
            default=PACKAGE / "frozen_test_claims.csv",
        )
        subparser.add_argument(
            "--assignments",
            type=Path,
            default=PACKAGE / "auditor_assignments.csv",
        )
        subparser.add_argument(
            "--public-roster",
            type=Path,
            default=PACKAGE / "participant_metadata_public_template.csv",
        )
        subparser.add_argument(
            "--calibration-summary",
            type=Path,
            default=PACKAGE / "calibration_summary.json",
        )
        subparser.add_argument(
            "--calibration-responses",
            type=Path,
            default=PACKAGE / "calibration_responses.csv",
        )
        subparser.add_argument(
            "--manifest",
            type=Path,
            default=PACKAGE / "MANIFEST.sha256",
        )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.command == "issue-initial":
        result = issue_initial(
            returned_root=args.returned_extractions,
            output_root=args.output,
            packet_registry_path=args.packet_registry,
            issuance_registry_path=args.issuance_registry,
            issuance_rows_path=args.issuance_rows,
            corrections_path=args.corrections,
            frozen_path=args.frozen_claims,
            assignments_path=args.assignments,
            public_roster_path=args.public_roster,
            issued_utc=args.recorded_utc,
            calibration_summary_path=args.calibration_summary,
            calibration_responses_path=args.calibration_responses,
            manifest_path=args.manifest,
        )
    elif args.command == "issue-correction":
        result = issue_correction(
            participant_id=args.participant_id,
            returned_extraction_path=args.returned_extraction,
            invalidated_composition_path=args.invalidated_composition,
            correction_reason=args.reason,
            output_root=args.output,
            packet_registry_path=args.packet_registry,
            issuance_registry_path=args.issuance_registry,
            issuance_rows_path=args.issuance_rows,
            corrections_path=args.corrections,
            frozen_path=args.frozen_claims,
            assignments_path=args.assignments,
            public_roster_path=args.public_roster,
            issued_utc=args.recorded_utc,
            calibration_summary_path=args.calibration_summary,
            calibration_responses_path=args.calibration_responses,
            manifest_path=args.manifest,
        )
    else:
        raise ValueError("choose issue-initial or issue-correction")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
