#!/usr/bin/env python3
"""Add a short, complete consequence field to the comparability case ledger.

A reviewer observed that five cells of the flagship table were truncated with
an ellipsis, so a reader could not judge the verdict from the main paper.  The
fix is not a wider column but a field that is written to fit: for each case we
add ``numeric_consequence_short``, a complete sentence of at most
``--max-chars`` characters that states what happens to the number when the
coordinate is matched.  The long ``numeric_consequence`` is retained verbatim
and remains the released field; the short field is a rendering aid whose
consistency with the long field is checked by
``verify_cross_paper_cases.py``.

The script writes the short field into both the CSV and the summary JSON, and
fails if any short field exceeds the budget or if any case is missing one.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUPPLEMENT = REPO / "manuscript" / "supplement"

# One complete sentence per case, at most MAX_CHARS characters, stating the
# consequence of matching the coordinate.  Each is a faithful compression of the
# corresponding ``numeric_consequence`` field and adds no new quantity.
SHORT = {
    "SEC-01": "C4 differs: 0.01 scores answer manipulation, 84.2 scores top-20 retrieval, so no gap is defined.",
    "SEC-02": "No matched operating point exists for C4 (targeted answer vs refusal), so no gap is defined at any budget.",
    "SEC-03": "No number is transported; RobustRAG re-implements the attack, and its own poisoning ASRs are 37-86.",
    "SEC-04": "Objectives differ (denial of service vs targeted answer), so the 1.2-point gap does not rank the two attacks.",
    "SEC-05": "At five injected documents on MedSquad the 66.66-point gap stands; it does not transfer to NQ.",
    "NOISE-01": "All five coordinates match, so the 6.9-point gap stands as reported.",
    "NOISE-02": "Backbone and retriever differ, so the 6.9-point gap has no determined sign.",
    "NOISE-03": "Substring accuracy is weaker than exact match, so the 4.53-point gap has no determined sign.",
    "NOISE-04": "The two baselines differ in whether gold context is present, so the two gains are not commensurable.",
    "NOISE-05": "Model, dataset, retrieval and metric match, so the 4.4-point accuracy gap stands.",
    "FAITH-01": "Response-level and span-level scores are different units, so the contrast holds only within one unit.",
    "FAITH-02": "Aggregate and single-task scores under different conflict types and models cannot be differenced.",
    "CALIB-01": "Within one paper and one harness the 23.9-point gap stands as reported.",
    "CALIB-02": "Within one paper and one harness the 4.0-point gap stands as reported.",
    "CALIB-03": "A harder test subset and a stricter metric are confounded with the method, so 16.75 is not a method effect.",
}

# Whether the comparison is one a paper states itself, or one a survey or
# benchmark invites by grouping two systems under a single label.
TYPE_LABEL = {
    "DIRECT": "stated",
    "SURVEY-INVITED": "invited",
    "STATED-TRANSPORTED": "quoted",
    "STATED-TRANSPORTED-BASELINE": "rerun",
    "STATED-REIMPLEMENTED": "rerun",
    "STATED-NO-NUMBER": "no num.",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-chars", type=int, default=118)
    parser.add_argument(
        "--cases", type=Path, default=SUPPLEMENT / "cross_paper_comparability_cases.csv"
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=SUPPLEMENT / "cross_paper_comparability_cases_summary.json",
    )
    args = parser.parse_args()

    rows = list(csv.DictReader(args.cases.open(encoding="utf-8", newline="")))
    missing = [r["case_id"] for r in rows if r["case_id"] not in SHORT]
    if missing:
        raise SystemExit(f"missing short consequence for: {missing}")
    too_long = {k: len(v) for k, v in SHORT.items() if len(v) > args.max_chars}
    if too_long:
        raise SystemExit(f"short consequence over budget: {too_long}")

    fieldnames = list(rows[0].keys())
    if "numeric_consequence_short" not in fieldnames:
        fieldnames.insert(
            fieldnames.index("numeric_consequence") + 1, "numeric_consequence_short"
        )
    for row in rows:
        row["numeric_consequence_short"] = SHORT[row["case_id"]]
    with args.cases.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    for case in summary["cases"]:
        case["numeric_consequence_short"] = SHORT[case["case_id"]]
        case["comparison_type_label"] = TYPE_LABEL.get(
            case.get("comparison_type", ""), case.get("comparison_type", "")
        )
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(f"annotated {len(rows)} cases; longest short field is "
          f"{max(len(v) for v in SHORT.values())} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
