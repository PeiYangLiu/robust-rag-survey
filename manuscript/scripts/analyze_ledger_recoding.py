#!/usr/bin/env python3
"""Agreement between the worked ledger and an independent re-coding (W5).

The ledger of worked cross-paper comparisons is coded by us.  A reviewer
observed that a paper which demonstrates that verdicts of this kind do not
replicate cannot then quote single-coded verdict rates without measuring the
same property of its own ledger.  ``recode_ledger_cases.py`` re-codes every
case with six independent judges from three developers, shown only the neutral
statement of the juxtaposition and the verbatim source excerpts.

This script reports, on the twelve cross-paper cases and on all fifteen:

  * exact agreement and Cohen's kappa between our verdict and each judge;
  * exact agreement and Cohen's kappa between our verdict and the panel
    majority;
  * Fleiss' kappa among the six judges;
  * the same three quantities collapsed to the binary distinction that the
    manuscript's negative conclusion actually uses -- does the quoted gap stand
    as reported, or not;
  * a per-case table of who said what.

Writes ``supplement/ledger_recoding_agreement.json`` and
``tables/ledger_recoding.tex``.
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

JUDGE_META = {
    "recB_opus46": ("Anthropic", "claude-opus-4.6"),
    "recG_opus48": ("Anthropic", "claude-opus-4.8"),
    "recC_gem31pro": ("Google", "gemini-3.1-pro-preview"),
    "recH_gem25pro": ("Google", "gemini-2.5-pro"),
    "recI_gpt54": ("OpenAI", "gpt-5.4"),
    "recJ_gpt55": ("OpenAI", "gpt-5.5"),
}

VERDICTS = ("survives", "narrows", "undefined")


def cohen_kappa(a: list[str], b: list[str]) -> float:
    if not a:
        return float("nan")
    cats = sorted(set(a) | set(b))
    if len(cats) < 2:
        return float("nan")
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa = Counter(a)
    pb = Counter(b)
    pe = sum((pa[c] / n) * (pb[c] / n) for c in cats)
    return float("nan") if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)


def fleiss_kappa(rows: list[list[str]]) -> float:
    rows = [r for r in rows if r]
    if not rows:
        return float("nan")
    n = len(rows[0])
    cats = sorted({v for r in rows for v in r})
    if len(cats) < 2:
        return float("nan")
    idx = {c: i for i, c in enumerate(cats)}
    p_bar = 0.0
    marg = [0.0] * len(cats)
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


def boot_ci(values: list[float], draws: int = 10000, seed: int = 2026080101):
    if not values:
        return None
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        sample = [rng.choice(values) for _ in values]
        out.append(sum(sample) / len(sample))
    out.sort()
    return [out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=Path, default=SUP / "cross_paper_comparability_cases.json")
    ap.add_argument("--coding", type=Path, default=SUP / "ledger_recoding")
    ap.add_argument("--output", type=Path, default=SUP / "ledger_recoding_agreement.json")
    args = ap.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    ours = {c["case_id"]: c["conclusion_change"] for c in cases}
    klass = {c["case_id"]: c["case_class"] for c in cases}
    ctype = {c["case_id"]: c["comparison_type"] for c in cases}

    panel: dict[str, dict[str, str]] = {}
    for name in JUDGE_META:
        path = args.coding / f"{name}.jsonl"
        if not path.exists():
            continue
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed"):
                table[row["case_id"]] = str(row["parsed"].get("verdict", "")).lower()
        panel[name] = table

    judges = sorted(panel)
    results = {"judges": {j: list(JUDGE_META[j]) for j in judges}}

    for scope, ids in (
        ("cross_paper", [c for c in ours if klass[c] == "cross_paper"]),
        ("all_cases", sorted(ours)),
        ("stated", [c for c in ours if ctype[c].startswith("STATED")]),
    ):
        ids = sorted(i for i in ids if all(i in panel[j] for j in judges))
        mine = [ours[i] for i in ids]
        per_judge = {}
        for j in judges:
            theirs = [panel[j][i] for i in ids]
            per_judge[j] = {
                "exact": sum(1 for x, y in zip(mine, theirs) if x == y) / len(ids),
                "kappa": cohen_kappa(mine, theirs),
            }
        majority = []
        for i in ids:
            votes = Counter(panel[j][i] for j in judges)
            top, n_top = votes.most_common(1)[0]
            tie = sum(1 for _, v in votes.items() if v == n_top) > 1
            majority.append("tied" if tie else top)
        rows = [[panel[j][i] for j in judges] for i in ids]
        # the binary distinction the paper's negative conclusion uses
        bin_mine = ["stands" if v == "survives" else "does_not_stand" for v in mine]
        bin_maj = [
            "stands" if v == "survives" else "does_not_stand" for v in majority
        ]
        bin_rows = [
            ["stands" if v == "survives" else "does_not_stand" for v in r] for r in rows
        ]
        results[scope] = {
            "n_cases": len(ids),
            "case_ids": ids,
            "per_judge": per_judge,
            "mean_judge_exact": sum(v["exact"] for v in per_judge.values()) / len(per_judge),
            "mean_judge_exact_ci95": boot_ci([v["exact"] for v in per_judge.values()]),
            "mean_judge_kappa": sum(v["kappa"] for v in per_judge.values()) / len(per_judge),
            "majority_exact": sum(1 for x, y in zip(mine, majority) if x == y) / len(ids),
            "majority_kappa": cohen_kappa(mine, majority),
            "panel_fleiss_kappa": fleiss_kappa(rows),
            "panel_unanimous_share": sum(1 for r in rows if len(set(r)) == 1) / len(ids),
            "binary_majority_exact": sum(
                1 for x, y in zip(bin_mine, bin_maj) if x == y
            ) / len(ids),
            "binary_majority_kappa": cohen_kappa(bin_mine, bin_maj),
            "binary_panel_fleiss_kappa": fleiss_kappa(bin_rows),
            "binary_panel_unanimous_share": sum(
                1 for r in bin_rows if len(set(r)) == 1
            ) / len(ids),
            "our_marginal": dict(Counter(mine)),
            "majority_marginal": dict(Counter(majority)),
        }
        print(f"[{scope}] n={len(ids)}")
        print(
            f"   mean judge exact {results[scope]['mean_judge_exact']:.3f}  "
            f"mean kappa {results[scope]['mean_judge_kappa']:+.3f}  "
            f"majority exact {results[scope]['majority_exact']:.3f} "
            f"kappa {results[scope]['majority_kappa']:+.3f}  "
            f"panel Fleiss {results[scope]['panel_fleiss_kappa']:+.3f}"
        )
        print(
            f"   binary: majority exact {results[scope]['binary_majority_exact']:.3f} "
            f"kappa {results[scope]['binary_majority_kappa']:+.3f} "
            f"panel Fleiss {results[scope]['binary_panel_fleiss_kappa']:+.3f} "
            f"unanimous {results[scope]['binary_panel_unanimous_share']:.3f}"
        )

    per_case = {}
    for cid in sorted(ours):
        votes = [panel[j].get(cid, "") for j in judges]
        per_case[cid] = {
            "ours": ours[cid],
            "class": klass[cid],
            "type": ctype[cid],
            "votes": dict(Counter(votes)),
            "agree_with_us": sum(1 for v in votes if v == ours[cid]),
            "n_judges": len(votes),
        }
    results["per_case"] = per_case
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")

    write_table(results, per_case, judges)
    return 0


def write_table(results: dict, per_case: dict, judges: list[str]) -> None:
    order = [c for c in per_case if per_case[c]["class"] == "cross_paper"] + [
        c for c in per_case if per_case[c]["class"] != "cross_paper"
    ]
    rows = []
    for cid in order:
        entry = per_case[cid]
        votes = entry["votes"]
        spread = ", ".join(
            f"{k[:4]}~{v}" for k, v in sorted(votes.items(), key=lambda kv: -kv[1]) if k
        )
        rows.append(
            " & ".join(
                [
                    cid.replace("_", "\\_"),
                    "cross" if entry["class"] == "cross_paper" else "ctrl",
                    entry["ours"],
                    spread,
                    f"{entry['agree_with_us']}/{entry['n_judges']}",
                ]
            )
            + r" \\"
        )
    cp = results["cross_paper"]
    tab = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{@{}lllll@{}}",
        r"\toprule",
        r"Case & Kind & Ours & Independent panel & Agree \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{The ledger holds up on the distinction it is used for and "
        r"not on the three-way label. Six judges from three developers re-code "
        r"every case from the neutral statement of the juxtaposition and the "
        r"verbatim source excerpts alone, never seeing our coordinate labels, "
        r"our reading, our matched number or our verdict. On the "
        + str(cp["n_cases"])
        + r" cross-paper cases the panel majority reproduces our three-way "
        r"verdict on "
        + f"{cp['majority_exact'] * 100:.0f}\\%"
        + r" of cases ($\kappa=" + f"{cp['majority_kappa']:.2f}" + r"$), and "
        r"agreement among the six judges themselves is $\kappa="
        + f"{cp['panel_fleiss_kappa']:.2f}" + r"$. On the binary distinction "
        r"the paper's conclusion actually uses---does the quoted gap stand as "
        r"reported---the majority reproduces us on "
        + f"{cp['binary_majority_exact'] * 100:.0f}\\%"
        + r" and the panel is unanimous on "
        + f"{cp['binary_panel_unanimous_share'] * 100:.0f}\\%"
        + r" of cases. This is why we report the ledger's negative statements "
        r"and not a rate.}",
        r"\label{tab:ledger-recoding}",
        r"\end{table}",
    ]
    (TAB / "ledger_recoding.tex").write_text("\n".join(tab) + "\n", encoding="utf-8")
    print(f"wrote {TAB / 'ledger_recoding.tex'}")


if __name__ == "__main__":
    raise SystemExit(main())
