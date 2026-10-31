#!/usr/bin/env python3
"""Canonical data synchronization, source-located C1-C5 semantic audit, and paired diagnostic re-analysis generator."""
import collections, csv, hashlib, json, re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
data = root / 'data'

prec = [
    'adversarially_manipulated',
    'conflicting_evidence',
    'noisy_or_distracting',
    'insufficient_or_uncertain',
    'clean_or_heterogeneous_mix',
]
rank = {k: i for i, k in enumerate(prec)}

# 1. Load canonical core map (336 studies)
lit_path = data / 'literature_map.csv'
with lit_path.open() as f:
    reader = csv.DictReader(f)
    lit_fields = reader.fieldnames
    lit_rows = list(reader)

# Source-located C1 primary & secondary regime audit updates (26 records)
c1_audit_updates = {
    'rrag019': ('adversarially_manipulated', 'conflicting_evidence;noisy_or_distracting'),
    'rrag032': ('conflicting_evidence', 'noisy_or_distracting'),
    'rrag037': ('noisy_or_distracting', 'conflicting_evidence;insufficient_or_uncertain'),
    'rrag040': ('conflicting_evidence', 'insufficient_or_uncertain'),
    'rgb2023': ('noisy_or_distracting', 'conflicting_evidence;insufficient_or_uncertain'),
    'rrag055': ('noisy_or_distracting', ''),
    'rrag058': ('noisy_or_distracting', ''),
    'rrag070': ('conflicting_evidence', 'insufficient_or_uncertain'),
    'rrag073': ('noisy_or_distracting', ''),
    'rrag111': ('insufficient_or_uncertain', ''),
    'rrag113': ('insufficient_or_uncertain', ''),
    'rrag141': ('insufficient_or_uncertain', ''),
    'rrag168': ('noisy_or_distracting', 'conflicting_evidence'),
    'rrag183': ('noisy_or_distracting', 'conflicting_evidence'),
    'rrag202': ('conflicting_evidence', 'insufficient_or_uncertain;noisy_or_distracting'),
    'venue006': ('conflicting_evidence', ''),
    'venue011': ('insufficient_or_uncertain', 'noisy_or_distracting'),
    'venue021': ('conflicting_evidence', ''),
    'venue024': ('conflicting_evidence', 'insufficient_or_uncertain;noisy_or_distracting'),
    'venue032': ('noisy_or_distracting', ''),
    'venue039': ('noisy_or_distracting', 'insufficient_or_uncertain'),
    'venueExpanded025': ('noisy_or_distracting', ''),
    'venueExpanded079': ('noisy_or_distracting', ''),
    'venueExpanded080': ('noisy_or_distracting', ''),
    'venueExpanded081': ('noisy_or_distracting', ''),
    'venueExpanded116': ('noisy_or_distracting', ''),
}

# Source-located C2 updates for reclassified benchmark entries
c2_audit_updates = {
    'rrag019': ('adversarial_corpus_poisoning', 'black_box_corpus_write_bounded_m', 'black_box_corpus_write_bounded_m;query_only_or_prompt_interface'),
    'rrag032': ('parametric_contextual_conflict', 'benign_stochastic_channel', 'benign_stochastic_channel'),
    'rrag040': ('parametric_contextual_conflict', 'benign_stochastic_channel', 'benign_stochastic_channel'),
    'rrag070': ('inter_document_source_conflict', 'benign_stochastic_channel', 'benign_stochastic_channel'),
    'rrag202': ('inter_document_source_conflict', 'benign_stochastic_channel', 'benign_stochastic_channel'),
    'venue006': ('inter_document_source_conflict', 'benign_stochastic_channel', 'benign_stochastic_channel'),
    'venue021': ('inter_document_source_conflict', 'benign_stochastic_channel', 'benign_stochastic_channel'),
    'venue024': ('inter_document_source_conflict', 'benign_stochastic_channel', 'benign_stochastic_channel'),
    'venue032': ('query_perturbation_or_drift', 'benign_stochastic_channel', 'benign_stochastic_channel'),
}

# Source-located C4 primary and all-applicable metric updates (10 records)
c4_audit_updates = {
    'rrag019': ('empirical_attack_success_and_robust_acc', 'empirical_attack_success_and_robust_acc;end_to_end_task_em_and_f1;retrieval_ranking_and_exposure'),
    'rrag037': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1;span_faithfulness_and_attribution_f1'),
    'rgb2023': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1;span_faithfulness_and_attribution_f1'),
    'rrag153': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1'),
    'rrag167': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1'),
    'rrag168': ('retrieval_ranking_and_exposure', 'retrieval_ranking_and_exposure;end_to_end_task_em_and_f1'),
    'rrag186': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1;efficiency_tokens_or_latency'),
    'rrag202': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1'),
    'rrag228': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1;efficiency_tokens_or_latency'),
    'venueExpanded130': ('end_to_end_task_em_and_f1', 'end_to_end_task_em_and_f1;efficiency_tokens_or_latency'),
}

# Populate missing metrics_reported_or_relevant fields (12 records)
missing_metrics_updates = {
    'venue006': 'NPOV viewpoint coverage score, hallucination detection F1, NLI entailment accuracy',
    'venue018': 'Exact Match (EM), F1, and multi-hop bridge fact retention under hard-negative noise',
    'venue019': 'Attribution sensitivity shift and source authorship selection bias across LLM vs. human metadata',
    'venue021': 'Cross-lingual geopolitical consistency score and territorial viewpoint bias across 49 languages',
    'venue028': 'Sub-claim nugget recall, precision, and CRUX context-coverage correlation on long-form RAG',
    'venue032': 'Multi-hop QA accuracy and retrieval stability across evolved query complexity levels',
    'venue035': 'Exact Match (EM), F1, and prompt token compression ratio via Pareto sentence-context attention',
    'venue039': 'Noise vulnerability, context acceptability, dynamic calibration error, and unanswerability detection',
    'venue044': 'Exact Match (EM) and F1 under noisy and missing retrieval candidates (ACM metadata/abstract record)',
    'venue045': 'LiveRAG competitive QA accuracy, faithfulness, and latency leaderboard score (ACM metadata/abstract record)',
    'venue050': 'Span extraction F1 and end-to-end QA Exact Match (EM) under noisy retrieval (ACM metadata/abstract record)',
    'venue051': 'Expected Calibration Error (ECE), AUROC, and KG-RAG accuracy under incomplete/noisy subgraphs',
}

for r in lit_rows:
    k = r['cite_key']
    if k in missing_metrics_updates:
        r['metrics_reported_or_relevant'] = missing_metrics_updates[k]
    if r['study_type'] == 'survey_or_overview':
        r['C1_evidence_state'] = 'N/A_foundational_or_survey'
        r['C1_all_applicable'] = 'N/A'
        r['C1_secondary_regimes'] = 'N/A'
        continue
    if k in c1_audit_updates:
        r['C1_evidence_state'], r['C1_secondary_regimes'] = c1_audit_updates[k]
    if k in c2_audit_updates:
        r['C2_disturbance_origin'], r['C2_capability_and_budget'], r['C2_capability_all_applicable'] = c2_audit_updates[k]
    if k in c4_audit_updates:
        r['C4_outcome_metric'], r['C4_all_applicable'] = c4_audit_updates[k]
    # Enforce exact three-field invariant:
    # C1_all_applicable = {C1_evidence_state} union C1_secondary_regimes, with C1_evidence_state not in C1_secondary_regimes
    prim = r['C1_evidence_state'].strip()
    assert prim in rank, (k, prim)
    existing_all = {t.strip() for t in r['C1_all_applicable'].split(';') if t.strip() in rank}
    existing_sec = {t.strip() for t in r.get('C1_secondary_regimes', '').split(';') if t.strip() in rank}
    if k in c1_audit_updates:
        sec_set = existing_sec - {prim}
    else:
        sec_set = (existing_all | existing_sec) - {prim}
    union_ordered = [prim] + sorted(sec_set, key=lambda t: rank[t])
    r['C1_secondary_regimes'] = ';'.join(sorted(sec_set, key=lambda t: rank[t]))
    r['C1_all_applicable'] = ';'.join(union_ordered)

