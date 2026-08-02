#!/usr/bin/env python3
"""Correct the cross-paper case ledger after reviewer W1, and add the fields
the reviewer's finding showed were missing.

WHAT WENT WRONG (recorded here so the correction is auditable)
--------------------------------------------------------------
The submitted ledger entry SEC-03 asserted that RobustRAG introduces its
certificate as "reducing PoisonedRAG's attack success from 97%".  That
attribution is wrong in three independent ways, all checkable in the extracted
source we ourselves released:

  (a) RobustRAG never writes "97%".  Its summary sentence
      (certifiedRAG2024.txt L185-187) reads "reducing attack success rates
      from over 90% to approximately 10%".
  (b) The only "97" in RobustRAG's text is at L1502, inside Table II: it is
      RobustRAG's *own* prompt-injection ASR for Llama2-C7B on RQA
      (racc 1.0 / asr 97.0).  It is not PoisonedRAG's 97%, which is
      PoisonedRAG's black-box ASR on NQ with five injected texts
      (poisonedRAG2024.txt L187-190).  The manuscript conflated two
      numerically identical but unrelated quantities.
  (c) RobustRAG does not transport any PoisonedRAG number.  It
      *re-implements* the attack in its own harness at a deliberately
      strengthened configuration -- malicious content repeated 10x for QA and
      3x for long generation inside a single passage
      (certifiedRAG2024.txt L2515-2521).

Our released verifier passed 70/70 because it only re-opens the line ranges
named in the ``provenance`` list and checks the numerals recorded in the
ledger's own fields.  SEC-03's provenance list was correct; the error lived in
the ``comparison_claim`` field and in the manuscript prose, neither of which
was ever checked against a source.  This script therefore also adds a
``quoted_strings`` field so that every string the manuscript presents inside
quotation marks as coming from a source is machine-checkable verbatim.

WHAT SEC-03 ACTUALLY IS
-----------------------
There is still a real and verifiable comparability failure here, but it is a
different one.  RobustRAG's summary sentence states a single "over 90%"
starting point jointly for PoisonedRAG-style data poisoning and for indirect
prompt injection.  In RobustRAG's own Table II the vanilla-RAG attack success
rates for the two attacks occupy disjoint ranges:

  prompt injection : 66.0, 85.0, 100, 97.0, 93.0, 98.0   (four of six >= 93)
  data poisoning   : 80.0, 37.0, 86.0, 76.0, 38.0, 44.0  (max 86.0, min 37.0)

"over 90%" is reached only in the prompt-injection column, and RobustRAG's own
results text attributes the 90+% figure to PIA (L1340-1343).  So the number a
reader carries away for the poisoning attack -- the attack that names
PoisonedRAG -- is a maximum taken over a union of two attacks with different
capability envelopes.  That is a C2 failure, and it is the failure the entry
should have recorded.

Idempotent: safe to re-run.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "manuscript" / "supplement" / "cross_paper_comparability_cases.json"
TEXTS = REPO / "manuscript" / "citation_audit" / "expanded_texts"


def t(name: str) -> str:
    return str(TEXTS / name)


# ---------------------------------------------------------------------------
# SEC-03, corrected.
# ---------------------------------------------------------------------------
SEC03 = {
    "case_id": "SEC-03",
    "domain": "security/poisoning",
    "comparison_type": "STATED-NO-NUMBER",
    "case_class": "cross_paper",
    "comparison_claim": (
        "RobustRAG states that it 'demonstrates strong empirical robustness "
        "against PoisonedRAG [45] and indirect prompt injection attacks [16], "
        "reducing attack success rates from over 90% to approximately 10%', "
        "and separately certifies 38.0% accuracy on RQA at k=10 retrieved "
        "passages against k'=1 malicious retrieved passage. A reader places "
        "that sentence beside PoisonedRAG's headline 0.97 ASR."
    ),
    "side_A_paper": "certifiedRAG2024",
    "side_A_name": "Certifiably Robust RAG against Retrieval Corruption",
    "side_A_number": (
        "RobustRAG: empirical ASR <=15% in all cells of Table II; vanilla-RAG "
        "ASR for the poisoning attack 37.0-86.0 and for prompt injection "
        "66.0-100; certified accuracy 38.0% on RQA (Mistral-I7B, k=10, k'=1)"
    ),
    "side_B_paper": "poisonedRAG2024",
    "side_B_name": (
        "PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented "
        "Generation of Large Language Models"
    ),
    "side_B_number": (
        "PoisonedRAG black-box ASR 0.97 on NQ, 5 malicious texts injected per "
        "target question into a 2,681,468-text database, GPT-4, Contriever"
    ),
    "naive_gap": (
        "The reading a reader forms: a defense reduces poisoning attack "
        "success to <=15%, from a starting point RobustRAG states as 'over "
        "90%' and a reader supplies from PoisonedRAG's headline 0.97. "
        "RobustRAG transports no 0.97, and its own vanilla poisoning rates are "
        "37.0-86.0."
    ),
    "mismatched_coordinates": "C1; C2; C4",
    "mismatch_evidence_A": (
        "certifiedRAG2024.txt L2515-2521: 'we follow PoisonedRAG [45] and use "
        "GPT-4 to generate fake texts ... We repeat malicious content multiple "
        "times (10 times for QA and 3 times for the long-generation task) in a "
        "single passage to simulate a strong attacker'"
    ),
    "mismatch_evidence_B": (
        "poisonedRAG2024.txt L774-776: 'inject 5 malicious texts for each "
        "target question into a knowledge database with 2,681,468 clean texts'"
    ),
    "corrected_reading": (
        "RobustRAG transports no PoisonedRAG number. It re-implements the "
        "attack inside its own harness at a strengthened configuration: "
        "malicious content repeated ten times within one passage, against "
        "PoisonedRAG's five separately injected texts. The two attacks are "
        "therefore different objects, and the 0.97 never enters RobustRAG's "
        "results. RobustRAG's own vanilla-RAG poisoning ASRs are 80.0 and 37.0 "
        "and 86.0 (Mistral) and 76.0 and 38.0 and 44.0 (Llama2), so the 'over "
        "90%' starting point in its summary sentence is not attained by the "
        "poisoning attack at all; it is attained only in the prompt-injection "
        "column (66.0, 85.0, 100, 97.0, 93.0, 98.0), and RobustRAG's results "
        "text attributes the 90+% figure to PIA. The certificate is a third "
        "quantity again: it binds at k'=1 malicious passage among k=10 "
        "retrieved, and PoisonedRAG's own Table 17 reports 0.48 at one "
        "malicious text among its k=5 retrieved. Three different numbers "
        "(0.97, 0.86, 0.48) answer three different questions."
    ),
    "matched_number": (
        "Within RobustRAG's own harness the poisoning reduction is 86.0 -> "
        "<=15.0 at its worst cell and 37.0 -> <=12.0 on NQ (Table II, "
        "certifiedRAG2024.txt L1480-1485 and L1502-1507); PoisonedRAG's rate "
        "at one malicious text among the retrieved passages is 0.48 "
        "(poisonedRAG2024.txt Table 17, L2853-2856)"
    ),
    "numeric_consequence": (
        "No cross-harness gap is defined: the attack instantiations differ "
        "(C2), the corpora and retrievers differ (C1), and a certified "
        "accuracy is not an empirical ASR (C4). The recoverable statement is "
        "within-harness only. The 'over 90%' summary is a maximum over a union "
        "of two attacks whose vanilla ASR ranges are disjoint."
    ),
    "conclusion_change": "undefined",
    "quoted_strings": [
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "184-187",
            "quote": (
                "demonstrates strong empirical robustness\nagainst PoisonedRAG "
                "[45] and indirect prompt injection\nattacks [16], reducing "
                "attack success rates from over 90%\nto approximately 10%."
            ),
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "1340-1341",
            "quote": "PIA can have a 90+% attack success rate",
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "2517-2520",
            "quote": (
                "We repeat malicious content multiple times\n(10 times for QA "
                "and 3 times for the long-generation task) in\na single passage "
                "to simulate a strong attacker"
            ),
        },
    ],
    "provenance": [
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "185-187",
            "content": "reducing attack success rates from over 90% to approximately 10%",
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "1296-1298",
            "content": "k = 10 passages against 1 malicious passage",
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "1303-1306",
            "content": "71.0% certifiable robust accuracy 38.0% for RQA",
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "1340-1343",
            "content": "PIA can have a 90+% attack success rate 15% in all cases",
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "1480-1485",
            "content": "Mistral vanilla Table II 66.0 80.0 85.0 37.0 100 86.0",
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "1502-1507",
            "content": "Llama2 vanilla Table II 97.0 76.0 93.0 38.0 98.0 44.0",
        },
        {
            "file": t("certifiedRAG2024.txt"),
            "lines": "2515-2521",
            "content": "we follow PoisonedRAG repeat malicious content 10 times single passage",
        },
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "187-190",
            "content": "achieve a 97% ASR by injecting 5 malicious texts",
        },
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "774-776",
            "content": "inject 5 malicious texts",
        },
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "2850-2867",
            "content": "Table 17 1 0.48 NQ Black-Box",
        },
    ],
    "erratum": (
        "The submitted version of this entry, and the manuscript prose built "
        "on it, attributed the string 'from 97%' to RobustRAG and treated the "
        "case as a transported attack rate. RobustRAG writes 'from over 90%', "
        "attributes the 90+% figure to prompt injection rather than to "
        "PoisonedRAG, and re-implements the poisoning attack rather than "
        "quoting it. The '97' that does appear in RobustRAG (L1502) is its own "
        "prompt-injection ASR for Llama2-C7B on RQA, not PoisonedRAG's 0.97. "
        "The verdict changes from 'narrows' to 'undefined'."
    ),
}


# ---------------------------------------------------------------------------
# SEC-01, promoted to the worked flagship, with the matched reading completed.
# ---------------------------------------------------------------------------
SEC01_UPDATES = {
    "comparison_type": "STATED-TRANSPORTED-BASELINE",
    "side_A_number": (
        "PoisonedRAG black-box ASR 0.97 on NQ, GPT-4, 5 injected texts per "
        "target question, Contriever retriever, top-5 context"
    ),
    "side_B_number": (
        "Corpus Poisoning Attack ASR 0.01 on NQ as re-run by PoisonedRAG "
        "(Table 4); the original paper reports, for NQ with the same "
        "pre-trained Contriever retriever, top-20 retrieval success of 84.2 "
        "with one adversarial passage, 98.1 with ten and 99.4 with fifty"
    ),
    "naive_gap": (
        "+0.96 in favour of PoisonedRAG, read as though corpus poisoning "
        "does not work"
    ),
    "corrected_reading": (
        "PoisonedRAG scores every baseline on its own outcome: the fraction of "
        "target questions answered with the attacker's chosen answer, on NQ "
        "with the Contriever retriever and top-5 context (poisonedRAG2024.txt "
        "L680-684). Corpus Poisoning does not target answers. Its own paper "
        "defines success as 'the percentage of queries for which at least one "
        "adversarial passage is retrieved in the top-k results' "
        "(poisoningRetrievalCorpora2023.txt L307-311), and for NQ with the same "
        "pre-trained Contriever retriever reports top-20 success of 84.2 with a "
        "single adversarial passage, 98.1 with ten and 99.4 with fifty (Figure "
        "2, L343-346). PoisonedRAG itself states the reason for the 0.01: the "
        "attack 'cannot achieve the generation condition' (L924-926, L1338-"
        "1340). Scoring a retrieval attack on an answer-manipulation metric is "
        "legitimate inside PoisonedRAG's own harness -- it is what a baseline "
        "comparison is for -- but the 0.01 does not license the reading it "
        "invites outside it, namely that corpus poisoning does not work. C4 is "
        "unmatched; the retrieved sets also differ (top-5 context against a "
        "top-20 retrieval metric) and the budgets are of different kinds "
        "(5 per-question malicious texts against a global set of query-agnostic "
        "adversarial passages), so no common scope exists in either text."
    ),
    "matched_number": "not_recoverable_from_text",
    "numeric_consequence": (
        "The apparent gap is between an answer-manipulation rate and a baseline "
        "evaluated on that same metric, so it is internally valid but does not "
        "transport: the same attack on the same dataset and retriever is "
        "recorded at 0.01 by PoisonedRAG and at 84.2-99.4 by its own authors, "
        "because the outcome unit differs. No coordinate-matched cross-paper "
        "number exists."
    ),
    "conclusion_change": "undefined",
    "quoted_strings": [
        {
            "file": t("poisoningRetrievalCorpora2023.txt"),
            "lines": "307-312",
            "quote": (
                "measure the top-k\nattack success rates on test queries, "
                "defined as the\npercentage of queries for which at least one "
                "adver-\nsarial passage is retrieved in the top-k results."
            ),
        },
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "924-926",
            "quote": "cannot achieve the generation condition",
        },
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "187-190",
            "quote": (
                "could achieve a 97% ASR by in-\njecting 5 malicious texts for "
                "each target question"
            ),
        },
    ],
    "extra_provenance": [
        {
            "file": t("poisoningRetrievalCorpora2023.txt"),
            "lines": "343-349",
            "content": "Contriever 84.2 98.1 99.4 75.2 92.2 98.6",
        },
        {
            "file": t("poisoningRetrievalCorpora2023.txt"),
            "lines": "397-401",
            "content": "Figure 2 Top-20 success rate adversarial passages 1 10 50 Contriever",
        },
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "680-684",
            "content": "default setting NQ knowledge database Contriever retriever retrieve 5",
        },
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "918-928",
            "content": "Corpus Poisoning Attack very low ASR cannot achieve the generation condition",
        },
    ],
}


# ---------------------------------------------------------------------------
# Comparison-type taxonomy.  The submitted ledger had two values, DIRECT and
# SURVEY-INVITED.  Reviewer W1(c) showed that DIRECT conflates two things that
# the paper's own provenance analysis treats as distinct: a citing paper that
# prints the other paper's number, and a citing paper that names the other work
# but supplies only numbers it produced itself.
# ---------------------------------------------------------------------------
COMPARISON_TYPE = {
    # citing paper prints a number attributed to the other paper
    "SEC-04": "STATED-TRANSPORTED",
    "FAITH-02": "STATED-TRANSPORTED",
    # citing paper re-ran the other system in its own harness and prints that
    "SEC-01": "STATED-TRANSPORTED-BASELINE",
    "SEC-05": "STATED-REIMPLEMENTED",
    "NOISE-01": "STATED-REIMPLEMENTED",
    "NOISE-02": "STATED-REIMPLEMENTED",
    "NOISE-05": "STATED-REIMPLEMENTED",
    # citing paper claims a relation but supplies no number for the other side
    "SEC-03": "STATED-NO-NUMBER",
    # no author states the comparison; a reader is led to it
    "SEC-02": "SURVEY-INVITED",
    "NOISE-03": "SURVEY-INVITED",
    "NOISE-04": "SURVEY-INVITED",
    "CALIB-03": "SURVEY-INVITED",
    # within-harness controls
    "FAITH-01": "SURVEY-INVITED",
    "CALIB-01": "DIRECT",
    "CALIB-02": "DIRECT",
}

STATED = {
    "STATED-TRANSPORTED",
    "STATED-TRANSPORTED-BASELINE",
    "STATED-REIMPLEMENTED",
    "STATED-NO-NUMBER",
}

# Scare-quoted category labels in ``comparison_claim``.  These are terms the
# literature uses, not attributions to a source, and the verifier requires them
# to be declared here so that a real attribution can never hide as a label.
UNSOURCED_LABELS = {
    "SEC-02": ["RAG poisoning"],
    "NOISE-03": ["noise robustness"],
}

# Provenance line ranges that no longer point at the cited content.  These were
# hidden by the old verifier rule, which failed a missing numeral only when the
# surrounding keywords were also absent; tightening that rule exposed them.
PROVENANCE_FIXES = {
    "NOISE-03": [
        {
            "match_file": "rgb2023.txt",
            "match_lines": "531-534",
            "lines": "543-549",
            "content": "0.8 noise ratio ChatGPT 96.33 76.00",
        },
        {
            "match_file": "raat2024.txt",
            "match_lines": "618-622",
            "lines": "645-650",
            "content": "two metrics exact match EM and F1 score",
        },
    ],
}

# Provenance entries a case relies on but never recorded.  Tightening the
# verifier to check every rendered numeric field exposed these.
PROVENANCE_ADDITIONS = {
    "CALIB-03": [
        {
            "file": t("whenToRetrieve2024.txt"),
            "lines": "383-387",
            "content": "PopQA 14,282 questions",
        }
    ],
    "SEC-05": [
        {
            "file": t("poisonedRAG2024.txt"),
            "lines": "185-192",
            "content": "achieve a 97% ASR by injecting 5 malicious texts",
        }
    ],
}

# Numbers a case states that are not quoted from a source but computed from
# quoted values.  Declaring the arithmetic makes each one checkable; an
# auto-derivation rule is not a check, because with N quoted values the N^2
# pairwise differences cover the range densely enough to accept anything.
# ``inputs`` must all appear in the case's provenance blocks.
DERIVED_NUMBERS = {
    "SEC-01": [{"value": 0.96, "op": "sub", "inputs": [0.97, 0.01]}],
    "SEC-02": [
        {"value": 3.7, "op": "sub", "inputs": [97.0, 93.3]},
        {"value": 45.3, "op": "sub", "inputs": [93.3, 48.0]},
    ],
    "SEC-04": [{"value": 1.2, "op": "sub", "inputs": [98.2, 97.0]}],
    "SEC-05": [
        {"value": 0.97, "op": "scale", "inputs": [97.0]},
        {"value": 66.66, "op": "sub", "inputs": [95.23, 28.57]},
    ],
    "NOISE-01": [{"value": 6.9, "op": "sub", "inputs": [61.8, 54.9]}],
    "NOISE-02": [{"value": 6.9, "op": "sub", "inputs": [61.8, 54.9]}],
    "NOISE-03": [{"value": 4.53, "op": "sub", "inputs": [76.0, 71.47]}],
    "NOISE-04": [{"value": 1.68, "op": "sub", "inputs": [87.15, 85.47]}],
    "NOISE-05": [
        {"value": 4.4, "op": "sub", "inputs": [52.2, 47.8]},
        {"value": 3.5, "op": "literal", "inputs": [], "note": "Claude 3.5 Sonnet, a model name"},
        {"value": 1.0, "op": "literal", "inputs": [], "note": "count of retrieval settings"},
    ],
    "FAITH-02": [{"value": 34.2, "op": "sub", "inputs": [81.7, 47.5]}],
    "CALIB-01": [{"value": 23.9, "op": "sub", "inputs": [66.4, 42.5]}],
    "CALIB-03": [{"value": 16.75, "op": "sub", "inputs": [54.9, 38.15]}],
}


def main() -> int:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    cases = data["cases"]
    by_id = {c["case_id"]: c for c in cases}

    # --- SEC-03: replace wholesale --------------------------------------
    for i, c in enumerate(cases):
        if c["case_id"] == "SEC-03":
            cases[i] = SEC03
            break

    # --- SEC-01: complete the matched reading ---------------------------
    sec01 = by_id["SEC-01"]
    extra = SEC01_UPDATES.pop("extra_provenance")
    have = {(p["file"], p["lines"]) for p in sec01["provenance"]}
    for p in extra:
        if (p["file"], p["lines"]) not in have:
            sec01["provenance"].append(p)
    sec01.update(SEC01_UPDATES)

    # --- comparison-type taxonomy ---------------------------------------
    for cid, kind in COMPARISON_TYPE.items():
        by_id[cid]["comparison_type"] = kind

    # --- declared scare-quoted labels ------------------------------------
    for cid, labels in UNSOURCED_LABELS.items():
        by_id[cid]["unsourced_labels"] = labels

    # --- drifted provenance line ranges ----------------------------------
    for cid, fixes in PROVENANCE_FIXES.items():
        for fix in fixes:
            for entry in by_id[cid]["provenance"]:
                if (
                    Path(entry["file"]).name == fix["match_file"]
                    and entry["lines"] == fix["match_lines"]
                ):
                    entry["lines"] = fix["lines"]
                    entry["content"] = fix["content"]

    for cid, derived in DERIVED_NUMBERS.items():
        by_id[cid]["derived_numbers"] = derived

    for cid, extras in PROVENANCE_ADDITIONS.items():
        have = {(p["file"], p["lines"]) for p in by_id[cid]["provenance"]}
        for extra in extras:
            if (extra["file"], extra["lines"]) not in have:
                by_id[cid]["provenance"].append(extra)

    # --- recompute the summary from the cases themselves -----------------
    cross = [c for c in cases if c["case_class"] == "cross_paper"]
    stated = [c for c in cross if c["comparison_type"] in STATED]
    invited = [c for c in cross if c["comparison_type"] == "SURVEY-INVITED"]

    def tally(rows):
        out = {}
        for r in rows:
            out[r["conclusion_change"]] = out.get(r["conclusion_change"], 0) + 1
        return dict(sorted(out.items()))

    summary = data["summary"]
    summary["n_cases"] = len(cases)
    summary["n_cross_paper"] = len(cross)
    summary["n_within_harness_control"] = len(cases) - len(cross)
    summary["counts_by_conclusion_change"] = tally(cases)
    summary["counts_by_conclusion_change_cross_paper_only"] = tally(cross)
    summary["counts_by_conclusion_change_stated_only"] = tally(stated)
    summary["counts_by_conclusion_change_survey_invited_only"] = tally(invited)
    summary["n_stated"] = len(stated)
    summary["n_survey_invited"] = len(invited)
    summary["counts_by_comparison_type"] = tally_type(cases)
    summary["headline"] = (
        f"Of {len(stated)} cross-paper comparisons an author actually stated, "
        f"{tally(stated).get('undefined', 0)} are undefined, "
        f"{tally(stated).get('narrows', 0)} narrow to a matched operating "
        f"point, and {tally(stated).get('survives', 0)} survive unchanged; the "
        f"further {len(invited)} survey-invited juxtapositions are comparisons "
        f"no author made."
    )
    summary["correction_note"] = SEC03["erratum"]

    LEDGER.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {LEDGER}")

    # Keep the CSV mirror in step with the JSON.  The two were maintained in
    # parallel, which is how a corrected JSON entry left a stale claim in an
    # appendix table generated from the CSV.
    sync_gap_shorts(cases)
    sync_csv(cases)
    sync_summary(summary, cases)
    sync_report(cases, summary)

    print(f"  cross-paper cases      : {len(cross)}")
    print(f"  author-stated          : {len(stated)}  {tally(stated)}")
    print(f"  survey-invited         : {len(invited)}  {tally(invited)}")
    print(f"  all cross-paper        : {tally(cross)}")
    print(f"  headline               : {summary['headline']}")
    return 0


def tally_type(rows):
    out = {}
    for r in rows:
        out[r["comparison_type"]] = out.get(r["comparison_type"], 0) + 1
    return dict(sorted(out.items()))


CSV_PATH = REPO / "manuscript" / "supplement" / "cross_paper_comparability_cases.csv"
SUMMARY_PATH = (
    REPO / "manuscript" / "supplement" / "cross_paper_comparability_cases_summary.json"
)

# Short rendering of the naive gap for the main table.  These were hand
# maintained in the CSV and were never regenerated from the JSON, which is why
# a corrected ledger entry still rendered its superseded claim in an appendix
# table.  They are set here so that one script owns them.
NAIVE_GAP_SHORT = {
    "SEC-01": "1% vs 84.2% for the same attack",
    "SEC-03": "Defense credited with reducing poisoning ASR to <=15%",
}


def sync_gap_shorts(cases: list[dict]) -> None:
    for case in cases:
        if case["case_id"] in NAIVE_GAP_SHORT:
            case["naive_gap_short"] = NAIVE_GAP_SHORT[case["case_id"]]


def sync_csv(cases: list[dict]) -> None:
    """Rewrite the CSV mirror from the JSON, preserving existing extra columns."""
    if not CSV_PATH.exists():
        return
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        old = {row["case_id"]: row for row in reader}
    by_id = {c["case_id"]: c for c in cases}
    rows = []
    for case_id, prev in old.items():
        case = by_id.get(case_id)
        if case is None:
            rows.append(prev)
            continue
        row = dict(prev)
        for key in fields:
            if key == "numeric_consequence_short":
                continue  # written by annotate_case_short_consequences.py
            if key == "naive_gap_short" and case_id not in NAIVE_GAP_SHORT:
                continue
            if key == "provenance":
                row[key] = json.dumps(case.get("provenance", []), ensure_ascii=False)
            elif key in case:
                row[key] = case[key]
        rows.append(row)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {CSV_PATH}")


REPORT_PATH = (
    REPO / "manuscript" / "supplement" / "cross_paper_comparability_cases_report.md"
)


def sync_report(cases: list[dict], summary: dict) -> None:
    """Regenerate the findings report from the ledger.

    The report was maintained by hand and was the last place the superseded
    SEC-03 claim survived a correction to the JSON.  Generating it removes that
    class of drift.
    """
    if not REPORT_PATH.exists():
        return
    cross = [c for c in cases if c["case_class"] == "cross_paper"]
    stated = [c for c in cross if c["comparison_type"] in STATED]
    invited = [c for c in cross if c["comparison_type"] == "SURVEY-INVITED"]

    def tally(rows):
        out = {}
        for r in rows:
            out[r["conclusion_change"]] = out.get(r["conclusion_change"], 0) + 1
        return out

    lines = [
        "# Cross-Paper Comparability Cases: Findings Report",
        "",
        "Generated by `scripts/correct_cross_paper_ledger.py`. Do not edit by "
        "hand: this file was previously maintained manually and retained a "
        "superseded claim after the ledger was corrected.",
        "",
        "## Overview",
        "",
        f"**Total cases**: {len(cases)} ({len(cross)} cross-paper, "
        f"{len(cases) - len(cross)} within-harness controls)",
        "",
        f"**Author-stated cross-paper comparisons**: {len(stated)} "
        + ", ".join(f"`{k}`: {v}" for k, v in sorted(tally(stated).items())),
        "",
        f"**Survey-invited juxtapositions**: {len(invited)} "
        + ", ".join(f"`{k}`: {v}" for k, v in sorted(tally(invited).items())),
        "",
        "**How the other side's number reached the citing paper**:",
    ]
    for kind, n in sorted(tally_type(cross).items()):
        lines.append(f"- `{kind}`: {n}")
    lines += ["", f"**Headline**: {summary.get('headline', '')}", "", "## Cases", ""]
    for case in cases:
        lines += [
            f"### {case['case_id']} ({case['comparison_type']}, "
            f"{case['conclusion_change']})",
            "",
            f"- **Claim**: {case['comparison_claim']}",
            f"- **Side A** ({case['side_A_paper']}): {case['side_A_number']}",
            f"- **Side B** ({case['side_B_paper']}): {case['side_B_number']}",
            f"- **Naive gap**: {case['naive_gap']}",
            f"- **Mismatched coordinates**: {case['mismatched_coordinates']}",
            f"- **Corrected reading**: {case['corrected_reading']}",
            f"- **Matched number**: {case['matched_number']}",
            f"- **Consequence**: {case['numeric_consequence']}",
        ]
        if case.get("erratum"):
            lines.append(f"- **Erratum**: {case['erratum']}")
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {REPORT_PATH}")


def sync_summary(summary: dict, cases: list[dict] | None = None) -> None:
    if not SUMMARY_PATH.exists():
        return
    existing = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    existing.update(summary)
    # The summary file carries its own copy of the case rows, and the main
    # cross-paper table is generated from *that* copy.  Keeping it in step is
    # the whole point of this function: an earlier correction updated the
    # ledger JSON only, and the superseded claim survived in an appendix table.
    if cases is not None and isinstance(existing.get("cases"), list):
        by_id = {c["case_id"]: c for c in cases}
        merged = []
        for row in existing["cases"]:
            case = by_id.get(row.get("case_id"))
            if case is None:
                merged.append(row)
                continue
            new = dict(row)
            for key in list(new):
                if key in ("numeric_consequence_short",):
                    continue
                if key == "comparison_type_label":
                    continue
                if key in case:
                    new[key] = case[key]
            if "naive_gap_short" in new and case["case_id"] in NAIVE_GAP_SHORT:
                new["naive_gap_short"] = NAIVE_GAP_SHORT[case["case_id"]]
            new["comparison_type_label"] = TYPE_LABEL.get(
                case["comparison_type"], row.get("comparison_type_label", "")
            )
            merged.append(new)
        existing["cases"] = merged
    SUMMARY_PATH.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {SUMMARY_PATH}")


TYPE_LABEL = {
    "DIRECT": "stated",
    "SURVEY-INVITED": "invited",
    "STATED-TRANSPORTED": "stated",
    "STATED-TRANSPORTED-BASELINE": "stated",
    "STATED-REIMPLEMENTED": "stated",
    "STATED-NO-NUMBER": "stated",
}


if __name__ == "__main__":
    raise SystemExit(main())
