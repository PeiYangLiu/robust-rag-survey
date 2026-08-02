# When Are Robust-RAG Results Comparable?

This repository contains the manuscript and audit artifacts for **When Are
Robust-RAG Results Comparable? A Coordinate Audit of Published Comparisons**.

The paper audits cross-paper comparisons in robust RAG against five substantive
coordinates (evidence state, origin/capability, intervention, outcome,
policy/utility) at two scales. A source-verified ledger of twelve worked
comparisons finds that ten do not survive as stated. A census over a
deterministic frame of 647 candidate juxtapositions screened from all 259 local
full texts, coded independently by three judges from three model developers,
separates two populations: numbers re-implemented inside the citing paper's own
harness mostly survive, while numbers transported from the other paper mostly
do not. Checking such claims is itself a measurement problem, so a second layer
records five measurement objects (item, reviewer, assignment, reference,
downstream loss) and prices what the current reporting practice costs, using a
between-reviewer heterogeneity parameter estimated from several genuinely
crossed reviewer-by-item designs rather than from one three-coder sample.

> **Scope of this repository.** Only the experiment code and data are
> published here. The paper's LaTeX sources, figures, tables and compiled
> PDF are not included; see `EXPERIMENTS.md` for how to reproduce every
> number the paper reports from the artifacts that are.

## Canonical evidence boundary

Release date: **2026-07-28** (revision)

| Component | Canonical path | Evidentiary status |
| --- | --- | --- |
| Manuscript | not distributed (experiment code and data only) | — |
| Cross-paper comparability cases | `manuscript/supplement/cross_paper_comparability_cases.csv` | 12 cross-paper cases + 3 within-harness controls; source-linked, single-coded, not a census |
| Case codebook and verifier | `manuscript/supplement/cross_paper_comparability_cases_codebook.md`, `manuscript/scripts/verify_cross_paper_cases.py` | 70 provenance checks, all passing |
| Reviewer-heterogeneity estimate | `manuscript/supplement/reviewer_heterogeneity_anchor.json` | Estimated from the crossed three-coder diagnostic; interval, not point |
| Retrospective-remedy simulation | `manuscript/supplement/retrospective_remedy_simulation.json` | Size and power for four analyses at the estimated heterogeneity |
| Controlled benchmark v2 | `manuscript/supplement/controlled_claim_audit_benchmark_v2.jsonl` | 600 consequence-defined items in 300 pairs; supersedes v1 |
| Controlled model outputs v2 | `manuscript/supplement/controlled_model_judge_raw_v2/` | Nine open models, 7,200 greedy decisions each |
| Controlled model outputs v3 | `manuscript/supplement/controlled_model_judge_raw_v3/` | Additional open checkpoints and API-served frontier models, 7,200 greedy decisions each |
| Decision normalisation report | `manuscript/supplement/decision_normalisation_report.json` | Symmetric last-token normalisation; changes no open-checkpoint decision |
| Controlled model analysis v3 | `manuscript/supplement/controlled_model_judge_results_v3.json` | 24 models, pair-clustered, Holm-corrected, gate-filtered, random-effects |
| Model-judge generalization | `manuscript/supplement/controlled_model_judge_generalization.json` | Prediction intervals, developer-level pooling, leave-one-developer-out, TOST on the negative control |
| Cross-paper sampling frame | `manuscript/supplement/cross_paper_frame_candidates.jsonl`, `..._summary.json` | Deterministic screen over 259 full texts; 647 candidates, gazetteer and cues released |
| Independent codings | `manuscript/supplement/cross_paper_coding/`, `cross_paper_coding_dev/` | Three judges from three developers; development pass kept separate |
| Provenance classification | `manuscript/supplement/cross_paper_provenance/` | Transported vs re-implemented, three independent judges |
| Census analysis | `manuscript/supplement/cross_paper_census.json`, `cross_paper_census_ledger.csv` | Agreement statistics, verdict distribution, provenance-stratified rates |
| Crossed-design sigma_r anchors | `manuscript/supplement/sigma_anchors/`, `manuscript/supplement/sigma_r_multi_anchor.json` | Five public human corpora plus the fully crossed model panel |
| Development-diagnostic baselines | `manuscript/supplement/claim_rule_baselines.json` | Negative result: no rule variant beats the majority-class baseline |
| Published human-evaluation audit | `manuscript/supplement/published_human_evaluation_audit.json` | Nine source-linked published cases; reporting audit, not prevalence |
| Audit summary and generator | `manuscript/supplement/published_human_evaluation_audit_summary.json`, `manuscript/scripts/analyze_published_human_evaluation_audit.py` | Deterministically checked |
| Assignment-unit simulation | `manuscript/scripts/simulate_assignment_unit_mismatch.py` | Same-statistic sharp-null design stress test |
| Simulation output | `manuscript/supplement/assignment_mismatch_simulation.json` | 5,000 replicates per scenario |
| Controlled decision benchmark (v1) | `manuscript/supplement/controlled_claim_audit_benchmark.jsonl` | 480 items; **superseded** by v2, retained as record |
| Controlled model outputs (v1) | `manuscript/supplement/controlled_model_judge_raw/` | Three fixed open models; **superseded** |
| Controlled model analysis (v1) | `manuscript/supplement/controlled_model_judge_results.json` | **Superseded**; see v2 |
| 80-claim development diagnostic | `manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/` | Descriptive development evidence |
| Scoping corpus and Map B | `manuscript/supplement/corpus_snapshot.json`, `manuscript/supplement/evidence_map_venue_expanded_adjudicated.csv` | Documentary context only |
| 480-claim protocol | `manuscript/human_coding/heldout_claim_validation_v3_20260715/README_REVIEWER_PACKAGE.md` | Privacy-minimized design-audit case only |
| De-identified excluded export | `manuscript/supplement/v3_human_reanalysis_20260725/` | Local historical record; omitted from release packages |
| Invalidation receipt | `files/v3_invalidated_shared_answer_run_20260719/invalidation_report.json` | Privacy-safe exclusion evidence; no study outcome |

