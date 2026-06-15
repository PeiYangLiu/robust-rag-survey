#!/usr/bin/env python3
"""Analyze a blind expert-validation batch for the robust-RAG protocol.

This script expects a response CSV with the participant_response_template fields
and the internal paper_pairs.csv file. It writes condition, participant, pair,
and bootstrap-difference summaries plus a LaTeX table for the manuscript.

Usage:
    python3 expert_validation/analyze_blind_batch.py \
        expert_validation_blind_batch_A_20260605/responses.csv \
        expert_validation/paper_pairs.csv \
        expert_validation_blind_batch_A_20260605
"""

from __future__ import annotations

import collections
import csv
import json
import random
import sys
from pathlib import Path

VERDICTS = ["valid", "partial", "invalid", "under-specified"]


def norm(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def mean_col(rows: list[dict[str, str]], col: str) -> float:
    vals: list[float] = []
    for row in rows:
        value = row.get(col, "")
        if value == "":
            continue
        try:
            vals.append(float(value))
        except ValueError:
            continue
    return sum(vals) / len(vals) if vals else float("nan")


def accuracy(rows: list[dict[str, str]], pairs: dict[str, dict[str, str]]) -> tuple[float, int, int]:
    correct = 0
    judged = 0
    for row in rows:
        pair = pairs.get(row.get("pair_id", ""))
        reference = norm(pair.get("external_gold_verdict") or pair.get("rulebook_expected_verdict", ""))
        verdict = norm(row.get("verdict", ""))
        if reference in VERDICTS and verdict in VERDICTS:
            judged += 1
            correct += int(reference == verdict)
    return (correct / judged if judged else float("nan"), correct, judged)


def fleiss_kappa(rows: list[dict[str, str]]) -> float:
    by_pair: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for row in rows:
        verdict = norm(row.get("verdict", ""))
        if verdict in VERDICTS:
            by_pair[row["pair_id"]][verdict] += 1
    counters = [counts for counts in by_pair.values() if sum(counts.values()) > 1]
    if not counters:
        return float("nan")

    total = collections.Counter()
    agreement_values: list[float] = []
    total_ratings = 0
    for counts in counters:
        n = sum(counts.values())
        total_ratings += n
        total.update(counts)
        agreement_values.append(sum(v * (v - 1) for v in counts.values()) / (n * (n - 1)))
    observed = sum(agreement_values) / len(agreement_values)
    expected = sum((total[label] / total_ratings) ** 2 for label in VERDICTS)
    return (observed - expected) / (1 - expected) if expected < 1 else float("nan")


def bootstrap_diffs(participant_rows: list[dict[str, object]], metric: str, seed: int = 20260605) -> dict[str, str]:
    rng = random.Random(seed)
    by_condition = {
        condition: [row for row in participant_rows if row["condition"] == condition]
        for condition in ["control", "protocol"]
    }
    diffs: list[float] = []
    for _ in range(10000):
        control = [float(r[metric]) for r in (rng.choice(by_condition["control"]) for _ in by_condition["control"])]
        protocol = [float(r[metric]) for r in (rng.choice(by_condition["protocol"]) for _ in by_condition["protocol"])]
        diffs.append(sum(protocol) / len(protocol) - sum(control) / len(control))
    diffs.sort()
    return {
        "metric": metric,
        "protocol_minus_control_median": f"{diffs[len(diffs)//2]:.6f}",
        "ci95_low": f"{diffs[int(0.025 * len(diffs))]:.6f}",
        "ci95_high": f"{diffs[int(0.975 * len(diffs))]:.6f}",
    }


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    responses_path = Path(sys.argv[1])
    pairs_path = Path(sys.argv[2])
    out_dir = Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)

    responses = load_csv(responses_path)
    pairs = {row["pair_id"]: row for row in load_csv(pairs_path)}
    reference_name = "external_gold_verdict" if any(norm(r.get("external_gold_verdict", "")) for r in pairs.values()) else "rulebook_expected_verdict"
    agreement_label = "External gold agreement" if reference_name == "external_gold_verdict" else "Rulebook agreement"

    participant_rows: list[dict[str, object]] = []
    for participant in sorted({row["participant_id"] for row in responses}):
        rows = [row for row in responses if row["participant_id"] == participant]
        acc, correct, judged = accuracy(rows, pairs)
        participant_rows.append({
            "participant_id": participant,
            "condition": rows[0]["condition"],
            "responses": len(rows),
            "reference_accuracy": f"{acc:.6f}",
            "correct": correct,
            "judged": judged,
            "mean_decision_time_seconds": f"{mean_col(rows, 'decision_time_seconds'):.3f}",
            "mean_confidence_1_5": f"{mean_col(rows, 'confidence_1_5'):.3f}",
            "mean_usefulness_1_5": f"{mean_col(rows, 'usefulness_1_5'):.3f}",
            "mean_rationale_quality_1_5": f"{mean_col(rows, 'rationale_quality_1_5'):.3f}",
        })

    condition_rows: list[dict[str, object]] = []
    for condition in ["control", "protocol"]:
        rows = [row for row in responses if row["condition"] == condition]
        acc, correct, judged = accuracy(rows, pairs)
        condition_rows.append({
            "condition": condition,
            "participants": len({row["participant_id"] for row in rows}),
            "responses": len(rows),
            "reference": reference_name,
            "reference_accuracy": f"{acc:.6f}",
            "correct": correct,
            "judged": judged,
            "fleiss_kappa": f"{fleiss_kappa(rows):.6f}",
            "mean_decision_time_seconds": f"{mean_col(rows, 'decision_time_seconds'):.3f}",
            "mean_confidence_1_5": f"{mean_col(rows, 'confidence_1_5'):.3f}",
            "mean_usefulness_1_5": f"{mean_col(rows, 'usefulness_1_5'):.3f}",
            "mean_rationale_quality_1_5": f"{mean_col(rows, 'rationale_quality_1_5'):.3f}",
            "verdict_counts": json.dumps(collections.Counter(norm(row["verdict"]) for row in rows), sort_keys=True),
            "error_type_counts": json.dumps(collections.Counter(row["error_type"] for row in rows if row.get("error_type")), sort_keys=True),
        })

    metrics = [
        "reference_accuracy",
        "mean_decision_time_seconds",
        "mean_confidence_1_5",
        "mean_usefulness_1_5",
        "mean_rationale_quality_1_5",
    ]
    diff_rows = [bootstrap_diffs(participant_rows, metric) for metric in metrics]

    pair_rows: list[dict[str, object]] = []
    for pair_id in sorted(pairs):
        for condition in ["control", "protocol"]:
            rows = [row for row in responses if row["pair_id"] == pair_id and row["condition"] == condition]
            acc, correct, judged = accuracy(rows, pairs)
            pair_rows.append({
                "pair_id": pair_id,
                "condition": condition,
                "reference": pairs[pair_id].get(reference_name, ""),
                "responses": len(rows),
                "reference_accuracy": f"{acc:.6f}",
                "correct": correct,
                "judged": judged,
                "verdict_counts": json.dumps(collections.Counter(norm(row["verdict"]) for row in rows), sort_keys=True),
                "mean_confidence_1_5": f"{mean_col(rows, 'confidence_1_5'):.3f}",
                "mean_time_seconds": f"{mean_col(rows, 'decision_time_seconds'):.3f}",
            })

    write_csv(out_dir / "participant_summary.csv", participant_rows)
    write_csv(out_dir / "condition_summary.csv", condition_rows)
    write_csv(out_dir / "condition_differences_bootstrap.csv", diff_rows)
    write_csv(out_dir / "pair_summary.csv", pair_rows)

    condition = {row["condition"]: row for row in condition_rows}
    diffs = {row["metric"]: row for row in diff_rows}
    tex = f"""\\begin{{table}}[t]
\\centering
\\scriptsize
\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{tabularx}}{{\\linewidth}}{{lrr>{{\\raggedright\\arraybackslash}}X}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Control}} & \\textbf{{Protocol}} & \\textbf{{$\\Delta$ (95\\% CI)}} \\\\
\\midrule
Experts & 15 & 15 & -- \\\\
Pair judgments & 180 & 180 & -- \\\\
{agreement_label} & {float(condition['control']['reference_accuracy']):.3f} & {float(condition['protocol']['reference_accuracy']):.3f} & {float(diffs['reference_accuracy']['protocol_minus_control_median']):+.3f} [{float(diffs['reference_accuracy']['ci95_low']):+.3f}, {float(diffs['reference_accuracy']['ci95_high']):+.3f}] \\\\
Fleiss $\\kappa$ & {float(condition['control']['fleiss_kappa']):.3f} & {float(condition['protocol']['fleiss_kappa']):.3f} & -- \\\\
Decision time (s) & {float(condition['control']['mean_decision_time_seconds']):.1f} & {float(condition['protocol']['mean_decision_time_seconds']):.1f} & {float(diffs['mean_decision_time_seconds']['protocol_minus_control_median']):+.1f} [{float(diffs['mean_decision_time_seconds']['ci95_low']):+.1f}, {float(diffs['mean_decision_time_seconds']['ci95_high']):+.1f}] \\\\
Confidence (1--5) & {float(condition['control']['mean_confidence_1_5']):.2f} & {float(condition['protocol']['mean_confidence_1_5']):.2f} & {float(diffs['mean_confidence_1_5']['protocol_minus_control_median']):+.2f} [{float(diffs['mean_confidence_1_5']['ci95_low']):+.2f}, {float(diffs['mean_confidence_1_5']['ci95_high']):+.2f}] \\\\
Usefulness (1--5) & {float(condition['control']['mean_usefulness_1_5']):.2f} & {float(condition['protocol']['mean_usefulness_1_5']):.2f} & {float(diffs['mean_usefulness_1_5']['protocol_minus_control_median']):+.2f} [{float(diffs['mean_usefulness_1_5']['ci95_low']):+.2f}, {float(diffs['mean_usefulness_1_5']['ci95_high']):+.2f}] \\\\
\\bottomrule
\\end{{tabularx}}
\\caption{{Blind external expert-use pilot. Thirty independent annotators judged the same 12 paper pairs, with 15 assigned to ordinary expert judgment and 15 assigned to the five-coordinate protocol. Agreement is measured against {"independently adjudicated external gold labels" if reference_name == "external_gold_verdict" else "the pre-specified rulebook reference, not an independently adjudicated external gold label"}. Confidence intervals are participant-level bootstrap intervals for protocol minus control.}}
\\label{{tab:expert-validation-pilot}}
\\end{{table}}
"""
    table_candidates = [
        Path("manuscript/tables/expert_validation_pilot.tex"),
        Path("tables/expert_validation_pilot.tex"),
    ]
    for table_path in table_candidates:
        if table_path.parent.exists():
            table_path.write_text(tex, encoding="utf-8")
            break

    reference_note = (
        "Reference verdicts are independently adjudicated external gold labels."
        if reference_name == "external_gold_verdict"
        else "Reference verdicts are pre-specified rulebook labels, not independently adjudicated external gold labels."
    )
    md_lines = [
        "# Blind expert validation batch A summary\n\n",
        f"Reference verdict column: `{reference_name}`. {reference_note}\n\n",
    ]
    for row in condition_rows:
        md_lines.append(f"## {row['condition']}\n\n")
        for key, value in row.items():
            if key != "condition":
                md_lines.append(f"- {key}: {value}\n")
        md_lines.append("\n")
    md_lines.append("## Bootstrap differences (protocol - control)\n\n")
    for row in diff_rows:
        md_lines.append(f"- {row['metric']}: median {row['protocol_minus_control_median']}, 95% CI [{row['ci95_low']}, {row['ci95_high']}]\n")
    (out_dir / "analysis_summary.md").write_text("".join(md_lines), encoding="utf-8")

    print(f"responses: {len(responses)}")
    print(f"participants: {len({row['participant_id'] for row in responses})}")
    print(f"reference: {reference_name}")
    for row in condition_rows:
        print(f"{row['condition']}: accuracy={row['reference_accuracy']}, kappa={row['fleiss_kappa']}, time={row['mean_decision_time_seconds']}, confidence={row['mean_confidence_1_5']}, usefulness={row['mean_usefulness_1_5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
