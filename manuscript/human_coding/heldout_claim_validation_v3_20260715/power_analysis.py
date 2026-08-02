#!/usr/bin/env python3
"""Deterministic planning approximation for the held-out paired comparison.

This script uses only the Python standard library. Its output is a prospective
design calculation, not an empirical result and not a test-label generator.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any


ALPHA = 0.05
POWER_TARGET = 0.80
MEANINGFUL_DIFFERENCE = 0.10
EQUIVALENCE_MARGIN = 0.10
CLAIMS_PER_SOURCE = 6
BASELINE_CLAIMS = 360
BASELINE_SOURCES = 60
CHOSEN_CLAIMS = 480
CHOSEN_SOURCES = 80
MAXIMUM_CLAIMS = 480
MAXIMUM_SOURCES = 80
DISCORDANCE_SCENARIOS = (0.25, 0.30, 0.35)
SOURCE_ICC_SCENARIOS = (0.05, 0.10, 0.15)


def design_effect(cluster_size: float, source_icc: float) -> float:
    """Return the equal-cluster design effect."""

    return 1.0 + (cluster_size - 1.0) * source_icc


def paired_superiority_power(
    claims: int,
    sources: int,
    discordance: float,
    source_icc: float,
    difference: float = MEANINGFUL_DIFFERENCE,
    alpha: float = ALPHA,
) -> float:
    """Approximate two-sided power for a clustered paired-accuracy difference.

    Let Y be +1 when the Arm-D strict-majority label alone is correct, -1 when
    the Arm-C strict-majority label alone is correct, and zero otherwise. Then
    E[Y] is the accuracy difference, E[Y^2] is discordance, and Var(Y) is
    discordance minus the squared difference.
    """

    if claims <= 0 or sources <= 0:
        raise ValueError("claims and sources must be positive")
    if not 0.0 < discordance < 1.0:
        raise ValueError("discordance must lie in (0, 1)")
    if abs(difference) >= discordance:
        raise ValueError("absolute difference must be smaller than discordance")
    cluster_size = claims / sources
    inflation = design_effect(cluster_size, source_icc)
    variance = discordance - difference * difference
    standard_error = math.sqrt(variance * inflation / claims)
    noncentrality = difference / standard_error
    normal = NormalDist()
    critical = normal.inv_cdf(1.0 - alpha / 2.0)
    return normal.cdf(-critical - noncentrality) + 1.0 - normal.cdf(
        critical - noncentrality
    )


def equivalence_power_at_zero(
    claims: int,
    sources: int,
    discordance: float,
    source_icc: float,
    margin: float = EQUIVALENCE_MARGIN,
    alpha: float = ALPHA,
) -> float:
    """Approximate TOST power at a true zero difference."""

    cluster_size = claims / sources
    inflation = design_effect(cluster_size, source_icc)
    standard_error = math.sqrt(discordance * inflation / claims)
    one_sided_critical = NormalDist().inv_cdf(1.0 - alpha)
    interior_z = margin / standard_error - one_sided_critical
    return max(0.0, 2.0 * NormalDist().cdf(interior_z) - 1.0)


def minimum_six_claim_cluster_design(
    discordance: float,
    source_icc: float,
    target: float,
    power_function: str = "superiority",
    search_limit_claims: int = 1200,
) -> tuple[int, int, float]:
    """Find the first six-claim-per-source design meeting the target."""

    for claims in range(CLAIMS_PER_SOURCE, search_limit_claims + 1, CLAIMS_PER_SOURCE):
        sources = claims // CLAIMS_PER_SOURCE
        if power_function == "superiority":
            power = paired_superiority_power(
                claims, sources, discordance, source_icc
            )
        elif power_function == "equivalence":
            power = equivalence_power_at_zero(
                claims, sources, discordance, source_icc
            )
        else:
            raise ValueError(f"unknown power function: {power_function}")
        if power >= target:
            return claims, sources, power
    raise RuntimeError("search limit did not contain a design meeting target")


def build_report() -> dict[str, Any]:
    """Build the machine-readable prospective planning report."""

    scenarios: list[dict[str, Any]] = []
    for discordance in DISCORDANCE_SCENARIOS:
        for source_icc in SOURCE_ICC_SCENARIOS:
            minimum_claims, minimum_sources, minimum_power = (
                minimum_six_claim_cluster_design(
                    discordance, source_icc, POWER_TARGET
                )
            )
            baseline_power = paired_superiority_power(
                BASELINE_CLAIMS,
                BASELINE_SOURCES,
                discordance,
                source_icc,
            )
            chosen_power = paired_superiority_power(
                CHOSEN_CLAIMS,
                CHOSEN_SOURCES,
                discordance,
                source_icc,
            )
            scenarios.append(
                {
                    "discordance": discordance,
                    "source_icc": source_icc,
                    "power_360_claims_60_sources": round(baseline_power, 6),
                    "baseline_meets_0.80": baseline_power >= POWER_TARGET,
                    "minimum_claims_at_six_per_source": minimum_claims,
                    "minimum_sources": minimum_sources,
                    "power_at_minimum": round(minimum_power, 6),
                    "power_480_claims_80_sources": round(chosen_power, 6),
                    "chosen_design_meets_0.80": chosen_power >= POWER_TARGET,
                }
            )

    conservative = max(
        scenarios,
        key=lambda row: (
            int(row["minimum_claims_at_six_per_source"]),
            float(row["discordance"]),
            float(row["source_icc"]),
        ),
    )
    worst_equivalence_claims, worst_equivalence_sources, worst_equivalence_power = (
        minimum_six_claim_cluster_design(
            max(DISCORDANCE_SCENARIOS),
            max(SOURCE_ICC_SCENARIOS),
            POWER_TARGET,
            power_function="equivalence",
        )
    )
    chosen_equivalence_power = equivalence_power_at_zero(
        CHOSEN_CLAIMS,
        CHOSEN_SOURCES,
        max(DISCORDANCE_SCENARIOS),
        max(SOURCE_ICC_SCENARIOS),
    )

    report: dict[str, Any] = {
        "status": "PROSPECTIVE_POWER_APPROXIMATION_NOT_EMPIRICAL_RESULTS",
        "generated_by": "power_analysis.py",
        "random_seed": None,
        "random_seed_note": "The calculation is deterministic and uses no RNG.",
        "method": {
            "name": "normal approximation with equal-cluster design effect",
            "paired_variable": (
                "Y=1 if the D strict-majority arm label alone is exactly "
                "correct, -1 if the C strict-majority arm label alone is "
                "exactly correct, and 0 otherwise"
            ),
            "variance": "discordance - difference^2",
            "design_effect": "1 + (claims_per_source - 1) * source_icc",
            "test": "two-sided clustered paired accuracy difference",
        },
        "parameters": {
            "alpha": ALPHA,
            "power_target": POWER_TARGET,
            "minimum_meaningful_difference": MEANINGFUL_DIFFERENCE,
            "equivalence_margin": EQUIVALENCE_MARGIN,
            "claims_per_source": CLAIMS_PER_SOURCE,
            "discordance_scenarios": list(DISCORDANCE_SCENARIOS),
            "source_icc_scenarios": list(SOURCE_ICC_SCENARIOS),
        },
        "baseline_design": {
            "claims": BASELINE_CLAIMS,
            "sources": BASELINE_SOURCES,
        },
        "scenarios": scenarios,
        "baseline_all_scenarios_meet_target": all(
            bool(row["baseline_meets_0.80"]) for row in scenarios
        ),
        "conservative_minimum_superiority_design": {
            "claims": int(conservative["minimum_claims_at_six_per_source"]),
            "sources": int(conservative["minimum_sources"]),
            "discordance": float(conservative["discordance"]),
            "source_icc": float(conservative["source_icc"]),
            "approximate_power": float(conservative["power_at_minimum"]),
        },
        "chosen_design": {
            "claims": CHOSEN_CLAIMS,
            "sources": CHOSEN_SOURCES,
            "reason": (
                "Exceeds the conservative approximate minimum and permits "
                "complete 20-block 3-of-6 auditor balance."
            ),
            "all_superiority_scenarios_meet_target": all(
                bool(row["chosen_design_meets_0.80"]) for row in scenarios
            ),
            "worst_superiority_power": round(
                min(float(row["power_480_claims_80_sources"]) for row in scenarios),
                6,
            ),
        },
        "conditional_equivalence_planning": {
            "true_difference": 0.0,
            "worst_scenario_chosen_design_power": round(
                chosen_equivalence_power, 6
            ),
            "claims_needed_for_0.80_in_worst_scenario": worst_equivalence_claims,
            "sources_needed_for_0.80_in_worst_scenario": worst_equivalence_sources,
            "power_at_that_design": round(worst_equivalence_power, 6),
            "within_480_claim_80_source_cap": (
                worst_equivalence_claims <= MAXIMUM_CLAIMS
                and worst_equivalence_sources <= MAXIMUM_SOURCES
            ),
            "interpretation": (
                "Equivalence is a conditional TOST branch. Failure is "
                "inconclusive and is never interpreted as non-equivalence."
            ),
        },
        "limitations": [
            "The source ICC is assumed to apply to the paired correctness-difference variable.",
            "Clusters are assumed equal at six claims per source.",
            "The approximation does not model crossed auditor or gold-expert effects.",
            "Resolved gold labels and complete C/D ratings are assumed; missingness reduces power.",
            "Normal and design-effect approximations may differ from finite-sample cluster inference.",
            "Power calculations are prospective assumptions, not observed validation results.",
        ],
    }

    if report["baseline_all_scenarios_meet_target"]:
        raise AssertionError("baseline unexpectedly meets every conservative scenario")
    if not report["chosen_design"]["all_superiority_scenarios_meet_target"]:
        raise AssertionError("chosen design does not meet the superiority power target")
    if int(conservative["minimum_claims_at_six_per_source"]) > CHOSEN_CLAIMS:
        raise AssertionError("chosen design is smaller than the conservative minimum")
    if CHOSEN_CLAIMS > MAXIMUM_CLAIMS or CHOSEN_SOURCES > MAXIMUM_SOURCES:
        raise AssertionError("chosen design exceeds the preregistered cap")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().with_name("power_analysis.json"),
        help="JSON output path (default: next to this script)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    staging = args.output.with_name(args.output.name + ".new")
    staging.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    staging.replace(args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "baseline_all_scenarios_meet_target": report[
                    "baseline_all_scenarios_meet_target"
                ],
                "conservative_minimum": report[
                    "conservative_minimum_superiority_design"
                ],
                "chosen_design": report["chosen_design"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
