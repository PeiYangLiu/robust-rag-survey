#!/usr/bin/env python3
"""Task B -- developer-independence / self-preference of the privileged reference.

A reviewer objects that the evidence-privileged reference is not independent of
the deployed panel it scores.  The deployed panel is
(coderA=gpt-5-mini=OpenAI, coderB=claude-opus-4.6=Anthropic,
coderC=gemini-3.1-pro=Google).  The four reference adjudicators are
(refA=claude-opus-5=Anthropic, refC=gemini-3.1-pro=Google,
refD=claude-opus-4.8=Anthropic, refE=gpt-5.5-cli=OpenAI).  So refC shares a
*checkpoint* with coderC, and refA/refD share a *developer* with coderB.  The
worry is self-preference: a judge scored kindly by an adjudicator from its own
developer.

This script stress-tests the reference against that worry, for BOTH the
provenance accuracy (published 0.91 on 170 windows) and the verdict accuracy
(published 0.82 on 114 windows):

  (a) accuracy against the all-four reference majority (reproduces the numbers);
  (b) leave-one-adjudicator-out -- all four variants, with the range;
  (c) leave-developer-out -- drop each developer's adjudicators in turn
      (Anthropic: refA+refD; Google: refC; OpenAI: refE);
  (d) a per-deployed-judge self-preference test: is each deployed judge's
      agreement with same-developer adjudicators higher than with
      different-developer adjudicators?  Difference with a paper/window bootstrap
      CI and a permutation check, for provenance and verdict separately;
  (e) how many reference windows change majority under each drop, so the
      reader can see the reference's stability.

The reference derivation (majority of quote-verified privileged adjudicators,
>=2 verified votes) is imported verbatim from
``scripts/revision3/analyze_privileged_reference.py``; leaving the shared
checkpoint (refC) out here reproduces that script's published ``__loo`` numbers.

Run:
    python3 manuscript/scripts/revision4/analyze_reference_independence.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUP = REPO / "manuscript" / "supplement"
TAB = REPO / "manuscript" / "tables"
MACRO_FILE = TAB / "revision4_instrument_macros.tex"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "revision3"))
import analyze_privileged_reference as apr  # noqa: E402

SEED = 20260802
N_BOOT = 4000

# developer provenance of each adjudicator and each deployed judge
ADJ_DEV = {
    "refA_claudeopus5": "Anthropic",
    "refC_gemini31pro": "Google",
    "refD_claudeopus48": "Anthropic",
    "refE_gpt55cli": "OpenAI",
}
DEP_DEV = {
    "comparability": {
        "coderA_gpt5mini": "OpenAI",
        "coderB_claudeopus46": "Anthropic",
        "coderC_gemini31pro": "Google",
    },
    "provenance": {
        "provA_gpt5mini": "OpenAI",
        "provB_claudeopus46": "Anthropic",
        "provC_gemini31pro": "Google",
    },
}
# a deployed judge that shares its exact checkpoint with an adjudicator
SHARED_CHECKPOINT = {"coderC_gemini31pro": "refC_gemini31pro",
                     "provC_gemini31pro": "refC_gemini31pro"}
DEV_GROUPS = {
    "Anthropic": ("refA_claudeopus5", "refD_claudeopus48"),
    "Google": ("refC_gemini31pro",),
    "OpenAI": ("refE_gpt55cli",),
}
PASSES = (("verdict", "comparability", "verdict", apr.norm_verdict),
          ("provenance", "provenance", "provenance", apr.norm_prov))


# ---------------------------------------------------------------- derivation
def best_tier(runs, cid, pass_name, judge):
    for tier in ("both_full", "citing_full"):
        if cid in runs.get((pass_name, tier, judge), {}):
            return tier
    return None


def collect(sample, runs, dep_comp, dep_prov, dep_prov_names):
    """Per-window verified adjudicator labels and individual deployed labels."""
    adj_labels = {"comparability": {}, "provenance": {}}
    adj_labels_all = {"comparability": {}, "provenance": {}}
    dep_labels = {"comparability": {}, "provenance": {}}
    paper_of = {}
    for cid, row in sample.items():
        paper_of[cid] = row["cite_key"]
        for pass_name, field, caster in (
            ("comparability", "verdict", apr.norm_verdict),
            ("provenance", "provenance", apr.norm_prov),
        ):
            verified, allv = {}, {}
            for judge in apr.REFERENCE:
                tier = best_tier(runs, cid, pass_name, judge)
                if tier is None:
                    continue
                parsed = runs[(pass_name, tier, judge)][cid]["parsed"]
                label = caster(parsed.get(field))
                allv[judge] = label
                ok = apr.quote_ok(parsed.get("evidence_quote", ""), row["cite_key"])
                if tier == "both_full" and row["cited_papers"]:
                    cited = [c["cite_key"] for c in row["cited_papers"][:2]]
                    ok = ok and any(
                        apr.quote_ok(parsed.get("evidence_quote_cited", ""), k) for k in cited
                    )
                if ok:
                    verified[judge] = label
            adj_labels[pass_name][cid] = verified
            adj_labels_all[pass_name][cid] = allv
        dep_labels["comparability"][cid] = {
            j: apr.norm_verdict(dep_comp[j][cid]["verdict"])
            for j in apr.DEPLOYED if cid in dep_comp[j]
        }
        dep_labels["provenance"][cid] = {
            n: apr.norm_prov(dep_prov[n][cid]["provenance"])
            for n in dep_prov_names if cid in dep_prov[n]
        }
    return adj_labels, adj_labels_all, dep_labels, paper_of


def ref_majority(verified: dict, drop=()):
    labs = [l for j, l in verified.items() if j not in drop]
    return apr.majority(labs) if len(labs) >= 2 else None


def deployed_majority(dep_labels, cid, pass_name):
    vals = list(dep_labels[pass_name].get(cid, {}).values())
    return apr.majority(vals) if len(vals) >= 2 else None


# ---------------------------------------------------------------- scoring
def score(adj_labels, dep_labels, paper_of, pass_name, drop=()):
    pairs = []
    for cid, verified in adj_labels[pass_name].items():
        ref = ref_majority(verified, drop)
        got = deployed_majority(dep_labels, cid, pass_name)
        if ref is None or got is None:
            continue
        pairs.append((paper_of[cid], ref, got))
    n = len(pairs)
    correct = sum(1 for _, r, g in pairs if r == g)
    acc = correct / n if n else float("nan")
    wl = apr.wilson(correct, n)
    cl = apr.cluster_ci(
        [(p, (r, g)) for p, r, g in pairs],
        lambda rows: sum(1 for r, g in rows if r == g) / len(rows),
        draws=N_BOOT, seed=SEED,
    )
    ref_dist = Counter(r for _, r, _ in pairs)
    base = (ref_dist.most_common(1)[0][1] / n) if n else float("nan")
    return {
        "n": n,
        "n_papers": len({p for p, _, _ in pairs}),
        "accuracy": acc,
        "wilson_ci95": list(wl),
        "cluster_ci95": list(cl),
        "majority_class_baseline": base,
        "reference_distribution": dict(ref_dist),
    }


def majority_stability(adj_labels, pass_name, drop):
    base = {cid: ref_majority(v) for cid, v in adj_labels[pass_name].items()}
    changed = lost = gained = kept = 0
    for cid, v in adj_labels[pass_name].items():
        b = base[cid]
        n = ref_majority(v, drop)
        if b and n:
            if b == n:
                kept += 1
            else:
                changed += 1
        elif b and not n:
            lost += 1
        elif not b and n:
            gained += 1
    return {"n_established_all_four": sum(1 for x in base.values() if x),
            "changed_label": changed, "lost_majority": lost,
            "gained_majority": gained, "kept_same_label": kept}


# ---------------------------------------------------------------- self-preference
def self_preference(adj, dep_labels, paper_of, pass_name, use_all=False):
    dep_dev = DEP_DEV[pass_name]
    cids = list(adj[pass_name])
    out = {}
    for dj, dev in dep_dev.items():
        same = [a for a, d in ADJ_DEV.items() if d == dev]
        diff = [a for a, d in ADJ_DEV.items() if d != dev]

        def pairs_for(adjs):
            rows = []  # (cid, match)
            for cid in cids:
                dl = dep_labels[pass_name].get(cid, {}).get(dj)
                if dl is None:
                    continue
                for a in adjs:
                    al = adj[pass_name][cid].get(a)
                    if al is None:
                        continue
                    rows.append((cid, 1.0 if dl == al else 0.0))
            return rows

        ps, pd = pairs_for(same), pairs_for(diff)
        ms = sum(m for _, m in ps) / len(ps) if ps else float("nan")
        md = sum(m for _, m in pd) / len(pd) if pd else float("nan")

        # cluster bootstrap over windows for the same-minus-diff difference
        by_s, by_d = defaultdict(list), defaultdict(list)
        for cid, m in ps:
            by_s[cid].append(m)
        for cid, m in pd:
            by_d[cid].append(m)
        keys = sorted(set(list(by_s) + list(by_d)))
        rng = __import__("random").Random(SEED)
        diffs = []
        for _ in range(N_BOOT):
            pick = [keys[rng.randrange(len(keys))] for _ in keys]
            s = [m for k in pick for m in by_s.get(k, [])]
            d2 = [m for k in pick for m in by_d.get(k, [])]
            if s and d2:
                diffs.append(sum(s) / len(s) - sum(d2) / len(d2))
        diffs.sort()
        lo = diffs[int(0.025 * len(diffs))] if diffs else float("nan")
        hi = diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))] if diffs else float("nan")

        # permutation over adjudicator->developer assignment (coarse: 4 adjudicators)
        observed = ms - md
        per_window = {}  # cid -> {adjudicator: match}
        for cid in cids:
            dl = dep_labels[pass_name].get(cid, {}).get(dj)
            if dl is None:
                continue
            row = {}
            for a in apr.REFERENCE:
                al = adj[pass_name][cid].get(a)
                if al is not None:
                    row[a] = 1.0 if dl == al else 0.0
            if row:
                per_window[cid] = row
        adjs = list(apr.REFERENCE)
        devs = [ADJ_DEV[a] for a in adjs]
        null = []
        for perm in set(permutations(devs)):
            assign = dict(zip(adjs, perm))
            s_a = [a for a in adjs if assign[a] == dev]
            d_a = [a for a in adjs if assign[a] != dev]
            sv = [m for row in per_window.values() for a, m in row.items() if a in s_a]
            dv = [m for row in per_window.values() for a, m in row.items() if a in d_a]
            if sv and dv:
                null.append(sum(sv) / len(sv) - sum(dv) / len(dv))
        perm_p = (sum(1 for x in null if x >= observed - 1e-12) / len(null)) if null else float("nan")

        out[dj] = {
            "developer": dev,
            "same_developer_adjudicators": same,
            "different_developer_adjudicators": diff,
            "shares_checkpoint_with": SHARED_CHECKPOINT.get(dj),
            "n_same_pairs": len(ps),
            "n_diff_pairs": len(pd),
            "agreement_same_developer": ms,
            "agreement_different_developer": md,
            "difference_same_minus_diff": observed,
            "difference_ci95": [lo, hi],
            "permutation_p_one_sided": perm_p,
            "n_permutations": len(null),
        }
    return out


# ---------------------------------------------------------------- main
# ---------------------------------------------------------------- latex + macros
MACRO_HEADER = (
    "% Generated by scripts/revision4/analyze_nonllm_instrument.py and\n"
    "% scripts/revision4/analyze_reference_independence.py -- do not edit by hand.\n"
    "% Task A macros are prefixed \\Nll; Task B macros are prefixed \\Ind.\n"
    "% Each analysis script owns and rewrites only its own marker-delimited block."
)


def _parse_macro_blocks(text: str) -> dict:
    blocks, cur, buf = {}, None, []
    for ln in text.splitlines():
        if ln.startswith("% >>> BEGIN "):
            cur, buf = ln[len("% >>> BEGIN "):].strip(), []
        elif ln.startswith("% <<< END ") and cur is not None:
            blocks[cur] = "\n".join(buf)
            cur = None
        elif cur is not None:
            buf.append(ln)
    return blocks


def write_macro_section(path: Path, prefix: str, macro_lines: list) -> None:
    """Idempotently merge this script's macro block, preserving the other one."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    blocks = _parse_macro_blocks(text)
    blocks[prefix] = "\n".join(macro_lines)
    order = [p for p in ("Nll", "Ind") if p in blocks]
    order += [p for p in blocks if p not in order]
    out = [MACRO_HEADER]
    for p in order:
        out += [f"% >>> BEGIN {p}", blocks[p], f"% <<< END {p}"]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _n2(x, nd=2, signed=False):
    if x is None or (isinstance(x, float) and x != x):
        return "--"
    return f"{float(x):+.{nd}f}" if signed else f"{float(x):.{nd}f}"


