#!/usr/bin/env python3
"""Does an explicit abstention option recover the verdict?

The manuscript concludes that judges "do not report silence, they resolve it".
A reviewer observed that the paper proves the opposite mechanism on a
neighbouring label -- adding a fourth provenance option moved the
asserted-no-number class from 0% to 100% recovery -- and then never runs the
analogous experiment on the failing judgment.  Without it, the paper's central
causal claim is confounded with prompt design: judges may be unable to *report*
underdetermination because the deployed instrument gives them no way to say it.

This script runs that experiment.  The codebook is the deployed one with two
changes and no others:

1.  a fourth verdict value, ``not_determinable_from_text``, described in the
    same register as the other three, and
2.  an instruction to prefer it under uncertainty rather than to guess.

Everything else -- coordinates, eligibility, worked examples, output schema,
context window, judges, item order -- is byte-identical to the deployed run, so
the contrast is the option and the instruction, not the instrument.

The same arm is run on the constructed benchmark, where a reference exists, so
the answer is not only "do they abstain more" but "do they abstain correctly".
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from code_cross_paper_frame import CODEBOOK, call, context_for, extract_json  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
ORDER_SEED = 2026072811  # identical to the deployed census, so the order matches

_OLD_RULE = """\
3. Otherwise the gap is undefined: verdict "undefined". Do NOT invent a
   replacement number. A number computed by mixing two unmatched settings is
   not a repair."""

_NEW_RULE = """\
3. Otherwise, if the text STATES a threatening mismatch that nothing repairs,
   the gap is undefined: verdict "undefined". Do NOT invent a replacement
   number. A number computed by mixing two unmatched settings is not a repair.
4. Otherwise -- if the text is SILENT on a coordinate that would decide the
   comparison, so that you cannot tell whether the two sides match on it --
   the correct answer is that the passage does not say: verdict
   "not_determinable_from_text".

CHOOSING BETWEEN 3 AND 4. "undefined" is a finding about the comparison: the
text told you the two sides differ in a way nothing repairs. "not_
determinable_from_text" is a finding about the text: it never told you. Prefer
"not_determinable_from_text" whenever you would otherwise have to assume what a
coordinate's value is. Assuming is the error this codebook exists to prevent;
answering "the passage does not say" is never penalised."""

_OLD_SCHEMA = ' "verdict": "survives"|"narrows"|"undefined",'
_NEW_SCHEMA = (
    ' "verdict": "survives"|"narrows"|"undefined"|"not_determinable_from_text",'
)
_OLD_TAIL = (
    'If eligible is false, set every other field to "" or "not_determinable" and\n'
    'verdict to "undefined".'
)
_NEW_TAIL = (
    'If eligible is false, set every other field to "" or "not_determinable" and\n'
    'verdict to "undefined".'
)


def abstention_codebook() -> str:
    text = CODEBOOK
    for old, new in ((_OLD_RULE, _NEW_RULE), (_OLD_SCHEMA, _NEW_SCHEMA), (_OLD_TAIL, _NEW_TAIL)):
        if old not in text:
            raise SystemExit(f"codebook anchor not found, refusing to run:\n{old[:70]}")
        text = text.replace(old, new)
    return text


_LOCK = threading.Lock()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", required=True)
    parser.add_argument("--judge-name", required=True)
    parser.add_argument(
        "--candidates", type=Path, default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl"
    )
    parser.add_argument(
        "--out-dir", type=Path, default=SUPPLEMENT / "abstention_verdict_runs"
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=3000)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--context-lines", type=int, default=45)
    parser.add_argument(
        "--restrict-to",
        type=Path,
        default=SUPPLEMENT / "cross_paper_census_ledger.csv",
        help="code only these candidate ids (the eligible census population)",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--print-codebook", action="store_true")
    args = parser.parse_args()

    codebook = abstention_codebook()
    if args.print_codebook:
        print(codebook)
        return 0

    candidates = [
        json.loads(line)
        for line in args.candidates.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    random.Random(ORDER_SEED).shuffle(candidates)

    if args.restrict_to and args.restrict_to.exists():
        import csv as _csv

        keep = {
            row["candidate_id"]
            for row in _csv.DictReader(args.restrict_to.open(encoding="utf-8"))
        }
        candidates = [c for c in candidates if c["candidate_id"] in keep]
    if args.limit:
        candidates = candidates[: args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.judge_name}.jsonl"
    done: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("parsed"):
                    done.add(rec["candidate_id"])
    pending = [c for c in candidates if c["candidate_id"] not in done]
    print(f"{args.judge_name}: {len(pending)} pending of {len(candidates)}", flush=True)
    if not pending:
        return 0

    handle = out_path.open("a", encoding="utf-8")
    progress = {"n": 0, "ok": 0}
    started = time.time()

    def work(candidate: dict) -> None:
        context = context_for(candidate, args.context_lines)
        user = (
            f"SOURCE FILE: {candidate['source_file']}\n"
            f"FOCUS LINE RANGE: {candidate['line_start']}-{candidate['line_end']}\n"
            f"SYSTEM NAMES DETECTED THAT ARE NOT THIS PAPER'S OWN: "
            f"{', '.join(candidate['external_systems'])}\n\n"
            f"FOCUS PASSAGE (the juxtaposition to code):\n<<<\n"
            f"{candidate['window_text']}\n>>>\n\n"
            f"SURROUNDING CONTEXT (use it to determine the coordinates; the "
            f"focus passage is repeated inside it):\n<<<\n{context}\n>>>\n"
        )
        text, error = call(
            args.base_url,
            args.api_key,
            args.judge,
            [
                {"role": "system", "content": codebook},
                {"role": "user", "content": user},
            ],
            args.max_tokens,
            args.timeout,
            args.retries,
        )
        parsed = extract_json(text)
        record = {
            "candidate_id": candidate["candidate_id"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "arm": "abstention",
            "source_file": candidate["source_file"],
            "cite_key": candidate["cite_key"],
            "line_start": candidate["line_start"],
            "line_end": candidate["line_end"],
            "window_sha256": candidate["window_sha256"],
            "raw_response": text,
            "api_error": error,
            "parsed": parsed,
        }
        with _LOCK:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            progress["n"] += 1
            progress["ok"] += 1 if parsed else 0
            if progress["n"] % 50 == 0:
                rate = progress["n"] / max(1e-9, time.time() - started)
                print(
                    f"  {args.judge_name} {progress['n']}/{len(pending)} "
                    f"parsed={progress['ok']} {rate:.2f}/s",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, pending))
    handle.close()
    print(f"done {args.judge_name}: {progress['ok']}/{progress['n']} parsed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
