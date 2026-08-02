# Observed published-claim audit protocol

Component freeze: `observed-claim-audit-2026.07.14`

Current interpretation: **negative reliability study**. The 289 model-coded
verdicts are a source-linked index, not headline evidence.

## Purpose and unit

The unit is an atomic comparative claim quoted from a published survey or
method paper. The audit asks whether evidence available in that source supports
the claim as written. A verdict is claim-specific; it is not a permanent label
for either paper or method.

This audit replaces the earlier hypothetical prior-survey stress tests as the
paper's empirical comparability evidence. The 342-row Map B remains a separate
literature-family/intervention map and is not represented as a five-coordinate
audit.

## Source and section selection

Three slices were constructed.

1. **General comparison slice (149 corrected atomic candidates).** Fixed
   result/synthesis sections from Sharma (2025), Zhou et al. (2024, v2 dated
   2026), Xu et al. (2026), and Alushi et al. (2026).
2. **Action-policy slice (86 candidates).** Fixed evaluation/result sections
   from Wen et al. (2025), Joren et al. (2025), Liu et al. (2025), and Zhu et
   al. (2026).
3. **Threat-model slice (56 candidates).** Fixed attack/defense sections from
   Xu et al. (2026), Zhou et al. (2024, v2 dated 2026), and Ni et al. (2025).

The first two candidate pools were frozen before their own adjudication. The
threat-model slice was added after the first two slices showed no
origin/capability-decisive cases. It was then frozen before its adjudication.
Consequently, the combined 291-candidate set is a purposive diagnostic audit,
not a preregistered or prevalence-estimating sample.

Within each fixed section, extraction included every explicit statement of
superiority, inferiority, equality, difference, correlation, trade-off,
comparability, field-level absence, or causal/mechanistic explanation between
two or more methods, conditions, signals, policies, metrics, or study families.
Definitions, tables without a prose claim, future-work statements, and
single-method descriptions without a comparator were excluded.

Compound claims were split into the smallest independently testable unit. A
post-adjudication challenge identified one missed compound sentence; the
correction ledger records its split into `ALU-035A` and `ALU-035B`. The final
set has 291 candidates, of which two metric-direction definitions were excluded
as non-comparative, leaving 289 claims.

## Quote and source verification

Each candidate preserves the exact quotation, one-sentence context, source
section, physical PDF page, printed page, URL, version, and PDF SHA-256.
Whitespace, ligatures, and line-break hyphenation were normalized only for
matching. Candidate manifests required every quotation to match its assigned
PDF page. One two-column extraction required a documented layout-view override.

The canonical release includes quotations, source URLs, page locations, and
hashes, but not third-party PDFs.

## Coordinates and verdicts

Every included claim is coded for:

1. evidence state;
2. origin or attacker capability;
3. intervention;
4. outcome and evaluation unit;
5. policy, action set, and utility context.

The full verdict additionally checks claim-specific experimental controls. The
controlled vocabulary, boundary cases, deterministic three-stage rules, and
the distinction between an internal intervention and an externally scored
action appear in `observed_claim_audit_codebook.md`.

The released script derives:

- a simple evidence-state/intervention/outcome verdict;
- a five-coordinate verdict without experimental controls;
- a full verdict after the control check.

`valid`, `partial`, `invalid`, and `under-specified` mean, respectively:
supported as written; a concrete narrower claim survives; no common estimand
or a direct counterexample defeats the claim; or a decision-critical field
cannot be recovered.

## Coding and adjudication provenance

Candidate extraction, structured coding, and source-linked adjudication were
LLM-assisted. The 289-row verdict distribution is not human gold and is not
used to estimate how often literature claims are valid or invalid.

The first 148-claim slice served as codebook development evidence. A distinct
86-claim action-policy slice was then coded independently by GPT-5.6,
Claude Opus 4.8, Claude Sonnet 5, and Gemini 3.1 Pro. Gemini was excluded from
agreement aggregation because several core fields were constant for all 86
rows despite heterogeneous sources. This exclusion and all raw outputs are
released.