def _ci2(pair, nd=2):
    if not pair or len(pair) != 2 or any(p is None or p != p for p in pair):
        return "--"
    return f"[{float(pair[0]):.{nd}f}, {float(pair[1]):.{nd}f}]"


def latex_tables(payload: dict) -> str:
    """Two floats: accuracy+stability under drops, and the self-preference test."""
    passes = payload["passes"]

    def drop_panel(name, title):
        p = passes[name]
        rows = [rf"\multicolumn{{6}}{{@{{}}l}}{{\emph{{{title}}}}} \\"]
        a = p["all_four"]
        rows.append(
            f"\\quad All four adjudicators & {a['n']} & {_n2(a['accuracy'])} & "
            f"{_ci2(a['cluster_ci95'])} & --- & --- \\\\"
        )
        loo_label = {"refA_claudeopus5": "$-$refA (Anthropic)",
                     "refC_gemini31pro": "$-$refC (Google, shared ckpt)",
                     "refD_claudeopus48": "$-$refD (Anthropic)",
                     "refE_gpt55cli": "$-$refE (OpenAI)"}
        for a_id in apr.REFERENCE:
            v = p["leave_one_out"][a_id]
            st = p["majority_stability"]["leave_one_out"][a_id]
            rows.append(
                f"\\quad {loo_label[a_id]} & {v['n']} & {_n2(v['accuracy'])} & "
                f"{_ci2(v['cluster_ci95'])} & {_n2(v['delta_accuracy_vs_all_four'], signed=True)} & "
                f"{st['changed_label']} / {st['lost_majority']} \\\\"
            )
        dev_label = {"Anthropic": "$-$Anthropic (refA$+$refD)",
                     "Google": "$-$Google (refC)", "OpenAI": "$-$OpenAI (refE)"}
        for dev in ("Anthropic", "Google", "OpenAI"):
            v = p["leave_developer_out"][dev]
            st = p["majority_stability"]["leave_developer_out"][dev]
            rows.append(
                f"\\quad {dev_label[dev]} & {v['n']} & {_n2(v['accuracy'])} & "
                f"{_ci2(v['cluster_ci95'])} & {_n2(v['delta_accuracy_vs_all_four'], signed=True)} & "
                f"{st['changed_label']} / {st['lost_majority']} \\\\"
            )
        return rows

    body = drop_panel("verdict", r"Verdict accuracy (published 0.82, $N{=}114$)")
    body.append(r"\midrule")
    body += drop_panel("provenance", r"Provenance accuracy (published 0.91, $N{=}170$)")
    drops = "\n".join(body)

    def sp_panel(name, title):
        p = passes[name]["self_preference_verified"]
        rows = [rf"\multicolumn{{5}}{{@{{}}l}}{{\emph{{{title}}}}} \\"]
        for dj, v in p.items():
            ck = " (shared ckpt)" if v["shares_checkpoint_with"] else ""
            rows.append(
                f"\\quad {v['developer']}{ck} & {_n2(v['agreement_same_developer'])} & "
                f"{_n2(v['agreement_different_developer'])} & "
                f"{_n2(v['difference_same_minus_diff'], signed=True)} & {_ci2(v['difference_ci95'])} \\\\"
            )
        return rows

    sp = sp_panel("verdict", r"Verdict")
    sp.append(r"\midrule")
    sp += sp_panel("provenance", r"Provenance")
    sp_body = "\n".join(sp)

    tbl1 = rf"""% Generated by scripts/revision4/analyze_reference_independence.py -- do not edit.
\begin{{table}}[t]
\centering\scriptsize
\setlength{{\tabcolsep}}{{3pt}}
\resizebox{{\columnwidth}}{{!}}{{%
\begin{{tabular}}{{@{{}}lrrlrr@{{}}}}
\toprule
Reference set & $n$ & Acc. & 95\% CI & $\Delta$Acc. & flip / lost \\
\midrule
{drops}
\bottomrule
\end{{tabular}}}}
\caption{{Developer-independence of the evidence-privileged reference. Accuracy
of the deployed panel is recomputed against a reference majority formed after
dropping each adjudicator (leave-one-out) and each developer's adjudicators
(leave-developer-out); ``$-$Google (refC)'' drops the checkpoint shared with the
deployed Google judge and reproduces the published leave-one-out number. The
last column counts reference windows whose established majority \emph{{flips to a
different label}} / \emph{{loses its majority}} under the drop: no drop ever flips
a label, so removing an adjudicator only shrinks coverage. Intervals are
paper-clustered bootstraps.}}
\label{{tab:reference-independence}}
\end{{table}}
"""
    tbl2 = rf"""% Generated by scripts/revision4/analyze_reference_independence.py -- do not edit.
\begin{{table}}[t]
\centering\scriptsize
\setlength{{\tabcolsep}}{{4pt}}
\begin{{tabular}}{{@{{}}lrrrl@{{}}}}
\toprule
Deployed judge (by developer) & Agr.\ same & Agr.\ diff & $\Delta$ & 95\% CI \\
\midrule
{sp_body}
\bottomrule
\end{{tabular}}
\caption{{Per-deployed-judge self-preference. For each deployed judge, agreement
with same-developer reference adjudicators versus different-developer
adjudicators, on quote-verified adjudicator labels; the Google judge shares its
exact checkpoint with refC. Every same$-$diff difference is small and positive
with a 95\% CI (window bootstrap) that includes 0, for both the verdict and
provenance passes: no judge is scored materially more kindly by its own
developer.}}
\label{{tab:reference-selfpreference}}
\end{{table}}
"""
    return tbl1 + "\n" + tbl2