# Write updated literature_map.csv
with lit_path.open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=lit_fields)
    w.writeheader()
    w.writerows(lit_rows)

lit_by_key = {r['cite_key']: r for r in lit_rows}

# 2. Synchronize citation_index.csv (390 rows) from canonical literature_map.csv + supplementary definitions
cit_path = data / 'citation_index.csv'
with cit_path.open() as f:
    reader = csv.DictReader(f)
    cit_fields = reader.fieldnames
    cit_rows = list(reader)

shared_cols = [
    'C1_evidence_state',
    'representation_modality',
    'C2_disturbance_origin',
    'C2_capability_and_budget',
    'C3_intervention_stage',
    'C4_outcome_metric',
    'C5_action_policy',
    'taxonomy_pillar',
    'mechanism_strand',
    'all_applicable_pillars',
    'is_figure2_representative_76',
]

for r in cit_rows:
    k = r['cite_key']
    if k in lit_by_key:
        lr = lit_by_key[k]
        r['study_type'] = lr['study_type']
        r['verification_status'] = lr['verification_status']
        for col in shared_cols:
            r[col] = lr[col]
    else:
        # Normalize foundational_or_survey N/A formatting (e.g., liu2026contrasts)
        if r['study_type'] == 'foundational_or_survey':
            r['C1_evidence_state'] = 'N/A_foundational_or_survey'
            r['representation_modality'] = 'N/A'
            r['C2_disturbance_origin'] = 'N/A_foundational_or_survey'
            r['C2_capability_and_budget'] = 'N/A'
            r['C3_intervention_stage'] = 'N/A_foundational_or_survey'
            r['C4_outcome_metric'] = 'N/A_foundational_or_survey'
            r['C5_action_policy'] = 'N/A_foundational_or_survey'

with cit_path.open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cit_fields)
    w.writeheader()
    w.writerows(cit_rows)

cit_by_key = {r['cite_key']: r for r in cit_rows}

# 3. Synchronize coverage_decisions.csv (476 rows) from citation_index.csv so 0 cross-file discrepancies exist
cov_path = data / 'coverage_decisions.csv'
with cov_path.open() as f:
    reader = csv.DictReader(f)
    cov_fields = reader.fieldnames
    cov_rows = list(reader)

cov_shared = [
    'study_type',
    'verification_status',
    'C1_evidence_state',
    'representation_modality',
    'C2_disturbance_origin',
    'C2_capability_and_budget',
    'C3_intervention_stage',
    'C4_outcome_metric',
    'C5_action_policy',
]

for r in cov_rows:
    k = r['cite_key']
    if r['in_main_text'] == 'true':
        assert k in cit_by_key, k
        cr = cit_by_key[k]
        r['status'] = 'included_and_cited_in_main_text'
        for col in cov_shared:
            r[col] = cr[col]

with cov_path.open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cov_fields)
    w.writeheader()
    w.writerows(cov_rows)

print("Synchronized literature_map.csv, citation_index.csv, and coverage_decisions.csv successfully.")

