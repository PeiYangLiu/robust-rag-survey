#!/usr/bin/env python3
"""Build a counterfactual robust-RAG deployment-decision benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO
    / "manuscript"
    / "supplement"
    / "controlled_claim_audit_benchmark.jsonl"
)
DEFAULT_SUMMARY = (
    REPO
    / "manuscript"
    / "supplement"
    / "controlled_claim_audit_benchmark_summary.json"
)
SEED = 2026072602
PAIRS_PER_STRATUM = 120
DECISIONS = ("deploy_A", "deploy_B", "defer")
TEMPLATE_FAMILIES = (
    "medical_qa",
    "legal_qa",
    "software_support",
    "financial_analysis",
    "scientific_qa",
    "public_policy",
    "cybersecurity",
    "enterprise_search",
    "education",
    "customer_support",
    "news_verification",
    "technical_manuals",
)


def canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def format_rate(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def expected_loss(
    *,
    coverage: float,
    answered_error: float,
    error_cost: float,
    abstention_cost: float,
    compute_cost: float,
    uncertainty_penalty: float = 0.0,
) -> float:
    return (
        coverage * answered_error * error_cost
        + (1.0 - coverage) * abstention_cost
        + compute_cost
        + uncertainty_penalty
    )


def target_from_losses(losses: Mapping[str, float]) -> str:
    target = min(losses, key=losses.get)
    ordered = sorted(losses.values())
    if not math.isfinite(ordered[0]) or ordered[1] - ordered[0] < 0.01:
        raise ValueError("benchmark target must have a unique consequential margin")
    return target


def family_context(family: str) -> tuple[str, str]:
    contexts = {
        "medical_qa": ("clinical evidence assistant", "patient-facing answer"),
        "legal_qa": ("legal research assistant", "case-law answer"),
        "software_support": ("software support agent", "troubleshooting answer"),
        "financial_analysis": ("financial analysis assistant", "market answer"),
        "scientific_qa": ("scientific literature assistant", "research answer"),
        "public_policy": ("public-policy assistant", "policy answer"),
        "cybersecurity": ("security operations assistant", "incident answer"),
        "enterprise_search": ("enterprise search assistant", "internal answer"),
        "education": ("educational tutor", "student answer"),
        "customer_support": ("customer support assistant", "service answer"),
        "news_verification": ("news verification assistant", "verification answer"),
        "technical_manuals": ("technical manual assistant", "maintenance answer"),
    }
    return contexts[family]


def c2_pair(index: int, rng: random.Random) -> list[dict[str, object]]:
    family = TEMPLATE_FAMILIES[index % len(TEMPLATE_FAMILIES)]
    system_context, answer_type = family_context(family)
    pair_id = f"C2-{index + 1:03d}"
    safer_is_a = index % 2 == 0
    lower = 0.035 + 0.005 * rng.randrange(0, 5)
    gap = 0.035 + 0.005 * rng.randrange(0, 5)
    error_a, error_b = (
        (lower, lower + gap) if safer_is_a else (lower + gap, lower)
    )
    compute_a = 0.006 + 0.002 * rng.randrange(0, 4)
    compute_b = 0.006 + 0.002 * rng.randrange(0, 4)
    tested_access = rng.choice(
        (
            "black-box query access with no retriever internals",
            "read-only corpus access with no index modification",
            "non-adaptive natural retrieval failures",
            "fixed prompt-injection strings with no model feedback",
        )
    )
    tested_budget = rng.choice((5, 8, 10, 12))
    stronger_access = rng.choice(
        (
            "white-box retriever access and index modification",
            "adaptive query feedback plus corpus write access",
            "generator-gradient access and adaptive payloads",
            "coordinated retrieval and prompt-injection control",
        )
    )
    stronger_budget = tested_budget * rng.choice((5, 8, 10))
    matched_defer = min(error_a + compute_a, error_b + compute_b) + 0.12
    variants = (
        (
            "matched",
            (
                f"{tested_access}; the maximum disturbance budget is "
                f"{tested_budget} attempts, exactly matching the evaluation."
            ),
            0.0,
            matched_defer,
        ),
        (
            "capability_shift",
            (
                f"{stronger_access}; the disturbance budget is "
                f"{stronger_budget} attempts, outside both evaluations."
            ),
            0.50,
            matched_defer,
        ),
    )
    rows = []
    for variant, deployment_capability, uncertainty_penalty, defer_cost in variants:
        losses = {
            "deploy_A": error_a + compute_a + uncertainty_penalty,
            "deploy_B": error_b + compute_b + uncertainty_penalty,
            "defer": defer_cost,
        }
        target = target_from_losses(losses)
        vignette = (
            f"Two reports evaluate System A and System B for a {system_context}. "
            f"Both use the same 10,000-query corpus snapshot, retriever, generator, "
            f"and exact definition of an erroneous {answer_type}. Both evaluations "
            f"cover {tested_access} with at most {tested_budget} disturbance attempts. "
            f"System A has {format_rate(error_a)} erroneous answers and "
            f"{compute_a:.3f} compute-cost units per query. System B has "
            f"{format_rate(error_b)} erroneous answers and {compute_b:.3f} "
            f"compute-cost units per query. The deployment condition is: "
            f"{deployment_capability} The deployment policy adds a 0.50 loss to "
            f"either system when the deployed origin/access/budget lies outside "
            f"that system's evaluated capability envelope; otherwise this penalty "
            f"is zero. Commissioning a matched evaluation instead of deploying "
            f"costs {defer_cost:.3f} loss units per query. Error loss is one unit "
            f"per erroneous answer. Choose the action with minimum expected loss."
        )
        rows.append(
            {
                "item_id": f"{pair_id}-{variant}",
                "pair_id": pair_id,
                "stratum": "c2_capability",
                "variant": variant,
                "template_family": family,
                "vignette": vignette,
                "target_decision": target,
                "decision_losses": losses,
                "decisive_change": "deployment_origin_access_budget",
                "schema_version": "controlled-claim-audit-v1",
            }
        )
    if rows[0]["target_decision"] == rows[1]["target_decision"]:
        raise AssertionError("C2 counterfactual did not change the target")
    return rows


def c5_pair(index: int, rng: random.Random) -> list[dict[str, object]]:
    family = TEMPLATE_FAMILIES[index % len(TEMPLATE_FAMILIES)]
    system_context, answer_type = family_context(family)
    pair_id = f"C5-{index + 1:03d}"
    selective_is_a = index % 2 == 0
    selective_coverage = 0.68 + 0.02 * rng.randrange(0, 5)
    broad_coverage = 0.91 + 0.01 * rng.randrange(0, 5)
    selective_error = 0.035 + 0.005 * rng.randrange(0, 5)
    broad_error = 0.105 + 0.005 * rng.randrange(0, 7)
    if selective_is_a:
        coverage_a, error_a = selective_coverage, selective_error
        coverage_b, error_b = broad_coverage, broad_error
    else:
        coverage_a, error_a = broad_coverage, broad_error
        coverage_b, error_b = selective_coverage, selective_error
    compute_a = 0.006 + 0.002 * rng.randrange(0, 3)
    compute_b = 0.006 + 0.002 * rng.randrange(0, 3)
    regimes = (
        ("error_costly", 3.0, 0.05),
        ("abstention_costly", 0.20, 0.80),
    )
    rows = []
    for variant, error_cost, abstention_cost in regimes:
        loss_a = expected_loss(
            coverage=coverage_a,
            answered_error=error_a,
            error_cost=error_cost,
            abstention_cost=abstention_cost,
            compute_cost=compute_a,
        )
        loss_b = expected_loss(
            coverage=coverage_b,
            answered_error=error_b,
            error_cost=error_cost,
            abstention_cost=abstention_cost,
            compute_cost=compute_b,
        )
        losses = {
            "deploy_A": loss_a,
            "deploy_B": loss_b,
            "defer": min(loss_a, loss_b) + 0.20,
        }
        target = target_from_losses(losses)
        vignette = (
            f"Two reports evaluate System A and System B for a {system_context}. "
            f"They use the same corpus snapshot, retriever, generator, evidence "
            f"condition, and 10,000-query test set. An error rate is measured only "
            f"among answered queries. System A answers {format_rate(coverage_a)} "
            f"of queries, has {format_rate(error_a)} error among answered "
            f"{answer_type}s, and costs {compute_a:.3f} per query. System B answers "
            f"{format_rate(coverage_b)} of queries, has {format_rate(error_b)} "
            f"error among answered {answer_type}s, and costs {compute_b:.3f} per "
            f"query. In deployment, an erroneous answered query costs "
            f"{error_cost:.2f} loss units and an abstention costs "
            f"{abstention_cost:.2f}; compute cost is added directly. Expected loss "
            f"is coverage times answered-query error times error cost, plus "
            f"one-minus-coverage times abstention cost, plus compute cost. "
            f"Deferring deployment for another study costs 0.20 more than the "
            f"better deployable system. Choose the action with minimum expected loss."
        )
        rows.append(
            {
                "item_id": f"{pair_id}-{variant}",
                "pair_id": pair_id,
                "stratum": "c5_utility",
                "variant": variant,
                "template_family": family,
                "vignette": vignette,
                "target_decision": target,
                "decision_losses": losses,
                "decisive_change": "error_abstention_costs",
                "schema_version": "controlled-claim-audit-v1",
            }
        )
    if rows[0]["target_decision"] == rows[1]["target_decision"]:
        raise AssertionError("C5 counterfactual did not change the target")
    return rows


def build_rows() -> list[dict[str, object]]:
    rng = random.Random(SEED)
    rows = []
    for index in range(PAIRS_PER_STRATUM):
        rows.extend(c2_pair(index, rng))
        rows.extend(c5_pair(index, rng))
    rows.sort(key=lambda row: str(row["item_id"]))
    for row in rows:
        record_without_hash = dict(row)
        row["record_sha256"] = sha256_text(canonical_json(record_without_hash))
    validate(rows)
    return rows


def validate(rows: Sequence[Mapping[str, object]]) -> None:
    if len(rows) != 480:
        raise ValueError(f"expected 480 benchmark items, found {len(rows)}")
    if len({row["item_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate item IDs")
    strata = Counter(str(row["stratum"]) for row in rows)
    if strata != {"c2_capability": 240, "c5_utility": 240}:
        raise ValueError(f"unexpected stratum balance: {strata}")
    pair_counts = Counter(str(row["pair_id"]) for row in rows)
    if len(pair_counts) != 240 or set(pair_counts.values()) != {2}:
        raise ValueError("counterfactual pairs must contain exactly two items")
    by_pair: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        by_pair.setdefault(str(row["pair_id"]), []).append(row)
    for pair_id, pair_rows in by_pair.items():
        if not pair_id.startswith("C2-"):
            continue
        by_variant = {str(row["variant"]): row for row in pair_rows}
        matched = by_variant["matched"]["decision_losses"]
        shifted = by_variant["capability_shift"]["decision_losses"]
        if not math.isclose(
            float(matched["defer"]), float(shifted["defer"])
        ):
            raise ValueError(f"C2 defer cost changes within {pair_id}")
        for action in ("deploy_A", "deploy_B"):
            if not math.isclose(
                float(shifted[action]) - float(matched[action]), 0.50
            ):
                raise ValueError(f"C2 capability penalty is not isolated in {pair_id}")
    family_counts = Counter(str(row["template_family"]) for row in rows)
    if set(family_counts.values()) != {40}:
        raise ValueError(f"template families are imbalanced: {family_counts}")
    if any(row["target_decision"] not in DECISIONS for row in rows):
        raise ValueError("invalid target decision")
    for row in rows:
        losses = row["decision_losses"]
        if row["target_decision"] != target_from_losses(losses):
            raise ValueError(f"loss/target mismatch for {row['item_id']}")
        unhashed = dict(row)
        stored_hash = unhashed.pop("record_sha256")
        if stored_hash != sha256_text(canonical_json(unhashed)):
            raise ValueError(f"record hash mismatch for {row['item_id']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_rows()
    payload = "\n".join(canonical_json(row) for row in rows) + "\n"
    summary = {
        "schema_version": "controlled-claim-audit-summary-v1",
        "seed": SEED,
        "items": len(rows),
        "pairs": len({row["pair_id"] for row in rows}),
        "strata": Counter(str(row["stratum"]) for row in rows),
        "template_families": Counter(str(row["template_family"]) for row in rows),
        "target_decisions": Counter(str(row["target_decision"]) for row in rows),
        "benchmark_sha256": sha256_text(payload),
        "target_definition": "unique minimum of the displayed deployment-loss rule",
        "counterfactual_controls": {
            "c2_defer_cost_fixed_within_pair": True,
            "c2_out_of_envelope_penalty": 0.50,
            "c5_capability_fixed_within_pair": True,
        },
        "design_status": (
            "Post-outcome correction removed an initial C2/defer-cost "
            "confound; all reported models were rerun on this benchmark."
        ),
        "human_labels_used": False,
        "source_paper_text_used": False,
    }
    summary_text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.check:
        if args.output.read_text(encoding="utf-8") != payload:
            raise ValueError("benchmark differs from deterministic rebuild")
        if args.summary.read_text(encoding="utf-8") != summary_text:
            raise ValueError("benchmark summary differs from deterministic rebuild")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        args.summary.write_text(summary_text, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "check": args.check,
                "items": len(rows),
                "output": str(args.output),
                "sha256": summary["benchmark_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
