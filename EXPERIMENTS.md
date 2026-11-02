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
1. **SHA-256 integrity** of `literature_map.csv` (336 canonical core records), `citation_index.csv` (390 total cited works), `coverage_decisions.csv` (476 inclusion/consolidation/exclusion records), `venue_systematic_queries.csv` (31 venue query logs), `claim_evidence_matrix.csv` (23 source-audited table rows), `paired_diagnostic_reanalysis.csv` (4 paired diagnostic re-analysis cases), `stratified_80_protocol_recoding_audit.csv` (80-study dual-coder recoding audit), `secondary_variants_71_sensitivity.csv` (71 excluded secondary variants for $N=401$ / $N=426$ full eligible pool recomputation), `warrant_micro_benchmark_audit.csv` (20-instance closed-form warrant demonstration), and `open_coding_and_temporal_audit.json`.
2. **Exact corpus stratification and search-bias sensitivity audit** (§2.2):
   - **355 primary RAG studies and benchmarks** (`330` in the frozen core map: `326` full-text-PDF verified [`98.8%`] + `4` ACM metadata/abstract records [`venue044, venue045, venue049, venue050`, `1.2%`]; plus `25` supplementary primary RAG studies).
   - **35 foundational, adjacent-benchmark, and prior-survey references** (`5` prior surveys + `1` foundational IR benchmark BEIR [`venueExpanded087`] in the core map + `29` supplementary foundational retrieval, calibration, selective prediction, transferable reasoning/calibration, and survey works).
   - **Two-phase search window, Representative-Selection Rules R1–R3, & 4-level coding validation**: separates the May 2020–June 3, 2026 core systematic freeze (`336` records) from the June–October 2026 rule-governed targeted update (`54` records under Rules S1–S3); documents the disposition of the `459` initial no-open-PDF hits and `236` Stage-1a deprioritized candidates (`167` scope exclusions vs. `69 + 2 = 71` secondary variants with `0` excluded counterexamples); reports exact pre-2024 shares (`14/336 = 4.17%` core and `38/390 = 9.74%` all cited by `year_in_map`, or `33/390 = 8.46%` by `references.bib` publication year); and validates C1–C5 across four levels (candidate disposition, upstream screening $\kappa$, $N=80$ stratified direct-protocol C1–C5 recoding $\kappa = 0.842\text{--}0.964$, and invariance of domain coverage gaps across 4 alternative coding rules).
3. **Single canonical source & C1–C5 semantic audit** (§2.2 & §8.2):
   - Confirms `set(C1_all_applicable) == {C1_evidence_state} union set(C1_secondary_regimes)` with `0/336` omissions, `0` empty metric fields, and `0` cross-file C1–C5 discrepancies across `literature_map.csv`, `citation_index.csv`, and `coverage_decisions.csv`.
   - Enforces the 5-stratum semantic audit: reclassifying BEIR (`venueExpanded087`) to foundational retrieval (`nDCG@10`/`Recall@100`, `N/A_retrieval_only_benchmark`), reclassifying URAG (`rrag001`) to `evaluation_protocol_and_benchmark` (`C3`) and `conformal_set_or_uncertainty_calibration` (`C5`), separating 17 core conformal/UQ studies from 22 abstention/clarification controllers, and aligning 12 C3 benchmark/forensic loci.
4. **Formal Proposition 1, two-sample TV concentration (W1b), one-sided Hoeffding-Bentkus FWER calibration (W1a), closed-form warrant micro-benchmark (W4), & 5-confound comparability verification** (§3.2–§3.3, §7.3, & §8.3): verifies Proposition 1 (including $(q, \mathcal{C}) \in \Omega_{\text{inv}}$ at $p_{\text{miss}}=0$ enforcing $r_0 \le \epsilon_{\text{task}}$, the counterexample at $r_0 = 0.20 > \alpha_r = 0.10$, and the 3-way separation of static violation, reachability $p_{\text{rec}} \ge 1 - p_{\text{tol}}(r_0)/p_{\text{miss}}$, and Bellman VoI optimality $\mathrm{VoI} > C_{\text{op}}$ under componentwise budget $\sum_t c_{\text{phys}}(a_t) \preceq B$ and absorbing terminal state $\bot$), two-sample TV concentration $\varepsilon_{\text{stat}} = \sqrt{(C_{\text{sem}}-1)/M} + \sqrt{\ln(2K/\delta)/M}$ (verified on the exact two-sample binomial case $P=Q=(0.5,0.5), C_{\text{sem}}=2, K=1, M=1000, \delta=10^{-12}$), one-sided truncated Hoeffding-Bentkus $p_{\lambda}^{\text{HB}}$ returning $1$ for $M_{\lambda}=0$ or $\hat{R}_{\lambda} > \alpha_r$ (verified on the F1 set-loss counterexample at $M_{\lambda}=100, \hat{R}_{\lambda}=0.20 > \alpha_r=0.10$), and the 20-instance closed-form warrant micro-benchmark (`warrant_micro_benchmark_audit.json`).

## 2. Mapping Between Manuscript Sections/Tables and Repository Artifacts

| Manuscript Section / Table / Figure | Repository Artifact & Script |
| --- | --- |
| **§2.2 Survey Scope, Coverage Bias Audit, & C1–C5 Quality Control** | `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md`, `survey_reproducibility/data/corpus_snapshot.json`, `survey_reproducibility/data/venue_systematic_queries.csv`, `survey_reproducibility/data/coverage_decisions.csv`, `survey_reproducibility/scripts/sync_canonical_data.py` |
| **§3 Conceptual Framework, Definition 1 (Properties 1–3), Operational Estimators vs. Proxies, & Table 1 (`concept_cases`)** | `survey_reproducibility/data/paired_diagnostic_reanalysis.json`, `survey_reproducibility/verify_survey_artifacts.py` |
| **§3.5 Four-Pillar Technical Taxonomy & Figure 2 (`survey_map`, 76 works across 20 strands)** | `survey_reproducibility/scripts/select_76_representative_works.py`, `survey_reproducibility/data/research_map_76_works.json`, `survey_reproducibility/data/research_map_76_works.csv` |
| **§4–§7 Technical Synthesis (Pillars I–IV) & Tables 2–4** | `survey_reproducibility/data/literature_map.csv`, `survey_reproducibility/data/citation_index.csv` |
| **§8 Evaluation Benchmarks, C1–C5 Complementary Reporting Dimensions, & Table 6 (`comparability_audit`)** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `survey_reproducibility/data/claim_evidence_matrix.json`, `survey_reproducibility/data/paired_diagnostic_reanalysis.csv` |
| **§9 Cross-Layer Interactions, Figure 3 (`evidence_lifecycle`), & Table 7 (`tradeoffs`)** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `survey_reproducibility/scripts/render_figures.py` |
