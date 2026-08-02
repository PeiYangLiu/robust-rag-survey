# Pre-registered protocol: paper-disjoint held-out human validation

> **Exclusion notice (2026-07-26).** This locally frozen document is retained
> as a design-audit artifact, not as evidence of a completed human study. The
> roster/calibration lineage and later de-identified outcome export do not have
> an independently verifiable real-participant package. No participant
> attribute, response, reference label, contrast, or derived statistic from
> that lineage enters the manuscript.

**Current status: DESIGN AUDIT ONLY / HUMAN COLLECTION EXCLUDED**  
Protocol version: `v3.0.0-preregistered`  
Freeze date: 2026-07-15

### Pre-label administrative amendment (2026-07-16)

After initial sampling screening but before replacement screening, test-claim
freeze, assignment, or any test response, a dry run showed that the earlier
global regeneration approach would renumber already screened candidates. It is
superseded by the ledger-driven append-only workflow in Sections 3.2--3.3.
This integrity repair changes no target size, stratum balance, outcome,
estimand, effect threshold, alpha, analysis rule, or test label. The
replacement batch timestamp, parent hashes, retained-row invariants, and new
namespace are frozen in `source_replacement_summary.json`.

RB-001 screening then showed that a promoted source was itself deficient.
Before any test claim or outcome, the same amendment was extended from one
batch to an iterative chain: RB-002+ must anchor and preserve every prior batch
and may alter only the currently deficient active source. This is an audit and
identity-preservation correction, not a change to the confirmatory design.

### Pre-label calibration implementation record (2026-07-17)

Before any test label, an administrative review found that the reported
calibration passes for 29 planned participants had been retained only as
conclusions. The item-level prompts, responses, correctness fields, and
completion records required by Section 6 were absent. Those conclusions are
therefore **not recognized as protocol-compliant passes**. All 29 public
statuses are reset to `awaiting_calibration`; no participant response or test
label is imputed. The fixed implementation below operationalizes the already
preregistered ten-item, two-dimension, 80%-per-dimension rule without changing
an endpoint, threshold, arm, estimand, or test item.

On 2026-07-18, a pre-response code review found participant-facing diagnostic
text and a release check that trusted a summary without reconstructing the
ledger. Calibration implementation `v3.0.1-calibration-freeze` removes every
item-specific hint, refreezes the same ten instructor cases with new hashes,
and makes formal packet release depend on complete ledger reconstruction. No
calibration response, pass, test response, endpoint, threshold, arm, estimand,
or frozen test item was created or changed by this correction.

### Frozen calibration completion record (2026-07-18)

After that correction, all 29 planned participants completed round 1 before
receiving any formal test packet. The retained ledger contains exactly 290
item responses; both dimensions were at least 8/10 for every participant, all
public statuses are `passed_round_1`, and inclusion is
`pending_test_completion`. The summary and release gate are mechanically
recomputed from those records. All arm, gold, and adjudication response files
remain header-only, so this is calibration-passed-before-test, not collected
test data.

### Pre-label staged-workflow integrity amendment (2026-07-18)

Before any formal packet was distributed, code review found that the proposed
participant-side stage-1 executable embedded the later output vocabulary and
treated participant-recomputable state as its hash root. That unissued
implementation is superseded by `v3.0.0-staged-review-v2`. Stage 1 now contains
only extraction files/instructions/minimal configuration; the coordinator
independently reconstructs immutable rows, issues stage 2, mediates every
correction, and receipts final rows. The same review aligned incomplete-gold
and zero-observation fail-safe handling across builder, validator, and
analysis. No formal response, label, endpoint, arm, threshold, estimand, test
claim, or assignment changed.

A final pre-distribution review of staged v2 required two additional
coordinator safeguards. Every superseded `composition.csv` is now copied to a
collected-only coordinator archive; its relative path and SHA-256 are repeated
in correction schema `coordinator-extraction-correction-v2.1` and issuance
registry schema `composition-issuance-registry-v2.1`. Issuance, collection,
and strict collected validation require that archive and rehash it. The
archive is absent from frozen and portable reviewer packages. In addition,
issuance times must be nondecreasing over extraction versions, the correction
time must equal the new issuance time, and each active response must satisfy
issuance/lock ≤ composition start ≤ composition completion ≤ coordinator
receipt. These are integrity constraints on the same unissued workflow; they
change no planned response or analysis.

### Pre-test administrative text correction (2026-07-18)

Before any stage-1 packet was distributed and while every formal response file
was header-only, the coordinator found C0 control bytes in the frozen text for
`H3-065-14` (`rrag015`). The authoritative arXiv HTML at
<https://arxiv.org/html/2506.04390v2> gives exact alttext
`1.8\times 10^{4}` and `\left(\sim\times 10^{3}\right)`; the corresponding
locator is PDF p18, Table 8 caption. The claim and evidence excerpt are
administratively normalized to:

> The runtime reaches up to 1.8 × 10⁴ seconds, which is several orders of
> magnitude (∼ × 10³) higher than the runtime of the existing attack Poison,
> as reported in (Zou et al., 2024).

`frozen_text_corrections.csv` is the append-only
`frozen-text-corrections-v1` record, recorded at
`2026-07-18T11:17:02Z`. It stores each old UTF-8 value as base64,
its byte SHA-256, the new visible text, provenance/reason, timestamp, field
mirrors, and a canonical record hash. This makes the pre-correction candidate,
human-screen, frozen-claim, sampling, and replacement-chain artifacts exactly
reconstructable. The selected old value's byte SHA-256 is
`b41006215a300cd984ab8651b50a1df9cf05c7c228271b47022e42082fc4101c`.
The selected correction is one of 12 field records across 11
candidate IDs: the other ten candidate IDs were already ineligible and never
entered the test sample; their remaining C0 values are replaced only by
literal visible `⟦U+XXXX⟧` tokens, with no semantic reconstruction asserted.
Together these records remove 33 control-bearing parsed cells from the
complete package.

