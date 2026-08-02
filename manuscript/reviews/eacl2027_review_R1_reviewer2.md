# EACL 2027 — Official Review

**Paper:** *What Robust RAG Papers Measure, and When Their Numbers Can Be Compared: A Survey with a Tested Taxonomy*
**Submission type:** Long paper (survey)
**Reviewer:** Reviewer #2
**Date:** 2026-08-02

---

## Scores

| Dimension | Score |
|---|---|
| **Soundness / Correctness** | **2.0 / 5** (major methodological problems; several headline claims are not supported by the design) |
| **Excitement / Substance** | **2.5 / 5** (the *question* is excellent; the *answer* delivered is much smaller than advertised) |
| **Reproducibility** | 3 / 5 (downstream pipeline is admirably reproducible; the search stage is admittedly *not* re-executable; no artifact link in the submission) |
| **Ethical concerns** | None beyond the dual-use note, which is handled well |
| **Reviewer confidence** | 4 / 5 (I read the 8-page body, Limitations/Ethics, and spot-checked Appendices C–H and the generated tables) |
| **Overall recommendation** | **Reject** — resubmit after a major restructuring (see §6) |

---

## 1. Summary of the paper

The paper surveys robust RAG along four "failure surfaces" (evidence, model, adversary, system control), reduces them to five "reporting coordinates" (C1 evidence state, C2 origin/capability, C3 intervention, C4 outcome/unit, C5 policy/utility), and defines a three-branch decision rule (*survives* / *narrows* / *undefined*) for when two published numbers answer the same question. Its self-described distinguishing move is that the taxonomy is *tested* rather than asserted: (i) a constructed 432-item benchmark on which LLM judges recover coordinates at 0.95 and agree on the verdict at κ = 0.74; (ii) an argument that C3 must be excluded from the rule, supported by κ = 0.00 on constructed passages and a 99.6% "mismatch" rate on corpus items; (iii) a deterministic screen over 259 full texts yielding 1,703 candidate cross-paper juxtapositions, from which 533/610 classified candidates are found to be *re-implementations* rather than *transported* numbers, while verdict agreement collapses to κ = 0.06 (ceiling 0.46) and survives four interventions.

The motivating case (PoisonedRAG's Table 4 reporting Corpus Poisoning at 0.01 against that method's own 84.2% retrieval-level success) is genuinely well chosen, and Figure 1 is the best page of the paper.

---

## 2. Reasons to accept

1. **The question is real and under-served.** "Under what conditions is a reported number about the same question as another" is the correct reading frame for robust RAG, and the field does routinely juxtapose ASR numbers that count different events. The paper identifies this crisply.
2. **The motivating case is exemplary.** Figure 1 does more work in one page than most survey taxonomies do in ten, and the observation that the benchmarked paper *itself* said the baselines were measuring something else is a nice piece of scholarship.
3. **Methodological hygiene well above survey norms.** κ_max ceilings (Umesh 1989; Sim & Wright 2005), exact McNemar tests, paired designs, leave-one-judge-out columns, a rule-fidelity check, quote verifiers against cited line ranges, a screen-recall re-weighting, and an explicit reviewer-as-unit-of-assignment simulation. This is more instrument discipline than I have seen in any RAG survey.
4. **An honest Limitations section.** It concedes the irreproducible search stage, the circularity of the constructed benchmark, the small privileged-reference design, and the panel-dependence of σ̂_r. I want to credit this explicitly — the concessions are real, not decorative.
5. **The provenance finding is the paper's most useful contribution.** "87.4% of cross-paper juxtapositions re-implement rather than transport" is actionable, plausible, and is the one quantity the instrument recovers against a reference (0.91 [0.86, 0.96] vs. 0.79 baseline).

Unfortunately, the concessions in Limitations do not neutralize the problems, because the abstract, title, contributions list and conclusion do **not** carry them.

---

## 3. Reasons to reject

### 3.1 The central negative claim is not licensed by the design (major)

