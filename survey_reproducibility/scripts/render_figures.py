"""V29 native 2D PowerPoint reconstruction of Figures 1, 3 (Quantitative Meta-Analysis), and 4 (Lifecycle Recovery)."""
from editorial import *
import copy, hashlib

P = deck()
P.core_properties.title = 'Robust RAG: Mathematical Principles, Lifecycle Recovery, and Quantitative Meta-Analysis (V29)'
drawings = []

def note(a, name):
    png_path = R / 'image2_png' / f'{name}.png'
    sha = hashlib.sha256(png_path.read_bytes()).hexdigest()
    a.s.notes_slide.notes_text_frame.text = (
        f'gpt-image-2.5 design, V29 (Harmonious Pastel Academic Edition): image2_png/{name}.png\n'
        f'SHA256={sha}\n'
        'Reconstructed as 100% native editable 2D PowerPoint shapes and typography. '
        'Zero 3D, zero gradients, zero shadows, zero embedded bitmaps, zero heavy dark banners.'
    )

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 1: Core Mathematical Principles of Robust RAG (Eqs. 2 to 5)
# ═══════════════════════════════════════════════════════════════════════════
a = Art(P, '01_concept')
drawings.append(a)

title(a, 'f1_title', 22, 12, 680, 'Core Principles of Robust RAG Across Evidence Transitions', 'ink', 22)
txt(a, 'f1_subtitle', 22, 45, 680, 'Distributional invariance, counterfactual plasticity, and POMDP control under partial observation D\'', 12.0, False, 'muted')

a.rect('base_chip', 714, 10, 464, 58, 'bg_chip', 'bl_border', 0.9, .05)
txt(a, 'bq_head', 724, 17, 138, 'Partial Obs. D\'', 10.5, True, 'ink', 'center')
txt(a, 'bq_body', 724, 33, 138, 'D\' = R(q\', C\')\nContamination ε ≤ ε_max', 9.2, False, 'slate', 'center')
arrow(a, 'b_arr1', 864, 39, 878, 39, 'blue', 1.3)
txt(a, 'bp_head', 882, 17, 148, 'Ref. Warrant W_T^ref', 10.2, True, 'blue', 'center')
txt(a, 'bp_body', 882, 33, 148, 'Evaluator W_T^ref vs.\nSystem Est. W_hat', 9.0, False, 'ink', 'center')
arrow(a, 'b_arr2', 1034, 39, 1048, 39, 'blue', 1.3)
txt(a, 'ba_head', 1052, 17, 118, 'Stochastic Policy', 10.5, True, 'ink', 'center')
txt(a, 'ba_body', 1052, 35, 118, 'P_S(Φ_T(Y) | q\', C\')', 10.5, True, 'blue_dark', 'center')

a.line('f1_header_rule', (22, 76), (1178, 76), 'line', 0.85)

panels = [
    ('a', 22, 374, 'blue', 'bl', 'bl_border', 'Selective stability', '(Eq. 2 invariance)', '(risk & TV bound)'),
    ('b', 413, 374, 'teal', 'tl', 'tl_border', 'Justified responsiveness', '(Eq. 3 plasticity)', '(counterfactual gain)'),
    ('c', 804, 374, 'purple', 'pl', 'pl_border', 'Graceful degradation', '(Eqs. 4 & 5 control)', '(risk ≤ α_r under B)'),
]
for key, x, w, col, pastel, brd, heading, g_sub, o_sub in panels:
    a.rect(f'panel_{key}', x, 88, w, 492, 'white', brd, 1.0, .022)
    a.rect(f'head_{key}', x, 88, w, 44, pastel, brd, 0.9, .022)
    a.circle(f'badge_{key}', x + 28, 110, 13, col, None, 0)
    txt(a, f'badge_t_{key}', x + 15, 101, 26, f'({key})', 11.5, True, 'white', 'center')
    title(a, f'head_t_{key}', x + 50, 99, w - 60, heading, 'ink', 17.5)

    a.rect(f'subbar_{key}', x + 8, 140, w - 16, 36, 'bg_slate', 'subline', 0.7, .03)
    txt(a, f'sc1_h_{key}', x + 12, 144, 104, 'Evidence Input', 10, True, 'ink', 'center')
    txt(a, f'sc1_s_{key}', x + 12, 158, 104, '(observed D\')', 9, False, 'muted', 'center')
    txt(a, f'sc2_h_{key}', x + 120, 144, 126, 'Controlled Gate', 10, True, 'ink', 'center')
    txt(a, f'sc2_s_{key}', x + 120, 158, 126, g_sub, 9, False, 'muted', 'center')
    txt(a, f'sc3_h_{key}', x + 250, 144, 114, 'Robust Output', 10, True, 'ink', 'center')
    txt(a, f'sc3_s_{key}', x + 250, 158, 114, o_sub, 9, False, 'muted', 'center')

# Panel (a)
folded_doc(a, 'a_doc_P', 32, 188, 102, 130, 'blue', 'bl', 11)
txt(a, 'a_P_tag', 42, 198, 30, 'P', 12.5, True, 'blue')
txt(a, 'a_P_txt', 40, 220, 86, 'Verified support\nWarranted premise', 9.2, True, 'ink')
a.line('a_P_l1', (42, 258), (120, 258), 'bl_border', 1.1)
a.line('a_P_l2', (42, 268), (108, 268), 'bl_border', 1.1)
check_badge(a, 'a_P_chk', 118, 302, 7.5, 'teal')

folded_doc(a, 'a_doc_D', 32, 334, 102, 148, 'red', 'rl', 11)
txt(a, 'a_D_tag', 42, 344, 30, 'D', 12.5, True, 'red')
txt(a, 'a_D_txt', 40, 366, 88, 'Hard negative /\nDistractor / Prompt\ninjection (ε ≤ ε_max)', 9.0, False, 'red_dark')
a.line('a_D_l1', (42, 422), (120, 422), 'rl_border', 1.1)
a.line('a_D_l2', (42, 432), (106, 432), 'rl_border', 1.1)
cross_badge(a, 'a_D_crs', 118, 466, 7.5, 'red')

arrow(a, 'a_in_P', 136, 252, 148, 252, 'blue', 1.3)
arrow(a, 'a_in_D', 136, 404, 148, 404, 'red', 1.3, dash=True)

a.rect('a_gate', 150, 188, 114, 294, 'bg_slate', 'blue', 1.0, .04)
shield_icon(a, 'a_shield', 207, 212, 19, 'blue', 'bl')
txt(a, 'a_gate_t', 155, 228, 104, 'Selective\nRelevance &\nPrivilege Gate', 10, True, 'ink', 'center', serif=True)

