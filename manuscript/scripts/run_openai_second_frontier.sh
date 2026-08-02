#!/usr/bin/env bash
# Second OpenAI frontier checkpoint, so that the same-developer / same-tier
# reference level exists for all three developers rather than only two.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
for pass in $(seq 1 12); do
  python3 scripts/prune_failed_judge_rows.py coderJ_gpt55 >>logs/coderJ.log 2>&1
  python3 scripts/code_cross_paper_frame.py \
    --judge gpt-5.5 --judge-name coderJ_gpt55 --backend cli \
    --workers 6 --timeout 300 --retries 3 \
    --out-dir supplement/cross_paper_coding >>logs/coderJ.log 2>&1
  n=$(python3 - <<'PY'
import json
try:
    print(sum(1 for l in open("supplement/cross_paper_coding/coderJ_gpt55.jsonl") if json.loads(l).get("parsed")))
except Exception:
    print(0)
PY
)
  echo "[$(date +%H:%M:%S)] pass $pass -> parsed=$n"
  [ "$n" -ge 1700 ] && break
  sleep 10
done
echo "OPENAI_SECOND_DONE"
