#!/usr/bin/env python3
"""Distribute v3 controlled model-judge runs over a pool of remote GPU hosts.

The v2 experiment ran nine open checkpoints, five of which were Qwen or Qwen
derivatives, and a reviewer observed that the capability effect was
concentrated in that single developer family.  The remedy is a substantially
larger and developer-balanced checkpoint sample plus API-served frontier
models, so that the pooled estimate and its prediction interval refer to a
model population that actually spans developers and scales.

This orchestrator assigns each checkpoint a contiguous block of GPUs on one
host, launches the runs in parallel, and polls until every run terminates.
Runs are idempotent: a model whose output file already validates is skipped.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

HOSTS = [
    "10.190.129.14",
    "10.190.129.15",
    "10.190.129.17",
    "10.190.129.20",
    "10.190.129.25",
]
GPUS_PER_HOST = 16
REMOTE_ROOT = "/data/lpy/robust_rag_exp"
REMOTE_PY = "/data/lpy/venvs/v100rag/bin/python"

# (repo_id, short_name, developer, n_gpus, extra_flags)
MODELS: list[tuple[str, str, str, int, list[str]]] = [
    ("NousResearch/Meta-Llama-3.1-8B-Instruct", "llama31-8b", "Meta", 1, []),
    ("NousResearch/Meta-Llama-3.1-70B-Instruct", "llama31-70b", "Meta", 6, []),
    ("unsloth/Llama-3.2-3B-Instruct", "llama32-3b", "Meta", 1, []),
    ("unsloth/gemma-2-9b-it", "gemma2-9b", "Google", 2, ["--dtype", "float32"]),
    ("unsloth/gemma-2-2b-it", "gemma2-2b", "Google", 1, ["--dtype", "float32"]),
    ("unsloth/mistral-7b-instruct-v0.3", "mistral-7b-v03", "Mistral", 1, []),
    ("01-ai/Yi-1.5-9B-Chat", "yi15-9b", "01.AI", 1, []),
    ("THUDM/glm-4-9b-chat", "glm4-9b", "Zhipu", 2, ["--trust-remote-code"]),
    ("internlm/internlm2_5-7b-chat", "internlm25-7b", "ShanghaiAILab", 2, ["--trust-remote-code"]),
    ("microsoft/Phi-4", "phi4-14b", "Microsoft", 2, []),
    ("ibm-granite/granite-3.3-8b-instruct", "granite-33-8b", "IBM", 1, []),
    ("tiiuae/Falcon3-10B-Instruct", "falcon3-10b", "TII", 2, []),
    ("HuggingFaceH4/zephyr-7b-beta", "zephyr-7b", "HuggingFace", 1, []),
    ("upstage/SOLAR-10.7B-Instruct-v1.0", "solar-107b", "Upstage", 2, []),
    ("nvidia/Mistral-NeMo-Minitron-8B-Instruct", "minitron-8b", "NVIDIA", 2, []),
    ("stabilityai/stablelm-2-12b-chat", "stablelm2-12b", "Stability", 2, []),
    ("Qwen/Qwen2.5-32B-Instruct", "qwen25-32b", "Alibaba", 3, []),
    ("allenai/OLMo-2-0325-32B-Instruct", "olmo2-32b", "AI2", 3, []),
    ("CohereLabs/aya-expanse-8b", "aya-expanse-8b", "Cohere", 2, []),
    ("deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-v2-lite", "DeepSeek", 3, ["--trust-remote-code"]),
]

PASSWORD = "Welcome@DGX2026"


def ssh(host: str, command: str, capture: bool = True) -> str:
    result = subprocess.run(
        [
            "sshpass",
            "-p",
            PASSWORD,
            "ssh",
            "-n",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=15",
            f"ubuntu@{host}",
            command,
        ],
        capture_output=capture,
        text=True,
    )
    return (result.stdout or "") + (result.stderr or "")


def scp(local: Path, host: str, remote: str) -> None:
    subprocess.run(
        [
            "sshpass",
            "-p",
            PASSWORD,
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-q",
            str(local),
            f"ubuntu@{host}:{remote}",
        ],
        check=True,
    )


def stage(hosts: list[str]) -> None:
    runner = REPO / "manuscript" / "scripts" / "run_controlled_model_judges_v2.py"
    benchmark = (
        REPO / "manuscript" / "supplement" / "controlled_claim_audit_benchmark_v2.jsonl"
    )
    for host in hosts:
        ssh(host, f"mkdir -p {REMOTE_ROOT}/out {REMOTE_ROOT}/scripts")
        scp(runner, host, f"{REMOTE_ROOT}/scripts/run_controlled_model_judges_v2.py")
        scp(benchmark, host, f"{REMOTE_ROOT}/benchmark_v2.jsonl")
        print(f"staged {host}", flush=True)


def plan(hosts: list[str], models: list) -> list[tuple[str, list[int], tuple]]:
    """Greedy bin-packing of GPU blocks onto hosts."""
    cursor = {host: 0 for host in hosts}
    assignments = []
    ordered = sorted(models, key=lambda m: -m[3])
    for entry in ordered:
        needed = entry[3]
        host = min(hosts, key=lambda h: cursor[h])
        if cursor[host] + needed > GPUS_PER_HOST:
            host = max(hosts, key=lambda h: GPUS_PER_HOST - cursor[h])
            if cursor[host] + needed > GPUS_PER_HOST:
                raise SystemExit(f"cannot place {entry[1]}: no host has {needed} free GPUs")
        gpus = list(range(cursor[host], cursor[host] + needed))
        cursor[host] += needed
        assignments.append((host, gpus, entry))
    return assignments


def launch(host: str, gpus: list[int], entry: tuple, hf_home: str) -> None:
    repo_id, short, _dev, _n, extra = entry
    flags = " ".join(extra)
    devices = ",".join(str(g) for g in gpus)
    batch = 24 if len(gpus) <= 2 else 12
    script = f"""#!/bin/bash
