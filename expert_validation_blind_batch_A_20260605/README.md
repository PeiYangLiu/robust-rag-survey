# Blind expert validation batch A (2026-06-05)

This directory contains the first completed blind external expert-use annotation batch.

## Raw response files

- `responses.csv`: full response file with confidence, timing, usefulness, five-coordinate fields, rationales, error types, and rationale-quality scores.
- `responses_reviewer_minimal.csv`: reviewer-facing minimal response file without timing/confidence/usefulness/rationale-quality fields.

## Analysis outputs

- `analysis_summary.md`: human-readable summary.
- `condition_summary.csv`: control/protocol aggregate metrics.
- `condition_differences_bootstrap.csv`: participant-level bootstrap intervals for protocol minus control.
- `participant_summary.csv`: participant-level metrics.
- `pair_summary.csv`: pair-level metrics.

## Main result with external gold

Thirty annotators completed all 12 paper-pair judgments: 15 in the control condition and 15 in the protocol condition. Using the independently adjudicated external gold labels from `../expert_gold_adjudication_blind_review_packet_20260605/`, the protocol condition improved agreement from 0.800 to 0.978 and Fleiss kappa from 0.589 to 0.846.

The original rulebook-reference analysis is preserved in the top-level summary files. The external-gold analysis is in `external_gold_analysis/`.
