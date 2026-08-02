#!/usr/bin/env python3
"""Run one open model on the v2 controlled consequence benchmark.

Design changes relative to ``run_controlled_model_judges.py``:

*   Three arms instead of two.  ``ablated`` names no capability or utility
    check; ``full`` names both; ``placebo`` adds generic auditing verbiage of
    comparable length to ``full`` while naming neither coordinate.  The
    ``full`` minus ``placebo`` contrast is therefore not confounded with
    instruction length or verbosity.
*   Four hand-written paraphrases per arm, varying wording, ordering, voice
    and layout, so an arm effect is estimated over a template population
    rather than a single string.
*   Every item is answered under all twelve prompt variants, with the item
    order shuffled once by a fixed seed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Mapping


REPO = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARK = (
    REPO / "manuscript" / "supplement" / "controlled_claim_audit_benchmark_v2.jsonl"
)
ORDER_SEED = 2026072704
ARMS = ("ablated", "placebo", "full")
PARAPHRASES = ("p1", "p2", "p3", "p4")
DECISIONS = ("deploy_A", "deploy_B", "defer")

# ---------------------------------------------------------------------------
# Prompt bank.  Each arm has four paraphrases.  Within a paraphrase index the
# three arms share their opening and closing wording, so the arm contrast is
# the presence of the capability (C2) and utility (C5) checks, and the placebo
# holds instruction length roughly fixed.
# ---------------------------------------------------------------------------

_BASE = {
    "p1": (
        "You audit comparisons used for robust-RAG deployment decisions. "
        "Check source support, evidence state, intervention, measured outcome "
        "and unit, and ordinary experimental controls. "
    ),
    "p2": (
        "Your role is to review a comparison between two retrieval-augmented "
        "systems before a deployment decision is taken. Establish what the "
        "sources support, what evidence condition holds, what was changed, "
        "which quantity was measured and in what unit, and whether the usual "
        "experimental controls are in place. "
    ),
    "p3": (
        "Act as a reviewer of robust-RAG deployment comparisons. Work through "
        "the report in this order: (a) ordinary experimental controls; "
        "(b) the measured outcome and its unit; (c) the intervention that was "
        "applied; (d) the evidence condition; (e) whether the sources support "
        "what is asserted. "
    ),
    "p4": (
        "A comparison of two retrieval-augmented systems is submitted for "
        "deployment review, and you are the reviewer. The evidence condition, "
        "the intervention, the measured outcome together with its unit, the "
        "ordinary experimental controls, and the support provided by the "
        "sources are all to be established. "
    ),
}

_COORDINATES = {
    "p1": (
        "Explicitly check how the evidence condition arose and the relevant "
        "access, knowledge, and budget capability. Also explicitly check "
        "available actions, coverage, stakes, and every stated error, "
        "abstention, compute, or follow-up cost. Do not transfer results "
        "outside an evaluated capability envelope. "
    ),
    "p2": (
        "Two further checks are required. First, determine how the evidence "
        "condition came about and which access, knowledge and budget "
        "capability the deployment assumes, and refuse to carry a result "
        "outside the capability envelope it was evaluated under. Second, "
        "determine the action set, the coverage, the stakes, and each stated "
        "error, abstention, compute or follow-up cost. "
    ),
    "p3": (
        "Add two checks to that order: (f) the origin of the evidence "
        "condition and the access, knowledge and budget capability it assumes, "
        "with no result carried outside its evaluated capability envelope; "
        "(g) the available actions, the coverage, the stakes, and every stated "
        "error, abstention, compute or follow-up cost. "
    ),
    "p4": (
        "The origin of the evidence condition and the access, knowledge and "
        "budget capability assumed at deployment must also be established, and "
        "no result may be carried outside the capability envelope under which "
        "it was evaluated. The available actions, the coverage, the stakes, "
        "and each stated error, abstention, compute or follow-up cost must "
        "likewise be established. "
    ),
}

# Length-matched verbiage that names neither capability nor utility content.
_PLACEBO = {
    "p1": (
        "Read the report carefully before answering, and read it a second time "
        "if anything is unclear. Work through it in a fixed order and finish "
        "one sentence before starting the next. Do not skip a stated condition "
        "and do not revise a reading without a reason drawn from the report "
        "itself. Use the report as written. "
    ),
    "p2": (
        "Two working habits are required. First, read the report through "
        "before answering and read any unclear passage a second time, "
        "finishing one sentence before starting the next. Second, proceed in a "
        "fixed order, skip no stated condition, and revise a reading only for "
        "a reason drawn from the report itself. "
    ),
    "p3": (
        "Add two working habits to that order: (f) read the report through "
        "before answering, read any unclear passage again, and finish one "
        "sentence before starting the next; (g) proceed in a fixed order, skip "
        "no stated condition, and revise a reading only for a reason drawn "
        "from the report itself. "
    ),
    "p4": (
        "The report is to be read through before answering, and any unclear "
        "passage is to be read a second time, with one sentence finished "
        "before the next is started. The reading is to proceed in a fixed "
        "order, no stated condition may be skipped, and a reading may be "
        "revised only for a reason drawn from the report itself. "
    ),
}

_CLOSING = {
    "p1": "Apply the stated deployment rule exactly.",
    "p2": "The stated deployment rule is then to be applied exactly as written.",
    "p3": "Finally, apply the stated deployment rule exactly.",
    "p4": "The stated deployment rule is to be applied exactly.",
}

_OUTPUT_INSTRUCTION = {
    "p1": (
        "\nReturn exactly one action token and no explanation. Use deploy_A for "
        "System A, deploy_B for System B, or defer for commissioning the "
        "matched evaluation. Do not repeat the alternatives."
    ),
    "p2": (
        "\nAnswer with a single action token and nothing else: deploy_A to "
        "deploy System A, deploy_B to deploy System B, or defer to commission "
        "the matched evaluation. Do not restate the options and do not explain."
    ),
    "p3": (
        "\nOutput one token only. The permitted tokens are deploy_A (deploy "
        "System A), deploy_B (deploy System B) and defer (commission the "
        "matched evaluation). No explanation, no restatement."
    ),
    "p4": (
        "\nExactly one action token is to be returned, with no explanation and "
        "no restatement of the options: deploy_A for System A, deploy_B for "
        "System B, defer for commissioning the matched evaluation."
    ),
}


def system_prompt(arm: str, paraphrase: str) -> str:
    if arm == "ablated":
        middle = ""
    elif arm == "placebo":
        middle = _PLACEBO[paraphrase]
    elif arm == "full":
        middle = _COORDINATES[paraphrase]
    else:
        raise ValueError(f"unknown arm {arm}")
    return _BASE[paraphrase] + middle + _CLOSING[paraphrase]


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSON at {path}:{number}")
        rows.append(value)
    return rows


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_decision(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"^\s*<think>\s*", " ", cleaned, flags=re.IGNORECASE)
    prefix = re.match(r"[\s*`\"']*(deploy_A|deploy_B|defer)", cleaned, re.IGNORECASE)
    if prefix:
        return {
            "deploy_a": "deploy_A",
            "deploy_b": "deploy_B",
            "defer": "defer",
        }[prefix.group(1).lower()]
    json_match = re.search(
        r'["\']decision["\']\s*:\s*["\'](deploy_A|deploy_B|defer)["\']',
        cleaned,
        re.IGNORECASE,
    )
    if json_match:
        return {
            "deploy_a": "deploy_A",
            "deploy_b": "deploy_B",
            "defer": "defer",
        }[json_match.group(1).lower()]
    tokens = re.findall(r"\b(deploy_A|deploy_B|defer)\b", cleaned, re.IGNORECASE)
    normalized = {"deploy_a": "deploy_A", "deploy_b": "deploy_B", "defer": "defer"}
    unique = {normalized[token.lower()] for token in tokens}
    return unique.pop() if len(unique) == 1 else "parse_failure"


def apply_template(tokenizer, messages, disable_thinking: bool) -> str:
    if disable_thinking:
        try:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            pass
    return tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )


def decision_regret(row: Mapping[str, object], decision: str) -> tuple[float, float]:
    losses = {key: float(value) for key, value in row["decision_losses"].items()}
    optimum = min(losses.values())
    chosen = losses[decision] if decision in losses else max(losses.values())
    return chosen, chosen - optimum


def run(args: argparse.Namespace) -> tuple[list[dict[str, object]], dict[str, object]]:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    benchmark = read_jsonl(args.benchmark)
    if not benchmark:
        raise ValueError("empty benchmark")

    tokenizer = AutoTokenizer.from_pretrained(
        args.model, revision=args.revision, trust_remote_code=args.trust_remote_code
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    dtype = {
        "auto": "auto",
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[args.dtype]
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        revision=args.revision,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=args.trust_remote_code,
    )
    model.eval()

    prompt_lengths: dict[str, int] = {}
    for arm in ARMS:
        for paraphrase in PARAPHRASES:
            text = system_prompt(arm, paraphrase) + _OUTPUT_INSTRUCTION[paraphrase]
            prompt_lengths[f"{arm}/{paraphrase}"] = len(
                tokenizer(text, add_special_tokens=False)["input_ids"]
            )

    work = []
    for row in benchmark:
        for arm in ARMS:
            for paraphrase in PARAPHRASES:
                messages = [
                    {"role": "system", "content": system_prompt(arm, paraphrase)},
                    {
                        "role": "user",
                        "content": str(row["vignette"]) + _OUTPUT_INSTRUCTION[paraphrase],
                    },
                ]
                prompt = apply_template(tokenizer, messages, args.disable_thinking)
                prompt_hash = sha256_text(
                    json.dumps(messages, ensure_ascii=True, sort_keys=True)
                )
                work.append((row, arm, paraphrase, prompt, prompt_hash))
    random.Random(ORDER_SEED).shuffle(work)

    output_rows: list[dict[str, object]] = []
    for start in range(0, len(work), args.batch_size):
        batch = work[start : start + args.batch_size]
        encoded = tokenizer(
            [record[3] for record in batch],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=args.max_input_tokens,
            add_special_tokens=False,
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
        for (row, arm, paraphrase, _prompt, prompt_hash), text in zip(batch, texts):
            decision = parse_decision(text)
            chosen_loss, regret = decision_regret(row, decision)
            output_rows.append(
                {
                    "schema_version": "controlled-model-judge-output-v2",
                    "model": args.model,
                    "model_revision_requested": args.revision or "",
                    "model_commit": getattr(model.config, "_commit_hash", "") or "",
                    "transformers_version": transformers.__version__,
                    "torch_version": torch.__version__,
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
                    "parsed_decision": decision,
                    "target_decision": row["target_decision"],
                    "exact_agreement": int(decision == row["target_decision"]),
                    "chosen_loss": chosen_loss,
                    "optimal_loss": min(
                        float(value) for value in row["decision_losses"].values()
                    ),
                    "regret": regret,
                }
            )
        if args.progress and (start // args.batch_size) % 25 == 0:
            print(
                json.dumps(
                    {"progress": start + len(batch), "total": len(work)}, sort_keys=True
                ),
                flush=True,
            )

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
        "model_revision_requested": args.revision or "",
        "model_commit": output_rows[0]["model_commit"],
        "records": len(output_rows),
        "items": len(benchmark),
        "arms": list(ARMS),
        "paraphrases": list(PARAPHRASES),
        "system_prompt_tokens": prompt_lengths,
        "parse_failures": sum(
            row["parsed_decision"] == "parse_failure" for row in output_rows
        ),
        "decision_distribution": dict(
            Counter(str(row["parsed_decision"]) for row in output_rows)
        ),
        "order_seed": ORDER_SEED,
        "decoding": {
            "do_sample": False,
            "max_new_tokens": args.max_new_tokens,
            "max_input_tokens": args.max_input_tokens,
            "batch_size": args.batch_size,
            "disable_thinking": bool(args.disable_thinking),
            "dtype": args.dtype,
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
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--max-input-tokens", type=int, default=1280)
    parser.add_argument("--max-new-tokens", type=int, default=24)
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--limit-items", type=int, default=0)
    parser.add_argument(
        "--dtype", choices=("auto", "float16", "bfloat16", "float32"), default="auto"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    if args.limit_items:
        rows = read_jsonl(args.benchmark)[: args.limit_items]
        smoke = args.output.parent / "smoke_benchmark.jsonl"
        smoke.parent.mkdir(parents=True, exist_ok=True)
        smoke.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        args.benchmark = smoke
    rows, summary = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True, sort_keys=True) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
