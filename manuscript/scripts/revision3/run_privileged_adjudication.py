#!/usr/bin/env python3
"""Adjudicate real frame windows under three information tiers.

The census codes each window from the window plus 45 lines of context, which is
what a screen can see.  That confounds two explanations of its negative result:
adjudication may be underdetermined *by the passage*, or it may be beyond the
judges.  Holding the judges, the codebook and the items fixed and varying only
the evidence separates them.

Tiers (identical prompt body, different attached documents):

``window``      the focus passage plus +-45 lines -- byte-identical to the
                deployed census condition.
``citing_full`` the entire extracted full text of the citing paper.
``both_full``   the citing paper's full text plus the full text of every cited
                paper whose system the window names and that we hold locally.

Two passes per tier, matching the deployed design exactly: the comparability
codebook (eligibility, five coordinates, verdict) and the provenance prompt.

Every answer must carry verbatim evidence, checked mechanically downstream
against the documents the judge was actually shown; at ``both_full`` a separate
quote from the cited paper is required, which is what makes the reference
*privileged* rather than merely better-read.

Outputs one JSONL per (judge, tier, pass) under
``supplement/privileged_reference_runs/``.
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
from code_cross_paper_frame import CODEBOOK, call, call_cli, extract_json  # noqa: E402
from classify_number_provenance import PROMPT as PROVENANCE_PROMPT  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SUPPLEMENT = REPO / "manuscript" / "supplement"
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"
ORDER_SEED = 2026073101

TIER_NOTE = {
    "window": (
        "You are shown the focus passage and the lines around it. This is all "
        "the evidence available."
    ),
    "citing_full": (
        "You are shown the focus passage and then the ENTIRE full text of the "
        "paper it comes from. Use the whole paper: the experimental setup, the "
        "table captions and the results discussion often state how a baseline "
        "number was obtained and under which conditions, even when the passage "
        "itself does not."
    ),
    "both_full": (
        "You are shown the focus passage, the ENTIRE full text of the paper it "
        "comes from, and the ENTIRE full text of the paper(s) that introduced "
        "the other system. Use both. A number is transported if it also appears "
        "in the other paper under the conditions that paper reports; it is "
        "re-implemented if this paper measured it under its own conditions. "
        "The other paper is also where the other side's evidence state, "
        "capability assumptions, outcome unit and action set are stated."
    ),
}

QUOTE_INSTRUCTION = {
    "window": (
        'Set "evidence_quote" to a string copied verbatim from the passage you '
        "were shown."
    ),
    "citing_full": (
        'Set "evidence_quote" to a string copied verbatim from the citing '
        "paper's full text."
    ),
    "both_full": (
        'Set "evidence_quote" to a string copied verbatim from the citing '
        'paper\'s full text, and "evidence_quote_cited" to a string copied '
        "verbatim from the other paper's full text. Both are checked "
        "mechanically; a paraphrase counts as a failure."
    ),
}

_LOCK = threading.Lock()
_TEXT_CACHE: dict[str, str] = {}


def full_text(cite_key: str, max_chars: int) -> str:
    if cite_key not in _TEXT_CACHE:
        path = TEXT_DIR / f"{cite_key}.txt"
        _TEXT_CACHE[cite_key] = (
            path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        )
    text = _TEXT_CACHE[cite_key]
    if max_chars and len(text) > max_chars:
        # Keep the opening (title, abstract, setup) and the closing (results,
        # appendix tables); drop the middle, which is related work and method
        # prose.  The elision is announced so a judge does not treat the join
        # as contiguous text, and quote checking runs against the full file.
        head = text[: int(max_chars * 0.6)]
        tail = text[-int(max_chars * 0.4) :]
        return head + "\n\n[... middle of paper elided for length ...]\n\n" + tail
    return text


def window_context(row: dict, context_lines: int) -> str:
    text = full_text(row["cite_key"], 0)
    lines = text.splitlines()
    if not lines:
        return row["window_text"]
    lo = max(0, row["line_start"] - 1 - context_lines)
    hi = min(len(lines), row["line_end"] + context_lines)
    return "\n".join(lines[lo:hi])


def build_user(row: dict, tier: str, context_lines: int, max_chars: int) -> str:
    header = (
        f"SOURCE FILE: {row['source_file']}\n"
        f"FOCUS LINE RANGE: {row['line_start']}-{row['line_end']}\n"
        f"SYSTEM NAMES DETECTED THAT ARE NOT THIS PAPER'S OWN: "
        f"{', '.join(row['external_systems'])}\n\n"
        f"EVIDENCE AVAILABLE TO YOU: {TIER_NOTE[tier]}\n\n"
        f"FOCUS PASSAGE (the juxtaposition to code):\n<<<\n{row['window_text']}\n>>>\n\n"
    )
    if tier == "window":
        body = (
            "SURROUNDING CONTEXT (use it to determine the coordinates; the "
            "focus passage is repeated inside it):\n<<<\n"
            f"{window_context(row, context_lines)}\n>>>\n"
        )
    else:
        body = (
            f"FULL TEXT OF THE CITING PAPER ({row['cite_key']}):\n<<<\n"
            f"{full_text(row['cite_key'], max_chars)}\n>>>\n"
        )
        if tier == "both_full":
            # Cap at the two most-referenced cited papers: three full texts is
            # already ~100k tokens and adding more trades evidence the judge
            # will use for evidence it will truncate.
            for cited in row["cited_papers"][:2]:
                body += (
                    f"\nFULL TEXT OF THE CITED PAPER {cited['cite_key']}, which "
                    f"introduced {', '.join(cited['systems'])}:\n<<<\n"
                    f"{full_text(cited['cite_key'], max_chars)}\n>>>\n"
                )
    return header + body + "\n" + QUOTE_INSTRUCTION[tier] + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", required=True)
    parser.add_argument("--judge-name", required=True)
    parser.add_argument("--tier", required=True, choices=sorted(TIER_NOTE))
    parser.add_argument("--pass-name", required=True, choices=("comparability", "provenance"))
    parser.add_argument(
        "--sample", type=Path, default=SUPPLEMENT / "privileged_reference_sample.jsonl"
    )
    parser.add_argument(
        "--out-dir", type=Path, default=SUPPLEMENT / "privileged_reference_runs"
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--context-lines", type=int, default=45)
    parser.add_argument(
        "--max-doc-chars",
        type=int,
        default=180_000,
        help="per-document character cap; 0 disables elision",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--backend",
        choices=("http", "cli"),
        default="http",
        help=(
            "how to reach the judge. 'http' uses the local proxy; 'cli' drives "
            "the vendor CLI, which reaches OpenAI checkpoints the proxy cannot "
            "serve because it injects max_tokens unconditionally. The prompt is "
            "assembled identically either way."
        ),
    )
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.sample.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.tier == "both_full":
        rows = [r for r in rows if r["cited_papers"]]
    random.Random(ORDER_SEED).shuffle(rows)
    if args.limit:
        rows = rows[: args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.pass_name}__{args.tier}__{args.judge_name}.jsonl"
    done: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("parsed"):
                    done.add(rec["candidate_id"])
    pending = [r for r in rows if r["candidate_id"] not in done]
    print(
        f"{args.pass_name}/{args.tier}/{args.judge_name}: {len(pending)} pending "
        f"of {len(rows)}",
        flush=True,
    )
    if not pending:
        return 0

    system = CODEBOOK if args.pass_name == "comparability" else PROVENANCE_PROMPT
    if args.pass_name == "provenance" and args.tier == "both_full":
        system = system.replace(
            'Return STRICT JSON only:\n{"rationale": str,\n "provenance":',
            'Return STRICT JSON only:\n{"rationale": str,\n "evidence_quote_cited": str,\n'
            ' "provenance":',
        )
    if args.pass_name == "comparability" and args.tier == "both_full":
        system = system.replace(
            ' "evidence_quote": str,\n', ' "evidence_quote": str,\n "evidence_quote_cited": str,\n'
        )

    handle = out_path.open("a", encoding="utf-8")
    progress = {"n": 0, "ok": 0}
    started = time.time()

    def work(row: dict) -> None:
        user = build_user(row, args.tier, args.context_lines, args.max_doc_chars)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
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
        parsed = extract_json(text)
        record = {
            "candidate_id": row["candidate_id"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "tier": args.tier,
            "pass_name": args.pass_name,
            "cite_key": row["cite_key"],
            "source_file": row["source_file"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "window_sha256": row["window_sha256"],
            "cited_papers": row["cited_papers"],
            "prompt_chars": len(user),
            "raw_response": text,
            "api_error": error,
            "parsed": parsed,
        }
        with _LOCK:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            progress["n"] += 1
            progress["ok"] += 1 if parsed else 0
            if progress["n"] % 20 == 0:
                rate = progress["n"] / max(1e-9, time.time() - started)
                print(
                    f"  {args.pass_name}/{args.tier}/{args.judge_name} "
                    f"{progress['n']}/{len(pending)} parsed={progress['ok']} "
                    f"{rate:.2f}/s",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, pending))
    handle.close()
    print(
        f"done {args.pass_name}/{args.tier}/{args.judge_name}: "
        f"{progress['ok']}/{progress['n']} parsed",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