The excluded collection could not be linked to controlled recruitment records,
one-to-one pseudonym mappings, and separate response receipts available to the
research team or an authorized auditor. Public identity disclosure is not
required: consent and identity-linkage records should remain access-controlled.
No response, agreement rate, arm contrast, reference statistic, participant
attribute, or timing claim from that collection enters the paper.

## Cross-paper comparability cases

Twelve cross-paper comparisons drawn from 259 locally extracted full texts, plus
three within-harness contrasts as negative controls. Ten of the twelve do not
survive the coordinate audit as stated: six have no common scope and four hold
only on a strict subset. The sharpest case reads PoisonedRAG's 97% black-box
attack success rate (five injected texts per target question) against Phantom's
93.3% (one poisoned document); PoisonedRAG's own budget ablation gives 0.48 at
one malicious text, so the quoted 3.7-point lead becomes a 45.3-point deficit.

Every reported value is copied verbatim from a local text with a file and line
range. Rebuild and re-check with:

```bash
python manuscript/scripts/verify_cross_paper_cases.py
```

Field definitions, the verdict vocabulary, the evidentiary standard and the
selection bias are documented in
`manuscript/supplement/cross_paper_comparability_cases_codebook.md`.

## Reviewer heterogeneity and retrospective remedies

Between-reviewer heterogeneity is identified only by a crossed reviewer-by-item
design. It is estimated here from the retained 80-claim diagnostic (three coders
× 80 adjudicated claims) as sigma_r = 0.27, with a source-clustered bootstrap
95% interval of [0.00, 0.53]. The agreement rates that audited papers do report
place no usable restriction on it: at the label prevalence they imply, every
value on a 0–1.2 grid reproduces the reported agreement for some item
dispersion.

At the estimated value, a source-level test of panel-majority correctness
rejects a true null 24.2% of the time at 80 sources and 36.7% at 160, and using
individual votes with a source-level standard error is worse still. A
two-sample test on individual reviewer accuracies and its exact 924-assignment
permutation both hold the nominal 5% and retain power (52.8% and 51.6% against a
0.4-logit effect at 80 sources). Both need only pre-aggregation votes carrying
reviewer identifiers, so both are executable after data collection.

```bash
python manuscript/scripts/estimate_reviewer_heterogeneity.py
python manuscript/scripts/simulate_retrospective_remedies.py
```

## Controlled consequence experiment, version 2

600 items in 300 counterfactual pairs across a competence probe and the
capability and utility strata, answered by nine instruction-tuned open models
from five developers under three arms crossed with four paraphrases: 64,800
greedy decisions. The third arm is a length-matched placebo, so the primary
contrast is not confounded with instruction verbosity, and a pre-declared
validity gate excludes models that cannot execute the displayed-loss rule.

Pooled full-minus-placebo effect across the eight gate-passing models: +5.4
points on the capability stratum (95% CI [+2.5, +8.2]) and +1.4 points on the
utility stratum (95% CI [-0.4, +3.2]). The competence probe, where naming a
coordinate should not help, gives +0.2 points.

```bash
python manuscript/scripts/build_controlled_claim_audit_benchmark_v2.py --check
python manuscript/scripts/run_controlled_model_judges_v2.py --model <hf-id> \
    --output raw.jsonl --summary raw-summary.json
python manuscript/scripts/analyze_controlled_model_judges_v2.py \
    --inputs manuscript/supplement/controlled_model_judge_raw_v2/*.jsonl
```

Design, guarantees, the validity gate and the interpretation boundary are in
`manuscript/supplement/controlled_claim_audit_benchmark_v2_protocol.md`. The
cluster configuration is `configs/amlt_controlled_model_judges_v2.yaml`.

## Published reporting audit

The fixed screen starts from 39 venue- or proceedings-linked Map B papers with
local full text. A deterministic term screen yields 19 candidates; full-text
eligibility review retains nine papers that collect original human judgments.
With the unreleased third-party full-text extraction directory present,
revalidate the frozen paper set, text hashes, source locators, counts, and
LaTeX tables with:

