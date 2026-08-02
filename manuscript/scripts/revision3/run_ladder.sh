#!/usr/bin/env bash
# Launch the privileged-adjudication information ladder, one stage at a time.
#
# The window tier is NOT run here: the deployed census already coded every
# sampled window under the byte-identical prompt, so its codings are the
# window-tier arm and re-running them would only add sampling noise.
#
# Two panels:
#   ladder     the three deployed judges, at citing_full and both_full, so that
#              information tier is the only thing that varies against the census.
#   reference  three stronger checkpoints, used to build the reference itself.
#              The Google cell reuses the deployed checkpoint because it is that
#              developer's strongest; the analysis reports a leave-one-judge-out
#              sensitivity for exactly that reason.
set -u
cd "$(dirname "$0")/../.." || exit 1
LOG=logs/revision3
mkdir -p "$LOG"

stage () {   # tier, pass, then "model:name" pairs
  local tier="$1" pass="$2"; shift 2
  local pids=()
  for spec in "$@"; do
    local model="${spec%%:*}" name="${spec##*:}"
    local tag="${pass}__${tier}__${name}"
    echo "[start] $(date +%T) $tag"
    python scripts/revision3/run_privileged_adjudication.py \
      --judge "$model" --judge-name "$name" --tier "$tier" --pass-name "$pass" \
      --workers 6 > "$LOG/$tag.log" 2>&1 &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
  echo "[stage done] $(date +%T) $tier/$pass"
}

LADDER="gpt-5-mini:coderA_gpt5mini claude-opus-4.6:coderB_claudeopus46 gemini-3.1-pro-preview:coderC_gemini31pro"
REFPANEL="claude-opus-5:refA_claudeopus5 gpt-4.1:refB_gpt41 gemini-3.1-pro-preview:refC_gemini31pro"

for arg in "$@"; do
  case "$arg" in
    ladder-comp)  stage citing_full comparability $LADDER; stage both_full comparability $LADDER ;;
    ladder-prov)  stage citing_full provenance    $LADDER; stage both_full provenance    $LADDER ;;
    ref-comp)     stage both_full  comparability $REFPANEL; stage citing_full comparability $REFPANEL ;;
    ref-prov)     stage both_full  provenance    $REFPANEL; stage citing_full provenance    $REFPANEL ;;
    *) echo "unknown stage $arg" ;;
  esac
done
echo "[all stages complete] $(date +%T)"