The abstract states: *"whether a quoted gap survives is **not reproducibly decidable from published text** (κ 0.06 against a ceiling of 0.46)."* The conclusion repeats it. This is a claim about **published text**. The evidence is exclusively about **disagreement among LLM judges**. No human annotation was collected anywhere in the paper (Ethics §, Limitations "Who did the coding"). The "evidence-privileged reference" that anchors the accuracy numbers is *also* an LLM panel, and the paper concedes that two of four reference adjudicators share a developer with the deployed panel and one shares a checkpoint.

The conclusion the design supports is: *"a panel of contemporary LLM judges, given 45-line windows or full papers, cannot reproducibly adjudicate comparability."* That is a legitimate and publishable finding — it is just a much smaller and less surprising one than the paper sells, and it belongs in the title. Attributing the failure to the *literature* rather than to the *instrument* is exactly the inferential move the paper spends 73 pages telling other authors not to make. The four interventions (full papers, abstention option, composed rule, open-weight checkpoints) rule out four specific instrument explanations; they do not rule out the instrument class, because every arm is the same instrument class.

### 3.2 The "test of the taxonomy" is substantially circular (major)

The paper's claimed differentiator from the six prior surveys is contribution (iii). Examined closely, its three legs are weak:

- **Leg 1 (codability).** The Limitations concede that "each item's reference verdict *is* the decision rule applied to that item's coordinate values, so the rule cannot be wrong on this benchmark by construction." What remains is a measurement of whether an LLM can extract explicitly stated facts from templated prose the authors wrote. That is an information-extraction result about LLMs, not a validation of a taxonomy. It cannot be reported as "we test the taxonomy" in an abstract.

- **Leg 2 (the C3 exclusion) is a tautology presented as a falsifiable prediction.** The paper's own justification is definitional: *"comparing two different systems means the intervention differs by construction."* No measurement can falsify a definition. The two "independent measurements" therefore confirm nothing: (a) a 99.6% mismatch rate is what "differs by construction" *means*; (b) κ ≈ 0.00 at 99.6% one-class prevalence is the textbook κ prevalence paradox — the paper elsewhere demonstrates it knows this (it computes κ_max = 0.42 for C3 and reports observed agreement 0.75), yet still reads κ = 0.00 as substantive evidence that C3 "carries no information for an agreement statistic to find." Note also the internal tension: if κ_max for C3 is 0.42, the marginals are *not* fully degenerate, and an observed κ of ≈0 (share of ceiling reported as **−26%**) means judges disagree *worse than chance* on a coordinate they can supposedly read off explicitly — that is an instrument-failure signal, not a confirmation of the taxonomy. Calling this "the taxonomy making a prediction and the data confirming it" is the strongest overclaim in the paper.

- **Leg 3 (five coordinates vs. two) does not survive its own numbers.** On non-degenerate items: 0.861 vs. 0.832, i.e. **+2.9 points**, statistically significant (p = 0.0015) and practically negligible, on a synthetic benchmark. On the corpus, the C1/C4 codebook is *not worse* (+0.03, [−0.05, +0.12]). The paper then claims the gap "widens where it matters" — on the degenerate arm, 0.33 (five) vs. 0.11 (two). But that arm's own stated baseline is **1.00**: a constant "the passage does not say" predictor is perfect there. So the sentence "the five-coordinate instrument scores 0.33 against 0.11" is a comparison between two catastrophic failures, 67 points below a trivial baseline the paper itself reports. Presenting this as the place where five coordinates "earn their place" is not acceptable, and it propagates verbatim into the abstract ("five coordinates beat the best two-coordinate estimator where it matters") and the conclusion.

### 3.3 The one positive result inherits a long chain of unvalidated gates (major)

The 533/610 (87.4%) re-implementation share depends on: a deterministic screen that its own recall analysis shows captures 1,703 of an estimated 6,710 relevant windows (**~75% missed**); an LLM eligibility gate at κ = 0.51; LLM provenance labels at κ = 0.55; over 103 papers drawn from an open-access, preprint-heavy frame of 259 texts. The re-weighted 93% [86, 96] estimate rests, by the paper's own Limitations, on **7** sampled transported-eligible windows, with perturbations moving it to 96.1%/88.8%. The direction is probably right; the number should not be in an abstract, and certainly not as "most cross-paper comparison here is a within-harness activity" without "here" being pinned to the frame in the same sentence.

