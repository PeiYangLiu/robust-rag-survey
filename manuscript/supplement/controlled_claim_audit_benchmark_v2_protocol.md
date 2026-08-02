# Controlled claim-audit benchmark, version 2 — protocol

Artifact: `controlled_claim_audit_benchmark_v2.jsonl`
Builder: `../scripts/build_controlled_claim_audit_benchmark_v2.py` (deterministic; `--check` re-derives the file byte for byte)
Runner: `../scripts/run_controlled_model_judges_v2.py`
Analysis: `../scripts/analyze_controlled_model_judges_v2.py`
Seed: `2026072701` (benchmark), `2026072704` (item order), `2026072708` (bootstrap)

## Why version 2 exists

Version 1 (`controlled_claim_audit_benchmark.jsonl`, 480 items) had two design
defects that were identified in review and are corrected here. Both corrections
change the target specification, so v1 results are not comparable to v2 results
and are retained only as a superseded record.

1. **The utility stratum was degenerate.** In v1 the deferral cost was computed
   as `min(loss_A, loss_B) + 0.20`, so `defer` was dominated on every C5 item
   and the stratum collapsed to a binary choice. Every evaluated model scored
   at or within noise of `.500`, i.e. the half of the benchmark instantiating
   the policy/utility coordinate carried no signal.
2. **The capability stratum had a single mechanism.** In v1 an out-of-envelope
   deployment penalised both systems equally, so a capability shift always
   resolved into `defer`. A model could score well by mapping the word
   "outside" to `defer` without comparing systems.

## Design

600 items in 300 counterfactual pairs. Within a pair exactly one exogenous
quantity changes, and the change always moves the loss-minimising action.

| Stratum | Pairs | Sub-types | Exogenous change within a pair |
|---|---|---|---|
| `probe_competence` | 60 | `displayed_loss_argmin` | one displayed action loss |
| `c2_capability` | 120 | `symmetric_envelope_exit` (60), `asymmetric_envelope_exit` (60) | deployed origin / access / disturbance budget |
| `c5_utility` | 120 | `cost_regime_shift` (60), `action_set_shift` (60) | error-vs-abstention prices, or the exogenous price of a follow-up study |

**Target.** The unique minimum of the deployment-loss rule displayed in the
item text. No human label is used anywhere. The margin between the best and
second-best action is at least `0.02` on every item; the builder raises rather
than emits an item that violates this.

**Balance.** Every stratum uses all three actions and no action exceeds 60% of
that stratum's targets, so no stratum is solvable by a constant response.
Realised target counts are in `controlled_claim_audit_benchmark_v2_summary.json`.
The twelve template families are exactly balanced (50 items each).

**Stratum-specific guarantees**, all asserted by the builder:

- `c2_capability`: the deferral cost is identical for both members of a pair, so
  the capability shift is the only exogenous change. In the asymmetric sub-type
  the deployment stays inside one system's evaluated envelope and leaves the
  other's, so all 60 pairs flip between `deploy_A` and `deploy_B` rather than
  resolving into `defer`.
- `c5_utility`: the deferral price is displayed as a constant that is not
  derived from the deployment losses. `defer` is the optimal action on 65 of
  240 C5 items, so the stratum is a genuine three-way decision. In the
  `action_set_shift` sub-type the cheap variant makes `defer` optimal and the
  dear variant does not.
- `probe_competence`: all three action losses are displayed directly and the
  correct answer is their argmin. This stratum measures whether a model
  executes the stated rule at all.

## Arms

Three arms, each with four hand-written paraphrases that vary wording,
ordering, voice and layout. Every model answers every item under all twelve
prompt variants: 600 × 3 × 4 = 7,200 greedy decisions per model.

| Arm | Content |
|---|---|
| `ablated` | source support, evidence state, intervention, measured outcome and unit, ordinary controls |
| `placebo` | `ablated` plus generic reading instructions of matched length that name neither capability nor utility content |
| `full` | `ablated` plus explicit origin/capability (C2) and policy/utility (C5) checks |

**Primary contrast: `full` − `placebo`.** The placebo arm exists so that the
contrast is not confounded with instruction length or verbosity; system-prompt
token counts for both arms are recorded in each run summary. `full` − `ablated`
is reported as a secondary contrast and is *not* interpreted as a coordinate
effect.

## Pre-declared validity gate

Fixed before the reported runs. A model enters the primary analysis only if

- it reaches ≥ 50% accuracy on `probe_competence` in at least one arm, and
- it emits no single action on more than 90% of all items.

Rationale: a model that cannot select the minimum of three displayed numbers is
not performing the task, and a constant predictor carries no information about
prompt sensitivity. Gate status, probe accuracy, modal-decision share and parse
failure rate are reported for every model whether or not it passes.

## Analysis

- Uncertainty: percentile bootstrap clustered on the 300 counterfactual pairs,
  which is the unit the benchmark varies. 4,000 draws.
- Paraphrase sensitivity: the spread of the primary contrast across the four
  paraphrases is reported alongside the point estimate.
- Exact McNemar tests on per-item paraphrase-majority decisions.
- Multiplicity: Holm across gate-passing models × {`c2_capability`, `c5_utility`}.
- Model population: DerSimonian–Laird random-effects combination across
  gate-passing models, so the pooled effect refers to a model population rather
  than to a checkpoint.
- `probe_competence` acts as an internal negative control: a coordinate prompt
  should not help where the answer is a direct comparison of displayed losses.

## Decoding and provenance

Greedy decoding (`do_sample=False`), `max_new_tokens=24`, left padding, item
order shuffled once by a fixed seed. Each output record carries the benchmark
record hash, the prompt hash, the model commit hash, and the transformers and
torch versions. Runs reported in the paper used float16 on V100 hardware; the
`amlt` configuration in `configs/amlt_controlled_model_judges_v2.yaml` runs the
same script on A100 hardware.

## Interpretation boundary

These items are templated arithmetic prose with a synthetic loss rule. Results
are construct evidence about what naming a coordinate does to a model's
deployment choice under a consequence-defined target. They are **not** evidence
about human auditors, they do not validate the coordinates as a coding
instrument, and they do not predict behaviour on natural paper prose. The
evaluated checkpoints are a convenience sample of open instruction-tuned
models, not a defined model population; the random-effects interval quantifies
heterogeneity across the models actually run.

## Correction history

The v1 C2 generator changed the deferral cost together with the capability
condition; that confound was found after outcomes were observed, corrected, and
every reported model rerun. v2 asserts deferral-cost invariance within C2 pairs
in the builder. v2 was constructed after the v1 outcomes were known, so the
benchmark family is not preregistered; the validity gate, the arm definitions
and the primary contrast were fixed before any v2 model was run.
