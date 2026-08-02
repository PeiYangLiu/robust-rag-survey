#!/usr/bin/env bash
# Draw every PowerPoint figure and export it to vector PDF for LaTeX.
# The .pptx files are the editable source and are released with the paper.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=figures/generated
mkdir -p "$OUT"
for f in fig_motivating_case fig_instrument fig_interventions fig_taxonomy_map fig_screening_flow fig_corpus_lineage fig_decision_flow fig_two_layer fig_benchmark_landscape fig_failure_matrix; do
  case "$f" in
    fig_taxonomy_map) python scripts/revision3/fig_appendix_taxonomy.py >/dev/null ;;
    fig_screening_flow|fig_corpus_lineage|fig_decision_flow|fig_two_layer)
      python scripts/revision3/fig_appendix_flows.py >/dev/null ;;
    fig_benchmark_landscape|fig_failure_matrix)
      python scripts/revision3/fig_appendix_schematics.py >/dev/null ;;
    *) python "scripts/revision3/$f.py" >/dev/null ;;
  esac
  rm -f "$OUT/$f.pdf"
  libreoffice --headless --convert-to pdf --outdir "$OUT" "$OUT/$f.pptx" >/dev/null 2>&1
  # crop the slide canvas to its ink so LaTeX sees no dead margin
  pdfcrop --margins 1 "$OUT/$f.pdf" "$OUT/$f-crop.pdf" >/dev/null 2>&1 \
    && mv "$OUT/$f-crop.pdf" "$OUT/$f.pdf"
  echo "built $OUT/$f.pdf"
done
