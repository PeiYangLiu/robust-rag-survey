#!/usr/bin/env bash
# Screen-recall sample: the same three judges that coded the frame, on windows
# the screen did not surface, under the same two prompts.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
TARGET=418

r() { # model name backend workers port
  for p in elig prov; do
    for try in 1 2 3 4 5; do
      python3 scripts/run_screen_recall_judges.py \
        --judge "$1" --judge-name "$2" --pass-name "$p" --backend "$3" \
        --base-url "http://localhost:$5/v1" \
        --workers "$4" --timeout 300 --retries 4 >>"logs/recall_${p}_$2.log" 2>&1
      n=$(grep -c '"parsed": {' "supplement/screen_recall_runs/$p/$2.jsonl" 2>/dev/null || echo 0)
      echo "[$(date +%H:%M:%S)] $2/$p try $try -> $n" >>"logs/recall_${p}_$2.log"
      [ "$n" -ge "$TARGET" ] && break
    done
  done
}

r gpt-5-mini             recA_gpt5mini http 12 4145 &
r claude-opus-4.6        recB_opus46   http 12 4146 &
r gemini-3.1-pro-preview recC_gem31pro http 12 4147 &
wait
echo "screen recall coding complete"
