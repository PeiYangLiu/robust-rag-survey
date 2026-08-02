#!/usr/bin/env bash
# Fill the OpenAI frontier cell of the tier-by-developer design.
#
# The local proxy injects max_tokens into /chat/completions, which the gpt-5.x
# reasoning models reject, and the gpt-4.x line shares an exhausted
# utility-model quota.  The Copilot CLI reaches the same checkpoint over a
# different transport with an identical prompt, so the cell can be filled
# without substituting another developer for it.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
for pass in $(seq 1 12); do
  python3 scripts/prune_failed_judge_rows.py coderI_gpt54 >>logs/coderI.log 2>&1
  python3 scripts/code_cross_paper_frame.py \
    --judge gpt-5.4 --judge-name coderI_gpt54 --backend cli \
    --workers 8 --timeout 300 --retries 3 \
    --out-dir supplement/cross_paper_coding >>logs/coderI.log 2>&1
  n=$(python3 - <<'PY'
import json
try:
    print(sum(1 for l in open("supplement/cross_paper_coding/coderI_gpt54.jsonl") if json.loads(l).get("parsed")))
except Exception:
    print(0)
PY
)
  echo "[$(date +%H:%M:%S)] pass $pass -> parsed=$n"
  [ "$n" -ge 1700 ] && break
  sleep 10
done
echo "OPENAI_FRONTIER_DONE"
