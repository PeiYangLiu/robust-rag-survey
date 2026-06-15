# Blind expert validation batch A summary

Reference verdict column: `rulebook_expected_verdict`. This is not an independently adjudicated external gold label unless `external_gold_verdict` is filled.

## control

- participants: 15
- responses: 180
- reference: rulebook_expected_verdict
- rulebook_accuracy: 0.727778
- correct: 131
- judged: 180
- fleiss_kappa: 0.589169
- mean_decision_time_seconds: 126.056
- mean_confidence_1_5: 3.689
- mean_usefulness_1_5: 3.511
- mean_rationale_quality_1_5: 4.078
- verdict_counts: {"invalid": 18, "partial": 144, "valid": 18}
- error_type_counts: {"action_policy_missing": 1, "evidence_assumption_mismatch": 22, "intervention_mismatch": 15, "metric_mismatch": 37, "objective_mismatch": 83}

## protocol

- participants: 15
- responses: 180
- reference: rulebook_expected_verdict
- rulebook_accuracy: 0.894444
- correct: 161
- judged: 180
- fleiss_kappa: 0.845714
- mean_decision_time_seconds: 121.806
- mean_confidence_1_5: 3.917
- mean_usefulness_1_5: 4.061
- mean_rationale_quality_1_5: 4.133
- verdict_counts: {"invalid": 30, "partial": 150}
- error_type_counts: {"action_policy_mismatch": 1, "action_policy_missing": 8, "evidence_assumption_mismatch": 29, "intervention_mismatch": 100, "metric_mismatch": 31, "objective_mismatch": 11}

## Bootstrap differences (protocol - control)

- rulebook_accuracy: median 0.166667, 95% CI [0.116667, 0.216667]
- mean_decision_time_seconds: median -4.333200, 95% CI [-13.944400, 5.833267]
- mean_confidence_1_5: median 0.227800, 95% CI [0.133400, 0.316467]
- mean_usefulness_1_5: median 0.549933, 95% CI [0.405667, 0.700000]
- mean_rationale_quality_1_5: median 0.055600, 95% CI [-0.022267, 0.133600]
