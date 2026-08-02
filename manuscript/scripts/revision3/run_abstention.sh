#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.." || exit 1
mkdir -p logs/revision3
pids=()
for spec in "gpt-5-mini:absA_gpt5mini" "claude-opus-4.6:absB_claudeopus46" "gemini-3.1-pro-preview:absC_gemini31pro"; do
  model="${spec%%:*}"; name="${spec##*:}"
  echo "[start] $(date +%T) $name"
  python scripts/revision3/run_abstention_verdict.py --judge "$model" --judge-name "$name" \
    --workers 8 > "logs/revision3/abstention__$name.log" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
echo "[abstention done] $(date +%T)"
