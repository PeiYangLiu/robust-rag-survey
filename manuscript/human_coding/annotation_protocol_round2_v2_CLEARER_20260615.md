# 第二轮重标手册 v2.1（更清晰版 + 修正 pair 构造）——valid / under-specified 验证 + 独立金标准

> **本文件取代上一版 round2 文档，重标时只用这一份。**
> 上一轮失败表现为**标注塌缩**：金标准把 48 对全判成 invalid/partial（0 valid、0 under-specified），独立面板把 48 对全判 high_risk。
> **真正根因不是标注者，而是 pair 构造太保守**：从任意真实论文对里硬分类，而真实论文几乎总在某个坐标上有差异，严格 codebook 于是把一切判成 invalid。
> 本版的核心改动是 **§6 重写 pair 构造（每个 pair 必须是其目标类别的“清晰实例”）**，外加：决策树 + 四类正例 + 带答案的校准轮 + 协调员防塌缩检查 + 更平衡的独立 rubric。

---

## 0. 上一轮为什么要重标（先读，避免重蹈覆辙）

| 失败现象 | 真正原因 | v2.1 的修法 |
|---|---|---|
| 金标准 0 个 `valid` | **pair 构造太保守**：valid 候选其实在某坐标上有差异，严格 codebook 必判非 valid | **§6 重写构造**：valid 用同-benchmark/同-metric/同-action 的清晰对（如同一排行榜两条目） |
| 金标准 0 个 `under-specified` | 没有真正“缺坐标”的 pair，且与 invalid 混淆 | §6 故意配“真的省略必需坐标”的论文 + §2 第 1 步先查缺失 + §3 正例 |
| 独立面板 48/48 全 high_risk | rubric 偏向“风险”，缺低风险锚点；且样本本身偏向不可比 | §4 改成对称“**能不能排名**”四档 + 锚点 + §6 平衡构造 |

**核心心法（两条）**：
1. **构造端**：每个 pair 必须是其目标类别的**一眼可判的清晰实例**（§6）。模糊/borderline 的不要用——否则严格 codebook 必然把它推向 invalid，结果再次塌缩。
2. **标注端**：本轮样本四类各约 12 对；如果你判完 48 对却**一个 `valid` 或一个 `under-specified` 都没用过，几乎可以肯定判错了**，重读 §2–§3。

---

## 1. 人员与分工（与上一轮同，强调互不重叠 + 盲化）

| 角色 | 推荐 | 最小 | 约束 |
|---|---:|---:|---|
| Control 标注者 | 6 | 5 | 不给五坐标，仅普通判断 |
| Protocol 标注者 | 6 | 5 | 用五坐标决策树 |
| 坐标金标准面板 | 5 | 3 | 用五坐标决策树定 gold |
| 独立盲审面板 | 5 | 3 | 只用 §4 rubric，**绝不接触五坐标/坐标金标准/两臂答案** |
| Coordinator | 1 | 1 | 发包、盲化、防塌缩检查、裁决、分析 |

互不重叠；pair 顺序对每人随机化；三类面板/两臂互不可见彼此答案。

---

## 2. 裁决决策树（Protocol 组 + 坐标金标准面板必用，按顺序走）

> 必须**按 1→2→3→4 的顺序**判，第一个命中的就是裁决。

**第 1 步（先查缺失坐标）**：两篇里，是否有**任一必需坐标无法从论文中得到**？
最常见：① **action 未报告**（没说系统该 answer / abstain / re-retrieve…）；② 安全类**未交代 attacker capability**（corpus 写权限、插入预算、目标）。
→ 只要缺一个必需坐标 → **`under-specified`**（停，不要再往下）。

**第 2 步（是不是同一个“游戏”）**：两篇的 **failure type** 和 **evidence assumption** 是否相同？
注意：自然矛盾 ≠ 攻击者制造的矛盾；benign 噪声 ≠ 对抗投毒。
→ 若**不同游戏**（不同失败属性 / 不同威胁模型 / 不同目标）→ **`invalid`**（停）。

**第 3 步（五坐标是否全对齐）**：在同一个游戏内，**intervention point、metric target、action policy 是否都对齐到“同一个指标在回答同一个问题”**？
→ 若**全对齐** → **`valid`**。
（valid **不要求两篇方法相同**，只要求五坐标对齐到可以放进同一张排行榜。）

**第 4 步**：同一个游戏，但 intervention / metric / action 有**非致命错配** → **`partial`**。

