#!/usr/bin/env python3
"""Census-side diagnostics the submitted version did not run.

Three analyses, all over data already released, each answering a reviewer
objection that the manuscript could not answer as written.

**Composed rule (was the rule executed?).**  Section 3 states a decision rule
over C1, C2, C4 and C5.  The census reports the verdict the judges *stated*; it
never checks whether that verdict is the one the rule returns on the judges'
own coordinate labels.  We compute both, at the majority level and -- which is
the analysis that identifies anything -- at the judge level, where no
aggregation artefact can enter.  If judges agree better on the *composed*
verdict than on the stated one, part of the census failure is rule execution
rather than coordinate reading, and the manuscript's causal claim needs
qualifying.

**Quote forensics (what are the unlocatable quotes?).**  13% of judge evidence
quotes are not found in the passage the judge was shown.  A paper whose thesis
is that unverified numbers must not be trusted should say what those are, so we
classify every one of them: recoverable after Unicode and de-hyphenation
normalisation, present elsewhere in the same paper (cross-window bleed), a near
paraphrase of some span, or absent from the source document entirely.

**Label space (is the kappa contrast like for like?).**  The constructed
benchmark is a balanced three-class problem; the census is degenerate, with
``narrows`` reachable on 1 of 704 windows.  We rescore the census on every
label space the constructed benchmark can be restricted to, so the two numbers
being contrasted are computed over comparable label sets.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"

DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
COORDS_IN_RULE = ["c1", "c2", "c4", "c5"]
VERDICTS = ["survives", "narrows", "undefined"]


# --------------------------------------------------------------------------
# agreement statistics (self-contained so this script can be run alone)
# --------------------------------------------------------------------------
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


def observed_agreement(rows: list[list[str]]) -> float:
    if not rows:
        return float("nan")
    tot = 0.0
    for r in rows:
        n = len(r)
        pairs = n * (n - 1) / 2
        same = sum(v * (v - 1) / 2 for v in Counter(r).values())
        tot += same / pairs if pairs else 0.0
    return tot / len(rows)


def cluster_bootstrap(
    items: list[tuple[str, list[str]]], stat, draws: int = 2000, seed: int = 20260731
) -> tuple[float, float]:
    """Resample source papers, not items: papers are the sampling unit."""
    import random

    by_paper: dict[str, list[list[str]]] = defaultdict(list)
    for paper, labels in items:
        by_paper[paper].append(labels)
    papers = sorted(by_paper)
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        pick = [papers[rng.randrange(len(papers))] for _ in papers]
        rows = [row for p in pick for row in by_paper[p]]
        v = stat(rows)
        if v == v:
            vals.append(v)
    if not vals:
        return float("nan"), float("nan")
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


# --------------------------------------------------------------------------
def load_judges(coding_dir: Path, names: list[str]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for name in names:
        path = coding_dir / f"{name}.jsonl"
        table: dict[str, dict] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed"):
                table[row["candidate_id"]] = row
        out[name] = table
    return out


def compose(labels: dict[str, str], matched_number: str) -> str:
    """The rule of Section 3, applied mechanically to one judge's coordinates."""
    vals = [labels.get(c, "not_determinable") for c in COORDS_IN_RULE]
    if all(v == "match" for v in vals):
        return "survives"
    recoverable = bool(matched_number) and "not_recoverable" not in matched_number.lower()
    return "narrows" if recoverable else "undefined"


def majority(values: list[str]) -> str | None:
    counts = Counter(values)
    top, n = counts.most_common(1)[0]
    return top if n > len(values) / 2 else None


# --------------------------------------------------------------------------
# quote forensics helpers
# --------------------------------------------------------------------------
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
DASHES = dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-")
QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "}


def squeeze(text: str) -> str:
    return " ".join(text.split())


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for src, dst in {**LIGATURES, **DASHES, **QUOTES}.items():
        text = text.replace(src, dst)
    text = re.sub(r"-\s*\n\s*", "", text)  # join words hyphenated across lines
    return squeeze(text).lower()


