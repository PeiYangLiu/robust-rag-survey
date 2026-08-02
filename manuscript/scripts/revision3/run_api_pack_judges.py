#!/usr/bin/env python3
"""Run an API-served judge over a pre-rendered prompt pack.

The open-weight judges consume ``supplement/open_judge_prompts/<task>.jsonl``.
Pointing the API judges at the same pack guarantees that an API judge and an
open judge answer byte-identical prompts, which is what lets the two pools be
compared and pooled rather than merely reported side by side. Each record
carries the prompt SHA-256 that proves it.

The purpose is the reviewer's objection to sigma_r: a variance component
estimated from six judges cannot carry a design recommendation. Widening the
pool is the only fix, and the constructed benchmark is the arm where widening it
means something, because its reference verdict is fixed before any judge sees
the item.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from code_cross_paper_frame import call, extract_json  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
_LOCK = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--judge-name", required=True)
    ap.add_argument("--task", default="instrument",
                    choices=("instrument", "census", "abstention"))
    ap.add_argument("--pack", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=SUPPLEMENT / "api_pack_runs")
    ap.add_argument("--base-url",
                    default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1"))
    ap.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    pack = args.pack or (SUPPLEMENT / "open_judge_prompts" / f"{args.task}.jsonl")
    records = [
        json.loads(line)
        for line in pack.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        records = records[: args.limit]

    out_dir = args.out_dir / args.task
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.judge_name}.jsonl"
    done: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("parsed"):
                    done.add(rec.get("item_id") or rec.get("candidate_id"))
    pending = [r for r in records if r["id"] not in done]
    print(f"{args.judge_name}/{args.task}: {len(pending)} pending of {len(records)}",
          flush=True)
    if not pending:
        return 0

    handle = out_path.open("a", encoding="utf-8")
    prog = {"n": 0, "ok": 0}
    started = time.time()

    def work(rec: dict) -> None:
        text, error = call(
            args.base_url, args.api_key, args.judge,
            [{"role": "system", "content": rec["system"]},
             {"role": "user", "content": rec["user"]}],
            args.max_tokens, args.timeout, args.retries,
        )
        parsed = extract_json(text)
        row = {
            rec.get("id_field", "item_id"): rec["id"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "task": args.task,
            "arm": args.task,
            "prompt_sha256": rec.get("prompt_sha256"),
            "meta": rec.get("meta"),
            "raw_response": text,
            "api_error": error,
            "parsed": parsed,
        }
        with _LOCK:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            prog["n"] += 1
            prog["ok"] += 1 if parsed else 0
            if prog["n"] % 50 == 0:
                print(f"  {args.judge_name} {prog['n']}/{len(pending)} "
                      f"parsed={prog['ok']} "
                      f"{prog['n']/max(1e-9,time.time()-started):.2f}/s", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, pending))
    handle.close()
    print(f"done {args.judge_name}/{args.task}: {prog['ok']}/{prog['n']} parsed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