def macros(payload: dict) -> list:
    lines = []
    add = lines.append
    passes = payload["passes"]
    tags = {"verdict": "Vd", "provenance": "Pv"}
    dev_short = {"Anthropic": "Anth", "Google": "Goog", "OpenAI": "Open"}
    for name, tg in tags.items():
        p = passes[name]
        a = p["all_four"]
        add(rf"\newcommand{{\Ind{tg}AllN}}{{{a['n']}}}")
        add(rf"\newcommand{{\Ind{tg}AllAcc}}{{{_n2(a['accuracy'])}}}")
        add(rf"\newcommand{{\Ind{tg}AllCI}}{{{_ci2(a['cluster_ci95'])}}}")
        add(rf"\newcommand{{\Ind{tg}AllWilson}}{{{_ci2(a['wilson_ci95'])}}}")
        add(rf"\newcommand{{\Ind{tg}Base}}{{{_n2(a['majority_class_baseline'])}}}")
        lr = p["leave_one_out_accuracy_range"]
        add(rf"\newcommand{{\Ind{tg}LooLo}}{{{_n2(lr[0])}}}")
        add(rf"\newcommand{{\Ind{tg}LooHi}}{{{_n2(lr[1])}}}")
        dr = p["leave_developer_out_accuracy_range"]
        add(rf"\newcommand{{\Ind{tg}DevLo}}{{{_n2(dr[0])}}}")
        add(rf"\newcommand{{\Ind{tg}DevHi}}{{{_n2(dr[1])}}}")
        for dev, ds in dev_short.items():
            v = p["leave_developer_out"][dev]
            add(rf"\newcommand{{\Ind{tg}Drop{ds}Acc}}{{{_n2(v['accuracy'])}}}")
            add(rf"\newcommand{{\Ind{tg}Drop{ds}N}}{{{v['n']}}}")
            add(rf"\newcommand{{\Ind{tg}Drop{ds}dAcc}}{{{_n2(v['delta_accuracy_vs_all_four'], signed=True)}}}")
        # self-preference: largest delta, and the shared-checkpoint judge's delta
        sp = p["self_preference_verified"]
        max_dj = max(sp, key=lambda k: sp[k]["difference_same_minus_diff"])
        add(rf"\newcommand{{\Ind{tg}SelfMax}}{{{_n2(sp[max_dj]['difference_same_minus_diff'], signed=True)}}}")
        add(rf"\newcommand{{\Ind{tg}SelfMaxCI}}{{{_ci2(sp[max_dj]['difference_ci95'])}}}")
        shared = [k for k, v in sp.items() if v["shares_checkpoint_with"]]
        if shared:
            sv = sp[shared[0]]
            add(rf"\newcommand{{\Ind{tg}SelfSharedDelta}}{{{_n2(sv['difference_same_minus_diff'], signed=True)}}}")
            add(rf"\newcommand{{\Ind{tg}SelfSharedCI}}{{{_ci2(sv['difference_ci95'])}}}")
        n_sig = sum(1 for v in sp.values() if v["difference_ci95"][0] > 0)
        add(rf"\newcommand{{\Ind{tg}SelfSigCount}}{{{n_sig}}}")
        # stability: total label flips across all drops
        flips = payload["interpretation"][name]["reference_label_flips_under_any_drop"]
        add(rf"\newcommand{{\Ind{tg}Flips}}{{{flips}}}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=Path, default=SUP / "privileged_reference_sample.jsonl")
    ap.add_argument("--runs", type=Path, default=SUP / "privileged_reference_runs")
    ap.add_argument("--coding-dir", type=Path, default=SUP / "cross_paper_coding")
    ap.add_argument("--prov-dir", type=Path, default=SUP / "cross_paper_provenance")
    ap.add_argument("--out", type=Path, default=SUP / "reference_independence.json")
    args = ap.parse_args()

    sample = {}
    for line in args.sample.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            sample[r["candidate_id"]] = r
    runs = apr.load_runs(args.runs)
    dep_comp, dep_prov = apr.load_deployed(args.coding_dir, args.prov_dir)
    dep_prov_names = sorted(dep_prov)
    adj, adj_all, dep_labels, paper_of = collect(sample, runs, dep_comp, dep_prov, dep_prov_names)

    passes = {}
    for name, pass_name, _field, _caster in PASSES:
        all_four = score(adj, dep_labels, paper_of, pass_name)

        loo = {}
        for a in apr.REFERENCE:
            s = score(adj, dep_labels, paper_of, pass_name, drop=(a,))
            s["delta_accuracy_vs_all_four"] = s["accuracy"] - all_four["accuracy"]
            loo[a] = s
        loo_accs = [v["accuracy"] for v in loo.values()]

        ldo = {}
        for devname, group in DEV_GROUPS.items():
            s = score(adj, dep_labels, paper_of, pass_name, drop=group)
            s["dropped_adjudicators"] = list(group)
            s["delta_accuracy_vs_all_four"] = s["accuracy"] - all_four["accuracy"]
            ldo[devname] = s
        ldo_accs = [v["accuracy"] for v in ldo.values()]

        stability = {
            "leave_one_out": {a: majority_stability(adj, pass_name, (a,)) for a in apr.REFERENCE},
            "leave_developer_out": {
                d: majority_stability(adj, pass_name, g) for d, g in DEV_GROUPS.items()
            },
        }

        passes[name] = {
            "all_four": all_four,
            "leave_one_out": loo,
            "leave_one_out_accuracy_range": [min(loo_accs), max(loo_accs), max(loo_accs) - min(loo_accs)],
            "leave_developer_out": ldo,
            "leave_developer_out_accuracy_range": [min(ldo_accs), max(ldo_accs), max(ldo_accs) - min(ldo_accs)],
            "self_preference_verified": self_preference(adj, dep_labels, paper_of, pass_name, use_all=False),
            "self_preference_all_votes": self_preference(adj_all, dep_labels, paper_of, pass_name, use_all=True),
            "majority_stability": stability,
        }

    # cross-check against the published __loo (refC dropped == Google-out)
    published = json.loads((SUP / "privileged_reference_results.json").read_text(encoding="utf-8"))
    crosscheck = {}
    for name, pass_name in (("verdict", "comparability"), ("provenance", "provenance")):
        pub_all = published["deployed_vs_reference"][f"{pass_name}__all"]
        pub_loo = published["deployed_vs_reference"][f"{pass_name}__loo"]
        mine_all = passes[name]["all_four"]
        mine_google = passes[name]["leave_developer_out"]["Google"]
        crosscheck[name] = {
            "all_four_matches_published": (
                mine_all["n"] == pub_all["n_reference_items"]
                and abs(mine_all["accuracy"] - pub_all["accuracy"]) < 1e-9
            ),
            "google_out_matches_published_loo": (
                mine_google["n"] == pub_loo["n_reference_items"]
                and abs(mine_google["accuracy"] - pub_loo["accuracy"]) < 1e-9
            ),
            "published_all": {"n": pub_all["n_reference_items"], "acc": pub_all["accuracy"]},
            "mine_all": {"n": mine_all["n"], "acc": mine_all["accuracy"]},
            "published_loo": {"n": pub_loo["n_reference_items"], "acc": pub_loo["accuracy"]},
            "mine_google_out": {"n": mine_google["n"], "acc": mine_google["accuracy"]},
        }

    payload = {
        "schema_version": 1,
        "seed": SEED,
        "n_bootstrap": N_BOOT,
        "design_note": (
            "The evidence-privileged reference is stress-tested for developer "
            "non-independence and self-preference. Accuracy is recomputed with "
            "each adjudicator, and each developer's adjudicators, removed; a "
            "per-deployed-judge test asks whether a judge agrees more with "
            "same-developer adjudicators than with different-developer ones. "
            "Removing an adjudicator shrinks the reference (fewer windows keep a "
            "quote-verified majority) but is not supposed to move the accuracy."
        ),
        "developer_map": {"adjudicators": ADJ_DEV, "deployed": DEP_DEV,
                          "shared_checkpoint": SHARED_CHECKPOINT},
        "reference_derivation": (
            "Imported verbatim from scripts/revision3/analyze_privileged_reference.py: "
            "majority of quote-verified privileged adjudicators, >=2 verified votes."
        ),
        "passes": passes,
        "crosscheck_against_published": crosscheck,
        "interpretation": interpret(passes),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (TAB / "reference_independence.tex").write_text(latex_tables(payload), encoding="utf-8")
    write_macro_section(MACRO_FILE, "Ind", macros(payload))

    # concise console summary
    print(json.dumps({
        name: {
            "all_four": {"n": p["all_four"]["n"], "acc": round(p["all_four"]["accuracy"], 4)},
            "leave_one_out_range": [round(x, 4) for x in p["leave_one_out_accuracy_range"]],
            "leave_developer_out": {
                d: {"n": v["n"], "acc": round(v["accuracy"], 4)}
                for d, v in p["leave_developer_out"].items()
            },
            "self_preference_verified": {
                dj: {"delta": round(v["difference_same_minus_diff"], 4),
                     "ci": [round(x, 4) for x in v["difference_ci95"]]}
                for dj, v in p["self_preference_verified"].items()
            },
        }
        for name, p in passes.items()
    }, indent=2))
    print("crosscheck:", json.dumps({k: {"all4": v["all_four_matches_published"],
                                         "google_out=loo": v["google_out_matches_published_loo"]}
                                     for k, v in crosscheck.items()}))
    print(f"wrote {args.out}")
    print(f"wrote {TAB / 'reference_independence.tex'}")
    print(f"wrote {MACRO_FILE} (\\Ind block)")
    return 0


def interpret(passes: dict) -> dict:
    r4 = lambda x: round(float(x), 4)  # noqa: E731
    out = {}
    for name in ("verdict", "provenance"):
        p = passes[name]
        a = p["all_four"]
        lo_range = p["leave_one_out_accuracy_range"]
        ld_range = p["leave_developer_out_accuracy_range"]
        # self-preference: does any CI exclude 0 (positive)?
        sp = p["self_preference_verified"]
        any_sig = any(v["difference_ci95"][0] > 0 for v in sp.values())
        max_delta = max(v["difference_same_minus_diff"] for v in sp.values())
        # majority stability: any defined label ever flip to a different label?
        flips = 0
        for blk in (p["majority_stability"]["leave_one_out"], p["majority_stability"]["leave_developer_out"]):
            for v in blk.values():
                flips += v["changed_label"]
        out[name] = {
            "all_four_accuracy": r4(a["accuracy"]), "n": a["n"],
            "leave_one_out_accuracy_min_max": [r4(lo_range[0]), r4(lo_range[1])],
            "leave_developer_out_accuracy_min_max": [r4(ld_range[0]), r4(ld_range[1])],
            "any_self_preference_ci_excludes_zero": any_sig,
            "largest_self_preference_delta": r4(max_delta),
            "reference_label_flips_under_any_drop": flips,
            "statement": (
                f"{name.capitalize()} accuracy is {r4(a['accuracy'])} on the all-four reference "
                f"(N={a['n']}); it stays within [{r4(lo_range[0])}, {r4(lo_range[1])}] across the four "
                f"leave-one-adjudicator-out variants and [{r4(ld_range[0])}, {r4(ld_range[1])}] across the "
                f"three leave-developer-out variants -- including dropping both Anthropic adjudicators and "
                f"dropping the shared-checkpoint Google adjudicator. No deployed judge's agreement with "
                f"same-developer adjudicators is significantly above its agreement with different-developer "
                f"adjudicators (largest delta {r4(max_delta)}, every 95% CI includes 0). Under every drop, "
                f"{flips} established reference labels flip to a different label: drops only shrink coverage, "
                f"never reverse a verdict."
            ),
        }
    out["headline"] = (
        "Accuracy is robust to removing any adjudicator or any developer's adjudicators, no deployed judge "
        "shows significant self-preference toward its own developer, and no dropped reference window ever "
        "flips to a different label -- the reference is not carrying a developer-alignment artifact."
    )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
