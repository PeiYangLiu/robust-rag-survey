# Robust RAG Evidence274 Round2 最终裁决说明

这份文档给 **最终 adjudicator / 裁决标注人员** 使用。

当前状态：

- 两名人工 coder 已经独立完成 274 篇 evidence-map 论文的 round2 标注；
- IAA 已经计算完成，主要字段一致性很高；
- 现在只需要裁决两名 coder 不一致的行；
- 不需要重新标 274 篇。

## 1. 你需要编辑哪个文件

主工作文件：

```text
robust-rag-survey/manuscript/human_coding/human_round2_evidence274_results/adjudication_template_evidence274_round2.csv
```

请在这个文件中填写：

```text
human_final_label
human_adjudication_reason
```

不要修改：

```text
paper_id
title
field
source_01_label
source_02_label
url
```

完成后另存为：

```text
robust-rag-survey/manuscript/human_coding/human_round2_evidence274_results/adjudication_log_evidence274_round2_final.csv
```

## 2. Round2 当前一致性结果

这轮人工双标质量已经很好，剩下是少量分歧裁决。

| Field | Agreement | Kappa / Score | Disagreements |
|---|---:|---:|---:|
| full_text_checked | 100.0% | 1.00 | 0 |
| screen_in_scope | 99.6% | 0.92 | 1 |
| primary_failure_type | 97.1% | 0.96 | 8 |
| method_family | 89.4% | 0.86 | 29 |
| intervention_point | 93.4% | 0.92 | 18 |
| evaluation_type | 94.9% | 0.93 | 14 |
| evidence_strength | 97.8% | 0.95 | 6 |
| relevance_level | -- | weighted 0.80 | 26 |
| is_core_candidate | 91.6% | 0.80 | 23 |
| include_in_evidence_map | 99.3% | 0.85 | 2 |
| secondary_failure_types | 79.2% exact | Jaccard 0.83 | 57 |

## 3. 裁决优先级

请优先裁决影响论文统计和 evidence map 的字段：

1. `screen_in_scope`
2. `include_in_evidence_map`
3. `primary_failure_type`
4. `method_family`
5. `intervention_point`
6. `evaluation_type`
7. `evidence_strength`
8. `relevance_level`
9. `is_core_candidate`
10. `secondary_failure_types`
11. `exclusion_reason`
12. `reproducibility_evidence`
13. `confidence_1_to_5`

如果时间有限，至少完成前 10 类字段。`reproducibility_evidence` 和 `confidence_1_to_5` 对主文核心统计影响较小，可以最后处理。

## 4. 每一行怎么填

每一行代表一个 disagreement：

```text
paper_id,title,field,source_01_label,source_02_label,human_final_label,human_adjudication_reason,url
```

你需要：

1. 看 `paper_id`、`title`、`url`；
2. 打开论文全文或关键部分；
3. 看 `field` 是哪个字段；
4. 比较 `source_01_label` 和 `source_02_label`；
5. 决定最终标签，填入 `human_final_label`；
6. 给出裁决原因，填入 `human_adjudication_reason`。

示例：

```text
field = primary_failure_type
source_01_label = noisy_retrieval
source_02_label = distraction
```

如果论文主要研究 retriever 返回坏 evidence，填：

```text
human_final_label = noisy_retrieval
human_adjudication_reason = definition_boundary
```

如果论文主要研究 generator 被 irrelevant context 带偏，填：

```text
human_final_label = distraction
human_adjudication_reason = definition_boundary
```

## 5. `human_adjudication_reason` 可选值

请尽量只使用以下值：

```text
definition_boundary
paper_multi_topic
coder_error
insufficient_full_text
metadata_error
codebook_updated
other
```

含义：

| Reason | Meaning |
|---|---|
| `definition_boundary` | 两个标签边界接近，需要根据定义裁决 |
| `paper_multi_topic` | 论文确实覆盖多个主题，需要确定主贡献 |
| `coder_error` | 某个 coder 明显填错或误读 |
| `insufficient_full_text` | 全文信息不足，无法完全确认 |
| `metadata_error` | title / venue / year / URL 等 metadata 有问题 |
| `codebook_updated` | 发现 codebook 定义需要修改 |
| `other` | 其他原因 |

## 6. 字段裁决规则

### 6.1 `screen_in_scope`

填 `1` 如果论文直接研究：

- robust RAG；
- evidence reliability；
- noisy retrieval；
- distraction / context utility；
- knowledge conflict；
- poisoning / prompt injection / RAG security；
- calibration / abstention / selective prediction；
- uncertainty / answerability；
- robust RAG evaluation / benchmark / metric。

填 `0` 如果论文只是：

- 普通 RAG application；
- retrieval-only；
- general LLM robustness；
- general survey；
- multimodal / agentic / code RAG 但没有 evidence reliability；
- duplicate；
- full text 不可访问。

