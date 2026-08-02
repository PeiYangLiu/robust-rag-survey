#!/usr/bin/env python3
"""Normalise verbose judge outputs to a final decision, symmetrically.

The benchmark instruction asks for exactly one action token with no
explanation.  Open 3--70B checkpoints comply almost always.  Several
API-served frontier models do not: they emit a worked calculation and then the
decision.  Under the strict parser those responses become ``parse_failure``,
which would score a model as wrong for a formatting deviation rather than for
its decision, and would make the open and API populations incomparable.

This script applies one normalisation to **every** model's raw outputs:

    normalised = strict_parse(text)
    if normalised == "parse_failure":
        normalised = last standalone occurrence of deploy_A / deploy_B / defer

The normalisation is symmetric by construction, and the script reports, per
model, how many cells it changes.  If it changes essentially nothing for the
open checkpoints and a great deal for the verbose API models, then it is a
formatting repair rather than a scoring intervention, and the reader can verify
that claim from the printed table.

Writes ``*.normalised.jsonl`` next to each raw file and a report JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from run_controlled_model_judges_v2 import parse_decision  # noqa: E402

MANUSCRIPT = SCRIPTS.parents[0]
REPO = SCRIPTS.parents[1]
SUPPLEMENT = MANUSCRIPT / "supplement"

DECISION = re.compile(r"\b(deploy_A|deploy_B|defer)\b", re.IGNORECASE)
NORMALISE = {"deploy_a": "deploy_A", "deploy_b": "deploy_B", "defer": "defer"}
THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def final_decision(text: str) -> str:
    """Last standalone decision token in the response."""
    cleaned = THINK.sub(" ", text or "")
    matches = DECISION.findall(cleaned)
    if not matches:
        return "parse_failure"
    return NORMALISE[matches[-1].lower()]


def decision_regret(losses: dict[str, float], decision: str) -> tuple[float, float]:
    optimum = min(losses.values())
    chosen = losses[decision] if decision in losses else max(losses.values())
    return chosen, chosen - optimum


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dirs",
        type=Path,
        nargs="+",
        default=[
            SUPPLEMENT / "controlled_model_judge_raw_v3",
            SUPPLEMENT / "controlled_model_judge_raw_v2",
        ],
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=SUPPLEMENT / "controlled_claim_audit_benchmark_v2.jsonl",
    )
    parser.add_argument(
        "--report", type=Path, default=SUPPLEMENT / "decision_normalisation_report.json"
    )
    args = parser.parse_args()

    losses_by_item = {}
    for line in args.benchmark.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            losses_by_item[str(row["item_id"])] = {
                k: float(v) for k, v in row["decision_losses"].items()
            }

    report = {}
    for directory in args.raw_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            if path.name.endswith(".normalised.jsonl") or ".tok24." in path.name:
                continue
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not rows:
                continue
            model = rows[0]["model"]
            changed = 0
            still_failing = 0
            recovered_agree = 0
            out = []
            for row in rows:
                strict = row["parsed_decision"]
                normalised = strict
                if strict == "parse_failure":
                    normalised = final_decision(str(row.get("raw_output", "")))
                    if normalised != "parse_failure":
                        changed += 1
                        if normalised == row["target_decision"]:
                            recovered_agree += 1
                    else:
                        still_failing += 1
                losses = losses_by_item.get(str(row["item_id"]), {})
                chosen, regret = (
                    decision_regret(losses, normalised) if losses else (0.0, 0.0)
                )
                new = dict(row)
                new["parsed_decision_strict"] = strict
                new["parsed_decision"] = normalised
                new["exact_agreement"] = int(normalised == row["target_decision"])
                new["chosen_loss"] = chosen
                new["regret"] = regret
                out.append(new)
            target = path.with_suffix(".normalised.jsonl")
            target.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in out) + "\n",
                encoding="utf-8",
            )
            report[model] = {
                "raw_file": str(path.relative_to(REPO)),
                "serving": rows[0].get("serving", "local_checkpoint"),
                "n_records": len(rows),
                "strict_parse_failures": sum(
                    r["parsed_decision"] == "parse_failure" for r in rows
                ),
                "cells_changed_by_normalisation": changed,
                "share_changed": round(changed / len(rows), 4),
                "unrecoverable_after_normalisation": still_failing,
                "recovered_cells_matching_target": recovered_agree,
            }

    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"{'model':<48}{'serving':<24}{'strict fail':>12}{'changed':>9}{'share':>8}")
    for model, entry in sorted(report.items(), key=lambda kv: -kv[1]["share_changed"]):
        print(
            f"{model:<48}{str(entry['serving']):<24}"
            f"{entry['strict_parse_failures']:>12}{entry['cells_changed_by_normalisation']:>9}"
            f"{entry['share_changed']:>8.3f}"
        )
    print(f"\nwrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