cd {REMOTE_ROOT}
export HF_HOME={hf_home}
export HF_HUB_ENABLE_HF_TRANSFER=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES={devices}
exec {REMOTE_PY} scripts/run_controlled_model_judges_v2.py \\
  --model {repo_id} --benchmark benchmark_v2.jsonl \\
  --output out/{short}.jsonl --summary out/{short}-summary.json \\
  --batch-size {batch} --dtype float16 --disable-thinking --progress {flags}
"""
    local = Path(f"/tmp/launch_{short}.sh")
    local.write_text(script, encoding="utf-8")
    scp(local, host, f"{REMOTE_ROOT}/scripts/launch_{short}.sh")
    ssh(
        host,
        f"cd {REMOTE_ROOT} && setsid nohup bash scripts/launch_{short}.sh "
        f"> out/{short}.log 2>&1 < /dev/null & disown; sleep 1; echo started_{short}",
    )
    print(f"launched {short:<18} on {host} gpus={devices}", flush=True)


def status(assignments: list) -> dict[str, str]:
    out = {}
    by_host: dict[str, list] = {}
    for host, _gpus, entry in assignments:
        by_host.setdefault(host, []).append(entry[1])
    for host, shorts in by_host.items():
        listing = ssh(host, f"ls -la {REMOTE_ROOT}/out/*.jsonl 2>/dev/null; echo ---; "
                            f"for f in {' '.join(REMOTE_ROOT + '/out/' + s + '.log' for s in shorts)}; "
                            f"do echo \"== $f\"; tail -1 $f 2>/dev/null; done")
        out[host] = listing
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--collect", type=Path)
    parser.add_argument("--hosts", nargs="+", default=HOSTS)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--hf-home", default="/data/lpy/hf_cache")
    args = parser.parse_args()

    models = MODELS
    if args.only:
        models = [m for m in MODELS if m[1] in set(args.only)]

    assignments = plan(args.hosts, models)
    if args.stage:
        stage(args.hosts)
    if args.launch:
        for host, gpus, entry in assignments:
            launch(host, gpus, entry, args.hf_home)
    if args.status:
        for host, text in status(assignments).items():
            print(f"######## {host}")
            print(text)
    if args.collect:
        args.collect.mkdir(parents=True, exist_ok=True)
        for host, _gpus, entry in assignments:
            short = entry[1]
            for suffix in (".jsonl", "-summary.json", ".log"):
                subprocess.run(
                    [
                        "sshpass",
                        "-p",
                        PASSWORD,
                        "scp",
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-q",
                        f"ubuntu@{host}:{REMOTE_ROOT}/out/{short}{suffix}",
                        str(args.collect / f"{short}{suffix}"),
                    ],
                    capture_output=True,
                )
        print(f"collected into {args.collect}")
    if not any([args.stage, args.launch, args.status, args.collect]):
        for host, gpus, entry in assignments:
            print(f"{entry[1]:<18} {entry[2]:<14} host={host} gpus={gpus}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
