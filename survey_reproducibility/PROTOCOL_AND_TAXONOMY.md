# Literature Scope, Four-Pillar Taxonomy, and Evaluation Framework

## 1. Literature Scope and Venue Coverage
- **Synthesized Corpus (386 Unique Cited Works):**
  - **355 Primary RAG Studies and Benchmarks** spanning query reformulation, context filtering and compression, positional bias mitigation, source provenance, noise-resilient reading, knowledge conflict resolution, white-box representation steering, adversarial poisoning and prompt injection, uncertainty calibration, and closed-loop adaptive control.
  - **31 Foundational, Adjacent-Benchmark, and Survey References** covering dense retrieval foundations, statistical concentration and multiple-testing theory, distribution-free risk control, transferable reasoning and code calibration, zero-shot IR benchmarking, and prior RAG surveys.
- **Covered Venues and Digital Libraries:**
  - **Natural Language Processing:** ACL, EMNLP, NAACL, EACL, TACL, COLING.
  - **Machine Learning:** ICLR, NeurIPS, ICML, AAAI.
  - **Information Retrieval and Web Mining:** SIGIR, WWW, KDD, CIKM, WSDM.
  - **Security:** USENIX Security, IEEE S&P, ACM CCS.
  - **Preprints:** arXiv (`cs.CL`, `cs.IR`, `cs.CR`, `cs.LG`, `cs.AI`).
- **Inclusion and Consolidation Principles:**
  - Preprints superseded by peer-reviewed conference or journal versions are consolidated into canonical entries, and homonymous system names are disambiguated by author and task.
  - Studies across unstructured text, source code, structured tables, knowledge graphs, multimodal streams, and agentic workflows are included whenever they formalize, analyze, attack, defend, or evaluate RAG behavior under an explicit perturbation regime $\Omega = \Omega_q \cup \Omega_{\text{ret}} \cup \Omega_{\text{conf}} \cup \Omega_{\text{gap}} \cup \Omega_{\text{adv}}$.

## 2. Four-Pillar and 20-Strand Technical Taxonomy
The technical taxonomy organizes interventions across the RAG architecture $\mathcal{S} = (\mathcal{R}, \mathcal{A}, \mathcal{G}_{\theta}, \Pi)$ into four pillars and twenty mechanism strands (with 76 representative works highlighted in Figure 2 and indexed in `data/research_map_76_works.csv`):
1. **Pillar I: Evidence-Centric Robustness (§4, Strands 1.1 to 1.5)**
   - Strand 1.1: Retrieval Noise Stratification and Distractor Dynamics
   - Strand 1.2: Granular Filtering, Utility Reranking, and Compression
   - Strand 1.3: Context Budget Allocation and Positional Ordering
   - Strand 1.4: Query-Side Stability and Pipeline Coordination
   - Strand 1.5: Source Provenance and Temporal Validity
2. **Pillar II: Model-Centric Robustness (§5, Strands 2.1 to 2.5)**
   - Strand 2.1: Noise-Resilient Reader Training and Structured Deliberation
   - Strand 2.2: Preference Alignment and Parametric-Contextual Conflicts
   - Strand 2.3: Inter-Document Conflicts and Multi-Source Arbitration
   - Strand 2.4: White-Box Representation and Subspace Interventions
   - Strand 2.5: Fine-Grained Attribution, Grounding, and Scaling Effects
3. **Pillar III: Adversarial Robustness and Security (§6, Strands 3.1 to 3.5)**
   - Strand 3.1: Corpus Poisoning and Backdoor Triggers
   - Strand 3.2: Attack Generalization, Stealth Budgets, and Black-Box Transfer
   - Strand 3.3: Indirect Prompt Injection and Confidentiality Exfiltration
   - Strand 3.4: Ingestion Screening, Reranker Defenses, and Context Sanitization
   - Strand 3.5: Cross-Document Isolation, Provable Certification, and Forensic Traceback
4. **Pillar IV: System-Level Robustness and Adaptive Control (§7, Strands 4.1 to 4.5)**
   - Strand 4.1: Adaptive Retrieval Triggering and Corrective Search Loops
   - Strand 4.2: Evidence Sufficiency, Knowledge Boundaries, and Clarification
   - Strand 4.3: Uncertainty Quantification and Conformal Risk Control
   - Strand 4.4: Joint Source Routing and Set-Level Verification
   - Strand 4.5: Multi-Agent Debate and Value-of-Information Control

## 3. Evaluation Benchmarks and Metric Families (§8)
Section 8 organizes evaluation along two complementary dimensions:
- **§8.1 Benchmark Suites Across Robustness Pillars (Table 5):** Covers diagnostic noise and context-reliance benchmarks (RGB, Magic Mushroom, CUB, PRGB, FaithEval), inter-document and temporal conflict benchmarks (ConflictBank, MAGIC, WikiContradict, DynamicQA), query-robustness and evolving benchmarks (QueryRobust, AutoEvolve, Synthetic Web), span-level grounding and judge calibration suites (RAGTruth, ALCE, RAGAS, ARES, SePer), sufficiency and abstention suites (Sufficient Context, NoMIRACL, MTRAG-UN, CRUMQs), adversarial poisoning and prompt-injection arenas (SafeRAG, PoisonArena, MPIB, Rag-and-Roll, LLMail-Inject), and standardized cross-pipeline suites (BERGEN, BEIR, URAG, RAG-QA Arena).
- **§8.2 Evaluation Metrics Across Robustness Dimensions (Table 6):** Groups evaluation metrics into five families aligned with Definition 1:
  1. *Task Utility and Noise Stability Metrics* (Exact Match, Token F1, Substring Accuracy, Resilience Rate, RAD, token compression ratio);
  2. *Long-Context and Multi-Hop Synthesis Metrics* (Multi-hop Token F1, zero-shot QA accuracy, reading-note robustness gain);
  3. *Conflict Resolution and Update Plasticity Metrics* (Context Adherence $R_{\text{Ad}}$ vs. Noise Robustness $R_{\text{Ro}}$, Memorization Ratio $M_R$, Boost Rate, multi-perspective set F1, span-level hallucination F1, citation precision and recall);
  4. *Adversarial Security and Certification Metrics* (top-$k$ poison exposure, empirical Attack Success Rate ASR, clean utility preservation, worst-case Certifiable Accuracy `cacc`);
  5. *Sufficiency, Calibration, and Control Metrics* (Sufficiency F1, ECE/Brier/AUROC, FactScore, conformal prediction set coverage and size, FWER-calibrated conditional selective risk).
