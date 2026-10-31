# Reproducibility Pipeline and Artifact Mapping for the 10-Section Systematic Survey

This document maps every section, table, and figure of the current 10-section manuscript (**Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation**) to the reproducible scripts and structured datasets in this repository.

> **Note on repository structure.** All canonical datasets, taxonomic mappings, source-verification matrices, and verification scripts for the current 10-section systematic survey reside in `survey_reproducibility/`. Root-level directories such as `expert_validation*`, `annotation_outputs*`, and `blind_review_deliverables*` are archived historical artifacts from an earlier exploratory draft and are **not** used as empirical claims in the current survey manuscript.

## 1. End-to-End Verification of All Survey Artifacts

From the repository root, run:

```bash
python3 survey_reproducibility/verify_survey_artifacts.py
```

This script deterministically verifies:
1. **SHA-256 integrity** of `literature_map.csv` (336 core records), `citation_index.csv` (390 total cited works), `coverage_decisions.csv` (476 inclusion/consolidation/exclusion records), `venue_systematic_queries.csv` (31 venue query logs), and `claim_evidence_matrix.csv` (23 source-verified table rows).
2. **Exact corpus stratification** (§2.2):
   - **356 primary RAG studies and benchmarks** (`331` in the frozen core map: `327` full-text-PDF verified + `4` ACM metadata/abstract records; plus `25` supplementary primary RAG studies).
   - **34 foundational, adjacent-transferable, and prior-survey references** (`5` prior surveys in the core map + `29` supplementary foundational retrieval, calibration, selective prediction, transferable reasoning/calibration, and survey works).
   - **76 representative works in Figure 2** (`75` primary RAG studies + `1` foundational provenance benchmark `kilt2021`) spanning the 4 intervention pillars and 20 mechanism strands.
3. **Field-level semantic audit**: confirms zero invalid metric tags in `literature_map.csv`, zero spurious `selective_risk_and_calibration_ece` tags on non-calibration works (e.g., RECOMP `rrag226`), zero spurious `adversarially_manipulated` tags on non-adversarial works (e.g., `venueExpanded025`), and explicit `taxonomy_pillar` and `mechanism_strand` assignments across all 390 records.
4. **Formal mathematical verification** (§3.2–§3.3 & §7.5): verifies that the slack-normalized responsiveness criterion in Equation (3) and the non-negative shifted CPOMDP dual loss in Equations (4) and (9) are free of algebraic counterexamples across the 5 paired diagnostic scenarios.

## 2. Mapping Between Manuscript Sections/Tables and Repository Artifacts

| Manuscript Section / Table / Figure | Repository Artifact & Script |
| --- | --- |
| **§2.2 Survey Scope and Literature Coverage** | `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md`, `survey_reproducibility/data/corpus_snapshot.json`, `survey_reproducibility/data/venue_systematic_queries.csv`, `survey_reproducibility/data/coverage_decisions.csv` |
| **§3 Conceptual Framework, Definition 1 (Properties 1–3), Figure 1, & Table 1 (`concept_cases`)** | `survey_reproducibility/scripts/render_figures.py`, `survey_reproducibility/verify_survey_artifacts.py` |
| **§3.5 Four-Pillar Technical Taxonomy & Figure 2 (`survey_map`, 76 works across 20 strands)** | `survey_reproducibility/scripts/select_figure2_76_works.py`, `survey_reproducibility/data/research_map_76_works.json`, `survey_reproducibility/data/research_map_76_works.csv` |
| **§4–§7 Technical Synthesis (Pillars I–IV) & Tables 2–4** | `survey_reproducibility/data/literature_map.csv`, `survey_reproducibility/data/citation_index.csv` |
| **§8 Evaluation Benchmarks, C1–C5 Protocol Dimensions, & Table 6 (`comparability_audit`)** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `survey_reproducibility/data/claim_evidence_matrix.json` |
| **§9 Cross-Layer Interactions, Figure 3 (`evidence_lifecycle`), & Table 7 (`tradeoffs`)** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `survey_reproducibility/scripts/render_figures.py` |
