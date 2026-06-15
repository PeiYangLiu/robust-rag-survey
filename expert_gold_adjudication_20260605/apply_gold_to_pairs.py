#!/usr/bin/env python3
"""Apply independent gold adjudication labels to the pair reference file.

Usage:
    python3 apply_gold_to_pairs.py gold_panel_adjudication_template.csv \
        ../expert_validation/paper_pairs.csv paper_pairs_with_external_gold.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

VALID_VERDICTS = {"valid", "partial", "invalid", "under-specified"}


def norm(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-")


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    gold_path = Path(sys.argv[1])
    pairs_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])

    with gold_path.open(newline="", encoding="utf-8-sig") as f:
        gold_rows = list(csv.DictReader(f))
    gold = {}
    for row in gold_rows:
        pair_id = row.get("pair_id", "").strip()
        verdict = norm(row.get("final_gold_verdict") or row.get("gold_verdict", ""))
        if not pair_id or not verdict:
            continue
        if verdict not in VALID_VERDICTS:
            raise ValueError(f"Invalid verdict for {pair_id}: {verdict}")
        gold[pair_id] = row

    with pairs_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    for col in [
        "external_gold_verdict",
        "external_gold_rationale",
        "external_gold_breaking_coordinates",
        "external_gold_valid_comparison_requires",
        "external_gold_disagreement_summary",
    ]:
        if col not in fieldnames:
            fieldnames.append(col)

    missing = []
    for row in rows:
        pair_id = row["pair_id"]
        gold_row = gold.get(pair_id)
        if not gold_row:
            missing.append(pair_id)
            continue
        row["external_gold_verdict"] = norm(gold_row.get("final_gold_verdict") or gold_row.get("gold_verdict", ""))
        row["external_gold_rationale"] = gold_row.get("final_gold_rationale") or gold_row.get("gold_rationale", "")
        row["external_gold_breaking_coordinates"] = gold_row.get("final_breaking_coordinates") or gold_row.get("breaking_coordinates", "")
        row["external_gold_valid_comparison_requires"] = gold_row.get("what_valid_comparison_requires", "")
        row["external_gold_disagreement_summary"] = gold_row.get("disagreement_summary", "")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {out_path}")
    print(f"gold labels applied: {len(gold)}")
    if missing:
        print("missing gold labels for:", ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
