# 60-pair expert validation 总标注流程

## 目标

这轮标注不是重新标 evidence map，而是验证论文里的五元组 comparability protocol 是否能帮助专家判断两篇 robust RAG paper 是否可比。

每个 pair 的最终 verdict 只能是：

- `valid`：可以直接比较/排序。
- `partial`：同属一个问题族，但只能局部比较或互补，不能直接排序。
- `invalid`：不应直接比较，直接比较会产生错误结论。
- `underspecified`：信息不足，无法判断。

## 推荐人数与分工

推荐一共 9 人：

| 角色 | 人数 | 发哪个 zip |
|---|---:|---|
| Protocol annotator | 3 | `expert_validation_60pair_protocol_annotator_packet.zip` |
| Control annotator | 3 | `expert_validation_60pair_control_annotator_packet.zip` |
| Gold adjudicator | 3 | `expert_validation_60pair_gold_adjudicator_packet.zip` |
| Coordinator | 1 | `expert_validation_60pair_coordinator_packet.zip` |

Coordinator 可以是你自己。Coordinator 包不要发给普通 annotator。

## 标注顺序

### Step 1：先发 Protocol 组

发给 3 个 protocol annotators：

`expert_validation_60pair_protocol_annotator_packet.zip`

他们需要先读：

1. `training_examples_readme_zh.md`
2. `training_examples_from_prior_pilot.csv`
3. `annotation_guide_zh.md`

然后填写：

1. `annotator_expertise_template.csv`
2. `paper_pairs_for_annotation.csv`

Protocol 组必须按照五元组判断：

1. failure：失败类型是否相同？
2. assumption：证据状态 / 威胁模型是否相同？
3. intervention：方法作用位置是否相同？
4. metric：评估指标是否衡量同一目标？
5. action：系统动作是否相同？

建议 rationale 写 1--3 句，并尽量填写 `breaking_coordinates_optional`，例如：

`intervention;action`

### Step 2：再发 Control 组

发给 3 个 control annotators：

`expert_validation_60pair_control_annotator_packet.zip`

他们只需要根据普通 expert judgment 判断，不给五元组训练。

他们填写：

1. `annotator_expertise_template.csv`
2. `paper_pairs_for_annotation.csv`

Control 组也要写 rationale，但不强制写 breaking coordinates。

### Step 3：独立发 Gold 组

发给 3 个 gold adjudicators：

`expert_validation_60pair_gold_adjudicator_packet.zip`

Gold 组不要看 protocol/control 的答案。

Gold adjudicator 填：

`paper_pairs_for_gold_adjudication.csv`

必须填写：

- `gold_verdict_valid_partial_invalid_underspecified`
- `gold_confidence_1_5`
- `breaking_coordinates`
- `gold_rationale`
- `what_valid_comparison_requires`

Gold 组最好先独立完成，再由 coordinator 合并成 panel consensus。

## Coordinator 不要泄漏的文件

以下只给 coordinator，不给普通标注员：

- `expert_validation_60pair_coordinator_packet.zip`
- `coordinator_hidden_pair_key.csv`
- `analyze_60pair_expert_validation.py`
- 已回收的其他 annotator 答案
- gold panel consensus

## 回收文件命名建议

建议这样命名：

Protocol:

- `protocol_annotator_001.csv`
- `protocol_annotator_002.csv`
- `protocol_annotator_003.csv`

Control:

- `control_annotator_001.csv`
- `control_annotator_002.csv`
- `control_annotator_003.csv`

Gold:

- `gold_adjudicator_001.csv`
- `gold_adjudicator_002.csv`
- `gold_adjudicator_003.csv`

## 回收后分析顺序

### Step 4：合并 participant responses

把 protocol 和 control 的 `paper_pairs_for_annotation.csv` 合并成一个文件：

`participant_responses.csv`

需要保留/补充一列：

`condition`

取值为：

- `protocol`
- `control`

### Step 5：合并 gold labels

把 3 个 gold adjudicator 的文件合并成：

`gold_adjudications.csv`

然后由 coordinator 生成：

`gold_panel_consensus.csv`

Panel consensus 至少包括：

- `pair_id`
- `gold_verdict_valid_partial_invalid_underspecified`
- `gold_confidence_1_5`
- `breaking_coordinates`
- `gold_rationale`
- `what_valid_comparison_requires`
- `panel_vote_counts`

### Step 6：运行分析脚本

在 coordinator 包中运行：

```bash
python3 analyze_60pair_expert_validation.py \
  --responses participant_responses.csv \
  --gold gold_panel_consensus.csv \
  --out-prefix expert_validation_60pair
```

如果要做 mixed-effects model，需要 Python 环境里有 `statsmodels`。没有也可以先报告 clustered bootstrap 和 descriptive statistics。

## 最终论文里应报告什么

必须报告：

1. protocol/control 各多少 annotator、多少 judgment
2. gold adjudicator 数量
3. inter-gold agreement
4. protocol vs control agreement with panel gold
5. per-coordinate error taxonomy
6. clustered bootstrap CI
7. mixed-effects model（如果跑得动）
8. disagreement analysis：哪些 pair 最容易错，错在哪些 coordinate

## 重要提醒

如果 protocol 组没有赢，不要硬写成 protocol validation。

可以写成：

> The protocol improves auditability of disagreement by making coordinate-level errors explicit, but it does not necessarily improve raw verdict accuracy without additional training or clearer gold construction.

这比强行包装成 positive result 更可信。

