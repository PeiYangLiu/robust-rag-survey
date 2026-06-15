# Completed Comparability Expert-Use Study Package

This directory contains the anonymized artifacts for the blind expert-use pilot
reported in the manuscript.

## Study design

- 30 anonymized annotators.
- 12 paper pairs per annotator.
- 360 total pairwise judgments.
- Balanced conditions:
  - 15 annotators used ordinary expert judgment (`control`).
  - 15 annotators used the five-coordinate comparability lens (`protocol`).
- A separate blind gold-adjudication packet produced external gold verdicts and
  rationales for all 12 pairs.

## Main files

- `expert_responses_full.csv`: full anonymized responses, including verdicts,
  confidence, timing, usefulness, five-coordinate fields, rationales, error
  types, and rationale-quality scores.
- `expert_responses_minimal.csv`: reviewer-facing minimal response file without
  timing/confidence/usefulness/rationale-quality fields.
- `participant_assignment_log.csv`: anonymized condition assignment log.
- `annotator_metadata_anonymized.csv`: public qualification metadata. Detailed
  identities and credentials are not included in the public artifact; annotators
  are represented only by anonymized IDs.
- `external_gold_panel.csv`: final external gold verdicts and rationales.
- `external_gold_votes.csv`: individual gold-adjudication votes.
- `paper_pairs_with_external_gold.csv`: paper pairs with final external gold
  labels applied.
- `external_gold_analysis/`: analysis outputs when using external gold as the
  reference.
- `analyze_blind_batch.py`: script used to compute condition summaries,
  participant summaries, pair summaries, bootstrap intervals, and the LaTeX
  result table.
- `manifest.json`: checksummed manifest for the package.

## Reproducing the main result

From the repository root:

```bash
python3 manuscript/human_coding/comparability_user_study_package/analyze_blind_batch.py \
  manuscript/human_coding/comparability_user_study_package/expert_responses_full.csv \
  manuscript/human_coding/comparability_user_study_package/paper_pairs_with_external_gold.csv \
  /tmp/comparability_user_study_recheck
```

The external-gold analysis reports 30 annotators, 360 judgments, and agreement
with external gold of 0.800 for the control condition and 0.978 for the protocol
condition.