a.rect('a_pass_row', 157, 286, 100, 34, 'tl', 'tl_border', 0.8, .12)
check_badge(a, 'a_pass_c', 169, 303, 6.2, 'teal')
txt(a, 'a_pass_t', 179, 296, 74, 'Valid P → Pass', 8.8, True, 'teal_dark')

a.rect('a_blk_row', 157, 328, 100, 34, 'rl', 'rl_border', 0.8, .12)
cross_badge(a, 'a_blk_c', 169, 345, 6.2, 'red')
txt(a, 'a_blk_t', 179, 338, 74, 'Noise D → Block', 8.8, True, 'red_dark')

a.rect('a_rule_box', 157, 376, 100, 92, 'white', 'bl_border', 0.8, .06)
txt(a, 'a_rule_t', 161, 390, 92, 'W_T^ref(q\', E_ref\') =\nW_T^ref(q, E_ref);\nisolate D.', 8.8, False, 'slate', 'center')

arrow(a, 'a_out_arr', 266, 296, 278, 296, 'blue', 1.4)

a.rect('a_out_card', 280, 206, 106, 258, 'bl', 'blue', 1.0, .04)
doc_mini_icon(a, 'a_out_ico', 326, 222, 15, 20, 'blue', 'white')
txt(a, 'a_out_eq', 284, 254, 98, 'D_TV ≤ δ_stab', 12.0, True, 'ink', 'center')
a.line('a_out_div', (292, 286), (374, 286), 'bl_border', 0.8)
txt(a, 'a_out_l1', 284, 298, 98, 'Distributional\ninvariance', 10, True, 'blue_dark', 'center')
txt(a, 'a_out_l2', 284, 336, 98, 'Bound loss ε_task\n& violation η_sec.', 9.2, False, 'slate', 'center')

a.rect('a_exc', 30, 496, 358, 74, 'rl_soft', 'rl_border', 0.85, .04)
cross_badge(a, 'a_exc_c', 48, 518, 7.5, 'red')
txt(a, 'a_exc_h', 62, 504, 318, 'Excludes degenerate mode:', 10, True, 'red_dark')
txt(a, 'a_exc_b', 62, 521, 318, 'Unconditional Context Compliance', 11, True, 'ink')
txt(a, 'a_exc_s', 62, 540, 318, '(blindly adopting salient distractors or injected prompts)', 9.8, False, 'muted')

# Panel (b)
folded_doc(a, 'b_doc_P0', 423, 188, 102, 108, 'subtle', 'bg_slate', 11)
txt(a, 'b_P0_tag', 433, 198, 36, 'P0', 12, True, 'muted')
txt(a, 'b_P0_txt', 431, 220, 86, 'Stale prior y_θ /\nSuperseded claim', 9.0, False, 'muted')
a.line('b_P0_l1', (433, 258), (511, 258), 'line', 1.1)
a.line('b_P0_l2', (433, 268), (498, 268), 'line', 1.1)

arrow(a, 'b_upd_down', 442, 302, 442, 332, 'teal', 1.4)
txt(a, 'b_upd_lbl', 448, 309, 76, 'Valid update', 9.5, True, 'teal_dark')

folded_doc(a, 'b_doc_P1', 423, 338, 102, 144, 'teal', 'tl', 11)
txt(a, 'b_P1_tag', 433, 348, 36, 'P1', 12, True, 'teal_dark')
txt(a, 'b_P1_txt', 431, 370, 86, 'Authoritative\ncorroborated\nevidence z*', 9.5, True, 'ink')
a.line('b_P1_l1', (433, 422), (511, 422), 'tl_border', 1.1)
a.line('b_P1_l2', (433, 432), (498, 432), 'tl_border', 1.1)
check_badge(a, 'b_P1_chk', 509, 466, 7.5, 'teal')

arrow(a, 'b_in_P1', 527, 404, 539, 404, 'teal', 1.3)

a.rect('b_gate', 541, 188, 114, 294, 'bg_slate', 'teal', 1.0, .04)
shield_icon(a, 'b_shield', 598, 212, 19, 'teal', 'tl')
txt(a, 'b_gate_t', 546, 228, 104, 'Conflict &\nProvenance Gate', 10.2, True, 'ink', 'center', serif=True)

a.rect('b_chk1', 548, 280, 100, 34, 'tl', 'tl_border', 0.8, .12)
check_badge(a, 'b_chk1_c', 560, 297, 6.2, 'teal')
txt(a, 'b_chk1_t', 570, 290, 74, 'Weight ρ(P1)', 9.0, True, 'teal_dark')

a.rect('b_chk2', 548, 322, 100, 34, 'tl', 'tl_border', 0.8, .12)
check_badge(a, 'b_chk2_c', 560, 339, 6.2, 'teal')
txt(a, 'b_chk2_t', 570, 332, 74, 'Valid Scope', 8.8, True, 'teal_dark')

a.rect('b_rule_box', 548, 372, 100, 96, 'white', 'tl_border', 0.8, .06)
txt(a, 'b_rule_t', 552, 386, 92, 'W_T^ref(q\', E_ref\') =\nz* ≠ Φ_T(y_θ);\noverride prior.', 8.8, False, 'slate', 'center')

arrow(a, 'b_out_arr', 657, 296, 669, 296, 'teal', 1.4)

a.rect('b_out_card', 671, 206, 106, 258, 'tl', 'teal', 1.0, .04)
doc_mini_icon(a, 'b_out_ico', 717, 222, 15, 20, 'teal', 'white')
txt(a, 'b_out_eq', 675, 254, 98, 'ΔP_S ≥ γ_resp', 11.5, True, 'ink', 'center')
a.line('b_out_div', (683, 286), (765, 286), 'tl_border', 0.8)
txt(a, 'b_out_l1', 675, 298, 98, 'Counterfactual\nplasticity', 10, True, 'teal_dark', 'center')
txt(a, 'b_out_l2', 675, 336, 98, 'Bound E[L_T] ≤ ε_upd\n& shift mass to z*.', 9.0, False, 'slate', 'center')

a.rect('b_exc', 421, 496, 358, 74, 'rl_soft', 'rl_border', 0.85, .04)
cross_badge(a, 'b_exc_c', 439, 518, 7.5, 'red')
txt(a, 'b_exc_h', 453, 504, 318, 'Excludes degenerate mode:', 10, True, 'red_dark')
txt(a, 'b_exc_b', 453, 521, 318, 'Static Parametric Reliance', 11, True, 'ink')
txt(a, 'b_exc_s', 453, 540, 318, '(ignoring retrieved updates to keep outputs artificially invariant)', 9.8, False, 'muted')

