#!/usr/bin/env python3
"""Build role-isolated, answer-free packets for the frozen calibration set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


PACKAGE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PACKAGE / "generated_calibration_packets"
CALIBRATION_VERSION = "v3.0.1-calibration-freeze"
CALIBRATION_ITEM_COUNT = 10
CALIBRATION_ORDER_NAMESPACE = "heldout-v3-calibration-order-v1"
CONSTRUCTION_STATUS = "INSTRUCTOR_CONSTRUCTED_NOT_A_REAL_PAPER"
SOURCE_TYPE = "SELF_CONTAINED_FICTIONAL_INSTRUCTOR_DOSSIER"
ANSWER_KEY_STATUS = (
    "INSTRUCTOR_CONSTRUCTED_CALIBRATION_KEY_NOT_HUMAN_TEST_GOLD"
)

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

ITEM_HEADER = (
    "calibration_item_id",
    "calibration_source_key",
    "dossier_title",
    "construction_status",
    "source_type",
    "source_excerpt",
    "source_table",
    "experimental_setup",
    "audited_claim",
    "source_locator",
    "item_record_sha256",
)
ITEM_HASH_FIELDS = ITEM_HEADER[:-1]
ANSWER_KEY_HEADER = (
    "calibration_item_id",
    "calibration_source_key",
    "item_record_sha256",
    "answer_key_status",
    "evidence_support_label",
    "evidence_answer_basis",
    "narrower_supported_wording",
    "comparability_label",
    "comparability_answer_basis",
    "supported_comparison_scope",
    "decisive_case_tags",
    "evidence_feedback_code",
    "comparability_feedback_code",
)
PRIVATE_ROSTER_HEADER = (
    "participant_id",
    "role",
    "assigned_arm",
    "legal_name",
    "email",
    "affiliation",
    "expertise_description",
    "recruitment_channel",
    "consent_record_locator",
    "consent_date",
    "compensation_record_locator",
    "conflict_of_interest_detail",
    "replacement_status",
    "notes_private",
)
PUBLIC_ROSTER_HEADER = (
    "participant_id",
    "role",
    "assigned_arm",
    "expertise_tier",
    "years_experience_band",
    "calibration_status",
    "replacement_status",
    "included_in_primary_analysis",
)
PACKET_HEADER = (
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
    "dossier_title",
    "construction_status",
    "source_type",
    "source_excerpt",
    "source_table",
    "experimental_setup",
    "claim_text",
    "source_locator",
    "response_status",
    "missing_reason_code",
    "evidence_support_label",
    "evidence_support_reason",
    "comparability_label",
    "comparability_reason",
    "completed_utc",
)
PACKET_ITEM_MAP = {
    "calibration_item_id": "calibration_item_id",
    "calibration_source_key": "calibration_source_key",
    "item_record_sha256": "item_record_sha256",
    "dossier_title": "dossier_title",
    "construction_status": "construction_status",
    "source_type": "source_type",
    "source_excerpt": "source_excerpt",
    "source_table": "source_table",
    "experimental_setup": "experimental_setup",
    "claim_text": "audited_claim",
    "source_locator": "source_locator",
}
RESPONSE_FIELDS = (
    "response_status",
    "missing_reason_code",
    "evidence_support_label",
    "evidence_support_reason",
    "comparability_label",
    "comparability_reason",
    "completed_utc",
)

COMMON_OUTPUT_INSTRUCTIONS = """## Required common outputs

Return two separate labels; never combine them into one verdict.

Evidence-support label:
- `supported_as_written`: every material proposition, direction, magnitude,
  quantifier, scope, and causal force is supported.
- `supported_after_narrowing`: a specific nontrivial narrower wording is
  supported. Put that wording in the reason.
- `contradicted`: an explicit dossier fact conflicts with a material part.
- `insufficient_source_evidence`: the dossier lacks facts needed to check a
  material proposition.

Comparability label:
- `same_estimand`: the compared sides answer the same scientific question at
  the claim's stated scope.
