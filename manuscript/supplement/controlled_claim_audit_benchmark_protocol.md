# Controlled robust-RAG decision benchmark

Status: the initial design record preceded model outcomes. A 2026-07-27
post-outcome audit found that the first C2 generator also changed the defer
cost, confounding capability with utility. The canonical generator now holds
defer cost fixed within every C2 pair and changes only deployment
origin/access/budget and its predeclared out-of-envelope penalty. All three
reported models were rerun on the corrected benchmark. The C5 generator was
unchanged. This correction makes the model experiment diagnostic rather than
preregistered confirmatory evidence.

## Purpose

This benchmark tests whether explicit origin/capability and policy/utility
prompts help language-model reviewers make consequence-defined deployment
decisions. It is not a human-subject study and does not validate the prompts
for human reviewers or natural paper prose.

## Design

- 480 synthetic vignettes form 240 counterfactual pairs.
- 240 items change only whether the deployment origin/access/budget lies
  inside the evaluated capability envelope (C2).
- 240 items change only the costs assigned to errors and abstentions (C5).
- Twelve application templates contribute 40 items each.
- The target is the unique minimum of a displayed expected-loss rule over
  `deploy_A`, `deploy_B`, and `defer`.
- No source-paper quotation, human reference label, adjudication, or
  2026-07-25 human-study output enters generation or scoring.

## Prompt contrast

The ablated condition requests source support, evidence state, intervention,
outcome/unit, controls, and the deployment action. The full condition adds
explicit checks for how the evidence condition arose; attacker
access/knowledge/budget; available actions; coverage; stakes; and costs.
Both conditions receive identical vignette text and the same output
vocabulary.

Two format-only pilot executions were used after the design record to replace
an ambiguous JSON schema with a single-action-token instruction and to accept
an unambiguous action token at the start of a response. No benchmark item,
target, model, substantive prompt field, or decoding rule was selected from
pilot accuracy.

## Outcomes

The primary descriptive outcomes are exact action agreement and mean
decision regret. Counterfactual-pair consistency is secondary. Results are
reported separately for every fixed model and for C2/C5 strata. Any aggregate
over models is a fixed-panel summary, not inference to a model population.
The released main table is descriptive; item-level McNemar diagnostics are
retained only as supplementary fixed-item checks because the 480 items form
dependent counterfactual pairs.

## Interpretation boundary

The experiment supplies construct evidence on controlled, numerically
defined decisions. It cannot establish performance on ambiguous published
claims, validate the five-field framework as a human instrument, or repair
the excluded unverifiable human collection.