# Panel (c)
folded_doc(a, 'c_miss_doc', 814, 204, 96, 146, 'purple', 'pl_soft', 11, dash=True)
a.circle('c_q_circ', 862, 248, 12.5, 'white', 'purple', 1.1)
txt(a, 'c_q_mark', 852, 239, 20, '?', 13.5, True, 'purple', 'center')
txt(a, 'c_miss_lbl', 820, 274, 84, 'Local warrant\nW_T^loc = empty', 9.6, True, 'purple_dark', 'center')
txt(a, 'c_miss_sub', 812, 362, 100, 'Missing premise /\nunresolved\nconflict', 9.5, False, 'muted', 'center')

arrow(a, 'c_in_arr', 912, 276, 922, 276, 'purple', 1.3)

a.rect('c_router', 924, 224, 56, 104, 'pl', 'purple', 1.0, .06)
router_icon(a, 'c_rt_ico', 952, 246, 8, 'purple_dark')
txt(a, 'c_rt_txt', 926, 266, 52, 'POMDP\nPolicy\nΠ*(b_t, B_t)', 8.4, True, 'ink', 'center')

a.path('c_br_1', [(980, 260), (986, 260), (986, 218), (992, 218)], 'purple', 1.1)
a.line('c_br_2', (980, 276), (992, 276), 'purple', 1.1)
a.path('c_br_3', [(980, 292), (986, 292), (986, 334), (992, 334)], 'purple', 1.1)

a.rect('c_p_search', 992, 192, 66, 50, 'tl', 'teal', 0.9, .14)
magnifier_icon(a, 'c_i_search', 1006, 206, 4.8, 'teal_dark')
txt(a, 'c_t_search', 1015, 198, 40, 'Search', 9.8, True, 'teal_dark')
txt(a, 'c_s_search', 995, 218, 60, 'VoI > C_op', 8.2, False, 'slate', 'center')

a.rect('c_p_clarify', 992, 251, 66, 50, 'pl', 'purple', 0.9, .14)
bubble_icon(a, 'c_i_clarify', 1001, 261, 10, 7.5, 'purple_dark', 'white')
txt(a, 'c_t_clarify', 1014, 257, 42, 'Clarify', 9.8, True, 'purple_dark')
txt(a, 'c_s_clarify', 995, 277, 60, 'Ask / qualify', 8.2, False, 'slate', 'center')

a.rect('c_p_defer', 992, 310, 66, 50, 'bl', 'blue', 0.9, .14)
clock_icon(a, 'c_i_defer', 1007, 324, 4.8, 'blue_dark')
txt(a, 'c_t_defer', 1016, 316, 38, 'Defer', 9.8, True, 'blue_dark')
txt(a, 'c_s_defer', 995, 336, 60, 'Abstain', 8.2, False, 'slate', 'center')

a.path('c_ret_loop', [(1025, 362), (1025, 426), (952, 426), (952, 332)], 'purple', 1.15, arrow=True)
a.rect('c_ret_lblbox', 936, 412, 108, 34, 'white', 'pl_border', 0.8, .12)
txt(a, 'c_ret_txt', 940, 416, 100, 'Support restored\n→ Purge & resume', 8.5, True, 'purple_dark', 'center')

a.path('c_out_br1', [(1058, 218), (1063, 218), (1063, 334), (1058, 334)], 'purple', 1.0)
arrow(a, 'c_out_arr', 1063, 276, 1070, 276, 'purple', 1.3)

a.rect('c_out_card', 1070, 206, 100, 258, 'pl', 'purple', 1.0, .04)
doc_mini_icon(a, 'c_out_ico', 1113, 222, 15, 20, 'purple', 'white')
txt(a, 'c_out_eq', 1073, 252, 94, 'Risk ≤ α_r\nCov ≥ τ_cov,r', 10.2, True, 'ink', 'center')
a.line('c_out_div', (1080, 294), (1160, 294), 'pl_border', 0.8)
txt(a, 'c_out_l1', 1073, 306, 94, 'Bellman control\nunder budget B', 9.2, True, 'purple_dark', 'center')
txt(a, 'c_out_l2', 1073, 344, 94, 'Withhold\nunsupported\nclaims.', 9.2, False, 'slate', 'center')

a.rect('c_exc', 812, 496, 358, 74, 'rl_soft', 'rl_border', 0.85, .04)
cross_badge(a, 'c_exc_c', 830, 518, 7.5, 'red')
txt(a, 'c_exc_h', 844, 504, 318, 'Excludes degenerate mode:', 10, True, 'red_dark')
txt(a, 'c_exc_b', 844, 521, 318, 'Universal Refusal or Speculative Guessing', 11, True, 'ink')
txt(a, 'c_exc_s', 844, 540, 318, '(refusing solvable queries or fabricating unsupported citations)', 9.8, False, 'muted')

a.rect('f1_footer', 22, 592, 1156, 68, 'bg_slate', 'line', 0.9, .025)
target_icon(a, 'f1_ft_ico', 50, 626, 12, 'ink')
title(a, 'f1_ft_t1', 74, 603, 520, 'System-Level Robustness Capacity S = (R, A, G, Π)', 'ink', 14.2)
txt(a, 'f1_ft_t2', 74, 627, 520, 'Conditioned on task specification T, perturbation regime Ω, and resource budget B', 10.8, False, 'muted')

persp_cards = [
    ('p4', 606, 134, 'pl', 'pl_border', 'purple_dark', '§4', 'Evidence Construction'),
    ('p5', 748, 134, 'bl', 'bl_border', 'blue_dark', '§5', 'Evidence Use'),
    ('p6', 890, 134, 'rl', 'rl_border', 'red_dark', '§6', 'Adversarial Security'),
    ('p7', 1032, 134, 'tl', 'tl_border', 'teal_dark', '§7', 'Adaptive Control'),
]
for pk, px, pw, pfill, pbrd, pcol, psec, pname in persp_cards:
    a.rect(pk, px, 602, pw, 48, pfill, pbrd, 0.9, .06)
    txt(a, pk + '_s', px + 6, 608, pw - 12, psec, 12, True, pcol, 'center', serif=True)
    txt(a, pk + '_n', px + 6, 627, pw - 12, pname, 9.8, True, pcol, 'center')

note(a, '01_concept')

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 4 (03_interactions): Compound Evidence Failure and Lineage Repair
# ═══════════════════════════════════════════════════════════════════════════
a = Art(P, '03_interactions')
drawings.append(a)

title(a, 'f3_title', 22, 12, 740, 'Compound Evidence Failure and Provenance-Guided Repair', 'ink', 22)
txt(a, 'f3_sub', 22, 44, 740, 'Cross-stage error propagation and source-anchored state recovery across P, N, Y, and K', 12, False, 'muted')

