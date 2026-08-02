# Published-Claim Comparability Audit Codebook, v2

Version: 2026-07-14

Status: **frozen codebook evaluated in the negative reliability study; not a
validated classifier**. The post-study v3 draft separates ordinary evidence
support from comparability and is not used to relabel these data.

This held-out codebook was fixed after a development audit on different
sources. The unit is an atomic published comparative claim. The task is to
encode evidence, not to choose a verdict freely. A deterministic script derives
the three-field, five-coordinate, and full-control verdicts.

## 1. Unit check

Use `include` when the quote plus supplied context compares at least two
methods, conditions, signals, actions, outcomes, or operating points. Use
`exclude_not_comparative` only for a definition or a one-sided statement with
no recoverable comparator. Do not exclude a claim because it appears weak,
wrong, or under-specified.

## 2. Primary claim archetype

Choose exactly one:

- `A_self_baseline`: one method or configuration versus its own baseline or
  ablation in a shared experiment.
- `B_shared_harness`: two or more methods, models, conditions, or policies
  compared in the same experimental harness.
- `C_cross_source_synthesis`: a survey or paper aggregates results from
  independently run studies.
- `D_causal_mechanistic`: the central claim attributes an observed difference
  to a cause or mechanism.
- `E_field_meta`: the claim states that a benchmark, metric, method family, or
  shared harness is absent, incomplete, incomparable, or dominant in a field.
- `F_policy_utility`: the central comparison concerns which action to take or a
  trade-off among answer, abstain, retrieve, clarify, verify, or another policy.

When a sentence reports both a result and an explanation, split candidates
should already separate them. If not, choose `D_causal_mechanistic` for the
explanation and `B_shared_harness` for the measured result.

## 3. Claim strength

Choose one:

- `descriptive`
- `directional`
- `rank_or_superlative`
- `causal`
- `field_absence_or_incommensurability`
- `normative_policy`

## 4. Five coordinates

For each side or compared group, record the value and then a relation:
`aligned`, `different`, `mixed`, `unknown`, or `not_applicable`.

### C1. Evidence state

The evidence condition visible at the RAG decision boundary:

`supported`, `irrelevant_or_distracting`, `insufficient`, `conflicting`,
`stale_or_low_provenance`, `adversarially_manipulated`, `mixed`,
`not_evidence_conditioned`, or `unreported`.

Query ambiguity, OOD input, model uncertainty, and attacker access are not
evidence states by themselves.

### C2. Origin and capability assumption

How the evidence condition arose:

`benign_retrieval`, `benchmark_constructed`, `natural_conflict_or_drift`,
`query_or_distribution_shift`, `attacker_created`, `shared_clean_harness`,
`mixed`, `not_applicable`, or `unreported`.

For attacks, inspect access, budget, visibility, and objective when the claim
depends on them.

When both sides of C1 are `not_evidence_conditioned`, C2 is
`not_applicable`, not `unreported`: the origin of an evidence condition is not
decision-critical when the claim does not condition on evidence.

### C3. Intervention

The component or condition that differs:

`corpus_or_index`, `retriever`, `reranker_or_filter`,
`context_assembly_or_compression`, `generator_prompt_or_decoding`,
`generator_training`, `verifier`, `system_controller_or_routing`,
`model_family_scale_or_alignment`, `evaluation_only`, `multiple_components`,
`none`, or `unreported`.

Different interventions can be legitimate alternatives in a shared harness.
Do not treat intervention difference alone as a full-framework failure.

### C4. Outcome and unit

`answer_correctness`, `retrieval_quality`, `evidence_or_citation_support`,
`conflict_resolution`, `attack_or_defense_utility`, `privacy_leakage`,
`calibration`, `selective_risk_coverage`, `action_utility`, `cost_latency`,
`human_preference`, `composite_score`, `qualitative_field_conclusion`, or
`unreported`.

The relation is `aligned` only when definition, direction, aggregation, and
evaluation unit match. Relative gains over different baselines are not
automatically aligned.

### C5. Policy and utility context

`answer`, `abstain`, `re_retrieve`, `filter`, `verify`, `expose_conflict`,
`clarify`, `quarantine`, `recover`, `mixed_multistep`,
`not_applicable`, or `unreported`.

Use `not_applicable` for a fixed descriptive comparison that does not ask which
system action is preferable. This never causes a downgrade. Use `answer` only
when answer-only behavior is decision-relevant to the claim.

Set `utility_required=yes` only when the claim ranks or recommends different
actions, operating points, risk-coverage choices, or cost-quality policies.
Fixed answer-accuracy comparisons do not require a utility function. If
utility is required, record whether stakes, costs, preferences, or a scalar
utility are actually supplied.

