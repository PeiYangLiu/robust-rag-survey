#!/usr/bin/env python3
"""Verify every source quotation printed by the manuscript against its source.

Reviewer feedback on an earlier version found a quotation in the manuscript
prose that does not occur in the paper it was attributed to.  The released
ledger verifier did not catch it, because that tool re-opens the line ranges
named in the ledger and compares numerals; it never reads the manuscript.  This
closes that gap from the other side.

Three properties matter, and the first draft of this script lacked all three:

*   it reads ``main.tex`` **and every file it inputs**, because a superseded
    claim can live in a generated table rather than in prose;
*   every registered quotation carries a **file and line range**, and the
    quotation must occur there rather than anywhere in the corpus;
*   there is **no length exemption**.  Short strings are either registered as
    quotations or declared as unsourced category labels, so that a real
    attribution can never be waved through for being brief.

Exits nonzero on any failure.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANUSCRIPT = REPO / "manuscript"
MAIN = MANUSCRIPT / "main.tex"
MAIN_SURVEY = MANUSCRIPT / "main_survey.tex"
TEXTS = MANUSCRIPT / "citation_audit" / "expanded_texts"
LEDGER = MANUSCRIPT / "supplement" / "cross_paper_comparability_cases.json"

# Every quotation the manuscript attributes to a source, with the file and the
# line range it is attributed to.  A quotation not listed here fails.
REGISTRY = [
    (
        "5 most similar texts from the knowledge database as the context",
        "poisonedRAG2024.txt",
        (680, 686),
    ),
    (
        "reducing attack success rates from over 90% to approximately 10%",
        "certifiedRAG2024.txt",
        (184, 189),
    ),
    (
        "are ineffective because they cannot achieve generation, generation, and "
        "retrieval condition, respectively",
        "poisonedRAG2024.txt",
        (1336, 1343),
    ),
    (
        "could achieve a 97% ASR by injecting 5 malicious texts for each target "
        "question",
        "poisonedRAG2024.txt",
        (185, 192),
    ),
    (
        "the percentage of queries for which at least one adversarial passage is "
        "retrieved in the top-k results.",
        "poisoningRetrievalCorpora2023.txt",
        (305, 314),
    ),
    (
        "cannot achieve the generation condition",
        "poisonedRAG2024.txt",
        (918, 930),
    ),
    (
        "demonstrates strong empirical robustness against PoisonedRAG [45] and "
        "indirect prompt injection attacks [16], reducing attack success rates "
        "from over 90% to approximately 10%",
        "certifiedRAG2024.txt",
        (182, 190),
    ),
    ("from over 90%", "certifiedRAG2024.txt", (182, 190)),
    ("over 90%", "certifiedRAG2024.txt", (182, 190)),
    (
        "10 times for QA and 3 times for the long-generation task",
        "certifiedRAG2024.txt",
        (2513, 2524),
    ),
    ("in a single passage", "certifiedRAG2024.txt", (2513, 2524)),
    ("PIA can have a 90+% attack success rate", "certifiedRAG2024.txt", (1336, 1346)),
]

# Strings the manuscript scare-quotes as category labels or as its own wording,
# which are not attributions.  Declared explicitly, with no length exemption, so
# that adding a real attribution here is a visible act.
LABELS = {
    # terms of art and scare-quoted field vocabulary: these are labels this
    # survey discusses, not quotations from any one source
    "rag robustness",
    "rag security",
    "abstention rate",
    "noise",
    "which method wins",
    "can the model answer",
    "does the retrieved context contain enough to answer",
    "under what conditions is a reported number about the same question as another.",
    # column glosses in generated tables: these name a column of our own table,
    # they are not quotations from any source
    "ref. est.",
    "base",
    "scored",
    "acc.",
    "acc. (loo)",
    "obs.",
    "kind",
    "pool",
    "frontier",
    "small",
    "robustness",
    "noise robustness",
    "rag poisoning",
    "quoted",
    "frontier",
    "substantial",
    "match",
    "mismatch",
    "not_determinable",
    "transported",
    "re-implemented",
    "narrows",
    "undefined",
    "survives",
    "one action token",
    # scare-quoted field vocabulary added in the EACL revision: these are terms
    # this survey discusses or names, not quotations from any one source
    "observed",
    "the passage does not say",
    "faithfulness",
    "relevant",
    "useful",
    "-google (refc)",
    "-anthropic (refa+refd)",
    "-openai (refe)",
    "reimplemented",
    "unclear",
    "valid",
    "partial",
    "invalid",
    "under-specified",
    # generic claim templates: these are the *shapes* of claims this survey
    # discusses, written by us as illustrations, not quotations from any source
    "method a is more robust to noise than method b.",
    "defense x lowers attack success.",
    "calibration improves reliability.",
    "benchmark y is harder.",
    "robust to retrieval noise",
    "noise-robust rag",
    "trust context or model",
    # operating questions this survey poses in its own voice
    "which method is best under noise?",
    "which evidence state is present, which module intervenes, and what action should be scored?",
    # our own vocabulary, quoted to mark it as a term of art rather than a claim
    "recovered",
    # our own wording, quoted in order to discuss or retract it
    "from 97%",
    "97",
    "reducing attack success from 97%",
    "ten of twelve do not survive",
    "property of the task",
    "verdict disagreement is a property of the task",
    "disagreement is a property of the task",
    "one weak judge",
    "one judge is weaker",
    "adjudicating is not reproducible",
    "it is reproducible if you use good models",
    "same tier versus different tier",
    "same tier",
    "small",
    "frontier",
    "we also ran a diagnostic",
    "badly miscalibrated",
    "fine",
}

INPUT_RE = re.compile(r"\\input\{([^}]+)\}")

# Paper-internal wording that is scare-quoted or used as an illustration, not
# attributed to a source.  Kept separate from LABELS so the canonical forms are
# derived once at import.
OWN_WORDING = {
    "action policy",
    "A is more robust than B.",
    "Prompt D improves review.",
    "conflict,",
}


def squash(text: str) -> str:
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def canon(text: str) -> str:
    """Canonical form for verbatim matching across PDF line wrapping.

    The extracted texts keep the PDF's line breaks, including hyphenated word
    splits.  Rejoining on ``-\\n`` alone is wrong, because it also welds
    genuine hyphenated tokens that happen to fall at a line end (``top-k``
    followed by a newline becomes ``topk``).  Comparing on alphanumerics only
    is invariant to both, and still detects a fabricated quotation, which is
    what this check exists for.
    """
    return re.sub(r"[^a-z0-9%]+", "", squash(text))


def detex(text: str) -> str:
    text = re.sub(r"\\%", "%", text)
    text = re.sub(r"\\emph\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\texttt\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\S\\ref\{[^}]*\}", "", text)
    text = re.sub(r"\$([^$]*)\$", r"\1", text)
    text = re.sub(r"\\dots|\\ldots|\\textellipsis|\.\.\.|\u2026", " \x00 ", text)
    text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+\s*", "", text)
    return text.replace("\\", "")


def segments(cleaned: str) -> list[str]:
    return [p for p in (canon(x) for x in cleaned.split("\x00")) if p]


def gather_sources() -> list[tuple[Path, str]]:
    """main.tex plus every file it inputs, transitively."""
    seen: set[Path] = set()
    out: list[tuple[Path, str]] = []
    stack = [MAIN, MAIN_SURVEY]
    while stack:
        path = stack.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        body = path.read_text(encoding="utf-8", errors="replace")
        out.append((path, body))
        for target in INPUT_RE.findall(body):
            candidate = MANUSCRIPT / target
            if not candidate.suffix:
                candidate = candidate.with_suffix(".tex")
            stack.append(candidate)
    return out


def load_window(name: str, lo: int, hi: int) -> str:
    path = TEXTS / name
    if not path.exists():
        return ""
    # Split on "\n" only.  ``str.splitlines`` also breaks on form feeds and
    # other Unicode separators, which PDF-extracted text uses for page breaks,
    # so it silently shifts every line number relative to grep, awk and the
    # ledger verifier.
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    return canon("\n".join(lines[max(0, lo - 1) : hi]))


LABELS_CANON = {canon(x) for x in LABELS | OWN_WORDING}


def main() -> int:
    failures: list[str] = []
    checked = labelled = 0
    windows: dict[tuple[str, int, int], str] = {}
    registry = [(canon(q), f, r) for q, f, r in REGISTRY]

    for path, body in gather_sources():
        rel = path.relative_to(MANUSCRIPT)
        for raw in re.findall(r"``(.+?)''", body, flags=re.S):
            cleaned = detex(raw)
            flat = squash(cleaned.replace("\x00", " "))
            if not flat:
                continue
            if flat in LABELS or canon(flat) in LABELS_CANON:
                labelled += 1
                continue
            hit = None
            cflat = canon(flat)
            for quote, fname, rng in registry:
                if (
                    cflat in quote
                    or quote in cflat
                    or any(s in quote for s in segments(cleaned))
                ):
                    hit = (fname, rng)
                    break
            if hit is None:
                failures.append(
                    f"  FAIL [{rel}] unregistered quotation "
                    f"(add to REGISTRY with a line range, or to LABELS):\n"
                    f"    {flat[:160]!r}"
                )
                continue
            fname, (lo, hi) = hit
            key = (fname, lo, hi)
            if key not in windows:
                windows[key] = load_window(fname, lo, hi)
            haystack = windows[key]
            checked += 1
            if not haystack:
                failures.append(f"  FAIL [{rel}] source window missing: {fname}")
                continue
            missing = [s for s in segments(cleaned) if s not in haystack]
            if missing:
                failures.append(
                    f"  FAIL [{rel}] not verbatim at {fname}:{lo}-{hi}\n"
                    f"    {missing[0][:160]!r}"
                )
            else:
                print(f"  PASS [{rel}] {fname}:{lo}-{hi} :: {flat[:58]!r}")

    if LEDGER.exists():
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        for case in data["cases"]:
            for entry in case.get("quoted_strings", []):
                name = Path(entry["file"]).name
                spec = str(entry["lines"])
                m = re.match(r"(\d+)\s*-\s*(\d+)", spec)
                lo, hi = (int(m.group(1)), int(m.group(2))) if m else (int(spec),) * 2
                key = (name, lo - 3, hi + 3)
                if key not in windows:
                    windows[key] = load_window(name, lo - 3, hi + 3)
                checked += 1
                if canon(entry["quote"]) not in windows[key]:
                    failures.append(
                        f"  FAIL ledger quote [{case['case_id']}] not verbatim at "
                        f"{name}:{spec}"
                    )
                else:
                    print(f"  PASS ledger quote [{case['case_id']}] {name}:{spec}")

    print("\n" + "=" * 60)
    print(
        f"quotations verified: {checked}, declared labels: {labelled}, "
        f"failures: {len(failures)}"
    )
    for msg in failures:
        print(msg)
    if failures:
        print("MANUSCRIPT QUOTATION VERIFICATION FAILED")
        return 1
    print("ALL MANUSCRIPT QUOTATIONS VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
