#!/usr/bin/env python3
"""Analyse the v2 controlled consequence experiment with clustered inference.

Reviewer A's objection to the version-1 analysis was that "a paper arguing that
others compute uncertainty over the wrong unit reports its own headline
experiment with no uncertainty at all", that a single prompt template confounds
coordinate naming with wording and length, and that a constant predictor was
counted as evidence.

This analysis therefore

*   applies a pre-declared validity gate on the ``probe_competence`` stratum
    and on response degeneracy, and reports gated and ungated results
    separately;
*   estimates every arm contrast with a bootstrap clustered on the 300
    counterfactual pairs, which is the unit the benchmark randomises;
*   reports the ``full`` minus ``placebo`` contrast as primary, since the
    placebo arm is length-matched, so the contrast is not confounded with
    instruction verbosity;
*   reports the spread of each contrast across the four paraphrases;
*   applies a Holm correction across the primary model-by-stratum grid; and
*   combines models with a DerSimonian-Laird random-effects meta-analysis, so
    that the reported effect refers to a model population rather than to one
    checkpoint.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_CSV = (
    REPO / "manuscript" / "supplement" / "controlled_model_judge_results_v2.csv"
)
DEFAULT_OUTPUT_JSON = (
    REPO / "manuscript" / "supplement" / "controlled_model_judge_results_v2.json"
)
ARMS = ("ablated", "placebo", "full")
STRATA = ("probe_competence", "c2_capability", "c5_utility")
BOOTSTRAP_DRAWS = 4_000
SEED = 2026072708

# Pre-declared validity gate.  A model that cannot execute the displayed-loss
# rule is not performing the task, and a model that emits one action for
# essentially every item is a constant predictor.
GATE_PROBE_ACCURACY = 0.50
GATE_MAX_DECISION_SHARE = 0.90


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def holm(pvalues: Sequence[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda index: pvalues[index])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    for rank, index in enumerate(order):
        value = (len(pvalues) - rank) * pvalues[index]
        running = max(running, min(1.0, value))
        adjusted[index] = running
    return adjusted


def exact_mcnemar(only_left: int, only_right: int) -> float:
    total = only_left + only_right
    if total == 0:
        return 1.0
    smaller = min(only_left, only_right)
    tail = sum(math.comb(total, k) for k in range(smaller + 1)) / (2.0**total)
    return min(1.0, 2.0 * tail)


def majority_decision(decisions: Sequence[str]) -> str:
    counts = Counter(decisions)
    top, top_count = counts.most_common(1)[0]
    if sum(1 for value in counts.values() if value == top_count) > 1:
        return "tie"
    return top


class ModelData:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self.model = str(rows[0]["model"])
        self.pairs: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in rows:
            self.pairs[str(row["pair_id"])].append(row)
        self.pair_ids = sorted(self.pairs)
        self.rows = rows

    def accuracy(
        self, rows: Iterable[Mapping[str, object]], arm: str, stratum: str | None
    ) -> float:
        selected = [
            row
            for row in rows
            if row["arm"] == arm and (stratum is None or row["stratum"] == stratum)
        ]
        if not selected:
            return float("nan")
        return sum(int(row["exact_agreement"]) for row in selected) / len(selected)

    def mean_regret(
        self, rows: Iterable[Mapping[str, object]], arm: str, stratum: str | None
    ) -> float:
        selected = [
            row
            for row in rows
            if row["arm"] == arm and (stratum is None or row["stratum"] == stratum)
        ]
        if not selected:
            return float("nan")
        return sum(float(row["regret"]) for row in selected) / len(selected)

    def flat_rows(self, pair_ids: Sequence[str]) -> list[Mapping[str, object]]:
        out: list[Mapping[str, object]] = []
        for pair_id in pair_ids:
            out.extend(self.pairs[pair_id])
        return out


def bootstrap_contrast(
    data: ModelData,
    left: str,
    right: str,
    stratum: str | None,
    draws: int,
    seed: int,
) -> dict[str, float]:
    rng = random.Random(seed)
    values = []
    count = len(data.pair_ids)
    for _ in range(draws):
        sample = [data.pair_ids[rng.randrange(count)] for _ in range(count)]
        rows = data.flat_rows(sample)
        values.append(
            data.accuracy(rows, left, stratum) - data.accuracy(rows, right, stratum)
        )
    values = [value for value in values if not math.isnan(value)]
    values.sort()

    def quantile(probability: float) -> float:
        position = (len(values) - 1) * probability
        low = math.floor(position)
        high = math.ceil(position)
        if low == high:
            return values[low]
        weight = position - low
        return values[low] * (1.0 - weight) + values[high] * weight

    point = data.accuracy(data.rows, left, stratum) - data.accuracy(
        data.rows, right, stratum
    )
    standard_error = float(np.std(values, ddof=1)) if len(values) > 1 else float("nan")
    # Bootstrap p-value by inverting the percentile interval.
    below = sum(1 for value in values if value <= 0.0) / len(values)
    pvalue = min(1.0, 2.0 * min(below, 1.0 - below))
    return {
        "estimate": point,
        "ci_low": quantile(0.025),
        "ci_high": quantile(0.975),
        "bootstrap_se": standard_error,
        "bootstrap_p": pvalue,
    }


def paraphrase_spread(
    data: ModelData, left: str, right: str, stratum: str | None
) -> dict[str, float]:
    per_paraphrase = []
    for paraphrase in sorted({str(row["paraphrase"]) for row in data.rows}):
        subset = [row for row in data.rows if row["paraphrase"] == paraphrase]
        per_paraphrase.append(
            data.accuracy(subset, left, stratum) - data.accuracy(subset, right, stratum)
        )
    return {
        "paraphrase_min": min(per_paraphrase),
        "paraphrase_max": max(per_paraphrase),
        "paraphrase_sd": float(np.std(per_paraphrase, ddof=1)),
        "paraphrase_sign_agreement": sum(
            1 for value in per_paraphrase if value > 0
        )
        / len(per_paraphrase),
    }


def mcnemar_on_paraphrase_majority(
    data: ModelData, left: str, right: str, stratum: str | None
) -> dict[str, object]:
    by_item: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    targets: dict[str, str] = {}
    for row in data.rows:
        if stratum is not None and row["stratum"] != stratum:
            continue
        by_item[str(row["item_id"])][str(row["arm"])].append(str(row["parsed_decision"]))
        targets[str(row["item_id"])] = str(row["target_decision"])
    only_left = only_right = 0
    for item_id, arms in by_item.items():
        left_decision = majority_decision(arms[left])
        right_decision = majority_decision(arms[right])
        left_correct = left_decision == targets[item_id]
        right_correct = right_decision == targets[item_id]
        if left_correct and not right_correct:
            only_left += 1
        elif right_correct and not left_correct:
            only_right += 1
    return {
        "discordant_left_only": only_left,
        "discordant_right_only": only_right,
        "mcnemar_exact_p": exact_mcnemar(only_left, only_right),
    }


def dersimonian_laird(
    estimates: Sequence[float], variances: Sequence[float]
) -> dict[str, float]:
    estimates = np.asarray(estimates, dtype=float)
    variances = np.asarray(variances, dtype=float)
    weights = 1.0 / variances
    fixed = float(np.sum(weights * estimates) / np.sum(weights))
    q = float(np.sum(weights * (estimates - fixed) ** 2))
    degrees = len(estimates) - 1
    c = float(np.sum(weights) - np.sum(weights**2) / np.sum(weights))
    tau2 = max(0.0, (q - degrees) / c) if c > 0 else 0.0
    random_weights = 1.0 / (variances + tau2)
    pooled = float(np.sum(random_weights * estimates) / np.sum(random_weights))
    pooled_se = float(math.sqrt(1.0 / np.sum(random_weights)))
    z = pooled / pooled_se if pooled_se > 0 else 0.0
    from scipy import stats

    return {
        "pooled_estimate": pooled,
        "pooled_se": pooled_se,
        "ci_low": pooled - 1.96 * pooled_se,
        "ci_high": pooled + 1.96 * pooled_se,
        "tau2": tau2,
        "q": q,
        "i2": max(0.0, (q - degrees) / q) if q > 0 else 0.0,
        "z": z,
        "p": float(2.0 * (1.0 - stats.norm.cdf(abs(z)))),
        "studies": len(estimates),
    }


def gate_status(data: ModelData) -> dict[str, object]:
    probe = data.accuracy(data.rows, "ablated", "probe_competence")
    probe_full = data.accuracy(data.rows, "full", "probe_competence")
    decisions = Counter(str(row["parsed_decision"]) for row in data.rows)
    top_share = decisions.most_common(1)[0][1] / sum(decisions.values())
    passes = (
        max(probe, probe_full) >= GATE_PROBE_ACCURACY
        and top_share <= GATE_MAX_DECISION_SHARE
    )
    return {
        "probe_accuracy_ablated": probe,
        "probe_accuracy_full": probe_full,
        "modal_decision": decisions.most_common(1)[0][0],
        "modal_decision_share": top_share,
        "parse_failure_rate": decisions.get("parse_failure", 0) / sum(decisions.values()),
        "passes_validity_gate": passes,
        "gate_rule": (
            f"probe_competence accuracy >= {GATE_PROBE_ACCURACY:.2f} in at least "
            f"one arm and modal decision share <= {GATE_MAX_DECISION_SHARE:.2f}"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--draws", type=int, default=BOOTSTRAP_DRAWS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = []
    for path in args.inputs:
        rows = read_jsonl(path)
        if not rows:
            raise ValueError(f"no rows in {path}")
        models.append(ModelData(rows))
    models.sort(key=lambda data: data.model)

    records = []
    gates = {}
    for data in models:
        gates[data.model] = gate_status(data)
        for stratum in (None,) + STRATA:
            label = stratum or "all"
            row: dict[str, object] = {
                "model": data.model,
                "stratum": label,
                "passes_validity_gate": gates[data.model]["passes_validity_gate"],
            }
            for arm in ARMS:
                row[f"{arm}_accuracy"] = data.accuracy(data.rows, arm, stratum)
                row[f"{arm}_mean_regret"] = data.mean_regret(data.rows, arm, stratum)
            for left, right, name in (
                ("full", "placebo", "full_minus_placebo"),
                ("full", "ablated", "full_minus_ablated"),
                ("placebo", "ablated", "placebo_minus_ablated"),
            ):
                contrast = bootstrap_contrast(
                    data, left, right, stratum, args.draws, SEED
                )
                spread = paraphrase_spread(data, left, right, stratum)
                mcnemar = mcnemar_on_paraphrase_majority(data, left, right, stratum)
                for key, value in contrast.items():
                    row[f"{name}_{key}"] = value
                for key, value in spread.items():
                    row[f"{name}_{key}"] = value
                row[f"{name}_mcnemar_exact_p"] = mcnemar["mcnemar_exact_p"]
            records.append(row)

    # Holm correction across the primary grid: the full-minus-placebo contrast
    # on the two substantive strata, for gate-passing models only.
    primary = [
        record
        for record in records
        if record["stratum"] in ("c2_capability", "c5_utility")
        and record["passes_validity_gate"]
    ]
    adjusted = holm([float(record["full_minus_placebo_bootstrap_p"]) for record in primary])
    for record, value in zip(primary, adjusted):
        record["full_minus_placebo_holm_p"] = value
    for record in records:
        record.setdefault("full_minus_placebo_holm_p", "")

    meta = {}
    for stratum in STRATA:
        subset = [
            record
            for record in records
            if record["stratum"] == stratum and record["passes_validity_gate"]
        ]
        if len(subset) >= 2:
            meta[stratum] = dersimonian_laird(
                [float(record["full_minus_placebo_estimate"]) for record in subset],
                [
                    max(float(record["full_minus_placebo_bootstrap_se"]) ** 2, 1e-9)
                    for record in subset
                ],
            )

    fieldnames = sorted({key for record in records for key in record})
    fieldnames = ["model", "stratum", "passes_validity_gate"] + [
        name for name in fieldnames if name not in ("model", "stratum", "passes_validity_gate")
    ]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)

    payload = {
        "schema_version": "controlled-model-judge-analysis-v2",
        "models": [data.model for data in models],
        "bootstrap": {
            "draws": args.draws,
            "unit": "counterfactual pair",
            "seed": SEED,
        },
        "validity_gate": gates,
        "gate_passing_models": [
            model for model, status in gates.items() if status["passes_validity_gate"]
        ],
        "primary_contrast": "full minus placebo (length-matched)",
        "multiplicity": "Holm across gate-passing models x {c2_capability, c5_utility}",
        "random_effects_meta_analysis": meta,
        "records": records,
    }
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    write_macros(payload, args.output_csv.parent.parent / "tables")
    print(
        json.dumps(
            {
                "status": "ok",
                "models": len(models),
                "gate_passing": payload["gate_passing_models"],
                "meta": meta,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def write_macros(payload: Mapping[str, object], tables: Path) -> None:
    """Emit the numbers the manuscript quotes, so prose cannot drift."""
    gates = payload["validity_gate"]
    passing = payload["gate_passing_models"]
    failing = [model for model in gates if model not in passing]
    meta = payload["random_effects_meta_analysis"]

    def percent(value: float) -> str:
        return f"{100.0 * float(value):.1f}"

    def format_p(value: float) -> str:
        return "<.001" if value < 0.001 else f"{value:.3f}".lstrip("0")

    def signed_points(value: float) -> str:
        return f"{100.0 * float(value):+.1f}"

    lines = [
        "% Generated by scripts/analyze_controlled_model_judges_v2.py. Do not edit.",
        rf"\newcommand{{\CMJmodels}}{{{len(gates)}}}",
        rf"\newcommand{{\CMJpassing}}{{{len(passing)}}}",
        rf"\newcommand{{\CMJfailing}}{{{len(failing)}}}",
        rf"\newcommand{{\CMJdraws}}{{{payload['bootstrap']['draws']:,}}}",
    ]
    for stratum, short in (("c2_capability", "Ctwo"), ("c5_utility", "Cfive"), ("probe_competence", "Probe")):
        if stratum not in meta:
            continue
        entry = meta[stratum]
        lines += [
            rf"\newcommand{{\CMJ{short}Pooled}}{{{signed_points(entry['pooled_estimate'])}}}",
            rf"\newcommand{{\CMJ{short}Low}}{{{signed_points(entry['ci_low'])}}}",
            rf"\newcommand{{\CMJ{short}High}}{{{signed_points(entry['ci_high'])}}}",
            rf"\newcommand{{\CMJ{short}P}}{{{format_p(float(entry['p']))}}}",
            rf"\newcommand{{\CMJ{short}Isq}}{{{100.0 * float(entry['i2']):.0f}}}",
        ]
    probe_values = [
        max(float(status["probe_accuracy_ablated"]), float(status["probe_accuracy_full"]))
        for status in gates.values()
    ]
    lines += [
        rf"\newcommand{{\CMJprobeMin}}{{{percent(min(probe_values))}}}",
        rf"\newcommand{{\CMJprobeMax}}{{{percent(max(probe_values))}}}",
    ]
    (tables / "controlled_model_judges_v2_macros.tex").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
