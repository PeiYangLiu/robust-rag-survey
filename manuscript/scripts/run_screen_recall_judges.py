#!/usr/bin/env python3
"""Code the out-of-frame sample with the deployed instrument (reviewer W5).

Two passes, each using a byte-identical copy of a prompt that was run on the
frame itself, so that a window the screen missed is judged by exactly the
instrument that judged the windows it kept:

  elig  the five-coordinate codebook from ``code_cross_paper_frame``; only its
        ``eligible`` field is used here;
  prov  the provenance prompt from ``classify_number_provenance``.

Outputs ``supplement/screen_recall_runs/<pass>/<judge>.jsonl``.
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
from code_cross_paper_frame import (  # noqa: E402
    CODEBOOK, call, call_cli, context_for, extract_json,
)
from classify_number_provenance import PROMPT as PROV_PROMPT  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SUP = REPO / "manuscript" / "supplement"
ORDER_SEED = 2026080432
PASSES = {"elig": CODEBOOK, "prov": PROV_PROMPT}
_LOCK = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--judge-name", required=True)
    ap.add_argument("--pass-name", required=True, choices=sorted(PASSES))
    ap.add_argument("--items", type=Path, default=SUP / "screen_recall_sample.jsonl")
    ap.add_argument("--out-root", type=Path, default=SUP / "screen_recall_runs")
    ap.add_argument("--base-url",
                    default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1"))
    ap.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--context-lines", type=int, default=45)
    ap.add_argument("--backend", choices=("http", "cli"), default="http")
    args = ap.parse_args()

    items = [json.loads(line) for line in
             args.items.read_text(encoding="utf-8").splitlines() if line.strip()]
    random.Random(ORDER_SEED).shuffle(items)

    out_dir = args.out_root / args.pass_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.judge_name}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("parsed"):
                    done.add(row["candidate_id"])
    pending = [i for i in items if i["candidate_id"] not in done]
    print(f"{args.judge_name}[{args.pass_name}]: {len(pending)} pending", flush=True)

    prompt = PASSES[args.pass_name]
    handle = out_path.open("a", encoding="utf-8")

    def work(cand):
        context = context_for(cand, args.context_lines)
        header = (
            f"SOURCE FILE: {cand['source_file']}\n"
            f"FOCUS LINE RANGE: {cand['line_start']}-{cand['line_end']}\n")
        if args.pass_name == "elig":
            header += (f"SYSTEM NAMES DETECTED THAT ARE NOT THIS PAPER'S OWN: "
                       f"{', '.join(cand['external_systems'])}\n\n"
                       f"FOCUS PASSAGE (the juxtaposition to code):\n<<<\n"
                       f"{cand['window_text']}\n>>>\n\n"
                       f"SURROUNDING CONTEXT (use it to determine the coordinates; "
                       f"the focus passage is repeated inside it):\n<<<\n{context}\n>>>\n")
        else:
            header += (f"OTHER-PAPER SYSTEMS DETECTED: "
                       f"{', '.join(cand['external_systems'])}\n\n"
                       f"FOCUS PASSAGE:\n<<<\n{cand['window_text']}\n>>>\n\n"
                       f"SURROUNDING CONTEXT:\n<<<\n{context}\n>>>\n")
        messages = [{"role": "system", "content": prompt},
                    {"role": "user", "content": header}]
        if args.backend == "cli":
            text, error = call_cli(args.judge, messages, args.timeout, args.retries)
        else:
            text, error = call(args.base_url, args.api_key, args.judge, messages,
                               args.max_tokens, args.timeout, args.retries)
        record = {
            "candidate_id": cand["candidate_id"],
            "cite_key": cand["cite_key"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "pass_name": args.pass_name,
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
    print(f"{args.judge_name}[{args.pass_name}]: wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
