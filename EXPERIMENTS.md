# Experiments: code, order of execution, and what each stage produces

This file maps every empirical claim in the submission
(`manuscript/main_survey.tex`) to the script that produces it and the artifact it
writes. The canonical artifact inventory is in `README.md`; this file is the
*execution* view.

Everything is run from the repository root. Paths in released JSON/CSV are
repository-relative, so a clone can re-run the pipeline without editing paths.

## 0. Prerequisites

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install numpy scipy pandas statsmodels matplotlib requests
```

API-served judges read credentials from the environment; nothing is stored in
the repository:

```bash
export JUDGE_API_KEY=...        # provider key
export JUDGE_BASE_URL=...       # provider endpoint
```

Open-weight judges were run on a GPU cluster through Amulet. The submitted
configs in `configs/amlt_*.yaml` have the cluster and workspace names replaced
by `<SINGULARITY_VC>` / `<AML_WORKSPACE>` placeholders; set them to your own
before submitting.

## 1. Corpus construction (inputs to everything else)

| Step | Script | Output |
| --- | --- | --- |
| Harvest arXiv + venue candidates | `scripts/collect_papers.py`, `scripts/collect_openreview_pmlr_accepted.py` | `metadata/`, `pdfs/` (git-ignored) |
| Venue matching and download | `scripts/match_and_download_venue_accepts.py` | `metadata/venue_accepts_*.csv` |
| Build the venue-expanded evidence map | `scripts/build_venue_expanded_evidence_map.py` | `manuscript/supplement/evidence_map_venue_expanded_adjudicated.csv` |

PDFs and extracted texts are deliberately git-ignored (third-party content,
several GB). Re-run the collectors to regenerate them.

## 2. §9 Testing the taxonomy — constructed instrument benchmark

Answers: *can independent coders recover the five coordinates from prose?*

```bash
python3 manuscript/scripts/build_comparability_instrument_benchmark_v2.py
bash    manuscript/scripts/run_comparability_instrument_v2.sh      # judge panel
python3 manuscript/scripts/analyze_comparability_instrument_v2.py
```

Produces the 432 constructed passages, the per-judge decisions, and
`manuscript/supplement/comparability_instrument_results_v2.json`, which backs the
0.95 coordinate accuracy / kappa 0.74 numbers and Appendix Tables
`instrument_disclosure_v2` and `instrument_baselines_v2`.

## 3. §10 Applied at scale — screening frame and census

Answers: *how often are cross-paper numbers juxtaposed, and does the gap survive?*

```bash
python3 manuscript/scripts/build_cross_paper_frame.py     # 259 texts -> 1,703 candidates
python3 manuscript/scripts/code_cross_paper_frame.py      # 3-judge coding
python3 manuscript/scripts/analyze_cross_paper_census.py  # eligibility, verdicts, kappa
```

Codebook ablation (the C1/C4 reduced arm):

```bash
bash    manuscript/scripts/run_codebook_ablation.sh
python3 manuscript/scripts/analyze_codebook_ablation.py
```

## 4. §10 Provenance — transported vs. re-implemented

```bash
python3 manuscript/scripts/build_provenance_benchmark.py
python3 manuscript/scripts/classify_number_provenance.py
bash    manuscript/scripts/run_provenance_benchmark.sh
python3 manuscript/scripts/analyze_provenance_benchmark.py
python3 manuscript/scripts/verify_provenance_number_trace.py
```

Backs the 533-of-610 re-implementation share and the 0.91 [0.86, 0.96]
provenance accuracy.

## 5. §10 Evaluator panels and diagnostic interventions

| Arm | Script |
| --- | --- |
| Crossed deployment panel (API + open models) | `manuscript/scripts/run_controlled_model_judges_v2.py`, `analyze_controlled_model_judges_v2.py` |
| Open-weight pool (9 checkpoints) | `manuscript/scripts/orchestrate_gpu_model_judges.py`, `dispatch_model_judge_runs.py` |
| Non-generative structural classifier | `manuscript/scripts/run_action_labeled_llm_baseline.py`, `analyze_claim_rule_baselines.py` |
| Evidence-privileged reference | `manuscript/scripts/derive_observed_claim_verdicts.py` |
| Screen recall re-weighting | `manuscript/scripts/run_screen_recall.sh`, `analyze_screen_recall.py` |

Raw per-decision dumps are git-ignored (≈370 MB); the analysis-level JSON/CSV
they reduce to are committed.

## 6. §10 Human expert panel

80 published claims, three annotators, 210 person-hours, senior adjudication.

- Instruments and annotations: `manuscript/human_coding/`
- Analysis: `manuscript/scripts/analyze_published_human_evaluation_audit.py`
- Result: `manuscript/supplement/human_anchor_results.json`

Consent forms and participant identities are access-controlled and excluded by
`.gitignore`; only labels, rationales and adjudicated consensus are released.

## 7. Appendix Q — reviewer heterogeneity and remedy simulation

```bash
python3 manuscript/scripts/estimate_sigma_r_multi_anchor.py    # sigma_r from crossed designs
python3 manuscript/scripts/simulate_retrospective_remedies.py  # size/power of 4 analyses
python3 manuscript/scripts/simulate_assignment_unit_mismatch.py
```

The public corpora used as sigma_r anchors (civil_comments, Wikipedia Detox,
MultiPref, DynaSent) are **not** redistributed here; the scripts download them
from their original sources into `manuscript/supplement/sigma_anchors/`.

## 8. Figures and tables

```bash
python3 manuscript/scripts/draw_python_figures.py
python3 manuscript/scripts/build_revision_tables.py
```

## 9. Self-checks (run before every build)

```bash
bash manuscript/scripts/verify_all.sh
```

Three checks, 117 provenance assertions plus quotation and prose/artifact
consistency:

1. `verify_cross_paper_cases.py` — re-opens every ledger quotation at its cited
   line range and re-derives every rendered numeral.
2. `verify_manuscript_quotations.py` — every quotation in the manuscript and its
   tables is matched verbatim against the source text.
3. `verify_prose_artifact_consistency.py` — every number the prose asserts about
   our own artifacts is compared to the artifact.

## 10. Building the paper

```bash
cd manuscript && latexmk -pdf -interaction=nonstopmode main_survey.tex
```

Content sections occupy exactly 8 pages; Limitations, Ethics, references and the
appendix follow.
