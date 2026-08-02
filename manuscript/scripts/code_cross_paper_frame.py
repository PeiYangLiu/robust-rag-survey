#!/usr/bin/env python3
"""Independently code every candidate cross-paper comparison in the frame.

The previous ledger had twelve author-chosen, single-coded cases.  This script
replaces that with a census over the reproducible frame built by
``build_cross_paper_frame.py``, coded independently by three judges drawn from
three different model developers, so that inter-coder agreement can be reported
rather than asserted.

Each judge sees exactly the same input: the verbatim window, its file, its line
range, and the coordinate codebook.  Judges never see one another's output, and
the run order is shuffled by a fixed seed so that no judge sees the frame in
frame order.  Every judge answers in one pass:

*   ``eligible``          -- is this a juxtaposition of two results a reader
                             would compare, with at least one number attributed
                             to a *different* paper?
*   ``side_a`` / ``side_b`` -- system, verbatim number, metric, dataset, model.
*   ``c1``..``c5``        -- ``match`` / ``mismatch`` / ``not_determinable``.
*   ``verdict``           -- ``survives`` / ``narrows`` / ``undefined``.
*   ``matched_number``    -- the coordinate-matched value or
                             ``not_recoverable_from_text``.
*   ``evidence_quote``    -- a verbatim substring of the window supporting the
                             coding, which is checked mechanically downstream.

Outputs one JSONL per judge under ``supplement/cross_paper_coding/``.
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

import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[2]
SUPPLEMENT = REPO / "manuscript" / "supplement"
ORDER_SEED = 2026072811

CODEBOOK = """\
You are coding whether two reported robust-RAG results are comparable.
Work only from the text you are shown. Never use outside knowledge of a paper.

COORDINATES
C1 evidence state - the evidence condition measured: corpus snapshot, retriever,
   distractor or conflict construction, noise ratio, number of retrieved
   passages, whether a gold passage is present, and whether the condition is
   irrelevant, insufficient, conflicting, stale, weakly sourced or malicious.
C2 origin / capability - how the condition arose. Natural retrieval error versus
   an adversary, and for an adversary: corpus write access, query access,
   knowledge of retriever or generator, injection budget, whether that budget
   counts documents INJECTED into the corpus or documents RETRIEVED into the
   context (these are different budgets), persistence, and whether the metric is
   computed over all queries or only over triggered queries.
C3 intervention - the method or system change being evaluated.
C4 outcome and unit - the measured quantity and its unit: exact match vs
   substring accuracy vs attack success rate vs retrieval hit rate vs certified
   accuracy; per-question vs per-response vs per-span; and whether the two sides
   measure the same objective at all.
C5 policy / utility - the action set, whether abstention or deferral is allowed,
   the stakes, and every stated error, abstention, compute or follow-up cost.

HOW TO LABEL EACH COORDINATE
"match"            - the text shows the two sides agree on this coordinate.
"mismatch"         - the text shows they differ on this coordinate.
"not_determinable" - the text does not say. Use this only when the text is
                     genuinely silent; do not use it as a hedge.

IMPORTANT ABOUT C3. Two systems being different methods is exactly what a
comparison is for. Label C3 "mismatch" whenever the two sides apply different
interventions, which is usual; a C3 mismatch on its own NEVER makes a comparison
undefined. Only C1, C2, C4 and C5 mismatches threaten comparability.

DECISION RULE (apply exactly, in this order)
1. If C1, C2, C4 and C5 all match (C3 may differ), the quoted gap stands:
   verdict "survives".
2. Otherwise, if the text reports an operating point at the other side's
   setting for every threatening coordinate, or the comparison remains valid on
   a strict subset (one dataset, one metric, one budget), re-read it there and
   report that value: verdict "narrows".
3. Otherwise the gap is undefined: verdict "undefined". Do NOT invent a
   replacement number. A number computed by mixing two unmatched settings is
   not a repair.