### 6.2 `include_in_evidence_map`

填 `1` 如果论文应该进入最终 evidence map，能支撑 taxonomy、case study、benchmark comparison、attacker matrix、peer-reviewed backbone 或 evidence-strength analysis。

填 `0` 如果论文只是背景、应用、弱相关、重复，或无法支撑结构化分析。

### 6.3 `primary_failure_type`

只能选一个：

```text
noisy_retrieval
distraction
knowledge_conflict
adversarial_corruption
ood_uncertainty
calibration_control
evaluation_benchmark
survey_related
multimodal_agentic_code
other
```

按论文 **主贡献** 判断。

### 6.4 `secondary_failure_types`

可以为空，也可以多个，用分号连接：

```text
knowledge_conflict;evaluation_benchmark
```

注意：

- 如果 secondary label 只是 introduction 里提到，不要加；
- 如果两个 coder 一个填空、一个填某标签，你可以最终填空；
- 空值是合法最终标签。

### 6.5 `method_family`

可选：

```text
attack
defense_mitigation
benchmark_evaluation
analysis
control_calibration
conflict_modeling
survey_background
application
method
other
```

判断主贡献：

- 攻击：`attack`
- 防御 / 缓解：`defense_mitigation`
- benchmark / dataset / metric：`benchmark_evaluation`
- 行为分析 / failure analysis：`analysis`
- 何时检索 / 拒答 / 校准：`control_calibration`
- 冲突建模 / source reconciliation：`conflict_modeling`

### 6.6 `intervention_point`

可选：

```text
corpus_kb
retriever
context_assembly
generator
system_control
evaluation
mixed
not_applicable
```

问：论文主要改变或测量 RAG pipeline 的哪个位置？

### 6.7 `evaluation_type`

可选：

```text
qa_accuracy
faithfulness_hallucination
attack_success
defense_bypass
calibration_selective_risk
retrieval_metric
human_eval
benchmark_only
not_applicable
other
```

选论文最核心的评价指标。

### 6.8 `evidence_strength`

可选：

```text
peer_reviewed_proceedings
venue_linked_preprint
review_platform_record
arxiv_only_preprint
workshop_or_challenge
unclear
```

规则：

- 正式 ACL / EMNLP / NAACL / COLING / SIGIR / WWW / WSDM / KDD / USENIX / CCS / NDSS / ICLR / NeurIPS / AAAI proceedings：`peer_reviewed_proceedings`
- arXiv only：`arxiv_only_preprint`
- OpenReview 但不确定录用：`review_platform_record`
- challenge / workshop / non-archival：`workshop_or_challenge`

### 6.9 `relevance_level`

```text
0 = exclude
1 = background only
2 = supporting evidence
3 = core paper
```

规则：

- `0`: 不属于 survey；
- `1`: 背景或邻近领域；
- `2`: 支持某个 subsection / table；
- `3`: 影响主 taxonomy、case study、benchmark blueprint、attacker matrix 或核心论点。

### 6.10 `is_core_candidate`

填 `1` 如果论文应该影响主文核心叙事。

填 `0` 如果只是 supporting evidence。

不要因为论文是新论文或大模型论文就标 core。

### 6.11 `exclusion_reason`

如果 `screen_in_scope=0`，必须填：

```text
not_rag
application_only
not_robustness
retrieval_only_no_generation
general_llm_only
duplicate
no_full_text
outside_text_scope
other
```

如果 `screen_in_scope=1`，可以为空。

## 7. 常见边界规则

### noisy retrieval vs distraction

- retriever 返回 bad / irrelevant evidence：`noisy_retrieval`
- generator 被 irrelevant evidence 带偏：`distraction`

### knowledge conflict vs adversarial corruption

- 自然冲突、过时文档、source disagreement：`knowledge_conflict`
- 攻击者故意污染或制造冲突：`adversarial_corruption`

### ood_uncertainty vs calibration_control

- 估计不确定性 / answerability：`ood_uncertainty`
- 基于不确定性采取行动：`calibration_control`

### evaluation_benchmark vs method

- 主贡献是 benchmark / dataset / metric：`evaluation_benchmark`
- benchmark 只是实验工具：按方法本身标。

## 8. 完成检查

提交前请确认：

1. `human_final_label` 没有遗漏，除非字段允许空值，例如 `secondary_failure_types` 或 `exclusion_reason`。
2. `human_adjudication_reason` 每行都有。
3. 没有改动 source labels。
4. 没有删除行。
5. 文件名是：

```text
adjudication_log_evidence274_round2_final.csv
```

完成后把文件放在：

```text
robust-rag-survey/manuscript/human_coding/human_round2_evidence274_results/
```

我之后会自动生成：

- final adjudicated evidence map；
- final corpus statistics；
- final category overlap；
- final method-family cross-tab；
- manuscript updated tables。

