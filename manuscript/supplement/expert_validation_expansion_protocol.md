# Expanded expert-validation protocol

The current expert-use pilot covers 12 deliberately difficult paper pairs. This
protocol defines the larger validation needed to test generalization.

## Pair selection

Select 60--100 paper pairs using a stratified design:

- 12--20 evidence-construction pairs
- 12--20 model/evidence-use pairs
- 12--20 security/adversarial-integrity pairs
- 12--20 control/calibration/abstention pairs
- 12--20 evaluation/benchmark pairs

Within each perspective, include:

- likely valid comparisons
- partial comparisons
- invalid comparisons
- under-specified comparisons
- attack-vs-defense role asymmetry
- benchmark-vs-method asymmetry

Record pair selection in `expert_pair_selection_protocol.csv` with:

- pair id
- paper ids
- perspective
- anticipated difficulty
- reason for selection
- whether the pair is near-miss, cross-family negative, or likely comparable
- whether the pair appeared in the manuscript case studies

## Annotators

Recruit at least 24 independent annotators:

- RAG/NLP
- IR/retrieval
- trustworthy ML/evaluation
- security/privacy

Record anonymized qualification metadata:

- role category
- years of research experience bucket
- familiarity with RAG (1--5)
- familiarity with security/evaluation/calibration (1--5)
- whether they participated in paper design (must be no)

## Gold adjudication

Use a separate gold panel of 3--5 experts. Report:

- individual gold votes
- inter-gold agreement
- adjudication rationale
- final gold verdict
- rulebook revisions

## Statistical analysis

Use mixed-effects or clustered analysis to account for dependence:

- annotator random effects
- pair random effects
- condition fixed effect
- perspective fixed effect

Report:

- accuracy to external gold
- macro-F1 by verdict class
- pair-level and annotator-level bootstrap intervals
- Fleiss kappa / Krippendorff alpha
- decision time
- confidence calibration
- rationale quality
- error-type reduction

The current 30-annotator / 12-pair study should be treated as a pilot for this
larger validation.
