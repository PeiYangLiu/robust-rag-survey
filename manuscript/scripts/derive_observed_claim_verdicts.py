#!/usr/bin/env python3
"""Derive all verdict levels from structured v2 coding fields."""

from __future__ import annotations

import csv
import sys
from pathlib import Path


REL_BAD = {"different", "mixed"}
VERDICT_ORDER = {"valid": 3, "partial": 2, "under-specified": 1, "invalid": 0}


def downgrade(verdict: str) -> str:
    return {"valid": "partial", "partial": "invalid"}.get(verdict, verdict)


def fim(row: dict[str, str]) -> str:
    if row["unit_status"] != "include":
        return "under-specified"
    rels = [row["c1_relation"], row["c3_relation"], row["c4_relation"]]
    if "unknown" in rels:
        return "under-specified"
    if row["c1_relation"] in REL_BAD or row["c4_relation"] in REL_BAD:
        return "invalid"
    if row["c3_relation"] in REL_BAD:
        return "partial"
    return "valid"


def five_coordinate(row: dict[str, str]) -> str:
    if row["unit_status"] != "include":
        return "under-specified"
    if row["factual_match"] == "no" or row["counterexample_status"] == "found":
        return "invalid"

    archetype = row["archetype"]
    strength = row["claim_strength"]
    if "unknown" in (row["c1_relation"], row["c2_relation"], row["c4_relation"]):
        return "under-specified"
    if (
        row["c5_relation"] == "unknown"
        and (archetype == "F_policy_utility" or row["utility_required"] == "yes")
    ):
        return "under-specified"

    verdict = "valid"
    if row["c1_relation"] in REL_BAD or row["c4_relation"] in REL_BAD:
        verdict = "partial" if archetype in {"C_cross_source_synthesis", "E_field_meta"} else "invalid"
    if row["c2_relation"] in REL_BAD:
        if archetype in {"C_cross_source_synthesis", "E_field_meta"}:
            if VERDICT_ORDER["partial"] < VERDICT_ORDER[verdict]:
                verdict = "partial"

    if row["c5_relation"] in REL_BAD:
        if row["utility_required"] == "yes" and row["utility_reported"] == "yes":
            pass
        elif strength in {"rank_or_superlative", "normative_policy"}:
            verdict = "invalid"
        elif VERDICT_ORDER["partial"] < VERDICT_ORDER[verdict]:
            verdict = "partial"

    if archetype == "C_cross_source_synthesis" and strength in {
        "rank_or_superlative",
        "causal",
    }:
        if VERDICT_ORDER["partial"] < VERDICT_ORDER[verdict]:
            verdict = "partial"
    elif archetype == "D_causal_mechanistic":
        if row["manipulation_or_ablation"] == "unknown":
            return "under-specified"
        if row["manipulation_or_ablation"] != "yes":
            if VERDICT_ORDER["partial"] < VERDICT_ORDER[verdict]:
                verdict = "partial"
    elif archetype == "E_field_meta":
        verdict = {
            "yes": "valid",
            "partial": "partial",
            "no": "invalid",
            "unknown": "under-specified",
            "not_applicable": "under-specified",
        }[row["field_audit_support"]]
    elif archetype == "F_policy_utility":
        if row["utility_required"] == "yes" and row["utility_reported"] != "yes":
            verdict = (
                "invalid"
                if strength in {"rank_or_superlative", "normative_policy"}
                else "partial"
            )

    return verdict


def full(row: dict[str, str], five_verdict: str) -> str:
    if five_verdict == "invalid":
        return "invalid"
    status = row["controls_status"]
    if status == "unknown" and row["controls_critical_missing"] == "yes":
        return "under-specified"
    if status == "unmatched":
        if five_verdict == "partial" and row.get("narrower_supported_claim", "").strip():
            return "partial"
        return downgrade(five_verdict)
    if status == "partial" and five_verdict == "valid":
        return "partial"
    return five_verdict


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: derive_verdicts_v2.py INPUT.csv OUTPUT.csv")
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["verdict_fim"] = fim(row)
        row["verdict_5coord_no_controls"] = five_coordinate(row)
        row["verdict_full"] = full(row, row["verdict_5coord_no_controls"])
    fields = list(rows[0])
    for field in ["verdict_fim", "verdict_5coord_no_controls", "verdict_full"]:
        if field not in fields:
            fields.append(field)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
