#!/usr/bin/env python3
"""Dispatch v3 controlled model-judge runs onto whatever GPUs are actually free.

The GPU hosts are shared, so a static GPU map causes out-of-memory failures
when another job is resident.  This dispatcher queries each host for GPUs whose
used memory is below a threshold, packs the pending checkpoints into those
GPUs, writes a per-host queue file, and starts a detached queue runner.

Re-running the dispatcher is safe: a checkpoint whose output JSONL already
exists and is complete is not re-queued.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PASSWORD = "Welcome@DGX2026"
REMOTE_ROOT = "/data/lpy/robust_rag_exp"
FREE_MIB = 1500

# short | repo | gpus_needed | batch | extra flags
MODELS: list[tuple[str, str, str, int, int, str]] = [
    ("llama31-8b", "NousResearch/Meta-Llama-3.1-8B-Instruct", "Meta", 1, 24, ""),
    ("llama32-3b", "unsloth/Llama-3.2-3B-Instruct", "Meta", 1, 24, ""),
    ("llama31-70b", "NousResearch/Meta-Llama-3.1-70B-Instruct", "Meta", 6, 12, ""),
    ("mistral-7b-v03", "unsloth/mistral-7b-instruct-v0.3", "Mistral", 1, 24, ""),
    ("mistral-nemo-12b", "unsloth/Mistral-Nemo-Instruct-2407", "Mistral", 2, 24, ""),
    ("yi15-9b", "01-ai/Yi-1.5-9B-Chat", "01.AI", 2, 24, ""),
    ("glm4-9b", "THUDM/glm-4-9b-chat", "Zhipu", 2, 24, "--trust-remote-code"),
    ("internlm25-7b", "internlm/internlm2_5-7b-chat", "ShanghaiAILab", 2, 24, "--trust-remote-code"),
    ("phi4-14b", "microsoft/Phi-4", "Microsoft", 2, 24, ""),
    ("granite-33-8b", "ibm-granite/granite-3.3-8b-instruct", "IBM", 1, 24, ""),
    ("falcon3-10b", "tiiuae/Falcon3-10B-Instruct", "TII", 2, 24, ""),
    ("zephyr-7b", "HuggingFaceH4/zephyr-7b-beta", "HuggingFace", 1, 24, ""),
    ("smollm3-3b", "HuggingFaceTB/SmolLM3-3B", "HuggingFace", 1, 24, ""),
    ("solar-107b", "upstage/SOLAR-10.7B-Instruct-v1.0", "Upstage", 2, 24, ""),
    ("minitron-8b", "nvidia/Mistral-NeMo-Minitron-8B-Instruct", "NVIDIA", 2, 24, ""),
    ("stablelm2-12b", "stabilityai/stablelm-2-12b-chat", "Stability", 2, 24, ""),
    ("gemma2-9b", "unsloth/gemma-2-9b-it", "Google", 2, 12, "--dtype float32"),
    ("gemma2-2b", "unsloth/gemma-2-2b-it", "Google", 1, 12, "--dtype float32"),
    ("qwen3-4b", "Qwen/Qwen3-4B", "Alibaba", 1, 24, ""),
    ("qwen25-32b", "Qwen/Qwen2.5-32B-Instruct", "Alibaba", 3, 12, ""),
    ("olmo2-32b", "allenai/OLMo-2-0325-32B-Instruct", "AI2", 3, 12, ""),
]


def ssh(host: str, command: str) -> str:
    result = subprocess.run(
        [
            "sshpass", "-p", PASSWORD, "ssh", "-n",
            "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=20",
            f"ubuntu@{host}", command,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return (result.stdout or "") + (result.stderr or "")


def scp(local: Path, host: str, remote: str) -> None:
    subprocess.run(
        ["sshpass", "-p", PASSWORD, "scp", "-o", "StrictHostKeyChecking=no", "-q",
         str(local), f"ubuntu@{host}:{remote}"],
        check=True,
        timeout=600,
    )


def free_gpus(host: str) -> list[int]:
    text = ssh(host, "nvidia-smi --query-gpu=index,memory.used --format=csv,noheader")
    out = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        used = int(parts[1].split()[0])
        if used < FREE_MIB:
            out.append(int(parts[0]))
    return out


def completed(host: str) -> set[str]:
    text = ssh(
        host,
        f"cd {REMOTE_ROOT}/out 2>/dev/null && for f in *.jsonl; do "
        f"n=$(wc -l < \"$f\"); [ \"$n\" -ge 7200 ] && echo \"${{f%.jsonl}}\"; done",
    )
    return {line.strip() for line in text.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hosts", nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stage", action="store_true")
    args = parser.parse_args()

    if args.stage:
        runner = REPO / "manuscript" / "scripts" / "run_controlled_model_judges_v2.py"
        queue_runner = REPO / "manuscript" / "scripts" / "host_queue_runner.sh"
        benchmark = (
            REPO / "manuscript" / "supplement" / "controlled_claim_audit_benchmark_v2.jsonl"
        )
        for host in args.hosts:
            ssh(host, f"mkdir -p {REMOTE_ROOT}/out {REMOTE_ROOT}/scripts")
            scp(runner, host, f"{REMOTE_ROOT}/scripts/run_controlled_model_judges_v2.py")
            scp(queue_runner, host, f"{REMOTE_ROOT}/scripts/host_queue_runner.sh")
            scp(benchmark, host, f"{REMOTE_ROOT}/benchmark_v2.jsonl")
            print(f"staged {host}", flush=True)

    done: set[str] = set()
    availability: dict[str, list[int]] = {}
    for host in args.hosts:
        availability[host] = free_gpus(host)
        done |= completed(host)
        print(f"{host}: {len(availability[host])} free GPUs {availability[host]}", flush=True)
    if done:
        print(f"already complete: {sorted(done)}", flush=True)

    pending = [m for m in MODELS if m[0] not in done]
    # Place the widest jobs first.
    pending.sort(key=lambda m: -m[3])

    queues: dict[str, list[str]] = {host: [] for host in args.hosts}
    placed: list[tuple[str, str, list[int]]] = []
    for short, repo, _dev, need, batch, extra in pending:
        host = max(args.hosts, key=lambda h: len(availability[h]))
        if len(availability[host]) < need:
            print(f"!! no host has {need} free GPUs for {short}; deferring", flush=True)
            continue
        gpus = [availability[host].pop(0) for _ in range(need)]
        queues[host].append(
            f"{short}|{repo}|{','.join(str(g) for g in gpus)}|{batch}|{extra}"
        )
        placed.append((short, host, gpus))

    for short, host, gpus in placed:
        print(f"place {short:<18} {host} gpus={gpus}", flush=True)
    if args.dry_run:
        return 0

    for host, lines in queues.items():
        if not lines:
            continue
        local = Path(f"/tmp/queue_{host.replace('.', '_')}.txt")
        local.write_text("\n".join(lines) + "\n", encoding="utf-8")
        scp(local, host, f"{REMOTE_ROOT}/queue.txt")
        ssh(
            host,
            f"cd {REMOTE_ROOT} && setsid -f bash scripts/host_queue_runner.sh "
            f"queue.txt > out/_queue.log 2>&1 < /dev/null; echo launched",
        )
        print(f"launched {len(lines)} jobs on {host}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
