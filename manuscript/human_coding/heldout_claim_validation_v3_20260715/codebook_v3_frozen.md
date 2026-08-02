# Published-claim audit codebook v3 — frozen

**Status: FROZEN BEFORE HELD-OUT TEST LABEL COLLECTION**  
Version: `v3.0.0`  
Freeze date: 2026-07-15  
Development basis: v3 draft, identifiable v1 validation lineage, and the
prior nine-source v2 development study  
Permitted test use: only under `preregistered_protocol.md`

No held-out test response was inspected in preparing this codebook. Future test
labels cannot be used to revise v3. Any later revision must receive a new
version and a new paper-disjoint test.

Map B literature informed broad domain concepts; “held-out” here means
paper-disjoint from identifiable v1/v2 claim-level development and validation
sources, not wholly unseen to the survey's literature map.

## 1. Two outputs, never one verdict

### 1.1 Evidence-support label

This label asks whether the cited source supports the claim's wording.

- `supported_as_written`: the located source evidence supports the material
  proposition, direction, magnitude, quantifier, scope, and causal force.
- `supported_after_narrowing`: a specific, nontrivial narrowing makes the claim
  supportable; record that wording.
- `contradicted`: located source evidence conflicts with a material part of the
  claim.
- `insufficient_source_evidence`: the supplied and locatable source material
  does not permit the proposition to be checked.

### 1.2 Comparability label

This label asks whether the compared sides estimate the same scientific
quantity at the scope asserted by the claim.

- `same_estimand`: the relevant quantity, unit, setting, and decision target
  align without an additional scope restriction.
- `comparable_with_declared_scope`: a comparison is defensible only under a
  scope restriction that the reviewer must state.
- `different_estimand`: the sides answer materially different scientific
  questions, so the asserted ranking, transfer, or pooling is not meaningful.
- `missing_comparison_assumption`: comparability could be established, but a
  decision-critical assumption or control is unreported; name the missing
  assumption and the inference it blocks.
- `not_a_comparability_claim`: the sentence does not rank, contrast, transfer,
  pool, or recommend across alternatives.

The outputs are recorded independently. For example, a faithful numerical
transcription can be evidence-supported while making an invalid cross-study
comparison. Conversely, an unsupported number does not automatically imply
that the compared quantities differ. No deterministic function collapses the
two labels.

## 2. Evidence-support gate

Complete these checks against the full source before diagnosing comparability.

1. **Numbers and direction.** Recompute quoted differences, ratios, orderings,
   and signs from the cited table, figure, or passage.
2. **Quantifiers.** For words such as `all`, `always`, `consistently`, `best`,
   or `never`, inspect every result in the stated scope.
3. **Causal force.** A mechanism claim requires an intervention, ablation,
   randomization, or identified natural experiment that isolates the proposed
   cause. Otherwise only association is supported.
4. **Field coverage.** Absence, dominance, or incommensurability claims require
   a documented sampling frame and coverage audit.
5. **Attribution.** A faithful statement that a cited study reported a result
   is assessed as an attributed report unless the sentence independently
   endorses, transfers, or generalizes it.
6. **Location.** Record the exact page, table, figure, or passage used. Search
   failure is not contradiction; it is insufficient evidence.

Record the evidence-support label and reason before beginning the final
comparability composition stage.

## 3. When comparability applies

Comparability analysis applies when a claim does at least one of the following:

- ranks or contrasts systems, methods, policies, operating points, or study
  families;
- transfers a result across evidence or threat settings;
- pools independently run results; or
- recommends one action or operating point over another.

Pure transcription, mechanism description, field-coverage, and
causal-identification claims receive `not_a_comparability_claim` unless they
also perform one of those comparisons.

## 4. Full-v3 diagnostic fields

For each applicable claim, extract each side separately. A difference is not
automatically a failure. The relation question determines whether the
difference changes the claim's scientific target.

### C1. Evidence state

Record what reaches the system at its decision boundary:
`supported`, `irrelevant_or_distracting`, `insufficient`, `conflicting`,
`stale_or_low_provenance`, `adversarially_manipulated`, `mixed`,
`not_evidence_conditioned`, or `unreported`.

Relation question: **Would the claimed direction still answer the same
scientific question if the two evidence-state descriptions were exchanged?**
Use `aligned_for_claim`, `estimand_shift`, or `missing`.

Do not infer use from availability. Evidence may be present but ignored, or
absent while parametric memory determines the answer.

### C2. Origin or attacker capability

Record how the evidence condition arose: benign retrieval, benchmark
construction, natural conflict or drift, distribution shift, attacker
creation, or a shared clean harness. For an attack, record corpus access,
query knowledge, retriever visibility, insertion budget, target scope, and
adaptive access when reported.

Relation question: **Does the conclusion transfer across the two origin or
capability envelopes without changing its scope?** A descriptive mechanism
report does not fail merely because envelopes differ; an effectiveness rank
or broad transfer claim may.

Use `aligned_for_claim`, `comparable_with_scope`, `estimand_shift`, or
`missing_decision_critical`.

### C3. Intervention

Record the changed component and unchanged pipeline. Different interventions
are expected in a method comparison and do not constitute a mismatch by
themselves.

Relation question: **Are these alternative ways to optimize the same outcome
in the same harness, complementary stages, or incomparable roles such as a
benchmark versus a mitigation?**

Use `alternative_same_role`, `complementary_roles`, `incomparable_roles`, or
`missing`.

### C4. Outcome and unit

Record outcome definition, direction, aggregation, evaluation unit, baseline,
and uncertainty. Relative improvements with different denominators are not the
same quantity.

Relation question: **Can both quantities be written as the same estimand with
the same unit, aggregation, and denominator?**

