#!/usr/bin/env python3
"""Apply final human adjudication labels to round2 Evidence274 annotations."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANUSCRIPT = ROOT.parents[1]
SUPP = MANUSCRIPT / "supplement"
SOURCE = ROOT / "source_01_annotations.csv"
FINAL_LOG = ROOT.parent / "blind_round2_adjudication_review" / "annotation_set_A.csv"

OPTIONAL_BLANK = {"secondary_failure_types", "exclusion_reason", "reproducibility_evidence"}

METHOD_MAP = {
    "attack": "attack",
    "defense_mitigation": "defense/mitigation",
    "benchmark_evaluation": "benchmark/evaluation",
    "analysis": "analysis",
    "control_calibration": "control/calibration",
    "conflict_modeling": "conflict modeling",
    "survey_background": "survey background",
    "application": "application",
    "method": "method",
    "other": "other",
}
INTERVENTION_MAP = {
    "corpus_kb": "corpus/KB",
    "retriever": "retriever/context",
    "context_assembly": "context assembly",
    "generator": "generator",
    "system_control": "system control",
    "evaluation": "evaluation",
    "mixed": "mixed",
    "not_applicable": "not applicable",
}


def clean(value: str | None) -> str:
    return (value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_categories(primary: str, secondary: str) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for raw in [primary, secondary]:
        for item in raw.split(";"):
            item = item.strip()
            if item and item not in seen:
                out.append(item)
                seen.add(item)
    return ";".join(out)


def main() -> None:
    rows = read_csv(SOURCE)
    final_rows = read_csv(FINAL_LOG)
    by_id = {row["paper_id"]: row for row in rows}
    decisions_applied = 0
    blank_by_field = Counter()
    missing_ids: list[str] = []

    for decision in final_rows:
        paper_id = clean(decision.get("paper_id"))
        field = clean(decision.get("field"))
        final = clean(decision.get("final_label"))
        if paper_id not in by_id:
            missing_ids.append(paper_id)
            continue
        if not final and field not in OPTIONAL_BLANK:
            raise SystemExit(f"Blank final label for non-optional field: {paper_id} {field}")
        if not final:
            blank_by_field[field] += 1
        by_id[paper_id][field] = final
        decisions_applied += 1

    if missing_ids:
        raise SystemExit(f"Missing paper IDs in source annotations: {missing_ids[:10]}")

    for row in rows:
        row["adjudication_status"] = "human_adjudicated_final_round2"

    full_fields = list(rows[0].keys())
    if "adjudication_status" not in full_fields:
        full_fields.append("adjudication_status")
    write_csv(ROOT / "adjudicated_evidence274_round2_final_full.csv", rows, full_fields)

    evidence_rows = []
    for row in rows:
        if clean(row.get("include_in_evidence_map")) != "1":
            continue
        cats = merge_categories(clean(row.get("primary_failure_type")), clean(row.get("secondary_failure_types")))
        evidence_rows.append(
            {
                "cite_key": clean(row.get("paper_id")),
                "title": clean(row.get("title")),
                "authors": clean(row.get("authors")),
                "year": clean(row.get("year")),
                "source_or_venue": clean(row.get("source_or_venue")),
                "url": clean(row.get("url")),
                "taxonomy_categories": cats,
                "failure_or_risk_type": clean(row.get("primary_failure_type")),
                "method_family": METHOD_MAP.get(clean(row.get("method_family")), clean(row.get("method_family"))),
                "intervention_point": INTERVENTION_MAP.get(clean(row.get("intervention_point")), clean(row.get("intervention_point"))),
                "benchmark_or_task": clean(row.get("retriever_generator_setup")),
                "metrics_reported_or_relevant": clean(row.get("metrics_reported")),
                "core100": "True" if clean(row.get("is_core_candidate")) == "1" else "False",
                "actual_contribution": clean(row.get("notes")),
                "limitation_or_note": "Final human-adjudicated round2 evidence-map label.",
            }
        )

    evidence_fields = list(evidence_rows[0].keys())
    write_csv(ROOT / "evidence_map_round2_adjudicated.csv", evidence_rows, evidence_fields)
    write_csv(SUPP / "evidence_map_adjudicated.csv", evidence_rows, evidence_fields)

    summary = {
        "source_rows": len(rows),
        "final_evidence_map_rows": len(evidence_rows),
        "decisions_applied": decisions_applied,
        "blank_final_labels_by_field": dict(blank_by_field),
        "excluded_by_final_include_flag": len(rows) - len(evidence_rows),
        "output_files": [
            str(ROOT / "adjudicated_evidence274_round2_final_full.csv"),
            str(ROOT / "evidence_map_round2_adjudicated.csv"),
            str(SUPP / "evidence_map_adjudicated.csv"),
        ],
    }
    with (ROOT / "round2_final_adjudication_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
