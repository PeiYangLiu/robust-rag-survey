# Venue-complete systematic review protocol

This protocol defines the manual venue-complete pass needed to upgrade the
current scoping survey into a venue-complete systematic review.

## Target venues

- NLP: ACL, EMNLP, NAACL, COLING, Findings ACL/EMNLP/NAACL, TACL
- IR/Web/Data mining: SIGIR, WWW/TheWebConf, WSDM, KDD, CIKM
- Security: USENIX Security, CCS, NDSS, IEEE S&P
- ML: ICLR, NeurIPS, ICML

## Years

Default: 2020--2026. Earlier years should be added for foundational retrieval,
open-domain QA, faithfulness, calibration, and selective prediction papers.

## Procedure

1. Download or query the complete accepted-paper list for each venue-year.
2. Screen titles and abstracts with the query terms in `search_protocol.json`.
3. Add a manual secondary screen for older terms such as open-domain QA,
   retrieval-augmented generation, grounded generation, source attribution,
   answerability, selective prediction, poisoning, prompt injection, and
   hallucination.
4. Record every screened paper in a venue census table with:
   - venue
   - year
   - title
   - authors
   - URL/DOI/OpenReview/PMLR/ACL Anthology ID
   - screening decision
   - inclusion/exclusion rationale
   - duplicate/preprint mapping
   - PDF availability
5. Resolve duplicates by normalized title, arXiv ID, DOI, and proceedings ID.
6. For included papers, code the five coordinates:
   - failure type
   - evidence assumption
   - intervention point
   - metric target
   - action policy
7. Double-code a stratified subset and report agreement.

## Output files

- `venue_complete_census.csv`
- `venue_complete_inclusion_log.csv`
- `venue_complete_exclusion_log.csv`
- `venue_complete_duplicate_map.csv`
- `venue_complete_source_strata.csv`

The current manuscript reports a venue-oriented metadata pass and triage, not
this full manual venue-complete census.
