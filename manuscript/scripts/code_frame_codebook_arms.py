#!/usr/bin/env python3
"""Codebook ablation for the cross-paper census (reviewer W4).

The submitted census asks every judge to code five coordinates and then to
return a verdict derived from them.  A reviewer observed that this design
cannot separate two explanations of the low verdict agreement:

  (a) the adjudication task is genuinely ill-posed, or
  (b) the *instrument* is under-specified -- in particular C3 is labelled
      "mismatch" on 99.6% of items by construction, because comparing two
      different systems means the intervention differs, so a coordinate that is
      constant cannot carry information and may instead inject noise.

This script re-codes the identical 1,703-window frame under two reduced
codebooks, holding the judge, the passage, the context window, the ordering
seed and the output schema fixed.  Only the instrument changes:

``c1c4``   the judge codes *only* C1 (evidence state) and C4 (outcome/unit) --
           the two coordinates that are not degenerate across systems -- and
           returns the verdict from those two alone.
``direct`` the judge codes *no* coordinates and answers the comparability
           question directly in one step.

Together with the released five-coordinate arm this gives a within-judge,
within-item, three-arm design whose contrast identifies how much of the verdict
unreliability is attributable to the instrument.

Outputs one JSONL per judge and arm under
``supplement/cross_paper_coding_arms/<arm>/``.
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
ORDER_SEED = 2026072811  # identical to code_cross_paper_frame.py

_SHARED_TAIL = """\
ELIGIBILITY
eligible=true only if the text juxtaposes two reported results such that a
reader would rank them, AND at least one number is attributed to a DIFFERENT
paper than this file (a baseline row credited to another paper, a number
credited to another system, or a survey grouping two systems under one label).
eligible=false for: within-paper ablations only, method descriptions without a
comparison, related-work prose without numbers, reference lists, and windows
whose numbers are not results (dataset sizes, hyperparameters, page or equation
numbers).
"""

CODEBOOK_C1C4 = """\
You are coding whether two reported robust-RAG results are comparable.
Work only from the text you are shown. Never use outside knowledge of a paper.

You will judge exactly TWO coordinates. Ignore every other difference between
the two sides, including the fact that they are different methods or systems:
that difference is what a comparison is for and it never by itself makes a
comparison undefined.

C1 evidence state - the evidence condition measured: corpus snapshot, retriever,
   distractor or conflict construction, noise ratio, number of retrieved
   passages, whether a gold passage is present, and whether the condition is
   irrelevant, insufficient, conflicting, stale, weakly sourced or malicious.
C4 outcome and unit - the measured quantity and its unit: exact match vs
   substring accuracy vs attack success rate vs retrieval hit rate vs certified
   accuracy; per-question vs per-response vs per-span; and whether the two sides
   measure the same objective at all.

HOW TO LABEL EACH COORDINATE
"match"            - the text shows the two sides agree on this coordinate.
"mismatch"         - the text shows they differ on this coordinate.
"not_determinable" - the text does not say. Use this only when the text is
                     genuinely silent; do not use it as a hedge.

DECISION RULE (apply exactly, in this order)
1. If C1 and C4 both match, the quoted gap stands: verdict "survives".
2. Otherwise, if the text reports an operating point at the other side's
   setting for the mismatched coordinate, or the comparison remains valid on a
   strict subset (one dataset, one metric, one budget), re-read it there and
   report that value: verdict "narrows".
3. Otherwise the gap is undefined: verdict "undefined". Do NOT invent a
   replacement number. A number computed by mixing two unmatched settings is
   not a repair.

WORKED EXAMPLES (from a source-verified ledger; follow this style)
(a) A paper reports its own 61.8% on PopQA next to another paper's 54.9% on
    PopQA, same backbone, same retriever, same metric. Only the method differs.
    -> c1 match, c4 match, verdict "survives".
(b) A defence reports a rate measured with one malicious passage in the
    retrieved context beside an attack rate measured with five injected texts,
    and the attacking paper also reports 0.48 at a one-passage budget.
    -> c1 mismatch (evidence condition), verdict "narrows", matched_number
    "0.48 at a one-passage budget".
(c) An attack reporting answer-level success is placed beside an attack
    reporting retrieval hit rate.
    -> c4 mismatch, and since no common unit exists, verdict "undefined",
    matched_number "not_recoverable_from_text".

""" + _SHARED_TAIL + """
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
 "c4": "match"|"mismatch"|"not_determinable",
 "verdict": "survives"|"narrows"|"undefined",
 "matched_number": str,
 "evidence_quote": str,
 "confidence": "high"|"medium"|"low"}
If eligible is false, set every other field to "" or "not_determinable" and
verdict to "undefined".
"rationale" must be at most 120 words and must name which of C1 and C4 you
could determine from the text.
evidence_quote MUST be copied verbatim from the passage you were shown.
"""

CODEBOOK_DIRECT = """\
You are coding whether two reported robust-RAG results are comparable.
Work only from the text you are shown. Never use outside knowledge of a paper.