Use `same_estimand`, `transformable_with_declared_rule`,
`different_estimand`, or `missing`.

### C5. Policy and utility

Record the externally scored action, alternatives, operating point, coverage,
stakes, and costs. Fixed answer-quality comparisons with no action choice are
`not_applicable`.

Relation question: **Does a shared utility or explicitly matched operating
point order the competing actions?** A descriptive trade-off can be reported
without a universal preference. A normative recommendation requires the
relevant costs or operating point.

Use `shared_or_matched`, `descriptive_tradeoff_only`,
`missing_decision_critical`, `different_decision_problem`, or
`not_applicable`.

## 5. Claim-specific controls

Select controls from the claim target before looking at which method wins.

| Claim target | Required controls |
| --- | --- |
| Answer or retrieval quality | dataset/split, evidence set, generator, prompt/decoding, baseline, metric |
| Efficiency | all quality controls plus hardware, batching, latency/compute budget |
| Security effectiveness | clean utility plus capability envelope, attack budget, adaptive access |
| Selective policy | action set, matched coverage or operating points, risk definition, cost/utility |
| Cross-study synthesis | every required within-study control plus uncertainty and aggregation |

For each required control, use `reported_aligned`, `reported_different`,
`unreported_but_noncritical`, or `unreported_decision_critical`. For a missing
critical control, state the exact inference it blocks. Do not treat every
unreported implementation detail as decision-critical.

## 6. Extraction and composition records

The extraction record must contain:

1. exact claim and source location;
2. source-linked result facts;
3. compared sides;
4. fields required by the assigned arm; and
5. required controls and what the source reports.

The extraction record is locked and hashed before the composition screen opens.
Composition then records the evidence-support label and reason, narrower
supported wording when needed, comparability label and reason, supported scope,
and unresolved information. Corrections are append-only.

## 7. Frozen arm modules

### Arm A: conventional source verification

Use Sections 1--3 only as the common output vocabulary. Verify the full text,
numbers, direction, quantifiers, scope, causal language, and ordinary
experimental controls using normal scientific-review practice. Do not use a
PICO worksheet or any v3 diagnostic field.

### Arm B: PICO-style review plus standard controls

Before composition, extract:

- population or experimental setting;
- intervention;
- comparison;
- outcome, direction, unit, aggregation, and baseline; and
- standard controls relevant to the claim target.

Use Sections 1--3 as the common output vocabulary. Do not use the v3 diagnostic
field names or definitions.

### Arm C: v3 evidence and controls with C2/C5 ablated

Use Sections 1--3, C1, C3, C4, and Section 5. Do not receive or reconstruct the
C2 or C5 prompt, definition, extraction column, relation value, or any value
imputed from another arm. Do not automatically mark omitted fields aligned.
The raw source remains unredacted.

### Arm D: full v3

Use all sections of this codebook, including C1--C5 and the claim-specific
control matrix.

## 8. Plain-language expert reference rubric

Only the text between the following markers is placed in gold-expert and
adjudicator packets. It is an independent scientific rubric, not a request to
match an arm's intermediate fields.

### BEGIN PLAIN-LANGUAGE REFERENCE RUBRIC

Read the exact claim, its surrounding context, and the cited full source.
Record the source passages and calculations that justify each answer.

**Question 1: Does the source support the sentence?**

- Choose `supported_as_written` when the source supports the important
  proposition, direction, magnitude, quantifier, scope, and causal strength.
- Choose `supported_after_narrowing` when a specific narrower sentence is
  supported; write that sentence.
- Choose `contradicted` when source evidence conflicts with an important part
  of the sentence.
- Choose `insufficient_source_evidence` when the available source does not
  permit a check.

Check quoted numbers, all rows covered by broad words such as “always” or
“best,” whether causal wording is justified, and whether literature-wide
statements have an adequate documented sample.

**Question 2: Is the stated comparison scientifically like-for-like?**

First decide whether the sentence actually ranks, contrasts, transfers, pools,
or recommends alternatives. If not, choose `not_a_comparability_claim`.

For an actual comparison, write in ordinary language:

- what is being compared;
- what was measured, in which direction, unit, population, and aggregation;
- the experimental or real-world circumstances on each side;
- how the relevant test condition arose and what resources or knowledge were
  available to produce it;
- what each method changed and what was held fixed;
- whether an action, recommendation, coverage level, operating point, stake,
  or cost is part of the conclusion; and
- which unreported fact, if any, would change the conclusion.

Then choose:

- `same_estimand` when the sides answer the same scientific question at the
  stated scope;
- `comparable_with_declared_scope` when a like-for-like statement is possible
  only after writing an explicit scope restriction;
- `different_estimand` when the sides answer materially different questions
  and cannot support the asserted ranking, transfer, or pooling; or
- `missing_comparison_assumption` when a critical unreported assumption could
  make the comparison valid or invalid. Name that assumption and the inference
  it blocks.

Decide the source-support and like-for-like questions separately. Do not create
an overall verdict.

### END PLAIN-LANGUAGE REFERENCE RUBRIC

### 8.1 Mapping without circularity

The first plain-language question maps directly to the four evidence-support
categories because it checks source facts, not schema compliance. The second
maps independently to the five comparability categories because it asks what
scientific question each side answers. Experts must supply passages,
calculations, settings, quantities, and missing assumptions in ordinary
language. Agreement with a v3 intermediate field is neither necessary nor
sufficient for gold correctness.

## 9. Missing and abstaining

Use `response_status=unable_to_determine` and a preregistered missing-reason
code when source access, conflict, or technical failure prevents review. Do not
force a substantive label. Ordinary uncertainty that is itself caused by an
unreported decision-critical assumption should instead receive
`missing_comparison_assumption` with that assumption named.
