# Artifact Mapping and Verification Guide for the Systematic Survey

This document maps each section, table, and figure of **Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation** to the structured bibliography datasets and scripts in `survey_reproducibility/`.

## 1. Deterministic Verification

From the repository root, run:

```bash
python3 survey_reproducibility/verify_survey_artifacts.py
```

This script verifies:
1. **Complete Bibliography Coverage (386 Unique Cited Works):** Confirms that `survey_reproducibility/data/citation_index.csv` indexes all 386 unique works cited in the manuscript ($355$ primary RAG studies and $31$ foundational, adjacent-benchmark, and survey references) with zero missing entries.
2. **Four-Pillar and 20-Strand Taxonomy Structure:** Confirms that all 20 mechanism strands across Pillar I (Evidence-Centric), Pillar II (Model-Centric), Pillar III (Adversarial Security), and Pillar IV (System-Level Control) are populated and mapped consistently in `literature_map.csv` and `research_map_76_works.json`.
3. **Formal Mathematical Properties (Section 3):** Verifies the mathematical properties of Definition 1 (Equations 2 to 5), Proposition 1 (static abstention tolerance $p_{\text{tol}}(r_0)$ versus positive Value-of-Information re-retrieval $\mathrm{VoI} > C_{\text{op}}$ in Equation 9), two-sample semantic total variation concentration $\varepsilon_{\text{stat}}(M, C_{\text{sem}}, K, \delta)$, and one-sided binomial and Hoeffding-Bentkus selective risk calibration.

## 2. Mapping Between Manuscript Sections and Repository Artifacts

| Manuscript Section / Table / Figure | Repository Artifact & Script |
| --- | --- |
| **§2.2 Survey Scope and Literature Coverage** | `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md`, `survey_reproducibility/data/citation_index.csv`, `survey_reproducibility/data/venue_systematic_queries.csv` |
| **§3 Conceptual Framework, Definition 1 (Properties 1 to 3), & Table 1 (`concept_cases`)** | `survey_reproducibility/verify_survey_artifacts.py`, `survey_reproducibility/figures/redraw_figures_1_3.py` |
| **§3.5 Four-Pillar Technical Taxonomy & Figure 2 (`survey_map`, 76 works across 20 strands)** | `survey_reproducibility/scripts/select_76_representative_works.py`, `survey_reproducibility/data/research_map_76_works.json`, `survey_reproducibility/data/research_map_76_works.csv`, `survey_reproducibility/figures/redraw_figure_2_map.py` |
| **§4 to §7 Technical Synthesis (Pillars I to IV) & Tables 2 to 4** | `survey_reproducibility/data/literature_map.csv`, `survey_reproducibility/data/citation_index.csv` |
| **§8 Evaluation Benchmarks and Metrics (§8.1 Benchmark Suites, Table 5; §8.2 Evaluation Metrics, Table 6)** | `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md`, `survey_reproducibility/data/citation_index.csv` |
| **§9 Cross-Layer Interactions, Figure 3 (`evidence_lifecycle`), & Table 7 (`tradeoffs`)** | `survey_reproducibility/scripts/render_figures.py`, `survey_reproducibility/figures/redraw_figures_1_3.py` |
