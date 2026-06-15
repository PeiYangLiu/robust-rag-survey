# 60-pair Gold Adjudication 指南

Gold adjudicator 需要独立给每个 pair 一个 reference verdict。请不要看普通 annotator 的答案。

## 输出
填写 `paper_pairs_for_gold_adjudication.csv`：
- `gold_verdict_valid_partial_invalid_underspecified`
- `gold_confidence_1_5`
- `breaking_coordinates`
- `gold_rationale`
- `what_valid_comparison_requires`

建议至少 2-3 名 gold adjudicators 独立完成。之后 coordinator 汇总 inter-gold agreement，再做 panel adjudication。
