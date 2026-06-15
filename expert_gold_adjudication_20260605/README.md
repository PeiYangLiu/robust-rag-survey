# Independent gold adjudication packet

This packet is for creating an independent external gold standard for the robust-RAG comparability study.

## Send to gold adjudicators

Send only:

- `paper_pairs_for_gold_adjudication.csv`
- `gold_adjudication_guide.md` or `gold_adjudication_guide_zh.md`
- `gold_individual_annotation_template.csv`
- paper PDFs or official paper links

After individual annotation, use:

- `gold_panel_adjudication_template.csv`

## Do not send

Do not send any file containing rulebook expected verdicts or previous annotator distributions, including:

- `../expert_validation/paper_pairs.csv`
- `../expert_validation_blind_batch_A_20260605/responses.csv`
- `../expert_validation_blind_batch_A_20260605/analysis_summary.md`

## After panel adjudication

When `gold_panel_adjudication_template.csv` has final labels, run:

```bash
python3 apply_gold_to_pairs.py gold_panel_adjudication_template.csv ../expert_validation/paper_pairs.csv paper_pairs_with_external_gold.csv
```

Then rerun the expert analysis with:

```bash
python3 ../expert_validation/analyze_blind_batch.py ../expert_validation_blind_batch_A_20260605/responses.csv paper_pairs_with_external_gold.csv ../expert_validation_blind_batch_A_20260605
```

This will use `external_gold_verdict` instead of `rulebook_expected_verdict`.

