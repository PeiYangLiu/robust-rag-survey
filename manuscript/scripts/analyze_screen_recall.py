#!/usr/bin/env python3
"""Estimate what the screen misses, and re-weight the composition (W5).

The manuscript's one positive claim is a *composition*: most cross-paper
juxtapositions re-implement the other system rather than transporting its
number.  That was measured inside the screen's own output, and the screen's
first stratum is baseline-table language -- the canonical home of a
re-implementation.  If transported juxtapositions are disproportionately
prose-borne, the share is partly an artefact of the inclusion criteria.

This script decides it.  The universe is every window that satisfies the
weakest necessary condition (a gazetteer system not the paper's own, and at
least one result-formatted number).  It splits into the screened frame and the
missed remainder; a uniform random sample of the remainder was coded by the
same three judges under the same two prompts.  From the two coded sets we
estimate, by class,

    recall(class) = eligible juxtapositions of that class inside the frame
                  / eligible juxtapositions of that class in the universe

and re-weight the composition to the universe.  Intervals resample source
papers in the missed sample, because papers, not windows, are the independent
unit.

Writes ``supplement/screen_recall_results.json`` and
``tables/screen_recall.tex``.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
TAB = REPO / "manuscript" / "tables"
DRAWS = 4000
SEED = 2026080461


def norm_prov(label: str) -> str:
    label = str(label or "").strip().lower().replace("-", "").replace(" ", "_")
    if label in ("reimplemented", "re_implemented"):
        return "reimplemented"
    if label.startswith("transport"):
        return "transported"
    return "unclear"


def majority(votes):
    top = Counter(votes).most_common()
    if top and (len(top) == 1 or top[0][1] > top[1][1]):
        return top[0][0]
    return None


def load_pass(root: Path, name: str, field: str):
    out = defaultdict(dict)
    d = root / name
    if not d.exists():
        return out
    for path in sorted(d.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            p = row.get("parsed") or {}
            if field in p:
                out[row["candidate_id"]][path.stem] = p[field]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=Path, default=SUP / "screen_recall_sample.jsonl")
    ap.add_argument("--pool", type=Path, default=SUP / "screen_recall_pool_summary.json")
    ap.add_argument("--runs", type=Path, default=SUP / "screen_recall_runs")
    ap.add_argument("--census", type=Path, default=SUP / "cross_paper_census.json")
    ap.add_argument("--out", type=Path, default=SUP / "screen_recall_results.json")
    args = ap.parse_args()

    pool = json.loads(args.pool.read_text(encoding="utf-8"))
    census = json.loads(args.census.read_text(encoding="utf-8"))
    sample = {}
    for line in args.sample.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            sample[r["candidate_id"]] = r

    elig_votes = load_pass(args.runs, "elig", "eligible")
    prov_votes = load_pass(args.runs, "prov", "provenance")
    judges = sorted({j for v in elig_votes.values() for j in v})

    coded = [cid for cid in sample if len(elig_votes.get(cid, {})) >= 2]
    rows = []
    for cid in coded:
        ev = [bool(v) for v in elig_votes[cid].values()]
        elig = majority(ev)
        prov = majority([norm_prov(v) for v in prov_votes.get(cid, {}).values()]) \
            if prov_votes.get(cid) else None
        rows.append({"candidate_id": cid, "cite_key": sample[cid]["cite_key"],
                     "eligible": bool(elig), "provenance": prov})

    n_missed = pool["n_missed_windows"]
    n_screened = pool["n_screened_windows"]
    n_universe = pool["n_universe_windows"]

    # frame-side quantities, from the census itself
    frame_coded = census["agreement"]["eligible"]["n_items"]
    frame_eligible = census["agreement"]["verdict"]["n_items"]
    frame_elig_rate = frame_eligible / frame_coded
    pc = census["provenance"]["counts"]
    frame_classified = pc["transported"] + pc["reimplemented"]
    frame_share_t = pc["transported"] / frame_classified
    frame_share_r = pc["reimplemented"] / frame_classified

    def estimate(sample_rows):
        n = len(sample_rows)
        if not n:
            return None
        elig = [r for r in sample_rows if r["eligible"]]
        p_elig = len(elig) / n
        cls = Counter(r["provenance"] for r in elig
                      if r["provenance"] in ("transported", "reimplemented"))
        n_cls = sum(cls.values())
        share_t = cls["transported"] / n_cls if n_cls else 0.0
        share_r = cls["reimplemented"] / n_cls if n_cls else 0.0
        # classified juxtapositions per window, by class
        rate_t_missed = p_elig * (n_cls / len(elig) if elig else 0) * share_t
        rate_r_missed = p_elig * (n_cls / len(elig) if elig else 0) * share_r
        rate_frame = frame_elig_rate * (frame_classified / frame_eligible)
        frame_t = n_screened * rate_frame * frame_share_t
        frame_r = n_screened * rate_frame * frame_share_r
        missed_t = n_missed * rate_t_missed
        missed_r = n_missed * rate_r_missed
        tot_t, tot_r = frame_t + missed_t, frame_r + missed_r
        return {
            "missed_sample_n": n,
            "missed_eligible_rate": round(p_elig, 4),
            "missed_share_transported": round(share_t, 4),
            "missed_share_reimplemented": round(share_r, 4),
            "frame_eligible_rate": round(frame_elig_rate, 4),
            "frame_share_transported": round(frame_share_t, 4),
            "estimated_universe_transported": round(tot_t, 1),
            "estimated_universe_reimplemented": round(tot_r, 1),
            "recall_transported": round(frame_t / tot_t, 4) if tot_t else None,
            "recall_reimplemented": round(frame_r / tot_r, 4) if tot_r else None,
            "frame_reimplemented_share": round(frame_share_r, 4),
            "universe_reimplemented_share": round(tot_r / (tot_t + tot_r), 4)
            if (tot_t + tot_r) else None,
        }

    point = estimate(rows)

    # cluster bootstrap over source papers in the missed sample
    by_paper = defaultdict(list)
    for r in rows:
        by_paper[r["cite_key"]].append(r)
    papers = sorted(by_paper)
    rng = random.Random(SEED)
    boots = defaultdict(list)
    for _ in range(DRAWS):
        draw = []
        for _ in papers:
            draw.extend(by_paper[rng.choice(papers)])
        e = estimate(draw)
        if not e:
            continue
        for k in ("recall_transported", "recall_reimplemented",
                  "universe_reimplemented_share", "missed_eligible_rate"):
            if e[k] is not None:
                boots[k].append(e[k])
    ci = {}
    for k, vals in boots.items():
        vals.sort()
        ci[k] = [round(vals[int(0.025 * len(vals))], 4),
                 round(vals[min(len(vals) - 1, int(0.975 * len(vals)))], 4)]

    out = {
        "schema_version": "screen-recall-results-v1",
        "judges": judges,
        "n_universe_windows": n_universe,
        "n_screened_windows": n_screened,
        "n_missed_windows": n_missed,
        "n_missed_sampled": len(sample),
        "n_missed_coded": len(rows),
        "n_source_papers_in_sample": len(papers),
        "point_estimates": point,
        "cluster_bootstrap_ci95": ci,
        "bootstrap_draws": DRAWS,
        "estimand_note": (
            "recall(class) is the share of eligible, classified juxtapositions "
            "of that class in the universe that the screen surfaced. The "
            "universe composition re-weights the frame's own composition by the "
            "missed set's, which is what the composition claim requires if it is "
            "to leave the frame."),
    }
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    if point:
        def c(k):
            v = ci.get(k)
            return f"[{v[0]:.2f}, {v[1]:.2f}]" if v else "---"
        tex = (
            "\\begin{table}[t]\n\\centering\\scriptsize\n"
            "\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{@{}lrr@{}}\n\\toprule\n"
            "Quantity & Estimate & 95\\% CI \\\\\n\\midrule\n"
            f"Windows in the universe & {n_universe:,} & --- \\\\\n"
            f"\\quad surfaced by the screen & {n_screened:,} & --- \\\\\n"
            f"\\quad missed, sampled & {len(rows)} & --- \\\\\n\\midrule\n"
            f"Eligible rate, missed windows & {point['missed_eligible_rate']:.3f} & "
            f"{c('missed_eligible_rate')} \\\\\n"
            f"Eligible rate, screened windows & {point['frame_eligible_rate']:.3f} & --- \\\\\n"
            "\\midrule\n"
            f"Screen recall, transported & {point['recall_transported']:.3f} & "
            f"{c('recall_transported')} \\\\\n"
            f"Screen recall, re-implemented & {point['recall_reimplemented']:.3f} & "
            f"{c('recall_reimplemented')} \\\\\n\\midrule\n"
            f"Re-implemented share, in frame & {point['frame_reimplemented_share']:.3f} & --- \\\\\n"
            f"Re-implemented share, re-weighted & {point['universe_reimplemented_share']:.3f} & "
            f"{c('universe_reimplemented_share')} \\\\\n"
            "\\bottomrule\n\\end{tabular}\n"
            "\\caption{What the screen misses. The universe is every window "
            "under the screen's own windowing that names another paper's system "
            "and carries at least one result-formatted number; the screen's "
            "second-numeral requirement and its three surface strata are "
            "dropped, which are exactly the conditions that select for baseline "
            "tables. A uniform sample of the missed windows was coded by the "
            "same three judges under the same two prompts. Intervals resample "
            "source papers.}\n\\label{tab:screen-recall}\n\\end{table}\n")
        (TAB / "screen_recall.tex").write_text(tex, encoding="utf-8")

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
