# Reproducibility Pipeline and Artifact Mapping for the 10-Section Systematic Survey

This document maps every section, table, and figure of the current 10-section manuscript (**Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation**) to the reproducible scripts and structured datasets in this repository.

> **Note on repository structure.** All canonical datasets, taxonomic mappings, source-verification matrices, paired diagnostic re-analyses, and verification scripts for the current 10-section systematic survey reside in `survey_reproducibility/`. Root-level directories such as `expert_validation*`, `annotation_outputs*`, and `blind_review_deliverables*` are archived historical artifacts from an earlier exploratory draft and are **not** used as empirical claims in the current survey manuscript.

## 1. End-to-End Synchronization and Verification of All Survey Artifacts

From the repository root, run:

```bash
python3 survey_reproducibility/scripts/sync_canonical_data.py
python3 survey_reproducibility/verify_survey_artifacts.py
```

These scripts deterministically verify:
1. **SHA-256 integrity** of `literature_map.csv` (336 canonical core records), `citation_index.csv` (390 total cited works), `coverage_decisions.csv` (476 inclusion/consolidation/exclusion records), `venue_systematic_queries.csv` (31 venue query logs), `claim_evidence_matrix.csv` (23 source-audited table rows), and `paired_diagnostic_reanalysis.csv` (4 paired diagnostic re-analysis cases).
2. **Exact corpus stratification and search-bias sensitivity audit** (§2.2):
   - **356 primary RAG studies and benchmarks** (`331` in the frozen core map: `327` full-text-PDF verified [`98.8%`] + `4` ACM metadata/abstract records [`venue044, venue045, venue049, venue050`, `1.2%`]; plus `25` supplementary primary RAG studies).
   - **34 foundational, adjacent-transferable, and prior-survey references** (`5` prior surveys in the core map + `29` supplementary foundational retrieval, calibration, selective prediction, transferable reasoning/calibration, and survey works).
   - **Search bias & funnel disposition accounting**: documents the disposition of the `459` initial no-open-PDF hits (`312` deduplicated against open versions in venue sweeps, `143` out-of-scope stubs, `4` ACM metadata/abstract records), the `236` Stage-1a deprioritized candidates (`167` scope exclusions for routine domain deployment without an $\Omega$ stressor vs. `69` representative-selection exclusions of secondary variants), pre-2024 recency remediation (`4.2%` in core map $\to 11.8%` across all 390 cited works), and C1–C5 coordinate sensitivity drift ($\le 2.12$ percentage points across `327`, `331`, and `356` studies).
3. **Single canonical source & C1–C5 semantic audit** (§2.2 & §8.2):
   - Confirms `set(C1_all_applicable) == {C1_evidence_state} union set(C1_secondary_regimes)` with `0/336` omissions, `0` empty metric fields, and `0` cross-file C1–C5 discrepancies across `literature_map.csv`, `citation_index.csv`, and `coverage_decisions.csv`.
   - Records the `26` C1 benchmark/modality reclassifications (e.g., `rrag037` Park & Lee, `rrag019` SafeRAG, `rrag032` CUB, `rrag040` FaithEval, `rgb2023` RGB), `15` C2 reconciliations (e.g., `rrag120` DIGA), `10` C4 metric-denominator alignments, and the `41` multi-regime studies whose strand-anchored primary `C1_evidence_state` is accompanied by a higher-severity secondary evaluation split in `C1_secondary_regimes`.
4. **Formal mathematical & paired diagnostic verification** (§3.2–§3.3, §7.5, & §8.3): verifies the symmetric F1 set-mismatch loss, the 3-class semantic $D_{\mathrm{TV}}$ vs. accuracy counterexample ($D_{\mathrm{TV}} = 0.20$ at equal accuracy $0.80$), the joint Property 1 + Property 3 scoring rule under retrieval omissions, the population CPOMDP dual threshold calibration, and the 4 paired diagnostic re-analyses in `paired_diagnostic_reanalysis.json`.

## 2. Mapping Between Manuscript Sections/Tables and Repository Artifacts

| Manuscript Section / Table / Figure | Repository Artifact & Script |
| --- | --- |
| **§2.2 Survey Scope, Coverage Bias Audit, & C1–C5 Quality Control** | `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md`, `survey_reproducibility/data/corpus_snapshot.json`, `survey_reproducibility/data/venue_systematic_queries.csv`, `survey_reproducibility/data/coverage_decisions.csv`, `survey_reproducibility/scripts/sync_canonical_data.py` |
| **§3 Conceptual Framework, Definition 1 (Properties 1–3), Operational Estimators vs. Proxies, & Table 1 (`concept_cases`)** | `survey_reproducibility/data/paired_diagnostic_reanalysis.json`, `survey_reproducibility/verify_survey_artifacts.py` |
| **§3.5 Four-Pillar Technical Taxonomy & Figure 2 (`survey_map`, 76 works across 20 strands)** | `survey_reproducibility/scripts/select_76_representative_works.py`, `survey_reproducibility/data/research_map_76_works.json`, `survey_reproducibility/data/research_map_76_works.csv` |
| **§4–§7 Technical Synthesis (Pillars I–IV) & Tables 2–4** | `survey_reproducibility/data/literature_map.csv`, `survey_reproducibility/data/citation_index.csv` |
| **§8 Evaluation Benchmarks, C1–C5 Complementary Reporting Dimensions, & Table 6 (`comparability_audit`)** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `survey_reproducibility/data/claim_evidence_matrix.json`, `survey_reproducibility/data/paired_diagnostic_reanalysis.csv` |
| **§9 Cross-Layer Interactions, Figure 3 (`evidence_lifecycle`), & Table 7 (`tradeoffs`)** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `survey_reproducibility/scripts/render_figures.py` |
