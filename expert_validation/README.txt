Expert validation package for the robust-RAG comparability protocol

Purpose
-------
This package is for collecting independent expert judgments. It is not a
completed experiment and should not be cited as evidence until responses have
been collected from experts who did not design the codebook.

Status update
-------------
Blind batch A has been collected in:

    ../expert_validation_blind_batch_A_20260605/

It contains 30 annotators, 12 paper pairs per annotator, and balanced
control/protocol conditions. The analysis uses the pre-specified rulebook
expected verdict as the reference, not an independently adjudicated external
gold label.

Recommended study
-----------------
Recruit independent RAG, IR, NLP, or security researchers. Randomly assign each
participant to one of two conditions:

1. Control: use instructions_control.txt. Participants judge whether each paper
   pair is valid, partial, invalid, or under-specified using their own criteria.
2. Protocol: use instructions_protocol.txt. Participants apply the five-coordinate
   codebook and verdict rules.

Send participants paper_pairs_for_annotation.csv, not paper_pairs.csv.
paper_pairs.csv contains internal reference verdicts and should only be used for
analysis after responses are collected.

Control participants fill participant_response_template_control.csv. Protocol
participants fill participant_response_template_protocol.csv. Record decision
time, confidence, verdict, rationale, and perceived usefulness. If possible,
create an independently adjudicated gold file from experts who did not design
the codebook; otherwise treat the included rulebook_expected_verdict only as an
internal reference.

See expert_annotation_guide.md for the full English coordinator guide. A
Chinese coordinator note is provided in annotation_guide_zh.md.

Analysis
--------
After collecting responses, save them as responses.csv with the columns from
response_template.csv and run:

    python3 analyze_expert_validation.py responses.csv paper_pairs.csv

The script reports verdict accuracy against the available reference verdict,
Fleiss kappa by condition, mean decision time, confidence, usefulness, and error
type counts. If paper_pairs.csv contains external_gold_verdict values, those are
used as the reference. Otherwise, the script uses rulebook_expected_verdict and
prints a warning that the metric is rulebook agreement rather than external
validity.

For the completed blind batch, run:

    python3 analyze_blind_batch.py ../expert_validation_blind_batch_A_20260605/responses.csv paper_pairs.csv ../expert_validation_blind_batch_A_20260605
