#!/usr/bin/env bash
# Run the v2 controlled experiment locally on one V100, cleaning the model
# cache after each model so the sweep fits in available disk.
set -u
REPO=.
PY=$REPO/.venv_v100/bin/python
OUT=$REPO/manuscript/supplement/controlled_model_judge_raw_v2
mkdir -p "$OUT"
export HF_HUB_ENABLE_HF_TRANSFER=1
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1
cd "$REPO/manuscript"
GPU=$1; shift
for spec in "$@"; do
  name="${spec%%=*}"; rest="${spec#*=}"; model="${rest%%|*}"; extra="${rest#*|}"
  [ "$extra" = "$rest" ] && extra=""
  if [ -s "$OUT/$name.jsonl" ]; then echo "[skip] $name"; continue; fi
  echo "[start] $(date +%T) $name -> $model (gpu $GPU) $extra"
  CUDA_VISIBLE_DEVICES=$GPU $PY scripts/run_controlled_model_judges_v2.py \
    --model "$model" \
    --benchmark supplement/controlled_claim_audit_benchmark_v2.jsonl \
    --output "$OUT/$name.jsonl" --summary "$OUT/$name-summary.json" \
    --batch-size 16 --dtype float16 --progress $extra \
    > "$OUT/$name.log" 2>&1
  status=$?
  echo "[done] $(date +%T) $name status=$status"
  if [ $status -ne 0 ]; then tail -5 "$OUT/$name.log"; fi
  cache="$HOME/.cache/huggingface/hub/models--$(echo "$model" | sed 's:/:--:g')"
  case "$model" in
    Qwen/Qwen3-8B|Qwen/Qwen3-14B) : ;;  # keep pre-existing cache entries
    *) rm -rf "$cache" 2>/dev/null || true ;;
  esac
  df -h / | tail -1
done
echo "[all done] gpu $GPU"
