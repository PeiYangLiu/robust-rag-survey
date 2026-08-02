#!/usr/bin/env python3
"""Build the privileged-information reference and read the information ladder.

Two things come out of the runs produced by ``run_privileged_adjudication.py``.

**The ladder.**  The same three judges, the same codebook and the same windows,
with only the attached evidence varying: the +-45 line window the census used,
the citing paper's entire full text, and both papers' full texts.  If agreement
climbs with evidence, the census result is a property of what a window
discloses; if it does not, it is a property of the judges or of the task.  This
is the contrast the submitted version could not draw, and it is what separates
the three explanations a reviewer said the paper conflates.

**The reference.**  Three stronger checkpoints adjudicate the same windows at
the highest evidence tier available for each, and must support each answer with
a quote that is mechanically located in the document they were shown -- at the
both-texts tier, one quote in each paper.  A reference label is established when
a majority of quote-verified privileged adjudicators agree; items without one
are reported, not silently dropped.  The deployed panel is then scored against
it.  Because the Google cell of the privileged panel reuses the deployed
checkpoint, every reference statistic is recomputed leaving that judge out.

This reference is not human gold and nothing here should be read as one.  It is
an *evidence-privileged* reference: it is better informed than the instrument it
scores, by construction and by a documented margin, and it is fully auditable.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"

DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
REFERENCE = [
    "refA_claudeopus5",
    "refC_gemini31pro",
    "refD_claudeopus48",
    "refE_gpt55cli",
]
# The Google cell reuses the deployed checkpoint because it is that
# developer's strongest available; every reference statistic is recomputed
# with it removed.
SHARED_WITH_DEPLOYED = "refC_gemini31pro"
TIERS = ["window", "citing_full", "both_full"]
VERDICTS = {"survives", "narrows", "undefined"}
PROV = {"transported", "reimplemented", "unclear"}


# ------------------------------------------------------------------ stats
def fleiss_kappa(rows: list[list[str]]) -> float:
    rows = [r for r in rows if len(r) >= 2]
    if not rows:
        return float("nan")
    cats = sorted({v for r in rows for v in r})
    if len(cats) < 2:
        return float("nan")
    n = len(rows[0])
    if any(len(r) != n for r in rows):
        return float("nan")
    counts = [[r.count(c) for c in cats] for r in rows]
    p_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in counts]
    p_bar = sum(p_i) / len(p_i)
    p_j = [sum(row[j] for row in counts) / (len(rows) * n) for j in range(len(cats))]
    p_e = sum(p * p for p in p_j)
    return (p_bar - p_e) / (1 - p_e) if abs(1 - p_e) > 1e-12 else float("nan")


def observed(rows: list[list[str]]) -> float:
    if not rows:
        return float("nan")
    tot = 0.0
    for r in rows:
        n = len(r)
        pairs = n * (n - 1) / 2
        same = sum(v * (v - 1) / 2 for v in Counter(r).values())
        tot += same / pairs if pairs else 0.0
    return tot / len(rows)


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    z, p = 1.959963985, k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - h) / d, (c + h) / d


def cluster_ci(
    items: list[tuple[str, object]], stat, draws: int = 3000, seed: int = 20260731
) -> tuple[float, float]:
    groups: dict[str, list] = defaultdict(list)
    for key, payload in items:
        groups[key].append(payload)
    keys = sorted(groups)
    if len(keys) < 2:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        drawn = [x for k in pick for x in groups[k]]
        v = stat(drawn)
        if v == v:
            vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


# ------------------------------------------------------------ quote checking
LIG = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
DASH = dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-")
QUOTE = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "}
_TEXT: dict[str, str] = {}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for a, b in {**LIG, **DASH, **QUOTE}.items():
        text = text.replace(a, b)
    text = re.sub(r"-\s*\n\s*", "", text)
    return " ".join(text.split()).lower()


def doc(cite_key: str) -> str:
    if cite_key not in _TEXT:
        path = TEXT_DIR / f"{cite_key}.txt"
        _TEXT[cite_key] = norm(
            path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        )
    return _TEXT[cite_key]


def quote_ok(quote: str, cite_key: str, min_len: int = 24) -> bool:
    probe = norm(str(quote or ""))[:80]
    if len(probe) < min_len:
        return False
    hay = doc(cite_key)
    if probe in hay:
        return True
    frags = [f for f in re.split(r"\s*(?:\.\.\.|\u2026)\s*", probe) if len(f) >= 16]
    if len(frags) >= 2 and all(f in hay for f in frags):
        return True
    toks = probe.split()
    if not toks:
        return False
    hc = Counter(hay.split())
    covered = sum(min(n, hc.get(t, 0)) for t, n in Counter(toks).items())
    return covered / len(toks) >= 0.95


# ------------------------------------------------------------------- loading
def load_runs(directory: Path) -> dict[tuple[str, str, str], dict[str, dict]]:
    """(pass, tier, judge) -> candidate_id -> parsed record."""
    out: dict[tuple[str, str, str], dict[str, dict]] = defaultdict(dict)
    for path in sorted(directory.glob("*.jsonl")):
        parts = path.stem.split("__")
        if len(parts) != 3:
            continue
        key = (parts[0], parts[1], parts[2])
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed"):
                out[key][row["candidate_id"]] = row
    return out


def load_deployed(coding_dir: Path, prov_dir: Path) -> tuple[dict, dict]:
    comp: dict[str, dict[str, dict]] = {}
    for name in DEPLOYED:
        table = {}
        for line in (coding_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row["parsed"]
        comp[name] = table
    prov: dict[str, dict[str, dict]] = {}
    for path in sorted(prov_dir.glob("*.jsonl")):
        table = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    table[row["candidate_id"]] = row["parsed"]
        prov[path.stem] = table
    return comp, prov


def majority(values: list[str]) -> str | None:
    if not values:
        return None
    top, n = Counter(values).most_common(1)[0]
    return top if n > len(values) / 2 else None


def norm_verdict(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in VERDICTS else "undefined"


def norm_prov(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in PROV else "unclear"


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, default=SUPPLEMENT / "privileged_reference_runs")
    ap.add_argument("--sample", type=Path, default=SUPPLEMENT / "privileged_reference_sample.jsonl")
    ap.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    ap.add_argument("--prov-dir", type=Path, default=SUPPLEMENT / "cross_paper_provenance")
    ap.add_argument("--out", type=Path, default=SUPPLEMENT / "privileged_reference_results.json")
    ap.add_argument("--ledger", type=Path, default=SUPPLEMENT / "privileged_reference_ledger.csv")
    args = ap.parse_args()

    sample = {}
    for line in args.sample.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            sample[row["candidate_id"]] = row

    runs = load_runs(args.runs)
    dep_comp, dep_prov = load_deployed(args.coding_dir, args.prov_dir)
    dep_prov_names = sorted(dep_prov)

    paper_of = {cid: r["cite_key"] for cid, r in sample.items()}

    # ------------------------------------------------------------------
    # A. the information ladder, deployed judges only
    # ------------------------------------------------------------------
    def tier_labels(pass_name: str, tier: str, judges: list[str], field: str, caster):
        """candidate -> list of labels, for items every judge answered."""
        if tier == "window":
            tables = (
                {j: dep_comp[j] for j in judges}
                if pass_name == "comparability"
                else {j: dep_prov[n] for j, n in zip(judges, dep_prov_names)}
            )
            get = lambda t, cid: t.get(cid)  # noqa: E731
        else:
            tables = {j: runs.get((pass_name, tier, j), {}) for j in judges}
            get = lambda t, cid: (t.get(cid) or {}).get("parsed")  # noqa: E731
        out = {}
        for cid in sample:
            vals = []
            for j in judges:
                parsed = get(tables[j], cid)
                if not parsed:
                    vals = []
                    break
                vals.append(caster(parsed.get(field)))
            if vals:
                out[cid] = vals
        return out

    ladder = {}
    for pass_name, field, caster, label_set in (
        ("comparability", "verdict", norm_verdict, VERDICTS),
        ("provenance", "provenance", norm_prov, PROV),
    ):
        per_tier = {
            tier: tier_labels(pass_name, tier, DEPLOYED, field, caster) for tier in TIERS
        }
        common_all = set.intersection(*(set(v) for v in per_tier.values())) if per_tier else set()
        block = {}
        for tier in TIERS:
            ids = sorted(per_tier[tier])
            rows = [per_tier[tier][c] for c in ids]
            ci = cluster_ci(
                [(paper_of[c], per_tier[tier][c]) for c in ids], fleiss_kappa
            )
            ids_c = sorted(common_all)
            rows_c = [per_tier[tier][c] for c in ids_c]
            block[tier] = {
                "n_items": len(ids),
                "n_papers": len({paper_of[c] for c in ids}),
                "fleiss_kappa": fleiss_kappa(rows),
                "fleiss_kappa_ci95": list(ci),
                "observed": observed(rows),
                "label_distribution": dict(Counter(v for r in rows for v in r)),
                "n_common_items": len(ids_c),
                "fleiss_kappa_on_common": fleiss_kappa(rows_c),
                "observed_on_common": observed(rows_c),
            }
        # paired difference on the common item set, resampling papers
        ids_c = sorted(common_all)
        if ids_c:
            paired = [
                (
                    paper_of[c],
                    (per_tier["window"][c], per_tier["citing_full"][c], per_tier["both_full"][c]),
                )
                for c in ids_c
            ]

            def d_citing(rows):
                return fleiss_kappa([r[1] for r in rows]) - fleiss_kappa([r[0] for r in rows])

            def d_both(rows):
                return fleiss_kappa([r[2] for r in rows]) - fleiss_kappa([r[0] for r in rows])

            block["delta_citing_minus_window"] = {
                "point": d_citing([p for _, p in paired]),
                "ci95": list(cluster_ci(paired, d_citing)),
            }
            block["delta_both_minus_window"] = {
                "point": d_both([p for _, p in paired]),
                "ci95": list(cluster_ci(paired, d_both)),
            }
        ladder[pass_name] = block

    # ------------------------------------------------------------------
    # B. the reference
    # ------------------------------------------------------------------
    def best_tier(cid: str, pass_name: str, judge: str) -> str | None:
        for tier in ("both_full", "citing_full"):
            if cid in runs.get((pass_name, tier, judge), {}):
                return tier
        return None

    reference: dict[str, dict] = {}
    ref_audit = []
    for cid, row in sample.items():
        entry = {"candidate_id": cid, "cite_key": row["cite_key"]}
        for pass_name, field, caster in (
            ("comparability", "verdict", norm_verdict),
            ("provenance", "provenance", norm_prov),
        ):
            votes, verified_votes, tiers_used = [], [], []
            for judge in REFERENCE:
                tier = best_tier(cid, pass_name, judge)
                if tier is None:
                    continue
                rec = runs[(pass_name, tier, judge)][cid]
                parsed = rec["parsed"]
                label = caster(parsed.get(field))
                ok = quote_ok(parsed.get("evidence_quote", ""), row["cite_key"])
                if tier == "both_full" and row["cited_papers"]:
                    cited_keys = [c["cite_key"] for c in row["cited_papers"][:2]]
                    ok_cited = any(
                        quote_ok(parsed.get("evidence_quote_cited", ""), k) for k in cited_keys
                    )
                    ok = ok and ok_cited
                votes.append((judge, tier, label, ok))
                tiers_used.append(tier)
                if ok:
                    verified_votes.append(label)
            entry[f"{pass_name}_votes"] = votes
            entry[f"{pass_name}_tier"] = (
                "both_full" if "both_full" in tiers_used else ("citing_full" if tiers_used else None)
            )
            entry[f"{pass_name}_reference"] = majority(verified_votes) if len(verified_votes) >= 2 else None
            entry[f"{pass_name}_n_verified"] = len(verified_votes)
            entry[f"{pass_name}_n_votes"] = len(votes)
            # leave-the-shared-checkpoint-out reference
            loo = [
                lab
                for j, t, lab, ok in votes
                if ok and j != SHARED_WITH_DEPLOYED
            ]
            entry[f"{pass_name}_reference_loo"] = majority(loo) if len(loo) >= 2 else None
        reference[cid] = entry
        ref_audit.append(entry)

    # ------------------------------------------------------------------
    # C. deployed panel scored against the reference
    # ------------------------------------------------------------------
    def deployed_majority(cid: str, pass_name: str) -> str | None:
        if pass_name == "comparability":
            vals = [norm_verdict(dep_comp[j].get(cid, {}).get("verdict")) for j in DEPLOYED
                    if cid in dep_comp[j]]
        else:
            vals = [norm_prov(dep_prov[n].get(cid, {}).get("provenance")) for n in dep_prov_names
                    if cid in dep_prov[n]]
        return majority(vals) if len(vals) >= 2 else None

    scored = {}
    for pass_name, key in (("comparability", "verdict"), ("provenance", "provenance")):
        for ref_field, tag in ((f"{pass_name}_reference", "all"), (f"{pass_name}_reference_loo", "loo")):
            pairs = []
            for cid, entry in reference.items():
                ref = entry.get(ref_field)
                got = deployed_majority(cid, pass_name)
                if ref is None or got is None:
                    continue
                pairs.append((paper_of[cid], (ref, got)))
            n = len(pairs)
            correct = sum(1 for _, (r, g) in pairs if r == g)
            lo, hi = wilson(correct, n)
            clo, chi = cluster_ci(pairs, lambda rows: sum(1 for r, g in rows if r == g) / len(rows))
            conf: dict[str, Counter] = defaultdict(Counter)
            for _, (r, g) in pairs:
                conf[r][g] += 1
            majority_class = Counter(r for _, (r, _) in pairs).most_common(1)
            scored[f"{pass_name}__{tag}"] = {
                "n_reference_items": n,
                "n_papers": len({p for p, _ in pairs}),
                "accuracy": correct / n if n else float("nan"),
                "wilson_ci95": [lo, hi],
                "cluster_ci95": [clo, chi],
                "majority_class_baseline": (majority_class[0][1] / n) if n and majority_class else float("nan"),
                "confusion_reference_by_deployed": {r: dict(c) for r, c in conf.items()},
                "reference_distribution": dict(Counter(r for _, (r, _) in pairs)),
                "deployed_distribution": dict(Counter(g for _, (_, g) in pairs)),
            }

    # per-class recall for provenance, which is what a composition claim needs
    prov_pairs = []
    for cid, entry in reference.items():
        ref, got = entry.get("provenance_reference"), deployed_majority(cid, "provenance")
        if ref and got:
            prov_pairs.append((ref, got))
    per_class = {}
    for cls in sorted(PROV):
        sel = [(r, g) for r, g in prov_pairs if r == cls]
        k = sum(1 for r, g in sel if g == cls)
        per_class[cls] = {
            "n": len(sel),
            "recall": k / len(sel) if sel else float("nan"),
            "wilson_ci95": list(wilson(k, len(sel))),
        }

    # bias-corrected composition using the *measured* confusion, not an identity
    conf = scored.get("provenance__all", {}).get("confusion_reference_by_deployed", {})
    tt = conf.get("transported", {}).get("transported", 0)
    tr = conf.get("transported", {}).get("reimplemented", 0)
    rr = conf.get("reimplemented", {}).get("reimplemented", 0)
    rt = conf.get("reimplemented", {}).get("transported", 0)
    sens_t = tt / (tt + tr) if (tt + tr) else float("nan")
    spec_t = rr / (rr + rt) if (rr + rt) else float("nan")
    census = json.loads((SUPPLEMENT / "cross_paper_census.json").read_text(encoding="utf-8"))
    counts = census["provenance"]["counts"]
    n_t, n_r = counts["transported"], counts["reimplemented"]
    observed_share_t = n_t / (n_t + n_r)
    denom = sens_t + spec_t - 1
    corrected_t = (
        (observed_share_t + spec_t - 1) / denom if denom == denom and abs(denom) > 1e-9 else float("nan")
    )

    payload = {
        "schema_version": 1,
        "design_note": (
            "The reference is evidence-privileged, not human. Its adjudicators "
            "read the full text of both papers where the census read 45 lines, "
            "and every vote counted toward it is supported by a quote located "
            "mechanically in the document that adjudicator was shown. It is not "
            "a gold standard and no claim here should be read as one."
        ),
        "deployed_judges": DEPLOYED,
        "reference_judges": REFERENCE,
        "shared_checkpoint_note": (
            f"{SHARED_WITH_DEPLOYED} is the same checkpoint as the deployed "
            f"Google judge, because it is that developer's strongest available. "
            f"Every reference statistic is therefore recomputed with it removed "
            f"(the '__loo' entries)."
        ),
        "sample": {
            "n_windows": len(sample),
            "n_papers": len({r["cite_key"] for r in sample.values()}),
            "n_with_cited_text": sum(1 for r in sample.values() if r["cited_papers"]),
        },
        "information_ladder": ladder,
        "reference_coverage": {
            f"{p}": {
                "n_established": sum(1 for e in reference.values() if e.get(f"{p}_reference")),
                "n_established_loo": sum(1 for e in reference.values() if e.get(f"{p}_reference_loo")),
                "n_no_majority": sum(
                    1
                    for e in reference.values()
                    if e.get(f"{p}_n_votes", 0) >= 2 and not e.get(f"{p}_reference")
                ),
                "tier_distribution": dict(
                    Counter(e.get(f"{p}_tier") or "none" for e in reference.values())
                ),
                "reference_distribution": dict(
                    Counter(
                        e.get(f"{p}_reference")
                        for e in reference.values()
                        if e.get(f"{p}_reference")
                    )
                ),
            }
            for p in ("comparability", "provenance")
        },
        "deployed_vs_reference": scored,
        "provenance_per_class_recall": per_class,
        "composition_bias_correction": {
            "sensitivity_transported": sens_t,
            "specificity_transported": spec_t,
            "observed_frame_share_transported": observed_share_t,
            "corrected_frame_share_transported": corrected_t,
            "corrected_frame_share_reimplemented": (
                1 - corrected_t if corrected_t == corrected_t else float("nan")
            ),
            "note": (
                "The submitted version corrected the composition with a "
                "confusion matrix estimated on a constructed benchmark where "
                "every judge was perfect, so the matrix was the identity and "
                "the correction returned its input. This correction uses the "
                "confusion measured on real windows against the privileged "
                "reference, which is not the identity."
            ),
        },
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with args.ledger.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "candidate_id", "cite_key", "reference_tier_provenance",
                "reference_provenance", "deployed_provenance",
                "reference_tier_verdict", "reference_verdict", "deployed_verdict",
                "n_verified_votes_provenance", "n_verified_votes_verdict",
            ]
        )
        for cid, e in sorted(reference.items()):
            w.writerow(
                [
                    cid, e["cite_key"], e.get("provenance_tier"),
                    e.get("provenance_reference"), deployed_majority(cid, "provenance"),
                    e.get("comparability_tier"), e.get("comparability_reference"),
                    deployed_majority(cid, "comparability"),
                    e.get("provenance_n_verified"), e.get("comparability_n_verified"),
                ]
            )

    print(json.dumps({
        "ladder_verdict_kappa": {
            t: round(ladder["comparability"][t]["fleiss_kappa"], 3) for t in TIERS
        },
        "ladder_verdict_kappa_common": {
            t: round(ladder["comparability"][t]["fleiss_kappa_on_common"], 3) for t in TIERS
        },
        "ladder_provenance_kappa": {
            t: round(ladder["provenance"][t]["fleiss_kappa"], 3) for t in TIERS
        },
        "reference_coverage": payload["reference_coverage"],
        "deployed_vs_reference": {
            k: {"n": v["n_reference_items"], "acc": round(v["accuracy"], 3),
                "base": round(v["majority_class_baseline"], 3)}
            for k, v in scored.items()
        },
        "provenance_per_class_recall": {
            k: {"n": v["n"], "recall": round(v["recall"], 3) if v["recall"] == v["recall"] else None}
            for k, v in per_class.items()
        },
        "corrected_share_reimplemented": payload["composition_bias_correction"][
            "corrected_frame_share_reimplemented"
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