## 5. Evidence flags

- `factual_match`: `yes`, `no`, or `unknown`. Check whether quoted numbers,
  orderings, and qualifiers match the cited table or figure.
- `counterexample_status`: `none`, `found`, or `unknown`. Claims using
  all/every/always/consistently/best require an explicit scan for contrary rows.
- `manipulation_or_ablation`: `yes`, `no`, `unknown`, or `not_applicable`.
  A causal claim can reach `valid` only if a manipulation or ablation isolates
  the claimed mechanism. Observational association alone preserves at most a
  narrower association.
- `field_audit_support`: `yes`, `partial`, `no`, `unknown`, or
  `not_applicable`. A field-level absence or incommensurability claim must be
  supported by a coverage table, documented search, or inspectable evidence,
  not the source's prose alone.

## 6. Claim-specific controls

Record the minimal controls required by the claim and their status:

- dataset and split
- corpus and evidence set
- retriever, chunking, and top-k
- generator and scale
- prompt, decoding, and context budget
- baseline definition
- metric implementation and aggregation
- compute or latency budget
- repeated runs, uncertainty, and statistical test

Use `aligned`, `partial`, `unmatched`, `unknown`, or `not_applicable`. Set
`controls_critical_missing=yes` only when a missing control prevents deciding
the claim, not merely because every possible implementation detail is absent.

Archetype defaults:

- A: baseline definition, metric implementation, and changed component.
- B: dataset/split, evidence set, generator, prompt/decoding, baseline, metric;
  include cost only for efficiency claims.
- C: all B controls across every source plus uncertainty for pooled claims.
- D: the relevant A/B/C controls plus an isolating manipulation or ablation.
- E: documented source coverage and screening/audit support.
- F: common action set, operating points or matched coverage, and utility/cost
  when policies differ.

## 7. Deterministic verdict rules

Coders do not output verdicts. `derive_verdicts_v2.py` applies the following
fixed rules.

### Three-field baseline

Use C1, C3, and C4 only:

1. Any `unknown` relation gives `under-specified`.
2. Different or mixed C1 or C4 gives `invalid`.
3. Different or mixed C3 gives `partial`.
4. Otherwise the result is `valid`.

This is intentionally a simple taxonomy-only baseline. It is not the paper's
preferred decision rule.

### Five coordinates without experimental controls

1. A factual mismatch or a direct counterexample gives `invalid`.
2. Unknown C1, C2, or C4 gives `under-specified`; unknown C5 matters only for
   archetype F or when utility is required.
3. Different/mixed C1 or C4 gives `invalid` for A, B, D, and F, and `partial`
   for C or E.
4. Different/mixed C2 gives `partial` for cross-source or field-level synthesis
   (C or E). In A/B shared-harness experiments, capability can be the controlled
   factor being compared and therefore does not by itself downgrade a
   descriptive result. D follows its manipulation/ablation rule, while F
   follows the common-utility rule. A cross-game ranking from independently
   run studies belongs to C, not B.
5. Different/mixed C5 is allowed only under a reported common utility. Without
   one, a rank/recommendation is `invalid`; a descriptive contrast is `partial`.
6. C3 difference alone does not downgrade this stage.
7. Archetype C is capped at `partial` for cross-study ranks or family
   generalizations, but a correctly scoped descriptive report can be `valid`.
8. Archetype D is capped at `partial` without an isolating manipulation or
   ablation.
9. Archetype E is `valid`, `partial`, `invalid`, or `under-specified` according
   to `field_audit_support`.
10. Archetype F with required but unreported utility is `invalid` for a
    recommendation/rank and `partial` for a descriptive trade-off.

### Full verdict with controls

Start from the five-coordinate verdict:

- factual mismatch or direct counterexample remains `invalid`;
- `unmatched` controls downgrade `valid` to `partial`. A `partial` verdict
  remains `partial` when a concrete `narrower_supported_claim` is recorded;
  otherwise it becomes `invalid`;
- `partial` controls downgrade `valid` to `partial`;
- `unknown` controls with `controls_critical_missing=yes` give
  `under-specified`;
- otherwise retain the five-coordinate verdict.

`partial` requires a narrower supported claim. `under-specified` must name the
specific missing field or control.

## 8. Model-only validation boundary

Independent model coding measures whether the executable codebook yields
stable structured decisions on held-out claims. It does not establish human
expert validity. Agreement and factual correctness are separate: a
source-linked adjudication pass is still required, and any released output
must be marked `synthetic_model_coding_not_human`.