The correction changes no claim/source ID, source membership, C2/C5 stratum,
sampling decision, assignment, endpoint, or label. `auditor_assignments.csv`
remains byte-identical (SHA-256
`ae50cb9a729f319ca713478e0dcc6d8e0ea50bbb9b516a15f6c80ffc39e9427c`).
The 27 unissued stage-1 directories were rebuilt from the corrected immutable
text (7,200 extraction rows, zero labels). The coordinator registry changed
from `fb65fcc8ee97bfb364b64c0e01c8b3150cbcdb8d926e38a8c84f7396877503a6`
to `50dfa5a7b348686f593ba9d0e73b0990bb67a51b42624aed79d15422f821b7ec`;
both hashes and the reversible artifact preimages are retained in
`sampling_freeze_summary.json`.

## 1. Prospective boundary and research question

This protocol was frozen before viewing or collecting any held-out test
response. The test is **paper-disjoint from all identifiable v1/v2 claim-level
development and validation sources**. This includes every nonempty
`paper_a_id` and `paper_b_id` in the v1/codebook-development lineage recorded
by `manuscript/supplement/validation_pair_provenance.csv`, plus the fixed nine
v2 source keys. At this freeze the inputs contain 106 unique pair-provenance
keys and nine fixed keys, with four overlaps, yielding 111 unique exclusions.
The companion title registry has 109 unique normalized titles and identifies
two same-paper cross-key aliases.
Their claims, labels, disagreements, and adjudications cannot enter the new
test set, gold process, training answer key, or stopping decisions.

The broader Map B literature did inform domain concepts and vocabulary during
the survey and codebook-development process. A paper's presence in Map B alone
does not make it a claim-level development source and is not, by itself, an
exclusion. Consequently, this study claims paper-disjointness from the
identifiable v1/v2 claim-level development and validation lineage, **not** that
the held-out papers were wholly unseen in the broader literature map.

The confirmatory question is whether adding the two prompts unique to the full
v3 procedure improves human comparability-label exact accuracy over the same
v3 evidence-and-control procedure with those prompts removed, on a prospectively
frozen set of claims for which those prompts could matter.

The original candidate design was 360 claims from 60 sources. The deterministic
planning approximation in `power_analysis.py` finds power below .80 in
conservative combinations of discordance and source ICC. The most conservative
scenario requires 468 claims from 78 six-claim sources under that
approximation. We choose **480 claims from 80 sources** because it exceeds that
minimum and permits exact 3-of-6 balanced incomplete blocks in every arm.

The package will not claim that simulated or approximated power is an empirical
result. It is a design calculation conditional on stated assumptions.

## 2. Outcomes remain separate

Every procedure produces two outputs:

1. **Evidence-support label:** whether the cited source supports the claim as
   written.
2. **Comparability label:** whether the compared sides answer the same
   scientific question under assumptions adequate for the stated scope.

No rule, analysis, table, or adjudication may combine these into one verdict.
The primary endpoint is comparability-label exact accuracy. Evidence-support
accuracy is a distinct secondary endpoint and a diagnostic negative-control
comparison for Arms C and D.

## 3. Source frame and paper-disjoint sampling

### 3.1 Source eligibility

A source is eligible only if all of the following hold before claim sampling:

- it is in the frozen parent corpus snapshot identified in
  `source_sampling_frame.csv`;
- stable full text can be archived and hashed;
- it contains at least six potentially eligible comparison claims;
- it is not a duplicate, earlier version, companion appendix, or overlapping
  report of a development source;
- its `source_key` is not in the generated
  `DEVELOPMENT_SOURCE_KEYS.txt`;
- its normalized title is not in generated `DEVELOPMENT_SOURCES.csv`; and
- no author overlap or shared experiment makes it the same study report as a
  development source.

The last two checks implement paper-level, not merely row-level, disjointness.
`build_development_source_keys.py` deterministically unions both paper-ID
and title columns from `validation_pair_provenance.csv` with the fixed nine v2
keys and their titles from the prior 80-claim
`analysis_results/final/human_final_consensus.csv`. Title normalization applies
Unicode NFKD, case folding, removal of combining marks, replacement of every
non-alphanumeric character by a space, and whitespace collapse.
`validate_package.py` recomputes both artifacts, checks both upstream file
hashes against `study_config.json`, and rejects an out-of-date exclusion file.
It checks the source frame, model-prescreen candidates (via their source-frame
join), and frozen tests by both key and normalized title. Two distinct
eligible, candidate, or test source keys with the same normalized title cause
validation failure rather than silent deduplication.
All exclusions use a frozen reason code plus free-text detail. Permitted source
reason codes are `DEV_SOURCE_OR_COMPANION`, `DUPLICATE_REPORT`,
`NO_STABLE_FULL_TEXT`, `FEWER_THAN_SIX_ELIGIBLE_CLAIMS`,
`OUTSIDE_FROZEN_CORPUS`, and `OTHER_PREDECLARED_ELIGIBILITY_FAILURE`.

### 3.2 Source-diverse deterministic selection

Before selection, the coordinator freezes the complete source frame, corpus
snapshot identifier, full-text SHA-256, eligibility status, exclusion reason,
and diversity stratum. Diversity strata are formed from the pre-existing
`venue_family` and `publication_status` fields; they are not outcomes. The
stored value is the exact trimmed concatenation
`venue_family + "::" + publication_status`, preserving case.
For this Map B snapshot, `venue_family` is the exact `source_or_venue` value.
`publication_status` is `preprint` for `arxiv_or_preprint`/arXiv rows and
`venue-linked` otherwise. Stable URL, year, and title come directly from Map B.
The corpus snapshot hashes the 342-row Map file and every available
`expanded_texts/<source_key>.txt`; no model output enters source eligibility.

