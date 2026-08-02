#!/usr/bin/env python3
"""Apply ledger-directed source replacements without renumbering screened claims."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_sampling_screen_packets import (
    MODEL_FREE_SCREENING_STATUS,
    PROHIBITED_USE as SCREEN_PROHIBITED_USE,
    SUMMARY_SCHEMA_VERSION as SCREEN_SCHEMA_VERSION,
    append_stage,
    artifact,
    initialize_rows,
)
from prepare_candidate_pool import (
    CANDIDATE_HEADER,
    DEFAULT_FRAME_FROZEN_UTC,
    MAX_CANDIDATES_PER_SELECTED_SOURCE,
    MODEL_FREE_STATUS,
    MODEL_PRESCREEN_HEADER,
    SOURCE_HEADER,
    TEXT_ROOT,
    canonical_candidate_hash,
    extract_candidates,
)


PACKAGE = Path(__file__).resolve().parent
SUMMARY_SCHEMA_VERSION = "stable-source-replacement-v1"
SUMMARY_STATUS = "APPLIED_AWAITING_REPLACEMENT_SCREEN"
SCREEN_STATUS = "awaiting_replacement_screen"
PROHIBITED_USE = (
    "Source replacement is pre-label sampling administration. It preserves "
    "retained human screening votes and creates no replacement vote, test "
    "outcome, gold label, evidence-support label, or comparability label."
)
LEDGER_HEADER = (
    "ledger_event_id",
    "event_type",
    "source_key",
    "replacement_source_key",
    "sampling_stratum",
    "reason_code",
    "reason_detail",
    "eligible_c2_count",
    "eligible_c5_count",
    "required_claims",
    "source_selection_rank",
    "recorded_utc",
    "record_sha256",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EVENT_RE = re.compile(r"^SR-(\d{3,})$")


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def serialize_csv(
    header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def serialize_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(content, encoding="utf-8")
    staging.replace(path)


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def subset_sha256(
    header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> str:
    return sha256_text(serialize_csv(header, rows))


def normalize_ledger_rows(
    ledger_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row_number, source_row in enumerate(ledger_rows, start=2):
        row = {
            field: (source_row.get(field) or "").strip()
            for field in LEDGER_HEADER
        }
        match = EVENT_RE.fullmatch(row["ledger_event_id"])
        if match is None or int(match.group(1)) != row_number - 1:
            raise ValueError(
                "replacement ledger event IDs must be the ordered SR-001..N suffix"
            )
        expected_hash = canonical_json_sha256(
            {
                field: row[field]
                for field in LEDGER_HEADER
                if field != "record_sha256"
            }
        )
        if row["record_sha256"] != expected_hash:
            raise ValueError(f"ledger row {row_number} has an invalid record hash")
        normalized.append(row)
    return normalized


def replacement_summary_prefix(
    summary: Mapping[str, Any], batch_count: int
) -> dict[str, Any]:
    batches = summary.get("batches")
    if not isinstance(batches, list) or not 1 <= batch_count <= len(batches):
        raise ValueError("invalid source replacement summary prefix")
    batch = batches[batch_count - 1]
    if not isinstance(batch, dict):
        raise ValueError("source replacement batch is not an object")
    return {
        "schema_version": summary.get("schema_version"),
        "status": summary.get("status"),
        "prohibited_use": summary.get("prohibited_use"),
        "batches": batches[:batch_count],
        "current_batch_id": batch.get("batch_id"),
    }


def replacement_event_ids(summary: Mapping[str, Any]) -> list[str]:
    event_ids: list[str] = []
    batches = summary.get("batches")
    if not isinstance(batches, list):
        raise ValueError("source replacement summary lacks batches")
    for batch in batches:
        if not isinstance(batch, dict):
            raise ValueError("source replacement batch is not an object")
        replacements = batch.get("replacements")
        if not isinstance(replacements, list) or not replacements:
            raise ValueError("source replacement batch lacks replacements")
        for replacement in replacements:
            if not isinstance(replacement, dict):
                raise ValueError("source replacement record is not an object")
            event_ids.append(
                str(replacement.get("ledger_event_id", "")).strip()
            )
    return event_ids


def load_inputs(args: argparse.Namespace) -> dict[str, Any]:
    frame_header, frame_rows = read_csv(args.source_frame)
    deterministic_header, deterministic_rows = read_csv(
        args.deterministic_candidates
    )
    human_header, human_rows = read_csv(args.human_screened_candidates)
    ledger_header, ledger_rows = read_csv(args.ledger)
    if frame_header != SOURCE_HEADER:
        raise ValueError("source frame schema mismatch")
    if deterministic_header != CANDIDATE_HEADER:
        raise ValueError("deterministic candidate schema mismatch")
    if human_header != MODEL_PRESCREEN_HEADER:
        raise ValueError("human-screened candidate schema mismatch")
    if ledger_header != LEDGER_HEADER:
        raise ValueError("replacement ledger schema mismatch")
    if not ledger_rows:
        raise ValueError("replacement ledger is empty")
    try:
        screen_summary = json.loads(
            args.screen_summary.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid sampling screen summary: {exc}") from exc
    replacement_summary: dict[str, Any] | None = None
    replacement_summary_text = ""
    if args.replacement_summary.exists():
        replacement_summary_text = args.replacement_summary.read_text(
            encoding="utf-8"
        )
        try:
            replacement_summary = json.loads(replacement_summary_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid source replacement summary: {exc}"
            ) from exc
    return {
        "frame_rows": frame_rows,
        "deterministic_rows": deterministic_rows,
        "human_rows": human_rows,
        "ledger_rows": ledger_rows,
        "screen_summary": screen_summary,
        "replacement_summary": replacement_summary,
        "replacement_summary_text": replacement_summary_text,
    }


def validate_parent_state(
    frame_rows: Sequence[Mapping[str, str]],
    deterministic_rows: Sequence[Mapping[str, str]],
    human_rows: Sequence[Mapping[str, str]],
    ledger_rows: Sequence[Mapping[str, str]],
    screen_summary: Mapping[str, Any],
) -> tuple[
    list[dict[str, str]],
    dict[str, Mapping[str, str]],
    dict[str, Mapping[str, str]],
]:
    if screen_summary.get("schema_version") != SCREEN_SCHEMA_VERSION:
        raise ValueError("sampling screen summary schema mismatch")
    if screen_summary.get("prohibited_use") != SCREEN_PROHIBITED_USE:
        raise ValueError("sampling screen summary lacks prohibited-use text")
    if (
        screen_summary.get("status") != "human_sampling_screen_complete"
        or screen_summary.get("screening_complete") is not True
    ):
        raise ValueError("parent human screening is not complete")
    current = screen_summary.get("current_candidate_state")
    human_text = serialize_csv(MODEL_PRESCREEN_HEADER, human_rows)
    if not isinstance(current, dict) or (
        current.get("sha256") != sha256_text(human_text)
        or current.get("rows") != len(human_rows)
    ):
        raise ValueError("sampling screen summary does not anchor parent human rows")
    stages = screen_summary.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("sampling screen summary lacks stage history")
    final_ids = stages[-1].get("screener_ids")
    if not isinstance(final_ids, list) or len(final_ids) != 3:
        raise ValueError("parent screening does not have three screener IDs")
    if len(set(final_ids)) != 3:
        raise ValueError("parent screening IDs are not distinct")

    frame_by_key = {
        (row.get("source_key") or "").strip(): row for row in frame_rows
    }
    deterministic_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row
        for row in deterministic_rows
    }
    human_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row
        for row in human_rows
    }
    if (
        len(frame_by_key) != len(frame_rows)
        or len(deterministic_by_id) != len(deterministic_rows)
        or len(human_by_id) != len(human_rows)
        or set(deterministic_by_id) != set(human_by_id)
    ):
        raise ValueError("parent frame/candidates contain duplicate or mismatched IDs")
    selected = {
        key
        for key, row in frame_by_key.items()
        if (row.get("eligibility_status") or "").strip() == "eligible_selected"
    }
    candidate_sources = {
        (row.get("source_key") or "").strip() for row in deterministic_rows
    }
    if selected != candidate_sources:
        raise ValueError("parent selected sources and candidates differ")

    validated_ledger: list[dict[str, str]] = []
    deficient_seen: set[str] = set()
    replacement_seen: set[str] = set()
    event_seen: set[str] = set()
    for row_number, source_row in enumerate(ledger_rows, start=2):
        row = {field: (source_row.get(field) or "").strip() for field in LEDGER_HEADER}
        event_id = row["ledger_event_id"]
        match = EVENT_RE.fullmatch(event_id)
        deficient = row["source_key"]
        replacement = row["replacement_source_key"]
        if (
            match is None
            or event_id in event_seen
            or deficient in deficient_seen
            or replacement in replacement_seen
            or deficient == replacement
        ):
            raise ValueError(f"ledger row {row_number} reuses an event/source")
        expected_hash = canonical_json_sha256(
            {
                field: row[field]
                for field in LEDGER_HEADER
                if field != "record_sha256"
            }
        )
        if row["record_sha256"] != expected_hash:
            raise ValueError(f"ledger row {row_number} has an invalid record hash")
        if row["event_type"] != "source_replacement_required":
            raise ValueError(f"ledger row {row_number} has an invalid event type")
        if deficient not in selected:
            raise ValueError(f"ledger deficient source is not selected: {deficient}")
        replacement_frame = frame_by_key.get(replacement)
        if replacement_frame is None or (
            replacement_frame.get("eligibility_status") or ""
        ).strip() != "eligible_reserve":
            raise ValueError(
                f"ledger replacement source is not an eligible reserve: {replacement}"
            )
        deficient_slots = {
            int((candidate.get("source_selection_rank") or "0").strip())
            for candidate in deterministic_rows
            if (candidate.get("source_key") or "").strip() == deficient
        }
        if deficient_slots != {int(row["source_selection_rank"])}:
            raise ValueError(f"ledger source slot mismatch for {deficient}")
        if (
            row["sampling_stratum"]
            != (frame_by_key[deficient].get("sampling_stratum") or "").strip()
        ):
            raise ValueError(f"ledger stratum mismatch for {deficient}")
        event_seen.add(event_id)
        deficient_seen.add(deficient)
        replacement_seen.add(replacement)
        validated_ledger.append(row)
    return validated_ledger, frame_by_key, deterministic_by_id


def extract_replacement_candidates(
    ledger_rows: Sequence[Mapping[str, str]],
    frame_by_key: Mapping[str, Mapping[str, str]],
    text_root: Path,
) -> list[dict[str, object]]:
    new_rows: list[dict[str, object]] = []
    for ledger in ledger_rows:
        event_match = EVENT_RE.fullmatch(ledger["ledger_event_id"])
        if event_match is None:
            raise AssertionError("validated ledger event became invalid")
        event_number = event_match.group(1)
        source_key = ledger["replacement_source_key"]
        frame_row = frame_by_key[source_key]
        text_path = text_root / f"{source_key}.txt"
        if not text_path.is_file():
            raise ValueError(f"replacement expanded text is missing: {source_key}")
        observed_hash = sha256_file(text_path)
        if observed_hash != (frame_row.get("full_text_sha256") or "").strip():
            raise ValueError(f"replacement expanded-text hash mismatch: {source_key}")
        extracted = extract_candidates(
            text_path.read_text(encoding="utf-8", errors="replace")
        )
        extracted.sort(
            key=lambda row: (
                -int(row["section_priority"]),
                -int(row["cue_score"]),
                int(row["pdf_page"]),
                int(row["sequence"]),
            )
        )
        selected = extracted[:MAX_CANDIDATES_PER_SELECTED_SOURCE]
        if len(selected) < 6:
            raise ValueError(
                f"replacement source has fewer than six candidates: {source_key}"
            )
        for rank, candidate in enumerate(selected, start=1):
            row: dict[str, object] = {
                "candidate_claim_id": f"H3R-{event_number}-{rank:02d}",
                "source_key": source_key,
                "source_title": frame_row["title"],
                "source_url_or_doi": frame_row["stable_url_or_doi"],
                "source_selection_rank": ledger["source_selection_rank"],
                "source_candidate_rank": rank,
                "source_section": candidate["source_section"],
                "pdf_page": candidate["pdf_page"],
                "exact_quote": candidate["exact_quote"],
                "context_before": candidate["context_before"],
                "context_after": candidate["context_after"],
                "cue_score": candidate["cue_score"],
                "section_priority": candidate["section_priority"],
                "source_text_sha256": frame_row["full_text_sha256"],
                "corpus_snapshot_id": frame_row["corpus_snapshot_id"],
                "candidate_record_sha256": "",
                "extraction_method": (
                    "deterministic_comparative_cue_v1_model_free"
                ),
                "model_free_status": MODEL_FREE_STATUS,
            }
            row["candidate_record_sha256"] = canonical_candidate_hash(row)
            new_rows.append(row)
    ids = [str(row["candidate_claim_id"]) for row in new_rows]
    if len(ids) != len(set(ids)):
        raise AssertionError("replacement namespace produced duplicate IDs")
    return new_rows


def build_outputs(
    frame_rows: Sequence[Mapping[str, str]],
    deterministic_rows: Sequence[Mapping[str, str]],
    human_rows: Sequence[Mapping[str, str]],
    ledger_rows: Sequence[Mapping[str, str]],
    screen_summary: Mapping[str, Any],
    text_root: Path,
    recorded_utc: str,
    expected_active_sources: int = 80,
    *,
    all_ledger_rows: Sequence[Mapping[str, str]] | None = None,
    prior_replacement_summary: Mapping[str, Any] | None = None,
    prior_replacement_summary_text: str = "",
) -> dict[str, Any]:
    if not recorded_utc.strip():
        raise ValueError("--recorded-utc is required")
    validated_ledger, frame_by_key, _deterministic_by_id = validate_parent_state(
        frame_rows,
        deterministic_rows,
        human_rows,
        ledger_rows,
        screen_summary,
    )
    complete_ledger = normalize_ledger_rows(
        all_ledger_rows if all_ledger_rows is not None else ledger_rows
    )
    if [row["ledger_event_id"] for row in complete_ledger[-len(validated_ledger) :]] != [
        row["ledger_event_id"] for row in validated_ledger
    ]:
        raise ValueError("new replacement ledger events are not the ledger suffix")
    prior_batches: list[Mapping[str, Any]] = []
    if prior_replacement_summary is not None:
        if (
            prior_replacement_summary.get("schema_version")
            != SUMMARY_SCHEMA_VERSION
            or prior_replacement_summary.get("status") != SUMMARY_STATUS
            or prior_replacement_summary.get("prohibited_use") != PROHIBITED_USE
        ):
            raise ValueError("prior source replacement summary metadata mismatch")
        prior_value = prior_replacement_summary.get("batches")
        if not isinstance(prior_value, list) or not prior_value:
            raise ValueError("prior source replacement summary lacks batches")
        prior_batches = prior_value
        if (
            prior_replacement_summary.get("current_batch_id")
            != prior_batches[-1].get("batch_id")
        ):
            raise ValueError("prior source replacement current batch is stale")
        if not prior_replacement_summary_text:
            prior_replacement_summary_text = serialize_json(
                prior_replacement_summary
            )
    deficient = {row["source_key"] for row in validated_ledger}
    replacements = {row["replacement_source_key"] for row in validated_ledger}
    retained_sources = {
        (row.get("source_key") or "").strip()
        for row in frame_rows
        if (row.get("eligibility_status") or "").strip() == "eligible_selected"
    } - deficient
    if len(retained_sources) != expected_active_sources - len(replacements):
        raise ValueError("replacement ledger does not leave the expected retained set")

    retained_frame_before = [
        dict(row)
        for row in frame_rows
        if (row.get("source_key") or "").strip() in retained_sources
    ]
    retained_deterministic_before = [
        dict(row)
        for row in deterministic_rows
        if (row.get("source_key") or "").strip() in retained_sources
    ]
    retained_human_before = [
        dict(row)
        for row in human_rows
        if (row.get("source_key") or "").strip() in retained_sources
    ]
    frame_output = [dict(row) for row in frame_rows]
    ledger_by_deficient = {row["source_key"]: row for row in validated_ledger}
    ledger_by_replacement = {
        row["replacement_source_key"]: row for row in validated_ledger
    }
    for row in frame_output:
        source_key = row["source_key"]
        if source_key in ledger_by_deficient:
            ledger = ledger_by_deficient[source_key]
            row["eligibility_status"] = "excluded"
            row["exclusion_reason_code"] = "FEWER_THAN_SIX_ELIGIBLE_CLAIMS"
            row["exclusion_reason_detail"] = (
                f"replaced_by={ledger['replacement_source_key']};"
                f"ledger_event={ledger['ledger_event_id']}"
            )
        elif source_key in ledger_by_replacement:
            row["eligibility_status"] = "eligible_selected"
            row["exclusion_reason_code"] = ""
            row["exclusion_reason_detail"] = ""

    retained_frame_after = [
        dict(row)
        for row in frame_output
        if (row.get("source_key") or "").strip() in retained_sources
    ]
    if retained_frame_after != retained_frame_before:
        raise AssertionError("retained source-frame rows changed")

    new_deterministic = extract_replacement_candidates(
        validated_ledger, frame_by_key, text_root
    )
    deterministic_output = [
        dict(row)
        for row in deterministic_rows
        if (row.get("source_key") or "").strip() not in deficient
    ] + new_deterministic
    human_output = [
        dict(row)
        for row in human_rows
        if (row.get("source_key") or "").strip() not in deficient
    ] + initialize_rows(new_deterministic)

    retained_deterministic_after = [
        row
        for row in deterministic_output
        if (row.get("source_key") or "").strip() in retained_sources
    ]
    retained_human_after = [
        row
        for row in human_output
        if (row.get("source_key") or "").strip() in retained_sources
    ]
    if retained_deterministic_after != retained_deterministic_before:
        raise AssertionError("retained deterministic candidate rows changed")
    if retained_human_after != retained_human_before:
        raise AssertionError("retained human-screened candidate rows changed")

    active_sources = retained_sources | replacements
    frame_selected = {
        row["source_key"]
        for row in frame_output
        if row["eligibility_status"] == "eligible_selected"
    }
    candidate_sources = {str(row["source_key"]) for row in deterministic_output}
    if (
        len(active_sources) != expected_active_sources
        or frame_selected != active_sources
        or candidate_sources != active_sources
    ):
        raise AssertionError("replacement outputs do not contain the active source set")
    if {row["candidate_claim_id"] for row in deterministic_output} != {
        row["candidate_claim_id"] for row in human_output
    }:
        raise AssertionError("replacement deterministic/human IDs differ")
    old_retained_ids = {
        row["candidate_claim_id"] for row in retained_deterministic_before
    }
    if any(
        row["candidate_claim_id"] in old_retained_ids for row in new_deterministic
    ):
        raise AssertionError("replacement IDs collide with retained IDs")

    if prior_batches:
        previous_slots = prior_batches[-1].get("active_source_slots")
        if (
            not isinstance(previous_slots, list)
            or len(previous_slots) != expected_active_sources
        ):
            raise ValueError("prior replacement batch active slots are invalid")
        active_slots = [dict(row) for row in previous_slots]
        active_by_slot = {
            int(row.get("slot", 0)): row for row in active_slots
        }
        for ledger in validated_ledger:
            slot = int(ledger["source_selection_rank"])
            prior_slot = active_by_slot.get(slot)
            if (
                prior_slot is None
                or str(prior_slot.get("source_key", "")).strip()
                != ledger["source_key"]
            ):
                raise ValueError(
                    f"ledger deficient source is not active in slot {slot}"
                )
            active_by_slot[slot] = {
                "slot": slot,
                "source_key": ledger["replacement_source_key"],
                "replaces_source_key": ledger["source_key"],
                "ledger_event_id": ledger["ledger_event_id"],
            }
        active_slots = list(active_by_slot.values())
    else:
        active_slots = [
            {
                "slot": int(row["source_selection_rank"]),
                "source_key": row["replacement_source_key"],
                "replaces_source_key": row["source_key"],
                "ledger_event_id": row["ledger_event_id"],
            }
            for row in validated_ledger
        ]
        retained_slots: dict[str, int] = {}
        for row in retained_deterministic_before:
            source_key = row["source_key"]
            slot = int(row["source_selection_rank"])
            previous = retained_slots.setdefault(source_key, slot)
            if previous != slot:
                raise AssertionError(
                    f"retained source has multiple slots: {source_key}"
                )
        active_slots.extend(
            {
                "slot": slot,
                "source_key": source_key,
                "replaces_source_key": "",
                "ledger_event_id": "",
            }
            for source_key, slot in retained_slots.items()
        )
    active_slots.sort(key=lambda row: int(row["slot"]))
    if [row["slot"] for row in active_slots] != list(
        range(1, expected_active_sources + 1)
    ):
        raise AssertionError("active replacement slots are not exactly 1..N")

    frame_text_before = serialize_csv(SOURCE_HEADER, frame_rows)
    deterministic_text_before = serialize_csv(
        CANDIDATE_HEADER, deterministic_rows
    )
    human_text_before = serialize_csv(MODEL_PRESCREEN_HEADER, human_rows)
    ledger_text = serialize_csv(LEDGER_HEADER, complete_ledger)
    new_ledger_text = serialize_csv(LEDGER_HEADER, validated_ledger)
    screen_summary_parent_text = serialize_json(screen_summary)
    frame_text = serialize_csv(SOURCE_HEADER, frame_output)
    deterministic_text = serialize_csv(CANDIDATE_HEADER, deterministic_output)
    human_text = serialize_csv(MODEL_PRESCREEN_HEADER, human_output)

    screen_summary_output = json.loads(screen_summary_parent_text)
    screener_ids = list(screen_summary["stages"][-1]["screener_ids"])
    batch_number = len(prior_batches) + 1
    batch_id = f"RB-{batch_number:03d}"
    apply_inputs = [
        artifact("source_sampling_frame.csv", frame_text_before, len(frame_rows)),
        artifact(
            "candidate_claims_deterministic.csv",
            deterministic_text_before,
            len(deterministic_rows),
        ),
        artifact(
            "candidate_claims_model_prescreen.csv",
            human_text_before,
            len(human_rows),
        ),
        artifact(
            "sampling_exclusion_replacement_ledger.csv",
            ledger_text,
            len(complete_ledger),
        ),
        artifact(
            "sampling_screen_summary_parent.json",
            screen_summary_parent_text,
            len(screen_summary["stages"]),
        ),
    ]
    if prior_batches:
        apply_inputs.append(
            artifact(
                "source_replacement_summary_parent.json",
                prior_replacement_summary_text,
                len(prior_batches),
            )
        )
    append_stage(
        screen_summary_output,
        "apply_replacements",
        recorded_utc,
        apply_inputs,
        [
            artifact("source_sampling_frame.csv", frame_text, len(frame_output)),
            artifact(
                "candidate_claims_deterministic.csv",
                deterministic_text,
                len(deterministic_output),
            ),
            artifact(
                "candidate_claims_model_prescreen.csv",
                human_text,
                len(human_output),
            ),
        ],
        {
            "deficient_sources_removed": len(deficient),
            "replacement_sources_added": len(replacements),
            "retained_sources_unchanged": len(retained_sources),
            "retained_candidate_rows_unchanged": len(
                retained_deterministic_before
            ),
            "new_replacement_candidates": len(new_deterministic),
            "replacement_batch_number": batch_number,
            "test_outcomes_generated": 0,
        },
        screener_ids,
        human_text,
        len(human_output),
        SCREEN_STATUS,
        False,
    )
    screen_summary_text = serialize_json(screen_summary_output)

    replacement_records = []
    new_counts: dict[str, int] = {}
    removed_counts: dict[str, int] = {}
    for row in new_deterministic:
        source_key = str(row["source_key"])
        new_counts[source_key] = new_counts.get(source_key, 0) + 1
    for row in deterministic_rows:
        source_key = row["source_key"]
        if source_key in deficient:
            removed_counts[source_key] = removed_counts.get(source_key, 0) + 1
    for ledger in validated_ledger:
        replacement_records.append(
            {
                "ledger_event_id": ledger["ledger_event_id"],
                "deficient_source_key": ledger["source_key"],
                "replacement_source_key": ledger["replacement_source_key"],
                "source_slot": int(ledger["source_selection_rank"]),
                "removed_candidates": removed_counts[ledger["source_key"]],
                "new_candidates": new_counts[ledger["replacement_source_key"]],
                "new_id_prefix": (
                    f"H3R-{EVENT_RE.fullmatch(ledger['ledger_event_id']).group(1)}-"
                ),
                "replacement_source_text_sha256": frame_by_key[
                    ledger["replacement_source_key"]
                ]["full_text_sha256"],
            }
        )

    parent = {
        "source_sampling_frame_sha256": sha256_text(frame_text_before),
        "source_sampling_frame_rows": len(frame_rows),
        "candidate_claims_deterministic_sha256": sha256_text(
            deterministic_text_before
        ),
        "candidate_claims_deterministic_rows": len(deterministic_rows),
        "candidate_claims_model_prescreen_sha256": sha256_text(human_text_before),
        "candidate_claims_model_prescreen_rows": len(human_rows),
        "sampling_screen_summary_sha256": sha256_text(screen_summary_parent_text),
        "sampling_exclusion_replacement_ledger_sha256": sha256_text(ledger_text),
        "sampling_exclusion_replacement_ledger_rows": len(complete_ledger),
        "new_sampling_exclusion_replacement_ledger_sha256": sha256_text(
            new_ledger_text
        ),
        "new_sampling_exclusion_replacement_ledger_rows": len(
            validated_ledger
        ),
        "new_ledger_event_ids": [
            row["ledger_event_id"] for row in validated_ledger
        ],
    }
    if prior_batches:
        parent.update(
            {
                "prior_batch_id": prior_batches[-1].get("batch_id"),
                "prior_source_replacement_summary_sha256": sha256_text(
                    prior_replacement_summary_text
                ),
            }
        )
    outputs = {
        "source_sampling_frame_sha256": sha256_text(frame_text),
        "source_sampling_frame_rows": len(frame_output),
        "candidate_claims_deterministic_sha256": sha256_text(deterministic_text),
        "candidate_claims_deterministic_rows": len(deterministic_output),
        "candidate_claims_model_prescreen_after_apply_sha256": sha256_text(
            human_text
        ),
        "candidate_claims_model_prescreen_rows": len(human_output),
        "sampling_screen_summary_after_apply_sha256": sha256_text(
            screen_summary_text
        ),
    }
    batch: dict[str, Any] = {
        "batch_id": batch_id,
        "recorded_utc": recorded_utc.strip(),
        "parent": parent,
        "replacements": replacement_records,
        "active_source_slots": active_slots,
        "invariants": {
            "retained_sources": len(retained_sources),
            "retained_source_frame_rows_sha256": subset_sha256(
                SOURCE_HEADER, retained_frame_before
            ),
            "retained_deterministic_rows": len(retained_deterministic_before),
            "retained_deterministic_rows_sha256": subset_sha256(
                CANDIDATE_HEADER, retained_deterministic_before
            ),
            "retained_human_rows": len(retained_human_before),
            "retained_human_rows_sha256": subset_sha256(
                MODEL_PRESCREEN_HEADER, retained_human_before
            ),
            "candidate_ids_raw_hashes_human_fields_unchanged": True,
        },
        "outputs": outputs,
    }
    batch["batch_record_sha256"] = canonical_json_sha256(batch)
    replacement_summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": SUMMARY_STATUS,
        "prohibited_use": PROHIBITED_USE,
        "batches": [*prior_batches, batch],
        "current_batch_id": batch_id,
    }
    replacement_summary_text = serialize_json(replacement_summary)
    return {
        "frame_rows": frame_output,
        "deterministic_rows": deterministic_output,
        "human_rows": human_output,
        "screen_summary": screen_summary_output,
        "replacement_summary": replacement_summary,
        "texts": {
            "frame": frame_text,
            "deterministic": deterministic_text,
            "human": human_text,
            "screen_summary": screen_summary_text,
            "replacement_summary": replacement_summary_text,
        },
        "result": {
            "status": SCREEN_STATUS,
            "retained_sources_unchanged": len(retained_sources),
            "replacement_sources": len(replacements),
            "replacement_batch_id": batch_id,
            "new_replacement_candidates": len(new_deterministic),
            "candidate_rows": len(deterministic_output),
            "test_outcomes_generated": 0,
        },
    }


def artifact_by_name(
    records: Any, name: str
) -> Mapping[str, Any]:
    matches = [
        record
        for record in records
        if isinstance(record, dict) and record.get("artifact") == name
    ] if isinstance(records, list) else []
    if len(matches) != 1:
        raise ValueError(f"expected one {name} artifact record")
    return matches[0]


def screen_summary_snapshot(
    screen_summary: Mapping[str, Any],
    stages: Sequence[Mapping[str, Any]],
    current_candidate: Mapping[str, Any],
    *,
    complete: bool,
) -> dict[str, Any]:
    return {
        "schema_version": screen_summary.get("schema_version"),
        "status": (
            "human_sampling_screen_complete"
            if complete
            else SCREEN_STATUS
        ),
        "screening_complete": complete,
        "prohibited_use": screen_summary.get("prohibited_use"),
        "current_candidate_state": {
            "artifact": "candidate_claims_model_prescreen.csv",
            "rows": current_candidate.get("rows"),
            "sha256": current_candidate.get("sha256"),
        },
        "stages": list(stages),
    }


def verify_replacement_chain(
    summary: Mapping[str, Any],
    loaded: Mapping[str, Any],
    *,
    expected_sources: int,
    text_root: Path | None,
) -> dict[str, Any]:
    if (
        summary.get("schema_version") != SUMMARY_SCHEMA_VERSION
        or summary.get("status") != SUMMARY_STATUS
        or summary.get("prohibited_use") != PROHIBITED_USE
    ):
        raise ValueError("source replacement summary metadata mismatch")
    batches = summary.get("batches")
    if not isinstance(batches, list) or not batches:
        raise ValueError("source replacement summary lacks a batch")
    if summary.get("current_batch_id") != batches[-1].get("batch_id"):
        raise ValueError("source replacement current batch ID is stale")

    ledger_rows = normalize_ledger_rows(loaded["ledger_rows"])
    screen_summary = loaded["screen_summary"]
    screen_stages = screen_summary.get("stages")
    if not isinstance(screen_stages, list):
        raise ValueError("sampling screen summary lacks stages")
    apply_stage_pairs = [
        (index, stage)
        for index, stage in enumerate(screen_stages)
        if isinstance(stage, dict) and stage.get("stage") == "apply_replacements"
    ]
    if len(apply_stage_pairs) != len(batches):
        raise ValueError(
            "sampling screen apply-stage count differs from replacement batches"
        )

    consumed_events = 0
    previous_batch: Mapping[str, Any] | None = None
    previous_slots: list[dict[str, Any]] | None = None
    cumulative_deficient: set[str] = set()

    for batch_index, batch_value in enumerate(batches, start=1):
        if not isinstance(batch_value, dict):
            raise ValueError("source replacement batch is not an object")
        batch = batch_value
        batch_id = f"RB-{batch_index:03d}"
        if batch.get("batch_id") != batch_id:
            raise ValueError("replacement batch IDs are not ordered RB-001..N")
        if batch.get("batch_record_sha256") != canonical_json_sha256(
            {
                key: value
                for key, value in batch.items()
                if key != "batch_record_sha256"
            }
        ):
            raise ValueError(f"{batch_id} record hash mismatch")
        parent = batch.get("parent")
        outputs = batch.get("outputs")
        invariants = batch.get("invariants")
        replacements = batch.get("replacements")
        active_slots = batch.get("active_source_slots")
        if (
            not isinstance(parent, dict)
            or not isinstance(outputs, dict)
            or not isinstance(invariants, dict)
            or not isinstance(replacements, list)
            or not replacements
            or not isinstance(active_slots, list)
        ):
            raise ValueError(f"{batch_id} structure is incomplete")

        batch_ledger = ledger_rows[
            consumed_events : consumed_events + len(replacements)
        ]
        if len(batch_ledger) != len(replacements):
            raise ValueError(f"{batch_id} has no matching ledger suffix")
        for replacement, ledger in zip(replacements, batch_ledger):
            if not isinstance(replacement, dict):
                raise ValueError(f"{batch_id} replacement is not an object")
            expected_mapping = (
                ledger["ledger_event_id"],
                ledger["source_key"],
                ledger["replacement_source_key"],
                int(ledger["source_selection_rank"]),
            )
            observed_mapping = (
                str(replacement.get("ledger_event_id", "")).strip(),
                str(replacement.get("deficient_source_key", "")).strip(),
                str(replacement.get("replacement_source_key", "")).strip(),
                int(replacement.get("source_slot", 0)),
            )
            if observed_mapping != expected_mapping:
                raise ValueError(f"{batch_id} differs from its ledger records")
            event_number = EVENT_RE.fullmatch(ledger["ledger_event_id"])
            expected_prefix = f"H3R-{event_number.group(1)}-"
            if replacement.get("new_id_prefix") != expected_prefix:
                raise ValueError(f"{batch_id} has an invalid candidate namespace")
            cumulative_deficient.add(ledger["source_key"])

        consumed_events += len(batch_ledger)
        ledger_prefix = ledger_rows[:consumed_events]
        if (
            parent.get("sampling_exclusion_replacement_ledger_rows")
            != consumed_events
            or parent.get("sampling_exclusion_replacement_ledger_sha256")
            != sha256_text(serialize_csv(LEDGER_HEADER, ledger_prefix))
        ):
            raise ValueError(f"{batch_id} parent ledger anchor mismatch")
        if batch_index > 1:
            new_ledger_text = serialize_csv(LEDGER_HEADER, batch_ledger)
            if (
                parent.get("new_sampling_exclusion_replacement_ledger_rows")
                != len(batch_ledger)
                or parent.get(
                    "new_sampling_exclusion_replacement_ledger_sha256"
                )
                != sha256_text(new_ledger_text)
                or parent.get("new_ledger_event_ids")
                != [row["ledger_event_id"] for row in batch_ledger]
            ):
                raise ValueError(f"{batch_id} new-ledger anchor mismatch")
            if previous_batch is None:
                raise AssertionError("previous replacement batch disappeared")
            previous_outputs = previous_batch["outputs"]
            continuity_fields = (
                "source_sampling_frame_sha256",
                "source_sampling_frame_rows",
                "candidate_claims_deterministic_sha256",
                "candidate_claims_deterministic_rows",
            )
            if any(
                parent.get(field) != previous_outputs.get(field)
                for field in continuity_fields
            ):
                raise ValueError(f"{batch_id} parent-output continuity failed")
            prior_prefix = replacement_summary_prefix(
                summary, batch_index - 1
            )
            if (
                parent.get("prior_batch_id")
                != previous_batch.get("batch_id")
                or parent.get("prior_source_replacement_summary_sha256")
                != sha256_text(serialize_json(prior_prefix))
            ):
                raise ValueError(f"{batch_id} prior-summary anchor mismatch")

        apply_index, apply_stage = apply_stage_pairs[batch_index - 1]
        if apply_stage.get("stage_record_sha256") != canonical_json_sha256(
            {
                key: value
                for key, value in apply_stage.items()
                if key != "stage_record_sha256"
            }
        ):
            raise ValueError(f"{batch_id} apply-stage record hash mismatch")
        apply_inputs = apply_stage.get("inputs")
        apply_outputs = apply_stage.get("outputs")
        input_frame = artifact_by_name(
            apply_inputs, "source_sampling_frame.csv"
        )
        input_deterministic = artifact_by_name(
            apply_inputs, "candidate_claims_deterministic.csv"
        )
        input_human = artifact_by_name(
            apply_inputs, "candidate_claims_model_prescreen.csv"
        )
        input_ledger = artifact_by_name(
            apply_inputs, "sampling_exclusion_replacement_ledger.csv"
        )
        input_screen = artifact_by_name(
            apply_inputs, "sampling_screen_summary_parent.json"
        )
        output_human = artifact_by_name(
            apply_outputs, "candidate_claims_model_prescreen.csv"
        )
        if (
            input_frame.get("sha256")
            != parent.get("source_sampling_frame_sha256")
            or input_frame.get("rows")
            != parent.get("source_sampling_frame_rows")
            or input_deterministic.get("sha256")
            != parent.get("candidate_claims_deterministic_sha256")
            or input_deterministic.get("rows")
            != parent.get("candidate_claims_deterministic_rows")
            or input_human.get("sha256")
            != parent.get("candidate_claims_model_prescreen_sha256")
            or input_human.get("rows")
            != parent.get("candidate_claims_model_prescreen_rows")
            or input_ledger.get("sha256")
            != parent.get("sampling_exclusion_replacement_ledger_sha256")
            or input_ledger.get("rows")
            != parent.get("sampling_exclusion_replacement_ledger_rows")
            or input_screen.get("sha256")
            != parent.get("sampling_screen_summary_sha256")
            or output_human.get("sha256")
            != outputs.get(
                "candidate_claims_model_prescreen_after_apply_sha256"
            )
            or output_human.get("rows")
            != outputs.get("candidate_claims_model_prescreen_rows")
        ):
            raise ValueError(f"{batch_id} apply artifact anchors mismatch")
        if batch_index > 1:
            input_prior = artifact_by_name(
                apply_inputs, "source_replacement_summary_parent.json"
            )
            if (
                input_prior.get("sha256")
                != parent.get("prior_source_replacement_summary_sha256")
                or input_prior.get("rows") != batch_index - 1
            ):
                raise ValueError(f"{batch_id} apply prior-summary anchor mismatch")

        parent_screen = screen_summary_snapshot(
            screen_summary,
            screen_stages[:apply_index],
            input_human,
            complete=True,
        )
        applied_screen = screen_summary_snapshot(
            screen_summary,
            screen_stages[: apply_index + 1],
            output_human,
            complete=False,
        )
        if (
            sha256_text(serialize_json(parent_screen))
            != parent.get("sampling_screen_summary_sha256")
            or sha256_text(serialize_json(applied_screen))
            != outputs.get("sampling_screen_summary_after_apply_sha256")
        ):
            raise ValueError(f"{batch_id} screen-summary chain mismatch")

        ordered_slots = sorted(
            (dict(row) for row in active_slots),
            key=lambda row: int(row.get("slot", 0)),
        )
        if (
            len(ordered_slots) != expected_sources
            or [int(row.get("slot", 0)) for row in ordered_slots]
            != list(range(1, expected_sources + 1))
            or len(
                {
                    str(row.get("source_key", "")).strip()
                    for row in ordered_slots
                }
            )
            != expected_sources
        ):
            raise ValueError(f"{batch_id} active slots are invalid")
        if previous_slots is not None:
            expected_slots = {
                int(row["slot"]): dict(row) for row in previous_slots
            }
            for ledger in batch_ledger:
                slot = int(ledger["source_selection_rank"])
                if (
                    str(expected_slots[slot].get("source_key", "")).strip()
                    != ledger["source_key"]
                ):
                    raise ValueError(
                        f"{batch_id} replaces a source outside its active slot"
                    )
                expected_slots[slot] = {
                    "slot": slot,
                    "source_key": ledger["replacement_source_key"],
                    "replaces_source_key": ledger["source_key"],
                    "ledger_event_id": ledger["ledger_event_id"],
                }
            if ordered_slots != [
                expected_slots[slot]
                for slot in range(1, expected_sources + 1)
            ]:
                raise ValueError(f"{batch_id} changed an unrelated active slot")
        if (
            invariants.get(
                "candidate_ids_raw_hashes_human_fields_unchanged"
            )
            is not True
        ):
            raise ValueError(f"{batch_id} lacks the append-only invariant")
        previous_batch = batch
        previous_slots = ordered_slots

    if consumed_events != len(ledger_rows):
        raise ValueError("replacement ledger contains unapplied events")
    if previous_batch is None or previous_slots is None:
        raise AssertionError("replacement batch traversal produced no state")

    final_outputs = previous_batch["outputs"]
    current_hashes = {
        "source_sampling_frame_sha256": sha256_text(
            serialize_csv(SOURCE_HEADER, loaded["frame_rows"])
        ),
        "source_sampling_frame_rows": len(loaded["frame_rows"]),
        "candidate_claims_deterministic_sha256": sha256_text(
            serialize_csv(CANDIDATE_HEADER, loaded["deterministic_rows"])
        ),
        "candidate_claims_deterministic_rows": len(
            loaded["deterministic_rows"]
        ),
        "candidate_claims_model_prescreen_rows": len(loaded["human_rows"]),
    }
    if any(
        final_outputs.get(field) != value
        for field, value in current_hashes.items()
    ):
        raise ValueError("final replacement outputs are stale")

    active_keys = {
        str(row.get("source_key", "")).strip() for row in previous_slots
    }
    selected_keys = {
        row["source_key"]
        for row in loaded["frame_rows"]
        if row["eligibility_status"] == "eligible_selected"
    }
    candidate_sources = {
        row["source_key"] for row in loaded["deterministic_rows"]
    }
    deterministic_ids = {
        row["candidate_claim_id"] for row in loaded["deterministic_rows"]
    }
    human_ids = {row["candidate_claim_id"] for row in loaded["human_rows"]}
    if (
        active_keys != selected_keys
        or candidate_sources != active_keys
        or deterministic_ids != human_ids
        or active_keys.intersection(cumulative_deficient)
    ):
        raise ValueError("final active sources/candidates are inconsistent")

    current_replacements = previous_batch["replacements"]
    current_replacement_keys = {
        str(row["replacement_source_key"]) for row in current_replacements
    }
    retained_keys = active_keys - current_replacement_keys
    retained_frame = [
        row for row in loaded["frame_rows"] if row["source_key"] in retained_keys
    ]
    retained_deterministic = [
        row
        for row in loaded["deterministic_rows"]
        if row["source_key"] in retained_keys
    ]
    retained_human = [
        row for row in loaded["human_rows"] if row["source_key"] in retained_keys
    ]
    invariants = previous_batch["invariants"]
    invariant_checks = {
        "retained_sources": len(retained_keys),
        "retained_source_frame_rows_sha256": subset_sha256(
            SOURCE_HEADER, retained_frame
        ),
        "retained_deterministic_rows": len(retained_deterministic),
        "retained_deterministic_rows_sha256": subset_sha256(
            CANDIDATE_HEADER, retained_deterministic
        ),
        "retained_human_rows": len(retained_human),
        "retained_human_rows_sha256": subset_sha256(
            MODEL_PRESCREEN_HEADER, retained_human
        ),
        "candidate_ids_raw_hashes_human_fields_unchanged": True,
    }
    if any(
        invariants.get(field) != value
        for field, value in invariant_checks.items()
    ):
        raise ValueError("final retained append-only invariant failed")

    active_event_ids = {
        str(row.get("ledger_event_id", "")).strip()
        for row in previous_slots
        if str(row.get("ledger_event_id", "")).strip()
    }
    active_ledger = [
        row for row in ledger_rows if row["ledger_event_id"] in active_event_ids
    ]
    active_replacement_keys = {
        row["replacement_source_key"] for row in active_ledger
    }
    actual_replacement_rows = [
        row
        for row in loaded["deterministic_rows"]
        if row["source_key"] in active_replacement_keys
    ]
    for row in actual_replacement_rows:
        ledger = next(
            event
            for event in active_ledger
            if event["replacement_source_key"] == row["source_key"]
        )
        event_number = EVENT_RE.fullmatch(ledger["ledger_event_id"])
        if not row["candidate_claim_id"].startswith(
            f"H3R-{event_number.group(1)}-"
        ):
            raise ValueError("active replacement candidate namespace mismatch")
    if text_root is not None:
        frame_by_key = {
            row["source_key"]: row for row in loaded["frame_rows"]
        }
        regenerated = extract_replacement_candidates(
            active_ledger, frame_by_key, text_root
        )
        if serialize_csv(CANDIDATE_HEADER, actual_replacement_rows) != (
            serialize_csv(CANDIDATE_HEADER, regenerated)
        ):
            raise ValueError(
                "active replacement candidates do not reproduce from text"
            )
    return {
        "status": "PASS_CURRENT_STABLE_REPLACEMENT",
        "batches": len(batches),
        "current_batch_id": summary["current_batch_id"],
        "active_sources": len(active_keys),
        "retained_sources_unchanged": len(retained_keys),
        "replacement_sources": len(active_replacement_keys),
        "candidate_rows": len(loaded["deterministic_rows"]),
        "deficient_source_keys": sorted(cumulative_deficient),
        "active_replacement_source_keys": sorted(active_replacement_keys),
        "active_source_order": [
            str(row["source_key"]) for row in previous_slots
        ],
        "test_outcomes_generated": 0,
    }


def verify_applied(
    args: argparse.Namespace,
    loaded: Mapping[str, Any],
) -> dict[str, Any]:
    summary = loaded.get("replacement_summary")
    if not isinstance(summary, dict):
        raise ValueError("source replacement summary does not exist")
    return verify_replacement_chain(
        summary,
        loaded,
        expected_sources=args.expected_sources,
        text_root=args.text_root,
    )


def command_apply(args: argparse.Namespace) -> dict[str, Any]:
    loaded = load_inputs(args)
    if args.check:
        correction_path = (
            args.deterministic_candidates.parent
            / "frozen_text_corrections.csv"
        )
        frozen_path = (
            args.deterministic_candidates.parent / "frozen_test_claims.csv"
        )
        if correction_path.exists() and frozen_path.exists():
            _correction_header, correction_rows = read_csv(correction_path)
            _frozen_header, frozen_rows = read_csv(frozen_path)
            if correction_rows and frozen_rows:
                from frozen_text_corrections import (
                    validate_and_reverse_corrections,
                )

                correction_state = validate_and_reverse_corrections(
                    correction_rows,
                    loaded["deterministic_rows"],
                    loaded["human_rows"],
                    frozen_rows,
                )
                loaded["deterministic_rows"] = (
                    correction_state.deterministic_rows
                )
                loaded["human_rows"] = correction_state.human_rows
        return verify_applied(args, loaded)
    complete_ledger = normalize_ledger_rows(loaded["ledger_rows"])
    prior_summary = loaded.get("replacement_summary")
    used_event_ids: list[str] = []
    if isinstance(prior_summary, dict):
        verify_replacement_chain(
            prior_summary,
            {
                **loaded,
                "ledger_rows": complete_ledger[
                    : len(replacement_event_ids(prior_summary))
                ],
            },
            expected_sources=args.expected_sources,
            text_root=args.text_root,
        )
        used_event_ids = replacement_event_ids(prior_summary)
        if [row["ledger_event_id"] for row in complete_ledger[: len(used_event_ids)]] != (
            used_event_ids
        ):
            raise ValueError("prior replacement events are not the ledger prefix")
    new_ledger = complete_ledger[len(used_event_ids) :]
    if not new_ledger:
        raise ValueError("replacement ledger contains no unapplied event")
    outputs = build_outputs(
        loaded["frame_rows"],
        loaded["deterministic_rows"],
        loaded["human_rows"],
        new_ledger,
        loaded["screen_summary"],
        args.text_root,
        args.recorded_utc,
        args.expected_sources,
        all_ledger_rows=complete_ledger,
        prior_replacement_summary=prior_summary,
        prior_replacement_summary_text=loaded["replacement_summary_text"],
    )
    write_atomic(args.source_frame, outputs["texts"]["frame"])
    write_atomic(
        args.deterministic_candidates, outputs["texts"]["deterministic"]
    )
    write_atomic(args.human_screened_candidates, outputs["texts"]["human"])
    write_atomic(args.screen_summary, outputs["texts"]["screen_summary"])
    write_atomic(
        args.replacement_summary, outputs["texts"]["replacement_summary"]
    )
    return outputs["result"]


def fixture_frame_row(
    source_key: str, status: str, source_hash: str, rank: int
) -> dict[str, str]:
    return {
        "source_key": source_key,
        "title": f"Title {source_key}",
        "year": "2026",
        "venue_family": "Fixture",
        "publication_status": "preprint",
        "stable_url_or_doi": f"https://example.invalid/{source_key}",
        "corpus_snapshot_id": "fixture",
        "full_text_sha256": source_hash,
        "license_or_access_note": "fixture",
        "sampling_stratum": "Fixture::preprint",
        "eligible_candidate_count": "8",
        "eligibility_status": status,
        "exclusion_reason_code": "",
        "exclusion_reason_detail": "",
        "development_source_flag": "false",
        "deterministic_source_rank": str(rank),
        "frame_frozen_utc": DEFAULT_FRAME_FROZEN_UTC,
    }


def fixture_candidate(
    candidate_id: str, source_key: str, slot: int, rank: int
) -> dict[str, object]:
    row: dict[str, object] = {
        "candidate_claim_id": candidate_id,
        "source_key": source_key,
        "source_title": f"Title {source_key}",
        "source_url_or_doi": f"https://example.invalid/{source_key}",
        "source_selection_rank": str(slot),
        "source_candidate_rank": str(rank),
        "source_section": "Results",
        "pdf_page": "1",
        "exact_quote": (
            f"Candidate {rank} is better than baseline by 10 compared with 5 "
            "under the fixture condition."
        ),
        "context_before": "",
        "context_after": "",
        "cue_score": "5",
        "section_priority": "2",
        "source_text_sha256": "a" * 64,
        "corpus_snapshot_id": "fixture",
        "candidate_record_sha256": "",
        "extraction_method": "deterministic_comparative_cue_v1_model_free",
        "model_free_status": MODEL_FREE_STATUS,
    }
    row["candidate_record_sha256"] = canonical_candidate_hash(row)
    return row


def self_test() -> None:
    workspace = PACKAGE / ".source_replacement_selftest_workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    try:
        text_root = workspace / "texts"
        text_root.mkdir()
        replacement_text = "\n".join(
            [
                "1 Results",
                *[
                    (
                        f"Replacement method {index} is better than baseline "
                        f"with 12 compared with 8 under condition {index}."
                    )
                    for index in range(8)
                ],
            ]
        )
        replacement_path = text_root / "reserve.txt"
        replacement_path.write_text(replacement_text, encoding="utf-8")
        replacement_hash = sha256_file(replacement_path)
        replacement_path_2 = text_root / "reserve2.txt"
        replacement_path_2.write_text(
            replacement_text.replace("Replacement", "Second replacement"),
            encoding="utf-8",
        )
        replacement_hash_2 = sha256_file(replacement_path_2)
        frame = [
            fixture_frame_row("deficient", "eligible_selected", "a" * 64, 1),
            fixture_frame_row("retained", "eligible_selected", "a" * 64, 2),
            fixture_frame_row("reserve", "eligible_reserve", replacement_hash, 3),
            fixture_frame_row(
                "reserve2", "eligible_reserve", replacement_hash_2, 4
            ),
        ]
        deterministic = [
            fixture_candidate("H3-001-01", "deficient", 1, 1),
            fixture_candidate("H3-002-01", "retained", 2, 1),
        ]
        human = initialize_rows(deterministic)
        for row in human:
            row["human_sampling_reviewer_1_id"] = "screen-1"
            row["human_sampling_reviewer_2_id"] = "screen-2"
            row["human_sampling_eligibility"] = "eligible_c2"
            row["human_sampling_stratum"] = "c2_decisive"
            row["selection_status"] = "human_screen_consensus"
        human_text = serialize_csv(MODEL_PRESCREEN_HEADER, human)
        parent_stage: dict[str, Any] = {
            "stage": "merge_tiebreak",
            "recorded_utc": "2026-07-15T00:00:00Z",
            "inputs": [{"artifact": "fixture", "sha256": "b" * 64, "rows": 2}],
            "outputs": [
                {
                    "artifact": "candidate_claims_model_prescreen.csv",
                    "sha256": sha256_text(human_text),
                    "rows": 2,
                }
            ],
            "counts": {"test_outcomes_generated": 0},
            "screener_ids": ["screen-1", "screen-2", "screen-3"],
        }
        parent_stage["stage_record_sha256"] = canonical_json_sha256(parent_stage)
        screen_summary = {
            "schema_version": SCREEN_SCHEMA_VERSION,
            "status": "human_sampling_screen_complete",
            "screening_complete": True,
            "prohibited_use": SCREEN_PROHIBITED_USE,
            "current_candidate_state": {
                "artifact": "candidate_claims_model_prescreen.csv",
                "sha256": sha256_text(human_text),
                "rows": 2,
            },
            "stages": [parent_stage],
        }
        ledger: dict[str, str] = {
            "ledger_event_id": "SR-001",
            "event_type": "source_replacement_required",
            "source_key": "deficient",
            "replacement_source_key": "reserve",
            "sampling_stratum": "Fixture::preprint",
            "reason_code": "SOURCE_REPLACED",
            "reason_detail": "fixture_deficiency",
            "eligible_c2_count": "1",
            "eligible_c5_count": "0",
            "required_claims": "1",
            "source_selection_rank": "1",
            "recorded_utc": "2026-07-15T00:01:00Z",
            "record_sha256": "",
        }
        ledger["record_sha256"] = canonical_json_sha256(
            {
                field: ledger[field]
                for field in LEDGER_HEADER
                if field != "record_sha256"
            }
        )
        retained_before = next(
            row for row in human if row["candidate_claim_id"] == "H3-002-01"
        )
        result = build_outputs(
            frame,
            deterministic,
            human,
            [ledger],
            screen_summary,
            text_root,
            "2026-07-15T00:02:00Z",
            expected_active_sources=2,
        )
        retained_after = next(
            row
            for row in result["human_rows"]
            if row["candidate_claim_id"] == "H3-002-01"
        )
        if retained_after != retained_before:
            raise AssertionError("self-test changed retained human row")
        new_rows = [
            row
            for row in result["human_rows"]
            if str(row["candidate_claim_id"]).startswith("H3R-")
        ]
        if (
            not new_rows
            or any(
                row["selection_status"] != "awaiting_human_sampling_screen"
                or row["human_sampling_eligibility"]
                for row in new_rows
            )
            or result["screen_summary"]["status"] != SCREEN_STATUS
        ):
            raise AssertionError("self-test replacement initialization failed")
        first_screened_human = [dict(row) for row in result["human_rows"]]
        for row in first_screened_human:
            if row["selection_status"] == "awaiting_human_sampling_screen":
                row["human_sampling_reviewer_1_id"] = "screen-1"
                row["human_sampling_reviewer_2_id"] = "screen-2"
                row["human_sampling_eligibility"] = "eligible_c2"
                row["human_sampling_stratum"] = "c2_decisive"
                row["selection_status"] = "human_screen_consensus"
        first_screened_text = serialize_csv(
            MODEL_PRESCREEN_HEADER, first_screened_human
        )
        completed_screen_summary = json.loads(
            serialize_json(result["screen_summary"])
        )
        append_stage(
            completed_screen_summary,
            "build_replacement",
            "2026-07-15T00:03:00Z",
            [
                artifact(
                    "candidate_claims_model_prescreen.csv",
                    result["texts"]["human"],
                    len(result["human_rows"]),
                )
            ],
            [
                artifact(
                    "replacement_initial_screener_1.csv",
                    "fixture packet 1\n",
                    len(new_rows),
                ),
                artifact(
                    "replacement_initial_screener_2.csv",
                    "fixture packet 2\n",
                    len(new_rows),
                ),
            ],
            {
                "replacement_batch_number": 1,
                "test_outcomes_generated": 0,
            },
            ["screen-1", "screen-2", "screen-3"],
            result["texts"]["human"],
            len(result["human_rows"]),
            "replacement_packets_built_awaiting_responses",
            False,
        )
        append_stage(
            completed_screen_summary,
            "merge_replacement_initial",
            "2026-07-15T00:04:00Z",
            [
                artifact(
                    "candidate_claims_model_prescreen.csv",
                    result["texts"]["human"],
                    len(result["human_rows"]),
                )
            ],
            [
                artifact(
                    "candidate_claims_model_prescreen.csv",
                    first_screened_text,
                    len(first_screened_human),
                )
            ],
            {
                "replacement_batch_number": 1,
                "test_outcomes_generated": 0,
            },
            ["screen-1", "screen-2", "screen-3"],
            first_screened_text,
            len(first_screened_human),
            "human_sampling_screen_complete",
            True,
        )
        ledger_2 = {
            "ledger_event_id": "SR-002",
            "event_type": "source_replacement_required",
            "source_key": "reserve",
            "replacement_source_key": "reserve2",
            "sampling_stratum": "Fixture::preprint",
            "reason_code": "SOURCE_REPLACED",
            "reason_detail": "fixture_second_deficiency",
            "eligible_c2_count": "1",
            "eligible_c5_count": "0",
            "required_claims": "1",
            "source_selection_rank": "1",
            "recorded_utc": "2026-07-15T00:05:00Z",
            "record_sha256": "",
        }
        ledger_2["record_sha256"] = canonical_json_sha256(
            {
                field: ledger_2[field]
                for field in LEDGER_HEADER
                if field != "record_sha256"
            }
        )
        retained_before_second = [
            dict(row)
            for row in first_screened_human
            if row["source_key"] == "retained"
        ]
        second = build_outputs(
            result["frame_rows"],
            result["deterministic_rows"],
            first_screened_human,
            [ledger_2],
            completed_screen_summary,
            text_root,
            "2026-07-15T00:06:00Z",
            expected_active_sources=2,
            all_ledger_rows=[ledger, ledger_2],
            prior_replacement_summary=result["replacement_summary"],
            prior_replacement_summary_text=result["texts"][
                "replacement_summary"
            ],
        )
        retained_after_second = [
            row
            for row in second["human_rows"]
            if row["source_key"] == "retained"
        ]
        if retained_after_second != retained_before_second:
            raise AssertionError("second batch changed retained IDs/votes")
        if (
            second["replacement_summary"]["batches"][0]
            != result["replacement_summary"]["batches"][0]
            or second["replacement_summary"]["current_batch_id"] != "RB-002"
            or any(
                row["source_key"] == "reserve"
                for row in second["deterministic_rows"]
            )
            or not any(
                str(row["candidate_claim_id"]).startswith("H3R-002-")
                for row in second["deterministic_rows"]
            )
        ):
            raise AssertionError("second replacement batch is not append-only")
        verify_replacement_chain(
            second["replacement_summary"],
            {
                "frame_rows": second["frame_rows"],
                "deterministic_rows": second["deterministic_rows"],
                "human_rows": second["human_rows"],
                "ledger_rows": [ledger, ledger_2],
                "screen_summary": second["screen_summary"],
            },
            expected_sources=2,
            text_root=text_root,
        )
    finally:
        shutil.rmtree(workspace)
    print(
        "self-test passed; two replacement batches retained prior IDs/votes "
        "and fixture was removed"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--source-frame",
        type=Path,
        default=PACKAGE / "source_sampling_frame.csv",
    )
    parser.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    parser.add_argument(
        "--human-screened-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=PACKAGE / "sampling_exclusion_replacement_ledger.csv",
    )
    parser.add_argument(
        "--screen-summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    parser.add_argument(
        "--replacement-summary",
        type=Path,
        default=PACKAGE / "source_replacement_summary.json",
    )
    parser.add_argument("--text-root", type=Path, default=TEXT_ROOT)
    parser.add_argument("--recorded-utc")
    parser.add_argument("--expected-sources", type=int, default=80)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.check and not args.recorded_utc:
        raise ValueError("--recorded-utc is required when applying replacements")
    result = command_apply(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
