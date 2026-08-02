#!/usr/bin/env python3
"""Build benchmark v2 for the controlled consequence test.

Revisions relative to v1 (``controlled_claim_audit_benchmark.jsonl``):

1.  v1 ``c5_utility`` items made ``defer`` a deterministic function of the two
    deployment losses, so ``defer`` was never optimal and the stratum collapsed
    to a binary choice on which every evaluated model scored at chance.  In v2
    the deferral price is an exogenous displayed constant that is optimal on a
    designed share of items, so the stratum is a genuine three-way decision.
2.  v1 ``c2_capability`` items always resolved a capability shift into
    ``defer``, because the out-of-envelope penalty hit both systems.  v2 splits
    the stratum into a symmetric sub-type (both systems leave their envelope)
    and an asymmetric sub-type (only one system leaves its envelope), so a
    capability shift can also flip the ordering between the two systems.
3.  A ``probe_competence`` stratum displays all three action losses directly.
    It measures whether a model executes the stated decision rule at all and
    supplies the pre-declared validity gate for the primary analysis.

The target of every item is the unique minimum of the displayed loss rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Callable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO / "manuscript" / "supplement" / "controlled_claim_audit_benchmark_v2.jsonl"
)
DEFAULT_SUMMARY = (
    REPO
    / "manuscript"
    / "supplement"
    / "controlled_claim_audit_benchmark_v2_summary.json"
)

SEED = 2026072701
SCHEMA_VERSION = "controlled-claim-audit-v2"
DECISIONS = ("deploy_A", "deploy_B", "defer")
MIN_MARGIN = 0.02

PROBE_PAIRS = 60
C2_PAIRS_PER_SUBTYPE = 60
C5_PAIRS_PER_SUBTYPE = 60

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

FAMILY_CONTEXT = {
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


def canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def format_rate(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def target_from_losses(losses: Mapping[str, float]) -> str:
    target = min(losses, key=losses.get)
    ordered = sorted(losses.values())
    if not math.isfinite(ordered[0]) or ordered[1] - ordered[0] < MIN_MARGIN:
        raise ValueError("benchmark target must have a unique consequential margin")
    return target


def selective_loss(
    *,
    coverage: float,
    answered_error: float,
    error_cost: float,
    abstention_cost: float,
    compute_cost: float,
) -> float:
    return (
        coverage * answered_error * error_cost
        + (1.0 - coverage) * abstention_cost
        + compute_cost
    )


def probe_pair(index: int, rng: random.Random) -> list[dict[str, object]]:
    """Displayed-loss argmin items that define the instruction-following gate."""
    family = TEMPLATE_FAMILIES[index % len(TEMPLATE_FAMILIES)]
    system_context, answer_type = FAMILY_CONTEXT[family]
    pair_id = f"P0-{index + 1:03d}"
    order = [
        ("deploy_A", "deploy_B"),
        ("deploy_B", "defer"),
        ("defer", "deploy_A"),
        ("deploy_A", "defer"),
        ("deploy_B", "deploy_A"),
        ("defer", "deploy_B"),
    ][index % 6]
    rows: list[dict[str, object]] = []
    for variant, winner in zip(("base", "shifted"), order):
        base = 0.20 + 0.01 * rng.randrange(0, 20)
        gaps = sorted(
            (
                MIN_MARGIN + 0.01 * rng.randrange(1, 12),
                MIN_MARGIN + 0.01 * rng.randrange(13, 26),
            )
        )
        others = [action for action in DECISIONS if action != winner]
        rng.shuffle(others)
        losses = {
            winner: round(base, 3),
            others[0]: round(base + gaps[0], 3),
            others[1]: round(base + gaps[1], 3),
        }
        target = target_from_losses(losses)
        vignette = (
            f"An operations review for a {system_context} has already computed the "
            f"expected loss of every available action on the same 10,000-query "
            f"evaluation, using one common definition of an erroneous "
            f"{answer_type}. Deploying System A has expected loss "
            f"{losses['deploy_A']:.3f} loss units per query. Deploying System B has "
            f"expected loss {losses['deploy_B']:.3f} loss units per query. "
            f"Commissioning a further matched evaluation instead of deploying has "
            f"expected loss {losses['defer']:.3f} loss units per query. No other "
            f"cost applies. Choose the action with minimum expected loss."
        )
        rows.append(
            {
                "item_id": f"{pair_id}-{variant}",
                "pair_id": pair_id,
                "stratum": "probe_competence",
                "subtype": "displayed_loss_argmin",
                "deferral_role": "displayed_constant",
                "variant": variant,
                "template_family": family,
                "vignette": vignette,
                "target_decision": target,
                "decision_losses": losses,
                "decisive_change": "displayed_expected_loss",
                "schema_version": SCHEMA_VERSION,
            }
        )
    if rows[0]["target_decision"] == rows[1]["target_decision"]:
        raise AssertionError(f"probe counterfactual did not move the target: {pair_id}")
    return rows


def c2_symmetric_pair(index: int, rng: random.Random) -> list[dict[str, object]]:
    """Deployment leaves both evaluated capability envelopes."""
    family = TEMPLATE_FAMILIES[index % len(TEMPLATE_FAMILIES)]
    system_context, answer_type = FAMILY_CONTEXT[family]
    pair_id = f"C2S-{index + 1:03d}"
    safer_is_a = index % 2 == 0
    lower = 0.035 + 0.005 * rng.randrange(0, 5)
    gap = 0.035 + 0.005 * rng.randrange(0, 5)
    error_a, error_b = (lower, lower + gap) if safer_is_a else (lower + gap, lower)
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
    penalty = 0.50
    defer_cost = round(min(error_a + compute_a, error_b + compute_b) + 0.12, 3)
    variants = (
        (
            "matched",
            f"{tested_access}; the maximum disturbance budget is {tested_budget} "
            f"attempts, exactly matching both evaluations",
            0.0,
            0.0,
        ),
        (
            "capability_shift",
            f"{stronger_access}; the disturbance budget is {stronger_budget} "
            f"attempts, outside both evaluations",
            penalty,
            penalty,
        ),
    )
    rows: list[dict[str, object]] = []
    for variant, deployment_capability, penalty_a, penalty_b in variants:
        losses = {
            "deploy_A": round(error_a + compute_a + penalty_a, 3),
            "deploy_B": round(error_b + compute_b + penalty_b, 3),
            "defer": defer_cost,
        }
        target = target_from_losses(losses)
        vignette = (
            f"Two reports evaluate System A and System B for a {system_context}. "
            f"Both use the same 10,000-query corpus snapshot, retriever, generator, "
            f"and exact definition of an erroneous {answer_type}. Both evaluations "
            f"cover {tested_access} with at most {tested_budget} disturbance "
            f"attempts. System A has {format_rate(error_a)} erroneous answers and "
            f"{compute_a:.3f} compute-cost units per query. System B has "
            f"{format_rate(error_b)} erroneous answers and {compute_b:.3f} "
            f"compute-cost units per query. The deployment condition is "
            f"{deployment_capability}. The deployment policy adds a {penalty:.2f} "
            f"loss to a system whenever the deployed origin, access, or budget lies "
            f"outside that system's evaluated capability envelope, and adds nothing "
            f"otherwise. Commissioning a matched evaluation instead of deploying "
            f"costs {defer_cost:.3f} loss units per query and is unaffected by the "
            f"deployment condition. Error loss is one unit per erroneous answer. "
            f"Choose the action with minimum expected loss."
        )
        rows.append(
            {
                "item_id": f"{pair_id}-{variant}",
                "pair_id": pair_id,
                "stratum": "c2_capability",
                "subtype": "symmetric_envelope_exit",
                "deferral_role": "fixed_within_pair",
                "variant": variant,
                "template_family": family,
                "vignette": vignette,
                "target_decision": target,
                "decision_losses": losses,
                "decisive_change": "deployment_origin_access_budget",
                "schema_version": SCHEMA_VERSION,
            }
        )
    if rows[0]["target_decision"] == rows[1]["target_decision"]:
        raise AssertionError(f"C2 symmetric counterfactual is inert: {pair_id}")
    return rows


def c2_asymmetric_pair(index: int, rng: random.Random) -> list[dict[str, object]]:
    """Deployment leaves only one evaluated envelope, so the ordering can flip."""
    family = TEMPLATE_FAMILIES[index % len(TEMPLATE_FAMILIES)]
    system_context, answer_type = FAMILY_CONTEXT[family]
    pair_id = f"C2A-{index + 1:03d}"
    narrow_is_a = index % 2 == 0
    strong_error = 0.030 + 0.005 * rng.randrange(0, 5)
    weak_error = strong_error + 0.030 + 0.005 * rng.randrange(0, 5)
    compute_narrow = 0.006 + 0.002 * rng.randrange(0, 4)
    compute_wide = 0.006 + 0.002 * rng.randrange(0, 4)
    narrow_budget = rng.choice((5, 8, 10))
    wide_budget = narrow_budget * rng.choice((6, 8, 10))
    narrow_access = rng.choice(
        (
            "black-box query access only",
            "read-only corpus access",
            "non-adaptive retrieval failures only",
        )
    )
    wide_access = rng.choice(
        (
            "corpus write access and adaptive queries",
            "white-box retriever access and adaptive payloads",
            "coordinated retrieval control with model feedback",
        )
    )
    penalty = 0.50
    narrow_name, wide_name = ("A", "B") if narrow_is_a else ("B", "A")
    error_narrow, error_wide = strong_error, weak_error
    defer_cost = round(
        min(error_narrow + compute_narrow, error_wide + compute_wide) + 0.30, 3
    )
    variants = (
        (
            "matched",
            f"{narrow_access} with at most {narrow_budget} disturbance attempts, "
            f"inside both evaluated envelopes",
            0.0,
        ),
        (
            "capability_shift",
            f"{wide_access} with up to {wide_budget} disturbance attempts, inside "
            f"System {wide_name}'s evaluated envelope but outside System "
            f"{narrow_name}'s",
            penalty,
        ),
    )
    rows: list[dict[str, object]] = []
    for variant, deployment_capability, narrow_penalty in variants:
        loss_narrow = round(error_narrow + compute_narrow + narrow_penalty, 3)
        loss_wide = round(error_wide + compute_wide, 3)
        losses = {
            "deploy_A": loss_narrow if narrow_is_a else loss_wide,
            "deploy_B": loss_wide if narrow_is_a else loss_narrow,
            "defer": defer_cost,
        }
        target = target_from_losses(losses)
        vignette = (
            f"Two reports evaluate System A and System B for a {system_context}. "
            f"Both use the same 10,000-query corpus snapshot, retriever, generator, "
            f"and exact definition of an erroneous {answer_type}. System "
            f"{narrow_name} was evaluated only under {narrow_access} with at most "
            f"{narrow_budget} disturbance attempts, and reports "
            f"{format_rate(error_narrow)} erroneous answers at {compute_narrow:.3f} "
            f"compute-cost units per query. System {wide_name} was evaluated under "
            f"{wide_access} with up to {wide_budget} disturbance attempts, and "
            f"reports {format_rate(error_wide)} erroneous answers at "
            f"{compute_wide:.3f} compute-cost units per query. The deployment "
            f"condition is {deployment_capability}. The deployment policy adds a "
            f"{penalty:.2f} loss to a system whenever the deployed origin, access, "
            f"or budget lies outside that system's evaluated capability envelope, "
            f"and adds nothing otherwise. Commissioning a matched evaluation "
            f"instead of deploying costs {defer_cost:.3f} loss units per query and "
            f"is unaffected by the deployment condition. Error loss is one unit per "
            f"erroneous answer. Choose the action with minimum expected loss."
        )
        rows.append(
            {
                "item_id": f"{pair_id}-{variant}",
                "pair_id": pair_id,
                "stratum": "c2_capability",
                "subtype": "asymmetric_envelope_exit",
                "deferral_role": "fixed_within_pair",
                "variant": variant,
                "template_family": family,
                "vignette": vignette,
                "target_decision": target,
                "decision_losses": losses,
                "decisive_change": "deployment_origin_access_budget",
                "schema_version": SCHEMA_VERSION,
            }
        )
    targets = {str(row["target_decision"]) for row in rows}
    if len(targets) != 2 or targets != {"deploy_A", "deploy_B"}:
        raise AssertionError(f"C2 asymmetric pair must flip the ordering: {pair_id}")
    return rows


def c5_cost_regime_pair(index: int, rng: random.Random) -> list[dict[str, object]]:
    """Error vs. abstention prices move the optimum between two action policies."""
    family = TEMPLATE_FAMILIES[index % len(TEMPLATE_FAMILIES)]
    system_context, answer_type = FAMILY_CONTEXT[family]
    pair_id = f"C5R-{index + 1:03d}"
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
    regimes = (("error_costly", 3.0, 0.05), ("abstention_costly", 0.20, 0.80))
    regime_losses: dict[str, dict[str, float]] = {}
    for variant, error_cost, abstention_cost in regimes:
        regime_losses[variant] = {
            "deploy_A": round(
                selective_loss(
                    coverage=coverage_a,
                    answered_error=error_a,
                    error_cost=error_cost,
                    abstention_cost=abstention_cost,
                    compute_cost=compute_a,
                ),
                3,
            ),
            "deploy_B": round(
                selective_loss(
                    coverage=coverage_b,
                    answered_error=error_b,
                    error_cost=error_cost,
                    abstention_cost=abstention_cost,
                    compute_cost=compute_b,
                ),
                3,
            ),
        }
    best_error = min(regime_losses["error_costly"].values())
    best_abstention = min(regime_losses["abstention_costly"].values())
    # The deferral price is exogenous: it is displayed as a constant that does
    # not track the deployment losses, so whether deferring is optimal depends
    # on the cost regime rather than on a fixed offset from the better system.
    if index % 2 == 1 and best_error - best_abstention > 3.0 * MIN_MARGIN:
        low = best_abstention + MIN_MARGIN
        high = best_error - MIN_MARGIN
        study_cost = round(low + (high - low) * (0.25 + 0.5 * rng.random()), 3)
        deferral_role = "optimal_under_costly_errors"
    else:
        ceiling = max(best_error, best_abstention)
        study_cost = round(ceiling + MIN_MARGIN + 0.01 * rng.randrange(1, 10), 3)
        deferral_role = "dominated_in_both_regimes"
    rows: list[dict[str, object]] = []
    for variant, error_cost, abstention_cost in regimes:
        losses = dict(regime_losses[variant])
        losses["defer"] = study_cost
        target = target_from_losses(losses)
        vignette = (
            f"Two reports evaluate System A and System B for a {system_context}. "
            f"They use the same corpus snapshot, retriever, generator, evidence "
            f"condition, attacker assumptions, and 10,000-query test set. An error "
            f"rate is measured only among answered queries. System A answers "
            f"{format_rate(coverage_a)} of queries, has {format_rate(error_a)} "
            f"error among answered {answer_type}s, and costs {compute_a:.3f} per "
            f"query. System B answers {format_rate(coverage_b)} of queries, has "
            f"{format_rate(error_b)} error among answered {answer_type}s, and costs "
            f"{compute_b:.3f} per query. In deployment, an erroneous answered query "
            f"costs {error_cost:.2f} loss units and an abstention costs "
            f"{abstention_cost:.2f}; compute cost is added directly. Expected "
            f"deployment loss is coverage times answered-query error times error "
            f"cost, plus one-minus-coverage times abstention cost, plus compute "
            f"cost. Commissioning a further matched evaluation instead of deploying "
            f"costs {study_cost:.3f} loss units per query regardless of these "
            f"prices. Choose the action with minimum expected loss."
        )
        rows.append(
            {
                "item_id": f"{pair_id}-{variant}",
                "pair_id": pair_id,
                "stratum": "c5_utility",
                "subtype": "cost_regime_shift",
                "deferral_role": deferral_role,
                "variant": variant,
                "template_family": family,
                "vignette": vignette,
                "target_decision": target,
                "decision_losses": losses,
                "decisive_change": "error_abstention_costs",
                "schema_version": SCHEMA_VERSION,
            }
        )
    if rows[0]["target_decision"] == rows[1]["target_decision"]:
        raise AssertionError(f"C5 regime counterfactual is inert: {pair_id}")
    return rows


def c5_action_set_pair(index: int, rng: random.Random) -> list[dict[str, object]]:
    """The exogenous deferral price moves the optimum in and out of ``defer``."""
    family = TEMPLATE_FAMILIES[index % len(TEMPLATE_FAMILIES)]
    system_context, answer_type = FAMILY_CONTEXT[family]
    pair_id = f"C5A-{index + 1:03d}"
    selective_is_a = index % 2 == 0
    coverage_selective = 0.70 + 0.02 * rng.randrange(0, 5)
    coverage_broad = 0.93 + 0.01 * rng.randrange(0, 4)
    error_selective = 0.040 + 0.005 * rng.randrange(0, 4)
    error_broad = 0.100 + 0.005 * rng.randrange(0, 6)
    if selective_is_a:
        coverage_a, error_a = coverage_selective, error_selective
        coverage_b, error_b = coverage_broad, error_broad
    else:
        coverage_a, error_a = coverage_broad, error_broad
        coverage_b, error_b = coverage_selective, error_selective
    compute_a = 0.006 + 0.002 * rng.randrange(0, 3)
    compute_b = 0.006 + 0.002 * rng.randrange(0, 3)
    error_cost = 2.0 + 0.5 * rng.randrange(0, 4)
    abstention_cost = 0.10 + 0.05 * rng.randrange(0, 4)
    loss_a = round(
        selective_loss(
            coverage=coverage_a,
            answered_error=error_a,
            error_cost=error_cost,
            abstention_cost=abstention_cost,
            compute_cost=compute_a,
        ),
        3,
    )
    loss_b = round(
        selective_loss(
            coverage=coverage_b,
            answered_error=error_b,
            error_cost=error_cost,
            abstention_cost=abstention_cost,
            compute_cost=compute_b,
        ),
        3,
    )
    best_deploy = min(loss_a, loss_b)
    if abs(loss_a - loss_b) < MIN_MARGIN:
        raise ValueError("C5 action-set pair needs a decisive deployment ordering")
    cheap_study = round(best_deploy - MIN_MARGIN - 0.01 * rng.randrange(1, 9), 3)
    dear_study = round(best_deploy + MIN_MARGIN + 0.01 * rng.randrange(1, 9), 3)
    if cheap_study <= 0.005:
        raise ValueError("C5 action-set pair needs a positive deferral price")
    variants = (("cheap_followup_study", cheap_study), ("dear_followup_study", dear_study))
    rows: list[dict[str, object]] = []
    for variant, study_cost in variants:
        losses = {"deploy_A": loss_a, "deploy_B": loss_b, "defer": study_cost}
        target = target_from_losses(losses)
        vignette = (
            f"Two reports evaluate System A and System B for a {system_context}. "
            f"They use the same corpus snapshot, retriever, generator, evidence "
            f"condition, attacker assumptions, and 10,000-query test set. An error "
            f"rate is measured only among answered queries. System A answers "
            f"{format_rate(coverage_a)} of queries, has {format_rate(error_a)} "
            f"error among answered {answer_type}s, and costs {compute_a:.3f} per "
            f"query. System B answers {format_rate(coverage_b)} of queries, has "
            f"{format_rate(error_b)} error among answered {answer_type}s, and costs "
            f"{compute_b:.3f} per query. In deployment an erroneous answered query "
            f"costs {error_cost:.2f} loss units, an abstention costs "
            f"{abstention_cost:.2f}, and compute cost is added directly. Expected "
            f"deployment loss is coverage times answered-query error times error "
            f"cost, plus one-minus-coverage times abstention cost, plus compute "
            f"cost. A third action is available: commissioning a matched follow-up "
            f"evaluation instead of deploying now costs {study_cost:.3f} loss units "
            f"per query. Choose the action with minimum expected loss."
        )
        rows.append(
            {
                "item_id": f"{pair_id}-{variant}",
                "pair_id": pair_id,
                "stratum": "c5_utility",
                "subtype": "action_set_shift",
                "deferral_role": "exogenous_price_manipulated",
                "variant": variant,
                "template_family": family,
                "vignette": vignette,
                "target_decision": target,
                "decision_losses": losses,
                "decisive_change": "deferral_price",
                "schema_version": SCHEMA_VERSION,
            }
        )
    targets = [str(row["target_decision"]) for row in rows]
    if targets[0] != "defer" or targets[1] == "defer":
        raise AssertionError(f"C5 action-set counterfactual is malformed: {pair_id}")
    return rows


def draw_pair(
    builder: Callable[[int, random.Random], list[dict[str, object]]],
    index: int,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Redraw a pair until its counterfactual and margin constraints hold.

    The retry loop consumes the shared generator, so the benchmark stays a
    deterministic function of ``SEED``.
    """
    for _ in range(2000):
        try:
            return builder(index, rng)
        except (ValueError, AssertionError):
            continue
    raise RuntimeError(f"could not construct pair {index} for {builder.__name__}")


