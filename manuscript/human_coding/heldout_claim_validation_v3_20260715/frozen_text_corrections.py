#!/usr/bin/env python3
"""Validate and reverse the append-only pre-test text-correction ledger."""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping, Sequence

from freeze_human_sample import sampling_record_sha256
from prepare_candidate_pool import canonical_candidate_hash


SCHEMA_VERSION = "frozen-text-corrections-v1"
CORRECTION_HEADER = (
    "correction_id",
    "claim_id",
    "source_key",
    "source_locator",
    "source_url",
    "deterministic_field",
    "human_mirror_fields",
    "frozen_mirror_fields",
    "old_text_utf8_base64",
    "old_bytes_sha256",
    "new_text",
    "authoritative_source_evidence",
    "reason_code",
    "reason",
    "recorded_utc",
    "record_sha256",
)
DETERMINISTIC_TO_HUMAN_FIELDS = {
    "exact_quote": ("claim_text", "source_evidence_excerpt"),
    "context_before": ("context_before",),
    "context_after": ("context_after",),
    "source_section": ("source_section",),
}
DETERMINISTIC_TO_FROZEN_FIELDS = {
    "exact_quote": ("claim_text", "source_evidence_excerpt"),
    "context_before": ("context_before",),
    "context_after": ("context_after",),
    "source_section": ("source_section",),
}
AUTHORITATIVE_CLAIM_ID = "H3-065-14"
AUTHORITATIVE_SOURCE_KEY = "rrag015"
AUTHORITATIVE_SOURCE_URL = "https://arxiv.org/html/2506.04390v2"
AUTHORITATIVE_OLD_BYTES_SHA256 = (
    "b41006215a300cd984ab8651b50a1df9cf05c7c228271b47022e42082fc4101c"
)
AUTHORITATIVE_NEW_TEXT = (
    "The runtime reaches up to 1.8 × 10⁴ seconds, which is several orders "
    "of magnitude (∼ × 10³) higher than the runtime of the existing attack "
    "Poison, as reported in (Zou et al., 2024)."
)
AUTHORITATIVE_REASON_CODE = "AUTHORITATIVE_ARXIV_HTML_ALTTEXT_NORMALIZATION"
BYTE_ESCAPE_REASON_CODE = "C0_VISIBLE_ESCAPE_NO_SEMANTIC_INFERENCE"


@dataclass(frozen=True)
class ReversedCorrectionState:
    deterministic_rows: list[dict[str, str]]
    human_rows: list[dict[str, str]]
    frozen_rows: list[dict[str, str]]
    affected_claim_ids: tuple[str, ...]
    selected_claim_ids: tuple[str, ...]


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def correction_record_sha256(row: Mapping[str, str]) -> str:
    return canonical_json_sha256(
        {
            field: str(row.get(field, ""))
            for field in CORRECTION_HEADER
            if field != "record_sha256"
        }
    )


def serialize_csv(
    header: Sequence[str], rows: Sequence[Mapping[str, str]]
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=header, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def c0_codepoints(value: str) -> tuple[int, ...]:
    return tuple(sorted({ord(character) for character in value if ord(character) < 32}))


def visible_c0_escape(value: str) -> str:
    return "".join(
        f"⟦U+{ord(character):04X}⟧" if ord(character) < 32 else character
        for character in value
    )


def _split_fields(value: str) -> tuple[str, ...]:
    return tuple(field for field in value.split("|") if field)


def _decode_old_text(row: Mapping[str, str]) -> str:
    encoded = row.get("old_text_utf8_base64", "")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            f"{row.get('correction_id', '<unknown>')} has invalid old-text base64"
        ) from exc
    if hashlib.sha256(raw).hexdigest() != row.get("old_bytes_sha256"):
        raise ValueError(
            f"{row.get('correction_id', '<unknown>')} old-byte hash mismatch"
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{row.get('correction_id', '<unknown>')} old text is not UTF-8"
        ) from exc


