#!/usr/bin/env python3
"""Analyze crossed prompt results on the controlled decision benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO / "manuscript" / "supplement" / "controlled_model_judge_results.json"
)
DEFAULT_BENCHMARK = (
    REPO
    / "manuscript"
    / "supplement"
    / "controlled_claim_audit_benchmark.jsonl"
)
DEFAULT_CSV = (
    REPO / "manuscript" / "supplement" / "controlled_model_judge_results.csv"
)
DEFAULT_TABLE = (
    REPO / "manuscript" / "tables" / "main_controlled_model_judges.tex"
)
DEFAULT_STRATA_TABLE = (
    REPO / "manuscript" / "tables" / "controlled_model_judges_strata.tex"
)
CONDITIONS = ("ablated", "full")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSON at {path}:{line_number}")
        rows.append(value)
    return rows


def write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    with staging.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    staging.replace(path)


def exact_binomial_two_sided(successes: int, trials: int) -> float:
    if trials == 0:
        return 1.0
    observed = math.comb(trials, successes) / (2**trials)
    return min(
        1.0,
        sum(
            math.comb(trials, value) / (2**trials)
            for value in range(trials + 1)
            if math.comb(trials, value) / (2**trials)
            <= observed + 1.0e-15
        ),
    )


def mcnemar(
    ablated: Mapping[str, Mapping[str, object]],
    full: Mapping[str, Mapping[str, object]],
    item_ids: Sequence[str],
) -> dict[str, object]:
    full_only = sum(
        int(full[item]["exact_agreement"]) == 1
        and int(ablated[item]["exact_agreement"]) == 0
        for item in item_ids
    )
    ablated_only = sum(
        int(ablated[item]["exact_agreement"]) == 1
        and int(full[item]["exact_agreement"]) == 0
        for item in item_ids
    )
    discordant = full_only + ablated_only
    return {
        "full_only_correct": full_only,
        "ablated_only_correct": ablated_only,
        "discordant": discordant,
        "exact_p_two_sided": exact_binomial_two_sided(
            full_only, discordant
        ),
    }


def validate_model(
    rows: Sequence[Mapping[str, object]],
    benchmark: Mapping[str, Mapping[str, object]],
) -> str:
    models = {str(row["model"]) for row in rows}
    if len(models) != 1:
        raise ValueError("each input must contain exactly one model")
    if len(rows) != 960:
        raise ValueError("each model input must contain 960 rows")
    keys = Counter((str(row["item_id"]), str(row["condition"])) for row in rows)
    if len(keys) != 960 or set(keys.values()) != {1}:
        raise ValueError("duplicate or missing model item-condition outputs")
    if Counter(str(row["condition"]) for row in rows) != {
        "ablated": 480,
        "full": 480,
    }:
        raise ValueError("condition coverage is not balanced")
    for field in (
        "model_commit",
        "model_revision_requested",
        "transformers_version",
        "torch_version",
    ):
        if len({str(row[field]) for row in rows}) != 1:
            raise ValueError(f"inconsistent {field} within model output")
    requested_revision = str(rows[0]["model_revision_requested"])
    model_commit = str(rows[0]["model_commit"])
    if requested_revision and requested_revision != model_commit:
        raise ValueError("requested model revision differs from loaded commit")
    target_by_item: dict[str, str] = {}
    hash_by_item: dict[str, str] = {}
    for row in rows:
        item_id = str(row["item_id"])
        if item_id not in benchmark:
            raise ValueError(f"model output contains unknown item: {item_id}")
        target = str(row["target_decision"])
        record_hash = str(row["benchmark_record_sha256"])
        if target != str(benchmark[item_id]["target_decision"]):
            raise ValueError(f"stale benchmark target for {item_id}")
        if record_hash != str(benchmark[item_id]["record_sha256"]):
            raise ValueError(f"stale benchmark hash for {item_id}")
        if item_id in target_by_item and target_by_item[item_id] != target:
            raise ValueError("target differs across conditions")
        if item_id in hash_by_item and hash_by_item[item_id] != record_hash:
            raise ValueError("benchmark record differs across conditions")
        target_by_item[item_id] = target
        hash_by_item[item_id] = record_hash
    if set(target_by_item) != set(benchmark):
        raise ValueError("model output does not cover the current benchmark")
    return models.pop()


def summarize_model(
    rows: Sequence[Mapping[str, object]],
    benchmark: Mapping[str, Mapping[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    model = validate_model(rows, benchmark)
    by_condition = {
        condition: {
            str(row["item_id"]): row
            for row in rows
            if row["condition"] == condition
        }
        for condition in CONDITIONS
    }
    item_ids = sorted(by_condition["ablated"])
    strata = {
        "all": item_ids,
        "c2_capability": [
            item for item in item_ids
            if by_condition["ablated"][item]["stratum"] == "c2_capability"
        ],
        "c5_utility": [
            item for item in item_ids
            if by_condition["ablated"][item]["stratum"] == "c5_utility"
        ],
    }
    result_rows = []
    for stratum, selected in strata.items():
        condition_results = {}
        for condition in CONDITIONS:
            chosen = [by_condition[condition][item] for item in selected]
            condition_results[condition] = {
                "accuracy": sum(int(row["exact_agreement"]) for row in chosen)
                / len(chosen),
                "mean_regret": sum(float(row["regret"]) for row in chosen)
                / len(chosen),
                "parse_failures": sum(
                    row["parsed_decision"] == "parse_failure"
                    for row in chosen
                ),
            }
        paired = mcnemar(
            by_condition["ablated"], by_condition["full"], selected
        )
        result_rows.append(
            {
                "model": model,
                "stratum": stratum,
                "items": len(selected),
                "ablated_accuracy": condition_results["ablated"]["accuracy"],
                "full_accuracy": condition_results["full"]["accuracy"],
                "full_minus_ablated_accuracy": (
                    condition_results["full"]["accuracy"]
                    - condition_results["ablated"]["accuracy"]
                ),
                "ablated_mean_regret": condition_results["ablated"][
                    "mean_regret"
                ],
                "full_mean_regret": condition_results["full"]["mean_regret"],
                "full_minus_ablated_regret": (
                    condition_results["full"]["mean_regret"]
                    - condition_results["ablated"]["mean_regret"]
                ),
                "full_only_correct": paired["full_only_correct"],
                "ablated_only_correct": paired["ablated_only_correct"],
                "mcnemar_exact_p": paired["exact_p_two_sided"],
                "ablated_parse_failures": condition_results["ablated"][
                    "parse_failures"
                ],
                "full_parse_failures": condition_results["full"][
                    "parse_failures"
                ],
            }
        )

    pair_results = []
    pairs: dict[str, list[str]] = defaultdict(list)
    for item_id, row in by_condition["ablated"].items():
        pairs[str(row["pair_id"])].append(item_id)
    if len(pairs) != 240 or set(map(len, pairs.values())) != {2}:
        raise ValueError("counterfactual pair coverage is invalid")
    for condition in CONDITIONS:
        exact_pairs = 0
        for pair_items in pairs.values():
            exact_pairs += all(
                int(by_condition[condition][item]["exact_agreement"]) == 1
                for item in pair_items
            )
        pair_results.append(
            {
                "model": model,
                "condition": condition,
                "pairs": len(pairs),
                "both_counterfactuals_correct": exact_pairs,
                "pair_accuracy": exact_pairs / len(pairs),
            }
        )
    pair_accuracy = {
        str(row["condition"]): float(row["pair_accuracy"])
        for row in pair_results
    }
    for row in result_rows:
        row["ablated_pair_accuracy"] = (
            pair_accuracy["ablated"] if row["stratum"] == "all" else ""
        )
        row["full_pair_accuracy"] = (
            pair_accuracy["full"] if row["stratum"] == "all" else ""
        )
    return result_rows, {
        "model": model,
        "model_commit": str(rows[0]["model_commit"]),
        "model_revision_requested": str(rows[0]["model_revision_requested"]),
        "transformers_version": str(rows[0]["transformers_version"]),
        "torch_version": str(rows[0]["torch_version"]),
        "counterfactual_pairs": pair_results,
    }


def render_table(rows: Sequence[Mapping[str, object]]) -> str:
    main_rows = [row for row in rows if row["stratum"] == "all"]
    model_display = {
        "Qwen/Qwen2.5-7B-Instruct": "Qwen2.5-7B",
        "microsoft/Phi-4-mini-instruct": "Phi-4-mini",
        "allenai/OLMo-2-1124-7B-Instruct": "OLMo-2-7B",
    }
    model_order = {
        "Qwen/Qwen2.5-7B-Instruct": 0,
        "microsoft/Phi-4-mini-instruct": 1,
        "allenai/OLMo-2-1124-7B-Instruct": 2,
    }
    main_rows.sort(key=lambda row: model_order.get(str(row["model"]), 99))
    lines = [
        r"\begin{table}[t]",
        r"\centering\footnotesize",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Model & Abl. & Full & $\Delta$ \\",
        r"\midrule",
    ]
    for row in main_rows:
        lines.append(
            f"{model_display.get(str(row['model']), str(row['model']))} & "
            f"{100 * float(row['ablated_accuracy']):.1f}\\% & "
            f"{100 * float(row['full_accuracy']):.1f}\\% & "
            f"{100 * float(row['full_minus_ablated_accuracy']):+.1f} pp \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\vspace{3pt}",
            r"\begin{tabular}{lrrr}",
            r"\toprule",
            r"Model & Abl. pair & Full pair & $\Delta$ regret \\",
            r"\midrule",
        ]
    )
    for row in main_rows:
        lines.append(
            f"{model_display.get(str(row['model']), str(row['model']))} & "
            f"{100 * float(row['ablated_pair_accuracy']):.1f}\\% & "
            f"{100 * float(row['full_pair_accuracy']):.1f}\\% & "
            f"{float(row['full_minus_ablated_regret']):+.3f} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            (
                r"\caption{Controlled crossed model-judge experiment. Targets "
                r"are unique minima of displayed deployment losses, not expert "
                r"labels. Pair columns require both members of a counterfactual "
                r"pair to be correct; negative $\Delta$ regret favors the full "
                r"prompt. Results describe these fixed models and items and do "
                r"not imply generalization to humans or a model population.}"
            ),
            r"\label{tab:controlled-model-judges}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def render_strata_table(rows: Sequence[Mapping[str, object]]) -> str:
    model_display = {
        "Qwen/Qwen2.5-7B-Instruct": "Qwen2.5-7B",
        "microsoft/Phi-4-mini-instruct": "Phi-4-mini",
        "allenai/OLMo-2-1124-7B-Instruct": "OLMo-2-7B",
    }
    stratum_display = {
        "all": "All",
        "c2_capability": "C2 capability",
        "c5_utility": "C5 utility",
    }
    lines = [
        r"\begin{table*}[t]",
        r"\centering\small",
        r"\setlength{\tabcolsep}{5pt}",
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule",
        (
            r"Model & Stratum & Ablated & Full & $\Delta$ agreement & "
            r"$\Delta$ regret & Full-only & Ablated-only \\"
        ),
        r"\midrule",
    ]
    previous_model = None
    for row in rows:
        if previous_model is not None and row["model"] != previous_model:
            lines.append(r"\addlinespace")
        previous_model = row["model"]
        lines.append(
            f"{model_display.get(str(row['model']), str(row['model']))} & "
            f"{stratum_display[str(row['stratum'])]} & "
            f"{100 * float(row['ablated_accuracy']):.1f}\\% & "
            f"{100 * float(row['full_accuracy']):.1f}\\% & "
            f"{100 * float(row['full_minus_ablated_accuracy']):+.1f} pp & "
            f"{float(row['full_minus_ablated_regret']):+.3f} & "
            f"{row['full_only_correct']} & {row['ablated_only_correct']} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            (
                r"\caption{Controlled model-judge results by decisive "
                r"coordinate. Full-only and ablated-only count discordant "
                r"item outcomes. Exact item-level McNemar diagnostics are "
                r"released but are not used for population inference because "
                r"the benchmark contains dependent counterfactual pairs.}"
            ),
            r"\label{tab:controlled-model-judges-strata}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--strata-table", type=Path, default=DEFAULT_STRATA_TABLE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark_rows = read_jsonl(args.benchmark)
    benchmark = {str(row["item_id"]): row for row in benchmark_rows}
    if len(benchmark) != 480 or len(benchmark_rows) != 480:
        raise ValueError("benchmark must contain 480 unique items")
    all_rows = []
    model_summaries = []
    raw_inputs = []
    seen_models = set()
    for path in args.input:
        rows, summary = summarize_model(read_jsonl(path), benchmark)
        model = str(summary["model"])
        if model in seen_models:
            raise ValueError(f"duplicate model input: {model}")
        seen_models.add(model)
        all_rows.extend(rows)
        model_summaries.append(summary)
        raw_inputs.append(
            {
                "model": model,
                "file": path.name,
                "sha256": sha256(path),
            }
        )
    model_order = {
        "Qwen/Qwen2.5-7B-Instruct": 0,
        "microsoft/Phi-4-mini-instruct": 1,
        "allenai/OLMo-2-1124-7B-Instruct": 2,
    }
    stratum_order = {"all": 0, "c2_capability": 1, "c5_utility": 2}
    all_rows.sort(
        key=lambda row: (
            model_order.get(str(row["model"]), 99),
            stratum_order.get(str(row["stratum"]), 99),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schema_version": "controlled-model-judge-analysis-v2",
                "models": sorted(seen_models),
                "rows": all_rows,
                "model_summaries": model_summaries,
                "benchmark_file": args.benchmark.name,
                "benchmark_sha256": sha256(args.benchmark),
                "raw_inputs": raw_inputs,
                "interpretation": (
                    "Fixed-model construct evidence on synthetic numerical "
                    "decisions; no human-study or natural-paper claim."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_csv(args.csv, tuple(all_rows[0]), all_rows)
    args.table.parent.mkdir(parents=True, exist_ok=True)
    args.table.write_text(render_table(all_rows), encoding="utf-8")
    args.strata_table.parent.mkdir(parents=True, exist_ok=True)
    args.strata_table.write_text(render_strata_table(all_rows), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "models": sorted(seen_models),
                "rows": len(all_rows),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
