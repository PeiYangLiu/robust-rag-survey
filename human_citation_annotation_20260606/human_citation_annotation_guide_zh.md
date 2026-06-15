# Robust RAG Survey 人工引用适配标注说明

## 目标

本任务用于判断已经下载到本地的 venue-linked RAG 论文是否适合引用进我们的 survey。请注意：

- 这是**人工标注**，不要使用 Opus/LLM 的审读结果。
- 不是判断论文质量高低，而是判断它在本 survey 中承担什么证据作用。
- 标注结果会用于决定哪些论文进入主文、case study、appendix、背景讨论，哪些不引用。

## 输入文件

可以选择其中一个或多个文件进行标注：

- `venue200_papers_for_human_annotation.csv`
  - 200 篇 venue-linked published/open PDFs。
- `multimodal100_papers_for_human_annotation.csv`
  - 100 篇 multimodal / graph / table / agentic / tool / code / domain / long-context RAG papers。
- `all_papers_for_human_annotation.csv`
  - 上面两者合并，共 300 行，可能存在重复或同主题重叠。

每行包含：

- `collection`
- `paper_id`
- `title`
- `year`
- `venue`
- `scenario`
- `scenario_hits`
- `pdf_path`
- `pdf_url`
- `landing_url`

请优先阅读 `pdf_path` 指向的本地 PDF。如果本地 PDF 打不开，可以使用 `pdf_url` 或 `landing_url`。

## 不要使用的文件

不要看以下 Opus / LLM 审读文件，否则会污染人工标注：

- `metadata/venue_200_opus_citation_audit.csv`
- `metadata/venue_200_opus_recommended_citations.csv`
- `metadata/venue_200_opus_citation_audit_summary.*`
- `metadata/multimodal_rag_100_opus_audit.csv`
- `metadata/multimodal_rag_100_opus_recommended.csv`
- `metadata/multimodal_rag_100_opus_summary.*`

## 标注输出文件

每位标注者填写：

`human_citation_annotation_template.csv`

建议复制一份并改名，例如：

`annotator_A_citation_annotations.csv`

## 需要标注的字段

### 1. `citation_decision`

只能选以下之一：

| Label | 含义 |
| --- | --- |
| `main_cite` | 适合放进主文核心 survey section，能支持重要机制性结论或方法谱系。 |
| `case_study` | 适合放进 deep comparative case study，用于细读、对比、反例或边界案例。 |
| `appendix_cite` | 适合放进 appendix extended survey，支持覆盖面，但不需要主文展开。 |
| `background_only` | 只适合作为背景或边界说明，不适合支撑核心结论。 |
| `exclude` | 不适合引用；与 robust RAG / unreliable evidence / action control 关系弱或不相关。 |

### 2. `primary_perspective`

只能选以下之一：

| Label | 含义 |
| --- | --- |
| `evidence_construction` | 检索、reranking、context construction、compression、sufficiency、noise filtering。 |
| `model_evidence_use` | faithfulness、attribution、knowledge conflict、context use、grounding。 |
| `security_integrity` | poisoning、prompt injection、privacy leakage、backdoor、attack/defense。 |
| `action_control` | uncertainty、calibration、abstention/refusal、adaptive retrieval、routing、correction。 |
| `evaluation` | benchmarks、metrics、datasets、diagnostic tools、evaluation protocols。 |
| `modality_scenario_core` | multimodal、vision、graph/KG、table、agentic/tool、code/math、domain-specific、long-context RAG。 |
| `foundation` | RAG / retrieval / calibration / selective prediction 等基础工作。 |
| `boundary` | 相关但偏应用、模态边界或领域边界。 |
| `unrelated` | 不相关。 |

### 3. `scenario_type`

如果 `primary_perspective = modality_scenario_core` 或论文属于跨模态/场景扩展，请填写：

