#!/usr/bin/env python3
"""Do passages that disclose more coordinates yield more reproducible verdicts?

Section 7 asks the community to report all five coordinates.  The paper's own
evidence for that recommendation is a constructed benchmark and five hand-picked
security cases; on real papers the coordinates are coded at kappa in
[-0.11, 0.19] and the codebook ablation finds no benefit from five fields over
two.  The counterfactual that *would* support the recommendation -- do windows
whose source passage discloses more in fact produce more reproducible
adjudications -- was never run, though the data for it are released.

This runs it, with an exposure that is not an audit outcome.  Disclosure is
scored deterministically from the passage's surface form: a coordinate counts as
disclosed when the window (plus the same +-45 lines the judges saw) contains a
term from that coordinate's released lexicon.  No model output enters the
exposure, so regressing agreement on disclosure is not regressing a panel's
labels on itself.

Reported: inter-judge verdict agreement (Fleiss' kappa and observed) by
disclosure level, a trend test over levels, and the same for coordinate labels.
Confidence intervals resample source papers.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"
DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]

# Surface markers of each coordinate.  These are declared before any analysis
# and released; they are deliberately generous, because a false positive
# weakens the contrast rather than manufacturing it.
LEXICON: dict[str, list[str]] = {
    "c1": [
        r"top-?\s?\d+", r"\bk\s*=\s*\d+", r"retriev(?:er|al)", r"\bBM25\b",
        r"\bContriever\b", r"\bDPR\b", r"\bColBERT\b", r"\bANCE\b",
        r"gold passage", r"corpus", r"snapshot", r"knowledge base",
        r"\bNQ\b", r"Natural Questions", r"HotpotQA", r"TriviaQA", r"MS ?MARCO",
        r"PopQA", r"\bWebQ", r"distractor", r"noise ratio", r"irrelevant",
        r"conflict", r"\bstale\b", r"passages? (?:are|were) retrieved",
    ],
    "c2": [
        r"attacker", r"adversar", r"threat model", r"inject", r"poison",
        r"budget", r"capabilit", r"white-?box", r"black-?box", r"access to",
        r"per (?:target )?quer", r"target question", r"triggered", r"trigger",
        r"malicious (?:text|passage|document)", r"corpus write", r"persist",
        r"natural(?:ly)? occurring", r"retrieval (?:error|failure)",
    ],
    "c4": [
        r"exact match", r"\bEM\b", r"\bF1\b", r"accurac", r"attack success",
        r"\bASR\b", r"recall@?\d*", r"precision", r"hit rate", r"success rate",
        r"per (?:question|response|span|query)", r"certified", r"calibration",
        r"\bECE\b", r"leakage", r"selective risk", r"we (?:report|measure)",
        r"metric",
    ],
    "c5": [
        r"abstain", r"abstention", r"refus", r"reject", r"defer", r"decline",
        r"fall ?back", r"re-?retriev", r"quarantin", r"flag", r"human review",
        r"cost", r"threshold", r"trade-?off", r"utility", r"risk",
        r"answer or", r"action",
    ],
}
COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in LEXICON.items()}
RULE_COORDS = ["c1", "c2", "c4", "c5"]
VERDICTS = {"survives", "narrows", "undefined"}


def fleiss_kappa(rows: list[list[str]]) -> float:
    rows = [r for r in rows if len(r) >= 2]
    if not rows:
        return float("nan")
    cats = sorted({v for r in rows for v in r})
    if len(cats) < 2:
        return float("nan")
    n = len(rows[0])
    counts = [[r.count(c) for c in cats] for r in rows]
    p_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in counts]
    p_bar = sum(p_i) / len(p_i)
    p_j = [sum(row[j] for row in counts) / (len(rows) * n) for j in range(len(cats))]
    p_e = sum(p * p for p in p_j)
    return (p_bar - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def observed(rows: list[list[str]]) -> float:
    if not rows:
        return float("nan")
    tot = 0.0
    for r in rows:
        n = len(r)
        pairs = n * (n - 1) / 2
        same = sum(v * (v - 1) / 2 for v in Counter(r).values())
        tot += same / pairs if pairs else 0.0
    return tot / len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    parser.add_argument(
        "--frame", type=Path, default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl"
    )
    parser.add_argument(
        "--ledger", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv"
    )
    parser.add_argument(
        "--out", type=Path, default=SUPPLEMENT / "disclosure_counterfactual.json"
    )
    parser.add_argument("--context-lines", type=int, default=45)
    parser.add_argument("--draws", type=int, default=3000)
    args = parser.parse_args()

    windows = {}
    for line in args.frame.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            windows[row["candidate_id"]] = row

    import csv

    eligible = [
        r["candidate_id"]
        for r in csv.DictReader(args.ledger.open(encoding="utf-8"))
        if r["candidate_id"] in windows
    ]

    per_judge: dict[str, dict[str, dict]] = {}
    for name in DEPLOYED:
        table = {}
        for line in (args.coding_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row["parsed"]
        per_judge[name] = table
    eligible = [c for c in eligible if all(c in per_judge[j] for j in DEPLOYED)]

    text_cache: dict[str, list[str]] = {}

    def shown(cid: str) -> str:
        w = windows[cid]
        name = w["source_file"]
        if name not in text_cache:
            path = TEXT_DIR / name
            text_cache[name] = (
                path.read_text(encoding="utf-8", errors="replace").splitlines()
                if path.exists()
                else []
            )
        lines = text_cache[name]
        if not lines:
            return w["window_text"]
        lo = max(0, w["line_start"] - 1 - args.context_lines)
        hi = min(len(lines), w["line_end"] + args.context_lines)
        return "\n".join(lines[lo:hi])

    disclosure: dict[str, dict[str, bool]] = {}
    for cid in eligible:
        text = shown(cid)
        disclosure[cid] = {
            coord: any(p.search(text) for p in pats) for coord, pats in COMPILED.items()
        }

    level_of = {cid: sum(disclosure[cid][c] for c in RULE_COORDS) for cid in eligible}

    def verdict_rows(ids: list[str]) -> list[list[str]]:
        rows = []
        for cid in ids:
            labels = []
            for j in DEPLOYED:
                v = str(per_judge[j][cid].get("verdict", "")).strip().lower()
                labels.append(v if v in VERDICTS else "undefined")
            rows.append(labels)
        return rows

    def coord_rows(ids: list[str], coord: str) -> list[list[str]]:
        return [
            [
                str(per_judge[j][cid].get(coord, "not_determinable")).strip().lower()
                for j in DEPLOYED
            ]
            for cid in ids
        ]

    by_level: dict[int, list[str]] = defaultdict(list)
    for cid in eligible:
        by_level[level_of[cid]].append(cid)

    rng = random.Random(20260731)
    papers_of = {cid: windows[cid]["cite_key"] for cid in eligible}

    def boot_kappa(ids: list[str], builder) -> tuple[float, float]:
        groups: dict[str, list[str]] = defaultdict(list)
        for cid in ids:
            groups[papers_of[cid]].append(cid)
        keys = sorted(groups)
        if len(keys) < 2:
            return float("nan"), float("nan")
        vals = []
        for _ in range(args.draws):
            pick = [keys[rng.randrange(len(keys))] for _ in keys]
            drawn = [c for k in pick for c in groups[k]]
            v = fleiss_kappa(builder(drawn))
            if v == v:
                vals.append(v)
        if not vals:
            return float("nan"), float("nan")
        vals.sort()
        return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]

    levels_block = {}
    for level in sorted(by_level):
        ids = by_level[level]
        rows = verdict_rows(ids)
        lo, hi = boot_kappa(ids, verdict_rows)
        levels_block[str(level)] = {
            "n_windows": len(ids),
            "n_papers": len({papers_of[c] for c in ids}),
            "verdict_fleiss_kappa": fleiss_kappa(rows),
            "verdict_kappa_ci95": [lo, hi],
            "verdict_observed": observed(rows),
            "verdict_distribution": dict(Counter(v for r in rows for v in r)),
        }

    # High versus low disclosure, the contrast the recommendation implies.
    hi_ids = [c for c in eligible if level_of[c] >= 3]
    lo_ids = [c for c in eligible if level_of[c] <= 2]
    k_hi, k_lo = fleiss_kappa(verdict_rows(hi_ids)), fleiss_kappa(verdict_rows(lo_ids))

    paired_ids = hi_ids + lo_ids
    groups: dict[str, list[str]] = defaultdict(list)
    for cid in paired_ids:
        groups[papers_of[cid]].append(cid)
    keys = sorted(groups)
    diffs = []
    for _ in range(args.draws):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        drawn = [c for k in pick for c in groups[k]]
        h = [c for c in drawn if level_of[c] >= 3]
        l = [c for c in drawn if level_of[c] <= 2]
        if len(h) > 5 and len(l) > 5:
            a, b = fleiss_kappa(verdict_rows(h)), fleiss_kappa(verdict_rows(l))
            if a == a and b == b:
                diffs.append(a - b)
    diffs.sort()

    coord_block = {}
    for coord in RULE_COORDS:
        d_ids = [c for c in eligible if disclosure[c][coord]]
        n_ids = [c for c in eligible if not disclosure[c][coord]]
        coord_block[coord] = {
            "n_disclosed": len(d_ids),
            "n_not_disclosed": len(n_ids),
            "kappa_when_disclosed": fleiss_kappa(coord_rows(d_ids, coord)),
            "kappa_when_not_disclosed": fleiss_kappa(coord_rows(n_ids, coord)),
            "not_determinable_share_when_disclosed": (
                sum(
                    1
                    for r in coord_rows(d_ids, coord)
                    for v in r
                    if v == "not_determinable"
                )
                / max(1, 3 * len(d_ids))
            ),
            "not_determinable_share_when_not_disclosed": (
                sum(
                    1
                    for r in coord_rows(n_ids, coord)
                    for v in r
                    if v == "not_determinable"
                )
                / max(1, 3 * len(n_ids))
            ),
        }

    payload = {
        "schema_version": 1,
        "exposure_note": (
            "Disclosure is a deterministic property of the passage the judges "
            "were shown, computed from a released lexicon before any label is "
            "consulted. It is not a model output and not an audit outcome."
        ),
        "lexicon": LEXICON,
        "n_eligible": len(eligible),
        "disclosure_level_distribution": dict(Counter(level_of.values())),
        "coordinate_disclosure_rate": {
            c: sum(1 for cid in eligible if disclosure[cid][c]) / len(eligible)
            for c in COMPILED
        },
        "by_disclosure_level": levels_block,
        "high_vs_low": {
            "definition": "high = at least 3 of C1,C2,C4,C5 disclosed; low = at most 2",
            "n_high": len(hi_ids),
            "n_low": len(lo_ids),
            "kappa_high": k_hi,
            "kappa_low": k_lo,
            "difference": k_hi - k_lo,
            "difference_ci95": (
                [diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs))]]
                if diffs
                else []
            ),
            "share_above_zero": sum(1 for d in diffs if d > 0) / len(diffs) if diffs else float("nan"),
        },
        "per_coordinate": coord_block,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "n_eligible": payload["n_eligible"],
                "disclosure_levels": payload["disclosure_level_distribution"],
                "by_level_kappa": {
                    k: round(v["verdict_fleiss_kappa"], 3) for k, v in levels_block.items()
                },
                "high_vs_low": {
                    k: (round(v, 3) if isinstance(v, float) else v)
                    for k, v in payload["high_vs_low"].items()
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