Within each stratum, sources are ordered by
`SHA256("2026071501|source|" + source_key)`. Selection proceeds in round-robin
passes over lexicographically ordered nonempty strata until 80 eligible sources
are selected. A stratum is skipped only when exhausted. This rule prevents a
large stratum from filling all positions while remaining fully reproducible.
The stored `deterministic_source_rank` must match that order. No source may
contribute more than six claims.

No capability/policy/control quota is permitted. In particular, a 30/20/30
source allocation is not the preregistered design and must not be substituted
for the SHA-256 round-robin. `prepare_candidate_pool.py` implements the
round-robin and marks all remaining eligible sources as ordered reserves.

If a selected source proves ineligible before any test response is opened, it
is replaced by the next source in the same stratum, or the next global
round-robin source if that stratum is exhausted. The original row and reason
remain in the frame. Replacement after any test response is forbidden.
Before test labels, a source with fewer than six human-confirmed decisive
claims is recorded in the hashed ledger. **The global pool script is not
rerun.** Doing so would change source-selection ranks, `H3-*` IDs, and
candidate-record hashes for already screened sources. The legacy
`--replacement-exclusions` path therefore fails closed.

`apply_source_replacements.py` applies only ledger-specified mappings. A
deficient source is marked excluded and its candidate rows are removed; every
other source-frame row and every retained deterministic/human candidate row is
copied without changing any field. The reserve inherits the deficient
source's frozen slot. Its candidates are extracted from the same hashed text
snapshot and appended under the independent
`H3R-<ledger-event-number>-<within-source-rank>` namespace. Existing IDs are
never reused, renumbered, or rehashed. `source_replacement_summary.json`
is an append-only `RB-001..N` chain. Every batch anchors the full prior summary,
the prior batch outputs, the cumulative ledger and new ledger suffix, the
active 80 slots, new text hashes/counts, and separate byte-equivalence hashes
for every immediate-parent active source not replaced in that batch. A later
batch may replace a source introduced by an earlier batch; only that source's
rows are removed. Earlier batch records and every other original or
replacement-source row remain unchanged. The freezer may append another
ledger suffix after a completed replacement screen, but repeated freezing
before application is idempotent and cannot duplicate the pending event.

### 3.3 Candidate claims and decisive strata

`candidate_claims_deterministic.csv` is generated before model prescreening.
The frozen model-free extractor scans section-aware sentences for explicit
comparative/effect cues, preserves exact quotation, adjacent sentences,
section, PDF page, source text SHA-256, and a canonical candidate-record hash,
then orders by result-section priority, cue score, page, and source sequence.
Operational pool eligibility requires at least 12 such nominations, providing
screening headroom for the six eventual decisive claims. The initial 80
round-robin sources contribute at most 20 nominations each.

Candidate extraction must preserve the exact claim, adjacent context, source
location, source excerpt, and source-file hash. An LLM or synthetic process may
nominate candidates only. If one is used, its row is marked
`SYNTHETIC_OR_MODEL_ONLY_PRESCREEN_NOT_HUMAN_LABEL`; model fields are never
copied into a sampling or rating packet or treated as a human observation.

The active frozen workflow uses no model prescreen.
`build_sampling_screen_packets.py initialize` maps all deterministic raw fields
into `candidate_claims_model_prescreen.csv`, leaves every model
system/version/prompt/seed/score/rationale field empty, leaves every human
field empty, and marks each row
`MODEL_FREE_SCREENING_INPUT_NOT_MODEL_OR_HUMAN_LABEL`. The legacy filename and
columns are retained only for schema/freeze compatibility. This status is not
a model label, human label, gold label, or test outcome.

The nomination request records prescreen seed `2026071505`, system/version,
prompt hash, and returned rationale. A provider's failure to honor a seed is
reported rather than described as deterministic; the archived rows, not a
claim of exact model replay, define the prescreen record.
The legacy columns named
`prescreen_c2_decisive_probability` and
`prescreen_c5_decisive_probability` contain only model-self-reported ranking
scores constrained to [0,1]. They are not calibrated probabilities and are not
used in power calculations. Qwen output, if imported, is nomination-only.
`prepare_candidate_pool.py --import-model-prescreen` requires exact candidate
coverage and leaves every `human_sampling_*` field empty.

Two mutually distinct sampling screeners then independently assess every
candidate from the raw source. This is a sampling decision, not an
evidence-support or comparability label. Each receives a separate full-coverage
packet containing only candidate ID, raw claim/source evidence and hashes,
their own anonymous ID, and empty `eligibility_vote`, `screening_reason`,
`source_checked`, and completion-time fields. They do not see model fields,
proposed strata, or the other screener's response. `source_checked=yes`, a
nonempty reason, and a completion timestamp are required. A claim is:

- **C2-decisive** when the claim transfers, ranks, or generalizes across how an
  evidence disturbance arose or what access/budget/knowledge produced it, and
  changing only that fact could change the defensible comparison scope.
- **C5-decisive** when the claim recommends, ranks, or transfers an action or
  operating point and its defensibility could change with coverage, available
  alternatives, stakes, or costs.

Matching initial votes are merged as `human_screen_consensus`. Any difference
among `eligible_c2`, `eligible_c5`, and `ineligible` is a dispute.
`merge-initial` creates a third packet containing exactly those disputed rows,
with no initial vote or rationale. A third sampling screener, whose anonymous
ID differs from both initial screeners, independently checks the source and
casts one of the same three votes. For an initial dispute, this preregistered
tiebreak vote is final even if it is the category chosen by neither initial
screener; authors do not select among the three responses. `merge-tiebreak`
records the result as `human_screen_tiebreak`.

