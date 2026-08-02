# 大修标注手册（EACL 2027 major revision）

> 目的：为回应审稿意见而新增的人工标注轮次提供一份**可直接发给标注者**的操作手册，
> 写明每项任务**具体怎么标、用什么量表、需要多少人、产出什么文件**。
> 本手册沿用论文现有量表（五坐标 + 四裁决 codebook），数值口径与 `comparability_user_study_package/` 一致。
>
> 协调员（Coordinator，可由你自己担任）负责发包、回收、盲化、裁决与分析；**协调员包不要发给普通标注者**。

---

## 0. 这轮要解决的审稿问题（对照表）

| 审稿点 | 现状不足 | 本轮如何修 | 对应任务 |
|---|---|---|---|
| 每臂只有 3 名标注者（n=3 硬伤） | control/protocol 各 3 人 | 每臂扩到 **≥6 人** | 任务一 |
| valid / under-specified 两类从未被人验证 | 金标准只含 partial/invalid | 样本集**补足四类裁决**并入金标准 | 任务一 |
| 定义性循环（量表与金标准共享坐标） | 金标准用同一套五坐标 | 金标准额外用**一套不共享坐标词汇的独立 rubric** 复测增益 | 任务一（独立 rubric） |
| 承重引用全由 LLM 审计 | 292 条核对均为 Claude Opus 4.7 | 对**承重引用做人工 full-text 核验**并标 `human-verified` | 任务二 |

---

## 1. 任务总览与总人数

| 任务 | 角色 | 推荐人数 | 最小可行 |
|---|---|---:|---:|
| 任务一 可比性裁决验证 | Control 标注者 | 6 | 5 |
| | Protocol 标注者 | 6 | 5 |
| | Gold 金标准评审 | 5 | 3 |
| 任务二 承重引用人工核验 | 引用核验者 | 2 | 2 |
| | 核验裁决者 | 1 | 1（可由 Gold 评审兼任） |
| 协调员 | Coordinator | 1（可你自己） | 1 |

- **推荐总计：约 17–20 名不同标注者 + 1 名协调员。**
- **最小可行：15 人**（任务一 5+5+3，任务二 2 人；裁决者复用 Gold 评审）。
- 硬性约束：**三组（Control / Protocol / Gold）人员必须互不重叠**；任务二核验者最好独立于任务一 arm 标注者。
- 资质：能独立阅读 RAG / 检索 / NLP 论文的研究者（博士生或以上）；英语阅读流利；了解 retrieval、faithfulness、calibration、poisoning 等基本概念。Gold 评审与裁决者应更资深。

---

## 2. 通用量表（所有任务一标注者必读）

每个 pair 的**最终裁决只能是四选一**：

| verdict | 含义 |
|---|---|
| `valid` | 五坐标全部对齐，可直接比较 / 排序。 |
| `partial` | 同属一个问题族，但 intervention / metric / action 有非致命错配，只能局部比较或互补，不能直接排序。 |
| `invalid` | assumption 或 objective 定义了不同的“科学游戏”，直接比较会得出错误结论。 |
| `underspecified` | 至少一个必需坐标无法从论文中获得（记为 `U`），信息不足无法判断。 |

**Protocol 组**必须按下表五坐标逐项判断（Control 组不给此表，仅凭普通专家判断）：

| 坐标 | 受控取值 | 等价 / 边界规则 | 对裁决的影响 |
|---|---|---|---|
| **failure type** | relevance/noise; sufficiency; consistency/conflict; provenance/freshness; integrity/adversarial; uncertainty/OOD | 编码“被测试的证据属性”，不是论文动机。只说 robustness 而无证据属性 → 记 `U`。 | valid 要求 failure type 相同；同领域但属性不同最多 partial。 |
| **evidence assumption** | benign retrieval error; benchmark-constructed stressor; naturally occurring conflict; stale/low-quality source; attacker-created evidence; privacy/extraction | 自然矛盾 ≠ 攻击者制造的矛盾（即便文本相似）。安全类要记 corpus 写权限、query 控制、retriever 可见性、generator 访问、插入预算、攻击目标。 | assumption 类别不同通常使排行榜比较 `invalid`；攻击者能力缺失则封顶为 `underspecified`。 |
| **intervention point** | corpus/index; retriever; reranker; context assembly/compression; generator prompt/train; verifier; system-control policy; evaluation-only | 编码“第一个改变系统行为的组件”。同 failure 但作用点不同 → 按流水线组件比较，不是替代品。 | 同 failure 但作用点不同 → `partial`（除非论文显式研究组合）。 |
| **metric target** | answer correctness; retrieval recall; evidence support; citation faithfulness; attack success; calibration error; selective risk/coverage; cost/latency; human preference | 仅当衡量“同一目标对象”时指标才等价。同一数据集上 answer correctness、citation support、attack success 互不可换。 | 指标族不同 → `partial`；目标对象冲突 → 单标量排序 `invalid`。 |
| **action policy** | answer; abstain; re-retrieve; filter; verify; expose conflict; clarify; escalate; quarantine; recover; unreported | action 必须被**显式陈述或评估**，不得从任务设置推断。 | action 未报告 → 封顶 `underspecified`；同 failure 但显式 action 不同 → `partial`。 |

