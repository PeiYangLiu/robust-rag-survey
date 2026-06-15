# Robust RAG Survey Evidence274 分歧裁决标注说明

这份文档给负责 **adjudication / 最终裁决** 的人工标注人员使用。当前两名独立 coder 已经完成 274 篇 evidence-map 论文的双标，IAA 已计算完成。现在要做的不是重新标 274 篇，而是对两名 coder 有分歧的字段做最终裁决。

## 1. 你需要处理的文件

主工作文件：

```text
robust-rag-survey/manuscript/human_coding/blind_quality_package_evidence274/adjudication_log_evidence274_draft.csv
```

辅助参考文件：

```text
robust-rag-survey/manuscript/human_coding/blind_quality_package_evidence274/adjudicated_evidence274_draft.csv
robust-rag-survey/manuscript/human_coding/human_human_double_coding_protocol.md
```

请不要修改：

```text
source_01_annotations.csv
source_02_annotations.csv
human_human_iaa_summary.json
human_human_iaa_report.csv
```

这些是原始独立标注和 IAA 结果，必须保留不变。

## 2. 标注任务是什么

`adjudication_log_evidence274_draft.csv` 中每一行代表：

- 一篇论文；
- 一个有分歧的字段；
- source 01 的标签；
- source 02 的标签；
- 一个规则辅助生成的 draft label。

你的任务是阅读论文后填写最终裁决：

```text
human_final_label
human_adjudication_reason
```

不要改这些列：

```text
source_01_label
source_02_label
draft_label
draft_rule
```

`draft_label` 只是规则建议，不是最终答案。你可以接受，也可以改。

## 3. 推荐裁决顺序

优先裁决影响 evidence map 和正文统计的字段：

1. `screen_in_scope`
2. `include_in_evidence_map`
3. `relevance_level`
4. `primary_failure_type`
5. `secondary_failure_types`
6. `method_family`
7. `intervention_point`
8. `evaluation_type`
9. `evidence_strength`
10. `is_core_candidate`
11. `exclusion_reason`
12. `reproducibility_evidence`
13. `confidence_1_to_5`

如果时间紧，至少完成前 10 类字段。`confidence_1_to_5` 可以最后处理，因为它不直接决定 evidence map 的统计。

## 4. 每一行怎么裁决

对每一行：

1. 看 `paper_id`、`title`、`url`。
2. 打开论文全文或 PDF。
3. 查看该行的 `field`。
4. 比较 `source_01_label`、`source_02_label`、`draft_label`。
5. 根据论文内容填入 `human_final_label`。
6. 填入 `human_adjudication_reason`。

示例：

```text
field = primary_failure_type
source_01_label = noisy_retrieval
source_02_label = distraction
draft_label = noisy_retrieval
```

如果论文主要研究 retriever 返回 irrelevant passages，最终填：

```text
human_final_label = noisy_retrieval
human_adjudication_reason = definition_boundary
```

如果论文主要研究 irrelevant passages 如何误导 generator，最终填：

```text
human_final_label = distraction
human_adjudication_reason = definition_boundary
```

## 5. `human_adjudication_reason` 可用值

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
| `definition_boundary` | 两个标签边界接近，需要按 codebook 判断 |
| `paper_multi_topic` | 论文确实覆盖多个主题，需要确定主贡献 |
| `coder_error` | 某个 coder 明显误读或填错 |
| `insufficient_full_text` | 全文信息不足，无法完全确认 |
| `metadata_error` | title、venue、year、URL 等 metadata 有问题 |
| `codebook_updated` | 发现 codebook 需要调整 |
| `other` | 其他原因，必要时在旁边备注 |

## 6. 关键字段裁决规则

### 6.1 `screen_in_scope`

填 `1` 如果论文直接研究：

- RAG robustness；
- evidence reliability；
- noisy retrieval；
- distraction / context utility；
- knowledge conflict；
- RAG poisoning / prompt injection / attack / defense；
- calibration / abstention / selective prediction；
- RAG uncertainty / answerability；
- RAG evaluation / benchmark / metric。

