# Human citation-suitability annotation package

This package is for **human-only** annotation of whether venue-linked RAG papers
should be cited in the survey. Annotators should not use Opus/LLM audit outputs.

## Files

- `human_citation_annotation_guide_zh.md`: Chinese annotation guide.
- `venue200_papers_for_human_annotation.csv`: 200 venue-linked papers.
- `multimodal100_papers_for_human_annotation.csv`: 100 multimodal/scenario RAG papers.
- `all_papers_for_human_annotation.csv`: combined 300-row paper list.
- `human_citation_annotation_template.csv`: individual annotator response template.
- `human_citation_adjudication_template.csv`: final adjudication template.

## Do not send annotators

Do not send Opus/LLM audit files:

- `metadata/venue_200_opus_citation_audit.csv`
- `metadata/venue_200_opus_recommended_citations.csv`
- `metadata/multimodal_rag_100_opus_audit.csv`
- `metadata/multimodal_rag_100_opus_recommended.csv`

The goal is an independent human citation audit.

