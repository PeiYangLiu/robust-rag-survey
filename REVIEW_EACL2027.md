# 审稿意见 / Review

**论文**：Robust RAG under Unreliable Evidence: A Comparability-Centered Survey
**投稿**：EACL 2027（ACL `review` 模板）
**审稿日期**：2026-06-15

---

## 总体推荐

**Weak Reject（borderline，需 Major Revision）**

选题与切入点有价值，透明度罕见地高；但作为 "survey" 核心综述偏薄、主文严重依赖附录、人评证据较弱。按当前形态在 EACL 这类竞争性主会偏 borderline。问题大多可修复。

**ARR 风格评分**

| 维度 | 评分 |
| --- | --- |
| Soundness | 3 / 5 |
| Contribution / Excitement | 3 / 5 |
| Presentation | 2.5 / 5 |

---

## 一、论文概述（审稿人理解）

论文提出一个五坐标"可比性元组"——`(failure, assumption, intervention, metric, action)`——用于判断两篇 robust-RAG 工作在共享标签（noise robustness / faithfulness / security / calibration）下是否真正可比，并把比较划分为 valid / partial / invalid / under-specified。基于一个 342 行经裁决的证据图（Map B），论文做了 5 个"重读改变结论"的案例、venue 加权敏感性分析、60 对盲评协议验证，并给出面向未来论文的 reporting checklist。

---

## 二、优点（应予肯定）

1. **真问题、好切入点**：robust-RAG 文献"标签相同、科学问题不同"的可比性危机是实际痛点；把 **action**（answer / abstain / re-retrieve / filter / verify / …）作为独立坐标是有洞见的观察，确实是多数现有 trustworthy-RAG 分类法欠缺的维度。
2. **文献新且广**：259 条引用覆盖到 2026 年的最新预印本。抽样核验 `auto_references.bib` 中的 arXiv 条目（如 2604.02194、2603.22934），标题与 arXiv 实际页面一致——**参考文献真实、非杜撰**。
3. **透明度罕见**：reliability、override audit、corpus flow、release manifest、checksum、second-coding trail 齐备，优于绝大多数 survey。
4. **可落地产物**：reporting checklist 与 5 个 worked re-analyses 具体、有教学价值，社区可直接采用。
5. **对局限的自陈较诚实**。

---

## 三、主要问题（Major）

### W1. 作为 "survey"，核心综述太薄、且是"引用堆砌"
`survey_core_sections.tex` 仅约 2 页，大量段落是不透明 key 的列表式引用，例如
`\citep{rrag140,rrag143,rrag154,rrag166,rrag168,rrag170}`（survey_core_sections.tex:7）。
读者无法从正文得知这些论文各自说了什么、如何被综合。真正的 survey 需要 synthesis，而非 enumeration。当前正文更像 position / meta-analysis 而非 survey。

### W2. 主文 8 页 vs 附录 40 页，主文不能自洽
主体在 p1–8，参考文献 p9–17，**附录 p18–58（40 页）**。几乎所有 load-bearing 证据（Map B reliability、60 对验证、peer-sensitivity）都在附录，正文充斥 "see Appendix Table X"。ACL/EACL 审稿人没有义务读附录；只读正文时，本文大量是前向引用与断言。

### W3. 人评是核心卖点，但证据较弱且可能循环
- **样本量极小**：作为 headline 的 60 对研究每条件仅 **3 名标注者**（expert_validation_60pair.tex:9 "3 / 180"）；作者自己也写 "unstable with only six annotators"（同表:12）。0.567→0.883 的差异基于 n=3/臂，统计上接近轶事。
- **疑似循环**：protocol 组用的是作者的框架，gold 又由"协议感知"的裁决者构造，于是"protocol 比 control 更贴近 gold"在设计上部分内生。
- **两套研究并存、口径不一致**：另有 12 对 / 30 标注者研究（`comparability_user_study_package`，control 0.800 / protocol 0.978），与 60 对研究（control 0.567）绝对数差异大，说明结果对**作者自选的 pair 集合**敏感。需说明哪一个是主验证、为何都要。
- **无人类受试者声明**：Ethics Statement（main.tex:110–112）只谈不发布攻击 payload，**完全未提**标注者招募、资质、知情同意、报酬、IRB/伦理审查；`annotator_metadata_anonymized.csv` 标注资质为 `not_collected_in_public_artifact`、来源写 "User-provided"。在有 30+ 标注者研究的论文里，这是 ACL 类会议明确要求、却缺失的内容，也直接影响可信度/可复核性。

