#!/usr/bin/env python3
"""Coordinator-only collection and receipt of staged review responses."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_staged_review_packets import (
    FORMAL_RESPONSE_FILES,
    expected_registry,
    initialize_empty_coordinator_state,
    validate_registry_against_package,
    write_stage1_packets,
)
from issue_composition_packets import (
    active_issuances,
    fill_extractions,
    issue_correction,
    issue_initial,
    load_json,
    resolve_invalidated_archive,
    validate_invalidated_composition,
    validate_issuance_state,
    verify_packet_registry_manifest_anchor,
)
from staged_review_core import (
    COLLECTION_RECEIPT_SCHEMA_VERSION,
    COMPOSITION_FIELDS,
    CORRECTION_HEADER,
    INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY,
    INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION,
    ISSUANCE_REGISTRY_SCHEMA_VERSION,
    ISSUANCE_ROW_HEADER,
    RECEIPT_HEADER,
    STAGE2_CONFIG_SCHEMA_VERSION,
    WORKFLOW_VERSION,
    collection_receipt_sha256,
    composition_header,
    csv_bytes,
    extraction_snapshot_sha256,
    final_header,
    final_row_sha256,
    issuance_rows_root_sha256,
    issuance_registry_sha256,
    json_bytes,
    locked_header,
    locked_row_sha256,
    packet_spec,
    parse_utc,
    read_csv,
    receipt_record_sha256,
    sha256_bytes,
    sha256_file,
    stage1_header,
    validate_composition_row,
    write_csv,
    write_json,
)


PACKAGE = Path(__file__).resolve().parent
DEFAULT_PACKET_REGISTRY = PACKAGE / "coordinator_packet_registry.json"
DEFAULT_ISSUANCE_REGISTRY = (
    PACKAGE / "composition_packet_issuance_registry.json"
)
DEFAULT_ISSUANCE_ROWS = PACKAGE / "composition_issuance_rows.csv"
DEFAULT_CORRECTIONS = PACKAGE / "review_extraction_corrections.csv"
DEFAULT_OUTPUT = PACKAGE / "collected_coordinator_responses_v2"


def canonical_response_file(role: str, arm: str) -> str:
    return f"arm_{arm}_responses.csv" if role == "auditor" else "gold_responses.csv"


def material_maps(
    materials: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    by_packet = {material["packet_id"]: material for material in materials}
    by_participant = {
        material["participant_id"]: material for material in materials
    }
    if len(by_packet) != len(materials) or len(by_participant) != len(materials):
        raise ValueError("packet materials reuse packet or participant IDs")
    return by_packet, by_participant


def validate_issuance_chains(
    registry: Mapping[str, Any],
    issuance_rows: Sequence[Mapping[str, str]],
    corrections: Sequence[Mapping[str, str]],
    materials: Sequence[Mapping[str, Any]],
    coordinator_root: Path,
    *,
    verify_archive_files: bool = True,
) -> dict[str, Mapping[str, Any]]:
    by_packet, _by_participant = material_maps(materials)
    rows_by_issuance: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in issuance_rows:
        rows_by_issuance[row["issuance_id"]].append(row)
    issuances_by_packet: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    issuance_by_id: dict[str, Mapping[str, Any]] = {}
    for issuance in registry["issuances"]:
        packet = issuance["packet_id"]
        material = by_packet.get(packet)
        if material is None:
            raise ValueError("issuance references an unknown packet")
        for field in ("participant_id", "participant_role", "assigned_arm"):
            if issuance[field] != material[field]:
                raise ValueError(f"issuance changed packet field {field}")
        issuance_by_id[issuance["issuance_id"]] = issuance
        issuances_by_packet[packet].append(issuance)
        anchors = rows_by_issuance[issuance["issuance_id"]]
        if issuance_rows_root_sha256(anchors) != issuance[
            "extraction_rows_root_sha256"
        ]:
            raise ValueError("issuance row root is invalid")
        expected_ids = [
            row[material["spec"]["response_id_field"]]
            for row in material["rows"]
        ]
        observed_ids = [row["extraction_response_id"] for row in anchors]
        if observed_ids != expected_ids:
            raise ValueError("issuance row IDs/order differ from frozen packet")
        for anchor, expected in zip(anchors, material["rows"]):
            if (
                anchor["packet_id"] != packet
                or anchor["participant_id"] != material["participant_id"]
                or anchor["participant_role"] != material["participant_role"]
                or anchor["assigned_arm"] != material["assigned_arm"]
                or anchor["display_order"] != expected["display_order"]
            ):
                raise ValueError("issuance row anchor changed packet metadata")
    corrections_by_new = {
        row["new_issuance_id"]: row for row in corrections
    }
    if len(corrections_by_new) != len(corrections):
        raise ValueError("multiple corrections create the same issuance")
    invalidated: set[str] = set()
    for packet, packet_issuances in issuances_by_packet.items():
        ordered = sorted(
            packet_issuances, key=lambda value: int(value["extraction_version"])
        )
        versions = [int(value["extraction_version"]) for value in ordered]
        if versions != list(range(1, len(ordered) + 1)):
            raise ValueError(f"packet {packet} issuance versions are discontinuous")
        for index, issuance in enumerate(ordered):
            expected_prior = "" if index == 0 else ordered[index - 1]["issuance_id"]
            if issuance["prior_issuance_id"] != expected_prior:
                raise ValueError(f"packet {packet} prior issuance chain broke")
            anchors = rows_by_issuance[issuance["issuance_id"]]
            if index == 0:
                if any(row["prior_extraction_snapshot_sha256"] for row in anchors):
                    raise ValueError("first issuance row has a prior hash")
                continue
            previous = ordered[index - 1]
            correction = corrections_by_new.get(issuance["issuance_id"])
            if correction is None:
                raise ValueError("corrected issuance lacks coordinator correction")
            if (
                correction["packet_id"] != packet
                or correction["old_issuance_id"] != previous["issuance_id"]
                or correction["old_issuance_record_sha256"]
                != previous["record_sha256"]
                or correction["new_issuance_record_sha256"]
                != issuance["record_sha256"]
                or correction["old_extraction_rows_root_sha256"]
                != previous["extraction_rows_root_sha256"]
                or correction["new_extraction_rows_root_sha256"]
                != issuance["extraction_rows_root_sha256"]
                or correction["old_extraction_version"] != str(index)
                or correction["new_extraction_version"] != str(index + 1)
                or correction["invalidated_composition_returned"] != "true"
                or correction["issued_utc"] != issuance["issued_utc"]
                or parse_utc(str(issuance["issued_utc"]))
                < parse_utc(str(previous["issued_utc"]))
            ):
                raise ValueError("coordinator correction linkage is invalid")
            if verify_archive_files:
                validate_invalidated_composition(
                    resolve_invalidated_archive(
                        coordinator_root,
                        correction[
                            "invalidated_composition_archive_relative_path"
                        ],
                    ),
                    material=by_packet[packet],
                    old_issuance=previous,
                    old_rows=rows_by_issuance[previous["issuance_id"]],
                    invalidated_utc=correction["issued_utc"],
                )
            previous_rows = {
                row["extraction_response_id"]: row
                for row in rows_by_issuance[previous["issuance_id"]]
            }
            for anchor in anchors:
                prior = previous_rows[anchor["extraction_response_id"]][
                    "extraction_snapshot_sha256"
                ]
                if anchor["prior_extraction_snapshot_sha256"] != prior:
                    raise ValueError("corrected extraction row prior hash broke")
            invalidated.add(previous["issuance_id"])
    if len(corrections) != len(invalidated):
        raise ValueError("correction ledger contains an extraneous transition")
    active = active_issuances(registry, corrections)
    if set(active) != set(issuances_by_packet):
        raise ValueError("issuance registry lacks one active issuance per packet")
    return active


def locked_rows_from_submission(
    *,
    composition_rows: Sequence[Mapping[str, str]],
    material: Mapping[str, Any],
    issuance: Mapping[str, Any],
    anchors: Sequence[Mapping[str, str]],
    packet_registry_file_sha256: str,
    validate_outputs: bool,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    spec = material["spec"]
    if len(composition_rows) != len(material["rows"]) or len(anchors) != len(
        material["rows"]
    ):
        raise ValueError("composition/anchor row count differs from packet")
    final_rows: list[dict[str, str]] = []
    locked_rows: list[dict[str, str]] = []
    response_id_field = spec["response_id_field"]
    extraction_hash_fields = stage1_header(spec)
    issued_time = parse_utc(str(issuance["issued_utc"]))
    for index, (row, expected, anchor) in enumerate(
        zip(composition_rows, material["rows"], anchors), start=1
    ):
        response_id = (row.get(response_id_field) or "")
        if (
            response_id != expected[response_id_field]
            or response_id != anchor["extraction_response_id"]
        ):
            raise ValueError(f"composition row {index} changed ID/order")
        for field in spec["immutable_fields"]:
            if (row.get(field) or "") != (expected.get(field) or ""):
                raise ValueError(
                    f"composition row {index} changed immutable field {field}"
                )
        locked = {
            field: (row.get(field) or "") for field in locked_header(spec)
        }
        if (
            locked["extraction_version"]
            != str(issuance["extraction_version"])
            or locked["prior_extraction_snapshot_sha256"]
            != anchor["prior_extraction_snapshot_sha256"]
            or locked["extraction_snapshot_sha256"]
            != anchor["extraction_snapshot_sha256"]
            or locked_row_sha256(locked, locked_header(spec))
            != anchor["locked_row_sha256"]
        ):
            raise ValueError(f"composition row {index} changed locked extraction")
        expected_snapshot = extraction_snapshot_sha256(
            locked,
            coordinator_registry_sha256=packet_registry_file_sha256,
            issuance_id=issuance["issuance_id"],
            packet=material["packet_id"],
            participant_id=material["participant_id"],
            participant_role=material["participant_role"],
            assigned_arm=material["assigned_arm"],
            response_id_field=response_id_field,
            extraction_hash_fields=extraction_hash_fields,
            extraction_version=int(issuance["extraction_version"]),
            prior_extraction_snapshot_sha256=locked[
                "prior_extraction_snapshot_sha256"
            ],
        )
        if expected_snapshot != locked["extraction_snapshot_sha256"]:
            raise ValueError(f"composition row {index} has an invalid lock hash")
        extraction_started = parse_utc(
            locked[str(spec["extraction_start_field"])]
        )
        extraction_completed = locked[
            str(spec["extraction_completed_field"])
        ]
        if (
            extraction_started > issued_time
            or extraction_completed != issuance["issued_utc"]
        ):
            raise ValueError(
                f"composition row {index} has an invalid issuance/lock time"
            )
        if validate_outputs:
            validate_composition_row(row, f"composition row {index}")
        output_header = final_header(spec)
        final_rows.append(
            {field: (row.get(field) or "") for field in output_header}
        )
        locked_rows.append(locked)
    if sha256_bytes(csv_bytes(locked_header(spec), locked_rows)) != issuance[
        "locked_extraction_sha256"
    ]:
        raise ValueError("composition changed locked extraction order/file")
    blank_template = [
        {
            **locked,
            **{field: "" for field in COMPOSITION_FIELDS},
        }
        for locked in locked_rows
    ]
    if sha256_bytes(
        csv_bytes(composition_header(spec), blank_template)
    ) != issuance["composition_template_sha256"]:
        raise ValueError("coordinator composition template hash is invalid")
    return locked_rows, final_rows


def collect(
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
    received_utc: str,
    manifest_path: Path = PACKAGE / "MANIFEST.sha256",
) -> dict[str, Any]:
    received_time = parse_utc(received_utc)
    verify_packet_registry_manifest_anchor(packet_registry_path, manifest_path)
    _packet_registry, materials = validate_registry_against_package(
        packet_registry_path,
        frozen_path=frozen_path,
        assignments_path=assignments_path,
        public_roster_path=public_roster_path,
    )
    registry, issuance_rows, corrections = validate_issuance_state(
        packet_registry_path,
        issuance_registry_path,
        issuance_rows_path,
        corrections_path,
    )
    active = validate_issuance_chains(
        registry,
        issuance_rows,
        corrections,
        materials,
        corrections_path.parent,
    )
    if len(active) != len(materials):
        raise ValueError("not every stage-1 packet has an active stage-2 issuance")
    rows_by_issuance: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in issuance_rows:
        rows_by_issuance[row["issuance_id"]].append(row)
    aggregate: dict[str, list[dict[str, str]]] = {
        name: [] for name in FORMAL_RESPONSE_FILES
    }
    participant_outputs: list[
        tuple[Mapping[str, Any], Mapping[str, Any], list[dict[str, str]]]
    ] = []
    receipt_rows: list[dict[str, str]] = []
    registry_file_hash = sha256_file(packet_registry_path)
    for material in materials:
        issuance = active[material["packet_id"]]
        composition_path = (
            returned_root / issuance["relative_directory"] / "composition.csv"
        )
        header, composition_rows = read_csv(composition_path)
        spec = material["spec"]
        if header != composition_header(spec):
            raise ValueError("returned composition has the wrong schema")
        _locked, final_rows = locked_rows_from_submission(
            composition_rows=composition_rows,
            material=material,
            issuance=issuance,
            anchors=rows_by_issuance[issuance["issuance_id"]],
            packet_registry_file_sha256=registry_file_hash,
            validate_outputs=True,
        )
        for row in final_rows:
            issued_time = parse_utc(str(issuance["issued_utc"]))
            started_time = parse_utc(row["composition_started_utc"])
            completed_time = parse_utc(row["completed_utc"])
            if not (
                issued_time
                <= started_time
                <= completed_time
                <= received_time
            ):
                raise ValueError(
                    "issuance/composition/receipt times are out of order"
                )
        name = canonical_response_file(
            material["participant_role"], material["assigned_arm"]
        )
        aggregate[name].extend(final_rows)
        participant_outputs.append((material, issuance, final_rows))
        response_id_field = spec["response_id_field"]
        output_header = final_header(spec)
        for row in final_rows:
            response_id = row[response_id_field]
            final_hash = final_row_sha256(row, output_header, name)
            receipt: dict[str, str] = {
                "receipt_id": "rcpt_"
                + hashlib.sha256(
                    (
                        f"{issuance['issuance_id']}|{response_id}|"
                        f"{received_utc}"
                    ).encode("utf-8")
                ).hexdigest()[:24],
                "issuance_id": issuance["issuance_id"],
                "packet_id": material["packet_id"],
                "participant_id": material["participant_id"],
                "participant_role": material["participant_role"],
                "assigned_arm": material["assigned_arm"],
                "extraction_response_id": response_id,
                "extraction_snapshot_sha256": row[
                    "extraction_snapshot_sha256"
                ],
                "canonical_response_file": name,
                "final_row_sha256": final_hash,
                "received_utc": received_utc,
                "record_sha256": "",
            }
            receipt["record_sha256"] = receipt_record_sha256(receipt)
            receipt_rows.append(receipt)
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("collector output must be absent or empty")
    output_root.mkdir(parents=True, exist_ok=True)
    for name, rows in aggregate.items():
        header, _empty = read_csv(PACKAGE / name)
        write_csv(output_root / name, header, rows)
    for material, issuance, rows in participant_outputs:
        directory = (
            output_root
            / "participant_final"
            / issuance["relative_directory"]
        )
        directory.mkdir(parents=True)
        write_csv(
            directory / "final_response.csv",
            final_header(material["spec"]),
            rows,
        )
    receipts_path = output_root / "coordinator_response_receipts.csv"
    write_csv(receipts_path, RECEIPT_HEADER, receipt_rows)
    collection_receipt: dict[str, Any] = {
        "schema_version": COLLECTION_RECEIPT_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "status": "COORDINATOR_FINAL_RESPONSES_RECEIVED",
        "coordinator_packet_registry_sha256": registry_file_hash,
        "composition_issuance_registry_sha256": sha256_file(
            issuance_registry_path
        ),
        "composition_issuance_registry_record_sha256": registry[
            "registry_sha256"
        ],
        "response_receipts_sha256": sha256_file(receipts_path),
        "formal_response_files": {
            name: {
                "rows": len(rows),
                "sha256": sha256_file(output_root / name),
            }
            for name, rows in aggregate.items()
        },
        "formal_response_rows": len(receipt_rows),
        "received_utc": received_utc,
    }
    collection_receipt["receipt_sha256"] = collection_receipt_sha256(
        collection_receipt
    )
    write_json(
        output_root / "coordinator_collection_receipt.json",
        collection_receipt,
    )
    return {
        "status": collection_receipt["status"],
        "workflow_version": WORKFLOW_VERSION,
        "participant_submissions": len(materials),
        "formal_response_rows": len(receipt_rows),
        "invalidated_composition_archives": len(corrections),
        "coordinator_response_receipts_sha256": sha256_file(receipts_path),
        "coordinator_collection_receipt_sha256": sha256_file(
            output_root / "coordinator_collection_receipt.json"
        ),
    }


def validate_collection_artifacts(root: Path) -> dict[str, Any]:
    packet_registry_path = root / "coordinator_packet_registry.json"
    issuance_registry_path = (
        root / "composition_packet_issuance_registry.json"
    )
    issuance_rows_path = root / "composition_issuance_rows.csv"
    corrections_path = root / "review_extraction_corrections.csv"
    _packet_registry, materials = validate_registry_against_package(
        packet_registry_path,
        frozen_path=root / "frozen_test_claims.csv",
        assignments_path=root / "auditor_assignments.csv",
        public_roster_path=root / "participant_metadata_public_template.csv",
    )
    registry, issuance_rows, corrections = validate_issuance_state(
        packet_registry_path,
        issuance_registry_path,
        issuance_rows_path,
        corrections_path,
    )
    active = validate_issuance_chains(
        registry,
        issuance_rows,
        corrections,
        materials,
        root,
    )
    rows_by_issuance: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in issuance_rows:
        rows_by_issuance[row["issuance_id"]].append(row)
    response_rows_by_file = {
        name: read_csv(root / name)[1] for name in FORMAL_RESPONSE_FILES
    }
    response_by_key: dict[tuple[str, str], Mapping[str, str]] = {}
    material_by_participant = {
        material["participant_id"]: material for material in materials
    }
    for name, rows in response_rows_by_file.items():
        for row in rows:
            participant = row["participant_id"]
            material = material_by_participant.get(participant)
            if material is None:
                raise ValueError("formal response has an unknown participant")
            expected_name = canonical_response_file(
                material["participant_role"], material["assigned_arm"]
            )
            if name != expected_name:
                raise ValueError("formal response is in the wrong canonical file")
            response_id = row[material["spec"]["response_id_field"]]
            key = (participant, response_id)
            if key in response_by_key:
                raise ValueError("formal responses duplicate a participant row")
            response_by_key[key] = row
    registry_file_hash = sha256_file(packet_registry_path)
    expected_keys: set[tuple[str, str]] = set()
    expected_final_hashes: dict[tuple[str, str], tuple[str, str, str]] = {}
    for material in materials:
        issuance = active.get(material["packet_id"])
        if issuance is None:
            raise ValueError("formal participant lacks an active issuance")
        anchors = rows_by_issuance[issuance["issuance_id"]]
        augmented_rows: list[dict[str, str]] = []
        for expected, anchor in zip(material["rows"], anchors):
            response_id = expected[material["spec"]["response_id_field"]]
            key = (material["participant_id"], response_id)
            expected_keys.add(key)
            row = response_by_key.get(key)
            if row is None:
                raise ValueError("collector final responses are incomplete")
            augmented = dict(row)
            augmented["extraction_version"] = anchor["extraction_version"]
            augmented["prior_extraction_snapshot_sha256"] = anchor[
                "prior_extraction_snapshot_sha256"
            ]
            augmented_rows.append(augmented)
            name = canonical_response_file(
                material["participant_role"], material["assigned_arm"]
            )
            expected_final_hashes[key] = (
                final_row_sha256(row, final_header(material["spec"]), name),
                issuance["issuance_id"],
                name,
            )
        _locked, reconstructed = locked_rows_from_submission(
            composition_rows=augmented_rows,
            material=material,
            issuance=issuance,
            anchors=anchors,
            packet_registry_file_sha256=registry_file_hash,
            validate_outputs=True,
        )
        if len(reconstructed) != len(material["rows"]):
            raise ValueError("formal packet reconstruction is incomplete")
    if set(response_by_key) != expected_keys:
        raise ValueError("formal responses include rows outside registry")
    receipt_header, receipts = read_csv(
        root / "coordinator_response_receipts.csv"
    )
    if receipt_header != RECEIPT_HEADER:
        raise ValueError("coordinator response receipt schema changed")
    receipt_by_key: dict[tuple[str, str], Mapping[str, str]] = {}
    for receipt in receipts:
        if receipt["record_sha256"] != receipt_record_sha256(receipt):
            raise ValueError("coordinator response receipt hash is invalid")
        key = (
            receipt["participant_id"],
            receipt["extraction_response_id"],
        )
        if key in receipt_by_key:
            raise ValueError("coordinator response receipts duplicate a row")
        receipt_by_key[key] = receipt
        expected_hash, expected_issuance, expected_name = expected_final_hashes.get(
            key, ("", "", "")
        )
        material = material_by_participant.get(receipt["participant_id"])
        expected_receipt_id = "rcpt_" + hashlib.sha256(
            (
                f"{expected_issuance}|{receipt['extraction_response_id']}|"
                f"{receipt['received_utc']}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        if (
            material is None
            or receipt["receipt_id"] != expected_receipt_id
            or receipt["final_row_sha256"] != expected_hash
            or receipt["issuance_id"] != expected_issuance
            or receipt["canonical_response_file"] != expected_name
            or receipt["packet_id"] != material["packet_id"]
            or receipt["participant_role"] != material["participant_role"]
            or receipt["assigned_arm"] != material["assigned_arm"]
            or key not in response_by_key
            or receipt["extraction_snapshot_sha256"]
            != response_by_key[key]["extraction_snapshot_sha256"]
        ):
            raise ValueError(
                "formal response differs from coordinator receipt"
            )
        response = response_by_key[key]
        issuance = next(
            (
                value
                for value in active.values()
                if value["issuance_id"] == expected_issuance
            ),
            None,
        )
        if issuance is None or not (
            parse_utc(str(issuance["issued_utc"]))
            <= parse_utc(response["composition_started_utc"])
            <= parse_utc(response["completed_utc"])
            <= parse_utc(receipt["received_utc"])
        ):
            raise ValueError(
                "receipt issuance/composition times are out of order"
            )
    if set(receipt_by_key) != expected_keys:
        raise ValueError("coordinator receipts do not exactly cover responses")
    collection = load_json(root / "coordinator_collection_receipt.json")
    if (
        collection.get("schema_version") != COLLECTION_RECEIPT_SCHEMA_VERSION
        or collection.get("workflow_version") != WORKFLOW_VERSION
        or collection.get("status") != "COORDINATOR_FINAL_RESPONSES_RECEIVED"
        or collection.get("receipt_sha256")
        != collection_receipt_sha256(collection)
        or collection.get("coordinator_packet_registry_sha256")
        != registry_file_hash
        or collection.get("composition_issuance_registry_sha256")
        != sha256_file(issuance_registry_path)
        or collection.get("composition_issuance_registry_record_sha256")
        != registry["registry_sha256"]
        or collection.get("response_receipts_sha256")
        != sha256_file(root / "coordinator_response_receipts.csv")
        or collection.get("formal_response_rows") != len(expected_keys)
    ):
        raise ValueError("coordinator collection receipt is invalid")
    if any(
        receipt["received_utc"] != collection.get("received_utc")
        for receipt in receipts
    ):
        raise ValueError("response receipt times differ from collection receipt")
    expected_files = {
        name: {
            "rows": len(rows),
            "sha256": sha256_file(root / name),
        }
        for name, rows in response_rows_by_file.items()
    }
    if collection.get("formal_response_files") != expected_files:
        raise ValueError("collection receipt formal-file hashes changed")
    received_time = parse_utc(str(collection.get("received_utc") or ""))
    if any(
        parse_utc((row.get("completed_utc") or "").strip()) > received_time
        for rows in response_rows_by_file.values()
        for row in rows
    ):
        raise ValueError("formal response completion follows coordinator receipt")
    return {
        "coordinator_receipt_rows": len(receipts),
        "coordinator_active_issuances": len(active),
        "coordinator_corrections": len(corrections),
        "coordinator_invalidated_composition_archives": len(corrections),
        "coordinator_collection_receipt": "VERIFIED",
    }


def empty_issuance_registry(
    packet_registry_path: Path,
) -> dict[str, Any]:
    registry: dict[str, Any] = {
        "schema_version": ISSUANCE_REGISTRY_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "status": "NO_COMPOSITION_PACKETS_ISSUED",
        "coordinator_packet_registry_sha256": sha256_file(
            packet_registry_path
        ),
        "issuance_rows_sha256": sha256_bytes(
            csv_bytes(ISSUANCE_ROW_HEADER, [])
        ),
        "correction_ledger_sha256": sha256_bytes(
            csv_bytes(CORRECTION_HEADER, [])
        ),
        "invalidated_composition_archive_schema_version": (
            INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION
        ),
        "invalidated_composition_archives": [],
        "issuance_count": 0,
        "issuances": [],
    }
    registry["registry_sha256"] = issuance_registry_sha256(registry)
    return registry


def expected_zero_response_receipt(
    root: Path,
    packet_registry_path: Path,
) -> dict[str, Any]:
    empty_registry = empty_issuance_registry(packet_registry_path)
    receipt: dict[str, Any] = {
        "schema_version": COLLECTION_RECEIPT_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "status": "NO_FORMAL_RESPONSES",
        "coordinator_packet_registry_sha256": sha256_file(
            packet_registry_path
        ),
        "composition_issuance_registry_sha256": sha256_bytes(
            json_bytes(empty_registry)
        ),
        "composition_issuance_registry_record_sha256": empty_registry[
            "registry_sha256"
        ],
        "response_receipts_sha256": sha256_bytes(
            csv_bytes(RECEIPT_HEADER, [])
        ),
        "formal_response_files": {
            name: {
                "rows": 0,
                "sha256": sha256_file(root / name),
            }
            for name in FORMAL_RESPONSE_FILES
        },
        "formal_response_rows": 0,
        "received_utc": "",
    }
    receipt["receipt_sha256"] = collection_receipt_sha256(receipt)
    return receipt


def resolve_issued_packet_directory(
    packet_root: Path,
    relative_directory: str,
) -> Path:
    relative = Path(relative_directory)
    if (
        not relative_directory
        or relative.is_absolute()
        or relative.as_posix() != relative_directory
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("issued composition packet path is unsafe")
    resolved_root = packet_root.resolve()
    candidate = (packet_root / relative).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            "issued composition packet path escapes packet root"
        ) from exc
    if not candidate.is_dir() or candidate.is_symlink():
        raise ValueError(
            f"issued composition packet directory is missing: "
            f"{relative_directory}"
        )
    return candidate


def validate_issued_composition_packets(
    packet_root: Path,
    packet_registry_path: Path,
    issuance_registry: Mapping[str, Any],
    issuance_rows: Sequence[Mapping[str, str]],
    materials: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not packet_root.is_dir():
        raise ValueError("composition packet root is missing or not a directory")
    packet_root = packet_root.resolve()
    by_packet, _by_participant = material_maps(materials)
    rows_by_issuance: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in issuance_rows:
        rows_by_issuance[row["issuance_id"]].append(row)
    required_names = {
        "composition.csv",
        "instructions_stage2.md",
        "locked_extraction.csv",
        "stage2_config.json",
    }
    expected_files: set[str] = set()
    verified_rows = 0
    packet_registry_file_sha256 = sha256_file(packet_registry_path)
    for issuance in issuance_registry["issuances"]:
        relative_directory = str(issuance["relative_directory"])
        directory = resolve_issued_packet_directory(
            packet_root, relative_directory
        )
        entries = {path.name for path in directory.iterdir()}
        if entries != required_names or any(
            not path.is_file() or path.is_symlink()
            for path in directory.iterdir()
        ):
            raise ValueError(
                f"issued composition packet {relative_directory} does not "
                "contain exactly the four frozen files"
            )
        files = {name: directory / name for name in required_names}
        expected_hashes = {
            "locked_extraction.csv": issuance[
                "locked_extraction_sha256"
            ],
            "composition.csv": issuance["composition_template_sha256"],
            "instructions_stage2.md": issuance[
                "instructions_stage2_sha256"
            ],
            "stage2_config.json": issuance["stage2_config_sha256"],
        }
        for name, expected_hash in expected_hashes.items():
            if sha256_file(files[name]) != expected_hash:
                raise ValueError(
                    f"issued composition packet hash changed: "
                    f"{relative_directory}/{name}"
                )
            expected_files.add(f"{relative_directory}/{name}")
        material = by_packet.get(str(issuance["packet_id"]))
        if material is None:
            raise ValueError("issued composition packet has an unknown packet ID")
        locked_header_observed, locked_rows = read_csv(
            files["locked_extraction.csv"]
        )
        composition_header_observed, composition_rows = read_csv(
            files["composition.csv"]
        )
        spec = material["spec"]
        if (
            locked_header_observed != locked_header(spec)
            or composition_header_observed != composition_header(spec)
            or len(locked_rows) != issuance["row_count"]
            or len(composition_rows) != issuance["row_count"]
        ):
            raise ValueError(
                f"issued composition packet schema/count changed: "
                f"{relative_directory}"
            )
        anchors = rows_by_issuance.get(str(issuance["issuance_id"]), [])
        reconstructed_locked, _final_rows = locked_rows_from_submission(
            composition_rows=composition_rows,
            material=material,
            issuance=issuance,
            anchors=anchors,
            packet_registry_file_sha256=packet_registry_file_sha256,
            validate_outputs=False,
        )
        if locked_rows != reconstructed_locked:
            raise ValueError(
                f"issued locked extraction differs from composition locks: "
                f"{relative_directory}"
            )
        try:
            config = load_json(files["stage2_config.json"])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"issued stage2 config is unreadable: {relative_directory}"
            ) from exc
        expected_config = {
            "schema_version": STAGE2_CONFIG_SCHEMA_VERSION,
            "workflow_version": WORKFLOW_VERSION,
            "issuance_id": issuance["issuance_id"],
            "packet_id": issuance["packet_id"],
            "participant_id": issuance["participant_id"],
            "participant_role": issuance["participant_role"],
            "assigned_arm": issuance["assigned_arm"],
            "extraction_version": issuance["extraction_version"],
            "response_id_field": spec["response_id_field"],
            "expected_rows": issuance["row_count"],
            "coordinator_packet_registry_sha256": (
                packet_registry_file_sha256
            ),
            "locked_extraction_sha256": issuance[
                "locked_extraction_sha256"
            ],
            "extraction_rows_root_sha256": issuance[
                "extraction_rows_root_sha256"
            ],
            "locked_fields": list(locked_header(spec)),
            "submission_fields": list(COMPOSITION_FIELDS),
        }
        if config != expected_config:
            raise ValueError(
                f"issued stage2 config metadata changed: "
                f"{relative_directory}"
            )
        verified_rows += int(issuance["row_count"])
    actual_files = {
        path.relative_to(packet_root).as_posix()
        for path in packet_root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError(
            "composition packet root contains missing or unregistered files"
        )
    return {
        "issued_composition_packet_directories_verified": len(
            issuance_registry["issuances"]
        ),
        "issued_composition_packet_files_verified": len(expected_files),
        "issued_composition_packet_rows_verified": verified_rows,
        "issued_composition_packet_byte_verification": "VERIFIED_STRICT",
    }


def validate_frozen_coordinator_state(
    root: Path,
    *,
    composition_packets_root: Path | None = None,
    portable: bool = False,
) -> dict[str, Any]:
    packet_registry_path = root / "coordinator_packet_registry.json"
    registry, materials = validate_registry_against_package(
        packet_registry_path,
        frozen_path=root / "frozen_test_claims.csv",
        assignments_path=root / "auditor_assignments.csv",
        public_roster_path=root / "participant_metadata_public_template.csv",
    )
    issuance_registry, issuance_rows, corrections = validate_issuance_state(
        packet_registry_path,
        root / "composition_packet_issuance_registry.json",
        root / "composition_issuance_rows.csv",
        root / "review_extraction_corrections.csv",
        verify_archive_files=not portable,
    )
    active = validate_issuance_chains(
        issuance_registry,
        issuance_rows,
        corrections,
        materials,
        root,
        verify_archive_files=not portable,
    )
    archive_root = root / INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY
    if not corrections and archive_root.exists():
        raise ValueError(
            "frozen coordinator state contains an unreferenced composition archive"
        )
    receipt_header, receipts = read_csv(
        root / "coordinator_response_receipts.csv"
    )
    if (
        receipt_header != RECEIPT_HEADER
        or receipts
        or sha256_file(root / "coordinator_response_receipts.csv")
        != sha256_bytes(csv_bytes(RECEIPT_HEADER, []))
    ):
        raise ValueError("frozen pretest state contains response receipts")
    for name in FORMAL_RESPONSE_FILES:
        _header, rows = read_csv(root / name)
        if rows:
            raise ValueError(
                f"frozen coordinator state contains formal responses: {name}"
            )
    collection = load_json(root / "coordinator_collection_receipt.json")
    if collection != expected_zero_response_receipt(
        root, packet_registry_path
    ):
        raise ValueError(
            "frozen zero-response coordinator sentinel is invalid"
        )
    result: dict[str, Any] = {
        "coordinator_packet_registry_record_sha256": registry[
            "registry_sha256"
        ],
        "coordinator_stage1_packets": len(materials),
        "coordinator_stage1_rows": sum(
            len(material["rows"]) for material in materials
        ),
        "coordinator_composition_issuances": len(
            issuance_registry["issuances"]
        ),
        "coordinator_active_composition_issuances": len(active),
        "coordinator_issuance_rows": len(issuance_rows),
        "coordinator_corrections": len(corrections),
        "coordinator_invalidated_composition_archives": len(corrections),
        "coordinator_response_receipts": 0,
        "coordinator_collection_receipt": (
            "ZERO_RESPONSE_SENTINEL_NO_COORDINATOR_RECEIPTS"
        ),
    }
    if not issuance_registry["issuances"]:
        if issuance_rows or corrections or active:
            raise ValueError("empty composition issuance state has ledger rows")
        result.update(
            {
                "composition_substate": (
                    "frozen_calibration_passed_before_composition_issuance"
                ),
                "issued_composition_packet_byte_verification": (
                    "NOT_APPLICABLE_NO_ISSUANCES"
                ),
            }
        )
        return result

    expected_packets = {
        str(material["packet_id"]) for material in materials
    }
    if (
        set(active) != expected_packets
        or len(active) != 27
        or len(issuance_registry["issuances"])
        != len(materials) + len(corrections)
        or sum(int(record["row_count"]) for record in active.values())
        != sum(len(material["rows"]) for material in materials)
    ):
        raise ValueError(
            "issued frozen state lacks 27 complete active composition packets"
        )
    result["composition_substate"] = "composition_issued_no_responses"
    result["coordinator_active_composition_rows"] = sum(
        int(record["row_count"]) for record in active.values()
    )
    if portable:
        if composition_packets_root is not None:
            raise ValueError(
                "portable frozen validation cannot byte-verify an external "
                "composition packet root"
            )
        result["issued_composition_packet_byte_verification"] = (
            "NOT_PERFORMED_PORTABLE_INTERNAL_CHAIN_ONLY"
        )
        return result
    if composition_packets_root is None:
        raise ValueError(
            "strict frozen issued state requires --composition-packets-root"
        )
    result.update(
        validate_issued_composition_packets(
            composition_packets_root,
            packet_registry_path,
            issuance_registry,
            issuance_rows,
            materials,
        )
    )
    return result


def fill_compositions(root: Path, registry_path: Path) -> None:
    issuance_registry = load_json(registry_path)
    for issuance in issuance_registry["issuances"]:
        path = root / issuance["relative_directory"] / "composition.csv"
        header, rows = read_csv(path)
        for row in rows:
            row.update(
                {
                    "response_status": "completed",
                    "composition_started_utc": "2026-07-18T09:11:00Z",
                    "evidence_support_label": "supported_as_written",
                    "evidence_support_reason": "source facts support the wording",
                    "comparability_label": "same_estimand",
                    "comparability_reason": "the scientific quantities align",
                    "completed_utc": "2026-07-18T09:12:00Z",
                }
            )
        write_csv(path, header, rows)


def self_test() -> None:
    workspace = PACKAGE / ".response_collector_selftest_workspace"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir()
    try:
        registry, materials = expected_registry(
            frozen_path=PACKAGE / "frozen_test_claims.csv",
            assignments_path=PACKAGE / "auditor_assignments.csv",
            public_roster_path=PACKAGE / "participant_metadata_public_template.csv",
        )
        registry_path = workspace / "coordinator_packet_registry.json"
        write_json(registry_path, registry)
        returned_stage1 = workspace / "returned_stage1"
        write_stage1_packets(returned_stage1, materials)
        fill_extractions(returned_stage1, materials)
        state = workspace / "state"
        state.mkdir()
        for name in FORMAL_RESPONSE_FILES:
            shutil.copy2(PACKAGE / name, state / name)
        initialize_empty_coordinator_state(state, registry_path)
        issued = workspace / "issued"
        issue_initial(
            returned_root=returned_stage1,
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
        for name in (
            "frozen_test_claims.csv",
            "frozen_text_corrections.csv",
            "auditor_assignments.csv",
            "participant_metadata_public_template.csv",
        ):
            shutil.copy2(PACKAGE / name, state / name)
        shutil.copy2(
            registry_path, state / "coordinator_packet_registry.json"
        )
        strict_issued = validate_frozen_coordinator_state(
            state,
            composition_packets_root=issued,
        )
        if (
            strict_issued["composition_substate"]
            != "composition_issued_no_responses"
            or strict_issued["coordinator_active_composition_issuances"]
            != 27
            or strict_issued["coordinator_active_composition_rows"] != 7200
            or strict_issued["issued_composition_packet_files_verified"] != 108
            or strict_issued["coordinator_response_receipts"] != 0
            or strict_issued["coordinator_collection_receipt"]
            != "ZERO_RESPONSE_SENTINEL_NO_COORDINATOR_RECEIPTS"
        ):
            raise AssertionError(
                "legal issued frozen state was not strictly verified"
            )
        try:
            validate_frozen_coordinator_state(state)
        except ValueError as exc:
            if "--composition-packets-root" not in str(exc):
                raise
        else:
            raise AssertionError(
                "strict issued frozen validation accepted a missing packet root"
            )
        first_issued_record = load_json(
            state / "composition_packet_issuance_registry.json"
        )["issuances"][0]
        tampered_packet = (
            issued
            / first_issued_record["relative_directory"]
            / "composition.csv"
        )
        original_packet = tampered_packet.read_bytes()
        tampered_packet.write_bytes(original_packet + b"\n")
        try:
            validate_frozen_coordinator_state(
                state,
                composition_packets_root=issued,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "strict issued frozen validation accepted a changed packet"
            )
        tampered_packet.write_bytes(original_packet)
        portable_issued = validate_frozen_coordinator_state(
            state,
            portable=True,
        )
        if (
            portable_issued["composition_substate"]
            != "composition_issued_no_responses"
            or portable_issued[
                "issued_composition_packet_byte_verification"
            ]
            != "NOT_PERFORMED_PORTABLE_INTERNAL_CHAIN_ONLY"
            or portable_issued["coordinator_response_receipts"] != 0
        ):
            raise AssertionError(
                "portable issued frozen internal validation failed"
            )
        try:
            validate_collection_artifacts(state)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "issued zero-response state passed collected validation"
            )
        first_material = materials[0]
        first_extraction_path = (
            returned_stage1
            / first_material["relative_directory"]
            / "extraction.csv"
        )
        extraction_header, extraction_rows = read_csv(
            first_extraction_path
        )
        extraction_rows[0][
            first_material["spec"]["extraction_fields"][0]
        ] += " corrected"
        write_csv(
            first_extraction_path, extraction_header, extraction_rows
        )
        old_registry = load_json(
            state / "composition_packet_issuance_registry.json"
        )
        old_issuance = next(
            value
            for value in old_registry["issuances"]
            if value["packet_id"] == first_material["packet_id"]
        )
        issue_correction(
            participant_id=first_material["participant_id"],
            returned_extraction_path=first_extraction_path,
            invalidated_composition_path=(
                issued
                / old_issuance["relative_directory"]
                / "composition.csv"
            ),
            correction_reason="synthetic collector correction",
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
            issued_utc="2026-07-18T09:10:30Z",
        )
        fill_compositions(
            issued, state / "composition_packet_issuance_registry.json"
        )
        current_registry = load_json(
            state / "composition_packet_issuance_registry.json"
        )
        _correction_header, current_corrections = read_csv(
            state / "review_extraction_corrections.csv"
        )
        first_issuance = active_issuances(
            current_registry, current_corrections
        )[first_material["packet_id"]]
        first_path = (
            issued / first_issuance["relative_directory"] / "composition.csv"
        )
        header, rows = read_csv(first_path)
        original = rows[0]["claim_text"]
        rows[0]["claim_text"] = "tampered locked claim"
        write_csv(first_path, header, rows)
        try:
            collect(
                returned_root=issued,
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
                received_utc="2026-07-18T09:13:00Z",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("collector accepted changed locked extraction")
        rows[0]["claim_text"] = original
        write_csv(first_path, header, rows)
        output = workspace / "collected"
        result = collect(
            returned_root=issued,
            output_root=output,
            packet_registry_path=registry_path,
            issuance_registry_path=state
            / "composition_packet_issuance_registry.json",
            issuance_rows_path=state / "composition_issuance_rows.csv",
            corrections_path=state / "review_extraction_corrections.csv",
            frozen_path=PACKAGE / "frozen_test_claims.csv",
            assignments_path=PACKAGE / "auditor_assignments.csv",
            public_roster_path=PACKAGE
            / "participant_metadata_public_template.csv",
            received_utc="2026-07-18T09:13:00Z",
        )
        if result["formal_response_rows"] != 7200:
            raise AssertionError("collector output row count is wrong")
        verify_root = workspace / "verify"
        verify_root.mkdir()
        for name in (
            "frozen_test_claims.csv",
            "frozen_text_corrections.csv",
            "auditor_assignments.csv",
            "participant_metadata_public_template.csv",
        ):
            shutil.copy2(PACKAGE / name, verify_root / name)
        shutil.copy2(registry_path, verify_root / registry_path.name)
        for name in (
            "composition_packet_issuance_registry.json",
            "composition_issuance_rows.csv",
            "review_extraction_corrections.csv",
        ):
            shutil.copy2(state / name, verify_root / name)
        shutil.copytree(
            state / INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY,
            verify_root / INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY,
        )
        for name in (*FORMAL_RESPONSE_FILES, "coordinator_response_receipts.csv"):
            shutil.copy2(output / name, verify_root / name)
        shutil.copy2(
            output / "coordinator_collection_receipt.json",
            verify_root / "coordinator_collection_receipt.json",
        )
        verified = validate_collection_artifacts(verify_root)
        if verified["coordinator_corrections"] != 1:
            raise AssertionError("legal corrected collection was not verified")
        _header, verified_corrections = read_csv(
            verify_root / "review_extraction_corrections.csv"
        )
        archived_composition = resolve_invalidated_archive(
            verify_root,
            verified_corrections[0][
                "invalidated_composition_archive_relative_path"
            ],
        )
        archived_payload = archived_composition.read_bytes()
        archived_composition.unlink()
        try:
            validate_collection_artifacts(verify_root)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "collected validator accepted a deleted archive"
            )
        archived_composition.write_bytes(archived_payload + b"\n")
        try:
            validate_collection_artifacts(verify_root)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "collected validator accepted a changed archive"
            )
        archived_composition.write_bytes(archived_payload)
        validate_collection_artifacts(verify_root)
        arm_path = verify_root / "arm_A_responses.csv"
        arm_header, arm_rows = read_csv(arm_path)
        arm_rows[0]["evidence_support_label"] = "contradicted"
        write_csv(arm_path, arm_header, arm_rows)
        try:
            validate_collection_artifacts(verify_root)
        except ValueError:
            pass
        else:
            raise AssertionError("validator accepted a post-receipt label edit")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print("self-test passed; coordinator collection/receipt fixture removed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--returned-compositions", type=Path)
    parser.add_argument("--recorded-utc")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--packet-registry", type=Path, default=DEFAULT_PACKET_REGISTRY
    )
    parser.add_argument(
        "--issuance-registry", type=Path, default=DEFAULT_ISSUANCE_REGISTRY
    )
    parser.add_argument(
        "--issuance-rows", type=Path, default=DEFAULT_ISSUANCE_ROWS
    )
    parser.add_argument(
        "--corrections", type=Path, default=DEFAULT_CORRECTIONS
    )
    parser.add_argument(
        "--frozen-claims", type=Path, default=PACKAGE / "frozen_test_claims.csv"
    )
    parser.add_argument(
        "--assignments", type=Path, default=PACKAGE / "auditor_assignments.csv"
    )
    parser.add_argument(
        "--public-roster",
        type=Path,
        default=PACKAGE / "participant_metadata_public_template.csv",
    )
    parser.add_argument(
        "--manifest", type=Path, default=PACKAGE / "MANIFEST.sha256"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.returned_compositions is None or not args.recorded_utc:
        raise ValueError(
            "--returned-compositions and --recorded-utc are required"
        )
    result = collect(
        returned_root=args.returned_compositions,
        output_root=args.output,
        packet_registry_path=args.packet_registry,
        issuance_registry_path=args.issuance_registry,
        issuance_rows_path=args.issuance_rows,
        corrections_path=args.corrections,
        frozen_path=args.frozen_claims,
        assignments_path=args.assignments,
        public_roster_path=args.public_roster,
        received_utc=args.recorded_utc,
        manifest_path=args.manifest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