Replacement candidates follow the same blind procedure but are a strict
subset. `build-replacement` reads the current hashed `RB-*` record and sends
only IDs under that batch's new ledger prefix(es) to the same two initial
screeners. It never reissues an earlier `H3R-*` row.
`merge-replacement-initial` sends only current-batch disputes to the same third
screener, and `merge-replacement-tiebreak` completes them. The three anonymous
IDs must exactly equal the original IDs. Every merge hashes and compares all
rows outside the current batch before and after; changing any retained
original or earlier-replacement candidate ID, raw field, candidate-record
hash, or human field is a hard failure. These replacement screening decisions
remain sampling administration, not test outcomes.

Claims meeting both substantive definitions within a screener's assessment
must receive the one category that the screener judges more decisive; the
screener records the reason. No model score or coordinator quota resolves
this choice. The later global 240/240 allocation operates only over the final
human categories and frozen hash order.

The two primary sampling reviewer IDs must be nonempty and different.
`selection_status=human_screen_consensus` requires an empty tiebreak ID;
`human_screen_tiebreak` requires a third ID distinct from both primary
screeners. While disputes remain, their rows are explicitly
`awaiting_human_sampling_tiebreak` and cannot be frozen.
`sampling_screen_summary.json` records every issued/completed input and output
artifact SHA-256, row count, anonymous screener IDs, administrative counts,
and a canonical stage-record hash. Every stage records
`test_outcomes_generated=0`; `MANIFEST.sha256` supplies the summary file's
nonrecursive hash. `freeze_human_sample.py` accepts only a fully
merged candidate file whose hash and row count equal the summary's
`human_sampling_screen_complete` state; it rejects every other status or
identity combination.

Within each source and stratum, eligible candidates are ordered by
`SHA256("2026071502|claim|" + candidate_claim_id)`. The target is exactly 240
C2-decisive and 240 C5-decisive claims, exactly six claims from each of 80
sources. A source unable to supply six jointly eligible claims is replaced
before labels, rather than padded with non-decisive claims. Failure to accrue
this set by the pre-label freeze is a recruitment failure; it does not permit
post hoc dilution, effect-size changes, or a smaller confirmatory sample.
The freezer first computes each source's feasible C2 count interval, starts as
close as possible to three C2 and three C5 claims, and deterministically adjusts
source allocations in hash order until the global 240/240 target is reached.
Within source and stratum it uses only the frozen claim hash order. Model
scores, rationales, systems, and versions are never read by the allocation
logic.

For every selected row, `sampling_record_sha256` is SHA-256 of a compact,
key-sorted UTF-8 JSON object containing deterministic raw candidate fields,
the deterministic record hash, sampling reviewer IDs, final human eligibility,
human stratum, and consensus/tiebreak status. It explicitly excludes every
`prescreen_*` value, model rationale, and model status. The validator
recomputes this link and requires all raw claim/source fields to be unchanged.

Claim exclusions use `DUPLICATE_CLAIM`, `NOT_A_COMPARISON`,
`NOT_DECISIVE_AFTER_HUMAN_SCREEN`, `INSUFFICIENT_LOCATABLE_SOURCE_CONTEXT`,
`SOURCE_REPLACED`, or `OTHER_PREDECLARED_ELIGIBILITY_FAILURE`. All candidate
rows, selection statuses, ranks, and reasons are retained.

### 3.4 Realized prepared pool (administrative, not labels)

Initial preparation produced 342 source-frame rows, 170 eligible sources,
80 initial sources, 90 reserves, and 1,568 deterministic nominations. Human
screening identified three deficient sources and the frozen ledger specified
`rgb2023 -> rrag175`, `rrag149 -> rrag161`, and
`rrag010 -> rrag142`. Stable application removed 46 deficient-source
candidates, preserved all 1,522 rows from the other 77 sources byte-for-byte,
and appended 53 `H3R-*` candidates (13, 20, and 20). Their completed screening
found only four C2 and one C5 claim for `rrag175`; SR-004 therefore fixed
`rrag175 -> rrag137` at slot 1. RB-002 removed the 13 `H3R-001-*` rows,
preserved all 1,562 rows from the other 79 active sources byte-for-byte, and
appended 20 model-free `H3R-004-*` rows. The current state is
`awaiting_replacement_screen`; those 20 reviewer/vote/stratum fields are
empty, no test label is present, and `frozen_test_claims.csv` remains
header-only.

## 4. Four independent arms

Each arm receives the same raw claim text, adjacent context, source title,
stable locator, excerpt, and source-file hash. Packets contain no model score,
model rationale, model-coded field, sampling stratum, other-arm response, gold
response, or prior-study label.

- **Arm A — conventional full-text source verification.** Reviewers inspect
  the source, verify the result, scope, numbers, causal wording, and ordinary
  experimental controls. They receive no PICO or v3 coordinate prompts.
- **Arm B — PICO-style plus standard controls.** Reviewers independently
  extract population/setting, intervention, comparison, outcome/unit, and a
  standard experimental-control checklist. They receive no v3 coordinate
  names or model fields.
- **Arm C — v3 evidence and controls, C2/C5 ablated.** Reviewers use the v3
  evidence-support gate, evidence condition, intervention, outcome/unit, and
  claim-specific controls. They receive no dedicated origin/capability or
  policy/utility prompt, definition, extraction column, or imputed value.
  Raw source facts are not redacted, so this estimates a prompt/schema
  ablation rather than impossible erasure of reviewers' background knowledge.
- **Arm D — full v3.** Reviewers use the frozen evidence-support gate, all five
  v3 diagnostic prompts, and claim-specific controls.

All arms use the same two output vocabularies solely to make exact accuracy
measurable. Arm instructions and extraction forms remain independently
implemented; no arm is generated by hiding columns from a completed full-v3
record.

