#!/usr/bin/env python3
"""Sample the juxtapositions the screen did *not* surface (reviewer W5).

The reviewer's objection to the composition claim is a selection argument, and
it is a good one.  The screen requires a gazetteer system name, at least two
result-formatted numbers in-window, and one of three surface strata, the first
of which is baseline-table language.  Baseline tables are the canonical home of
re-implementations, while a transported number is often prose-borne and often
appears with only one numeral in the window.  If that is right, the 87%
re-implementation share is partly a property of the inclusion criteria.

This script builds the negative sample that decides it.  The *universe* is
every window that satisfies the weakest necessary condition for a numeric
cross-paper juxtaposition to exist at all -- it names a gazetteer system that
is not the paper's own, and it contains at least one result-formatted number --
under exactly the windowing the screen uses, so screened and missed windows are
the same kind of object.  Removing the screened windows leaves the *missed*
set, from which we draw a uniform random sample with a fixed seed.

Those windows are then coded with the identical eligibility and provenance
prompts used on the frame, which lets us estimate, for each provenance class,
the share of eligible juxtapositions in the universe that the screen surfaced,
and to re-weight the composition accordingly.

Writes ``supplement/screen_recall_sample.jsonl`` and a pool summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_cross_paper_frame import (  # noqa: E402
    NUMBER_PATTERN, PAGE_MARKER, SURVEY_TITLE_CUES, build_patterns, own_systems,
)

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"
SEED = 2026080431


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text-dir", type=Path, default=TEXT_DIR)
    ap.add_argument("--frame", type=Path, default=SUP / "cross_paper_frame_candidates.jsonl")
    ap.add_argument("--window", type=int, default=12)
    ap.add_argument("--stride", type=int, default=6)
    ap.add_argument("--survey-window", type=int, default=26)
    ap.add_argument("--head-lines", type=int, default=40)
    ap.add_argument("--min-numbers", type=int, default=1)
    ap.add_argument("--sample-size", type=int, default=420)
    ap.add_argument("--out", type=Path, default=SUP / "screen_recall_sample.jsonl")
    ap.add_argument("--summary", type=Path, default=SUP / "screen_recall_pool_summary.json")
    args = ap.parse_args()

    screened = set()
    for line in args.frame.read_text(encoding="utf-8").splitlines():
        if line.strip():
            screened.add(json.loads(line)["candidate_id"])

    patterns = build_patterns()
    survey_pattern = re.compile("|".join(SURVEY_TITLE_CUES), re.I)

    universe, missed = 0, []
    per_file_missed: Counter[str] = Counter()
    for path in sorted(args.text_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        mine = own_systems(text, patterns, args.head_lines)
        is_survey = bool(survey_pattern.search("\n".join(lines[: args.head_lines])))
        for start in range(0, max(len(lines) - 1, 1), args.stride):
            span = args.survey_window if is_survey else args.window
            window = lines[start: start + span]
            if not window:
                continue
            blob = "\n".join(w for w in window if not PAGE_MARKER.match(w.strip()))
            if not blob.strip():
                continue
            matched = [n for n, p in patterns.items()
                       if n not in mine and p.search(blob)]
            if not matched:
                continue
            numbers = NUMBER_PATTERN.findall(blob)
            if len(numbers) < args.min_numbers:
                continue
            universe += 1
            cid = hashlib.sha256(
                f"{path.name}:{start + 1}:{start + len(window)}".encode()
            ).hexdigest()[:16]
            if cid in screened:
                continue
            per_file_missed[path.name] += 1
            missed.append({
                "candidate_id": cid,
                "source_file": path.name,
                "cite_key": path.stem,
                "line_start": start + 1,
                "line_end": start + len(window),
                "external_systems": sorted(matched),
                "own_systems": sorted(mine),
                "numbers": numbers[:24],
                "n_numbers": len(numbers),
                "window_text": blob,
                "window_sha256": hashlib.sha256(blob.encode()).hexdigest(),
            })

    rng = random.Random(SEED)
    sample = rng.sample(missed, min(args.sample_size, len(missed)))
    sample.sort(key=lambda r: r["candidate_id"])
    with args.out.open("w", encoding="utf-8") as fh:
        for row in sample:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "schema_version": "screen-recall-pool-v1",
        "seed": SEED,
        "universe_definition": (
            "every window under the screen's own windowing that names a "
            "gazetteer system absent from the paper's title/abstract region and "
            "contains at least one result-formatted number; this drops the "
            "screen's second-numeral requirement and all three surface strata, "
            "which are exactly the conditions the reviewer identifies as "
            "selecting for baseline tables"),
        "n_universe_windows": universe,
        "n_screened_windows": len(screened),
        "n_missed_windows": len(missed),
        "screen_coverage_of_universe": len(screened) / universe if universe else None,
        "sample_size": len(sample),
        "sampling_fraction_of_missed": len(sample) / len(missed) if missed else None,
        "missed_numeral_counts": dict(Counter(
            min(r["n_numbers"], 5) for r in missed)),
        "missed_per_file_top20": per_file_missed.most_common(20),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "missed_per_file_top20"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