```bash
python manuscript/scripts/analyze_published_human_evaluation_audit.py
```

The reviewer package contains the frozen key/hash manifest but not the
copyrighted full texts, so source-line revalidation is intentionally not
portable from that ZIP alone.

The audit identifies reporting gaps, not hidden design errors. None of the nine
papers randomizes an audit prompt across annotators, so no published paper is
classified as a confirmed assignment-unit mismatch.

## Same-statistic simulation (oracle benchmark, superseded as the headline result)

This simulation is retained as a design reference. The headline calibration
result now comes from the retrospective-remedy simulation above, which is
evaluated at the estimated reviewer heterogeneity and compares analyses that an
author can actually run after collection.

The simulation reproduces a 12-reviewer, six-per-arm, three-of-six-panel design
under a sharp null. It compares:

1. a paired source `t` reference for panel-majority correctness;
2. an oracle reviewer-randomization reference for the identical studentized
   panel-majority statistic; and
3. reviewer randomization using individual accuracy.

```bash
python manuscript/scripts/simulate_assignment_unit_mismatch.py \
  --replicates 5000 --workers 7
```

At 80 sources and reviewer logit SD 0.20, rejection is 17.0% for the source
reference and 5.3% for the same-statistic randomization benchmark. The latter
requires a complete simulated vote matrix and an arm-independent schedule; it
is not a retrospective test for realized-panel-only data.

## Controlled consequence experiment, version 1 (superseded)

Retained as a record. Version 1 had two design defects found in review: the
utility stratum made deferral a deterministic function of the deployment
losses, so it was never optimal and every model scored at chance; and the
capability stratum resolved every shift into deferral. Both are corrected in
version 2 above, and no version-1 number is quoted in the current manuscript.

The benchmark contains 240 counterfactual pairs:

- 120 pairs change only deployment origin/access/budget relative to the
  evaluated capability envelope;
- 120 pairs change only error-versus-abstention costs;
- 12 application templates contribute 40 items each; and
- each target is the unique minimum of a displayed deployment-loss rule over
  `deploy_A`, `deploy_B`, and `defer`.

Rebuild the benchmark and analyze the released model outputs with:

```bash
python manuscript/scripts/build_controlled_claim_audit_benchmark.py --check
python manuscript/scripts/analyze_controlled_model_judges.py \
  --input manuscript/supplement/controlled_model_judge_raw/qwen2.5-7b.jsonl \
  --input manuscript/supplement/controlled_model_judge_raw/phi-4-mini.jsonl \
  --input manuscript/supplement/controlled_model_judge_raw/olmo-2-7b.jsonl
```

The full prompt is not uniformly better: exact agreement changes by -2.1,
+3.3, and 0.0 percentage points for Qwen2.5-7B, Phi-4-mini, and OLMo-2-7B.
Two format-only pilot runs finalized an unambiguous single-token output
instruction and prefix parser; benchmark targets and the substantive prompt
contrast were unchanged. A later audit found and removed a C2/defer-cost
confound; all three canonical models were rerun on the corrected benchmark, so
the reported experiment is diagnostic rather than preregistered. The released
raw records pin the model commits and package versions; cluster- and
workspace-specific submission settings are intentionally omitted for
double-blind review.

## Development diagnostic

Three coders and one adjudicator reviewed 80 claims with model labels hidden.
Only 39/80 verdicts were unanimous, and pairwise verdict kappa is 0.258--0.525.
Reliability is uneven across coordinates in an informative way: the
policy/utility field is the most reliable (pairwise kappa up to 0.737, Gwet's
AC1 up to 0.913) and the evidence state the least (kappa 0.101--0.283).

Read against the baselines a classifier must beat, the result is negative and is
reported as such in the paper. Majority class scores 0.537, a random draw from
the adjudicated marginal 0.427, and uniform guessing 0.250; the full rule
reaches 0.500 and the five-coordinate variant 0.550, both inside the
majority-class interval. Adding C2 and C5 to the ablation shifts exact
agreement by 0.000 (95% CI [-0.066, +0.079], exact McNemar p = 1.0).

```bash
python manuscript/scripts/analyze_claim_rule_baselines.py
```

The sample is purposive, overlaps codebook development, and has a recoverable
deterministic selection procedure for only 16 items. It gives no evidence that
the coordinates work as a four-way classifier; the paper's substantive evidence
is the cross-paper case analysis.

## Build

Regenerate every table and figure added in the revision, then compile:

```bash
cd manuscript
python scripts/build_revision_tables.py
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Re-derive the release indices and check the whole package:

```bash
python scripts/build_submission_sources.py
python scripts/build_canonical_artifact_index.py
python scripts/refresh_artifact_release_manifest.py
python scripts/validate_release.py
```

`validate_release.py` checks artifact hashes, the exclusion disclosures, the
eight-page body limit, undefined references and overfull boxes, so it is the
single command that verifies the release is internally consistent.

Code is MIT licensed. Original annotation data are CC BY 4.0 under
`DATA_LICENSE.md`; third-party source texts retain their original terms.