**Additionally, a selection effect is not addressed.** Verdict accuracy against the privileged reference is computed on 114 of 180 windows — those where the reference adjudicators themselves reached a quote-verified majority (RefVdN = 129, no-majority = 51). The 51 discarded windows are precisely the hardest cases, i.e. the ones that most directly bear on "not decidable." Dropping them from the accuracy computation while retaining them as motivation for the undecidability claim is having it both ways. At minimum, worst-case/best-case bounds over the excluded windows are required.

### 3.4 Instrument-quality facts that belong in the body are buried in an appendix table (major)

Appendix Table `census-diagnostics` reports two things a reader must know before believing anything in §10:

- **Rule fidelity 0.770 for judge coderB**, with **162 "survives" verdicts that the judge's own coordinate labels contradict** (coderC: 0.925, 53 contradictions). One-quarter of one judge's codings violate the instrument it was given.
- **21 evidence quotes (1.1%) are absent from the source document altogether** — i.e. fabricated citations from the judges.

The body reports only the aggregate consequence ("composing the rule mechanically … moves it by +0.02"). A paper whose thesis is that unverified declarations are not evidence cannot relegate its own instrument's 23%-infidelity and 1.1%-fabrication rates to a generated appendix table.

### 3.5 It is not usable as a survey, and it says so (major, venue fit)

- The synthesis is **~4.5 pages** in the body covering four surfaces; the actual survey is Appendix Part I (pp. 18–43). Reviewers are not obliged to read appendices, and readers seeking a field map should not have to.
- The evidence base is **342 map rows / 259 full texts**, from **55 arXiv queries at one snapshot**, and the paper states that the first search stage is "documented but not re-executable" because per-query hit counts were not logged. A survey that invokes PRISMA (Figure `screening-frame-flow`) and then concedes its search cannot be reproduced does not meet the standard the citation implies.
- The paper explicitly disclaims field-level statements: *"where it measures, the statement is about the frame, never the field."* A survey whose measurements cannot speak about the field, and whose narrative sections are compressed to four pages, serves neither audience.
- The body's citation base is dominated by `@misc` arXiv preprints (the `rragNNN` keys). The `peer-reviewed-backbone` table is a good-faith mitigation, but it is prose-level and does not restore coverage. Several canonical peer-reviewed anchors are absent from the **body**: Liu et al. 2024 (*Lost in the Middle*), Longpre et al. 2021 (entity-based knowledge conflicts), Cuconasu et al. 2024 (*The Power of Noise*, SIGIR), Xie et al. 2024 (*Adaptive Chameleon or Stubborn Sloth*, ICLR), and RAG evaluation frameworks (RAGAS, ARES).

### 3.6 Missing related work in exactly the two areas the paper operates in (moderate)

Given that the entire empirical apparatus is LLM-as-judge meta-evaluation, the omission of the LLM-judge reliability literature is disqualifying for the novelty claim: no citation to Zheng et al. 2023 (MT-Bench / LLM-as-a-judge), to work validating LLM judges against human judges, to self-preference / self-bias findings (which bear directly on the shared-developer reference problem the paper concedes), or to position/verbosity bias work. Similarly, the meta-science precedent on cross-paper comparability in NLP is uncited: Marie et al. 2021 (*Scientific Credibility of Machine Translation Research*, ACL) is the closest prior art to this paper's entire premise and does the comparable-numbers audit **with human coding over 769 papers**; Bowman & Dahl 2021 (*What Will it Take to Fix Benchmarking*) and Gehrmann et al. on evaluation reporting are also relevant. Card et al. 2020 is in the `.bib` but the surrounding literature is not engaged. The claim "no survey is accompanied by evidence that its categories can be read off a paper" is defensible only for RAG surveys, not as stated.

### 3.7 Presentation (moderate, but it affects reviewability)

