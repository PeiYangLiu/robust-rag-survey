# Cross-paper comparability cases — codebook

Artifacts:

- `cross_paper_comparability_cases.csv` / `.json` — the case ledger (15 rows)
- `cross_paper_comparability_cases_summary.json` — compact per-case table rendered into the main paper table
- `cross_paper_comparability_cases_report.md` — narrative write-up with the three strongest cases in full
- `../scripts/verify_cross_paper_cases.py` — deterministic verifier; exits non-zero on any mismatch

## What a case is

A **case** is one juxtaposition of two reported robust-RAG results that a reader
of the published literature would treat as a comparison, together with the audit
verdict on whether that comparison is answerable as stated.

Two kinds are admitted, recorded in `comparison_type`:

- `DIRECT` (10 cases) — one paper reports its own number beside a number
  attributed to another paper, e.g. a baseline row copied from that paper or a
  sentence of the form "X achieves N whereas our method …".
- `SURVEY-INVITED` (5 cases) — a survey or benchmark groups two systems under a
  single label ("noise robustness", "faithfulness", "attack success rate",
  "abstention") such that a reader would rank their headline numbers.

`case_class` separates the two populations that must not be pooled:

- `cross_paper` (12) — the two sides come from different papers. These are the
  cases the paper's headline claim is about.
- `within_harness_control` (3) — both sides come from one paper, measured under
  one corpus, retriever, generator and metric. These are negative controls: an
  audit that flagged these would be useless.

## Fields

| Field | Meaning |
|---|---|
| `case_id` | Stable identifier, prefixed by domain (`SEC`, `NOISE`, `FAITH`, `CALIB`) |
| `case_class` | `cross_paper` or `within_harness_control` |
| `domain` | Literature area the comparison sits in |
| `comparison_type` | `DIRECT` or `SURVEY-INVITED` |
| `comparison_claim` | The juxtaposition as a reader would state it |
| `side_A_paper`, `side_B_paper` | Citation keys resolvable in `../references.bib` / `../auto_references.bib` |
| `side_A_name`, `side_B_name` | Short system labels used in the paper table |
| `side_A_number`, `side_B_number` | **Verbatim** reported value with metric, dataset and model |
| `naive_gap` | The difference a reader would compute from the juxtaposition |
| `mismatched_coordinates` | Which of C1–C5 differ, semicolon separated |
| `mismatch_evidence_A`, `mismatch_evidence_B` | Short quotation from each side documenting the mismatch, with file and line numbers |
| `corrected_reading` | What remains defensible after restricting to the common scope |
| `matched_number` | The coordinate-matched value, or `not_recoverable_from_text` |
| `numeric_consequence` | One-line quantified statement of how the conclusion changes |
| `conclusion_change` | Verdict, see below |
| `provenance` | File paths and line ranges for every quoted value |

## Coordinate vocabulary

- **C1 evidence state** — what the evidence condition is (irrelevant,
  insufficient, conflicting, stale, weakly sourced, malicious), which corpus
  snapshot, which retriever, which distractor or conflict construction.
- **C2 origin / capability** — how the condition arose: natural retrieval error
  versus an adversary, and the adversary's corpus write access, query
  knowledge, retriever visibility, insertion budget, persistence and objective.
- **C3 intervention** — what was changed: context filter, generator training,
  reader prompting, retrieval policy, defense, certification.
- **C4 outcome** — the measured quantity and its unit: exact match versus
  substring accuracy, attack success rate versus retrieval hit rate,
  span-level versus response-level, coverage-conditional versus unconditional.
- **C5 policy / utility** — the action set and loss: answer, re-retrieve,
  verify, abstain, escalate, and the relative price of an error, an abstention
  and additional compute.

## Verdict vocabulary (`conclusion_change`)

| Verdict | Meaning | Count (cross-paper) |
|---|---|---|
| `undefined` | No common scope exists; the quoted gap is uninterpretable as stated | 6 |
| `narrows` | The comparison survives only on a strict subset of the conditions both papers cover | 4 |
| `survives` | The comparison is valid as stated; all decision-relevant coordinates match | 2 |

`reverses` is defined but is not used as a standalone verdict: where matching a
coordinate flips the ordering, the case is recorded as `undefined` when a second
coordinate also differs, with the reversal quantified in `numeric_consequence`.
SEC-02 is the clearest instance — the ordering reverses at a matched insertion
budget, but the two papers also measure different objectives, so the comparison
is not merely reversed but unanswerable.

## Evidentiary standard

1. Every number in `side_A_number`, `side_B_number` and `matched_number` is
   copied verbatim from a locally extracted full text under
   `../citation_audit/expanded_texts/` or `../citation_audit/texts/`, and the
   `provenance` field records the file and line range.
2. `verify_cross_paper_cases.py` re-opens every cited range and asserts that the
   quoted snippet and each quoted numeral literally occur there. It currently
   performs **70 checks, all passing**. Any case whose value could not be
   verified was dropped rather than estimated.
3. Where a paper reports no operating point at the other side's setting,
   `matched_number` is `not_recoverable_from_text` (7 of 15 entries). No
   coordinate-matched value is ever inferred, interpolated or read off a figure.
4. Coding of `mismatched_coordinates` and `conclusion_change` is by the authors
   and is single-coded. This is a limitation stated in the paper: the cases
   establish that the failure mode occurs and can be decisive, not how often it
   occurs.

## Selection and its bias

Cases were located by searching the extracted full texts for number-bearing
comparison sentences (baseline tables, "compared with", "outperforms", metric
names) and required both sides to be present locally with an explicit number.
Selection therefore favours open-access and widely cited work and is **not** a
random or exhaustive sample of the literature. Domain coverage was constrained
in advance to span security/poisoning, noise robustness, faithfulness, and
calibration/abstention so that the cases are not drawn from one area.

## Reproduction

```bash
python scripts/verify_cross_paper_cases.py     # re-checks every quoted value
python scripts/build_revision_tables.py        # regenerates the paper tables
```
