#!/usr/bin/env bash
# Drive every tier-control judge to full frame coverage.
# Between passes it prunes rows that carry an api_error or failed to parse,
# because the resume logic in code_cross_paper_frame.py treats any written row
# as done and would otherwise leave rate-limited candidates permanently blank.
set -u
cd "$(dirname "$0")/.."
declare -A MODEL=( [coderD_gpt41]=gpt-4.1 [coderE_haiku45]=claude-haiku-4.5 \
                   [coderF_gemini35flash]=gemini-3.5-flash [coderG_opus48]=claude-opus-4.8 )
declare -A TOKS=(  [coderD_gpt41]=3000 [coderE_haiku45]=3000 \
                   [coderF_gemini35flash]=12000 [coderG_opus48]=3000 )
declare -A WORK=(  [coderD_gpt41]=2 [coderE_haiku45]=6 \
                   [coderF_gemini35flash]=4 [coderG_opus48]=4 )
for pass in 1 2 3 4 5 6 7 8 9 10; do
  alldone=1
  for name in "${!MODEL[@]}"; do
    n=$(wc -l < "supplement/cross_paper_coding/$name.jsonl" 2>/dev/null || echo 0)
    [ "$n" -ge 1700 ] && continue
    alldone=0
    python3 scripts/prune_failed_judge_rows.py "$name" >>"logs/complete_$name.log" 2>&1
    python3 scripts/code_cross_paper_frame.py --judge "${MODEL[$name]}" \
      --judge-name "$name" --max-tokens "${TOKS[$name]}" --workers "${WORK[$name]}" \
      --timeout 300 --retries 6 --out-dir supplement/cross_paper_coding \
      >>"logs/complete_$name.log" 2>&1 &
  done
  wait
  echo "[pass $pass] $(for n in "${!MODEL[@]}"; do printf '%s=%s ' "$n" "$(wc -l < supplement/cross_paper_coding/$n.jsonl 2>/dev/null || echo 0)"; done)"
  [ "$alldone" = 1 ] && break
  sleep 15
done
echo "tier judges complete"
