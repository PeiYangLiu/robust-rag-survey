# 60-pair Expert Validation Coordinator 说明

## 发包
- Protocol 组：`expert_validation_60pair_protocol_annotator_packet.zip`
- Control 组：`expert_validation_60pair_control_annotator_packet.zip`
- Gold adjudicators：`expert_validation_60pair_gold_adjudicator_packet.zip`

## 不要泄漏给普通 annotator
- `coordinator_hidden_pair_key.csv`
- stratum / primary label / intervention / intended_contrast
- gold adjudicator 输出

## 推荐收集规模
- 至少 protocol/control 各 10-15 人，或每个 pair 每组至少 3 个 judgment。
- 至少 2-3 名 independent gold adjudicators。

## 报告
- annotator expertise distribution
- inter-gold agreement
- control vs protocol gold agreement
- per-coordinate error taxonomy
- clustered bootstrap by annotator/pair
- mixed-effects logistic model（样本足够时）