a.rect('f3_q_box', 776, 16, 402, 44, 'bg_chip', 'bl_border', 0.9, .12)
txt(a, 'f3_q_txt', 788, 29, 378, 'Query q: Is Feature X supported on Windows?', 11.5, True, 'ink', 'center')

a.line('f3_header_rule', (22, 72), (1178, 72), 'line', 0.85)

col_headers = [
    ('ch1', 22, 266, '1', 'Source & Provenance', '(Original and mirrors)'),
    ('ch2', 304, 280, '2', 'Compression', '(Into note N)'),
    ('ch3', 598, 280, '3', 'Generation', '(Produced as Y)'),
    ('ch4', 892, 286, '4', 'Agent Memory', '(Stored in K; reused)'),
]
for ck, cx, cw, cnum, ctitle, csub in col_headers:
    a.rect(ck, cx, 82, cw, 38, 'bg_slate', 'line', 0.8, .06)
    a.circle(ck + '_b', cx + 22, 101, 11, 'muted', None, 0)
    txt(a, ck + '_n', cx + 11, 93, 22, cnum, 11, True, 'white', 'center')
    txt(a, ck + '_t', cx + 40, 86, cw - 48, ctitle, 11.5, True, 'ink')
    txt(a, ck + '_s', cx + 40, 102, cw - 48, csub, 9.8, False, 'muted')

a.rect('c1_outer', 22, 128, 266, 474, 'bl_soft', 'bl_border', 1.0, .025)

folded_doc(a, 'c1_P_doc', 36, 142, 238, 178, 'blue', 'white', 14)
a.circle('c1_P_bdg', 58, 164, 12, 'blue', None, 0)
txt(a, 'c1_P_btxt', 46, 156, 24, 'P', 12, True, 'white', 'center')
txt(a, 'c1_P_head', 78, 156, 180, 'Primary source', 12, True, 'blue_dark')
a.line('c1_P_div', (48, 184), (260, 184), 'bl_border', 0.8)
txt(a, 'c1_P_rel', 48, 194, 210, 'Technical Spec:\nFeature X is available', 12.5, True, 'ink')
a.rect('c1_P_hl', 48, 236, 172, 28, 'yl', 'yl_border', 0.9, .08)
txt(a, 'c1_P_qual', 56, 241, 156, 'only on Linux.', 13.5, True, 'ink')
txt(a, 'c1_P_note', 48, 274, 212, 'Scoped claim: Linux only (not Windows)', 9.8, False, 'muted')
a.line('c1_P_l1', (48, 298), (244, 298), 'bl_border', 1.0)

a.path('c1_fork1', [(155, 320), (155, 344), (92, 344), (92, 362)], 'blue', 1.15, dash=True)
a.path('c1_fork2', [(155, 344), (218, 344), (218, 362)], 'blue', 1.15, dash=True)

for tag, mx in [('M1', 36), ('M2', 160)]:
    folded_doc(a, f'c1_{tag}', mx, 362, 114, 146, 'blue', 'white', 10)
    a.circle(f'c1_{tag}_b', mx + 20, 382, 10.5, 'blue', None, 0)
    txt(a, f'c1_{tag}_bt', mx + 8, 375, 24, tag, 10, True, 'white', 'center')
    txt(a, f'c1_{tag}_ml', mx + 36, 375, 70, 'Mirror copy', 9.5, True, 'muted')
    txt(a, f'c1_{tag}_fx', mx + 12, 404, 90, 'Feature X:\nLinux only', 11, True, 'ink')
    a.rect(f'c1_{tag}_hl', mx + 12, 442, 88, 20, 'yl', 'yl_border', 0.7, .08)
    txt(a, f'c1_{tag}_hlt', mx + 16, 445, 80, 'only on Linux', 9.5, True, 'ink', 'center')
    txt(a, f'c1_{tag}_cp', mx + 12, 470, 90, 'Copied from P', 9.2, False, 'muted')

a.rect('c1_prov_box', 36, 522, 238, 66, 'bl', 'bl_border', 0.9, .05)
doc_mini_icon(a, 'c1_prov_ico', 50, 542, 15, 20, 'blue', 'white')
txt(a, 'c1_prov_t1', 76, 534, 188, '3 documents / 1 origin', 11.5, True, 'ink')
txt(a, 'c1_prov_t2', 76, 554, 188, '(No independent corroboration)', 10, False, 'blue_dark')

a.rect('trackA_outer', 304, 128, 874, 228, 'rl_soft', 'rl_border', 1.0, .022)
a.rect('trackA_head', 304, 128, 874, 32, 'rl', 'rl_border', 0.9, .022)
txt(a, 'trackA_htxt', 318, 136, 846, 'Track A (Error Propagation): Scope qualifier lost in N, unsupported claim cited in Y, cached in K', 11.5, True, 'red_dark')

a.rect('tA_N', 316, 168, 258, 176, 'white', 'rl_border', 0.95, .035)
a.circle('tA_N_b', 336, 188, 11, 'red', None, 0)
txt(a, 'tA_N_bt', 325, 180, 22, 'N', 11.5, True, 'white', 'center')
txt(a, 'tA_N_h', 354, 180, 208, 'Compressed Note', 12, True, 'ink')

a.rect('tA_N_in', 328, 206, 234, 82, 'rl_soft', 'rl_border', 0.8, .04)
txt(a, 'tA_N_c1', 338, 214, 214, 'Feature X is available.', 12, True, 'ink')
a.rect('tA_N_lost', 338, 242, 214, 28, 'white', 'red', 0.75, .06, dash=True)
txt(a, 'tA_N_ltxt', 346, 248, 198, 'only on Linux', 11.5, False, 'muted', 'center')
a.line('tA_N_strk', (356, 257), (534, 255), 'red', 1.3)

a.rect('tA_N_pill', 328, 298, 234, 34, 'rl_badge', 'rl_border', 0.8, .12)
bang_badge(a, 'tA_N_bg', 346, 315, 7.5, 'red', 'white')
txt(a, 'tA_N_pt', 360, 307, 194, 'Scope dropped', 11.5, True, 'red_dark')

a.rect('tA_Y', 602, 168, 268, 176, 'white', 'rl_border', 0.95, .035)
a.circle('tA_Y_b', 622, 188, 11, 'red', None, 0)
txt(a, 'tA_Y_bt', 611, 180, 22, 'Y', 11.5, True, 'white', 'center')
txt(a, 'tA_Y_h', 640, 180, 218, 'Generated Output', 12, True, 'ink')

a.rect('tA_Y_in', 614, 206, 244, 82, 'rl_soft', 'rl_border', 0.8, .04)
txt(a, 'tA_Y_c1', 624, 222, 224, 'Yes, Windows is\nsupported. [P]', 13.5, True, 'ink', 'center')