Among the three non-degenerate coders, pairwise agreement was strongest for
claim archetype (Cohen's kappa 0.63--0.85), evidence state (Gwet's AC1
0.95--1.00), and whether utility was required (Gwet's AC1 0.66--0.94).
Five-coordinate verdict agreement was moderate (kappa 0.35--0.44). Full
control-aware verdict agreement remained poor (kappa -0.08--0.28), driven
mainly by disagreement over intervention boundaries and which unreported
controls were decision-critical.

A separate source-linked model adjudication resolved fields for the released
audit. Two independent challenge passes inspected all high-risk labels and
produced 23 logged corrections, including three missed appendix-table checks
and one atomicity split. This process improves traceability but does not
constitute external validation.

An independent human round subsequently sampled 80 claims using hidden model
strata (26 model-valid, 25 partial, 25 invalid, and 4 under-specified).
Three different human coders labeled every claim without model labels or
generative AI, and a fourth human supplied the final adjudicated label. Pairwise
verdict agreement was 0.538--0.788 (Cohen's kappa 0.258--0.525); only 39/80
verdicts were unanimous. Adjudicated labels were 43 valid, 29 partial, 6
invalid, and 2 under-specified. They matched model adjudication on 40/80 claims
(kappa 0.273; macro-F1 0.437). Model-predicted invalid claims had precision
0.20 against the adjudicated labels.

The sample is not a probability sample. Sixteen cases form a deterministic
four-stratum core generated with seed 20260714. The selection code and seed for
the remaining 64 were not retained, so no inverse-probability weighting or
population performance estimate is justified. The frozen v2 codebook was the
delivered instruction. Aggregate participant background, recruitment,
training, compensation, work time, consent, ethics status, and adjudication
procedure are recorded in `human_validation_protocol.md`. One adjudicator
resolved final disagreements; nine of 78 available coder majorities were
changed.

## Rule-baseline evaluation

Four deterministic rules were evaluated against the adjudicated labels using
the same source-linked model-coded fields:

| Rule | Exact | Kappa | Macro-F1 |
| --- | ---: | ---: | ---: |
| Three-field taxonomy | 0.300 | -0.003 | 0.180 |
| Evidence+control rule with C2/C5 ablated | 0.500 | 0.254 | 0.417 |
| Five coordinates without controls | 0.550 | 0.315 | 0.382 |
| Five coordinates plus controls | 0.500 | 0.273 | 0.437 |

The C2/C5 ablation is part of the same executable rule family, not an
independently implemented conventional audit. It and the full schema each
uniquely corrected three of their six disagreements (two-sided exact McNemar
p=1.0).
Adding controls after the five-coordinate rule produced six newly incorrect
and two newly correct cases (p=0.289). Hard rules emit no probabilities, so
calibration is not estimable.

Within the unvalidated 289-row index, 7 cases trigger factual or
counterexample checks, 52 trigger causal-isolation checks, and 28 are
field-level claims. Removing those ordinary audit types leaves 202 cases; 20
have a C1, C2, or C5 transition. These are rule-behavior counts, not validated
errors.

## Reportable scope

The reportable empirical result is the negative reliability finding on the
80-claim model-stratified sample. The combined 289-row index contains
125 model-valid, 134 partial, 26 invalid, and 4 under-specified labels, but this
distribution appears only as provenance for the released index. Internal
counterfactual counts (C1=1, C2=7, C5=12, controls=23, intervention
transition=120) describe what the model-coded rule does and do not establish
that the transitions improve validity judgments.

The post-study `observed_claim_audit_codebook_v3_draft.md` separates ordinary
evidence support from comparability. It is not applied to the same 80 labels
and requires a newly frozen, paper-disjoint evaluation before use.

## Known limitations

- The source and section sample is purposive and was expanded adaptively.
- The 289-claim counts remain model-adjudicated and are not headline results.
- The 80-claim sample is drawn from the full pool, which includes the
  148-claim codebook-development slice; it is not a paper-disjoint test.
- Only four genuine under-specified claims survived source checking, so the
  human sample could include only four such model-labeled cases.
- The model-balanced 16-claim core becomes 9 valid, 6 partial, 0 invalid, and
  1 under-specified after human adjudication.
- Human pre-adjudication verdict agreement is only fair-to-moderate, so the
  current codebook does not establish independently reliable final verdicts.
- The remaining 64 sample-selection procedure, pilot responses, calibration
  notes, consent forms, and institutional determination document are not
  released.
- Primary studies cited by survey prose were not all re-run; narrow attributed
  reports remain marked as such.
