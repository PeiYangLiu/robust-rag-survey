# Robust Retrieval-Augmented Generation (RAG): Systematic Survey Code and Data

This repository distributes the reproducibility code, structured literature-mapping data, source-verified claim-evidence matrix, paired diagnostic re-analysis, and vector figure-construction scripts for **Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation**.

> **Repository scope.** Only the reproducibility code and structured data artifacts are distributed in this repository; the paper's LaTeX manuscript sources (31 pure LaTeX files) are maintained separately for Overleaf compilation.

## 1. Canonical Survey Artifacts (`survey_reproducibility/`)

| Artifact | Path | Description |
| --- | --- | --- |
| **336-Study Canonical Core Map** | `survey_reproducibility/data/literature_map.csv` | Canonical source for the $336$ deduplicated core records ($330$ primary RAG studies [$326$ full-text PDF verified + $4$ ACM metadata/abstract records] + $6$ foundational/survey records [$5$ prior surveys + $1$ foundational IR benchmark BEIR `venueExpanded087`]), mapped across the $4$ pillars, $20$ strands, and 5-stratum source-audited C1–C5 coordinates. |
| **390-Work Complete Citation Index** | `survey_reproducibility/data/citation_index.csv` | Complete index of all $390$ unique works synthesized in the survey ($355$ primary RAG studies [$330$ core + $25$ supplementary] and $35$ foundational, adjacent-benchmark, and prior-survey references [$6$ core + $29$ supplementary]), deterministically synchronized from `literature_map.csv` via `scripts/sync_canonical_data.py` with $0$ cross-file discrepancies. |
| **476-Record Screening & Consolidation Ledger** | `survey_reproducibility/data/coverage_decisions.csv` | Auditable decision log covering all $390$ included & cited works, $12$ duplicate merges (including `venue001 -> venueExpanded059`), $2$ unified-scope Rule R1 code-RAG secondary variants (`rrag194`, `rrag196`), $3$ Round-2 scope exclusions, and $69$ Map-B exclusions ($0$ legacy `outside_text_scope` tags). |
| **80-Study Direct-Protocol Recoding Audit** | `survey_reproducibility/data/stratified_80_protocol_recoding_audit.csv`, `.json` | Stratified $N=80$ sample ($4$ primary studies per each of the $20$ strands) with raw dual-coder C1–C5 labels (Coder A strand-anchored vs. Coder B blind direct-protocol recoding from experimental setups), full confusion matrices, and deterministic Cohen's $\kappa$ verification ($\kappa \in [0.842, 0.964]$). |
| **71-Variant Full Eligible Pool Sensitivity** | `survey_reproducibility/data/secondary_variants_71_sensitivity.csv`, `.json`, `open_coding_and_temporal_audit.json` | Row-level records for all $71$ excluded same-cell secondary variants ($69$ Stage-1a + $2$ Round-2 code-RAG), enabling deterministic recomputation of the pre-June full eligible pool ($N=401$) and total eligible pool ($N=426$), alongside strand-independent temporal strata and open-coding residual mechanism audits. |
| **20-Instance Warrant Micro-Benchmark Audit** | `survey_reproducibility/data/warrant_micro_benchmark_audit.csv`, `.json` | Fixed-backbone (`Llama-3.1-8B-Instruct`), fixed-budget ($B$: $\le 2$ calls, $\le 1{,}600$ tokens) 20-instance ($5$ query families $\times 4$ regimes) demonstration of closed-form reference warrant rules (a)–(d), scalar reliability $\rho(d, t_q)$, and comparative ranking reversals over single/dual proxy metrics. |
| **Source-Verified Claim–Evidence Matrix** | `survey_reproducibility/data/claim_evidence_matrix.csv`, `.json` | Row-by-row source verification for Table 6 (`comparability_audit`, 17 rows) and Table 7 (`tradeoffs`, 6 rows), binding exact paper version, PDF page, table row/column, model backbone, subset, denominator, disambiguated call/chunking cost units, and guarantee boundaries. |
| **Proposition 1 & 5-Confound Comparability Audit** | `survey_reproducibility/data/paired_diagnostic_reanalysis.json`, `.csv` | Formal Proposition 1 (full 5-constraint system, conditional reduction under $P_{\mathcal{S}}(\text{abs})=0$ and invariant $P_{\text{ans}}$ requiring $r_0 \le \min\{\alpha_r, \epsilon_{\text{task}}\}$ and $p_{\text{miss}} \le p_{\text{tol}}(r_0)$, counterexample at $r_0=0.20 > \alpha_r=0.10$, and 3-way separation of static violation, recovery reachability, and Bellman VoI optimality), fine-grained vs. coarse $D_{\mathrm{TV}}$ analysis, 5-confound comparability matrix over `C1 x C3`, and $4$ protocol-comparability case studies. |
| **Search Protocol, 4-Level Validation & Query Logs** | `survey_reproducibility/data/corpus_snapshot.json`, `venue_systematic_queries.csv`, `PROTOCOL_AND_TAXONOMY.md` | Contains all $55$ Boolean arXiv queries, $31$ venue query logs, June 3, 2026 core freeze vs. June–Oct 2026 targeted update (Rules S1–S3), Representative-Selection Rules R1–R3, 4-level validation (candidate disposition, upstream $\kappa$, $N=80$ stratified direct-protocol C1–C5 recoding $\kappa=0.842\text{--}0.964$, and 4-rule coverage-gap invariance), and explicit pre-2024 year accounting (`38/390 = 9.74%` by `year_in_map`; `33/390 = 8.46%` by `references.bib`). |
| **76-Work Taxonomy Map Manifest** | `survey_reproducibility/data/research_map_76_works.json`, `.csv` | Structured manifest of the $76$ representative works ($75$ primary RAG studies + $1$ foundational provenance benchmark `kilt2021`) organized across the $4$ intervention pillars and $20$ mechanism strands in Figure 2. |
| **Deterministic Synchronizer & Verifier** | `survey_reproducibility/scripts/sync_canonical_data.py`, `survey_reproducibility/verify_survey_artifacts.py` | Scripts that synchronize derived CSV/JSON artifacts from the canonical source and deterministically verify SHA-256 hashes, C1 set-union invariants, cross-file consistency, and formal mathematical properties. |

## 2. Quick Verification

Run the deterministic artifact verification script from the repository root:

```bash
python3 survey_reproducibility/verify_survey_artifacts.py
```

See `EXPERIMENTS.md` and `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md` for full execution and protocol documentation.
