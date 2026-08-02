# 第二轮标注总文档（valid / under-specified 验证 + 独立金标准检验循环性）

> 一份**自包含、可直接发包**的标注手册，覆盖大修后**仅剩的两项需要真人标注的任务**。
> 沿用论文现有量表（五坐标 + 四裁决 codebook）与列名，与第一轮 `comparability_user_study_package/` 口径一致。
> 协调员（Coordinator，可由你自己担任）负责发包、回收、盲化、裁决与分析；协调员专属文件不得发给普通标注者。

---

## 0. 为什么还要这一轮（上一轮的硬缺口）

第一轮（6 control + 6 protocol + 5 gold，60 对）已完成，但留下两个审稿无法回避的缺口：

| 缺口 | 第一轮实测 | 本轮目标 | 审稿点 |
|---|---|---|---|
| `valid` 裁决从未被人验证 | 金标准 60 对里 **valid = 0 对** | 补足 valid 并验证 | B3 / 审稿问题 Q1 |
| `under-specified` 样本太少 | 仅 **4 对**，per-class 不稳 | 扩到 ≥12 对 | B3 |
| 定义性循环未被检验 | “独立 rubric”与坐标金标准在 **60/60 对上 1:1 完全重合**（同一面板同时产出两套标签，等于改名，未能独立检验） | **另设一个盲审面板**，不看五坐标，用下游后果 rubric 独立判定 | B4 / 循环性批评 |

本轮把 B3 与 B4 合并为**一轮、一套样本**完成。

---

## 1. 本轮总人数与分工

| 角色 | 推荐 | 最小 | 关键约束 |
|---|---:|---:|---|
| Control 标注者 | 6 | 5 | 不给五坐标量表，仅普通专家判断 |
| Protocol 标注者 | 6 | 5 | 走五坐标量表 |
| **坐标金标准面板** | 5 | 3 | 用五坐标量表给 gold verdict |
| **独立盲审面板（B4 核心）** | 5 | 3 | **只看朴素 rubric，绝不接触五坐标/坐标金标准/两臂答案** |
| Coordinator | 1 | 1 | 可你自己 |

- **推荐 ~22 名不同标注者 + 1 协调员；最小可行 16 人。**
- **硬约束（决定 B4 成败）**：独立盲审面板**必须与坐标金标准面板、两臂标注者完全不重叠**，且全程**不接触任何五坐标材料**。第一轮失败正是因为同一批人同时产出两套标签。
- 资质：能独立阅读 RAG / 检索 / NLP 论文的研究者（博士生或以上）；英语阅读流利。金标准与独立面板成员应更资深。

---

## 2. 样本集构建（协调员在标注前完成）

- **目标规模：48 对，四类裁决各 12 对**（valid / partial / invalid / under-specified 平衡）。
  平衡设计是为了让 `valid` 与 `under-specified` 两类**各自有 ≥12 对**、能算出稳定的 per-class 准确率。
- 重点是补齐上一轮缺的两类（其余两类作锚点，可少量复用第一轮 EV60 中的 partial/invalid）：
  - **`valid` 候选（最难，≥12 对）**：找两篇**五坐标真正全对齐**、可直接比较/排序的论文。判据：同一 failure type、同一 evidence assumption、同一 intervention point、**同一 metric target、同一显式 action**。典型来源：同一 benchmark 上同指标、同 action（如都 answer-only）的两个方法；同一 leaderboard 的两个条目。
  - **`under-specified` 候选（≥12 对）**：至少一篇**缺失某个必需坐标**——最常见是 action 未报告，或安全类的 attacker capability 未交代。
- 每对提供给标注者的字段（沿用 `paper_pairs_for_annotation.csv`）：
  `pair_id, area, paper_a_key, paper_a_title, paper_b_key, paper_b_title`（可附两篇 abstract / 关键段落；**不得泄露期望裁决**）。
- 协调员另存隐藏 key `coordinator_hidden_pair_key.csv`（含 `expected_verdict`、构造类别），**只供分析**，不发给任何标注者。

> 协调员若需要，我可以从证据图（Map B）自动产出一批 `valid` / `under-specified` 候选 pair 供你筛选。

---

## 3. 量表（Control / Protocol / 坐标金标准 共用）

每对**最终裁决四选一**：

| verdict | 含义 |
|---|---|
| `valid` | 五坐标全部对齐，可直接比较 / 排序。 |
| `partial` | 同问题族，但 intervention / metric / action 有非致命错配，只能局部比较或互补。 |
| `invalid` | assumption 或 objective 定义了不同的“科学游戏”，直接比较会得错误结论。 |
| `underspecified` | 至少一个必需坐标无法从论文获得（记 `U`），信息不足。 |

**Protocol 组与坐标金标准面板**按五坐标逐项判断（Control 组不给此表）：

| 坐标 | 受控取值 | 等价 / 边界规则 | 对裁决的影响 |
|---|---|---|---|
| **failure type** | relevance/noise; sufficiency; consistency/conflict; provenance/freshness; integrity/adversarial; uncertainty/OOD | 编码被测“证据属性”，非动机；只说 robustness 而无属性 → `U`。 | valid 需同 failure type；属性不同最多 partial。 |
| **evidence assumption** | benign retrieval error; benchmark stressor; natural conflict; stale/low-quality; attacker-created; privacy/extraction | 自然矛盾 ≠ 攻击者矛盾；安全类记 corpus 写权限、query 控制、retriever 可见性、generator 访问、插入预算、目标。 | assumption 类别不同→多 `invalid`；攻击者能力缺失→封顶 `underspecified`。 |
| **intervention point** | corpus/index; retriever; reranker; context assembly/compression; generator prompt/train; verifier; system-control; evaluation-only | 编码第一个改变系统行为的组件。 | 同 failure 但作用点不同→`partial`（除非显式研究组合）。 |
| **metric target** | answer correctness; retrieval recall; evidence support; citation faithfulness; attack success; calibration; selective risk/coverage; cost; human preference | 仅当衡量同一目标对象时等价。 | 指标族不同→`partial`；目标冲突→单标量排序 `invalid`。 |
| **action policy** | answer; abstain; re-retrieve; filter; verify; expose conflict; clarify; escalate; quarantine; recover; unreported | action 必须显式陈述或评估，不得从任务设置推断。 | action 未报告→封顶 `underspecified`；显式 action 不同→`partial`。 |

