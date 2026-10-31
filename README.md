# Robust Retrieval-Augmented Generation (RAG): Systematic Survey Code and Data

This repository distributes the reproducibility code, structured literature-mapping data, and figure-construction scripts for **Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation**.

> **Repository scope.** Only the reproducibility code and structured data artifacts are distributed in this repository; the paper's LaTeX manuscript sources are maintained separately for Overleaf compilation.

## 1. Structured Survey Artifacts (`survey_reproducibility/`)

| Artifact | Path | Description |
| --- | --- | --- |
| **335-Study Core Evidence Map** | `survey_reproducibility/data/literature_map.csv` | Deduplicated core Map-B studies ($330$ primary RAG studies + $5$ prior surveys), encoding mechanisms (`method_family`, `intervention_point`), threat conditions (`failure_or_risk_type`, `C1_evidence_state`, `C2_disturbance_origin`, `C2_capability_and_budget`), evaluation setups (`benchmark_or_task`, `metrics_reported_or_relevant`, `C4_outcome_metric`), action policies (`C5_action_policy`), multi-label coverage (`C1_all_applicable` to `C5_all_applicable`), verification status, and core conclusions/boundaries (`actual_contribution`, `limitation_or_note`). |
| **389-Work Citation Index** | `survey_reproducibility/data/citation_index.csv` | Complete index of all $389$ unique works synthesized in the survey ($335$ core Map-B records + $26$ supplementary primary RAG studies + $28$ foundational/survey references), mapped to C1–C5 coordinates and manuscript sections. |
| **476-Record Inclusion/Exclusion Ledger** | `survey_reproducibility/data/coverage_decisions.csv` | Auditable decision log covering all $389$ included & cited works, $7$ cross-stratum duplicate merges, $6$ Round-2 adjudication exclusions, and $74$ Map-B venue-expansion adjudication exclusions with rationales. |
| **Search Protocol & Snapshot Metadata** | `survey_reproducibility/data/corpus_snapshot.json` | Contains all $55$ Boolean arXiv queries, $30$ structured venue queries, stage-by-stage screening funnel counts, C1–C5 precedence codebook, and SHA-256 checksums. |
| **76-Paper Taxonomy Map Manifest** | `survey_reproducibility/data/research_map_76_works.json`, `survey_reproducibility/data/research_map_76_works.csv` | Structured manifest of the $76$ representative primary works organized across the $4$ intervention pillars and $20$ mechanism strands in Figure 2. |
| **Artifact Verifier** | `survey_reproducibility/verify_survey_artifacts.py` | Deterministic self-check script verifying SHA-256 hashes, deduplication counts, coordinate coverage, and the 4-pillar / 20-strand / 76-paper taxonomy manifest. |
| **Vector Figure Builders** | `survey_reproducibility/figures/redraw_figures_1_3.py`, `survey_reproducibility/figures/redraw_figure_2_map.py` | Native 2D PowerPoint/vector diagram builders for Figure 1 (Core Principles), Figure 2 (76-Paper Taxonomy Map), and Figure 3 (Compound Error Propagation and Lineage-Guided Recovery). |

## 2. Quick Verification

Run the deterministic artifact verification script from the repository root:

```bash
python3 survey_reproducibility/verify_survey_artifacts.py
```

See `EXPERIMENTS.md` for detailed documentation of the corpus collection scripts, adjudication ledgers in `manuscript/supplement/` and `manuscript/human_coding/`, and taxonomy construction pipelines.