- Nearly every quantitative claim in the body is a macro-substituted number with no inline definition of its denominator, its N, or which agreement statistic it is. §10 in particular reads as a compressed technical report: "raises agreement by +0.20 [0.09, 0.36]", "moves it by +0.01 [−0.07, 0.11]", "moves it by +0.02 [0.00, 0.05]" in consecutive clauses, with three different N's the reader cannot see.
- Four different agreement quantities (Fleiss/Cohen κ, Gwet AC1, raw observed agreement, and "% of κ_max") are used interchangeably across body and tables without a single place defining which is used where.
- The prose style — long appositive chains, em-dash-heavy, terminal clauses that carry the actual claim — is consistently hard to parse. Example: *"What remains is the distance between 0.29, with both papers read end to end, and the κ 0.74 the same instrument reaches on prose written to state its coordinates."* This is the paper's closing analytical statement and it takes three readings.
- The abstract promises "We release the frame, the evidence map, all codings and four verifiers," but the submission contains **no anonymous artifact link and no pointer to supplementary material** in the body, Limitations, or Ethics.

---

## 4. Detailed comments and questions to the authors

1. **(§1, Figure 1)** The quoted sentence *"are ineffective because they cannot achieve generation, generation, and retrieval condition, respectively"* is ungrammatical. If it is verbatim, mark it `[sic]`. If it is a PDF-extraction artifact, then the "released verifier (7/7 checks pass)" passed a corrupted string — which materially weakens the verbatim-verification guarantee the paper leans on throughout (and which the census diagnostics show fails 1.1% of the time in the other direction). Please state which it is.
2. **(§1, Figure 1)** State the retriever/top-k row from which 84.2% is taken, and whether it is the same Contriever checkpoint as PoisonedRAG's Table 4. The figure asserts "shared by both"; the audit's own C1 requires this to be shown, not asserted.
3. **(§9)** What would have falsified the intervention exclusion? Please give the observation that would have led you to include C3 in the rule. If none exists, drop "falsifiable commitment" and present C3's exclusion as the definitional choice it is.
4. **(§9)** Report the observed-agreement and κ_max values for C3 in the body next to κ = 0.00, and address the prevalence paradox explicitly rather than in a citation.
5. **(§9)** On the degenerate arm, report the constant baseline (1.00) in the same sentence as 0.33 vs. 0.11, or remove the "where it matters" claim from the abstract and conclusion.
6. **(§10)** Provide bounds on the verdict accuracy over the 51 privileged windows with no reference majority (best case / worst case), or drop the accuracy figure and report agreement only.
7. **(§10)** Report a sensitivity analysis of the 87.4% provenance share to the eligibility gate (κ = 0.51): what is the share under unanimous-eligibility, under majority-eligibility, and under all-candidates?
8. **(§10)** Move the rule-fidelity (0.770 for one judge; 162 self-contradicting "survives") and quote-fabrication (21 absent quotes) numbers into the body.
9. **(§10, §11)** σ̂_r = 0.50 [0.33, 0.62] is a property of the assembled panel (the paper says so). Then the type-I inflation of 8%–28% is also panel-specific. What does a designer do with a parameter that is not a property of the task?
10. **(Global)** Please add a human-coded subsample — even 60–100 windows, two annotators, adjudicated — as the anchor for the negative claim. Without it, no sentence of the form "not decidable from published text" can be sustained. With it, the paper's headline becomes defensible and its contribution goes up substantially.
11. **(Global)** Give the artifact link (anonymized) or state where in the supplementary material each released component lives.
12. **(§2)** "259 full texts" from "1,904 records" over a field this size will strike many readers as thin. Please justify the 55 queries, or report coverage against a known list (e.g. recall against the reference lists of the six prior surveys you compare to).

---

## 5. Typos / minor

