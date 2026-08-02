#!/usr/bin/env python3
"""Freeze the human-screened 480-claim sample without using model scores."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_sampling_screen_packets import (
    MODEL_FIELDS as SAMPLING_MODEL_FIELDS,
    MODEL_FREE_SCREENING_STATUS,
    PROHIBITED_USE as SAMPLING_SCREEN_PROHIBITED_USE,
    SUMMARY_SCHEMA_VERSION as SAMPLING_SCREEN_SCHEMA_VERSION,
)
from prepare_candidate_pool import CANDIDATE_HEADER as DETERMINISTIC_HEADER
from prepare_candidate_pool import (
    MODEL_ONLY_STATUS,
    MODEL_PRESCREEN_HEADER,
    SOURCE_HEADER,
    stable_digest,
)


PACKAGE = Path(__file__).resolve().parent
CLAIM_SEED = 2026071502
CLAIMS_PER_SOURCE = 6
TARGET_SOURCES = 80
TARGET_PER_STRATUM = 240
FROZEN_VERSION = "v3.0.0-test-freeze"
REPLACEMENT_SUMMARY_SCHEMA_VERSION = "stable-source-replacement-v1"

MODEL_HUMAN_FIELDS = (
    "human_sampling_reviewer_1_id",
    "human_sampling_reviewer_2_id",
    "human_sampling_tiebreak_reviewer_id",
    "human_sampling_eligibility",
    "human_sampling_stratum",
    "selection_status",
    "exclusion_reason_code",
    "exclusion_reason_detail",
)
FROZEN_HEADER = (
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
REPLACEMENT_HEADER = ("source_key", "exclusion_reason_detail")


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_merged_screen_summary(
    path: Path,
    candidate_path: Path,
    candidate_rows: Sequence[Mapping[str, str]],
) -> str:
    try:
        summary: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read merged sampling-screen summary: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid merged sampling-screen summary: {exc}") from exc
    if summary.get("schema_version") != SAMPLING_SCREEN_SCHEMA_VERSION:
        raise ValueError("sampling-screen summary schema mismatch")
    if summary.get("prohibited_use") != SAMPLING_SCREEN_PROHIBITED_USE:
        raise ValueError("sampling-screen summary lacks the label-use prohibition")
    if summary.get("status") != "human_sampling_screen_complete":
        raise ValueError("sampling screening is not fully merged")
    if summary.get("screening_complete") is not True:
        raise ValueError("sampling-screen completion flag is not true")
    current = summary.get("current_candidate_state")
    if not isinstance(current, dict):
        raise ValueError("sampling-screen summary lacks current candidate state")
    if (
        current.get("artifact") != "candidate_claims_model_prescreen.csv"
        or current.get("rows") != len(candidate_rows)
        or current.get("sha256") != sha256_file(candidate_path)
    ):
        raise ValueError("sampling-screen summary does not match candidate input")
    stages = summary.get("stages")
    merge_stages = {
        "merge_initial",
        "merge_tiebreak",
        "merge_replacement_initial",
        "merge_replacement_tiebreak",
    }
    if (
        not isinstance(stages, list)
        or not stages
        or not isinstance(stages[-1], dict)
        or (
            stages[-1].get("stage") not in merge_stages
            and not (
                stages[-1].get("stage")
                == "apply_pretest_text_corrections"
                and len(stages) >= 2
                and isinstance(stages[-2], dict)
                and stages[-2].get("stage") in merge_stages
            )
        )
    ):
        raise ValueError("sampling-screen summary lacks a final merge stage")
    final_stage = stages[-1]
    expected_stage_hash = canonical_json_sha256(
        {
            key: value
            for key, value in final_stage.items()
            if key != "stage_record_sha256"
        }
    )
    if final_stage.get("stage_record_sha256") != expected_stage_hash:
        raise ValueError("sampling-screen final merge record hash is invalid")
    return sha256_file(path)


def load_replacement_source_order(
    path: Path,
    source_rows: Sequence[Mapping[str, str]],
    deterministic_rows: Sequence[Mapping[str, str]],
    human_rows: Sequence[Mapping[str, str]],
    ledger_rows: Sequence[Mapping[str, str]],
    screen_summary: Mapping[str, Any],
) -> tuple[list[str] | None, str]:
    if not path.exists():
        return None, ""
    try:
        summary: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid source replacement summary: {exc}") from exc
    if (
        summary.get("schema_version") != REPLACEMENT_SUMMARY_SCHEMA_VERSION
        or summary.get("status") != "APPLIED_AWAITING_REPLACEMENT_SCREEN"
    ):
        raise ValueError("source replacement summary metadata mismatch")
    from apply_source_replacements import (
        replacement_event_ids,
        verify_replacement_chain,
    )

    applied_count = len(replacement_event_ids(summary))
    if len(ledger_rows) < applied_count:
        raise ValueError("replacement ledger is shorter than the applied chain")
    historical_deterministic_rows = list(deterministic_rows)
    historical_human_rows = list(human_rows)
    correction_path = path.parent / "frozen_text_corrections.csv"
    frozen_path = path.parent / "frozen_test_claims.csv"
    if correction_path.exists() and frozen_path.exists():
        _correction_header, correction_rows = read_csv(correction_path)
        _frozen_header, frozen_rows = read_csv(frozen_path)
        if correction_rows and frozen_rows:
            from frozen_text_corrections import (
                validate_and_reverse_corrections,
            )

            correction_state = validate_and_reverse_corrections(
                correction_rows,
                deterministic_rows,
                human_rows,
                frozen_rows,
            )
            historical_deterministic_rows = (
                correction_state.deterministic_rows
            )
            historical_human_rows = correction_state.human_rows
    result = verify_replacement_chain(
        summary,
        {
            "frame_rows": list(source_rows),
            "deterministic_rows": historical_deterministic_rows,
            "human_rows": historical_human_rows,
            "ledger_rows": list(ledger_rows[:applied_count]),
            "screen_summary": screen_summary,
        },
        expected_sources=TARGET_SOURCES,
        text_root=None,
    )
    return list(result["active_source_order"]), sha256_file(path)


def selected_source_order(source_rows: Sequence[Mapping[str, str]]) -> list[str]:
    selected = [
        row
        for row in source_rows
        if (row.get("eligibility_status") or "").strip() == "eligible_selected"
    ]
    by_stratum: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in source_rows:
        if (row.get("eligibility_status") or "").strip() in {
            "eligible_selected",
            "eligible_reserve",
        }:
            by_stratum[(row.get("sampling_stratum") or "").strip()].append(row)
    for rows in by_stratum.values():
        rows.sort(key=lambda row: int((row.get("deterministic_source_rank") or "0")))
    global_order: list[str] = []
    pass_index = 0
    while True:
        added = False
        for stratum in sorted(by_stratum):
            rows = by_stratum[stratum]
            if pass_index < len(rows):
                global_order.append((rows[pass_index].get("source_key") or "").strip())
                added = True
        if not added:
            break
        pass_index += 1
    selected_keys = {
        (row.get("source_key") or "").strip() for row in selected
    }
    order = [source_key for source_key in global_order if source_key in selected_keys]
    if len(order) != TARGET_SOURCES or len(selected_keys) != TARGET_SOURCES:
        raise ValueError("source frame does not contain exactly 80 selected sources")
    return order


def sanitize_human_sampling_row(row: Mapping[str, str]) -> dict[str, str]:
    """Return only identifiers and human sampling fields; omit every model field."""

    sanitized = {"candidate_claim_id": (row.get("candidate_claim_id") or "").strip()}
    for field in MODEL_HUMAN_FIELDS:
        sanitized[field] = (row.get(field) or "").strip()
    return sanitized


def validate_human_screen_row(
    row: Mapping[str, str], candidate_id: str
) -> tuple[str | None, dict[str, str]]:
    human = sanitize_human_sampling_row(row)
    reviewer_1 = human["human_sampling_reviewer_1_id"]
    reviewer_2 = human["human_sampling_reviewer_2_id"]
    tiebreak = human["human_sampling_tiebreak_reviewer_id"]
    if not reviewer_1 or not reviewer_2 or reviewer_1 == reviewer_2:
        raise ValueError(f"{candidate_id} lacks two distinct sampling screeners")
    status = human["selection_status"]
    if status == "human_screen_consensus":
        if tiebreak:
            raise ValueError(f"{candidate_id} has an unnecessary tiebreak reviewer")
    elif status == "human_screen_tiebreak":
        if not tiebreak or tiebreak in {reviewer_1, reviewer_2}:
            raise ValueError(f"{candidate_id} lacks a distinct tiebreak reviewer")
    else:
        raise ValueError(
            f"{candidate_id} must be human_screen_consensus or human_screen_tiebreak"
        )
    eligibility = human["human_sampling_eligibility"]
    stratum = human["human_sampling_stratum"]
    if eligibility == "eligible_c2":
        if stratum != "c2_decisive":
            raise ValueError(f"{candidate_id} has inconsistent C2 sampling fields")
        return "c2_decisive", human
    if eligibility == "eligible_c5":
        if stratum != "c5_decisive":
            raise ValueError(f"{candidate_id} has inconsistent C5 sampling fields")
        return "c5_decisive", human
    if eligibility == "ineligible":
        if stratum:
            raise ValueError(f"{candidate_id} assigns a stratum to an ineligible row")
        if not human["exclusion_reason_code"]:
            raise ValueError(f"{candidate_id} lacks a human exclusion reason")
        return None, human
    raise ValueError(f"{candidate_id} has an unknown human sampling eligibility")


def allocate_c2_counts(
    capacities: Mapping[str, tuple[int, int]]
) -> dict[str, int]:
    lower: dict[str, int] = {}
    upper: dict[str, int] = {}
    allocation: dict[str, int] = {}
    for source_key, (c2_count, c5_count) in capacities.items():
        lower[source_key] = max(0, CLAIMS_PER_SOURCE - c5_count)
        upper[source_key] = min(CLAIMS_PER_SOURCE, c2_count)
        if lower[source_key] > upper[source_key]:
            raise ValueError(f"{source_key} cannot provide six eligible claims")
        allocation[source_key] = min(
            upper[source_key], max(lower[source_key], CLAIMS_PER_SOURCE // 2)
        )
    if sum(lower.values()) > TARGET_PER_STRATUM:
        raise ValueError("C2 lower bounds exceed 240")
    if sum(upper.values()) < TARGET_PER_STRATUM:
        raise ValueError("C2 upper bounds are below 240")
    order = sorted(
        capacities,
        key=lambda source_key: stable_digest(
            CLAIM_SEED, "stratum-allocation", source_key
        ),
    )
    while sum(allocation.values()) < TARGET_PER_STRATUM:
        progressed = False
        for source_key in order:
            if allocation[source_key] < upper[source_key]:
                allocation[source_key] += 1
                progressed = True
                if sum(allocation.values()) == TARGET_PER_STRATUM:
                    break
        if not progressed:
            raise ValueError("cannot increase C2 allocation to 240")
    while sum(allocation.values()) > TARGET_PER_STRATUM:
        progressed = False
        for source_key in reversed(order):
            if allocation[source_key] > lower[source_key]:
                allocation[source_key] -= 1
                progressed = True
                if sum(allocation.values()) == TARGET_PER_STRATUM:
                    break
        if not progressed:
            raise ValueError("cannot decrease C2 allocation to 240")
    return allocation


def replacement_order(source_rows: Sequence[Mapping[str, str]]) -> list[str]:
    reserves = [
        row
        for row in source_rows
        if (row.get("eligibility_status") or "").strip() == "eligible_reserve"
    ]
    by_stratum: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in reserves:
        by_stratum[(row.get("sampling_stratum") or "").strip()].append(row)
    for rows in by_stratum.values():
        rows.sort(key=lambda row: int((row.get("deterministic_source_rank") or "0")))
    order: list[str] = []
    pass_index = 0
    while True:
        added = False
        for stratum in sorted(by_stratum):
            if pass_index < len(by_stratum[stratum]):
                order.append(
                    (by_stratum[stratum][pass_index].get("source_key") or "").strip()
                )
                added = True
        if not added:
            break
        pass_index += 1
    return order


def choose_replacements(
    deficient_sources: Sequence[str],
    source_rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    frame = {
        (row.get("source_key") or "").strip(): row for row in source_rows
    }
    reserves = [
        row
        for row in source_rows
        if (row.get("eligibility_status") or "").strip() == "eligible_reserve"
    ]
    global_reserves = replacement_order(source_rows)
    used: set[str] = set()
    replacements: dict[str, str] = {}
    for source_key in deficient_sources:
        stratum = (frame[source_key].get("sampling_stratum") or "").strip()
        same_stratum = sorted(
            (
                row
                for row in reserves
                if (row.get("sampling_stratum") or "").strip() == stratum
                and (row.get("source_key") or "").strip() not in used
            ),
            key=lambda row: int((row.get("deterministic_source_rank") or "0")),
        )
        if same_stratum:
            replacement = (same_stratum[0].get("source_key") or "").strip()
        else:
            replacement = next(
                (
                    candidate
                    for candidate in global_reserves
                    if candidate not in used
                ),
                "",
            )
        if not replacement:
            raise ValueError(f"no reserve source available to replace {source_key}")
        replacements[source_key] = replacement
        used.add(replacement)
    return replacements


def ledger_row(
    event_index: int,
    source_key: str,
    replacement_source_key: str,
    frame_row: Mapping[str, str],
    c2_count: int,
    c5_count: int,
    reason_code: str,
    reason_detail: str,
    recorded_utc: str,
    source_rank: int,
) -> dict[str, object]:
    row: dict[str, object] = {
        "ledger_event_id": f"SR-{event_index:03d}",
        "event_type": "source_replacement_required",
        "source_key": source_key,
        "replacement_source_key": replacement_source_key,
        "sampling_stratum": (frame_row.get("sampling_stratum") or "").strip(),
        "reason_code": reason_code,
        "reason_detail": reason_detail,
        "eligible_c2_count": c2_count,
        "eligible_c5_count": c5_count,
        "required_claims": CLAIMS_PER_SOURCE,
        "source_selection_rank": source_rank,
        "recorded_utc": recorded_utc,
        "record_sha256": "",
    }
    row["record_sha256"] = canonical_json_sha256(
        {
            field: str(row[field])
            for field in LEDGER_HEADER
            if field != "record_sha256"
        }
    )
    return row


def sampling_record_sha256(
    deterministic: Mapping[str, str],
    human: Mapping[str, str],
    stratum: str,
) -> str:
    payload = {
        "candidate_claim_id": deterministic["candidate_claim_id"],
        "source_key": deterministic["source_key"],
        "source_title": deterministic["source_title"],
        "source_url_or_doi": deterministic["source_url_or_doi"],
        "source_section": deterministic["source_section"],
        "pdf_page": deterministic["pdf_page"],
        "exact_quote": deterministic["exact_quote"],
        "context_before": deterministic["context_before"],
        "context_after": deterministic["context_after"],
        "source_text_sha256": deterministic["source_text_sha256"],
        "candidate_record_sha256": deterministic["candidate_record_sha256"],
        "human_sampling_reviewer_1_id": human[
            "human_sampling_reviewer_1_id"
        ],
        "human_sampling_reviewer_2_id": human[
            "human_sampling_reviewer_2_id"
        ],
        "human_sampling_tiebreak_reviewer_id": human[
            "human_sampling_tiebreak_reviewer_id"
        ],
        "human_sampling_eligibility": human["human_sampling_eligibility"],
        "human_sampling_stratum": stratum,
        "selection_status": human["selection_status"],
    }
    return canonical_json_sha256(payload)


def freeze_sample(
    source_rows: Sequence[Mapping[str, str]],
    deterministic_rows: Sequence[Mapping[str, str]],
    model_rows: Sequence[Mapping[str, str]],
    freeze_utc: str,
    source_order_override: Sequence[str] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, str]], dict[str, object]]:
    source_order = (
        list(source_order_override)
        if source_order_override is not None
        else selected_source_order(source_rows)
    )
    if len(source_order) != TARGET_SOURCES or len(set(source_order)) != TARGET_SOURCES:
        raise ValueError("active source order must contain exactly 80 unique sources")
    selected_keys = {
        (row.get("source_key") or "").strip()
        for row in source_rows
        if (row.get("eligibility_status") or "").strip() == "eligible_selected"
    }
    if set(source_order) != selected_keys:
        raise ValueError("active source order differs from selected source frame")
    source_rank = {
        source_key: rank for rank, source_key in enumerate(source_order, start=1)
    }
    frame = {
        (row.get("source_key") or "").strip(): row for row in source_rows
    }
    deterministic_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row
        for row in deterministic_rows
    }
    model_by_id = {
        (row.get("candidate_claim_id") or "").strip(): row for row in model_rows
    }
    if len(deterministic_by_id) != len(deterministic_rows):
        raise ValueError("deterministic candidate IDs are not unique")
    if set(model_by_id) != set(deterministic_by_id):
        raise ValueError(
            "human-screened model-prescreen file must exactly cover deterministic candidates"
        )

    by_source_stratum: dict[str, dict[str, list[tuple[Mapping[str, str], dict[str, str]]]]] = {
        source_key: {"c2_decisive": [], "c5_decisive": []}
        for source_key in source_order
    }
    sanitized_rows: list[dict[str, str]] = []
    for candidate_id, deterministic in deterministic_by_id.items():
        source_key = (deterministic.get("source_key") or "").strip()
        if source_key not in by_source_stratum:
            raise ValueError(f"candidate {candidate_id} is not from a selected source")
        model_row = model_by_id[candidate_id]
        model_status = (model_row.get("model_only_status") or "").strip()
        if model_status == MODEL_FREE_SCREENING_STATUS:
            if any(
                (model_row.get(field) or "").strip()
                for field in SAMPLING_MODEL_FIELDS
            ):
                raise ValueError(
                    f"{candidate_id} marks model-free screening but contains "
                    "a model field"
                )
        elif model_status != MODEL_ONLY_STATUS:
            raise ValueError(
                f"{candidate_id} has an unknown model/model-free status"
            )
        stratum, human = validate_human_screen_row(model_row, candidate_id)
        sanitized_rows.append(human)
        if stratum is not None:
            by_source_stratum[source_key][stratum].append((deterministic, human))

    capacities = {
        source_key: (
            len(by_source_stratum[source_key]["c2_decisive"]),
            len(by_source_stratum[source_key]["c5_decisive"]),
        )
        for source_key in source_order
    }
    deficient = [
        source_key
        for source_key, (c2_count, c5_count) in capacities.items()
        if c2_count + c5_count < CLAIMS_PER_SOURCE
    ]
    global_reason = ""
    if not deficient:
        lower_sum = sum(max(0, CLAIMS_PER_SOURCE - c5) for c2, c5 in capacities.values())
        upper_sum = sum(min(CLAIMS_PER_SOURCE, c2) for c2, c5 in capacities.values())
        if lower_sum > TARGET_PER_STRATUM:
            deficient = [
                min(
                    source_order,
                    key=lambda source_key: (
                        capacities[source_key][1],
                        stable_digest(CLAIM_SEED, "replace", source_key),
                    ),
                )
            ]
            global_reason = "global_c2_lower_bound_exceeds_240"
        elif upper_sum < TARGET_PER_STRATUM:
            deficient = [
                min(
                    source_order,
                    key=lambda source_key: (
                        capacities[source_key][0],
                        stable_digest(CLAIM_SEED, "replace", source_key),
                    ),
                )
            ]
            global_reason = "global_c2_upper_bound_below_240"

    if deficient:
        replacements = choose_replacements(deficient, source_rows)
        ledger: list[dict[str, object]] = []
        replacement_rows: list[dict[str, str]] = []
        for event_index, source_key in enumerate(deficient, start=1):
            c2_count, c5_count = capacities[source_key]
            reason_detail = global_reason or "fewer_than_six_human_confirmed_decisive_claims"
            ledger.append(
                ledger_row(
                    event_index,
                    source_key,
                    replacements[source_key],
                    frame[source_key],
                    c2_count,
                    c5_count,
                    "SOURCE_REPLACED",
                    reason_detail,
                    freeze_utc,
                    source_rank[source_key],
                )
            )
            replacement_rows.append(
                {
                    "source_key": source_key,
                    "exclusion_reason_detail": reason_detail,
                }
            )
        summary = {
            "status": "REPLACEMENT_REQUIRED_NO_TEST_FREEZE",
            "replacement_required": True,
            "claims": 0,
            "sources": 0,
            "c2_claims": 0,
            "c5_claims": 0,
            "sampling_claim_seed": CLAIM_SEED,
            "model_fields_used_for_selection": False,
            "ledger_events": len(ledger),
            "human_sampling_input_sha256": canonical_json_sha256(
                {"rows": sorted(sanitized_rows, key=lambda row: row["candidate_claim_id"])}
            ),
            "frozen_claims_sha256": "",
        }
        return [], ledger, replacement_rows, summary

    c2_allocation = allocate_c2_counts(capacities)
    frozen: list[dict[str, object]] = []
    for source_key in source_order:
        for stratum, take in (
            ("c2_decisive", c2_allocation[source_key]),
            ("c5_decisive", CLAIMS_PER_SOURCE - c2_allocation[source_key]),
        ):
            ranked = sorted(
                by_source_stratum[source_key][stratum],
                key=lambda pair: stable_digest(
                    CLAIM_SEED,
                    "claim",
                    (pair[0].get("candidate_claim_id") or "").strip(),
                ),
            )
            for deterministic, human in ranked[:take]:
                candidate_id = (deterministic.get("candidate_claim_id") or "").strip()
                frozen.append(
                    {
                        "claim_id": candidate_id,
                        "source_key": source_key,
                        "claim_text": deterministic["exact_quote"],
                        "context_before": deterministic["context_before"],
                        "context_after": deterministic["context_after"],
                        "source_title": deterministic["source_title"],
                        "source_section": deterministic["source_section"],
                        "source_locator": f"PDF page {deterministic['pdf_page']}",
                        "source_url_or_doi": deterministic["source_url_or_doi"],
                        "source_evidence_excerpt": deterministic["exact_quote"],
                        "source_file_sha256": deterministic["source_text_sha256"],
                        "coordinator_only_primary_stratum": stratum,
                        "sampling_record_sha256": sampling_record_sha256(
                            deterministic, human, stratum
                        ),
                        "freeze_version": FROZEN_VERSION,
                        "freeze_utc": freeze_utc,
                        "label_collection_status": "NO_TEST_LABELS_COLLECTED",
                    }
                )
    frozen.sort(
        key=lambda row: (
            source_rank[str(row["source_key"])],
            str(row["coordinator_only_primary_stratum"]),
            stable_digest(CLAIM_SEED, "claim", str(row["claim_id"])),
        )
    )
    if len(frozen) != 480:
        raise AssertionError(f"freeze produced {len(frozen)} claims, expected 480")
    if len({row["source_key"] for row in frozen}) != 80:
        raise AssertionError("freeze did not retain exactly 80 sources")
    if sum(row["coordinator_only_primary_stratum"] == "c2_decisive" for row in frozen) != 240:
        raise AssertionError("freeze did not produce 240 C2 claims")
    frozen_text = serialize_csv(FROZEN_HEADER, frozen)
    summary = {
        "status": "FROZEN_NO_TEST_LABELS",
        "replacement_required": False,
        "claims": 480,
        "sources": 80,
        "c2_claims": 240,
        "c5_claims": 240,
        "sampling_claim_seed": CLAIM_SEED,
        "model_fields_used_for_selection": False,
        "ledger_events": 0,
        "human_sampling_input_sha256": canonical_json_sha256(
            {"rows": sorted(sanitized_rows, key=lambda row: row["candidate_claim_id"])}
        ),
        "frozen_claims_sha256": sha256_text(frozen_text),
    }
    return frozen, [], [], summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-frame", type=Path, default=PACKAGE / "source_sampling_frame.csv"
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
        "--screen-summary",
        type=Path,
        default=PACKAGE / "sampling_screen_summary.json",
    )
    parser.add_argument(
        "--replacement-summary",
        type=Path,
        default=PACKAGE / "source_replacement_summary.json",
    )
    parser.add_argument(
        "--frozen-output", type=Path, default=PACKAGE / "frozen_test_claims.csv"
    )
    parser.add_argument(
        "--ledger-output",
        type=Path,
        default=PACKAGE / "sampling_exclusion_replacement_ledger.csv",
    )
    parser.add_argument(
        "--replacement-output",
        type=Path,
        default=PACKAGE / "source_replacement_exclusions.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PACKAGE / "sampling_freeze_summary.json",
    )
    parser.add_argument("--freeze-utc")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def self_test() -> None:
    source_rows: list[dict[str, str]] = []
    deterministic_rows: list[dict[str, str]] = []
    model_rows: list[dict[str, str]] = []
    for source_index in range(80):
        source_key = f"source_{source_index:03d}"
        source_rows.append(
            {
                "source_key": source_key,
                "eligibility_status": "eligible_selected",
                "sampling_stratum": f"stratum_{source_index % 4}",
                "deterministic_source_rank": str(source_index // 4 + 1),
            }
        )
        for claim_index in range(6):
            candidate_id = f"candidate_{source_index:03d}_{claim_index}"
            stratum = "c2_decisive" if claim_index < 3 else "c5_decisive"
            eligibility = "eligible_c2" if claim_index < 3 else "eligible_c5"
            deterministic_rows.append(
                {
                    "candidate_claim_id": candidate_id,
                    "source_key": source_key,
                    "source_title": f"Source {source_index}",
                    "source_url_or_doi": f"https://example.invalid/{source_key}",
                    "source_section": "Results",
                    "pdf_page": "1",
                    "exact_quote": (
                        "The method is better than the baseline under the tested "
                        f"condition {claim_index}."
                    ),
                    "context_before": "",
                    "context_after": "",
                    "source_text_sha256": "a" * 64,
                    "candidate_record_sha256": hashlib.sha256(
                        candidate_id.encode("utf-8")
                    ).hexdigest(),
                }
            )
            model_rows.append(
                {
                    "candidate_claim_id": candidate_id,
                    "human_sampling_reviewer_1_id": "screen_1",
                    "human_sampling_reviewer_2_id": "screen_2",
                    "human_sampling_tiebreak_reviewer_id": "",
                    "human_sampling_eligibility": eligibility,
                    "human_sampling_stratum": stratum,
                    "selection_status": "human_screen_consensus",
                    "exclusion_reason_code": "",
                    "exclusion_reason_detail": "",
                    "model_only_status": MODEL_ONLY_STATUS,
                    "prescreen_c2_decisive_probability": "0.99",
                    "prescreen_c5_decisive_probability": "0.01",
                }
            )
    for reserve_index in range(4):
        source_rows.append(
            {
                "source_key": f"reserve_{reserve_index}",
                "eligibility_status": "eligible_reserve",
                "sampling_stratum": f"stratum_{reserve_index}",
                "deterministic_source_rank": "21",
            }
        )
    frozen, ledger, replacements, summary = freeze_sample(
        source_rows,
        deterministic_rows,
        model_rows,
        "2026-07-15T00:00:00Z",
    )
    if len(frozen) != 480 or ledger or replacements:
        raise AssertionError("freeze self-test coverage failed")
    if summary["c2_claims"] != 240 or summary["c5_claims"] != 240:
        raise AssertionError("freeze self-test stratum balance failed")
    reversed_scores = list(reversed(model_rows))
    for row in reversed_scores:
        row["prescreen_c2_decisive_probability"] = "0"
        row["prescreen_c5_decisive_probability"] = "1"
    frozen_again, _, _, _ = freeze_sample(
        source_rows,
        deterministic_rows,
        reversed_scores,
        "2026-07-15T00:00:00Z",
    )
    if [row["claim_id"] for row in frozen] != [
        row["claim_id"] for row in frozen_again
    ]:
        raise AssertionError("model scores affected human sample selection")
    model_free_rows = [dict(row) for row in model_rows]
    for row in model_free_rows:
        row["model_only_status"] = MODEL_FREE_SCREENING_STATUS
        for field in SAMPLING_MODEL_FIELDS:
            row[field] = ""
    frozen_model_free, _, _, _ = freeze_sample(
        source_rows,
        deterministic_rows,
        model_free_rows,
        "2026-07-15T00:00:00Z",
    )
    if [row["claim_id"] for row in frozen] != [
        row["claim_id"] for row in frozen_model_free
    ]:
        raise AssertionError("model-free empty-score input changed sample selection")
    deficient_rows = [dict(row) for row in model_rows]
    deficient_rows[0]["human_sampling_eligibility"] = "ineligible"
    deficient_rows[0]["human_sampling_stratum"] = ""
    deficient_rows[0]["exclusion_reason_code"] = "NOT_DECISIVE_AFTER_HUMAN_SCREEN"
    no_freeze, replacement_ledger, replacement_rows, replacement_summary = (
        freeze_sample(
            source_rows,
            deterministic_rows,
            deficient_rows,
            "2026-07-15T00:00:00Z",
        )
    )
    if (
        no_freeze
        or len(replacement_ledger) != 1
        or len(replacement_rows) != 1
        or not replacement_summary["replacement_required"]
    ):
        raise AssertionError("replacement self-test failed")
    post_source_rows = [dict(row) for row in source_rows]
    for row in post_source_rows:
        if row["source_key"] == "source_000":
            row["eligibility_status"] = "excluded"
        elif row["source_key"] == "reserve_0":
            row["eligibility_status"] = "eligible_selected"
    post_deterministic = [
        dict(row)
        for row in deterministic_rows
        if row["source_key"] != "source_000"
    ]
    post_model = [
        dict(row) for row in model_rows if row["candidate_claim_id"] not in {
            f"candidate_000_{claim_index}" for claim_index in range(6)
        }
    ]
    for claim_index in range(6):
        candidate_id = f"H3R-001-{claim_index + 1:02d}"
        stratum = "c2_decisive" if claim_index < 3 else "c5_decisive"
        eligibility = "eligible_c2" if claim_index < 3 else "eligible_c5"
        post_deterministic.append(
            {
                "candidate_claim_id": candidate_id,
                "source_key": "reserve_0",
                "source_title": "Replacement source",
                "source_url_or_doi": "https://example.invalid/reserve_0",
                "source_section": "Results",
                "pdf_page": "1",
                "exact_quote": f"Replacement comparative result {claim_index}.",
                "context_before": "",
                "context_after": "",
                "source_text_sha256": "b" * 64,
                "candidate_record_sha256": hashlib.sha256(
                    candidate_id.encode("utf-8")
                ).hexdigest(),
            }
        )
        post_model.append(
            {
                "candidate_claim_id": candidate_id,
                "human_sampling_reviewer_1_id": "screen_1",
                "human_sampling_reviewer_2_id": "screen_2",
                "human_sampling_tiebreak_reviewer_id": "",
                "human_sampling_eligibility": eligibility,
                "human_sampling_stratum": stratum,
                "selection_status": "human_screen_consensus",
                "exclusion_reason_code": "",
                "exclusion_reason_detail": "",
                "model_only_status": MODEL_FREE_SCREENING_STATUS,
                "prescreen_c2_decisive_probability": "",
                "prescreen_c5_decisive_probability": "",
            }
        )
    post_order = ["reserve_0"] + [
        f"source_{source_index:03d}" for source_index in range(1, 80)
    ]
    post_frozen, post_ledger, _, post_summary = freeze_sample(
        post_source_rows,
        post_deterministic,
        post_model,
        "2026-07-15T00:00:00Z",
        post_order,
    )
    if (
        len(post_frozen) != 480
        or post_ledger
        or post_summary["c2_claims"] != 240
        or post_summary["c5_claims"] != 240
    ):
        raise AssertionError("post-replacement freeze self-test failed")
    retained_before = {
        row["claim_id"]
        for row in frozen
        if row["source_key"] != "source_000"
    }
    retained_after = {
        row["claim_id"]
        for row in post_frozen
        if row["source_key"] != "reserve_0"
    }
    if retained_before != retained_after:
        raise AssertionError("replacement changed retained-source claim IDs")
    print("self-test passed; no files or test labels written")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.freeze_utc:
        raise ValueError("--freeze-utc is required for an auditable freeze")
    prior_freeze_summary: dict[str, Any] = {}
    if args.summary_output.exists():
        try:
            prior_freeze_summary = json.loads(
                args.summary_output.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise ValueError("existing freeze summary is invalid") from exc
    source_header, source_rows = read_csv(args.source_frame)
    deterministic_header, deterministic_rows = read_csv(
        args.deterministic_candidates
    )
    model_header, model_rows = read_csv(args.human_screened_candidates)
    if source_header != SOURCE_HEADER:
        raise ValueError("source frame schema mismatch")
    if deterministic_header != DETERMINISTIC_HEADER:
        raise ValueError("deterministic candidate schema mismatch")
    if model_header != MODEL_PRESCREEN_HEADER:
        raise ValueError("human-screened candidate schema mismatch")
    screen_summary_sha256 = validate_merged_screen_summary(
        args.screen_summary,
        args.human_screened_candidates,
        model_rows,
    )
    screen_summary = json.loads(args.screen_summary.read_text(encoding="utf-8"))
    existing_ledger: list[dict[str, str]] = []
    if args.ledger_output.exists():
        ledger_header, existing_ledger = read_csv(args.ledger_output)
        if ledger_header != LEDGER_HEADER:
            raise ValueError("existing sampling ledger schema mismatch")
    source_order_override, replacement_summary_sha256 = (
        load_replacement_source_order(
            args.replacement_summary,
            source_rows,
            deterministic_rows,
            model_rows,
            existing_ledger,
            screen_summary,
        )
    )
    frozen, ledger, replacements, summary = freeze_sample(
        source_rows,
        deterministic_rows,
        model_rows,
        args.freeze_utc,
        source_order_override,
    )
    summary["sampling_screen_summary_sha256"] = screen_summary_sha256
    summary["source_replacement_summary_sha256"] = (
        replacement_summary_sha256
    )
    correction_path = args.frozen_output.parent / "frozen_text_corrections.csv"
    if correction_path.exists() and read_csv(correction_path)[1]:
        correction_audit = prior_freeze_summary.get(
            "pre_test_text_correction"
        )
        if not isinstance(correction_audit, dict):
            raise ValueError(
                "cannot overwrite a corrected freeze without its audit record"
            )
        post_correction = correction_audit.get("post_correction")
        if (
            not isinstance(post_correction, dict)
            or post_correction.get("frozen_test_claims_sha256")
            != summary["frozen_claims_sha256"]
            or post_correction.get("sampling_screen_summary_sha256")
            != screen_summary_sha256
        ):
            raise ValueError(
                "repeated freeze differs from the corrected frozen artifacts"
            )
        summary["pre_test_text_correction"] = correction_audit
    from apply_source_replacements import replacement_event_ids

    if args.replacement_summary.exists():
        replacement_summary = json.loads(
            args.replacement_summary.read_text(encoding="utf-8")
        )
        applied_ledger_count = len(
            replacement_event_ids(replacement_summary)
        )
    else:
        applied_ledger_count = 0
    pending_ledger = existing_ledger[applied_ledger_count:]
    if len(existing_ledger) < applied_ledger_count:
        raise ValueError("existing ledger is shorter than replacement chain")
    if summary["replacement_required"] and pending_ledger:
        comparable_fields = [
            field
            for field in LEDGER_HEADER
            if field not in {"ledger_event_id", "recorded_utc", "record_sha256"}
        ]
        if len(pending_ledger) != len(ledger) or any(
            {
                field: str(existing.get(field, ""))
                for field in comparable_fields
            }
            != {
                field: str(proposed.get(field, ""))
                for field in comparable_fields
            }
            for existing, proposed in zip(pending_ledger, ledger)
        ):
            raise ValueError(
                "unapplied ledger suffix differs from the repeated freeze result"
            )
        combined_ledger: list[Mapping[str, object]] = list(existing_ledger)
    else:
        if pending_ledger:
            raise ValueError(
                "cannot freeze claims while replacement ledger events are unapplied"
            )
        for offset, row in enumerate(ledger, start=len(existing_ledger) + 1):
            row["ledger_event_id"] = f"SR-{offset:03d}"
            row["record_sha256"] = canonical_json_sha256(
                {
                    field: str(row[field])
                    for field in LEDGER_HEADER
                    if field != "record_sha256"
                }
            )
        combined_ledger = [*existing_ledger, *ledger]
    existing_replacements: list[dict[str, str]] = []
    if args.replacement_output.exists():
        replacement_header, existing_replacements = read_csv(
            args.replacement_output
        )
        if replacement_header != REPLACEMENT_HEADER:
            raise ValueError("existing replacement exclusion schema mismatch")
    replacements_by_source = {
        row["source_key"]: row for row in existing_replacements
    }
    for row in replacements:
        replacements_by_source[row["source_key"]] = row
    combined_replacements = [
        replacements_by_source[source_key]
        for source_key in sorted(replacements_by_source)
    ]
    summary["ledger_events"] = len(combined_ledger)
    write_atomic(
        args.ledger_output, serialize_csv(LEDGER_HEADER, combined_ledger)
    )
    write_atomic(
        args.replacement_output,
        serialize_csv(REPLACEMENT_HEADER, combined_replacements),
    )
    write_atomic(
        args.summary_output,
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    if summary["replacement_required"]:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 2
    write_atomic(args.frozen_output, serialize_csv(FROZEN_HEADER, frozen))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
