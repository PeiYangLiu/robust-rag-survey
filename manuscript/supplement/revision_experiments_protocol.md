# Protocol for the revision experiments

Three experiments were added in response to reviewer objections W1/W2 (the
disclosure contrast), W4 (no reference-based check on the provenance label) and
W5 (a frame-level composition stated as a field-level fact).  Everything below
was fixed before any judge was run, and every artifact named is released.

## 1. Redesigned comparability benchmark (W1, W2, W7)

*Builder*: `scripts/build_comparability_instrument_benchmark_v2.py`, seed
`2026080401`.  *Items*: `supplement/comparability_instrument_benchmark_v2.jsonl`
(432 items from 216 specifications).  *Runner*:
`scripts/run_comparability_instrument_v2.sh` (6 judges from 3 developers x 3
codebooks).  *Analysis*: `scripts/analyze_comparability_instrument_v2.py`.

Design: `presentation` (canonical | naturalistic, paired within specification)
x `disclosure` (full | partial_balanced | partial_forcing).  Verdict classes are
equinumerous inside `full` and `partial_balanced` at each presentation level, so
each arm's constant baseline is 1/3 and no baseline is produced by pooling.
`partial_forcing` reproduces the v1 manipulation and is declared degenerate: its
reference verdict never varies, its constant baseline is 1.00, it is scored
against that baseline and it is excluded from every pooled figure.

Two implementation corrections relative to v1.  (a) The composed rule now checks
the repair branch before falling through to `undefined`, which is the order
Section 3 of the manuscript states; the v1 implementation returned `undefined`
whenever any threatening coordinate was not `match`/`mismatch`, which made
branch 2 unreachable for a withheld coordinate.  (b) Baselines are stratum
specific throughout.

## 2. Constructed provenance reference (W4)

*Builder*: `scripts/build_provenance_benchmark.py`, seed `2026080421`.  *Items*:
`supplement/provenance_benchmark.jsonl` (280 items).  *Runner*:
`scripts/run_provenance_benchmark.sh`.  *Analysis*:
`scripts/analyze_provenance_benchmark.py`.

Four reference classes fixed at construction: `reimplemented`, `transported`,
`unclear` and `asserted_no_number`.  The first three are equinumerous, so the
three-way constant baseline is 1/3; `asserted_no_number` is reported separately
because the deployed three-option prompt cannot express it.  A difficulty factor
crosses the two decidable classes: `explicit` items carry a declaration
sentence, `implicit` items carry none and provenance follows only from
structure, so a phrase-matching classifier scores at baseline on the second.

The `deployed` arm uses the byte-identical prompt from
`scripts/classify_number_provenance.py` and the same three judges and majority
rule that produced the census labels; the `fourway` arm adds the missing option.

## 3. Out-of-frame recall sample (W5)

*Builder*: `scripts/build_screen_recall_sample.py`, seed `2026080431`.  *Sample*:
`supplement/screen_recall_sample.jsonl` (420 of 5,007 missed windows).
*Runner*: `scripts/run_screen_recall.sh`.  *Analysis*:
`scripts/analyze_screen_recall.py`.

The universe is every window, under the screen's own windowing, naming a
gazetteer system absent from the paper's title/abstract region and containing at
least one result-formatted value.  This drops the screen's second-numeral
requirement and all three surface strata, which are the conditions that select
for baseline tables.  The sample is uniform over the missed set; intervals are a
cluster bootstrap over source papers.

## 4. A check that did not work, reported for completeness

`scripts/verify_provenance_number_trace.py` attempts a model-free reference by
asking whether a value a citing paper prints for another system occurs verbatim
in that system's own paper.  It does not discriminate: the placebo rate,
computed against randomly drawn non-cited papers, is as high as the true-target
rate, because short numerals collide and table extraction is lossy.  The script
and its output are released so that the negative result is inspectable, and no
manuscript claim rests on it.