`build_staged_review_packets.py` generates one stage-1 directory per anonymous
auditor and gold expert only after claims, assignments, the role roster, and
the complete calibration ledger are frozen. Packets contain the common raw
evidence plus only that participant's extraction schema; they exclude
composition fields, model fields, coordinator-only strata, other-arm
responses, and gold responses. Generated packets are ignored working
artifacts, not committed labels. Adjudicator packets are not generated at this
stage.

## 5. Participants, assignment, and independence

The primary roster contains 24 auditors, with six assigned to each arm.
Anonymous IDs are sorted and then randomized with seed `2026071503`.
`build_assignments.py` assigns each auditor to exactly one arm. A participant
cannot rate, train, supervise, or adjudicate another test arm.
Public IDs are random study codes and must not encode names, initials,
affiliations, email handles, or recruitment order.

Within each arm, every claim receives exactly three independent judgments. For
each 20-claim superblock, all 20 possible 3-of-6 auditor triples are used once.
Thus every auditor rates ten claims and every auditor pair co-rates four claims
per superblock. With 480 claims, each auditor rates 240 claims in one arm and
each within-arm auditor pair co-rates 96 claims. Claim order and block order
are deterministic functions of the frozen seed and IDs. The script hard-fails
on incomplete coverage, cross-arm reuse, duplicate ratings, source-count
violations, or workload/pair imbalance.

Reserve auditors may replace a participant only before that participant sees a
test packet. The replacement receives the same anonymous slot and completes
calibration. Once any test response is opened, partial work is retained and
handled as missing; it is not reassigned selectively based on content.

Before collection, the coordinator must archive the applicable institutional
ethics determination, informed-consent record, compensation plan, withdrawal
procedure, and conflict declarations. Those records and filled private
metadata are access-controlled and are not part of the public artifact.

### 5.1 Public frozen reviewer validation boundary

A standalone reviewer ZIP may run explicit
`validate_package.py --mode frozen --portable` without any private roster. This
is a public structural check only. It uses the exact non-PII anonymous roster
to verify 29 mutually distinct role identities, 24 auditors with six per arm,
three gold experts, two adjudicators, deterministic balanced assignments, the
480/80/6 frozen design, frozen calibration hashes, and zero formal responses.
It accepts exactly two calibration substates: (A) zero ledger rows, 29
`awaiting_calibration` statuses, and a closed gate; or (B) exactly 290
round-1 ledger rows, 29 `passed_round_1` statuses with
`pending_test_completion`, and
`OPEN_CALIBRATION_PASSED_NO_TEST_RESPONSES`. Both use the same non-PII
calibration state/ledger validator as strict mode, including immutable fields,
global response IDs, score recomputation, summary item results, and roster
hash/status checks. A summary alone is never sufficient. A public roster
containing a legal-name, contact, affiliation, consent, compensation,
conflict, or private-notes field is invalid.

The portable v3 directory is limited to a fixed source-code allowlist whose
authorized files also appear in `MANIFEST.sha256`. The private roster template
must be strictly header-only. A populated template, another private metadata
file, any bundled `expanded_texts` path, or any other unlisted file is a
validation failure; rewriting the manifest cannot make such a path valid.
The full working repository may contain ignored generated calibration and
stage-1 participant packets; those directories are deliberately rejected by
portable validation and omitted from a standalone reviewer ZIP assembled from
the manifest.

Portable frozen output must identify third-party full texts and private
legal-name/contact/consent/compensation-locator verification as
`external_input_skips`. It must state that the latter was **not verified in
portable mode** and must not imply that private ethics records passed.
Checking the exact private schema and required legal-name, contact,
consent-date/locator, and compensation-locator fields remains exclusive to
strict full-repository frozen validation with `--participant-metadata`. Portable
`collected` and auto-detected modes are prohibited; prepared portable
validation remains available. This reviewer check does not weaken or replace
the strict private-roster freeze validation. Strict frozen validation also
requires the private and public rosters to have exactly the same 29 participant
IDs, roles, assigned arms, and replacement statuses, including all gold and
adjudicator records.

For source replacement, the public reviewer check does not regenerate text.
It verifies both frozen batch schemas and canonical record hashes, hashed
ledger prefixes, parent-to-output and prior-summary continuity, active slots,
current packaged artifact hashes/counts, each batch's retained-row invariants,
replacement namespaces/source hashes, and sampling-stage anchors. Its scope is
reported as `frozen internal chain/hash verification; no full-text
regeneration`. Strict full-repository frozen validation must instead rebuild
the replacement candidates for every batch from archived `expanded_texts` and
must fail if any required replacement text is unavailable.

## 6. Training and calibration

Training uses development or external calibration sources that are absent from
the test frame. All training and calibration responses are retained in
`calibration_responses.csv`, including participant ID, arm, item, response,
feedback code, completion time, and pass status. Calibration answer keys may
be constructed by instructors but are never test labels.

Auditors must pass a fixed criterion of at least 80% on each of the two
separate output dimensions over the final ten calibration items. One
predeclared retraining attempt is allowed. Failure after retraining excludes
the auditor before test release and invokes the reserve rule. Thresholds,
items, and responses cannot be changed after test packets are opened.
Gold experts and adjudicators complete a separate plain-rubric calibration
with the same per-dimension threshold and retained responses; they never
receive the v3 coordinate materials.

The frozen implementation is `v3.0.1-calibration-freeze`:

- `calibration_items.csv` contains ten fictional, instructor-constructed,
  self-contained dossiers under `CAL-*` identifiers. They are not papers,
  future test sources, or human test gold. Each uses a neutral title and
  supplies only the complete raw excerpt, table, setup, claim, and locator.
  Item-specific calculation, diagnostic, and comparison questions are
  prohibited from participant-visible materials.
