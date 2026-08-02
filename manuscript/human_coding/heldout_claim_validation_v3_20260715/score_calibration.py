#!/usr/bin/env python3
"""Validate and score completed frozen-calibration packets without reading PII."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_calibration_packets import (
    ANSWER_KEY_STATUS,
    CALIBRATION_ITEM_COUNT,
    CALIBRATION_VERSION,
    COMPARABILITY_LABELS,
    EVIDENCE_LABELS,
    PACKET_HEADER,
    PACKET_ITEM_MAP,
    PUBLIC_ROSTER_HEADER,
    RESPONSE_FIELDS,
    calibration_response_id,
    calibration_set_sha256,
    participant_item_digest,
    read_calibration_items,
    read_calibration_key,
    read_csv,
    sha256_file,
    write_csv,
)


PACKAGE = Path(__file__).resolve().parent
MINIMUM_CORRECT_PER_DIMENSION = 8
MAXIMUM_RETRAINING_ATTEMPTS = 1
CALIBRATION_RESPONSE_HEADER = (
    "calibration_response_id",
    "calibration_round",
    "calibration_item_id",
    "calibration_source_key",
    "participant_id",
    "participant_role",
    "assigned_arm",
    "display_order",
    "packet_version",
    "calibration_set_sha256",
    "item_record_sha256",
    "claim_text",
    "source_locator",
    "response_status",
    "missing_reason_code",
    "evidence_support_label",
    "evidence_support_reason",
    "comparability_label",
    "comparability_reason",
    "instructor_feedback_code",
    "evidence_support_correct",
    "comparability_correct",
    "passed_for_live_assignment",
    "completed_utc",
)
ALLOWED_CALIBRATION_STATUSES = frozenset(
    {
        "",
        "awaiting_calibration",
        "retraining_required_round_2",
        "passed_round_1",
        "passed_round_2",
        "exclude_before_test",
    }
)
PASS_STATUSES = frozenset({"passed_round_1", "passed_round_2"})
SUMMARY_SCHEMA_VERSION = "frozen-calibration-summary-v2"
UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)


def csv_bytes(
    header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_completed_utc(value: str) -> bool:
    if not UTC_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def validate_public_roster_rows(
    rows: Sequence[Mapping[str, str]], *, allow_empty: bool
) -> list[str]:
    errors: list[str] = []
    if not rows:
        if not allow_empty:
            errors.append("public calibration roster must contain 29 rows")
        return errors
    if len(rows) != 29:
        errors.append(f"public calibration roster has {len(rows)} rows, not 29")
    ids = [(row.get("participant_id") or "").strip() for row in rows]
    if "" in ids or len(ids) != len(set(ids)):
        errors.append("public calibration participant IDs are empty or duplicated")
    roles = Counter((row.get("role") or "").strip().lower() for row in rows)
    expected_roles = Counter(
        {
            "auditor": 24,
            "gold_expert": 3,
            "adjudicator_1": 1,
            "adjudicator_2": 1,
        }
    )
    if roles != expected_roles:
        errors.append(f"public calibration role counts are invalid: {dict(roles)}")
    arms: Counter[str] = Counter()
    for index, row in enumerate(rows, start=2):
        role = (row.get("role") or "").strip().lower()
        arm = (row.get("assigned_arm") or "").strip().upper()
        status = (row.get("calibration_status") or "").strip()
        if status not in ALLOWED_CALIBRATION_STATUSES:
            errors.append(f"public roster row {index} has invalid calibration status")
        if (row.get("replacement_status") or "").strip().lower() != "primary":
            errors.append(f"public roster row {index} is not an active primary")
        expected_inclusion = (
            "pending_test_completion" if status in PASS_STATUSES else "false"
        )
        if (
            (row.get("included_in_primary_analysis") or "").strip()
            != expected_inclusion
        ):
            errors.append(
                f"public roster row {index} has an invalid primary-analysis status"
            )
        if role == "auditor":
            if arm not in {"A", "B", "C", "D"}:
                errors.append(f"public roster row {index} has invalid auditor arm")
            else:
                arms[arm] += 1
        elif arm:
            errors.append(f"public roster row {index} gives a non-auditor an arm")
    if arms != Counter({"A": 6, "B": 6, "C": 6, "D": 6}):
        errors.append(f"public calibration auditor arm counts are invalid: {dict(arms)}")
    return errors


def read_public_roster(
    path: Path, *, allow_empty: bool
) -> list[dict[str, str]]:
    header, rows = read_csv(path)
    if header != PUBLIC_ROSTER_HEADER:
        raise ValueError(
            "public roster must use the exact non-PII public template schema"
        )
    errors = validate_public_roster_rows(rows, allow_empty=allow_empty)
    if errors:
        raise ValueError("; ".join(errors))
    return rows


def expected_feedback(
    response: Mapping[str, str], key: Mapping[str, str]
) -> tuple[bool, bool, str]:
    evidence_correct = (
        response["evidence_support_label"] == key["evidence_support_label"]
    )
    comparability_correct = (
        response["comparability_label"] == key["comparability_label"]
    )
    feedback = "|".join(
        (
            "evidence:"
            + key["evidence_feedback_code"]
            + (":correct" if evidence_correct else ":review"),
            "comparability:"
            + key["comparability_feedback_code"]
            + (":correct" if comparability_correct else ":review"),
        )
    )
    return evidence_correct, comparability_correct, feedback


def expected_order(
    participant_id: str, items: Sequence[Mapping[str, str]]
) -> list[Mapping[str, str]]:
    return sorted(
        items,
        key=lambda item: participant_item_digest(
            participant_id, item["calibration_item_id"]
        ),
    )


def validate_response_fields(row: Mapping[str, str], context: str) -> list[str]:
    errors: list[str] = []
    if (row.get("response_status") or "").strip() != "completed":
        errors.append(f"{context} is not marked completed")
    if (row.get("missing_reason_code") or "").strip():
        errors.append(f"{context} has a missing-reason code despite completion")
    if (row.get("evidence_support_label") or "").strip() not in EVIDENCE_LABELS:
        errors.append(f"{context} has an invalid evidence-support label")
    if not (row.get("evidence_support_reason") or "").strip():
        errors.append(f"{context} lacks an evidence-support reason")
    if (row.get("comparability_label") or "").strip() not in COMPARABILITY_LABELS:
        errors.append(f"{context} has an invalid comparability label")
    if not (row.get("comparability_reason") or "").strip():
        errors.append(f"{context} lacks a comparability reason")
    completed = (row.get("completed_utc") or "").strip()
    if not validate_completed_utc(completed):
        errors.append(f"{context} has an invalid UTC completion timestamp")
    return errors


def discover_completed_packets(paths: Sequence[Path]) -> list[Path]:
    discovered: list[Path] = []
    for path in paths:
        if path.is_file():
            discovered.append(path)
        elif path.is_dir():
            discovered.extend(
                candidate
                for candidate in path.rglob("*.csv")
                if candidate.is_file()
            )
        else:
            raise ValueError(f"completed packet input does not exist: {path}")
    unique = sorted({path.resolve() for path in discovered})
    if not unique:
        raise ValueError("no completed calibration packet CSV was found")
    return unique


def validate_completed_packet(
    path: Path,
    items: Sequence[Mapping[str, str]],
    participant: Mapping[str, str],
) -> tuple[int, list[dict[str, str]]]:
    header, rows = read_csv(path)
    if header != PACKET_HEADER:
        raise ValueError(
            f"{path} is not an exact calibration packet; test/other responses "
            "must not be mixed"
        )
    if len(rows) != CALIBRATION_ITEM_COUNT:
        raise ValueError(f"{path} does not contain exactly ten item responses")
    participant_id = participant["participant_id"].strip()
    participant_role = participant["role"].strip().lower()
    participant_arm = participant["assigned_arm"].strip().upper()
    rounds = {(row.get("calibration_round") or "").strip() for row in rows}
    if len(rounds) != 1 or next(iter(rounds)) not in {"1", "2"}:
        raise ValueError(f"{path} does not contain one valid calibration round")
    calibration_round = int(next(iter(rounds)))
    set_hash = calibration_set_sha256(items)
    ordered = expected_order(participant_id, items)
    item_ids = [(row.get("calibration_item_id") or "").strip() for row in rows]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError(f"{path} reuses a calibration item ID")
    if set(item_ids) != {item["calibration_item_id"] for item in items}:
        raise ValueError(f"{path} does not exactly cover the frozen ten items")
    errors: list[str] = []
    for display_order, (row, item) in enumerate(zip(rows, ordered), start=1):
        context = f"{path} row {display_order + 1}"
        expected_fixed = {
            "calibration_response_id": calibration_response_id(
                participant_id,
                calibration_round,
                item["calibration_item_id"],
            ),
            "calibration_round": str(calibration_round),
            "participant_id": participant_id,
            "participant_role": participant_role,
            "assigned_arm": participant_arm,
            "display_order": str(display_order),
            "packet_version": CALIBRATION_VERSION,
            "calibration_set_sha256": set_hash,
        }
        for packet_field, item_field in PACKET_ITEM_MAP.items():
            expected_fixed[packet_field] = item[item_field]
        for field, expected in expected_fixed.items():
            if (row.get(field) or "") != expected:
                errors.append(f"{context} changed immutable field {field}")
        errors.extend(validate_response_fields(row, context))
    response_ids = [row["calibration_response_id"] for row in rows]
    if len(response_ids) != len(set(response_ids)):
        errors.append(f"{path} has duplicate calibration response IDs")
    if errors:
        raise ValueError("\n- " + "\n- ".join(errors))
    return calibration_round, rows


def ledger_row_from_packet(
    row: Mapping[str, str],
    key: Mapping[str, str],
    passed: bool,
) -> dict[str, str]:
    evidence_correct, comparability_correct, feedback = expected_feedback(row, key)
    output = {field: "" for field in CALIBRATION_RESPONSE_HEADER}
    for field in (
        "calibration_response_id",
        "calibration_round",
        "calibration_item_id",
        "calibration_source_key",
        "participant_id",
        "participant_role",
        "assigned_arm",
        "display_order",
        "packet_version",
        "calibration_set_sha256",
        "item_record_sha256",
        "claim_text",
        "source_locator",
        "response_status",
        "missing_reason_code",
        "evidence_support_label",
        "evidence_support_reason",
        "comparability_label",
        "comparability_reason",
        "completed_utc",
    ):
        output[field] = (row.get(field) or "")
    output["instructor_feedback_code"] = feedback
    output["evidence_support_correct"] = str(evidence_correct).lower()
    output["comparability_correct"] = str(comparability_correct).lower()
    output["passed_for_live_assignment"] = str(passed).lower()
    return output


def score_packet_rows(
    rows: Sequence[Mapping[str, str]], key_by_id: Mapping[str, Mapping[str, str]]
) -> tuple[int, int, bool]:
    evidence_correct = 0
    comparability_correct = 0
    for row in rows:
        key = key_by_id[row["calibration_item_id"]]
        evidence, comparability, _feedback = expected_feedback(row, key)
        evidence_correct += int(evidence)
        comparability_correct += int(comparability)
    passed = (
        evidence_correct >= MINIMUM_CORRECT_PER_DIMENSION
        and comparability_correct >= MINIMUM_CORRECT_PER_DIMENSION
    )
    return evidence_correct, comparability_correct, passed


def validate_ledger_round(
    participant: Mapping[str, str],
    calibration_round: int,
    rows: Sequence[Mapping[str, str]],
    items: Sequence[Mapping[str, str]],
    key_by_id: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    participant_id = participant["participant_id"].strip()
    role = participant["role"].strip().lower()
    arm = participant["assigned_arm"].strip().upper()
    if len(rows) != 10:
        return None, [
            f"{participant_id} round {calibration_round} has {len(rows)} ledger rows"
        ]
    ordered_items = expected_order(participant_id, items)
    ordered_rows = sorted(rows, key=lambda row: int(row.get("display_order") or "0"))
    set_hash = calibration_set_sha256(items)
    for display_order, (row, item) in enumerate(
        zip(ordered_rows, ordered_items), start=1
    ):
        context = f"ledger {participant_id} round {calibration_round} item {display_order}"
        expected = {
            "calibration_response_id": calibration_response_id(
                participant_id, calibration_round, item["calibration_item_id"]
            ),
            "calibration_round": str(calibration_round),
            "calibration_item_id": item["calibration_item_id"],
            "calibration_source_key": item["calibration_source_key"],
            "participant_id": participant_id,
            "participant_role": role,
            "assigned_arm": arm,
            "display_order": str(display_order),
            "packet_version": CALIBRATION_VERSION,
            "calibration_set_sha256": set_hash,
            "item_record_sha256": item["item_record_sha256"],
            "claim_text": item["audited_claim"],
            "source_locator": item["source_locator"],
        }
        for field, value in expected.items():
            if (row.get(field) or "") != value:
                errors.append(f"{context} changed immutable field {field}")
        errors.extend(validate_response_fields(row, context))
        key = key_by_id[item["calibration_item_id"]]
        evidence, comparability, feedback = expected_feedback(row, key)
        derived = {
            "instructor_feedback_code": feedback,
            "evidence_support_correct": str(evidence).lower(),
            "comparability_correct": str(comparability).lower(),
        }
        for field, value in derived.items():
            if (row.get(field) or "") != value:
                errors.append(f"{context} has invalid derived field {field}")
    evidence_correct, comparability_correct, passed = score_packet_rows(
        ordered_rows, key_by_id
    )
    expected_pass = str(passed).lower()
    if any(
        (row.get("passed_for_live_assignment") or "") != expected_pass
        for row in ordered_rows
    ):
        errors.append(
            f"{participant_id} round {calibration_round} has inconsistent pass flags"
        )
    detail: dict[str, Any] = {
        "round": calibration_round,
        "evidence_correct": evidence_correct,
        "comparability_correct": comparability_correct,
        "evidence_accuracy": evidence_correct / 10,
        "comparability_accuracy": comparability_correct / 10,
        "passed": passed,
        "outcome": (
            "passed"
            if passed
            else (
                "retraining_required_round_2"
                if calibration_round == 1
                else "exclude_before_test"
            )
        ),
        "item_results": [
            {
                "calibration_response_id": row["calibration_response_id"],
                "calibration_item_id": row["calibration_item_id"],
                "evidence_support_correct": (
                    row["evidence_support_correct"] == "true"
                ),
                "comparability_correct": (
                    row["comparability_correct"] == "true"
                ),
            }
            for row in ordered_rows
        ],
    }
    return detail, errors


def reconstruct_ledger_state(
    ledger_rows: Sequence[Mapping[str, str]],
    public_rows: Sequence[Mapping[str, str]],
    items: Sequence[Mapping[str, str]],
    key: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]], list[str]]:
    errors: list[str] = []
    public_by_id = {
        (row.get("participant_id") or "").strip(): row for row in public_rows
    }
    key_by_id = {row["calibration_item_id"]: row for row in key}
    response_ids = [
        (row.get("calibration_response_id") or "").strip() for row in ledger_rows
    ]
    if "" in response_ids or len(response_ids) != len(set(response_ids)):
        errors.append("calibration ledger response IDs are empty or duplicated")
    grouped: dict[tuple[str, int], list[Mapping[str, str]]] = defaultdict(list)
    for index, row in enumerate(ledger_rows, start=2):
        participant_id = (row.get("participant_id") or "").strip()
        if participant_id not in public_by_id:
            errors.append(f"calibration ledger row {index} has unknown participant")
            continue
        try:
            calibration_round = int((row.get("calibration_round") or ""))
        except ValueError:
            errors.append(f"calibration ledger row {index} has invalid round")
            continue
        if calibration_round not in {1, 2}:
            errors.append(f"calibration ledger row {index} has invalid round")
            continue
        grouped[(participant_id, calibration_round)].append(row)

    states: dict[str, str] = {}
    details: dict[str, list[dict[str, Any]]] = {}
    for participant_id, participant in public_by_id.items():
        participant_rounds: list[dict[str, Any]] = []
        round_numbers = sorted(
            round_number
            for pid, round_number in grouped
            if pid == participant_id
        )
        if round_numbers not in ([], [1], [1, 2]):
            errors.append(f"{participant_id} has an invalid calibration round sequence")
        for round_number in round_numbers:
            detail, round_errors = validate_ledger_round(
                participant,
                round_number,
                grouped[(participant_id, round_number)],
                items,
                key_by_id,
            )
            errors.extend(round_errors)
            if detail is not None:
                participant_rounds.append(detail)
        if not participant_rounds:
            status = "awaiting_calibration"
        elif participant_rounds[0]["passed"]:
            status = "passed_round_1"
            if len(participant_rounds) > 1:
                errors.append(f"{participant_id} received round 2 after passing round 1")
        elif len(participant_rounds) == 1:
            status = "retraining_required_round_2"
        elif participant_rounds[1]["passed"]:
            status = "passed_round_2"
        else:
            status = "exclude_before_test"
        states[participant_id] = status
        details[participant_id] = participant_rounds
    return states, details, errors


def update_public_roster(
    rows: Sequence[Mapping[str, str]], states: Mapping[str, str]
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for source in rows:
        row = {field: (source.get(field) or "") for field in PUBLIC_ROSTER_HEADER}
        participant_id = row["participant_id"].strip()
        status = states[participant_id]
        row["calibration_status"] = status
        row["included_in_primary_analysis"] = (
            "pending_test_completion" if status in PASS_STATUSES else "false"
        )
        output.append(row)
    return output


def label_distribution(
    key: Sequence[Mapping[str, str]]
) -> dict[str, dict[str, int]]:
    return {
        "evidence_support": dict(
            sorted(Counter(row["evidence_support_label"] for row in key).items())
        ),
        "comparability": dict(
            sorted(Counter(row["comparability_label"] for row in key).items())
        ),
    }


def build_summary(
    *,
    items: Sequence[Mapping[str, str]],
    key: Sequence[Mapping[str, str]],
    public_rows: Sequence[Mapping[str, str]],
    states: Mapping[str, str],
    details: Mapping[str, Sequence[Mapping[str, Any]]],
    packet_hashes: Mapping[tuple[str, int], str],
    response_bytes: bytes,
    public_bytes: bytes,
    items_path: Path,
    key_path: Path,
    materials_path: Path,
) -> dict[str, Any]:
    participants: list[dict[str, Any]] = []
    for row in sorted(public_rows, key=lambda value: value["participant_id"]):
        participant_id = row["participant_id"]
        rounds: list[dict[str, Any]] = []
        for detail in details.get(participant_id, []):
            round_record = dict(detail)
            packet_hash = packet_hashes.get(
                (participant_id, int(detail["round"])), ""
            )
            if packet_hash:
                round_record["completed_packet_sha256"] = packet_hash
            rounds.append(round_record)
        participants.append(
            {
                "participant_id": participant_id,
                "role": row["role"].strip().lower(),
                "assigned_arm": row["assigned_arm"].strip().upper(),
                "final_status": states[participant_id],
                "rounds": rounds,
            }
        )
    counts = Counter(states.values())
    release_eligible = (
        len(public_rows) == 29
        and len(states) == 29
        and all(status in PASS_STATUSES for status in states.values())
    )
    if not any(details.values()):
        status = "AWAITING_FROZEN_CALIBRATION_RESPONSES"
    elif release_eligible:
        status = "FROZEN_CALIBRATION_PASSED_BEFORE_TEST"
    elif counts.get("exclude_before_test", 0):
        status = "CALIBRATION_EXCLUSIONS_REQUIRE_PRETEST_ROSTER_ACTION"
    else:
        status = "FROZEN_CALIBRATION_IN_PROGRESS"
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": status,
        "calibration_version": CALIBRATION_VERSION,
        "calibration_set_sha256": calibration_set_sha256(items),
        "calibration_items_sha256": sha256_file(items_path),
        "calibration_answer_key_sha256": sha256_file(key_path),
        "calibration_materials_sha256": sha256_file(materials_path),
        "answer_key_status": ANSWER_KEY_STATUS,
        "instructor_constructed_key_is_test_gold": False,
        "prior_unitemized_pass_claims_recognized": False,
        "item_count": CALIBRATION_ITEM_COUNT,
        "calibration_item_ids": sorted(
            row["calibration_item_id"] for row in items
        ),
        "minimum_correct_per_dimension": MINIMUM_CORRECT_PER_DIMENSION,
        "maximum_retraining_attempts": MAXIMUM_RETRAINING_ATTEMPTS,
        "label_distribution": label_distribution(key),
        "response_rows": sum(
            len(record["item_results"])
            for records in details.values()
            for record in records
        ),
        "calibration_responses_sha256": bytes_sha256(response_bytes),
        "public_roster_sha256": bytes_sha256(public_bytes),
        "participant_status_counts": dict(sorted(counts.items())),
        "participants": participants,
        "test_packet_release_eligible": release_eligible,
        "test_response_files_read": 0,
        "test_labels_generated": 0,
    }


def summary_packet_hashes(summary: Mapping[str, Any]) -> dict[tuple[str, int], str]:
    output: dict[tuple[str, int], str] = {}
    participants = summary.get("participants", [])
    if not isinstance(participants, list):
        return output
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        participant_id = str(participant.get("participant_id", ""))
        rounds = participant.get("rounds", [])
        if not isinstance(rounds, list):
            continue
        for record in rounds:
            if not isinstance(record, dict):
                continue
            digest = str(record.get("completed_packet_sha256", ""))
            try:
                round_number = int(record.get("round"))
            except (TypeError, ValueError):
                continue
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                output[(participant_id, round_number)] = digest
    return output


def validate_summary_item_records(
    summary: Mapping[str, Any],
    states: Mapping[str, str],
    details: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    records = summary.get("participants")
    if not isinstance(records, list):
        return ["calibration summary participants is not a list"]
    by_id: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            errors.append("calibration summary participant record is not an object")
            continue
        participant_id = str(record.get("participant_id", ""))
        if not participant_id or participant_id in by_id:
            errors.append("calibration summary participant IDs are empty or duplicated")
            continue
        by_id[participant_id] = record
    if set(by_id) != set(states):
        errors.append("calibration summary does not exactly cover public participants")
        return errors
    for participant_id, state in states.items():
        record = by_id[participant_id]
        if record.get("final_status") != state:
            errors.append(f"calibration summary status mismatch for {participant_id}")
        actual_rounds = record.get("rounds")
        expected_rounds = details.get(participant_id, [])
        if not isinstance(actual_rounds, list) or len(actual_rounds) != len(
            expected_rounds
        ):
            errors.append(f"calibration summary round count mismatch for {participant_id}")
            continue
        for actual, expected in zip(actual_rounds, expected_rounds):
            for field in (
                "round",
                "evidence_correct",
                "comparability_correct",
                "evidence_accuracy",
                "comparability_accuracy",
                "passed",
                "outcome",
                "item_results",
            ):
                if actual.get(field) != expected.get(field):
                    errors.append(
                        f"calibration summary {field} mismatch for {participant_id}"
                    )
    return errors


def validate_release_gate(
    public_rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, Any],
    responses_sha256: str,
) -> list[str]:
    errors = validate_public_roster_rows(public_rows, allow_empty=False)
    if any(
        (row.get("calibration_status") or "").strip() not in PASS_STATUSES
        for row in public_rows
    ):
        errors.append("every public-roster participant must pass calibration")
    if summary.get("status") != "FROZEN_CALIBRATION_PASSED_BEFORE_TEST":
        errors.append("calibration summary is not in the passed pretest state")
    if summary.get("test_packet_release_eligible") is not True:
        errors.append("calibration summary does not authorize test packet release")
    if summary.get("calibration_responses_sha256") != responses_sha256:
        errors.append("calibration response ledger hash differs from summary")
    if summary.get("prior_unitemized_pass_claims_recognized") is not False:
        errors.append("summary improperly recognizes unitemized prior pass claims")
    records = summary.get("participants")
    if not isinstance(records, list) or len(records) != 29:
        errors.append("calibration summary must contain 29 participant records")
        return errors
    by_id = {
        str(record.get("participant_id", "")): record
        for record in records
        if isinstance(record, dict)
    }
    public_ids = {row["participant_id"].strip() for row in public_rows}
    if set(by_id) != public_ids:
        errors.append("public roster and calibration summary participants differ")
        return errors
    public_by_id = {
        row["participant_id"].strip(): row for row in public_rows
    }
    frozen_item_ids = set(summary.get("calibration_item_ids", []))
    if len(frozen_item_ids) != CALIBRATION_ITEM_COUNT:
        errors.append("calibration summary lacks the frozen ten item IDs")
    for participant_id, record in by_id.items():
        public = public_by_id[participant_id]
        if (
            record.get("role") != public["role"].strip().lower()
            or record.get("assigned_arm")
            != public["assigned_arm"].strip().upper()
        ):
            errors.append(f"{participant_id} summary role/arm differs from roster")
        if record.get("final_status") not in PASS_STATUSES:
            errors.append(f"{participant_id} lacks a passing final summary status")
            continue
        rounds = record.get("rounds")
        if not isinstance(rounds, list) or not rounds:
            errors.append(f"{participant_id} lacks scored calibration rounds")
            continue
        final_round = rounds[-1]
        item_results = final_round.get("item_results")
        if not isinstance(item_results, list) or len(item_results) != 10:
            errors.append(f"{participant_id} lacks ten final item-level results")
            continue
        item_ids = {
            str(item.get("calibration_item_id", ""))
            for item in item_results
            if isinstance(item, dict)
        }
        response_ids = {
            str(item.get("calibration_response_id", ""))
            for item in item_results
            if isinstance(item, dict)
        }
        if len(item_ids) != 10 or len(response_ids) != 10 or "" in response_ids:
            errors.append(f"{participant_id} final item IDs are not independent")
        if item_ids != frozen_item_ids:
            errors.append(f"{participant_id} final item set is not the frozen set")
        if (
            final_round.get("evidence_correct", 0)
            < MINIMUM_CORRECT_PER_DIMENSION
            or final_round.get("comparability_correct", 0)
            < MINIMUM_CORRECT_PER_DIMENSION
        ):
            errors.append(f"{participant_id} fails a per-dimension threshold")
    return errors


def assert_calibration_release(
    public_roster_path: Path,
    summary_path: Path,
    responses_path: Path,
    *,
    items_path: Path = PACKAGE / "calibration_items.csv",
    key_path: Path = PACKAGE / "calibration_answer_key.csv",
    materials_path: Path = PACKAGE / "calibration_materials.md",
) -> list[dict[str, str]]:
    public_rows = read_public_roster(public_roster_path, allow_empty=False)
    response_header, ledger_rows = read_csv(responses_path)
    if response_header != CALIBRATION_RESPONSE_HEADER:
        raise ValueError("calibration response ledger has the wrong schema")
    items = read_calibration_items(items_path)
    key = read_calibration_key(key_path, items)
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read calibration summary: {exc}") from exc
    release, errors = validate_calibration_state(
        items=items,
        key=key,
        ledger_rows=ledger_rows,
        public_rows=public_rows,
        summary=summary,
        response_sha256=sha256_file(responses_path),
        public_sha256=sha256_file(public_roster_path),
        items_sha256=sha256_file(items_path),
        key_sha256=sha256_file(key_path),
        materials_sha256=sha256_file(materials_path),
    )
    if not release:
        errors.append(
            "real item-level calibration ledger does not authorize release"
        )
    if errors:
        raise ValueError(
            "test packet release blocked by calibration gate:\n- "
            + "\n- ".join(errors)
        )
    return public_rows


def validate_calibration_state(
    *,
    items: Sequence[Mapping[str, str]],
    key: Sequence[Mapping[str, str]],
    ledger_rows: Sequence[Mapping[str, str]],
    public_rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, Any],
    response_sha256: str,
    public_sha256: str,
    items_sha256: str,
    key_sha256: str,
    materials_sha256: str,
) -> tuple[bool, list[str]]:
    errors = validate_public_roster_rows(public_rows, allow_empty=True)
    fixed_expectations = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "calibration_version": CALIBRATION_VERSION,
        "calibration_set_sha256": calibration_set_sha256(items),
        "calibration_items_sha256": items_sha256,
        "calibration_answer_key_sha256": key_sha256,
        "calibration_materials_sha256": materials_sha256,
        "answer_key_status": ANSWER_KEY_STATUS,
        "instructor_constructed_key_is_test_gold": False,
        "prior_unitemized_pass_claims_recognized": False,
        "item_count": 10,
        "minimum_correct_per_dimension": 8,
        "maximum_retraining_attempts": 1,
        "label_distribution": label_distribution(key),
        "calibration_responses_sha256": response_sha256,
        "public_roster_sha256": public_sha256,
        "test_response_files_read": 0,
        "test_labels_generated": 0,
    }
    for field, expected in fixed_expectations.items():
        if summary.get(field) != expected:
            errors.append(f"calibration summary field {field} is inconsistent")
    if summary.get("response_rows") != len(ledger_rows):
        errors.append("calibration summary response row count is inconsistent")
    if not public_rows:
        if ledger_rows:
            errors.append("calibration ledger cannot have rows without public roster")
        if summary.get("participants") != []:
            errors.append("empty public roster requires empty summary participants")
        if summary.get("status") != "AWAITING_FROZEN_CALIBRATION_RESPONSES":
            errors.append("empty calibration state has the wrong summary status")
        if summary.get("test_packet_release_eligible") is not False:
            errors.append("empty calibration state authorizes test packet release")
        return False, errors

    states, details, ledger_errors = reconstruct_ledger_state(
        ledger_rows, public_rows, items, key
    )
    errors.extend(ledger_errors)
    for row in public_rows:
        participant_id = row["participant_id"].strip()
        actual = (row.get("calibration_status") or "").strip()
        expected = states.get(participant_id, "")
        if actual in {"", "awaiting_calibration"} and expected == "awaiting_calibration":
            continue
        if actual != expected:
            errors.append(f"public calibration status mismatch for {participant_id}")
    errors.extend(validate_summary_item_records(summary, states, details))
    counts = Counter(states.values())
    expected_release_from_ledger = (
        len(public_rows) == 29
        and len(states) == 29
        and all(status in PASS_STATUSES for status in states.values())
    )
    if not any(details.values()):
        expected_summary_status = "AWAITING_FROZEN_CALIBRATION_RESPONSES"
    elif expected_release_from_ledger:
        expected_summary_status = "FROZEN_CALIBRATION_PASSED_BEFORE_TEST"
    elif counts.get("exclude_before_test", 0):
        expected_summary_status = (
            "CALIBRATION_EXCLUSIONS_REQUIRE_PRETEST_ROSTER_ACTION"
        )
    else:
        expected_summary_status = "FROZEN_CALIBRATION_IN_PROGRESS"
    if summary.get("status") != expected_summary_status:
        errors.append("calibration summary status is inconsistent with the ledger")
    if summary.get("participant_status_counts") != dict(sorted(counts.items())):
        errors.append(
            "calibration summary participant-status counts are inconsistent"
        )
    if summary.get("calibration_item_ids") != sorted(
        row["calibration_item_id"] for row in items
    ):
        errors.append("calibration summary item IDs are inconsistent")
    final_response_ids = [
        str(item.get("calibration_response_id", ""))
        for participant_id in sorted(details)
        if details[participant_id]
        for item in details[participant_id][-1]["item_results"]
    ]
    if expected_release_from_ledger and (
        len(final_response_ids) != 29 * CALIBRATION_ITEM_COUNT
        or "" in final_response_ids
        or len(final_response_ids) != len(set(final_response_ids))
    ):
        errors.append(
            "release requires 29 independent ten-item final-round ledger records"
        )
    summary_records = {
        str(record.get("participant_id", "")): record
        for record in summary.get("participants", [])
        if isinstance(record, dict)
    }
    for row in public_rows:
        participant_id = row["participant_id"].strip()
        record = summary_records.get(participant_id)
        if record is None:
            continue
        if (
            record.get("role") != row["role"].strip().lower()
            or record.get("assigned_arm") != row["assigned_arm"].strip().upper()
        ):
            errors.append(f"calibration summary role/arm mismatch for {participant_id}")
    release = (
        not errors
        and expected_release_from_ledger
    )
    if summary.get("test_packet_release_eligible") is not release:
        errors.append("calibration summary release flag is inconsistent")
    if release:
        errors.extend(validate_release_gate(public_rows, summary, response_sha256))
    return release, errors


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(text, encoding="utf-8")
    staging.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--completed-packets",
        type=Path,
        nargs="+",
        help="completed calibration CSV files or directories; never test responses",
    )
    parser.add_argument(
        "--items", type=Path, default=PACKAGE / "calibration_items.csv"
    )
    parser.add_argument(
        "--answer-key", type=Path, default=PACKAGE / "calibration_answer_key.csv"
    )
    parser.add_argument(
        "--materials", type=Path, default=PACKAGE / "calibration_materials.md"
    )
    parser.add_argument(
        "--responses", type=Path, default=PACKAGE / "calibration_responses.csv"
    )
    parser.add_argument(
        "--summary", type=Path, default=PACKAGE / "calibration_summary.json"
    )
    parser.add_argument(
        "--public-roster",
        type=Path,
        default=PACKAGE / "participant_metadata_public_template.csv",
        help="exact non-PII public roster; private roster input is intentionally absent",
    )
    parser.add_argument("--responses-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--public-roster-output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def run_scoring(
    *,
    completed_paths: Sequence[Path],
    items_path: Path,
    key_path: Path,
    materials_path: Path,
    responses_path: Path,
    summary_path: Path,
    public_roster_path: Path,
    responses_output: Path,
    summary_output: Path,
    public_roster_output: Path,
) -> dict[str, Any]:
    items = read_calibration_items(items_path)
    key = read_calibration_key(key_path, items)
    key_by_id = {row["calibration_item_id"]: row for row in key}
    public_rows = read_public_roster(public_roster_path, allow_empty=False)
    public_by_id = {row["participant_id"].strip(): row for row in public_rows}

    response_header, existing_rows = read_csv(responses_path)
    if response_header != CALIBRATION_RESPONSE_HEADER:
        raise ValueError("calibration response ledger has the wrong schema")
    try:
        existing_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read existing calibration summary: {exc}") from exc

    existing_states, existing_details, existing_errors = reconstruct_ledger_state(
        existing_rows, public_rows, items, key
    )
    _existing_release, summary_errors = validate_calibration_state(
        items=items,
        key=key,
        ledger_rows=existing_rows,
        public_rows=public_rows,
        summary=existing_summary,
        response_sha256=sha256_file(responses_path),
        public_sha256=sha256_file(public_roster_path),
        items_sha256=sha256_file(items_path),
        key_sha256=sha256_file(key_path),
        materials_sha256=sha256_file(materials_path),
    )
    existing_errors.extend(summary_errors)
    if existing_errors:
        raise ValueError(
            "existing calibration ledger is invalid:\n- "
            + "\n- ".join(existing_errors)
        )
    for participant_id, expected in existing_states.items():
        actual = public_by_id[participant_id]["calibration_status"].strip()
        if actual in {"", "awaiting_calibration"} and expected == "awaiting_calibration":
            continue
        if actual != expected:
            raise ValueError(
                f"public roster status does not match ledger for {participant_id}"
            )

    packet_hashes = summary_packet_hashes(existing_summary)
    existing_pairs = {
        (row["participant_id"], int(row["calibration_round"]))
        for row in existing_rows
    }
    existing_response_ids = {
        row["calibration_response_id"] for row in existing_rows
    }
    packet_records: list[tuple[str, int, Path, list[dict[str, str]]]] = []
    incoming_pairs: set[tuple[str, int]] = set()
    incoming_response_ids: set[str] = set()
    for packet_path in discover_completed_packets(completed_paths):
        header, probe_rows = read_csv(packet_path)
        if header != PACKET_HEADER:
            raise ValueError(
                f"{packet_path} is not a calibration packet; test responses "
                "must never be supplied"
            )
        participant_ids = {
            (row.get("participant_id") or "").strip() for row in probe_rows
        }
        if len(participant_ids) != 1:
            raise ValueError(f"{packet_path} mixes participant IDs")
        participant_id = next(iter(participant_ids))
        participant = public_by_id.get(participant_id)
        if participant is None:
            raise ValueError(f"{packet_path} has a participant absent from public roster")
        calibration_round, rows = validate_completed_packet(
            packet_path, items, participant
        )
        pair = (participant_id, calibration_round)
        if pair in existing_pairs or pair in incoming_pairs:
            raise ValueError(f"duplicate participant/round submission: {pair}")
        ids = {row["calibration_response_id"] for row in rows}
        if ids & existing_response_ids or ids & incoming_response_ids:
            raise ValueError("calibration response IDs are not independent")
        incoming_response_ids.update(ids)
        incoming_pairs.add(pair)
        packet_records.append((participant_id, calibration_round, packet_path, rows))

    new_rows: list[dict[str, str]] = []
    for participant_id, calibration_round, packet_path, rows in packet_records:
        prior_status = existing_states[participant_id]
        if calibration_round == 1 and prior_status != "awaiting_calibration":
            raise ValueError(f"{participant_id} is not eligible for round 1")
        if (
            calibration_round == 2
            and prior_status != "retraining_required_round_2"
        ):
            raise ValueError(f"{participant_id} is not eligible for fixed round 2")
        _evidence, _comparability, passed = score_packet_rows(rows, key_by_id)
        for row in rows:
            new_rows.append(
                ledger_row_from_packet(
                    row, key_by_id[row["calibration_item_id"]], passed
                )
            )
        packet_hashes[(participant_id, calibration_round)] = sha256_file(packet_path)

    combined_rows = sorted(
        [*existing_rows, *new_rows],
        key=lambda row: (
            row["participant_id"],
            int(row["calibration_round"]),
            int(row["display_order"]),
        ),
    )
    states, details, errors = reconstruct_ledger_state(
        combined_rows, public_rows, items, key
    )
    if errors:
        raise ValueError("scored calibration state is invalid:\n- " + "\n- ".join(errors))
    updated_public = update_public_roster(public_rows, states)
    response_payload = csv_bytes(CALIBRATION_RESPONSE_HEADER, combined_rows)
    public_payload = csv_bytes(PUBLIC_ROSTER_HEADER, updated_public)
    summary = build_summary(
        items=items,
        key=key,
        public_rows=updated_public,
        states=states,
        details=details,
        packet_hashes=packet_hashes,
        response_bytes=response_payload,
        public_bytes=public_payload,
        items_path=items_path,
        key_path=key_path,
        materials_path=materials_path,
    )
    release, audit_errors = validate_calibration_state(
        items=items,
        key=key,
        ledger_rows=combined_rows,
        public_rows=updated_public,
        summary=summary,
        response_sha256=bytes_sha256(response_payload),
        public_sha256=bytes_sha256(public_payload),
        items_sha256=sha256_file(items_path),
        key_sha256=sha256_file(key_path),
        materials_sha256=sha256_file(materials_path),
    )
    if audit_errors:
        raise AssertionError(
            "post-score calibration audit failed:\n- " + "\n- ".join(audit_errors)
        )
    write_text_atomic(responses_output, response_payload.decode("utf-8"))
    write_text_atomic(public_roster_output, public_payload.decode("utf-8"))
    write_text_atomic(
        summary_output,
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return {
        "status": summary["status"],
        "new_response_rows": len(new_rows),
        "total_response_rows": len(combined_rows),
        "participant_status_counts": summary["participant_status_counts"],
        "test_packet_release_eligible": release,
        "test_response_files_read": 0,
        "test_labels_generated": 0,
        "responses_output": str(responses_output),
        "summary_output": str(summary_output),
        "public_roster_output": str(public_roster_output),
    }


def self_test() -> None:
    from build_calibration_packets import (
        PRIVATE_ROSTER_HEADER,
        anonymous_private_roster,
        build_packet_rows,
    )

    del PRIVATE_ROSTER_HEADER  # Imported to assert the self-test uses that roster shape.
    workspace = PACKAGE / ".calibration_score_selftest_workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    try:
        items_path = PACKAGE / "calibration_items.csv"
        key_path = PACKAGE / "calibration_answer_key.csv"
        materials_path = PACKAGE / "calibration_materials.md"
        items = read_calibration_items(items_path)
        key = read_calibration_key(key_path, items)
        key_by_id = {row["calibration_item_id"]: row for row in key}
        private = anonymous_private_roster()
        public: list[dict[str, str]] = []
        for source in private:
            row = {field: "" for field in PUBLIC_ROSTER_HEADER}
            row.update(
                {
                    "participant_id": source["participant_id"],
                    "role": source["role"],
                    "assigned_arm": source["assigned_arm"],
                    "calibration_status": "awaiting_calibration",
                    "replacement_status": "primary",
                    "included_in_primary_analysis": "false",
                }
            )
            public.append(row)
        public_path = workspace / "public.csv"
        responses_path = workspace / "responses.csv"
        summary_path = workspace / "summary.json"
        write_csv(public_path, PUBLIC_ROSTER_HEADER, public)
        write_csv(responses_path, CALIBRATION_RESPONSE_HEADER, [])
        empty_response_bytes = csv_bytes(CALIBRATION_RESPONSE_HEADER, [])
        empty_public_bytes = csv_bytes(PUBLIC_ROSTER_HEADER, public)
        empty_states = {row["participant_id"]: "awaiting_calibration" for row in public}
        empty_details = {row["participant_id"]: [] for row in public}
        empty_summary = build_summary(
            items=items,
            key=key,
            public_rows=public,
            states=empty_states,
            details=empty_details,
            packet_hashes={},
            response_bytes=empty_response_bytes,
            public_bytes=empty_public_bytes,
            items_path=items_path,
            key_path=key_path,
            materials_path=materials_path,
        )
        summary_path.write_text(
            json.dumps(empty_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        round1_dir = workspace / "round1"
        round1_dir.mkdir()
        failing_id = public[0]["participant_id"]
        for participant in public:
            packet_rows = build_packet_rows(participant, items, 1)
            for index, row in enumerate(packet_rows):
                answer = key_by_id[row["calibration_item_id"]]
                row["response_status"] = "completed"
                row["evidence_support_label"] = answer["evidence_support_label"]
                row["comparability_label"] = answer["comparability_label"]
                row["evidence_support_reason"] = "temporary self-test reason"
                row["comparability_reason"] = "temporary self-test reason"
                row["completed_utc"] = "2026-07-18T06:00:00Z"
                if participant["participant_id"] == failing_id and index < 3:
                    row["evidence_support_label"] = next(
                        label
                        for label in sorted(EVIDENCE_LABELS)
                        if label != answer["evidence_support_label"]
                    )
            write_csv(
                round1_dir / f"{participant['participant_id']}.csv",
                PACKET_HEADER,
                packet_rows,
            )
        result1 = run_scoring(
            completed_paths=[round1_dir],
            items_path=items_path,
            key_path=key_path,
            materials_path=materials_path,
            responses_path=responses_path,
            summary_path=summary_path,
            public_roster_path=public_path,
            responses_output=responses_path,
            summary_output=summary_path,
            public_roster_output=public_path,
        )
        if result1["participant_status_counts"] != {
            "passed_round_1": 28,
            "retraining_required_round_2": 1,
        }:
            raise AssertionError("round-1 scoring transition self-test failed")

        failing_public = next(
            row
            for row in read_public_roster(public_path, allow_empty=False)
            if row["participant_id"] == failing_id
        )
        exclusion_dir = workspace / "exclusion_branch"
        exclusion_dir.mkdir()
        exclusion_responses = exclusion_dir / "responses.csv"
        exclusion_summary = exclusion_dir / "summary.json"
        exclusion_public = exclusion_dir / "public.csv"
        shutil.copyfile(responses_path, exclusion_responses)
        shutil.copyfile(summary_path, exclusion_summary)
        shutil.copyfile(public_path, exclusion_public)
        failed_round2 = build_packet_rows(failing_public, items, 2)
        for index, row in enumerate(failed_round2):
            answer = key_by_id[row["calibration_item_id"]]
            row["response_status"] = "completed"
            row["evidence_support_label"] = answer["evidence_support_label"]
            row["comparability_label"] = answer["comparability_label"]
            row["evidence_support_reason"] = "temporary self-test reason"
            row["comparability_reason"] = "temporary self-test reason"
            row["completed_utc"] = "2026-07-18T06:30:00Z"
            if index < 3:
                row["comparability_label"] = next(
                    label
                    for label in sorted(COMPARABILITY_LABELS)
                    if label != answer["comparability_label"]
                )
        failed_packet = exclusion_dir / "failed_round2.csv"
        write_csv(failed_packet, PACKET_HEADER, failed_round2)
        exclusion_result = run_scoring(
            completed_paths=[failed_packet],
            items_path=items_path,
            key_path=key_path,
            materials_path=materials_path,
            responses_path=exclusion_responses,
            summary_path=exclusion_summary,
            public_roster_path=exclusion_public,
            responses_output=exclusion_responses,
            summary_output=exclusion_summary,
            public_roster_output=exclusion_public,
        )
        if exclusion_result["participant_status_counts"] != {
            "exclude_before_test": 1,
            "passed_round_1": 28,
        } or exclusion_result["test_packet_release_eligible"]:
            raise AssertionError("second-failure exclusion self-test failed")

        round2_dir = workspace / "round2"
        round2_dir.mkdir()
        packet_rows = build_packet_rows(failing_public, items, 2)
        for row in packet_rows:
            answer = key_by_id[row["calibration_item_id"]]
            row["response_status"] = "completed"
            row["evidence_support_label"] = answer["evidence_support_label"]
            row["comparability_label"] = answer["comparability_label"]
            row["evidence_support_reason"] = "temporary self-test reason"
            row["comparability_reason"] = "temporary self-test reason"
            row["completed_utc"] = "2026-07-18T07:00:00Z"
        write_csv(round2_dir / "round2.csv", PACKET_HEADER, packet_rows)
        result2 = run_scoring(
            completed_paths=[round2_dir],
            items_path=items_path,
            key_path=key_path,
            materials_path=materials_path,
            responses_path=responses_path,
            summary_path=summary_path,
            public_roster_path=public_path,
            responses_output=responses_path,
            summary_output=summary_path,
            public_roster_output=public_path,
        )
        if not result2["test_packet_release_eligible"]:
            raise AssertionError("round-2 pass did not open the calibration gate")
        assert_calibration_release(public_path, summary_path, responses_path)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print("self-test passed; temporary responses removed and no test data read")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.completed_packets:
        raise ValueError("--completed-packets is required unless --self-test is used")
    responses_output = args.responses_output or args.responses
    summary_output = args.summary_output or args.summary
    public_output = args.public_roster_output or args.public_roster
    result = run_scoring(
        completed_paths=args.completed_packets,
        items_path=args.items,
        key_path=args.answer_key,
        materials_path=args.materials,
        responses_path=args.responses,
        summary_path=args.summary,
        public_roster_path=args.public_roster,
        responses_output=responses_output,
        summary_output=summary_output,
        public_roster_output=public_output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
