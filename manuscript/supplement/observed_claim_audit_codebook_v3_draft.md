# Post-study Claim-Audit Codebook v3 Draft

Status: **post-study redesign, not used for any reported metric**

This draft responds to disagreements observed under the frozen 2026-07-14 v2
codebook. It must be frozen and evaluated on new sources before use. The
existing 289 model-coded records and 80 human labels are not relabeled with
this draft.

## 1. Separate outputs

Version 2 collapsed ordinary evidence support and cross-system comparability
into one four-way verdict. Version 3 produces two labels.

### A. Evidence-support status

- `supported_as_written`
- `supported_after_narrowing`
- `contradicted`
- `insufficient_source_evidence`

This label answers whether the cited source supports the sentence. It covers
numeric transcription, quantifiers, causal isolation, and field-coverage
claims. It does not attribute an error to a comparability coordinate.

### B. Comparability status

- `same_estimand`
- `comparable_with_declared_scope`
- `different_estimand`
- `missing_comparison_assumption`
- `not_a_comparability_claim`

This label answers whether the compared sides estimate the same scientific
quantity under assumptions adequate for the claim. It is assigned only after
the evidence-support check.

No deterministic function collapses A and B into a single final verdict.

## 2. Gate 1: ordinary evidence support

Apply these checks before the five-coordinate diagnosis.

1. **Numbers and direction.** Recompute every quoted difference, ordering,
   ratio, and sign from the cited table or figure.
2. **Quantifiers.** For `all`, `always`, `consistently`, `best`, or equivalent
   wording, inspect every row in the stated scope.
3. **Causal language.** A mechanism claim requires an intervention, ablation,
   randomization, or identified natural experiment that isolates the proposed
   cause. Otherwise retain only an association.
4. **Field-level language.** Absence, dominance, or incommensurability claims
   require a documented sampling frame and coverage audit.
5. **Attributed reports.** A faithful statement that a cited study reported a
   result is judged as an attributed report unless the claim independently
   endorses or generalizes that result.

If this gate returns `contradicted` or `insufficient_source_evidence`, record
the reason separately. Do not call it a comparability failure unless a
coordinate also changes the estimand.

## 3. Gate 2: comparability applicability

Use the five-coordinate diagnosis only when a claim:

- directly ranks or contrasts systems, methods, policies, or study families;
- transfers a result across evidence or threat settings;
- pools independently run results; or
- recommends one action or operating point over another.

Pure transcription, mechanism description, field-coverage, and causal
identification claims receive `not_a_comparability_claim` unless they also make
one of the comparisons above.

## 4. Coordinate questions

For each side, record a value and answer the operational question below.

### C1. Evidence state

What evidence reaches the system at the decision boundary? Use:
`supported`, `irrelevant_or_distracting`, `insufficient`, `conflicting`,
`stale_or_low_provenance`, `adversarially_manipulated`, `mixed`,
`not_evidence_conditioned`, or `unreported`.

Relation question: **Would the claimed direction still answer the same
scientific question if the compared evidence-state labels were exchanged?**
If yes, code `aligned_for_claim` even when surface labels differ. If no, code
`estimand_shift`. Use `missing` only when the source evidence cannot answer.

### C2. Origin or attacker capability

Record benign retrieval, benchmark construction, natural conflict or drift,
distribution shift, attacker creation, or a shared clean harness. For attacks,
also record corpus access, query knowledge, retriever visibility, insertion
budget, target scope, and adaptive access.

Relation question: **Does the conclusion transfer across the two capability
envelopes without changing its scope?** A descriptive mechanism report does
not fail merely because capability differs. An effectiveness rank does.

### C3. Intervention

Record the changed component. Different interventions are expected in a method
comparison and never constitute a mismatch by themselves.

Relation question: **Are interventions alternative ways to optimize the same
outcome in the same harness, complementary stages, or incomparable roles such
as a benchmark versus a mitigation?**

### C4. Outcome and unit

Record outcome definition, direction, aggregation, evaluation unit, and
baseline. Relative improvements with different denominators are not aligned.

Relation question: **Can both reported quantities be written as the same
estimand with the same unit and aggregation?**

### C5. Policy and utility

Record the externally scored action, available alternatives, operating point,
coverage, stakes, and costs. Fixed answer-quality comparisons are
`not_applicable`.

Relation question: **Does a shared utility order the competing actions or
operating points?** A normative recommendation without shared utility is
`missing_comparison_assumption`; a descriptive trade-off may remain
`comparable_with_declared_scope`.

## 5. Claim-specific controls

Select controls from a claim-to-control matrix before inspecting results.

| Claim target | Required controls |
| --- | --- |
| Answer or retrieval quality | dataset/split, evidence set, generator, prompt/decoding, baseline, metric |
| Efficiency | all quality controls plus hardware, batching, latency/compute budget |
| Security effectiveness | clean utility plus capability envelope, attack budget, adaptive access |
| Selective policy | action set, matched coverage or operating points, risk definition, cost/utility |
| Cross-study synthesis | every required within-study control plus uncertainty and aggregation |

For each required control use `reported_aligned`, `reported_different`,
`unreported_but_noncritical`, or `unreported_decision_critical`. Coders must
name the exact inference blocked by a missing critical control.

## 6. Reporting format

Each audited claim should expose:

1. exact quotation and source location;
2. evidence-support label and reason;
3. whether comparability analysis applies;
4. C1--C5 values and relation questions;
5. claim-specific control matrix;
6. comparability label and supported scope;
7. unresolved information.

## 7. Required validation

Before this draft can replace v2:

1. freeze development sources and a paper-disjoint test source set;
2. archive the complete instructions, examples, sampling code, and seed;
3. obtain at least two independent labels per test claim and two independent
   adjudications for disputed cases;
4. report field reliability, evidence-support accuracy, comparability accuracy,
   time, and abstention rates;
5. compare against full-text evidence review plus a conventional
   intervention/comparison/outcome and control checklist;
6. do not tune rules after opening the test labels.