- `calibration_answer_key.csv` is a coordinator-only instructor key. It may be
  retained in the reviewer artifact for reproducibility but is never copied to
  a participant packet. Its labels are calibration answers, not test labels.
- Every item and the ten-item set have canonical SHA-256 records. The builder
  rejects any calibration item/source identifier or content that reuses a
  frozen test claim or source identifier.
- All participants receive the same ten dossiers in an order determined by a
  hash of anonymous participant ID and item ID. Auditors receive only their
  assigned arm's general instructions. Arm C has no C2/C5 name or dedicated
  origin, capability, attacker-access, budget, policy, utility, cost, stakes,
  or coverage prompt/schema field. Raw dossier facts remain unredacted, as in
  the formal test. Arm D has the full general frozen v3 guidance but no
  item-specific hint. Gold experts and both adjudicators receive only the
  marked plain-language rubric and no C1--C5 vocabulary.
- A completed round must contain exactly one independently identified response
  to every frozen item, with all packet-invariant fields unchanged. Evidence
  and comparability are scored separately; at least 8/10 is required on each.
- A first-round failure deterministically becomes
  `retraining_required_round_2`. The sole allowed retraining uses the same
  items and key; neither may be selected or revised in response to performance.
  Passing round 2 yields `passed_round_2`; a second failure yields
  `exclude_before_test` and invokes the preregistered reserve rule.
- `calibration_responses.csv` is the item-level append-only scoring ledger.
  `calibration_summary.json` contains anonymous per-round and per-item
  correctness records and hashes the ledger and non-PII public roster. A
  conclusion-only pass can never satisfy this gate.
- Assignments may be constructed while calibration is pending. Test packet
  construction and collected-mode validation are prohibited until the real
  ledger is parsed and reconstructs legal round transitions, globally unique
  response IDs, both per-dimension thresholds, exact public-roster
  IDs/status/hash, and 29 complete ten-item final rounds. Summary item results
  must equal a full recomputation from that ledger and the frozen key; a
  header-only ledger plus a fabricated passing summary cannot release packets.

Generative AI is prohibited for auditors, gold experts, and adjudicators.
Full-text search, calculators, and non-generative reference tools are allowed
and logged consistently across arms.

## 7. Lock extraction before composition

For every arm, the coordinator releases two sequential stages:

1. **Extraction:** source-linked facts and arm-specific fields are entered.
2. **Composition:** only after extraction is submitted, the reviewer assigns
   the two separate output labels and reasons.

The extraction snapshot is timestamped and hashed before composition prompts
appear. Edits require an append-only correction record; the original remains
available. This separates field/fact extraction error from label-composition
error. It does not imply the two errors are statistically independent.

The frozen staged implementation is `v3.0.0-staged-review-v2`:

- The initial participant directory contains exactly `extraction.csv`,
  `instructions_stage1.md`, and minimal `stage1_config.json`. It contains no
  executable CLI, composition field, output label/string/definition, or
  stage-2 instruction. `coordinator_packet_registry.json`, which is never
  distributed as a participant packet, freezes the independently
  reconstructed participant/role/arm, ordered IDs, immutable-row roots, and
  hashes of every stage-1 file. Its file hash is in `MANIFEST.sha256`;
  participant configuration is not a trust root.
- Participants return extraction only. `issue_composition_packets.py`
  reconstructs all immutable fields from frozen claims, assignments, the
  public role roster, and the coordinator registry; requires nonblank
  arm/plain-gold extraction (`unknown` and `not_applicable` are explicit);
  fills coordinator completion UTC; and computes
  `coordinator-extraction-row-v2` hashes.
- Only after that coordinator check is a versioned stage-2 directory issued
  with `locked_extraction.csv`, `composition.csv`,
  `instructions_stage2.md`, and `stage2_config.json`. This is the first
  participant-visible appearance of the two output vocabularies.
- Frozen validation has two post-calibration substates:
  `frozen_calibration_passed_before_composition_issuance` has no issuance,
  while `composition_issued_no_responses` has exactly 27 active chains and
  7,200 active rows but no coordinator response receipt or formal response.
  Issuance alone is not collection. Strict validation of the second state
  requires `--composition-packets-root` and rehashes all four files for every
  issuance version, including identity, version, order, and row-count checks.
  These external participant directories never enter the package manifest.
  Portable frozen validation omits them, verifies only the internal
  registry/row/correction chain, and explicitly records that packet bytes
  were not verified. The unchanged `NO_FORMAL_RESPONSES` receipt is treated
  only as a zero-response pre-issuance sentinel; collected status requires a
  new coordinator receipt that anchors completed final responses.
- `collect_final_responses.py` distrusts participant-written hashes and state.
  It verifies returned raw/locked fields against the coordinator issuance row
  ledger, recomputes hashes, enforces labels, reasons,
  narrowing/scope/missing-information and UTC rules, and writes canonical
  arm/gold responses plus per-row `coordinator_response_receipts.csv` and a
  file-level `coordinator_collection_receipt.json`.
- Any extraction amendment is returned to the coordinator with the prior
  composition. The coordinator preserves the prior stage-2 directory, copies
  the returned composition into
  `coordinator_invalidated_composition_archive/`, and appends a
  `coordinator-extraction-correction-v2.1` record linking old/new issuance
  roots plus the archive-relative path and SHA-256. The
  `composition-issuance-registry-v2.1` archive index repeats those anchors.
  Missing or changed archives invalidate issuance, collection, and strict
  validation. A strict full-package issued state retains any correction
  archive; a portable reviewer package omits participant working archives and
  validates only their internal declared chain/hash anchors.
