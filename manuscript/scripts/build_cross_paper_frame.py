#!/usr/bin/env python3
"""Build a reproducible sampling frame of candidate cross-paper comparisons.

Motivation
----------
The previous version of the paper analysed twelve comparisons that were chosen
by the authors, with no recoverable sampling rule.  A reviewer objected that
this supports "the failure mode exists" but licenses no statement about the
literature, and asked for a reproducible sampling frame with a much larger
case count.

This script constructs that frame deterministically.  Nothing here is a
judgment: it is a text screen whose output is a list of *candidate* windows,
each of which is then coded independently downstream.

Screen
------
A candidate is a contiguous window of ``--window`` lines in one locally
extracted full text such that:

1.  the window mentions at least one **external system name**, i.e. a system
    from the gazetteer that is not attributed to the file's own paper;
2.  the window contains at least ``--min-numbers`` numeric values that look
    like reported results (a percentage, or a decimal in [0, 1], or a score
    with one or two decimals);
3.  the window contains at least one **comparison cue** (a baseline table
    header, or a comparative construction such as "outperforms", "compared
    with", "whereas", "versus", "improves over", "reduces ... from").

The gazetteer is built from the citation-key map plus a fixed list of system
names that appear as table row labels in this literature; every gazetteer entry
is recorded in the output so the screen is auditable and re-runnable.

Outputs
-------
``cross_paper_frame_candidates.jsonl`` -- every candidate with its file, line
range, verbatim window text, matched system names, matched numbers and cues.
``cross_paper_frame_summary.json``     -- frame size and per-file counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"
SUPPLEMENT = REPO / "manuscript" / "supplement"

# System names that appear as baseline row labels or as subjects of comparative
# sentences in the robust-RAG literature.  Matching is case-insensitive on a
# word boundary; hyphen and space variants are generated automatically.
SYSTEM_GAZETTEER = [
    "PoisonedRAG", "Phantom", "BadRAG", "AgentPoison", "GARAG", "AIP",
    "Corpus Poisoning", "Prompt Injection", "GASLITE", "Jamming",
    "RobustRAG", "CertifiedRAG", "AstuteRAG", "InstructRAG", "TrustRAG",
    "Self-RAG", "SelfRAG", "CRAG", "Self-CRAG", "CtrlA", "FLARE", "DRAGIN",
    "Adaptive-RAG", "Chain-of-Note", "CoN", "RAAT", "RGB", "RECALL",
    "ClashEval", "FaithEval", "RAGTruth", "RAGAS", "ARES", "RAGChecker",
    "LongRAG", "REPLUG", "Atlas", "RETRO", "FiD", "REALM", "kNN-LM",
    "DPR", "Contriever", "BM25", "ColBERT", "SPLADE",
    "RQ-RAG", "SearChain", "IRCoT", "ReAct", "Toolformer",
    "Self-Ask", "Chain-of-Verification", "CoVe", "RARR", "Verify-and-Edit",
    "Sufficient Context", "ParamMute", "Astute", "SEER", "SKR",
    "Speculative RAG", "Blended RAG", "GraphRAG", "HippoRAG", "RAPTOR",
    "Self-Reflective", "Corrective Retrieval", "MuRAG", "Atlas-11B",
]

# Stratum A cues: the language of a baseline table, which mostly surfaces
# comparisons whose other side was re-run inside the citing paper's harness.
COMPARISON_CUES = [
    r"outperform\w*", r"compared\s+(?:to|with)", r"comparison\s+with",
    r"whereas", r"versus", r"\bvs\.?\b", r"improves?\s+(?:over|upon)",
    r"reduces?\s+\w*\s*from", r"higher\s+than", r"lower\s+than",
    r"better\s+than", r"worse\s+than", r"surpass\w*", r"exceeds?",
    r"baselines?", r"state[- ]of[- ]the[- ]art", r"prior\s+work",
    r"achiev\w+\s+only", r"in\s+contrast", r"by\s+\d+(?:\.\d+)?\s*(?:%|points?|pp)",
]

# Stratum B cues: explicit attribution of a number to another paper. These are
# the windows in which a value is *transported* rather than re-measured. The
# stratum is defined by an exposure (how the number was obtained), never by the
# outcome (whether the comparison survives), so enriching it does not bias the
# within-stratum failure rate.
ATTRIBUTION_CUES = [
    r"as\s+reported\s+(?:in|by)", r"reported\s+(?:in|by)\s+(?:the\s+)?(?:original|their|its)",
    r"cited\s+from", r"taken\s+from", r"copied\s+from", r"quoted\s+from",
    r"originally\s+reported", r"reported\s+results", r"results?\s+are\s+(?:taken|cited|copied|quoted)",
    r"numbers?\s+are\s+(?:taken|cited|from)", r"according\s+to\s+\w+\s+et\s+al",
    r"et\s+al\.?\s*\(?\d{4}\)?\s+(?:report|reports|reported|achieve|achieves|achieved|obtain|obtains)",
    r"\w+\s+et\s+al\.?,?\s*\(?\d{4}\)?", r"in\s+their\s+(?:paper|work|setup|experiments)",
    r"their\s+reported", r"the\s+original\s+paper", r"as\s+published",
    r"we\s+(?:quote|reuse|reproduce|copy)\s+", r"from\s+the\s+respective\s+papers",
    r"scores?\s+(?:are|were)\s+(?:those|taken)", r"survey", r"we\s+compile",
]

# Stratum C: survey and review papers compile headline numbers from several
# papers into one table, which is the canonical site of a *transported* value.
# Their tables survive PDF extraction as long runs of numbers with system names,
# and no comparative cue is present, so strata A and B miss them. The stratum is
# defined by document type and table shape, never by the audit outcome.
SURVEY_TITLE_CUES = [
    r"\bsurvey\b", r"\ba review of\b", r"systematic review", r"\breview\b",
    r"comprehensive (?:study|review|analysis|survey)", r"\btaxonomy\b",
    r"empirical study", r"\bbenchmark(?:ing)?\b", r"\bcompass\b", r"\bcomparison\b",
]

NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:\d{1,3}(?:\.\d{1,2})?\s*%|0?\.\d{2,3}|\d{1,3}\.\d{1,2})(?![\w])"
)
PAGE_MARKER = re.compile(r"^=+\s*PAGE\s+\d+\s*=+$")


def variants(name: str) -> list[str]:
    base = {name, name.replace("-", " "), name.replace(" ", "-"), name.replace("-", "")}
    return sorted({v for v in base if v})


def build_patterns() -> dict[str, re.Pattern[str]]:
    patterns = {}
    for name in SYSTEM_GAZETTEER:
        alternatives = "|".join(re.escape(v) for v in variants(name))
        patterns[name] = re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])", re.I)
    return patterns


def own_systems(text: str, patterns: dict[str, re.Pattern[str]], head_lines: int) -> set[str]:
    """Systems named in the title/abstract region are treated as the paper's own."""
    head = "\n".join(text.splitlines()[:head_lines])
    return {name for name, pattern in patterns.items() if pattern.search(head)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-dir", type=Path, default=TEXT_DIR)
    parser.add_argument("--window", type=int, default=12)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--min-numbers", type=int, default=2)
    parser.add_argument("--head-lines", type=int, default=40)
    parser.add_argument(
        "--stratum",
        choices=("baseline", "attribution", "survey_table", "all"),
        default="all",
    )
    parser.add_argument("--survey-window", type=int, default=26)
    parser.add_argument("--survey-min-numbers", type=int, default=4)
    parser.add_argument("--survey-min-systems", type=int, default=2)
    parser.add_argument(
        "--out-candidates", type=Path, default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl"
    )
    parser.add_argument(
        "--out-summary", type=Path, default=SUPPLEMENT / "cross_paper_frame_summary.json"
    )
    args = parser.parse_args()

    patterns = build_patterns()
    cue_pattern = re.compile("|".join(COMPARISON_CUES), re.I)
    attribution_pattern = re.compile("|".join(ATTRIBUTION_CUES), re.I)
    survey_pattern = re.compile("|".join(SURVEY_TITLE_CUES), re.I)

    candidates = []
    per_file: Counter[str] = Counter()
    files = sorted(args.text_dir.glob("*.txt"))
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        mine = own_systems(text, patterns, args.head_lines)
        is_survey = bool(
            survey_pattern.search("\n".join(lines[: args.head_lines]))
        )
        for start in range(0, max(len(lines) - 1, 1), args.stride):
            span = args.survey_window if is_survey else args.window
            window = lines[start : start + span]
            if not window:
                continue
            blob = "\n".join(w for w in window if not PAGE_MARKER.match(w.strip()))
            if not blob.strip():
                continue
            matched = [
                name
                for name, pattern in patterns.items()
                if name not in mine and pattern.search(blob)
            ]
            if not matched:
                continue
            numbers = NUMBER_PATTERN.findall(blob)
            if len(numbers) < args.min_numbers:
                continue
            cues = sorted({m.group(0).lower() for m in cue_pattern.finditer(blob)})
            attribution = sorted(
                {m.group(0).lower() for m in attribution_pattern.finditer(blob)}
            )
            strata = []
            if cues:
                strata.append("baseline")
            if attribution:
                strata.append("attribution")
            if (
                is_survey
                and len(matched) >= args.survey_min_systems
                and len(numbers) >= args.survey_min_numbers
            ):
                strata.append("survey_table")
            if not strata:
                continue
            if args.stratum != "all" and args.stratum not in strata:
                continue
            candidate_id = hashlib.sha256(
                f"{path.name}:{start + 1}:{start + len(window)}".encode()
            ).hexdigest()[:16]
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_file": path.name,
                    "cite_key": path.stem,
                    "line_start": start + 1,
                    "line_end": start + len(window),
                    "external_systems": sorted(matched),
                    "own_systems": sorted(mine),
                    "numbers": numbers[:24],
                    "comparison_cues": cues[:8],
                    "attribution_cues": attribution[:8],
                    "frame_strata": strata,
                    "window_text": blob,
                    "window_sha256": hashlib.sha256(blob.encode()).hexdigest(),
                }
            )
            per_file[path.name] += 1

    args.out_candidates.parent.mkdir(parents=True, exist_ok=True)
    with args.out_candidates.open("w", encoding="utf-8") as handle:
        for row in candidates:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "schema_version": "cross-paper-frame-v1",
        "text_dir": str(args.text_dir),
        "n_files_screened": len(files),
        "n_files_with_candidates": len(per_file),
        "n_candidates": len(candidates),
        "n_baseline_stratum": sum(1 for c in candidates if "baseline" in c["frame_strata"]),
        "n_attribution_stratum": sum(
            1 for c in candidates if "attribution" in c["frame_strata"]
        ),
        "n_attribution_only": sum(1 for c in candidates if c["frame_strata"] == ["attribution"]),
        "n_survey_table_stratum": sum(
            1 for c in candidates if "survey_table" in c["frame_strata"]
        ),
        "n_survey_table_only": sum(
            1 for c in candidates if c["frame_strata"] == ["survey_table"]
        ),
        "survey_title_cues": SURVEY_TITLE_CUES,
        "screen": {
            "window_lines": args.window,
            "stride_lines": args.stride,
            "min_numbers": args.min_numbers,
            "head_lines_for_own_systems": args.head_lines,
            "gazetteer_size": len(SYSTEM_GAZETTEER),
            "gazetteer": SYSTEM_GAZETTEER,
            "comparison_cues": COMPARISON_CUES,
            "attribution_cues": ATTRIBUTION_CUES,
            "survey_window_lines": args.survey_window,
            "survey_min_numbers": args.survey_min_numbers,
            "number_pattern": NUMBER_PATTERN.pattern,
        },
        "candidates_per_file_top20": per_file.most_common(20),
    }
    args.out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"screened {len(files)} files -> {len(candidates)} candidate windows "
        f"in {len(per_file)} files"
    )
    print(f"wrote {args.out_candidates}")
    print(f"wrote {args.out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
