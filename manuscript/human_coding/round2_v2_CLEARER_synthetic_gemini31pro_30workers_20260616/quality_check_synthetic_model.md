# Synthetic Gemini 3.1 Pro 30-worker annotation QC

Generated on 2026-06-16 UTC.

This directory contains model-generated synthetic annotations, not human annotations.
The outputs are marked with `synthetic_not_human=1` where applicable and must not be
reported as human-verified evidence.

## Completeness

- Model: `gemini-3.1-pro-preview`
- Endpoint: `http://127.0.0.1:4141/v1/chat/completions`
- Worker concurrency used: 30
- Pair count: 48
- Synthetic participants: 30
  - control: 8
  - protocol: 8
  - coordinate_gold: 7
  - independent_gold: 7
- Raw successful task keys: 1440 / 1440
- Per-participant coverage: 48 / 48 for all 30 participants
- Failed task file: none

## Output Counts

- `participant_responses_synthetic_model.csv`: 768 rows
- `coordinate_gold_individual_synthetic_model.csv`: 336 rows
- `coordinate_gold_consensus_synthetic_model.csv`: 48 rows
- `independent_gold_individual_synthetic_model.csv`: 336 rows
- `independent_gold_consensus_synthetic_model.csv`: 48 rows
- `annotator_metadata_anonymized.csv`: 30 rows

## Consensus Distributions

Coordinate gold consensus:

- valid: 0
- partial: 22
- invalid: 16
- under-specified: 10

Independent gold consensus:

- can_rank / valid: 0
- rank_with_caveats / partial: 17
- cannot_rank / invalid: 30
- not_enough_info / under-specified: 1

Participant arm responses:

- control: invalid 356, partial 28, valid 0, under-specified 0
- protocol: invalid 133, partial 169, under-specified 68, valid 14

## Protocol QC Result

This synthetic run does not pass the collapse checks in
`annotation_protocol_round2_v2_CLEARER_20260615.md` section 8:

- Coordinate gold consensus has 0 `valid` labels.
- Independent gold consensus has 0 `can_rank` / `valid` labels.
- Every control annotator has 0 `valid` and 0 `under-specified`.
- Several coordinate gold individuals have 0 `valid`.

The run is complete as a 30-worker synthetic model annotation job, but it should
not be accepted as a valid round-2 annotation result under the protocol. The
main failure appears to be pair construction: the hidden heuristic `valid`
pairs are often not clear valid instances under the v2.1 decision tree.
