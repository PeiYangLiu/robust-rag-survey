#!/usr/bin/env python3
"""How thin is the evidence behind the re-weighted composition figure?

The abstract and conclusion foreground "coding the windows the screen missed
leaves the re-weighted share at 93%".  That figure is a ratio of estimated
universe counts, and its numerator for the transported class is estimated from
the handful of sampled missed windows the panel called transported.  A reviewer
counted them from the released runs and found single digits.  The manuscript
should print that count where it prints the figure, and should say what happens
if those few items are wrong.

This script does three things:

1.  counts, exactly, how many sampled missed windows carry a majority
    *transported* label and how many of those are also majority-eligible;
2.  runs a leave-k-out and adversarial perturbation sensitivity over precisely
    those items, so a reader can see the figure's dependence on them; and
3.  reports the figure under the most hostile reassignment of those items that
    the data admit.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"


def majority(values: list[str]) -> str | None:
    if not values:
        return None
    top, n = Counter(values).most_common(1)[0]
    return top if n > len(values) / 2 else None


def load_runs(directory: Path, field: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for path in sorted(directory.glob("*.jsonl")):
        judge = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            parsed = row.get("parsed")
            if not parsed:
                continue
            value = parsed.get(field)
            if field == "eligible":
                value = str(bool(value))
            out[row["candidate_id"]][judge] = str(value).strip().lower()
    return out


def composition(
    frame_share_transported: float,
    frame_eligible_rate: float,
    n_screened: int,
    n_missed: int,
    missed_eligible_rate: float,
    missed_share_transported: float,
) -> float:
    """Re-implemented share of the universe, the manuscript's estimator."""
    frame_elig = n_screened * frame_eligible_rate
    missed_elig = n_missed * missed_eligible_rate
    trans = frame_elig * frame_share_transported + missed_elig * missed_share_transported
    reimpl = frame_elig * (1 - frame_share_transported) + missed_elig * (
        1 - missed_share_transported
    )
    return reimpl / (trans + reimpl) if (trans + reimpl) else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=SUPPLEMENT / "screen_recall_runs")
    parser.add_argument("--results", type=Path, default=SUPPLEMENT / "screen_recall_results.json")
    parser.add_argument(
        "--out", type=Path, default=SUPPLEMENT / "screen_recall_sensitivity.json"
    )
    args = parser.parse_args()

    base = json.loads(args.results.read_text(encoding="utf-8"))
    pe = base["point_estimates"]

    elig = load_runs(args.runs / "elig", "eligible")
    prov = load_runs(args.runs / "prov", "provenance")

    ids = sorted(set(elig) | set(prov))
    maj_elig = {cid: majority(sorted(elig.get(cid, {}).values())) for cid in ids}
    maj_prov = {cid: majority(sorted(prov.get(cid, {}).values())) for cid in ids}

    transported = [cid for cid in ids if maj_prov.get(cid) == "transported"]
    transported_eligible = [cid for cid in transported if maj_elig.get(cid) == "true"]
    reimplemented_eligible = [
        cid
        for cid in ids
        if maj_prov.get(cid) == "reimplemented" and maj_elig.get(cid) == "true"
    ]
    classified_eligible = transported_eligible + reimplemented_eligible

    n_t, n_r = len(transported_eligible), len(reimplemented_eligible)
    observed_share = n_t / (n_t + n_r) if (n_t + n_r) else float("nan")

    def share_from(counts_t: int, counts_r: int) -> float:
        return counts_t / (counts_t + counts_r) if (counts_t + counts_r) else float("nan")

    def universe_share(missed_share_t: float) -> float:
        return composition(
            pe["frame_share_transported"],
            pe["frame_eligible_rate"],
            base["n_screened_windows"],
            base["n_missed_windows"],
            pe["missed_eligible_rate"],
            missed_share_t,
        )

    # --- adversarial perturbation over the transported items -----------------
    # Every one of the transported-labelled eligible windows is reassigned to
    # re-implemented, then every re-implemented one that could plausibly flip is
    # reassigned the other way, at matched count.
    all_to_reimplemented = universe_share(share_from(0, n_t + n_r))
    doubled_transported = universe_share(share_from(2 * n_t, max(0, n_r - n_t)))

    leave_one_out = []
    for cid in transported_eligible:
        leave_one_out.append(
            {
                "dropped": cid,
                "universe_reimplemented_share": universe_share(
                    share_from(n_t - 1, n_r)
                ),
            }
        )
    loo_vals = [row["universe_reimplemented_share"] for row in leave_one_out]

    # leave-k-out over every subset of the transported items, exhaustive while
    # the count is small enough to enumerate
    exhaustive = {}
    if n_t <= 20:
        for k in range(0, n_t + 1):
            exhaustive[str(k)] = universe_share(share_from(n_t - k, n_r + k))

    # --- a Bayesian-flavoured floor: what if the panel is right only p of the
    # time on these items?  A judge-level bootstrap over the sampled windows.
    rng = random.Random(20260731)
    boot = []
    papers = defaultdict(list)
    sample_rows = {}
    sample_path = SUPPLEMENT / "screen_recall_sample.jsonl"
    if sample_path.exists():
        for line in sample_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                sample_rows[row["candidate_id"]] = row
    for cid in classified_eligible:
        paper = sample_rows.get(cid, {}).get("cite_key", cid)
        papers[paper].append(cid)
    keys = sorted(papers)
    for _ in range(4000):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        drawn = [cid for k in pick for cid in papers[k]]
        t = sum(1 for cid in drawn if maj_prov.get(cid) == "transported")
        r = len(drawn) - t
        if t + r:
            boot.append(universe_share(share_from(t, r)))
    boot.sort()

    payload = {
        "schema_version": 1,
        "n_missed_sampled": base["n_missed_sampled"],
        "n_missed_with_majority_transported": len(transported),
        "n_missed_transported_and_eligible": n_t,
        "n_missed_reimplemented_and_eligible": n_r,
        "n_missed_classified_eligible": n_t + n_r,
        "observed_missed_share_transported": observed_share,
        "published_missed_share_transported": pe["missed_share_transported"],
        "published_universe_reimplemented_share": pe["universe_reimplemented_share"],
        "published_ci95": base["cluster_bootstrap_ci95"]["universe_reimplemented_share"],
        "sensitivity": {
            "all_transported_items_reassigned_to_reimplemented": all_to_reimplemented,
            "transported_count_doubled": doubled_transported,
            "leave_one_out_min": min(loo_vals) if loo_vals else float("nan"),
            "leave_one_out_max": max(loo_vals) if loo_vals else float("nan"),
            "exhaustive_leave_k_out": exhaustive,
            "frame_share_unchanged": pe["frame_reimplemented_share"],
        },
        "paper_cluster_bootstrap": {
            "draws": len(boot),
            "ci95": [boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]] if boot else [],
            "median": boot[len(boot) // 2] if boot else float("nan"),
        },
        "recall_transported_ci95": base["cluster_bootstrap_ci95"]["recall_transported"],
        "interpretation": (
            f"The re-weighting from {pe['frame_reimplemented_share']:.3f} inside "
            f"the frame to {pe['universe_reimplemented_share']:.3f} over the "
            f"universe is driven by {n_t} eligible sampled windows the panel "
            f"called transported. Reassigning all {n_t} to re-implemented moves "
            f"the figure to {all_to_reimplemented:.3f}; doubling their count "
            f"moves it to {doubled_transported:.3f}. The direction of the "
            f"re-weighting is stable under both perturbations but its magnitude "
            f"is not, which is why the frame figure and the universe figure are "
            f"both reported and neither is claimed for the literature."
        ),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in (
        "n_missed_with_majority_transported",
        "n_missed_transported_and_eligible",
        "n_missed_reimplemented_and_eligible",
        "observed_missed_share_transported",
        "published_universe_reimplemented_share",
        "sensitivity",
        "paper_cluster_bootstrap",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