> 裁决保守：任一必需坐标为 `U`，即便两篇很像也不能给 `valid`。

---

## 4. 独立盲审 rubric（B4：检验循环性的关键，单独发给独立面板）

独立面板**只拿到 pair（query / 两篇论文）和下面这套朴素 rubric**，**不接触五坐标、坐标 codebook、坐标金标准、两臂答案**。
rubric 故意从**下游后果**出发，且**禁止出现 failure / assumption / intervention / metric / action 等词**：

> 「如果有人把这两篇的主结果并排，得出‘其中一个方法更好’的结论，这个结论有多大风险？」
> - `low_risk`：基本没风险，可以直接比。
> - `some_risk`：有一定风险，需加保留条件。
> - `high_risk`：很可能被误导，不该直接比。
> - `unclear`：信息不足，无法判断。
> 再写**一句口语化理由**（不得使用上述受控术语）。

分析时映射：`low_risk→valid, some_risk→partial, high_risk→invalid, unclear→underspecified`。
用**这套独立面板**的金标准重新计算 protocol vs control 增益。

> 与第一轮的差别（务必做到）：独立判定**由不同的人、在不看坐标的情况下**完成，因此**不会**像上一轮那样与坐标金标准 1:1 重合；只有这样才能真正检验“增益是否只是定义性循环”。

---

## 5. 标注流程（顺序很重要）

1. **校准轮（所有人）**：先标 6–8 个公开练习对（取自第一轮，附参考），对齐理解、讨论分歧，再正式开始。
2. **Protocol 组**：逐对走五坐标 → 给 verdict + `breaking_coordinates`（如 `intervention;action`）+ 1–3 句 rationale。
3. **Control 组**：仅凭专家判断给 verdict + rationale（不强制 breaking coordinates）。
4. **坐标金标准面板**：独立完成（不看两臂答案），给五坐标 gold verdict + rationale + `what_valid_comparison_requires`。
5. **独立盲审面板**：**单独发包**，只用第 4 节 rubric，**全程不接触五坐标任何材料**。
6. 协调员回收 → 生成两套金标准 consensus → 运行分析。

每名标注者判断**全部 48 对**；pair 顺序对每人随机化；三类面板/两臂互不可见彼此答案。

---

## 6. 盲化与质量控制

- **盲化**：两臂不看任何金标准；坐标金标准不看两臂；**独立面板不看坐标材料/坐标金标准**；隐藏 key 只给协调员。
- **IAA 目标**：坐标金标准 Fleiss $\kappa \ge 0.6$；独立面板内部也报 Fleiss $\kappa$（衡量朴素 rubric 的可重复性）。
- **裁决**：各面板分歧由协调员按多数票 + 讨论裁决，记录 `panel_vote_counts`。
- **样本偏斜检查**：本轮目标是平衡四类；回收后核对金标准实际分布，避免再次像第一轮那样塌成单一类别（若坐标金标准把多数 valid 又判成 invalid，需复核 rubric 是否过严）。

---

## 7. 产出文件（CSV 列）

- `participant_responses.csv`：
  `participant_id, condition(protocol/control), pair_id, verdict, confidence_1_5, decision_time_seconds, failure_type, evidence_assumption, intervention_point, metric_target, action_policy, breaking_coordinates, rationale`
- `coordinate_gold_consensus.csv`：
  `pair_id, gold_verdict, gold_confidence_1_5, breaking_coordinates, gold_rationale, what_valid_comparison_requires, panel_vote_counts`
- `independent_gold_consensus.csv`（B4，独立面板）：
  `pair_id, rubric_label(low_risk/some_risk/high_risk/unclear), mapped_verdict, rubric_rationale, panel_vote_counts`
- `annotator_metadata_anonymized.csv`：`participant_id, role(control/protocol/coordinate_gold/independent_gold), qualification_record_public`

---

## 8. 分析与论文应报告

1. **per-class 准确率**：control vs protocol 在 **valid** 与 **under-specified** 两类上的一致率（本轮新增的承重证据）。
2. 平衡准确率 + Cohen's $\kappa$（对坐标金标准），与第一轮口径一致。
3. **循环性检验**：protocol−control 增益在**独立盲审金标准**下是否仍成立；报告独立金标准与坐标金标准的一致程度（这次**不应**再是 1:1）。
4. 坐标金标准与独立面板各自的 Fleiss $\kappa$、裁决分歧分析。

---

## 9. 诚实底线（务必遵守）

- 若 protocol 在 valid / under-specified 上**没有改进**，照实写“仅对 partial/invalid 有效”，不得粉饰。
- 若独立盲审金标准下增益消失，照实写“增益部分是定义性的，循环性未能排除”。
- 凡真人判断字段**只能真人填写**，不得用模型代填后冒充人工。
- 独立面板一旦接触过五坐标材料，本轮 B4 即作废，需换人重做。

---

*协调员可让我接着生成：① 从 Map B 抽取的 `valid` / `under-specified` 候选 pair 清单；② 四类面板的 CSV 模板与发包 zip 结构；③ 回收后的分析脚本（per-class、平衡准确率、独立金标准增益）。*
