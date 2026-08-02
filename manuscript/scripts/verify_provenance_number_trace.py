#!/usr/bin/env python3
"""A reference-based check on the provenance label (reviewer W4).

The reviewer's central objection to the paper's one positive claim is that
``transported`` versus ``re-implemented`` is validated only by inter-judge
agreement, and agreement is not accuracy -- especially when the same section
shows the judges are not independent.  This script supplies the part of the
answer that needs no model at all.

The logic is one-sided and deterministic.  If a citing paper P prints a value
for another system S, then

  * if that value cannot be found anywhere in S's own paper, P did not copy it
    from S: the number was produced inside P's harness.  Absence is therefore
    *sound* evidence for ``re-implemented``;
  * if the value does occur in S's own paper, transport is possible but not
    established, because short numerals collide by chance.

We therefore report a trace statistic per window -- does any result-formatted
number in the window occur verbatim in the cited system's own full text -- and
calibrate its chance level with a placebo, recomputing the same statistic
against a randomly drawn *other* paper from the same corpus.  The gap between
the true-target rate and the placebo rate is the part of the overlap that
citation actually explains.

The check runs only where the cited system's own paper is in the local corpus,
which is a declared, auditable subset, and it is applied identically to every
provenance class, so it cannot favour one.

Writes ``supplement/provenance_number_trace.json`` and a per-window CSV.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"
SEED = 2026080411
PLACEBO_DRAWS = 20

# System name -> the file of the paper that introduces it.  Built from the
# citation-key map where the title states the name, plus this explicit seed for
# systems whose paper title does not contain the system name.
SEED_MAP = {
    "PoisonedRAG": "poisonedRAG2024.txt",
    "Phantom": "phantom2024.txt",
    "BadRAG": "badRAG2024.txt",
    "AIP": "aip2025.txt",
    "Corpus Poisoning": "poisoningRetrievalCorpora2023.txt",
    "RobustRAG": "certifiedRAG2024.txt",
    "CertifiedRAG": "certifiedRAG2024.txt",
    "AstuteRAG": "astuteRAG2025.txt",
    "Astute": "astuteRAG2025.txt",
    "CRAG": "crag2024.txt",
    "Self-CRAG": "crag2024.txt",
    "RAAT": "raat2024.txt",
    "RGB": "rgb2023.txt",
    "RAGTruth": "ragTruth2024.txt",
    "Chain-of-Note": "chainOfNote2023.txt",
    "CoN": "chainOfNote2023.txt",
    "CtrlA": "ctrla2025.txt",
    "REALM": "realm2020.txt",
    "FiD": "fid2021.txt",
    "RETRO": "retro2022.txt",
    "Atlas": "atlas2023.txt",
    "REPLUG": "replug2024.txt",
    "kNN-LM": "knnlm2020.txt",
    "DPR": "dpr2020.txt",
}

NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:\d{1,3}(?:\.\d{1,2})?\s*%|0?\.\d{2,3}|\d{1,3}\.\d{1,2})(?![\w])"
)


def norm_number(tok: str) -> str:
    return tok.replace(" ", "").rstrip("%")


def load_texts() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8", errors="ignore")
            for p in sorted(TEXT_DIR.glob("*.txt"))}


def build_system_map(texts: dict[str, str]) -> dict[str, str]:
    """Resolve gazetteer names to the file of the paper that introduces them."""
    mapping = {k: v for k, v in SEED_MAP.items() if v in texts}
    key_map = REPO / "manuscript" / "citation_key_map.csv"
    if key_map.exists():
        rows = list(csv.DictReader(key_map.open(encoding="utf-8")))
        for row in rows:
            fname = f"{row['cite_key']}.txt"
            if fname not in texts:
                continue
            title = row["title"]
            head = title.split(":")[0].strip()
            # a title of the form "NAME: rest" names the system it introduces
            if 2 <= len(head) <= 24 and " " not in head.strip("-"):
                mapping.setdefault(head, fname)
    return mapping


def numbers_in(text: str) -> set[str]:
    return {norm_number(m.group(0)) for m in NUMBER_PATTERN.finditer(text)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=Path,
                    default=SUP / "cross_paper_frame_candidates.jsonl")
    ap.add_argument("--provenance-dir", type=Path, default=SUP / "cross_paper_provenance")
    ap.add_argument("--out", type=Path, default=SUP / "provenance_number_trace.json")
    ap.add_argument("--csv", type=Path, default=SUP / "provenance_number_trace.csv")
    args = ap.parse_args()

    texts = load_texts()
    sysmap = build_system_map(texts)
    number_index = {name: numbers_in(body) for name, body in texts.items()}

    frame = {}
    for line in args.frame.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            frame[row["candidate_id"]] = row

    votes: dict[str, list[str]] = defaultdict(list)
    for path in sorted(args.provenance_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            parsed = row.get("parsed") or {}
            label = str(parsed.get("provenance", "")).strip().lower()
            if label in ("transported", "reimplemented", "re-implemented", "unclear"):
                votes[row["candidate_id"]].append(
                    "reimplemented" if label == "re-implemented" else label)

    majority = {}
    for cid, vs in votes.items():
        top = Counter(vs).most_common()
        if top and (len(top) == 1 or top[0][1] > top[1][1]):
            majority[cid] = top[0][0]

    rng = random.Random(SEED)
    all_files = sorted(texts)
    rows, per_class = [], defaultdict(lambda: {"n": 0, "hit": 0, "placebo": 0.0})

    for cid, label in sorted(majority.items()):
        cand = frame.get(cid)
        if not cand:
            continue
        targets = [sysmap[s] for s in cand.get("external_systems", [])
                   if s in sysmap and sysmap[s] != cand["source_file"]]
        if not targets:
            continue
        win_numbers = {norm_number(n) for n in cand.get("numbers", [])}
        if not win_numbers:
            continue
        hit = any(win_numbers & number_index[t] for t in targets)
        # placebo: the identical statistic against papers that are NOT cited here
        pool = [f for f in all_files if f not in targets and f != cand["source_file"]]
        placebo_hits = 0
        for _ in range(PLACEBO_DRAWS):
            draw = rng.sample(pool, len(targets))
            placebo_hits += int(any(win_numbers & number_index[d] for d in draw))
        placebo = placebo_hits / PLACEBO_DRAWS
        rows.append({
            "candidate_id": cid,
            "source_file": cand["source_file"],
            "provenance_majority": label,
            "n_window_numbers": len(win_numbers),
            "cited_paper_files": ";".join(targets),
            "number_found_in_cited_paper": int(hit),
            "placebo_rate": round(placebo, 4),
        })
        cell = per_class[label]
        cell["n"] += 1
        cell["hit"] += int(hit)
        cell["placebo"] += placebo

    summary = {}
    for label, cell in per_class.items():
        n = cell["n"]
        summary[label] = {
            "n_windows_checked": n,
            "trace_rate": cell["hit"] / n if n else None,
            "placebo_rate": cell["placebo"] / n if n else None,
            "excess_over_placebo": (cell["hit"] / n - cell["placebo"] / n) if n else None,
        }

    tr = summary.get("transported", {})
    ri = summary.get("reimplemented", {})

    def two_proportion_perm(a_lab, b_lab, draws=20000):
        a = [r["number_found_in_cited_paper"] for r in rows if r["provenance_majority"] == a_lab]
        b = [r["number_found_in_cited_paper"] for r in rows if r["provenance_majority"] == b_lab]
        if not a or not b:
            return None
        obs = sum(a) / len(a) - sum(b) / len(b)
        pool = a + b
        g = random.Random(SEED + 7)
        hits = 0
        for _ in range(draws):
            g.shuffle(pool)
            d = sum(pool[:len(a)]) / len(a) - sum(pool[len(a):]) / len(b)
            if abs(d) >= abs(obs) - 1e-12:
                hits += 1
        return {"difference": obs, "p_two_sided": hits / draws, "draws": draws,
                "n_a": len(a), "n_b": len(b)}

    out = {
        "schema_version": "provenance-number-trace-v1",
        "what_this_is": (
            "A deterministic, one-sided reference check on the provenance label. "
            "A value a citing paper prints for another system that occurs nowhere "
            "in that system's own paper cannot have been transported from it, so "
            "absence is sound evidence for re-implementation; presence is only "
            "consistent with transport because numerals collide by chance, which "
            "the placebo column measures."),
        "n_windows_checked": len(rows),
        "n_windows_with_majority_provenance": len(majority),
        "systems_resolved_to_a_local_paper": len(sysmap),
        "placebo_draws": PLACEBO_DRAWS,
        "by_provenance_class": summary,
        "transported_minus_reimplemented": two_proportion_perm("transported", "reimplemented"),
        "seed": SEED,
    }
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    if rows:
        with args.csv.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
