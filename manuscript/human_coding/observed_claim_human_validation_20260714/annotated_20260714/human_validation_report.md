# Human validation results

## Scope

The release contains 80 model-stratified publicly stated comparison claims with
independent human judgments and adjudicated consensus. Model labels were hidden
during validation.

The model-stratum coverage is 26/125 valid, 25/134 partial, 25/26 invalid, and
4/4 under-specified claims. Sixteen cases are a deterministic balanced core
(seed 20260714). The selection procedure for the remaining 64 was not retained,
and the pool includes the 148-claim codebook-development slice. This is neither
a probability sample nor a paper-disjoint test, so no population performance
estimate is reported.

## Pre-adjudication agreement

| Pair | Raw verdict agreement | Cohen's kappa | Gwet's AC1 |
| --- | ---: | ---: | ---: |
| A--B | 0.625 | 0.396 | 0.535 |
| A--C | 0.788 | 0.525 | 0.751 |
| B--C | 0.538 | 0.258 | 0.434 |

The result is fair-to-moderate rather than substantial reliability.
Only 39/80 verdicts are unanimous. A coder majority exists for 78 claims, and
the separate adjudicator changes nine of those majority labels.

Core-field pairwise Cohen's kappa ranges are:

| Field | Kappa range |
| --- | ---: |
| C1 evidence-state relation | 0.101--0.283 |
| C2 origin/capability relation | 0.153--0.401 |
| C3 intervention relation | 0.215--0.535 |
| C4 outcome relation | 0.253--0.462 |
| C5 policy/utility relation | 0.445--0.737 |
| Control status | 0.208--0.266 |

## Adjudicated human labels

| Verdict | Claims |
| --- | ---: |
| Valid | 43 |
| Partial | 29 |
| Invalid | 6 |
| Under-specified | 2 |

## Model comparison

The adjudicated labels match the source-linked model adjudication on 40/80 claims:

- exact agreement: 0.500;
- Cohen's kappa: 0.273;
- Gwet's AC1: 0.359;
- macro-F1: 0.437.

| Model class | Model claims | Human claims | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Valid | 26 | 43 | 0.808 | 0.488 | 0.609 |
| Partial | 25 | 29 | 0.520 | 0.448 | 0.481 |
| Invalid | 25 | 6 | 0.200 | 0.833 | 0.323 |
| Under-specified | 4 | 2 | 0.250 | 0.500 | 0.333 |

The largest error is model over-rejection: only 5 of 25 model-predicted invalid
claims remain invalid under human adjudication.

## Rule comparison

All rules below use the same source-linked model-coded fields and are compared
with the final adjudicated human label.

| Rule | Exact | Kappa | Macro-F1 |
| --- | ---: | ---: | ---: |
| Three-field taxonomy | 0.300 | -0.003 | 0.180 |
| Evidence+control rule with C2/C5 ablated | 0.500 | 0.254 | 0.417 |
| Five coordinates without controls | 0.550 | 0.315 | 0.382 |
| Five coordinates plus controls | 0.500 | 0.273 | 0.437 |

The ablation belongs to the same rule family and is not an independently
implemented conventional audit. It and the full schema each uniquely correct
three of their six disagreements (two-sided exact McNemar p=1.0). The
deterministic rules emit no probabilities or confidence scores, so calibration
is not estimable.

The 16-item core was balanced only by model labels. Human adjudication changes
its distribution to 9 valid, 6 partial, 0 invalid, and 1 under-specified, so it
is not a human-balanced gold set.

## Interpretation

The project owner attests that distinct people tested real published claims,
but the public release does not independently verify participant-level
records, and the round does not validate the current final-verdict procedure
as reliable. The schema improves evidence-linked disagreement analysis;
controls, intervention boundaries, and valid-versus-partial scope still need a
revised codebook and a newly frozen human-balanced evaluation.

The model-adjudicated 289-claim resource remains useful as an auditable
diagnostic inventory, but its absolute verdict counts should not be represented
as human-validated prevalence or gold.

## Provenance boundary

The project-owner provenance reports three distinct human coders, a separate
human adjudicator, hidden model labels, and no generative-AI use; the release
itself does not independently confirm participant identities. It does not
retain participant identifiers. The same attestation reports that all three
coders had NLP, RAG, or experimental-methodology research backgrounds; the
adjudicator had more senior relevant experience. They were recruited through
the authors' professional network, compensated, trained with the frozen v2
codebook plus a pilot and boundary calibration, and spent 60 hours per coder
and 30 hours in adjudication. The adjudicator is reported to have checked all
80 claims before consulting coder labels and rationales.

The project owner confirms explicit consent for paper use and public release of
de-identified annotations and an institutional determination that formal IRB
review was not required (exemption or non-human-subjects status). Original
pilot responses, calibration notes, consent forms, and the institutional
determination document are not released. See `../human_validation_protocol.md`.
