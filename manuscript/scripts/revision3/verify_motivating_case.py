#!/usr/bin/env python3
"""Pin the motivating case to exact source locations.

The opening asserts that the corpus-poisoning figures are "on the same dataset
and the same retriever" as PoisonedRAG's.  Zhong et al. report across several
retrievers, corpora and budgets, so the sentence carries rhetorical weight that
its citation does not discharge.  This verifier re-opens both source texts and
checks, numeral by numeral, that each quantity the introduction prints occurs at
the line range the manuscript cites and under the conditions it states.  It
fails loudly if any does not.

Every check is a triple: a claimed value, the file and line range where the
manuscript says it lives, and the qualifying condition the manuscript attaches
to it.  The condition is checked as a set of strings that must occur in a
declared neighbourhood of the value.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"
SUPPLEMENT = REPO / "manuscript" / "supplement"

CHECKS = [
    {
        "id": "corpus_poisoning_84_2",
        "file": "poisoningRetrievalCorpora2023.txt",
        "value": "84.2",
        "lines": [366, 372],
        "conditions": ["NQ", "Contriever"],
        "condition_window": [344, 372],
        "manuscript_statement": (
            "Corpus poisoning places an adversarial passage in the top-20 for "
            "84.2% of NQ queries with a single adversarial passage, using the "
            "pre-trained Contriever retriever."
        ),
    },
    {
        "id": "corpus_poisoning_99_4",
        "file": "poisoningRetrievalCorpora2023.txt",
        "value": "99.4",
        "lines": [366, 372],
        "conditions": ["NQ", "Contriever"],
        "condition_window": [344, 372],
        "manuscript_statement": (
            "The same setting reaches 99.4% with fifty adversarial passages."
        ),
    },
    {
        "id": "corpus_poisoning_metric_is_topk_retrieval",
        "file": "poisoningRetrievalCorpora2023.txt",
        "value": "percentage of queries for which at least one adver-",
        "lines": [333, 337],
        "conditions": ["top-k"],
        "condition_window": [330, 340],
        "manuscript_statement": (
            "Its success metric is retrieval, not answer manipulation: the "
            "percentage of queries for which at least one adversarial passage "
            "is retrieved in the top-k results."
        ),
    },
    {
        "id": "corpus_poisoning_topk_is_20",
        "file": "poisoningRetrievalCorpora2023.txt",
        "value": "top-20",
        "lines": [466, 470],
        "conditions": ["success rate"],
        "condition_window": [466, 472],
        "manuscript_statement": "The reported operating point is top-20.",
    },
    {
        "id": "poisonedrag_baseline_0_01",
        "file": "poisonedRAG2024.txt",
        "value": "0.01",
        "lines": [1061, 1064],
        "conditions": ["Corpus Poisoning Attack", "NQ"],
        "condition_window": [1060, 1066],
        "manuscript_statement": (
            "PoisonedRAG's Table 4 records the Corpus Poisoning Attack at 0.01 "
            "ASR on NQ."
        ),
    },
    {
        "id": "poisonedrag_default_retriever_and_topk",
        "file": "poisonedRAG2024.txt",
        "value": "Contriever retriever",
        "lines": [681, 684],
        "conditions": ["NQ knowledge database", "5 most similar texts"],
        "condition_window": [680, 685],
        "manuscript_statement": (
            "PoisonedRAG's default setting is the NQ knowledge database, the "
            "Contriever retriever and five retrieved texts, so the two figures "
            "share a corpus and a retriever but not a retrieved-set size."
        ),
    },
    {
        "id": "poisonedrag_says_baseline_cannot_satisfy_generation",
        "file": "poisonedRAG2024.txt",
        "value": "are ineffective because they cannot achieve generation,",
        "lines": [1338, 1341],
        "conditions": ["Corpus Poisoning Attack", "respectively"],
        "condition_window": [1337, 1341],
        "manuscript_statement": (
            "PoisonedRAG itself states that Naive Attack, Corpus Poisoning "
            "Attack and GCG Attack \"are ineffective because they cannot "
            "achieve generation, generation, and retrieval condition, "
            "respectively\", so the condition the corpus-poisoning baseline "
            "fails is generation."
        ),
    },
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=SUPPLEMENT / "motivating_case_verification.json")
    ap.add_argument("--slack", type=int, default=6, help="lines of slack around a cited range")
    args = ap.parse_args()

    results = []
    failures = 0
    for check in CHECKS:
        path = TEXT_DIR / check["file"]
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lo, hi = check["lines"]
        span = "\n".join(lines[max(0, lo - 1 - args.slack) : hi + args.slack])
        clo, chi = check["condition_window"]
        cond_span = "\n".join(lines[max(0, clo - 1 - args.slack) : chi + args.slack])
        value_found = check["value"] in span
        missing = [c for c in check["conditions"] if c not in cond_span]
        ok = value_found and not missing
        failures += 0 if ok else 1
        results.append(
            {
                "id": check["id"],
                "file": check["file"],
                "cited_lines": check["lines"],
                "value": check["value"],
                "value_located": value_found,
                "conditions_required": check["conditions"],
                "conditions_missing": missing,
                "passed": ok,
                "manuscript_statement": check["manuscript_statement"],
            }
        )

    payload = {
        "schema_version": 1,
        "n_checks": len(CHECKS),
        "n_passed": len(CHECKS) - failures,
        "n_failed": failures,
        "checks": results,
        "note": (
            "The two attacks share the NQ corpus and the pre-trained Contriever "
            "retriever. They do not share the retrieved-set size (top-20 for "
            "the retrieval metric, five retrieved texts in PoisonedRAG's "
            "default), the counted event (a passage entering the retrieved set "
            "versus a target question answered with the attacker's answer), or "
            "the unit (percentage of queries versus fraction of target "
            "questions). The introduction now states each of these inline."
        ),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in results:
        flag = "PASS" if row["passed"] else "FAIL"
        print(f"[{flag}] {row['id']}: {row['file']} {row['cited_lines']} "
              f"value={row['value_located']} missing={row['conditions_missing']}")
    print(f"{payload['n_passed']}/{payload['n_checks']} motivating-case checks pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