a.rect('tA_Y_pill', 614, 298, 244, 34, 'rl_badge', 'rl_border', 0.8, .12)
bang_badge(a, 'tA_Y_bg', 632, 315, 7.5, 'red', 'white')
txt(a, 'tA_Y_pt', 646, 301, 204, 'Citation kept;\nclaim unsupported', 10.2, True, 'red_dark')

a.rect('tA_K', 898, 168, 268, 176, 'white', 'rl_border', 0.95, .035)
a.circle('tA_K_b', 918, 188, 11, 'red', None, 0)
txt(a, 'tA_K_bt', 907, 180, 22, 'K', 11.5, True, 'white', 'center')
txt(a, 'tA_K_h', 936, 180, 218, 'Cached Memory Entry', 12, True, 'ink')

a.rect('tA_K_in', 910, 206, 244, 82, 'rl_soft', 'rl_border', 0.8, .04)
txt(a, 'tA_K_c1', 920, 216, 224, 'Feature X on Windows? →', 11, False, 'slate')
txt(a, 'tA_K_c2', 920, 238, 224, 'Yes, supported. [P]', 12.5, True, 'ink')

a.rect('tA_K_pill', 910, 298, 244, 34, 'rl_badge', 'rl_border', 0.8, .12)
loop_icon(a, 'tA_K_lp', 928, 315, 8.5, 'red')
txt(a, 'tA_K_pt', 944, 301, 204, 'Later turn → same error\n(Windows: yes. [P])', 10, True, 'red_dark')

a.circle('p_port_a', 274, 246, 3.2, 'white', 'red', 1.3)
arrow(a, 'tA_arr0', 277, 246, 316, 246, 'red', 1.5)
arrow(a, 'tA_arr1', 574, 246, 602, 246, 'red', 1.5)
arrow(a, 'tA_arr2', 870, 246, 898, 246, 'red', 1.5)

a.rect('trackB_outer', 304, 368, 874, 234, 'tl_soft', 'tl_border', 1.0, .022)
a.rect('trackB_head', 304, 368, 874, 32, 'tl', 'tl_border', 0.9, .022)
txt(a, 'trackB_htxt', 318, 376, 846, 'Track B (Provenance-Guided Recovery): Inspect scoped source P, correct output, invalidate N & K', 11.5, True, 'teal_dark')

a.rect('tB_R1', 316, 408, 258, 182, 'white', 'tl_border', 0.95, .035)
a.circle('tB_R1_b', 336, 428, 11, 'teal', None, 0)
magnifier_icon(a, 'tB_R1_m1', 334.5, 426.5, 4.6, 'white', 'teal')
txt(a, 'tB_R1_h', 354, 420, 208, 'Verify Primary Source P', 12, True, 'ink')

a.rect('tB_R1_in', 328, 446, 234, 88, 'tl_soft', 'tl_border', 0.8, .04)
txt(a, 'tB_R1_c1', 338, 454, 180, 'Technical Spec: Feature X\nis available', 10.5, False, 'slate')
a.rect('tB_R1_hl', 338, 488, 146, 26, 'yl', 'yl_border', 0.8, .08)
txt(a, 'tB_R1_q', 346, 493, 130, 'only on Linux.', 12, True, 'ink')
magnifier_icon(a, 'tB_R1_m2', 516, 496, 9.5, 'blue')

a.rect('tB_R1_pill', 328, 544, 234, 34, 'tl_badge', 'tl_border', 0.8, .12)
check_badge(a, 'tB_R1_ck', 346, 561, 7.5, 'teal')
txt(a, 'tB_R1_pt', 360, 553, 194, 'Restore scope qualifier', 11.5, True, 'teal_dark')

a.rect('tB_R2', 602, 408, 268, 182, 'white', 'tl_border', 0.95, .035)
check_badge(a, 'tB_R2_b', 622, 428, 11, 'teal')
txt(a, 'tB_R2_h', 640, 420, 218, 'Emit Scoped Answer', 12, True, 'ink')

a.rect('tB_R2_in', 614, 446, 244, 88, 'tl_soft', 'tl_border', 0.8, .04)
txt(a, 'tB_R2_c1', 624, 466, 224, 'No: Linux only. [P]', 12.5, True, 'ink', 'center')
txt(a, 'tB_R2_c2', 624, 494, 224, '(Windows unsupported under P)', 10, False, 'teal_dark', 'center')

a.rect('tB_R2_pill', 614, 544, 244, 34, 'tl_badge', 'tl_border', 0.8, .12)
check_badge(a, 'tB_R2_ck', 632, 561, 7.5, 'teal')
txt(a, 'tB_R2_pt', 646, 547, 204, 'Claim matches\nscoped source P', 10.2, True, 'teal_dark')

a.rect('tB_R3', 898, 408, 268, 182, 'white', 'tl_border', 0.95, .035)
a.circle('tB_R3_b', 918, 428, 11, 'teal', None, 0)
cross_badge(a, 'tB_R3_bi', 918, 428, 7, 'teal')
txt(a, 'tB_R3_h', 936, 420, 218, 'Invalidate Affected N & K', 11.5, True, 'ink')

a.rect('tB_invN', 910, 450, 244, 54, 'bg_slate', 'line', 0.8, .06)
a.circle('tB_invN_b', 925, 477, 9.5, 'red', None, 0)
txt(a, 'tB_invN_bt', 915, 470, 20, 'N', 10, True, 'white', 'center')
txt(a, 'tB_invN_t', 940, 458, 146, 'Feature X is available.', 9.8, False, 'muted')
a.line('tB_invN_s', (940, 466), (1062, 466), 'red', 1.1)
txt(a, 'tB_invN_sub', 940, 478, 146, 'Unscoped note revoked', 9.2, True, 'red_dark')
pill(a, 'tB_invN_p', 1090, 464, 58, 24, '× Revoked', 'rl', 'rl_border', 'red_dark', 8.8, True, .25)

a.rect('tB_invK', 910, 514, 244, 54, 'bg_slate', 'line', 0.8, .06)
a.circle('tB_invK_b', 925, 541, 9.5, 'red', None, 0)
txt(a, 'tB_invK_bt', 915, 534, 20, 'K', 10, True, 'white', 'center')
txt(a, 'tB_invK_t', 940, 522, 146, 'Windows: yes. [P]', 9.8, False, 'muted')
a.line('tB_invK_s', (940, 530), (1042, 530), 'red', 1.1)
txt(a, 'tB_invK_sub', 940, 542, 146, 'Derived memory reset', 9.2, True, 'red_dark')
pill(a, 'tB_invK_p', 1090, 528, 58, 24, '× Reset', 'rl', 'rl_border', 'red_dark', 8.8, True, .25)

