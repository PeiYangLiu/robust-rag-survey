#!/usr/bin/env python3
"""Answer the constructed provenance benchmark (reviewer W4).

Two arms:

  deployed   the byte-identical prompt used on the real corpus in
             ``classify_number_provenance.py``.  This is the arm that scores the
             instrument the census actually ran, which is the thing the
             reviewer asks to see validated.
  fourway    the same prompt with the fourth option the manuscript's Section 4
             names but the deployed prompt cannot express, so that the cost of
             the missing option is separable from the cost of the judgment.

Outputs ``supplement/provenance_benchmark_runs/<arm>/<judge>.jsonl``.
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
from code_cross_paper_frame import call, call_cli, extract_json  # noqa: E402
from classify_number_provenance import PROMPT as DEPLOYED_PROMPT  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
ORDER_SEED = 2026080422

FOURWAY_PROMPT = DEPLOYED_PROMPT.replace(
    '"unclear" - the passage genuinely does not say which of the two it is.',
    '"asserted_no_number" - the passage asserts a relation to the other system\n'
    "   (that this system beats it, or reduces its effect) while supplying NO\n"
    "   number for the other side at a comparable operating point. There is no\n"
    "   other-paper value in the passage to have been obtained either way.\n"
    '"unclear" - the passage genuinely does not say which of the two it is.',
).replace(
    '"provenance": "reimplemented"|"transported"|"unclear",',
    '"provenance": "reimplemented"|"transported"|"asserted_no_number"|"unclear",',
)

ARMS = {"deployed": DEPLOYED_PROMPT, "fourway": FOURWAY_PROMPT}
_LOCK = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--judge-name", required=True)
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--items", type=Path, default=SUP / "provenance_benchmark.jsonl")
    ap.add_argument("--out-root", type=Path, default=SUP / "provenance_benchmark_runs")
    ap.add_argument("--base-url",
                    default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1"))
    ap.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=900)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--backend", choices=("http", "cli"), default="http")
    args = ap.parse_args()

    items = [json.loads(line) for line in
             args.items.read_text(encoding="utf-8").splitlines() if line.strip()]
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

    prompt = ARMS[args.arm]
    handle = out_path.open("a", encoding="utf-8")

    def work(item):
        user = (
            f"SOURCE FILE: {item['item_id']}.txt\n"
            f"FOCUS LINE RANGE: 1-1\n"
            f"OTHER-PAPER SYSTEMS DETECTED: {item['side_other']}\n\n"
            f"FOCUS PASSAGE:\n<<<\n{item['focus_text']}\n>>>\n\n"
            f"SURROUNDING CONTEXT:\n<<<\n{item['context_text']}\n>>>\n"
        )
        messages = [{"role": "system", "content": prompt},
                    {"role": "user", "content": user}]
        if args.backend == "cli":
            text, error = call_cli(args.judge, messages, args.timeout, args.retries)
        else:
            text, error = call(args.base_url, args.api_key, args.judge, messages,
                               args.max_tokens, args.timeout, args.retries)
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