Answer the comparability question directly. Do not decompose it into a schema.

THE QUESTION
When this passage places two numbers side by side, does the gap between them
answer a single well-defined question, so that a reader may legitimately rank
the two systems by those two numbers?

The two sides being different methods is exactly what a comparison is for and
never by itself makes the comparison undefined. What does threaten it is that
the two numbers were produced under conditions that make the gap
uninterpretable -- for example a different evidence condition, a different
attacker budget or objective, a different measured quantity or unit, a
different evaluation population, or a different action set and cost structure.

VERDICTS
"survives"  - the quoted gap stands as reported; a reader may rank the two
              systems by these two numbers.
"narrows"   - the gap as quoted does not stand, but the text reports a value at
              a common operating point, or the comparison remains valid on a
              strict subset (one dataset, one metric, one budget). Report that
              value in matched_number.
"undefined" - no common operating point is available in the text, so the two
              numbers do not answer one question. Do NOT invent a replacement
              number. A number computed by mixing two unmatched settings is not
              a repair; set matched_number to "not_recoverable_from_text".

WORKED EXAMPLES (from a source-verified ledger; follow this style)
(a) A paper reports its own 61.8% on PopQA next to another paper's 54.9% on
    PopQA, same backbone, same retriever, same metric. -> "survives".
(b) A defence reports a rate at one malicious passage in the retrieved context
    beside an attack rate measured with five injected texts, and the attacking
    paper also reports 0.48 at a one-passage budget. -> "narrows",
    matched_number "0.48 at a one-passage budget".
(c) An attack reporting answer-level success is placed beside an attack
    reporting retrieval hit rate. -> "undefined", matched_number
    "not_recoverable_from_text".

""" + _SHARED_TAIL + """
OUTPUT
Return STRICT JSON only, no prose outside the object, with exactly these keys
and with "rationale" written FIRST, before you commit to any label:
{"rationale": str,
 "eligible": bool,
 "comparison_claim": str,
 "side_a": {"system": str, "number": str, "metric": str, "dataset": str, "model": str},
 "side_b": {"system": str, "number": str, "metric": str, "dataset": str, "model": str},
 "naive_gap": str,
 "verdict": "survives"|"narrows"|"undefined",
 "matched_number": str,
 "evidence_quote": str,
 "confidence": "high"|"medium"|"low"}
If eligible is false, set every other field to "" and verdict to "undefined".
"rationale" must be at most 120 words and must name what in the text decided
the verdict.
evidence_quote MUST be copied verbatim from the passage you were shown.
"""

ARMS = {"c1c4": CODEBOOK_C1C4, "direct": CODEBOOK_DIRECT}

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

    Identical to ``code_cross_paper_frame.py``: the local proxy injects
    ``max_tokens`` into ``/chat/completions``, which the gpt-5.x reasoning
    checkpoints reject, so the OpenAI cell is served over the vendor CLI. The
    prompt is byte-identical across the two transports.
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
    parser.add_argument("--judge", required=True)
    parser.add_argument("--judge-name", required=True)
    parser.add_argument("--arm", required=True, choices=sorted(ARMS))
    parser.add_argument(
        "--candidates",
        type=Path,
        default=SUPPLEMENT / "cross_paper_frame_candidates.jsonl",
    )
    parser.add_argument(
        "--out-root", type=Path, default=SUPPLEMENT / "cross_paper_coding_arms"
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=1600)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--backend", choices=("http", "cli"), default="http")
    parser.add_argument("--context-lines", type=int, default=45)
    args = parser.parse_args()

    candidates = [
        json.loads(line)
        for line in args.candidates.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    random.Random(ORDER_SEED).shuffle(candidates)
    if args.limit:
        candidates = candidates[: args.limit]

    out_dir = args.out_root / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.judge_name}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("parsed"):
                done.add(row["candidate_id"])
    pending = [c for c in candidates if c["candidate_id"] not in done]
    print(
        f"{args.judge_name}[{args.arm}]: {len(pending)} pending of {len(candidates)}",
        flush=True,
    )

    codebook = ARMS[args.arm]
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
        parsed = extract_json(text)
        record = {
            "candidate_id": candidate["candidate_id"],
            "judge_name": args.judge_name,
            "judge_model": args.judge,
            "arm": args.arm,
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
            if progress["n"] % 100 == 0:
                rate = progress["n"] / max(time.time() - started, 1e-9)
                print(
                    json.dumps(
                        {
                            "judge": args.judge_name,
                            "arm": args.arm,
                            "done": progress["n"],
                            "total": len(pending),
                            "per_second": round(rate, 3),
                        }
                    ),
                    flush=True,
                )
        return record

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, pending))
    handle.close()
    print(f"{args.judge_name}[{args.arm}]: wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