- For each packet, a corrected issuance time is greater than or equal to its
  predecessor, and the correction ledger time exactly equals the new issuance
  time. Active rows must preserve
  `issued/extraction_completed ≤ composition_started ≤ completed ≤ received`;
  the validator traverses every version transition and receipt locally.
- Collected validation accepts canonical arm/gold rows only when every row
  matches the active coordinator packet/issuance/correction chain and its
  archived receipt. Labels remain freely chosen until coordinator receipt;
  any later raw, extraction, or label edit without a new receipt is invalid.
- Arm C has no dedicated C2/C5 extraction field. Gold uses a plain-language
  extraction schema and no C1--C5 instruction/schema vocabulary. The staged
  builder never creates an adjudicator packet.
- The legacy combined auditor/gold builder is fail-closed by default. Its
  explicit `--internal-combined` mode is coordinator-only and marked
  `INTERNAL_NOT_FOR_DISTRIBUTION`; such files cannot be participant packets.

Extraction is reported separately through snapshot/hash completion and
nonempty field diagnostics for each arm and gold. Because arm fields are not
commensurate and no independent atom-level fact-scoring key is frozen, these
diagnostics are not called extraction accuracy. Composition is evaluated
through the two separate exact-label outcomes and no-consensus rates. Neither
diagnostic replaces the intention-to-audit primary endpoint.

## 8. Independent plain-language gold reference

Three experts, distinct from all auditors and adjudicators, independently
review every claim. They use only the plain scientific-support and
comparability rubric in `codebook_v3_frozen.md`; their packet contains no
`C1`--`C5` names, arm outputs, model fields, or decisive-stratum flag.
Their display order is the ascending order of
`SHA256("2026071506|gold-order|" + participant_id + "|" + claim_id)`.

Gold experts and adjudicators must have doctoral-level or equivalent
publication/review experience in NLP, IR, security evaluation, or experimental
methodology. They cannot be manuscript authors, codebook developers, sampling
screeners, prior-study annotators, or supervisors of an auditor, and must
declare source-author conflicts before packet release.

Gold experts separately record source facts, evidence support, and
comparability. The gold question is not whether the v3 fields agree; it is
whether the source supports the wording and whether the compared quantities
answer the same scientific question at the asserted scope. This avoids using
the evaluated procedure as its own definition of correctness.

For each output separately:

1. fewer than three completed expert responses is
   `unresolved_incomplete_gold` and never triggers adjudication;
2. unanimous agreement among exactly three completed experts establishes the
   provisional reference;
3. disagreement among exactly three completed experts triggers two
   independent adjudications without waiting for or blocking unrelated
   complete disagreements;
4. adjudicators first inspect the raw material, then receive the three blinded
   expert records, but never see an arm response or the other adjudicator;
5. both adjudication files are retained without overwriting;
6. if the two adjudicators independently choose the same label, that label is
   the resolved reference, even if it differs from the expert majority; and
7. if they differ, abstain, or identify missing source material, that output is
   `unresolved`. Authors may not choose between them.

An output can be resolved while the other remains unresolved. No combined
reference verdict is created.

Adjudicator packets are generated only when three completed gold records
disagree for the relevant output. Both adjudicators receive
the same blinded expert records and raw evidence, but packet construction never
reads or includes the other adjudicator's response.

The coordinator retains
`adjudicator_packet_registry.json` (schema
`coordinator-adjudicator-packet-registry-v1`). Packet version
`adjudicator-packet-v1` derives each adjudication ID deterministically from the
anonymous adjudicator, claim, and ordered disputed outputs. The registry
anchors the blinded gold identifiers, raw-material hash, row order/root, and
issued blank-packet SHA-256. Collected validation reconstructs these values
from the frozen claims, completed gold records, and public role roster.
Each adjudicator file must have exactly one row per eligible complete-gold
disagreement and no row for unanimous or incomplete gold; duplicate claim IDs
fail independently of adjudication ID. Analysis rejects duplicates before
constructing claim maps, so legal row permutations cannot change resolution.

## 9. Frozen endpoints and estimands

For claim \(i\), arm \(a\), and each output separately, the arm label is the
strict majority of the three independent labels. If all three labels differ,
the arm result is `no_consensus`; this is not a substantive label and scores
zero for exact accuracy. Exact accuracy is the binary indicator that the
strict-majority arm label equals the resolved gold label. The paired claim
difference is \(Y_i=accuracy_{i,D}-accuracy_{i,C}\), taking values -1, 0, or
1. This aggregation handles the repeated ratings and pairs C and D on the same
claim without pretending that their different auditors are paired. Individual
auditor accuracy and the no-consensus rate are separate secondary outcomes.

### 9.1 Primary test

The sole confirmatory endpoint is the mean paired difference in
**comparability-label exact accuracy, D minus C**, pooled over the frozen
480-claim C2/C5-decisive cohort.

- Minimum meaningful effect: **10 percentage points**.
- Two-sided alpha: **.05**.
- Power target: **at least .80** for a true +10-point difference under every
  planning scenario in `power_analysis.json`.
- Estimate and 95% interval: source-cluster bootstrap over the 80 sources,
  resampling whole six-claim clusters with seed `2026071504`, 100,000
  replicates, percentile interval.
- Test: an intercept-only paired linear model of \(Y_i\), whose intercept is
  the pooled mean difference. The implementation uses CR1
  \(G/(G-1)\) variance inflation, source clusters, \(G-1\) Student-t degrees of
  freedom, and a two-sided p-value. A p-value below .05 plus a positive
  estimate is required for a superiority conclusion.

The bootstrap interval is the primary uncertainty display; the
cluster-robust model supplies the predeclared p-value. No claim-level
independence p-value may replace either.

If missingness leaves zero primary observations or observations from fewer
than two sources, the endpoint is `not_estimable`: CR1, bootstrap, and TOST
are not run. Unresolved/incomplete rates and preregistered worst/best bounds
are still reported, and the conclusion is
`inconclusive_nonconfirmatory_missingness`.

