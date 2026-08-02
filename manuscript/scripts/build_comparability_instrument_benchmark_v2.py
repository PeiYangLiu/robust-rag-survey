#!/usr/bin/env python3
"""Build the redesigned comparability benchmark (reviewer W1, W2, W7).

Why a v2.  The v1 benchmark crossed disclosure with the reference verdict in a
way that made the withheld arm uninterpretable: *every* withheld item had
reference verdict ``undefined``, because the decision rule maps silence about a
threatening coordinate to ``undefined``.  On that arm the constant predictor
"undefined" scores 1.00, so a judge accuracy of 0.91 is *below* the trivial
baseline, an inter-judge kappa of 0.71 is mostly a measure of how often judges
default, and pooling the degenerate arm into the full arm manufactured the
1/3 constant baseline that the headline was measured against.

v2 fixes both, and adds the factor that the v1 design could not separate.

FACTOR 1 -- disclosure, with three levels instead of two.

  full              every coordinate is stated.  Verdict balanced 1/3 each.

  partial_balanced  a fact is withheld, but the reference verdict is *not*
                    determined by the withholding, so the arm carries all three
                    verdict classes in equal number and its constant baseline
                    is 1/3, exactly as in ``full``:
                      survives   withholds only facts the rule does not consume
                                 (the C3 intervention sentence and an
                                 implementation detail); the four threatening
                                 coordinates are stated and agree.
                      narrows    withholds one threatening coordinate AND
                                 states the other side's value at the matched
                                 operating point for it, which is rule branch 2.
                      undefined  withholds one threatening coordinate AND
                                 discloses an unrepaired mismatch on a
                                 *different* threatening coordinate, so the
                                 verdict is already fixed with the withheld
                                 coordinate restored.
                    The narrows and undefined cells therefore both withhold a
                    threatening coordinate and differ only in the repair, which
                    is the two-class contrast (constant baseline 1/2) that the
                    v1 design could not produce.

  partial_forcing   the v1 manipulation, kept as a declared degenerate control:
                    a threatening coordinate is withheld and nothing repairs
                    it, so ``undefined`` follows from the withholding alone and
                    the constant baseline on this arm is 1.00.

FACTOR 2 -- presentation, which v1 held fixed at its easiest level.

  canonical     one dedicated sentence per coordinate, in a fixed order, in the
                vocabulary of the codebook.
  naturalistic  the same facts, every one of them, but phrased the way papers
                phrase them: indirect constructions, back-references to an
                earlier section, table-caption fragments, and interleaved
                sentences about implementation, related work and hardware that
                carry no coordinate information.  Information content is
                identical by construction -- each canonical fact has exactly one
                naturalistic realisation -- so any drop is a *readability* cost
                and not a disclosure cost.

Every specification is instantiated twice, once at each presentation level, and
the two instances share a ``pair_id``.  Presentation is therefore a paired,
within-specification contrast, and disclosure is a between-specification one
with the verdict balance held fixed.

This lets the manuscript ask the question the v1 design could not: when the
coordinates *are* disclosed but are written the way papers write them, does
adjudication survive?  If it does, disclosure is the binding constraint; if it
does not, disclosure is not by itself the explanation and the manuscript must
say so.

Writes ``supplement/comparability_instrument_benchmark_v2.jsonl`` and a summary.
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
SEED = 2026080401
SCHEMA_VERSION = "comparability-instrument-v2"

# per presentation level
N_FULL_PER_CLASS = 30            # x3 classes = 90
N_PARTIAL_BAL_PER_CLASS = 30     # x3 classes = 90
N_PARTIAL_FORCING = 36           # all undefined, declared degenerate control

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

# Sentences that carry no coordinate information at all.  They exist so that the
# naturalistic level has the density of real prose without changing what a
# careful reader can determine.
FILLER = [
    "All runs use greedy decoding with a maximum of 128 new tokens.",
    "We use eight A100 GPUs and report the mean of three seeds.",
    "Preliminary experiments with a larger beam gave no measurable difference.",
    "Implementation details and prompts are given in Appendix B.",
    "The retrieval index is built once and cached across runs.",
    "We follow the preprocessing pipeline released with the original benchmark.",
    "Related work on this failure mode is surveyed in Section 2.",
    "Full per-dataset breakdowns appear in the supplementary material.",
    "Training took approximately nine hours on a single node.",
    "We release code and configuration files to support replication.",
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

# Statements that a coordinate was deliberately not restated.  These are what a
# withheld coordinate looks like in a real paper: the paper does not announce a
# gap, it simply moves on.
WITHHELD_SURROGATE = {
    "c1": "{a} is evaluated under our standard retrieval configuration, and we "
          "report {b} as published.",
    "c2": "The conditions under which each system was stressed follow each "
          "paper's own protocol.",
    "c4": "Both figures are reported as accuracy on {ds}.",
    "c5": "Deployment settings are as described in the respective papers.",
}


def fmt_value(metric: str, rng: random.Random) -> str:
    if "rate" in metric or "accuracy" in metric or "precision" in metric:
        return f"{rng.uniform(20, 95):.1f}%"
    if "risk" in metric or "error" in metric:
        return f"{rng.uniform(0.05, 0.45):.2f}"
    return f"{rng.uniform(20, 95):.1f}"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def realise(spec: dict, rng: random.Random) -> dict:
    """Draw every surface value a specification needs, once, so that the two
    presentation levels of one specification differ in wording only."""
    domain = spec["domain"]
    cfg = DOMAINS[domain]
    a, b = rng.sample(cfg["systems"], 2)
    ds_a = rng.choice(cfg["datasets"])
    ds_b = ds_a if spec["c1"] == "match" else rng.choice(
        [d for d in cfg["datasets"] if d != ds_a])
    ret_a = rng.choice(cfg["retrievers"])
    ret_b = ret_a if spec["c1"] == "match" else rng.choice(
        [r for r in cfg["retrievers"] if r != ret_a])
    cond_a = rng.choice(cfg["conditions"])
    cond_b = cond_a if spec["c1"] == "match" else rng.choice(
        [c for c in cfg["conditions"] if c != cond_a])
    k_a = rng.choice([5, 10, 20])
    k_b = k_a if spec["c1"] == "match" else rng.choice([x for x in (5, 10, 20) if x != k_a])
    n_a = rng.choice([1, 3, 5])
    n_b = n_a if spec["c1"] == "match" else rng.choice([x for x in (1, 3, 5) if x != n_a])
    r_a = rng.choice(["0.2", "0.4", "0.6", "0.8"])
    r_b = r_a if spec["c1"] == "match" else rng.choice(
        [x for x in ("0.2", "0.4", "0.6", "0.8") if x != r_a])
    met_a = rng.choice(cfg["metrics"])
    met_b = met_a if spec["c4"] == "match" else rng.choice(
        [m for m in cfg["metrics"] if m != met_a])
    org_a = rng.choice(ORIGINS)
    org_b = org_a if spec["c2"] == "match" else rng.choice(
        [o for o in ORIGINS if o != org_a])
    act_a = rng.choice(ACTION_SETS)
    act_b = act_a if spec["c5"] == "match" else rng.choice(
        [x for x in ACTION_SETS if x != act_a])
    return {
        "a": a, "b": b, "ds_a": ds_a, "ds_b": ds_b, "ret_a": ret_a, "ret_b": ret_b,
        "cond_a": cond_a, "cond_b": cond_b, "k_a": k_a, "k_b": k_b, "n_a": n_a,
        "n_b": n_b, "r_a": r_a, "r_b": r_b, "met_a": met_a, "met_b": met_b,
        "org_a": org_a, "org_b": org_b, "act_a": act_a, "act_b": act_b,
        "va": fmt_value(met_a[0], rng), "vb": fmt_value(met_b[0], rng),
        "matched": fmt_value(met_a[0], rng), "decoy": fmt_value(met_b[0], rng),
        "intro": rng.choice(INTROS), "compare": rng.choice(COMPARE),
        "repair_t": rng.choice(REPAIR_TEMPLATES), "decoy_t": rng.choice(DECOY_TEMPLATES),
        "filler": rng.sample(FILLER, 5),
    }


def cond_text(cond, k, n, r):
    return cond[1].format(k=k, n=n, r=r, d=max(1, k // 2))


def canonical_sentences(spec: dict, s: dict) -> dict[str, str]:
    """One dedicated sentence per coordinate, in codebook vocabulary."""
    stated = spec["stated"]
    out = {}
    if "c1" in stated:
        out["c1"] = (
            f"{s['a']} is evaluated on {s['ds_a']} with the {s['ret_a']} retriever and "
            f"{s['k_a']} retrieved passages, where "
            f"{cond_text(s['cond_a'], s['k_a'], s['n_a'], s['r_a'])}. "
            f"{s['b']} is evaluated on {s['ds_b']} with the {s['ret_b']} retriever and "
            f"{s['k_b']} retrieved passages, where "
            f"{cond_text(s['cond_b'], s['k_b'], s['n_b'], s['r_b'])}.")
    if "c2" in stated:
        out["c2"] = (
            f"For {s['a']} the condition arises from {s['org_a'][0]}: {s['org_a'][1]}. "
            f"For {s['b']} it arises from {s['org_b'][0]}: {s['org_b'][1]}.")
    if "c4" in stated:
        out["c4"] = (
            f"We score {s['a']} by {s['met_a'][0]}, {s['met_a'][1]}. The figure quoted "
            f"for {s['b']} is {s['met_b'][0]}, {s['met_b'][1]}.")
    if "c5" in stated:
        out["c5"] = (
            f"{s['a']} is deployed with the action set {s['act_a'][0]}, where "
            f"{s['act_a'][1]}. {s['b']} is deployed with the action set "
            f"{s['act_b'][0]}, where {s['act_b'][1]}.")
    if "c3" in stated:
        out["c3"] = (
            f"The two systems differ in where they intervene: {s['a']} modifies "
            f"context assembly, whereas {s['b']} modifies the generator's decoding."
            if spec["c3"] == "mismatch" else
            f"Both {s['a']} and {s['b']} intervene at context assembly; they differ "
            f"only in the scoring function used there.")
    return out


def naturalistic_sentences(spec: dict, s: dict) -> dict[str, str]:
    """The identical facts, written the way a paper writes them.

    Every fact realised canonically has exactly one realisation here, so the two
    levels are information-equivalent by construction; what changes is that the
    facts are indirect, split across clauses, and no longer announced.
    """
    stated = spec["stated"]
    out = {}
    if "c1" in stated:
        same = spec["c1"] == "match"
        if same:
            out["c1"] = (
                f"Our setup for {s['a']} is the {s['ds_a']} split described in "
                f"Section 3, retrieved with {s['ret_a']} at depth {s['k_a']}; "
                f"{cond_text(s['cond_a'], s['k_a'], s['n_a'], s['r_a'])}. "
                f"We keep that configuration when we turn to {s['b']}.")
        else:
            out["c1"] = (
                f"Our setup for {s['a']} is the {s['ds_a']} split described in "
                f"Section 3, retrieved with {s['ret_a']} at depth {s['k_a']}; "
                f"{cond_text(s['cond_a'], s['k_a'], s['n_a'], s['r_a'])}. "
                f"The {s['b']} column is carried over from a {s['ds_b']} run at "
                f"depth {s['k_b']} using {s['ret_b']}, where "
                f"{cond_text(s['cond_b'], s['k_b'], s['n_b'], s['r_b'])}.")
    if "c2" in stated:
        same = spec["c2"] == "match"
        if same:
            out["c2"] = (
                f"The degradation we study is {s['org_a'][0]} -- {s['org_a'][1]} -- "
                f"and the same threat model governs the {s['b']} row.")
        else:
            out["c2"] = (
                f"The degradation we study is {s['org_a'][0]} -- {s['org_a'][1]}. "
                f"The {s['b']} row was produced under a different regime, "
                f"{s['org_b'][0]}, in which {s['org_b'][1]}.")
    if "c4" in stated:
        same = spec["c4"] == "match"
        if same:
            out["c4"] = (
                f"Unless noted, all figures in this section are {s['met_a'][0]} "
                f"({s['met_a'][1]}), including the {s['b']} entry.")
        else:
            out["c4"] = (
                f"Unless noted, our figures are {s['met_a'][0]} ({s['met_a'][1]}); "
                f"the {s['b']} entry is instead {s['met_b'][0]}, i.e. "
                f"{s['met_b'][1]}.")
    if "c5" in stated:
        same = spec["c5"] == "match"
        if same:
            out["c5"] = (
                f"In deployment {s['a']} may {s['act_a'][0]}, and {s['act_a'][1]}; "
                f"{s['b']} is operated under the same policy and the same prices.")
        else:
            out["c5"] = (
                f"In deployment {s['a']} may {s['act_a'][0]}, and {s['act_a'][1]}. "
                f"{s['b']}, by contrast, was evaluated where the system may "
                f"{s['act_b'][0]} and {s['act_b'][1]}.")
    if "c3" in stated:
        out["c3"] = (
            f"Architecturally the contrast is between our context-assembly stage "
            f"and the decoding-time mechanism {s['b']} uses."
            if spec["c3"] == "mismatch" else
            f"Both methods act at context assembly and differ only in the "
            f"scoring function applied there.")
    return out


def build_item(index: int, pair_id: int, spec: dict, s: dict,
               presentation: str, rng: random.Random) -> dict:
    sents = (canonical_sentences(spec, s) if presentation == "canonical"
             else naturalistic_sentences(spec, s))
    stated = spec["stated"]

    surrogates = []
    for coord in ("c1", "c2", "c4", "c5"):
        if coord not in stated:
            surrogates.append(
                WITHHELD_SURROGATE[coord].format(a=s["a"], b=s["b"], ds=s["ds_a"]))

    setup = [s["intro"].format(a=s["a"], ds=s["ds_a"])]
    ordered = [sents[c] for c in ("c1", "c2", "c4", "c5", "c3") if c in sents]
    if presentation == "canonical":
        setup.extend(ordered)
        setup.extend(surrogates)
    else:
        blocks = ordered + surrogates
        rng.shuffle(blocks)
        # interleave prose that carries no coordinate information
        woven, fillers = [], list(s["filler"])
        for i, blk in enumerate(blocks):
            woven.append(blk)
            if i % 2 == 1 and fillers:
                woven.append(fillers.pop(0))
        if fillers:
            woven.insert(1, fillers.pop(0))
        setup.extend(woven)

    focus = [s["compare"].format(a=s["a"], b=s["b"], ds=s["ds_a"],
                                 va=s["va"], vb=s["vb"])]
    matched_number = ""
    if spec["repair"]:
        matched_number = s["matched"]
        focus.append(s["repair_t"].format(a=s["a"], b=s["b"], v=matched_number,
                                          ds=s["ds_a"]))
    elif spec.get("decoy"):
        focus.append(s["decoy_t"].format(a=s["a"], b=s["b"], v=s["decoy"],
                                         ds=s["ds_b"]))
    focus.append(f"We therefore include {s['b']} as the strongest published "
                 f"point of reference for {s['a']}.")

    body = "\n".join(setup) + "\n\n" + " ".join(focus)
    truth_coords = {c: (spec[c] if c in stated else "not_determinable")
                    for c in ("c1", "c2", "c3", "c4", "c5")}
    return {
        "item_id": f"CMPX-{index:04d}",
        "pair_id": f"SPEC-{pair_id:04d}",
        "schema_version": SCHEMA_VERSION,
        "domain": spec["domain"],
        "presentation": presentation,
        "disclosure": spec["disclosure"],
        "withheld_coordinates": sorted({"c1", "c2", "c3", "c4", "c5"} - set(stated)),
        "withholding_is_decisive": spec["withholding_is_decisive"],
        "verdict_forced_by": spec["verdict_forced_by"],
        "stated_coordinates": sorted(stated),
        "truth_coordinates": truth_coords,
        "truth_verdict": spec["verdict"],
        "truth_matched_number": matched_number,
        "side_a": s["a"],
        "side_b": s["b"],
        "focus_text": " ".join(focus),
        "context_text": body,
        "window_sha256": sha(body),
    }


ALL_COORDS = {"c1", "c2", "c3", "c4", "c5"}


def make_specs(rng: random.Random) -> list[dict]:
    specs, domains = [], list(DOMAINS)

    def base(i):
        return {"domain": domains[i % len(domains)],
                "c3": rng.choice(["mismatch"] * 4 + ["match"])}

    # ---- full disclosure, three balanced classes -------------------------
    for i in range(N_FULL_PER_CLASS):
        s = base(i)
        s.update({c: "match" for c in THREATENING})
        s.update(disclosure="full", stated=set(ALL_COORDS), repair=(i % 5 < 2),
                 decoy=(i % 5 == 2), verdict="survives",
                 withholding_is_decisive=False, verdict_forced_by="all_coordinates_match")
        specs.append(s)
    for i in range(N_FULL_PER_CLASS):
        s = base(i)
        broken = rng.sample(("c1", "c2", "c5"), rng.choice([1, 1, 1, 2]))
        s.update({c: ("mismatch" if c in broken else "match") for c in THREATENING})
        s.update(disclosure="full", stated=set(ALL_COORDS), repair=True, decoy=False,
                 verdict="narrows", withholding_is_decisive=False,
                 verdict_forced_by="disclosed_mismatch_with_repair")
        specs.append(s)
    for i in range(N_FULL_PER_CLASS):
        s = base(i)
        broken = rng.sample(THREATENING, rng.choice([1, 2, 2, 3]))
        if i % 2 == 0:
            broken = sorted(set(broken) | {"c4"})
        s.update({c: ("mismatch" if c in broken else "match") for c in THREATENING})
        s.update(disclosure="full", stated=set(ALL_COORDS), repair=False,
                 decoy=(i % 3 != 2), verdict="undefined",
                 withholding_is_decisive=False,
                 verdict_forced_by="disclosed_mismatch_unrepaired")
        specs.append(s)

    # ---- partial, balanced: withholding does not decide the verdict ------
    # survives: only rule-irrelevant facts are withheld (C3 and filler detail)
    for i in range(N_PARTIAL_BAL_PER_CLASS):
        s = base(i)
        s.update({c: "match" for c in THREATENING})
        s.update(disclosure="partial_balanced", stated=set(ALL_COORDS) - {"c3"},
                 repair=(i % 5 < 2), decoy=(i % 5 == 2), verdict="survives",
                 withholding_is_decisive=False,
                 verdict_forced_by="all_threatening_coordinates_match")
        specs.append(s)
    # narrows: a threatening coordinate is withheld and the repair covers it
    for i in range(N_PARTIAL_BAL_PER_CLASS):
        s = base(i)
        withheld = rng.choice(["c1", "c2", "c5"])
        s.update({c: "match" for c in THREATENING})
        s[withheld] = rng.choice(["match", "mismatch"])
        s.update(disclosure="partial_balanced", stated=set(ALL_COORDS) - {withheld},
                 repair=True, decoy=False, verdict="narrows",
                 withholding_is_decisive=False,
                 verdict_forced_by="withheld_coordinate_repaired_at_matched_point")
        specs.append(s)
    # undefined: a threatening coordinate is withheld AND a *different* one is
    # disclosed as mismatched with no repair, so the verdict is unchanged if the
    # withheld coordinate were restored at either of its values
    for i in range(N_PARTIAL_BAL_PER_CLASS):
        s = base(i)
        withheld = rng.choice(["c1", "c2", "c5"])
        others = [c for c in THREATENING if c != withheld]
        broken = rng.sample(others, rng.choice([1, 1, 2]))
        if i % 2 == 0 and "c4" in others:
            broken = sorted(set(broken) | {"c4"})
        s.update({c: ("mismatch" if c in broken else "match") for c in THREATENING})
        s[withheld] = rng.choice(["match", "mismatch"])
        s.update(disclosure="partial_balanced", stated=set(ALL_COORDS) - {withheld},
                 repair=False, decoy=(i % 3 != 2), verdict="undefined",
                 withholding_is_decisive=False,
                 verdict_forced_by="disclosed_mismatch_unrepaired")
        specs.append(s)

    # ---- partial, forcing: the v1 manipulation, kept as a labelled control
    for i in range(N_PARTIAL_FORCING):
        s = base(i)
        withheld = rng.choice(list(THREATENING))
        s.update({c: "match" for c in THREATENING})
        s[withheld] = rng.choice(["match", "mismatch"])
        s.update(disclosure="partial_forcing", stated=set(ALL_COORDS) - {withheld},
                 repair=False, decoy=(i % 2 == 0), verdict="undefined",
                 withholding_is_decisive=True,
                 verdict_forced_by="withholding_alone")
        specs.append(s)

    rng.shuffle(specs)
    return specs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path,
                    default=SUP / "comparability_instrument_benchmark_v2.jsonl")
    ap.add_argument("--summary", type=Path,
                    default=SUP / "comparability_instrument_benchmark_v2_summary.json")
    args = ap.parse_args()

    rng = random.Random(SEED)
    specs = make_specs(rng)
    items, idx = [], 0
    for pair_id, spec in enumerate(specs):
        surface = realise(spec, rng)
        for presentation in ("canonical", "naturalistic"):
            items.append(build_item(idx, pair_id, spec, surface, presentation, rng))
            idx += 1

    # ---- verify every reference verdict follows from the specification ----
    for item in items:
        stated = set(item["stated_coordinates"])
        threat_unstated = [c for c in THREATENING if c not in stated]
        v, disc = item["truth_verdict"], item["disclosure"]
        if v == "survives":
            assert not threat_unstated, item["item_id"]
            assert all(item["truth_coordinates"][c] == "match" for c in THREATENING)
        if v == "narrows":
            assert item["truth_matched_number"], item["item_id"]
            assert item["truth_coordinates"]["c4"] in ("match",), item["item_id"]
        if v == "undefined":
            assert not item["truth_matched_number"], item["item_id"]
        if disc == "partial_balanced":
            assert item["withheld_coordinates"], item["item_id"]
            assert not item["withholding_is_decisive"]
            if v == "undefined":
                # the verdict must be undefined with the withheld coordinate
                # restored at *either* value: a disclosed unrepaired mismatch
                # on a different threatening coordinate already forces it
                disclosed_mismatch = [
                    c for c in THREATENING
                    if c in stated and item["truth_coordinates"][c] == "mismatch"]
                assert disclosed_mismatch, item["item_id"]
            if v == "survives":
                assert item["withheld_coordinates"] == ["c3"], item["item_id"]
        if disc == "partial_forcing":
            assert v == "undefined" and threat_unstated, item["item_id"]
            # nothing but the withholding forces it: every stated threatening
            # coordinate matches and there is no repair
            for c in THREATENING:
                if c in stated:
                    assert item["truth_coordinates"][c] == "match", item["item_id"]

    # class balance must hold inside each non-degenerate arm, separately per
    # presentation level, so that no arm's baseline is manufactured by pooling
    for pres in ("canonical", "naturalistic"):
        for arm in ("full", "partial_balanced"):
            c = Counter(i["truth_verdict"] for i in items
                        if i["disclosure"] == arm and i["presentation"] == pres)
            assert len(set(c.values())) == 1, (pres, arm, c)

    with args.output.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, sort_keys=True) + "\n")

    def cell(pres, disc):
        sub = [i for i in items if i["presentation"] == pres and i["disclosure"] == disc]
        counts = Counter(i["truth_verdict"] for i in sub)
        return {"n": len(sub), "verdict_counts": dict(counts),
                "constant_baseline": max(counts.values()) / len(sub) if sub else None}

    summary = {
        "schema_version": SCHEMA_VERSION,
        "seed": SEED,
        "n_items": len(items),
        "n_specifications": len(specs),
        "design": "presentation (canonical | naturalistic) x disclosure "
                  "(full | partial_balanced | partial_forcing); presentation is "
                  "paired within specification",
        "cells": {f"{p}/{d}": cell(p, d)
                  for p in ("canonical", "naturalistic")
                  for d in ("full", "partial_balanced", "partial_forcing")},
        "stratum_constant_baselines": {
            d: (lambda c: max(c.values()) / sum(c.values()))(
                Counter(i["truth_verdict"] for i in items if i["disclosure"] == d))
            for d in ("full", "partial_balanced", "partial_forcing")},
        "pooled_constant_baseline_not_used_as_a_reference": (
            lambda c: max(c.values()) / sum(c.values()))(
                Counter(i["truth_verdict"] for i in items)),
        "verdict_counts": dict(Counter(i["truth_verdict"] for i in items)),
        "disclosure_counts": dict(Counter(i["disclosure"] for i in items)),
        "presentation_counts": dict(Counter(i["presentation"] for i in items)),
        "domain_counts": dict(Counter(i["domain"] for i in items)),
        "withheld_coordinate_counts": dict(Counter(
            ",".join(i["withheld_coordinates"]) for i in items if i["withheld_coordinates"])),
        "repair_sentence_by_verdict": {
            v: sum(1 for i in items if i["truth_verdict"] == v and i["truth_matched_number"])
            for v in ("survives", "narrows", "undefined")},
        "coordinate_truth_counts": {
            c: dict(Counter(i["truth_coordinates"][c] for i in items))
            for c in ("c1", "c2", "c3", "c4", "c5")},
        "file_sha256": sha(args.output.read_text(encoding="utf-8")),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
