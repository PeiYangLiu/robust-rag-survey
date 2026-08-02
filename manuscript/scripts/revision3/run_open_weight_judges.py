#!/usr/bin/env python3
"""Run one open-weight checkpoint as a comparability judge.

Why this exists.  Every judge in the submitted version is a proprietary
checkpoint reached over a vendor API, and two of the paper's claims are weakened
by that.  The between-reviewer variance sigma_r is estimated from six judges,
so its own interval spans a factor of four and cannot carry a design
recommendation.  And the OpenAI cells are served over a different transport from
the rest, so the panel is not a single harness.  Open-weight checkpoints fix
both: they run under greedy decoding in one identical harness, their weights and
revisions are pinned, and there are enough of them to make the variance
component estimable.

Three tasks, all reusing prompts already released with the paper so that an open
judge answers exactly what the API judges answered:

``instrument``  the constructed comparability benchmark, whose reference verdict
                is fixed before any judge sees the item.  This is the arm that
                gives sigma_r a reference that is not a majority of the judges
                being measured.
``census``      the majority-eligible frame windows under the deployed codebook.
``abstention``  the same windows under the four-verdict codebook of the
                abstention arm.

Decoding is greedy with a fixed seed, and the model, revision and prompt hash
are written into every record.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANUSCRIPT = HERE.parents[1]
sys.path.insert(0, str(MANUSCRIPT / "scripts"))
sys.path.insert(0, str(HERE))

SUPPLEMENT = MANUSCRIPT / "supplement"
TEXT_DIR = MANUSCRIPT / "citation_audit" / "expanded_texts"
ORDER_SEED = 2026072811

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
        # Tolerate a truncated object by closing it, which is the common
        # failure when a model stops mid-JSON.
        try:
            value = json.loads(blob[start:] + "}")
        except Exception:  # noqa: BLE001
            return None
    return value if isinstance(value, dict) else None


# --------------------------------------------------------------------------
def load_pack(path: Path) -> list[dict]:
    """Read the pre-rendered prompt pack.

    The pack is built by ``build_open_judge_prompt_pack.py`` on the machine that
    holds the full-text corpus, so an open judge answers byte-identical prompts
    to the API judges and the job needs no paper corpus.
    """
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(json.loads(line))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--revision", default=None)
    ap.add_argument("--judge-name", required=True)
    ap.add_argument("--pack", type=Path, required=True)
    ap.add_argument("--task", required=True,
                    choices=("census", "abstention", "instrument"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--max-model-len", type=int, default=16384)
    ap.add_argument("--max-new-tokens", type=int, default=1400)
    ap.add_argument("--tensor-parallel-size", type=int, default=1)
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--trust-remote-code", action="store_true")
    args = ap.parse_args()

    records = load_pack(args.pack)
    if args.limit:
        records = records[: args.limit]
    print(f"[build] {args.task}: {len(records)} records from {args.pack}", flush=True)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        args.model, revision=args.revision, trust_remote_code=args.trust_remote_code
    )
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"
    prompts, kept, dropped = [], [], 0
    for rec in records:
        messages = [
            {"role": "system", "content": rec["system"]},
            {"role": "user", "content": rec["user"]},
        ]
        try:
            text = tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            text = tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:  # noqa: BLE001
            text = rec["system"] + "\n\n" + rec["user"]
        n_tok = len(tok(text, add_special_tokens=False)["input_ids"])
        if n_tok + args.max_new_tokens > args.max_model_len:
            dropped += 1
            continue
        prompts.append(text)
        kept.append(rec)
    print(f"[fit] {len(kept)}/{len(records)} prompts fit "
          f"(max_model_len={args.max_model_len}, dropped={dropped})", flush=True)

    # The scheduler exports torchrun-style variables even for a single-process
    # job. transformers 4.51 reads those as "you are in a distributed run" and
    # switches on tensor parallelism with a device mesh of size one, which makes
    # every shard the full tensor and puts the whole model on GPU 0. Clearing
    # them restores ordinary accelerate sharding across the visible GPUs.
    for var in ("RANK", "LOCAL_RANK", "WORLD_SIZE", "LOCAL_WORLD_SIZE",
                "MASTER_ADDR", "MASTER_PORT", "GROUP_RANK"):
        os.environ.pop(var, None)
    n_gpu = torch.cuda.device_count()
    print(f"[load] {args.model} across {n_gpu} visible GPU(s)", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        revision=args.revision,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        max_memory={i: "36GiB" for i in range(n_gpu)} if n_gpu > 1 else None,
        trust_remote_code=args.trust_remote_code,
    )
    model.eval()
    print(f"[load] done; device map spans {len(set(model.hf_device_map.values())) if hasattr(model,'hf_device_map') else 1} device(s)", flush=True)

    # Sort by length so each batch is roughly homogeneous, which keeps padding
    # waste down; the original order is restored before writing.
    order = sorted(range(len(prompts)), key=lambda i: len(prompts[i]))
    texts, generated = [prompts[i] for i in order], [None] * len(prompts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix(".partial.jsonl")
    ph = partial.open("w", encoding="utf-8")
    started = time.time()
    bs = args.batch_size
    done = 0
    while done < len(texts):
        chunk = texts[done : done + bs]
        try:
            enc = tok(chunk, return_tensors="pt", padding=True,
                      truncation=True, max_length=args.max_model_len).to(model.device)
            with torch.no_grad():
                out = model.generate(
                    **enc,
                    max_new_tokens=args.max_new_tokens,
                    do_sample=False,
                    temperature=None,
                    top_p=None,
                    top_k=None,
                    pad_token_id=tok.pad_token_id,
                )
            for j in range(len(chunk)):
                idx = order[done + j]
                text = tok.decode(
                    out[j][enc["input_ids"].shape[1]:], skip_special_tokens=True
                )
                generated[idx] = text
                rec = kept[idx]
                ph.write(json.dumps({
                    rec.get("id_field", "candidate_id"): rec["id"],
                    "judge_name": args.judge_name,
                    "judge_model": args.model,
                    "task": args.task,
                    "arm": args.task,
                    "prompt_sha256": rec.get("prompt_sha256"),
                    "meta": rec.get("meta"),
                    "raw_response": text,
                    "api_error": "",
                    "parsed": extract_json(text),
                }, sort_keys=True) + "\n")
            ph.flush()
            done += len(chunk)
            if done % 40 < bs:
                rate = done / max(1e-9, time.time() - started)
                print(f"[gen] {done}/{len(texts)} {rate:.2f}/s", flush=True)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            if bs == 1:
                print("[oom] skipping one item at batch size 1", flush=True)
                done += 1
                continue
            bs = max(1, bs // 2)
            print(f"[oom] reducing batch size to {bs}", flush=True)
    elapsed = time.time() - started

    class _O:
        def __init__(self, t): self.outputs = [type("x", (), {"text": t})()]
    outputs = [_O(t) for t in generated]

    ph.close()
    print(f"[gen] finished {len(texts)} in {elapsed:.0f}s", flush=True)
    generated = [g if g is not None else "" for g in generated]
    n_parsed = 0
    with args.output.open("w", encoding="utf-8") as fh:
        for rec, out in zip(kept, outputs):
            text = out.outputs[0].text if out.outputs else ""
            parsed = extract_json(text)
            n_parsed += int(bool(parsed))
            row = {
                rec.get("id_field", "candidate_id"): rec["id"],
                "judge_name": args.judge_name,
                "judge_model": args.model,
                "judge_revision": args.revision,
                "task": args.task,
                "arm": args.task,
                "prompt_sha256": rec.get("prompt_sha256"),
                "meta": rec.get("meta"),
                "raw_response": text,
                "api_error": "",
                "parsed": parsed,
            }
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "model": args.model,
        "revision": args.revision,
        "judge_name": args.judge_name,
        "task": args.task,
        "n_records": len(records),
        "n_prompts_fit": len(kept),
        "n_dropped_too_long": dropped,
        "n_parsed": n_parsed,
        "parse_rate": n_parsed / max(1, len(kept)),
        "seconds": elapsed,
        "max_model_len": args.max_model_len,
        "max_new_tokens": args.max_new_tokens,
        "decoding": "greedy (temperature 0)",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
