#!/usr/bin/env python3
"""Validate adjudication and produce the final human-validation analysis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from analyze_human_annotations import metrics, read_csv, write_csv


VERDICTS = ["valid", "partial", "invalid", "under-specified"]
RELATIONS = {"aligned", "different", "mixed", "unknown", "not_applicable"}
ARCHETYPES = {
    "A_self_baseline",
    "B_shared_harness",
    "C_cross_source_synthesis",
    "D_causal_mechanistic",
    "E_field_meta",
    "F_policy_utility",
}
CONTROL_STATUS = {"aligned", "partial", "unmatched", "unknown", "not_applicable"}
FINAL_FIELDS = [
    "final_verdict",
    "final_archetype",
    "final_c1_relation",
    "final_c2_relation",
    "final_c3_relation",
    "final_c4_relation",
    "final_c5_relation",
    "final_controls_status",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def class_metrics(
    predicted: dict[str, str], gold: dict[str, str]
) -> list[dict[str, object]]:
    rows = []
    for label in VERDICTS:
        tp = sum(predicted[item] == label and gold[item] == label for item in gold)
        predicted_n = sum(predicted[item] == label for item in gold)
        gold_n = sum(gold[item] == label for item in gold)
        precision = tp / predicted_n if predicted_n else 0.0
        recall = tp / gold_n if gold_n else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        rows.append(
            {
                "label": label,
                "tp": tp,
                "predicted_n": predicted_n,
                "human_n": gold_n,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--hidden-key",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    completed_files = sorted(args.annotations.glob("annotator_*_claims_completed.csv"))
    if len(completed_files) != 3:
        raise SystemExit(f"expected 3 completed files, found {len(completed_files)}")
    by_annotator = {}
    source_by_id = {}
    for path in completed_files:
        rows = read_csv(path)
        annotator = rows[0]["annotator_id"]
        by_annotator[annotator] = {row["annotation_id"]: row for row in rows}
        for row in rows:
            source_by_id[row["annotation_id"]] = row
    annotators = sorted(by_annotator)
    ids = sorted(source_by_id)
    if len(ids) != 80 or any(set(rows) != set(ids) for rows in by_annotator.values()):
        raise SystemExit("completed annotation ID sets do not match 80 claims")

    adjudicated_rows = read_csv(args.annotations / "adjudicated_consensus.csv")
    adjudicated = {row["annotation_id"]: row for row in adjudicated_rows}
    if set(adjudicated) != set(ids) or len(adjudicated_rows) != 80:
        raise SystemExit("adjudicated consensus must contain exactly the same 80 IDs")

    errors = []
    for annotation_id, row in adjudicated.items():
        for annotator in annotators:
            if row[f"{annotator}_verdict"] != by_annotator[annotator][annotation_id][
                "verdict"
            ]:
                errors.append(
                    f"{annotation_id}: {annotator}_verdict differs from completed file"
                )
        if row["final_verdict"] not in VERDICTS:
            errors.append(f"{annotation_id}: invalid final verdict")
        if row["final_archetype"] not in ARCHETYPES:
            errors.append(f"{annotation_id}: invalid final archetype")
        for field in [
            "final_c1_relation",
            "final_c2_relation",
            "final_c3_relation",
            "final_c4_relation",
            "final_c5_relation",
        ]:
            if row[field] not in RELATIONS:
                errors.append(f"{annotation_id}: invalid {field}")
        if row["final_controls_status"] not in CONTROL_STATUS:
            errors.append(f"{annotation_id}: invalid final controls")
        if row["final_verdict"] == "partial" and not row[
            "final_narrower_supported_claim"
        ].strip():
            errors.append(f"{annotation_id}: partial lacks narrower claim")
        if row["final_verdict"] == "under-specified" and not row[
            "final_missing_information"
        ].strip():
            errors.append(f"{annotation_id}: under-specified lacks missing info")
        if not row["adjudication_evidence_location"].strip() or not row[
            "adjudication_rationale"
        ].strip():
            errors.append(f"{annotation_id}: missing adjudication evidence/rationale")
    if errors:
        raise SystemExit("\n".join(errors[:100]))

    hidden_key = args.hidden_key or args.annotations / "sample_key.csv"
    hidden = {row["annotation_id"]: row for row in read_csv(hidden_key)}
    provenance_path = args.annotations / "human_annotation_provenance.json"
    provenance = (
        json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance_path.is_file()
        else {}
    )
    human_gold = {
        annotation_id: adjudicated[annotation_id]["final_verdict"]
        for annotation_id in ids
    }
    model_prediction = {
        annotation_id: hidden[annotation_id]["model_adjudicated_verdict"]
        for annotation_id in ids
    }

    final_rows = []
    for annotation_id in ids:
        source = source_by_id[annotation_id]
        adjudication = adjudicated[annotation_id]
        final = {
            "annotation_id": annotation_id,
            "candidate_id": hidden[annotation_id]["candidate_id"],
            "source_key": hidden[annotation_id]["source_key"],
            "audit_slice": hidden[annotation_id]["audit_slice"],
            "balanced_core_16": hidden[annotation_id]["balanced_core_16"],
            "source_title": source["source_title"],
            "source_url": source["source_url"],
            "source_section": source["source_section"],
            "pdf_page": source["pdf_page"],
            "printed_page": source["printed_page"],
            "exact_quote": source["exact_quote"],
            **{
                key: value
                for key, value in adjudication.items()
                if key.startswith("final_")
                or key.startswith("adjudication_")
            },
        }
        final_rows.append(final)

    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "human_final_consensus.csv", final_rows)

    confusion_rows = []
    for model_label in VERDICTS:
        for human_label in VERDICTS:
            confusion_rows.append(
                {
                    "model_adjudicated_verdict": model_label,
                    "human_final_verdict": human_label,
                    "count": sum(
                        model_prediction[item] == model_label
                        and human_gold[item] == human_label
                        for item in ids
                    ),
                }
            )
    write_csv(args.output / "human_vs_model_confusion.csv", confusion_rows)
    per_class = class_metrics(model_prediction, human_gold)
    write_csv(args.output / "human_vs_model_per_class.csv", per_class)
    raw, kappa, ac1 = metrics(
        [model_prediction[item] for item in ids],
        [human_gold[item] for item in ids],
    )

    core_ids = [item for item in ids if hidden[item]["balanced_core_16"] == "1"]
    core_raw, core_kappa, core_ac1 = metrics(
        [model_prediction[item] for item in core_ids],
        [human_gold[item] for item in core_ids],
    )
    summary = {
        "status": "user_supplied_human_annotations_with_adjudicated_consensus",
        "annotator_ids": annotators,
        "human_provenance": provenance,
        "n_claims": len(ids),
        "balanced_core_n": len(core_ids),
        "adjudicated_distribution": dict(Counter(human_gold.values())),
        "balanced_core_human_distribution": dict(
            Counter(human_gold[item] for item in core_ids)
        ),
        "human_vs_model_secondary": {
            "exact_agreement": raw,
            "cohen_kappa": kappa,
            "gwet_ac1": ac1,
            "macro_f1": sum(row["f1"] for row in per_class) / len(per_class),
            "balanced_core_exact_agreement": core_raw,
            "balanced_core_cohen_kappa": core_kappa,
            "balanced_core_gwet_ac1": core_ac1,
        },
        "model_labels_used_during_human_annotation_or_adjudication": False,
    }
    (args.output / "human_validation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest_path = args.annotations / "MANIFEST.sha256"
    files = [
        path
        for path in args.annotations.rglob("*")
        if path.is_file() and path != manifest_path
    ]
    manifest_path.write_text(
        "\n".join(
            f"{sha256(path)}  {path.relative_to(args.annotations).as_posix()}"
            for path in sorted(files)
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
