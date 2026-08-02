#!/usr/bin/env python3
"""Build coordinator-anchored, extraction-only stage-1 review packets."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_assignments import ASSIGNMENT_HEADER, ARMS
from build_calibration_packets import PRIVATE_ROSTER_HEADER
from build_review_packets import (
    build_auditor_and_gold_packets,
    read_header,
    role_roster,
    validate_public_private_roster_match,
)
from freeze_human_sample import FROZEN_HEADER
from frozen_text_corrections import (
    SCHEMA_VERSION as FROZEN_TEXT_CORRECTION_SCHEMA_VERSION,
)
from score_calibration import assert_calibration_release
from staged_review_core import (
    COLLECTION_RECEIPT_SCHEMA_VERSION,
    CORRECTION_HEADER,
    INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY,
    INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION,
    ISSUANCE_REGISTRY_SCHEMA_VERSION,
    ISSUANCE_ROW_HEADER,
    PACKET_REGISTRY_SCHEMA_VERSION,
    RECEIPT_HEADER,
    WORKFLOW_VERSION,
    collection_receipt_sha256,
    csv_bytes,
    immutable_rows_sha256,
    issuance_registry_sha256,
    json_bytes,
    make_stage1_config,
    ordered_response_ids_sha256,
    packet_id,
    packet_registry_sha256,
    packet_spec,
    participant_slug,
    read_csv,
    registry_entry_sha256,
    sha256_bytes,
    sha256_file,
    stage1_header,
    write_csv,
    write_json,
    canonical_sha256,
)


PACKAGE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PACKAGE / "generated_staged_review_packets_v2"
DEFAULT_REGISTRY = PACKAGE / "coordinator_packet_registry.json"

COMMON_INSTRUCTIONS = """\

Complete every extraction cell from the supplied source material. Do not leave
a cell blank: use exactly `not_applicable` or `unknown` when that is the
faithful extraction. Use `source_location_checked=yes`, `not_applicable`, or
`unknown` where that field is present. Record the UTC start timestamp for every
row. Leave the coordinator completion timestamp blank.

Return the completed `extraction.csv` to the coordinator. The coordinator will
validate it against the frozen assignment and source records. Do not rename,
reorder, add, or remove rows or columns.
"""

ROLE_INSTRUCTIONS = {
    "A": """# Extraction submission — Auditor Arm A

Extract the reported result facts, verify number/direction and quantifier
scope, record the stated causal basis, identify compared items and the measured
quantity/unit, and note ordinary experimental controls. Link the extraction to
the supplied source location.
""",
    "B": """# Extraction submission — Auditor Arm B

Use the supplied source to record population or setting, intervention,
comparison, outcome, outcome unit and aggregation, and standard controls
reported or missing. Link the extraction to the supplied source location.
""",
    "C": """# Extraction submission — Auditor Arm C

Record the evidence condition on each side, what each intervention changes,
the outcome definition/unit/aggregation on each side, their relations, and
claim-specific controls and findings. Link the extraction to the supplied
source location. Do not infer an unreported fact.
""",
    "D": """# Extraction submission — Auditor Arm D

Use the full frozen diagnostic extraction:

- C1: evidence state on each side and its relation.
- C2: origin or attacker capability, including access, knowledge, adaptive
  behavior, target scope, and budget.
- C3: changed intervention component and fixed pipeline.
- C4: outcome definition, direction, unit, aggregation, denominator, baseline,
  and uncertainty.
- C5: action set, operating point, coverage, alternatives, stakes, costs, and
  shared utility.

Also record required controls, findings, and the checked source location.
""",
    "gold": """# Extraction submission — Independent gold expert

