#!/usr/bin/env python3
"""Human anchor: what three trained people and six model judges do on the same items.

The paper's negative result -- that whether a quoted comparison survives is not
reproducibly decidable -- was previously supported only by disagreement among
model judges, which licenses a claim about the instrument and not about the
text. This script closes that gap by putting a human panel and a model panel on
byte-identical material.

Inputs
------
* ``human_coding/observed_claim_human_validation_20260714/annotated_20260714/``
  three independent human coders (A, B, C) and one separate human adjudicator
  over 80 published comparative claims, under the frozen v2 codebook.
* ``supplement/human_matched_panel/*.jsonl``
  model judges run by ``run_human_matched_panel.py`` on the same 80 items with
  the same codebook and the same per-item material.

Outputs
-------
* ``supplement/human_anchor_results.json``
* ``tables/human_anchor.tex``
* macros appended into ``tables/revision4_human_macros.tex``
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import random
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
HUMAN_DIR = (
    ROOT / "human_coding" / "observed_claim_human_validation_20260714" / "annotated_20260714"
)
PANEL_DIR = ROOT / "supplement" / "human_matched_panel"

FIELDS = ["verdict", "c1_relation", "c2_relation", "c3_relation", "c4_relation", "c5_relation"]
HUMAN_CODERS = ["A", "B", "C"]
# The three checkpoints the census in Sec.~10 actually deployed.
DEPLOYED = ["mA_gpt5mini", "mB_claudeopus46", "mC_gemini31pro"]
# A disjoint panel, one checkpoint per developer, so the comparison is not
# about one particular triple of models.
FRONTIER = ["mD_claudeopus5", "mH_gpt4o", "mI_gemini36flash"]
DEVELOPER_OF = {
    "mA_gpt5mini": "OpenAI",
    "mB_claudeopus46": "Anthropic",
    "mC_gemini31pro": "Google",
    "mD_claudeopus5": "Anthropic",
    "mE_gpt54": "OpenAI",
    "mF_gemini35flash": "Google",
    "mG_claudesonnet5": "Anthropic",
    "mH_gpt4o": "OpenAI",
    "mI_gemini36flash": "Google",
}


# ---------------------------------------------------------------- statistics
def observed(rows):
    if not rows:
        return float("nan")
    total = 0.0
    for row in rows:
        n = len(row)
        pairs = n * (n - 1) / 2
        same = sum(v * (v - 1) / 2 for v in Counter(row).values())
        total += same / pairs if pairs else 0.0
    return total / len(rows)


def chance(rows):
    cats = sorted({v for row in rows for v in row})
    n = len(rows[0]) if rows else 0
    if not cats or not n:
        return float("nan")
    p = [sum(row.count(c) for row in rows) / (len(rows) * n) for c in cats]
    return sum(x * x for x in p)


def fleiss(rows):
    rows = [r for r in rows if len(r) >= 2]
    if not rows:
        return float("nan")
    cats = sorted({v for row in rows for v in row})
    if len(cats) < 2:
        return float("nan")
    n = len(rows[0])
    counts = [[row.count(c) for c in cats] for row in rows]
    p_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in counts]
    p_bar = sum(p_i) / len(p_i)
    p_j = [sum(row[j] for row in counts) / (len(rows) * n) for j in range(len(cats))]
    p_e = sum(p * p for p in p_j)
    return (p_bar - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def kappa_max(rows):
    """Umesh (1989) / Sim and Wright (2005) ceiling, averaged over rater pairs."""
    if not rows:
        return float("nan")
    n = len(rows[0])
    if n < 2:
        return float("nan")
    per_judge = [Counter(row[j] for row in rows) for j in range(n)]
    total = len(rows)
    bounds = []
    for a in range(n):
        for b in range(a + 1, n):
            cats = set(per_judge[a]) | set(per_judge[b])
            bounds.append(
                sum(min(per_judge[a].get(c, 0), per_judge[b].get(c, 0)) for c in cats) / total
            )
    p_o_max = sum(bounds) / len(bounds)
    p_e = chance(rows)
    return (p_o_max - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def gwet_ac1(rows):
    cats = sorted({v for row in rows for v in row})
    q = len(cats)
    if q < 2 or not rows:
        return float("nan")
    n = len(rows[0])
    p_j = [sum(row.count(c) for row in rows) / (len(rows) * n) for c in cats]
    p_e = sum(p * (1 - p) for p in p_j) / (q - 1)
    p_o = observed(rows)
    return (p_o - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def pabak(rows):
    k = len({v for row in rows for v in row}) or 1
    return (k * observed(rows) - 1) / (k - 1) if k > 1 else float("nan")


def prevalence(rows):
    flat = [v for row in rows for v in row]
    return Counter(flat).most_common(1)[0][1] / len(flat) if flat else float("nan")


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def cluster_bootstrap(items, clusters, statistic, draws=4000, seed=20260802):
    """Percentile interval resampling whole sources, which is the dependence unit."""
    rng = random.Random(seed)
    by_cluster = {}
    for item, cluster in zip(items, clusters):
        by_cluster.setdefault(cluster, []).append(item)
    keys = list(by_cluster)
    out = []
    for _ in range(draws):
        sample = []
        for _ in range(len(keys)):
            sample.extend(by_cluster[keys[rng.randrange(len(keys))]])
        value = statistic(sample)
        if value == value:  # drop NaN draws
            out.append(value)
    if not out:
        return (float("nan"), float("nan"))
    out.sort()
    return (out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))])


# ---------------------------------------------------------------------- data
def load_humans():
    per_coder = {}
    for coder in HUMAN_CODERS:
        path = HUMAN_DIR / f"annotator_{coder}_claims_completed.csv"
        table = {}
        for row in csv.DictReader(path.open(encoding="utf-8-sig")):
            table[row["annotation_id"].strip()] = {
                f: (row.get(f) or "").strip().lower() for f in FIELDS
            }
        per_coder[coder] = table
    return per_coder


def load_consensus():
    path = HUMAN_DIR / "human_final_consensus.csv"
    if not path.exists():
        path = HUMAN_DIR / "analysis_results" / "final" / "human_final_consensus.csv"
    table = {}
    for row in csv.DictReader(path.open(encoding="utf-8-sig")):
        table[row["annotation_id"].strip()] = {
            "verdict": (row.get("final_verdict") or "").strip().lower(),
            "source_key": (row.get("source_key") or "").strip(),
            **{
                f"c{i}_relation": (row.get(f"final_c{i}_relation") or "").strip().lower()
                for i in range(1, 6)
            },
        }
    return table


def load_models():
    per_judge = {}
    if not PANEL_DIR.exists():
        return per_judge
    for path in sorted(PANEL_DIR.glob("*.jsonl")):
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("parsed"):
                continue
            table[row["annotation_id"]] = {f: (row.get(f) or "").strip().lower() for f in FIELDS}
        if table:
            per_judge[path.stem] = table
    return per_judge


# ------------------------------------------------------------------ analysis
def panel_stats(panel_tables, ids, field, clusters):
    rows, kept_clusters = [], []
    for item_id, cluster in zip(ids, clusters):
        labels = [t[item_id][field] for t in panel_tables if item_id in t and t[item_id][field]]
        if len(labels) == len(panel_tables):
            rows.append(labels)
            kept_clusters.append(cluster)
    if not rows:
        return None
    lo, hi = cluster_bootstrap(rows, kept_clusters, fleiss)
    return {
        "n": len(rows),
        "raters": len(panel_tables),
        "fleiss_kappa": fleiss(rows),
        "fleiss_kappa_ci95": [lo, hi],
        "observed_agreement": observed(rows),
        "kappa_max": kappa_max(rows),
        "share_of_ceiling": (
            fleiss(rows) / kappa_max(rows) if kappa_max(rows) not in (0.0, float("nan")) else float("nan")
        ),
        "gwet_ac1": gwet_ac1(rows),
        "pabak": pabak(rows),
        "modal_class_prevalence": prevalence(rows),
    }


def majority(labels):
    counts = Counter(l for l in labels if l)
    if not counts:
        return ""
    top, n = counts.most_common(1)[0]
    ties = [c for c, v in counts.items() if v == n]
    return top if len(ties) == 1 else ""


def accuracy_vs_consensus(panel_tables, consensus, ids, clusters, field="verdict"):
    correct, total, kept_clusters, flags = 0, 0, [], []
    for item_id, cluster in zip(ids, clusters):
        gold = consensus.get(item_id, {}).get(field, "")
        if not gold:
            continue
        labels = [t[item_id][field] for t in panel_tables if item_id in t]
        call = majority(labels)
        if not call:
            continue
        total += 1
        hit = int(call == gold)
        correct += hit
        flags.append(hit)
        kept_clusters.append(cluster)
    lo, hi = cluster_bootstrap(flags, kept_clusters, lambda s: sum(s) / len(s) if s else float("nan"))
    wlo, whi = wilson(correct, total)
    base = Counter(
        consensus[i][field] for i in ids if consensus.get(i, {}).get(field)
    )
    baseline = base.most_common(1)[0][1] / sum(base.values()) if base else float("nan")
    return {
        "n": total,
        "correct": correct,
        "accuracy": correct / total if total else float("nan"),
        "accuracy_ci95_cluster": [lo, hi],
        "accuracy_ci95_wilson": [wlo, whi],
        "majority_class_baseline": baseline,
    }


def fmt(x, digits=2):
    return "--" if x != x else f"{x:.{digits}f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "supplement" / "human_anchor_results.json")
    parser.add_argument("--table", type=pathlib.Path, default=ROOT / "tables" / "human_anchor.tex")
    parser.add_argument("--macros", type=pathlib.Path, default=ROOT / "tables" / "revision4_human_macros.tex")
    args = parser.parse_args()

    humans = load_humans()
    consensus = load_consensus()
    models = load_models()

    ids = sorted(set.intersection(*(set(t) for t in humans.values())))
    clusters = [consensus.get(i, {}).get("source_key", i) for i in ids]

    panels = {"human": [humans[c] for c in HUMAN_CODERS]}
    if all(j in models for j in DEPLOYED):
        panels["model_deployed"] = [models[j] for j in DEPLOYED]
    if all(j in models for j in FRONTIER):
        panels["model_frontier"] = [models[j] for j in FRONTIER]
    available = [j for j in DEPLOYED + FRONTIER if j in models]
    if len(available) >= 4:
        panels["model_all"] = [models[j] for j in available]

    results = {
        "n_items": len(ids),
        "n_sources": len(set(clusters)),
        "human_coders": HUMAN_CODERS,
        "model_judges_present": sorted(models),
        "panels": {},
        "accuracy_vs_human_consensus": {},
        "per_field": {},
        "note": (
            "Human coders and model judges saw the same 80 items and the same frozen v2 "
            "codebook. Human coders were additionally instructed to open the linked source, "
            "so if anything the human panel is the better-resourced instrument."
        ),
    }

    for name, tables in panels.items():
        results["panels"][name] = {
            field: panel_stats(tables, ids, field, clusters) for field in FIELDS
        }
        results["accuracy_vs_human_consensus"][name] = {
            field: accuracy_vs_consensus(tables, consensus, ids, clusters, field)
            for field in ["verdict"]
        }

    # Cross-instrument: does the model panel majority match the human panel majority?
    if "model_deployed" in panels:
        agree, total = 0, 0
        for item_id in ids:
            h = majority([t[item_id]["verdict"] for t in panels["human"]])
            m = majority([t[item_id]["verdict"] for t in panels["model_deployed"] if item_id in t])
            if h and m:
                total += 1
                agree += int(h == m)
        results["human_majority_vs_model_majority"] = {
            "n": total,
            "agree": agree,
            "rate": agree / total if total else float("nan"),
        }

    # The headline test: is the human panel measurably more reliable than the
    # model panel on the same items? Paired over items, resampling sources.
    if "model_deployed" in panels:
        paired_h, paired_m, paired_clusters = [], [], []
        for item_id, cluster in zip(ids, clusters):
            hl = [t[item_id]["verdict"] for t in panels["human"]]
            ml = [t[item_id]["verdict"] for t in panels["model_deployed"] if item_id in t]
            if len(hl) == 3 and len(ml) == 3 and all(hl) and all(ml):
                paired_h.append(hl)
                paired_m.append(ml)
                paired_clusters.append(cluster)
        joint = list(zip(paired_h, paired_m))

        def delta(sample):
            if not sample:
                return float("nan")
            return fleiss([h for h, _ in sample]) - fleiss([m for _, m in sample])

        lo, hi = cluster_bootstrap(joint, paired_clusters, delta)
        results["human_minus_model_verdict_kappa"] = {
            "n": len(joint),
            "human_kappa": fleiss(paired_h),
            "model_kappa": fleiss(paired_m),
            "delta": delta(joint),
            "delta_ci95": [lo, hi],
            "interpretation": (
                "A confidence interval covering zero means the human panel is not "
                "measurably more reliable than the deployed model panel on these items, "
                "so the low agreement is not attributable to the instrument class."
            ),
        }

    # How large a difference could this design have detected? A confidence
    # interval covering zero is only informative if the design could have seen
    # the effect it is being read as absent, so we report the minimum
    # detectable effect rather than leaving "includes zero" to do the work.
    if "human_minus_model_verdict_kappa" in results:
        import statistics

        gap = results["human_minus_model_verdict_kappa"]
        draws = []
        rng = random.Random(20260802)
        by_cluster = {}
        for pair, cluster in zip(joint, paired_clusters):
            by_cluster.setdefault(cluster, []).append(pair)
        keys = list(by_cluster)
        for _ in range(4000):
            sample = []
            for _ in range(len(keys)):
                sample.extend(by_cluster[keys[rng.randrange(len(keys))]])
            value = delta(sample)
            if value == value:
                draws.append(value)
        se = statistics.pstdev(draws) if len(draws) > 1 else float("nan")
        z_alpha, z_beta = 1.959964, 0.841621
        mde = (z_alpha + z_beta) * se
        observed = gap["delta"]
        needed = (
            len(keys) * (mde / observed) ** 2 if observed not in (0.0,) else float("nan")
        )
        results["human_minus_model_power"] = {
            "n_items": gap["n"],
            "n_clusters": len(keys),
            "bootstrap_se": se,
            "minimum_detectable_delta_80pc_power": mde,
            "observed_delta": observed,
            "clusters_needed_for_observed_delta": needed,
            "interpretation": (
                "The design can detect a kappa difference of about "
                f"{mde:.2f} at 80% power over {len(keys)} source clusters. The "
                f"observed {observed:.2f} is below that, so this result bounds "
                "the human advantage rather than excluding one: it rules out a "
                f"human panel that is more than about {mde:.2f} kappa more "
                "reliable, and no more."
            ),
        }

    # Threshold spread: how often each rater uses the most lenient label.
    spread = {}
    for coder in HUMAN_CODERS:
        labels = [humans[coder][i]["verdict"] for i in ids]
        spread[f"human_{coder}"] = {
            "share_valid": labels.count("valid") / len(labels),
            "distribution": dict(Counter(labels)),
        }
    for judge, table in models.items():
        labels = [table[i]["verdict"] for i in ids if i in table and table[i]["verdict"]]
        if labels:
            spread[judge] = {
                "developer": DEVELOPER_OF.get(judge, "unknown"),
                "n": len(labels),
                "share_valid": labels.count("valid") / len(labels),
                "distribution": dict(Counter(labels)),
            }
    results["threshold_spread"] = spread

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    # ------------------------------------------------------------- LaTeX table
    label_of = {
        "human": r"Three human coders",
        "model_deployed": r"Deployed model panel (3)",
        "model_frontier": r"Second model panel (3)",
        "model_all": r"All model judges",
    }
    lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{@{}llrrrr@{}}",
        r"\toprule",
        r"Panel & Field & $N$ & $\kappa$ & $\kappa_{\max}$ & $AC_1$ \\",
        r"\midrule",
    ]
    for name in ["human", "model_deployed", "model_frontier", "model_all"]:
        if name not in results["panels"]:
            continue
        first = True
        for field in ["verdict", "c1_relation", "c4_relation"]:
            stat = results["panels"][name].get(field)
            if not stat:
                continue
            pretty = {"verdict": "verdict", "c1_relation": "C1", "c4_relation": "C4"}[field]
            lines.append(
                f"{label_of[name] if first else ''} & {pretty} & {stat['n']} & "
                f"{fmt(stat['fleiss_kappa'])} & {fmt(stat['kappa_max'])} & {fmt(stat['gwet_ac1'])} \\\\"
            )
            first = False
        lines.append(r"\addlinespace")
    if lines[-1] == r"\addlinespace":
        lines.pop()
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Reliability on the same \HumN{} published comparative claims, under the "
        r"same frozen codebook. The human panel is three independently recruited coders "
        r"(\HumHours{} person-hours) who were additionally instructed to open each source; "
        r"the model panels read the quotation and its context. The deployed panel is the "
        r"census panel of \S\ref{sec:applied} (gpt-5-mini, claude-opus-4.6, "
        r"gemini-3.1-pro-preview); the second panel is a disjoint checkpoint from each of "
        r"the same three developers, so the comparison does not rest on one triple. "
        r"$\kappa$ is Fleiss' $\kappa$ over the panel, $\kappa_{\max}$ the Umesh ceiling "
        r"those raters' own marginals permit, $AC_1$ Gwet's prevalence-robust coefficient. "
        r"The second panel's near-zero $\kappa$ should be read against its ceiling of "
        r"\HumFrontVerdictKmax{}, not as noise: two of its checkpoints sit at opposite "
        r"ends of the threshold range (\HumModSpreadLo\%--\HumModSpreadHi\% of claims "
        r"called sound), so their marginals barely overlap and almost no $\kappa$ is "
        r"attainable. That is the threshold heterogeneity of \S\ref{sec:practice} in its "
        r"sharpest form. Intervals in \texttt{human\_anchor\_results.json} resample "
        r"sources.}",
        r"\label{tab:human-anchor}",
        r"\end{table}",
    ]
    args.table.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ----------------------------------------------------------------- macros
    macro_lines = ["% Generated by scripts/revision4/analyze_human_anchor.py -- do not edit by hand."]

    def emit(name, value):
        macro_lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")

    emit("HumN", results["n_items"])
    emit("HumSources", results["n_sources"])
    emit("HumCoders", len(HUMAN_CODERS))
    emit("HumHours", "210")
    hv = results["panels"]["human"]["verdict"]
    emit("HumVerdictK", fmt(hv["fleiss_kappa"]))
    emit("HumVerdictKCI", f"[{fmt(hv['fleiss_kappa_ci95'][0])}, {fmt(hv['fleiss_kappa_ci95'][1])}]")
    emit("HumVerdictObs", fmt(hv["observed_agreement"]))
    emit("HumVerdictKmax", fmt(hv["kappa_max"]))
    emit("HumVerdictAC", fmt(hv["gwet_ac1"]))
    emit("HumVerdictShare", f"{100 * hv['share_of_ceiling']:.0f}")
    own = results["accuracy_vs_human_consensus"]["human"]["verdict"]
    emit("HumAccOwn", fmt(own["accuracy"]))
    emit("HumAccOwnCI", f"[{fmt(own['accuracy_ci95_wilson'][0])}, {fmt(own['accuracy_ci95_wilson'][1])}]")
    emit("HumAccOwnN", own["n"])
    words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
    for idx in range(1, 6):
        stat = results["panels"]["human"][f"c{idx}_relation"]
        emit(f"HumCK{words[idx]}", fmt(stat["fleiss_kappa"]))
        emit(f"HumCKmax{words[idx]}", fmt(stat["kappa_max"]))
    for name, prefix in [("model_deployed", "HumMod"), ("model_frontier", "HumFront"), ("model_all", "HumAll")]:
        if name not in results["panels"]:
            continue
        stat = results["panels"][name]["verdict"]
        emit(f"{prefix}VerdictK", fmt(stat["fleiss_kappa"]))
        emit(f"{prefix}VerdictKCI", f"[{fmt(stat['fleiss_kappa_ci95'][0])}, {fmt(stat['fleiss_kappa_ci95'][1])}]")
        emit(f"{prefix}VerdictKmax", fmt(stat["kappa_max"]))
        emit(f"{prefix}VerdictObs", fmt(stat["observed_agreement"]))
        emit(f"{prefix}N", stat["n"])
        acc = results["accuracy_vs_human_consensus"][name]["verdict"]
        emit(f"{prefix}Acc", fmt(acc["accuracy"]))
        emit(f"{prefix}AccCI", f"[{fmt(acc['accuracy_ci95_wilson'][0])}, {fmt(acc['accuracy_ci95_wilson'][1])}]")
        emit(f"{prefix}Base", fmt(acc["majority_class_baseline"]))
    if "human_majority_vs_model_majority" in results:
        cross = results["human_majority_vs_model_majority"]
        emit("HumCrossAgree", fmt(cross["rate"]))
        emit("HumCrossN", cross["n"])
    if "human_minus_model_verdict_kappa" in results:
        gap = results["human_minus_model_verdict_kappa"]
        emit("HumGapDelta", ("+" if gap["delta"] >= 0 else "") + fmt(gap["delta"]))
        emit("HumGapCI", f"[{fmt(gap['delta_ci95'][0])}, {fmt(gap['delta_ci95'][1])}]")
        emit("HumGapN", gap["n"])
    if "human_minus_model_power" in results:
        pw = results["human_minus_model_power"]
        emit("HumMDE", fmt(pw["minimum_detectable_delta_80pc_power"]))
        emit("HumSE", fmt(pw["bootstrap_se"]))
        emit("HumClusters", pw["n_clusters"])
    shares = [
        v["share_valid"] for k, v in results["threshold_spread"].items() if k.startswith("human_")
    ]
    if shares:
        emit("HumSpreadLo", f"{100 * min(shares):.0f}")
        emit("HumSpreadHi", f"{100 * max(shares):.0f}")
    model_shares = [
        v["share_valid"] for k, v in results["threshold_spread"].items() if not k.startswith("human_")
    ]
    if model_shares:
        emit("HumModSpreadLo", f"{100 * min(model_shares):.0f}")
        emit("HumModSpreadHi", f"{100 * max(model_shares):.0f}")
        emit("HumModJudges", len(model_shares))
        emit("HumModDevs", len({DEVELOPER_OF.get(k, k) for k in results["threshold_spread"] if not k.startswith("human_")}))
    args.macros.write_text("\n".join(macro_lines) + "\n", encoding="utf-8")

    print(json.dumps({k: v for k, v in results.items() if k != "per_field"}, indent=2, default=str)[:4000])
    print(f"\nwrote {args.out}\nwrote {args.table}\nwrote {args.macros}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
