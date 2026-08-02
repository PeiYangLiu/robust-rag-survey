#!/usr/bin/env bash
# Tier x developer control panel for the cross-paper census (reviewer W6).
#
# The submitted panel was {gpt-5-mini, claude-opus-4.6, gemini-3.1-pro-preview},
# which confounds "verdict disagreement is a property of the task" with
# "one judge is a smaller capability tier".  This adds four judges so that
# capability tier is crossed with developer on the same 1,703-window frame:
#
#   developer   small tier            frontier tier
#   OpenAI      gpt-5-mini (have)     gpt-4.1            (coderD)
#   Anthropic   claude-haiku-4.5 (E)  claude-opus-4.6 (have)
#   Google      gemini-3.5-flash (F)  gemini-3.1-pro-preview (have)
#   Anthropic   --                    claude-opus-4.8    (coderG, same-tier pair)
#
# Every run is resumable: re-invoking skips candidates already written.
set -u
cd "$(dirname "$0")/.."
OUT=supplement/cross_paper_coding
mkdir -p "$OUT" logs

run() {
  local model="$1" name="$2" toks="$3" workers="$4"
  for attempt in 1 2 3 4 5 6; do
    python3 scripts/code_cross_paper_frame.py \
      --judge "$model" --judge-name "$name" \
      --max-tokens "$toks" --workers "$workers" \
      --timeout 300 --retries 4 \
      --out-dir "$OUT" >>"logs/tier_${name}.log" 2>&1
    local done_n
    done_n=$(wc -l <"$OUT/$name.jsonl" 2>/dev/null || echo 0)
    echo "[$(date +%H:%M:%S)] $name attempt $attempt -> $done_n rows" >>"logs/tier_${name}.log"
    [ "$done_n" -ge 1703 ] && break
    sleep 10
  done
}

run gpt-4.1                 coderD_gpt41         3000 8 &
run claude-haiku-4.5        coderE_haiku45       3000 8 &
run gemini-3.5-flash        coderF_gemini35flash 8000 8 &
run claude-opus-4.8         coderG_opus48        3000 6 &
wait
echo "tier control panel complete"
