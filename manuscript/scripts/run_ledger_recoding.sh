#!/usr/bin/env bash
# Independent re-coding of the worked ledger by six judges from three
# developers (reviewer W5).  None of them sees our labels.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
r() { python3 scripts/recode_ledger_cases.py --judge "$1" --judge-name "$2" \
        --backend "$3" --workers "$4" >>"logs/recode_$2.log" 2>&1; }
r claude-opus-4.6        recB_opus46   http 5 &
r claude-opus-4.8        recG_opus48   http 5 &
r gemini-3.1-pro-preview recC_gem31pro http 5 &
r gemini-2.5-pro         recH_gem25pro http 5 &
r gpt-5.4                recI_gpt54    cli  3 &
r gpt-5.5                recJ_gpt55    cli  3 &
wait
echo "ledger re-coding complete"
