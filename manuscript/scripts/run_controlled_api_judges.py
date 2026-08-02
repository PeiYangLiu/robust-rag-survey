#!/usr/bin/env python3
"""Run one API-served (frontier) model on the v2 controlled consequence benchmark.

This mirrors ``run_controlled_model_judges_v2.py`` exactly: the same benchmark,
the same three arms, the same four paraphrases, the same output instruction, the
same decision parser and the same regret accounting.  The only difference is
that generation is served by an OpenAI-compatible HTTP endpoint instead of a
local checkpoint, so that the model population sampled by the experiment is not
restricted to 7--14B open checkpoints.

Reviewer point addressed: "in practice the models actually used as claim judges
are frontier models, not 7--14B open checkpoints".

Decoding is greedy (``temperature=0``) wherever the endpoint honours it.  Every
raw response is written out, so the released artifact supports reanalysis.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import urllib.error
import urllib.request

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from run_controlled_model_judges_v2 import (  # noqa: E402
    ARMS,
    ORDER_SEED,
    PARAPHRASES,
    _OUTPUT_INSTRUCTION,
    decision_regret,
    parse_decision,
    read_jsonl,
    sha256_text,
    system_prompt,
)

REPO = SCRIPTS.resolve().parents[1]
DEFAULT_BENCHMARK = (
    REPO / "manuscript" / "supplement" / "controlled_claim_audit_benchmark_v2.jsonl"
)

_PRINT_LOCK = threading.Lock()


def call_endpoint(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_new_tokens: int,
    timeout: float,
    retries: int,
) -> tuple[str, dict[str, object]]:
    """POST one chat completion, retrying on transport and rate-limit errors."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": max_new_tokens,
        "n": 1,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Initiator": "agent",
        "Copilot-Integration-Id": "vscode-chat",
        "Editor-Version": "vscode/1.99.0",
    }
    last_error = ""
    for attempt in range(retries):
        request = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            choice = parsed["choices"][0]
            text = choice.get("message", {}).get("content") or ""
            meta = {
                "finish_reason": choice.get("finish_reason", ""),
                "response_model": parsed.get("model", ""),
                "attempts": attempt + 1,
            }
            return text, meta
        except urllib.error.HTTPError as error:  # noqa: PERF203
            detail = error.read().decode("utf-8", "replace")[:200]
            last_error = f"HTTP {error.code}: {detail}"
            if error.code in (400, 404) and "max_tokens" in detail:
                payload.pop("max_tokens", None)
                body = json.dumps(payload).encode("utf-8")
            if error.code in (400, 404) and "temperature" in detail:
                payload.pop("temperature", None)
                payload.pop("top_p", None)
                body = json.dumps(payload).encode("utf-8")
            time.sleep(min(2.0 * (attempt + 1), 30.0))
        except Exception as error:  # noqa: BLE001
            last_error = f"{type(error).__name__}: {error}"
            time.sleep(min(2.0 * (attempt + 1), 30.0))
    return "", {"finish_reason": "error", "error": last_error, "attempts": retries}


def run(args: argparse.Namespace) -> tuple[list[dict[str, object]], dict[str, object]]:
    benchmark = read_jsonl(args.benchmark)
    if not benchmark:
        raise ValueError("empty benchmark")

    work = []
    for row in benchmark:
        for arm in ARMS:
            for paraphrase in PARAPHRASES:
                messages = [
                    {"role": "system", "content": system_prompt(arm, paraphrase)},
                    {
                        "role": "user",
                        "content": str(row["vignette"])
                        + _OUTPUT_INSTRUCTION[paraphrase],
                    },
                ]
                prompt_hash = sha256_text(
                    json.dumps(messages, ensure_ascii=True, sort_keys=True)
                )
                work.append((row, arm, paraphrase, messages, prompt_hash))
    random.Random(ORDER_SEED).shuffle(work)

    done = {"n": 0}
    started = time.time()

    def one(job):
        row, arm, paraphrase, messages, prompt_hash = job
        text, meta = call_endpoint(
            args.base_url,
            args.api_key,
            args.model,
            messages,
            args.max_new_tokens,
            args.timeout,
            args.retries,
        )
        decision = parse_decision(text)
        chosen_loss, regret = decision_regret(row, decision)
        with _PRINT_LOCK:
            done["n"] += 1
            if args.progress and done["n"] % 200 == 0:
                rate = done["n"] / max(time.time() - started, 1e-9)
                print(
                    json.dumps(
                        {
                            "model": args.model,
                            "progress": done["n"],
                            "total": len(work),
                            "per_second": round(rate, 2),
                            "eta_min": round((len(work) - done["n"]) / rate / 60, 1),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
        return {
            "schema_version": "controlled-model-judge-output-v2",
            "model": args.model,
            "serving": "openai_compatible_api",
            "endpoint_response_model": meta.get("response_model", ""),
            "item_id": row["item_id"],
            "pair_id": row["pair_id"],
            "stratum": row["stratum"],
            "subtype": row["subtype"],
            "variant": row["variant"],
            "template_family": row["template_family"],
            "benchmark_record_sha256": row["record_sha256"],
            "arm": arm,
            "paraphrase": paraphrase,
            "prompt_sha256": prompt_hash,
            "raw_output": text,
            "finish_reason": meta.get("finish_reason", ""),
            "api_attempts": meta.get("attempts", 1),
            "api_error": meta.get("error", ""),
            "parsed_decision": decision,
            "target_decision": row["target_decision"],
            "exact_agreement": int(decision == row["target_decision"]),
            "chosen_loss": chosen_loss,
            "optimal_loss": min(
                float(value) for value in row["decision_losses"].values()
            ),
            "regret": regret,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        output_rows = list(pool.map(one, work))

    output_rows.sort(
        key=lambda row: (str(row["item_id"]), str(row["arm"]), str(row["paraphrase"]))
    )
    expected = {
        (str(row["item_id"]), arm, paraphrase)
        for row in benchmark
        for arm in ARMS
        for paraphrase in PARAPHRASES
    }
    actual = {
        (str(row["item_id"]), str(row["arm"]), str(row["paraphrase"]))
        for row in output_rows
    }
    if actual != expected:
        raise ValueError("model output does not cover every item/arm/paraphrase cell")

    summary = {
        "schema_version": "controlled-model-judge-summary-v2",
        "model": args.model,
        "serving": "openai_compatible_api",
        "records": len(output_rows),
        "items": len(benchmark),
        "arms": list(ARMS),
        "paraphrases": list(PARAPHRASES),
        "parse_failures": sum(
            row["parsed_decision"] == "parse_failure" for row in output_rows
        ),
        "api_errors": sum(1 for row in output_rows if row["api_error"]),
        "decision_distribution": dict(
            Counter(str(row["parsed_decision"]) for row in output_rows)
        ),
        "order_seed": ORDER_SEED,
        "decoding": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": args.max_new_tokens,
            "workers": args.workers,
        },
        "wall_clock_seconds": round(time.time() - started, 1),
    }
    return output_rows, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument(
        "--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1")
    )
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--max-new-tokens", type=int, default=400)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--limit-items", type=int, default=0)
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit_items:
        rows = read_jsonl(args.benchmark)[: args.limit_items]
        smoke = args.output.parent / f"smoke_benchmark_{args.limit_items}.jsonl"
        smoke.parent.mkdir(parents=True, exist_ok=True)
        smoke.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        args.benchmark = smoke
    output_rows, summary = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in output_rows) + "\n",
        encoding="utf-8",
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
