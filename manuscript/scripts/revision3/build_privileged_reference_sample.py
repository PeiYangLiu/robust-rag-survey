#!/usr/bin/env python3
"""Draw the sample of *real* frame windows on which a privileged-information
adjudication reference is built.

Why this exists.  The provenance label was previously validated only on
constructed excerpts whose provenance was fixed when the item was written.  On
that set every judge is perfect, so it has no power to detect the bias it was
invoked to rule out, and it says nothing about real windows, where the same
judges agree at only kappa 0.55.  This script draws the deployment-set sample
that replaces it.

Sampling is on document features only.  The stratum is the frame stratum
(baseline table language / explicit attribution / survey-style table), which is
a property of the window's surface form and was fixed before any judgment was
made, crossed with whether the cited paper's full text is held locally, which is
a property of our corpus and not of the audit outcome.  Nothing is sampled on a
label, a verdict, a provenance class, or an agreement statistic.

Output: one JSONL row per sampled window carrying the window, the citing paper's
identity, and the resolved cited papers, ready for the three information tiers
of ``run_privileged_adjudication.py``.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from system_paper_map import verified_map, _pattern  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"
SAMPLE_SEED = 20260731


def load_frame() -> dict[str, dict]:
    frame = {}
    with (SUPPLEMENT / "cross_paper_frame_candidates.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                frame[row["candidate_id"]] = row
    return frame


def load_eligible_ledger() -> list[dict]:
    with (SUPPLEMENT / "cross_paper_census_ledger.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def stratum_of(row: dict) -> str:
    """One label per window, in a fixed precedence, so strata partition."""
    strata = row["frame_strata"]
    for name in ("attribution", "survey_table", "baseline"):
        if name in strata:
            return name
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=180, help="target sample size")
    parser.add_argument(
        "--out", type=Path, default=SUPPLEMENT / "privileged_reference_sample.jsonl"
    )
    parser.add_argument(
        "--summary", type=Path, default=SUPPLEMENT / "privileged_reference_sample_summary.json"
    )
    args = parser.parse_args()

    resolved, rejected = verified_map()
    frame = load_frame()
    ledger = load_eligible_ledger()

    population = []
    for entry in ledger:
        cid = entry["candidate_id"]
        window = frame.get(cid)
        if window is None:
            continue
        cited = {}
        for system in window["external_systems"]:
            key = resolved.get(system)
            if key and key != window["cite_key"] and (TEXT_DIR / f"{key}.txt").exists():
                cited.setdefault(key, []).append(system)
        population.append(
            {
                "candidate_id": cid,
                "cite_key": window["cite_key"],
                "source_file": window["source_file"],
                "line_start": window["line_start"],
                "line_end": window["line_end"],
                "window_sha256": window["window_sha256"],
                "window_text": window["window_text"],
                "external_systems": window["external_systems"],
                "frame_strata": window["frame_strata"],
                "stratum": stratum_of(window),
                "cited_papers": [
                    {"cite_key": k, "systems": sorted(v)} for k, v in sorted(cited.items())
                ],
                "cited_text_available": bool(cited),
            }
        )

    # Stratified proportional allocation over (frame stratum x cited-text
    # availability).  Availability is a corpus property; including it as a
    # stratum guarantees the both-texts tier is populated in every frame
    # stratum rather than concentrating in whichever stratum happens to cite
    # papers we hold.
    cells: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for row in population:
        cells[(row["stratum"], row["cited_text_available"])].append(row)

    rng = random.Random(SAMPLE_SEED)
    total = len(population)
    picked: list[dict] = []
    # Guarantee the both-texts tier is usable: allocate half the sample to
    # available cells, then fill proportionally.
    avail_cells = {k: v for k, v in cells.items() if k[1]}
    other_cells = {k: v for k, v in cells.items() if not k[1]}
    n_avail_target = min(args.n // 2, sum(len(v) for v in avail_cells.values()))
    n_other_target = args.n - n_avail_target

    def allocate(group: dict[tuple[str, bool], list[dict]], target: int) -> list[dict]:
        size = sum(len(v) for v in group.values())
        if size == 0 or target <= 0:
            return []
        out: list[dict] = []
        keys = sorted(group)
        quotas = {k: min(len(group[k]), round(target * len(group[k]) / size)) for k in keys}
        # repair rounding
        while sum(quotas.values()) > target:
            k = max(keys, key=lambda k: quotas[k])
            quotas[k] -= 1
        while sum(quotas.values()) < target:
            k = min(
                (k for k in keys if quotas[k] < len(group[k])),
                key=lambda k: quotas[k] / max(1, len(group[k])),
                default=None,
            )
            if k is None:
                break
            quotas[k] += 1
        for k in keys:
            pool = sorted(group[k], key=lambda r: r["candidate_id"])
            out.extend(rng.sample(pool, quotas[k]))
        return out

    picked.extend(allocate(avail_cells, n_avail_target))
    picked.extend(allocate(other_cells, n_other_target))
    picked.sort(key=lambda r: r["candidate_id"])

    with args.out.open("w", encoding="utf-8") as fh:
        for row in picked:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "seed": SAMPLE_SEED,
        "population_definition": (
            "every window in the frame that the deployed three-judge panel "
            "called eligible by majority; this is the set on which the census "
            "reports a verdict"
        ),
        "population_n": total,
        "sample_n": len(picked),
        "sample_papers": len({r["cite_key"] for r in picked}),
        "population_papers": len({r["cite_key"] for r in population}),
        "strata_population": dict(Counter(f"{s}|{a}" for s, a in
                                          [(r["stratum"], r["cited_text_available"]) for r in population])),
        "strata_sample": dict(Counter(f"{s}|{a}" for s, a in
                                      [(r["stratum"], r["cited_text_available"]) for r in picked])),
        "n_cited_text_available": sum(1 for r in picked if r["cited_text_available"]),
        "resolved_systems": {k: v for k, v in sorted(resolved.items())},
        "rejected_system_mappings": rejected,
        "note": (
            "Sampling uses only document features (frame stratum) and a corpus "
            "property (whether the cited paper's full text is held locally). "
            "No label, verdict, provenance class or agreement statistic enters "
            "the sampling design."
        ),
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("population_n", "sample_n", "sample_papers", "n_cited_text_available",
                       "strata_sample")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
