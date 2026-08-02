#!/usr/bin/env python3
"""Simulate source-only inference when prompts are assigned to auditors."""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import itertools
import json
import math
import random
import statistics
from pathlib import Path
from types import ModuleType
from statistics import NormalDist
from typing import Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[2]
DEFAULT_ANALYSIS = (
    REPO
    / "manuscript"
    / "human_coding"
    / "heldout_claim_validation_v3_20260715"
    / "analyze_collected_results.py"
)
DEFAULT_OUTPUT = REPO / "manuscript" / "supplement"
DEFAULT_TABLES = REPO / "manuscript" / "tables"
SEED = 2026072601
REPLICATES = 5_000
ALPHA = 0.05
CLAIMS_PER_SOURCE = 6
SOURCE_COUNTS = (20, 40, 80, 160)
BASELINE_ACCURACY = 0.75
RATER_LOGIT_SDS = (0.0, 0.10, 0.20, 0.30)
SOURCE_LOGIT_SD = 0.15
CLAIM_LOGIT_SD = 0.35
TRIPLES = tuple(itertools.combinations(range(6), 3))
PERMUTATIONS = tuple(itertools.combinations(range(12), 6))
TRIPLE_ARRAY = np.asarray(TRIPLES, dtype=np.int8)
PERMUTATION_D_PANELS = np.asarray(
    [
        [[assignment[slot] for slot in triple] for triple in TRIPLES]
        for assignment in PERMUTATIONS
    ],
    dtype=np.int8,
)
PERMUTATION_C_PANELS = np.asarray(
    [
        [
            [
                tuple(index for index in range(12) if index not in assignment)[slot]
                for slot in triple
            ]
            for triple in TRIPLES
        ]
        for assignment in PERMUTATIONS
    ],
    dtype=np.int8,
)
PERMUTATION_COMPLEMENTS = np.asarray(
    [
        PERMUTATIONS.index(
            tuple(index for index in range(12) if index not in assignment)
        )
        for assignment in PERMUTATIONS
    ],
    dtype=np.int16,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(text, encoding="utf-8")
    staging.replace(path)


def load_analysis(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("v3_simulation_analysis", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load analysis module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "student_t_quantile"):
        raise ValueError("analysis module lacks student_t_quantile")
    return module


def logistic(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def logit(probability: float) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must lie strictly between zero and one")
    return math.log(probability / (1.0 - probability))


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def rater_profiles(rater_logit_sd: float) -> list[float]:
    center = logit(BASELINE_ACCURACY)
    normal = NormalDist()
    return [
        logistic(
            center
            + rater_logit_sd * normal.inv_cdf((index + 0.5) / 12)
        )
        for index in range(12)
    ]


def exact_permutation_reject(
    participant_scores: Sequence[float],
    d_participants: set[int],
) -> bool:
    observed = (
        sum(participant_scores[index] for index in d_participants) / 6
        - sum(
            participant_scores[index]
            for index in range(12)
            if index not in d_participants
        )
        / 6
    )
    total = sum(participant_scores)
    extreme = 0
    for d_indices in PERMUTATIONS:
        d_sum = sum(participant_scores[index] for index in d_indices)
        estimate = d_sum / 6 - (total - d_sum) / 6
        extreme += abs(estimate) >= abs(observed) - 1.0e-15
    return extreme / len(PERMUTATIONS) < ALPHA


def all_panel_statistics(
    votes: np.ndarray,
    source_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    claim_count = source_count * CLAIMS_PER_SOURCE
    if votes.shape != (12, claim_count):
        raise ValueError("full vote matrix has the wrong shape")
    claim_indices = np.arange(claim_count)
    schedule = claim_indices % len(TRIPLES)
    expanded_claims = claim_indices[None, :, None]
    d_correct = (
        votes[PERMUTATION_D_PANELS[:, schedule, :], expanded_claims].sum(axis=2)
        >= 2
    )
    c_correct = (
        votes[PERMUTATION_C_PANELS[:, schedule, :], expanded_claims].sum(axis=2)
        >= 2
    )
    source_differences = (
        d_correct.astype(np.int8) - c_correct.astype(np.int8)
    ).reshape(len(PERMUTATIONS), source_count, CLAIMS_PER_SOURCE).mean(axis=2)
    estimates = source_differences.mean(axis=1)
    standard_errors = source_differences.std(axis=1, ddof=1) / math.sqrt(
        source_count
    )
    statistics_array = np.divide(
        estimates,
        standard_errors,
        out=np.zeros_like(estimates),
        where=standard_errors > 0.0,
    )
    zero_se = standard_errors == 0.0
    statistics_array[zero_se & (estimates > 0.0)] = math.inf
    statistics_array[zero_se & (estimates < 0.0)] = -math.inf
    return estimates, standard_errors, statistics_array


def randomization_reject(
    statistics_array: np.ndarray,
    observed_index: int,
) -> bool:
    observed = float(statistics_array[observed_index])
    extreme = int(
        np.count_nonzero(
            np.abs(statistics_array) >= abs(observed) - 1.0e-12
        )
    )
    return extreme / len(PERMUTATIONS) < ALPHA


def participant_scores_for_assignment(
    votes: np.ndarray,
    d_group: Sequence[int],
    c_group: Sequence[int],
) -> list[float]:
    participant_correct = np.zeros(12, dtype=np.int64)
    participant_total = np.zeros(12, dtype=np.int64)
    for claim_index in range(votes.shape[1]):
        triple = TRIPLES[claim_index % len(TRIPLES)]
        for group in (c_group, d_group):
            selected = [group[slot] for slot in triple]
            participant_correct[selected] += votes[selected, claim_index]
            participant_total[selected] += 1
    if np.any(participant_total == 0):
        raise ValueError("panel schedule leaves at least one participant unrated")
    return [
        float(participant_correct[index] / participant_total[index])
        for index in range(12)
    ]


def simulate_once(
    rng: random.Random,
    source_count: int,
    profiles: Sequence[float],
    t_critical: float,
) -> tuple[bool, bool, bool, bool, float, float]:
    observed_index = rng.randrange(len(PERMUTATIONS))
    d_group = PERMUTATIONS[observed_index]
    c_group = tuple(index for index in range(12) if index not in d_group)
    d_participants = set(d_group)
    profile_logits = [logit(value) for value in profiles]
    claim_count = source_count * CLAIMS_PER_SOURCE
    votes = np.empty((12, claim_count), dtype=np.int8)
    global_claim_index = 0

    for _source in range(source_count):
        source_shift = rng.gauss(0.0, SOURCE_LOGIT_SD)
        for _claim in range(CLAIMS_PER_SOURCE):
            claim_shift = source_shift + rng.gauss(0.0, CLAIM_LOGIT_SD)
            for participant in range(12):
                votes[participant, global_claim_index] = int(
                    rng.random()
                    < logistic(profile_logits[participant] + claim_shift)
                )
            global_claim_index += 1

    estimates, source_standard_errors, panel_t_statistics = all_panel_statistics(
        votes, source_count
    )
    if not np.allclose(
        panel_t_statistics[PERMUTATION_COMPLEMENTS],
        -panel_t_statistics,
        equal_nan=False,
    ):
        raise AssertionError("assignment distribution is not arm-swap symmetric")
    estimate = float(estimates[observed_index])
    source_se = float(source_standard_errors[observed_index])
    observed_t = float(panel_t_statistics[observed_index])
    source_reject = abs(observed_t) > t_critical
    same_statistic_reject = randomization_reject(
        panel_t_statistics, observed_index
    )
    raw_panel_reject = randomization_reject(estimates, observed_index)
    participant_scores = participant_scores_for_assignment(
        votes, d_group, c_group
    )
    participant_reject = exact_permutation_reject(
        participant_scores, d_participants
    )
    return (
        source_reject,
        same_statistic_reject,
        raw_panel_reject,
        participant_reject,
        estimate,
        source_se,
    )


def run_scenario(
    *,
    seed: int,
    replicates: int,
    source_count: int,
    rater_logit_sd: float,
    t_critical: float,
) -> dict[str, object]:
    rng = random.Random(seed)
    profiles = rater_profiles(rater_logit_sd)
    source_rejections = 0
    same_statistic_rejections = 0
    raw_panel_rejections = 0
    participant_rejections = 0
    estimates = []
    source_standard_errors = []
    for _replicate in range(replicates):
        (
            source_reject,
            same_statistic_reject,
            raw_panel_reject,
            participant_reject,
            estimate,
            source_se,
        ) = simulate_once(rng, source_count, profiles, t_critical)
        source_rejections += int(source_reject)
        same_statistic_rejections += int(same_statistic_reject)
        raw_panel_rejections += int(raw_panel_reject)
        participant_rejections += int(participant_reject)
        estimates.append(estimate)
        source_standard_errors.append(source_se)

    source_rate = source_rejections / replicates
    same_statistic_rate = same_statistic_rejections / replicates
    raw_panel_rate = raw_panel_rejections / replicates
    participant_rate = participant_rejections / replicates
    empirical_sd = statistics.stdev(estimates)
    mean_source_se = statistics.mean(source_standard_errors)
    return {
        "source_count": source_count,
        "claim_count": source_count * CLAIMS_PER_SOURCE,
        "auditors": 12,
        "auditors_per_arm": 6,
        "rater_logit_sd": rater_logit_sd,
        "profile_minimum": min(profiles),
        "profile_maximum": max(profiles),
        "replicates": replicates,
        "true_prompt_effect": 0.0,
        "source_only_rejection_rate": source_rate,
        "source_only_monte_carlo_se": math.sqrt(
            source_rate * (1.0 - source_rate) / replicates
        ),
        "same_statistic_permutation_rejection_rate": same_statistic_rate,
        "same_statistic_permutation_monte_carlo_se": math.sqrt(
            same_statistic_rate
            * (1.0 - same_statistic_rate)
            / replicates
        ),
        "raw_panel_permutation_rejection_rate": raw_panel_rate,
        "raw_panel_permutation_monte_carlo_se": math.sqrt(
            raw_panel_rate * (1.0 - raw_panel_rate) / replicates
        ),
        "participant_permutation_rejection_rate": participant_rate,
        "participant_permutation_monte_carlo_se": math.sqrt(
            participant_rate * (1.0 - participant_rate) / replicates
        ),
        "source_only_null_coverage": 1.0 - source_rate,
        "same_statistic_permutation_null_coverage": 1.0 - same_statistic_rate,
        "raw_panel_permutation_null_coverage": 1.0 - raw_panel_rate,
        "participant_permutation_null_coverage": 1.0 - participant_rate,
        "mean_estimate": statistics.mean(estimates),
        "estimate_sd": empirical_sd,
        "mean_source_only_se": mean_source_se,
        "empirical_sd_to_source_se": empirical_sd / mean_source_se,
        "estimate_q025": percentile(estimates, 0.025),
        "estimate_q975": percentile(estimates, 0.975),
    }


def render_table(rows: Sequence[Mapping[str, object]]) -> str:
    selected = [
        row
        for row in rows
        if (
            row["source_count"] == 80
            and row["rater_logit_sd"] == 0.0
        )
        or (
            row["rater_logit_sd"] == 0.2
            and row["source_count"] in {20, 80, 160}
        )
    ]
    lines = [
        r"\begin{table}[t]",
        r"\centering\footnotesize",
        r"\setlength{\tabcolsep}{1.2pt}",
        r"\begin{tabular}{@{}lrrrr@{}}",
        r"\toprule",
        (
            r"Setting & Source & Panel RI & Rater RI & SD/SE \\"
        ),
        r"\midrule",
    ]
    for row in selected:
        profile = (
            "Homog."
            if float(row["rater_logit_sd"]) == 0.0
            else rf"$\sigma={float(row['rater_logit_sd']):.2f}$"
        )
        lines.append(
            f"{profile}, $G={row['source_count']}$ & "
            f"{100 * float(row['source_only_rejection_rate']):.1f}"
            f" ({100 * float(row['source_only_monte_carlo_se']):.1f}) & "
            f"{100 * float(row['same_statistic_permutation_rejection_rate']):.1f}"
            f" ({100 * float(row['same_statistic_permutation_monte_carlo_se']):.1f}) & "
            f"{100 * float(row['participant_permutation_rejection_rate']):.1f}"
            f" ({100 * float(row['participant_permutation_monte_carlo_se']):.1f}) & "
            f"{float(row['empirical_sd_to_source_se']):.2f} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            (
                rf"\caption{{Null simulations with {int(selected[0]['replicates']):,} "
                r"replicates per row, 12 auditors (six per prompt), six claims "
                r"per source, and balanced three-of-six panels. "
                r"$G$ is the number of sources. "
                r"Rater ability follows 12 fixed normal quantiles "
                r"on the logit scale around 75\% mean agreement; $\sigma_r$ is "
                r"a sensitivity parameter, not an estimate from the excluded "
                r"human collection. Entries are rejection percentages with "
                r"Monte Carlo standard errors in parentheses. Source $t$ and "
                r"Panel RI use the identical studentized source-level "
                r"panel-majority statistic; Panel RI refers it to all 924 "
                r"six-versus-six assignments under a full-vote oracle and a "
                r"fixed arm-independent schedule. Rater RI instead uses "
                r"individual accuracy. SD/SE is the "
                r"empirical standard deviation of D$-$C divided by the mean "
                r"source-only standard error. Panel RI is a sharp-null design "
                r"benchmark, not an implementable test for the excluded "
                r"collection.}"
            ),
            r"\label{tab:assignment-mismatch-simulation}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def render_full_table(rows: Sequence[Mapping[str, object]]) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"\centering\small",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        (
            r"Rater profiles & Sources & Claims & Source-only rejection "
            r"& Panel-RI rejection & Rater-RI rejection & SD/SE \\"
        ),
        r"\midrule",
    ]
    for row in rows:
        profile = (
            "Homogeneous"
            if float(row["rater_logit_sd"]) == 0.0
            else rf"$\sigma_r={float(row['rater_logit_sd']):.2f}$"
        )
        lines.append(
            f"{profile} & {row['source_count']} & {row['claim_count']} & "
            f"{100 * float(row['source_only_rejection_rate']):.1f}\\% & "
            f"{100 * float(row['same_statistic_permutation_rejection_rate']):.1f}\\% & "
            f"{100 * float(row['participant_permutation_rejection_rate']):.1f}\\% & "
            f"{float(row['empirical_sd_to_source_se']):.2f} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            (
                r"\caption{Complete null-simulation sweep. Each row uses 5,000 "
                r"replicates and a true zero prompt effect. Panel RI uses the "
                r"same studentized panel-majority statistic as the source-only "
                r"test. A raw-contrast randomization sensitivity and Monte Carlo "
                r"standard errors are recorded in the released JSON. The four "
                r"headline rows appear in "
                r"Table~\ref{tab:assignment-mismatch-simulation}.}"
            ),
            r"\label{tab:assignment-mismatch-simulation-full}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-module", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tables-dir", type=Path, default=DEFAULT_TABLES)
    parser.add_argument("--replicates", type=int, default=REPLICATES)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.replicates < 1:
        raise ValueError("--replicates must be positive")
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    analysis = load_analysis(args.analysis_module)
    scenarios = sorted(
        {
            *(
                (source_count, 0.20)
                for source_count in SOURCE_COUNTS
            ),
            *(
                (80, rater_logit_sd)
                for rater_logit_sd in RATER_LOGIT_SDS
            ),
        }
    )
    scenario_arguments = []
    for index, (source_count, rater_logit_sd) in enumerate(scenarios):
        t_critical = analysis.student_t_quantile(1.0 - ALPHA / 2.0, source_count - 1)
        scenario_arguments.append(
            {
                "seed": SEED + index,
                "replicates": args.replicates,
                "source_count": source_count,
                "rater_logit_sd": rater_logit_sd,
                "t_critical": t_critical,
            }
        )
    if args.workers == 1:
        rows = [run_scenario(**arguments) for arguments in scenario_arguments]
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=min(args.workers, len(scenario_arguments))
        ) as executor:
            futures = [
                executor.submit(run_scenario, **arguments)
                for arguments in scenario_arguments
            ]
            rows = [future.result() for future in futures]

    json_path = args.output_dir / "assignment_mismatch_simulation.json"
    table_path = args.tables_dir / "main_assignment_mismatch_simulation.tex"
    full_table_path = (
        args.tables_dir / "assignment_mismatch_simulation_full.tex"
    )
    write_text(
        json_path,
        json.dumps(
            {
                "schema_version": "assignment-mismatch-simulation-v2",
                "seed": SEED,
                "alpha": ALPHA,
                "claims_per_source": CLAIMS_PER_SOURCE,
                "baseline_accuracy": BASELINE_ACCURACY,
                "source_logit_sd": SOURCE_LOGIT_SD,
                "claim_logit_sd": CLAIM_LOGIT_SD,
                "simulation_scope": (
                    "Parameter-sweep null design diagnostic; not a model of "
                    "the prompt effect or a population prevalence estimate."
                ),
                "same_statistic_scope": (
                    "Oracle Fisher randomization benchmark under the sharp "
                    "null, a complete 12-by-claim vote matrix, and a fixed "
                    "arm-independent panel schedule; not implementable from "
                    "the excluded collection's realized-arm votes."
                ),
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write_text(table_path, render_table(rows))
    write_text(full_table_path, render_full_table(rows))
    print(
        json.dumps(
            {
                "status": "ok",
                "replicates": args.replicates,
                "scenarios": len(rows),
                "outputs": [str(json_path), str(table_path), str(full_table_path)],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
