#!/usr/bin/env python3
"""Second-stage classification: is the other paper's number transported or re-run?

The first-stage census showed that "cross-paper juxtaposition" covers two
populations that must not be pooled.

*   **Re-implemented.**  The other system was re-run inside this paper's own
    corpus, retriever, generator and metric, and the number in the table is
    this paper's measurement of that system.  These are within-harness
    contrasts wearing a cross-paper label, and they should usually survive a
    coordinate audit -- the whole point of a shared harness is that the
    coordinates match.
*   **Transported.**  The number is copied from the other paper and placed
    beside a number measured here (or beside another paper's number by a
    survey).  Only these are exposed to the failure mode this paper is about.

Pooling them makes the audit look either vacuous or alarmist depending on the
mixture, so we classify every eligible candidate with the same three
independent judges and report the two populations separately.

Consumes the eligible candidates identified by ``analyze_cross_paper_census.py``
and writes one JSONL per judge to ``supplement/cross_paper_provenance/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from code_cross_paper_frame import call, context_for, extract_json  # noqa: E402

MANUSCRIPT = SCRIPTS.parents[0]
REPO = SCRIPTS.parents[1]
SUPPLEMENT = MANUSCRIPT / "supplement"
ORDER_SEED = 2026072812

PROMPT = """\
You are told that a passage from one paper places a reported result beside a
result associated with a DIFFERENT paper's system. Decide how that other
number was obtained. Use only the text shown.

"reimplemented" - the other system was run by THIS paper, inside this paper's
   own corpus, retriever, generator and metric. Signals: the other system
   appears as a baseline row in this paper's own results table; the text says
   "we implement", "we reproduce", "we re-run", "using our setup", "under the
   same backbone/retriever/dataset"; all compared numbers share this paper's
   experimental description; the other system is evaluated on datasets or
   models the original paper did not use.
"transported" - the number was copied from the other paper and is quoted here.
   Signals: the text cites the other paper for the value; the value is
   introduced as "reported", "as reported in", "achieves ... in their paper";
   the numbers are attached to the other paper's own datasets or backbone; a
   survey lists headline numbers from several papers side by side.
"unclear" - the passage genuinely does not say which of the two it is.

Do not guess from plausibility. If the passage does not distinguish them,
answer "unclear".

Return STRICT JSON only:
{"rationale": str,
 "provenance": "reimplemented"|"transported"|"unclear",
 "evidence_quote": str,
 "confidence": "high"|"medium"|"low"}
"rationale" at most 60 words. "evidence_quote" copied verbatim from the passage.
"""

_LOCK = threading.Lock()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", required=True)
    parser.add_argument("--judge-name", required=True)
    parser.add_argument(
        "--ledger", type=Path, default=SUPPLEMENT / "cross_paper_census_ledger.csv"
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=SUPPLEMENT / "cross_paper_provenance"
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--context-lines", type=int, default=45)
    args = parser.parse_args()

    windows = {}
    for line in args.candidates.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            windows[row["candidate_id"]] = row

    eligible = [
        row["candidate_id"]
        for row in csv.DictReader(args.ledger.open(encoding="utf-8"))
        if row["candidate_id"] in windows
    ]
    random.Random(ORDER_SEED).shuffle(eligible)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.judge_name}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["candidate_id"])
    pending = [cid for cid in eligible if cid not in done]
    print(f"{args.judge_name}: {len(pending)} pending of {len(eligible)}", flush=True)

    handle = out_path.open("a", encoding="utf-8")
    progress = {"n": 0}
    started = time.time()

    def work(cid: str):
        candidate = windows[cid]
        context = context_for(candidate, args.context_lines)
        user = (
            f"SOURCE FILE: {candidate['source_file']}\n"
            f"FOCUS LINE RANGE: {candidate['line_start']}-{candidate['line_end']}\n"
            f"OTHER-PAPER SYSTEMS DETECTED: "
            f"{', '.join(candidate['external_systems'])}\n\n"
            f"FOCUS PASSAGE:\n<<<\n{candidate['window_text']}\n>>>\n\n"
            f"SURROUNDING CONTEXT:\n<<<\n{context}\n>>>\n"
        )
        text, error = call(
            args.base_url,
            args.api_key,
            args.judge,
            [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}],
            args.max_tokens,
            args.timeout,
            args.retries,
        )
        record = {
            "candidate_id": cid,
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "cite_key": candidate["cite_key"],
            "raw_response": text,
            "api_error": error,
            "parsed": extract_json(text),
        }
        with _LOCK:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            progress["n"] += 1
            if progress["n"] % 25 == 0:
                rate = progress["n"] / max(time.time() - started, 1e-9)
                print(
                    json.dumps(
                        {
                            "judge": args.judge_name,
                            "done": progress["n"],
                            "total": len(pending),
                            "per_second": round(rate, 2),
                        }
                    ),
                    flush=True,
                )
        return record

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, pending))
    handle.close()
    print(f"{args.judge_name}: wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
