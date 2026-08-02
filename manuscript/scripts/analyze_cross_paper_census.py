#!/usr/bin/env python3
"""Aggregate the three independent codings of the cross-paper frame.

Reports, for the census over the reproducible frame:

*   eligibility: how many candidate windows at least two of three judges call a
    genuine cross-paper juxtaposition;
*   inter-coder agreement on eligibility, on each coordinate, and on the
    verdict, as observed agreement, Cohen's kappa (pairwise, averaged), Fleiss'
    kappa, and Gwet's AC1 -- Gwet's statistic is reported because kappa is
    depressed by skewed marginals, which is exactly the regime here;
*   the majority verdict distribution and the coordinate violation rates with
    binomial intervals;
*   an evidence-quote check: what share of codings quote a string that really
    occurs in the window they were shown.

Nothing here adjudicates: the majority label is mechanical, and cases with no
majority are counted and reported rather than resolved.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from itertools import combinations
from typing import Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUPPLEMENT = REPO / "manuscript" / "supplement"
COORDINATES = ("c1", "c2", "c3", "c4", "c5")
VERDICTS = ("survives", "narrows", "undefined")


def observed_agreement(labels: list[list[str]]) -> float:
    total, agree = 0, 0
    for row in labels:
        for a, b in combinations(row, 2):
            total += 1
            agree += int(a == b)
    return agree / total if total else float("nan")


def cohen_kappa(x: list[str], y: list[str]) -> float:
    categories = sorted(set(x) | set(y))
    n = len(x)
    if n == 0 or len(categories) < 2:
        return float("nan")
    po = sum(a == b for a, b in zip(x, y)) / n
    cx, cy = Counter(x), Counter(y)
    pe = sum((cx[c] / n) * (cy[c] / n) for c in categories)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def fleiss_kappa(labels: list[list[str]]) -> float:
    categories = sorted({v for row in labels for v in row})
    n_items = len(labels)
    if not n_items:
        return float("nan")
    raters = len(labels[0])
    if raters < 2 or len(categories) < 2:
        return float("nan")
    counts = [[row.count(c) for c in categories] for row in labels]
    p_i = [
        (sum(v * v for v in row) - raters) / (raters * (raters - 1)) for row in counts
    ]
    p_bar = sum(p_i) / n_items
    p_j = [sum(row[j] for row in counts) / (n_items * raters) for j in range(len(categories))]
    pe = sum(v * v for v in p_j)
    return (p_bar - pe) / (1 - pe) if pe < 1 else float("nan")


def gwet_ac1(labels: list[list[str]]) -> float:
    categories = sorted({v for row in labels for v in row})
    n_items = len(labels)
    raters = len(labels[0]) if labels else 0
    if n_items == 0 or raters < 2 or len(categories) < 2:
        return float("nan")
    counts = [[row.count(c) for c in categories] for row in labels]
    pa = sum(
        (sum(v * v for v in row) - raters) / (raters * (raters - 1)) for row in counts
    ) / n_items
    pi = [sum(row[j] for row in counts) / (n_items * raters) for j in range(len(categories))]
    q = len(categories)
    pe = sum(p * (1 - p) for p in pi) / (q - 1)
    return (pa - pe) / (1 - pe) if pe < 1 else float("nan")


def wilson(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_bootstrap(
    by_cluster: Mapping[str, list[bool]], draws: int = 5000, seed: int = 2026072813
) -> tuple[float, float]:
    """Resample *source papers*, not candidates.

    Candidates are nested in source papers, and one survey can contribute many
    windows. A binomial interval over candidates would compute uncertainty at
    the wrong unit -- exactly the error this paper is about -- so every rate we
    report over the census is given a paper-clustered interval instead.
    """
    keys = list(by_cluster)
    if not keys:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    draws_out = []
    for _ in range(draws):
        picked = [rng.choice(keys) for _ in keys]
        values = [v for k in picked for v in by_cluster[k]]
        if values:
            draws_out.append(sum(values) / len(values))
    if not draws_out:
        return (float("nan"), float("nan"))
    draws_out.sort()
    lo = draws_out[int(0.025 * len(draws_out))]
    hi = draws_out[min(len(draws_out) - 1, int(0.975 * len(draws_out)))]
    return (lo, hi)


def leave_one_cluster_out(by_cluster: Mapping[str, list[bool]]) -> tuple[float, float]:
    keys = list(by_cluster)
    if len(keys) < 2:
        return (float("nan"), float("nan"))
    rates = []
    for k in keys:
        values = [v for kk, vv in by_cluster.items() if kk != k for v in vv]
        if values:
            rates.append(sum(values) / len(values))
    return (min(rates), max(rates)) if rates else (float("nan"), float("nan"))



def clustered_agreement(
    labels_by_item: Mapping[str, list[str]],
    cluster_of: Mapping[str, str],
    statistic,
    draws: int = 2000,
    seed: int = 2026072814,
) -> dict[str, float]:
    """Bootstrap an agreement statistic by resampling *source papers*.

    Candidate windows are nested in source papers, and a single survey can
    contribute dozens of them. An interval computed over candidates would
    compute uncertainty at the wrong unit, which is the error this paper is
    about, so every agreement statistic we report over the census is given a
    paper-clustered interval.
    """
    by_cluster: dict[str, list[list[str]]] = defaultdict(list)
    for item, row in labels_by_item.items():
        by_cluster[cluster_of.get(item, item)].append(row)
    keys = list(by_cluster)
    if len(keys) < 2:
        return {}
    point = statistic(list(labels_by_item.values()))
    rng = random.Random(seed)
    draws_out = []
    for _ in range(draws):
        picked = [rng.choice(keys) for _ in keys]
        rows = [r for k in picked for r in by_cluster[k]]
        if len(rows) > 3:
            value = statistic(rows)
            if value == value:
                draws_out.append(value)
    if not draws_out:
        return {"point": point}
    draws_out.sort()
    return {
        "point": point,
        "ci95": [
            draws_out[int(0.025 * len(draws_out))],
            draws_out[min(len(draws_out) - 1, int(0.975 * len(draws_out)))],
        ],
        "n_clusters": len(keys),
        "draws": len(draws_out),
    }


def clustered_difference(
    labels_a: Mapping[str, list[str]],
    labels_b: Mapping[str, list[str]],
    cluster_of: Mapping[str, str],
    statistic,
    draws: int = 2000,
    seed: int = 2026072815,
) -> dict[str, float]:
    """Paper-clustered interval for the difference of two agreement statistics.

    Both statistics are recomputed on the *same* resampled papers, so the
    interval accounts for the correlation between them.
    """
    shared = sorted(set(labels_a) & set(labels_b))
    by_cluster: dict[str, list[str]] = defaultdict(list)
    for item in shared:
        by_cluster[cluster_of.get(item, item)].append(item)
    keys = list(by_cluster)
    if len(keys) < 2 or not shared:
        return {}
    point = statistic([labels_a[i] for i in shared]) - statistic(
        [labels_b[i] for i in shared]
    )
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        picked = [rng.choice(keys) for _ in keys]
        items = [i for k in picked for i in by_cluster[k]]
        if len(items) < 4:
            continue
        va = statistic([labels_a[i] for i in items])
        vb = statistic([labels_b[i] for i in items])
        if va == va and vb == vb:
            out.append(va - vb)
    if not out:
        return {"point": point}
    out.sort()
    return {
        "point": point,
        "ci95": [out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))]],
        "share_above_zero": sum(v > 0 for v in out) / len(out),
        "draws": len(out),
        "n_clusters": len(keys),
    }


def majority(values: list[str]) -> str | None:
    counts = Counter(values)
    top, n = counts.most_common(1)[0]
    return top if n >= 2 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding"
    )
    parser.add_argument(
        "--judges",
        default="coderA_gpt5mini,coderB_claudeopus46,coderC_gemini31pro",
        help=(
            "comma-separated judge file stems to analyse. Defaults to the "
            "three-judge primary panel; pass an explicit list to analyse the "
            "tier-by-developer control panel, or an empty string for every "
            "judge present."
        ),
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl",
    )
    parser.add_argument(
        "--output", type=Path, default=SUPPLEMENT / "cross_paper_census.json"
    )
    parser.add_argument(
        "--ledger", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv"
    )
    parser.add_argument(
        "--development-dir",
        type=Path,
        default=SUPPLEMENT / "cross_paper_coding_dev",
        help="codings from the declared codebook-development pass; the "
        "candidates they cover are excluded from the primary census",
    )
    parser.add_argument("--include-development", action="store_true")
    parser.add_argument(
        "--provenance-dir", type=Path, default=SUPPLEMENT / "cross_paper_provenance"
    )
    args = parser.parse_args()

    windows = {}
    for line in args.candidates.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            windows[row["candidate_id"]] = row

    per_judge: dict[str, dict[str, dict]] = {}
    only = {j.strip() for j in (args.judges or "").split(",") if j.strip()}
    for path in sorted(args.coding_dir.glob("*.jsonl")):
        name = path.stem
        if name.startswith("smoke"):
            continue
        if only and name not in only:
            continue
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed"):
                table[row["candidate_id"]] = row
        if table:
            per_judge[name] = table
    judges = sorted(per_judge)
    if only:
        missing = sorted(only - set(judges))
        if missing:
            raise SystemExit(f"requested judges not found: {missing}")
    if len(judges) < 2:
        raise SystemExit(f"need at least two judges, found {judges}")

    common = set.intersection(*(set(per_judge[j]) for j in judges))
    common &= set(windows)
    all_coded = sorted(common)

    # The codebook was revised once after a development pass. Candidates that
    # pass covered are excluded from the primary census so that the reported
    # numbers are not contaminated by instrument development on the same items.
    development: set[str] = set()
    if args.development_dir.exists():
        dev_tables = []
        for path in sorted(args.development_dir.glob("*.jsonl")):
            ids = set()
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("parsed"):
                        ids.add(row["candidate_id"])
            if ids:
                dev_tables.append(ids)
        if dev_tables:
            development = set.intersection(*dev_tables)
    ordered = (
        all_coded
        if args.include_development
        else [cid for cid in all_coded if cid not in development]
    )
    print(f"judges: {judges}")
    print(f"candidates coded by all judges: {len(all_coded)} of {len(windows)}")
    print(f"development pass covered: {len(development)}; held out: {len(ordered)}")

    elig_labels = [
        [str(bool(per_judge[j][cid]["parsed"].get("eligible"))) for j in judges]
        for cid in ordered
    ]
    eligible = [
        cid
        for cid, row in zip(ordered, elig_labels)
        if sum(v == "True" for v in row) >= 2
    ]
    unanimous_eligible = [
        cid
        for cid, row in zip(ordered, elig_labels)
        if all(v == "True" for v in row)
    ]

    agreement: dict[str, dict[str, float]] = {}
    agreement["eligible"] = {
        "observed": observed_agreement(elig_labels),
        "fleiss_kappa": fleiss_kappa(elig_labels),
        "gwet_ac1": gwet_ac1(elig_labels),
        "n_items": len(elig_labels),
    }
    for a, b in combinations(judges, 2):
        agreement["eligible"][f"cohen_kappa_{a}__{b}"] = cohen_kappa(
            [str(bool(per_judge[a][cid]["parsed"].get("eligible"))) for cid in ordered],
            [str(bool(per_judge[b][cid]["parsed"].get("eligible"))) for cid in ordered],
        )

    def field_labels(field: str, ids: list[str]) -> list[list[str]]:
        return [
            [str(per_judge[j][cid]["parsed"].get(field, "")).lower() or "missing" for j in judges]
            for cid in ids
        ]

    for field in (*COORDINATES, "verdict"):
        labels = field_labels(field, eligible)
        if not labels:
            continue
        entry = {
            "observed": observed_agreement(labels),
            "fleiss_kappa": fleiss_kappa(labels),
            "gwet_ac1": gwet_ac1(labels),
            "n_items": len(labels),
        }
        for a, b in combinations(judges, 2):
            ia, ib = judges.index(a), judges.index(b)
            entry[f"cohen_kappa_{a}__{b}"] = cohen_kappa(
                [row[ia] for row in labels], [row[ib] for row in labels]
            )
        agreement[field] = entry

    verdict_labels = field_labels("verdict", eligible)
    verdict_majority = [majority(row) for row in verdict_labels]
    verdict_counts = Counter(v for v in verdict_majority if v)
    no_majority = sum(1 for v in verdict_majority if v is None)

    coordinate_violation = {}
    for field in COORDINATES:
        labels = field_labels(field, eligible)
        mismatches = 0
        decided = 0
        for row in labels:
            call = majority(row)
            if call is None:
                continue
            decided += 1
            mismatches += int(call == "mismatch")
        low, high = wilson(mismatches, decided)
        coordinate_violation[field] = {
            "n_with_majority": decided,
            "n_mismatch": mismatches,
            "rate": mismatches / decided if decided else float("nan"),
            "ci95": [low, high],
        }

    # Judges see the focus window plus surrounding context, so the quote check
    # must search the same text they were shown, not the window alone.
    text_dir = REPO / "manuscript" / "citation_audit" / "expanded_texts"
    text_cache: dict[str, list[str]] = {}

    def shown_text(cid: str, context_lines: int = 45) -> str:
        window = windows[cid]
        name = window["source_file"]
        if name not in text_cache:
            path = text_dir / name
            text_cache[name] = (
                path.read_text(encoding="utf-8", errors="replace").splitlines()
                if path.exists()
                else []
            )
        lines = text_cache[name]
        if not lines:
            return window["window_text"]
        lo = max(0, window["line_start"] - 1 - context_lines)
        hi = min(len(lines), window["line_end"] + context_lines)
        return "\n".join(lines[lo:hi])

    quote_ok, quote_total = 0, 0
    quote_verified_items: list[str] = []
    for cid in eligible:
        haystack = " ".join(shown_text(cid).split())
        item_ok = True
        for j in judges:
            quote = str(per_judge[j][cid]["parsed"].get("evidence_quote", "")).strip()
            if not quote:
                item_ok = False
                continue
            quote_total += 1
            probe = " ".join(quote.split())
            found = probe[:80] in haystack
            quote_ok += int(found)
            item_ok = item_ok and found
        if item_ok:
            quote_verified_items.append(cid)

    # Sensitivity: a share of codings support themselves with a quote that is
    # not in the passage the judge was shown.  A reviewer asked whether the
    # agreement statistics are driven by those codings.  We therefore recompute
    # every field on the subset of eligible items where *every* judge's quote
    # was located verbatim, and report the two side by side.
    quote_sensitivity: dict[str, dict] = {
        "n_eligible": len(eligible),
        "n_all_quotes_verified": len(quote_verified_items),
        "share": len(quote_verified_items) / len(eligible) if eligible else float("nan"),
    }
    for field in (*COORDINATES, "verdict"):
        rows_all = field_labels(field, eligible)
        rows_ok = field_labels(field, quote_verified_items)
        if not rows_all or not rows_ok:
            continue
        quote_sensitivity[field] = {
            "fleiss_kappa_all": fleiss_kappa(rows_all),
            "fleiss_kappa_quote_verified": fleiss_kappa(rows_ok),
            "gwet_ac1_all": gwet_ac1(rows_all),
            "gwet_ac1_quote_verified": gwet_ac1(rows_ok),
            "n_all": len(rows_all),
            "n_quote_verified": len(rows_ok),
        }

    # The census produces "narrows" on a vanishing share of items while the
    # worked ledger produces it on a third of cases.  That is a property of the
    # label space, not of the corpus: "narrows" requires the citing passage to
    # print the other side's value at a matched operating point, which the
    # windowed frame almost never contains, whereas a ledger case is assembled
    # from both papers' full texts.  We record the rate so the discrepancy is
    # reported rather than left for a reader to find.
    matched_available = 0
    for cid in eligible:
        calls = [
            str(per_judge[j][cid]["parsed"].get("matched_number", "")).strip().lower()
            for j in judges
        ]
        matched_available += int(
            any(c and c != "not_recoverable_from_text" for c in calls)
        )
    quote_sensitivity["narrows_label_space"] = {
        "n_eligible": len(eligible),
        "n_any_judge_recovered_matched_number": matched_available,
        "share": matched_available / len(eligible) if eligible else float("nan"),
        "note": (
            "a narrows verdict requires a matched operating point inside the "
            "window the judge was shown; the frame is a single passage, the "
            "ledger is two full texts"
        ),
    }

    matched_recoverable = 0
    for cid in eligible:
        calls = [
            str(per_judge[j][cid]["parsed"].get("matched_number", "")).strip().lower()
            for j in judges
        ]
        recoverable = [
            c for c in calls if c and c != "not_recoverable_from_text"
        ]
        matched_recoverable += int(len(recoverable) >= 2)

    papers = sorted({windows[cid]["cite_key"] for cid in eligible})

    # ---- second stage: transported vs re-implemented -------------------------
    # "Cross-paper juxtaposition" covers two populations. When the other system
    # was re-run inside this paper's harness the coordinates match by
    # construction and the contrast should survive; only a number transported
    # from the other paper is exposed to the failure mode this paper is about.
    provenance_tables: dict[str, dict[str, str]] = {}
    for path in sorted(args.provenance_dir.glob("*.jsonl")) if args.provenance_dir.exists() else []:
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            parsed = row.get("parsed") or {}
            value = str(parsed.get("provenance", "")).strip().lower()
            if value in {"transported", "reimplemented", "unclear"}:
                table[row["candidate_id"]] = value
        if table:
            provenance_tables[path.stem] = table

    provenance_block: dict[str, object] = {}
    if len(provenance_tables) >= 2:
        pj = sorted(provenance_tables)
        shared = [
            cid
            for cid in eligible
            if all(cid in provenance_tables[j] for j in pj)
        ]
        plabels = [[provenance_tables[j][cid] for j in pj] for cid in shared]
        call = {cid: majority(row) for cid, row in zip(shared, plabels)}
        counts = Counter(v for v in call.values() if v)
        by_class: dict[str, Counter] = defaultdict(Counter)
        for cid in shared:
            klass = call.get(cid) or "no_majority"
            verdict_row = [
                str(per_judge[j][cid]["parsed"].get("verdict", "")).lower() for j in judges
            ]
            by_class[klass][majority(verdict_row) or "no_majority"] += 1
        n_no_majority = sum(1 for v in call.values() if v is None)
        n_assigned = counts.get("transported", 0) + counts.get("reimplemented", 0)
        provenance_block = {
            "judges": pj,
            # every eligible window all provenance judges returned a parseable
            # label for.  This is NOT the denominator of the composition claim:
            # it includes windows the panel called "unclear" and windows with no
            # majority, neither of which is assigned a provenance class.
            "n_coded_by_all_judges": len(shared),
            # the denominator the composition claim uses
            "n_assigned_a_class": n_assigned,
            "n_unclassified": len(shared) - n_assigned,
            "agreement": {
                "observed": observed_agreement(plabels),
                "fleiss_kappa": fleiss_kappa(plabels),
                "gwet_ac1": gwet_ac1(plabels),
            },
            "counts": dict(counts),
            "no_majority": n_no_majority,
            "composition_check": {
                "transported_plus_reimplemented": n_assigned,
                "plus_unclear": counts.get("unclear", 0),
                "plus_no_majority": n_no_majority,
                "equals_coded_by_all_judges": (
                    n_assigned + counts.get("unclear", 0) + n_no_majority == len(shared)),
            },
            "verdict_by_provenance": {k: dict(v) for k, v in by_class.items()},
        }
        for klass, verdicts in by_class.items():
            n = sum(verdicts.values())
            not_surviving = n - verdicts.get("survives", 0) - verdicts.get("no_majority", 0)
            lo, hi = wilson(not_surviving, n)
            members = [cid for cid in shared if (call.get(cid) or "no_majority") == klass]
            by_paper: dict[str, list[bool]] = defaultdict(list)
            for cid in members:
                verdict_row = [
                    str(per_judge[j][cid]["parsed"].get("verdict", "")).lower()
                    for j in judges
                ]
                decided = majority(verdict_row)
                if decided is None:
                    continue
                by_paper[windows[cid]["cite_key"]].append(decided != "survives")
            clo, chi = cluster_bootstrap(by_paper)
            llo, lhi = leave_one_cluster_out(by_paper)
            provenance_block.setdefault("not_surviving_rate", {})[klass] = {
                "n": n,
                "n_not_surviving": not_surviving,
                "rate": not_surviving / n if n else float("nan"),
                "ci95_binomial_candidate_unit": [lo, hi],
                "n_source_papers": len(by_paper),
                "largest_paper_share": (
                    max((len(v) for v in by_paper.values()), default=0) / max(1, sum(len(v) for v in by_paper.values()))
                ),
                "ci95": [clo, chi],
                "ci95_unit": "source paper (cluster bootstrap)",
                "leave_one_paper_out_range": [llo, lhi],
            }

    # ---- descriptive vs inferential agreement ------------------------------
    # The three judges answer two kinds of question about the same items.
    # *Descriptive*: what is being compared, and how was the other number
    # obtained. *Inferential*: does the comparison survive the coordinate rule.
    # Reporting them separately, at the source-paper unit, is the census's main
    # result: reading a comparison is reproducible, adjudicating it is not.
    cluster_of = {cid: windows[cid]["cite_key"] for cid in windows}

    elig_labels = {
        cid: [str(bool(per_judge[j][cid]["parsed"].get("eligible"))) for j in judges]
        for cid in ordered
    }
    verdict_labels_map = {
        cid: [
            str(per_judge[j][cid]["parsed"].get("verdict", "")).lower() or "missing"
            for j in judges
        ]
        for cid in eligible
    }
    provenance_labels_map = {}
    if len(provenance_tables) >= 2:
        pj = sorted(provenance_tables)
        for cid in eligible:
            if all(cid in provenance_tables[j] for j in pj):
                provenance_labels_map[cid] = [provenance_tables[j][cid] for j in pj]

    decomposition = {
        "note": (
            "Descriptive judgments (what is compared; how the number was "
            "obtained) versus the inferential judgment (does the comparison "
            "survive), on the same items, by the same judges, with intervals "
            "bootstrapped over source papers."
        ),
        "population_note": (
            "Populations differ by construction and are named explicitly. "
            "'eligibility' is over every held-out candidate, because that is "
            "the question the screen poses of the whole frame. 'verdict', "
            "'provenance' and the coordinates are defined only where a "
            "majority of judges called the window eligible, so they are over "
            "the majority-eligible subset. A difference is only reported "
            "between statistics computed on the SAME items: "
            "'provenance_minus_verdict' and "
            "'eligibility_matched_minus_verdict' both use the "
            "majority-eligible subset, and 'eligibility_matched' is the "
            "eligibility statistic recomputed there so that the difference is "
            "a visible subtraction of two reported numbers. Conditioning on "
            "majority eligibility selects for windows whose eligibility labels "
            "already agreed, so 'eligibility_matched' is mechanically higher "
            "than 'eligibility'; both are reported and neither is presented "
            "as the other."
        ),
        "eligibility": clustered_agreement(elig_labels, cluster_of, gwet_ac1),
        "eligibility_matched": clustered_agreement(
            {cid: elig_labels[cid] for cid in verdict_labels_map if cid in elig_labels},
            cluster_of,
            gwet_ac1,
        ),
        "provenance": clustered_agreement(provenance_labels_map, cluster_of, gwet_ac1),
        "verdict": clustered_agreement(verdict_labels_map, cluster_of, gwet_ac1),
        "provenance_minus_verdict": clustered_difference(
            provenance_labels_map, verdict_labels_map, cluster_of, gwet_ac1
        ),
        "eligibility_matched_minus_verdict": clustered_difference(
            {cid: elig_labels[cid] for cid in verdict_labels_map if cid in elig_labels},
            verdict_labels_map,
            cluster_of,
            gwet_ac1,
        ),
    }
    # Fleiss' kappa for every field reported as AC_1.  The submitted version
    # reported only AC_1; a reviewer correctly observed that kappa tells a
    # different story for the five coordinates, and that omitting it is not a
    # licence the "skewed marginals" argument grants.  Both are reported.
    kappa_maps = {
        "eligibility": elig_labels,
        "eligibility_matched": {
            cid: elig_labels[cid] for cid in verdict_labels_map if cid in elig_labels
        },
        "provenance": provenance_labels_map,
        "verdict": verdict_labels_map,
    }
    for field in COORDINATES:
        kappa_maps[f"coordinate_{field}"] = {
            cid: [
                str(per_judge[j][cid]["parsed"].get(field, "")).lower() or "missing"
                for j in judges
            ]
            for cid in eligible
        }
    for name, mapping in kappa_maps.items():
        if not mapping:
            continue
        entry = decomposition.setdefault(name, {})
        kd = clustered_agreement(mapping, cluster_of, fleiss_kappa)
        entry["fleiss_kappa"] = kd.get("point")
        entry["fleiss_kappa_ci95"] = kd.get("ci95")
    # The same two differences under Fleiss' kappa.  This matters: the
    # eligibility gap is large under AC_1 and vanishes (indeed reverses) under
    # kappa, because on the majority-eligible subset almost every window is
    # labelled eligible and AC_1 rewards that prevalence.  The provenance gap
    # is the one that survives both statistics, so it is the one the paper
    # rests the descriptive-versus-inferential claim on.
    if provenance_labels_map and verdict_labels_map:
        decomposition["provenance_minus_verdict_kappa"] = clustered_difference(
            provenance_labels_map, verdict_labels_map, cluster_of, fleiss_kappa
        )
    if verdict_labels_map:
        decomposition["eligibility_matched_minus_verdict_kappa"] = clustered_difference(
            {cid: elig_labels[cid] for cid in verdict_labels_map if cid in elig_labels},
            verdict_labels_map,
            cluster_of,
            fleiss_kappa,
        )
    for field in COORDINATES:
        decomposition[f"coordinate_{field}"] = clustered_agreement(
            {
                cid: [
                    str(per_judge[j][cid]["parsed"].get(field, "")).lower() or "missing"
                    for j in judges
                ]
                for cid in eligible
            },
            cluster_of,
            gwet_ac1,
        )
        kd = clustered_agreement(kappa_maps[f"coordinate_{field}"], cluster_of, fleiss_kappa)
        decomposition[f"coordinate_{field}"]["fleiss_kappa"] = kd.get("point")
        decomposition[f"coordinate_{field}"]["fleiss_kappa_ci95"] = kd.get("ci95")

    payload = {
        "schema_version": "cross-paper-census-v2",
        "agreement_decomposition": decomposition,
        "judges": {
            name: sorted({row["judge_model"] for row in per_judge[name].values()})
            for name in judges
        },
        "frame": {
            "n_candidates": len(windows),
            "n_coded_by_all_judges": len(all_coded),
            "n_development": len(development),
            "n_heldout": len(ordered),
            "development_included": bool(args.include_development),
            "n_eligible_majority": len(eligible),
            "n_eligible_unanimous": len(unanimous_eligible),
            "n_papers_contributing_eligible": len(papers),
            "papers": papers,
        },
        "agreement": agreement,
        "verdict_majority": {
            **{v: verdict_counts.get(v, 0) for v in VERDICTS},
            "no_majority": no_majority,
            "n": len(eligible),
        },
        "verdict_shares": {
            v: (verdict_counts.get(v, 0) / len(eligible) if eligible else float("nan"))
            for v in VERDICTS
        },
        "verdict_ci95": {
            v: list(wilson(verdict_counts.get(v, 0), len(eligible))) for v in VERDICTS
        },
        "coordinate_violation": coordinate_violation,
        "evidence_quote_check": {
            "checked": quote_total,
            "found_in_window": quote_ok,
            "rate": quote_ok / quote_total if quote_total else float("nan"),
        },
        "matched_number_recoverable_by_majority": matched_recoverable,
        "quote_verified_sensitivity": quote_sensitivity,
        "provenance": provenance_block,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    import csv as _csv

    with args.ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.writer(handle)
        writer.writerow(
            ["candidate_id", "cite_key", "source_file", "line_start", "line_end"]
            + [f"{j}_verdict" for j in judges]
            + ["majority_verdict"]
            + [f"majority_{c}" for c in COORDINATES]
            + ["comparison_claim"]
        )
        for cid, row in zip(eligible, verdict_labels):
            window = windows[cid]
            claims = [
                str(per_judge[j][cid]["parsed"].get("comparison_claim", "")) for j in judges
            ]
            writer.writerow(
                [cid, window["cite_key"], window["source_file"], window["line_start"], window["line_end"]]
                + row
                + [majority(row) or "no_majority"]
                + [
                    majority(
                        [
                            str(per_judge[j][cid]["parsed"].get(c, "")).lower()
                            for j in judges
                        ]
                    )
                    or "no_majority"
                    for c in COORDINATES
                ]
                + [max(claims, key=len)]
            )

    print(f"\neligible (>=2/3): {len(eligible)}  unanimous: {len(unanimous_eligible)}")
    print(f"papers contributing: {len(papers)}")
    print("verdict (majority):", dict(verdict_counts), f"no_majority={no_majority}")
    print("\nagreement:")
    for field, entry in agreement.items():
        print(
            f"  {field:<10} observed={entry['observed']:.3f} "
            f"Fleiss k={entry['fleiss_kappa']:.3f} "
            f"Gwet AC1={entry['gwet_ac1']:.3f} (n={entry['n_items']})"
        )
    print("\ncoordinate mismatch rate (majority):")
    for field, entry in coordinate_violation.items():
        print(
            f"  {field}: {entry['n_mismatch']}/{entry['n_with_majority']} = "
            f"{entry['rate']:.3f} CI[{entry['ci95'][0]:.3f}, {entry['ci95'][1]:.3f}]"
        )
    print(
        f"\nevidence quotes found verbatim in window: "
        f"{payload['evidence_quote_check']['found_in_window']}/"
        f"{payload['evidence_quote_check']['checked']}"
    )
    if provenance_block:
        print("\nprovenance (majority of independent judges):")
        print(f"  counts: {provenance_block['counts']}, "
              f"no_majority={provenance_block['no_majority']}")
        a = provenance_block["agreement"]
        print(f"  agreement observed={a['observed']:.3f} "
              f"Fleiss k={a['fleiss_kappa']:.3f} Gwet AC1={a['gwet_ac1']:.3f}")
        for klass, entry in sorted(provenance_block["not_surviving_rate"].items()):
            print(
                f"  {klass:<16} {entry['n_not_surviving']}/{entry['n']} = "
                f"{entry['rate']:.3f}  paper-clustered CI"
                f"[{entry['ci95'][0]:.3f}, {entry['ci95'][1]:.3f}]  "
                f"papers={entry['n_source_papers']} "
                f"largest={entry['largest_paper_share']:.2f} "
                f"LOO[{entry['leave_one_paper_out_range'][0]:.3f}, "
                f"{entry['leave_one_paper_out_range'][1]:.3f}]"
            )
    print("\ndescriptive vs inferential agreement (paper-clustered):")
    for name in (
        "provenance",
        "eligibility",
        "eligibility_matched",
        "verdict",
    ):
        entry = decomposition.get(name) or {}
        if entry.get("ci95"):
            kap = entry.get("fleiss_kappa")
            kaps = f"  kappa={kap:+.3f}" if kap is not None else ""
            print(
                f"  {name:<20} AC1={entry['point']:.3f}  "
                f"CI[{entry['ci95'][0]:.3f}, {entry['ci95'][1]:.3f}]  "
                f"papers={entry['n_clusters']}{kaps}"
            )
    for field in COORDINATES:
        entry = decomposition.get(f"coordinate_{field}") or {}
        if entry.get("point") is not None:
            kap = entry.get("fleiss_kappa")
            print(
                f"  coordinate {field:<9} AC1={entry['point']:.3f}"
                + (f"  kappa={kap:+.3f}" if kap is not None else "")
            )
    for name in (
        "provenance_minus_verdict",
        "eligibility_matched_minus_verdict",
        "provenance_minus_verdict_kappa",
        "eligibility_matched_minus_verdict_kappa",
    ):
        entry = decomposition.get(name) or {}
        if entry.get("ci95"):
            print(
                f"  {name:<34} {entry['point']:+.3f}  "
                f"CI[{entry['ci95'][0]:+.3f}, {entry['ci95'][1]:+.3f}]  "
                f"P(>0)={entry['share_above_zero']:.3f} "
                f"({entry.get('draws', 0)} draws)"
            )
    print(f"\nwrote {args.output}\nwrote {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