a.circle('p_port_b', 274, 286, 3.2, 'white', 'teal', 1.3)
a.path('tB_arr0', [(277, 286), (295, 286), (295, 496), (316, 496)], 'teal', 1.5, arrow=True)
arrow(a, 'tB_arr1', 574, 496, 602, 496, 'teal', 1.5)
arrow(a, 'tB_arr2', 870, 496, 898, 496, 'teal', 1.5)

a.rect('f3_footer', 22, 612, 1156, 48, 'bg_slate', 'line', 0.9, .025)
a.rect('f3_ft_bar', 22, 612, 8, 48, 'blue', None, 0, 0)
txt(a, 'f3_ft_t1', 42, 626, 270, 'Citation present ≠ claim supported', 12.5, True, 'ink', serif=True)
txt(a, 'f3_ft_t2', 318, 628, 610, '·   Recovery requires invalidating affected derived state (N, K) alongside re-answering', 11, False, 'slate')
txt(a, 'f3_ft_t3', 936, 628, 230, '·   Lineage tracked across P, N, Y, K', 10.5, True, 'muted', 'right')

note(a, '03_interactions')

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 3 (04_empirical_audit): Quantitative Synthesis of Deduplicated Corpus & Source-Linked Benchmarks
# ═══════════════════════════════════════════════════════════════════════════
a = Art(P, '04_empirical_audit')
drawings.append(a)

title(a, 'f4_title', 22, 10, 840, 'Quantitative Synthesis: Deduplicated Corpus Coordinates and Source-Linked Benchmarks', 'ink', 19.0)
txt(a, 'f4_sub', 22, 39, 840, 'Synthesizing 389 unique cited works (330 core primary RAG studies: 326 full-text PDF + 4 metadata ACM) across C1 to C5', 10.8, False, 'muted')
a.rect('f4_badge', 874, 12, 304, 42, 'bg_chip', 'bl_border', 0.9, .10)
txt(a, 'f4_b_t1', 882, 17, 288, '389 Unique Cited · 330 Core Primary', 10.0, True, 'blue_dark', 'center')
txt(a, 'f4_b_t2', 882, 33, 288, '326 Full-Text PDF · 4 ACM Meta · 33 N/A', 8.8, False, 'slate', 'center')
a.line('f4_head_rule', (22, 62), (1178, 62), 'line', 0.85)

# ─── Panel (a): Top-Left (x=22..590, y=72..358) — Temporal Trajectory & C3 Stage Distribution (N = 330) ───
a.rect('p4a_box', 22, 72, 568, 286, 'white', 'bl_border', 1.0, .022)
a.rect('p4a_hdr', 22, 72, 568, 34, 'bl', 'bl_border', 0.9, .022)
a.circle('p4a_bdg', 44, 89, 11, 'blue', None, 0)
txt(a, 'p4a_bt', 33, 81, 22, '(a)', 10.5, True, 'white', 'center')
title(a, 'p4a_ht', 62, 79, 518, 'Temporal Growth & Intervention Stage Distribution (C3, N = 330)', 'ink', 13.5)

txt(a, 'p4a_fh', 34, 112, 152, 'Publication Trajectory', 10, True, 'blue_dark', 'center')
year_steps = [
    ('y_s1', 132, '2021-23', '14 papers (4.2%)', 'bg_slate', 'line'),
    ('y_s2', 172, '2024', '88 papers (26.7%)', 'bl_soft', 'bl_border'),
    ('y_s3', 212, '2025', '165 papers (50.0%)', 'bl', 'blue'),
    ('y_s4', 252, '2026 H1', '63 papers (19.1%)', 'tl', 'teal'),
]
for fn, fy, fnum, flbl, ffill, fstrk in year_steps:
    a.rect(fn, 34, fy, 152, 32, ffill, fstrk, 0.85, .08)
    txt(a, fn + '_n', 40, fy + 8, 54, fnum, 9.5, True, 'ink')
    txt(a, fn + '_l', 94, fy + 8, 88, flbl, 8.6, False, 'slate')

txt(a, 'p4a_fsub', 34, 290, 152, '+59 Suppl./Found. = 389', 8.5, True, 'muted', 'center')

txt(a, 'p4a_sh', 200, 112, 376, 'Distribution by Pipeline Intervention Stage (C3, N = 330)', 10, True, 'ink')
stages = [
    ('st1', 'Generator Reading & Conflict', 79, 'blue', '79 (23.9%)'),
    ('st2', 'Corpus & Index Security', 68, 'red', '68 (20.6%)'),
    ('st3', 'Evaluation & Benchmarks', 49, 'teal', '49 (14.8%)'),
    ('st4', 'Context Filtering & Assembly', 45, 'purple', '45 (13.6%)'),
    ('st5', 'Closed-Loop System Control', 41, 'teal', '41 (12.4%)'),
    ('st6', 'Multi-Stage Joint Pipeline', 35, 'blue', '35 (10.6%)'),
    ('st7', 'Query & Retriever Tuning', 13, 'purple', '13 (3.9%)'),
]
for idx, (sk, slbl, sval, scol, sstr) in enumerate(stages):
    sy = 131 + idx * 23
    txt(a, sk + '_l', 200, sy + 2, 156, slbl, 8.8, False, 'slate')
    a.rect(sk + '_bg', 358, sy + 3, 148, 14, 'bg_slate', 'subline', 0.6, 0)
    bw = max(12, round(148 * sval / 85))
    a.rect(sk + '_fg', 358, sy + 3, bw, 14, scol, None, 0, 0)
    txt(a, sk + '_v', 510, sy + 1, 66, sstr, 8.6, True, 'ink', 'right')

a.rect('p4a_iaa', 34, 304, 544, 44, 'bg_chip', 'bl_border', 0.85, .05)
txt(a, 'p4a_i1', 44, 309, 272, 'Verification Status (N = 330 Core Primary)', 9.1, True, 'blue_dark')
txt(a, 'p4a_i2', 44, 325, 272, '326 Full-Text PDF (98.8%) · 4 Metadata ACM', 8.4, False, 'slate')
a.line('p4a_idiv', (322, 310), (322, 342), 'bl_border', 0.8)
txt(a, 'p4a_i3', 332, 309, 238, 'Orthogonal Modality (N = 330)', 9.1, True, 'teal_dark')
txt(a, 'p4a_i4', 332, 325, 238, '295 Text · 17 Graph/Tab · 18 Multimodal', 8.5, True, 'ink')

