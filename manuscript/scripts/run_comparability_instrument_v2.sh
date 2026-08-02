#!/usr/bin/env bash
# Instrument benchmark v2: the same six judges from three developers and the
# same three codebooks as v1, on the redesigned item set whose withheld arm is
# class balanced and whose presentation factor is crossed with disclosure.
# Holding the panel and the codebooks fixed makes the design the only change.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
ITEMS=supplement/comparability_instrument_benchmark_v2.jsonl
OUT=supplement/comparability_instrument_runs_v2
TARGET=430

r() { # model name backend workers port
  for a in five c1c4 direct; do
    for try in 1 2 3 4 5; do
      python3 scripts/run_comparability_instrument_judges.py \
        --judge "$1" --judge-name "$2" --arm "$a" --backend "$3" \
        --items "$ITEMS" --out-root "$OUT" \
        --base-url "http://localhost:$5/v1" \
        --workers "$4" --timeout 300 --retries 4 >>"logs/instv2_${a}_$2.log" 2>&1
      n=$(grep -c '"parsed": {' "$OUT/$a/$2.jsonl" 2>/dev/null || echo 0)
      echo "[$(date +%H:%M:%S)] $2/$a try $try -> $n" >>"logs/instv2_${a}_$2.log"
      [ "$n" -ge "$TARGET" ] && break
    done
  done
}

r claude-opus-4.6        insB_opus46   http 12 4141 &
r claude-opus-4.8        insG_opus48   http 12 4142 &
r gemini-3.1-pro-preview insC_gem31pro http 12 4143 &
r gemini-2.5-pro         insH_gem25pro http 12 4144 &
r gpt-5.4                insI_gpt54    cli   8  4145 &
r gpt-5.5                insJ_gpt55    cli   8  4146 &
wait
echo "instrument benchmark v2 complete"
