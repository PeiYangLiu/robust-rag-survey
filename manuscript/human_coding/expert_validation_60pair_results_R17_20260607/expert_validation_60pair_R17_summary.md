# R17 60-pair expert validation results

Responses: 360
Pairs: 60
Gold judgments: 180

## Gold inter-adjudicator agreement
- Fleiss kappa: 0.772
- Mean pair agreement: 0.889
- Unanimous pairs: 50/60 (0.833)

## Participant agreement with panel gold
| Condition | Reviewers | Judgments | Gold agreement | Mean confidence | Verdict counts |
|---|---:|---:|---:|---:|---|
| control | 3 | 180 | 0.567 | 4.07 | {'invalid': 150, 'partial': 30} |
| protocol | 3 | 180 | 0.883 | 3.83 | {'partial': 93, 'invalid': 87} |

Protocol-control agreement difference: 0.317, 95% clustered bootstrap CI [0.192, 0.439]

## Coordinate error summary
### control
- Wrong verdicts: 78 / 180
- Missed coordinates: {'action': 82, 'intervention': 28, 'assumption': 55, 'failure': 34, 'metric': 1}
- Extra coordinates: {'failure': 12, 'assumption': 20, 'metric': 3, 'action': 2}
### protocol
- Wrong verdicts: 21 / 180
- Missed coordinates: {'action': 16, 'assumption': 12, 'failure': 10, 'metric': 13, 'intervention': 7}
- Extra coordinates: {'assumption': 27, 'failure': 9, 'action': 2}

## Mixed-effects logit
- Status: ok_vb_binomial_mixed_model
- Protocol odds ratio: 80.34
