#!/usr/bin/env python3
"""Deterministic verification script for all quantitative, taxonomic, C1-C5 cross-file consistency, and formal CPOMDP/warrant artifacts of the Robust RAG Systematic Survey."""
import collections, csv, hashlib, json, re
import math
from pathlib import Path

root = Path(__file__).resolve().parent
data = root / 'data'

snap = json.loads((data / 'corpus_snapshot.json').read_text())
lit_bytes = (data / 'literature_map.csv').read_bytes()
cit_bytes = (data / 'citation_index.csv').read_bytes()
cov_bytes = (data / 'coverage_decisions.csv').read_bytes()
vq_bytes = (data / 'venue_systematic_queries.csv').read_bytes()
cm_bytes = (data / 'claim_evidence_matrix.csv').read_bytes()
pd_bytes = (data / 'paired_diagnostic_reanalysis.csv').read_bytes()
r80_bytes = (data / 'stratified_80_protocol_recoding_audit.csv').read_bytes()
s71_bytes = (data / 'secondary_variants_71_sensitivity.csv').read_bytes()
wmb_bytes = (data / 'warrant_micro_benchmark_audit.csv').read_bytes()
oct_bytes = (data / 'open_coding_and_temporal_audit.json').read_bytes()

assert hashlib.sha256(lit_bytes).hexdigest() == snap['packaged_literature_map_sha256']
assert hashlib.sha256(cit_bytes).hexdigest() == snap['packaged_citation_index_sha256']
assert hashlib.sha256(cov_bytes).hexdigest() == snap['packaged_coverage_decisions_sha256']
assert hashlib.sha256(vq_bytes).hexdigest() == snap['packaged_venue_queries_sha256']
assert hashlib.sha256(cm_bytes).hexdigest() == snap['packaged_claim_evidence_matrix_sha256']
assert hashlib.sha256(pd_bytes).hexdigest() == snap['packaged_paired_diagnostic_reanalysis_sha256']
assert hashlib.sha256(r80_bytes).hexdigest() == snap['packaged_stratified_80_recoding_audit_sha256']
assert hashlib.sha256(s71_bytes).hexdigest() == snap['packaged_secondary_variants_71_sha256']
assert hashlib.sha256(wmb_bytes).hexdigest() == snap['packaged_warrant_micro_benchmark_sha256']
assert hashlib.sha256(oct_bytes).hexdigest() == snap['packaged_open_coding_temporal_audit_sha256']

lit_rows = list(csv.DictReader((data / 'literature_map.csv').open()))
cit_rows = list(csv.DictReader((data / 'citation_index.csv').open()))
cov_rows = list(csv.DictReader((data / 'coverage_decisions.csv').open()))
cm_rows = list(csv.DictReader((data / 'claim_evidence_matrix.csv').open()))
pd_json = json.loads((data / 'paired_diagnostic_reanalysis.json').read_text())
r80_rows = list(csv.DictReader((data / 'stratified_80_protocol_recoding_audit.csv').open()))
s71_rows = list(csv.DictReader((data / 'secondary_variants_71_sensitivity.csv').open()))
wmb_rows = list(csv.DictReader((data / 'warrant_micro_benchmark_audit.csv').open()))
wmb_json = json.loads((data / 'warrant_micro_benchmark_audit.json').read_text())

assert len(lit_rows) == 336, len(lit_rows)
assert sum(1 for r in lit_rows if r['study_type'] == 'primary_rag_study') == 330
assert sum(1 for r in lit_rows if r['study_type'] == 'survey_or_overview') == 5
assert sum(1 for r in lit_rows if r['study_type'] == 'foundational_or_survey') == 1
assert all(r['metrics_reported_or_relevant'].strip() for r in lit_rows), "Empty metrics_reported_or_relevant found"
assert not any(r['metrics_reported_or_relevant'].strip().lower() in {'high', 'medium', 'low'} for r in lit_rows)
assert all(r.get('taxonomy_pillar') and r.get('mechanism_strand') for r in lit_rows)

# 1. Verify 326 full-text-verified core primary studies and 4 metadata-only ACM records (330 core primary RAG studies total)
core_ft = [r for r in lit_rows if r['study_type'] == 'primary_rag_study' and r['verification_status'].startswith('full_text')]
assert len(core_ft) == 326, len(core_ft)
meta_only_keys = sorted(r['cite_key'] for r in lit_rows if 'metadata_and_abstract' in r['verification_status'])
assert meta_only_keys == ['venue044', 'venue045', 'venue049', 'venue050'], meta_only_keys

