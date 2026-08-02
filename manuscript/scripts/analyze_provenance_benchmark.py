#!/usr/bin/env python3
"""Score the constructed provenance benchmark (reviewer W4).

Reports, against a reference fixed when each item was written:

  * accuracy of the deployed three-option prompt on the balanced three-way
    subset, per judge and for the three-judge panel majority that produced the
    census labels, with the constant baseline of that subset;
  * the same split by whether the passage declares how the number was obtained
    or leaves it to be inferred from structure, since a benchmark solvable by
    matching a declaration phrase would prove nothing about the census;
  * the confusion matrix, so that the direction of any error is visible: the
    manuscript's claim is about a *share*, and a classifier biased toward
    ``reimplemented`` would inflate exactly that share;
  * a bias-corrected re-estimate of the census composition using the measured
    confusion matrix, which is what the claim needs if the classifier is not
    perfect;
  * what the deployed prompt does with the fourth category the manuscript names
    but the prompt cannot express, and what changes when the option is added.

Writes ``supplement/provenance_benchmark_results.json`` and
``tables/provenance_validation.tex``.
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
THREE = ("reimplemented", "transported", "unclear")


def norm(label: str) -> str:
    label = str(label or "").strip().lower().replace("-", "").replace(" ", "_")
    if label in ("reimplemented", "re_implemented", "reimplement"):
        return "reimplemented"
    if label.startswith("transport"):
        return "transported"
    if label.startswith("assert"):
        return "asserted_no_number"
    if label.startswith("unclear"):
        return "unclear"
    return label


def boot_ci(hits, draws=5000, seed=2026080451):
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


def load(root: Path, arm: str) -> dict[str, dict[str, str]]:
    out = {}
    d = root / arm
    if not d.exists():
        return out
    for path in sorted(d.glob("*.jsonl")):
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            p = row.get("parsed") or {}
            if p.get("provenance"):
                table[row["item_id"]] = norm(p["provenance"])
        out[path.stem] = table
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", type=Path, default=SUP / "provenance_benchmark.jsonl")
    ap.add_argument("--runs", type=Path, default=SUP / "provenance_benchmark_runs")
    ap.add_argument("--census", type=Path, default=SUP / "cross_paper_census.json")
    ap.add_argument("--out", type=Path, default=SUP / "provenance_benchmark_results.json")
    args = ap.parse_args()

    items = {}
    for line in args.items.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            items[r["item_id"]] = r

    result = {"schema_version": "provenance-benchmark-results-v1",
              "n_items": len(items)}

    for arm in ("deployed", "fourway"):
        tables = load(args.runs, arm)
        if not tables:
            continue
        judges = sorted(tables)
        common = set(items)
        for j in judges:
            common &= set(tables[j])
        # the census panel is these three judges; keep it identifiable
        census_panel = [j for j in judges if j in
                        ("pbA_gpt5mini", "pbB_opus46", "pbC_gem31pro")]

        scorable = [i for i in sorted(common)
                    if items[i]["truth_provenance"] in THREE]
        base_counts = Counter(items[i]["truth_provenance"] for i in scorable)
        baseline = max(base_counts.values()) / len(scorable) if scorable else None

        per_judge, conf = {}, defaultdict(Counter)
        for j in judges:
            hits = [int(tables[j][i] == items[i]["truth_provenance"]) for i in scorable]
            per_judge[j] = {"n": len(hits),
                            "accuracy": round(sum(hits) / len(hits), 4) if hits else None,
                            "ci95": boot_ci(hits)}
            for i in scorable:
                conf[items[i]["truth_provenance"]][tables[j][i]] += 1

        def majority(panel, i):
            votes = [tables[j][i] for j in panel if i in tables[j]]
            top = Counter(votes).most_common()
            if top and (len(top) == 1 or top[0][1] > top[1][1]):
                return top[0][0]
            return "no_majority"

        panel_blocks = {}
        for pname, panel in (("census_three_judge_panel", census_panel),
                             ("all_judges", judges)):
            if not panel:
                continue
            hits = [int(majority(panel, i) == items[i]["truth_provenance"])
                    for i in scorable]
            pconf = defaultdict(Counter)
            for i in scorable:
                pconf[items[i]["truth_provenance"]][majority(panel, i)] += 1
            by_mode = {}
            for mode in ("explicit", "implicit", "none"):
                sub = [i for i in scorable if items[i]["explicitness"] == mode]
                if not sub:
                    continue
                h = [int(majority(panel, i) == items[i]["truth_provenance"]) for i in sub]
                by_mode[mode] = {"n": len(h), "accuracy": round(sum(h) / len(h), 4),
                                 "ci95": boot_ci(h)}
            by_class = {}
            for cls in THREE:
                sub = [i for i in scorable if items[i]["truth_provenance"] == cls]
                h = [int(majority(panel, i) == cls) for i in sub]
                by_class[cls] = {"n": len(h),
                                 "recall": round(sum(h) / len(h), 4) if h else None,
                                 "ci95": boot_ci(h)}
                pred = [i for i in scorable if majority(panel, i) == cls]
                tp = sum(1 for i in pred if items[i]["truth_provenance"] == cls)
                by_class[cls]["precision"] = round(tp / len(pred), 4) if pred else None
                by_class[cls]["n_predicted"] = len(pred)
            panel_blocks[pname] = {
                "judges": panel, "n_scored": len(scorable),
                "accuracy": round(sum(hits) / len(hits), 4) if hits else None,
                "ci95": boot_ci(hits),
                "constant_baseline": round(baseline, 4) if baseline else None,
                "by_explicitness": by_mode,
                "by_class": by_class,
                "confusion_truth_by_prediction": {k: dict(v) for k, v in pconf.items()},
            }

        asserted = [i for i in sorted(common)
                    if items[i]["truth_provenance"] == "asserted_no_number"]
        asserted_disposition = Counter()
        for i in asserted:
            for j in judges:
                asserted_disposition[tables[j][i]] += 1

        result[arm] = {
            "judges": judges,
            "n_scored_three_way": len(scorable),
            "constant_baseline_three_way": round(baseline, 4) if baseline else None,
            "per_judge": per_judge,
            "panels": panel_blocks,
            "confusion_truth_by_prediction_all_judges": {k: dict(v) for k, v in conf.items()},
            "asserted_no_number_disposition": dict(asserted_disposition),
            "n_asserted_no_number_items": len(asserted),
        }

    # ---- bias-corrected census composition -------------------------------
    dep = result.get("deployed", {}).get("panels", {}).get("census_three_judge_panel")
    if dep and args.census.exists():
        census = json.loads(args.census.read_text(encoding="utf-8"))
        counts = census["provenance"]["counts"]
        obs_t, obs_r = counts["transported"], counts["reimplemented"]
        conf = dep["confusion_truth_by_prediction"]

        def rate(truth, pred):
            row = conf.get(truth, {})
            tot = sum(row.values())
            return row.get(pred, 0) / tot if tot else 0.0

        # observed = M @ true, restricted to the two classes the claim uses
        a = rate("transported", "transported")
        b = rate("reimplemented", "transported")
        c = rate("transported", "reimplemented")
        d = rate("reimplemented", "reimplemented")
        det = a * d - b * c
        corrected = None
        if abs(det) > 1e-9:
            t = (d * obs_t - b * obs_r) / det
            r = (-c * obs_t + a * obs_r) / det
            if t >= 0 and r >= 0 and (t + r) > 0:
                corrected = {"transported": round(t, 1), "reimplemented": round(r, 1),
                             "reimplemented_share": round(r / (t + r), 4)}
        result["census_composition_bias_correction"] = {
            "observed_counts": {"transported": obs_t, "reimplemented": obs_r},
            "observed_reimplemented_share": round(obs_r / (obs_t + obs_r), 4),
            "confusion_rates_used": {"tt": round(a, 4), "rt": round(b, 4),
                                     "tr": round(c, 4), "rr": round(d, 4)},
            "corrected": corrected,
            "note": ("A two-class matrix inversion using the panel's measured "
                     "confusion on the constructed benchmark. It assumes the "
                     "constructed items elicit the same error rates as real "
                     "windows, which is exactly what a constructed benchmark "
                     "cannot establish; it is reported to show the direction "
                     "and rough size of the correction, not as an estimate."),
        }

    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    dep_all = result.get("deployed", {})
    panel = dep_all.get("panels", {}).get("census_three_judge_panel", {})
    if panel:
        _disp = dep_all.get("asserted_no_number_disposition", {})
        _tot = sum(_disp.values()) or 1
        asserted_pct = 100.0 * _disp.get("unclear", 0) / _tot
        _fw = result.get("fourway", {}).get("asserted_no_number_disposition", {})
        _fwt = sum(_fw.values()) or 1
        fourway_asserted = 100.0 * _fw.get("asserted_no_number", 0) / _fwt
        rows = [f"Panel majority, all items & {panel['n_scored']} & "
                f"{panel['accuracy']:.3f} & "
                f"[{panel['ci95'][0]:.2f}, {panel['ci95'][1]:.2f}] \\\\"]
        for mode, lab in (("explicit", "\\quad passage declares provenance"),
                          ("implicit", "\\quad provenance only from structure")):
            m = panel["by_explicitness"].get(mode)
            if m:
                rows.append(f"{lab} & {m['n']} & {m['accuracy']:.3f} & "
                            f"[{m['ci95'][0]:.2f}, {m['ci95'][1]:.2f}] \\\\")
        rows.append("\\midrule")
        for cls in THREE:
            k = panel["by_class"][cls]
            rows.append(f"\\quad recall, {cls} & {k['n']} & {k['recall']:.3f} & "
                        f"[{k['ci95'][0]:.2f}, {k['ci95'][1]:.2f}] \\\\")
        rows.append("\\midrule")
        rows.append(f"Constant baseline & {panel['n_scored']} & "
                    f"{panel['constant_baseline']:.3f} & --- \\\\")
        tex = ("\\begin{table}[t]\n\\centering\\scriptsize\n"
               "\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{@{}lrrr@{}}\n"
               "\\toprule\nSubset & $N$ & Accuracy & 95\\% CI \\\\\n\\midrule\n"
               + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n"
               "\\caption{The provenance label scored against a reference, not "
               "against agreement. Items are constructed excerpts whose "
               "provenance is fixed when the item is written; the prompt, the "
               "three judges and the majority rule are byte-identical to the "
               "ones that produced the census labels. The three reference "
               "classes are equinumerous, so the constant baseline is $1/3$. "
               "The \\emph{implicit} rows carry no declaration sentence at all, "
               "so a classifier that keyed on a re-implementation or attribution "
               "phrase would score at baseline there. The stratum that asserts "
               "a relation while supplying no number for the other side is not "
               "scorable under a three-option prompt and is reported "
               "separately: the deployed prompt sends "
               f"{asserted_pct:.0f}\\% of those judgments to \\emph{{unclear}}, "
               "while the same prompt with a fourth option recovers them at "
               f"{fourway_asserted:.0f}\\%, so the category is codable and the "
               "deployed instrument simply cannot express it.}\n"
               "\\label{tab:provenance-validation}\n\\end{table}\n")
        (TAB / "provenance_validation.tex").write_text(tex, encoding="utf-8")

    print(json.dumps({k: v for k, v in result.items()
                      if k != "deployed" or True}, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
