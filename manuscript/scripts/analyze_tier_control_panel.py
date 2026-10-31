#!/usr/bin/env python3
"""Tier-by-developer control for the cross-paper census (reviewer W6).

The submitted panel was one judge per developer -- gpt-5-mini,
claude-opus-4.6, gemini-3.1-pro-preview -- and one of the three is an
explicitly mini-tier model.  A reviewer correctly observed that the pairwise
kappas order exactly by tier, so "verdict disagreement is a property of the
task" is not identified: it is confounded with capability heterogeneity.

This script analyses a panel that crosses capability tier with developer on the
same 1,703-window frame, so the confound is broken by design:

    developer   small tier              frontier tier
    OpenAI      gpt-5-mini              gpt-5.4 (via the Copilot CLI)
    Anthropic   claude-haiku-4.5        claude-opus-4.6,  claude-opus-4.8
    Google      gemini-3.5-flash        gemini-3.1-pro-preview

Four contrasts are reported:

``submitted``     the original three judges, for reference.
``frontier``      one frontier judge per developer.  If the verdict is still
                  unreliable here, the finding is not an artifact of a weak
                  judge.
``small``         one small judge per developer.
``same_dev_tier`` claude-opus-4.6 against claude-opus-4.8: same developer, same
                  tier, same family.  This is the reference level -- the
                  agreement two judges reach when *nothing* differs but the
                  checkpoint.

Writes ``supplement/cross_paper_tier_control.json`` and
``tables/tier_control.tex``.
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
CODING = SUP / "cross_paper_coding"

JUDGE_META = {
    "coderA_gpt5mini": ("OpenAI", "small", "gpt-5-mini"),
    "coderI_gpt54": ("OpenAI", "frontier", "gpt-5.4"),
    "coderJ_gpt55": ("OpenAI", "frontier", "gpt-5.5"),
    "coderE_haiku45": ("Anthropic", "small", "claude-haiku-4.5"),
    "coderB_claudeopus46": ("Anthropic", "frontier", "claude-opus-4.6"),
    "coderG_opus48": ("Anthropic", "frontier", "claude-opus-4.8"),
    "coderF_gemini35flash": ("Google", "small", "gemini-3.5-flash"),
    "coderC_gemini31pro": ("Google", "frontier", "gemini-3.1-pro-preview"),
    "coderH_gemini25pro": ("Google", "frontier", "gemini-2.5-pro"),
}

PANELS = {
    "submitted": ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"],
    "frontier": ["coderI_gpt54", "coderB_claudeopus46", "coderC_gemini31pro"],
    "small": ["coderA_gpt5mini", "coderE_haiku45", "coderF_gemini35flash"],
    "frontier_cross_dev": [
        "coderB_claudeopus46",
        "coderG_opus48",
        "coderC_gemini31pro",
        "coderH_gemini25pro",
        "coderI_gpt54",
        "coderJ_gpt55",
    ],
    "same_dev_tier": ["coderB_claudeopus46", "coderG_opus48"],
    "same_dev_tier_google": ["coderC_gemini31pro", "coderH_gemini25pro"],
    "same_dev_tier_openai": ["coderI_gpt54", "coderJ_gpt55"],
    "cross_dev_frontier_pair_a": ["coderB_claudeopus46", "coderC_gemini31pro"],
    "cross_dev_frontier_pair_b": ["coderG_opus48", "coderH_gemini25pro"],
}

PANEL_LABEL = {
    "submitted": "Deployed panel (1 mini, 2 front.)",
    "frontier": "Frontier only, 3 developers",
    "small": "Small tier only, 3 developers",
    "frontier_cross_dev": "Frontier only, 3 dev.\\ $\\times$ 2 checkpoints",
    "same_dev_tier": "\\quad same dev.\\ (Anthropic)",
    "same_dev_tier_google": "\\quad same dev.\\ (Google)",
    "same_dev_tier_openai": "\\quad same dev.\\ (OpenAI)",
    "cross_dev_frontier_pair_a": "\\quad across dev.\\ (pair A)",
    "cross_dev_frontier_pair_b": "\\quad across dev.\\ (pair B)",
}


# --------------------------------------------------------------------------
# agreement statistics (kept identical to analyze_cross_paper_census.py)
# --------------------------------------------------------------------------
def fleiss_kappa(rows: list[list[str]]) -> float:
    rows = [r for r in rows if r]
    if not rows:
        return float("nan")
    n = len(rows[0])
    if n < 2 or any(len(r) != n for r in rows):
        return float("nan")
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


def gwet_ac1(rows: list[list[str]]) -> float:
    rows = [r for r in rows if r]
    if not rows:
        return float("nan")
    n = len(rows[0])
    if n < 2 or any(len(r) != n for r in rows):
        return float("nan")
    cats = sorted({v for r in rows for v in r})
    if len(cats) < 2:
        return 1.0
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
    pis = [m / total for m in marg]
    q = len(cats)
    p_e = sum(p * (1 - p) for p in pis) / (q - 1)
    return float("nan") if abs(1 - p_e) < 1e-12 else (p_bar - p_e) / (1 - p_e)


def clustered(labels, cluster_of, stat, draws=2000, seed=2026073001):
    by_cluster = defaultdict(list)
    for item, row in labels.items():
        by_cluster[cluster_of.get(item, item)].append(row)
    keys = list(by_cluster)
    if len(keys) < 2:
        return {}
    point = stat(list(labels.values()))
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        picked = [rng.choice(keys) for _ in keys]
        rows = [r for k in picked for r in by_cluster[k]]
        if len(rows) > 3:
            v = stat(rows)
            if v == v:
                out.append(v)
    if not out:
        return {"point": point}
    out.sort()
    return {
        "point": point,
        "ci95": [out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))]],
        "n_clusters": len(keys),
        "n_items": len(labels),
        "draws": len(out),
    }


def load_judge(name: str) -> dict[str, dict]:
    path = CODING / f"{name}.jsonl"
    table = {}
    if not path.exists():
        return table
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("parsed"):
            table[row["candidate_id"]] = row
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coverage", type=float, default=0.95)
    ap.add_argument("--output", type=Path, default=SUP / "cross_paper_tier_control.json")
    args = ap.parse_args()

    windows = {}
    for line in (SUP / "cross_paper_frame_candidates.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if line.strip():
            row = json.loads(line)
            windows[row["candidate_id"]] = row
    cluster_of = {cid: w["cite_key"] for cid, w in windows.items()}

    tables = {name: load_judge(name) for name in JUDGE_META}
    # Coverage is over the frame.  Counting ids a judge wrote for an older
    # frame revision produced impossible values above 100%.
    coverage = {
        n: len(set(t) & set(windows)) / len(windows) for n, t in tables.items()
    }
    for name, cov in sorted(coverage.items()):
        print(
            f"  {name:26s} coverage {cov:6.1%}  "
            f"({len(set(tables[name]) & set(windows))} of {len(windows)})"
        )

    results = {"coverage": coverage, "judge_meta": {k: list(v) for k, v in JUDGE_META.items()}}

    # ------------------------------------------------------------------
    # A single item population shared by every panel.
    #
    # Comparing kappa across panels each of which is evaluated on its own
    # majority-eligible subset confounds judge capability with item
    # composition, because kappa is prevalence sensitive.  We therefore fix
    # one population, defined by the *whole nine-judge pool* and so identical
    # for every panel:
    #
    #   pool_common      every candidate all nine judges returned a parseable
    #                    coding for;
    #   pool_eligible    the subset of pool_common that a majority of the nine
    #                    judges called eligible.  Panel membership plays no
    #                    part in this definition.
    #
    # Every headline comparison below is computed on ``pool_eligible``.  The
    # panel's own subset is retained under ``*_own`` for continuity with the
    # released artifact, and an all-item analysis that drops nothing --
    # ineligibility is carried as its own verdict category rather than as a
    # deletion -- is reported as ``*_allitems``.
    # ------------------------------------------------------------------
    full = [n for n in JUDGE_META if coverage.get(n, 0) >= args.min_coverage]
    pool_common = sorted(set.intersection(*(set(tables[m]) for m in full)) & set(windows))
    pool_elig_votes = {
        cid: sum(bool(tables[m][cid]["parsed"].get("eligible")) for m in full)
        for cid in pool_common
    }
    pool_eligible = [
        cid for cid in pool_common if pool_elig_votes[cid] * 2 > len(full)
    ]
    results["pool"] = {
        "judges": full,
        "n_common": len(pool_common),
        "n_pool_eligible": len(pool_eligible),
        "rule": "majority of the nine-judge pool called the window eligible",
    }
    print(
        f"  pool: {len(pool_common)} commonly coded, "
        f"{len(pool_eligible)} majority-eligible across all {len(full)} judges"
    )

    def verdict_of(member: str, cid: str, carry_ineligible: bool) -> str:
        parsed = tables[member][cid]["parsed"]
        if carry_ineligible and not parsed.get("eligible"):
            return "ineligible"
        return str(parsed.get("verdict", "")).lower() or "missing"

    for panel_name, members in PANELS.items():
        if any(coverage.get(m, 0) < args.min_coverage for m in members):
            print(f"  SKIP panel {panel_name}: incomplete coverage")
            continue
        common = set.intersection(*(set(tables[m]) for m in members)) & set(windows)
        elig = {
            cid: [str(bool(tables[m][cid]["parsed"].get("eligible"))) for m in members]
            for cid in common
        }
        maj_elig = [cid for cid, row in elig.items() if sum(v == "True" for v in row) >= 2]
        verdict_own = {
            cid: [verdict_of(m, cid, False) for m in members] for cid in maj_elig
        }
        verdict_common = {
            cid: [verdict_of(m, cid, False) for m in members] for cid in pool_eligible
        }
        verdict_all = {
            cid: [verdict_of(m, cid, True) for m in members] for cid in pool_common
        }
        elig_common = {
            cid: [str(bool(tables[m][cid]["parsed"].get("eligible"))) for m in members]
            for cid in pool_common
        }
        entry = {
            "members": members,
            "models": [JUDGE_META[m][2] for m in members],
            "developers": sorted({JUDGE_META[m][0] for m in members}),
            "tiers": sorted({JUDGE_META[m][1] for m in members}),
            "n_common": len(common),
            "n_majority_eligible": len(maj_elig),
            "n_pool_eligible": len(pool_eligible),
            "n_all_items": len(pool_common),
            "eligibility_ac1": clustered(elig_common, cluster_of, gwet_ac1),
            "eligibility_kappa": clustered(elig_common, cluster_of, fleiss_kappa),
            # headline: one fixed population for every panel
            "verdict_ac1": clustered(verdict_common, cluster_of, gwet_ac1),
            "verdict_kappa": clustered(verdict_common, cluster_of, fleiss_kappa),
            # panel's own subset, as released, kept for continuity
            "verdict_ac1_own": clustered(verdict_own, cluster_of, gwet_ac1),
            "verdict_kappa_own": clustered(verdict_own, cluster_of, fleiss_kappa),
            # nothing dropped: ineligibility carried as a category
            "verdict_ac1_allitems": clustered(verdict_all, cluster_of, gwet_ac1),
            "verdict_kappa_allitems": clustered(verdict_all, cluster_of, fleiss_kappa),
        }
        for field in ("c1", "c2", "c3", "c4", "c5"):
            lab = {
                cid: [
                    str(tables[m][cid]["parsed"].get(field, "")).lower() or "missing"
                    for m in members
                ]
                for cid in pool_eligible
            }
            entry[f"coordinate_{field}_kappa"] = clustered(lab, cluster_of, fleiss_kappa)
        results[panel_name] = entry
        v = entry["verdict_kappa"].get("point")
        a = entry["verdict_ac1"].get("point")
        vo = entry["verdict_kappa_own"].get("point")
        va = entry["verdict_kappa_allitems"].get("point")
        print(
            f"  {panel_name:26s} common n={len(pool_eligible):5d} AC1={a:.3f} "
            f"kappa={v:+.3f} | own n={len(maj_elig):5d} kappa={vo:+.3f} "
            f"| all n={len(pool_common):5d} kappa={va:+.3f}"
        )

    # pairwise verdict agreement for every judge pair with full coverage,
    # computed on the single fixed pool-level population so that no pair is
    # scored on a different item mix from any other
    pairs = {}
    for a, b in combinations(sorted(full), 2):
        elig_all = {
            cid: [
                str(bool(tables[a][cid]["parsed"].get("eligible"))),
                str(bool(tables[b][cid]["parsed"].get("eligible"))),
            ]
            for cid in pool_common
        }
        both = [cid for cid, r in elig_all.items() if r == ["True", "True"]]
        verdict_common = {
            cid: [
                str(tables[a][cid]["parsed"].get("verdict", "")).lower() or "missing",
                str(tables[b][cid]["parsed"].get("verdict", "")).lower() or "missing",
            ]
            for cid in pool_eligible
        }
        verdict_own = {
            cid: [
                str(tables[a][cid]["parsed"].get("verdict", "")).lower() or "missing",
                str(tables[b][cid]["parsed"].get("verdict", "")).lower() or "missing",
            ]
            for cid in both
        }
        if len(verdict_common) < 20:
            continue
        pairs[f"{a}|{b}"] = {
            "same_developer": JUDGE_META[a][0] == JUDGE_META[b][0],
            "same_tier": JUDGE_META[a][1] == JUDGE_META[b][1],
            "n_items": len(verdict_common),
            "n_items_own": len(verdict_own),
            "verdict_kappa": fleiss_kappa(list(verdict_common.values())),
            "verdict_ac1": gwet_ac1(list(verdict_common.values())),
            "verdict_kappa_own": fleiss_kappa(list(verdict_own.values())),
            "eligibility_kappa": fleiss_kappa(list(elig_all.values())),
        }
    results["pairwise"] = pairs

    # Does tier explain pairwise verdict agreement?  Compare mean kappa across
    # pair types.  With the submitted panel this contrast was not identified.
    groups = defaultdict(list)
    for key, val in pairs.items():
        kind = (
            "same dev, same tier"
            if val["same_developer"] and val["same_tier"]
            else "same dev, diff tier"
            if val["same_developer"]
            else "diff dev, same tier"
            if val["same_tier"]
            else "diff dev, diff tier"
        )
        groups[kind].append(val["verdict_kappa"])
    results["pair_type_means"] = {
        k: {"mean_kappa": sum(v) / len(v), "n_pairs": len(v), "values": v}
        for k, v in sorted(groups.items())
    }
    for kind, val in results["pair_type_means"].items():
        print(f"  pairs [{kind:20s}] mean verdict kappa = {val['mean_kappa']:+.3f} "
              f"(n={val['n_pairs']})")

    # Tier composition, stated precisely.  A pooled "same tier vs different
    # tier" contrast is null here for a reason that matters: "same tier" pools
    # small-small pairs, which agree at about zero, with frontier-frontier
    # pairs, which agree considerably better.  Averaging the two ends hides the
    # effect, so the composition is reported directly.
    comp = defaultdict(list)
    for key, val in pairs.items():
        a, b = key.split("|")
        ta, tb = JUDGE_META[a][1], JUDGE_META[b][1]
        tier_kind = (
            "frontier-frontier"
            if ta == tb == "frontier"
            else "small-small"
            if ta == tb == "small"
            else "mixed"
        )
        dev_kind = "same-dev" if val["same_developer"] else "cross-dev"
        comp[f"{tier_kind} / {dev_kind}"].append(val["verdict_kappa"])
    results["tier_composition"] = {
        k: {
            "mean_kappa": sum(v) / len(v),
            "min_kappa": min(v),
            "max_kappa": max(v),
            "n_pairs": len(v),
        }
        for k, v in sorted(comp.items())
    }
    for kind, val in results["tier_composition"].items():
        print(
            f"  comp [{kind:32s}] n={val['n_pairs']:2d} "
            f"mean={val['mean_kappa']:+.3f} "
            f"range=[{val['min_kappa']:+.3f},{val['max_kappa']:+.3f}]"
        )

    # ------------------------------------------------------------------
    # Which factor explains pairwise verdict agreement: sharing a developer, or
    # sharing a capability tier?
    #
    # An earlier analysis permuted the *pair* labels.  That is not a valid
    # reference distribution: nine judges generate thirty-six pairs, each judge
    # appears in eight of them, and the pairs are therefore neither independent
    # nor the unit at which anything was assigned.  The unit is the judge.  We
    # therefore enumerate randomisations of the *judges*, exhaustively, and
    # report exact p-values whose support is small and stated:
    #
    #  developer_partition_exact  all 280 ways of splitting the nine judges into
    #                             three unlabelled groups of three; statistic is
    #                             mean within-group kappa minus mean
    #                             between-group kappa.  The observed grouping is
    #                             the developer grouping.
    #  frontier_pairing_exact     all 15 perfect matchings of the six frontier
    #                             checkpoints into three disjoint pairs;
    #                             statistic is mean matched-pair kappa minus
    #                             mean unmatched-pair kappa.  The observed
    #                             matching is the developer matching.  This is
    #                             the randomisation for the abstract's
    #                             same-developer versus cross-developer
    #                             contrast, and its smallest attainable
    #                             two-sided p-value is 1/15 = 0.067.
    #  tier_label_exact           all 84 ways of labelling three of the nine
    #                             judges "small".
    #
    # A judge-level bootstrap accompanies each contrast.
    # ------------------------------------------------------------------
    kap = {
        frozenset(key.split("|")): val["verdict_kappa"] for key, val in pairs.items()
    }

    def group_contrast(groups: list[list[str]]) -> float | None:
        """mean kappa within the given groups minus mean kappa across them."""
        within, between = [], []
        member_of = {}
        for gi, grp in enumerate(groups):
            for m in grp:
                member_of[m] = gi
        for key, value in kap.items():
            a, b = tuple(key)
            if a not in member_of or b not in member_of:
                continue
            (within if member_of[a] == member_of[b] else between).append(value)
        if not within or not between:
            return None
        return sum(within) / len(within) - sum(between) / len(between)

    def partitions_into_triples(items: list[str]):
        if not items:
            yield []
            return
        first, rest = items[0], items[1:]
        for pair in combinations(rest, 2):
            remaining = [x for x in rest if x not in pair]
            for tail in partitions_into_triples(remaining):
                yield [[first, *pair], *tail]

    def perfect_matchings(items: list[str]):
        if not items:
            yield []
            return
        first, rest = items[0], items[1:]
        for other in rest:
            remaining = [x for x in rest if x != other]
            for tail in perfect_matchings(remaining):
                yield [[first, other], *tail]

    def exact_test(observed_groups, enumerator, universe) -> dict:
        obs = group_contrast(observed_groups)
        if obs is None:
            return {}
        draws = [group_contrast(g) for g in enumerator(list(universe))]
        draws = [d for d in draws if d is not None]
        hits = sum(1 for d in draws if abs(d) >= abs(obs) - 1e-12)
        return {
            "difference": obs,
            "n_randomisations": len(draws),
            "p_exact_two_sided": hits / len(draws) if draws else None,
            "smallest_attainable_p": 1.0 / len(draws) if draws else None,
            "randomisation_unit": "judge",
        }

    def judge_bootstrap(observed_groups, draws: int = 5000, seed: int = 2026073002) -> dict:
        """Resample judges with replacement; recompute the same contrast."""
        rng = random.Random(seed)
        members = [m for g in observed_groups for m in g]
        member_of = {}
        for gi, grp in enumerate(observed_groups):
            for m in grp:
                member_of[m] = gi
        out = []
        for _ in range(draws):
            picked = [rng.choice(members) for _ in members]
            within, between = [], []
            for i in range(len(picked)):
                for j in range(i + 1, len(picked)):
                    a, b = picked[i], picked[j]
                    if a == b:
                        continue
                    value = kap.get(frozenset((a, b)))
                    if value is None:
                        continue
                    (within if member_of[a] == member_of[b] else between).append(value)
            if within and between:
                out.append(sum(within) / len(within) - sum(between) / len(between))
        if not out:
            return {}
        out.sort()
        return {
            "ci95": [out[int(0.025 * len(out))], out[min(len(out) - 1, int(0.975 * len(out)))]],
            "share_above_zero": sum(1 for v in out if v > 0) / len(out),
            "draws": len(out),
            "unit": "judge",
        }

    by_dev: dict[str, list[str]] = defaultdict(list)
    for name in full:
        by_dev[JUDGE_META[name][0]].append(name)
    dev_groups = [sorted(v) for _, v in sorted(by_dev.items())]

    frontier = [n for n in full if JUDGE_META[n][1] == "frontier"]
    by_dev_frontier: dict[str, list[str]] = defaultdict(list)
    for name in frontier:
        by_dev_frontier[JUDGE_META[name][0]].append(name)
    frontier_pairs = [sorted(v) for _, v in sorted(by_dev_frontier.items()) if len(v) == 2]

    by_tier: dict[str, list[str]] = defaultdict(list)
    for name in full:
        by_tier[JUDGE_META[name][1]].append(name)
    tier_groups = [sorted(v) for _, v in sorted(by_tier.items())]

    def tier_enumerator(universe: list[str]):
        universe = sorted(universe)
        n_small = len(tier_groups[1]) if len(tier_groups) > 1 else 0
        for small in combinations(universe, n_small):
            yield [list(small), [x for x in universe if x not in small]]

    results["factor_tests"] = {
        "developer_partition_exact": exact_test(
            dev_groups, partitions_into_triples, sorted(full)
        ),
        "frontier_pairing_exact": exact_test(
            frontier_pairs, perfect_matchings, sorted(frontier)
        ),
        "tier_label_exact": exact_test(tier_groups, tier_enumerator, sorted(full)),
        "developer_bootstrap": judge_bootstrap(dev_groups),
        "frontier_pairing_bootstrap": judge_bootstrap(frontier_pairs),
    }
    for name, val in results["factor_tests"].items():
        if val:
            print(f"  {name:32s} " + json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in val.items()}))

    # Descriptive means, unchanged in definition but now on the common
    # population.  These are reported as description, never as a test.
    fs = [v["verdict_kappa"] for k, v in pairs.items()
          if all(JUDGE_META[m][1] == "frontier" for m in k.split("|"))]
    fs_same = [v["verdict_kappa"] for k, v in pairs.items()
               if all(JUDGE_META[m][1] == "frontier" for m in k.split("|"))
               and v["same_developer"]]
    fs_cross = [v["verdict_kappa"] for k, v in pairs.items()
                if all(JUDGE_META[m][1] == "frontier" for m in k.split("|"))
                and not v["same_developer"]]
    results["frontier_pair_summary"] = {
        "all": {"n": len(fs), "mean": sum(fs) / len(fs) if fs else None,
                "min": min(fs) if fs else None, "max": max(fs) if fs else None},
        "same_developer": {
            "n": len(fs_same),
            "mean": sum(fs_same) / len(fs_same) if fs_same else None,
            "values": sorted(fs_same),
        },
        "cross_developer": {
            "n": len(fs_cross),
            "mean": sum(fs_cross) / len(fs_cross) if fs_cross else None,
            "min": min(fs_cross) if fs_cross else None,
            "max": max(fs_cross) if fs_cross else None,
            "n_exceeding_worst_same_dev": sum(
                1 for v in fs_cross if fs_same and v > min(fs_same)
            ),
        },
    }
    print("  frontier pair summary " + json.dumps(results["frontier_pair_summary"]))

    # Where the disagreement lives.  Judges are not noisy about a shared
    # threshold; each holds a different one.  Reported on the common item
    # population so the spread cannot be an item-composition artifact.
    marginals = {}
    for name in full:
        counts = Counter(
            str(tables[name][cid]["parsed"].get("verdict", "")).lower()
            for cid in pool_eligible
        )
        total = sum(counts.values()) or 1
        marginals[name] = {
            "model": JUDGE_META[name][2],
            "developer": JUDGE_META[name][0],
            "tier": JUDGE_META[name][1],
            "n": total,
            **{k: v / total for k, v in counts.items()},
        }
    shares = [v.get("survives", 0.0) for v in marginals.values()]
    results["verdict_marginals"] = {
        "per_judge": marginals,
        "survives_share_min": min(shares),
        "survives_share_max": max(shares),
        "n_items": len(pool_eligible),
    }
    print(
        f"  survives share across the pool: {min(shares):.3f}--{max(shares):.3f} "
        f"on {len(pool_eligible)} common items"
    )

    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")

    write_table(results)
    return 0


def write_table(results: dict) -> None:
    def fmt(entry, key):
        e = entry.get(key) or {}
        p = e.get("point")
        return "--" if p is None else f"{p:.2f}"

    rows = []
    for name in (
        "submitted",
        "small",
        "frontier",
        "frontier_cross_dev",
        "same_dev_tier",
        "same_dev_tier_google",
        "same_dev_tier_openai",
        "cross_dev_frontier_pair_a",
        "cross_dev_frontier_pair_b",
    ):
        entry = results.get(name)
        if not entry:
            continue
        rows.append(
            " & ".join(
                [
                    PANEL_LABEL[name],
                    str(len(entry["members"])),
                    fmt(entry, "verdict_ac1"),
                    fmt(entry, "verdict_kappa"),
                    fmt(entry, "verdict_kappa_allitems"),
                    fmt(entry, "verdict_kappa_own"),
                ]
            )
            + r" \\"
        )
    if not rows:
        return
    n_common = results.get("pool", {}).get("n_pool_eligible", 0)
    n_all = results.get("pool", {}).get("n_common", 0)
    tab = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{@{}lrrrrr@{}}",
        r"\toprule",
        r"Panel & $J$ & \multicolumn{2}{c}{Common items} & All & Own \\",
        r"\cmidrule(lr){3-4}\cmidrule(lr){5-5}\cmidrule(lr){6-6}",
        r" & & $AC_1$ & $\kappa$ & $\kappa$ & $\kappa$ \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Upgrading the judges helps and does not rescue the "
        r"verdict, on a population that is identical for every row. The same "
        r"\FrameCandidates{}-window frame is coded by a fully crossed pool of "
        r"nine judges---a small and two frontier checkpoints from each of "
        r"three developers---from which these panels are drawn. Because "
        r"$\kappa$ is prevalence sensitive, comparing panels each scored on "
        r"its own majority-eligible subset would confound capability with "
        r"item composition, so \emph{Common items} fixes one population of " + f"{n_common:,} "
        r"windows that a majority of the whole nine-judge pool called "
        r"eligible, and \emph{All} drops nothing at all: it scores every one of the " + f"{n_all:,} "
        r"commonly coded windows, carrying ineligibility as its own category. "
        r"\emph{Own} is each panel's own subset, as previously released. "
        r"Conclusions are unchanged across the three: an all-frontier panel of "
        r"three developers multiplies verdict $\kappa$ several-fold over the "
        r"submitted panel and still reaches only \emph{fair}. The three "
        r"\emph{same dev.} rows are the reference level, two frontier "
        r"checkpoints from one developer where nothing differs but the "
        r"checkpoint; they bound what \emph{correlated} judges reach, not what "
        r"the task affords, and Table~\ref{tab:frontier-pairs} shows that one "
        r"cross-developer pair beats two of them.}",
        r"\label{tab:tier-control}",
        r"\end{table}",
    ]
    (TAB / "tier_control.tex").write_text("\n".join(tab) + "\n", encoding="utf-8")
    print(f"wrote {TAB / 'tier_control.tex'}")

    # Every frontier-frontier cell, so that no averaged contrast is reported
    # over pairs the reader is not shown.
    short = {
        "coderB_claudeopus46": "opus-4.6",
        "coderG_opus48": "opus-4.8",
        "coderC_gemini31pro": "gem-3.1p",
        "coderH_gemini25pro": "gem-2.5p",
        "coderI_gpt54": "gpt-5.4",
        "coderJ_gpt55": "gpt-5.5",
    }
    cells = []
    for key, val in sorted(
        results.get("pairwise", {}).items(),
        key=lambda kv: -kv[1]["verdict_kappa"],
    ):
        a, b = key.split("|")
        if a not in short or b not in short:
            continue
        cells.append(
            " & ".join(
                [
                    f"{short[a]} vs {short[b]}",
                    "same" if val["same_developer"] else "cross",
                    f"{val['verdict_kappa']:.2f}",
                    f"{val['verdict_ac1']:.2f}",
                    f"{val['eligibility_kappa']:.2f}",
                ]
            )
            + r" \\"
        )
    summary = results.get("frontier_pair_summary", {})
    ft = results.get("factor_tests", {}).get("frontier_pairing_exact", {})
    beats = summary.get("cross_developer", {}).get("n_exceeding_worst_same_dev", 0)
    tab2 = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{@{}llrrr@{}}",
        r"\toprule",
        r"Frontier pair & Dev. & $\kappa$ & $AC_1$ & Elig.\ $\kappa$ \\",
        r"\midrule",
        *cells,
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Every frontier-frontier judge pair, on the common item "
        r"population, ordered by verdict $\kappa$. The averaged "
        r"same-developer advantage is "
        + (f"{ft.get('difference', float('nan')):+.2f}" if ft else "--")
        + r"; its exact randomisation over the "
        + (str(ft.get("n_randomisations", "--")) if ft else "--")
        + r" ways of matching six checkpoints into three disjoint pairs gives "
        + (f"$p={ft.get('p_exact_two_sided', float('nan')):.2f}$" if ft else "--")
        + r", against a smallest attainable value of "
        + (f"{ft.get('smallest_attainable_p', float('nan')):.2f}" if ft else "--")
        + f". The contrast is also not uniform: {beats} cross-developer "
        r"pairs agree better than the weakest same-developer pair, so sharing "
        r"a developer is reported as residual structure and not as an effect.}",
        r"\label{tab:frontier-pairs}",
        r"\end{table}",
    ]
    (TAB / "frontier_pairs.tex").write_text("\n".join(tab2) + "\n", encoding="utf-8")
    print(f"wrote {TAB / 'frontier_pairs.tex'}")


if __name__ == "__main__":
    raise SystemExit(main())
