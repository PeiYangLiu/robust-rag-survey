#!/usr/bin/env python3
"""Run a model-judge panel on the 80 items that three human coders annotated.

The human round (``manuscript/human_coding/observed_claim_human_validation_20260714``)
gave three independent human coders the frozen v2 codebook and, per item, the
exact quotation, adjacent context, source title/URL/section and page. This
script hands a model judge byte-identical material and the same codebook, and
asks for the same fields, so that human-panel and model-panel reliability are
measured on the same items under the same instructions.

Nothing here reads the human labels.
"""

import argparse
import csv
import json
import os
import pathlib
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from code_cross_paper_frame import call, call_cli  # noqa: E402

HUMAN_DIR = (
    ROOT
    / "human_coding"
    / "observed_claim_human_validation_20260714"
    / "annotated_20260714"
)
CODEBOOK = ROOT / "supplement" / "observed_claim_audit_codebook.md"
OUT_DIR = ROOT / "supplement" / "human_matched_panel"

RELATIONS = ["aligned", "different", "mixed", "unknown", "not_applicable"]
VERDICTS = ["valid", "partial", "invalid", "under-specified"]

SYSTEM = """You are coding published comparative claims for a comparability audit.
You are given the frozen codebook and one claim with its exact quotation, the
surrounding context, and its source location. Apply the codebook to that
material.

Return one JSON object and nothing else, with exactly these keys:
  "unit_status": "include" or "exclude_not_comparative"
  "archetype": one of A_self_baseline, B_shared_harness, C_cross_source_synthesis,
               D_causal_mechanistic, E_field_meta, F_policy_utility
  "claim_strength": one of descriptive, directional, rank_or_superlative, causal,
               field_absence_or_incommensurability, normative_policy
  "c1_relation", "c2_relation", "c3_relation", "c4_relation", "c5_relation":
               each one of aligned, different, mixed, unknown, not_applicable
  "verdict": one of valid, partial, invalid, under-specified
  "rationale": at most 80 words naming which coordinates you could determine.

Do not hedge outside the label set. Do not add keys."""


def load_items():
    path = HUMAN_DIR / "annotator_A_claims_completed.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    items = []
    for row in rows:
        items.append(
            {
                "annotation_id": row["annotation_id"].strip(),
                "source_title": row.get("source_title", "").strip(),
                "source_url": row.get("source_url", "").strip(),
                "source_section": row.get("source_section", "").strip(),
                "pdf_page": row.get("pdf_page", "").strip(),
                "printed_page": row.get("printed_page", "").strip(),
                "exact_quote": row.get("exact_quote", "").strip(),
                "context_before": row.get("context_before", "").strip(),
                "context_after": row.get("context_after", "").strip(),
                "comparison_subjects": row.get("comparison_subjects", "").strip(),
            }
        )
    return items


def build_prompt(codebook, item):
    return f"""## Codebook (frozen, v2)

{codebook}

## Claim to code

Annotation id: {item['annotation_id']}
Source title: {item['source_title']}
Source URL: {item['source_url']}
Source section: {item['source_section']}
PDF page: {item['pdf_page']}   Printed page: {item['printed_page']}
Comparison subjects: {item['comparison_subjects']}

Context before: {item['context_before']}

EXACT QUOTATION:
{item['exact_quote']}

Context after: {item['context_after']}

Code this claim now. Return only the JSON object."""


def extract_json(text):
    if not text:
        return None
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, re.S)
    for block in fenced:
        try:
            return json.loads(block.strip())
        except Exception:  # noqa: BLE001
            continue
    start = text.find("{")
    while start != -1:
        depth = 0
        for idx in range(start, len(text)):
            if text[idx] == "{":
                depth += 1
            elif text[idx] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : idx + 1])
                    except Exception:  # noqa: BLE001
                        break
        start = text.find("{", start + 1)
    return None


def normalise(record):
    out = {}
    for key in [
        "unit_status",
        "archetype",
        "claim_strength",
        "c1_relation",
        "c2_relation",
        "c3_relation",
        "c4_relation",
        "c5_relation",
        "verdict",
    ]:
        value = record.get(key)
        value = str(value).strip().lower() if value is not None else ""
        value = value.replace(" ", "_")
        if key.endswith("_relation") and value not in RELATIONS:
            value = "unknown" if value else ""
        if key == "verdict":
            value = value.replace("_", "-")
            if value not in VERDICTS:
                value = ""
        out[key] = value
    out["rationale"] = str(record.get("rationale", ""))[:1200]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", required=True, help="model id served by the proxy")
    parser.add_argument("--judge-name", required=True)
    parser.add_argument("--backend", choices=["http", "cli"], default="http")
    parser.add_argument("--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1"))
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=1400)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    codebook = CODEBOOK.read_text(encoding="utf-8")
    items = load_items()
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.judge_name}.jsonl"

    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["annotation_id"])
            except Exception:  # noqa: BLE001
                continue
    todo = [i for i in items if i["annotation_id"] not in done]
    print(f"[{args.judge_name}] {len(done)} done, {len(todo)} to run", flush=True)

    lock = threading.Lock()
    handle = out_path.open("a", encoding="utf-8")
    counters = {"ok": 0, "fail": 0}

    def work(item):
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(codebook, item)},
        ]
        if args.backend == "cli":
            text, err = call_cli(args.judge, messages, args.timeout, args.retries)
        else:
            text, err = call(
                args.base_url, args.api_key, args.judge, messages,
                args.max_tokens, args.timeout, args.retries,
            )
        parsed = extract_json(text)
        record = {
            "annotation_id": item["annotation_id"],
            "judge": args.judge_name,
            "model": args.judge,
            "raw": (text or "")[:6000],
            "error": err,
            "parsed": bool(parsed),
        }
        if parsed:
            record.update(normalise(parsed))
        with lock:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            counters["ok" if parsed else "fail"] += 1
            total = counters["ok"] + counters["fail"]
            if total % 10 == 0 or total == len(todo):
                print(
                    f"[{args.judge_name}] {total}/{len(todo)} "
                    f"parsed={counters['ok']} failed={counters['fail']}",
                    flush=True,
                )

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, todo))
    handle.close()
    print(
        f"[{args.judge_name}] finished in {time.time() - started:.0f}s "
        f"parsed={counters['ok']} failed={counters['fail']} -> {out_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