def best_ratio(needle: str, haystack: str, window_slack: int = 60) -> float:
    """Best SequenceMatcher ratio of ``needle`` against any same-length span."""
    if not needle or not haystack:
        return 0.0
    n = len(needle)
    step = max(1, n // 4)
    best = 0.0
    for start in range(0, max(1, len(haystack) - n + 1), step):
        span = haystack[start : start + n + window_slack]
        r = SequenceMatcher(None, needle, span).quick_ratio()
        if r > best - 0.05:
            r = SequenceMatcher(None, needle, span).ratio()
            best = max(best, r)
        if best > 0.98:
            break
    return best


def classify_quote(quote: str, shown: str, full_paper: str) -> str:
    """Classify one evidence quote against the passage the judge was shown.

    The classes are ordered from benign to serious.  The distinction that
    matters is between a quote that *re-serialises* text the judge was shown
    (an extracted table flattened into a sentence, or a span abridged with an
    ellipsis) and one whose content is not in the source document at all.  The
    submitted version reported a single located/not-located rate, which pools
    the two.
    """
    probe_raw = squeeze(quote)[:80]
    if probe_raw and probe_raw in squeeze(shown):
        return "verbatim_in_shown"

    n_quote, n_shown, n_paper = normalise(quote), normalise(shown), normalise(full_paper)
    probe = n_quote[:80]
    if not probe:
        return "empty"
    if probe in n_shown:
        return "recovered_by_normalisation"

    # An abridgement: the judge marked an omission with an ellipsis and every
    # retained fragment is present verbatim in what it was shown.
    fragments = [f.strip() for f in re.split(r"\s*(?:\.\.\.|\u2026)\s*", n_quote)]
    fragments = [f for f in fragments if len(f) >= 12]
    if len(fragments) >= 2 and all(f[:60] in n_shown for f in fragments):
        return "elision_of_shown"

    # A re-serialisation: every token of the quote occurs in the shown passage,
    # but not in that order or not contiguously.  This is what happens when a
    # judge reads a column-major extracted table and writes it out row-major.
    q_tokens = n_quote.split()
    if q_tokens:
        shown_counts = Counter(n_shown.split())
        covered = 0
        for tok, need in Counter(q_tokens).items():
            covered += min(need, shown_counts.get(tok, 0))
        if covered / len(q_tokens) >= 0.95:
            return "reserialised_from_shown"

    if probe in n_paper:
        return "elsewhere_in_same_paper"
    if best_ratio(probe, n_shown) >= 0.90:
        return "near_paraphrase_of_shown"

    if q_tokens:
        paper_counts = Counter(n_paper.split())
        covered_doc = 0
        for tok, need in Counter(q_tokens).items():
            covered_doc += min(need, paper_counts.get(tok, 0))
        if covered_doc / len(q_tokens) >= 0.95:
            return "reserialised_from_elsewhere"

    if best_ratio(probe, n_paper) >= 0.90:
        return "near_paraphrase_elsewhere"
    return "absent_from_source_document"


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    parser.add_argument(
        "--dev-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding_dev"
    )
    parser.add_argument(
        "--frame", type=Path, default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl"
    )
    parser.add_argument(
        "--out", type=Path, default=SUPPLEMENT / "census_diagnostics.json"
    )
    parser.add_argument("--context-lines", type=int, default=45)
    parser.add_argument("--quote-forensics", action="store_true", default=True)
    args = parser.parse_args()

    windows = {}
    for line in args.frame.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            windows[row["candidate_id"]] = row

    judges = load_judges(args.coding_dir, DEPLOYED)
    common = set.intersection(*(set(t) for t in judges.values())) & set(windows)

    # Reproduce the manuscript's held-out definition exactly.
    dev_sets = []
    for path in sorted(args.dev_dir.glob("*.jsonl")):
        ids = {
            json.loads(l)["candidate_id"]
            for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("parsed")
        }
        if ids:
            dev_sets.append(ids)
    development = set.intersection(*dev_sets) if dev_sets else set()
    heldout = sorted(common - development)
    dev_in_coded = len(development & common)

    eligible = []
    for cid in heldout:
        flags = [str(bool(judges[j][cid]["parsed"].get("eligible"))) for j in DEPLOYED]
        if majority(flags) == "True":
            eligible.append(cid)

    # ------------------------------------------------------------------
    # 1. composed rule
    # ------------------------------------------------------------------
    stated_rows, composed_rows, paper_of = [], [], {}
    per_judge_fidelity = {j: {"n": 0, "agree": 0, "survives_contradicted": 0} for j in DEPLOYED}
    maj_stated, maj_composed = {}, {}
    contradiction_examples = []
    for cid in eligible:
        paper_of[cid] = windows[cid]["cite_key"]
        stated, comp = [], []
        for j in DEPLOYED:
            p = judges[j][cid]["parsed"]
            s = str(p.get("verdict", "")).strip().lower()
            c = compose(
                {k: str(p.get(k, "not_determinable")).strip().lower() for k in COORDS_IN_RULE},
                str(p.get("matched_number", "")),
            )
            if s not in VERDICTS:
                s = "undefined"
            stated.append(s)
            comp.append(c)
            per_judge_fidelity[j]["n"] += 1
            per_judge_fidelity[j]["agree"] += int(s == c)
            if s == "survives" and c != "survives":
                per_judge_fidelity[j]["survives_contradicted"] += 1
        stated_rows.append((paper_of[cid], stated))
        composed_rows.append((paper_of[cid], comp))
        maj_stated[cid] = majority(stated)
        maj_composed[cid] = majority(comp)

    both = [c for c in eligible if maj_stated[c] and maj_composed[c]]
    agree_maj = sum(1 for c in both if maj_stated[c] == maj_composed[c])
    surv = [c for c in both if maj_stated[c] == "survives"]
    surv_contra = [c for c in surv if maj_composed[c] != "survives"]
    for cid in surv_contra[:8]:
        row = windows[cid]
        contradiction_examples.append(
            {
                "candidate_id": cid,
                "cite_key": row["cite_key"],
                "majority_coordinates": {
                    k: majority([str(judges[j][cid]["parsed"].get(k, "")).lower() for j in DEPLOYED])
                    for k in COORDS_IN_RULE
                },
            }
        )

    stated_only = [r for _, r in stated_rows]
    composed_only = [r for _, r in composed_rows]
    k_stated, k_composed = fleiss_kappa(stated_only), fleiss_kappa(composed_only)
    ci_stated = cluster_bootstrap(stated_rows, fleiss_kappa)
    ci_composed = cluster_bootstrap(composed_rows, fleiss_kappa)
    paired = [
        (p, s + c) for (p, s), (_, c) in zip(stated_rows, composed_rows)
    ]

    def diff_stat(rows: list[list[str]]) -> float:
        half = len(rows[0]) // 2 if rows else 0
        return fleiss_kappa([r[half:] for r in rows]) - fleiss_kappa([r[:half] for r in rows])

    ci_diff = cluster_bootstrap(paired, diff_stat)

    composed_block = {
        "n_eligible": len(eligible),
        "n_with_both_majorities": len(both),
        "majority_stated_equals_composed": agree_maj,
        "majority_agreement_rate": agree_maj / len(both) if both else float("nan"),
        "n_majority_survives": len(surv),
        "n_majority_survives_contradicted_by_own_coordinates": len(surv_contra),
        "share_of_survives_contradicted": len(surv_contra) / len(surv) if surv else float("nan"),
        "per_judge_rule_fidelity": {
            j: {
                **v,
                "rate": v["agree"] / v["n"] if v["n"] else float("nan"),
            }
            for j, v in per_judge_fidelity.items()
        },
        "pooled_judge_level_rule_fidelity": (
            sum(v["agree"] for v in per_judge_fidelity.values())
            / max(1, sum(v["n"] for v in per_judge_fidelity.values()))
        ),
        "fleiss_kappa_stated_verdict": k_stated,
        "fleiss_kappa_stated_verdict_ci95": list(ci_stated),
        "fleiss_kappa_composed_verdict": k_composed,
        "fleiss_kappa_composed_verdict_ci95": list(ci_composed),
        "kappa_composed_minus_stated": k_composed - k_stated,
        "kappa_composed_minus_stated_ci95": list(ci_diff),
        "observed_stated": observed_agreement(stated_only),
        "observed_composed": observed_agreement(composed_only),
        "majority_composed_distribution": dict(
            Counter(maj_composed[c] or "no_majority" for c in eligible)
        ),
        "majority_stated_distribution": dict(
            Counter(maj_stated[c] or "no_majority" for c in eligible)
        ),
        "contradiction_examples": contradiction_examples,
        "interpretation_note": (
            "If composed kappa exceeds stated kappa, judges agree more on the "
            "coordinates than on the verdict they report, and part of the "
            "census failure is rule execution rather than coordinate reading."
        ),
    }

    # ------------------------------------------------------------------
    # 2. quote forensics
    # ------------------------------------------------------------------
    text_cache: dict[str, list[str]] = {}

    def shown_text(cid: str) -> tuple[str, str]:
        w = windows[cid]
        name = w["source_file"]
        if name not in text_cache:
            path = TEXT_DIR / name
            text_cache[name] = (
                path.read_text(encoding="utf-8", errors="replace").splitlines()
                if path.exists()
                else []
            )
        lines = text_cache[name]
        if not lines:
            return w["window_text"], w["window_text"]
        lo = max(0, w["line_start"] - 1 - args.context_lines)
        hi = min(len(lines), w["line_end"] + args.context_lines)
        return "\n".join(lines[lo:hi]), "\n".join(lines)

    forensics = Counter()
    per_judge_forensics: dict[str, Counter] = {j: Counter() for j in DEPLOYED}
    unlocated_samples = []
    for cid in eligible:
        shown, whole = shown_text(cid)
        for j in DEPLOYED:
            quote = str(judges[j][cid]["parsed"].get("evidence_quote", "")).strip()
            if not quote:
                forensics["empty"] += 1
                per_judge_forensics[j]["empty"] += 1
                continue
            label = classify_quote(quote, shown, whole)
            forensics[label] += 1
            per_judge_forensics[j][label] += 1
            if label in ("absent_from_source_document", "near_paraphrase_elsewhere") and len(
                unlocated_samples
            ) < 12:
                unlocated_samples.append(
                    {
                        "candidate_id": cid,
                        "judge": j,
                        "class": label,
                        "quote_prefix": squeeze(quote)[:160],
                    }
                )

    total_q = sum(forensics.values())
    benign = (
        forensics["verbatim_in_shown"]
        + forensics["recovered_by_normalisation"]
        + forensics["elision_of_shown"]
        + forensics["reserialised_from_shown"]
    )
    quote_block = {
        "n_codings_checked": total_q,
        "classes": dict(forensics),
        "shares": {k: v / total_q for k, v in forensics.items()},
        "per_judge": {j: dict(c) for j, c in per_judge_forensics.items()},
        "n_nonempty": total_q - forensics["empty"],
        "share_supported_by_shown_passage": benign / max(1, total_q - forensics["empty"]),
        "share_absent_from_source_document": forensics["absent_from_source_document"]
        / max(1, total_q - forensics["empty"]),
        "share_empty": forensics["empty"] / total_q,
        "examples": unlocated_samples,
        "note": (
            "'recovered_by_normalisation' is verbatim after Unicode, ligature "
            "and de-hyphenation normalisation, so it is a PDF-extraction "
            "artefact rather than judge behaviour. 'elision_of_shown' marks an "
            "omission with an ellipsis and every retained fragment is verbatim. "
            "'reserialised_from_shown' uses only tokens present in the passage "
            "but reorders them, which is what reading an extracted table "
            "produces. 'elsewhere_in_same_paper' is cross-window bleed. Only "
            "'absent_from_source_document' is consistent with fabrication."
        ),
    }

    # ------------------------------------------------------------------
    # 3. label space
    # ------------------------------------------------------------------
    def binarise(v: str) -> str:
        return "survives" if v == "survives" else "not_survives"

    stated_binary = [(p, [binarise(x) for x in r]) for p, r in stated_rows]
    drop_narrows_rows = []
    for (p, r) in stated_rows:
        if "narrows" not in r:
            drop_narrows_rows.append((p, r))
    label_block = {
        "census_stated_verdict_label_counts": dict(
            Counter(v for _, r in stated_rows for v in r)
        ),
        "n_items_any_judge_said_narrows": sum(1 for _, r in stated_rows if "narrows" in r),
        "kappa_three_class": k_stated,
        "kappa_binary_survives_vs_not": fleiss_kappa([r for _, r in stated_binary]),
        "kappa_binary_ci95": list(cluster_bootstrap(stated_binary, fleiss_kappa)),
        "kappa_three_class_dropping_items_with_any_narrows": fleiss_kappa(
            [r for _, r in drop_narrows_rows]
        ),
        "n_after_dropping_narrows_items": len(drop_narrows_rows),
        "note": (
            "The constructed benchmark is a balanced three-class problem. The "
            "census is not: narrows requires a matched operating point inside "
            "one window and is essentially unreachable there. Binarising the "
            "census removes the class-count difference between the two "
            "settings; the residual gap is what the disclosure regime has to "
            "explain."
        ),
    }

    payload = {
        "schema_version": 1,
        "judges": DEPLOYED,
        "frame": {
            "n_coded_by_all_judges": len(common),
            "n_development_pass": len(development),
            "n_development_pass_also_coded": dev_in_coded,
            "n_heldout": len(heldout),
            "n_eligible_majority": len(eligible),
            "accounting_note": (
                f"The development pass declared {len(development)} candidates. "
                f"{dev_in_coded} of them are also among the {len(common)} "
                f"candidates all three judges returned a parseable coding for, "
                f"so the held-out set is {len(common)} - {dev_in_coded} = "
                f"{len(heldout)}. The remaining "
                f"{len(development) - dev_in_coded} development candidates were "
                f"not coded by all three judges in the deployed pass, so they "
                f"never entered the coded set to be removed from it. The "
                f"submitted version printed {len(common)}, {len(development)} "
                f"and {len(heldout)} without the middle number, which is why "
                f"they could not be reconciled by a reader."
            ),
        },
        "composed_rule": composed_block,
        "quote_forensics": quote_block,
        "label_space": label_block,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "heldout": len(heldout),
        "development_pass_also_coded": dev_in_coded,
        "eligible": len(eligible),
        "kappa_stated": round(k_stated, 3),
        "kappa_composed": round(k_composed, 3),
        "rule_fidelity_judge_level": round(composed_block["pooled_judge_level_rule_fidelity"], 3),
        "survives_contradicted": composed_block["share_of_survives_contradicted"],
        "quote_classes": dict(forensics),
        "kappa_binary": round(label_block["kappa_binary_survives_vs_not"], 3),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
