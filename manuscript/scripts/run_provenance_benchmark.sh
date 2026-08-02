#!/usr/bin/env bash
# Constructed provenance benchmark: the three judges that produced the census
# provenance labels, plus three further checkpoints so the reference-based
# accuracy is not a property of one panel.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
TARGET=278

r() { # model name backend workers port
  for a in deployed fourway; do
    for try in 1 2 3 4 5; do
      python3 scripts/run_provenance_benchmark_judges.py \
        --judge "$1" --judge-name "$2" --arm "$a" --backend "$3" \
        --base-url "http://localhost:$5/v1" \
        --workers "$4" --timeout 300 --retries 4 >>"logs/provbench_${a}_$2.log" 2>&1
      n=$(grep -c '"parsed": {' "supplement/provenance_benchmark_runs/$a/$2.jsonl" 2>/dev/null || echo 0)
      echo "[$(date +%H:%M:%S)] $2/$a try $try -> $n" >>"logs/provbench_${a}_$2.log"
      [ "$n" -ge "$TARGET" ] && break
    done
  done
}

# the three judges whose labels the census reports
r gpt-5-mini             pbA_gpt5mini  http 12 4147 &
r claude-opus-4.6        pbB_opus46    http 12 4148 &
r gemini-3.1-pro-preview pbC_gem31pro  http 12 4141 &
# three further checkpoints from the same three developers
r claude-opus-4.8        pbG_opus48    http 12 4142 &
r gemini-2.5-pro         pbH_gem25pro  http 12 4143 &
r gpt-5.4                pbI_gpt54     cli   8  4144 &
wait
echo "provenance benchmark complete"
