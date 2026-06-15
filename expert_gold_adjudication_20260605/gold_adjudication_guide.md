# Independent Gold Adjudication Guide for Robust-RAG Comparability

## Purpose

This gold-adjudication round creates an **independent external gold standard** for judging whether pairs of robust-RAG papers are directly comparable.

The task is not to decide which paper is better. The task is to decide whether a direct comparison or leaderboard-style ranking would be valid.

This round is separate from the blind control/protocol annotation batch. Gold adjudicators should not see the rulebook expected verdicts or the previous annotator distributions.

## Key principles

1. Do **not** inspect internal reference verdicts.
   - Do not use `expert_validation/paper_pairs.csv`.
   - Do not inspect `expert_validation_blind_batch_A_20260605/`.

2. The panel may use the five-coordinate protocol, but should not be constrained by the authors' original rulebook labels.
   - If the panel believes an original rulebook verdict is wrong, the panel verdict should become the gold label.

3. Each final gold verdict must include a gold rationale.
   - A label without a rationale is not sufficient.
   - The rationale should identify the coordinate(s) that make the comparison valid, partial, invalid, or under-specified.

## Recommended workflow

### Phase 1: independent annotation

Each adjudicator independently fills:

`gold_individual_annotation_template.csv`

Input file:

`paper_pairs_for_gold_adjudication.csv`

### Phase 2: panel adjudication

After independent annotation, adjudicators discuss disagreements and fill:

`gold_panel_adjudication_template.csv`

The final panel file should include:

- `final_gold_verdict`
- `final_gold_rationale`
- `final_breaking_coordinates`
- `what_valid_comparison_requires`
- `disagreement_summary`
- `rulebook_revision_needed`

### Phase 3: analysis update

Copy `final_gold_verdict` into the `external_gold_verdict` column of the analysis pair file, then rerun the control/protocol comparison.

## Verdict definitions

| Verdict | Meaning |
| --- | --- |
| `valid` | The two papers can be directly compared as substitutes for the same robust-RAG question. A leaderboard-style comparison is meaningful. |
| `partial` | The papers are related, but differ in intervention point, metric target, action policy, assumption, or another non-fatal coordinate. They should be compared as complementary components or operating regions, not direct substitutes. |
| `invalid` | The papers define incompatible games or assumptions. A direct ranking would be misleading. |
| `under-specified` | The available paper information omits a coordinate needed to decide, such as action policy, attacker capability, metric target, or evidence assumption. |

## Five-coordinate protocol

| Coordinate | Allowed values / guidance |
| --- | --- |
| Failure type | `relevance/noise`; `sufficiency`; `consistency/conflict`; `provenance/freshness`; `integrity/adversarial corruption`; `uncertainty/OOD`. |
| Evidence assumption | `benign retrieval error`; `benchmark-constructed stressor`; `naturally occurring conflict`; `stale or low-quality source`; `attacker-created evidence`; `privacy or extraction threat`. For security pairs, also inspect corpus write access, query control, retriever visibility, generator access, insertion budget, and attack objective. |
| Intervention point | `corpus/index`; `retriever`; `reranker`; `context assembly/compression`; `generator prompting or training`; `verifier`; `system-control policy`; `evaluation artifact`. |
| Metric target | `answer correctness`; `retrieval recall`; `evidence support`; `citation faithfulness`; `attack success`; `calibration error`; `selective risk/coverage`; `cost/latency`; `human preference`. |
| Action policy | `answer`; `abstain`; `re-retrieve`; `filter`; `verify`; `expose conflict`; `ask clarification`; `escalate`; `quarantine`; `recover`; `unreported`. |

Important action rule:

> The action policy cannot be inferred from a generic QA setup. If a paper does not explicitly state or evaluate the action policy, the comparison should normally not receive a `valid` verdict.

The panel should decide whether a missing action policy makes the comparison `partial` or `under-specified`:

- Use `partial` when the remaining coordinates are sufficient to conclude that the papers are related but not substitutes.
- Use `under-specified` when missing action or threat-model information prevents a reliable comparability judgment.

## Gold rationale requirements

A good gold rationale should state:

1. What the two papers share.
2. Which coordinate(s) diverge.
3. Why the divergence supports the final verdict.
4. What experiment, metric, or report would be required to make the comparison valid.

## Files to send to the gold panel

Send:

- `paper_pairs_for_gold_adjudication.csv`
- `gold_adjudication_guide.md` or `gold_adjudication_guide_zh.md`
- `gold_individual_annotation_template.csv`
- `gold_panel_adjudication_template.csv`
- paper PDFs or official paper links

Do not send:

- `expert_validation/paper_pairs.csv`
- any previous response file
- any previous analysis summary
- any file containing rulebook expected verdicts

