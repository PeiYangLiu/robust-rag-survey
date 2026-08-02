#!/usr/bin/env python3
"""A provenance benchmark whose label is fixed when the item is written (W4).

The reviewer's decisive objection: the paper's title, abstract, contribution (i)
and conclusion all rest on the transported / re-implemented distinction, and
that distinction is validated *only* by inter-judge agreement, on a panel the
paper itself shows is not independent.  Correlated judges can agree on a
systematically wrong label.

This builds the reference the census lacks.  Each item is a short excerpt from
an imaginary paper that places its own result beside a result associated with
another paper's system.  How the other number was obtained is fixed by the
specification, never annotated, so accuracy is measurable without trusting any
rater.

Four reference classes, which are exactly the classes the deployed instrument
can and cannot express:

  reimplemented       the excerpt establishes the other system was run inside
                      this paper's harness;
  transported         the excerpt establishes the number was copied from the
                      other paper;
  unclear             the excerpt is a bare table fragment that carries no
                      information about either, so ``unclear`` is correct and a
                      confident answer is an error;
  asserted_no_number  the excerpt asserts a relation to the other system while
                      supplying no number for its side.  Section 4 of the
                      manuscript introduces this category and the deployed
                      three-option prompt has no way to express it, so the
                      census never counted it.  Including it here measures what
                      the deployed prompt does with it.

Crossed with a difficulty factor, so the benchmark cannot be solved by matching
a declaration phrase:

  explicit   a sentence states how the number was obtained;
  implicit   no such sentence exists and provenance follows only from structure
             -- a number carrying the other paper's own datasets and backbone
             beside a citation, versus the other system scored on a dataset
             this paper introduces, which its original paper could not have
             reported.

Writes ``supplement/provenance_benchmark.jsonl`` and a summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
SEED = 2026080421
SCHEMA_VERSION = "provenance-benchmark-v1"

N_PER_CELL = 40  # transported/reimplemented x explicit/implicit
N_UNCLEAR = 80
N_ASSERTED = 40

OWN = ["EvidenceSort", "PoisonShield", "CiteCheck", "AbstainRAG", "ContextSieve",
       "CorpusWard", "GroundTrace", "RiskGate", "PassageTrim", "InjectGuard"]
OTHER = ["NoiseGuard", "PromptFence", "SupportScan", "DeferNet", "RelevanceGate",
         "AdvScreen", "ClaimBind", "ConfRoute", "DistractFilter", "SourceLock"]
CITES = ["Alvarez et al. (2023)", "Bhatt and Ono (2024)", "Cardoso et al. (2022)",
         "Doan et al. (2024)", "Esposito and Reyes (2023)", "Farkas et al. (2025)",
         "Gupta and Lindqvist (2024)", "Haddad et al. (2023)"]
DATASETS = ["NaturalQuestions", "TriviaQA", "PopQA", "HotpotQA", "MS-MARCO", "BoolQ"]
NEW_BENCH = ["StressQA", "DriftBench", "ConflictSet", "NoiseProbe", "PoisonSuite"]
RETRIEVERS = ["Contriever", "BM25", "DPR", "GTR-base", "E5-large", "ANCE"]
BACKBONES = ["Llama-3-8B", "Mistral-7B", "Qwen2-7B", "GPT-4o-mini", "Vicuna-13B"]
METRICS = ["exact match", "substring accuracy", "attack success rate",
           "claim support rate", "selective risk"]

FILLER = [
    "All runs use greedy decoding.",
    "Hyperparameters are listed in Appendix A.",
    "We average over three random seeds.",
    "Statistical tests use a paired bootstrap.",
    "The index is rebuilt once per configuration.",
]

DECL_REIMPL = [
    "We re-run {o} with the authors' released code inside our own pipeline.",
    "All baselines, including {o}, are re-implemented and evaluated under our setup.",
    "We reproduce {o} on our corpus so that every row shares one retriever and one generator.",
    "{o} is evaluated here by us, using the released checkpoint, under the configuration of Section 3.",
]

DECL_TRANS = [
    "Numbers for {o} are taken from {c} and are not re-measured here.",
    "We cite the result reported by {c} for {o} rather than re-running it.",
    "The {o} entry is quoted from the original paper, {c}.",
    "Baseline figures are copied from the respective papers; {o} follows {c}.",
]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def val(rng):
    return f"{rng.uniform(15, 95):.1f}"


def build(index: int, spec: dict, rng: random.Random) -> dict:
    a, o = rng.choice(OWN), rng.choice(OTHER)
    c = rng.choice(CITES)
    ds, ds2 = rng.sample(DATASETS, 2)
    nb = rng.choice(NEW_BENCH)
    ret, ret2 = rng.sample(RETRIEVERS, 2)
    bb, bb2 = rng.sample(BACKBONES, 2)
    met = rng.choice(METRICS)
    va, vb = val(rng), val(rng)
    kind, mode = spec["truth"], spec["explicitness"]
    lines = []

    if kind == "reimplemented":
        if mode == "explicit":
            lines += [
                f"Section 4.2 reports {met} on {ds} with the {ret} retriever and a {bb} generator.",
                rng.choice(DECL_REIMPL).format(o=o, c=c),
                f"Table 2 places {a} at {va} beside {o} at {vb}.",
            ]
        else:
            # the other system is scored on a benchmark this paper introduces,
            # so its original paper cannot be the source of the number
            lines += [
                f"We introduce {nb}, a benchmark of stressed retrieval conditions "
                f"released with this paper.",
                f"Every system in Table 2 is scored on {nb} with the {ret} retriever "
                f"and a {bb} generator, holding the prompt fixed.",
                f"{a} reaches {va} and {o} [{c}] reaches {vb} in {met}.",
            ]
    elif kind == "transported":
        if mode == "explicit":
            lines += [
                f"Our own results use {ds} with {ret} and a {bb} generator.",
                rng.choice(DECL_TRANS).format(o=o, c=c),
                f"Table 2 places {a} at {va} beside {o} at {vb}.",
            ]
        else:
            # the other number carries the other paper's own coordinates, which
            # this paper never runs
            lines += [
                f"Throughout, {a} is evaluated on {ds} with {ret} and a {bb} generator.",
                f"{c} evaluate {o} on {ds2} with {ret2} and a {bb2} generator and "
                f"obtain {vb} {met}; we place that figure beside our {va}.",
                f"We did not have access to the {ds2} split used there.",
            ]
    elif kind == "unclear":
        # a bare table fragment: names, numbers, a citation marker, nothing else
        lines += [
            f"{met.title()}",
            f"{o} [{c}] {vb}",
            f"{a} (ours) {va}",
            f"Table 2: Results on {ds}.",
        ]
    else:  # asserted_no_number
        lines += [
            f"Our own evaluation of {a} on {ds} with {ret} gives {va} {met}.",
            f"{a} shows strong robustness against the attack of {c}, reducing "
            f"attack success rates from over 90% to approximately 10%.",
            f"No comparable figure for {o} at our operating point is available.",
        ]

    if spec.get("filler"):
        lines.insert(rng.randrange(1, len(lines)), rng.choice(FILLER))
    body = "\n".join(lines)
    return {
        "item_id": f"PROV-{index:04d}",
        "schema_version": SCHEMA_VERSION,
        "truth_provenance": kind,
        "explicitness": mode,
        "side_own": a,
        "side_other": o,
        "focus_text": body,
        "context_text": body,
        "window_sha256": sha(body),
    }


def make_specs(rng: random.Random) -> list[dict]:
    specs = []
    for kind in ("reimplemented", "transported"):
        for mode in ("explicit", "implicit"):
            for i in range(N_PER_CELL):
                specs.append({"truth": kind, "explicitness": mode,
                              "filler": i % 2 == 0})
    for i in range(N_UNCLEAR):
        specs.append({"truth": "unclear", "explicitness": "none",
                      "filler": i % 2 == 0})
    for i in range(N_ASSERTED):
        specs.append({"truth": "asserted_no_number", "explicitness": "none",
                      "filler": i % 2 == 0})
    rng.shuffle(specs)
    return specs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=SUP / "provenance_benchmark.jsonl")
    ap.add_argument("--summary", type=Path,
                    default=SUP / "provenance_benchmark_summary.json")
    args = ap.parse_args()

    rng = random.Random(SEED)
    specs = make_specs(rng)
    items = [build(i, s, rng) for i, s in enumerate(specs)]

    three_way = [i for i in items
                 if i["truth_provenance"] in ("reimplemented", "transported", "unclear")]
    counts3 = Counter(i["truth_provenance"] for i in three_way)
    assert len(set(counts3.values())) == 1, counts3

    with args.output.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, sort_keys=True) + "\n")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "seed": SEED,
        "n_items": len(items),
        "truth_counts": dict(Counter(i["truth_provenance"] for i in items)),
        "explicitness_counts": dict(Counter(i["explicitness"] for i in items)),
        "three_way_scorable_items": len(three_way),
        "three_way_constant_baseline": max(counts3.values()) / len(three_way),
        "note": (
            "The deployed census prompt offers three options, so accuracy is "
            "scored on the three-way subset whose classes are balanced by "
            "construction. The asserted_no_number stratum is reported "
            "separately: it is the category the manuscript names in Section 4 "
            "and the deployed prompt cannot express."),
        "file_sha256": sha(args.output.read_text(encoding="utf-8")),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
