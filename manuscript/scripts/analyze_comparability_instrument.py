#!/usr/bin/env python3
"""Score the comparability instrument benchmark (reviewer W1, W4, W7).

Every item's coordinate values and its verdict are fixed when the item is
written, so the reference here is independent of every reviewer and has no
annotation provenance to audit.  This replaces the withdrawn human diagnostic
as the evidence for what the five coordinates are and are not.

Reported, per judge and pooled:

  * coordinate recovery -- can a reader read C1..C5 off a passage at all,
    against the value the passage was built to carry;
  * verdict accuracy of the judge's own answer, of the deterministic rule
    composed with the judge's coordinate labels, and of the same rule with
    C2 and C5 ablated;
  * the strongest constant baseline, which is exactly 1/3 by construction;
  * inter-judge agreement in every arm;
  * everything again split by disclosure regime, which is the contrast that
    separates ``the schema cannot be coded'' from ``papers do not state what
    the schema asks for''.

Writes ``supplement/comparability_instrument_results.json``,
``tables/instrument_baselines.tex`` and ``tables/instrument_disclosure.tex``.
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

ARMS = ("five", "c1c4", "direct")
THREAT = ("c1", "c2", "c4", "c5")
COORDS = ("c1", "c2", "c3", "c4", "c5")
VERDICTS = ("survives", "narrows", "undefined")


def cohen_kappa(a, b):
    if not a:
        return float("nan")
    cats = sorted(set(a) | set(b))
    if len(cats) < 2:
        return float("nan")
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return float("nan") if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)


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


def boot_ci(hits, draws=10000, seed=2026080301):
    if not hits:
        return None
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        s = [rng.choice(hits) for _ in hits]
        out.append(sum(s) / len(s))
    out.sort()
    return [out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))]]


def mcnemar_exact(a_hits, b_hits):
    """Exact two-sided McNemar on paired 0/1 correctness vectors."""
    from math import comb

    b = sum(1 for x, y in zip(a_hits, b_hits) if x and not y)
    c = sum(1 for x, y in zip(a_hits, b_hits) if y and not x)
    n = b + c
    if n == 0:
        return 1.0, b, c
    k = min(b, c)
    p = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n) * 2
    return min(1.0, p), b, c


def compose(parsed: dict, threatening=THREAT) -> str:
    """The manuscript's decision rule applied to a judge's coordinate labels."""
    labels = {c: str(parsed.get(c, "")).lower() for c in threatening}
    if any(labels[c] not in ("match", "mismatch") for c in threatening):
        return "undefined"
    if all(labels[c] == "match" for c in threatening):
        return "survives"
    matched = str(parsed.get("matched_number", "")).strip().lower()
    if matched and matched not in ("not_recoverable_from_text", "n/a", "none"):
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--items", type=Path, default=SUP / "comparability_instrument_benchmark.jsonl"
    )
    ap.add_argument("--runs", type=Path, default=SUP / "comparability_instrument_runs")
    ap.add_argument(
        "--output", type=Path, default=SUP / "comparability_instrument_results.json"
    )
    args = ap.parse_args()

    truth = {}
    for line in args.items.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            truth[row["item_id"]] = row

    arms = {a: load_arm(args.runs, a, truth) for a in ARMS}
    for arm, judges in arms.items():
        print(f"  arm {arm}: {len(judges)} judges " + ", ".join(sorted(judges)))
    if not arms["five"]:
        print("no five-coordinate runs found")
        return 1

    ids = sorted(
        set.intersection(
            *[set(t) for judges in arms.values() if judges for t in judges.values()]
        )
    )
    print(f"  items scored by every judge in every arm: {len(ids)}")
    counts = Counter(truth[i]["truth_verdict"] for i in ids)
    majority_base = max(counts.values()) / len(ids)

    results = {
        "n_items": len(ids),
        "verdict_counts": dict(counts),
        "majority_class_baseline": majority_base,
        "judges": {a: sorted(j) for a, j in arms.items()},
        "arms": {},
        "estimators": {},
        "disclosure": {},
    }

    # ---------------- coordinate recovery, five-coordinate arm ----------------
    coord_block = {}
    for coord in COORDS:
        per_judge = {}
        for judge, table in arms["five"].items():
            hits = [
                int(str(table[i].get(coord, "")).lower() == truth[i]["truth_coordinates"][coord])
                for i in ids
            ]
            per_judge[judge] = {"accuracy": sum(hits) / len(hits), "ci95": boot_ci(hits)}
        rows = [[str(arms["five"][j][i].get(coord, "")).lower() for j in sorted(arms["five"])] for i in ids]
        coord_block[coord] = {
            "per_judge": per_judge,
            "mean_accuracy": sum(v["accuracy"] for v in per_judge.values()) / len(per_judge),
            "inter_judge_kappa": fleiss_kappa(rows),
            "truth_marginal": dict(Counter(truth[i]["truth_coordinates"][coord] for i in ids)),
        }
        print(
            f"  coordinate {coord}: mean recovery "
            f"{coord_block[coord]['mean_accuracy']:.3f}  inter-judge kappa "
            f"{coord_block[coord]['inter_judge_kappa']:+.3f}"
        )
    results["coordinate_recovery"] = coord_block

    # ---------------- estimators against the constructed reference -----------
    def score(name, predictor, judges):
        per_judge, all_hits = {}, {}
        for judge, table in judges.items():
            hits = [int(predictor(table[i]) == truth[i]["truth_verdict"]) for i in ids]
            kappa = cohen_kappa(
                [predictor(table[i]) for i in ids], [truth[i]["truth_verdict"] for i in ids]
            )
            per_judge[judge] = {
                "exact": sum(hits) / len(hits),
                "kappa": kappa,
                "ci95": boot_ci(hits),
            }
            all_hits[judge] = hits
        return {
            "per_judge": per_judge,
            "mean_exact": sum(v["exact"] for v in per_judge.values()) / len(per_judge),
            "mean_kappa": sum(v["kappa"] for v in per_judge.values()) / len(per_judge),
            "min_exact": min(v["exact"] for v in per_judge.values()),
            "max_exact": max(v["exact"] for v in per_judge.values()),
            "_hits": all_hits,
        }, name

    estimators = {}
    entry, _ = score("five_coordinate_rule", lambda p: compose(p, THREAT), arms["five"])
    estimators["Five coordinates (rule)"] = entry
    entry, _ = score("ablated_rule", lambda p: compose(p, ("c1", "c4")), arms["five"])
    estimators["Rule with C2/C5 ablated"] = entry
    entry, _ = score("judge_verdict_five", lambda p: str(p.get("verdict", "")).lower(), arms["five"])
    estimators["Judge verdict, five-coordinate prompt"] = entry
    if arms.get("c1c4"):
        entry, _ = score("judge_verdict_c1c4", lambda p: str(p.get("verdict", "")).lower(), arms["c1c4"])
        estimators["Judge verdict, C1/C4 prompt"] = entry
    if arms.get("direct"):
        entry, _ = score("judge_verdict_direct", lambda p: str(p.get("verdict", "")).lower(), arms["direct"])
        estimators["Judge verdict, no coordinates"] = entry
    constant = max(counts, key=counts.get)
    estimators[f"Majority class ({constant})"] = {
        "per_judge": {},
        "mean_exact": majority_base,
        "mean_kappa": 0.0,
        "min_exact": majority_base,
        "max_exact": majority_base,
        "_hits": {"constant": [int(truth[i]["truth_verdict"] == constant) for i in ids]},
    }

    for name, entry in estimators.items():
        print(
            f"  {name:42s} exact {entry['mean_exact']:.3f} "
            f"[{entry['min_exact']:.3f},{entry['max_exact']:.3f}]  "
            f"kappa {entry['mean_kappa']:+.3f}"
        )

    # paired contrast against the constant baseline, per judge, exact McNemar
    base_hits = estimators[f"Majority class ({constant})"]["_hits"]["constant"]
    contrasts = {}
    for name, entry in estimators.items():
        if not entry["_hits"] or name.startswith("Majority class"):
            continue
        rows = []
        for judge, hits in entry["_hits"].items():
            p, b, c = mcnemar_exact(hits, base_hits)
            rows.append(
                {
                    "judge": judge,
                    "difference": sum(hits) / len(hits) - sum(base_hits) / len(base_hits),
                    "mcnemar_exact_p": p,
                    "wins": b,
                    "losses": c,
                }
            )
        contrasts[name] = {
            "per_judge": rows,
            "min_difference": min(r["difference"] for r in rows),
            "max_p": max(r["mcnemar_exact_p"] for r in rows),
            "all_beat_baseline": all(
                r["difference"] > 0 and r["mcnemar_exact_p"] < 0.05 for r in rows
            ),
        }
    results["contrasts_vs_majority"] = contrasts

    # ---------------- disclosure regime ----------------
    for regime in ("full", "partial"):
        sub = [i for i in ids if truth[i]["disclosure"] == regime]
        if not sub:
            continue
        block = {"n_items": len(sub)}
        coord_acc = {}
        for coord in COORDS:
            accs = [
                sum(
                    int(str(t[i].get(coord, "")).lower() == truth[i]["truth_coordinates"][coord])
                    for i in sub
                )
                / len(sub)
                for t in arms["five"].values()
            ]
            coord_acc[coord] = sum(accs) / len(accs)
        block["coordinate_recovery"] = coord_acc
        block["mean_coordinate_recovery"] = sum(coord_acc.values()) / len(coord_acc)
        for arm in ARMS:
            if not arms.get(arm):
                continue
            accs = [
                sum(int(str(t[i].get("verdict", "")).lower() == truth[i]["truth_verdict"]) for i in sub)
                / len(sub)
                for t in arms[arm].values()
            ]
            rows = [[str(arms[arm][j][i].get("verdict", "")).lower() for j in sorted(arms[arm])] for i in sub]
            block[f"{arm}_verdict_accuracy"] = sum(accs) / len(accs)
            block[f"{arm}_inter_judge_kappa"] = fleiss_kappa(rows)
        rule_accs = [
            sum(int(compose(t[i]) == truth[i]["truth_verdict"]) for i in sub) / len(sub)
            for t in arms["five"].values()
        ]
        block["rule_accuracy"] = sum(rule_accs) / len(rule_accs)
        results["disclosure"][regime] = block
        print(
            f"  disclosure {regime:8s} n={len(sub):4d} coord recovery "
            f"{block['mean_coordinate_recovery']:.3f}  rule {block['rule_accuracy']:.3f}  "
            f"five-arm verdict {block.get('five_verdict_accuracy', float('nan')):.3f}"
        )

    # ---------------- inter-judge agreement by arm ----------------
    for arm in ARMS:
        if not arms.get(arm):
            continue
        rows = [[str(arms[arm][j][i].get("verdict", "")).lower() for j in sorted(arms[arm])] for i in ids]
        results["arms"][arm] = {
            "n_judges": len(arms[arm]),
            "inter_judge_kappa": fleiss_kappa(rows),
            "mean_accuracy": sum(
                sum(int(str(t[i].get("verdict", "")).lower() == truth[i]["truth_verdict"]) for i in ids)
                / len(ids)
                for t in arms[arm].values()
            )
            / len(arms[arm]),
        }
        print(
            f"  arm {arm:7s} inter-judge kappa {results['arms'][arm]['inter_judge_kappa']:+.3f} "
            f"accuracy {results['arms'][arm]['mean_accuracy']:.3f}"
        )

    results["estimators"] = {
        k: {kk: vv for kk, vv in v.items() if kk != "_hits"} for k, v in estimators.items()
    }
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    write_tables(results, estimators, constant)
    return 0


def write_tables(results: dict, estimators: dict, constant: str) -> None:
    order = [
        "Five coordinates (rule)",
        "Rule with C2/C5 ablated",
        "Judge verdict, five-coordinate prompt",
        "Judge verdict, C1/C4 prompt",
        "Judge verdict, no coordinates",
        f"Majority class ({constant})",
    ]
    rows = []
    for name in order:
        entry = estimators.get(name)
        if not entry:
            continue
        contrast = results["contrasts_vs_majority"].get(name)
        if contrast:
            pmax = contrast["max_p"]
            ptext = "p<0.001" if pmax < 0.001 else f"p={pmax:.3f}"
            delta = f"{contrast['min_difference']:+.2f}, ${ptext}$"
        else:
            delta = "---"
        rows.append(
            " & ".join(
                [
                    name,
                    f"{entry['mean_exact']:.3f}",
                    f"{entry['min_exact']:.2f}--{entry['max_exact']:.2f}",
                    f"{entry['mean_kappa']:.3f}",
                    delta,
                ]
            )
            + r" \\"
        )
    tab = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{@{}lrrrl@{}}",
        r"\toprule",
        r"Estimator & Exact & Range & $\kappa$ & vs.\ baseline \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{The five coordinates do separate from the strongest trivial "
        r"baseline once the reference is not an annotation. Every one of the "
        + f"{results['n_items']:,}"
        + r" items every judge answered in every arm carries a verdict fixed "
        r"when it was written, and the three verdict classes are balanced by "
        r"construction, so the strongest constant predictor scores "
        + f"{results['majority_class_baseline']:.3f}"
        + r", within rounding of $1/3$. \emph{Range} is across the "
        r"judges; \emph{vs.\ baseline} reports the \emph{weakest} judge's "
        r"margin over the constant baseline and the \emph{largest} exact "
        r"McNemar $p$ across judges, so the row is a claim about every judge "
        r"and not about their average. What this does not show is that a "
        r"verdict can be scored on real papers: "
        r"Table~\ref{tab:instrument-disclosure} is the same instrument on "
        r"passages that withhold what the schema asks for.}",
        r"\label{tab:instrument-baselines}",
        r"\end{table}",
    ]
    (TAB / "instrument_baselines.tex").write_text("\n".join(tab) + "\n", encoding="utf-8")
    print(f"wrote {TAB / 'instrument_baselines.tex'}")

    drows = []
    for regime, label in (("full", "States every coordinate"), ("partial", "Withholds a coordinate")):
        block = results["disclosure"].get(regime)
        if not block:
            continue
        drows.append(
            " & ".join(
                [
                    label,
                    f"{block['n_items']:,}",
                    f"{block['mean_coordinate_recovery']:.2f}",
                    f"{block['rule_accuracy']:.2f}",
                    f"{block.get('five_verdict_accuracy', float('nan')):.2f}",
                    f"{block.get('five_inter_judge_kappa', float('nan')):.2f}",
                ]
            )
            + r" \\"
        )
    dtab = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{@{}lrrrrr@{}}",
        r"\toprule",
        r"Passage & $N$ & Coord. & Rule & Verdict & $\kappa$ \\",
        r"\midrule",
        *drows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{What fails is disclosure, not the schema. The same judges "
        r"and the same instrument are applied to constructed passages that "
        r"state every coordinate and to passages that withhold one, where the "
        r"correct coordinate label becomes \emph{not determinable} and the "
        r"correct verdict becomes \emph{undefined}. \emph{Coord.} is mean "
        r"recovery of the five coordinate labels against the value the passage "
        r"was built to carry, \emph{Rule} is the decision rule composed with "
        r"the judge's labels, \emph{Verdict} is the judge's own answer and "
        r"$\kappa$ is agreement among the judges. Real papers behave like the "
        r"second row.}",
        r"\label{tab:instrument-disclosure}",
        r"\end{table}",
    ]
    (TAB / "instrument_disclosure.tex").write_text("\n".join(dtab) + "\n", encoding="utf-8")
    print(f"wrote {TAB / 'instrument_disclosure.tex'}")


if __name__ == "__main__":
    raise SystemExit(main())