> 裁决是**保守**的：只要有一个必需坐标为 `U`，即便两篇看起来很像，也不能给 `valid`。

---

## 3. 任务一：可比性裁决验证（修 B2 + B3 + B4）

### 3.1 样本集（协调员在标注前准备好）

- **目标规模：约 72 对，四类裁决各 ~18 对**（valid / partial / invalid / underspecified 平衡）。
- 复用现有 60 对难样本（多为 partial/invalid）作为子集；**新增 ≥15 对 valid + ≥15 对 underspecified** 以覆盖此前未验证的两类。
  - `valid` 候选：找两篇 failure/assumption/intervention/metric/action **真正全对齐**、可直接比的论文（例如同 benchmark、同指标、同 action 的两个方法）。
  - `underspecified` 候选：至少有一篇缺失 action 或 attacker capability 等必需坐标。
- 每对提供给标注者的字段（沿用 `paper_pairs_for_annotation.csv`）：
  `pair_id, area, paper_a_key, paper_a_title, paper_b_key, paper_b_title`
  （可附两篇的 abstract / 关键段落链接；**不要泄露期望裁决**）。
- 协调员另存一份**隐藏 key**（`coordinator_hidden_pair_key.csv`，含 `expected_verdict`），只供分析，不发给任何标注者。

### 3.2 三组分工与人数

| 组 | 人数（推荐/最小） | 看什么 | 填什么 |
|---|---:|---|---|
| **Protocol** | 6 / 5 | 第 2 节五坐标量表 + 校准例子 | 每对填五坐标判断 + verdict + breaking_coordinates + rationale |
| **Control** | 6 / 5 | **不给**五坐标量表，仅普通专家判断 | 每对填 verdict + rationale |
| **Gold** | 5 / 3（奇数，独立） | 五坐标量表 + **独立 rubric（见 3.4）** | 每对填 gold verdict + 独立 rubric 判断 + rationale |

- 每名标注者判断**全部 72 对**。每臂判断数 = 人数 × 72（如 6×72 = 432）。
- 三组**互不可见彼此答案**；pair 顺序对每人**随机化**。

### 3.3 标注步骤

1. **校准轮（所有人，正式标注前）**：先标 6–8 个公开练习对（取自旧 pilot，附参考答案），对齐理解、讨论分歧，再开始正式标注。
2. **Protocol 组**：逐对走五坐标 → 任一坐标致命错配/缺失即按规则封顶 → 给 verdict；`breaking_coordinates` 填如 `intervention;action`；rationale 写 1–3 句。
3. **Control 组**：仅凭专家判断给 verdict + rationale，不强制填 breaking coordinates。
4. **Gold 组**：独立完成（不看 arm 答案），先给五坐标 gold verdict，再**额外**完成 3.4 的独立 rubric。
5. 协调员回收后合并、生成 panel consensus、运行分析。

### 3.4 独立 rubric（修“定义性循环” B4）

Gold 评审对每对**再做一次判断**，使用一套**完全不含五坐标词汇**的朴素 rubric（禁止出现 failure/assumption/intervention/metric/action 等词）：

> 「如果把这两篇的主结果放进同一张排行榜直接比较，实践者会不会被误导？」
> - `safe`：不会，可直接比。
> - `partly`：会部分误导。
> - `misleading`：会严重误导，不该直接比。
> - `cant_tell`：信息不足，无法判断。
> 另写一句**口语化理由**（不得使用上述受控术语）。

分析时映射：`safe→valid, partly→partial, misleading→invalid, cant_tell→underspecified`，
用**这套独立金标准**重新计算 protocol vs control 的一致性增益。
若在不共享词汇的金标准下 protocol 仍有增益 → 说明增益不是纯定义性的。

### 3.5 质量控制与盲化

- 盲化：Gold 不看 arm 答案；arm 不看 Gold；隐藏 key 只给协调员。
- IAA 目标：Gold panel **Fleiss κ ≥ 0.6**（对齐现有 0.772）；arm 内不强求高一致（本就是要测协议差异）。
- 裁决：Gold 分歧由协调员按**多数票 + 讨论**裁决，记录 `panel_vote_counts`。