> 一句话区分易混项：
> - **invalid vs under-specified**：坐标都在但**冲突** = invalid；某个必需坐标**缺失/读不到** = under-specified。
> - **valid vs partial**：五坐标**全对齐** = valid；同游戏但作用点/指标/动作**有一处错配** = partial。

---

## 3. 四类裁决的正例（务必照着找感觉，尤其 valid 和 under-specified）

**`valid`（可直接比，约占 1/4，别漏判）**
> A、B 都在固定 generator 前加一个 reranker，都在 Natural Questions 上用 Exact Match、同一 DPR retriever、top-5、都 answer-only（不弃答），只是 reranker 结构不同。
> → 同 failure(噪声)、同 assumption(benign 检索)、同 intervention(reranker)、同 metric(EM)、同 action(answer)，五坐标全对齐 → 可放同一排行榜 → **valid**。

**`partial`（同游戏、有非致命错配）**
> A 先过滤无关段再回答、并带弃答兜底；B 对 generator 做对抗训练、总是回答。两者都针对噪声检索的 QA 准确率。
> → 同 failure，但 intervention(过滤 vs 训练)、action(可弃答 vs 只回答)不同 → 互补不可排名 → **partial**。

**`invalid`（不同游戏）**
> A 研究自然冲突来源如何调和；B 防御攻击者注入的投毒文档。两者都涉及“检索到相互矛盾的文本”。
> → evidence assumption 不同（benign 冲突 vs 对抗完整性）→ 直接比是张冠李戴 → **invalid**。

**`under-specified`（必需坐标缺失，约占 1/4，别漏判）**
> 例 1：A 报告其 RAG 防御把 attack-success 降低了，但**从不交代攻击者的 corpus 写权限/插入预算**；B 在明确预算下报告。→ 缺 attacker capability → **under-specified**。
> 例 2：A 改进了置信度分数，但**没说系统到底是回答、弃答还是再检索**（action 未报告）→ 缺 action 坐标 → **under-specified**。

---

## 4. 独立盲审 rubric（独立面板专用，修“全判 high_risk”）

独立面板**只拿到 pair（query / 两篇论文）和下面这套朴素 rubric**，**不接触五坐标、坐标 codebook、坐标金标准、两臂答案**。
改成**“能不能给两个方法排名”**的对称四档（不再用偏向风险的措辞），并给每档锚点：

> 「假设你只能凭两篇报告的主结果，决定部署哪个方法。你处于哪种情况？」
>
> - `can_rank`：能有把握说哪个更好——两者用**同样的方式在同样的任务**上衡量。
>   *锚点：两篇都在 NQ 上报 Exact Match、设置一致 → 数字高的就是更好的。*
> - `rank_with_caveats`：能倾向一方，但**只能带保留**——目标接近但衡量/操作方式不完全一致。
>   *锚点：两篇都在噪声下提升 QA，但一篇会弃答、一篇不会 → 可倾向数字高者，但要加保留。*
> - `cannot_rank`：**无法排名**——两者在解**不同的问题**，一个数字高不代表它更好。
>   *锚点：一篇降低“被注入文档攻击者”的攻击成功率，另一篇调和自然冲突来源 → 不是一回事。*
> - `not_enough_info`：信息不足——至少一篇**没报够**关键信息，根本判不了。
>   *锚点：一篇没说攻击者多强，你无法判断它那个更低的攻击成功率是否可比。*
>
> 再写**一句口语化理由**（禁止出现 failure / assumption / intervention / metric / action 等词）。

映射：`can_rank→valid, rank_with_caveats→partial, cannot_rank→invalid, not_enough_info→under-specified`。

> **平衡提示（务必告知独立面板）**：这批配对是特意挑成四种情况都有的；如果你发现自己**几乎每对都选 `cannot_rank`**，请回去重读 `can_rank` 与 `rank_with_caveats` 的锚点——这通常说明标准用偏了。

---

## 5. 校准轮（**本版新增、必做**——这是修塌缩的关键）

正式标注**之前**，每个人（含两臂、两个面板）先做一轮校准：

1. 协调员发 **8 个练习对**，其中**至少 2 个 valid、2 个 under-specified、2 个 partial、2 个 invalid**（独立面板对应 can_rank/not_enough_info/rank_with_caveats/cannot_rank 各 2）。
2. 标注者先独立判这 8 个。
3. 协调员公布**练习对的标准答案 + 一句理由**，每人对照、讨论分歧。
4. 只有当标注者在校准轮**能正确判出至少 1 个 valid 和 1 个 under-specified**，才进入正式 48 对标注。

