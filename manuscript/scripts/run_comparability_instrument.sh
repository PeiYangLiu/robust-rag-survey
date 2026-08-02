#!/usr/bin/env bash
# Instrument benchmark: six judges from three developers x three codebooks.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
r() { # model name backend workers
  for a in five c1c4 direct; do
    for try in 1 2 3 4; do
      python3 scripts/run_comparability_instrument_judges.py \
        --judge "$1" --judge-name "$2" --arm "$a" --backend "$3" \
        --workers "$4" --timeout 300 --retries 4 >>"logs/inst_${a}_$2.log" 2>&1
      n=$(grep -c '"parsed": {' "supplement/comparability_instrument_runs/$a/$2.jsonl" 2>/dev/null || echo 0)
      echo "[$(date +%H:%M:%S)] $2/$a try $try -> $n" >>"logs/inst_${a}_$2.log"
      [ "$n" -ge 358 ] && break
    done
  done
}
r claude-opus-4.6        insB_opus46   http 12 &
r claude-opus-4.8        insG_opus48   http 12 &
r gemini-3.1-pro-preview insC_gem31pro http 12 &
r gemini-2.5-pro         insH_gem25pro http 12 &
r gpt-5.4                insI_gpt54    cli   8 &
r gpt-5.5                insJ_gpt55    cli   8 &
wait
echo "instrument benchmark complete"
