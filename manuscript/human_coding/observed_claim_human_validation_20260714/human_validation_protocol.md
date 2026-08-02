# Human Claim-Validation Protocol

Study date: 2026-07-14  
Claims: 80  
Roles: three coders and one separate adjudicator, reported by the project
owner to have worked independently

This document records the protocol and aggregate administrative metadata
confirmed by the project owner. It contains no participant identifiers.

## Participants and recruitment

- All three coders had research backgrounds in NLP, RAG, or experimental
  methodology.
- The adjudicator had more senior relevant research experience than the three
  coders.
- Participants were invited through the authors' professional collaborator
  network.
- All four participants were compensated under a pre-agreed arrangement.
- Each coder reported 60 hours of work; the adjudicator reported 30 hours,
  totaling 210 person-hours.

## Ethics and consent

- All four participants explicitly agreed that their de-identified annotations
  could be used in the paper and publicly released with the submission data.
- The project owner reports an institutional determination that formal IRB
  review was not required, under an exemption or non-human-subjects
  determination.
- The consent and institutional-determination documents are not included in the
  public artifact. The release contains only aggregate protocol metadata and
  de-identified annotation IDs.

## Materials

The annotation instructions were the frozen `Published-Claim Comparability
Audit Codebook, v2`, version 2026-07-14:

`manuscript/supplement/observed_claim_audit_codebook.md`

Each row also supplied:

- an anonymous annotation ID;
- exact quotation and adjacent context;
- source title and URL;
- source section;
- physical PDF page and printed page;
- comparison subjects.

Model verdicts, model strata, model rationales, and the hidden sample key were
not provided to coders or the adjudicator before final labels were complete.

## Training

Before formal annotation, participants:

1. read the v2 codebook;
2. completed pilot annotations; and
3. discussed boundary rules without seeing model labels.

The original pilot responses and calibration-meeting notes were not retained.
The frozen v2 codebook is therefore the complete released instruction
document, while the training interaction is documented only at this aggregate
level.

## Independent coding

All three coders reviewed all 80 claims. For each claim they recorded:

- unit status, archetype, and claim strength;
- C1--C5 values and relations;
- utility requirement and reporting;
- factual, counterexample, causal-isolation, and field-audit flags;
- required controls and control status;
- a four-way verdict;
- narrower supported wording or missing information when applicable;
- source evidence location and rationale.

Coders were instructed to open the linked source and verify the cited page,
table, figure, or passage. No generative AI was used.

## Adjudication

The adjudicator independently checked all 80 source claims before consulting
the three completed coder labels and rationales. The adjudicator then issued:

- final archetype;
- final C1--C5 relations;
- final control status;
- final verdict;
- narrower wording or missing information where required; and
- source-linked rationale.

The adjudicator did not merely accept majority vote: a coder majority existed
for 78 claims, and nine of those majority labels were changed. There was no
second independent adjudicator, so adjudication sensitivity remains a
limitation.

## Sampling provenance

The sample was stratified by hidden model verdict:

| Model stratum | Inventory | Human sample |
| --- | ---: | ---: |
| Valid | 125 | 26 |
| Partial | 134 | 25 |
| Invalid | 26 | 25 |
| Under-specified | 4 | 4 |

Sixteen items form a deterministic four-per-stratum core generated with seed
20260714. The selection procedure for the other 64 was not retained. The pool
also includes claims from the 148-claim codebook-development slice. The sample
is therefore neither a probability sample nor paper-disjoint from development.

## Analysis boundary

The adjudicated human label is a diagnostic reference for these 80 claims, not
a population gold standard. Pairwise human agreement is only fair-to-moderate,
and one adjudicator resolves final disagreements. Rule accuracy, kappa, and
macro-F1 are descriptive for this model-stratified sample. The deterministic
rules emit no probabilities, so calibration is not estimable.
