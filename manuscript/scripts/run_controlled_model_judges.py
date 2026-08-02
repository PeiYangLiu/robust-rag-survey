#!/usr/bin/env python3
"""Run one open model on both controlled claim-audit prompt conditions."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARK = (
    REPO
    / "manuscript"
    / "supplement"
    / "controlled_claim_audit_benchmark.jsonl"
)
ORDER_SEED = 2026072603
CONDITIONS = ("ablated", "full")
DECISIONS = ("deploy_A", "deploy_B", "defer")
SYSTEM_PROMPTS = {
    "ablated": (
        "You audit comparisons used for robust-RAG deployment decisions. "
        "Check source support, evidence state, intervention, measured outcome "
        "and unit, and ordinary experimental controls. Apply the stated "
        "deployment rule exactly."
    ),
    "full": (
        "You audit comparisons used for robust-RAG deployment decisions. "
        "Check source support, evidence state, intervention, measured outcome "
        "and unit, and ordinary experimental controls. Explicitly check how "
        "the evidence condition arose and the relevant access, knowledge, and "
        "budget capability. Also explicitly check available actions, coverage, "
        "stakes, and every stated error, abstention, compute, or follow-up cost. "
        "Do not transfer results outside an evaluated capability envelope. "
        "Apply the stated deployment rule exactly."
    ),
}
OUTPUT_INSTRUCTION = (
    "\nReturn exactly one action token and no explanation. Use deploy_A for "
    "System A, deploy_B for System B, or defer for commissioning the matched "
    "evaluation. Do not repeat the alternatives."
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSON at {path}:{line_number}")
        rows.append(value)
    return rows


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_decision(text: str) -> str:
    prefix_match = re.match(
        r"\s*(deploy_A|deploy_B|defer)", text, flags=re.IGNORECASE
    )
    if prefix_match:
        value = prefix_match.group(1).lower()
        return {
            "deploy_a": "deploy_A",
            "deploy_b": "deploy_B",
            "defer": "defer",
        }[value]
    json_match = re.search(
        r'["\']decision["\']\s*:\s*["\'](deploy_A|deploy_B|defer)["\']',
        text,
        flags=re.IGNORECASE,
    )
    if json_match:
        value = json_match.group(1)
        if value.lower() == "deploy_a":
            return "deploy_A"
        if value.lower() == "deploy_b":
            return "deploy_B"
        return "defer"
    tokens = re.findall(r"\b(deploy_A|deploy_B|defer)\b", text, re.IGNORECASE)
    normalized = {
        "deploy_a": "deploy_A",
        "deploy_b": "deploy_B",
        "defer": "defer",
    }
    unique = {normalized[token.lower()] for token in tokens}
    return unique.pop() if len(unique) == 1 else "parse_failure"


def make_prompt(
    tokenizer: object, condition: str, vignette: str
) -> tuple[str, str]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPTS[condition]},
        {"role": "user", "content": vignette + OUTPUT_INSTRUCTION},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    prompt_hash = sha256_text(
        json.dumps(messages, ensure_ascii=True, sort_keys=True)
    )
    return prompt, prompt_hash


def decision_regret(
    row: Mapping[str, object], decision: str
) -> tuple[float, float]:
    losses = {key: float(value) for key, value in row["decision_losses"].items()}
    optimum = min(losses.values())
    chosen_loss = (
        losses[decision]
        if decision in losses
        else max(losses.values())
    )
    return chosen_loss, chosen_loss - optimum


def run(args: argparse.Namespace) -> tuple[list[dict[str, object]], dict[str, object]]:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    benchmark = read_jsonl(args.benchmark)
    if len(benchmark) != 480:
        raise ValueError("controlled benchmark must contain 480 rows")

    tokenizer = AutoTokenizer.from_pretrained(
        args.model, revision=args.revision, trust_remote_code=args.trust_remote_code
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        revision=args.revision,
        torch_dtype="auto",
        device_map="auto",
        trust_remote_code=args.trust_remote_code,
    )
    model.eval()

    work = []
    for row in benchmark:
        for condition in CONDITIONS:
            prompt, prompt_hash = make_prompt(
                tokenizer, condition, str(row["vignette"])
            )
            work.append((row, condition, prompt, prompt_hash))
    random.Random(ORDER_SEED).shuffle(work)

    output_rows: list[dict[str, object]] = []
    for start in range(0, len(work), args.batch_size):
        batch = work[start : start + args.batch_size]
        encoded = tokenizer(
            [record[2] for record in batch],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=args.max_input_tokens,
        )
        encoded = {key: value.to(model.device) for key, value in encoded.items()}
        input_length = encoded["input_ids"].shape[1]
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                do_sample=False,
                max_new_tokens=args.max_new_tokens,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        texts = tokenizer.batch_decode(
            generated[:, input_length:], skip_special_tokens=True
        )
        for (row, condition, _prompt, prompt_hash), text in zip(batch, texts):
            decision = parse_decision(text)
            chosen_loss, regret = decision_regret(row, decision)
            output_rows.append(
                {
                    "schema_version": "controlled-model-judge-output-v1",
                    "model": args.model,
                    "model_revision_requested": args.revision or "",
                    "model_commit": getattr(model.config, "_commit_hash", "") or "",
                    "transformers_version": transformers.__version__,
                    "torch_version": torch.__version__,
                    "item_id": row["item_id"],
                    "pair_id": row["pair_id"],
                    "stratum": row["stratum"],
                    "variant": row["variant"],
                    "template_family": row["template_family"],
                    "benchmark_record_sha256": row["record_sha256"],
                    "condition": condition,
                    "prompt_sha256": prompt_hash,
                    "raw_output": text,
                    "parsed_decision": decision,
                    "target_decision": row["target_decision"],
                    "exact_agreement": int(decision == row["target_decision"]),
                    "chosen_loss": chosen_loss,
                    "optimal_loss": min(
                        float(value)
                        for value in row["decision_losses"].values()
                    ),
                    "regret": regret,
                }
            )

    output_rows.sort(
        key=lambda row: (str(row["item_id"]), str(row["condition"]))
    )
    expected_keys = {
        (str(row["item_id"]), condition)
        for row in benchmark
        for condition in CONDITIONS
    }
    actual_keys = {
        (str(row["item_id"]), str(row["condition"])) for row in output_rows
    }
    if actual_keys != expected_keys or len(output_rows) != 960:
        raise ValueError("model output does not cover every item-condition pair")
    summary = {
        "schema_version": "controlled-model-judge-summary-v1",
        "model": args.model,
        "model_revision_requested": args.revision or "",
        "model_commit": output_rows[0]["model_commit"],
        "records": len(output_rows),
        "items": len(benchmark),
        "conditions": list(CONDITIONS),
        "parse_failures": sum(
            row["parsed_decision"] == "parse_failure" for row in output_rows
        ),
        "order_seed": ORDER_SEED,
        "decoding": {
            "do_sample": False,
            "max_new_tokens": args.max_new_tokens,
            "max_input_tokens": args.max_input_tokens,
            "batch_size": args.batch_size,
        },
    }
    return output_rows, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-input-tokens", type=int, default=1024)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    rows, summary = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=True, sort_keys=True) for row in rows
        )
        + "\n",
        encoding="utf-8",
    )
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
