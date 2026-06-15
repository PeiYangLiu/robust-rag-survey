# 训练样例说明

`training_examples_from_prior_pilot.csv` 来自上一轮 12-pair pilot，不属于本次 EV60 正式标注集合，可以在正式标注前阅读。

使用方式：
1. 先看每个样例的 `gold_verdict`。
2. 再看 `breaking_coordinates`，理解为什么不是简单按主题相似度判断。
3. 正式标注 EV60 时，不要套模板；仍然逐对判断 failure / assumption / intervention / metric / action。

经验规则：
- 同主题但 intervention/action 不同，多数是 `partial`。
- 攻击 vs 防御不是自动 invalid；如果 threat model 对齐，常常是 `partial`。
- 自然 conflict vs poisoning 通常不是 direct ranking。
- method vs benchmark 常常是 `partial` 或 `underspecified`，不是 valid leaderboard。
