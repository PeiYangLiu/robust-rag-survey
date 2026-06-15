#!/usr/bin/env python3
"""Compute human-human IAA for round2 Evidence274 annotations."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
A_PATH = ROOT / "source_01_annotations.csv"
B_PATH = ROOT / "source_02_annotations.csv"

NOMINAL = [
    "full_text_checked",
    "screen_in_scope",
    "primary_failure_type",
    "method_family",
    "intervention_point",
    "evaluation_type",
    "evidence_strength",
    "is_core_candidate",
    "include_in_evidence_map",
]
ORDINAL = {
    "relevance_level": ["0", "1", "2", "3"],
    "confidence_1_to_5": ["1", "2", "3", "4", "5"],
}
MULTILABEL = ["secondary_failure_types", "reproducibility_evidence"]
CONDITIONAL = ["exclusion_reason"]
OPTIONAL_TEXT = ["attacker_capability", "retriever_generator_setup", "metrics_reported"]


def clean(v: str | None) -> str:
    return (v or "").strip()


def label_set(v: str | None) -> set[str]:
    raw = clean(v)
    if not raw:
        return set()
    return {x.strip() for x in raw.split(";") if x.strip()}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def nominal_stats(pairs: list[tuple[str, str]]) -> dict[str, object]:
    pairs = [(a, b) for a, b in pairs if a or b]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "agreement": None, "kappa": None}
    agree = sum(a == b for a, b in pairs)
    po = agree / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum((ca[x] / n) * (cb[x] / n) for x in set(ca) | set(cb))
    kappa = None if math.isclose(pe, 1.0) else (po - pe) / (1 - pe)
    return {"n": n, "agreement": po, "kappa": kappa}


def weighted_kappa(pairs: list[tuple[str, str]], labels: list[str]) -> dict[str, object]:
    pairs = [(a, b) for a, b in pairs if a or b]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "linear_weighted_kappa": None, "mean_abs_disagreement": None}
    idx = {label: i for i, label in enumerate(labels)}
    max_dist = max(1, len(labels) - 1)
    ca, cb = Counter(), Counter()
    obs = 0.0
    abs_diffs = []
    for a, b in pairs:
        ia, ib = idx.get(a), idx.get(b)
        dist = max_dist if ia is None or ib is None else abs(ia - ib)
        obs += dist / max_dist
        abs_diffs.append(dist)
        ca[a] += 1
        cb[b] += 1
    obs /= n
    exp = 0.0
    for a, na in ca.items():
        for b, nb in cb.items():
            ia, ib = idx.get(a), idx.get(b)
            dist = max_dist if ia is None or ib is None else abs(ia - ib)
            exp += (na / n) * (nb / n) * (dist / max_dist)
    return {
        "n": n,
        "linear_weighted_kappa": None if math.isclose(exp, 0.0) else 1 - obs / exp,
        "mean_abs_disagreement": sum(abs_diffs) / n,
    }


def multilabel_stats(pairs: list[tuple[set[str], set[str]]]) -> dict[str, object]:
    n = len(pairs)
    exact = sum(a == b for a, b in pairs)
    jaccards = []
    for a, b in pairs:
        union = a | b
        jaccards.append(1.0 if not union else len(a & b) / len(union))
    return {"n": n, "exact_match": exact / n, "mean_jaccard": sum(jaccards) / n}


def disagreement_count(a_rows: list[dict[str, str]], b_rows: list[dict[str, str]], field: str) -> int:
    out = ROOT / f"disagreements_{field}.csv"
    count = 0
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["paper_id", "title", "field", "source_01_label", "source_02_label", "url"],
        )
        writer.writeheader()
        for a, b in zip(a_rows, b_rows):
            va, vb = clean(a.get(field)), clean(b.get(field))
            different = label_set(va) != label_set(vb) if field in MULTILABEL else va != vb
            if different:
                count += 1
                writer.writerow(
                    {
                        "paper_id": a.get("paper_id", ""),
                        "title": a.get("title", ""),
                        "field": field,
                        "source_01_label": va,
                        "source_02_label": vb,
                        "url": a.get("url", ""),
                    }
                )
    return count


def write_adjudication_template(a_rows: list[dict[str, str]], b_rows: list[dict[str, str]]) -> int:
    fields = NOMINAL + list(ORDINAL) + MULTILABEL + CONDITIONAL
    out = ROOT / "adjudication_template_evidence274_round2.csv"
    count = 0
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "paper_id",
                "title",
                "field",
                "source_01_label",
                "source_02_label",
                "human_final_label",
                "human_adjudication_reason",
                "url",
            ],
        )
        writer.writeheader()
        for a, b in zip(a_rows, b_rows):
            for field in fields:
                va, vb = clean(a.get(field)), clean(b.get(field))
                different = label_set(va) != label_set(vb) if field in MULTILABEL else va != vb
                if different:
                    count += 1
                    writer.writerow(
                        {
                            "paper_id": a.get("paper_id", ""),
                            "title": a.get("title", ""),
                            "field": field,
                            "source_01_label": va,
                            "source_02_label": vb,
                            "human_final_label": "",
                            "human_adjudication_reason": "",
                            "url": a.get("url", ""),
                        }
                    )
    return count


def confusion(a_rows: list[dict[str, str]], b_rows: list[dict[str, str]], field: str) -> dict[str, dict[str, int]]:
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for a, b in zip(a_rows, b_rows):
        matrix[clean(a.get(field))][clean(b.get(field))] += 1
    return {k: dict(v) for k, v in sorted(matrix.items())}


def main() -> None:
    a_rows, b_rows = read_rows(A_PATH), read_rows(B_PATH)
    if len(a_rows) != len(b_rows):
        raise SystemExit(f"Row mismatch: {len(a_rows)} vs {len(b_rows)}")
    for i, (a, b) in enumerate(zip(a_rows, b_rows), start=1):
        if a.get("paper_id") != b.get("paper_id"):
            raise SystemExit(f"paper_id mismatch at row {i}: {a.get('paper_id')} vs {b.get('paper_id')}")

    summary: dict[str, object] = {
        "n_items": len(a_rows),
        "source_files": [A_PATH.name, B_PATH.name],
        "nominal": {},
        "ordinal": {},
        "multilabel": {},
        "conditional": {},
        "disagreement_counts": {},
        "confusion_matrices": {},
        "optional_field_fill_rates": {},
    }

    for field in NOMINAL:
        pairs = [(clean(a.get(field)), clean(b.get(field))) for a, b in zip(a_rows, b_rows)]
        summary["nominal"][field] = nominal_stats(pairs)
        summary["disagreement_counts"][field] = disagreement_count(a_rows, b_rows, field)
        if field in {"primary_failure_type", "method_family", "intervention_point", "evaluation_type", "evidence_strength"}:
            summary["confusion_matrices"][field] = confusion(a_rows, b_rows, field)

    for field, labels in ORDINAL.items():
        pairs = [(clean(a.get(field)), clean(b.get(field))) for a, b in zip(a_rows, b_rows)]
        summary["ordinal"][field] = weighted_kappa(pairs, labels)
        summary["disagreement_counts"][field] = disagreement_count(a_rows, b_rows, field)

    for field in MULTILABEL:
        pairs = [(label_set(a.get(field)), label_set(b.get(field))) for a, b in zip(a_rows, b_rows)]
        summary["multilabel"][field] = multilabel_stats(pairs)
        summary["disagreement_counts"][field] = disagreement_count(a_rows, b_rows, field)

    excluded_pairs = [
        (clean(a.get("exclusion_reason")), clean(b.get("exclusion_reason")))
        for a, b in zip(a_rows, b_rows)
        if clean(a.get("screen_in_scope")) == "0" or clean(b.get("screen_in_scope")) == "0"
    ]
    summary["conditional"]["exclusion_reason"] = nominal_stats(excluded_pairs)
    summary["disagreement_counts"]["exclusion_reason"] = disagreement_count(a_rows, b_rows, "exclusion_reason")

    for field in OPTIONAL_TEXT:
        summary["optional_field_fill_rates"][field] = {
            "source_01": sum(1 for r in a_rows if clean(r.get(field))) / len(a_rows),
            "source_02": sum(1 for r in b_rows if clean(r.get(field))) / len(b_rows),
        }

    summary["adjudication_template_rows"] = write_adjudication_template(a_rows, b_rows)

    with (ROOT / "human_human_iaa_summary_round2.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    report = []
    for field, stats in summary["nominal"].items():
        report.append({"field": field, "n": stats["n"], "agreement": stats["agreement"], "kappa_or_score": stats["kappa"], "metric": "cohen_kappa"})
    for field, stats in summary["ordinal"].items():
        report.append({"field": field, "n": stats["n"], "agreement": "", "kappa_or_score": stats["linear_weighted_kappa"], "metric": "linear_weighted_kappa"})
    for field, stats in summary["multilabel"].items():
        report.append({"field": field, "n": stats["n"], "agreement": stats["exact_match"], "kappa_or_score": stats["mean_jaccard"], "metric": "exact_match / mean_jaccard"})
    with (ROOT / "human_human_iaa_report_round2.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["field", "n", "agreement", "kappa_or_score", "metric"])
        writer.writeheader()
        writer.writerows(report)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
