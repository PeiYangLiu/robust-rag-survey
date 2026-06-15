# Expert Annotation Guide: Comparing Robust-RAG Papers under Unreliable Evidence

## Purpose

This annotation study asks independent experts to judge whether pairs of robust retrieval-augmented generation (RAG) papers can be directly compared.

The task is **not** to decide which paper is better. The task is to decide whether a direct comparison or leaderboard-style ranking would be valid.

## Study design

Use two conditions.

### Control condition

Send these files:

- `instructions_control.txt`
- `paper_pairs_for_annotation.csv`
- `participant_response_template_control.csv`

Control participants use ordinary expert judgment. Do **not** provide the five-coordinate protocol.

### Protocol condition

Send these files:

- `instructions_protocol.txt`
- `paper_pairs_for_annotation.csv`
- `participant_response_template_protocol.csv`

Protocol participants apply the five-coordinate protocol and verdict rules.

> Important: do **not** send `paper_pairs.csv` to participants. That file contains internal reference verdicts and would leak the answer key.

Participants should annotate independently and should not discuss the task with each other. If possible, recruit RAG, IR, NLP, or security researchers who did not design the codebook.

## Files in the package

| File | Purpose |
| --- | --- |
| `expert_annotation_guide.md` | English coordinator guide. |
| `annotation_guide_zh.md` | Chinese coordinator guide. |
| `instructions_control.txt` | Participant-facing instructions for the control condition. |
| `instructions_protocol.txt` | Participant-facing instructions for the protocol condition. |
| `paper_pairs_for_annotation.csv` | Participant-facing paper-pair list without reference verdicts. |
| `participant_response_template_control.csv` | Response sheet for control participants. |
| `participant_response_template_protocol.csv` | Response sheet for protocol participants. |
| `paper_pairs.csv` | Internal reference file; do not send to participants. |
| `analyze_expert_validation.py` | Analysis script for collected responses. |

## What participants should annotate

Each row in `paper_pairs_for_annotation.csv` contains two papers. For each pair, the participant chooses one verdict:

| Verdict | Meaning |
| --- | --- |
| `valid` | The two papers can be directly compared as substitutes for the same robust-RAG question. A leaderboard-style comparison is meaningful. |
| `partial` | The papers are related, but differ in intervention point, metric target, action policy, or another non-fatal coordinate. They should be compared as complementary components or operating regions, not direct substitutes. |
| `invalid` | The papers define incompatible games or assumptions. A direct ranking would be misleading. |
| `under-specified` | The available paper information omits a coordinate needed to decide. Missing action policy should usually produce this verdict. |

## Protocol-condition codebook

Protocol-condition participants should code five coordinates.

| Coordinate | Allowed values / guidance |
| --- | --- |
| Failure type | `relevance/noise`; `sufficiency`; `consistency/conflict`; `provenance/freshness`; `integrity/adversarial corruption`; `uncertainty/OOD`. |
| Evidence assumption | `benign retrieval error`; `benchmark-constructed stressor`; `naturally occurring conflict`; `stale or low-quality source`; `attacker-created evidence`; `privacy or extraction threat`. For security cases, note corpus write access, query control, retriever visibility, generator access, insertion budget, and objective when reported. |
| Intervention point | `corpus/index`; `retriever`; `reranker`; `context assembly/compression`; `generator prompting or training`; `verifier`; `system-control policy`; `evaluation artifact`. |
| Metric target | `answer correctness`; `retrieval recall`; `evidence support`; `citation faithfulness`; `attack success`; `calibration error`; `selective risk/coverage`; `cost/latency`; `human preference`. |
| Action policy | `answer`; `abstain`; `re-retrieve`; `filter`; `verify`; `expose conflict`; `ask clarification`; `escalate`; `quarantine`; `recover`; `unreported`. |

### Protocol verdict rules

1. `valid`: all five coordinates align. The action policy must be explicitly stated or evaluated; it cannot be inferred from a QA setup.
2. `partial`: the failure type is shared, but the intervention point, metric target, or action policy differs.
3. `invalid`: the evidence assumption or objective defines a different game, such as natural conflict versus attacker-created corruption.
4. `under-specified`: at least one coordinate needed for comparison is unobtainable from the paper description. Missing action policy caps the verdict at `under-specified`.

## Response fields

| Field | How to fill |
| --- | --- |
| `participant_id` | Anonymous ID assigned by the coordinator, e.g., `E01`. |
| `condition` | `control` or `protocol`. |
| `pair_id` | Copy from `paper_pairs_for_annotation.csv`. |
| `verdict` | One of `valid`, `partial`, `invalid`, `under-specified`. |
| `confidence_1_5` | 1 = very uncertain, 5 = very confident. |
| `decision_time_seconds` | Time spent on this pair, in seconds. Approximate timing is acceptable. |
| `usefulness_1_5` | How useful the available information/instructions were for this decision; 1 = not useful, 5 = very useful. |
| `failure_type`--`action_policy` | Protocol condition only. Fill the five coordinates. Control participants leave these absent or blank. |
| `breaking_coordinates` | Protocol condition: semicolon-separated coordinates that block direct comparison, e.g., `intervention;metric;action`. |
| `rationale` | One or two sentences explaining the verdict. |
| `error_type` | Optional; examples: `missing_action`, `threat_model_missing`, `metric_mismatch`, `intervention_mismatch`. |

## Recommended coordinator workflow

1. Assign each expert an anonymous participant ID.
2. Randomly assign experts to control or protocol. Balance conditions if possible.
3. Send only the files for that condition, plus paper PDFs or official paper links.
4. Ask experts to annotate independently and record time per pair.
5. Merge all completed response CSVs into one `responses.csv`.
6. Run:

```bash
python3 analyze_expert_validation.py responses.csv paper_pairs.csv
```

If an independently adjudicated gold file is available, fill `external_gold_verdict` in `paper_pairs.csv`. Otherwise the script uses `rulebook_expected_verdict` and will report the result as rulebook agreement rather than external validity.

## Minimum useful sample

- Minimal pilot: 4--6 independent experts and 12 paper pairs.
- Stronger EACL version: 8--12 experts, balanced across control and protocol conditions.
- Ideal: experts come from RAG, IR, NLP, or security, and did not participate in designing the codebook.

## Reportable metrics after collection

After collecting real expert responses, the paper can report:

- control vs. protocol verdict agreement
- Fleiss kappa or Cohen kappa
- agreement with independently adjudicated gold rationales
- mean decision time
- mean confidence
- usefulness score
- error type distribution
- rationale quality

If no independent external gold exists, report only agreement with the rulebook reference and do **not** claim external validity.