填 `0` 如果论文只是：

- domain application；
- general RAG system；
- retrieval-only；
- general LLM robustness；
- multimodal / agentic / code RAG 但没有 evidence reliability；
- duplicate；
- full text 不可访问。

### 6.2 `include_in_evidence_map`

填 `1` 如果论文足以进入最终 evidence map，能支撑主文 taxonomy、case study、benchmark comparison、attacker matrix 或 evidence-strength analysis。

填 `0` 如果论文只是背景、应用、survey、弱相关、重复，或无法支撑结构化分析。

### 6.3 `relevance_level`

使用：

```text
0 = exclude
1 = background only
2 = supporting evidence
3 = core paper
```

判断标准：

- `0`: 不属于 survey。
- `1`: 背景或邻近工作。
- `2`: 支持某个 subsection 或 table。
- `3`: 影响主 taxonomy、case study、benchmark blueprint、attacker matrix 或核心论点。

### 6.4 `primary_failure_type`

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

按论文 **主贡献** 判断，不要因为 introduction 里提到某个词就作为 primary。

### 6.5 `secondary_failure_types`

可以是多个，用分号分隔：

```text
knowledge_conflict;evaluation_benchmark
```

只填实质性 secondary topic。不要过度标注。

### 6.6 `method_family`

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

如果论文主要贡献是 benchmark，优先 `benchmark_evaluation`。如果主要是攻击，优先 `attack`。如果主要是防御，优先 `defense_mitigation`。

### 6.7 `intervention_point`

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

看论文最主要改变或测量 RAG pipeline 的哪个位置。

### 6.8 `evaluation_type`

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

选择论文最核心的评价指标类型。

### 6.9 `evidence_strength`

可选：

```text
peer_reviewed_proceedings
venue_linked_preprint
review_platform_record
arxiv_only_preprint
workshop_or_challenge
unclear
```

如果论文已在 ACL / EMNLP / NAACL / COLING / SIGIR / WWW / WSDM / KDD / USENIX / CCS / NDSS / ICLR / NeurIPS / AAAI 等正式 proceedings 中发表，填：

```text
peer_reviewed_proceedings
```

如果只是 arXiv，填：

```text
arxiv_only_preprint
```

## 7. 常见边界

### noisy retrieval vs distraction

- 研究 retriever 返回坏 evidence：`noisy_retrieval`
- 研究 generator 被 irrelevant/distracting evidence 带偏：`distraction`

### knowledge conflict vs adversarial corruption

- 自然冲突、过时文档、source disagreement：`knowledge_conflict`
- 攻击者故意制造冲突或污染：`adversarial_corruption`

### ood_uncertainty vs calibration_control

- 估计不确定性、判断是否 answerable：`ood_uncertainty`
- 基于不确定性决定 retrieve / abstain / clarify：`calibration_control`

### evaluation_benchmark vs method

- 主贡献是 benchmark / dataset / metric：`evaluation_benchmark`
- benchmark 只是用来测方法：按方法对应类别标注。

## 8. 输出文件

完成后请另存为：

```text
adjudication_log_evidence274_final.csv
```

不要覆盖原始：

```text
adjudication_log_evidence274_draft.csv
```

如果你直接在 draft 文件上编辑，请最后复制一份并重命名为 final。

## 9. 完成标准

合格的 final 文件应满足：

1. 每一行都有 `human_final_label`。
2. 每一行都有 `human_adjudication_reason`。
3. 没有修改 source labels。
4. 没有修改 draft labels。
5. 所有关键字段分歧都已裁决。

完成后，把这个文件交回：

```text
robust-rag-survey/manuscript/human_coding/blind_quality_package_evidence274/adjudication_log_evidence274_final.csv
```

之后可以自动生成：

- final adjudicated evidence map；
- final IAA + adjudication summary；
- regenerated corpus statistics；
- regenerated cross-tabs；
- updated manuscript tables。

