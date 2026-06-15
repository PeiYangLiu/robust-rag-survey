# Robust RAG comparability protocol 独立 gold adjudication 标注说明

## 目标

这轮标注的目标是建立一个**独立外部 gold standard**，用于判断我们的 five-coordinate comparability protocol 是否真的让专家做出更正确的论文比较判断。

这不是重复上一轮 blind annotation。上一轮 30 人标注已经比较了 control vs protocol；这轮需要由更资深、独立的专家小组给出每个 paper pair 的最终 gold verdict 和 gold rationale。

核心问题：

> 两篇 robust RAG 论文是否可以被直接比较为同一个问题下的替代方法？

不是判断哪篇论文更好，而是判断直接比较 / leaderboard-style ranking 是否成立。

## 重要原则

1. **不要看任何 rulebook expected verdict。**
   - 不要使用 `expert_validation/paper_pairs.csv`。
   - 不要看上一轮 `expert_validation_blind_batch_A_20260605/` 的结果。
   - 本轮 gold panel 应独立判断。

2. **可以使用 five-coordinate protocol，但不要被作者原始答案约束。**
   - 如果 panel 认为某个 pair 的正确 verdict 与作者 rulebook 不同，应以 panel adjudication 为准。
   - 特别注意 P09 这类争议样本：如果专家一致认为 `partial` 比 `under-specified` 更合理，就应该把 gold 标成 `partial`。

3. **gold verdict 必须配 gold rationale。**
   - 只给 label 不够。
   - rationale 应说明哪个 coordinate 断裂，为什么。

4. **优先判定 comparability，而不是方法优劣。**
   - 不需要判断哪个系统性能更好。
   - 需要判断能否直接作为同一 leaderboard 上的替代方法比较。

## 推荐流程

### Phase 1：独立个人标注

每位 gold adjudicator 独立填写：

`gold_individual_annotation_template.csv`

输入文件：

`paper_pairs_for_gold_adjudication.csv`

每个 pair 需要填写：

- `individual_verdict`
- `confidence_1_5`
- five-coordinate coding
- `breaking_coordinates`
- `gold_rationale_candidate`
- `what_valid_comparison_requires`
- optional notes

### Phase 2：panel adjudication

3--5 位 adjudicators 开会或异步讨论 disagreement，最后填写：

`gold_panel_adjudication_template.csv`

每个 pair 需要给出：

- `final_gold_verdict`
- `final_gold_rationale`
- `final_breaking_coordinates`
- `what_valid_comparison_requires`
- `disagreement_summary`
- `rulebook_revision_needed`

### Phase 3：更新分析

把 `final_gold_verdict` 填回主分析文件中的 `external_gold_verdict` 字段，然后重新跑分析。

最终论文可报告：

- control vs protocol agreement with independent gold
- macro-F1 against independent gold
- Cohen/Fleiss kappa
- error reduction
- rationale quality
- disagreement cases and rulebook revisions

## Verdict 定义

| Verdict | 含义 |
| --- | --- |
| `valid` | 两篇论文可以作为同一 robust-RAG 问题下的替代方法直接比较。leaderboard-style comparison 有意义。 |
| `partial` | 两篇论文相关，但 intervention、metric、action、assumption 等有非致命差异。应作为互补模块、不同 operating region 或部分重叠来讨论，而不是直接排名。 |
| `invalid` | 两篇论文的问题设定或 assumption 不兼容，直接比较会误导。 |
| `under-specified` | 信息不足，无法可靠判断；例如 action policy、attacker capability、metric target 或 evidence assumption 缺失。 |

## Five-coordinate protocol

### 1. Failure type

可选：

- `relevance/noise`
- `sufficiency`
- `consistency/conflict`
- `provenance/freshness`
- `integrity/adversarial corruption`
- `uncertainty/OOD`

### 2. Evidence assumption

可选：

- `benign retrieval error`
- `benchmark-constructed stressor`
- `naturally occurring conflict`
- `stale or low-quality source`
- `attacker-created evidence`
- `privacy or extraction threat`

安全相关 pair 还需要判断：

- corpus write access
- query control
- retriever visibility
- generator access
- insertion budget
- attack objective

### 3. Intervention point

可选：

- `corpus/index`
- `retriever`
- `reranker`
- `context assembly/compression`
- `generator prompting or training`
- `verifier`
- `system-control policy`
- `evaluation artifact`

### 4. Metric target

可选：

- `answer correctness`
- `retrieval recall`
- `evidence support`
- `citation faithfulness`
- `attack success`
- `calibration error`
- `selective risk/coverage`
- `cost/latency`
- `human preference`

### 5. Action policy

可选：

- `answer`
- `abstain`
- `re-retrieve`
- `filter`
- `verify`
- `expose conflict`
- `ask clarification`
- `escalate`
- `quarantine`
- `recover`
- `unreported`

关键规则：

> action policy 不能从普通 QA setup 中默认推断。若论文没有显式说明或评测 action policy，则通常不能给 `valid`。

但 gold panel 可以判断是否应为 `partial` 还是 `under-specified`：

- 如果 action policy 缺失但其他坐标足以判断两者是互补/不同机制，可给 `partial`。
- 如果 action policy 或 threat model 缺失导致无法判断比较对象，可给 `under-specified`。

## 如何写 gold rationale

一个好的 gold rationale 应包含：

1. 两篇论文共同点是什么。
2. 哪些坐标不同。
3. 为什么这些差异导致 `valid` / `partial` / `invalid` / `under-specified`。
4. 如果要让比较变成 valid，需要补什么实验或报告什么信息。

示例格式：

> Both papers address retrieved-evidence noise, but Paper A evaluates generator sensitivity to irrelevant contexts while Paper B trains against adversarially constructed retrieval noise. The failure type overlaps, but the intervention point and metric target differ, and neither evaluates the same action policy. Therefore the comparison is partial rather than valid. A valid comparison would require the same retriever, generator, noise construction, metric family, and explicit action labels.

## 推荐样本与角色

最低要求：

- 3 位 independent gold adjudicators
- 每人独立标 12 个 pairs
- panel 最终 adjudicate 12 个 final gold verdicts

更强版本：

- 5 位 adjudicators
- 至少 2 位 RAG/NLP，1 位 IR，1 位 security/trustworthy ML
- 对 disagreement 做书面 adjudication rationale

## 不要发给 gold panel 的文件

不要发：

- `expert_validation/paper_pairs.csv`
- `expert_validation_blind_batch_A_20260605/responses.csv`
- `expert_validation_blind_batch_A_20260605/analysis_summary.md`
- 任何包含 rulebook expected verdict 或上一轮 annotator 分布的文件

可以发：

- `paper_pairs_for_gold_adjudication.csv`
- 本说明文件
- 论文 PDF 或官方链接
- `gold_individual_annotation_template.csv`
- `gold_panel_adjudication_template.csv`