Using only the supplied source material and ordinary scientific language,
record reported result facts, compared items, studied setting, measured
quantity and unit, decision or recommendation context, controls needed for the
claim, and controls found. Do not infer an unreported fact.
""",
}

PARTICIPANT_FILE_NAMES = (
    "extraction.csv",
    "instructions_stage1.md",
    "stage1_config.json",
)
FORMAL_RESPONSE_FILES = (
    "arm_A_responses.csv",
    "arm_B_responses.csv",
    "arm_C_responses.csv",
    "arm_D_responses.csv",
    "gold_responses.csv",
)


def initial_stage1_rows(
    source_rows: Sequence[Mapping[str, str]], spec: Mapping[str, Any]
) -> list[dict[str, str]]:
    header = stage1_header(spec)
    immutable = set(spec["immutable_fields"])
    return [
        {
            field: (source.get(field) or "") if field in immutable else ""
            for field in header
        }
        for source in source_rows
    ]


def packet_materials(
    frozen_rows: Sequence[Mapping[str, str]],
    assignment_rows: Sequence[Mapping[str, str]],
    public_roster_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    arm_headers = {
        arm: read_header(PACKAGE / f"arm_{arm}_responses.csv") for arm in ARMS
    }
    gold_header = read_header(PACKAGE / "gold_responses.csv")
    combined = build_auditor_and_gold_packets(
        frozen_rows,
        assignment_rows,
        public_roster_rows,
        arm_headers,
        gold_header,
    )
    materials: list[dict[str, Any]] = []
    for relative, (_combined_header, combined_rows) in sorted(combined.items()):
        if not combined_rows:
            raise ValueError(f"empty internal reconstruction: {relative}")
        participant_id = (combined_rows[0].get("participant_id") or "").strip()
        role = "auditor" if relative.startswith("auditors/") else "gold_expert"
        arm = (
            (combined_rows[0].get("arm") or "").strip()
            if role == "auditor"
            else ""
        )
        spec = packet_spec(role, arm)
        rows = initial_stage1_rows(combined_rows, spec)
        identifier = packet_id(role, participant_id)
        config = make_stage1_config(
            packet=identifier,
            participant_id=participant_id,
            role=role,
            arm=arm,
            expected_rows=len(rows),
        )
        instructions = (
            ROLE_INSTRUCTIONS[arm if role == "auditor" else "gold"]
            + COMMON_INSTRUCTIONS
        ).rstrip() + "\n"
        relative_directory = (
            ("auditors" if role == "auditor" else "gold")
            + "/"
            + participant_slug(role, participant_id)
        )
        materials.append(
            {
                "packet_id": identifier,
                "participant_id": participant_id,
                "participant_role": role,
                "assigned_arm": arm,
                "relative_directory": relative_directory,
                "spec": spec,
                "rows": rows,
                "config": config,
                "instructions": instructions,
                "extraction_payload": csv_bytes(stage1_header(spec), rows),
                "config_payload": json_bytes(config),
                "instructions_payload": instructions.encode("utf-8"),
            }
        )
    return sorted(materials, key=lambda value: value["packet_id"])


def make_registry(
    materials: Sequence[Mapping[str, Any]],
    *,
    frozen_claims_sha256: str,
    frozen_text_corrections_sha256: str,
    assignments_sha256: str,
    public_role_roster_sha256: str,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for material in materials:
        spec = material["spec"]
        rows = material["rows"]
        entry: dict[str, Any] = {
            "packet_id": material["packet_id"],
            "participant_id": material["participant_id"],
            "participant_role": material["participant_role"],
            "assigned_arm": material["assigned_arm"],
            "relative_directory": material["relative_directory"],
            "response_id_field": spec["response_id_field"],
            "expected_rows": len(rows),
            "immutable_fields": list(spec["immutable_fields"]),
            "extraction_fields": list(spec["extraction_fields"]),
            "immutable_rows_sha256": immutable_rows_sha256(
                rows, spec["immutable_fields"]
            ),
            "ordered_response_ids_sha256": ordered_response_ids_sha256(
                rows, spec["response_id_field"]
            ),
            "stage1_extraction_template_sha256": sha256_bytes(
                material["extraction_payload"]
            ),
            "stage1_config_sha256": sha256_bytes(material["config_payload"]),
            "stage1_instructions_sha256": sha256_bytes(
                material["instructions_payload"]
            ),
        }
        entry["entry_sha256"] = registry_entry_sha256(entry)
        entries.append(entry)
    registry: dict[str, Any] = {
        "schema_version": PACKET_REGISTRY_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "status": "COORDINATOR_STAGE1_REGISTRY_FROZEN",
        "frozen_claims_sha256": frozen_claims_sha256,
        "frozen_text_correction_schema_version": (
            FROZEN_TEXT_CORRECTION_SCHEMA_VERSION
        ),
        "frozen_text_corrections_sha256": (
            frozen_text_corrections_sha256
        ),
        "assignments_sha256": assignments_sha256,
        "public_role_roster_sha256": public_role_roster_sha256,
        "packet_count": len(entries),
        "total_extraction_rows": sum(
            int(entry["expected_rows"]) for entry in entries
        ),
        "packets": entries,
    }
    registry["registry_sha256"] = packet_registry_sha256(registry)
    return registry


def expected_registry(
    *,
    frozen_path: Path,
    assignments_path: Path,
    public_roster_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frozen_header, frozen_rows = read_csv(frozen_path)
    if frozen_header != FROZEN_HEADER:
        raise ValueError("frozen claim schema mismatch")
    assignment_header, assignment_rows = read_csv(assignments_path)
    if assignment_header != ASSIGNMENT_HEADER:
        raise ValueError("assignment schema mismatch")
    _public_header, public_rows = read_csv(public_roster_path)
    public_role_roster_hash = canonical_sha256(
        {
            "schema_version": "public-role-roster-projection-v2",
            "participants": sorted(
                [
                    {
                        "participant_id": (row.get("participant_id") or "").strip(),
                        "role": (row.get("role") or "").strip().lower(),
                        "assigned_arm": (
                            row.get("assigned_arm") or ""
                        ).strip().upper(),
                        "replacement_status": (
                            row.get("replacement_status") or ""
                        ).strip().lower(),
                    }
                    for row in public_rows
                ],
                key=lambda value: value["participant_id"],
            ),
        }
    )
    materials = packet_materials(frozen_rows, assignment_rows, public_rows)
    registry = make_registry(
        materials,
        frozen_claims_sha256=sha256_file(frozen_path),
        frozen_text_corrections_sha256=sha256_file(
            frozen_path.parent / "frozen_text_corrections.csv"
        ),
        assignments_sha256=sha256_file(assignments_path),
        public_role_roster_sha256=public_role_roster_hash,
    )
    return registry, materials


def validate_registry_against_package(
    registry_path: Path,
    *,
    frozen_path: Path,
    assignments_path: Path,
    public_roster_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        observed = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read coordinator packet registry: {exc}") from exc
    expected, materials = expected_registry(
        frozen_path=frozen_path,
        assignments_path=assignments_path,
        public_roster_path=public_roster_path,
    )
    if observed != expected:
        raise ValueError(
            "coordinator packet registry differs from frozen package reconstruction"
        )
    return observed, materials


def write_stage1_packets(
    output: Path, materials: Sequence[Mapping[str, Any]]
) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for material in materials:
        directory = output / material["relative_directory"]
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "extraction.csv").write_bytes(
            material["extraction_payload"]
        )
        (directory / "stage1_config.json").write_bytes(
            material["config_payload"]
        )
        (directory / "instructions_stage1.md").write_bytes(
            material["instructions_payload"]
        )
        if tuple(sorted(path.name for path in directory.iterdir())) != (
            "extraction.csv",
            "instructions_stage1.md",
            "stage1_config.json",
        ):
            raise AssertionError("stage-1 directory has an unauthorized file")


def make_empty_issuance_registry(
    packet_registry_path: Path,
    issuance_rows_path: Path,
    corrections_path: Path,
) -> dict[str, Any]:
    registry: dict[str, Any] = {
        "schema_version": ISSUANCE_REGISTRY_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "status": "NO_COMPOSITION_PACKETS_ISSUED",
        "coordinator_packet_registry_sha256": sha256_file(
            packet_registry_path
        ),
        "issuance_rows_sha256": sha256_file(issuance_rows_path),
        "correction_ledger_sha256": sha256_file(corrections_path),
        "invalidated_composition_archive_schema_version": (
            INVALIDATED_COMPOSITION_ARCHIVE_SCHEMA_VERSION
        ),
        "invalidated_composition_archives": [],
        "issuance_count": 0,
        "issuances": [],
    }
    registry["registry_sha256"] = issuance_registry_sha256(registry)
    return registry


def initialize_empty_coordinator_state(
    state_dir: Path, packet_registry_path: Path
) -> None:
    archive_root = state_dir / INVALIDATED_COMPOSITION_ARCHIVE_DIRECTORY
    if archive_root.exists():
        if any(path.is_file() for path in archive_root.rglob("*")):
            raise ValueError(
                "cannot reset coordinator state with invalidated archives"
            )
        shutil.rmtree(archive_root)
    for name in FORMAL_RESPONSE_FILES:
        _header, rows = read_csv(state_dir / name)
        if rows:
            raise ValueError("cannot reset coordinator state after formal responses")
    existing_registry_path = (
        state_dir / "composition_packet_issuance_registry.json"
    )
    if existing_registry_path.exists():
        try:
            existing_registry = json.loads(
                existing_registry_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "cannot reset malformed coordinator issuance state"
            ) from exc
        if existing_registry.get("issuances"):
            raise ValueError(
                "cannot reset coordinator state after stage-2 issuance"
            )
    for name in (
        "composition_issuance_rows.csv",
        "review_extraction_corrections.csv",
        "coordinator_response_receipts.csv",
    ):
        path = state_dir / name
        if path.exists() and read_csv(path)[1]:
            raise ValueError(f"cannot reset nonempty coordinator ledger {name}")
    issuance_rows_path = state_dir / "composition_issuance_rows.csv"
    corrections_path = state_dir / "review_extraction_corrections.csv"
    receipts_path = state_dir / "coordinator_response_receipts.csv"
    write_csv(issuance_rows_path, ISSUANCE_ROW_HEADER, [])
    write_csv(corrections_path, CORRECTION_HEADER, [])
    write_csv(receipts_path, RECEIPT_HEADER, [])
    issuance_registry = make_empty_issuance_registry(
        packet_registry_path, issuance_rows_path, corrections_path
    )
    issuance_registry_path = existing_registry_path
    write_json(issuance_registry_path, issuance_registry)
    receipt: dict[str, Any] = {
        "schema_version": COLLECTION_RECEIPT_SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "status": "NO_FORMAL_RESPONSES",
        "coordinator_packet_registry_sha256": sha256_file(
            packet_registry_path
        ),
        "composition_issuance_registry_sha256": sha256_file(
            issuance_registry_path
        ),
        "composition_issuance_registry_record_sha256": issuance_registry[
            "registry_sha256"
        ],
        "response_receipts_sha256": sha256_file(receipts_path),
        "formal_response_files": {
            name: {
                "rows": 0,
                "sha256": sha256_file(state_dir / name),
            }
            for name in FORMAL_RESPONSE_FILES
        },
        "formal_response_rows": 0,
        "received_utc": "",
    }
    receipt["receipt_sha256"] = collection_receipt_sha256(receipt)
    write_json(state_dir / "coordinator_collection_receipt.json", receipt)


def run_self_test() -> None:
    workspace = PACKAGE / ".staged_review_selftest_workspace"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir()
    try:
        registry, materials = expected_registry(
            frozen_path=PACKAGE / "frozen_test_claims.csv",
            assignments_path=PACKAGE / "auditor_assignments.csv",
            public_roster_path=PACKAGE / "participant_metadata_public_template.csv",
        )
        if len(materials) != 27 or registry["total_extraction_rows"] != 7200:
            raise AssertionError("stage-1 fixture has the wrong size")
        output = workspace / "packets"
        write_stage1_packets(output, materials)
        forbidden = {
            "evidence_support_label",
            "comparability_label",
            "supported_after_narrowing",
            "same_estimand",
            "instructions_stage2",
            "composition.csv",
        }
        roles: set[tuple[str, str]] = set()
        for material in materials:
            roles.add(
                (material["participant_role"], material["assigned_arm"])
            )
            directory = output / material["relative_directory"]
            for path in directory.iterdir():
                text = path.read_text(encoding="utf-8").lower()
                if any(token in text for token in forbidden):
                    raise AssertionError(f"stage-1 leakage in {path}")
            if material["assigned_arm"] == "C":
                schema = " ".join(material["spec"]["extraction_fields"]).lower()
                if any(
                    token in schema
                    for token in (
                        "origin",
                        "capability",
                        "policy",
                        "utility",
                        "budget",
                        "coverage",
                    )
                ):
                    raise AssertionError("Arm C leaks ablated extraction fields")
            if material["participant_role"] == "gold_expert":
                instruction = material["instructions"]
                if any(f"C{index}" in instruction for index in range(1, 6)):
                    raise AssertionError("gold instructions leak coordinates")
        expected_roles = {
            ("auditor", arm) for arm in ARMS
        } | {("gold_expert", "")}
        if roles != expected_roles:
            raise AssertionError("stage-1 self-test omitted a role/arm")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print("self-test passed; 27 label-free stage-1 fixtures removed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frozen-claims", type=Path, default=PACKAGE / "frozen_test_claims.csv"
    )
    parser.add_argument(
        "--assignments", type=Path, default=PACKAGE / "auditor_assignments.csv"
    )
    parser.add_argument(
        "--roster",
        type=Path,
        default=PACKAGE / "participant_metadata_private_template.csv",
    )
    parser.add_argument(
        "--public-roster",
        type=Path,
        default=PACKAGE / "participant_metadata_public_template.csv",
    )
    parser.add_argument(
        "--calibration-summary",
        type=Path,
        default=PACKAGE / "calibration_summary.json",
    )
    parser.add_argument(
        "--calibration-responses",
        type=Path,
        default=PACKAGE / "calibration_responses.csv",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--coordinator-state-dir", type=Path, default=PACKAGE
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0
    private_header, private_rows = read_csv(args.roster)
    if private_header != PRIVATE_ROSTER_HEADER:
        raise ValueError("private roster schema mismatch")
    role_roster(private_rows)
    public_rows = assert_calibration_release(
        args.public_roster,
        args.calibration_summary,
        args.calibration_responses,
    )
    validate_public_private_roster_match(private_rows, public_rows)
    registry, materials = expected_registry(
        frozen_path=args.frozen_claims,
        assignments_path=args.assignments,
        public_roster_path=args.public_roster,
    )
    write_stage1_packets(args.output, materials)
    write_json(args.registry, registry)
    initialize_empty_coordinator_state(
        args.coordinator_state_dir, args.registry
    )
    summary = {
        "status": "COORDINATOR_STAGE1_PACKETS_NO_TEST_RESPONSES",
        "workflow_version": WORKFLOW_VERSION,
        "participant_packets": len(materials),
        "total_extraction_rows": registry["total_extraction_rows"],
        "test_labels_generated": 0,
        "participant_files_per_packet": list(PARTICIPANT_FILE_NAMES),
        "coordinator_packet_registry": str(args.registry),
        "coordinator_packet_registry_sha256": sha256_file(args.registry),
        "coordinator_packet_registry_record_sha256": registry[
            "registry_sha256"
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