> 校准对可取自 §3 的四个正例 + 论文已有 pilot 难例，协调员补足到每类 2 个。

---

## 6. 样本集与 pair 构造（**本版核心：填一张表、机械读出类别**）

> 把构造**完全机械化**：为每个候选 pair 填下面这张 5×2 坐标表，再按固定规则读出类别。
> **填不出“五格全对齐”就不是 valid，换 pair——不要凭感觉。**

**Step 1：给候选 pair 填坐标表**（A / B 各一列；论文里读不到就写 `U`）：

| 坐标 | Paper A | Paper B |
|---|---|---|
| failure type | … | … |
| evidence assumption | … | … |
| intervention point | … | … |
| metric target | … | … |
| action policy | … | … |

**Step 2：按规则机械读出 `expected_verdict`**（从上到下，第一个命中即是）：
1. A 或 B 任一格 = `U`（未报告/读不到）→ **under-specified**
2. 否则 failure 或 assumption 两格不同 → **invalid**
3. 否则（failure + assumption 都相同）intervention、metric、action 三格**都相同** → **valid**
4. 否则（failure + assumption 相同，但后三格有 ≥1 不同）→ **partial**

**Step 3：四类各凑 12 个清晰 pair**（下面每类给：填好的样例表 + 去哪找）。

### 6.1 `valid` 样例（最难，务必逐格核对全同）
取材：从**同一 benchmark / 同一 shared task** 里挑两个用**同指标、同 retrieval 设置、同 action** 上报数的方法；或**同系统两个 ablation**；或 B 显式复刻 A 的 setup。
样例（两个 corpus-poisoning 防御，在**同一 PoisonedRAG 设置**上同口径上报，*前提是你逐格核对确实全同*）：

| 坐标 | A: ProGRank（probe-gradient rerank 防御） | B: 另一在同 setup 同口径报数的 rerank 防御 |
|---|---|---|
| failure | adversarial corruption | adversarial corruption |
| assumption | 攻击者注入文档，同 budget | 攻击者注入文档，同 budget |
| intervention | reranker | reranker |
| metric | attack-success-rate @ 同数据集 | attack-success-rate @ 同数据集 |
| action | answer | answer |

→ 五格全同 → **valid**。任一格不同就降级为 partial/invalid。

### 6.2 `partial` 样例（论文 P01，真实）
A: **IrrelCtx**；B: **RAAT**。

| 坐标 | A: IrrelCtx | B: RAAT |
|---|---|---|
| failure | noise/relevance | noise/relevance |
| assumption | benign 检索噪声 | benign + 反事实噪声 |
| intervention | NLI 过滤 + 微调 | 对抗训练（generator） |
| metric | NQ EM/F1 | EM/F1 |
| action | 过滤后答 + 弃答兜底 | 只回答 |

→ failure 同、assumption 大体同，但 intervention 与 action 不同 → **partial**。

### 6.3 `invalid` 样例（论文用例，真实）
A: **AstuteRAG/FaithfulRAG**（调和自然冲突）；B: **PoisonedRAG**（攻击者注入投毒文档）。

| 坐标 | A: 自然冲突调和 | B: PoisonedRAG |
|---|---|---|
| failure | knowledge conflict | adversarial corruption |
| assumption | 自然相互矛盾来源 | 攻击者注入文档 |

→ failure 与 assumption 都不同 → **invalid**（命中规则 2，无需再看后三格）。

### 6.4 `under-specified` 样例（关键是“缺”，不是“冲突”）
A: 一篇校准论文（如 **CalibRAG / UncertaintyRAG**）**其报告未说明系统是答 / 弃答 / 再检索**；B: **SuffCtx**（充分性→弃答）。

| 坐标 | A: 校准论文（action 未报告） | B: SuffCtx |
|---|---|---|
| failure | calibration/uncertainty | sufficiency |
| assumption | benign 不确定 | 证据可能不足 |
| intervention | 置信度校准 | 充分性判定 |
| metric | calibration error | selective risk |
| action | **U（未报告）** | abstain |

→ A 的 action 格 = `U` → **under-specified**（命中规则 1）。