def validate_and_reverse_corrections(
    correction_rows: Sequence[Mapping[str, str]],
    deterministic_rows: Sequence[Mapping[str, str]],
    human_rows: Sequence[Mapping[str, str]],
    frozen_rows: Sequence[Mapping[str, str]],
) -> ReversedCorrectionState:
    if not correction_rows:
        raise ValueError("frozen text-correction ledger must not be empty")
    deterministic_current = [dict(row) for row in deterministic_rows]
    human_current = [dict(row) for row in human_rows]
    frozen_current = [dict(row) for row in frozen_rows]
    deterministic_old = deepcopy(deterministic_current)
    human_old = deepcopy(human_current)
    frozen_old = deepcopy(frozen_current)

    deterministic_by_id = {
        row["candidate_claim_id"]: row for row in deterministic_current
    }
    deterministic_old_by_id = {
        row["candidate_claim_id"]: row for row in deterministic_old
    }
    human_by_id = {row["candidate_claim_id"]: row for row in human_current}
    human_old_by_id = {row["candidate_claim_id"]: row for row in human_old}
    frozen_by_id = {row["claim_id"]: row for row in frozen_current}
    frozen_old_by_id = {row["claim_id"]: row for row in frozen_old}
    if len(deterministic_by_id) != len(deterministic_current):
        raise ValueError("deterministic candidates contain duplicate IDs")
    if len(human_by_id) != len(human_current):
        raise ValueError("human-screened candidates contain duplicate IDs")
    if len(frozen_by_id) != len(frozen_current):
        raise ValueError("frozen claims contain duplicate IDs")

    correction_ids: set[str] = set()
    corrected_fields: set[tuple[str, str]] = set()
    affected_ids: set[str] = set()
    selected_ids: set[str] = set()
    for row_number, value in enumerate(correction_rows, start=2):
        row = {field: str(value.get(field, "")) for field in CORRECTION_HEADER}
        correction_id = row["correction_id"]
        claim_id = row["claim_id"]
        field = row["deterministic_field"]
        if not correction_id or correction_id in correction_ids:
            raise ValueError(
                f"frozen text-correction row {row_number} has a duplicate/blank ID"
            )
        correction_ids.add(correction_id)
        if row["record_sha256"] != correction_record_sha256(row):
            raise ValueError(f"{correction_id} has an invalid record hash")
        if field not in DETERMINISTIC_TO_HUMAN_FIELDS:
            raise ValueError(f"{correction_id} names an unauthorized field")
        if (claim_id, field) in corrected_fields:
            raise ValueError(f"{correction_id} duplicates a corrected field")
        corrected_fields.add((claim_id, field))
        deterministic = deterministic_by_id.get(claim_id)
        old_deterministic = deterministic_old_by_id.get(claim_id)
        human = human_by_id.get(claim_id)
        old_human = human_old_by_id.get(claim_id)
        if (
            deterministic is None
            or old_deterministic is None
            or human is None
            or old_human is None
        ):
            raise ValueError(f"{correction_id} references an unknown candidate")
        expected_source_url = (
            AUTHORITATIVE_SOURCE_URL
            if claim_id == AUTHORITATIVE_CLAIM_ID
            else deterministic["source_url_or_doi"]
        )
        if (
            row["source_key"] != deterministic["source_key"]
            or row["source_url"] != expected_source_url
        ):
            raise ValueError(f"{correction_id} has stale source provenance")
        expected_human_fields = DETERMINISTIC_TO_HUMAN_FIELDS[field]
        expected_frozen_fields = (
            DETERMINISTIC_TO_FROZEN_FIELDS[field]
            if claim_id in frozen_by_id
            else ()
        )
        if _split_fields(row["human_mirror_fields"]) != expected_human_fields:
            raise ValueError(f"{correction_id} has stale human mirror fields")
        if _split_fields(row["frozen_mirror_fields"]) != expected_frozen_fields:
            raise ValueError(f"{correction_id} has stale frozen mirror fields")
        old_text = _decode_old_text(row)
        if not c0_codepoints(old_text):
            raise ValueError(f"{correction_id} old text contains no C0 byte")
        if c0_codepoints(row["new_text"]):
            raise ValueError(f"{correction_id} new text still contains C0")
        if old_text == row["new_text"]:
            raise ValueError(f"{correction_id} does not change text")
        if deterministic[field] != row["new_text"]:
            raise ValueError(f"{correction_id} does not match current deterministic text")
        old_deterministic[field] = old_text
        for mirror_field in expected_human_fields:
            if human[mirror_field] != row["new_text"]:
                raise ValueError(f"{correction_id} has a stale human mirror")
            old_human[mirror_field] = old_text
        if claim_id in frozen_by_id:
            selected_ids.add(claim_id)
            frozen = frozen_by_id[claim_id]
            old_frozen = frozen_old_by_id[claim_id]
            for mirror_field in expected_frozen_fields:
                if frozen[mirror_field] != row["new_text"]:
                    raise ValueError(f"{correction_id} has a stale frozen mirror")
                old_frozen[mirror_field] = old_text
        if claim_id == AUTHORITATIVE_CLAIM_ID:
            if (
                row["source_key"] != AUTHORITATIVE_SOURCE_KEY
                or row["source_url"] != AUTHORITATIVE_SOURCE_URL
                or row["new_text"] != AUTHORITATIVE_NEW_TEXT
                or row["old_bytes_sha256"]
                != AUTHORITATIVE_OLD_BYTES_SHA256
                or row["reason_code"] != AUTHORITATIVE_REASON_CODE
                or row["source_locator"] != "PDF p18, Table 8 caption"
                or "1.8\\times 10^{4}"
                not in row["authoritative_source_evidence"]
                or "\\left(\\sim\\times 10^{3}\\right)"
                not in row["authoritative_source_evidence"]
                or field != "exact_quote"
            ):
                raise ValueError("authoritative H3-065-14 correction is not exact")
        elif (
            row["reason_code"] != BYTE_ESCAPE_REASON_CODE
            or row["new_text"] != visible_c0_escape(old_text)
        ):
            raise ValueError(
                f"{correction_id} is not a reversible no-inference C0 escape"
            )
        affected_ids.add(claim_id)

    if AUTHORITATIVE_CLAIM_ID not in affected_ids:
        raise ValueError("authoritative H3-065-14 correction is missing")
    if tuple(sorted(correction_ids)) != tuple(
        f"FTC-20260718-{index:03d}"
        for index in range(1, len(correction_rows) + 1)
    ):
        raise ValueError("frozen text-correction IDs are not contiguous")

    for row in deterministic_current:
        if row["candidate_record_sha256"] != canonical_candidate_hash(row):
            raise ValueError(
                f"{row['candidate_claim_id']} current candidate hash is invalid"
            )
    for claim_id in affected_ids:
        old = deterministic_old_by_id[claim_id]
        old["candidate_record_sha256"] = canonical_candidate_hash(old)

    human_old_by_id = {row["candidate_claim_id"]: row for row in human_old}
    deterministic_old_by_id = {
        row["candidate_claim_id"]: row for row in deterministic_old
    }
    for claim_id in selected_ids:
        frozen = frozen_by_id[claim_id]
        expected_current_sampling_hash = sampling_record_sha256(
            deterministic_by_id[claim_id],
            human_by_id[claim_id],
            frozen["coordinator_only_primary_stratum"],
        )
        if frozen["sampling_record_sha256"] != expected_current_sampling_hash:
            raise ValueError(f"{claim_id} current sampling-record hash is invalid")
        frozen_old_by_id[claim_id]["sampling_record_sha256"] = (
            sampling_record_sha256(
                deterministic_old_by_id[claim_id],
                human_old_by_id[claim_id],
                frozen["coordinator_only_primary_stratum"],
            )
        )

    return ReversedCorrectionState(
        deterministic_rows=deterministic_old,
        human_rows=human_old,
        frozen_rows=frozen_old,
        affected_claim_ids=tuple(sorted(affected_ids)),
        selected_claim_ids=tuple(sorted(selected_ids)),
    )