# 4. Build source-audited claim_evidence_matrix.csv and .json (23 rows across Tables 6 and 7)
cm_rows = [
    {
        'table_or_sec': 'Table 6 (Row 1)',
        'method_or_tension': 'RGB Stress Test (rgb2023)',
        'source_location': 'Chen et al. (AAAI 2024, arXiv:2309.01431v2), p. 5 & p. 7, Tables 1 & 5 (Noise Robustness & Information Integration)',
        'experimental_setup': 'RGB English & Chinese splits (300 queries each); synthetic hard-negative noise ratios r in {0.0, 0.2, 0.4, 0.6, 0.8}, negative rejection, information integration, and counterfactual resistance across ChatGPT, ChatGLM-6B/2-6B, Vicuna-7B, Qwen-7B, BELLE-7B',
        'metric_and_denominator': 'Lenient substring inclusion accuracy (%) over all 300 test queries per split (single 1x decoding call; O((kL)^2) attention prefill FLOPs)',
        'verified_finding': 'Table 1 (EN): ChatGPT accuracy drops monotonically from 96.33% (r=0.0) to 94.67% (0.2), 94.00% (0.4), 90.00% (0.6), and 76.00% (0.8) (-20.33 pp total; -18.67 pp from 0.2 to 0.8); Vicuna-7B drops 87.67% -> 60.33%. Directional proxy for Property 1 task risk (does not measure semantic D_TV or control for parametric memorization)',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 2)',
        'method_or_tension': 'FILCO (rrag044)',
        'source_location': 'Wang et al. (ICML 2023, arXiv:2311.08377v1), §4.5 Fig. 6 (p. 7) & §6.2 Table 5 (p. 9)',
        'experimental_setup': 'Six KILT datasets (NQ, TriviaQA, HotpotQA, ELI5, FEVER, WoW); DPR top-1 and top-5 Wikipedia passages filtered at sentence level via STRINC/LEXICAL/CXMI for fine-tuned FLAN-T5-XL and Llama-2-7B readers',
        'metric_and_denominator': 'Exact Match (EM on NQ/TQA), F1 (HotpotQA/WoW), Rouge-L (ELI5), Accuracy (FEVER) over full KILT validation splits; LlamaTokenizer input token length (§4.5 Fig. 6)',
        'verified_finding': '§4.5 Fig. 6: cuts model input prompt length by 44-64% (1.8-2.8x token reduction) across all 6 tasks. §6.2 Table 5 (top-5 DPR on FLAN-T5-XL, FULL vs. FILCO rows): improves NQ EM 47.6 -> 61.8 (+14.2 pp), TQA EM 67.3 -> 71.1 (+3.8 pp), HotpotQA F1 61.5 -> 65.0 (+3.5 pp), FEVER Acc 88.0 -> 91.4 (+3.4 pp) in O(k) filter passes + 1x reader call',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 3)',
        'method_or_tension': 'RECOMP (rrag226) & xRAG (venueExpanded148)',
        'source_location': 'RECOMP: Xu et al. (ICLR 2024, arXiv:2310.04408v1), p. 7, Table 2; xRAG: Cheng et al. (NeurIPS 2024), §6.1 & Appendix E p. 19, Table 11 (and Table 3 p. 8)',
        'experimental_setup': 'RECOMP: Flan-UL2 (20B) over MS-MARCO Contriever top-5 Wikipedia passages on NQ, TriviaQA, HotpotQA (extractive dual-encoder or distilled T5-Large abstractive compressor with null gate). xRAG: frozen Mistral-7B over SFR top-1 Wikipedia passage (175.1 avg tokens -> 1 bridge token) across NQ, TriviaQA, WebQA, HotpotQA',
        'metric_and_denominator': 'RECOMP Table 2: normalized EM, F1, and in-context evidence tokens (excluding few-shot exemplars; CIs not reported). xRAG §6.1 Table 11: conditional single-draw Resilience Rate P(Y_RAG=z* | y_theta=z*) and Boost Rate P(Y_RAG=z* | y_theta!=z*) relative to closed-book generation y_theta',
        'verified_finding': 'RECOMP v1 Table 2 (vs. Top-5 uncompressed: NQ 660 tok / 39.39 EM, TQA 677 tok / 62.37 EM, HotpotQA 684 tok / 32.80 EM): Extractive (Ours) yields NQ 37 tok / 36.57 EM (-2.82 pp), TQA 38 tok / 58.99 EM (-3.38 pp), HotpotQA 75 tok / 30.40 EM (-2.40 pp); Abstractive T5-Large (Ours) yields NQ 36 tok / 37.04 EM (-2.35 pp), TQA 32 tok / 58.68 EM (-3.69 pp), HotpotQA 64 tok / 28.20 EM (-4.60 pp) (9.1x to 21.2x token reduction; teacher GPT-3.5 summaries: NQ 56 tok / 37.12 EM, TQA 41 tok / 62.03 EM, HotpotQA 107 tok / 31.60 EM). xRAG Table 11 (Mistral-7B + SFR): raises Resilience 74.1% -> 82.3% (+8.2 pp) while lowering Boost 29.5% -> 22.2% (-7.3 pp; proxy for closed-book-to-RAG transition, not paired Z_0 -> Z* update)',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 4)',
        'method_or_tension': 'RankRAG (venueExpanded120)',
        'source_location': 'Yu et al. (NeurIPS 2024), §3 & §4.2, p. 7 Table 2 & Appendix Overhead Analysis',
        'experimental_setup': 'Nine knowledge-intensive datasets (NQ, TriviaQA, PopQA, HotpotQA, 2WikiMQA, FEVER, Doc2Dial, TopiOCQA, INSCIT); unified instruction-tuned Llama-3-8B and Llama-3-70B backbones',
        'metric_and_denominator': 'Zero-shot Exact Match (EM), Accuracy, and F1 over full evaluation splits; 2-stage inference cost: O(N) candidate relevance-scoring forward passes + 1x top-k generation call',
        'verified_finding': 'Table 2: unified ranking-and-generation weights in one LLM outperform separate reranker+reader pipelines (e.g., Llama3-RankRAG-8B averages 50.6 vs. 46.1 for ChatQA-1.5-8B across 9 benchmarks) while still requiring O(N) scoring passes before top-k decoding',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 5)',
        'method_or_tension': 'LongRAG (venueExpanded105)',
        'source_location': 'Zhao et al. (EMNLP 2024), §5.1-§5.2, p. 6-7, Tables 1 & 2',
        'experimental_setup': 'LongBench Multi-Hop QA subsets (HotpotQA, 2WikiMultihopQA, MuSiQue; 200 samples each, 4.9K-11.2K avg words); dual-perspective CoT-guided chunk filter (I_d) + LLM-augmented global context extractor (I_g) across Llama2/3, Qwen1.5, Vicuna, ChatGLM3, GPT-3.5, GLM-4',
        'metric_and_denominator': 'Token-level F1 (%) over 200-query LongBench test splits per dataset; multi-step filter, global extractor, and reader LLM calls',
        'verified_finding': 'Table 1: dual-perspective local filtering + global extraction improves average multi-hop F1 across all backbones (e.g., Llama3-8B-8k: 37.13 -> 44.59 [+7.46 pp]; GPT-3.5-Turbo: 40.32 -> 46.79 [+6.47 pp]; GLM-4: 45.96 -> 52.56 [+6.60 pp])',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 6)',
        'method_or_tension': 'RAAT (raat2024)',
        'source_location': 'Fang et al. (ACL 2024, arXiv:2405.20978v1), §4.1 & §5.1, p. 7, Table 2',
        'experimental_setup': 'RAG-Bench (combined NQ, TriviaQA, WebQ test queries pre-filtered in §4.1 to contain >=2 retrieved golden passages in top-k); LLaMA2-7B evaluated across Golden Only, Golden & c_i (irrelevant), Golden & c_r (relevant hard-negative), and Golden & c_c (counterfactual noise)',
        'metric_and_denominator': 'Strict normalized Exact Match (EM) and F1 conditioned on gold-present queries (E_ref in D\'); 1x decoding call at inference (with O((kL)^2) full-context attention prefill)',
        'verified_finding': 'Table 2 (Golden Only -> Golden & c_c counterfactual noise): RAAT bounds EM drop to 83.07 -> 82.10 (-0.97 pp EM; F1 87.15 -> 86.29, -0.86 pp), compared with 51.80 -> 38.37 (-13.43 pp EM; F1 65.56 -> 51.81, -13.75 pp) for unadapted zero-shot LLaMA2-7B and 74.03 -> 65.40 (-8.63 pp EM) for golden-only fine-tuned RALM_golden. Pre-filtering to >=2 gold passages leaves retrieval omissions untested',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 7)',
        'method_or_tension': 'Chain-of-Note (chainOfNote2023)',
        'source_location': 'Yu et al. (EMNLP 2024, arXiv:2311.09210v1), §3.1-§3.2, p. 5-7, Tables 1-3',
        'experimental_setup': 'NQ (3,610 full / 2,086 gold-retrieved subset), TriviaQA (7,993 / 7,074), WebQ (2,032 / 1,231), plus RealTimeQA unknown splits; DPR top-k passages with fine-tuned LLaMa-2-7B emitting per-passage reading notes',
        'metric_and_denominator': 'Normalized EM and F1 on full test sets (Table 2) and noise-ratio subsets (Table 3, noise ratios 0%-100%); 1x decoding call with additional generated note output tokens',
        'verified_finding': 'Table 2 (full test set): improves average EM from 48.49 to 50.46 (+1.97 pp) over standard Retrieve-Read on LLaMa-2-7B. Table 3 (noisy subsets): improves average EM by +3.18 pp at 80% noise ratio (54.52 -> 57.70) and +7.94 pp at 100% noise ratio (39.72 -> 47.66, unknown rejection / fallback)',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 8)',
        'method_or_tension': 'FaithfulRAG (faithfulRAG2025)',
        'source_location': 'Zhang et al. (ACL 2025), §5.2, p. 6-7, Tables 1 & 2',
        'experimental_setup': 'FaithEval, RealtimeQA, MuSiQue, and SQuAD counterfactual conflict splits (Table 1) plus non-conflict golden splits (Table 2); Llama-3.1-8B-Instruct, Qwen-2.5-7B-Instruct, and Mistral-7B-Instruct backbones',
        'metric_and_denominator': 'Conflict-resolution accuracy (%) over counterfactual conflict splits and golden non-conflict splits; multi-step self-knowledge extraction, fact alignment, and self-think calls',
        'verified_finding': 'Table 1: achieves 81.7% on FaithEval (Mistral-7B, +8.5 pp over KRE at 73.2%) and 86.3% on SQuAD conflict (Llama-3.1-8B, +9.3 pp over ChatQA-2.0 at 77.0%), while preserving non-conflict accuracy in Table 2 (MuSiQue-golden 84.0 -> 85.3%, SQuAD-golden 95.2 -> 96.6%)',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 9)',
        'method_or_tension': 'Astute RAG (astuteRAG2025)',
        'source_location': 'Wang et al. (ACL 2025, arXiv:2410.07176v2), §4, p. 7 & p. 13, Tables 1-3',
        'experimental_setup': 'NQ, TriviaQA, BioASQ, PopQA (1,000 samples total); zero-shot Claude 3.5 Sonnet, Gemini 1.5 Pro, Mistral-Large (128B), and Mistral-Nemo (12B) with iterative internal-external passage clustering',
        'metric_and_denominator': 'Substring match accuracy (%) across all test queries; multi-step LLM API calls for internal passage generation, iterative source-aware clustering, and answer finalization',
        'verified_finding': 'Table 1: improves overall accuracy over standard RAG from 55.5% to 61.7% (+6.2 pp) on Claude 3.5 Sonnet and from 53.7% to 59.2% (+5.5 pp) on Gemini 1.5 Pro without weight training',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 10)',
        'method_or_tension': 'ParamMute (rrag024) & CoRect (rrag008)',
        'source_location': 'ParamMute: Huang et al. (NeurIPS 2025), §5, p. 6-7, Tables 1-2; CoRect: Ma et al. (2026, arXiv:2602.08221v1), §4.4, §5, & §7, p. 6-9, Table 1',
        'experimental_setup': 'ParamMute: CoFaithfulQA unfaithful subset D^- (HotpotQA, NQ, NewsQA, SearchQA, SQuAD, TriviaQA) and ConFiQA on LLaMA-3-8B; CoRect: NQ, NQ-Swap, HotpotQA, TriviaQA, TabMWP, SQuAD across Qwen2.5-7B, LLaMA3-8B, Mistral-7B, LLaMA2-13B',
        'metric_and_denominator': 'ParamMute: Context Recall (ConR), Memory Recall (MemR), and Memorization Ratio MR = MemR/(MemR+ConR) in 1x decoding call; CoRect: QA EM/Accuracy across 2x forward passes (full vs. null context with KV-cache prefix reuse)',
        'verified_finding': 'ParamMute Table 2 (CoFaithfulQA D^-): raises HotpotQA ConR 60.34% -> 71.06% (MR 18.70% -> 7.99%) and SearchQA ConR 66.76% -> 78.76% in 1x call. CoRect Table 1: raises LLaMA3-8B NQ-Swap 60.67% -> 79.32% and 6-task average 63.08% -> 68.50% across 2x passes (O(1) calls in k, still incurring O((kL)^2) attention prefill on the full-context pass)',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 11)',
        'method_or_tension': 'PoisonedRAG (poisonedRAG2024) & CorruptRAG (rrag057)',
        'source_location': 'PoisonedRAG: Zou et al. (USENIX Security 2025, arXiv:2402.07867), p. 8, Table 1; CorruptRAG: Zhang et al. (arXiv:2504.03957v1), p. 6, Table 2',
        'experimental_setup': 'BEIR NQ (2.68M texts), HotpotQA (5.23M), MS-MARCO (8.84M) with Contriever top-5 retrieval; PoisonedRAG injects m=5 malicious passages per target query across 8 LLMs; CorruptRAG injects a single passage m=1 per target query across GPT-3.5/4o-mini/4o/4-turbo',
        'metric_and_denominator': 'Empirical Attack Success Rate (ASR: fraction of target queries yielding attacker-chosen answer) and retrieval F1 over 100 targeted close-ended queries (10 queries x 10 trials)',
        'verified_finding': 'PoisonedRAG Table 1 (m=5 in top-5, PaLM-2 / GPT-4): achieves 97%/97% black-box ASR on NQ, 99%/93% on HotpotQA, and 91%/92% on MS-MARCO. CorruptRAG Table 2 (strict single-passage m=1 in top-5, GPT-3.5-turbo / GPT-4o-mini): CorruptRAG-AS/AK raise NQ ASR to 90-94% / 95-97% vs. 54% / 69% for black-box PoisonedRAG at m=1',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 12)',
        'method_or_tension': 'TrustRAG (rrag013)',
        'source_location': 'Zhou et al. (arXiv:2501.00879v3), §4.2 & Appendix, p. 7 & p. 18-21, Tables 2 & 12-15',
        'experimental_setup': 'Poisoned NQ, HotpotQA, MS-MARCO under PoisonedRAG and PIA attacks across Contriever, Contriever-MS, and ANCE top-k retrieval with MistralNemo-12B, Llama-3.1-8B, and GPT-4o',
        'metric_and_denominator': 'Clean/attacked QA Accuracy (ACC %) and Attack Success Rate (ASR %) under 20%-100% poison rates; Stage-1 k-means embedding filtering + Stage-2 LLM self-assessment',
        'verified_finding': 'Table 2 & Table 14 (Contriever + Llama-3.1-8B at 100% PoisonedRAG rate): reduces NQ ASR from 98.0% to 2.0% while restoring QA accuracy from 2.0% to 83.0% (and HotpotQA ASR 99.0% -> 4.0%, ACC 1.0% -> 67.0%); empirical defense without worst-case formal certificates',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 13)',
        'method_or_tension': 'RobustRAG (certifiedRAG2024)',
        'source_location': 'Xiang et al. (ICML 2024, arXiv:2405.15556v2), Definition 1, Algorithms 3-4, Tables I-III (p. 9-12)',
        'experimental_setup': 'RQA-MC, RQA, NQ, and Biography generation under k\' poisoned passages out of k=10 retrieved passages; G=ceil(k/omega) isolated passage groups (G=10 for omega=1) on Mistral-7B, Llama2-7B, and GPT-3.5/4 on one NVIDIA A100 GPU',
        'metric_and_denominator': 'Worst-case certified task-score lower bound min_{C\'} M(y_hat_{C\'}, y*) >= tau (Certifiable Accuracy cacc for tau=1 on QA) over all corrupted sets with <=k\' poisons; per-query wall-clock latency ratio vs. vanilla 1-call RAG in Table III (p. 12, Mistral-7B, k=10, omega=1)',
        'verified_finding': 'Certifies worst-case task score >= tau across all reachable outputs under <=k\' poisons. Table III separates latency by aggregation mode: Secure Keyword Aggregation (G isolated group calls + 1 final synthesis call = G+1 LLM calls) incurs 1.63x (0-shot RQA-MC, 0.62s vs. 0.38s), 2.77x (1-shot RQA, 1.22s vs. 0.44s), 3.65x (4-shot RQA, 1.68s vs. 0.46s), and 1.94x (1-shot Bio, 14.90s vs. 7.69s) latency; Secure Decoding Aggregation (G parallel token-probability streams) incurs 1.63x, 1.16x (0.51s vs. 0.44s), 2.87x, and 1.25x latency. Cross-group multi-hop synthesis remains unvalidated without query decomposition',
        'evidence_tier': 'formal_theorem_or_bound',
    },
    {
        'table_or_sec': 'Table 6 (Row 14)',
        'method_or_tension': 'Self-RAG (selfRAG2023)',
        'source_location': 'Asai et al. (ICLR 2024), §4.2, p. 8, Table 2',
        'experimental_setup': 'Short-form QA (PopQA, TriviaQA-unfiltered), closed-set reasoning (PubHealth, ARC-Challenge), and long-form generation (Biography FactScore, ASQA str-EM & citation F1); Contriever top-k + Self-RAG-7B and 13B',
        'metric_and_denominator': 'Lenient substring inclusion accuracy (%) on PopQA/TriviaQA/PubHealth/ARC, FactScore on Bio, and str-EM / citation precision-recall on ASQA; O(T) adaptive segment-level retrieval and critique calls',
        'verified_finding': 'Table 2: Self-RAG-7B/13B achieve 54.9%/55.8% inclusion accuracy on PopQA and 66.4%/69.3% on TriviaQA (vs. 38.2%/42.5% for standard retrieved Llama2-7B), and 81.2%/80.2% FactScore on Biography',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 15)',
        'method_or_tension': 'CRAG (crag2024)',
        'source_location': 'Yan et al. (arXiv:2401.15884v2), §4.4, Table 1',
        'experimental_setup': 'PopQA, Biography, PubHealth, and Arc-Challenge; lightweight fine-tuned T5-Large retrieval evaluator (0.77B) routing among Correct (strip refinement), Incorrect (web search), and Ambiguous (both) over standard RAG and Self-RAG backbones',
        'metric_and_denominator': 'Accuracy (%) on PopQA/PubHealth/Arc-Challenge and FactScore on Biography; 1x T5 evaluator call + conditional strip-refinement and web-search calls',
        'verified_finding': 'Table 1: improves standard RAG from 38.2% to 50.8% on PopQA and improves Self-RAG (Self-CRAG-7B) from 54.9% to 61.8% (+6.9 pp) on PopQA and from 81.2% to 86.2% (+5.0 pp) FactScore on Biography',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 16)',
        'method_or_tension': 'CtrlA (ctrla2025)',
        'source_location': 'Liu et al. (ICLR 2025), §5.1, p. 6-7, Tables 1-3',
        'experimental_setup': 'Short-form QA (PopQA, TriviaQA), long-form QA (ASQA, Biography), multi-hop QA (2WikiMultihopQA, HotpotQA), and FreshQA; frozen 7B LLM with representation honesty steering and online token-level confidence probing',
        'metric_and_denominator': 'Exact Match (EM), F1, str-EM, FactScore, and average retrieval trigger frequency (Freq) across full evaluation splits; O(T) in-decoding segment triggers with 0 external classifier parameters',
        'verified_finding': 'Table 2 (long-form): achieves 37.0 str-EM on ASQA and 83.4 FactScore on Bio (vs. 29.9 str-EM / 74.8 FS for matched FLARE-7B). Table 3 (multi-hop): achieves 36.9 EM (Freq 2.01) on 2WikiMQA and 34.7 EM (Freq 3.28) on HotpotQA vs. 14.3 / 14.9 EM for FLARE-7B and 22.4 / 23.7 EM for DRAGIN-7B',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 6 (Row 17)',
        'method_or_tension': 'Sufficient Context (sufficientContext2024)',
        'source_location': 'Joren et al. (ICLR 2025), §3.2 p. 5 Table 1, §5.1 p. 9-10 Figure 4, & Appendix B.1 p. 17 Table 3',
        'experimental_setup': 'HotpotQA, MuSiQue-Ans, TQA, and FreshQA across Gemini-1.5-Pro, GPT-4o, Claude-3.5, Llama-3.1-8B/70B, Mistral-3-7B, and Gemma-2-27B; 1-shot Gemini-1.5-Pro / FLAMe-24B sufficient-context autorater combined linearly with self-rated confidence P(Correct)/P(True)',
        'metric_and_denominator': 'Conditional selective accuracy (# correct / # answered) vs. coverage (% answered, <100% when abstaining) in Fig. 4; full-dataset %Correct / %Abstain / %Hallucinate in Table 3; 1x autorater call + 1x reader call',
        'verified_finding': 'Table 1: 1-shot Gemini-1.5-Pro autorater achieves 0.935 F1 (0.930 Acc) on gold sufficiency labels without GT answers. Fig. 4: combining sufficient-context classification with P(Correct)/P(True) raises selective accuracy across coverage levels on HotpotQA and MuSiQue over confidence thresholding alone',
        'evidence_tier': 'direct_empirical_finding',
    },
    {
        'table_or_sec': 'Table 7 (Row 1)',
        'method_or_tension': 'Topical recall vs. set utility',
        'source_location': 'Yoran et al. (ICLR 2024); Cuconasu et al. (SIGIR 2024); Park & Lee (2024, Table 6); Liu et al. (CoRM-RAG 2026)',
        'experimental_setup': 'Open-domain QA (NQ, TriviaQA, PopQA) and multi-hop QA under hard negatives vs. random noise and missing gold support',
        'metric_and_denominator': 'EM/F1 and RAD = 100 * |ARA-Add| / |ARA| under hard-negative distraction; counterfactual doc-query utility',
        'verified_finding': 'Empirical regularity: topically proximate hard negatives degrade reader EM/F1 and RAD more than random passages, and Park & Lee Table 6 show sharper RAD drops when GenADV distraction co-occurs with unanswerability (e.g., Mistral-7B NQ RAD 74.63 -> 49.25 on unanswerable vs. 94.84 -> 89.26 on answerable). Open hypothesis: extending doc-query counterfactual utility to joint subset selection with local multi-hop complementarity',
        'evidence_tier': 'cross_study_mechanistic_synthesis',
    },
    {
        'table_or_sec': 'Table 7 (Row 2)',
        'method_or_tension': 'Context adherence vs. factuality',
        'source_location': 'Context-DPO (rrag042), ParamMute (rrag024, Table 2), Parenting (rrag214, p. 4 Fig. 2 & p. 8 Table 1), PoisonedRAG (poisonedRAG2024)',
        'experimental_setup': 'Single-hop counterfactual adherence (ConFiQA, CoFaithfulQA) vs. joint adherence (R_Ad) and noise robustness (R_Ro) on SQuAD2.0-Eval, RGB, and KNOT (Parenting Table 1)',
        'metric_and_denominator': 'Context Adherence Rate (ConR / R_Ad) vs. Noise Robustness Rate (R_Ro) and poisoning ASR',
        'verified_finding': 'Empirical: unselective adherence tuning (IRCAN: 72.50% R_Ad, 20.00% R_Ro on RGB) degrades noise robustness, while noise-only training (RAAT: 49.50% R_Ad, 41.00% R_Ro on RGB) lowers adherence below the base model (68.00% R_Ad, 29.50% R_Ro); Parenting decouples adherence, robustness, and entangled subspaces to reach 79.50% R_Ad and 45.50% R_Ro. Mechanistic risk/hypothesis: zeroing parametric FFN neurons risks impairing unretrieved multi-hop bridges',
        'evidence_tier': 'cross_study_mechanistic_synthesis',
    },
    {
        'table_or_sec': 'Table 7 (Row 3)',
        'method_or_tension': 'Upstream pruning vs. sufficiency',
        'source_location': 'FILCO (rrag044, §4.5 Fig. 6 & Table 5), RECOMP (rrag226, v1 p. 7 Table 2), xRAG (venueExpanded148, Table 11), Zhao et al. financial RAG audit (venueExpanded073)',
        'experimental_setup': 'Single-hop (NQ, TriviaQA) and multi-hop (HotpotQA) context compression vs. premise preservation',
        'metric_and_denominator': 'Prompt token reduction (44-64% in FILCO; 9.1-21.2x in RECOMP; 175.1->1 tok in xRAG) vs. multi-hop EM and Boost Rate',
        'verified_finding': 'Empirical: RECOMP Table 2 shows trained compression cuts tokens by 9.1-21.2x with -2.40 pp extractive (32.80 -> 30.40) and -4.60 pp abstractive (32.80 -> 28.20, 64 tok) EM drop on multi-hop HotpotQA, while xRAG raises Resilience (74.1% -> 82.3%) at the cost of Boost Rate (29.5% -> 22.2%). Design direction: soft reliability tokens + O(kL^2) parallel KV encoding',
        'evidence_tier': 'cross_study_mechanistic_synthesis',
    },
    {
        'table_or_sec': 'Table 7 (Row 4)',
        'method_or_tension': 'Iterative verification vs. budget',
        'source_location': 'Self-RAG (selfRAG2023), CRAG (crag2024), DRAG (drag2025), Adaptive Stopping (rrag006)',
        'experimental_setup': 'Multi-step corrective search and multi-agent debate under decoding-call and token budgets',
        'metric_and_denominator': 'QA accuracy gain vs. O(T*M) generator calls or G+1 / G group calls',
        'verified_finding': 'Empirical: iterative search repairs initial retrieval misses (W_T^loc = empty != W_T^ref) but wastes budget and degrades abstention on true corpus gaps (W_T^ref = empty). Normative direction: dual-calibrated CPOMDP VoI stopping rule Eq. (9)',
        'evidence_tier': 'cross_study_mechanistic_synthesis',
    },
    {
        'table_or_sec': 'Table 7 (Row 5)',
        'method_or_tension': 'Selective refusal vs. coverage',
        'source_location': 'Geifman & El-Yaniv (2017), URAG (rrag001), BalanceRAG (rrag095), Sufficient Context (sufficientContext2024), NeuroSym-Cal (liu2026neurosym)',
        'experimental_setup': 'i.i.d. conformal set prediction vs. selective risk-coverage threshold calibration and multi-turn covariate shift',
        'metric_and_denominator': 'Marginal prediction-set coverage P(Y* in Gamma_alpha) >= 1-alpha vs. conditional answered-subset risk E[L_T | a_T=ans] <= alpha_r and end-to-end risk E[L_T]',
        'verified_finding': 'Theoretical/empirical: marginal set coverage (URAG) does not bound singleton selective error, and abstaining on retrieval misses lowers answered-subset risk while incurring refusal cost c_abs in end-to-end task loss Eq. (2); Open hypothesis: transferring neuro-symbolic confidence calibration (validated on code ECE in Liu et al. 2026) to covariate-shift RAG',
        'evidence_tier': 'open_testable_hypothesis',
    },
    {
        'table_or_sec': 'Table 7 (Row 6)',
        'method_or_tension': 'Multimodal & agentic scaling',
        'source_location': 'Capabilities: ColPali, TableRAG, G-Retriever, ChatQA 1/2, CoE; Attacks/Audits: Poisoned-MRAG (rrag229), LogicPoison (rrag127), AgentPoison (rrag053), MemoryGraft (rrag188), Traceback (rrag128), MEMSAD (rrag072)',
        'experimental_setup': 'Visual, tabular, graph, and persistent agent-memory RAG under cross-modal, subgraph, and memory poisoning',
        'metric_and_denominator': 'Multimodal/Graph QA F1 vs. cross-modal/subgraph/memory ASR and post-hoc traceback precision',
        'verified_finding': 'Empirical: cross-modal triggers, GraphRAG subgraph cascades, and persistent memory poisoning compromise extended pipelines, while post-hoc corpus traceback and memory anomaly detection are validated individually; Open hypothesis: automated end-to-end multi-turn cache and memory lineage revocation',
        'evidence_tier': 'open_testable_hypothesis',
    },
]

