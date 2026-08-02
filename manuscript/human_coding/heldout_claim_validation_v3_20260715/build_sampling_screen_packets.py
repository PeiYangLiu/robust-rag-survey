#!/usr/bin/env python3
"""Build and merge blinded, model-free human sampling-screen packets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from prepare_candidate_pool import (
    CANDIDATE_HEADER as DETERMINISTIC_HEADER,
    MODEL_PRESCREEN_HEADER,
)


PACKAGE = Path(__file__).resolve().parent
SUMMARY_SCHEMA_VERSION = "sampling-screen-v1"
MODEL_FREE_SCREENING_STATUS = (
    "MODEL_FREE_SCREENING_INPUT_NOT_MODEL_OR_HUMAN_LABEL"
)
PROHIBITED_USE = (
    "Sampling eligibility votes are administrative inclusion decisions, not "
    "test outcomes, evidence-support labels, comparability labels, model "
    "labels, gold labels, or adjudications."
)
VOTES = frozenset({"eligible_c2", "eligible_c5", "ineligible"})
MODEL_FIELDS = (
    "prescreen_system",
    "prescreen_system_version",
    "prescreen_prompt_sha256",
    "prescreen_seed",
    "prescreen_c2_decisive_probability",
    "prescreen_c5_decisive_probability",
    "prescreen_rationale",
)
HUMAN_FIELDS = (
    "human_sampling_reviewer_1_id",
    "human_sampling_reviewer_2_id",
    "human_sampling_tiebreak_reviewer_id",
    "human_sampling_eligibility",
    "human_sampling_stratum",
    "exclusion_reason_code",
    "exclusion_reason_detail",
    "deterministic_claim_rank",
)
SCREEN_RESPONSE_HEADER = (
    "candidate_claim_id",
    "source_key",
    "source_title",
    "source_url_or_doi",
    "source_section",
    "source_locator",
    "claim_text",
    "context_before",
    "context_after",
    "source_evidence_excerpt",
    "source_file_sha256",
    "candidate_record_sha256",
    "packet_role",
    "sampling_screener_id",
    "eligibility_vote",
    "screening_reason",
    "source_checked",
    "response_completed_utc",
)


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


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_screener_id(screener_id: str, role: str) -> str:
    cleaned = screener_id.strip()
    if not cleaned or any(character in cleaned for character in "\r\n,"):
        raise ValueError(f"{role} must be a nonempty anonymous ID without comma/newline")
    return cleaned


def load_deterministic(path: Path) -> list[dict[str, str]]:
    header, rows = read_csv(path)
    if header != DETERMINISTIC_HEADER:
        raise ValueError("deterministic candidate schema mismatch")
    ids = [(row.get("candidate_claim_id") or "").strip() for row in rows]
    if not rows or "" in ids or len(ids) != len(set(ids)):
        raise ValueError("deterministic candidates require unique nonempty IDs")
    return rows


def load_screening_candidates(path: Path) -> list[dict[str, str]]:
    header, rows = read_csv(path)
    if header != MODEL_PRESCREEN_HEADER:
        raise ValueError("sampling candidate schema mismatch")
    ids = [(row.get("candidate_claim_id") or "").strip() for row in rows]
    if not rows or "" in ids or len(ids) != len(set(ids)):
        raise ValueError("sampling candidates require unique nonempty IDs")
    return rows


def validate_raw_candidate_link(
    deterministic_rows: Sequence[Mapping[str, str]],
    candidate_rows: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    deterministic_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row
        for row in deterministic_rows
    }
    candidate_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row
        for row in candidate_rows
    }
    if set(deterministic_by_id) != set(candidate_by_id):
        raise ValueError(
            "sampling candidate file must exactly cover deterministic candidates"
        )
    links = {
        "source_key": "source_key",
        "claim_text": "exact_quote",
        "context_before": "context_before",
        "context_after": "context_after",
        "source_section": "source_section",
        "source_url_or_doi": "source_url_or_doi",
        "source_evidence_excerpt": "exact_quote",
        "source_file_sha256": "source_text_sha256",
        "candidate_extraction_method": "extraction_method",
    }
    for candidate_id, deterministic in deterministic_by_id.items():
        candidate = candidate_by_id[candidate_id]
        for candidate_field, deterministic_field in links.items():
            if (candidate.get(candidate_field) or "").strip() != (
                deterministic.get(deterministic_field) or ""
            ).strip():
                raise ValueError(
                    f"{candidate_id} changed raw field {candidate_field}"
                )
        expected_locator = f"PDF page {(deterministic.get('pdf_page') or '').strip()}"
        if (candidate.get("source_locator") or "").strip() != expected_locator:
            raise ValueError(f"{candidate_id} changed raw source locator")
    return deterministic_by_id


def initialize_rows(
    deterministic_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for deterministic in deterministic_rows:
        output.append(
            {
                "candidate_claim_id": deterministic["candidate_claim_id"],
                "source_key": deterministic["source_key"],
                "claim_text": deterministic["exact_quote"],
                "context_before": deterministic["context_before"],
                "context_after": deterministic["context_after"],
                "source_section": deterministic["source_section"],
                "source_locator": f"PDF page {deterministic['pdf_page']}",
                "source_url_or_doi": deterministic["source_url_or_doi"],
                "source_evidence_excerpt": deterministic["exact_quote"],
                "source_file_sha256": deterministic["source_text_sha256"],
                "candidate_extraction_method": deterministic["extraction_method"],
                "prescreen_system": "",
                "prescreen_system_version": "",
                "prescreen_prompt_sha256": "",
                "prescreen_seed": "",
                "prescreen_c2_decisive_probability": "",
                "prescreen_c5_decisive_probability": "",
                "prescreen_rationale": "",
                "model_only_status": MODEL_FREE_SCREENING_STATUS,
                "human_sampling_reviewer_1_id": "",
                "human_sampling_reviewer_2_id": "",
                "human_sampling_tiebreak_reviewer_id": "",
                "human_sampling_eligibility": "",
                "human_sampling_stratum": "",
                "selection_status": "awaiting_human_sampling_screen",
                "exclusion_reason_code": "",
                "exclusion_reason_detail": "",
                "deterministic_claim_rank": "",
            }
        )
    return output


def packet_raw_row(
    deterministic: Mapping[str, str],
    packet_role: str,
    screener_id: str,
) -> dict[str, str]:
    return {
        "candidate_claim_id": deterministic["candidate_claim_id"],
        "source_key": deterministic["source_key"],
        "source_title": deterministic["source_title"],
        "source_url_or_doi": deterministic["source_url_or_doi"],
        "source_section": deterministic["source_section"],
        "source_locator": f"PDF page {deterministic['pdf_page']}",
        "claim_text": deterministic["exact_quote"],
        "context_before": deterministic["context_before"],
        "context_after": deterministic["context_after"],
        "source_evidence_excerpt": deterministic["exact_quote"],
        "source_file_sha256": deterministic["source_text_sha256"],
        "candidate_record_sha256": deterministic["candidate_record_sha256"],
        "packet_role": packet_role,
        "sampling_screener_id": screener_id,
        "eligibility_vote": "",
        "screening_reason": "",
        "source_checked": "",
        "response_completed_utc": "",
    }


def assert_model_free_initialized(
    candidate_rows: Sequence[Mapping[str, str]],
) -> None:
    for row in candidate_rows:
        candidate_id = (row.get("candidate_claim_id") or "").strip()
        if (row.get("model_only_status") or "").strip() != MODEL_FREE_SCREENING_STATUS:
            raise ValueError(
                f"{candidate_id} is not an initialized model-free screening row"
            )
        if any((row.get(field) or "").strip() for field in MODEL_FIELDS):
            raise ValueError(f"{candidate_id} contains a model field")
        if any((row.get(field) or "").strip() for field in HUMAN_FIELDS):
            raise ValueError(f"{candidate_id} contains a prefilled human field")
        if (row.get("selection_status") or "").strip() != (
            "awaiting_human_sampling_screen"
        ):
            raise ValueError(f"{candidate_id} is not awaiting initial screening")


def artifact(name: str, content: str, rows: int) -> dict[str, object]:
    return {
        "artifact": name,
        "sha256": sha256_text(content),
        "rows": rows,
    }


def read_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"sampling screen summary does not exist: {path}")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid sampling screen summary: {exc}") from exc
    if summary.get("schema_version") != SUMMARY_SCHEMA_VERSION:
        raise ValueError("sampling screen summary schema version mismatch")
    if summary.get("prohibited_use") != PROHIBITED_USE:
        raise ValueError("sampling screen summary lacks the prohibited-use statement")
    if not isinstance(summary.get("stages"), list):
        raise ValueError("sampling screen summary stages must be a list")
    return summary


def require_current_summary(
    summary: Mapping[str, Any],
    candidate_text: str,
    candidate_count: int,
    allowed_states: set[str],
) -> None:
    current = summary.get("current_candidate_state")
    if not isinstance(current, dict):
        raise ValueError("sampling screen summary lacks current candidate state")
    if (
        current.get("sha256") != sha256_text(candidate_text)
        or current.get("rows") != candidate_count
    ):
        raise ValueError("sampling screen summary does not match current candidates")
    if summary.get("status") not in allowed_states:
        raise ValueError(
            f"sampling screen summary is in unexpected state {summary.get('status')}"
        )


def append_stage(
    summary: dict[str, Any],
    stage: str,
    recorded_utc: str,
    inputs: Sequence[Mapping[str, object]],
    outputs: Sequence[Mapping[str, object]],
    counts: Mapping[str, int],
    screener_ids: Sequence[str],
    candidate_text: str,
    candidate_rows: int,
    status: str,
    screening_complete: bool,
) -> None:
    if not recorded_utc.strip():
        raise ValueError("--recorded-utc is required")
    stage_record: dict[str, Any] = {
        "stage": stage,
        "recorded_utc": recorded_utc.strip(),
        "inputs": list(inputs),
        "outputs": list(outputs),
        "counts": dict(counts),
        "screener_ids": list(screener_ids),
    }
    stage_record["stage_record_sha256"] = canonical_json_sha256(stage_record)
    summary["stages"].append(stage_record)
    summary["status"] = status
    summary["screening_complete"] = screening_complete
    summary["current_candidate_state"] = {
        "artifact": "candidate_claims_model_prescreen.csv",
        "sha256": sha256_text(candidate_text),
        "rows": candidate_rows,
    }


def new_summary() -> dict[str, Any]:
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "",
        "screening_complete": False,
        "prohibited_use": PROHIBITED_USE,
        "current_candidate_state": {},
        "stages": [],
    }


def write_summary(path: Path, summary: Mapping[str, Any]) -> None:
    write_atomic(
        path,
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def validate_packet_raw(
    row: Mapping[str, str],
    deterministic: Mapping[str, str],
    packet_role: str,
    screener_id: str,
    row_number: int,
) -> None:
    expected = packet_raw_row(deterministic, packet_role, screener_id)
    for field in SCREEN_RESPONSE_HEADER[:14]:
        if (row.get(field) or "").strip() != expected[field].strip():
            raise ValueError(
                f"response row {row_number} changed packet field {field}"
            )


def read_completed_packet(
    path: Path,
    deterministic_by_id: Mapping[str, Mapping[str, str]],
    expected_ids: set[str],
    packet_role: str,
    expected_screener_id: str | None = None,
) -> tuple[str, dict[str, dict[str, str]]]:
    header, rows = read_csv(path)
    if header != SCREEN_RESPONSE_HEADER:
        raise ValueError(f"{path} has an invalid screening response schema")
    ids = [(row.get("candidate_claim_id") or "").strip() for row in rows]
    if set(ids) != expected_ids or len(ids) != len(set(ids)):
        raise ValueError(f"{path} does not exactly cover its assigned candidates")
    screener_ids = {
        (row.get("sampling_screener_id") or "").strip() for row in rows
    }
    if len(screener_ids) != 1:
        raise ValueError(f"{path} must contain exactly one sampling screener ID")
    screener_id = validate_screener_id(next(iter(screener_ids)), "screener ID")
    if expected_screener_id is not None and screener_id != expected_screener_id:
        raise ValueError(f"{path} has the wrong sampling screener ID")
    by_id: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        candidate_id = (row.get("candidate_claim_id") or "").strip()
        validate_packet_raw(
            row,
            deterministic_by_id[candidate_id],
            packet_role,
            screener_id,
            row_number,
        )
        vote = (row.get("eligibility_vote") or "").strip()
        if vote not in VOTES:
            raise ValueError(f"{path}:{row_number} has an invalid eligibility vote")
        if not (row.get("screening_reason") or "").strip():
            raise ValueError(f"{path}:{row_number} lacks a screening reason")
        if (row.get("source_checked") or "").strip().lower() != "yes":
            raise ValueError(f"{path}:{row_number} must record source_checked=yes")
        if not (row.get("response_completed_utc") or "").strip():
            raise ValueError(f"{path}:{row_number} lacks response_completed_utc")
        by_id[candidate_id] = row
    return screener_id, by_id


def set_aggregated_vote(
    candidate: dict[str, str],
    vote: str,
    reviewer_1: str,
    reviewer_2: str,
    tiebreak: str,
    status: str,
    reasons: Mapping[str, str],
) -> None:
    candidate["human_sampling_reviewer_1_id"] = reviewer_1
    candidate["human_sampling_reviewer_2_id"] = reviewer_2
    candidate["human_sampling_tiebreak_reviewer_id"] = tiebreak
    candidate["human_sampling_eligibility"] = vote
    candidate["human_sampling_stratum"] = {
        "eligible_c2": "c2_decisive",
        "eligible_c5": "c5_decisive",
        "ineligible": "",
    }[vote]
    candidate["selection_status"] = status
    if vote == "ineligible":
        candidate["exclusion_reason_code"] = (
            "NOT_DECISIVE_AFTER_HUMAN_SCREEN"
        )
        candidate["exclusion_reason_detail"] = json.dumps(
            dict(reasons),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        candidate["exclusion_reason_code"] = ""
        candidate["exclusion_reason_detail"] = ""


def command_initialize(args: argparse.Namespace) -> dict[str, Any]:
    deterministic_rows = load_deterministic(args.deterministic_candidates)
    candidate_rows = initialize_rows(deterministic_rows)
    candidate_text = serialize_csv(MODEL_PRESCREEN_HEADER, candidate_rows)
    if args.output.exists():
        existing_header, existing_rows = read_csv(args.output)
        if existing_header != MODEL_PRESCREEN_HEADER:
            raise ValueError("existing sampling candidate schema mismatch")
        if existing_rows and args.output.read_text(encoding="utf-8") != candidate_text:
            raise ValueError(
                "initialize refuses to overwrite non-identical populated candidates"
            )
    if args.summary.exists():
        existing_summary = read_summary(args.summary)
        if existing_summary.get("status") not in {
            "initialized_model_free_awaiting_initial_packets"
        }:
            raise ValueError(
                "initialize refuses to reset a screening workflow already in progress"
            )
    deterministic_text = args.deterministic_candidates.read_text(encoding="utf-8")
    summary = new_summary()
    append_stage(
        summary,
        "initialize",
        args.recorded_utc,
        [
            artifact(
                "candidate_claims_deterministic.csv",
                deterministic_text,
                len(deterministic_rows),
            )
        ],
        [
            artifact(
                "candidate_claims_model_prescreen.csv",
                candidate_text,
                len(candidate_rows),
            )
        ],
        {
            "deterministic_candidates": len(deterministic_rows),
            "initialized_model_free_candidates": len(candidate_rows),
            "model_fields_populated": 0,
            "human_sampling_fields_populated": 0,
            "test_outcomes_generated": 0,
        },
        [],
        candidate_text,
        len(candidate_rows),
        "initialized_model_free_awaiting_initial_packets",
        False,
    )
    write_atomic(args.output, candidate_text)
    write_summary(args.summary, summary)
    return {
        "status": summary["status"],
        "candidates": len(candidate_rows),
        "candidate_sha256": sha256_text(candidate_text),
        "test_outcomes_generated": 0,
    }


def command_build_initial(args: argparse.Namespace) -> dict[str, Any]:
    screener_1 = validate_screener_id(args.screener_1_id, "screener 1 ID")
    screener_2 = validate_screener_id(args.screener_2_id, "screener 2 ID")
    if screener_1 == screener_2:
        raise ValueError("initial sampling screener IDs must differ")
    deterministic_rows = load_deterministic(args.deterministic_candidates)
    candidate_rows = load_screening_candidates(args.candidates)
    deterministic_by_id = validate_raw_candidate_link(
        deterministic_rows, candidate_rows
    )
    assert_model_free_initialized(candidate_rows)
    candidate_text = args.candidates.read_text(encoding="utf-8")
    summary = read_summary(args.summary)
    require_current_summary(
        summary,
        candidate_text,
        len(candidate_rows),
        {"initialized_model_free_awaiting_initial_packets"},
    )
    packet_1 = [
        packet_raw_row(deterministic_by_id[row["candidate_claim_id"]], "initial", screener_1)
        for row in candidate_rows
    ]
    packet_2 = [
        packet_raw_row(deterministic_by_id[row["candidate_claim_id"]], "initial", screener_2)
        for row in candidate_rows
    ]
    packet_1_text = serialize_csv(SCREEN_RESPONSE_HEADER, packet_1)
    packet_2_text = serialize_csv(SCREEN_RESPONSE_HEADER, packet_2)
    output_1 = args.output_dir / "initial_screener_1.csv"
    output_2 = args.output_dir / "initial_screener_2.csv"
    append_stage(
        summary,
        "build_initial",
        args.recorded_utc,
        [
            artifact(
                "candidate_claims_deterministic.csv",
                args.deterministic_candidates.read_text(encoding="utf-8"),
                len(deterministic_rows),
            ),
            artifact(
                "candidate_claims_model_prescreen.csv",
                candidate_text,
                len(candidate_rows),
            )
        ],
        [
            artifact("initial_screener_1.csv", packet_1_text, len(packet_1)),
            artifact("initial_screener_2.csv", packet_2_text, len(packet_2)),
        ],
        {
            "candidates_per_initial_screener": len(candidate_rows),
            "initial_screeners": 2,
            "test_outcomes_generated": 0,
        },
        [screener_1, screener_2],
        candidate_text,
        len(candidate_rows),
        "initial_packets_built_awaiting_responses",
        False,
    )
    write_atomic(output_1, packet_1_text)
    write_atomic(output_2, packet_2_text)
    write_summary(args.summary, summary)
    return {
        "status": summary["status"],
        "candidates_per_screener": len(candidate_rows),
        "packet_1": str(output_1),
        "packet_2": str(output_2),
        "test_outcomes_generated": 0,
    }


def command_merge_initial(args: argparse.Namespace) -> dict[str, Any]:
    tiebreak_id = validate_screener_id(
        args.tiebreak_screener_id, "tiebreak screener ID"
    )
    deterministic_rows = load_deterministic(args.deterministic_candidates)
    candidate_rows = load_screening_candidates(args.candidates)
    deterministic_by_id = validate_raw_candidate_link(
        deterministic_rows, candidate_rows
    )
    assert_model_free_initialized(candidate_rows)
    candidate_text_before = args.candidates.read_text(encoding="utf-8")
    summary = read_summary(args.summary)
    require_current_summary(
        summary,
        candidate_text_before,
        len(candidate_rows),
        {"initial_packets_built_awaiting_responses"},
    )
    last_stage = summary["stages"][-1]
    expected_initial_ids = last_stage.get("screener_ids")
    if (
        last_stage.get("stage") != "build_initial"
        or not isinstance(expected_initial_ids, list)
        or len(expected_initial_ids) != 2
    ):
        raise ValueError("sampling summary lacks the issued initial packet record")
    expected_ids = {
        (row.get("candidate_claim_id") or "").strip() for row in candidate_rows
    }
    screener_1, responses_1 = read_completed_packet(
        args.response_1,
        deterministic_by_id,
        expected_ids,
        "initial",
        str(expected_initial_ids[0]),
    )
    screener_2, responses_2 = read_completed_packet(
        args.response_2,
        deterministic_by_id,
        expected_ids,
        "initial",
        str(expected_initial_ids[1]),
    )
    if len({screener_1, screener_2, tiebreak_id}) != 3:
        raise ValueError("all three sampling screener IDs must be distinct")

    merged = [dict(row) for row in candidate_rows]
    merged_by_id = {row["candidate_claim_id"]: row for row in merged}
    disputed_ids: list[str] = []
    vote_pairs: Counter[str] = Counter()
    for candidate_id in sorted(expected_ids):
        response_1 = responses_1[candidate_id]
        response_2 = responses_2[candidate_id]
        vote_1 = response_1["eligibility_vote"].strip()
        vote_2 = response_2["eligibility_vote"].strip()
        vote_pairs[f"{vote_1}|{vote_2}"] += 1
        candidate = merged_by_id[candidate_id]
        if vote_1 == vote_2:
            set_aggregated_vote(
                candidate,
                vote_1,
                screener_1,
                screener_2,
                "",
                "human_screen_consensus",
                {
                    "reviewer_1_reason": response_1["screening_reason"].strip(),
                    "reviewer_2_reason": response_2["screening_reason"].strip(),
                },
            )
        else:
            candidate["human_sampling_reviewer_1_id"] = screener_1
            candidate["human_sampling_reviewer_2_id"] = screener_2
            candidate["human_sampling_tiebreak_reviewer_id"] = ""
            candidate["human_sampling_eligibility"] = ""
            candidate["human_sampling_stratum"] = ""
            candidate["selection_status"] = "awaiting_human_sampling_tiebreak"
            candidate["exclusion_reason_code"] = ""
            candidate["exclusion_reason_detail"] = ""
            disputed_ids.append(candidate_id)

    tiebreak_rows = [
        packet_raw_row(
            deterministic_by_id[candidate_id],
            "tiebreak",
            tiebreak_id,
        )
        for candidate_id in disputed_ids
    ]
    merged_text = serialize_csv(MODEL_PRESCREEN_HEADER, merged)
    tiebreak_text = serialize_csv(SCREEN_RESPONSE_HEADER, tiebreak_rows)
    screening_complete = not disputed_ids
    status = (
        "human_sampling_screen_complete"
        if screening_complete
        else "awaiting_tiebreak"
    )
    append_stage(
        summary,
        "merge_initial",
        args.recorded_utc,
        [
            artifact(
                "candidate_claims_deterministic.csv",
                args.deterministic_candidates.read_text(encoding="utf-8"),
                len(deterministic_rows),
            ),
            artifact(
                "candidate_claims_model_prescreen.csv",
                candidate_text_before,
                len(candidate_rows),
            ),
            artifact(
                "completed_initial_screener_1.csv",
                args.response_1.read_text(encoding="utf-8"),
                len(responses_1),
            ),
            artifact(
                "completed_initial_screener_2.csv",
                args.response_2.read_text(encoding="utf-8"),
                len(responses_2),
            ),
        ],
        [
            artifact(
                "candidate_claims_model_prescreen.csv",
                merged_text,
                len(merged),
            ),
            artifact(
                "tiebreak_disputes.csv",
                tiebreak_text,
                len(tiebreak_rows),
            ),
        ],
        {
            "initial_agreements": len(candidate_rows) - len(disputed_ids),
            "initial_disputes": len(disputed_ids),
            "tiebreak_rows": len(tiebreak_rows),
            "test_outcomes_generated": 0,
            **{
                f"vote_pair_{key.replace('|', '_')}": value
                for key, value in sorted(vote_pairs.items())
            },
        },
        [screener_1, screener_2, tiebreak_id],
        merged_text,
        len(merged),
        status,
        screening_complete,
    )
    write_atomic(args.output, merged_text)
    write_atomic(args.tiebreak_output, tiebreak_text)
    write_summary(args.summary, summary)
    return {
        "status": status,
        "initial_agreements": len(candidate_rows) - len(disputed_ids),
        "initial_disputes": len(disputed_ids),
        "tiebreak_packet": str(args.tiebreak_output),
        "test_outcomes_generated": 0,
    }


def command_merge_tiebreak(args: argparse.Namespace) -> dict[str, Any]:
    deterministic_rows = load_deterministic(args.deterministic_candidates)
    candidate_rows = load_screening_candidates(args.candidates)
    deterministic_by_id = validate_raw_candidate_link(
        deterministic_rows, candidate_rows
    )
    candidate_text_before = args.candidates.read_text(encoding="utf-8")
    summary = read_summary(args.summary)
    require_current_summary(
        summary,
        candidate_text_before,
        len(candidate_rows),
        {"awaiting_tiebreak"},
    )
    last_stage = summary["stages"][-1]
    screener_ids = last_stage.get("screener_ids")
    if (
        last_stage.get("stage") != "merge_initial"
        or not isinstance(screener_ids, list)
        or len(screener_ids) != 3
        or len(set(screener_ids)) != 3
    ):
        raise ValueError("sampling summary lacks three distinct screener IDs")
    disputed_ids = {
        (row.get("candidate_claim_id") or "").strip()
        for row in candidate_rows
        if (row.get("selection_status") or "").strip()
        == "awaiting_human_sampling_tiebreak"
    }
    if not disputed_ids:
        raise ValueError("there are no disputed candidates to merge")
    for row in candidate_rows:
        status = (row.get("selection_status") or "").strip()
        if status not in {
            "human_screen_consensus",
            "awaiting_human_sampling_tiebreak",
        }:
            raise ValueError("candidate file is not a merge-initial output")
    tiebreak_id, responses = read_completed_packet(
        args.tiebreak_response,
        deterministic_by_id,
        disputed_ids,
        "tiebreak",
        str(screener_ids[2]),
    )
    reviewer_1, reviewer_2 = str(screener_ids[0]), str(screener_ids[1])
    if len({reviewer_1, reviewer_2, tiebreak_id}) != 3:
        raise ValueError("all three sampling screener IDs must be distinct")

    merged = [dict(row) for row in candidate_rows]
    merged_by_id = {row["candidate_claim_id"]: row for row in merged}
    vote_counts: Counter[str] = Counter()
    for candidate_id in sorted(disputed_ids):
        response = responses[candidate_id]
        vote = response["eligibility_vote"].strip()
        vote_counts[vote] += 1
        candidate = merged_by_id[candidate_id]
        if (
            candidate["human_sampling_reviewer_1_id"] != reviewer_1
            or candidate["human_sampling_reviewer_2_id"] != reviewer_2
        ):
            raise ValueError(f"{candidate_id} changed its initial screener IDs")
        set_aggregated_vote(
            candidate,
            vote,
            reviewer_1,
            reviewer_2,
            tiebreak_id,
            "human_screen_tiebreak",
            {"tiebreak_reason": response["screening_reason"].strip()},
        )
    if any(
        row["selection_status"]
        not in {"human_screen_consensus", "human_screen_tiebreak"}
        for row in merged
    ):
        raise AssertionError("tiebreak merge did not complete every candidate")
    merged_text = serialize_csv(MODEL_PRESCREEN_HEADER, merged)
    final_votes = Counter(row["human_sampling_eligibility"] for row in merged)
    append_stage(
        summary,
        "merge_tiebreak",
        args.recorded_utc,
        [
            artifact(
                "candidate_claims_deterministic.csv",
                args.deterministic_candidates.read_text(encoding="utf-8"),
                len(deterministic_rows),
            ),
            artifact(
                "candidate_claims_model_prescreen.csv",
                candidate_text_before,
                len(candidate_rows),
            ),
            artifact(
                "completed_tiebreak_disputes.csv",
                args.tiebreak_response.read_text(encoding="utf-8"),
                len(responses),
            ),
        ],
        [
            artifact(
                "candidate_claims_model_prescreen.csv",
                merged_text,
                len(merged),
            )
        ],
        {
            "tiebreak_rows": len(responses),
            "final_eligible_c2": final_votes["eligible_c2"],
            "final_eligible_c5": final_votes["eligible_c5"],
            "final_ineligible": final_votes["ineligible"],
            "test_outcomes_generated": 0,
            **{
                f"tiebreak_vote_{key}": value
                for key, value in sorted(vote_counts.items())
            },
        },
        [reviewer_1, reviewer_2, tiebreak_id],
        merged_text,
        len(merged),
        "human_sampling_screen_complete",
        True,
    )
    write_atomic(args.output, merged_text)
    write_summary(args.summary, summary)
    return {
        "status": summary["status"],
        "tiebreak_rows": len(responses),
        "final_vote_counts": dict(final_votes),
        "test_outcomes_generated": 0,
    }


def original_screener_ids(summary: Mapping[str, Any]) -> tuple[str, str, str]:
    initial_ids: list[str] | None = None
    all_ids: list[str] | None = None
    for stage in summary.get("stages", []):
        if not isinstance(stage, dict):
            continue
        stage_name = stage.get("stage")
        ids = stage.get("screener_ids")
        if stage_name == "build_initial" and isinstance(ids, list):
            initial_ids = [str(value) for value in ids]
        if stage_name in {"merge_initial", "merge_tiebreak"} and isinstance(
            ids, list
        ):
            all_ids = [str(value) for value in ids]
    if (
        initial_ids is None
        or all_ids is None
        or len(initial_ids) != 2
        or len(all_ids) != 3
        or all_ids[:2] != initial_ids
        or len(set(all_ids)) != 3
    ):
        raise ValueError("sampling summary lacks the original three screener IDs")
    return all_ids[0], all_ids[1], all_ids[2]


def current_replacement_batch(
    path: Path,
    candidate_rows: Sequence[Mapping[str, str]],
) -> tuple[str, set[str]]:
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read replacement summary: {exc}") from exc
    batches = summary.get("batches")
    current_batch_id = str(summary.get("current_batch_id", "")).strip()
    if (
        not isinstance(batches, list)
        or not batches
        or not isinstance(batches[-1], dict)
        or batches[-1].get("batch_id") != current_batch_id
    ):
        raise ValueError("replacement summary current batch is invalid")
    current_batch = batches[-1]
    if current_batch.get("batch_record_sha256") != canonical_json_sha256(
        {
            key: value
            for key, value in current_batch.items()
            if key != "batch_record_sha256"
        }
    ):
        raise ValueError("replacement summary current batch hash is invalid")
    replacements = current_batch.get("replacements")
    if not isinstance(replacements, list) or not replacements:
        raise ValueError("replacement summary current batch has no rows")
    expected: set[str] = set()
    expected_sources: dict[str, str] = {}
    for replacement in replacements:
        if not isinstance(replacement, dict):
            raise ValueError("replacement summary record is invalid")
        prefix = str(replacement.get("new_id_prefix", "")).strip()
        source_key = str(
            replacement.get("replacement_source_key", "")
        ).strip()
        count = int(replacement.get("new_candidates", 0))
        if not prefix.startswith("H3R-") or not source_key or count < 1:
            raise ValueError("replacement summary namespace/count is invalid")
        for rank in range(1, count + 1):
            candidate_id = f"{prefix}{rank:02d}"
            expected.add(candidate_id)
            expected_sources[candidate_id] = source_key
    actual_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row
        for row in candidate_rows
    }
    if not expected or not expected.issubset(actual_by_id):
        raise ValueError("current replacement candidates are incomplete")
    for candidate_id in expected:
        if (
            actual_by_id[candidate_id].get("source_key") or ""
        ).strip() != expected_sources[candidate_id]:
            raise ValueError(
                f"current replacement source changed for {candidate_id}"
            )
    return current_batch_id, expected


def replacement_subset_ids(
    candidate_rows: Sequence[Mapping[str, str]],
    allowed_statuses: set[str],
    target_ids: set[str],
) -> set[str]:
    if not target_ids:
        raise ValueError("current replacement batch contains no candidates")
    for row in candidate_rows:
        candidate_id = (row.get("candidate_claim_id") or "").strip()
        status = (row.get("selection_status") or "").strip()
        if candidate_id in target_ids:
            if status not in allowed_statuses:
                raise ValueError(
                    f"replacement candidate {candidate_id} has status {status!r}"
                )
        elif status not in {"human_screen_consensus", "human_screen_tiebreak"}:
            raise ValueError(
                f"retained candidate {candidate_id} is not fully screened"
            )
    return target_ids


def retained_rows_snapshot(
    candidate_rows: Sequence[Mapping[str, str]],
    excluded_ids: set[str],
) -> list[dict[str, str]]:
    return [
        dict(row)
        for row in candidate_rows
        if (row.get("candidate_claim_id") or "").strip() not in excluded_ids
    ]


def command_build_replacement(args: argparse.Namespace) -> dict[str, Any]:
    deterministic_rows = load_deterministic(args.deterministic_candidates)
    candidate_rows = load_screening_candidates(args.candidates)
    deterministic_by_id = validate_raw_candidate_link(
        deterministic_rows, candidate_rows
    )
    batch_id, batch_candidate_ids = current_replacement_batch(
        args.replacement_summary, candidate_rows
    )
    replacement_ids = replacement_subset_ids(
        candidate_rows,
        {"awaiting_human_sampling_screen"},
        batch_candidate_ids,
    )
    replacement_rows = [
        row for row in candidate_rows if row["candidate_claim_id"] in replacement_ids
    ]
    assert_model_free_initialized(replacement_rows)
    candidate_text = args.candidates.read_text(encoding="utf-8")
    summary = read_summary(args.summary)
    require_current_summary(
        summary,
        candidate_text,
        len(candidate_rows),
        {"awaiting_replacement_screen"},
    )
    screener_1, screener_2, screener_3 = original_screener_ids(summary)
    packet_1 = [
        packet_raw_row(
            deterministic_by_id[row["candidate_claim_id"]],
            "replacement_initial",
            screener_1,
        )
        for row in replacement_rows
    ]
    packet_2 = [
        packet_raw_row(
            deterministic_by_id[row["candidate_claim_id"]],
            "replacement_initial",
            screener_2,
        )
        for row in replacement_rows
    ]
    packet_1_text = serialize_csv(SCREEN_RESPONSE_HEADER, packet_1)
    packet_2_text = serialize_csv(SCREEN_RESPONSE_HEADER, packet_2)
    output_1 = args.output_dir / f"{batch_id}_replacement_initial_screener_1.csv"
    output_2 = args.output_dir / f"{batch_id}_replacement_initial_screener_2.csv"
    inputs = [
        artifact(
            "candidate_claims_deterministic.csv",
            args.deterministic_candidates.read_text(encoding="utf-8"),
            len(deterministic_rows),
        ),
        artifact(
            "candidate_claims_model_prescreen.csv",
            candidate_text,
            len(candidate_rows),
        ),
    ]
    if args.replacement_summary.exists():
        replacement_summary_text = args.replacement_summary.read_text(
            encoding="utf-8"
        )
        inputs.append(
            artifact(
                "source_replacement_summary.json",
                replacement_summary_text,
                1,
            )
        )
    append_stage(
        summary,
        "build_replacement",
        args.recorded_utc,
        inputs,
        [
            artifact(
                "replacement_initial_screener_1.csv",
                packet_1_text,
                len(packet_1),
            ),
            artifact(
                "replacement_initial_screener_2.csv",
                packet_2_text,
                len(packet_2),
            ),
        ],
        {
            "replacement_candidates_per_initial_screener": len(
                replacement_rows
            ),
            "replacement_batch_number": int(batch_id.split("-")[1]),
            "retained_candidates_not_reissued": len(candidate_rows)
            - len(replacement_rows),
            "test_outcomes_generated": 0,
        },
        [screener_1, screener_2, screener_3],
        candidate_text,
        len(candidate_rows),
        "replacement_packets_built_awaiting_responses",
        False,
    )
    write_atomic(output_1, packet_1_text)
    write_atomic(output_2, packet_2_text)
    write_summary(args.summary, summary)
    return {
        "status": summary["status"],
        "replacement_batch_id": batch_id,
        "replacement_candidates_per_screener": len(replacement_rows),
        "retained_candidates_not_reissued": len(candidate_rows)
        - len(replacement_rows),
        "packet_1": str(output_1),
        "packet_2": str(output_2),
        "test_outcomes_generated": 0,
    }


def command_merge_replacement_initial(
    args: argparse.Namespace,
) -> dict[str, Any]:
    deterministic_rows = load_deterministic(args.deterministic_candidates)
    candidate_rows = load_screening_candidates(args.candidates)
    deterministic_by_id = validate_raw_candidate_link(
        deterministic_rows, candidate_rows
    )
    batch_id, batch_candidate_ids = current_replacement_batch(
        args.replacement_summary, candidate_rows
    )
    replacement_ids = replacement_subset_ids(
        candidate_rows,
        {"awaiting_human_sampling_screen"},
        batch_candidate_ids,
    )
    candidate_text_before = args.candidates.read_text(encoding="utf-8")
    summary = read_summary(args.summary)
    require_current_summary(
        summary,
        candidate_text_before,
        len(candidate_rows),
        {"replacement_packets_built_awaiting_responses"},
    )
    screener_1, screener_2, screener_3 = original_screener_ids(summary)
    last_ids = summary["stages"][-1].get("screener_ids")
    if last_ids != [screener_1, screener_2, screener_3]:
        raise ValueError("replacement packet stage changed screener identities")
    response_id_1, responses_1 = read_completed_packet(
        args.response_1,
        deterministic_by_id,
        replacement_ids,
        "replacement_initial",
        screener_1,
    )
    response_id_2, responses_2 = read_completed_packet(
        args.response_2,
        deterministic_by_id,
        replacement_ids,
        "replacement_initial",
        screener_2,
    )
    if (response_id_1, response_id_2) != (screener_1, screener_2):
        raise AssertionError("validated replacement identities changed")
    retained_before = retained_rows_snapshot(candidate_rows, replacement_ids)
    merged = [dict(row) for row in candidate_rows]
    merged_by_id = {row["candidate_claim_id"]: row for row in merged}
    disputed_ids: list[str] = []
    vote_pairs: Counter[str] = Counter()
    for candidate_id in sorted(replacement_ids):
        response_1 = responses_1[candidate_id]
        response_2 = responses_2[candidate_id]
        vote_1 = response_1["eligibility_vote"].strip()
        vote_2 = response_2["eligibility_vote"].strip()
        vote_pairs[f"{vote_1}|{vote_2}"] += 1
        candidate = merged_by_id[candidate_id]
        if vote_1 == vote_2:
            set_aggregated_vote(
                candidate,
                vote_1,
                screener_1,
                screener_2,
                "",
                "human_screen_consensus",
                {
                    "reviewer_1_reason": response_1["screening_reason"].strip(),
                    "reviewer_2_reason": response_2["screening_reason"].strip(),
                },
            )
        else:
            candidate["human_sampling_reviewer_1_id"] = screener_1
            candidate["human_sampling_reviewer_2_id"] = screener_2
            candidate["human_sampling_tiebreak_reviewer_id"] = ""
            candidate["human_sampling_eligibility"] = ""
            candidate["human_sampling_stratum"] = ""
            candidate["selection_status"] = "awaiting_human_sampling_tiebreak"
            candidate["exclusion_reason_code"] = ""
            candidate["exclusion_reason_detail"] = ""
            disputed_ids.append(candidate_id)
    if retained_rows_snapshot(merged, replacement_ids) != retained_before:
        raise AssertionError("replacement initial merge changed retained votes")
    tiebreak_rows = [
        packet_raw_row(
            deterministic_by_id[candidate_id],
            "replacement_tiebreak",
            screener_3,
        )
        for candidate_id in disputed_ids
    ]
    merged_text = serialize_csv(MODEL_PRESCREEN_HEADER, merged)
    tiebreak_text = serialize_csv(SCREEN_RESPONSE_HEADER, tiebreak_rows)
    screening_complete = not disputed_ids
    status = (
        "human_sampling_screen_complete"
        if screening_complete
        else "awaiting_replacement_tiebreak"
    )
    tiebreak_output = (
        args.tiebreak_output
        if args.tiebreak_output is not None
        else args.candidates.parent
        / "generated_sampling_screen_packets"
        / f"{batch_id}_replacement_tiebreak_disputes.csv"
    )
    append_stage(
        summary,
        "merge_replacement_initial",
        args.recorded_utc,
        [
            artifact(
                "candidate_claims_deterministic.csv",
                args.deterministic_candidates.read_text(encoding="utf-8"),
                len(deterministic_rows),
            ),
            artifact(
                "candidate_claims_model_prescreen.csv",
                candidate_text_before,
                len(candidate_rows),
            ),
            artifact(
                "completed_replacement_initial_screener_1.csv",
                args.response_1.read_text(encoding="utf-8"),
                len(responses_1),
            ),
            artifact(
                "completed_replacement_initial_screener_2.csv",
                args.response_2.read_text(encoding="utf-8"),
                len(responses_2),
            ),
        ],
        [
            artifact(
                "candidate_claims_model_prescreen.csv",
                merged_text,
                len(merged),
            ),
            artifact(
                "replacement_tiebreak_disputes.csv",
                tiebreak_text,
                len(tiebreak_rows),
            ),
        ],
        {
            "replacement_initial_agreements": len(replacement_ids)
            - len(disputed_ids),
            "replacement_initial_disputes": len(disputed_ids),
            "replacement_batch_number": int(batch_id.split("-")[1]),
            "retained_candidates_unchanged": len(retained_before),
            "test_outcomes_generated": 0,
            **{
                f"replacement_vote_pair_{key.replace('|', '_')}": value
                for key, value in sorted(vote_pairs.items())
            },
        },
        [screener_1, screener_2, screener_3],
        merged_text,
        len(merged),
        status,
        screening_complete,
    )
    write_atomic(args.output, merged_text)
    write_atomic(tiebreak_output, tiebreak_text)
    write_summary(args.summary, summary)
    return {
        "status": status,
        "replacement_batch_id": batch_id,
        "replacement_initial_agreements": len(replacement_ids)
        - len(disputed_ids),
        "replacement_initial_disputes": len(disputed_ids),
        "retained_candidates_unchanged": len(retained_before),
        "tiebreak_packet": str(tiebreak_output),
        "test_outcomes_generated": 0,
    }


def command_merge_replacement_tiebreak(
    args: argparse.Namespace,
) -> dict[str, Any]:
    deterministic_rows = load_deterministic(args.deterministic_candidates)
    candidate_rows = load_screening_candidates(args.candidates)
    deterministic_by_id = validate_raw_candidate_link(
        deterministic_rows, candidate_rows
    )
    batch_id, batch_candidate_ids = current_replacement_batch(
        args.replacement_summary, candidate_rows
    )
    all_replacement_ids = replacement_subset_ids(
        candidate_rows,
        {
            "human_screen_consensus",
            "awaiting_human_sampling_tiebreak",
        },
        batch_candidate_ids,
    )
    disputed_ids = {
        candidate_id
        for candidate_id in all_replacement_ids
        if next(
            row
            for row in candidate_rows
            if row["candidate_claim_id"] == candidate_id
        )["selection_status"]
        == "awaiting_human_sampling_tiebreak"
    }
    if not disputed_ids:
        raise ValueError("there are no replacement disputes to merge")
    candidate_text_before = args.candidates.read_text(encoding="utf-8")
    summary = read_summary(args.summary)
    require_current_summary(
        summary,
        candidate_text_before,
        len(candidate_rows),
        {"awaiting_replacement_tiebreak"},
    )
    screener_1, screener_2, screener_3 = original_screener_ids(summary)
    response_id, responses = read_completed_packet(
        args.tiebreak_response,
        deterministic_by_id,
        disputed_ids,
        "replacement_tiebreak",
        screener_3,
    )
    if response_id != screener_3:
        raise AssertionError("validated replacement tiebreak identity changed")
    retained_before = retained_rows_snapshot(
        candidate_rows, all_replacement_ids
    )
    merged = [dict(row) for row in candidate_rows]
    merged_by_id = {row["candidate_claim_id"]: row for row in merged}
    vote_counts: Counter[str] = Counter()
    for candidate_id in sorted(disputed_ids):
        candidate = merged_by_id[candidate_id]
        if (
            candidate["human_sampling_reviewer_1_id"] != screener_1
            or candidate["human_sampling_reviewer_2_id"] != screener_2
        ):
            raise ValueError(
                f"{candidate_id} changed replacement initial screener IDs"
            )
        response = responses[candidate_id]
        vote = response["eligibility_vote"].strip()
        vote_counts[vote] += 1
        set_aggregated_vote(
            candidate,
            vote,
            screener_1,
            screener_2,
            screener_3,
            "human_screen_tiebreak",
            {"tiebreak_reason": response["screening_reason"].strip()},
        )
    if (
        retained_rows_snapshot(merged, all_replacement_ids)
        != retained_before
    ):
        raise AssertionError("replacement tiebreak merge changed retained votes")
    if any(
        row["selection_status"]
        not in {"human_screen_consensus", "human_screen_tiebreak"}
        for row in merged
    ):
        raise AssertionError("replacement tiebreak did not complete screening")
    merged_text = serialize_csv(MODEL_PRESCREEN_HEADER, merged)
    append_stage(
        summary,
        "merge_replacement_tiebreak",
        args.recorded_utc,
        [
            artifact(
                "candidate_claims_deterministic.csv",
                args.deterministic_candidates.read_text(encoding="utf-8"),
                len(deterministic_rows),
            ),
            artifact(
                "candidate_claims_model_prescreen.csv",
                candidate_text_before,
                len(candidate_rows),
            ),
            artifact(
                "completed_replacement_tiebreak_disputes.csv",
                args.tiebreak_response.read_text(encoding="utf-8"),
                len(responses),
            ),
        ],
        [
            artifact(
                "candidate_claims_model_prescreen.csv",
                merged_text,
                len(merged),
            )
        ],
        {
            "replacement_tiebreak_rows": len(responses),
            "replacement_batch_number": int(batch_id.split("-")[1]),
            "retained_candidates_unchanged": len(retained_before),
            "test_outcomes_generated": 0,
            **{
                f"replacement_tiebreak_vote_{key}": value
                for key, value in sorted(vote_counts.items())
            },
        },
        [screener_1, screener_2, screener_3],
        merged_text,
        len(merged),
        "human_sampling_screen_complete",
        True,
    )
    write_atomic(args.output, merged_text)
    write_summary(args.summary, summary)
    return {
        "status": summary["status"],
        "replacement_batch_id": batch_id,
        "replacement_tiebreak_rows": len(responses),
        "retained_candidates_unchanged": len(retained_before),
        "test_outcomes_generated": 0,
    }


def fill_responses(
    path: Path,
    votes: Mapping[str, str],
    completed_utc: str,
) -> None:
    header, rows = read_csv(path)
    if header != SCREEN_RESPONSE_HEADER:
        raise AssertionError("self-test packet schema mismatch")
    for row in rows:
        candidate_id = row["candidate_claim_id"]
        row["eligibility_vote"] = votes[candidate_id]
        row["screening_reason"] = f"source-checked reason for {candidate_id}"
        row["source_checked"] = "yes"
        row["response_completed_utc"] = completed_utc
    write_atomic(path, serialize_csv(SCREEN_RESPONSE_HEADER, rows))


def self_test() -> None:
    workspace = PACKAGE / ".sampling_screen_selftest_workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    try:
        deterministic_rows: list[dict[str, str]] = []
        for index in range(4):
            candidate_id = f"fixture-{index}"
            deterministic_rows.append(
                {
                    "candidate_claim_id": candidate_id,
                    "source_key": "fixture-source",
                    "source_title": "Fixture Source",
                    "source_url_or_doi": "https://example.invalid/fixture",
                    "source_selection_rank": "1",
                    "source_candidate_rank": str(index + 1),
                    "source_section": "Results",
                    "pdf_page": "1",
                    "exact_quote": (
                        f"Fixture comparative claim {index} is better than baseline "
                        "under the reported condition."
                    ),
                    "context_before": "Fixture context before.",
                    "context_after": "Fixture context after.",
                    "cue_score": "3",
                    "section_priority": "0",
                    "source_text_sha256": "a" * 64,
                    "corpus_snapshot_id": "fixture-snapshot",
                    "candidate_record_sha256": hashlib.sha256(
                        candidate_id.encode("utf-8")
                    ).hexdigest(),
                    "extraction_method": (
                        "deterministic_comparative_cue_v1_model_free"
                    ),
                    "model_free_status": (
                        "MODEL_FREE_DETERMINISTIC_NOMINATION_NOT_HUMAN_LABEL"
                    ),
                }
            )
        deterministic_path = workspace / "deterministic.csv"
        candidates_path = workspace / "candidates.csv"
        summary_path = workspace / "summary.json"
        packets = workspace / "packets"
        write_atomic(
            deterministic_path,
            serialize_csv(DETERMINISTIC_HEADER, deterministic_rows),
        )
        command_initialize(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                output=candidates_path,
                summary=summary_path,
                recorded_utc="2026-07-15T00:00:00Z",
            )
        )
        initialized = load_screening_candidates(candidates_path)
        if any(
            any((row.get(field) or "").strip() for field in MODEL_FIELDS)
            for row in initialized
        ):
            raise AssertionError("self-test initialize populated a model field")
        command_build_initial(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                screener_1_id="screen-A",
                screener_2_id="screen-B",
                output_dir=packets,
                summary=summary_path,
                recorded_utc="2026-07-15T00:01:00Z",
            )
        )
        votes_1 = {
            "fixture-0": "eligible_c2",
            "fixture-1": "eligible_c2",
            "fixture-2": "ineligible",
            "fixture-3": "eligible_c5",
        }
        votes_2 = {
            "fixture-0": "eligible_c2",
            "fixture-1": "eligible_c5",
            "fixture-2": "ineligible",
            "fixture-3": "ineligible",
        }
        response_1 = packets / "initial_screener_1.csv"
        response_2 = packets / "initial_screener_2.csv"
        fill_responses(response_1, votes_1, "2026-07-15T00:02:00Z")
        fill_responses(response_2, votes_2, "2026-07-15T00:03:00Z")
        tiebreak_path = packets / "tiebreak.csv"
        merged_initial = command_merge_initial(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                response_1=response_1,
                response_2=response_2,
                tiebreak_screener_id="screen-C",
                output=candidates_path,
                tiebreak_output=tiebreak_path,
                summary=summary_path,
                recorded_utc="2026-07-15T00:04:00Z",
            )
        )
        if merged_initial["initial_disputes"] != 2:
            raise AssertionError("self-test dispute count mismatch")
        fill_responses(
            tiebreak_path,
            {"fixture-1": "eligible_c5", "fixture-3": "ineligible"},
            "2026-07-15T00:05:00Z",
        )
        result = command_merge_tiebreak(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                tiebreak_response=tiebreak_path,
                output=candidates_path,
                summary=summary_path,
                recorded_utc="2026-07-15T00:06:00Z",
            )
        )
        if result["status"] != "human_sampling_screen_complete":
            raise AssertionError("self-test did not complete screening")
        final_rows = load_screening_candidates(candidates_path)
        if Counter(row["selection_status"] for row in final_rows) != Counter(
            {"human_screen_consensus": 2, "human_screen_tiebreak": 2}
        ):
            raise AssertionError("self-test aggregation statuses mismatch")
        summary = read_summary(summary_path)
        if (
            not summary["screening_complete"]
            or [stage["stage"] for stage in summary["stages"]]
            != [
                "initialize",
                "build_initial",
                "merge_initial",
                "merge_tiebreak",
            ]
        ):
            raise AssertionError("self-test summary audit chain mismatch")
        try:
            command_build_initial(
                argparse.Namespace(
                    deterministic_candidates=deterministic_path,
                    candidates=candidates_path,
                    screener_1_id="same",
                    screener_2_id="same",
                    output_dir=packets,
                    summary=summary_path,
                    recorded_utc="2026-07-15T00:07:00Z",
                )
            )
        except ValueError:
            pass
        else:
            raise AssertionError("self-test accepted duplicate screener IDs")

        retained_before_replacement = [
            dict(row) for row in load_screening_candidates(candidates_path)
        ]
        replacement_deterministic = dict(deterministic_rows[0])
        replacement_deterministic.update(
            {
                "candidate_claim_id": "H3R-001-01",
                "source_key": "replacement-source",
                "source_title": "Replacement Source",
                "source_url_or_doi": "https://example.invalid/replacement",
                "source_selection_rank": "1",
                "source_candidate_rank": "1",
                "exact_quote": (
                    "Replacement claim is better than baseline with 12 compared "
                    "with 8 under the checked condition."
                ),
                "source_text_sha256": "b" * 64,
                "candidate_record_sha256": hashlib.sha256(
                    b"replacement-fixture"
                ).hexdigest(),
            }
        )
        deterministic_with_replacement = [
            *deterministic_rows,
            replacement_deterministic,
        ]
        write_atomic(
            deterministic_path,
            serialize_csv(
                DETERMINISTIC_HEADER, deterministic_with_replacement
            ),
        )
        candidates_with_replacement = [
            *retained_before_replacement,
            *initialize_rows([replacement_deterministic]),
        ]
        candidates_text = serialize_csv(
            MODEL_PRESCREEN_HEADER, candidates_with_replacement
        )
        write_atomic(candidates_path, candidates_text)
        summary = read_summary(summary_path)
        append_stage(
            summary,
            "apply_replacements",
            "2026-07-15T00:07:00Z",
            [
                artifact(
                    "candidate_claims_model_prescreen.csv",
                    serialize_csv(
                        MODEL_PRESCREEN_HEADER, retained_before_replacement
                    ),
                    len(retained_before_replacement),
                )
            ],
            [
                artifact(
                    "candidate_claims_model_prescreen.csv",
                    candidates_text,
                    len(candidates_with_replacement),
                )
            ],
            {
                "new_replacement_candidates": 1,
                "retained_candidates_unchanged": len(
                    retained_before_replacement
                ),
                "test_outcomes_generated": 0,
            },
            ["screen-A", "screen-B", "screen-C"],
            candidates_text,
            len(candidates_with_replacement),
            "awaiting_replacement_screen",
            False,
        )
        write_summary(summary_path, summary)
        replacement_summary_path = workspace / "replacement_summary.json"
        replacement_summary: dict[str, Any] = {
            "batches": [
                {
                    "batch_id": "RB-001",
                    "replacements": [
                        {
                            "replacement_source_key": "replacement-source",
                            "new_id_prefix": "H3R-001-",
                            "new_candidates": 1,
                        }
                    ],
                }
            ],
            "current_batch_id": "RB-001",
        }
        replacement_summary["batches"][0][
            "batch_record_sha256"
        ] = canonical_json_sha256(replacement_summary["batches"][0])
        replacement_summary_path.write_text(
            json.dumps(replacement_summary), encoding="utf-8"
        )
        command_build_replacement(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                replacement_summary=replacement_summary_path,
                output_dir=packets,
                summary=summary_path,
                recorded_utc="2026-07-15T00:08:00Z",
            )
        )
        replacement_response_1 = (
            packets / "RB-001_replacement_initial_screener_1.csv"
        )
        replacement_response_2 = (
            packets / "RB-001_replacement_initial_screener_2.csv"
        )
        fill_responses(
            replacement_response_1,
            {"H3R-001-01": "eligible_c2"},
            "2026-07-15T00:09:00Z",
        )
        fill_responses(
            replacement_response_2,
            {"H3R-001-01": "eligible_c5"},
            "2026-07-15T00:10:00Z",
        )
        replacement_tiebreak = packets / "replacement_tiebreak.csv"
        replacement_merge = command_merge_replacement_initial(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                response_1=replacement_response_1,
                response_2=replacement_response_2,
                replacement_summary=replacement_summary_path,
                output=candidates_path,
                tiebreak_output=replacement_tiebreak,
                summary=summary_path,
                recorded_utc="2026-07-15T00:11:00Z",
            )
        )
        if replacement_merge["replacement_initial_disputes"] != 1:
            raise AssertionError("replacement self-test missed its dispute")
        fill_responses(
            replacement_tiebreak,
            {"H3R-001-01": "eligible_c2"},
            "2026-07-15T00:12:00Z",
        )
        command_merge_replacement_tiebreak(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                replacement_summary=replacement_summary_path,
                tiebreak_response=replacement_tiebreak,
                output=candidates_path,
                summary=summary_path,
                recorded_utc="2026-07-15T00:13:00Z",
            )
        )
        after_first = load_screening_candidates(candidates_path)
        retained_after_replacement = retained_rows_snapshot(
            after_first, {"H3R-001-01"}
        )
        if retained_after_replacement != retained_before_replacement:
            raise AssertionError(
                "replacement screening changed non-replacement IDs/votes"
            )
        retained_before_second = [dict(row) for row in after_first]
        replacement_deterministic_2 = dict(replacement_deterministic)
        replacement_deterministic_2.update(
            {
                "candidate_claim_id": "H3R-002-01",
                "source_key": "replacement-source-2",
                "source_title": "Replacement Source 2",
                "source_url_or_doi": (
                    "https://example.invalid/replacement-source-2"
                ),
                "source_text_sha256": "c" * 64,
                "candidate_record_sha256": hashlib.sha256(
                    b"replacement-fixture-2"
                ).hexdigest(),
            }
        )
        deterministic_round_2 = [
            *deterministic_with_replacement,
            replacement_deterministic_2,
        ]
        write_atomic(
            deterministic_path,
            serialize_csv(DETERMINISTIC_HEADER, deterministic_round_2),
        )
        candidates_round_2 = [
            *retained_before_second,
            *initialize_rows([replacement_deterministic_2]),
        ]
        candidates_round_2_text = serialize_csv(
            MODEL_PRESCREEN_HEADER, candidates_round_2
        )
        write_atomic(candidates_path, candidates_round_2_text)
        summary = read_summary(summary_path)
        append_stage(
            summary,
            "apply_replacements",
            "2026-07-15T00:14:00Z",
            [
                artifact(
                    "candidate_claims_model_prescreen.csv",
                    serialize_csv(
                        MODEL_PRESCREEN_HEADER, retained_before_second
                    ),
                    len(retained_before_second),
                )
            ],
            [
                artifact(
                    "candidate_claims_model_prescreen.csv",
                    candidates_round_2_text,
                    len(candidates_round_2),
                )
            ],
            {
                "new_replacement_candidates": 1,
                "replacement_batch_number": 2,
                "retained_candidates_unchanged": len(
                    retained_before_second
                ),
                "test_outcomes_generated": 0,
            },
            ["screen-A", "screen-B", "screen-C"],
            candidates_round_2_text,
            len(candidates_round_2),
            "awaiting_replacement_screen",
            False,
        )
        write_summary(summary_path, summary)
        second_replacement_batch: dict[str, Any] = {
            "batch_id": "RB-002",
            "replacements": [
                {
                    "replacement_source_key": "replacement-source-2",
                    "new_id_prefix": "H3R-002-",
                    "new_candidates": 1,
                }
            ],
        }
        second_replacement_batch[
            "batch_record_sha256"
        ] = canonical_json_sha256(second_replacement_batch)
        replacement_summary["batches"].append(second_replacement_batch)
        replacement_summary["current_batch_id"] = "RB-002"
        replacement_summary_path.write_text(
            json.dumps(replacement_summary), encoding="utf-8"
        )
        command_build_replacement(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                replacement_summary=replacement_summary_path,
                output_dir=packets,
                summary=summary_path,
                recorded_utc="2026-07-15T00:15:00Z",
            )
        )
        response_2a = (
            packets / "RB-002_replacement_initial_screener_1.csv"
        )
        response_2b = (
            packets / "RB-002_replacement_initial_screener_2.csv"
        )
        fill_responses(
            response_2a,
            {"H3R-002-01": "eligible_c5"},
            "2026-07-15T00:16:00Z",
        )
        fill_responses(
            response_2b,
            {"H3R-002-01": "eligible_c5"},
            "2026-07-15T00:17:00Z",
        )
        second_merge = command_merge_replacement_initial(
            argparse.Namespace(
                deterministic_candidates=deterministic_path,
                candidates=candidates_path,
                response_1=response_2a,
                response_2=response_2b,
                replacement_summary=replacement_summary_path,
                output=candidates_path,
                tiebreak_output=None,
                summary=summary_path,
                recorded_utc="2026-07-15T00:18:00Z",
            )
        )
        if (
            second_merge["status"] != "human_sampling_screen_complete"
            or second_merge["replacement_initial_disputes"] != 0
        ):
            raise AssertionError("second replacement round did not complete")
        after_second = load_screening_candidates(candidates_path)
        if retained_rows_snapshot(
            after_second, {"H3R-002-01"}
        ) != retained_before_second:
            raise AssertionError(
                "second replacement changed first-round IDs/votes"
            )
    finally:
        shutil.rmtree(workspace)
    print(
        "self-test passed; two replacement batches preserved prior IDs/votes "
        "and synthetic fixture was removed"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    initialize = subparsers.add_parser("initialize")
    initialize.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    initialize.add_argument(
        "--output",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    initialize.add_argument(
        "--summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    initialize.add_argument("--recorded-utc", required=True)

    build_initial = subparsers.add_parser("build-initial")
    build_initial.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    build_initial.add_argument(
        "--candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    build_initial.add_argument("--screener-1-id", required=True)
    build_initial.add_argument("--screener-2-id", required=True)
    build_initial.add_argument(
        "--output-dir",
        type=Path,
        default=PACKAGE / "generated_sampling_screen_packets",
    )
    build_initial.add_argument(
        "--summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    build_initial.add_argument("--recorded-utc", required=True)

    merge_initial = subparsers.add_parser("merge-initial")
    merge_initial.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    merge_initial.add_argument(
        "--candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_initial.add_argument("--response-1", type=Path, required=True)
    merge_initial.add_argument("--response-2", type=Path, required=True)
    merge_initial.add_argument("--tiebreak-screener-id", required=True)
    merge_initial.add_argument(
        "--output",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_initial.add_argument(
        "--tiebreak-output",
        type=Path,
        default=(
            PACKAGE
            / "generated_sampling_screen_packets"
            / "tiebreak_disputes.csv"
        ),
    )
    merge_initial.add_argument(
        "--summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    merge_initial.add_argument("--recorded-utc", required=True)

    merge_tiebreak = subparsers.add_parser("merge-tiebreak")
    merge_tiebreak.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    merge_tiebreak.add_argument(
        "--candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_tiebreak.add_argument(
        "--tiebreak-response", type=Path, required=True
    )
    merge_tiebreak.add_argument(
        "--output",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_tiebreak.add_argument(
        "--summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    merge_tiebreak.add_argument("--recorded-utc", required=True)

    build_replacement = subparsers.add_parser("build-replacement")
    build_replacement.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    build_replacement.add_argument(
        "--candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    build_replacement.add_argument(
        "--replacement-summary",
        type=Path,
        default=PACKAGE / "source_replacement_summary.json",
    )
    build_replacement.add_argument(
        "--output-dir",
        type=Path,
        default=PACKAGE / "generated_sampling_screen_packets",
    )
    build_replacement.add_argument(
        "--summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    build_replacement.add_argument("--recorded-utc", required=True)

    merge_replacement_initial = subparsers.add_parser(
        "merge-replacement-initial"
    )
    merge_replacement_initial.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    merge_replacement_initial.add_argument(
        "--candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_replacement_initial.add_argument(
        "--replacement-summary",
        type=Path,
        default=PACKAGE / "source_replacement_summary.json",
    )
    merge_replacement_initial.add_argument(
        "--response-1", type=Path, required=True
    )
    merge_replacement_initial.add_argument(
        "--response-2", type=Path, required=True
    )
    merge_replacement_initial.add_argument(
        "--output",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_replacement_initial.add_argument(
        "--tiebreak-output",
        type=Path,
        default=None,
    )
    merge_replacement_initial.add_argument(
        "--summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    merge_replacement_initial.add_argument("--recorded-utc", required=True)

    merge_replacement_tiebreak = subparsers.add_parser(
        "merge-replacement-tiebreak"
    )
    merge_replacement_tiebreak.add_argument(
        "--deterministic-candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    merge_replacement_tiebreak.add_argument(
        "--candidates",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_replacement_tiebreak.add_argument(
        "--replacement-summary",
        type=Path,
        default=PACKAGE / "source_replacement_summary.json",
    )
    merge_replacement_tiebreak.add_argument(
        "--tiebreak-response", type=Path, required=True
    )
    merge_replacement_tiebreak.add_argument(
        "--output",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    merge_replacement_tiebreak.add_argument(
        "--summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    merge_replacement_tiebreak.add_argument("--recorded-utc", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    commands = {
        "initialize": command_initialize,
        "build-initial": command_build_initial,
        "merge-initial": command_merge_initial,
        "merge-tiebreak": command_merge_tiebreak,
        "build-replacement": command_build_replacement,
        "merge-replacement-initial": command_merge_replacement_initial,
        "merge-replacement-tiebreak": command_merge_replacement_tiebreak,
    }
    if args.command not in commands:
        raise ValueError("choose a screening workflow command or --self-test")
    result = commands[args.command](args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
