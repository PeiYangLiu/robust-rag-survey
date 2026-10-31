# Robust Retrieval-Augmented Generation (RAG): Systematic Survey Code and Data

This repository distributes the reproducibility code, structured literature-mapping data, source-verified claim-evidence matrix, paired diagnostic re-analysis, and vector figure-construction scripts for **Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation**.

> **Repository scope.** Only the reproducibility code and structured data artifacts are distributed in this repository; the paper's LaTeX manuscript sources (31 pure LaTeX files) are maintained separately for Overleaf compilation.

## 1. Canonical Survey Artifacts (`survey_reproducibility/`)

| Artifact | Path | Description |
| --- | --- | --- |
| **336-Study Canonical Core Map** | `survey_reproducibility/data/literature_map.csv` | Canonical source for the $336$ deduplicated core studies ($331$ primary RAG studies [$327$ full-text PDF verified + $4$ ACM metadata/abstract records] + $5$ prior surveys), mapped to the $4$ pillars (`taxonomy_pillar`), $20$ strands (`mechanism_strand`), C1–C5 complementary reporting coordinates (`C1_evidence_state`, `C1_secondary_regimes`, `C1_all_applicable = {C1_evidence_state} U C1_secondary_regimes`), source-verified metrics (`metrics_reported_or_relevant`), and scope notes (`actual_contribution`, `limitation_or_note`). |
| **390-Work Complete Citation Index** | `survey_reproducibility/data/citation_index.csv` | Complete index of all $390$ unique works synthesized in the survey ($356$ primary RAG studies [$331$ core + $25$ supplementary] and $34$ foundational, adjacent-transferable, and prior-survey references [$5$ core + $29$ supplementary]), deterministically synchronized from `literature_map.csv` via `scripts/sync_canonical_data.py` with $0$ cross-file discrepancies. |
| **476-Record Screening & Consolidation Ledger** | `survey_reproducibility/data/coverage_decisions.csv` | Auditable decision log covering all $390$ included & cited works, $11$ duplicate merges, $6$ Round-2 exclusions, and $69$ Map-B exclusions, deterministically synchronized with `citation_index.csv` ($0$ C1–C5 discrepancies). |
| **Source-Verified Claim–Evidence Matrix** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `.json` | Row-by-row source verification for Table 6 (`comparability_audit`, 17 rows) and Table 7 (`tradeoffs`, 6 rows), binding exact paper version, PDF page, table row/column, model backbone, subset, denominator, disambiguated cost units, and evidence tiers. |
| **Paired Diagnostic Re-Analysis (W2 & W4)** | `survey_reproducibility/data/paired_diagnostic_reanalysis.json`, `.csv` | Operational estimator taxonomy (separating direct estimators of Equations 2–5 from directional proxy metrics and untested properties) and $4$ reproducible paired re-analyses (RECOMP vs. xRAG; Base vs. CAD/IRCAN vs. RAAT vs. Parenting; RAAT vs. RGB vs. Chain-of-Note denominator audit; and static abstention vs. VoI recovery under recall misses). |
| **Search Protocol, Bias Audit & Query Logs** | `survey_reproducibility/data/corpus_snapshot.json`, `venue_systematic_queries.csv`, `PROTOCOL_AND_TAXONOMY.md` | Contains all $55$ Boolean arXiv queries, $31$ venue query logs, screening funnel accounting (including disposition of the $236$ deprioritized candidates and $459$ initial no-open-PDF hits), C1–C5 semantic audit log, and sensitivity analysis ($\le 2.12$ pp max drift). |
| **76-Work Taxonomy Map Manifest** | `survey_reproducibility/data/research_map_76_works.json`, `.csv` | Structured manifest of the $76$ representative works ($75$ primary RAG studies + $1$ foundational provenance benchmark `kilt2021`) organized across the $4$ intervention pillars and $20$ mechanism strands in Figure 2. |
| **Deterministic Synchronizer & Verifier** | `survey_reproducibility/scripts/sync_canonical_data.py`, `survey_reproducibility/verify_survey_artifacts.py` | Scripts that synchronize derived CSV/JSON artifacts from the canonical source and deterministically verify SHA-256 hashes, C1 set-union invariants, cross-file consistency, and formal mathematical properties. |

## 2. Quick Verification

Run the deterministic artifact verification script from the repository root:

```bash
python3 survey_reproducibility/verify_survey_artifacts.py
```

See `EXPERIMENTS.md` and `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md` for full execution and protocol documentation.
