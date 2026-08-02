# Completed human claim-validation round

This directory contains the completed 80-claim validation round:

- `annotator_A_claims_completed.csv`
- `annotator_B_claims_completed.csv`
- `annotator_C_claims_completed.csv`
- `adjudicated_consensus.csv`
- `human_annotation_provenance.json`
- `analysis_results/`

The project owner confirmed that A, B, C, and the adjudicator are four
different human participants and that no generative AI was used for annotation
or adjudication. Model labels were hidden until human adjudication was
complete.

The release keeps only claim labels, evidence locations, rationales, consensus,
and the minimal project-owner-attested independence/no-AI provenance needed to
interpret the results.
The frozen v2 codebook was the delivered instruction document. Aggregate
expertise, recruitment, training, compensation, work time, consent, ethics
status, and adjudication information is recorded in
`../human_validation_protocol.md` and `human_annotation_provenance.json`.
Participant identifiers, pilot responses, calibration notes, consent forms,
the institutional determination document, and the selection procedure for
64 of the 80 claims are not released.

The model-adjudicated sampling labels are not human gold. The canonical human
result is `analysis_results/final/human_final_consensus.csv`.