# 2. Verify all 20 normalized Strand x.y codes exist in the 326 full-text-verified core primary studies
strand_codes = {re.match(r'(Strand \d+\.\d+)', r['mechanism_strand']).group(1) for r in core_ft}
assert len(strand_codes) == 20, (len(strand_codes), sorted(strand_codes))

# 3. Verify three-field C1 invariant across all 336 core records:
# set(C1_all_applicable) == {C1_evidence_state} union set(C1_secondary_regimes) and C1_evidence_state not in C1_secondary_regimes
prec = ['adversarially_manipulated', 'conflicting_evidence', 'noisy_or_distracting', 'insufficient_or_uncertain', 'clean_or_heterogeneous_mix']
rank = {k: i for i, k in enumerate(prec)}
secondary_higher_severity_count = 0
for r in lit_rows:
    if r['study_type'] in {'survey_or_overview', 'foundational_or_survey'}:
        assert r['C1_evidence_state'] == 'N/A_foundational_or_survey'
        continue
    prim = r['C1_evidence_state'].strip()
    assert prim in rank, (r['cite_key'], prim)
    all_tags = {t.strip() for t in r['C1_all_applicable'].split(';') if t.strip()}
    sec_tags = {t.strip() for t in r.get('C1_secondary_regimes', '').split(';') if t.strip()}
    assert prim not in sec_tags, (r['cite_key'], prim, sec_tags)
    assert all_tags == ({prim} | sec_tags), (r['cite_key'], prim, sec_tags, all_tags)
    if min(all_tags, key=lambda t: rank[t]) != prim:
        secondary_higher_severity_count += 1

assert secondary_higher_severity_count == 41, secondary_higher_severity_count

# 4. Verify zero cross-file discrepancies across literature_map.csv, citation_index.csv, and coverage_decisions.csv
lit_by_key = {r['cite_key']: r for r in lit_rows}
cit_by_key = {r['cite_key']: r for r in cit_rows}
cov_by_key = {r['cite_key']: r for r in cov_rows if r['in_main_text'] == 'true'}
assert len(cit_rows) == len(cov_by_key) == 390

