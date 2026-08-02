#!/usr/bin/env python3
"""Run the comparability instrument benchmark (reviewer W1, W4, W7, W9).

Every item's five coordinate values and its verdict are fixed when the item is
written, so this measures the instrument against a reference that needs no
annotation and has no provenance to audit.  Each judge answers every item under
one of three codebooks, which are byte-identical to the ones used on the real
corpus:

  five    the released five-coordinate codebook;
  c1c4    the two non-degenerate coordinates only;
  direct  no coordinates, the comparability question asked in one step.

Outputs ``supplement/comparability_instrument_runs/<arm>/<judge>.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from code_cross_paper_frame import CODEBOOK, call, call_cli, extract_json  # noqa: E402
from code_frame_codebook_arms import CODEBOOK_C1C4, CODEBOOK_DIRECT  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
ORDER_SEED = 2026073111

ARMS = {"five": CODEBOOK, "c1c4": CODEBOOK_C1C4, "direct": CODEBOOK_DIRECT}
_LOCK = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--judge-name", required=True)
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument(
        "--items", type=Path, default=SUP / "comparability_instrument_benchmark.jsonl"
    )
    ap.add_argument("--out-root", type=Path, default=SUP / "comparability_instrument_runs")
    ap.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    ap.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=2500)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--backend", choices=("http", "cli"), default="http")
    args = ap.parse_args()

    items = [
        json.loads(line)
        for line in args.items.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    random.Random(ORDER_SEED).shuffle(items)

    out_dir = args.out_root / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.judge_name}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    done.add(row["item_id"])
    pending = [i for i in items if i["item_id"] not in done]
    print(f"{args.judge_name}[{args.arm}]: {len(pending)} pending", flush=True)

    codebook = ARMS[args.arm]
    handle = out_path.open("a", encoding="utf-8")

    def work(item):
        user = (
            f"SOURCE FILE: {item['item_id']}.txt\n"
            f"FOCUS LINE RANGE: 1-1\n"
            f"SYSTEM NAMES DETECTED THAT ARE NOT THIS PAPER'S OWN: "
            f"{item['side_b']}\n\n"
            f"FOCUS PASSAGE (the juxtaposition to code):\n<<<\n"
            f"{item['focus_text']}\n>>>\n\n"
            f"SURROUNDING CONTEXT (use it to determine the coordinates; the "
            f"focus passage is repeated inside it):\n<<<\n"
            f"{item['context_text']}\n>>>\n"
        )
        messages = [
            {"role": "system", "content": codebook},
            {"role": "user", "content": user},
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
            "item_id": item["item_id"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "arm": args.arm,
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
    print(f"{args.judge_name}[{args.arm}]: wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
