# Round-2 候选 pair（按 v2.1 §6 规则机械生成）

- 来源：`../human_round2_evidence274_results/evidence_map_round2_adjudicated.csv`（268 篇，含 failure/intervention/method_family/benchmark/metrics 列）。
- 生成器：`generate_pairs.py`。每篇推导五坐标签名（failure/assumption/intervention/metric/action；action 由 method_family+intervention 推断，未报告记 `U`），再按 §6 四条规则装配。
- 产物：
  - `r2_candidate_pairs_for_annotation.csv`：发给标注者（无裁决）。
  - `r2_coordinator_hidden_pair_key.csv`：协调员保留，含每对 A/B 五坐标 + `expected_verdict` + `mechanical_check`（=按规则机械读出，应与 expected 一致）。
- 四类各 12 对；48/48 机械判定与目标类别一致。
- **必须人工核对**：坐标值由证据图标签推断、较粗；尤其 `valid`（同 method_family 的同签名对）与 `under-specified`（同 failure、一方 action 未报告）务必逐对核对真实论文后再定稿；borderline 的换掉。
