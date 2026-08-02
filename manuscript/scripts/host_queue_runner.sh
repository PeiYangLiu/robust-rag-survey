#!/bin/bash
# Per-host queue runner for the v3 controlled model-judge experiment.
#
# Usage:  bash host_queue_runner.sh <queue-file>
#
# Each queue line is:  <short_name>|<repo_id>|<gpu_list>|<batch_size>|<extra flags>
# Jobs are launched in parallel (one process per GPU block) and each writes its
# own log.  A job whose output JSONL already exists and is non-empty is skipped,
# so the script is safe to re-run after a partial failure.

set -u
ROOT=/data/lpy/robust_rag_exp
PY=/data/lpy/venvs/v100rag/bin/python
export HF_HOME=/data/lpy/hf_cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export TOKENIZERS_PARALLELISM=false
export HF_HUB_DOWNLOAD_TIMEOUT=120

QUEUE="$1"
mkdir -p "$ROOT/out"

while IFS='|' read -r SHORT REPO GPUS BATCH EXTRA; do
  [ -z "${SHORT:-}" ] && continue
  case "$SHORT" in \#*) continue ;; esac
  if [ -s "$ROOT/out/$SHORT.jsonl" ]; then
    echo "skip $SHORT (already complete)"
    continue
  fi
  (
    export CUDA_VISIBLE_DEVICES="$GPUS"
    echo "[$(date -Is)] start $SHORT repo=$REPO gpus=$GPUS batch=$BATCH extra=$EXTRA"
    $PY "$ROOT/scripts/run_controlled_model_judges_v2.py" \
      --model "$REPO" \
      --benchmark "$ROOT/benchmark_v2.jsonl" \
      --output "$ROOT/out/$SHORT.jsonl" \
      --summary "$ROOT/out/$SHORT-summary.json" \
      --batch-size "$BATCH" --dtype float16 --disable-thinking --progress $EXTRA
    echo "[$(date -Is)] exit $SHORT rc=$?"
  ) > "$ROOT/out/$SHORT.log" 2>&1 &
  sleep 3
done < "$QUEUE"

wait
echo "[$(date -Is)] ALL_JOBS_DONE"