# ─── Panel (b): Top-Right (x=610..1178, y=72..358) — C1, C2, C4, and C5 Coordinate Distributions ───
a.rect('p4b_box', 610, 72, 568, 286, 'white', 'tl_border', 1.0, .022)
a.rect('p4b_hdr', 610, 72, 568, 34, 'tl', 'tl_border', 0.9, .022)
a.circle('p4b_bdg', 632, 89, 11, 'teal', None, 0)
txt(a, 'p4b_bt', 621, 81, 22, '(b)', 10.5, True, 'white', 'center')
title(a, 'p4b_ht', 650, 79, 518, 'Primary & Multi-Label Coordinates C1, C2, C4, C5 (N = 330)', 'ink', 13.5)

txt(a, 'p4b_bh', 622, 112, 270, 'C1: Primary State (Multi-Label in brackets)', 9.2, True, 'ink')
c1_bars = [
    ('c1_1', 'Adversarial [145 ML]', 118, 'red', '118 (35.8%)'),
    ('c1_2', 'Insufficient [73 ML]', 58, 'purple', '58 (17.6%)'),
    ('c1_3', 'Conflicting [86 ML]', 57, 'blue', '57 (17.3%)'),
    ('c1_4', 'Noisy / Distract [105]', 49, 'teal', '49 (14.8%)'),
    ('c1_5', 'Clean / Mixed Bench', 48, 'muted', '48 (14.5%)'),
]
for idx, (ek, elbl, eval_num, ecol, estr) in enumerate(c1_bars):
    ey = 134 + idx * 26
    txt(a, ek + '_l', 622, ey + 2, 130, elbl, 8.5, False, 'slate')
    a.rect(ek + '_bg', 754, ey + 3, 78, 14, 'bg_slate', 'subline', 0.6, 0)
    ebw = max(10, round(78 * eval_num / 125.0))
    a.rect(ek + '_fg', 754, ey + 3, ebw, 14, ecol, None, 0, 0)
    txt(a, ek + '_v', 834, ey + 1, 58, estr, 8.5, True, 'ink', 'right')

a.rect('p4b_c5_card', 622, 270, 270, 78, 'tl_soft', 'tl_border', 0.85, .04)
txt(a, 'p4b_c5_h', 632, 276, 250, 'C5: System Action Policy (N = 330)', 9.2, True, 'teal_dark')
txt(a, 'p4b_c5_b1', 632, 294, 250, '• Single-Pass Answering: 250 (75.8%)', 8.4, True, 'ink')
txt(a, 'p4b_c5_b2', 632, 311, 250, '• Selective Abstention / Clarify: 39 (11.8%)', 8.4, False, 'slate')
txt(a, 'p4b_c5_b3', 632, 328, 250, '• Re-Retrieve 22 (6.7%) · Multi-Pass 19 (5.8%)', 8.3, False, 'slate')

a.rect('p4b_u1', 904, 114, 262, 234, 'bl_soft', 'bl_border', 0.85, .04)
txt(a, 'p4b_u1_h', 914, 120, 242, 'C4: Outcome Metric & Granularity (N = 330)', 9.3, True, 'blue_dark')
txt(a, 'p4b_u1_s', 914, 137, 242, 'Primary metric (Multi-Label: 280 report EM/F1)', 8.1, False, 'muted')

c4_rows = [
    ('ur1', 158, 'End-to-End EM / F1', '134 papers', '40.6%'),
    ('ur2', 181, 'Empirical ASR / Rob. Acc', '107 papers', '32.4%'),
    ('ur3', 204, 'Span Faithfulness / Cit.', '43 papers', '13.0%'),
    ('ur4', 227, 'Selective Risk / ECE', '35 papers', '10.6%'),
    ('ur5', 250, 'Top-k Retrieval Exposure', '6 papers', '1.8%'),
    ('ur6', 273, 'Certified Robust Bound', '5 papers', '1.5%'),
]
for uk, uy, ulbl, uval, udelta in c4_rows:
    txt(a, uk + '_l', 914, uy, 124, ulbl, 8.4, False, 'slate')
    txt(a, uk + '_v', 1040, uy, 66, uval, 8.4, True, 'ink', 'center')
    txt(a, uk + '_d', 1108, uy, 48, udelta, 8.4, True, 'blue_dark', 'right')

a.line('p4b_u_div', (914, 298), (1156, 298), 'bl_border', 0.8)
txt(a, 'p4b_u_ft', 914, 305, 242, 'C2 Cap. Primary [Multi]: 67 [86] BB-Write\n17 [56] WB-Grad · 24 Prompt · 10 Memory', 8.1, True, 'ink')

# ─── Panel (c): Bottom-Left (x=22..590, y=370..656) — Source-Linked Pillar I & II Benchmark Contrasts ───
a.rect('p4c_box', 22, 370, 568, 286, 'white', 'pl_border', 1.0, .022)
a.rect('p4c_hdr', 22, 370, 568, 34, 'pl', 'pl_border', 0.9, .022)
a.circle('p4c_bdg', 44, 387, 11, 'purple', None, 0)
txt(a, 'p4c_bt', 33, 379, 22, '(c)', 10.5, True, 'white', 'center')
title(a, 'p4c_ht', 62, 377, 518, 'Source-Linked Contrasts: Noise Degradation & Conflict Resolution', 'ink', 13.5)

a.rect('p4c_p1', 34, 412, 544, 108, 'pl_soft', 'pl_border', 0.85, .04)
txt(a, 'p4c_p1_h', 44, 418, 524, 'RGB Noise Curve (Tab. 1, r = 0.2 to 0.8) vs. RAG-Bench Counterfactual Noise (RAAT Tab. 2)', 9.1, True, 'purple_dark')

txt(a, 'p4c_n1_l', 44, 442, 174, 'RGB-EN ChatGPT (r = 0.2 to 0.8)', 8.5, False, 'slate')
a.rect('p4c_n1_bg', 220, 443, 172, 14, 'white', 'pl_border', 0.6, 0)
a.rect('p4c_n1_fg', 220, 443, round(172 * 0.760), 14, 'red', None, 0, 0)
txt(a, 'p4c_n1_v', 396, 441, 172, '94.7% to 76.0% Acc (-18.7 pp)', 8.5, True, 'red_dark', 'right')

txt(a, 'p4c_n2_l', 44, 466, 174, 'RAAT 7B (RAG-Bench Gold to cc)', 8.5, True, 'ink')
a.rect('p4c_n2_bg', 220, 467, 172, 14, 'white', 'tl_border', 0.6, 0)
a.rect('p4c_n2_fg', 220, 467, round(172 * 0.821), 14, 'teal', None, 0, 0)
txt(a, 'p4c_n2_v', 396, 465, 172, '83.1% to 82.1% EM (-1.0 pp)', 8.5, True, 'teal_dark', 'right')