WORKED EXAMPLES (from a source-verified ledger; follow this style)
(a) A paper reports its own 61.8% on PopQA next to another paper's 54.9% on
    PopQA, same backbone, same retriever, same metric. Only the method differs.
    -> c1 match, c2 match, c3 mismatch, c4 match, c5 match, verdict "survives".
(b) A defence certifies accuracy against one malicious passage in the retrieved
    context and states that it "reduces attack success from 97%", where the 97%
    was measured with five injected texts. The attacking paper also reports 0.48
    at one malicious passage in the retrieved context.
    -> c2 mismatch (budget), verdict "narrows", matched_number "0.48 at a
    one-passage budget".
(c) An attack reporting answer-level success is placed beside an attack
    reporting retrieval hit rate.
    -> c4 mismatch, and since no common unit exists, verdict "undefined",
    matched_number "not_recoverable_from_text".

ELIGIBILITY
eligible=true only if the text juxtaposes two reported results such that a
reader would rank them, AND at least one number is attributed to a DIFFERENT
paper than this file (a baseline row credited to another paper, a number
credited to another system, or a survey grouping two systems under one label).
eligible=false for: within-paper ablations only, method descriptions without a
comparison, related-work prose without numbers, reference lists, and windows
whose numbers are not results (dataset sizes, hyperparameters, page or equation
numbers).

OUTPUT
Return STRICT JSON only, no prose outside the object, with exactly these keys
and with "rationale" written FIRST, before you commit to any label:
{"rationale": str,
 "eligible": bool,
 "comparison_claim": str,
 "side_a": {"system": str, "number": str, "metric": str, "dataset": str, "model": str},
 "side_b": {"system": str, "number": str, "metric": str, "dataset": str, "model": str},
 "naive_gap": str,
 "c1": "match"|"mismatch"|"not_determinable",
 "c2": "match"|"mismatch"|"not_determinable",
 "c3": "match"|"mismatch"|"not_determinable",
 "c4": "match"|"mismatch"|"not_determinable",
 "c5": "match"|"mismatch"|"not_determinable",
 "verdict": "survives"|"narrows"|"undefined",
 "matched_number": str,
 "evidence_quote": str,
 "confidence": "high"|"medium"|"low"}