- Abstract: "533 of the 610 classified candidates" invites the reader to compute 533/1,703. Give both denominators.
- §10: "\ProvReimplemented{} of \ProvClassified{}" and §12 repeat the same figure three times with three different framings ("classified candidates", "candidates assigned a provenance class", "juxtapositions"). Fix to one.
- The appendix runs to 56 pages with **58 tables and 13 figures**, several of which report the same quantity under different framings. Consolidate; a reviewer cannot audit 58 generated tables, and the paper's credibility currently depends on them.
- §11: "the coordinate published passages state least often" — supported where? Give the number.
- Figure 1 caption: "the coordinates of §8" — forward reference across seven sections; consider moving the coordinates earlier or repeating the definition.
- British/American spelling is mixed ("organise"/"analyze", "utilisation"/"utilization") across body and appendix.

---

## 6. Recommendation and path forward

**Reject.** I want to be clear that this is not a low-effort submission — it is the opposite, and the instrument discipline on display is better than that of most empirical papers I review. The reason for rejection is that the paper's three headline claims each overshoot what its design licenses, and two of them (the C3 "prediction" and the five-vs-two "where it matters" comparison) do so in ways that the paper's own reported numbers contradict. A survey that argues the field over-reads its numbers must be held to that standard first.

There are two good papers inside this submission, and I would review either favorably:

- **(A) A survey.** Promote Appendix Part I into the body, expand the peer-reviewed base, make the search reproducible, and keep the coordinates + Figure 1 as the organizing contribution. Drop the census to a short section reporting the provenance finding only.
- **(B) A meta-evaluation / resource paper**, retitled to what is shown — e.g. *"Can LLM panels adjudicate cross-paper comparability? A negative result with an evidence ladder"* — with a human-coded anchor subsample, the LLM-judge reliability literature engaged, the instrument-fidelity numbers in the body, and the taxonomy presented as the codebook rather than as a tested theory.

Splitting them is, in my judgment, the fastest route to acceptance for both.

---

## 中文要点（供作者参考）

**结论：拒稿（Reject），建议大改后重投。**

1. **核心负面结论超出了实验设计能支撑的范围。** 摘要说"某个引用的差距是否成立，无法从已发表文本中可复现地判定"，但全文没有任何人工标注，所有证据都是 LLM 评审之间的一致性；连"特权参考标准"本身也是 LLM，且与被评面板共享厂商甚至同一 checkpoint。设计能支持的结论只是"当前 LLM 面板做不了这件事"。
2. **所谓"对分类法的检验"存在循环。** 构造基准的金标准就是把决策规则套用在该条目自己的坐标上，规则按构造不可能出错（作者在 Limitations 已承认）；C3 的排除是定义性真理（比较两个不同系统，干预点必然不同），99.6% 的 mismatch 与 κ=0.00 什么都没验证，反而正是 κ 的 prevalence 悖论。
3. **"五坐标优于两坐标"经不起自身数据检验。** 非退化条目 0.861 vs 0.832（+2.9 点）；语料上 C1/C4 "并不更差"；而所谓"最关键的那一组"是 0.33 vs 0.11——该组的常数基线是 **1.00**，这是在比较两次彻底失败。
4. **唯一的正面结论（87.4% 为重实现）依赖一长串未验证的关卡：** 筛选漏掉了约 75% 的相关窗口，eligibility κ=0.51，provenance κ=0.55，重加权后的 93% 只基于 7 个采样窗口。
5. **仪器质量问题被放进了附录表：** 一个评审 23% 的编码与自己给出的坐标矛盾（162 条 "survives"），1.1% 的证据引文在原文中根本不存在（即编造）。这两条必须进正文。
6. **作为综述不合格：** 正文综述仅约 4.5 页，证据库 259 篇全文 / 342 行，以 arXiv 预印本为主，检索阶段作者自承"不可重新执行"，却引用了 PRISMA；正文缺 Lost in the Middle、Longpre 2021、Power of Noise 等经典工作。
7. **相关工作缺失两大块：** LLM-as-a-judge 可靠性文献（含 self-preference 偏差，直接关系到"同厂商参考标准"问题）与 NLP 元科学先例（尤其 Marie et al. 2021，用**人工**标注做了 769 篇论文的可比性审计）。
8. **建议拆成两篇**：(A) 一篇真正的综述；(B) 一篇改名后的元评估论文，加入人工标注锚点。任何一篇我都会给出正面评价。
