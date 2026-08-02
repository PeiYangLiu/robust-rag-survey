#!/usr/bin/env python3
"""Build a comparability benchmark whose verdict is known by construction.

Why this exists.  The manuscript's claim about the five coordinates -- that
they are disclosure fields rather than a score -- previously rested on a small
purposive human annotation whose provenance we could not audit, and which is
withdrawn.  It also rested on a comparison against a majority-class baseline
that is not identified on eighty items.  This benchmark replaces both with an
instrument test that needs no annotation at all, because every coordinate value
and every verdict is fixed when the passage is written.

Construction.  Each item is a short synthetic excerpt from an imaginary paper:
a setup paragraph that describes how each side was evaluated, and a results
paragraph that places two numbers beside each other.  Behind the excerpt is a
specification that fixes, for the four *threatening* coordinates C1, C2, C4 and
C5, whether the two sides agree, and whether the excerpt discloses the fact at
all.  C3 is recorded but never threatening: comparing two different systems
means the intervention differs, so a C3 mismatch is the normal state of a
comparison and cannot by itself make one undefined.

Ground truth follows the manuscript's decision rule applied to what the text
states, which is the only thing a reader has:

  survives  the excerpt establishes that C1, C2, C4 and C5 all agree;
  narrows   the excerpt states a threatening disagreement *and* reports the
            other side's value at the matched operating point;
  undefined the excerpt states an unrepaired threatening disagreement, or is
            silent about a coordinate a reader would need in order to affirm
            comparability.

Two disclosure regimes are crossed with this.  In ``full`` every coordinate is
stated, so a reader who can code the schema can reach the right verdict.  In
``partial`` a designed subset of coordinates is withheld exactly as real papers
withhold them, so the correct coordinate label is ``not_determinable`` and the
correct verdict is ``undefined``.  The contrast between the two regimes
separates ``the schema cannot be coded'' from ``papers do not state what the
schema asks for'', which observational agreement statistics cannot do.

Verdict classes are balanced by construction, so the strongest constant
baseline scores exactly 1/3 and no result below depends on prevalence.

Writes ``supplement/comparability_instrument_benchmark.jsonl`` and a summary.
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
SEED = 2026073110
SCHEMA_VERSION = "comparability-instrument-v1"

N_SURVIVES = 120
N_NARROWS = 120
N_UNDEFINED_STATED = 60
N_UNDEFINED_SILENT = 60

THREATENING = ("c1", "c2", "c4", "c5")

DOMAINS = {
    "noise": {
        "systems": ["NoiseGuard", "DistractFilter", "ContextSieve", "RelevanceGate",
                    "PassageTrim", "EvidenceSort"],
        "datasets": ["NaturalQuestions", "TriviaQA", "PopQA", "HotpotQA", "WebQ"],
        "retrievers": ["Contriever", "BM25", "DPR", "GTR-base", "E5-large"],
        "metrics": [
            ("exact match", "exact-match accuracy over questions"),
            ("substring accuracy", "substring-match accuracy over questions"),
            ("F1 over answer spans", "token F1 computed per answer span"),
        ],
        "conditions": [
            ("a noise ratio of {r}", "{r} of the retrieved passages are distractors"),
            ("{k} retrieved passages of which {d} are irrelevant",
             "{d} of the {k} retrieved passages are irrelevant"),
        ],
    },
    "security": {
        "systems": ["PoisonShield", "InjectGuard", "CorpusWard", "PromptFence",
                    "PassageAudit", "AdvScreen"],
        "datasets": ["NaturalQuestions", "MS-MARCO", "HotpotQA", "BoolQ"],
        "retrievers": ["Contriever", "BM25", "DPR", "ANCE"],
        "metrics": [
            ("attack success rate over target questions",
             "the fraction of target questions answered with the attacker's chosen answer"),
            ("retrieval hit rate", "the percentage of queries for which at least one "
             "adversarial passage appears in the retrieved set"),
            ("certified accuracy", "accuracy provable under the stated corruption bound"),
        ],
        "conditions": [
            ("{n} malicious texts injected into the corpus per target question",
             "{n} malicious texts are written into the corpus for each target question"),
            ("{n} malicious passages present in the retrieved context",
             "{n} of the passages placed in the context are malicious"),
        ],
    },
    "faithfulness": {
        "systems": ["CiteCheck", "SupportScan", "GroundTrace", "AttributeNet",
                    "ClaimBind", "SourceLock"],
        "datasets": ["RAGTruth-QA", "ASQA", "ELI5-attrib", "FactScore-bio"],
        "retrievers": ["Contriever", "BM25", "GTR-base"],
        "metrics": [
            ("claim-level support rate", "the share of extracted claims supported by a cited passage"),
            ("response-level hallucination rate", "the share of responses containing at least one unsupported claim"),
            ("citation precision", "the share of citations that entail the sentence they attach to"),
        ],
        "conditions": [
            ("a conflicting-evidence rate of {r}", "{r} of the retrieved passages contradict the gold source"),
            ("{k} retrieved passages with a gold passage always present",
             "a gold passage is present among the {k} retrieved passages on every question"),
            ("{k} retrieved passages with no gold passage available",
             "no gold passage exists in the index for these questions"),
        ],
    },
    "calibration": {
        "systems": ["AbstainRAG", "DeferNet", "RiskGate", "SelectiveQA",
                    "ConfRoute", "CoverGuard"],
        "datasets": ["NaturalQuestions", "PopQA", "TriviaQA", "MedQA-sub"],
        "retrievers": ["Contriever", "BM25", "E5-large"],
        "metrics": [
            ("selective risk at 50% coverage", "error rate on the half of questions the system answers"),
            ("accuracy over answered questions", "accuracy computed only where the system chose to answer"),
            ("expected calibration error", "the gap between confidence and accuracy, binned"),
        ],
        "conditions": [
            ("an insufficient-context rate of {r}", "{r} of the questions have no sufficient evidence in the index"),
            ("{k} retrieved passages under a fixed index snapshot",
             "the index snapshot is held fixed and {k} passages are retrieved"),
        ],
    },
}

ACTION_SETS = [
    ("answer or abstain", "an abstention is priced at one third of a wrong answer"),
    ("answer only", "the system must answer every question and abstention is not permitted"),
    ("answer, abstain or escalate to a further retrieval round",
     "an escalation costs one further retrieval round and abstention is free"),
    ("answer or quarantine the retrieved passage",
     "quarantining a passage costs a manual review"),
]

ORIGINS = [
    ("benign retrieval error", "the distracting passages are the ones the retriever "
     "actually returns, with no adversary involved"),
    ("a constructed stressor", "the distracting passages are inserted by the "
     "evaluation harness rather than returned by the retriever"),
    ("an adversary with corpus write access",
     "the adversary may write passages into the corpus but cannot see the generator"),
    ("an adversary with query access and retriever knowledge",
     "the adversary knows the retriever's embedding model and may probe it with queries"),
]

REPAIR_TEMPLATES = [
    "{b}'s own paper additionally reports {v} at the operating point we use "
    "for {a}, and that is the value we compare against.",
    "Reading {b} at our own configuration instead, its paper gives {v}, which "
    "is the number the comparison should use.",
    "{b} also publishes {v} under exactly the setting {a} is evaluated in.",
    "At the matched setting, {b}'s reported figure is {v}.",
]

DECOY_TEMPLATES = [
    "{b}'s own paper also reports {v}, measured under its own configuration.",
    "For completeness, {v} is the other figure {b} publishes for {ds}.",
    "{b} reports {v} elsewhere in its evaluation, under settings of its own "
    "choosing.",
    "A second figure of {v} appears in {b}'s paper for a different "
    "configuration.",
]

INTROS = [
    "We evaluate {a} on {ds}.",
    "Our experiments use {ds} throughout.",
    "This section reports results for {a} on {ds}.",
    "{a} is evaluated on {ds} under the setting described below.",
]

COMPARE = [
    "{a} reaches {va} on {ds}, against {vb} reported for {b}.",
    "On {ds}, {a} obtains {va} while {b} is reported at {vb}.",
    "Table 3 places {a} at {va} beside {b} at {vb}.",
    "{a} improves over {b}, {va} against {vb}.",
]


def fmt_value(metric: str, rng: random.Random) -> str:
    if "rate" in metric or "accuracy" in metric or "precision" in metric:
        return f"{rng.uniform(20, 95):.1f}%"
    if "risk" in metric or "error" in metric:
        return f"{rng.uniform(0.05, 0.45):.2f}"
    return f"{rng.uniform(20, 95):.1f}"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_item(index: int, spec: dict, rng: random.Random) -> dict:
    domain = spec["domain"]
    cfg = DOMAINS[domain]
    a, b = rng.sample(cfg["systems"], 2)
    ds_a = rng.choice(cfg["datasets"])
    ds_b = ds_a if spec["c1"] == "match" else rng.choice(
        [d for d in cfg["datasets"] if d != ds_a]
    )
    ret_a = rng.choice(cfg["retrievers"])
    ret_b = ret_a if spec["c1"] == "match" else rng.choice(
        [r for r in cfg["retrievers"] if r != ret_a]
    )
    cond_a = rng.choice(cfg["conditions"])
    cond_b = cond_a if spec["c1"] == "match" else rng.choice(
        [c for c in cfg["conditions"] if c != cond_a]
    )
    k_a, k_b = rng.choice([5, 10, 20]), rng.choice([5, 10, 20])
    if spec["c1"] == "match":
        k_b = k_a
    n_a, n_b = rng.choice([1, 3, 5]), rng.choice([1, 3, 5])
    r_a, r_b = rng.choice(["0.2", "0.4", "0.6", "0.8"]), rng.choice(["0.2", "0.4", "0.6", "0.8"])
    if spec["c1"] == "match":
        n_b, r_b = n_a, r_a

    def cond_text(cond, k, n, r):
        return cond[1].format(k=k, n=n, r=r, d=max(1, k // 2))

    met_a = rng.choice(cfg["metrics"])
    met_b = met_a if spec["c4"] == "match" else rng.choice(
        [m for m in cfg["metrics"] if m != met_a]
    )
    org_a = rng.choice(ORIGINS)
    org_b = org_a if spec["c2"] == "match" else rng.choice(
        [o for o in ORIGINS if o != org_a]
    )
    act_a = rng.choice(ACTION_SETS)
    act_b = act_a if spec["c5"] == "match" else rng.choice(
        [x for x in ACTION_SETS if x != act_a]
    )
    va, vb = fmt_value(met_a[0], rng), fmt_value(met_b[0], rng)

    stated = spec["stated"]
    setup = [rng.choice(INTROS).format(a=a, ds=ds_a)]
    if "c1" in stated:
        setup.append(
            f"{a} is evaluated on {ds_a} with the {ret_a} retriever and "
            f"{k_a} retrieved passages, where {cond_text(cond_a, k_a, n_a, r_a)}. "
            f"{b} is evaluated on {ds_b} with the {ret_b} retriever and "
            f"{k_b} retrieved passages, where {cond_text(cond_b, k_b, n_b, r_b)}."
        )
    else:
        setup.append(
            f"{a} is evaluated under our standard retrieval configuration. "
            f"We report {b} as published."
        )
    if "c2" in stated:
        setup.append(
            f"For {a} the condition arises from {org_a[0]}: {org_a[1]}. "
            f"For {b} it arises from {org_b[0]}: {org_b[1]}."
        )
    if "c4" in stated:
        setup.append(
            f"We score {a} by {met_a[0]}, {met_a[1]}. The figure quoted for {b} "
            f"is {met_b[0]}, {met_b[1]}."
        )
    else:
        setup.append(f"Both figures are reported as accuracy on {ds_a}.")
    if "c5" in stated:
        setup.append(
            f"{a} is deployed with the action set {act_a[0]}, where {act_a[1]}. "
            f"{b} is deployed with the action set {act_b[0]}, where {act_b[1]}."
        )
    if "c3" in stated:
        setup.append(
            f"The two systems differ in where they intervene: {a} modifies "
            f"context assembly, whereas {b} modifies the generator's decoding."
            if spec["c3"] == "mismatch"
            else f"Both {a} and {b} intervene at context assembly; they differ "
            f"only in the scoring function used there."
        )

    focus = [rng.choice(COMPARE).format(a=a, b=b, ds=ds_a, va=va, vb=vb)]
    # A second number from the other paper appears on most items whatever the
    # verdict, so its presence is not a cue.  What differs is whether it is
    # reported *at the operating point this paper uses*, which is the only
    # thing that repairs a disagreement.
    if spec["repair"]:
        matched = fmt_value(met_a[0], rng)
        focus.append(
            rng.choice(REPAIR_TEMPLATES).format(a=a, b=b, v=matched, ds=ds_a)
        )
        spec = dict(spec, matched_number=matched)
    else:
        spec = dict(spec, matched_number="")
        if spec.get("decoy"):
            decoy = fmt_value(met_b[0], rng)
            focus.append(rng.choice(DECOY_TEMPLATES).format(a=a, b=b, v=decoy, ds=ds_b))
    focus.append(
        f"We therefore include {b} as the strongest published point of "
        f"reference for {a}."
    )

    body = "\n".join(setup) + "\n\n" + " ".join(focus)
    truth_coords = {}
    for coord in ("c1", "c2", "c3", "c4", "c5"):
        truth_coords[coord] = spec[coord] if coord in stated else "not_determinable"
    return {
        "item_id": f"CMP-{index:04d}",
        "schema_version": SCHEMA_VERSION,
        "domain": domain,
        "disclosure": spec["disclosure"],
        "stated_coordinates": sorted(stated),
        "truth_coordinates": truth_coords,
        "truth_verdict": spec["verdict"],
        "truth_matched_number": spec["matched_number"],
        "side_a": a,
        "side_b": b,
        "focus_text": " ".join(focus),
        "context_text": body,
        "window_sha256": sha(body),
    }


def make_specs(rng: random.Random) -> list[dict]:
    specs = []
    domains = list(DOMAINS)

    def base(i):
        return {"domain": domains[i % len(domains)], "c3": rng.choice(["mismatch"] * 4 + ["match"])}

    # survives: every threatening coordinate agrees and every one is stated
    for i in range(N_SURVIVES):
        s = base(i)
        s.update({c: "match" for c in THREATENING})
        # a matched-operating-point sentence is present on a designed share of
        # these items too, where it changes nothing, so that the sentence is
        # not by itself a signal for "narrows"
        s.update(
            disclosure="full",
            stated={"c1", "c2", "c3", "c4", "c5"},
            repair=(i % 5 < 2),
            decoy=(i % 5 == 2),
            verdict="survives",
        )
        specs.append(s)

    # narrows: at least one threatening coordinate disagrees, and the excerpt
    # reports the other side's value at the matched operating point
    for i in range(N_NARROWS):
        s = base(i)
        # a mismatched outcome unit cannot be repaired by re-reading a number,
        # so only operating-point coordinates break in this stratum
        broken = rng.sample(("c1", "c2", "c5"), rng.choice([1, 1, 1, 2]))
        s.update({c: ("mismatch" if c in broken else "match") for c in THREATENING})
        s.update(
            disclosure="full",
            stated={"c1", "c2", "c3", "c4", "c5"},
            repair=True,
            decoy=False,
            verdict="narrows",
        )
        specs.append(s)

    # undefined, stated: a disagreement is disclosed and nothing repairs it
    for i in range(N_UNDEFINED_STATED):
        s = base(i)
        broken = rng.sample(THREATENING, rng.choice([1, 2, 2, 3]))
        if i % 2 == 0:
            broken = sorted(set(broken) | {"c4"})
        s.update({c: ("mismatch" if c in broken else "match") for c in THREATENING})
        s.update(
            disclosure="full",
            stated={"c1", "c2", "c3", "c4", "c5"},
            repair=False,
            decoy=(i % 3 != 2),
            verdict="undefined",
        )
        specs.append(s)

    # undefined, silent: the excerpt withholds a coordinate a reader needs
    for i in range(N_UNDEFINED_SILENT):
        s = base(i)
        withheld = set(rng.sample(THREATENING, rng.choice([1, 1, 2])))
        s.update({c: rng.choice(["match", "mismatch"]) for c in THREATENING})
        s.update(
            disclosure="partial",
            stated={"c1", "c2", "c3", "c4", "c5"} - withheld,
            repair=False,
            decoy=(i % 2 == 0),
            verdict="undefined",
        )
        specs.append(s)

    rng.shuffle(specs)
    return specs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=SUP / "comparability_instrument_benchmark.jsonl")
    ap.add_argument(
        "--summary", type=Path, default=SUP / "comparability_instrument_benchmark_summary.json"
    )
    args = ap.parse_args()

    rng = random.Random(SEED)
    specs = make_specs(rng)
    items = [build_item(i, s, rng) for i, s in enumerate(specs)]

    # every verdict must follow from the specification, never from the prose
    for item in items:
        stated = set(item["stated_coordinates"])
        threat_unstated = [c for c in THREATENING if c not in stated]
        if item["truth_verdict"] == "survives":
            assert not threat_unstated
            assert all(item["truth_coordinates"][c] == "match" for c in THREATENING)
        if item["truth_verdict"] == "narrows":
            assert any(item["truth_coordinates"][c] == "mismatch" for c in THREATENING)
            assert item["truth_coordinates"]["c4"] == "match"
            assert item["truth_matched_number"]
        if item["truth_verdict"] == "undefined":
            assert threat_unstated or any(
                item["truth_coordinates"][c] == "mismatch" for c in THREATENING
            )
            assert not item["truth_matched_number"]

    counts = Counter(i["truth_verdict"] for i in items)
    assert len(set(counts.values())) == 1, counts
    with args.output.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, sort_keys=True) + "\n")
    summary = {
        "schema_version": SCHEMA_VERSION,
        "seed": SEED,
        "n_items": len(items),
        "verdict_counts": dict(counts),
        "majority_class_baseline": max(counts.values()) / len(items),
        "disclosure_counts": dict(Counter(i["disclosure"] for i in items)),
        "domain_counts": dict(Counter(i["domain"] for i in items)),
        "repair_sentence_by_verdict": {
            v: sum(1 for i in items if i["truth_verdict"] == v and i["truth_matched_number"])
            for v in ("survives", "narrows", "undefined")
        },
        "coordinate_truth_counts": {
            c: dict(Counter(i["truth_coordinates"][c] for i in items))
            for c in ("c1", "c2", "c3", "c4", "c5")
        },
        "file_sha256": sha(args.output.read_text(encoding="utf-8")),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