### 3.6 产出文件（CSV 列）

- `participant_responses.csv`：
  `participant_id, condition(protocol/control), pair_id, verdict, confidence_1_5, decision_time_seconds, usefulness_1_5, failure_type, evidence_assumption, intervention_point, metric_target, action_policy, breaking_coordinates, rationale`
- `gold_panel_consensus.csv`：
  `pair_id, gold_verdict, gold_confidence_1_5, breaking_coordinates, gold_rationale, what_valid_comparison_requires, panel_vote_counts, independent_rubric_label, independent_rubric_rationale`
- `annotator_metadata_anonymized.csv`：`participant_id, condition, anonymized_role, qualification_record_public`

### 3.7 论文应报告

protocol/control 各人数与判断数、Gold 人数与 inter-gold κ、**四类裁决各自**的 protocol vs control 一致性、独立 rubric 下的增益、per-coordinate 错误分类、clustered bootstrap CI。

---

## 4. 任务二：承重引用人工 full-text 核验（修 B5）

### 4.1 范围（承重引用）

只核验**承重层**，不必核全部 259 条证据图引用：
1. 框架/导言的 **33 条 strict-claim**（见 `citation_audit/strict_claim_audit_report.csv` 的 `claim_being_supported` + `key`）；
2. **5 个重分析行**（`tables/main_worked_examples`）点名的论文；
3. **6 条渠道结论**（venue-linked）所依据的引用。
- 预计 ~40–60 篇去重论文。协调员先导出 `citation_verification_worklist.csv`：
  `claim_id, manuscript_claim_text, cited_key, cited_title, pdf_path`。

### 4.2 人数与分工

- **2 名引用核验者**（独立、互不可见）逐条核验全部条目；
- **1 名裁决者**处理两人分歧（可由任务一 Gold 评审兼任）。

### 4.3 步骤与判定

对每条 `(manuscript_claim, cited_paper)`：
1. 读被引论文**全文**（至少定位到相关 section）；
2. 给判定：`fully_supported / partially_supported / not_supported / cant_tell`；
3. 记录**一句支持性引文 + 出处**（section 或 page）；
4. 若有 overclaim / 错引 / 部分支持，写明问题与建议改法。

判定标准：
- `fully_supported`：原文明确支持该 claim 的全部断言。
- `partially_supported`：支持主旨但有范围/条件差异（需记差异）。
- `not_supported` / `cant_tell`：原文不支持或无法定位 → **必须**反馈给协调员改写或换引。

### 4.4 产出与“human-verified”标记规则

- `citation_verification_results.csv`：
  `claim_id, cited_key, verifier_id, verdict, evidence_quote, evidence_location, problem_if_any, suggested_fix`
- 仅当**两名核验者一致（或经裁决）为 `fully_supported`** 时，该引用在 release / 表中标 `human-verified`；
  与 LLM 审计列**分开**呈现，绝不混淆。
- 任何 `not_supported` 必须在正文/表中改写或替换后才能保留。

---

## 5. 资质、伦理与报酬（对齐论文 Ethics Statement）

- 任务对象是**已公开发表的论文**，不涉及标注者个人敏感信息，最小风险。
- 自愿参与 + 知情同意：告知研究目的、流程、匿名判断的发布用途。
- 报酬不低于当地专家标注时薪。
- 公开物只保留**匿名 ID + 判断**；标注者身份与资历不发布。

---

## 6. 时间与工作量估算（单人）

| 任务 | 单位工作量 | 总量（单人） |
|---|---|---|
| 任务一 arm/Gold 标注 | ~2 分钟/对 | 72 对 ≈ 2.5 小时（建议分 2 次） |
| 任务一校准轮 | ~30 分钟 | 一次 |
| 任务二引用核验 | ~12 分钟/篇 | ~50 篇 ≈ 10 小时（建议分多次） |

---

## 7. 重要提醒（诚实底线）

- **若 protocol 组没赢，不要硬写成 protocol validation。** 可改写为：
  > The protocol improves auditability of disagreement by making coordinate-level errors explicit, but it does not necessarily improve raw verdict accuracy without additional training or clearer gold construction.
- 任务二中任何**未通过人工核验**的承重引用，必须先改写/替换，**不得**标 `human-verified`。
- 凡是真人判断的字段，**只能由真人填写**；不得用模型代填后冒充人工。

---

*协调员可让我接着生成：① 任务一的候选 pair 清单与各组 CSV 模板 / 发包 zip 结构；② 任务二的 `citation_verification_worklist.csv`（从 `citation_audit/` 自动抽取承重引用）。*
