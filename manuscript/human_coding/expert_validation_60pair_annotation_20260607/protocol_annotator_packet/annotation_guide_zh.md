# 60-pair Expert Validation 标注指南（Protocol 组）

## 任务
你会看到 60 对 robust RAG 论文。请判断两篇论文的结果是否可以作为同一问题下的直接比较。

## 输出文件
1. `annotator_expertise_template.csv`：填写匿名背景。
2. `paper_pairs_for_annotation.csv`：填写每个 pair 的 verdict、confidence、time_seconds、rationale。

## verdict 定义
- `valid`：failure、assumption、intervention、metric、action 基本对齐，可以直接比较或排序。
- `partial`：同属一个问题族，但至少一个关键坐标不同；只能作为互补机制或局部比较。
- `invalid`：问题设定不同，直接比较会产生错误结论。
- `underspecified`：论文信息不足，无法判断是否可比。

## 五个判断坐标
1. failure：失败类型是否相同？如 noisy retrieval、knowledge conflict、poisoning、calibration。
2. assumption：证据状态/威胁模型是否相同？如自然噪声、构造 benchmark、攻击者插入、prompt injection。
3. intervention：作用位置是否相同？corpus/KB、retriever/context、context assembly、generator、system control、evaluation。
4. metric：指标是否衡量同一目标？answer accuracy、faithfulness、attack success、selective risk、calibration、cost。
5. action：系统动作是否相同？answer、filter、verify、retrieve again、abstain、clarify、quarantine、trace、recover。

## 标注原则
- 不要因为两篇都叫 robust RAG / faithfulness / security 就判 valid。
- 如果同问题族但 intervention/action 不同，多数是 `partial`。
- 如果自然 conflict 和 adversarial poisoning 混在一起，多数不是 direct ranking。
- rationale 用 1-3 句说明最关键 breaking coordinate。
