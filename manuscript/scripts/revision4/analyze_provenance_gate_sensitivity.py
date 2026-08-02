#!/usr/bin/env python3
"""Reviewer Q7: is the re-implementation share sensitive to the eligibility gate?

The composition claim -- 533 of 610 classified windows (87.4%) are
re-implementations rather than transported numbers -- is measured on the
candidates that passed a *majority* eligibility gate, whose inter-judge Fleiss
kappa on eligibility is only ~0.51.  A reviewer asked whether that share moves
when the gate is tightened, loosened, or removed.

This script recomputes the re-implementation share, its Wilson 95% interval and
its N under four gates, and under a per-judge leave-one-out variant of the
majority gate.  It changes nothing upstream: eligibility is re-derived from the
same three deployed coders, the development pass is held out exactly as the
primary census holds it out, and the provenance class of a window is the
majority of the same three independent provenance judges.  Nothing here is
fabricated: where a gate would require provenance labels that were never
elicited, that is reported as a coverage gap, not filled in.

Gates
  (a) unanimous   -- all three coders call the window eligible;
  (b) majority    -- at least two of three (the deployed setting; reproduces
                     the published 87.4% exactly);
  (c) any-judge   -- at least one of three;
  (d) no gate     -- every candidate that received a provenance class.

Writes ``supplement/provenance_gate_sensitivity.json``.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"

DEPLOYED = ["coderA_gpt5mini", "coderB_claudeopus46", "coderC_gemini31pro"]
PROV_CLASSES = {"transported", "reimplemented", "unclear"}


def wilson(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson score interval; identical formula to the census script."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def majority(values: list[str]) -> str | None:
    """Strict majority: the top label must be strictly more than half the votes.

    For three votes this means at least two agree; for two votes it means both
    agree.  Matches ``analyze_cross_paper_census.py``.
    """
    if not values:
        return None
    top, n = Counter(values).most_common(1)[0]
    return top if n > len(values) / 2 else None


def load_parsed(path: Path, key: str = "candidate_id") -> dict[str, dict]:
    table: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("parsed"):
            table[row[key]] = row
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", type=Path, default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl")
    ap.add_argument("--coding-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    ap.add_argument("--development-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding_dev")
    ap.add_argument("--provenance-dir", type=Path, default=SUPPLEMENT / "cross_paper_provenance")
    ap.add_argument("--output", type=Path, default=SUPPLEMENT / "provenance_gate_sensitivity.json")
    args = ap.parse_args()

    # ---- frame and deployed eligibility codings -----------------------------
    windows = {}
    for line in args.candidates.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            windows[row["candidate_id"]] = row

    per_judge = {j: load_parsed(args.coding_dir / f"{j}.jsonl") for j in DEPLOYED}
    common = set.intersection(*(set(per_judge[j]) for j in DEPLOYED)) & set(windows)

    # Hold out the codebook-development pass exactly as the primary census does:
    # candidates every development coding covers are excluded.
    dev_tables = []
    for j in DEPLOYED:
        path = args.development_dir / f"{j}.jsonl"
        ids = set(load_parsed(path)) if path.exists() else set()
        if ids:
            dev_tables.append(ids)
    development = set.intersection(*dev_tables) if dev_tables else set()

    ordered = [cid for cid in sorted(common) if cid not in development]

    def elig_row(cid: str) -> list[bool]:
        return [bool(per_judge[j][cid]["parsed"].get("eligible")) for j in DEPLOYED]

    elig = {cid: elig_row(cid) for cid in ordered}
    gate_sets = {
        "unanimous": {cid for cid in ordered if all(elig[cid])},
        "majority": {cid for cid in ordered if sum(elig[cid]) >= 2},
        "any_judge": {cid for cid in ordered if any(elig[cid])},
    }

    # ---- provenance class per candidate (majority of three prov judges) -----
    prov_tables: dict[str, dict[str, str]] = {}
    for path in sorted(args.provenance_dir.glob("*.jsonl")):
        table: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            value = str((row.get("parsed") or {}).get("provenance", "")).strip().lower()
            if value in PROV_CLASSES:
                table[row["candidate_id"]] = value
        if table:
            prov_tables[path.stem] = table
    prov_judges = sorted(prov_tables)
    prov_coded_all = set.intersection(*(set(prov_tables[j]) for j in prov_judges))
    # class map over every candidate all three provenance judges labelled
    pclass = {
        cid: majority([prov_tables[j][cid] for j in prov_judges]) for cid in prov_coded_all
    }

    def summarise(id_iterable) -> dict:
        ids = [cid for cid in id_iterable if cid in pclass]
        counts = Counter(pclass[cid] for cid in ids)
        reimp = counts.get("reimplemented", 0)
        trans = counts.get("transported", 0)
        unclear = counts.get("unclear", 0)
        no_maj = counts.get(None, 0)
        classified = reimp + trans
        lo, hi = wilson(reimp, classified)
        lo_u, hi_u = wilson(reimp, classified + unclear)
        return {
            "n_provenance_coded": len(ids),
            "n_reimplemented": reimp,
            "n_transported": trans,
            "n_unclear": unclear,
            "n_no_majority": no_maj,
            "n_classified": classified,
            "reimplemented_share": (reimp / classified if classified else float("nan")),
            "wilson_ci95": [lo, hi],
            # secondary denominator that keeps 'unclear' in the base, for readers
            # who object to dropping it; not the published definition.
            "reimplemented_share_incl_unclear": (
                reimp / (classified + unclear) if (classified + unclear) else float("nan")
            ),
            "wilson_ci95_incl_unclear": [lo_u, hi_u],
            "composition_consistent": (reimp + trans + unclear + no_maj == len(ids)),
        }

    # ---- the four gates -----------------------------------------------------
    gates: dict[str, dict] = {}

    a = summarise(gate_sets["unanimous"])
    a.update({
        "definition": "all three coders call the window eligible",
        "n_gate_eligible": len(gate_sets["unanimous"]),
        "n_missing_provenance": len(gate_sets["unanimous"]) - a["n_provenance_coded"],
    })
    gates["a_unanimous"] = a

    b = summarise(gate_sets["majority"])
    b.update({
        "definition": "at least two of three coders call the window eligible (deployed setting)",
        "n_gate_eligible": len(gate_sets["majority"]),
        "n_missing_provenance": len(gate_sets["majority"]) - b["n_provenance_coded"],
        "reproduces_published_874": (
            b["n_reimplemented"] == 533 and b["n_classified"] == 610
        ),
    })
    gates["b_majority"] = b

    c = summarise(gate_sets["any_judge"])
    c.update({
        "definition": "at least one of three coders calls the window eligible",
        "n_gate_eligible": len(gate_sets["any_judge"]),
        "n_missing_provenance": len(gate_sets["any_judge"]) - c["n_provenance_coded"],
        "coverage_note": (
            "The provenance pass was only ever run on the majority-eligible "
            "ledger, so no window that fails the majority gate carries a "
            "provenance label. Every provenance-coded any-judge-eligible window "
            "is therefore also majority-eligible, and this row necessarily "
            "equals the majority gate. The re-implementation share over the "
            "windows that are any-judge-eligible but NOT majority-eligible "
            "cannot be computed from existing data and is not invented."
        ),
    })
    gates["c_any_judge"] = c

    # (d) no gate: every candidate that received a provenance class, ignoring
    # eligibility entirely. This is bounded by what the provenance pass covered.
    d = summarise(prov_coded_all)
    in_frame = prov_coded_all & set(windows)
    not_in_frame = prov_coded_all - set(windows)
    d.update({
        "definition": "every candidate all three provenance judges labelled, no eligibility gate",
        "n_gate_eligible": len(prov_coded_all),
        "n_missing_provenance": 0,
        "n_in_current_frame": len(in_frame),
        "n_absent_from_current_frame": len(not_in_frame),
        "coverage_note": (
            "A true no-gate share over all 1,703 candidates is not computable: "
            "only the provenance-coded set carries labels. Of these, "
            f"{len(not_in_frame)} are absent from the current candidate frame "
            "(they appear only in the codebook-development codings) and are "
            "excluded from the primary census by construction; restricting to "
            "the current frame reproduces the majority gate exactly."
        ),
    })
    d["restricted_to_current_frame"] = summarise(in_frame)
    gates["d_no_gate"] = d

    # ---- per-judge leave-one-out on the majority gate -----------------------
    # Drop one coder; require a majority of the remaining two (i.e. both agree).
    loo_configs = []
    for drop in DEPLOYED:
        keep = [j for j in DEPLOYED if j != drop]
        idx = [DEPLOYED.index(j) for j in keep]
        gate = {cid for cid in ordered if all(elig[cid][i] for i in idx)}
        s = summarise(gate)
        s["dropped_judge"] = drop
        s["kept_judges"] = keep
        s["n_gate_eligible"] = len(gate)
        loo_configs.append(s)
    loo_shares = [s["reimplemented_share"] for s in loo_configs if s["n_classified"]]

    payload = {
        "schema_version": "provenance-gate-sensitivity-v1",
        "question": (
            "Reviewer Q7: sensitivity of the 87.4% re-implementation share to "
            "the LLM eligibility gate (eligibility Fleiss kappa ~= 0.51)."
        ),
        "definitions": {
            "reimplemented_share": "n_reimplemented / (n_reimplemented + n_transported)",
            "classified": "windows the provenance panel assigned to reimplemented or transported (excludes unclear and no-majority)",
            "provenance_class": "strict majority of three independent provenance judges (provA_gpt5mini, provB_claudeopus46, provC_gemini31pro)",
        },
        "frame": {
            "n_candidates": len(windows),
            "n_coded_by_all_deployed": len(common),
            "n_development_heldout": len(development),
            "n_ordered_heldout": len(ordered),
            "n_unanimous_eligible": len(gate_sets["unanimous"]),
            "n_majority_eligible": len(gate_sets["majority"]),
            "n_any_judge_eligible": len(gate_sets["any_judge"]),
        },
        "provenance": {
            "judges": prov_judges,
            "n_coded_by_all_provenance_judges": len(prov_coded_all),
        },
        "gates": gates,
        "leave_one_out_majority_gate": {
            "note": "drop one coder in turn; majority of the remaining two = both agree eligible",
            "configs": loo_configs,
            "share_min": min(loo_shares) if loo_shares else float("nan"),
            "share_max": max(loo_shares) if loo_shares else float("nan"),
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # ---- console summary ----------------------------------------------------
    print(f"frame: {len(windows)} candidates; held out {len(ordered)}; "
          f"unanimous {len(gate_sets['unanimous'])}, majority {len(gate_sets['majority'])}, "
          f"any-judge {len(gate_sets['any_judge'])}")
    print(f"provenance coded by all 3 judges: {len(prov_coded_all)}\n")
    order = [
        ("a_unanimous", "unanimous"),
        ("b_majority", "majority"),
        ("c_any_judge", "any-judge*"),
        ("d_no_gate", "no gate*"),
    ]
    print(f"{'gate':<12}{'N_class':>8}{'reimp':>7}{'trans':>7}{'unclear':>8}{'share':>8}  Wilson95")
    for gkey, label in order:
        g = gates[gkey]
        lo, hi = g["wilson_ci95"]
        print(f"{label:<12}{g['n_classified']:>8}{g['n_reimplemented']:>7}"
              f"{g['n_transported']:>7}{g['n_unclear']:>8}{g['reimplemented_share']:>8.4f}"
              f"  [{lo:.4f}, {hi:.4f}]")
    print("  * see coverage_note: provenance was elicited only on the majority-eligible ledger")
    print(f"\nleave-one-out majority gate share range: "
          f"[{payload['leave_one_out_majority_gate']['share_min']:.4f}, "
          f"{payload['leave_one_out_majority_gate']['share_max']:.4f}]")
    for s in loo_configs:
        lo, hi = s["wilson_ci95"]
        print(f"  drop {s['dropped_judge']:<22} N_class={s['n_classified']:>4} "
              f"share={s['reimplemented_share']:.4f} [{lo:.4f}, {hi:.4f}]")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