def build_rows() -> list[dict[str, object]]:
    rng = random.Random(SEED)
    rows: list[dict[str, object]] = []
    for index in range(PROBE_PAIRS):
        rows.extend(draw_pair(probe_pair, index, rng))
    for index in range(C2_PAIRS_PER_SUBTYPE):
        rows.extend(draw_pair(c2_symmetric_pair, index, rng))
        rows.extend(draw_pair(c2_asymmetric_pair, index, rng))
    for index in range(C5_PAIRS_PER_SUBTYPE):
        rows.extend(draw_pair(c5_cost_regime_pair, index, rng))
        rows.extend(draw_pair(c5_action_set_pair, index, rng))
    rows.sort(key=lambda row: str(row["item_id"]))
    for row in rows:
        row["record_sha256"] = sha256_text(canonical_json(dict(row)))
    validate(rows)
    return rows


def validate(rows: Sequence[Mapping[str, object]]) -> None:
    expected_items = 2 * (
        PROBE_PAIRS + 2 * C2_PAIRS_PER_SUBTYPE + 2 * C5_PAIRS_PER_SUBTYPE
    )
    if len(rows) != expected_items:
        raise ValueError(f"expected {expected_items} items, found {len(rows)}")
    if len({row["item_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate item IDs")
    strata = Counter(str(row["stratum"]) for row in rows)
    if strata != {
        "probe_competence": 2 * PROBE_PAIRS,
        "c2_capability": 4 * C2_PAIRS_PER_SUBTYPE,
        "c5_utility": 4 * C5_PAIRS_PER_SUBTYPE,
    }:
        raise ValueError(f"unexpected stratum balance: {strata}")
    pair_counts = Counter(str(row["pair_id"]) for row in rows)
    if set(pair_counts.values()) != {2}:
        raise ValueError("counterfactual pairs must contain exactly two items")
    for row in rows:
        losses = {k: float(v) for k, v in row["decision_losses"].items()}
        if set(losses) != set(DECISIONS):
            raise ValueError(f"missing action in {row['item_id']}")
        if row["target_decision"] != target_from_losses(losses):
            raise ValueError(f"loss/target mismatch for {row['item_id']}")
        unhashed = dict(row)
        stored = unhashed.pop("record_sha256")
        if stored != sha256_text(canonical_json(unhashed)):
            raise ValueError(f"record hash mismatch for {row['item_id']}")
    for stratum in ("probe_competence", "c2_capability", "c5_utility"):
        targets = Counter(
            str(row["target_decision"]) for row in rows if row["stratum"] == stratum
        )
        if set(targets) != set(DECISIONS):
            raise ValueError(f"stratum {stratum} does not use every action: {targets}")
        total = sum(targets.values())
        if max(targets.values()) / total > 0.60:
            raise ValueError(
                f"stratum {stratum} target distribution is too skewed: {targets}"
            )
    families = Counter(str(row["template_family"]) for row in rows)
    if len(set(families.values())) != 1:
        raise ValueError(f"template families are imbalanced: {families}")
    by_pair: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        by_pair.setdefault(str(row["pair_id"]), []).append(row)
    for pair_id, pair_rows in by_pair.items():
        if not pair_id.startswith("C2"):
            continue
        if len({float(row["decision_losses"]["defer"]) for row in pair_rows}) != 1:
            raise ValueError(f"C2 deferral cost changes within {pair_id}")
    flips = sum(
        1
        for pair_rows in by_pair.values()
        if str(pair_rows[0]["subtype"]) == "asymmetric_envelope_exit"
        and {str(row["target_decision"]) for row in pair_rows} == {"deploy_A", "deploy_B"}
    )
    if flips != C2_PAIRS_PER_SUBTYPE:
        raise ValueError(f"asymmetric C2 sub-type produced {flips} ordering flips")
    c5_targets = Counter(
        str(row["target_decision"]) for row in rows if row["stratum"] == "c5_utility"
    )
    if c5_targets["defer"] < 0.15 * sum(c5_targets.values()):
        raise ValueError(f"C5 deferral share is too small: {c5_targets}")


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
    strata_targets = {
        stratum: dict(
            Counter(
                str(row["target_decision"]) for row in rows if row["stratum"] == stratum
            )
        )
        for stratum in ("probe_competence", "c2_capability", "c5_utility")
    }
    summary = {
        "schema_version": "controlled-claim-audit-summary-v2",
        "seed": SEED,
        "items": len(rows),
        "pairs": len({row["pair_id"] for row in rows}),
        "strata": dict(Counter(str(row["stratum"]) for row in rows)),
        "subtypes": dict(Counter(str(row["subtype"]) for row in rows)),
        "template_families": dict(Counter(str(row["template_family"]) for row in rows)),
        "target_decisions": dict(Counter(str(row["target_decision"]) for row in rows)),
        "target_decisions_by_stratum": strata_targets,
        "benchmark_sha256": sha256_text(payload),
        "target_definition": "unique minimum of the displayed deployment-loss rule",
        "minimum_margin": MIN_MARGIN,
        "design_changes_from_v1": [
            "c5_utility deferral price is exogenous and optimal on a designed share of items",
            "c2_capability adds an asymmetric sub-type in which only one system leaves its envelope",
            "probe_competence stratum displays all three action losses and defines the validity gate",
        ],
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
        args.output.write_text(payload, encoding="utf-8")
        args.summary.write_text(summary_text, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "check": args.check,
                "items": summary["items"],
                "pairs": summary["pairs"],
                "strata": summary["strata"],
                "target_decisions_by_stratum": strata_targets,
                "sha256": summary["benchmark_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
