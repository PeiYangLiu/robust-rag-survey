# Systematic Literature Protocol, Taxonomic Coding Rules, and Cross-Classification Matrix

## 1. Search Scope, Platforms, and Boolean Query Structure
- **Time Window**: May 2020 (following the introduction of Retrieval-Augmented Generation, Lewis et al., 2020) through June 2026.
- **Indexed Digital Libraries & Venues**:
  - **ACL Anthology**: ACL, EMNLP, NAACL, EACL, TACL, COLING, Findings.
  - **OpenReview / ML Conferences**: ICLR, NeurIPS, ICML.
  - **Security Venues**: USENIX Security, IEEE S&P, ACM CCS, NDSS.
  - **Information Retrieval & Web Venues (ACM DL / IEEE Xplore)**: SIGIR, WWW, KDD, CIKM, WSDM, TOIS, TKDE.
  - **AI & Preprint Repositories**: AAAI, IJCAI, arXiv (`cs.CL`, `cs.IR`, `cs.CR`, `cs.LG`, `cs.AI`).
- **Boolean Query Construction (Title / Abstract Fields)**:
  - **Clause A (RAG Architecture & Paradigm)**:
    `("retrieval-augmented generation" OR "retrieval augmented generation" OR "RAG" OR "retrieval-augmented language model" OR "RALM" OR "grounded generation" OR "open-domain question answering" OR "GraphRAG" OR "multimodal RAG" OR "TableRAG" OR "agentic RAG")`
  - **Clause B (Perturbation Regimes & Robustness Mechanisms)**:
    - *Pillar I (Evidence & Context)*: `("retrieval noise" OR "noisy context" OR "irrelevant context" OR "hard negative" OR "distractor" OR "lost in the middle" OR "position bias" OR "context compression" OR "context filtering" OR "query robustness" OR "source reliability" OR "temporal drift")`
    - *Pillar II (Model Reading & Conflict)*: `("knowledge conflict" OR "context-memory conflict" OR "inter-context conflict" OR "counterfactual robustness" OR "contextual faithfulness" OR "citation grounding" OR "hallucination detection" OR "representation steering")`
    - *Pillar III (Adversarial Security)*: `("corpus poisoning" OR "knowledge poisoning" OR "retrieval poisoning" OR "backdoor attack" OR "indirect prompt injection" OR "certified robustness" OR "forensic traceback" OR "data extraction")`
    - *Pillar IV (System Calibration & Control)*: `("adaptive retrieval" OR "corrective RAG" OR "sufficient context" OR "unanswerable" OR "selective abstention" OR "uncertainty calibration" OR "conformal prediction" OR "multi-agent debate")`

## 2. Deduplication, Version Consolidation, and Screening Criteria
1. **Version Consolidation**: When an arXiv preprint has a corresponding peer-reviewed conference or journal publication, both records are merged into a single canonical bibliography entry carrying the peer-reviewed venue metadata.
2. **Homonymous Study Disambiguation**: Distinct papers sharing identical or similar system names (e.g., *LongRAG* by Zhao et al., EMNLP 2024 on dual-perspective LongBench multi-hop QA vs. *LongRAG* by Jiang et al., 2024 on 4K-token retrieval units; *MIRAGE* metric-sensitivity benchmark vs. *MIRAGE* surrogate black-box poisoning attack) are disambiguated by author list, venue, task setup, and evaluation metric.
3. **Inclusion and Exclusion Criteria**:
   - **Included ($N = 389$ unique works)**:
     - **$335$ Primary Robust RAG Studies & Benchmarks**: Papers that directly formalize, diagnose, attack, defend, mitigate, or benchmark RAG pipelines under query variations ($\Omega_q$), retrieval noise ($\Omega_{	ext{ret}}$), knowledge conflicts ($\Omega_{	ext{conf}}$), evidential insufficiency ($\Omega_{	ext{gap}}$), or adversarial manipulation ($\Omega_{	ext{adv}}$).
     - **$26$ Structural & Ecosystem Extensions**: GraphRAG, tabular RAG, multimodal (vision, video, 3D) RAG, and persistent agentic RAG works analyzing grounding and robustness across rich modalities.
     - **$28$ Foundational & Survey References**: Classical retrieval (DPR, REALM, FiD, BEIR, KILT), statistical selective prediction and calibration (Chow, 1970; Geifman & El-Yaniv, 2017; Guo et al., 2017), and prior RAG/conflict/abstention/security surveys.
   - **Excluded**: Domain-specific RAG deployment descriptions that neither evaluate robustness under imperfect evidence nor propose a mechanism addressing $\Omega$.

## 3. Two-Axis Taxonomic Coding (C3 Locus $\times$ C1/C2 Regime) and Multi-Label Assignment
Our four-pillar taxonomy couples **architectural intervention locus (C3)** with **perturbation origin and capability (C1/C2)**:
- **Pillar I (Evidence-Centric Robustness, §4)**: Acquisition and context-assembly interface $(q, \mathcal{C}) \mapsto C$ under $\Omega_q, \Omega_{\text{ret}}, \Omega_{\text{gap}}$.
- **Pillar II (Model-Centric Robustness, §5)**: Generator reading and integration interface $(q, C, \theta) \mapsto P_{\mathcal{G}_{\theta}}(Y \mid q, C)$ under $\Omega_{\text{ret}}, \Omega_{\text{conf}}$.
- **Pillar III (Adversarial Robustness and Security, §6)**: Worst-case intentional perturbations $\Omega_{\text{adv}}$ across C1/C2, with defenses cross-classified across architectural loci:
  - *Stage 1 (Ingestion & Reranker Defenses)* $\leftrightarrow$ Acquisition Interface (C3: Index & Retriever).
  - *Stage 2 (Context & Activation Sanitization)* $\leftrightarrow$ Reading Interface (C3: Context & Generator Layers).
  - *Stages 3 & 4 (Cross-Document Isolation, Certification, & Forensic Traceback)* $\leftrightarrow$ Supervisory Control Interface (C3: Multi-Pass Aggregation & State Purge).
- **Pillar IV (System-Level Robustness and Adaptive Control, §7)**: Closed-loop supervisory control policy $\Pi(a_t \mid b_t, B_t)$ across $\Omega$.

In `data/citation_index.csv` and `data/literature_map.csv`, each study is assigned both a primary taxonomic strand (among the 20 strands in Sections 4–7) and structured C1–C5 protocol coordinates (`N/A (foundational_or_survey)` for non-experimental theoretical or survey references).

## 4. Selection Rules for the 76 Representative Works in Figure 2
The script `scripts/select_figure2_76_works.py` maps 76 representative primary works across the 4 pillars and 20 mechanism strands ($3\text{ to }4$ works per strand) recorded in `data/research_map_76_works.json` and `data/research_map_76_works.csv` according to three explicit criteria:
1. **Foundational Formulation**: Introduces the canonical problem formulation, mathematical objective, or attack/defense paradigm for that mechanism strand.
2. **Mechanistic Diversity Across C3/C5**: Spans distinct algorithmic sub-mechanisms within the strand (e.g., single-pass FFN neuron suppression in ParamMute vs. two-pass logit/hidden-state contrast in CoRect; empirical cluster filtering in TrustRAG vs. provable $G = \lceil k/\omega \rceil$ group certification in RobustRAG).
3. **Benchmark & Protocol Coverage Across C1–C4**: Anchors the canonical benchmark suites and evaluation protocols synthesized in Section 8 and Table 5.
