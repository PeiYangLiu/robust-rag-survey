#!/bin/bash
# Keep the v3 model-judge queue draining without supervision.
#
# Every cycle: collect any finished outputs from the GPU hosts into the
# supplement, then re-dispatch pending checkpoints onto whatever GPUs are free.
# Both steps are idempotent, so the loop is safe to run alongside other users'
# jobs on the same shared hosts.

set -u
export SSHPASS='Welcome@DGX2026'
MAN=manuscript
DEST=$MAN/supplement/controlled_model_judge_raw_v3
HOSTS="10.190.129.14 10.190.129.20 10.190.129.25"
CYCLES=${1:-48}
SLEEP=${2:-300}

mkdir -p "$DEST"
for cycle in $(seq 1 "$CYCLES"); do
  echo "=== cycle $cycle $(date -Is)"
  for ip in $HOSTS; do
    done_list=$(sshpass -e ssh -n -o StrictHostKeyChecking=no -o ConnectTimeout=20 ubuntu@$ip \
      "cd /data/lpy/robust_rag_exp/out 2>/dev/null && for f in *.jsonl; do n=\$(wc -l<\"\$f\" 2>/dev/null); [ \"\${n:-0}\" -ge 7200 ] && echo \${f%.jsonl}; done" 2>/dev/null)
    for f in $done_list; do
      if [ ! -s "$DEST/$f.jsonl" ]; then
        sshpass -e scp -o StrictHostKeyChecking=no -q ubuntu@$ip:/data/lpy/robust_rag_exp/out/$f.jsonl "$DEST/" 2>/dev/null && \
        sshpass -e scp -o StrictHostKeyChecking=no -q ubuntu@$ip:/data/lpy/robust_rag_exp/out/$f-summary.json "$DEST/" 2>/dev/null
        echo "collected $f from $ip"
      fi
    done
  done
  python3 -u "$MAN/scripts/dispatch_model_judge_runs.py" --hosts $HOSTS 2>&1 | grep -E "^(place|launched|already|!!)" | head -25
  sleep "$SLEEP"
done
echo "=== loop finished $(date -Is)"
