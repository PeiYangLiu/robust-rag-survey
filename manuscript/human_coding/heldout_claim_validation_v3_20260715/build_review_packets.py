#!/usr/bin/env python3
"""Build coordinator-internal combined templates or post-gold adjudication."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_assignments import (
    ARMS,
    DEFAULT_SEED,
    Claim,
    build_assignments,
    stable_digest,
    validate_assignment_rows,
)
from freeze_human_sample import FROZEN_HEADER
from build_calibration_packets import PUBLIC_ROSTER_HEADER
from score_calibration import (
    CALIBRATION_RESPONSE_HEADER,
    assert_calibration_release,
)


PACKAGE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PACKAGE / "generated_packets"
DEFAULT_ADJUDICATOR_REGISTRY = PACKAGE / "adjudicator_packet_registry.json"
GOLD_DISPLAY_SEED = 2026071506
ADJUDICATOR_PACKET_VERSION = "adjudicator-packet-v1"
ADJUDICATOR_REGISTRY_SCHEMA_VERSION = (
    "coordinator-adjudicator-packet-registry-v1"
)
RAW_FIELDS = (
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
)
FORBIDDEN_PACKET_TOKENS = (
    "model",
    "prescreen",
    "coordinator_only",
    "primary_stratum",
    "sampling_stratum",
)
ADJUDICATOR_PACKET_HEADER = (
    "adjudication_id",
    "claim_id",
    "source_key",
    "participant_id",
    "disputed_outputs",
    "blinded_gold_response_ids",
    "raw_materials_sha256",
    "claim_text",
    "context_before",
    "context_after",
    "source_title",
    "source_section",
    "source_locator",
    "source_url_or_doi",
    "source_evidence_excerpt",
    "source_file_sha256",
    "gold_1_evidence_support_label",
    "gold_1_evidence_support_reason",
    "gold_1_comparability_label",
    "gold_1_comparability_reason",
    "gold_2_evidence_support_label",
    "gold_2_evidence_support_reason",
    "gold_2_comparability_label",
    "gold_2_comparability_reason",
    "gold_3_evidence_support_label",
    "gold_3_evidence_support_reason",
    "gold_3_comparability_label",
    "gold_3_comparability_reason",
    "response_status",
    "missing_reason_code",
    "independent_review_started_utc",
    "source_facts_checked",
    "adjudicated_evidence_support_label",
    "evidence_support_rationale",
    "adjudicated_comparability_label",
    "comparability_rationale",
    "supported_comparison_scope",
    "other_adjudicator_response_seen",
    "completed_utc",
)


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def read_header(path: Path) -> tuple[str, ...]:
    header, _rows = read_csv(path)
    return header


def write_csv(
    path: Path, header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    with staging.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    staging.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def csv_bytes(
    header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=header, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def adjudication_id(
    role: str,
    participant_id: str,
    claim_id: str,
    disputed_outputs: Sequence[str],
) -> str:
    digest = canonical_sha256(
        {
            "packet_version": ADJUDICATOR_PACKET_VERSION,
            "participant_id": participant_id,
            "claim_id": claim_id,
            "disputed_outputs": list(disputed_outputs),
        }
    )
    return f"adj_{role[-1]}_{digest[:20]}"


def adjudicator_registry_sha256(registry: Mapping[str, object]) -> str:
    return canonical_sha256(
        {
            key: value
            for key, value in registry.items()
            if key != "registry_sha256"
        }
    )


def adjudicator_registry_record_sha256(
    record: Mapping[str, object],
) -> str:
    return canonical_sha256(
        {
            key: value
            for key, value in record.items()
            if key != "record_sha256"
        }
    )


def public_role_roster_sha256(
    roster_rows: Sequence[Mapping[str, str]],
) -> str:
    participants = [
        {
            "participant_id": (row.get("participant_id") or "").strip(),
            "role": (row.get("role") or "").strip().lower(),
            "assigned_arm": (row.get("assigned_arm") or "").strip().upper(),
            "replacement_status": (
                row.get("replacement_status") or ""
            ).strip().lower(),
        }
        for row in roster_rows
    ]
    participants.sort(key=lambda row: row["participant_id"])
    return canonical_sha256(
        {
            "schema_version": "public-role-roster-projection-v2",
            "participants": participants,
        }
    )


def build_adjudicator_registry(
    packets: Mapping[
        str, tuple[Sequence[str], Sequence[Mapping[str, object]]]
    ],
    *,
    frozen_claims_sha256: str,
    gold_responses_sha256: str,
    public_role_roster_sha256: str,
) -> dict[str, Any]:
    packet_records: list[dict[str, object]] = []
    row_records: list[dict[str, object]] = []
    disagreement_claims: set[str] = set()
    for relative, (header, rows) in sorted(packets.items()):
        packet_payload = csv_bytes(header, rows)
        packet_sha256 = hashlib.sha256(packet_payload).hexdigest()
        matching_roles = [
            role
            for role in ("adjudicator_1", "adjudicator_2")
            if Path(relative).name.startswith(f"{role}_")
        ]
        if len(matching_roles) != 1:
            raise ValueError(
                f"adjudicator packet path has no unique role: {relative}"
            )
        role = matching_roles[0]
        participant_ids = {
            str(row.get("participant_id") or "") for row in rows
        }
        if len(participant_ids) != 1:
            raise ValueError(
                f"adjudicator packet {relative} lacks one participant identity"
            )
        participant_id = next(iter(participant_ids))
        packet_row_records: list[dict[str, object]] = []
        for display_order, row in enumerate(rows, start=1):
            record: dict[str, object] = {
                "adjudication_id": str(row.get("adjudication_id") or ""),
                "claim_id": str(row.get("claim_id") or ""),
                "source_key": str(row.get("source_key") or ""),
                "participant_id": participant_id,
                "adjudicator_role": role,
                "packet_version": ADJUDICATOR_PACKET_VERSION,
                "packet_relative_path": relative,
                "packet_sha256": packet_sha256,
                "display_order": display_order,
                "disputed_outputs": str(row.get("disputed_outputs") or ""),
                "blinded_gold_response_ids": str(
                    row.get("blinded_gold_response_ids") or ""
                ),
                "raw_materials_sha256": str(
                    row.get("raw_materials_sha256") or ""
                ),
                "record_sha256": "",
            }
            record["record_sha256"] = adjudicator_registry_record_sha256(
                record
            )
            packet_row_records.append(record)
            row_records.append(record)
            disagreement_claims.add(str(record["claim_id"]))
        packet_record: dict[str, object] = {
            "adjudicator_role": role,
            "participant_id": participant_id,
            "packet_version": ADJUDICATOR_PACKET_VERSION,
            "relative_path": relative,
            "row_count": len(rows),
            "packet_sha256": packet_sha256,
            "rows_root_sha256": canonical_sha256(
                {"rows": packet_row_records}
            ),
            "record_sha256": "",
        }
        packet_record["record_sha256"] = (
            adjudicator_registry_record_sha256(packet_record)
        )
        packet_records.append(packet_record)
    if packets and len(packet_records) != 2:
        raise ValueError("a nonempty adjudication requires two packets")
    registry: dict[str, Any] = {
        "schema_version": ADJUDICATOR_REGISTRY_SCHEMA_VERSION,
        "packet_version": ADJUDICATOR_PACKET_VERSION,
        "status": (
            "COORDINATOR_ADJUDICATOR_PACKETS_ISSUED"
            if packet_records
            else "NO_ADJUDICATOR_PACKETS_ISSUED"
        ),
        "frozen_claims_sha256": frozen_claims_sha256,
        "gold_responses_sha256": gold_responses_sha256,
        "public_role_roster_sha256": public_role_roster_sha256,
        "disagreement_claim_count": len(disagreement_claims),
        "packet_count": len(packet_records),
        "row_count": len(row_records),
        "packets": packet_records,
        "rows": row_records,
        "registry_sha256": "",
    }
    registry["registry_sha256"] = adjudicator_registry_sha256(registry)
    return registry


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_bytes(json_bytes(value))
    staging.replace(path)


def safe_packet_name(role: str, participant_id: str) -> str:
    digest = hashlib.sha256(
        f"{role}|{participant_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{role}_{digest}.csv"


def validate_packet_header(header: Sequence[str], name: str) -> None:
    lowered = [field.lower() for field in header]
    leaked = [
        field
        for field in lowered
        if any(token in field for token in FORBIDDEN_PACKET_TOKENS)
    ]
    if leaked:
        raise ValueError(f"{name} leaks hidden/model fields: {leaked}")


def claims_by_id(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    claims: dict[str, Mapping[str, str]] = {}
    for row in rows:
        claim_id = (row.get("claim_id") or "").strip()
        if not claim_id or claim_id in claims:
            raise ValueError(f"empty or duplicate frozen claim ID: {claim_id}")
        claims[claim_id] = row
    return claims


def role_roster(
    rows: Sequence[Mapping[str, str]]
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    ids = [(row.get("participant_id") or "").strip() for row in rows]
    if "" in ids or len(ids) != len(set(ids)):
        raise ValueError("role roster has empty or duplicate participant IDs")
    auditors = [
        (row.get("participant_id") or "").strip()
        for row in rows
        if (row.get("role") or "").strip().lower() == "auditor"
        and (row.get("replacement_status") or "").strip().lower()
        not in {"reserve", "inactive"}
    ]
    gold = [
        (row.get("participant_id") or "").strip()
        for row in rows
        if (row.get("role") or "").strip().lower() == "gold_expert"
    ]
    adjudicators = {
        role: [
            (row.get("participant_id") or "").strip()
            for row in rows
            if (row.get("role") or "").strip().lower() == role
        ]
        for role in ("adjudicator_1", "adjudicator_2")
    }
    if len(auditors) != 24 or len(gold) != 3:
        raise ValueError("roster must contain 24 auditors and three gold experts")
    if any(len(adjudicators[role]) != 1 for role in adjudicators):
        raise ValueError("roster must contain two distinct named adjudicator roles")
    return auditors, gold, adjudicators


def validate_public_private_roster_match(
    private_rows: Sequence[Mapping[str, str]],
    public_rows: Sequence[Mapping[str, str]],
) -> None:
    private_by_id = {
        (row.get("participant_id") or "").strip(): row for row in private_rows
    }
    public_by_id = {
        (row.get("participant_id") or "").strip(): row for row in public_rows
    }
    if set(private_by_id) != set(public_by_id):
        raise ValueError(
            "private test roster does not exactly match the calibrated public roster"
        )
    for participant_id, private in private_by_id.items():
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
            if private_value != public_value:
                raise ValueError(
                    f"private/public roster {field} mismatch for {participant_id}"
                )


def blank_row(header: Sequence[str]) -> dict[str, str]:
    return {field: "" for field in header}


def populate_raw_fields(
    row: dict[str, str], claim: Mapping[str, str]
) -> None:
    for field in RAW_FIELDS:
        if field in row:
            row[field] = (claim.get(field) or "").strip()


def build_auditor_and_gold_packets(
    frozen_rows: Sequence[Mapping[str, str]],
    assignment_rows: Sequence[Mapping[str, str]],
    roster_rows: Sequence[Mapping[str, str]],
    arm_headers: Mapping[str, Sequence[str]],
    gold_header: Sequence[str],
) -> dict[str, tuple[tuple[str, ...], list[dict[str, str]]]]:
    claims = claims_by_id(frozen_rows)
    auditors, gold_ids, _adjudicators = role_roster(roster_rows)
    claim_objects = [
        Claim(claim_id=claim_id, source_key=(row.get("source_key") or "").strip())
        for claim_id, row in claims.items()
    ]
    validate_assignment_rows(
        assignment_rows, claim_objects, auditors, DEFAULT_SEED
    )
    for arm, header in arm_headers.items():
        validate_packet_header(header, f"Arm {arm}")
    validate_packet_header(gold_header, "gold")

    packets: dict[str, tuple[tuple[str, ...], list[dict[str, str]]]] = {}
    assignments_by_participant: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    participant_arm: dict[str, str] = {}
    for assignment in assignment_rows:
        participant_id = (assignment.get("participant_id") or "").strip()
        assignments_by_participant[participant_id].append(assignment)
        participant_arm[participant_id] = (assignment.get("arm") or "").strip()
    for participant_id in auditors:
        arm = participant_arm[participant_id]
        header = tuple(arm_headers[arm])
        rows: list[dict[str, str]] = []
        for assignment in sorted(
            assignments_by_participant[participant_id],
            key=lambda row: int((row.get("participant_item_order") or "0")),
        ):
            claim = claims[(assignment.get("claim_id") or "").strip()]
            packet_row = blank_row(header)
            for field in (
                "assignment_id",
                "claim_id",
                "source_key",
                "participant_id",
                "arm",
                "packet_version",
            ):
                packet_row[field] = (assignment.get(field) or "").strip()
            packet_row["display_order"] = (
                assignment.get("participant_item_order") or ""
            ).strip()
            populate_raw_fields(packet_row, claim)
            rows.append(packet_row)
        path = f"auditors/{safe_packet_name('auditor', participant_id)}"
        packets[path] = (header, rows)

    for participant_id in gold_ids:
        ordered_claims = sorted(
            claims.values(),
            key=lambda claim: stable_digest(
                GOLD_DISPLAY_SEED,
                f"gold-order|{participant_id}",
                (claim.get("claim_id") or "").strip(),
            ),
        )
        rows = []
        for display_order, claim in enumerate(ordered_claims, start=1):
            packet_row = blank_row(gold_header)
            claim_id = (claim.get("claim_id") or "").strip()
            packet_row["gold_response_id"] = (
                "gold_"
                + hashlib.sha256(
                    f"{participant_id}|{claim_id}".encode("utf-8")
                ).hexdigest()[:20]
            )
            packet_row["participant_id"] = participant_id
            packet_row["packet_version"] = (
                claim.get("freeze_version") or ""
            ).strip()
            packet_row["display_order"] = str(display_order)
            populate_raw_fields(packet_row, claim)
            rows.append(packet_row)
        path = f"gold/{safe_packet_name('gold', participant_id)}"
        packets[path] = (tuple(gold_header), rows)

    forbidden_claim_fields = {
        "coordinator_only_primary_stratum",
        "sampling_record_sha256",
    }
    for path, (header, _rows) in packets.items():
        if forbidden_claim_fields.intersection(header):
            raise ValueError(f"{path} leaks coordinator-only fields")
    return packets


def gold_disagreements(
    gold_rows: Sequence[Mapping[str, str]]
) -> dict[str, tuple[list[Mapping[str, str]], list[str]]]:
    by_claim: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in gold_rows:
        by_claim[(row.get("claim_id") or "").strip()].append(row)
    disputes: dict[str, tuple[list[Mapping[str, str]], list[str]]] = {}
    for claim_id, rows in by_claim.items():
        completed = [
            row
            for row in rows
            if (row.get("response_status") or "").strip() == "completed"
        ]
        if len(completed) < 3:
            continue
        if len(completed) != 3 or len(
            {(row.get("participant_id") or "").strip() for row in completed}
        ) != 3:
            raise ValueError(
                f"claim {claim_id} has invalid completed gold multiplicity"
            )
        if any(
            (row.get("evidence_support_label") or "").strip()
            not in {
                "supported_as_written",
                "supported_after_narrowing",
                "contradicted",
                "insufficient_source_evidence",
            }
            or (row.get("comparability_label") or "").strip()
            not in {
                "same_estimand",
                "comparable_with_declared_scope",
                "different_estimand",
                "missing_comparison_assumption",
                "not_a_comparability_claim",
            }
            for row in completed
        ):
            raise ValueError(f"claim {claim_id} has an invalid gold label")
        outputs = []
        if len(
            {
                (row.get("evidence_support_label") or "").strip()
                for row in completed
            }
        ) > 1:
            outputs.append("evidence_support")
        if len(
            {
                (row.get("comparability_label") or "").strip()
                for row in completed
            }
        ) > 1:
            outputs.append("comparability")
        if outputs:
            disputes[claim_id] = (completed, outputs)
    return disputes


def build_adjudicator_packets(
    frozen_rows: Sequence[Mapping[str, str]],
    roster_rows: Sequence[Mapping[str, str]],
    gold_rows: Sequence[Mapping[str, str]],
) -> dict[str, tuple[tuple[str, ...], list[dict[str, str]]]]:
    claims = claims_by_id(frozen_rows)
    _auditors, _gold, adjudicators = role_roster(roster_rows)
    disputes = gold_disagreements(gold_rows)
    gold_claim_ids = {
        (row.get("claim_id") or "").strip() for row in gold_rows
    }
    if not gold_claim_ids.issubset(claims):
        raise ValueError("gold responses contain a non-frozen claim")
    if not disputes:
        return {}
    packets: dict[str, tuple[tuple[str, ...], list[dict[str, str]]]] = {}
    for role in ("adjudicator_1", "adjudicator_2"):
        participant_id = adjudicators[role][0]
        rows: list[dict[str, str]] = []
        for claim_id in sorted(
            disputes,
            key=lambda value: stable_digest(
                GOLD_DISPLAY_SEED, f"{role}|{participant_id}", value
            ),
        ):
            gold_records, outputs = disputes[claim_id]
            blinded = sorted(
                gold_records,
                key=lambda row: stable_digest(
                    GOLD_DISPLAY_SEED,
                    f"blind-gold|{claim_id}",
                    (row.get("gold_response_id") or "").strip(),
                ),
            )
            claim = claims[claim_id]
            row = blank_row(ADJUDICATOR_PACKET_HEADER)
            row["adjudication_id"] = adjudication_id(
                role,
                participant_id,
                claim_id,
                outputs,
            )
            row["claim_id"] = claim_id
            row["source_key"] = (claim.get("source_key") or "").strip()
            row["participant_id"] = participant_id
            row["disputed_outputs"] = "|".join(outputs)
            row["blinded_gold_response_ids"] = "expert_1|expert_2|expert_3"
            populate_raw_fields(row, claim)
            gold_material: dict[str, object] = {}
            for index, gold in enumerate(blinded, start=1):
                for output_field in (
                    "evidence_support_label",
                    "evidence_support_reason",
                    "comparability_label",
                    "comparability_reason",
                ):
                    target = f"gold_{index}_{output_field}"
                    row[target] = (gold.get(output_field) or "").strip()
                    gold_material[target] = row[target]
            row["raw_materials_sha256"] = canonical_sha256(
                {
                    "claim": {field: (claim.get(field) or "") for field in RAW_FIELDS},
                    "blinded_gold": gold_material,
                }
            )
            row["other_adjudicator_response_seen"] = "false"
            rows.append(row)
        path = f"adjudicators/{safe_packet_name(role, participant_id)}"
        packets[path] = (ADJUDICATOR_PACKET_HEADER, rows)
    return packets


def write_packets(
    output: Path,
    packets: Mapping[str, tuple[Sequence[str], Sequence[Mapping[str, object]]]],
    packet_type: str,
    *,
    adjudicator_registry: Mapping[str, object] | None = None,
    adjudicator_registry_path: Path | None = None,
) -> dict[str, object]:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for relative, (header, rows) in sorted(packets.items()):
        path = output / relative
        write_csv(path, header, rows)
        entries.append(
            {
                "path": relative,
                "rows": len(rows),
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "status": (
            "INTERNAL_NOT_FOR_DISTRIBUTION"
            if packet_type == "auditor_and_gold_internal"
            else "BLINDED_ADJUDICATOR_PACKETS_NO_RESPONSES"
        ),
        "packet_type": packet_type,
        "packets": entries,
        "model_fields_included": False,
        "coordinator_stratum_included": False,
        "other_adjudicator_response_included": False,
    }
    if adjudicator_registry is not None:
        if adjudicator_registry_path is None:
            raise ValueError("adjudicator registry output path is missing")
        if (
            adjudicator_registry_path.resolve() == output.resolve()
            or output.resolve() in adjudicator_registry_path.resolve().parents
        ):
            raise ValueError(
                "coordinator adjudicator registry cannot be placed in the "
                "participant packet output"
            )
        write_json(adjudicator_registry_path, adjudicator_registry)
        manifest.update(
            {
                "adjudicator_packet_version": ADJUDICATOR_PACKET_VERSION,
                "coordinator_adjudicator_registry_path": str(
                    adjudicator_registry_path.name
                ),
                "coordinator_adjudicator_registry_sha256": sha256_file(
                    adjudicator_registry_path
                ),
                "coordinator_adjudicator_registry_record_sha256": (
                    adjudicator_registry["registry_sha256"]
                ),
            }
        )
    manifest_path = output / "packet_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


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
        "--gold-responses", type=Path, default=PACKAGE / "gold_responses.csv"
    )
    parser.add_argument(
        "--public-roster",
        type=Path,
        default=PACKAGE / "participant_metadata_public_template.csv",
        help="non-PII roster with passing calibration statuses",
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
    parser.add_argument(
        "--adjudicator-registry",
        type=Path,
        default=DEFAULT_ADJUDICATOR_REGISTRY,
        help="coordinator-only registry retained in the collected package",
    )
    parser.add_argument("--adjudicator-after-gold", action="store_true")
    parser.add_argument(
        "--internal-combined",
        action="store_true",
        help="coordinator-only legacy combined templates; never distribute",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def self_test() -> None:
    frozen = []
    for index in range(20):
        frozen.append(
            {
                "claim_id": f"claim_{index:02d}",
                "source_key": f"source_{index // 2:02d}",
                "claim_text": f"Claim {index}",
                "context_before": "before",
                "context_after": "after",
                "source_title": f"Source {index // 2}",
                "source_section": "Results",
                "source_locator": "PDF page 1",
                "source_url_or_doi": "https://example.invalid",
                "source_evidence_excerpt": f"Claim {index}",
                "source_file_sha256": "a" * 64,
                "coordinator_only_primary_stratum": "c2_decisive",
                "freeze_version": "self-test",
            }
        )
    auditors = [f"auditor_{index:02d}" for index in range(24)]
    assignments = build_assignments(
        [Claim(row["claim_id"], row["source_key"]) for row in frozen],
        auditors,
        DEFAULT_SEED,
    )
    groups: dict[str, str] = {}
    for row in assignments:
        groups[row["participant_id"]] = row["arm"]
    roster = [
        {
            "participant_id": participant_id,
            "role": "auditor",
            "assigned_arm": groups[participant_id],
            "replacement_status": "primary",
        }
        for participant_id in auditors
    ]
    roster.extend(
        {
            "participant_id": f"gold_{index}",
            "role": "gold_expert",
            "replacement_status": "primary",
        }
        for index in range(3)
    )
    roster.extend(
        {
            "participant_id": f"adj_{index}",
            "role": f"adjudicator_{index}",
            "replacement_status": "primary",
        }
        for index in (1, 2)
    )
    public_roster = []
    for source in roster:
        row = {field: "" for field in PUBLIC_ROSTER_HEADER}
        row.update(
            {
                "participant_id": source["participant_id"],
                "role": source["role"],
                "assigned_arm": source.get("assigned_arm", ""),
                "replacement_status": source["replacement_status"],
                "calibration_status": "passed_round_1",
                "included_in_primary_analysis": "pending_test_completion",
            }
        )
        public_roster.append(row)
    fake_summary = json.loads(
        (PACKAGE / "calibration_summary.json").read_text(encoding="utf-8")
    )
    frozen_calibration_item_ids = fake_summary["calibration_item_ids"]
    fake_summary.update(
        {
            "status": "FROZEN_CALIBRATION_PASSED_BEFORE_TEST",
            "test_packet_release_eligible": True,
            "response_rows": 0,
            "participant_status_counts": {"passed_round_1": 29},
            "participants": [
            {
                "participant_id": row["participant_id"],
                "role": row["role"],
                "assigned_arm": row.get("assigned_arm", ""),
                "final_status": "passed_round_1",
                "rounds": [
                    {
                        "round": 1,
                        "evidence_correct": 8,
                        "comparability_correct": 8,
                        "evidence_accuracy": 0.8,
                        "comparability_accuracy": 0.8,
                        "passed": True,
                        "outcome": "passed",
                        "item_results": [
                            {
                                "calibration_item_id": item_id,
                                "calibration_response_id": (
                                    f"{row['participant_id']}_{item_id}"
                                ),
                                "evidence_support_correct": True,
                                "comparability_correct": True,
                            }
                            for item_id in frozen_calibration_item_ids
                        ],
                    }
                ],
            }
            for row in roster
            ],
        }
    )
    workspace = PACKAGE / ".packet_selftest_workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    try:
        public_path = workspace / "public.csv"
        response_path = workspace / "calibration_responses.csv"
        summary_path = workspace / "calibration_summary.json"
        write_csv(public_path, PUBLIC_ROSTER_HEADER, public_roster)
        write_csv(response_path, CALIBRATION_RESPONSE_HEADER, [])
        fake_summary["calibration_responses_sha256"] = sha256_file(response_path)
        fake_summary["public_roster_sha256"] = sha256_file(public_path)
        summary_path.write_text(
            json.dumps(fake_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            assert_calibration_release(public_path, summary_path, response_path)
        except ValueError as exc:
            if "real item-level calibration ledger" not in str(exc):
                raise AssertionError(
                    "fabricated-summary attack was not rejected by ledger audit"
                ) from exc
        else:
            raise AssertionError(
                "header-only ledger plus fabricated passing summary opened the gate"
            )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    validate_public_private_roster_match(roster, public_roster)
    arm_headers = {
        arm: read_header(PACKAGE / f"arm_{arm}_responses.csv") for arm in ARMS
    }
    gold_header = read_header(PACKAGE / "gold_responses.csv")
    packets = build_auditor_and_gold_packets(
        frozen, assignments, roster, arm_headers, gold_header
    )
    if len(packets) != 27:
        raise AssertionError("packet self-test did not create 24+3 packets")
    for header, rows in packets.values():
        validate_packet_header(header, "self-test")
        if any(
            (row.get("evidence_support_label") or "")
            or (row.get("comparability_label") or "")
            for row in rows
        ):
            raise AssertionError("packet self-test created a response label")
    gold_rows = []
    for claim in frozen:
        for expert in range(3):
            comparability = "same_estimand"
            if claim["claim_id"] == "claim_00" and expert == 2:
                comparability = "different_estimand"
            response_status = (
                "unable_to_determine"
                if claim["claim_id"] == "claim_01" and expert == 2
                else "completed"
            )
            gold_rows.append(
                {
                    "claim_id": claim["claim_id"],
                    "participant_id": f"gold_{expert}",
                    "gold_response_id": f"{claim['claim_id']}_{expert}",
                    "response_status": response_status,
                    "evidence_support_label": (
                        "supported_as_written"
                        if response_status == "completed"
                        else ""
                    ),
                    "evidence_support_reason": (
                        "reason" if response_status == "completed" else ""
                    ),
                    "comparability_label": (
                        comparability if response_status == "completed" else ""
                    ),
                    "comparability_reason": (
                        "reason" if response_status == "completed" else ""
                    ),
                }
            )
    adjudicator_packets = build_adjudicator_packets(frozen, roster, gold_rows)
    if len(adjudicator_packets) != 2:
        raise AssertionError("adjudicator self-test did not create two packets")
    for _header, rows in adjudicator_packets.values():
        if len(rows) != 1 or rows[0]["other_adjudicator_response_seen"] != "false":
            raise AssertionError("adjudicator packet independence check failed")
        if (
            rows[0]["adjudicated_evidence_support_label"]
            or rows[0]["adjudicated_comparability_label"]
        ):
            raise AssertionError("adjudicator packet contains a response label")
    registry = build_adjudicator_registry(
        adjudicator_packets,
        frozen_claims_sha256="a" * 64,
        gold_responses_sha256="b" * 64,
        public_role_roster_sha256="c" * 64,
    )
    reversed_registry = build_adjudicator_registry(
        build_adjudicator_packets(frozen, roster, list(reversed(gold_rows))),
        frozen_claims_sha256="a" * 64,
        gold_responses_sha256="b" * 64,
        public_role_roster_sha256="c" * 64,
    )
    if (
        registry != reversed_registry
        or registry["packet_count"] != 2
        or registry["row_count"] != 2
        or registry["disagreement_claim_count"] != 1
    ):
        raise AssertionError(
            "adjudicator registry is incomplete or input-order dependent"
        )
    for record in registry["rows"]:
        outputs = str(record["disputed_outputs"]).split("|")
        if record["adjudication_id"] != adjudication_id(
            str(record["adjudicator_role"]),
            str(record["participant_id"]),
            str(record["claim_id"]),
            outputs,
        ):
            raise AssertionError("adjudication ID is not deterministic")
        if record["claim_id"] == "claim_01":
            raise AssertionError("incomplete gold incorrectly triggered adjudication")
    print("self-test passed; no packets or labels written")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.adjudicator_after_gold and not args.internal_combined:
        raise ValueError(
            "combined auditor/gold packets are prohibited for participant "
            "distribution; use build_staged_review_packets.py (or pass "
            "--internal-combined for a coordinator-only template)"
        )
    frozen_header, frozen_rows = read_csv(args.frozen_claims)
    if frozen_header != FROZEN_HEADER:
        raise ValueError("frozen claim schema mismatch")
    _roster_header, roster_rows = read_csv(args.roster)
    public_rows = assert_calibration_release(
        args.public_roster,
        args.calibration_summary,
        args.calibration_responses,
    )
    validate_public_private_roster_match(roster_rows, public_rows)
    if args.adjudicator_after_gold:
        _gold_header, gold_rows = read_csv(args.gold_responses)
        packets = build_adjudicator_packets(frozen_rows, public_rows, gold_rows)
        registry = build_adjudicator_registry(
            packets,
            frozen_claims_sha256=sha256_file(args.frozen_claims),
            gold_responses_sha256=sha256_file(args.gold_responses),
            public_role_roster_sha256=public_role_roster_sha256(public_rows),
        )
        manifest = write_packets(
            args.output,
            packets,
            "adjudicator_after_gold",
            adjudicator_registry=registry,
            adjudicator_registry_path=args.adjudicator_registry,
        )
    else:
        _assignment_header, assignment_rows = read_csv(args.assignments)
        arm_headers = {
            arm: read_header(PACKAGE / f"arm_{arm}_responses.csv") for arm in ARMS
        }
        gold_header = read_header(PACKAGE / "gold_responses.csv")
        packets = build_auditor_and_gold_packets(
            frozen_rows,
            assignment_rows,
            roster_rows,
            arm_headers,
            gold_header,
        )
        manifest = write_packets(
            args.output, packets, "auditor_and_gold_internal"
        )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