- `comparable_with_declared_scope`: a like-for-like conclusion requires an
  explicit scope restriction; state it.
- `different_estimand`: the sides answer materially different questions.
- `missing_comparison_assumption`: a named, decision-critical unreported
  assumption could make the comparison valid or invalid.
- `not_a_comparability_claim`: the claim does not rank, contrast, transfer,
  pool, or recommend alternatives.

Use only the self-contained dossier. Recompute every stated number and inspect
all rows covered by a quantifier. Fill only the seven response fields. A
completed response needs both labels, both reasons, and a UTC completion time.
"""

ARM_INSTRUCTIONS = {
    "A": """# Auditor Arm A calibration instructions

Use conventional source verification. Check the full dossier, numbers,
direction, quantifiers, scope, causal wording, and ordinary experimental
controls. Identify the compared items and measured quantity in ordinary
scientific-review language. Do not use a structured worksheet beyond those
checks.
""",
    "B": """# Auditor Arm B calibration instructions

Use a PICO-style review plus standard controls. Before labeling, write in your
reasoning the population or experimental setting, intervention, comparison,
outcome definition and unit, aggregation, baseline, and relevant reported or
missing controls.
""",
    "C": """# Auditor Arm C calibration instructions

Use conventional exact-source verification. Read the complete dossier before
labeling. Verify reported numbers against the table, inspect every row named by
a quantifier, distinguish descriptive from causal wording, and check whether
the stated methods, measurements, and ordinary experimental controls match the
claim. Describe compared sides and measured quantities in ordinary scientific
language. Do not infer an unreported fact.
""",
    "D": """# Auditor Arm D calibration instructions

Use the full frozen v3 diagnostic sequence:

- C1 evidence state: what reaches the decision boundary and whether exchanging
  the states changes the question.
- C2 origin or attacker capability: how the condition arose, access, knowledge,
  budget, target scope, and adaptive access; determine transfer scope.
- C3 intervention: changed component, fixed pipeline, and whether roles are
  alternative, complementary, or incomparable.
- C4 outcome and unit: definition, direction, unit, aggregation, denominator,
  baseline, and uncertainty.
- C5 policy and utility: action set, operating point, coverage, alternatives,
  stakes, costs, and shared utility.

Also check all claim-specific controls before composing the two common outputs.
""",
}

PLAIN_LANGUAGE_INSTRUCTIONS = """# Plain-language calibration instructions

Use only this ordinary-language rubric. Read the exact claim and every supplied
source fact. Record passages and calculations supporting each answer.

First ask whether the source supports the important proposition, direction,
magnitude, quantifier, scope, and causal strength. Use the four evidence labels
defined below.

Then decide whether the sentence actually ranks, contrasts, transfers, pools,
or recommends alternatives. If it does not, use
`not_a_comparability_claim`. Otherwise write what is compared; what is measured
and in which unit, population, and aggregation; the circumstances on each side;
what each method changes and holds fixed; whether an action, coverage level,
operating point, stake, or cost matters; and which unreported fact could change
the conclusion. Use the five comparability labels defined below.

