# Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation

This repository provides the structured literature index, taxonomy mappings, and vector figure generation scripts for the survey paper **Robust Retrieval-Augmented Generation (RAG): A Systematic Survey of Concepts, Taxonomy, Methods, and Evaluation**.

## 1. Survey Overview and Structure

Given a task specification $\mathcal{T}$, a perturbation regime $\Omega = \Omega_q \cup \Omega_{\text{ret}} \cup \Omega_{\text{conf}} \cup \Omega_{\text{gap}} \cup \Omega_{\text{adv}}$, and an operational resource budget $B$, the survey formulates **Robust RAG** as the system-level capacity of a retrieval-augmented architecture $\mathcal{S} = (\mathcal{R}, \mathcal{A}, \mathcal{G}_{\theta}, \Pi)$ to sustain evidence-governed behavior across query and corpus transitions $(q, \mathcal{C}) \to (q', \mathcal{C}') \in \Omega$ through three coupled behavioral properties:
1. **Property 1 (Selective Stability):** Bounded task risk, semantic distributional divergence ($D_{\mathrm{TV}}$), and privilege-boundary violation under perturbations that preserve the reference warrant $W_{\mathcal{T}}^{\text{ref}}$.
2. **Property 2 (Justified Responsiveness):** Bounded update risk and counterfactual probability gain toward authoritative, corroborated updates ($\rho(d') > \rho(d_0)$) when prior beliefs are outdated.
3. **Property 3 (Graceful Degradation and Recovery):** Budget-feasible Constrained POMDP sequential control (re-retrieval, verification, clarification, or calibrated abstention) when support is absent or unresolved, paired with lineage-guided state recovery in stateful workflows.

Across **386 unique cited works** ($355$ primary RAG studies and $31$ foundational, adjacent-benchmark, and survey references), technical interventions are organized into **4 pillars and 20 mechanism strands**:
- **Section 1:** Introduction
- **Section 2:** Background and Systematic Survey Scope
- **Section 3:** Conceptual Framework and Taxonomy of Robust RAG (Definition 1, Properties 1 to 3, Proposition 1, and Figure 2 Research Map of 76 representative works)
- **Section 4 (Pillar I):** Evidence-Centric Robustness: Query and Context Construction
- **Section 5 (Pillar II):** Model-Centric Robustness: Reading and Conflict Resolution
- **Section 6 (Pillar III):** Adversarial Robustness and Security
- **Section 7 (Pillar IV):** System-Level Robustness: Calibration and Adaptive Control
- **Section 8:** Evaluation Benchmarks and Metrics (§8.1 Benchmark Suites; §8.2 Evaluation Metrics)
- **Section 9:** Cross-Layer Interactions and Future Directions
- **Section 10:** Conclusion

## 2. Repository Artifacts (`survey_reproducibility/`)

| Artifact | Path | Description |
| --- | --- | --- |
| **Complete 386-Work Citation Index** | `survey_reproducibility/data/citation_index.csv` | Structured index of all 386 unique works cited in the survey ($355$ primary RAG studies and $31$ foundational, adjacent-benchmark, and survey references). |
| **Core Literature Map** | `survey_reproducibility/data/literature_map.csv` | Structured mapping of core studies across the 4 intervention pillars and 20 mechanism strands. |
| **Figure 2 Taxonomy Map Manifest (76 Works)** | `survey_reproducibility/data/research_map_76_works.csv`, `.json` | Structured manifest of the 76 representative works organized across the 4 pillars and 20 mechanism strands in Figure 2. |
| **Taxonomy and Scope Documentation** | `survey_reproducibility/PROTOCOL_AND_TAXONOMY.md` | Documentation of the literature collection scope, four-pillar taxonomy, and evaluation benchmark and metric categories. |
| **Figure Generation Scripts** | `survey_reproducibility/figures/`, `survey_reproducibility/scripts/render_figures.py` | Scripts for constructing the native vector figures (Figure 1 Concept Overview, Figure 2 Research Map, and Figure 3 Cross-Stage Lifecycle Recovery). |
| **Artifact Verification Script** | `survey_reproducibility/verify_survey_artifacts.py` | Deterministic script verifying the 386 cited works, 4-pillar / 20-strand taxonomy mapping, 76-work Figure 2 manifest, and formal mathematical properties. |

## 3. Quick Verification

From the repository root, run:

```bash
python3 survey_reproducibility/verify_survey_artifacts.py
```
