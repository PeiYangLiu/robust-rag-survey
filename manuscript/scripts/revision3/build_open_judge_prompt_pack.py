#!/usr/bin/env python3
"""Render the exact prompts the API judges answered into a portable pack.

The open-weight judges must answer the *same question* as the API judges, not a
reconstruction of it.  Rendering the prompts once, here, and shipping the
rendered strings to the GPU job guarantees that: the system message is the
released codebook, the user message is assembled by the same code path the
census used, and the pack carries a SHA-256 of each prompt so a reader can check
that an open judge and an API judge saw identical bytes.

It also keeps the compute job small.  The census prompts embed +-45 lines of
extracted paper text, so rendering them here means the job needs the pack rather
than the 679 MB full-text corpus.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANUSCRIPT = HERE.parents[1]
sys.path.insert(0, str(MANUSCRIPT / "scripts"))
sys.path.insert(0, str(HERE))

from code_cross_paper_frame import CODEBOOK, context_for  # noqa: E402
from run_abstention_verdict import abstention_codebook  # noqa: E402

SUPPLEMENT = MANUSCRIPT / "supplement"
ORDER_SEED = 2026072811


def census_records(codebook: str, context_lines: int, restrict: Path) -> list[dict]:
    windows = [
        json.loads(line)
        for line in (SUPPLEMENT / "cross_paper_frame_candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    keep = {
        r["candidate_id"] for r in csv.DictReader(restrict.open(encoding="utf-8"))
    }
    random.Random(ORDER_SEED).shuffle(windows)
    out = []
    for w in windows:
        if w["candidate_id"] not in keep:
            continue
        user = (
            f"SOURCE FILE: {w['source_file']}\n"
            f"FOCUS LINE RANGE: {w['line_start']}-{w['line_end']}\n"
            f"SYSTEM NAMES DETECTED THAT ARE NOT THIS PAPER'S OWN: "
            f"{', '.join(w['external_systems'])}\n\n"
            f"FOCUS PASSAGE (the juxtaposition to code):\n<<<\n"
            f"{w['window_text']}\n>>>\n\n"
            f"SURROUNDING CONTEXT (use it to determine the coordinates; the "
            f"focus passage is repeated inside it):\n<<<\n"
            f"{context_for(w, context_lines)}\n>>>\n"
        )
        out.append(
            {
                "id": w["candidate_id"],
                "id_field": "candidate_id",
                "system": codebook,
                "user": user,
                "meta": {
                    "cite_key": w["cite_key"],
                    "window_sha256": w["window_sha256"],
                },
            }
        )
    return out


def instrument_records(codebook: str) -> list[dict]:
    items = [
        json.loads(line)
        for line in (SUPPLEMENT / "comparability_instrument_benchmark_v2.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    random.Random(ORDER_SEED).shuffle(items)
    out = []
    for it in items:
        user = (
            "SETUP AND RESULTS PASSAGE (code the juxtaposition it contains):\n"
            f"<<<\n{it['context_text']}\n>>>\n\n"
            f"FOCUS SENTENCES:\n<<<\n{it['focus_text']}\n>>>\n"
        )
        out.append(
            {
                "id": it["item_id"],
                "id_field": "item_id",
                "system": codebook,
                "user": user,
                "meta": {
                    "disclosure": it["disclosure"],
                    "presentation": it["presentation"],
                    "truth_verdict": it["truth_verdict"],
                    "pair_id": it["pair_id"],
                },
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=SUPPLEMENT / "open_judge_prompts")
    ap.add_argument("--context-lines", type=int, default=45)
    ap.add_argument(
        "--restrict-to", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv"
    )
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    packs = {
        "census": census_records(CODEBOOK, args.context_lines, args.restrict_to),
        "abstention": census_records(
            abstention_codebook(), args.context_lines, args.restrict_to
        ),
        "instrument": instrument_records(CODEBOOK),
    }
    manifest = {}
    for name, records in packs.items():
        path = args.out_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for rec in records:
                rec["prompt_sha256"] = hashlib.sha256(
                    (rec["system"] + rec["user"]).encode("utf-8")
                ).hexdigest()
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
        manifest[name] = {
            "n_records": len(records),
            "path": str(path.relative_to(MANUSCRIPT)),
            "bytes": path.stat().st_size,
            "codebook_sha256": hashlib.sha256(
                records[0]["system"].encode("utf-8")
            ).hexdigest()
            if records
            else None,
            "mean_user_chars": (
                sum(len(r["user"]) for r in records) / len(records) if records else 0
            ),
            "max_user_chars": max((len(r["user"]) for r in records), default=0),
        }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
