#!/usr/bin/env python3
"""Score the redesigned comparability benchmark (reviewer W1, W2, W7).

What changed relative to ``analyze_comparability_instrument.py``:

*   every accuracy is reported against the constant baseline **of its own
    stratum**, never against a baseline manufactured by pooling strata with
    different class distributions;
*   the degenerate arm, on which the reference verdict is ``undefined`` by
    construction and the constant predictor therefore scores 1.00, is reported
    as such and is excluded from every pooled figure;
*   disclosure and presentation are reported as a two-factor table, so the
    question "is it that papers do not state the coordinates, or that they do
    not state them in a readable place?" is answerable;
*   every estimator arm is reported, including the two-coordinate ones, with a
    paired exact McNemar test between the best two-coordinate estimator and the
    best five-coordinate estimator on the items both answered.

Writes ``supplement/comparability_instrument_v2_results.json``,
``tables/instrument_baselines_v2.tex`` and ``tables/instrument_disclosure_v2.tex``.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from itertools import combinations
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
TAB = REPO / "manuscript" / "tables"

ARMS = ("five", "c1c4", "direct")
THREAT = ("c1", "c2", "c4", "c5")
COORDS = ("c1", "c2", "c3", "c4", "c5")
DISCLOSURES = ("full", "partial_balanced", "partial_forcing")
PRESENTATIONS = ("canonical", "naturalistic")


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


def mcnemar_exact(a_hits, b_hits):
    b = sum(1 for x, y in zip(a_hits, b_hits) if x and not y)
    c = sum(1 for x, y in zip(a_hits, b_hits) if y and not x)
    n = b + c
    if n == 0:
        return 1.0, b, c
    k = min(b, c)
    p = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n) * 2
    return min(1.0, p), b, c


def boot_ci(hits, draws=5000, seed=2026080441):
    if not hits:
        return None
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        s = [rng.choice(hits) for _ in hits]
        out.append(sum(s) / len(s))
    out.sort()
    return [round(out[int(0.025 * len(out))], 4),
            round(out[min(len(out) - 1, int(0.975 * len(out)))], 4)]


def compose(parsed: dict, threatening=THREAT) -> str:
    """The manuscript's decision rule, applied in the order Section 3 states it.

    Branch 2 is checked *before* falling through to ``undefined``, because the
    rule reads "otherwise, if a side reports an operating point at the other's
    setting ... report the matched number".  A coordinate the passage does not
    state is a coordinate that fails branch 1, not one that skips branch 2: a
    disagreement that a paper repairs at a matched operating point narrows the
    comparison whether the disagreement was disclosed or merely possible.
    """
    labels = {c: str(parsed.get(c, "")).lower() for c in threatening}
    if all(labels[c] == "match" for c in threatening):
        return "survives"
    matched = str(parsed.get("matched_number", "")).strip().lower()
    if matched and matched not in ("not_recoverable_from_text", "n/a", "none", "-"):
        return "narrows"
    return "undefined"


def load_arm(root: Path, arm: str, truth: dict) -> dict[str, dict[str, dict]]:
    out = {}
    arm_dir = root / arm
    if not arm_dir.exists():
        return out
    for path in sorted(arm_dir.glob("*.jsonl")):
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed") and row["item_id"] in truth:
                table[row["item_id"]] = row["parsed"]
        if len(table) >= 0.9 * len(truth):
            out[path.stem] = table
    return out


def constant_baseline(items) -> tuple[float, str]:
    counts = Counter(i["truth_verdict"] for i in items)
    if not counts:
        return float("nan"), ""
    label, n = counts.most_common(1)[0]
    return n / sum(counts.values()), label


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", type=Path,
                    default=SUP / "comparability_instrument_benchmark_v2.jsonl")
    ap.add_argument("--runs", type=Path, default=SUP / "comparability_instrument_runs_v2")
    ap.add_argument("--out", type=Path,
                    default=SUP / "comparability_instrument_v2_results.json")
    args = ap.parse_args()

    items = {}
    for line in args.items.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            items[row["item_id"]] = row

    arm_tables = {a: load_arm(args.runs, a, items) for a in ARMS}
    judges = sorted(set.intersection(*[set(arm_tables[a]) for a in ARMS])
                    ) if all(arm_tables[a] for a in ARMS) else []
    if not judges:
        raise SystemExit("no judge answered every arm yet")

    # the item population is fixed once: every item every judge answered in
    # every arm, so no arm is scored on a population of its own choosing
    common = set(items)
    for a in ARMS:
        for j in judges:
            common &= set(arm_tables[a][j])
    common = sorted(common)
    pop = [items[i] for i in common]

    estimators = {
        "Five coordinates (rule)": ("five", lambda p: compose(p)),
        "Rule with C2/C5 ablated": ("five", lambda p: compose(p, ("c1", "c4"))),
        "Two coordinates (rule, C1/C4 prompt)": ("c1c4", lambda p: compose(p, ("c1", "c4"))),
        "Judge verdict, five-coordinate prompt": (
            "five", lambda p: str(p.get("verdict", "")).lower()),
        "Judge verdict, C1/C4 prompt": (
            "c1c4", lambda p: str(p.get("verdict", "")).lower()),
        "Judge verdict, no coordinates": (
            "direct", lambda p: str(p.get("verdict", "")).lower()),
    }

    def hits_for(name, subset_ids):
        arm, fn = estimators[name]
        per_judge = {}
        for j in judges:
            tbl = arm_tables[arm][j]
            per_judge[j] = [int(fn(tbl[i]) == items[i]["truth_verdict"])
                            for i in subset_ids if i in tbl]
        return per_judge

    def summarise(subset_ids, label):
        sub = [items[i] for i in subset_ids]
        base, base_lab = constant_baseline(sub)
        block = {"n_items": len(subset_ids), "constant_baseline": round(base, 4),
                 "constant_baseline_label": base_lab,
                 "verdict_counts": dict(Counter(i["truth_verdict"] for i in sub)),
                 "estimators": {}}
        for name in estimators:
            pj = hits_for(name, subset_ids)
            pooled = [h for j in judges for h in pj[j]]
            per = {j: round(sum(v) / len(v), 4) for j, v in pj.items() if v}
            worst = min(per.values()) if per else float("nan")
            block["estimators"][name] = {
                "pooled_accuracy": round(sum(pooled) / len(pooled), 4) if pooled else None,
                "per_judge": per,
                "judge_range": [round(min(per.values()), 4), round(max(per.values()), 4)] if per else None,
                "weakest_judge_margin_over_stratum_baseline": round(worst - base, 4) if per else None,
                "every_judge_beats_stratum_baseline": bool(per) and worst > base,
                "ci95_pooled": boot_ci(pooled),
            }
        # inter-judge agreement on the judge's own five-coordinate verdict
        rows = []
        for i in subset_ids:
            v = [str(arm_tables["five"][j][i].get("verdict", "")).lower()
                 for j in judges if i in arm_tables["five"][j]]
            if len(v) == len(judges):
                rows.append(v)
        block["verdict_fleiss_kappa"] = round(fleiss_kappa(rows), 4) if rows else None
        # coordinate recovery
        coord = {}
        for c in COORDS:
            hits = []
            for j in judges:
                for i in subset_ids:
                    p = arm_tables["five"][j].get(i)
                    if not p:
                        continue
                    hits.append(int(str(p.get(c, "")).lower()
                                    == items[i]["truth_coordinates"][c]))
            coord[c] = round(sum(hits) / len(hits), 4) if hits else None
            rows_c = []
            for i in subset_ids:
                v = [str(arm_tables["five"][j][i].get(c, "")).lower()
                     for j in judges if i in arm_tables["five"][j]]
                if len(v) == len(judges):
                    rows_c.append(v)
            coord[f"{c}_fleiss_kappa"] = round(fleiss_kappa(rows_c), 4) if rows_c else None
        block["coordinate_recovery"] = coord
        block["coordinate_recovery_mean_threatening"] = round(
            sum(coord[c] for c in THREAT) / len(THREAT), 4)
        block["label"] = label
        return block

    by_disclosure = {
        d: summarise([i for i in common if items[i]["disclosure"] == d], d)
        for d in DISCLOSURES}
    by_cell = {
        f"{p}/{d}": summarise(
            [i for i in common
             if items[i]["disclosure"] == d and items[i]["presentation"] == p],
            f"{p}/{d}")
        for p in PRESENTATIONS for d in DISCLOSURES}
    non_degenerate = [i for i in common
                      if items[i]["disclosure"] in ("full", "partial_balanced")]
    pooled_block = summarise(non_degenerate, "full+partial_balanced")
    by_presentation = {
        p: summarise([i for i in non_degenerate if items[i]["presentation"] == p], p)
        for p in PRESENTATIONS}

    # ---- the fair two-versus-five comparison the reviewer asks for --------
    def paired(name_a, name_b, subset_ids):
        arm_a, fn_a = estimators[name_a]
        arm_b, fn_b = estimators[name_b]
        a_hits, b_hits = [], []
        for j in judges:
            ta, tb = arm_tables[arm_a][j], arm_tables[arm_b][j]
            for i in subset_ids:
                if i in ta and i in tb:
                    a_hits.append(int(fn_a(ta[i]) == items[i]["truth_verdict"]))
                    b_hits.append(int(fn_b(tb[i]) == items[i]["truth_verdict"]))
        p, b, c = mcnemar_exact(a_hits, b_hits)
        return {"n_paired": len(a_hits),
                "accuracy_a": round(sum(a_hits) / len(a_hits), 4) if a_hits else None,
                "accuracy_b": round(sum(b_hits) / len(b_hits), 4) if b_hits else None,
                "difference": round((sum(a_hits) - sum(b_hits)) / len(a_hits), 4) if a_hits else None,
                "discordant_a_only": b, "discordant_b_only": c,
                "mcnemar_p_two_sided": p}

    five_vs_two = {
        "five_rule_vs_best_two_coordinate_estimator": paired(
            "Five coordinates (rule)", "Judge verdict, C1/C4 prompt", non_degenerate),
        "five_rule_vs_two_coordinate_rule": paired(
            "Five coordinates (rule)", "Two coordinates (rule, C1/C4 prompt)",
            non_degenerate),
        "five_rule_vs_rule_with_c2c5_ablated": paired(
            "Five coordinates (rule)", "Rule with C2/C5 ablated", non_degenerate),
        "note": ("The comparison a five-field checklist has to win is against "
                 "the best two-coordinate estimator, not against a five-coordinate "
                 "rule with two of its inputs deleted."),
    }

    # ---- the degenerate arm, stated as such ------------------------------
    forcing = by_disclosure["partial_forcing"]
    degenerate_note = {
        "constant_baseline_on_this_arm": forcing["constant_baseline"],
        "best_estimator_accuracy": max(
            (v["pooled_accuracy"] or 0) for v in forcing["estimators"].values()),
        "reading": ("On this arm the reference verdict never varies, so the "
                    "constant predictor scores 1.00 and no estimator can beat "
                    "it. It is reported to show that judges do not answer "
                    "'undefined' whenever a coordinate is missing, which is a "
                    "check on the judges, not evidence that the schema is "
                    "codable under withholding."),
    }

    out = {
        "schema_version": "comparability-instrument-v2-results",
        "n_items_in_benchmark": len(items),
        "n_items_scored": len(common),
        "judges": judges,
        "arms": list(ARMS),
        "population_note": ("Every figure is computed on the items every judge "
                            "answered in every arm, fixed once before any "
                            "estimator is scored."),
        "pooled_non_degenerate": pooled_block,
        "by_disclosure": by_disclosure,
        "by_presentation": by_presentation,
        "by_cell": by_cell,
        "five_vs_two_coordinates": five_vs_two,
        "degenerate_arm": degenerate_note,
    }
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    def pct(x):
        return "---" if x is None else f"{x:.3f}"

    # ---- tables ----------------------------------------------------------
    rows = []
    for name in estimators:
        e = pooled_block["estimators"][name]
        rng = e["judge_range"]
        rows.append(
            f"{name} & {pct(e['pooled_accuracy'])} & "
            f"{rng[0]:.2f}--{rng[1]:.2f} & "
            f"{e['weakest_judge_margin_over_stratum_baseline']:+.2f} \\\\")
    base = pooled_block["constant_baseline"]
    rows.append(f"Majority class ({pooled_block['constant_baseline_label']}) & "
                f"{base:.3f} & --- & --- \\\\")
    tex = (
        "\\begin{table}[t]\n\\centering\\scriptsize\n"
        "\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{@{}lrrr@{}}\n\\toprule\n"
        "Estimator & Exact & Range & Weakest judge \\\\\n\\midrule\n"
        + "\n".join(rows) +
        "\n\\bottomrule\n\\end{tabular}\n"
        "\\caption{Every estimator arm, on the "
        f"{pooled_block['n_items']} non-degenerate items, scored against the "
        f"constant baseline of that population ({base:.3f}; the three verdict "
        "classes are equinumerous inside every disclosure arm, so this baseline "
        "is not an artefact of pooling). \\emph{Range} is across judges and "
        "\\emph{weakest judge} is the smallest judge margin over that baseline. "
        "The degenerate withholding arm, whose reference verdict never varies "
        "and whose constant baseline is therefore $1.00$, is excluded here and "
        "reported separately in Table~\\ref{tab:instrument-disclosure-v2}.}\n"
        "\\label{tab:instrument-baselines-v2}\n\\end{table}\n")
    (TAB / "instrument_baselines_v2.tex").write_text(tex, encoding="utf-8")

    drows = []
    labels = {"full": "States every coordinate",
              "partial_balanced": "Withholds one, verdict unaffected",
              "partial_forcing": "Withholds one, verdict forced"}
    for p in PRESENTATIONS:
        for d in DISCLOSURES:
            b = by_cell[f"{p}/{d}"]
            e = b["estimators"]["Five coordinates (rule)"]
            jv = b["estimators"]["Judge verdict, five-coordinate prompt"]
            drows.append(
                f"{p[:4].capitalize()}. & {labels[d]} & {b['n_items']} & "
                f"{b['constant_baseline']:.2f} & "
                f"{b['coordinate_recovery_mean_threatening']:.2f} & "
                f"{pct(e['pooled_accuracy'])} & {pct(jv['pooled_accuracy'])} & "
                f"{b['verdict_fleiss_kappa']:.2f} \\\\")
    tex2 = (
        "\\begin{table}[t]\n\\centering\\scriptsize\n"
        "\\setlength{\\tabcolsep}{2.5pt}\n"
        "\\begin{tabular}{@{}llrrrrrr@{}}\n\\toprule\n"
        "Prose & Passage & $N$ & Base & Coord. & Rule & Verd. & $\\kappa$ \\\\\n"
        "\\midrule\n" + "\n".join(drows) + "\n\\bottomrule\n\\end{tabular}\n"
        "\\caption{Disclosure crossed with prose realism, each cell scored "
        "against \\emph{its own} constant baseline (\\emph{Base}). "
        "\\emph{Cano.} states one coordinate per sentence in the codebook's own "
        "vocabulary; \\emph{Natu.} states the identical facts in paper-style "
        "prose, reordered and interleaved with sentences that carry no "
        "coordinate information. \\emph{Coord.} is mean recovery over C1, C2, C4 "
        "and C5. In the second row of each block the withheld coordinate does "
        "not determine the verdict, so all three classes occur and the baseline "
        "is $1/3$; in the third the verdict follows from the withholding alone, "
        "so the baseline is $1.00$ and no estimator can beat it.}\n"
        "\\label{tab:instrument-disclosure-v2}\n\\end{table}\n")
    (TAB / "instrument_disclosure_v2.tex").write_text(tex2, encoding="utf-8")

    print(json.dumps({
        "judges": judges, "n_scored": len(common),
        "pooled_non_degenerate_baseline": pooled_block["constant_baseline"],
        "pooled_rule": pooled_block["estimators"]["Five coordinates (rule)"]["pooled_accuracy"],
        "by_disclosure": {d: {
            "n": by_disclosure[d]["n_items"],
            "base": by_disclosure[d]["constant_baseline"],
            "coord": by_disclosure[d]["coordinate_recovery_mean_threatening"],
            "rule": by_disclosure[d]["estimators"]["Five coordinates (rule)"]["pooled_accuracy"],
            "judge_verdict": by_disclosure[d]["estimators"]["Judge verdict, five-coordinate prompt"]["pooled_accuracy"],
            "kappa": by_disclosure[d]["verdict_fleiss_kappa"]} for d in DISCLOSURES},
        "by_presentation": {p: {
            "coord": by_presentation[p]["coordinate_recovery_mean_threatening"],
            "rule": by_presentation[p]["estimators"]["Five coordinates (rule)"]["pooled_accuracy"],
            "kappa": by_presentation[p]["verdict_fleiss_kappa"]} for p in PRESENTATIONS},
        "five_vs_two": five_vs_two,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