| Label | 含义 |
| --- | --- |
| `vision_multimodal` | 图像、视频、视觉问答、VLM/LVLM、multimodal RAG。 |
| `graph_kg` | graph RAG、knowledge graph RAG、subgraph retrieval。 |
| `table_structured` | table RAG、structured data、database、text-to-SQL。 |
| `agent_memory_tool` | agentic RAG、memory RAG、tool/web-search RAG、multi-agent search。 |
| `code_math_symbolic` | code、math、symbolic、theorem、program RAG。 |
| `domain_biomed_legal_finance` | 医疗、法律、金融、专利、电商等高风险领域 RAG。 |
| `long_context_doc` | long-context、long-document、million-token、document RAG。 |
| `other` | 其他。 |
| `not_applicable` | 不属于多模态/场景扩展。 |

### 4. `relevance`

只能选：

- `high`
- `medium`
- `low`
- `none`

判断它与本 survey 主题的关系，而不是论文质量。

### 5. `evidence_strength`

只能选：

| Label | 含义 |
| --- | --- |
| `venue_backbone` | 已发表/venue-linked，且可支撑主文核心结论。 |
| `useful_venue_support` | 已发表/venue-linked，适合支持某个子点或 appendix。 |
| `boundary_context` | 边界/背景/应用场景，可用于说明扩展范围。 |
| `not_relevant` | 不适合作为本文证据。 |

### 6. `supports_claims`

写 1--3 条它能支持的 survey claim。例如：

- `context compression can reduce distractor burden`
- `visual RAG requires modality-specific evidence grounding`
- `agentic RAG turns retrieval into an action policy`
- `medical RAG exposes corpus mismatch and safety risks`

### 7. `suggested_location`

只能选：

- `main:evidence`
- `main:model`
- `main:security`
- `main:control`
- `main:evaluation`
- `main:modality`
- `main:case_study`
- `appendix:extended_survey`
- `appendix:background`
- `do_not_cite`

### 8. `artifact_availability`

只能选：

- `code_data_available`
- `code_only`
- `data_only`
- `paper_only`
- `unclear`

如果论文里明确给了 GitHub / dataset / benchmark，请选对应项。

### 9. `rationale`

用 2--4 句话解释：

1. 这篇论文实际做了什么。
2. 它和 robust RAG under unreliable evidence 有什么关系。
3. 为什么应该放在主文 / case study / appendix / background / exclude。
4. 有什么 overclaim risk。

### 10. `confidence_1_5`

- 1 = 很不确定
- 3 = 中等确定
- 5 = 很确定

## 判断原则

### 适合 `main_cite` 的论文

通常满足：

- venue-linked / 已发表；
- 与 robust RAG 的核心问题直接相关；
- 能支撑主文机制性结论；
- 不只是普通应用；
- 有明确方法、benchmark、failure analysis 或 evaluation insight。

### 适合 `case_study` 的论文

通常满足：

- 和其他论文存在有价值的对比；
- 能展示 failure / assumption / metric / action mismatch；
- 能说明某个常见结论需要被修正；
- 或者是 multimodal / graph / table / agentic RAG 的代表性边界案例。

### 适合 `appendix_cite` 的论文

通常满足：

- 相关但不是主文核心；
- 支持覆盖面；
- 是某个细分方向的补充；
- 或者是较窄 domain/application，但仍有 RAG reliability 信息。

### 适合 `background_only` 的论文

通常满足：

- 是基础 RAG / retrieval / long-context / multimodal retrieval 工作；
- 对本文有背景价值；
- 但没有直接讨论 unreliable evidence / robustness / action control。

### 应该 `exclude` 的论文

通常满足：

- 只是使用 RAG 做应用，没有 robustness/evidence/action/evaluation insight；
- 与 RAG 关系很弱；
- 与文本/多模态/结构化/agentic RAG 可靠性无关；
- 只是 diffusion / unrelated generation / generic retrieval，不支撑本文论点。

## 最终 adjudication

如果有多位标注者，请使用：

`human_citation_adjudication_template.csv`

最终 adjudication 应保留：

- disagreement summary
- final decision
- final rationale
- whether manuscript should cite it
- whether BibTeX key exists / needs adding

## 建议样本

如果时间有限：

- 每个 annotator 标 50--100 篇；
- 每篇至少 2 人独立标；
- disagreement 再由第三人 adjudicate。

如果要最严格：

- 300 行全部双人独立标注；
- 统计 Cohen/Fleiss kappa；
- 输出 final human citation map。

