# Privacy-minimized design-audit package

This reviewer package contains only the pre-outcome design materials needed to
inspect the planned 480-claim study. It contains no participant roster,
calibration response, formal response, adjudication response, outcome,
participant attribute, timing record, or derived study statistic. The original
workflow README is intentionally omitted because it preserves historical
state descriptions that are not evidence.

The public package includes the 480-row frozen claim frame, ten fictional
calibration items, design and analysis code, schemas, source-sampling records,
and a deterministic manifest. These files document what the planned study
would have measured; they do not establish that a participant cohort existed
or acted independently.

From the extracted reviewer ZIP, the following command checks only:

- the required public file set and manifest hashes;
- absence of private field names and original participant IDs;
- the 480-row frozen-claim header/count; and
- the ten-item fictional calibration-set header/count.

```bash
python manuscript/human_coding/heldout_claim_validation_v3_20260715/validate_package.py \
  --mode frozen --portable
```

A `PASS` does **not** validate recruitment, participant independence,
calibration completion, assignment issuance, returned responses, gold labels,
or outcomes. Those materials are absent, and no result from the excluded
collection is used by the paper.
