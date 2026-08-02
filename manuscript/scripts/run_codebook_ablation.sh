#!/usr/bin/env bash
# Codebook-ablation runs for the cross-paper census (reviewer W4).
#
# Holds the judge, the passage, the context window, the ordering seed and the
# output schema fixed and varies only the instrument:
#
#   five  (released)  C1..C5 coded, verdict derived from five coordinates
#   c1c4  (new)       only C1 and C4 coded, verdict derived from those two
#   direct(new)       no coordinates, comparability answered in one step
#
# The panel is the frontier panel of the paper -- one frontier checkpoint per
# developer -- so the ablation contrast is computed inside the configuration the
# paper reports as its best.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs supplement/cross_paper_coding_arms

run() {
  local model="$1" name="$2" arm="$3" backend="$4" toks="$5" workers="$6"
  for attempt in 1 2 3 4 5 6 7 8; do
    python3 scripts/code_frame_codebook_arms.py \
      --judge "$model" --judge-name "$name" --arm "$arm" \
      --backend "$backend" --max-tokens "$toks" --workers "$workers" \
      --timeout 300 --retries 4 >>"logs/arm_${arm}_${name}.log" 2>&1
    local done_n
    done_n=$(grep -c '"parsed": {' "supplement/cross_paper_coding_arms/$arm/$name.jsonl" 2>/dev/null || echo 0)
    echo "[$(date +%H:%M:%S)] $name/$arm attempt $attempt -> $done_n parsed rows" \
      >>"logs/arm_${arm}_${name}.log"
    [ "$done_n" -ge 1690 ] && break
    sleep 10
  done
}

run claude-opus-4.6        coderB_claudeopus46  c1c4   http 3000 14 &
run gemini-3.1-pro-preview coderC_gemini31pro   c1c4   http 8000 14 &
run gpt-5.4                coderI_gpt54         c1c4   cli  3000 10 &
run claude-opus-4.6        coderB_claudeopus46  direct http 3000 14 &
run gemini-3.1-pro-preview coderC_gemini31pro   direct http 8000 14 &
run gpt-5.4                coderI_gpt54         direct cli  3000 10 &
wait
echo "codebook ablation complete"