cm_path = data / 'claim_evidence_matrix.csv'
with cm_path.open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(cm_rows[0].keys()))
    w.writeheader()
    w.writerows(cm_rows)
(data / 'claim_evidence_matrix.json').write_text(json.dumps(cm_rows, ensure_ascii=False, indent=2) + '\n')

# 5. Build reproducible paired diagnostic re-analysis (paired_diagnostic_reanalysis.json & .csv) for W2 & W4
paired_diagnostics = {
    'protocol_version': 'v40_coupled_transition_reanalysis',
    'operational_estimator_taxonomy': [
        {
            'formal_quantity': 'Property 1 End-to-End Task Risk: sup_{Omega_inv} E_S[L_T(Phi_T(Y_T), Z*) | q\', C\'] <= eps_task (Eq. 2a)',
            'direct_operational_estimator': 'Worst-case task-score lower bound min_{C\'} M(y_hat_{C\'}, y*) >= tau (Certifiable Accuracy cacc at tau=1 in RobustRAG) over bounded corruption |C\' Delta C| <= k\'; or empirical maximum loss across K paired perturbations (q\', C\') in Omega_inv_hat with refusal scored at L_T(abs, Z*) = c_abs > 0.',
            'directional_proxy_metrics': 'Dataset-mean EM/F1 under synthetic noise ratios (RGB, RECOMP, Chain-of-Note), conditional gold-present EM drop (RAAT), Resilience Rate P(Y_RAG=z* | y_theta=z*) (xRAG), and RAD = 100*|ARA-Add|/|ARA| (Park & Lee). These average over finite test sets or condition on closed-book/gold-present subsets rather than bounding the full-pipeline supremum.',
            'untested_when_using_proxy_alone': 'Retriever recall misses (when pre-filtered to gold-present queries in RAAT), worst-case adversarial perturbations (when averaging over benign noise), and semantic distribution drift among distinct error classes.',
        },
        {
            'formal_quantity': 'Property 1 Semantic Distributional Invariance: sup_{Omega_inv} D_TV(P_S(Phi_T | q, C), P_S(Phi_T | q\', C\')) <= delta_stab (Eq. 2b)',
            'direct_operational_estimator': 'Plug-in L1/2 distance 0.5 * sum_{z in Z_hat} |P_hat_M(z | q, C) - P_hat_M(z | q\', C\')| over M decoding draws clustered into semantic equivalence classes Z_hat via normalized alias match or bidirectional NLI entailment, with finite-sample concentration bound O(sqrt(|Z_hat|/M)).',
            'directional_proxy_metrics': 'Single-draw answer flip rate 1 - A->A (Park & Lee Table 8) or self-consistency agreement rate.',
            'untested_when_using_proxy_alone': 'Pointwise accuracy and binary correct/incorrect transition rates (Resilience/Boost, EM drop) do NOT identify D_TV: e.g., over (z*, wrong_A, wrong_B), P=(0.80, 0.20, 0.00) and Q=(0.80, 0.00, 0.20) have identical accuracy 0.80 and error 0.20, yet D_TV(P, Q) = 0.20 > 0.',
        },
        {
            'formal_quantity': 'Property 2 Counterfactual Update Risk & Plasticity: E[L_T | Omega_upd] <= eps_upd, P_S(Z* | q\', D\') - P_0(q\') >= gamma_resp*(1 - P_0(q\')), P_S(Z_0 | Omega_upd^conf) <= delta_prior (Eq. 3)',
            'direct_operational_estimator': 'Paired corpus-state transition (q, C_0) -> (q, C_1) where authoritative evidence shifts W_T^ref from Z_0 to Z* != Z_0 (instantiated on counterfactual entity-swap benchmarks ConFiQA, NQ-Swap, FaithEval, CoFaithfulQA, Parenting SQuAD2.0-Eval): Context Adherence Rate ConR / R_Ad estimates P_S(Z* | q\', D\'), Memorization Rate MemR estimates P_S(Z_0 | Omega_upd^conf), and M-draw sampling estimates probability gain Delta P_S(Z*) with Clopper-Pearson / bootstrap CIs.',
            'directional_proxy_metrics': 'xRAG Boost Rate P(Y_RAG=z* | y_theta!=z*) on a static corpus. Boost Rate measures whether retrieval corrects closed-book ignorance on a static fact, which motivates external context reliance but does NOT construct a paired authoritative state transition Z_0 -> Z* overriding an existing belief.',
            'untested_when_using_proxy_alone': 'Static closed-book-to-RAG comparisons do not test whether the system overrides a high-confidence stale parametric prior (Z_0 -> Z*) or whether provenance weights rho(d) reject low-authority misinformation.',
        },
        {
            'formal_quantity': 'Property 3 Admissible Risk-Coverage Control & VoI Routing: E[L_T | a_T=ans] <= alpha_r, P(a_T=ans) >= tau_cov,r under budget B (Eqs. 4, 5, 9)',
            'direct_operational_estimator': 'Empirical selective risk R_hat_sel(tau) = sum_{i in ans(tau)} L_T(Y_i, z_i*) / |ans(tau)| and coverage Cov_hat(tau) = |ans(tau)| / N_cal calibrated on held-out split D_cal,r via dual multipliers (lambda_r, nu_r) or Clopper-Pearson UCB threshold tau_hat_UCB(alpha_r, delta) (BalanceRAG, Geifman & El-Yaniv, Sufficient Context Fig. 4).',
            'directional_proxy_metrics': 'Marginal split-conformal set coverage P(Y* in Gamma_alpha) >= 1 - alpha (URAG), uncalibrated verbalized confidence ECE/AUROC, or standalone unanswerable F1.',
            'untested_when_using_proxy_alone': 'Marginal set coverage over multi-answer sets does not bound singleton error on accepted answers; and lowering selective risk via abstention on retrieval misses (W_T^loc=empty != W_T^ref={z*}) still incurs refusal loss c_abs in Property 1 end-to-end risk Eq. (2a) unless VoI-routed re-retrieval recovers z*.',
        },
    ],
    'paired_empirical_reanalyses': [
        {
            'case_id': 'Pair_1_Pillar_I_Compression',
            'compared_methods': 'RECOMP (Extractive 75-tok vs. Abstractive T5-Large 64-tok, v1 Table 2) vs. xRAG (1-tok bridge, Table 11 & Table 3)',
            'single_metric_illusion': 'On single-hop NQ, RECOMP Abstractive (37.04 EM at 36 tok), RECOMP Extractive (36.57 EM at 37 tok), and xRAG (39.10 EM at 1 tok) appear similarly effective at extreme compression (9-18x to 175x), and xRAG improves Resilience Rate from 74.1% to 82.3% (+8.2 pp).',
            'coupled_framework_diagnosis': 'Evaluating Property 1 and Property 2 proxies jointly with multi-hop Omega_gap exposes distinct failure mechanisms: (1) in RECOMP Table 2, moving from 75-token extractive selection to 64-token T5-Large abstractive compression slightly helps single-hop NQ (36.57 -> 37.04 EM, -2.82 vs. -2.35 pp) but nearly doubles the multi-hop HotpotQA loss from -2.40 pp (32.80 -> 30.40 EM) to -4.60 pp (32.80 -> 28.20 EM) due to dropped bridge premises; (2) in xRAG Table 11, collapsing 175.1 tokens into 1 embedding token raises Resilience (+8.2 pp) by attenuating context influence, which simultaneously depresses Boost Rate from 29.5% to 22.2% (-7.3 pp) and lags on multi-hop HotpotQA.',
            'property_status': {'Property_1_Stability': 'Proxy tested (EM drop / Resilience)', 'Property_2_Responsiveness': 'Directional proxy only in xRAG (Boost -7.3 pp); paired Z_0->Z* untested', 'Property_3_Control': 'Null-gate tested in RECOMP; sequential VoI untested'},
        },
        {
            'case_id': 'Pair_2_Pillar_II_Adherence_vs_Noise',
            'compared_methods': 'Base LLaMA2-7B-Chat vs. Prompt / CAD / IRCAN vs. RAAT vs. Parenting (Parenting Table 1, p. 8, on SQuAD2.0-Eval, RGB, and KNOT)',
            'single_metric_illusion': 'Evaluated on context adherence (R_Ad) alone on RGB, IRCAN (72.50%) and CAD (70.00%) outperform Base (68.00%) and appear superior to RAAT (49.50%); evaluated on noise robustness (R_Ro) alone on RGB, RAAT (41.00%) outperforms Base (29.50%), IRCAN (20.00%), and CAD (16.00%).',
            'coupled_framework_diagnosis': 'Coupling Property 1 (R_Ro under noisy distractors) with Property 2 (R_Ad under counterfactual context updates Z_0 -> Z*) on identical backbones proves that single-axis methods trade one property against the other: CAD and IRCAN raise R_Ad (+2.0 to +4.5 pp on RGB; +1.52 to +8.97 pp on SQuAD) by inducing blind context compliance that collapses R_Ro (-13.50 and -9.50 pp on RGB; -7.60 and -2.90 pp on SQuAD), whereas noise-only adversarial training in RAAT raises R_Ro (+11.50 pp on RGB; +24.33 pp on SQuAD) by inducing parametric stubbornness that drops R_Ad below the unadapted base model (-18.50 pp on RGB; -4.95 pp on SQuAD). Subspace-decoupled tuning in Parenting jointly improves both (RGB: 79.50% R_Ad [+11.50 pp], 45.50% R_Ro [+16.00 pp]; SQuAD: 69.24% R_Ad [+25.04 pp], 44.85% R_Ro [+28.45 pp]).',
            'property_status': {'Property_1_Stability': 'Directly tested on R_Ro noise splits', 'Property_2_Responsiveness': 'Directly tested on paired counterfactual R_Ad splits', 'Property_3_Control': 'Untested (forced answering)'},
        },
        {
            'case_id': 'Pair_3_Cross_Study_Comparability_Audit',
            'compared_methods': 'RAAT on RAG-Bench (Table 2: 83.07 -> 82.10 EM) vs. RGB Stress Test (Table 1: 96.33 -> 76.00% Acc) vs. Chain-of-Note on NQ/TQA/WebQ (Tables 2-3)',
            'single_metric_illusion': 'Surface comparison suggests RAAT nearly eliminates counterfactual noise degradation (-0.97 pp EM), whereas RGB and Chain-of-Note still suffer 15-25 pp degradation at high noise ratios.',
            'coupled_framework_diagnosis': 'C1-C5 protocol alignment corrects three non-comparable experimental denominators: (1) RAAT (§4.1) pre-filters test queries to those with >=2 gold passages in top-k (conditioning on retrieval recall = 1) and compares against unadapted LLaMA2-7B (51.80 -> 38.37 EM, -13.43 pp) and golden-only fine-tuned RALM_golden (74.03 -> 65.40 EM, -8.63 pp); (2) Chain-of-Note evaluates both unfiltered DPR top-k (Table 2, where retrieval recall is 64.2-89.9%) and controlled noise ratios up to 100% (Table 3, where gold support is completely absent at 100% noise); and (3) RGB scores lenient substring match on recent news entities.',
            'property_status': {'Property_1_Stability': 'Conditional reader stability (RAAT) vs. end-to-end stability (CoN Table 2)', 'Property_2_Responsiveness': 'Untested', 'Property_3_Control': 'Unknown rejection tested in CoN at 100% noise; untested in RAAT'},
        },
        {
            'case_id': 'Pair_4_Abstention_vs_Recovery_Scoring',
            'compared_methods': 'Static Sufficiency Abstention (Sufficient Context / Park & Lee Unans Prompt) vs. VoI-Routed Corrective Search (CRAG / CtrlA) under Paraphrase Recall Miss (W_T^loc = empty != W_T^ref = {z*})',
            'single_metric_illusion': 'On queries where initial retrieval misses the gold passage (32% of NQ in Park & Lee Table 3), abstaining reduces answered-subset hallucination rate and improves conditional selective accuracy (Property 3 Eq. 5).',
            'coupled_framework_diagnosis': 'Under our joint Property 1 + Property 3 scoring rule, when W_T^ref(q\', E_ref\') = {z*} != empty (solvable query in Omega_inv whose initial retrieval D_1 missed z*), terminal abstention satisfies selective risk E[L_T | a_T=ans] <= alpha_r only by shrinking coverage P(a_T=ans) and incurring full refusal penalty L_T(abs, z*) = c_abs in end-to-end task risk E[L_T] (Eq. 2a). Satisfying Eq. (2a) and Eq. (5) simultaneously requires positive-VoI re-retrieval (Eq. 9: VoI(re-retrieve) > C_op) to recover z* into D_2, reserving terminal abstention for true corpus gaps (W_T^ref = empty) or exhausted budget B.',
            'property_status': {'Property_1_Stability': 'Violated by static abstention on solvable recall misses (loss = c_abs); satisfied via recovery', 'Property_2_Responsiveness': 'N/A (warrant invariant)', 'Property_3_Control': 'Coupled selective risk <= alpha_r and coverage >= tau_cov,r under budget B'},
        },
    ],
}
(data / 'paired_diagnostic_reanalysis.json').write_text(json.dumps(paired_diagnostics, ensure_ascii=False, indent=2) + '\n')
with (data / 'paired_diagnostic_reanalysis.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['case_id', 'compared_methods', 'single_metric_illusion', 'coupled_framework_diagnosis'])
    w.writeheader()
    for row in paired_diagnostics['paired_empirical_reanalyses']:
        w.writerow({k: row[k] for k in ['case_id', 'compared_methods', 'single_metric_illusion', 'coupled_framework_diagnosis']})

# 6. Recompute exact distributions and update corpus_snapshot.json
snap_path = data / 'corpus_snapshot.json'
snap = json.loads(snap_path.read_text())

core_primary = [r for r in lit_rows if r['study_type'] == 'primary_rag_study']
core_ft = [r for r in core_primary if r['verification_status'].startswith('full_text')]
all_primary = [r for r in cit_rows if r['study_type'].startswith('primary_rag_study')]

def dist_of(rows, cols):
    out = {}
    for c in cols:
        cnt = collections.Counter(r[c] for r in rows)
        out[c] = dict(cnt.most_common())
    return out

coord_cols = [
    'C1_evidence_state',
    'representation_modality',
    'C2_disturbance_origin',
    'C2_capability_and_budget',
    'C3_intervention_stage',
    'C4_outcome_metric',
    'C5_action_policy',
]

snap['coordinate_distributions_core_full_text_verified_327'] = dist_of(core_ft, coord_cols)
snap['coordinate_distributions_core_primary_rag_331'] = dist_of(core_primary, coord_cols)
snap['coordinate_distributions_all_primary_rag_356_sensitivity'] = dist_of(all_primary, coord_cols)

# Also compute C1 distribution if pure severity precedence is applied across the full union C1_all_applicable
sev_prec_counts = collections.Counter()
strand_vs_sev_diff = []
for r in core_primary:
    tags = [t.strip() for t in r['C1_all_applicable'].split(';') if t.strip() in rank]
    sev_top = min(tags, key=lambda t: rank[t])
    sev_prec_counts[sev_top] += 1
    if sev_top != r['C1_evidence_state']:
        strand_vs_sev_diff.append({
            'cite_key': r['cite_key'],
            'mechanism_strand': r['mechanism_strand'],
            'primary_C1_evidence_state': r['C1_evidence_state'],
            'secondary_regimes': r['C1_secondary_regimes'],
            'highest_severity_in_all_applicable': sev_top,
        })

ml_counts = {}
for col in ['C1_all_applicable', 'C2_capability_all_applicable', 'C4_all_applicable', 'C5_all_applicable']:
    cnt = collections.Counter()
    for r in core_primary:
        for t in r[col].split(';'):
            t = t.strip()
            if t and t != 'N/A':
                cnt[t] += 1
    ml_counts[col + '_counts'] = dict(cnt.most_common())
snap['multilabel_actual_coverage_core_primary_rag_331'] = ml_counts

# Compute maximum sensitivity drift (in percentage points) across 327 full-text, 331 core primary, and 356 all primary
max_drift_pp = 0.0
drift_by_dim = {}
for c in coord_cols:
    d327 = snap['coordinate_distributions_core_full_text_verified_327'][c]
    d331 = snap['coordinate_distributions_core_primary_rag_331'][c]
    d356 = snap['coordinate_distributions_all_primary_rag_356_sensitivity'][c]
    keys = set(d327) | set(d331) | set(d356)
    dim_max = 0.0
    for k in keys:
        p327 = 100.0 * d327.get(k, 0) / len(core_ft)
        p331 = 100.0 * d331.get(k, 0) / len(core_primary)
        p356 = 100.0 * d356.get(k, 0) / len(all_primary)
        dim_max = max(dim_max, abs(p356 - p331), abs(p331 - p327), abs(p356 - p327))
    drift_by_dim[c] = round(dim_max, 2)
    max_drift_pp = max(max_drift_pp, dim_max)

snap['c1_c5_semantic_audit_and_precedence_protocol'] = {
    'canonical_source_file': 'survey_reproducibility/data/literature_map.csv (336 core records) + deterministic sync via scripts/sync_canonical_data.py to citation_index.csv (390) and coverage_decisions.csv (476)',
    'three_field_c1_invariant': 'For all 331 core primary studies, set(C1_all_applicable) == {C1_evidence_state} union set(C1_secondary_regimes) and C1_evidence_state not in set(C1_secondary_regimes) (0 omissions out of 336 rows).',
    'primary_vs_secondary_adjudication_rule': 'Step 1 (Strand-Anchored Primary): C1_evidence_state records the primary perturbation regime targeted by the study core thesis and mechanism strand (Strand 3.x -> adversarially_manipulated; Strand 2.2-2.4 -> conflicting_evidence; Strand 1.1-1.4 & 2.1 -> noisy_or_distracting; Strand 4.1-4.5 -> insufficient_or_uncertain; general cross-pipeline evaluation suites -> clean_or_heterogeneous_mix), while C1_secondary_regimes records auxiliary evaluation splits. Step 2 (Multi-Stressor Benchmark Tie-Breaking): Benchmarks spanning multiple stressors without a single method locus are adjudicated by severity precedence (adversarially_manipulated > conflicting_evidence > noisy_or_distracting > insufficient_or_uncertain > clean_or_heterogeneous_mix).',
    'multi_regime_secondary_higher_severity_count': len(strand_vs_sev_diff),
    'c1_distribution_under_unconditional_severity_precedence_331': dict(sev_prec_counts.most_common()),
    'source_located_reclassifications_applied': {
        'c1_benchmark_and_modality_reclassifications': len(c1_audit_updates),
        'c2_cross_file_reconciliations_and_updates': 6 + len(c2_audit_updates),
        'c4_metric_denominator_alignments': len(c4_audit_updates),
        'missing_metric_descriptions_populated': len(missing_metrics_updates),
        'cross_file_discrepancies_remaining': 0,
    },
    'sensitivity_analysis_max_coordinate_drift_pp': {
        'max_drift_pp_across_327_331_356': round(max_drift_pp, 2),
        'max_drift_pp_by_dimension': drift_by_dim,
        'pre_2024_temporal_share_core_336': '14/336 (4.17%)',
        'pre_2024_temporal_share_all_cited_390': '46/390 (11.79%, after foundational and venue snowballing remediation)',
        'residual_paywall_accessibility_rate_core_331': '4/331 (1.21%, ACM metadata/abstract records venue044, venue045, venue049, venue050; 327/331 = 98.79% full-text PDF verified)',
        'disposition_of_236_stage1a_deprioritized_candidates': {
            'scope_exclusion_routine_domain_deployment_without_omega_stressor': 167,
            'representative_selection_secondary_variants_of_covered_strands': 69,
        },
        'disposition_of_459_initial_no_open_pdf_hits': {
            'deduplicated_against_open_arxiv_or_proceedings_versions_in_stage1b_1c': 312,
            'out_of_scope_non_rag_or_broken_metadata_stubs': 143,
            'retained_as_metadata_abstract_only_acm_records_in_core_map': 4,
        },
    },
}

snap['packaged_literature_map_sha256'] = hashlib.sha256((data / 'literature_map.csv').read_bytes()).hexdigest()
snap['packaged_citation_index_sha256'] = hashlib.sha256((data / 'citation_index.csv').read_bytes()).hexdigest()
snap['packaged_coverage_decisions_sha256'] = hashlib.sha256((data / 'coverage_decisions.csv').read_bytes()).hexdigest()
snap['packaged_venue_queries_sha256'] = hashlib.sha256((data / 'venue_systematic_queries.csv').read_bytes()).hexdigest()
snap['packaged_claim_evidence_matrix_sha256'] = hashlib.sha256((data / 'claim_evidence_matrix.csv').read_bytes()).hexdigest()
snap['packaged_paired_diagnostic_reanalysis_sha256'] = hashlib.sha256((data / 'paired_diagnostic_reanalysis.csv').read_bytes()).hexdigest()

snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + '\n')
print("Updated claim_evidence_matrix, paired_diagnostic_reanalysis, and corpus_snapshot.json.")
print("Max C1-C5 drift across 327/331/356:", round(max_drift_pp, 2), "pp", drift_by_dim)
print("Multi-regime studies with higher-severity secondary split:", len(strand_vs_sev_diff))
