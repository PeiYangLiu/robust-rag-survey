#!/usr/bin/env python3
"""Analyze independent expert-use validation responses.

Usage:
    python3 analyze_expert_validation.py responses.csv paper_pairs.csv

The script uses external_gold_verdict from paper_pairs.csv when present. If no
external gold verdicts are provided, it falls back to rulebook_expected_verdict
and reports the metric as rulebook agreement rather than external validity.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from statistics import mean

VERDICTS = ["valid", "partial", "invalid", "under-specified"]


def norm(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-")


def load_pairs(path: str) -> tuple[dict[str, dict[str, str]], str]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = {row["pair_id"]: row for row in csv.DictReader(f)}
    has_external = any(norm(row.get("external_gold_verdict", "")) for row in rows.values())
    reference_col = "external_gold_verdict" if has_external else "rulebook_expected_verdict"
    return rows, reference_col


def load_responses(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def safe_float(value: str) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except ValueError:
        return None


def fleiss_kappa(rows: list[dict[str, str]]) -> float | None:
    by_pair: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        verdict = norm(row.get("verdict", ""))
        if verdict in VERDICTS:
            by_pair[row["pair_id"]][verdict] += 1

    item_counters = [counts for counts in by_pair.values() if sum(counts.values()) > 1]
    if not item_counters:
        return None

    total_counts = Counter()
    p_observed_values = []
    total_ratings = 0
    for counts in item_counters:
        n_i = sum(counts.values())
        total_ratings += n_i
        total_counts.update(counts)
        p_i = sum(n_ij * (n_ij - 1) for n_ij in counts.values()) / (n_i * (n_i - 1))
        p_observed_values.append(p_i)

    p_bar = mean(p_observed_values)
    p_expected = sum((total_counts[label] / total_ratings) ** 2 for label in VERDICTS)
    if p_expected >= 1.0:
        return None
    return (p_bar - p_expected) / (1 - p_expected)


def summarize(rows: list[dict[str, str]], pairs: dict[str, dict[str, str]], reference_col: str) -> None:
    by_condition: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_condition[row.get("condition", "unknown").strip() or "unknown"].append(row)

    print(f"responses: {len(rows)}")
    print(f"participants: {len(set(row.get('participant_id', '') for row in rows))}")
    print(f"reference_verdict_column: {reference_col}")
    if reference_col != "external_gold_verdict":
        print("WARNING: using rulebook_expected_verdict; this is not external expert validity.")
    print()

    for condition, condition_rows in sorted(by_condition.items()):
        correct = 0
        judged = 0
        times: list[float] = []
        confidences: list[float] = []
        usefulness: list[float] = []
        rationale_quality: list[float] = []
        error_types = Counter()
        verdicts = Counter()

        for row in condition_rows:
            pair = pairs.get(row.get("pair_id", ""))
            verdict = norm(row.get("verdict", ""))
            if verdict:
                verdicts[verdict] += 1
            if pair:
                reference = norm(pair.get(reference_col, ""))
                if reference in VERDICTS and verdict in VERDICTS:
                    judged += 1
                    correct += int(verdict == reference)
            for target, col in [
                (times, "decision_time_seconds"),
                (confidences, "confidence_1_5"),
                (usefulness, "usefulness_1_5"),
                (rationale_quality, "rationale_quality_1_5"),
            ]:
                value = safe_float(row.get(col, ""))
                if value is not None:
                    target.append(value)
            error_type = row.get("error_type", "").strip()
            if error_type:
                error_types[error_type] += 1

        kappa = fleiss_kappa(condition_rows)
        print(f"condition: {condition}")
        print(f"  responses: {len(condition_rows)}")
        print(f"  participants: {len(set(row.get('participant_id', '') for row in condition_rows))}")
        print(f"  reference_accuracy: {correct / judged:.3f}" if judged else "  reference_accuracy: n/a")
        print(f"  fleiss_kappa: {kappa:.3f}" if kappa is not None else "  fleiss_kappa: n/a")
        print(f"  mean_decision_time_seconds: {mean(times):.1f}" if times else "  mean_decision_time_seconds: n/a")
        print(f"  mean_confidence_1_5: {mean(confidences):.2f}" if confidences else "  mean_confidence_1_5: n/a")
        print(f"  mean_usefulness_1_5: {mean(usefulness):.2f}" if usefulness else "  mean_usefulness_1_5: n/a")
        print(f"  mean_rationale_quality_1_5: {mean(rationale_quality):.2f}" if rationale_quality else "  mean_rationale_quality_1_5: n/a")
        print(f"  verdict_counts: {dict(verdicts)}")
        print(f"  error_type_counts: {dict(error_types)}")
        print()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    responses_path, pairs_path = sys.argv[1], sys.argv[2]
    pairs, reference_col = load_pairs(pairs_path)
    responses = load_responses(responses_path)
    summarize(responses, pairs, reference_col)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