If eligible is false, set every other field to "" or "not_determinable" and
verdict to "undefined".
"rationale" must be at most 120 words and must name which coordinates you could
determine from the text.
evidence_quote MUST be copied verbatim from the passage you were shown.
"""

_LOCK = threading.Lock()


def call(base_url, api_key, model, messages, max_tokens, timeout, retries):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Initiator": "agent",
        "Copilot-Integration-Id": "vscode-chat",
        "Editor-Version": "vscode/1.99.0",
    }
    body = json.dumps(payload).encode("utf-8")
    last = ""
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                base_url.rstrip("/") + "/chat/completions",
                data=body,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            return parsed["choices"][0].get("message", {}).get("content") or "", ""
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {error.code}: {detail}"
            if error.code == 400 and "max_tokens" in detail:
                payload["max_completion_tokens"] = payload.pop("max_tokens", max_tokens)
                body = json.dumps(payload).encode("utf-8")
                continue
            if error.code == 400 and "temperature" in detail:
                payload.pop("temperature", None)
                body = json.dumps(payload).encode("utf-8")
                continue
            time.sleep(min(2.0 * (attempt + 1), 25.0))
        except Exception as error:  # noqa: BLE001
            last = f"{type(error).__name__}: {error}"
            time.sleep(min(2.0 * (attempt + 1), 25.0))
    return "", last



def call_cli(model, messages, timeout, retries):
    """Judge backend that drives the Copilot CLI instead of the HTTP proxy.

    The local proxy unconditionally injects ``max_tokens`` into
    ``/chat/completions``, which the gpt-5.x reasoning models reject, and the
    gpt-4.x line shares an exhausted utility-model quota.  The CLI reaches the
    same checkpoints over a different transport, so the OpenAI cell of the
    tier-by-developer design can be filled without substituting a different
    developer for it.

    The prompt is assembled from exactly the same system and user messages the
    HTTP backend sends, so a judge served this way is answering the identical
    question in the identical codebook.
    """
    prompt = "\n\n".join(m["content"] for m in messages) + (
        "\n\nReturn ONLY the JSON object. Do not use any tools. Do not read or "
        "write files. Do not explain."
    )
    last = ""
    for attempt in range(retries):
        handle = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(prompt)
                handle = fh.name
            proc = subprocess.run(
                [
                    "copilot",
                    "-p",
                    f"@{handle}",
                    "--model",
                    model,
                    "--allow-all-tools",
                    "--no-color",
                    "--disable-builtin-mcps",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir(),
            )
            out = proc.stdout or ""
            # Strip the CLI's trailing usage banner.
            out = re.split(r"\n\s*(?:Changes|AI Credits|Tokens|Resume)\s", out)[0]
            if out.strip():
                return out, ""
            last = (proc.stderr or "empty response")[:300]
        except subprocess.TimeoutExpired:
            last = "cli timeout"
        except Exception as error:  # noqa: BLE001
            last = f"{type(error).__name__}: {error}"
        finally:
            if handle:
                try:
                    os.unlink(handle)
                except OSError:
                    pass
        time.sleep(min(3.0 * (attempt + 1), 30.0))
    return "", last


_TEXT_CACHE: dict[str, list[str]] = {}
_TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"


def context_for(candidate: dict, context_lines: int) -> str:
    """Return the focus window widened by ``context_lines`` on each side."""
    name = candidate["source_file"]
    if name not in _TEXT_CACHE:
        path = _TEXT_DIR / name
        _TEXT_CACHE[name] = (
            path.read_text(encoding="utf-8", errors="replace").splitlines()
            if path.exists()
            else []
        )
    lines = _TEXT_CACHE[name]
    if not lines:
        return candidate["window_text"]
    lo = max(0, candidate["line_start"] - 1 - context_lines)
    hi = min(len(lines), candidate["line_end"] + context_lines)
    return "\n".join(lines[lo:hi])


FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    match = FENCE.search(text)
    blob = match.group(1) if match else text
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(blob[start : end + 1])
    except Exception:  # noqa: BLE001
        return None
    return value if isinstance(value, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", required=True, help="API model id acting as coder")
    parser.add_argument("--judge-name", required=True, help="short label, e.g. coderA")
    parser.add_argument(
        "--candidates", type=Path, default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl"
    )
    parser.add_argument("--out-dir", type=Path, default=SUPPLEMENT / "cross_paper_coding")
    parser.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--backend",
        choices=("http", "cli"),
        default="http",
        help=(
            "how to reach the judge. 'http' uses the local OpenAI-compatible "
            "proxy; 'cli' drives the Copilot CLI, which reaches checkpoints "
            "the proxy cannot serve. The prompt is identical either way."
        ),
    )
    parser.add_argument("--context-lines", type=int, default=45)
    parser.add_argument(
        "--text-dir",
        type=Path,
        default=REPO / "manuscript" / "citation_audit" / "expanded_texts",
    )
    args = parser.parse_args()

    candidates = [
        json.loads(line)
        for line in args.candidates.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    random.Random(ORDER_SEED).shuffle(candidates)
    if args.limit:
        candidates = candidates[: args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.judge_name}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["candidate_id"])
    pending = [c for c in candidates if c["candidate_id"] not in done]
    print(f"{args.judge_name}: {len(pending)} pending of {len(candidates)}", flush=True)

    progress = {"n": 0}
    started = time.time()
    handle = out_path.open("a", encoding="utf-8")

    def work(candidate):
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
        messages = [
            {"role": "system", "content": CODEBOOK},
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
        parsed = extract_json(text)
        record = {
            "candidate_id": candidate["candidate_id"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
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
            if progress["n"] % 50 == 0:
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
