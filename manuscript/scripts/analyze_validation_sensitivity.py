#!/usr/bin/env python3
"""Reanalyze the 60-pair comparability study after the packet-integrity audit."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable


VERDICTS = ("valid", "partial", "invalid", "underspecified")
CONDITIONS = ("control", "protocol")
PACKET_OMISSIONS = {
    "EV60-008": "Gold rationale says Paper A was represented only by its title.",
    "EV60-025": "Gold rationale says both papers lacked text snippets.",
    "EV60-026": "Gold rationale says Paper A lacked an abstract or full-text excerpt.",
    "EV60-054": "Gold rationale says Paper A was represented only by its title.",
}
PLAIN_LANGUAGE_MAP = {
    "safe": "valid",
    "partly": "partial",
    "misleading": "invalid",
    "cant_tell": "underspecified",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def portable_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def validate_inputs(
    responses: list[dict[str, str]], gold_rows: list[dict[str, str]]
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    gold = {row["pair_id"]: row for row in gold_rows}
    if len(gold) != len(gold_rows):
        raise ValueError("Gold file contains duplicate pair IDs.")

    participants: dict[str, set[str]] = {condition: set() for condition in CONDITIONS}
    seen: set[tuple[str, str, str]] = set()
    for row in responses:
        condition = row["condition"]
        if condition not in participants:
            raise ValueError(f"Unexpected condition: {condition}")
        if row["pair_id"] not in gold:
            raise ValueError(f"Response has no gold row: {row['pair_id']}")
        if row["verdict"] not in VERDICTS:
            raise ValueError(f"Unexpected verdict: {row['verdict']}")
        key = (condition, row["participant_id"], row["pair_id"])
        if key in seen:
            raise ValueError(f"Duplicate response: {key}")
        seen.add(key)
        participants[condition].add(row["participant_id"])

    pair_ids = set(gold)
    for condition, condition_participants in participants.items():
        expected = {
            (condition, participant, pair_id)
            for participant in condition_participants
            for pair_id in pair_ids
        }
        missing = expected - seen
        if missing:
            raise ValueError(
                f"{condition} response grid is incomplete; first missing cell: "
                f"{sorted(missing)[0]}"
            )

    return gold, {
        condition: sorted(condition_participants)
        for condition, condition_participants in participants.items()
    }


def accuracy(predictions: Iterable[str], targets: Iterable[str]) -> float:
    pairs = list(zip(predictions, targets))
    return sum(prediction == target for prediction, target in pairs) / len(pairs)


def recall(predictions: list[str], targets: list[str], label: str) -> float:
    selected = [
        prediction == target
        for prediction, target in zip(predictions, targets)
        if target == label
    ]
    if not selected:
        return math.nan
    return sum(selected) / len(selected)


def balanced_accuracy(
    predictions: list[str], targets: list[str], labels: tuple[str, ...]
) -> float:
    values = [recall(predictions, targets, label) for label in labels]
    if any(math.isnan(value) for value in values):
        return math.nan
    return sum(values) / len(values)


def cohen_kappa(predictions: list[str], targets: list[str]) -> float:
    observed = accuracy(predictions, targets)
    pred_counts = Counter(predictions)
    target_counts = Counter(targets)
    n = len(predictions)
    expected = sum(
        pred_counts[label] / n * target_counts[label] / n for label in VERDICTS
    )
    if math.isclose(expected, 1.0):
        return math.nan
    return (observed - expected) / (1.0 - expected)


def metric_value(
    metric: str,
    predictions: list[str],
    targets: list[str],
    labels: tuple[str, ...],
) -> float:
    if metric == "raw_accuracy":
        return accuracy(predictions, targets)
    if metric == "cohen_kappa":
        return cohen_kappa(predictions, targets)
    if metric == "macro_recall_observed_classes":
        return balanced_accuracy(predictions, targets, labels)
    if metric.startswith("recall_"):
        return recall(predictions, targets, metric.removeprefix("recall_"))
    raise ValueError(f"Unknown metric: {metric}")


def percentile(values: list[float], quantile: float) -> float:
    clean = sorted(value for value in values if not math.isnan(value))
    if not clean:
        return math.nan
    index = (len(clean) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return clean[lower]
    fraction = index - lower
    return clean[lower] * (1.0 - fraction) + clean[upper] * fraction


def crossed_bootstrap(
    *,
    pair_ids: list[str],
    participants: dict[str, list[str]],
    response_index: dict[tuple[str, str, str], str],
    gold: dict[str, dict[str, str]],
    labels: tuple[str, ...],
    metric: str,
    repetitions: int,
    rng: random.Random,
) -> tuple[list[float], list[float], list[float]]:
    values = {condition: [] for condition in CONDITIONS}
    differences: list[float] = []
    for _ in range(repetitions):
        sampled_pairs = rng.choices(pair_ids, k=len(pair_ids))
        sampled_participants = {
            condition: rng.choices(ids, k=len(ids))
            for condition, ids in participants.items()
        }
        iteration: dict[str, float] = {}
        for condition in CONDITIONS:
            predictions: list[str] = []
            targets: list[str] = []
            for pair_id in sampled_pairs:
                target = gold[pair_id]["gold_verdict"]
                for participant_id in sampled_participants[condition]:
                    predictions.append(
                        response_index[(condition, participant_id, pair_id)]
                    )
                    targets.append(target)
            iteration[condition] = metric_value(
                metric, predictions, targets, labels
            )
            values[condition].append(iteration[condition])
        differences.append(iteration["protocol"] - iteration["control"])
    return values["control"], values["protocol"], differences


def point_estimate(
    *,
    pair_ids: list[str],
    participants: dict[str, list[str]],
    response_index: dict[tuple[str, str, str], str],
    gold: dict[str, dict[str, str]],
    labels: tuple[str, ...],
    metric: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for condition in CONDITIONS:
        predictions: list[str] = []
        targets: list[str] = []
        for pair_id in pair_ids:
            target = gold[pair_id]["gold_verdict"]
            for participant_id in participants[condition]:
                predictions.append(response_index[(condition, participant_id, pair_id)])
                targets.append(target)
        result[condition] = metric_value(metric, predictions, targets, labels)
    result["difference"] = result["protocol"] - result["control"]
    return result


def format_result_rows(
    *,
    scope: str,
    pair_ids: list[str],
    labels: tuple[str, ...],
    metrics: tuple[str, ...],
    participants: dict[str, list[str]],
    response_index: dict[tuple[str, str, str], str],
    gold: dict[str, dict[str, str]],
    repetitions: int,
    seed: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metric_index, metric in enumerate(metrics):
        estimate = point_estimate(
            pair_ids=pair_ids,
            participants=participants,
            response_index=response_index,
            gold=gold,
            labels=labels,
            metric=metric,
        )
        control_boot, protocol_boot, difference_boot = crossed_bootstrap(
            pair_ids=pair_ids,
            participants=participants,
            response_index=response_index,
            gold=gold,
            labels=labels,
            metric=metric,
            repetitions=repetitions,
            rng=random.Random(seed + metric_index),
        )
        rows.append(
            {
                "scope": scope,
                "pairs": len(pair_ids),
                "metric": metric,
                "control": round(estimate["control"], 6),
                "control_ci_low": round(percentile(control_boot, 0.025), 6),
                "control_ci_high": round(percentile(control_boot, 0.975), 6),
                "protocol": round(estimate["protocol"], 6),
                "protocol_ci_low": round(percentile(protocol_boot, 0.025), 6),
                "protocol_ci_high": round(percentile(protocol_boot, 0.975), 6),
                "protocol_minus_control": round(estimate["difference"], 6),
                "difference_ci_low": round(percentile(difference_boot, 0.025), 6),
                "difference_ci_high": round(percentile(difference_boot, 0.975), 6),
                "bootstrap": (
                    f"{repetitions} crossed pair-by-annotator resamples; seed={seed + metric_index}"
                ),
            }
        )
    return rows


def same_panel_consistency(
    individual_rows: list[dict[str, str]],
    consensus_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    def summarize(
        rows: list[dict[str, str]],
        coordinate_key: str,
        plain_key: str,
        level: str,
    ) -> dict[str, object]:
        agreements = 0
        mapped = 0
        for row in rows:
            plain_label = row[plain_key]
            if plain_label not in PLAIN_LANGUAGE_MAP:
                raise ValueError(f"Unexpected plain-language label: {plain_label}")
            mapped += 1
            agreements += (
                row[coordinate_key] == PLAIN_LANGUAGE_MAP[plain_label]
            )
        return {
            "level": level,
            "records": mapped,
            "agreements": agreements,
            "agreement_rate": round(agreements / mapped, 6),
            "interpretation": (
                "Within-panel label-translation consistency only; the same adjudicators "
                "produced both labels, so this is not independent validation."
            ),
        }

    return [
        summarize(
            individual_rows,
            "gold_verdict",
            "independent_rubric_label",
            "individual_judgment",
        ),
        summarize(
            consensus_rows,
            "gold_verdict",
            "independent_rubric_label",
            "pair_consensus",
        ),
    ]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    canonical = (
        repo_root
        / "annotation_outputs"
        / "major_revision_blind_packet_20260615"
        / "evaluator_packet"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--responses", type=Path, default=canonical / "participant_responses.csv"
    )
    parser.add_argument(
        "--gold-consensus", type=Path, default=canonical / "gold_panel_consensus.csv"
    )
    parser.add_argument(
        "--gold-individual", type=Path, default=canonical / "gold_adjudications.csv"
    )
    parser.add_argument(
        "--canonical-map",
        type=Path,
        default=repo_root
        / "manuscript"
        / "supplement"
        / "evidence_map_venue_expanded_adjudicated.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "manuscript" / "supplement",
    )
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260713)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    responses = read_csv(args.responses)
    consensus_rows = read_csv(args.gold_consensus)
    individual_rows = read_csv(args.gold_individual)
    map_rows = read_csv(args.canonical_map)
    gold, participants = validate_inputs(responses, consensus_rows)
    response_index = {
        (row["condition"], row["participant_id"], row["pair_id"]): row["verdict"]
        for row in responses
    }

    all_pairs = sorted(gold)
    clean_pairs = [pair_id for pair_id in all_pairs if pair_id not in PACKET_OMISSIONS]
    if set(all_pairs) & set(PACKET_OMISSIONS) != set(PACKET_OMISSIONS):
        raise ValueError("A declared packet-omission pair is absent from the gold file.")

    canonical_paper_ids = {row["cite_key"] for row in map_rows}
    pair_papers: dict[str, tuple[str, str]] = {}
    pair_titles: dict[str, tuple[str, str]] = {}
    for row in individual_rows:
        pair_id = row["pair_id"]
        paper_pair = (row["paper_a_id"], row["paper_b_id"])
        title_pair = (row["paper_a_title"], row["paper_b_title"])
        previous = pair_papers.setdefault(pair_id, paper_pair)
        if previous != paper_pair:
            raise ValueError(f"Inconsistent paper IDs for pair {pair_id}")
        previous_titles = pair_titles.setdefault(pair_id, title_pair)
        if previous_titles != title_pair:
            raise ValueError(f"Inconsistent paper titles for pair {pair_id}")
    if set(pair_papers) != set(all_pairs):
        raise ValueError("Individual gold rows do not cover the consensus pair set.")
    canonical_pairs = [
        pair_id
        for pair_id in all_pairs
        if all(paper_id in canonical_paper_ids for paper_id in pair_papers[pair_id])
    ]
    canonical_clean_pairs = [
        pair_id for pair_id in canonical_pairs if pair_id not in PACKET_OMISSIONS
    ]

    results: list[dict[str, object]] = []
    results.extend(
        format_result_rows(
            scope="reported_60_pairs",
            pair_ids=all_pairs,
            labels=("invalid", "partial", "underspecified"),
            metrics=(
                "recall_invalid",
                "recall_partial",
                "recall_underspecified",
                "macro_recall_observed_classes",
                "raw_accuracy",
                "cohen_kappa",
            ),
            participants=participants,
            response_index=response_index,
            gold=gold,
            repetitions=args.bootstrap_repetitions,
            seed=args.seed,
        )
    )
    results.extend(
        format_result_rows(
            scope="canonical_map_and_documented_omissions_excluded_38_pairs",
            pair_ids=canonical_clean_pairs,
            labels=("invalid", "partial"),
            metrics=(
                "recall_invalid",
                "recall_partial",
                "macro_recall_observed_classes",
                "raw_accuracy",
                "cohen_kappa",
            ),
            participants=participants,
            response_index=response_index,
            gold=gold,
            repetitions=args.bootstrap_repetitions,
            seed=args.seed + 200,
        )
    )
    results.extend(
        format_result_rows(
            scope="documented_omissions_excluded_56_pairs",
            pair_ids=clean_pairs,
            labels=("invalid", "partial"),
            metrics=(
                "recall_invalid",
                "recall_partial",
                "macro_recall_observed_classes",
                "raw_accuracy",
                "cohen_kappa",
            ),
            participants=participants,
            response_index=response_index,
            gold=gold,
            repetitions=args.bootstrap_repetitions,
            seed=args.seed + 100,
        )
    )

    result_fields = [
        "scope",
        "pairs",
        "metric",
        "control",
        "control_ci_low",
        "control_ci_high",
        "protocol",
        "protocol_ci_low",
        "protocol_ci_high",
        "protocol_minus_control",
        "difference_ci_low",
        "difference_ci_high",
        "bootstrap",
    ]
    write_csv(
        args.output_dir / "validation_sensitivity_results.csv",
        results,
        result_fields,
    )

    exclusion_rows = [
        {
            "pair_id": pair_id,
            "reported_gold_verdict": gold[pair_id]["gold_verdict"],
            "exclusion_reason": reason,
            "analysis_action": (
                "Exclude from inferential metrics; do not relabel without a new blinded panel "
                "using a complete packet."
            ),
        }
        for pair_id, reason in PACKET_OMISSIONS.items()
    ]
    write_csv(
        args.output_dir / "validation_packet_integrity_exclusions.csv",
        exclusion_rows,
        [
            "pair_id",
            "reported_gold_verdict",
            "exclusion_reason",
            "analysis_action",
        ],
    )

    provenance_rows = []
    for pair_id in all_pairs:
        paper_a_id, paper_b_id = pair_papers[pair_id]
        paper_a_title, paper_b_title = pair_titles[pair_id]
        provenance_rows.append(
            {
                "pair_id": pair_id,
                "paper_a_id": paper_a_id,
                "paper_a_title": paper_a_title,
                "paper_a_in_canonical_map_b": str(
                    paper_a_id in canonical_paper_ids
                ).lower(),
                "paper_b_id": paper_b_id,
                "paper_b_title": paper_b_title,
                "paper_b_in_canonical_map_b": str(
                    paper_b_id in canonical_paper_ids
                ).lower(),
                "both_papers_in_canonical_map_b": str(
                    paper_a_id in canonical_paper_ids
                    and paper_b_id in canonical_paper_ids
                ).lower(),
                "gold_verdict": gold[pair_id]["gold_verdict"],
                "documented_packet_omission": str(
                    pair_id in PACKET_OMISSIONS
                ).lower(),
                "stimulus_snapshot_available_in_v1_release": "false",
            }
        )
    write_csv(
        args.output_dir / "validation_pair_provenance.csv",
        provenance_rows,
        [
            "pair_id",
            "paper_a_id",
            "paper_a_title",
            "paper_a_in_canonical_map_b",
            "paper_b_id",
            "paper_b_title",
            "paper_b_in_canonical_map_b",
            "both_papers_in_canonical_map_b",
            "gold_verdict",
            "documented_packet_omission",
            "stimulus_snapshot_available_in_v1_release",
        ],
    )

    consistency_rows = same_panel_consistency(individual_rows, consensus_rows)
    write_csv(
        args.output_dir / "within_panel_label_consistency.csv",
        consistency_rows,
        ["level", "records", "agreements", "agreement_rate", "interpretation"],
    )

    all_metrics = {row["metric"]: row for row in results if row["scope"] == "reported_60_pairs"}
    macro_contributions = {
        label: (
            all_metrics[f"recall_{label}"]["protocol_minus_control"] / 3
        )
        for label in ("invalid", "partial", "underspecified")
    }
    summary = {
        "canonical_inputs": {
            "responses": portable_path(args.responses, repo_root),
            "gold_consensus": portable_path(args.gold_consensus, repo_root),
            "gold_individual": portable_path(args.gold_individual, repo_root),
            "canonical_map": portable_path(args.canonical_map, repo_root),
        },
        "participants": {key: len(value) for key, value in participants.items()},
        "reported_pairs": len(all_pairs),
        "documented_omissions_excluded_pairs": len(clean_pairs),
        "both_papers_in_canonical_map_pairs": len(canonical_pairs),
        "canonical_map_and_documented_omissions_excluded_pairs": len(
            canonical_clean_pairs
        ),
        "excluded_packet_omissions": sorted(PACKET_OMISSIONS),
        "gold_distribution_reported": dict(
            Counter(gold[pair_id]["gold_verdict"] for pair_id in all_pairs)
        ),
        "gold_distribution_after_documented_omission_exclusions": dict(
            Counter(gold[pair_id]["gold_verdict"] for pair_id in clean_pairs)
        ),
        "gold_distribution_canonical_map_after_documented_omission_exclusions": dict(
            Counter(
                gold[pair_id]["gold_verdict"] for pair_id in canonical_clean_pairs
            )
        ),
        "reported_macro_gain_contribution_by_class": macro_contributions,
        "same_panel_plain_language_consistency": consistency_rows,
        "bootstrap": {
            "method": "crossed pair-by-annotator nonparametric bootstrap",
            "repetitions": args.bootstrap_repetitions,
            "seed": args.seed,
        },
        "interpretation": (
            "The four under-specified gold pairs are packet-integrity failures rather than "
            "validated instances of under-specification in the source papers. Once excluded, "
            "the present-class macro-recall difference is small; the remaining improvement is "
            "concentrated on invalid recall, while partial recall decreases. The plain-language "
            "labels were produced by the same adjudicators and measure within-panel consistency, "
            "not independent external validity."
        ),
    }
    with (args.output_dir / "validation_sensitivity_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(
        json.dumps(
            {
                "results": str(args.output_dir / "validation_sensitivity_results.csv"),
                "exclusions": str(
                    args.output_dir / "validation_packet_integrity_exclusions.csv"
                ),
                "consistency": str(
                    args.output_dir / "within_panel_label_consistency.csv"
                ),
                "pair_provenance": str(
                    args.output_dir / "validation_pair_provenance.csv"
                ),
                "summary": str(
                    args.output_dir / "validation_sensitivity_summary.json"
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
