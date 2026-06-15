#!/usr/bin/env python3
"""Apply human adjudication decisions to Evidence274 labels."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANUSCRIPT = ROOT.parents[1]
SUPP = MANUSCRIPT / "supplement"

DRAFT = ROOT / "adjudicated_evidence274_draft.csv"
FINAL_LOG = ROOT / "adjudication_log_evidence274_final.csv"
FINAL_FULL = ROOT / "adjudicated_evidence274_final.csv"
SUPP_FINAL = SUPP / "evidence_map_adjudicated.csv"

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
    out = []
    seen = set()
    for raw in [primary, secondary]:
        for item in raw.split(";"):
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                out.append(item)
    return ";".join(out)


def main() -> None:
    rows = read_csv(DRAFT)
    final_log = read_csv(FINAL_LOG)
    by_id = {row["paper_id"]: row for row in rows}
    applied = 0
    missing_ids = []
    blank_finals = Counter()

    for decision in final_log:
        paper_id = clean(decision.get("paper_id"))
        field = clean(decision.get("field"))
        final = clean(decision.get("human_final_label"))
        if paper_id not in by_id:
            missing_ids.append(paper_id)
            continue
        if not final:
            blank_finals[field] += 1
        by_id[paper_id][field] = final
        applied += 1

    if missing_ids:
        raise SystemExit(f"Missing paper_ids in draft: {missing_ids[:10]}")

    for row in rows:
        row["adjudication_status"] = "human_adjudicated_final"

    write_csv(DRAFT.with_name("adjudicated_evidence274_final.csv"), rows, list(rows[0].keys()))

    supp_rows = []
    for row in rows:
        cats = merge_categories(clean(row.get("primary_failure_type")), clean(row.get("secondary_failure_types")))
        method = METHOD_MAP.get(clean(row.get("method_family")), clean(row.get("method_family")))
        intervention = INTERVENTION_MAP.get(clean(row.get("intervention_point")), clean(row.get("intervention_point")))
        supp_rows.append(
            {
                "cite_key": clean(row.get("paper_id")),
                "title": clean(row.get("title")),
                "authors": clean(row.get("authors")),
                "year": clean(row.get("year")),
                "source_or_venue": clean(row.get("source_or_venue")),
                "url": clean(row.get("url")),
                "taxonomy_categories": cats,
                "failure_or_risk_type": clean(row.get("primary_failure_type")),
                "method_family": method,
                "intervention_point": intervention,
                "benchmark_or_task": clean(row.get("retriever_generator_setup")),
                "metrics_reported_or_relevant": clean(row.get("metrics_reported")),
                "core100": "True" if clean(row.get("is_core_candidate")) == "1" else "False",
                "actual_contribution": clean(row.get("notes")),
                "limitation_or_note": "Human-adjudicated final label from Evidence274 adjudication round.",
            }
        )
    write_csv(SUPP_FINAL, supp_rows, list(supp_rows[0].keys()))

    summary = {
        "rows": len(rows),
        "adjudication_decisions_applied": applied,
        "blank_final_labels_by_field": dict(blank_finals),
        "output_files": [str(FINAL_FULL), str(SUPP_FINAL)],
    }
    with (ROOT / "final_adjudication_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