### 9.2 Conditional equivalence branch

Only if primary superiority does not pass may equivalence be tested on the same
endpoint. The equivalence margin is **-10 to +10 percentage points**. Two
one-sided tests use alpha .05 and the same intercept-only source-cluster-robust
standard error; equivalence requires the entire corresponding 90% interval to
lie strictly inside both margins. A failed superiority test is never evidence
of equivalence. If neither branch passes, the result is `inconclusive`.

The cap of 480 claims gives approximately .752 power for equivalence at a true
zero difference in the most conservative planning scenario; about 528 claims
from 88 six-claim sources would be needed for .80 under the same approximation
and exceeds the predeclared cap. Therefore failure of the equivalence branch
must be described as potentially underpowered, never as non-equivalence.

### 9.3 Secondary analyses

Secondary outcomes are:

- evidence-support exact accuracy for each arm;
- comparability accuracy for A, B, C, and D;
- the six pairwise arm contrasts for each separate output;
- C2-decisive and C5-decisive subgroup contrasts;
- field/fact extraction-lock and field-completeness diagnostics by arm;
- composition accuracy and no-consensus rates;
- inter-rater agreement, abstention, time, and missingness; and
- sensitivity to each adjudicator's independent label.

The 11 nonprimary pairwise contrasts (the other five comparability contrasts
and all six evidence-support contrasts) form one Holm-corrected family. The
two D-versus-C stratum contrasts form a separate Holm-corrected secondary
family. The already tested pooled D-versus-C comparability contrast is not
tested a second time. Remaining diagnostics are labeled exploratory with
intervals and no confirmatory language. Evidence-support and comparability are
never pooled.

## 10. Dependency, missingness, and sensitivity

Claims share a source; three judgments share a claim; auditors rate many
claims; and the same gold experts rate all claims. Strict-majority aggregation
handles the three judgments per claim, and source CR1/bootstrap inference
handles paper clustering. Repeated-auditor dependence is reported as a design
limitation; no claim-level or participant-level independence model replaces
the source-cluster primary analysis.

No response is silently dropped. Missing reason codes are
`SOURCE_FILE_UNAVAILABLE`, `ASSIGNED_AUDITOR_WITHDREW`, `TECHNICAL_FAILURE`,
`CONFLICT_DISCLOSED`, `UNABLE_TO_DETERMINE`, and `OTHER_WITH_TEXT`.

- Primary analysis requires a resolved gold comparability label and all three
  assigned ratings in both C and D.
- A three-distinct-label `no_consensus` result is an observed arm failure, not
  missingness, and remains in the denominator with exact accuracy zero.
- Missing auditor ratings are not replaced after unblinding. The complete-case
  estimate is accompanied by worst/best bounds that set missing D and C
  correctness in opposing directions.
- Gold-unresolved claims are excluded only from accuracy denominators, with
  counts and rates reported by source and stratum. Worst/best bounds treat
  their potential paired differences as -1 and +1.
- If more than 5% of the decisive cohort has unresolved comparability gold, or
  more than 5% lacks complete C/D ratings, the confirmatory result is declared
  non-confirmatory regardless of p-value. Descriptive estimates and bounds
  remain reportable.
- Deviations, exclusions, corrections, withdrawals, and timestamps are
  retained before any outcome analysis.

No optional stopping, sample-size re-estimation from observed labels, source
replacement after packet release, or exclusion based on arm/gold results is
allowed.

## 11. Freeze, release, and unblinding order

The immutable order is:

1. freeze this protocol, codebook, configuration, scripts, templates, seeds,
   power output, generated development-source key/title registries, and the
   recorded SHA-256 values of both title-provenance inputs;
2. freeze and hash the complete source frame and all exclusion reasons;
3. freeze candidate rows, human sampling decisions, 480 raw claims, 80 source
   hashes, and the coordinator-only 240/240 stratum allocation;
4. freeze anonymous role metadata; verify that 24 auditors, three gold
   experts, and two adjudicators are distinct; retain the validator-reported
   SHA-256 of the access-controlled metadata without publishing the file;
5. generate assignments; run `validate_package.py --mode frozen`; regenerate
   and verify `MANIFEST.sha256`;
6. archive the validation output, manifest, and git commit in the study
   registry;
7. release calibration, then extraction-only stage-1 packets;
8. validate returned extraction against the coordinator registry, issue
   stage 2, and retain every correction/reissuance version;
9. collect auditor/gold composition through the coordinator collector and
   archive row/file receipts;
10. trigger and lock both adjudication files independently for eligible
   three-completed-expert disagreements;
11. construct the resolved-reference table by the mechanical rule above; and
12. unblind arm names and coordinator-only strata for analysis.

Any hash change after step 5 creates a new version and a documented deviation;
it cannot silently overwrite the freeze. Model prescreen outputs are unblinded
only after all confirmatory analyses are locked. Filled private metadata,
consent, and compensation records remain outside the public release.

## 12. Planning assumptions and limitations

The power approximation treats the paired correctness difference as a
three-valued variable, assumes equal six-claim clusters, uses a design effect
for a specified source ICC, and assumes a resolved gold reference with no
missingness. It does not model auditor, gold, venue-stratum, or unequal-cluster
effects; these can reduce effective power. Enrichment for decisive claims
limits prevalence and population-accuracy claims. The study estimates
performance on the frozen decisive cohort, not all robust-RAG prose.

The C-versus-D contrast tests the incremental effect of dedicated prompts
within this human workflow. It cannot prove that reviewers in Arm C never use
related background knowledge. Arms A and B are independent operational
baselines, not claims that one generic review tradition has a single canonical
implementation.