### 6.5 取材配方与构造纪律
- **valid（12）**：同 benchmark 同指标同 action 的方法对（优先 RGB / 同 QA 榜 / 同 PoisonedRAG setup）或同系统 ablation。
- **under-specified（12）**：挑一篇**真的省略了 action、或 attacker capability、或 retriever/top-k/split** 的论文，与一篇可比的配。
- **invalid（12）**：跨 failure 或跨 assumption（自然冲突 vs 投毒、诊断 benchmark vs 方法、不同威胁模型）。
- **partial（12）**：同 failure + assumption，**只差** intervention / metric / action 之一。
- **纪律**：每个 pair 必须能把 5×2 表填满且**机械落到目标类别**；一眼填不清的 borderline 一律弃用。隐藏 key `coordinator_hidden_pair_key.csv` 保存**每对的坐标表 + `expected_verdict`**，供 §8 逐格核对。

> 需要的话我可从 Map B / 已有排行榜数据**按上面规则自动产出四类各 12 的候选 pair（含填好的坐标表）**供你定稿。

---

## 7. 标注流程

1. **校准轮**（§5，所有人，必过）。
2. **Protocol 组**：走 §2 决策树 → verdict + `breaking_coordinates` + 1–3 句 rationale。
3. **Control 组**：仅凭专家判断 → verdict + rationale。
4. **坐标金标准面板**：独立完成 → 五坐标 gold verdict + rationale + `what_valid_comparison_requires`。
5. **独立盲审面板**：单独发包，只用 §4 rubric，全程不接触五坐标材料。
6. 协调员回收 → §8 防塌缩检查 → 生成两套金标准 consensus → 分析。

---

## 8. 协调员防塌缩检查（**本版新增、回收时必做**）

1. **逐人类别使用检查**：对每个标注者统计 4 类裁决的使用次数。
   - 任何人**整套 48 对里 0 个 valid 或 0 个 under-specified** → 判定为**误读**，必须**重新培训后重标**（样本本就四类平衡）。
   - 任何人某一类占比 **>90%** → 复核 / 重标。
2. **金标准分布检查**：坐标金标准 consensus 若仍出现 0 个 valid 或 0 个 under-specified → **不要接受**，回到 §5 重新校准面板后重标。
3. **独立面板检查**：任何独立判者把 48 对判成**全同一档** → 用 §4 锚点重新培训后重标。
4. **与隐藏 key 对照**：金标准与 `expected_verdict` 的总体分布应大致吻合（不要求逐对一致，但不应整类消失）。

> 只有通过以上检查，本轮数据才算有效；否则按“标注有问题”处理、重标。

---

## 9. 产出文件（CSV 列）

- `participant_responses.csv`：`participant_id, condition, pair_id, verdict, confidence_1_5, decision_time_seconds, failure_type, evidence_assumption, intervention_point, metric_target, action_policy, breaking_coordinates, rationale`
- `coordinate_gold_consensus.csv`：`pair_id, gold_verdict, gold_confidence_1_5, breaking_coordinates, gold_rationale, what_valid_comparison_requires, panel_vote_counts`
- `independent_gold_consensus.csv`：`pair_id, rubric_label(can_rank/rank_with_caveats/cannot_rank/not_enough_info), mapped_verdict, rubric_rationale, panel_vote_counts`
- `annotator_metadata_anonymized.csv`：`participant_id, role, qualification_record_public`
- 校准记录：`calibration_responses.csv`（含 8 练习对的各人判定，用于证明已通过校准）。

---

## 10. 分析与论文应报告

1. **per-class 准确率**：control vs protocol 在 **valid**、**under-specified** 两类上的一致率（本轮的承重新证据）。
2. 平衡准确率 + Cohen's κ（对坐标金标准），与第一轮口径一致。
3. **循环性检验**：protocol−control 增益在**独立盲审金标准**下是否仍成立；报告独立金标准与坐标金标准的一致程度（应**有区分、但不是 1:1**）。
4. 两面板各自 Fleiss κ、裁决分歧分析、校准通过率。

---

## 11. 诚实底线

- 校准/防塌缩**不是为了把结果做成正面**，而是确保标注者**真的理解任务**；判定标准本身不得为了得到 valid 而放水。
- 若重标后金标准里 valid/under-specified **仍然极少**，那是**真实结论**（说明这类直接可比在该文献里确实罕见），照实报，不得伪造。
- 真人判断字段只能真人填写；独立面板一旦接触五坐标材料即作废、换人重做。
