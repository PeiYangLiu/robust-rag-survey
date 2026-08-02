#!/usr/bin/env python3
"""Independent re-coding of the worked comparability ledger (reviewer W5).

The ledger of worked cross-paper comparisons is coded once, by us.  A reviewer
observed that a paper whose own census shows verdicts of this kind do not
replicate cannot then report single-coded verdicts as headline rates without
measuring the same thing about itself.

This script re-codes every ledger case from scratch with an independent panel of
judges drawn from three developers.  Each judge is shown, for one case:

  * the neutral statement of what the two papers place side by side,
  * the two paper titles, and
  * every verbatim source excerpt registered in the ledger's provenance list,
    widened by a fixed context margin and labelled only by file and line,

and nothing else.  Our mismatch labels, our corrected reading, our matched
number and our verdict are never shown.  The judge answers under the identical
census codebook.  Agreement between the panel and our coding, and among the
panel members, is then reported in the manuscript instead of being asserted.

Outputs ``supplement/ledger_recoding/<judge>.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from code_cross_paper_frame import (  # noqa: E402
    CODEBOOK,
    call,
    call_cli,
    extract_json,
)

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
ORDER_SEED = 2026073101
CONTEXT = 6

_LOCK = threading.Lock()
_LINES: dict[str, list[str]] = {}


def excerpt(path: str, span: str) -> str:
    if path not in _LINES:
        p = Path(path)
        _LINES[path] = (
            p.read_text(encoding="utf-8", errors="replace").splitlines()
            if p.exists()
            else []
        )
    lines = _LINES[path]
    if not lines:
        return ""
    match = re.match(r"(\d+)\s*-\s*(\d+)", str(span))
    if not match:
        return ""
    lo = max(0, int(match.group(1)) - 1 - CONTEXT)
    hi = min(len(lines), int(match.group(2)) + CONTEXT)
    body = "\n".join(lines[lo:hi])
    return f"[{Path(path).name} lines {lo + 1}-{hi}]\n{body}"


def packet(case: dict) -> str:
    """Everything the judge sees.  Our own labels are excluded by construction."""
    seen: set[tuple[str, str]] = set()
    blocks = []
    for item in case.get("provenance", []) + case.get("quoted_strings", []):
        key = (item.get("file", ""), item.get("lines", ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        text = excerpt(key[0], key[1])
        if text:
            blocks.append(text)
    return (
        f"CASE: {case['case_id']}\n"
        f"WHAT IS PLACED SIDE BY SIDE:\n{case['comparison_claim']}\n\n"
        f"SIDE A PAPER: {case['side_A_name']}\n"
        f"SIDE B PAPER: {case['side_B_name']}\n\n"
        "VERBATIM SOURCE EXCERPTS (every passage either paper supplies that "
        "bears on this juxtaposition; work only from these):\n<<<\n"
        + "\n\n---\n\n".join(blocks)
        + "\n>>>\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--judge-name", required=True)
    ap.add_argument(
        "--cases", type=Path, default=SUP / "cross_paper_comparability_cases.json"
    )
    ap.add_argument("--out-dir", type=Path, default=SUP / "ledger_recoding")
    ap.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    ap.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--timeout", type=float, default=420.0)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--backend", choices=("http", "cli"), default="http")
    args = ap.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    random.Random(ORDER_SEED).shuffle(cases)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.judge_name}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    done.add(row["case_id"])
    pending = [c for c in cases if c["case_id"] not in done]
    print(f"{args.judge_name}: {len(pending)} pending of {len(cases)}", flush=True)
    handle = out_path.open("a", encoding="utf-8")

    def work(case):
        messages = [
            {"role": "system", "content": CODEBOOK},
            {"role": "user", "content": packet(case)},
        ]
        if args.backend == "cli":
            text, error = call_cli(args.judge, messages, args.timeout, args.retries)
        else:
            text, error = call(
                args.base_url,
                args.api_key,
                args.judge,
                messages,
                args.max_tokens,
                args.timeout,
                args.retries,
            )
        record = {
            "case_id": case["case_id"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "raw_response": text,
            "api_error": error,
            "parsed": extract_json(text),
        }
        with _LOCK:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
        return record

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, pending))
    handle.close()
    print(f"{args.judge_name}: wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