Base both outputs only on the ordinary-language questions above and the
self-contained dossier facts.
"""

NEUTRAL_DOSSIER_TITLE_RE = re.compile(r"^Calibration dossier \d{2}$")
FORBIDDEN_ITEM_PROMPT_FIELDS = frozenset(
    {
        "calculation_or_logic_check",
        "comparison_check",
        "diagnostic_prompt",
        "item_specific_question",
    }
)
ARM_C_FORBIDDEN_PROMPT_TERMS = (
    "origin",
    "capability",
    "attacker access",
    "budget",
    "policy",
    "utility",
    "cost",
    "stakes",
    "coverage",
)


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


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


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def item_record_sha256(row: Mapping[str, str]) -> str:
    return canonical_sha256(
        {field: (row.get(field) or "") for field in ITEM_HASH_FIELDS}
    )


def calibration_set_sha256(rows: Sequence[Mapping[str, str]]) -> str:
    return canonical_sha256(
        {
            "calibration_version": CALIBRATION_VERSION,
            "items": [
                {
                    "calibration_item_id": (row.get("calibration_item_id") or ""),
                    "item_record_sha256": (row.get("item_record_sha256") or ""),
                }
                for row in sorted(
                    rows, key=lambda value: value["calibration_item_id"]
                )
            ],
        }
    )


def read_calibration_items(path: Path) -> list[dict[str, str]]:
    header, rows = read_csv(path)
    if header != ITEM_HEADER:
        raise ValueError(f"{path} does not use the frozen calibration-item schema")
    if len(rows) != CALIBRATION_ITEM_COUNT:
        raise ValueError(
            f"{path} must contain exactly {CALIBRATION_ITEM_COUNT} items"
        )
    item_ids = [(row.get("calibration_item_id") or "").strip() for row in rows]
    source_keys = [
        (row.get("calibration_source_key") or "").strip() for row in rows
    ]
    if "" in item_ids or len(item_ids) != len(set(item_ids)):
        raise ValueError("calibration item IDs must be unique and nonempty")
    if "" in source_keys or len(source_keys) != len(set(source_keys)):
        raise ValueError("calibration source keys must be unique and nonempty")
    for index, row in enumerate(rows, start=2):
        for field in ITEM_HASH_FIELDS:
            if not (row.get(field) or "").strip():
                raise ValueError(f"calibration item row {index} has empty {field}")
        if not NEUTRAL_DOSSIER_TITLE_RE.fullmatch(row["dossier_title"]):
            raise ValueError(
                f"calibration item row {index} does not use a neutral dossier title"
            )
        if any(
            "?" in row[field]
            for field in (
                "dossier_title",
                "source_excerpt",
                "source_table",
                "experimental_setup",
                "source_locator",
            )
        ):
            raise ValueError(
                f"calibration item row {index} contains an item-specific question"
            )
        if row["construction_status"] != CONSTRUCTION_STATUS:
            raise ValueError(f"calibration item row {index} has wrong construction status")
        if row["source_type"] != SOURCE_TYPE:
            raise ValueError(f"calibration item row {index} has wrong source type")
        if row["item_record_sha256"] != item_record_sha256(row):
            raise ValueError(f"calibration item row {index} has an invalid record hash")
    if rows != sorted(rows, key=lambda row: row["calibration_item_id"]):
        raise ValueError("calibration items are not in canonical item-ID order")
    return rows


def read_calibration_key(
    path: Path, items: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    header, rows = read_csv(path)
    if header != ANSWER_KEY_HEADER:
        raise ValueError(f"{path} does not use the frozen answer-key schema")
    if len(rows) != CALIBRATION_ITEM_COUNT:
        raise ValueError("calibration answer key must contain exactly ten rows")
    items_by_id = {row["calibration_item_id"]: row for row in items}
    key_ids = [(row.get("calibration_item_id") or "").strip() for row in rows]
    if len(key_ids) != len(set(key_ids)) or set(key_ids) != set(items_by_id):
        raise ValueError("answer key does not exactly cover the calibration items")
    for index, row in enumerate(rows, start=2):
        item = items_by_id[row["calibration_item_id"]]
        if row["calibration_source_key"] != item["calibration_source_key"]:
            raise ValueError(f"answer key row {index} changed the source key")
        if row["item_record_sha256"] != item["item_record_sha256"]:
            raise ValueError(f"answer key row {index} changed the item hash")
        if row["answer_key_status"] != ANSWER_KEY_STATUS:
            raise ValueError(f"answer key row {index} has the wrong status")
        if row["evidence_support_label"] not in EVIDENCE_LABELS:
            raise ValueError(f"answer key row {index} has an invalid evidence label")
        if row["comparability_label"] not in COMPARABILITY_LABELS:
            raise ValueError(
                f"answer key row {index} has an invalid comparability label"
            )
        for field in (
            "evidence_answer_basis",
            "comparability_answer_basis",
            "decisive_case_tags",
            "evidence_feedback_code",
            "comparability_feedback_code",
        ):
            if not row[field].strip():
                raise ValueError(f"answer key row {index} has empty {field}")
        if (
            row["evidence_support_label"] == "supported_after_narrowing"
            and not row["narrower_supported_wording"].strip()
        ):
            raise ValueError(f"answer key row {index} lacks narrower wording")
        if (
            row["comparability_label"] == "comparable_with_declared_scope"
            and not row["supported_comparison_scope"].strip()
        ):
            raise ValueError(f"answer key row {index} lacks a supported scope")
    if rows != sorted(rows, key=lambda row: row["calibration_item_id"]):
        raise ValueError("calibration key is not in canonical item-ID order")
    return rows


def frozen_identifiers(path: Path) -> tuple[set[str], set[str]]:
    header, rows = read_csv(path)
    if not {"claim_id", "source_key"}.issubset(header):
        raise ValueError(f"{path} lacks frozen claim/source identifiers")
    return (
        {(row.get("claim_id") or "").strip() for row in rows},
        {(row.get("source_key") or "").strip() for row in rows},
    )


def assert_test_disjoint(
    items: Sequence[Mapping[str, str]], frozen_claims_path: Path
) -> None:
    test_claim_ids, test_source_keys = frozen_identifiers(frozen_claims_path)
    item_ids = {row["calibration_item_id"] for row in items}
    calibration_sources = {row["calibration_source_key"] for row in items}
    claim_overlap = sorted((item_ids & test_claim_ids) - {""})
    source_overlap = sorted((calibration_sources & test_source_keys) - {""})
    calibration_text = "\n".join(
        value for row in items for value in row.values()
    )
    content_overlap = sorted(
        identifier
        for identifier in (test_claim_ids | test_source_keys) - {""}
        if identifier in calibration_text
    )
    if claim_overlap or source_overlap or content_overlap:
        raise ValueError(
            "calibration/test identifier leakage: "
            f"claims={claim_overlap}, sources={source_overlap}, "
            f"content={content_overlap}"
        )


def read_private_roster(path: Path) -> list[dict[str, str]]:
    header, rows = read_csv(path)
    if header != PRIVATE_ROSTER_HEADER:
        raise ValueError(
            "calibration packet construction requires the strict private-roster schema"
        )
    if len(rows) != 29:
        raise ValueError(f"strict calibration roster requires 29 rows, found {len(rows)}")
    participant_ids = [(row.get("participant_id") or "").strip() for row in rows]
    if "" in participant_ids or len(participant_ids) != len(set(participant_ids)):
        raise ValueError("private roster participant IDs must be unique and nonempty")
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
        raise ValueError(f"private roster role counts are invalid: {dict(roles)}")
    auditor_arms: Counter[str] = Counter()
    for index, row in enumerate(rows, start=2):
        role = row["role"].strip().lower()
        arm = row["assigned_arm"].strip().upper()
        replacement = row["replacement_status"].strip().lower()
        if replacement in {"reserve", "inactive"}:
            raise ValueError(f"private roster row {index} is not an active participant")
        if role == "auditor":
            if arm not in ARM_INSTRUCTIONS:
                raise ValueError(f"auditor row {index} has invalid assigned arm")
            auditor_arms[arm] += 1
        elif arm:
            raise ValueError(f"non-auditor row {index} must have a blank assigned arm")
    if auditor_arms != Counter({"A": 6, "B": 6, "C": 6, "D": 6}):
        raise ValueError(f"auditor arm counts are invalid: {dict(auditor_arms)}")
    return rows


def participant_item_digest(participant_id: str, item_id: str) -> str:
    return hashlib.sha256(
        f"{CALIBRATION_ORDER_NAMESPACE}|{participant_id}|{item_id}".encode("utf-8")
    ).hexdigest()


def calibration_response_id(
    participant_id: str, calibration_round: int, item_id: str
) -> str:
    digest = hashlib.sha256(
        (
            f"{CALIBRATION_VERSION}|{participant_id}|"
            f"{calibration_round}|{item_id}"
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"cal_{digest}"


def safe_participant_slug(role: str, participant_id: str) -> str:
    digest = hashlib.sha256(
        f"calibration-packet|{role}|{participant_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{role}_{digest}"


def instructions_for(role: str, arm: str) -> str:
    normalized_role = role.strip().lower()
    if normalized_role == "auditor":
        if arm not in ARM_INSTRUCTIONS:
            raise ValueError(f"unknown auditor arm: {arm}")
        text = ARM_INSTRUCTIONS[arm] + "\n" + COMMON_OUTPUT_INSTRUCTIONS
    elif normalized_role in {"gold_expert", "adjudicator_1", "adjudicator_2"}:
        text = PLAIN_LANGUAGE_INSTRUCTIONS + "\n" + COMMON_OUTPUT_INSTRUCTIONS
    else:
        raise ValueError(f"unknown calibration role: {role}")
    validate_instruction_isolation(normalized_role, arm, text)
    return text


def validate_instruction_isolation(role: str, arm: str, text: str) -> None:
    coordinate_pattern = re.compile(r"\bC[1-5]\b", flags=re.IGNORECASE)
    if role in {"gold_expert", "adjudicator_1", "adjudicator_2"}:
        if coordinate_pattern.search(text):
            raise ValueError("plain-language calibration instruction leaks C1-C5")
        forbidden_plain_phrases = (
            "coordinate",
            "origin or attacker capability",
            "policy and utility",
            "answer key",
        )
        if any(phrase in text.lower() for phrase in forbidden_plain_phrases):
            raise ValueError(
                "plain-language calibration instruction leaks coordinate/key vocabulary"
            )
    if role == "auditor":
        other_arms = {value for value in ARM_INSTRUCTIONS if value != arm}
        leaked_arms = [value for value in other_arms if f"Arm {value}" in text]
        if leaked_arms:
            raise ValueError(f"auditor instruction leaks other arms: {leaked_arms}")
        if arm == "C":
            lowered = text.lower()
            leaks = [
                term
                for term in ARM_C_FORBIDDEN_PROMPT_TERMS
                if term in lowered
            ]
            if re.search(r"\bC(?:2|5)\b", text, flags=re.IGNORECASE) or leaks:
                raise ValueError(
                    f"Arm C calibration instruction leaks ablated prompts: {leaks}"
                )


def validate_packet_isolation(
    role: str,
    arm: str,
    rows: Sequence[Mapping[str, str]],
) -> None:
    lowered_header = {field.lower() for field in PACKET_HEADER}
    leaked_fields = sorted(lowered_header.intersection(FORBIDDEN_ITEM_PROMPT_FIELDS))
    if leaked_fields:
        raise ValueError(
            f"participant calibration packet has answer-directed fields: {leaked_fields}"
        )
    if role == "auditor" and arm == "C":
        specialized_fields = sorted(
            field
            for field in lowered_header
            if any(
                token.replace(" ", "_") in field
                for token in ARM_C_FORBIDDEN_PROMPT_TERMS
            )
        )
        if specialized_fields:
            raise ValueError(
                f"Arm C calibration packet has ablated schema fields: "
                f"{specialized_fields}"
            )
    for row in rows:
        if not NEUTRAL_DOSSIER_TITLE_RE.fullmatch(
            (row.get("dossier_title") or "").strip()
        ):
            raise ValueError("participant packet contains a diagnostic dossier title")


def build_packet_rows(
    participant: Mapping[str, str],
    items: Sequence[Mapping[str, str]],
    calibration_round: int,
) -> list[dict[str, str]]:
    participant_id = participant["participant_id"].strip()
    role = participant["role"].strip().lower()
    arm = participant["assigned_arm"].strip().upper()
    set_hash = calibration_set_sha256(items)
    ordered = sorted(
        items,
        key=lambda item: participant_item_digest(
            participant_id, item["calibration_item_id"]
        ),
    )
    rows: list[dict[str, str]] = []
    for display_order, item in enumerate(ordered, start=1):
        row = {field: "" for field in PACKET_HEADER}
        row.update(
            {
                "calibration_response_id": calibration_response_id(
                    participant_id,
                    calibration_round,
                    item["calibration_item_id"],
                ),
                "calibration_round": str(calibration_round),
                "participant_id": participant_id,
                "participant_role": role,
                "assigned_arm": arm,
                "display_order": str(display_order),
                "packet_version": CALIBRATION_VERSION,
                "calibration_set_sha256": set_hash,
            }
        )
        for packet_field, item_field in PACKET_ITEM_MAP.items():
            row[packet_field] = item[item_field]
        rows.append(row)
    return rows


def read_round2_eligible(
    public_roster_path: Path, summary_path: Path, private_ids: set[str]
) -> set[str]:
    header, public_rows = read_csv(public_roster_path)
    if header != PUBLIC_ROSTER_HEADER:
        raise ValueError("round-2 public roster has the wrong schema")
    public_by_id = {
        (row.get("participant_id") or "").strip(): row for row in public_rows
    }
    if set(public_by_id) != private_ids:
        raise ValueError("round-2 public and private roster IDs differ")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read round-2 calibration summary: {exc}") from exc
    summary_by_id = {
        str(record.get("participant_id", "")): record
        for record in summary.get("participants", [])
        if isinstance(record, dict)
    }
    eligible = {
        participant_id
        for participant_id, row in public_by_id.items()
        if row["calibration_status"].strip() == "retraining_required_round_2"
    }
    if not eligible:
        raise ValueError("no participant has fixed round-2 retraining status")
    for participant_id in eligible:
        record = summary_by_id.get(participant_id)
        if record is None or record.get("final_status") != (
            "retraining_required_round_2"
        ):
            raise ValueError(
                f"round-2 summary does not confirm eligibility for {participant_id}"
            )
        rounds = record.get("rounds")
        if not isinstance(rounds, list) or len(rounds) != 1:
            raise ValueError(f"round-2 eligibility lacks one scored first round")
        item_results = rounds[0].get("item_results")
        if not isinstance(item_results, list) or len(item_results) != 10:
            raise ValueError(f"round-2 eligibility lacks ten item-level results")
    return eligible


def assert_private_public_identity(
    private_rows: Sequence[Mapping[str, str]], public_roster_path: Path
) -> None:
    if not public_roster_path.exists():
        return
    header, public_rows = read_csv(public_roster_path)
    if header != PUBLIC_ROSTER_HEADER:
        raise ValueError("public calibration roster has the wrong schema")
    if not public_rows:
        return
    private_by_id = {row["participant_id"].strip(): row for row in private_rows}
    public_by_id = {
        (row.get("participant_id") or "").strip(): row for row in public_rows
    }
    if set(private_by_id) != set(public_by_id):
        raise ValueError("private and public calibration roster IDs differ")
    for participant_id, private in private_by_id.items():
        public = public_by_id[participant_id]
        if (
            private["role"].strip().lower()
            != public["role"].strip().lower()
            or private["assigned_arm"].strip().upper()
            != public["assigned_arm"].strip().upper()
            or private["replacement_status"].strip().lower()
            != public["replacement_status"].strip().lower()
        ):
            raise ValueError(
                f"private/public role, arm, or status differs for {participant_id}"
            )


def write_packets(
    output: Path,
    roster: Sequence[Mapping[str, str]],
    items: Sequence[Mapping[str, str]],
    calibration_round: int,
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for participant in sorted(roster, key=lambda row: row["participant_id"]):
        participant_id = participant["participant_id"].strip()
        role = participant["role"].strip().lower()
        arm = participant["assigned_arm"].strip().upper()
        relative_dir = Path(role) / safe_participant_slug(role, participant_id)
        instruction_path = output / relative_dir / "instructions.md"
        packet_path = output / relative_dir / (
            f"calibration_round_{calibration_round}.csv"
        )
        instruction_path.parent.mkdir(parents=True, exist_ok=True)
        instruction_path.write_text(
            instructions_for(role, arm).rstrip() + "\n", encoding="utf-8"
        )
        packet_rows = build_packet_rows(participant, items, calibration_round)
        validate_packet_isolation(role, arm, packet_rows)
        write_csv(packet_path, PACKET_HEADER, packet_rows)
        if any(row[field] for row in packet_rows for field in RESPONSE_FIELDS):
            raise AssertionError("packet builder populated a participant response")
        entries.append(
            {
                "participant_id": participant_id,
                "role": role,
                "assigned_arm": arm,
                "instruction_path": instruction_path.relative_to(output).as_posix(),
                "instruction_sha256": sha256_file(instruction_path),
                "packet_path": packet_path.relative_to(output).as_posix(),
                "packet_sha256": sha256_file(packet_path),
                "rows": len(packet_rows),
            }
        )
    manifest: dict[str, Any] = {
        "status": "FROZEN_CALIBRATION_PACKETS_NO_PARTICIPANT_RESPONSES",
        "calibration_version": CALIBRATION_VERSION,
        "calibration_round": calibration_round,
        "calibration_set_sha256": calibration_set_sha256(items),
        "participant_count": len(entries),
        "item_count_per_packet": CALIBRATION_ITEM_COUNT,
        "answer_key_included": False,
        "test_sources_or_claims_included": False,
        "participant_responses_generated": 0,
        "packets": entries,
    }
    manifest_path = output / "packet_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def render_calibration_materials(
    items: Sequence[Mapping[str, str]]
) -> str:
    lines = [
        "# Frozen instructor-constructed calibration materials",
        "",
        "**Not real publications; not held-out test sources; no participant "
        "responses or answer key.**",
        "",
        f"Calibration version: `{CALIBRATION_VERSION}`  ",
        f"Calibration set SHA-256: `{calibration_set_sha256(items)}`",
        "",
        "Each dossier is intentionally self-contained. Participant packets are "
        "generated by role; this reviewer artifact is not itself a packet.",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item['calibration_item_id']}: {item['dossier_title']}",
                "",
                f"- Instructor source key: `{item['calibration_source_key']}`",
                f"- Construction status: `{item['construction_status']}`",
                f"- Source type: `{item['source_type']}`",
                f"- Locator: {item['source_locator']}",
                f"- Item record SHA-256: `{item['item_record_sha256']}`",
                "",
                "### Source excerpt",
                "",
                item["source_excerpt"],
                "",
                "### Source table",
                "",
                "```text",
                item["source_table"],
                "```",
                "",
                "### Experimental setup",
                "",
                item["experimental_setup"],
                "",
                "### Claim to audit",
                "",
                f"> {item['audited_claim']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roster",
        type=Path,
        default=PACKAGE / "participant_metadata_private_template.csv",
        help="access-controlled 29-row private roster",
    )
    parser.add_argument(
        "--items", type=Path, default=PACKAGE / "calibration_items.csv"
    )
    parser.add_argument(
        "--frozen-claims", type=Path, default=PACKAGE / "frozen_test_claims.csv"
    )
    parser.add_argument(
        "--round", type=int, choices=(1, 2), default=1, dest="calibration_round"
    )
    parser.add_argument(
        "--public-roster",
        type=Path,
        default=PACKAGE / "participant_metadata_public_template.csv",
        help="required for round 2; contains no PII",
    )
    parser.add_argument(
        "--calibration-summary",
        type=Path,
        default=PACKAGE / "calibration_summary.json",
        help="required for round 2",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def anonymous_private_roster() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for arm in ARM_INSTRUCTIONS:
        for index in range(1, 7):
            row = {field: "" for field in PRIVATE_ROSTER_HEADER}
            row.update(
                {
                    "participant_id": f"anon_auditor_{arm}_{index:02d}",
                    "role": "auditor",
                    "assigned_arm": arm,
                    "replacement_status": "primary",
                }
            )
            rows.append(row)
    for index in range(1, 4):
        row = {field: "" for field in PRIVATE_ROSTER_HEADER}
        row.update(
            {
                "participant_id": f"anon_gold_{index:02d}",
                "role": "gold_expert",
                "replacement_status": "primary",
            }
        )
        rows.append(row)
    for index in (1, 2):
        row = {field: "" for field in PRIVATE_ROSTER_HEADER}
        row.update(
            {
                "participant_id": f"anon_adjudicator_{index}",
                "role": f"adjudicator_{index}",
                "replacement_status": "primary",
            }
        )
        rows.append(row)
    return rows


def self_test() -> None:
    workspace = PACKAGE / ".calibration_packet_selftest_workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    try:
        roster_path = workspace / "anonymous_private_roster.csv"
        output = workspace / "packets"
        write_csv(roster_path, PRIVATE_ROSTER_HEADER, anonymous_private_roster())
        roster = read_private_roster(roster_path)
        items = read_calibration_items(PACKAGE / "calibration_items.csv")
        read_calibration_key(PACKAGE / "calibration_answer_key.csv", items)
        assert_test_disjoint(items, PACKAGE / "frozen_test_claims.csv")
        manifest = write_packets(output, roster, items, 1)
        if manifest["participant_count"] != 29:
            raise AssertionError("self-test did not produce 29 anonymous packets")
        packet_files = sorted(output.rglob("calibration_round_1.csv"))
        if len(packet_files) != 29:
            raise AssertionError("self-test packet file count differs from 29")
        for packet_path in packet_files:
            header, rows = read_csv(packet_path)
            if header != PACKET_HEADER or len(rows) != 10:
                raise AssertionError("self-test packet schema/count failed")
            if set(header).intersection(FORBIDDEN_ITEM_PROMPT_FIELDS):
                raise AssertionError(
                    "self-test packet exposes an item-specific check field"
                )
            if any(row[field] for row in rows for field in RESPONSE_FIELDS):
                raise AssertionError("self-test generated a participant response")
            item_ids = {row["calibration_item_id"] for row in rows}
            if len(item_ids) != 10:
                raise AssertionError("self-test packet does not cover ten items")
            if any(
                not NEUTRAL_DOSSIER_TITLE_RE.fullmatch(row["dossier_title"])
                for row in rows
            ):
                raise AssertionError("self-test packet exposes diagnostic item titles")
        for instruction_path in output.rglob("instructions.md"):
            text = instruction_path.read_text(encoding="utf-8")
            relative = instruction_path.relative_to(output).parts
            role = relative[0]
            if role in {"gold_expert", "adjudicator_1", "adjudicator_2"}:
                if re.search(r"\bC[1-5]\b", text, flags=re.IGNORECASE):
                    raise AssertionError("plain-rubric packet leaked C1-C5")
        c_texts = [
            path.read_text(encoding="utf-8")
            for path in output.glob("auditor/auditor_*/instructions.md")
            if "Arm C" in path.read_text(encoding="utf-8")
        ]
        if len(c_texts) != 6 or any(
            re.search(r"\bC(?:2|5)\b", text, flags=re.IGNORECASE)
            or any(term in text.lower() for term in ARM_C_FORBIDDEN_PROMPT_TERMS)
            for text in c_texts
        ):
            raise AssertionError("Arm C instruction ablation failed")
        if any(path.name == "calibration_answer_key.csv" for path in output.rglob("*")):
            raise AssertionError("answer key entered a participant packet")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print("self-test passed; temporary anonymous roster and packets removed")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    items = read_calibration_items(args.items)
    assert_test_disjoint(items, args.frozen_claims)
    roster = read_private_roster(args.roster)
    assert_private_public_identity(roster, args.public_roster)
    if args.calibration_round == 2:
        eligible = read_round2_eligible(
            args.public_roster,
            args.calibration_summary,
            {row["participant_id"] for row in roster},
        )
        roster = [row for row in roster if row["participant_id"] in eligible]
    manifest = write_packets(
        args.output, roster, items, args.calibration_round
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