shared_cols = [
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
for k, cr in cit_by_key.items():
    cv = cov_by_key[k]
    for col in shared_cols:
        assert cr[col] == cv[col], (k, col, cr[col], cv[col])
    if k in lit_by_key:
        lr = lit_by_key[k]
        for col in shared_cols + ['taxonomy_pillar', 'mechanism_strand', 'all_applicable_pillars', 'is_figure2_representative_76']:
            assert cr[col] == lr[col], (k, col, cr[col], lr[col])

# 4b. Verify source-located 5-stratum semantic audit invariants (W3 & W4):
# (i) BEIR (venueExpanded087) is a foundational retrieval benchmark (nDCG@10 / Recall@100), not an end-to-end RAG generation study
assert lit_by_key['venueExpanded087']['study_type'] == 'foundational_or_survey'
assert lit_by_key['venueExpanded087']['C3_intervention_stage'] == 'evaluation_protocol_and_benchmark'
assert lit_by_key['venueExpanded087']['C4_outcome_metric'] == 'retrieval_ranking_and_exposure'
assert lit_by_key['venueExpanded087']['C5_action_policy'] == 'N/A_retrieval_only_benchmark'

# (ii) URAG (rrag001) is an uncertainty/conformal benchmark outputting LAC/APS sets, not a closed-loop abstention controller
assert lit_by_key['rrag001']['C3_intervention_stage'] == 'evaluation_protocol_and_benchmark'
assert lit_by_key['rrag001']['C4_outcome_metric'] == 'selective_risk_and_calibration_ece'
assert lit_by_key['rrag001']['C5_action_policy'] == 'conformal_set_or_uncertainty_calibration'

# (iii) All 17 core conformal-set and uncertainty/calibration scoring studies are separated from selective_abstention_or_clarification
conformal_or_uq_keys = {
    'rrag001', 'rrag007', 'rrag012', 'rrag074', 'rrag087', 'rrag089', 'rrag105',
    'rrag135', 'rrag146', 'rrag159', 'rrag164', 'rrag178', 'rrag181',
    'venue051', 'venueExpanded028', 'venueExpanded082', 'calibRAG2025',
}
for k_uq in conformal_or_uq_keys:
    assert lit_by_key[k_uq]['C5_action_policy'] == 'conformal_set_or_uncertainty_calibration', k_uq
assert cit_by_key['uncertaintyRAG2024']['C5_action_policy'] == 'conformal_set_or_uncertainty_calibration'

# (iv) Retrieval-only benchmarks/studies have C5 = N/A_retrieval_only_benchmark
for k_ret in ['venueExpanded087', 'rrag168', 'poisoningRetrievalCorpora2023', 'rrag090', 'colpali2025']:
    assert cit_by_key[k_ret]['C5_action_policy'] == 'N/A_retrieval_only_benchmark', k_ret

# (iv-b) Verify exact C5 distribution across all 355 primary studies (264, 22, 18, 25, 22, 4) and 330 core primary studies (246, 22, 17, 22, 20, 3)
prim_355 = [r for r in cit_rows if r['study_type'].startswith('primary_rag_study')]
core_330 = [r for r in lit_rows if r['study_type'] == 'primary_rag_study']
c5_355 = collections.Counter(r['C5_action_policy'] for r in prim_355)
c5_330 = collections.Counter(r['C5_action_policy'] for r in core_330)
assert c5_355 == {
    'single_pass_grounded_answering': 264,
    'selective_abstention_or_clarification': 22,
    'conformal_set_or_uncertainty_calibration': 18,
    'adaptive_re_retrieval_and_routing': 25,
    'multi_pass_verification_or_aggregation': 22,
    'N/A_retrieval_only_benchmark': 4,
}, dict(c5_355)
assert c5_330 == {
    'single_pass_grounded_answering': 246,
    'selective_abstention_or_clarification': 22,
    'conformal_set_or_uncertainty_calibration': 17,
    'adaptive_re_retrieval_and_routing': 22,
    'multi_pass_verification_or_aggregation': 20,
    'N/A_retrieval_only_benchmark': 3,
}, dict(c5_330)

# (iv-c) Verify all 6 foundational statistical concentration and multiple-testing theory sources are present (Section 5.4)
for k_stat in ['hoeffding1963probability', 'mcdiarmid1989bounded', 'bentkus2004hoeffding', 'bretz2009graphical', 'bates2021rcps', 'angelopoulos2025ltt']:
    assert k_stat in cit_by_key and cit_by_key[k_stat]['study_type'] == 'foundational_or_survey', k_stat

# (iv-d) Verify N=80 stratified direct-protocol recoding audit row-level Cohen's kappa and confusion matrices (W2)
assert len(r80_rows) == 80
assert len( collections.Counter(r['strand_code'] for r in r80_rows) ) == 20
assert all(v == 4 for v in collections.Counter(r['strand_code'] for r in r80_rows).values())
def verify_kappa(rows, col_a, col_b):
    n = len(rows)
    po = sum(1 for r in rows if r[col_a] == r[col_b]) / n
    ca = collections.Counter(r[col_a] for r in rows)
    cb = collections.Counter(r[col_b] for r in rows)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    return round((po - pe) / (1.0 - pe), 3)
k_c1 = verify_kappa(r80_rows, 'coder_A_C1_primary', 'coder_B_C1_primary')
k_mod = verify_kappa(r80_rows, 'coder_A_modality', 'coder_B_modality')
k_c2 = verify_kappa(r80_rows, 'coder_A_C2_origin', 'coder_B_C2_origin')
k_c3 = verify_kappa(r80_rows, 'coder_A_C3_stage', 'coder_B_C3_stage')
k_c4 = verify_kappa(r80_rows, 'coder_A_C4_metric', 'coder_B_C4_metric')
k_c5 = verify_kappa(r80_rows, 'coder_A_C5_policy', 'coder_B_C5_policy')
assert (k_c1, k_mod, k_c2, k_c3, k_c4, k_c5) == (0.842, 0.964, 0.892, 0.910, 0.928, 0.956), (k_c1, k_mod, k_c2, k_c3, k_c4, k_c5)

# (iv-e) Verify N=71 excluded secondary variants row-level sensitivity recomputation for N=401 and N=426 (W3)
assert len(s71_rows) == 71
assert sum(1 for r in s71_rows if r['reports_negative_result_or_counterexample'] == 'true') == 0
c5_401 = collections.Counter(r['C5_action_policy'] for r in (core_330 + s71_rows))
c5_426 = collections.Counter(r['C5_action_policy'] for r in (prim_355 + s71_rows))
assert c5_401['single_pass_grounded_answering'] == 300 and sum(c5_401.values()) == 401
assert c5_426['single_pass_grounded_answering'] == 318 and sum(c5_426.values()) == 426

# (iv-f) Verify 20-instance warrant micro-benchmark closed-form rho and ranking reversals (W4)
assert len(wmb_rows) == 20
assert wmb_json['comparative_ranking_reversal_summary']['Pi_comply_unconditional_context_compliance']['mean_definition1_loss_across_20_instances'] == 0.50
assert wmb_json['comparative_ranking_reversal_summary']['Pi_prior_stubborn_parametric_reader']['mean_definition1_loss_across_20_instances'] == 0.50
assert wmb_json['comparative_ranking_reversal_summary']['Pi_warrant_provenance_and_voi_controller']['mean_definition1_loss_across_20_instances'] == 0.05
# (v) Benchmark papers have C3 = evaluation_protocol_and_benchmark, and AttnTrace (rrag208) is corpus_and_index_security / multi_pass_verification_or_aggregation
for k_bench in ['rrag001', 'rrag019', 'rrag114', 'rrag142', 'rrag148', 'rrag157', 'rrag164', 'rrag168', 'rrag190', 'venueExpanded088']:
    assert lit_by_key[k_bench]['C3_intervention_stage'] == 'evaluation_protocol_and_benchmark', k_bench
assert lit_by_key['rrag208']['C3_intervention_stage'] == 'corpus_and_index_security'
assert lit_by_key['rrag208']['C5_action_policy'] == 'multi_pass_verification_or_aggregation'

# (vi) Verify W4 unified-scope re-audit of Round-2 exclusions: zero legacy outside_text_scope tags remain
cov_all_by_key = {r['cite_key']: r for r in cov_rows}
assert not any('outside_text_scope' in r['role'] for r in cov_rows if r['cite_key'] not in {'rrag194', 'rrag196'})
assert cov_all_by_key['venue001']['status'] == 'excluded_duplicate_merged' and cov_all_by_key['venue001']['canonical_key'] == 'venueExpanded059'
for k_code in ['rrag194', 'rrag196']:
    assert cov_all_by_key[k_code]['status'] == 'excluded_representative_selection_round2'
    assert cov_all_by_key[k_code]['C1_evidence_state'] == 'adversarially_manipulated'
    assert 'Rule R1' in cov_all_by_key[k_code]['role']

assert lit_by_key['rrag037']['C1_evidence_state'] == 'noisy_or_distracting'
assert set(lit_by_key['rrag037']['C1_all_applicable'].split(';')) == {'noisy_or_distracting', 'conflicting_evidence', 'insufficient_or_uncertain'}
assert lit_by_key['rrag037']['C4_outcome_metric'] == 'end_to_end_task_em_and_f1'
assert cit_by_key['rrag120']['C2_disturbance_origin'] == cov_by_key['rrag120']['C2_disturbance_origin'] == 'adversarial_corpus_poisoning'
assert cit_by_key['rrag120']['C2_capability_and_budget'] == cov_by_key['rrag120']['C2_capability_and_budget'] == 'black_box_corpus_write_bounded_m'
assert lit_by_key['rrag019']['C1_evidence_state'] == 'adversarially_manipulated'

# 5. Verify W1, W2, and Section 5.4 quantitative source fixes in claim_evidence_matrix.csv
cm_by_row = {r['table_or_sec']: r for r in cm_rows}
assert '64 tok / 28.20 EM (-4.60 pp)' in cm_by_row['Table 6 (Row 3)']['verified_finding']
assert '32 tok / 58.68 EM (-3.69 pp)' in cm_by_row['Table 6 (Row 3)']['verified_finding']
assert 'not token-budget-matched' in cm_by_row['Table 6 (Row 3)']['verified_finding']
assert '51.80 -> 38.37 (-13.43 pp EM' in cm_by_row['Table 6 (Row 6)']['verified_finding']
assert 'A(P_k, k\')' in cm_by_row['Table 6 (Row 13)']['verified_finding']
assert '1.63x' in cm_by_row['Table 6 (Row 13)']['verified_finding'] and '3.65x' in cm_by_row['Table 6 (Row 13)']['verified_finding']
assert '1.16x' in cm_by_row['Table 6 (Row 13)']['verified_finding'] and '2.87x' in cm_by_row['Table 6 (Row 13)']['verified_finding']
assert '20 sampled responses + 5 evaluation queries' in cm_by_row['Table 6 (Row 17)']['metric_and_denominator']
assert '1600-tok chunk' in cm_by_row['Table 6 (Row 17)']['metric_and_denominator']
assert 'without certifying a prescribed alpha_r' in cm_by_row['Table 6 (Row 17)']['verified_finding']

# 5b. Verify exact pre-2024 temporal shares and zero stale legacy keys in corpus_snapshot.json (W5):
assert sum(1 for r in lit_rows if int(r['year']) < 2024) == 14
assert sum(1 for r in cit_rows if int(r['year_in_map']) < 2024) == 38
for stale_key in [
    'coordinate_distributions_core_full_text_verified_327',
    'coordinate_distributions_core_primary_rag_331',
    'coordinate_distributions_all_primary_rag_356_sensitivity',
    'multilabel_actual_coverage_core_primary_rag_331',
]:
    assert stale_key not in snap, stale_key
assert snap['c1_c5_semantic_audit_and_precedence_protocol']['sensitivity_analysis_max_coordinate_drift_pp']['pre_2024_temporal_share_all_cited_390_by_year_in_map'].startswith('38/390 (9.74%')
assert snap['c1_c5_semantic_audit_and_precedence_protocol']['sensitivity_analysis_max_coordinate_drift_pp']['pre_2024_temporal_share_all_cited_390_by_bib_pub_year'].startswith('33/390 (8.46%')

# Verify backup directory (if present) is byte-identical to canonical data
backup_dir = root.parent / 'revision_survey_20261026/survey_resources_backup'
if backup_dir.exists():
    for fname in ['literature_map.csv', 'citation_index.csv', 'coverage_decisions.csv', 'corpus_snapshot.json']:
        assert (backup_dir / fname).read_bytes() == (data / fname).read_bytes(), fname

# Verify Pair 2 evidence grading in paired_diagnostic_reanalysis.json (W5 & Section 4.3):
pair2 = [c for c in pd_json['paired_empirical_reanalyses'] if c['case_id'] == 'Pair_2_Pillar_II_Adherence_vs_Noise'][0]
assert 'Proxy only: stipulated counterfactual entity-swap compliance' in pair2['property_status']['Property_2_Responsiveness']
assert 'Partial empirical proxy' in pair2['property_status']['Property_1_Stability']

# 6. Verify formal mathematical propositions, counterexamples, and FWER calibration (W1, W2, W4, W5, Sec. 4):
# (a) Symmetric F1 set-mismatch loss penalizes unsupported extra claims z_3:
def f1_set_loss(pred_set, ref_set):
    return 1.0 - (2.0 * len(pred_set & ref_set)) / (len(pred_set) + len(ref_set))
Z_star = {'z1', 'z2'}
assert abs(f1_set_loss({'z1', 'z2'}, Z_star) - 0.0) < 1e-12
assert abs(f1_set_loss({'z1', 'z2', 'z3'}, Z_star) - 0.20) < 1e-12

# (b) W2.1 & W2.2: Fine-grained semantic TV vs. coarse 4-label collapse & two-sample error bound:
P_dist = (0.80, 0.20, 0.00)
Q_dist = (0.80, 0.00, 0.20)
acc_P, acc_Q = P_dist[0], Q_dist[0]
tv_PQ = 0.5 * sum(abs(p - q) for p, q in zip(P_dist, Q_dist))
assert abs(acc_P - acc_Q) < 1e-12 and abs(tv_PQ - 0.20) < 1e-12
# Coarse collapsing (merging err_A and err_B into other-error) reduces TV to 0 (hiding semantic drift):
P_coarse = (P_dist[0], P_dist[1] + P_dist[2])
Q_coarse = (Q_dist[0], Q_dist[1] + Q_dist[2])
tv_coarse = 0.5 * sum(abs(p - q) for p, q in zip(P_coarse, Q_coarse))
assert abs(tv_coarse - 0.0) < 1e-12 and tv_coarse < tv_PQ
# Two-sample statistical margin eps_stat(M, C_sem, K, delta) with 2M independent draws (sensitivity c_i = 1/M, sum c_i^2 = 2/M):
def tv_eps_stat(M, C_sem=5, K=5, delta=0.10):
    return math.sqrt((C_sem - 1.0) / M) + math.sqrt(math.log(2.0 * K / delta) / M)
assert tv_eps_stat(20, 5, 5, 0.10) > 0.10  # Pilot M=20 is too wide for tight delta_stab=0.10
M_req_008 = math.ceil(((math.sqrt(5 - 1) + math.sqrt(math.log(2 * 5 / 0.10))) / 0.08) ** 2)
assert tv_eps_stat(M_req_008, 5, 5, 0.10) <= 0.08 + 1e-12
# Verify W1b exact two-sample binomial counterexample at P=Q=(0.5,0.5), C_sem=2, K=1, M=1000, delta=1e-12:
M_w1b = 1000
delta_w1b = 1e-12
eps_w1b_corrected = tv_eps_stat(M_w1b, C_sem=2, K=1, delta=delta_w1b)
assert abs(eps_w1b_corrected - 0.19992063248965553) < 1e-12
binom_probs_1000 = [math.comb(M_w1b, x) * (0.5 ** M_w1b) for x in range(M_w1b + 1)]
tail_w1b_corrected = sum(
    binom_probs_1000[x] * binom_probs_1000[y]
    for x in range(M_w1b + 1)
    for y in range(M_w1b + 1)
    if abs(x - y) > eps_w1b_corrected * M_w1b
)
assert tail_w1b_corrected <= delta_w1b and abs(tail_w1b_corrected - 3.5050062e-19) < 1e-24

# (c) Proposition 1 complete verification (W1):
def tau_task_fn(r0, c_abs, eps_task):
    assert r0 <= eps_task + 1e-12
    return (eps_task - r0) / (c_abs - r0) if c_abs > r0 else 1.0

def p_tol_fn(r0, c_abs, eps_task, delta_stab, tau_cov):
    return min(tau_task_fn(r0, c_abs, eps_task), delta_stab, 1.0 - tau_cov)

# (c1) Reviewer W1 counterexample: r0 = 0.20 > alpha_r = 0.10 breaks Eq. (5) even when p_miss = 0.05 <= 0.10!
P_base_ce = (0.80, 0.20, 0.00)
p_miss_ce = 0.05
P_pert_ce = (0.80 * (1.0 - p_miss_ce), 0.20 * (1.0 - p_miss_ce), p_miss_ce)  # (0.76, 0.19, 0.05)
r0_ce, c_abs_ce, eps_task_ce, delta_stab_ce, tau_cov_ce, alpha_ce = 0.20, 0.20, 0.25, 0.10, 0.90, 0.10
task_risk_ce = (1.0 - p_miss_ce) * r0_ce + p_miss_ce * c_abs_ce
tv_ce = 0.5 * sum(abs(p - q) for p, q in zip(P_base_ce, P_pert_ce))
cov_ce = 1.0 - p_miss_ce
sel_risk_ce = r0_ce
assert abs(task_risk_ce - 0.20) < 1e-12 and task_risk_ce <= eps_task_ce
assert abs(tv_ce - 0.05) < 1e-12 and tv_ce <= delta_stab_ce
assert abs(cov_ce - 0.95) < 1e-12 and cov_ce >= tau_cov_ce
assert sel_risk_ce > alpha_ce  # Violates Eq. (5) because r0 = 0.20 > alpha_r = 0.10!

# (c2) Feasible low-miss case when r0 = 0.0 <= alpha_r = 0.10 and non-zero r0 = 0.05 <= alpha_r = 0.10:
c_abs_w1 = 0.20
eps_task_w1 = 0.02
delta_stab_w1 = 0.10
tau_cov_w1 = 0.90
alpha_w1 = 0.10
r0_w1 = 0.0
p_tol_w1 = p_tol_fn(r0_w1, c_abs_w1, eps_task_w1, delta_stab_w1, tau_cov_w1)
assert r0_w1 <= alpha_w1 and abs(p_tol_w1 - 0.10) < 1e-12
p_miss_low = 0.05
e_loss_low = (1.0 - p_miss_low) * r0_w1 + p_miss_low * c_abs_w1
tv_low = 0.5 * (abs(1.0 - (1.0 - p_miss_low)) + abs(0.0 - p_miss_low))
cov_low = 1.0 - p_miss_low
assert e_loss_low <= eps_task_w1 + 1e-12 and tv_low <= delta_stab_w1 + 1e-12 and cov_low >= tau_cov_w1 - 1e-12 and r0_w1 <= alpha_w1
# Non-zero r0 = 0.05 <= alpha_r = 0.10 with c_abs = 0.25, eps_task = 0.07 -> tau_task = (0.07 - 0.05)/(0.25 - 0.05) = 0.10:
assert abs(tau_task_fn(0.05, 0.25, 0.07) - 0.10) < 1e-12

# (c3) Three-way separation when p_miss = 0.32 > p_tol = 0.10:
p_miss_high = 0.32
assert p_miss_high * c_abs_w1 > eps_task_w1 and (1.0 - p_miss_high) < tau_cov_w1
p_rec = 0.75
c_op_reretrieve = 0.02
voi_reretrieve = p_rec * c_abs_w1
assert voi_reretrieve > c_op_reretrieve and (1.0 - p_miss_high * (1.0 - p_rec)) >= tau_cov_w1 - 1e-12
# Also verify non-equivalence: if p_rec = 0.20, VoI = 0.20 * 0.20 = 0.04 > C_op = 0.02 (Bellman VoI-positive),
# yet post-recovery miss is 0.32 * 0.80 = 0.256 > p_tol = 0.10 (fails reachability for coverage/task-risk constraints!):
assert (0.20 * c_abs_w1 > c_op_reretrieve) and (p_miss_high * (1.0 - 0.20) > p_tol_w1)

# (d) Population CPOMDP dual threshold calibration:
classes = [(0.5, 0.0), (0.5, 0.15)]
alpha_r = 0.10
tau_cov = 1.0
c_abs_cpomdp = 0.10
lam_r = 0.0
nu_r = 0.05  # c_abs + nu_r = 0.15 > alpha_r = 0.10
tau_thr_star = (c_abs_cpomdp + lam_r * alpha_r + nu_r) / (1.0 + lam_r)
assert abs((tau_thr_star - alpha_r) - (c_abs_cpomdp + nu_r - alpha_r) / (1.0 + lam_r)) < 1e-12
answered_prob = sum(p for p, r_q in classes if r_q <= tau_thr_star)
pop_sel_risk = sum(p * r_q for p, r_q in classes if r_q <= tau_thr_star) / answered_prob
assert answered_prob >= tau_cov - 1e-12 and pop_sel_risk <= alpha_r + 1e-12

# (e) Simultaneous multiple-testing FWER calibration for binary 0-1 loss (exact binomial) & bounded [0,1] F1 loss (Hoeffding-Bentkus):
def binom_cdf(k, m, alpha):
    return sum(math.comb(m, j) * (alpha ** j) * ((1.0 - alpha) ** (m - j)) for j in range(k + 1))
def kl_ber(q, p):
    if q <= 0.0:
        return -math.log(1.0 - p)
    if q >= 1.0:
        return -math.log(p)
    return q * math.log(q / p) + (1.0 - q) * math.log((1.0 - q) / (1.0 - p))
def hb_pval(r_hat, m, alpha):
    if m <= 0 or r_hat > alpha:
        return 1.0
    return min(math.exp(-m * kl_ber(r_hat, alpha)), math.e * binom_cdf(math.ceil(m * r_hat), m, alpha), 1.0)
# Verify W1a counterexample: M_lambda = 100, R_hat_lambda = R_sel = 0.20 > alpha_r = 0.10
# Untruncated KL term is ~0.0117924 < 0.05, whereas one-sided hb_pval returns 1.0 (and returns 1.0 at m=0):
untruncated_kl_w1a = math.exp(-100 * kl_ber(0.20, 0.10))
assert abs(untruncated_kl_w1a - 0.01179238) < 1e-6 and untruncated_kl_w1a < 0.05
assert hb_pval(0.20, 100, 0.10) == 1.0 and hb_pval(0.0, 0, 0.10) == 1.0
# Candidate grid of |Lambda| = 5 thresholds at delta = 0.10, alpha_r = 0.10
p_val_safe = binom_cdf(k=8, m=200, alpha=0.10)
p_val_hb_safe = hb_pval(r_hat=0.035, m=200, alpha=0.10)
assert p_val_safe <= 0.10 / 5
assert p_val_hb_safe <= 0.10 / 5
assert len(pd_json['five_confound_comparability_audit_vs_c1_x_c3_baseline']['five_confounds_detected_by_coupled_framework']) == 5

summary = {
    'status': 'PASS',
    'verification_scope_note': 'Deterministic verification of canonical dataset hashes, cross-file synchronization, 5-stratum C1-C5 source audit invariants, 4-level coding sensitivity, and mathematical propositions/counterexamples (Proposition 1, TV coarsening inequality, and FWER p-values).',
    'total_unique_cited_works': len(cit_rows),
    'deduplicated_core_map_b_studies': len(lit_rows),
    'core_primary_rag_studies': 330,
    'core_full_text_pdf_verified_studies': 326,
    'core_metadata_only_acm_studies': 4,
    'core_metadata_only_keys': meta_only_keys,
    'core_foundational_or_prior_surveys_na': 6,
    'supplementary_primary_rag_studies': 25,
    'supplementary_foundational_adjacent_or_survey_na': 29,
    'total_primary_rag_studies_all_cited': 355,
    'total_foundational_adjacent_or_survey_na_all_cited': 35,
    'full_eligible_core_primary_pool_with_71_variants': 401,
    'full_eligible_all_primary_pool_with_71_variants': 426,
    'c5_distribution_all_primary_355': dict(c5_355),
    'c5_distribution_core_primary_330': dict(c5_330),
    'c5_distribution_full_eligible_core_401': dict(c5_401),
    'c5_distribution_full_eligible_all_426': dict(c5_426),
    'pre_2024_core_by_year_in_map': '14/336 (4.17%)',
    'pre_2024_all_cited_by_year_in_map': '38/390 (9.74%)',
    'pre_2024_all_cited_by_bib_pub_year': '33/390 (8.46%)',
    'distinct_strands_in_core_326_full_text': len(strand_codes),
    'c1_three_field_set_union_omissions': 0,
    'c1_multi_regime_higher_severity_secondary_count': secondary_higher_severity_count,
    'cross_file_c1_c5_discrepancies': 0,
    'beir_and_urag_semantic_audit_verified': True,
    'six_statistical_theory_foundations_verified': True,
    'stratified_80_recoding_audit_kappas': {
        'C1_primary': k_c1,
        'representation_modality': k_mod,
        'C2_disturbance_origin': k_c2,
        'C3_intervention_stage': k_c3,
        'C4_outcome_metric': k_c4,
        'C5_action_policy': k_c5,
    },
    'w1a_one_sided_hb_pval_verified': {
        'untruncated_kl_at_020_vs_010': round(untruncated_kl_w1a, 7),
        'one_sided_hb_pval_at_020_vs_010': hb_pval(0.20, 100, 0.10),
        'one_sided_hb_pval_at_m0': hb_pval(0.0, 0, 0.10),
    },
    'w1b_two_sample_tv_bound_verified': {
        'eps_stat_at_C2_K1_M1000_delta1e12': round(eps_w1b_corrected, 7),
        'exact_two_sample_binomial_tail': tail_w1b_corrected,
        'holds_below_delta': tail_w1b_corrected <= delta_w1b,
    },
    'warrant_micro_benchmark_20_instances_verified': True,
    'w4_unified_scope_round2_audit_verified': True,
    'empty_metric_fields_in_core_map': 0,
    'claim_evidence_matrix_rows': len(cm_rows),
    'paired_diagnostic_reanalysis_cases': len(pd_json['paired_empirical_reanalyses']),
    'five_confound_comparability_gains_over_c1_x_c3': 5,
    'tv_fine_grained_vs_coarse_collapse_verified': {'acc_P': acc_P, 'acc_Q': acc_Q, 'fine_grained_D_TV': round(tv_PQ, 4), 'coarse_collapsed_D_TV': round(tv_coarse, 4)},
    'proposition_1_counterexample_and_voi_verified': {
        'p_tol': round(p_tol_w1, 4),
        'w1_selective_risk_violation_when_r0_exceeds_alpha': {'p_miss': p_miss_ce, 'r_0': r0_ce, 'alpha_r': alpha_ce, 'E_L': round(task_risk_ce, 4), 'D_TV': round(tv_ce, 4), 'Cov': round(cov_ce, 4), 'violates_eq5': True},
        'low_miss_counterexample_admissible': {'p_miss': p_miss_low, 'E_L': round(e_loss_low, 4), 'D_TV': round(tv_low, 4), 'Cov': round(cov_low, 4)},
        'high_miss_voi_recovery': {'p_miss': p_miss_high, 'net_voi': round(voi_reretrieve - c_op_reretrieve, 4), 'post_recovery_cov': round(1.0 - p_miss_high * (1.0 - p_rec), 4)},
    },
    'sha256_verified': True,
}
print(json.dumps(summary, indent=2))
