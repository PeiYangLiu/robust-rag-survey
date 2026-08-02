#!/usr/bin/env python3
"""Population bridge: one instrument, one codebook, two item populations.

The human anchor is measured on published comparative *claims*; the census is
measured on 45-line *screen windows*. A reviewer can fairly object that the
human result therefore does not license anything about the census number,
because the two populations differ. This run isolates the population effect:
it puts the deployed census panel, under the byte-identical census codebook,
onto the same 80 claims the human panel coded, so the only thing that changes
between this run and the census is the item population.

The census codebook and its ``call`` transport are imported, not re-typed.
"""

import argparse
import csv
import json
import os
import pathlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from code_cross_paper_frame import CODEBOOK, call, call_cli  # noqa: E402
from run_human_matched_panel import extract_json, load_items  # noqa: E402

OUT_DIR = ROOT / "supplement" / "population_bridge"
COORDS = ["c1", "c2", "c3", "c4", "c5"]
COORD_LABELS = {"match", "mismatch", "not_determinable"}
VERDICTS = {"survives", "narrows", "undefined"}


def build_user(item):
    """Present a claim in the same shape the census presents a window."""
    return (
        f"SOURCE FILE: {item['source_title']}\n"
        f"FOCUS LOCATION: {item['source_section']} (printed page "
        f"{item['printed_page']})\n"
        f"SYSTEMS OR QUANTITIES COMPARED: {item['comparison_subjects']}\n\n"
        f"FOCUS PASSAGE (the juxtaposition to code):\n<<<\n"
        f"{item['exact_quote']}\n>>>\n\n"
        f"SURROUNDING CONTEXT (use it to determine the coordinates; the focus "
        f"passage is repeated inside it):\n<<<\n"
        f"{item['context_before']}\n{item['exact_quote']}\n{item['context_after']}\n>>>\n"
    )


def normalise(record):
    out = {}
    for coord in COORDS:
        value = str(record.get(coord, "")).strip().lower().replace(" ", "_")
        out[coord] = value if value in COORD_LABELS else ""
    verdict = str(record.get("verdict", "")).strip().lower()
    out["verdict"] = verdict if verdict in VERDICTS else ""
    out["eligible"] = bool(record.get("eligible"))
    out["rationale"] = str(record.get("rationale", ""))[:900]
    out["evidence_quote"] = str(record.get("evidence_quote", ""))[:900]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", required=True)
    parser.add_argument("--judge-name", required=True)
    parser.add_argument("--backend", choices=["http", "cli"], default="http")
    parser.add_argument("--base-url", default=os.environ.get("JUDGE_BASE_URL", "http://localhost:4141/v1"))
    parser.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY", "dummy"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    items = load_items()
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.judge_name}.jsonl"

    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["annotation_id"])
    todo = [i for i in items if i["annotation_id"] not in done]
    print(f"[{args.judge_name}] {len(done)} done, {len(todo)} to run", flush=True)

    lock = threading.Lock()
    handle = out_path.open("a", encoding="utf-8")
    counters = {"ok": 0, "fail": 0}

    def work(item):
        messages = [
            {"role": "system", "content": CODEBOOK},
            {"role": "user", "content": build_user(item)},
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
            "error": err,
            "parsed": bool(parsed),
            "raw": (text or "")[:4000],
        }
        if parsed:
            record.update(normalise(parsed))
        with lock:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            counters["ok" if parsed else "fail"] += 1
            total = counters["ok"] + counters["fail"]
            if total % 20 == 0 or total == len(todo):
                print(f"[{args.judge_name}] {total}/{len(todo)} ok={counters['ok']}", flush=True)

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, todo))
    handle.close()
    print(
        f"[{args.judge_name}] done in {time.time() - started:.0f}s "
        f"parsed={counters['ok']} failed={counters['fail']} -> {out_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
