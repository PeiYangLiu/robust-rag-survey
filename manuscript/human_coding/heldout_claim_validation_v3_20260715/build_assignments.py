#!/usr/bin/env python3
"""Build deterministic four-arm 3-of-6 balanced auditor assignments.

The script reads only anonymous participant IDs and frozen claim identifiers.
It never reads, creates, or infers a test label.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


ARMS = ("A", "B", "C", "D")
DEFAULT_SEED = 2026071503
DEFAULT_EXPECTED_CLAIMS = 480
DEFAULT_EXPECTED_SOURCES = 80
DEFAULT_MAX_PER_SOURCE = 6
AUDITORS_PER_ARM = 6
RATINGS_PER_CLAIM_ARM = 3
PACKET_VERSION = "v3.0.0-test-freeze"
ASSIGNMENT_HEADER = (
    "assignment_id",
    "claim_id",
    "source_key",
    "arm",
    "participant_id",
    "block_id",
    "block_position",
    "participant_item_order",
    "assignment_seed",
    "packet_version",
)


@dataclass(frozen=True)
class Claim:
    claim_id: str
    source_key: str


def stable_digest(seed: int, namespace: str, value: str) -> str:
    """Return a cross-version deterministic ordering key."""

    payload = f"{seed}|{namespace}|{value}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_unique_nonempty(values: Iterable[str], name: str) -> list[str]:
    cleaned = [value.strip() for value in values]
    if any(not value for value in cleaned):
        raise ValueError(f"{name} contains an empty value")
    duplicates = sorted(value for value, count in Counter(cleaned).items() if count > 1)
    if duplicates:
        raise ValueError(f"{name} contains duplicate values: {duplicates[:5]}")
    return cleaned


def read_claims(path: Path) -> list[Claim]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"claim_id", "source_key"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain columns {sorted(required)}")
        rows = list(reader)
    claims = [
        Claim(
            claim_id=(row.get("claim_id") or "").strip(),
            source_key=(row.get("source_key") or "").strip(),
        )
        for row in rows
    ]
    require_unique_nonempty((claim.claim_id for claim in claims), "claim_id")
    if any(not claim.source_key for claim in claims):
        raise ValueError("source_key contains an empty value")
    return claims


def read_primary_auditor_ids(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"participant_id", "role"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain columns {sorted(required)}")
        all_rows = list(reader)
    all_ids = require_unique_nonempty(
        ((row.get("participant_id") or "") for row in all_rows), "participant_id"
    )
    if len(all_ids) != len(all_rows):
        raise AssertionError("participant ID validation failed")
    auditor_ids: list[str] = []
    for row in all_rows:
        role = (row.get("role") or "").strip().lower()
        replacement_status = (row.get("replacement_status") or "").strip().lower()
        if role == "auditor" and replacement_status not in {"reserve", "inactive"}:
            auditor_ids.append((row.get("participant_id") or "").strip())
    return require_unique_nonempty(auditor_ids, "primary auditor participant_id")


def assign_participants_to_arms(
    participant_ids: Sequence[str], seed: int
) -> dict[str, tuple[str, ...]]:
    expected = len(ARMS) * AUDITORS_PER_ARM
    if len(participant_ids) != expected:
        raise ValueError(
            f"expected exactly {expected} primary auditors, found {len(participant_ids)}"
        )
    ordered = sorted(
        require_unique_nonempty(participant_ids, "participant_id"),
        key=lambda participant_id: stable_digest(
            seed, "participant-arm", participant_id
        ),
    )
    return {
        arm: tuple(
            ordered[
                arm_index * AUDITORS_PER_ARM : (arm_index + 1)
                * AUDITORS_PER_ARM
            ]
        )
        for arm_index, arm in enumerate(ARMS)
    }


def validate_claim_design(
    claims: Sequence[Claim],
    expected_claims: int,
    expected_sources: int,
    max_per_source: int,
    development_source_keys: set[str] | None = None,
) -> dict[str, int]:
    require_unique_nonempty((claim.claim_id for claim in claims), "claim_id")
    if len(claims) != expected_claims:
        raise ValueError(f"expected {expected_claims} claims, found {len(claims)}")
    if len(claims) % 20 != 0:
        raise ValueError(
            "claim count must be divisible by 20 for complete 3-of-6 blocks"
        )
    source_counts = Counter(claim.source_key for claim in claims)
    if "" in source_counts:
        raise ValueError("source_key contains an empty value")
    if len(source_counts) != expected_sources:
        raise ValueError(
            f"expected {expected_sources} distinct sources, found {len(source_counts)}"
        )
    too_large = {
        source: count for source, count in source_counts.items() if count > max_per_source
    }
    if too_large:
        raise ValueError(f"source claim cap exceeded: {too_large}")
    if development_source_keys:
        overlap = sorted(set(source_counts).intersection(development_source_keys))
        if overlap:
            raise ValueError(f"development sources present in test claims: {overlap}")
    return dict(source_counts)


def build_assignments(
    claims: Sequence[Claim],
    participant_ids: Sequence[str],
    seed: int = DEFAULT_SEED,
) -> list[dict[str, str]]:
    """Construct complete 3-of-6 blocks for each of four disjoint arms."""

    if len(claims) % 20 != 0:
        raise ValueError("complete balance requires a multiple of 20 claims")
    arm_participants = assign_participants_to_arms(participant_ids, seed)
    ordered_claims = sorted(
        claims,
        key=lambda claim: stable_digest(seed, "claim-order", claim.claim_id),
    )
    assignments: list[dict[str, str]] = []

    for arm in ARMS:
        participants = arm_participants[arm]
        triples = list(itertools.combinations(participants, RATINGS_PER_CLAIM_ARM))
        if len(triples) != 20:
            raise AssertionError("six choose three must yield 20 blocks")
        for cycle_index in range(len(ordered_claims) // 20):
            cycle_claims = ordered_claims[cycle_index * 20 : (cycle_index + 1) * 20]
            cycle_triples = sorted(
                triples,
                key=lambda triple: stable_digest(
                    seed,
                    f"block-order-{arm}-{cycle_index + 1}",
                    "|".join(triple),
                ),
            )
            for block_position, (claim, triple) in enumerate(
                zip(cycle_claims, cycle_triples), start=1
            ):
                for participant_id in triple:
                    identity = (
                        f"{arm}|{claim.claim_id}|{participant_id}|{seed}"
                    )
                    assignment_id = (
                        f"asg_{arm.lower()}_"
                        f"{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]}"
                    )
                    assignments.append(
                        {
                            "assignment_id": assignment_id,
                            "claim_id": claim.claim_id,
                            "source_key": claim.source_key,
                            "arm": arm,
                            "participant_id": participant_id,
                            "block_id": f"{arm}_block_{cycle_index + 1:03d}",
                            "block_position": str(block_position),
                            "participant_item_order": "",
                            "assignment_seed": str(seed),
                            "packet_version": PACKET_VERSION,
                        }
                    )

    by_participant: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in assignments:
        by_participant[row["participant_id"]].append(row)
    for participant_id, rows in by_participant.items():
        rows.sort(
            key=lambda row: stable_digest(
                seed,
                f"participant-order-{participant_id}",
                row["assignment_id"],
            )
        )
        for item_order, row in enumerate(rows, start=1):
            row["participant_item_order"] = str(item_order)

    assignments.sort(
        key=lambda row: (
            row["arm"],
            row["participant_id"],
            int(row["participant_item_order"]),
        )
    )
    return assignments


def validate_assignment_rows(
    rows: Sequence[Mapping[str, str]],
    claims: Sequence[Claim],
    expected_participant_ids: Sequence[str],
    seed: int,
) -> dict[str, object]:
    """Hard-check coverage, disjointness, workload, and pair balance."""

    claim_by_id = {claim.claim_id: claim for claim in claims}
    expected_participants = set(expected_participant_ids)
    assignment_ids = require_unique_nonempty(
        (row.get("assignment_id", "") for row in rows), "assignment_id"
    )
    if len(assignment_ids) != len(rows):
        raise AssertionError("assignment ID count mismatch")
    expected_rows = len(claims) * len(ARMS) * RATINGS_PER_CLAIM_ARM
    if len(rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} assignment rows, found {len(rows)}")

    coverage: Counter[tuple[str, str]] = Counter()
    raters: dict[tuple[str, str], set[str]] = defaultdict(set)
    participant_arms: dict[str, set[str]] = defaultdict(set)
    workloads: Counter[str] = Counter()
    triples_by_claim_arm: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in rows:
        claim_id = row.get("claim_id", "")
        source_key = row.get("source_key", "")
        arm = row.get("arm", "")
        participant_id = row.get("participant_id", "")
        if claim_id not in claim_by_id:
            raise ValueError(f"assignment references unknown claim: {claim_id}")
        if source_key != claim_by_id[claim_id].source_key:
            raise ValueError(f"source mismatch for claim {claim_id}")
        if arm not in ARMS:
            raise ValueError(f"unknown arm: {arm}")
        if participant_id not in expected_participants:
            raise ValueError(f"unknown primary auditor: {participant_id}")
        if row.get("assignment_seed", "") != str(seed):
            raise ValueError("assignment seed mismatch")
        if row.get("packet_version", "") != PACKET_VERSION:
            raise ValueError("packet version mismatch")
        coverage[(claim_id, arm)] += 1
        raters[(claim_id, arm)].add(participant_id)
        triples_by_claim_arm[(claim_id, arm)].add(participant_id)
        participant_arms[participant_id].add(arm)
        workloads[participant_id] += 1

    expected_pairs = {(claim.claim_id, arm) for claim in claims for arm in ARMS}
    if set(coverage) != expected_pairs:
        raise ValueError("not every claim appears in every arm")
    bad_coverage = {
        key: count
        for key, count in coverage.items()
        if count != RATINGS_PER_CLAIM_ARM or len(raters[key]) != RATINGS_PER_CLAIM_ARM
    }
    if bad_coverage:
        raise ValueError(f"claim-arm coverage failure: {list(bad_coverage.items())[:5]}")
    if set(participant_arms) != expected_participants:
        raise ValueError("not every primary auditor has an assignment")
    cross_arm = {
        participant_id: sorted(arms)
        for participant_id, arms in participant_arms.items()
        if len(arms) != 1
    }
    if cross_arm:
        raise ValueError(f"participants assigned across arms: {cross_arm}")
    arm_counts = Counter(next(iter(arms)) for arms in participant_arms.values())
    if any(arm_counts[arm] != AUDITORS_PER_ARM for arm in ARMS):
        raise ValueError(f"arm auditor counts are not six each: {dict(arm_counts)}")
    if max(workloads.values()) - min(workloads.values()) > 0:
        raise ValueError(f"workloads are not exactly balanced: {dict(workloads)}")

    pair_counts_by_arm: dict[str, Counter[tuple[str, str]]] = {
        arm: Counter() for arm in ARMS
    }
    for (claim_id, arm), triple in triples_by_claim_arm.items():
        del claim_id
        for pair in itertools.combinations(sorted(triple), 2):
            pair_counts_by_arm[arm][pair] += 1
    pair_ranges: dict[str, tuple[int, int]] = {}
    for arm, counts in pair_counts_by_arm.items():
        if len(counts) != math_comb(AUDITORS_PER_ARM, 2):
            raise ValueError(f"not every within-arm auditor pair appears in arm {arm}")
        pair_ranges[arm] = (min(counts.values()), max(counts.values()))
        if pair_ranges[arm][0] != pair_ranges[arm][1]:
            raise ValueError(f"auditor-pair balance failed in arm {arm}")

    return {
        "assignment_rows": len(rows),
        "claim_arm_cells": len(coverage),
        "participants": len(participant_arms),
        "auditors_per_arm": {arm: arm_counts[arm] for arm in ARMS},
        "workload_per_participant": sorted(set(workloads.values())),
        "pair_occurrences_per_arm": {
            arm: pair_ranges[arm][0] for arm in ARMS
        },
    }


def math_comb(n: int, k: int) -> int:
    """Small local combination count without an extra runtime dependency."""

    if k < 0 or k > n:
        return 0
    numerator = 1
    denominator = 1
    for value in range(1, k + 1):
        numerator *= n - value + 1
        denominator *= value
    return numerator // denominator


def write_assignments(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    with staging.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ASSIGNMENT_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    staging.replace(path)


def read_development_keys(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def run_self_test() -> dict[str, object]:
    claims = [
        Claim(claim_id=f"synthetic_claim_{source:03d}_{item}", source_key=f"source_{source:03d}")
        for source in range(1, 81)
        for item in range(1, 7)
    ]
    participants = [f"auditor_{index:02d}" for index in range(1, 25)]
    validate_claim_design(claims, 480, 80, 6)
    rows = build_assignments(claims, participants, DEFAULT_SEED)
    summary = validate_assignment_rows(rows, claims, participants, DEFAULT_SEED)
    summary["self_test"] = "PASS"
    summary["persistent_files_written"] = 0
    return summary


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, default=root / "frozen_test_claims.csv")
    parser.add_argument(
        "--participants",
        type=Path,
        default=root / "participant_metadata_private_template.csv",
    )
    parser.add_argument(
        "--output", type=Path, default=root / "auditor_assignments.csv"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--expected-claims", type=int, default=DEFAULT_EXPECTED_CLAIMS)
    parser.add_argument("--expected-sources", type=int, default=DEFAULT_EXPECTED_SOURCES)
    parser.add_argument("--max-per-source", type=int, default=DEFAULT_MAX_PER_SOURCE)
    parser.add_argument(
        "--development-source-keys",
        type=Path,
        default=root / "DEVELOPMENT_SOURCE_KEYS.txt",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run an in-memory 480-claim test and write no files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2, sort_keys=True))
        return 0

    claims = read_claims(args.claims)
    participant_ids = read_primary_auditor_ids(args.participants)
    development_keys = read_development_keys(args.development_source_keys)
    source_counts = validate_claim_design(
        claims,
        args.expected_claims,
        args.expected_sources,
        args.max_per_source,
        development_keys,
    )
    rows = build_assignments(claims, participant_ids, args.seed)
    summary = validate_assignment_rows(rows, claims, participant_ids, args.seed)
    write_assignments(args.output, rows)
    summary["output"] = str(args.output)
    summary["sources"] = len(source_counts)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
