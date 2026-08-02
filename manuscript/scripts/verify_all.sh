#!/usr/bin/env bash
# Run every self-check this paper makes about itself.
#
# The submitted version shipped one verifier, which re-opened the line ranges
# named in the ledger and compared numerals.  A reviewer showed that this left
# two gaps: it never read the manuscript, so a fabricated quotation in the prose
# passed; and it never compared a reported difference to the numbers it was a
# difference of, so a gap computed on a third population passed.  Three checks
# now run, and the contribution statement claims only what they establish.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
run() {
  echo "=============================================================="
  echo "$1"
  echo "=============================================================="
  if python3 "$2"; then
    echo "-> OK"
  else
    echo "-> FAILED"
    fail=1
  fi
  echo
}

run "1/3  ledger values and quotations against their source line ranges" \
    scripts/verify_cross_paper_cases.py
run "2/3  every quotation in main.tex and its included tables" \
    scripts/verify_manuscript_quotations.py
run "3/3  every number the manuscript asserts about its own artifacts" \
    scripts/verify_prose_artifact_consistency.py

if [ "$fail" -ne 0 ]; then
  echo "AT LEAST ONE CHECK FAILED"
  exit 1
fi
echo "ALL SELF-CHECKS PASSED"
