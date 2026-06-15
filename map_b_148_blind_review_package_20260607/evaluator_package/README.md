# Blind Review Package

Files:

- `annotation_set.csv`: adjudicated annotation table for review.
- `validation_summary.json`: row counts, field completeness checks, and label-count summaries.

Validation checks:

- 139 rows.
- 139 unique `record_id` values.
- No duplicate `record_id` values.
- No blank adjudicated target fields.
- No mismatch between `adjudicated_in_scope` and `adjudicated_include_in_map`.
