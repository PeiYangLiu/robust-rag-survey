#!/usr/bin/env python3
"""Build small validation pilots for the Robust RAG scoping survey.

The pilots are deliberately small and transparent:
1. A synthetic action-trace scoring pilot showing why answer-only scoring can
   hide wrong control decisions.
2. A pairwise comparability pilot derived from two independent human coding
   sources, testing whether the decision procedure yields stable comparable /
   non-comparable judgments.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPP = ROOT / "supplement"
HUMAN = ROOT / "human_coding" / "human_round2_evidence274_results"


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def kappa(pairs: list[tuple[str, str]]) -> dict[str, float | int | None]:
    n = len(pairs)
    agree = sum(a == b for a, b in pairs)
    po = agree / n if n else 0.0
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[x] / n) * (cb[x] / n) for x in set(ca) | set(cb)) if n else 0.0
    return {
        "n": n,
        "agreement": po,
        "kappa": None if math.isclose(pe, 1.0) else (po - pe) / (1 - pe),
    }


def build_action_trace_pilot() -> None:
    """Create a small synthetic pilot and score simple policies.

    This does not claim to be a benchmark release. It demonstrates that
    answer-only scoring and action-aware scoring diagnose different failures.
    """

    items = [
        ("N1", "benign_hard_negative", "support_present+distractor_ranked_first", "answer", "filter", "answer_supported", "A"),
        ("N2", "benign_hard_negative", "support_present+distractor_ranked_first", "answer", "rerank", "answer_supported", "B"),
        ("N3", "distractor_only", "no_support+plausible_distractor", "abstain", "detect_insufficient", "no_answer", "C"),
        ("N4", "distractor_only", "no_support+plausible_distractor", "abstain", "retrieve_more", "no_answer", "D"),
        ("C1", "retrieved_conflict", "two_sources_conflict", "expose_conflict", "compare_sources", "qualified_answer", "E"),
        ("C2", "retrieved_conflict", "parametric_vs_retrieved_conflict", "verify", "compare_internal_external", "qualified_answer", "F"),
        ("U1", "insufficient_context", "related_but_missing_answer_span", "reretrieve", "detect_insufficient", "no_answer", "G"),
        ("U2", "ambiguous_query", "multiple_possible_intents", "clarify", "ask_user", "no_answer", "H"),
        ("A1", "poisoned_evidence", "malicious_doc_retrieved", "abstain", "detect_poison", "safe_refusal", "I"),
        ("A2", "poisoned_evidence", "malicious_doc_retrieved_with_support_like_text", "quarantine", "trace_document", "safe_refusal", "J"),
        ("F1", "faithfulness_gap", "support_present_but_wrong_citation", "answer", "verify_citation", "answer_supported", "K"),
        ("F2", "faithfulness_gap", "answer_correct_but_no_support_span", "abstain", "verify_support", "no_answer", "L"),
    ]
    item_rows = [
        {
            "item_id": item_id,
            "failure_type": failure,
            "evidence_state": evidence,
            "gold_action": action,
            "gold_intermediate_step": step,
            "gold_answer_state": answer_state,
            "gold_answer": answer,
        }
        for item_id, failure, evidence, action, step, answer_state, answer in items
    ]

    policies = {
        "answer_only": lambda row: ("answer", "none", row["gold_answer"] if row["gold_answer_state"] == "answer_supported" else "hallucinated_answer"),
        "abstain_on_missing": lambda row: (
            ("abstain" if row["gold_answer_state"] == "no_answer" else "answer"),
            ("detect_insufficient" if row["gold_answer_state"] == "no_answer" else "none"),
            ("" if row["gold_answer_state"] == "no_answer" else row["gold_answer"]),
        ),
        "evidence_action_oracle": lambda row: (row["gold_action"], row["gold_intermediate_step"], row["gold_answer"] if row["gold_answer_state"] == "answer_supported" else ""),
    }

    pred_rows = []
    summary_rows = []
    for policy_name, policy in policies.items():
        answer_correct = 0
        action_correct = 0
        joint_correct = 0
        for row in item_rows:
            pred_action, pred_step, pred_answer = policy(row)
            ans_ok = (row["gold_answer_state"] == "answer_supported" and pred_answer == row["gold_answer"]) or (
                row["gold_answer_state"] != "answer_supported" and pred_answer == ""
            )
            action_ok = pred_action == row["gold_action"]
            joint_ok = ans_ok and action_ok
            answer_correct += int(ans_ok)
            action_correct += int(action_ok)
            joint_correct += int(joint_ok)
            pred_rows.append(
                {
                    **row,
                    "policy": policy_name,
                    "pred_action": pred_action,
                    "pred_intermediate_step": pred_step,
                    "pred_answer": pred_answer,
                    "answer_correct": int(ans_ok),
                    "action_correct": int(action_ok),
                    "joint_correct": int(joint_ok),
                }
            )
        n = len(item_rows)
        summary_rows.append(
            {
                "policy": policy_name,
                "n": n,
                "answer_accuracy": answer_correct / n,
                "action_accuracy": action_correct / n,
                "joint_answer_action_accuracy": joint_correct / n,
            }
        )

    write_csv(SUPP / "action_trace_pilot_items.csv", item_rows, list(item_rows[0].keys()))
    write_csv(SUPP / "action_trace_pilot_predictions.csv", pred_rows, list(pred_rows[0].keys()))
    write_csv(SUPP / "action_trace_pilot_summary.csv", summary_rows, list(summary_rows[0].keys()))


def read_human(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def comparable(row_a: dict[str, str], row_b: dict[str, str]) -> str:
    fields = ["primary_failure_type", "intervention_point", "evaluation_type"]
    return "comparable" if all(row_a.get(f, "") == row_b.get(f, "") for f in fields) else "not_comparable"


def build_comparability_pilot() -> None:
    src1 = read_human(HUMAN / "source_01_annotations.csv")
    src2 = read_human(HUMAN / "source_02_annotations.csv")
    by1 = {r["paper_id"]: r for r in src1}
    by2 = {r["paper_id"]: r for r in src2}
    ids = [r["paper_id"] for r in src1]

    comparable_pairs = []
    near_miss_pairs = []
    random_non_pairs = []
    for a, b in itertools.combinations(ids, 2):
        c1 = comparable(by1[a], by1[b])
        if c1 == "comparable":
            comparable_pairs.append((a, b))
        elif by1[a].get("primary_failure_type") == by1[b].get("primary_failure_type"):
            near_miss_pairs.append((a, b))
        else:
            random_non_pairs.append((a, b))
    selected = comparable_pairs[:25] + near_miss_pairs[:25] + random_non_pairs[:25]
    rows = []
    pairs_for_kappa = []
    for idx, (a, b) in enumerate(selected, start=1):
        s1 = comparable(by1[a], by1[b])
        s2 = comparable(by2[a], by2[b])
        pairs_for_kappa.append((s1, s2))
        rows.append(
            {
                "pair_id": f"P{idx:03d}",
                "paper_a": a,
                "paper_b": b,
                "title_a": by1[a].get("title", ""),
                "title_b": by1[b].get("title", ""),
                "source_01_decision": s1,
                "source_02_decision": s2,
                "source_01_failure_pair": f"{by1[a].get('primary_failure_type')} / {by1[b].get('primary_failure_type')}",
                "source_01_intervention_pair": f"{by1[a].get('intervention_point')} / {by1[b].get('intervention_point')}",
                "source_01_evaluation_pair": f"{by1[a].get('evaluation_type')} / {by1[b].get('evaluation_type')}",
            }
        )
    summary = kappa(pairs_for_kappa)
    summary["n_comparable_by_source_01"] = sum(1 for a, _ in pairs_for_kappa if a == "comparable")
    summary["n_comparable_by_source_02"] = sum(1 for _, b in pairs_for_kappa if b == "comparable")

    write_csv(SUPP / "comparability_decision_pilot.csv", rows, list(rows[0].keys()))
    with (SUPP / "comparability_decision_pilot_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


def main() -> None:
    build_action_trace_pilot()
    build_comparability_pilot()
    print("wrote action-trace and comparability pilot artifacts")


if __name__ == "__main__":
    main()