txt(a, 'p4c_n3_l', 44, 490, 524, '• Verified Gains: FILCO +8.6 EM (NQ 7B) · CoN +7.6 EM (100% noise) · RankRAG +8.2 EM · LongRAG +7.5 F1', 8.3, True, 'ink')

a.rect('p4c_p3', 34, 530, 544, 116, 'bg_slate', 'line', 0.85, .04)
txt(a, 'p4c_p3_h', 44, 536, 524, 'Source-Linked Conflict Resolution (Table 1 / Table 2 Primary Report Cells)', 9.3, True, 'ink')

conf_bars = [
    ('cb1', 560, 'FaithfulRAG (Llama3.1-8B FaithEval)', 63.3, 79.8, '+16.5 pp, Tab. 1', 'purple'),
    ('cb2', 586, 'ParamMute (LLaMA3-8B SearchQA)', 66.8, 78.8, '+12.0 pp, Tab. 2', 'blue'),
    ('cb3', 612, 'Astute RAG (Claude 3.5 PopQA)', 36.0, 44.4, '+8.4 pp, Tab. 1', 'teal'),
]
for ck, cy, clbl, cbase, crob, cstr, ccol in conf_bars:
    txt(a, ck + '_l', 44, cy, 192, clbl, 8.5, True, 'ink')
    a.rect(ck + '_bg', 238, cy + 2, 152, 14, 'white', 'line', 0.6, 0)
    a.rect(ck + '_fg', 238, cy + 2, round(152 * crob / 100.0), 14, ccol, None, 0, 0)
    txt(a, ck + '_v', 394, cy, 174, f'{cbase:.1f}% to {crob:.1f}% ({cstr})', 8.4, True, 'ink', 'right')

# ─── Panel (d): Bottom-Right (x=610..1178, y=370..656) — Source-Linked Security & Closed-Loop Control ───
a.rect('p4d_box', 610, 370, 568, 286, 'white', 'rl_border', 1.0, .022)
a.rect('p4d_hdr', 610, 370, 568, 34, 'rl', 'rl_border', 0.9, .022)
a.circle('p4d_bdg', 632, 387, 11, 'red', None, 0)
txt(a, 'p4d_bt', 621, 379, 22, '(d)', 10.5, True, 'white', 'center')
title(a, 'p4d_ht', 650, 377, 518, 'Source-Linked Security (ASR vs. Cert. cacc) & Control Contrasts', 'ink', 13.5)

a.rect('p4d_top', 622, 412, 544, 106, 'rl_soft', 'rl_border', 0.85, .04)
txt(a, 'p4d_th', 632, 418, 524, 'Empirical Poisoning ASR vs. Certifiable Accuracy (cacc) & Measured Latency', 9.3, True, 'red_dark')

sec_cards = [
    ('sc1', 632, 168, 'PoisonedRAG (Tab. 1,4)', '97.0% ASR (N=5)', 'CPA 1% · CorruptRAG 94% (N=1)', 'white', 'rl_border', 'red_dark'),
    ('sc2', 810, 168, 'TrustRAG (Tab. 2, NQ)', '73% to 9% ASR (20% p)', '98% to 2% ASR (100% p) · 82% Acc', 'bl_soft', 'bl_border', 'blue_dark'),
    ('sc3', 988, 168, 'RobustRAG (Tab. I to III)', '38% RQA / 26% NQ cacc', 'Emp. ASR 15%/12% · 1.16 to 3.65×', 'tl_soft', 'tl_border', 'teal_dark'),
]
for lk, lx, lw, ltitle, lp1, lp2, lfill, lbrd, lcol in sec_cards:
    a.rect(lk, lx, 442, lw, 66, lfill, lbrd, 0.85, .06)
    txt(a, lk + '_t', lx + 6, 447, lw - 12, ltitle, 8.8, True, 'ink', 'center')
    txt(a, lk + '_p1', lx + 6, 465, lw - 12, lp1, 9.2, True, lcol, 'center')
    txt(a, lk + '_p2', lx + 6, 485, lw - 12, lp2, 7.8, False, 'slate', 'center')

a.rect('p4d_bot', 622, 526, 544, 120, 'white', 'tl_border', 0.85, .04)
txt(a, 'p4d_bh', 632, 532, 524, 'Closed-Loop Control & Selective Abstention Contrasts (Pillar IV Primary Tables)', 9.3, True, 'teal_dark')

ctrl_bars = [
    ('ct1', 'Self-RAG 7B (PopQA vs Llama2-7B)', 16.7, '38.2% to 54.9% (+16.7 pp, Tab. 2)', 'teal'),
    ('ct2', 'Self-CRAG (PopQA / PubHealth Tab. 1)', 6.9, '+6.9 pp Pop / +2.4 pp PubH', 'purple'),
    ('ct3', 'CtrlA-7B (TQA vs matched FLARE)', 4.0, '72.4% to 76.4% (+4.0 pp, Tab. 1)', 'blue'),
    ('ct4', 'Sufficient Context (Selective Acc)', 10.0, '+2.0 to +10.0 pp (Fig. 4)', 'teal'),
]
for idx, (dk, dlbl, dval, dstr, dcol) in enumerate(ctrl_bars):
    dy = 554 + idx * 21
    txt(a, dk + '_l', 632, dy + 1, 188, dlbl, 8.4, False, 'slate')
    a.rect(dk + '_bg', 824, dy + 3, 156, 12, 'bg_slate', 'subline', 0.5, 0)
    dbw = max(14, round(156 * dval / 18.0))
    a.rect(dk + '_fg', 824, dy + 3, dbw, 12, dcol, None, 0, 0)
    txt(a, dk + '_v', 984, dy, 172, dstr, 8.3, True, 'ink', 'right')

note(a, '04_empirical_audit')

assert not TEXT_ERRORS, json.dumps(TEXT_ERRORS, ensure_ascii=False, indent=2)
master = R / 'pptx/figures_1_3_editable.pptx'
P.save(master)
for i, n in enumerate(['01_concept', '03_interactions', '04_empirical_audit']):
    one = deck()
    s = one.slides.add_slide(one.slide_layouts[6])
    for sh in P.slides[i].shapes:
        s.shapes._spTree.insert_element_before(copy.deepcopy(sh.element), 'p:extLst')
    s.notes_slide.notes_text_frame.text = P.slides[i].notes_slide.notes_text_frame.text
    one.save(R / 'pptx' / f'{n}.pptx')
(R / 'checks/layout.json').write_text(json.dumps({'slide_size': [W, H], 'slides': [a.summary() for a in drawings]}, indent=2))
print('NEW_PPT=' + str(master))
print('NATIVE_SHAPES=' + str([len(s.shapes) for s in P.slides]))
print('LAYOUT_PREFLIGHT=PASS')
