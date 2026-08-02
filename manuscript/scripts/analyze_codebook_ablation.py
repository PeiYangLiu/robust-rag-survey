#!/usr/bin/env python3
"""Codebook ablation on the real corpus (reviewer W4).

Three judges, one frontier checkpoint per developer, code the identical
1,703-window frame three times.  Only the instrument changes:

  five    the released five-coordinate codebook;
  c1c4    the two non-degenerate coordinates only;
  direct  no coordinates, the comparability question asked in one step.

Everything else -- passage, context window, ordering seed, output schema,
decision rule, worked examples -- is held fixed, and every arm is scored on the
same item population, defined by the nine-judge pool and so independent of any
arm.  The contrast answers the reviewer's question: is verdict disagreement a
property of the adjudication task, or of a schema in which one coordinate is
mismatched on essentially every item by construction?

Writes ``supplement/codebook_ablation.json`` and ``tables/codebook_ablation.tex``.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
TAB = REPO / "manuscript" / "tables"

JUDGES = {
    "coderB_claudeopus46": ("Anthropic", "claude-opus-4.6"),
    "coderC_gemini31pro": ("Google", "gemini-3.1-pro-preview"),
    "coderI_gpt54": ("OpenAI", "gpt-5.4"),
}
ARMS = ("five", "c1c4", "direct")
ARM_LABEL = {
    "five": "Five coordinates (released)",
    "c1c4": "C1 and C4 only",
    "direct": "No coordinates, asked directly",
}


def fleiss_kappa(rows):
    rows = [r for r in rows if r]
    if not rows:
        return float("nan")
    n = len(rows[0])
    cats = sorted({v for r in rows for v in r})
    if len(cats) < 2:
        return float("nan")
    idx = {c: i for i, c in enumerate(cats)}
    p_bar, marg = 0.0, [0.0] * len(cats)
    for r in rows:
        counts = [0] * len(cats)
        for v in r:
            counts[idx[v]] += 1
        p_bar += (sum(c * c for c in counts) - n) / (n * (n - 1))
        for i, c in enumerate(counts):
            marg[i] += c
    p_bar /= len(rows)
    total = len(rows) * n
    p_e = sum((m / total) ** 2 for m in marg)
    return float("nan") if abs(1 - p_e) < 1e-12 else (p_bar - p_e) / (1 - p_e)


def gwet_ac1(rows):
    rows = [r for r in rows if r]
    if not rows:
        return float("nan")
    n = len(rows[0])
    cats = sorted({v for r in rows for v in r})
    if len(cats) < 2:
        return 1.0
    idx = {c: i for i, c in enumerate(cats)}
    p_bar, marg = 0.0, [0.0] * len(cats)
    for r in rows:
        counts = [0] * len(cats)
        for v in r:
            counts[idx[v]] += 1
        p_bar += (sum(c * c for c in counts) - n) / (n * (n - 1))
        for i, c in enumerate(counts):
            marg[i] += c
    p_bar /= len(rows)
    total = len(rows) * n
    pis = [m / total for m in marg]
    q = len(cats)
    p_e = sum(p * (1 - p) for p in pis) / (q - 1)
    return float("nan") if abs(1 - p_e) < 1e-12 else (p_bar - p_e) / (1 - p_e)


def clustered_pair(rows_a, rows_b, clusters, stat, draws=2000, seed=2026080201):
    """Bootstrap the difference between two arms, resampling source papers."""
    by_cluster = defaultdict(list)
    for i, key in enumerate(clusters):
        by_cluster[key].append(i)
    keys = list(by_cluster)
    obs = stat(rows_a) - stat(rows_b)
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        picked = [rng.choice(keys) for _ in keys]
        idx = [i for k in picked for i in by_cluster[k]]
        if len(idx) < 20:
            continue
        va = stat([rows_a[i] for i in idx])
        vb = stat([rows_b[i] for i in idx])
        if va == va and vb == vb:
            out.append(va - vb)
    if not out:
        return {"difference": obs}
    out.sort()
    return {
        "difference": obs,
        "ci95": [out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))]],
        "share_above_zero": sum(1 for v in out if v > 0) / len(out),
        "draws": len(out),
        "n_clusters": len(keys),
    }


def load(path: Path, key: str = "candidate_id"):
    table = {}
    if not path.exists():
        return table
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("parsed"):
            table[row[key]] = row
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--five-dir", type=Path, default=SUP / "cross_paper_coding")
    ap.add_argument("--arms-root", type=Path, default=SUP / "cross_paper_coding_arms")
    ap.add_argument(
        "--candidates", type=Path, default=SUP / "cross_paper_frame_candidates.jsonl"
    )
    ap.add_argument("--tier", type=Path, default=SUP / "cross_paper_tier_control.json")
    ap.add_argument("--output", type=Path, default=SUP / "codebook_ablation.json")
    args = ap.parse_args()

    windows = {}
    for line in args.candidates.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            windows[row["candidate_id"]] = row
    cluster_of = {cid: w["cite_key"] for cid, w in windows.items()}

    tables = {}
    for arm in ARMS:
        for judge in JUDGES:
            path = (
                args.five_dir / f"{judge}.jsonl"
                if arm == "five"
                else args.arms_root / arm / f"{judge}.jsonl"
            )
            tables[(arm, judge)] = load(path)

    coverage = {
        f"{arm}/{judge}": len(set(tables[(arm, judge)]) & set(windows)) / len(windows)
        for arm in ARMS
        for judge in JUDGES
    }
    for name, cov in sorted(coverage.items()):
        print(f"  {name:38s} {cov:6.1%}")

    # One population for every arm, defined by the nine-judge pool so that no
    # arm can be scored on a subset its own eligibility labels selected.
    tier = json.loads(args.tier.read_text(encoding="utf-8")) if args.tier.exists() else {}
    pool_judges = tier.get("pool", {}).get("judges", [])
    pool_eligible = None
    if pool_judges:
        pool_tables = {j: load(args.five_dir / f"{j}.jsonl") for j in pool_judges}
        common = set.intersection(*(set(t) for t in pool_tables.values())) & set(windows)
        pool_eligible = {
            cid
            for cid in common
            if sum(bool(pool_tables[j][cid]["parsed"].get("eligible")) for j in pool_judges)
            * 2
            > len(pool_judges)
        }
    covered = set.intersection(*(set(t) for t in tables.values())) & set(windows)
    items = sorted((pool_eligible & covered) if pool_eligible else covered)
    print(f"  common analysable items across all arms and judges: {len(items)}")

    clusters = [cluster_of[cid] for cid in items]
    results = {
        "coverage": coverage,
        "n_items": len(items),
        "judges": {j: list(v) for j, v in JUDGES.items()},
        "item_population": (
            "windows a majority of the nine-judge pool called eligible, "
            "intersected with windows every arm and judge coded"
        ),
        "arms": {},
    }
    verdict_rows = {}
    for arm in ARMS:
        rows = [
            [
                str(tables[(arm, j)][cid]["parsed"].get("verdict", "")).lower() or "missing"
                for j in JUDGES
            ]
            for cid in items
        ]
        verdict_rows[arm] = rows
        marginals = {
            j: dict(
                Counter(
                    str(tables[(arm, j)][cid]["parsed"].get("verdict", "")).lower()
                    for cid in items
                )
            )
            for j in JUDGES
        }
        entry = {
            "verdict_kappa": fleiss_kappa(rows),
            "verdict_ac1": gwet_ac1(rows),
            "unanimous_share": sum(1 for r in rows if len(set(r)) == 1) / len(rows),
            "per_judge_marginal": marginals,
            "survives_share_by_judge": {
                j: marginals[j].get("survives", 0) / len(items) for j in JUDGES
            },
        }
        for a, b in combinations(sorted(JUDGES), 2):
            ia, ib = list(JUDGES).index(a), list(JUDGES).index(b)
            entry[f"pair_{a}__{b}"] = fleiss_kappa(
                [[r[ia], r[ib]] for r in rows]
            )
        results["arms"][arm] = entry
        print(
            f"  {arm:7s} verdict kappa={entry['verdict_kappa']:+.3f} "
            f"AC1={entry['verdict_ac1']:.3f} unanimous={entry['unanimous_share']:.3f} "
            f"survives share by judge="
            + ", ".join(f"{v:.2f}" for v in entry["survives_share_by_judge"].values())
        )

    results["contrasts"] = {}
    for a, b in (("c1c4", "five"), ("direct", "five"), ("direct", "c1c4")):
        results["contrasts"][f"{a}_minus_{b}"] = clustered_pair(
            verdict_rows[a], verdict_rows[b], clusters, fleiss_kappa
        )
        d = results["contrasts"][f"{a}_minus_{b}"]
        ci = d.get("ci95")
        print(
            f"  {a} - {b}: {d['difference']:+.3f}"
            + (f"  CI[{ci[0]:+.3f},{ci[1]:+.3f}]  P(>0)={d['share_above_zero']:.3f}" if ci else "")
        )

    # C3's prevalence, which motivates the ablation
    c3 = [
        str(tables[("five", j)][cid]["parsed"].get("c3", "")).lower()
        for cid in items
        for j in JUDGES
    ]
    results["c3_label_distribution"] = dict(Counter(c3))
    results["c3_mismatch_share"] = c3.count("mismatch") / len(c3)
    print(f"  C3 labelled mismatch on {results['c3_mismatch_share']:.1%} of judge-item cells")

    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    write_table(results)
    return 0


def write_table(results: dict) -> None:
    rows = []
    for arm in ARMS:
        entry = results["arms"].get(arm)
        if not entry:
            continue
        contrast = results["contrasts"].get(f"{arm}_minus_five")
        if arm == "five":
            delta = "---"
        elif contrast and contrast.get("ci95"):
            delta = (
                f"{contrast['difference']:+.2f} "
                f"[{contrast['ci95'][0]:+.2f}, {contrast['ci95'][1]:+.2f}]"
            )
        else:
            delta = "--"
        shares = list(entry["survives_share_by_judge"].values())
        rows.append(
            " & ".join(
                [
                    ARM_LABEL[arm],
                    f"{entry['verdict_ac1']:.2f}",
                    f"{entry['verdict_kappa']:.2f}",
                    f"{entry['unanimous_share']:.2f}",
                    f"{min(shares):.2f}--{max(shares):.2f}",
                    delta,
                ]
            )
            + r" \\"
        )
    tab = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{@{}lrrrrl@{}}",
        r"\toprule",
        r"Instrument & $AC_1$ & $\kappa$ & Unan. & \emph{Survives} share & $\Delta\kappa$ \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{The verdict does not become reliable when the instrument is "
        r"simplified. The same three frontier judges, one per developer, code "
        r"the same \FrameCandidates{}-window frame three times, changing only "
        r"the codebook: the released five coordinates, the two coordinates that "
        r"are not degenerate across systems, and no coordinates at all. All "
        r"three arms are scored on the same "
        + f"{results['n_items']:,}"
        + r" windows. $\Delta\kappa$ is against the five-coordinate arm with a "
        r"95\% interval resampling source papers. \emph{Survives} share is the "
        r"range across the three judges of how often each calls a comparison "
        r"sound; the spread, not the noise, is what fails to port.}",
        r"\label{tab:codebook-ablation}",
        r"\end{table}",
    ]
    (TAB / "codebook_ablation.tex").write_text("\n".join(tab) + "\n", encoding="utf-8")
    print(f"wrote {TAB / 'codebook_ablation.tex'}")


if __name__ == "__main__":
    raise SystemExit(main())
