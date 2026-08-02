# Post-study analysis addendum

## Status and scope

The preregistered primary analysis is unchanged: the endpoint remains the
claim-level D-minus-C difference in comparability strict-majority exact
accuracy against resolved gold, with source-cluster CR1 inference, the frozen
missingness rule, the planned source-cluster bootstrap, and conditional TOST.
Nothing below amends the preregistration or changes that primary estimand.
For the preregistered missingness bounds, unresolved gold contributes
`[-1,+1]`; when gold is resolved, any observed C or D accuracy remains fixed
and only a missing arm varies over `[0,1]`. Claims with both arm accuracies
observed contribute their fixed D-minus-C difference.

The additional outputs are reviewer-requested **post hoc exploratory or
descriptive analyses**. They must not be reported as preregistered,
confirmatory, or as replacements for the source-cluster primary.

## Rater-aware exploratory sensitivities

Individual-rater accuracy is the proportion of that auditor's completed,
valid ratings with resolved gold that exactly match gold. The output reports
the denominator and arm/output participant mean, minimum, median, and maximum.
The participant-level D-minus-C contrast is the difference between arm means
of these accuracies.

The conditional arm-label permutation holds the 12 realized C/D participant
accuracies fixed and enumerates all `choose(12,6) = 924` assignments of six
labels to D. Its two-sided p-value is the proportion with an absolute
D-minus-C mean difference at least as large as observed. This is a conditional
arm-label sensitivity, **not** an exact design-based test of the claim-level
majority endpoint.

The individual-rating model is OLS `accuracy_indicator ~ 1 + D`. Its
two-way cluster covariance is the Cameron–Gelbach–Miller combination
`V_source + V_auditor - V_source×auditor`. Each meat receives
`G/(G-1) * (N-1)/(N-K)` separately; the t reference uses
`min(G_source-1, G_auditor-1)` degrees of freedom. A negative CGM coefficient
variance is reported as `negative_variance`; it is never clamped to zero.
Insufficient clusters, rank failure, and non-finite variance are explicitly
non-estimable.

Leave-one-auditor-out deletes each realized C/D auditor in turn and rebuilds
claim aggregates. On an affected claim, two retained votes yield a label only
when unanimous; disagreement becomes `no_consensus` and has accuracy zero,
matching the original no-consensus scoring convention. This deliberately
changes aggregation and is therefore a changed-aggregation exploratory
sensitivity, not the preregistered estimand.

Each auditor observed only one arm, and there are only six auditors per arm.
Participant variation is consequently partly aliased with arm, small-cluster
inference is fragile, and none of these analyses can establish a confirmatory
prompt effect.

## Descriptive diagnostics

Fleiss nominal kappa and raw unordered-pair agreement use only claims with
exactly three completed valid votes and are reported by arm/output. Undefined
kappa (for example, zero chance-corrected denominator) is explicit. Class
distributions include `missing` and `no_consensus`; confusion tables compare
arm aggregates with resolved gold.

Response status, missing-reason code, and a declared unable/abstention status
set are counted by arm. Timing uses strict ISO UTC values and computes only
row-level extraction, composition, and extraction-start-to-composition-end
elapsed seconds. Extraction ends at `extraction_completed_utc`; composition
and total end at the formal schema field `completed_utc`. Missing, invalid,
and negative intervals are separate.
Medians and interpolation-based quartiles use only valid nonnegative rows.
These diagnostics are **not labor cost**, and packet-wide timestamps are not
used to infer total work time. Missingness rows expose source, primary
stratum, gold resolution method, unresolved-gold count, and arm-missing count.

## Deidentified public observations

The directory passed through `--output` is the complete **private** analysis
directory. It retains original-ID analyses, including
`analysis_individual_raters.csv` and `analysis_rater_sensitivity.csv`; those
files and every other table containing original participant IDs must never be
published. Public and private outputs are not mixed.

Public rating tables are opt-in and require
`--deidentification-key-file` with a non-empty secret. Release IDs are
role/arm-separated HMAC-SHA256-derived opaque IDs. The key and its path are
never emitted. The only releasable directory is
`--output/public_release/`. It contains HMAC-deidentified arm, gold, and
adjudication observations plus copies of the safe results, claim-level,
gold-resolution, pairwise, agreement, confusion, response-diagnostic, and
missingness-pattern summaries needed for public
recalculation.

Public files retain only claim/source keys, release IDs, role/arm,
response/missingness fields, categorical labels, and the minimum adjudication
fields needed to reproduce gold resolution. They exclude original participant
and linkable response IDs, free text and rationales, claim text, timestamps,
demographics, assignment metadata, and key material or paths. The manifest
uses an explicit allowlist and hashes only files inside `public_release`; it
never inventories the private parent directory.

Before analysis, the offline wrapper binds every used stage-2/adjudication CSV
to the exact-status root manifest and participant index, and checks the pinned
frozen-cohort hash/schema/version. Adjudicators must have unique nonempty IDs
and exact eligible-claim coverage. This is a byte/identity/coverage check:
**the manifest authenticates package bytes but cannot by itself prove
behavioral independence**. No claim is made that
`other_adjudicator_response_seen` was verified.
