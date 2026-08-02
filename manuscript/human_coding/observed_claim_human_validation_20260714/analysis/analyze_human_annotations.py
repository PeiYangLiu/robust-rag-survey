#!/usr/bin/env python3
"""Analyze three independent human annotations without exposing model labels."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
from collections import Counter
from pathlib import Path


FIELDS = [
    "unit_status",
    "archetype",
    "claim_strength",
    "c1_relation",
    "c2_relation",
    "c3_relation",
    "c4_relation",
    "c5_relation",
    "utility_required",
    "controls_status",
    "verdict",
]
ENUMS = {
    "unit_status": {"include", "exclude_not_comparative"},
    "archetype": {
        "A_self_baseline",
        "B_shared_harness",
        "C_cross_source_synthesis",
        "D_causal_mechanistic",
        "E_field_meta",
        "F_policy_utility",
    },
    "claim_strength": {
        "descriptive",
        "directional",
        "rank_or_superlative",
        "causal",
        "field_absence_or_incommensurability",
        "normative_policy",
    },
    "c1_relation": {"aligned", "different", "mixed", "unknown", "not_applicable"},
    "c2_relation": {"aligned", "different", "mixed", "unknown", "not_applicable"},
    "c3_relation": {"aligned", "different", "mixed", "unknown", "not_applicable"},
    "c4_relation": {"aligned", "different", "mixed", "unknown", "not_applicable"},
    "c5_relation": {"aligned", "different", "mixed", "unknown", "not_applicable"},
    "utility_required": {"yes", "no"},
    "controls_status": {
        "aligned",
        "partial",
        "unmatched",
        "unknown",
        "not_applicable",
    },
    "verdict": {"valid", "partial", "invalid", "under-specified"},
}
KEY_FIELDS = [
    "verdict",
    "archetype",
    "c1_relation",
    "c2_relation",
    "c3_relation",
    "c4_relation",
    "c5_relation",
    "controls_status",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def metrics(left: list[str], right: list[str]) -> tuple[float, float, float]:
    pairs = [(a, b) for a, b in zip(left, right) if a and b]
    n = len(pairs)
    if not n:
        return float("nan"), float("nan"), float("nan")
    observed = sum(a == b for a, b in pairs) / n
    left_counts = Counter(a for a, _ in pairs)
    right_counts = Counter(b for _, b in pairs)
    labels = set(left_counts) | set(right_counts)
    expected = sum(
        (left_counts[label] / n) * (right_counts[label] / n) for label in labels
    )
    kappa = (
        1.0
        if math.isclose(observed, 1.0) and math.isclose(expected, 1.0)
        else (observed - expected) / (1 - expected)
        if not math.isclose(expected, 1.0)
        else float("nan")
    )
    categories = max(2, len(labels))
    pooled = {
        label: (left_counts[label] + right_counts[label]) / (2 * n)
        for label in labels
    }
    expected_ac1 = sum(p * (1 - p) for p in pooled.values()) / (categories - 1)
    ac1 = (
        1.0
        if math.isclose(observed, 1.0) and math.isclose(expected_ac1, 1.0)
        else (observed - expected_ac1) / (1 - expected_ac1)
        if not math.isclose(expected_ac1, 1.0)
        else float("nan")
    )
    return observed, kappa, ac1


def percentile(values: list[float], probability: float) -> float:
    values = sorted(value for value in values if not math.isnan(value))
    if not values:
        return float("nan")
    index = min(len(values) - 1, max(0, round((len(values) - 1) * probability)))
    return values[index]


def bootstrap_ci(
    left: list[str], right: list[str], iterations: int, seed: int
) -> dict[str, float]:
    rng = random.Random(seed)
    n = len(left)
    samples = {"raw": [], "kappa": [], "ac1": []}
    for _ in range(iterations):
        indices = [rng.randrange(n) for _ in range(n)]
        raw, kappa, ac1 = metrics(
            [left[index] for index in indices],
            [right[index] for index in indices],
        )
        samples["raw"].append(raw)
        samples["kappa"].append(kappa)
        samples["ac1"].append(ac1)
    return {
        f"{name}_ci_low": percentile(values, 0.025)
        for name, values in samples.items()
    } | {
        f"{name}_ci_high": percentile(values, 0.975)
        for name, values in samples.items()
    }


def majority(values: list[str]) -> str:
    label, count = Counter(values).most_common(1)[0]
    return label if count >= 2 else ""


def validate(
    files: list[Path], by_annotator: dict[str, dict[str, dict[str, str]]]
) -> list[str]:
    errors = []
    expected_ids = None
    for file in files:
        rows = read_csv(file)
        annotators = {row.get("annotator_id", "") for row in rows}
        if len(annotators) != 1 or "" in annotators:
            errors.append(f"{file}: must contain exactly one nonempty annotator_id")
            continue
        annotator = next(iter(annotators))
        ids = [row.get("annotation_id", "") for row in rows]
        if len(ids) != 80 or len(set(ids)) != 80 or "" in ids:
            errors.append(f"{file}: expected 80 unique annotation_id values")
        if expected_ids is None:
            expected_ids = set(ids)
        elif set(ids) != expected_ids:
            errors.append(f"{file}: annotation_id set differs")
        for row in rows:
            for field, allowed in ENUMS.items():
                if row.get(field, "") not in allowed:
                    errors.append(
                        f"{file}:{row.get('annotation_id')} invalid {field}={row.get(field)!r}"
                    )
            if not row.get("rationale", "").strip():
                errors.append(f"{file}:{row.get('annotation_id')} missing rationale")
            if not row.get("evidence_location_checked", "").strip():
                errors.append(
                    f"{file}:{row.get('annotation_id')} missing evidence location"
                )
            if row.get("verdict") == "partial" and not row.get(
                "narrower_supported_claim", ""
            ).strip():
                errors.append(
                    f"{file}:{row.get('annotation_id')} partial lacks narrower claim"
                )
            if row.get("verdict") == "under-specified" and not row.get(
                "missing_information", ""
            ).strip():
                errors.append(
                    f"{file}:{row.get('annotation_id')} under-specified lacks missing info"
                )
        by_annotator[annotator] = {row["annotation_id"]: row for row in rows}
    if len(by_annotator) != 3:
        errors.append(f"expected 3 annotators, found {len(by_annotator)}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument(
        "--hidden-key",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    files = sorted(args.responses.glob("*claims_completed.csv"))
    if not files:
        files = sorted(args.responses.glob("human_*_claims.csv"))
    by_annotator: dict[str, dict[str, dict[str, str]]] = {}
    errors = validate(files, by_annotator)
    if errors:
        raise SystemExit("\n".join(errors[:100]))

    hidden_key = args.hidden_key or args.responses / "sample_key.csv"
    hidden = {row["annotation_id"]: row for row in read_csv(hidden_key)}
    annotation_ids = sorted(next(iter(by_annotator.values())))
    annotators = sorted(by_annotator)
    agreement_rows = []
    distribution_rows = []
    for annotator in annotators:
        for field in FIELDS:
            for label, count in sorted(
                Counter(
                    by_annotator[annotator][annotation_id][field]
                    for annotation_id in annotation_ids
                ).items()
            ):
                distribution_rows.append(
                    {
                        "annotator_id": annotator,
                        "field": field,
                        "label": label,
                        "count": count,
                    }
                )
    for subset_name, subset_ids in [
        ("all_80", annotation_ids),
        (
            "balanced_core_16",
            [
                annotation_id
                for annotation_id in annotation_ids
                if hidden[annotation_id]["balanced_core_16"] == "1"
            ],
        ),
    ]:
        for field in FIELDS:
            for pair_index, (left_name, right_name) in enumerate(
                itertools.combinations(annotators, 2)
            ):
                left = [
                    by_annotator[left_name][annotation_id][field]
                    for annotation_id in subset_ids
                ]
                right = [
                    by_annotator[right_name][annotation_id][field]
                    for annotation_id in subset_ids
                ]
                raw, kappa, ac1 = metrics(left, right)
                ci = bootstrap_ci(
                    left,
                    right,
                    args.bootstrap,
                    20260714 + pair_index + len(field),
                )
                agreement_rows.append(
                    {
                        "subset": subset_name,
                        "field": field,
                        "annotator_a": left_name,
                        "annotator_b": right_name,
                        "n": len(subset_ids),
                        "raw_agreement": raw,
                        "cohen_kappa": kappa,
                        "gwet_ac1": ac1,
                        **ci,
                    }
                )

    consensus_rows = []
    worklist_rows = []
    for annotation_id in annotation_ids:
        row = {"annotation_id": annotation_id}
        disagree = False
        for field in KEY_FIELDS:
            labels = [
                by_annotator[annotator][annotation_id][field]
                for annotator in annotators
            ]
            row[f"{field}_labels"] = "|".join(labels)
            row[f"{field}_majority"] = majority(labels)
            row[f"{field}_unanimous"] = int(len(set(labels)) == 1)
            disagree |= len(set(labels)) != 1
        consensus_rows.append(row)
        if disagree:
            source = next(iter(by_annotator.values()))[annotation_id]
            work = {
                "annotation_id": annotation_id,
                "source_title": source["source_title"],
                "source_url": source["source_url"],
                "source_section": source["source_section"],
                "pdf_page": source["pdf_page"],
                "exact_quote": source["exact_quote"],
            }
            for annotator in annotators:
                response = by_annotator[annotator][annotation_id]
                work[f"{annotator}_verdict"] = response["verdict"]
                work[f"{annotator}_rationale"] = response["rationale"]
                work[f"{annotator}_evidence"] = response[
                    "evidence_location_checked"
                ]
            worklist_rows.append(work)

    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "pairwise_agreement.csv", agreement_rows)
    write_csv(args.output / "field_distributions.csv", distribution_rows)
    write_csv(args.output / "majority_consensus.csv", consensus_rows)
    write_csv(args.output / "adjudication_worklist.csv", worklist_rows)
    summary = {
        "annotators": annotators,
        "n_claims": len(annotation_ids),
        "balanced_core_n": sum(
            hidden[annotation_id]["balanced_core_16"] == "1"
            for annotation_id in annotation_ids
        ),
        "fully_unanimous_verdict": sum(
            row["verdict_unanimous"] == 1 for row in consensus_rows
        ),
        "needs_adjudication": len(worklist_rows),
        "bootstrap_iterations": args.bootstrap,
        "model_labels_used_in_pre_adjudication_metrics": False,
    }
    (args.output / "analysis_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
