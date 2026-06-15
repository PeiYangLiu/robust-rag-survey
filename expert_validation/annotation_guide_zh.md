# Robust RAG comparability protocol 专家标注说明

## 目标

这次专家标注不是让专家判断哪篇论文更好，而是判断两篇 robust RAG 论文是否可以被直接比较。

核心问题是：如果两篇论文都说自己处理 noise / conflict / poisoning / calibration / abstention，它们是否真的在同一个 failure assumption、intervention point、metric target 和 action policy 下回答同一个问题？

## 实验分组

建议采用两个条件：

1. **Control 组**
   - 发给专家：
     - `instructions_control.txt`
     - `paper_pairs_for_annotation.csv`
     - `participant_response_template_control.csv`
   - 专家用自己的领域判断决定 verdict。
   - 不给五元组 protocol。

2. **Protocol 组**
   - 发给专家：
     - `instructions_protocol.txt`
     - `paper_pairs_for_annotation.csv`
     - `participant_response_template_protocol.csv`
   - 专家必须按五元组标注：
     - failure type
     - evidence assumption
     - intervention point
     - metric target
     - action policy

**不要把 `paper_pairs.csv` 发给专家。** 这个文件包含内部参考 verdict，会泄露答案。

## 专家需要标什么

每一行是一个 paper pair。专家需要判断这个 pair 的比较 verdict：

- `valid`：两篇论文可以作为同一 robust-RAG 问题下的直接竞争方法比较。
- `partial`：两篇论文相关，但 intervention、metric、action 等不同，只能作为互补模块/不同 operating regions 比较。
- `invalid`：两篇论文的 assumption 或 objective 不同，直接 ranking 会误导。
- `under-specified`：论文信息不足，无法判断；尤其是 action policy 没有显式报告时，应倾向 under-specified。

## Protocol 组五元组规则

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

如果是安全论文，还要看是否报告：

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

关键规则：**action policy 不能从普通 QA setup 里默认推断。** 如果论文没有显式说明或评测 action policy，则不能给 `valid`，通常应标成 `under-specified`。

## 推荐组织流程

1. 给每位专家分配匿名 ID，例如 `E01`, `E02`。
2. 随机分配到 control 或 protocol 组。
3. 每组只发对应 instruction 和 response template。
4. 所有专家使用同一个 `paper_pairs_for_annotation.csv`。
5. 最好同时发论文 PDF 或官方链接，避免专家只凭标题判断。
6. 专家独立标注，不要互相讨论。
7. 收齐后合并成 `responses.csv`。
8. 运行：

```bash
python3 analyze_expert_validation.py responses.csv paper_pairs.csv
```

## 最低样本建议

- 最小 pilot：4--6 位独立专家，12 个 paper pairs。
- 更强的 EACL 版本：8--12 位专家，control/protocol 平衡分组。
- 最理想：专家来自 RAG、IR、NLP、安全方向，且没有参与本文 codebook 设计。

## 论文里可以报告的指标

收集完成后可以报告：

- control vs protocol 的 verdict agreement
- Fleiss kappa / Cohen kappa
- 与 external adjudicated gold 的一致率
- 平均 decision time
- 平均 confidence
- usefulness score
- error type 分布
- rationale quality

注意：如果没有独立 external gold，只能报告与 rulebook expected verdict 的一致性，不能声称是 external validity。
