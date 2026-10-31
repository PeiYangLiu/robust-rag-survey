# Robust Retrieval-Augmented Generation (RAG): Systematic Survey Code and Data

This repository distributes the reproducibility code, structured literature-mapping data, source-verified claim-evidence matrix, and vector figure-construction scripts for **Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation**.

> **Repository scope.** Only the reproducibility code and structured data artifacts are distributed in this repository; the paper's LaTeX manuscript sources (31 pure LaTeX files) are maintained separately for Overleaf compilation.

## 1. Canonical Survey Artifacts (`survey_reproducibility/`)

| Artifact | Path | Description |
| --- | --- | --- |
| **336-Study Core Evidence Map** | `survey_reproducibility/data/literature_map.csv` | Deduplicated core Map-B studies ($331$ primary RAG studies [$327$ full-text PDF verified + $4$ ACM metadata/abstract records] + $5$ prior surveys), mapped to the $4$ intervention pillars (`taxonomy_pillar`), $20$ mechanism strands (`mechanism_strand`), C1–C5 protocol coordinates, paper-specific evaluation metrics (`metrics_reported_or_relevant`), and scope boundaries (`actual_contribution`, `limitation_or_note`). |
| **390-Work Complete Citation Index** | `survey_reproducibility/data/citation_index.csv` | Complete index of all $390$ unique works synthesized in the survey ($356$ primary RAG studies [$331$ core + $25$ supplementary] and $34$ foundational, adjacent-transferable, and prior-survey references [$5$ core + $29$ supplementary]), mapped to the $4$ pillars, $20$ strands, and C1–C5 coordinates. |
| **Source-Verified Claim–Evidence Matrix** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `.json` | Row-by-row source verification for Table 6 (`comparability_audit`, 17 rows) and Table 7 (`tradeoffs`, 6 rows), recording exact paper section/table locations, experimental setups, denominators, findings, and evidence tiers (`direct_empirical_finding`, `formal_theorem_or_bound`, `cross_study_mechanistic_synthesis`, `open_testable_hypothesis`). |
| **476-Record Screening & Consolidation Ledger** | `survey_reproducibility/data/coverage_decisions.csv` | Auditable decision log covering all $390$ included & cited works, $7$ cross-stratum duplicate merges, $6$ Round-2 exclusions, and $74$ Map-B venue-expansion exclusions with rationales. |
| **Search Protocol & Query Logs** | `survey_reproducibility/data/corpus_snapshot.json`, `venue_systematic_queries.csv`, `PROTOCOL_AND_TAXONOMY.md` | Contains all $55$ Boolean arXiv queries (with recency-truncation mitigation rules), $31$ venue query logs ($1$ full ACL Anthology bib scan + $15$ DBLP + $15$ OpenAlex API queries), screening funnel accounting, and taxonomic coding rules. |
| **76-Work Taxonomy Map Manifest** | `survey_reproducibility/data/research_map_76_works.json`, `.csv` | Structured manifest of the $76$ representative works ($75$ primary RAG studies + $1$ foundational provenance benchmark `kilt2021`) organized across the $4$ intervention pillars and $20$ mechanism strands in Figure 2. |
| **Deterministic Artifact Verifier** | `survey_reproducibility/verify_survey_artifacts.py` | Self-check script verifying SHA-256 hashes, deduplication counts, field-level semantic validity, 4-pillar/20-strand coverage, and mathematical non-degeneracy of Equations (2)–(5) and (9). |
| **Vector Figure & Selection Scripts** | `survey_reproducibility/scripts/select_figure2_76_works.py`, `render_figures.py` | Scripts that select the 76 representative works and build the native 2D vector diagrams for Figures 1–3. |

## 2. Quick Verification

Run the deterministic artifact verification script from the repository root:

```bash
python3 survey_reproducibility/verify_survey_artifacts.py
```

See `EXPERIMENTS.md` and `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md` for full execution and protocol documentation.