### W4. 过度对冲（hedging）反噬贡献
"scoping not census" / "audit sample rather than field-level estimate" / "schema sanity check rather than real-system evidence" / "validates triage for this hard regime, not every category" …… 几乎每个结论都被收回一半。诚实可取，但密度过高时审稿人会问：**剥掉所有 caveat 后，真正站得住的贡献是什么？** 目前实际只剩"一套 taxonomy + 一份 checklist + 一个数据集"，需要更自信地立住这一核心。

### W5. 引用核验严重不完整
`citation_audit/audit_summary.json` 显示仅 **30 / 259** 条被核验，且自述为 `preliminary_automated_screen_only`（LLM 自动筛查）；`rewrite_status.json` 写明其余 "pending strict full-text audit"。survey 的价值取决于对所引论文论断的准确性；只验了 ~11% 是硬伤。

### W6. 新颖性论证不足
五个坐标单独看都是已知维度。需更明确说明相对于 trustworthy-RAG / RAG-security 既有分类法，本文"可比性"框架新在哪、为何不能由现有 taxonomy 平凡导出（main.tex:68 那段还不够）。

---

## 四、可执行的修改建议（对应 W）

1. **二选一明确定位（W1）**：要么做成真正的 survey（每个 cluster 给 2–4 句机制级综合，去掉裸 key 列表，正文配代表作小表/小结）；要么改标题与 framing 为 *position / meta-analytical study*，对"comparability"立论与 checklist 加重——后者其实更贴合现有内容。
2. **正文自洽化（W2）**：把 Map B reliability、60 对验证主结果、peer-sensitivity 至少各一张精简版移入正文，附录只留细节。目标是"不读附录也能评审"。
3. **修人评（W3）**：扩大每条件标注人数（理想 ≥8–10）或显著下调结论强度为"探索性"；用**对 hypothesis 盲化**的 gold（裁决者不知道哪组是 protocol）破循环；合并/澄清两套研究；新增 **Human Subjects / Ethics 段落**（招募、资质、同意、报酬、IRB 或豁免依据）。
4. **收敛对冲（W4）**：用一段集中陈述 scope 与 caveat，正文其余处停止反复自我收回；用 1–2 句正面声明"survives-all-caveats"的核心主张。
5. **补全引用核验（W5）**：承诺并报告对全部（或至少所有进入结论的）引用做 per-claim 核验，给出方法与抽样复核率。
6. **强化新颖性对比（W6）**：加一张"本框架 vs 既有 3–4 个 RAG/trust/security taxonomy"的差异表，聚焦"comparability 字段"而非覆盖面（现有 `prior_survey_delta` 可改造）。

---

## 五、次要问题（Minor）

- **表格字号过小**：`main_worked_examples` 用 `\tiny`（tables/main_worked_examples.tex:3）、`main_prior_survey_error_cases` 用 `\scriptsize`。正文 table\* 用 `\tiny` 低于 ACL 可读性预期，建议精简列数后升到 ≥ `\footnotesize`。
- **数字一致性**：正文 Map A 为 **268** 行（main.tex:94），但 reliability 表写 "**274** candidates double-coded"（main_map_b_reliability.tex:9）。请统一或区分 "candidates vs included"。
- **venue 设置**：模板仍是通用 "Anonymous ACL submission"；投 EACL 2027 请确认 venue / 年份与（若适用）survey/position 形态要求。
- 大量 underfull `\hbox`/`\vbox`（窄列 ragged 文本所致），排版可优化。
- 确认所有 released artifact（含 `human_coding/*`）无去匿名信息。

---

## 六、给作者的问题（Questions to Authors）

1. 60 对里的 60 个 pair 与 gold 由谁、按什么标准选定？protocol-aware 选择是否影响 control 偏低？
2. 30 名标注者是真人专家吗？资质、招募、报酬、伦理审批如何？为何 12 对与 60 对两套研究并存？
3. 剥离全部 caveat 后，本文有哪 1–2 条"无需读附录即可验证"的硬结论？
4. 其余 229 条未核验引用的论断准确率，是否做过任何抽样复核？

---

## 七、修改优先级（按性价比）

| 优先级 | 动作 | 对应 |
| --- | --- | --- |
| P0 | 关键证据表移入正文，使主文自洽 | W2 |
| P0 | 新增 Human Subjects / Ethics 段落 | W3 |
| P0 | 明确 survey vs position 定位 | W1 |
| P1 | 改写 `survey_core_sections` 裸引用为机制级综述 | W1 |
| P1 | 人评：扩样本或下调结论 + 破循环 | W3 |
| P1 | 补全/承诺引用 per-claim 核验 | W5 |
| P2 | 收敛 hedging；新颖性对比表 | W4, W6 |
| P2 | 表格字号、268/274 一致性、venue、排版 | Minor |
