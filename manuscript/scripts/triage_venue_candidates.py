#!/usr/bin/env python3
"""Triage venue-linked robust-RAG candidates after the metadata pass."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPP = ROOT / "supplement"


DECISIONS = {
    "Robust Retrieval Augmented Generation for Zero-shot Slot Filling": (
        "include_evidence",
        "noisy_retrieval",
        "method",
        "generator",
        "slot filling / domain transfer",
        "venue-linked early robust RAG method; adds pre-2024 peer-reviewed context.",
    ),
    "Retrieval-Augmented Parsing for Complex Graphs by Exploiting Structure and Uncertainty": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "graph parsing",
        "RAG-style parsing/uncertainty paper but not evidence reliability or robust text RAG.",
    ),
    "Benchmarking Retrieval-Augmented Generation for Medicine": (
        "include_background",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "medical RAG benchmark",
        "domain benchmark useful for scope discussion but not central robust-RAG evidence.",
    ),
    "Enhancing Distractor Generation for Multiple-Choice Questions with Retrieval Augmented Pretraining and Knowledge Graph Integration": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "distractor generation",
        "False positive: distractor generation for MCQs, not RAG distraction robustness.",
    ),
    "Detecting Hallucination and Coverage Errors in Retrieval Augmented Generation for Controversial Topics": (
        "include_evidence",
        "evaluation_benchmark;ood_uncertainty",
        "benchmark/evaluation",
        "evaluation",
        "hallucination / coverage detection",
        "Directly evaluates hallucination and evidence coverage errors in RAG.",
    ),
    "{A}lpha{F}in: Benchmarking Financial Analysis with Retrieval-Augmented Stock-Chain Framework": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "financial RAG benchmark",
        "Application benchmark without robust evidence-reliability analysis.",
    ),
    "``Knowing When You Don{'}t Know'': A Multilingual Relevance Assessment Dataset for Robust Retrieval-Augmented Generation": (
        "include_evidence",
        "ood_uncertainty;calibration_control;evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "multilingual relevance / answerability",
        "Directly targets relevance assessment and knowing-when-not-to-answer in RAG.",
    ),
    "{BERGEN}: A Benchmarking Library for Retrieval-Augmented Generation": (
        "include_evidence",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "RAG benchmarking library",
        "Reusable benchmarking library; relevant to evaluation infrastructure.",
    ),
    "{R}e{E}val: Automatic Hallucination Evaluation for Retrieval-Augmented Large Language Models via Transferable Adversarial Attacks": (
        "include_evidence",
        "evaluation_benchmark;adversarial_corruption",
        "benchmark/evaluation",
        "evaluation",
        "hallucination evaluation / adversarial attacks",
        "Directly connects hallucination evaluation with adversarially generated RAG evidence.",
    ),
    "IRSC: A Zero-shot Evaluation Benchmark for Information Retrieval through Semantic Comprehension in Retrieval-Augmented Generation Scenarios.": (
        "include_evidence",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "IR/RAG semantic-comprehension benchmark",
        "Relevant evaluation benchmark for retrieval in RAG scenarios.",
    ),
    "Optimizing biomedical information retrieval with a keyword frequency-driven prompt enhancement strategy": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "biomedical retrieval",
        "Application-focused retrieval/prompting paper, not robust RAG evidence reliability.",
    ),
    "All That Glitters is Not Gold: Improving Robust Retrieval-Augmented Language Models with Fact-Centric Preference Alignment": (
        "include_evidence",
        "noisy_retrieval;knowledge_conflict",
        "defense/mitigation",
        "generator",
        "fact-centric preference alignment",
        "Directly improves robust RALMs under unreliable retrieved evidence.",
    ),
    "Evaluation of Attribution Bias in Generator-Aware Retrieval-Augmented Large Language Models": (
        "include_evidence",
        "evaluation_benchmark;knowledge_conflict",
        "analysis",
        "evaluation",
        "attribution bias",
        "Directly analyzes attribution/citation bias in generator-aware RAG.",
    ),
    "Judge as A Judge: Improving the Evaluation of Retrieval-Augmented Generation through the Judge-Consistency of Large Language Models": (
        "include_evidence",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "LLM judge consistency",
        "Relevant to robustness of RAG evaluation protocols.",
    ),
    "Multilingual Retrieval Augmented Generation for Culturally-Sensitive Tasks: A Benchmark for Cross-lingual Robustness": (
        "include_evidence",
        "evaluation_benchmark;ood_uncertainty",
        "benchmark/evaluation",
        "evaluation",
        "cross-lingual robustness",
        "Venue-linked benchmark for multilingual/cultural robustness; included as boundary evidence.",
    ),
    "{RAG}-{R}eward{B}ench: Benchmarking Reward Models in Retrieval Augmented Generation for Preference Alignment": (
        "include_evidence",
        "evaluation_benchmark;calibration_control",
        "benchmark/evaluation",
        "evaluation",
        "reward-model benchmarking",
        "Relevant to RAG evaluation and preference/alignment under retrieved evidence.",
    ),
    "{R}ose{RAG}: Robust Retrieval-augmented Generation with Small-scale {LLM}s via Margin-aware Preference Optimization": (
        "include_evidence",
        "noisy_retrieval",
        "defense/mitigation",
        "generator",
        "robust small-model RAG",
        "Directly targets robust RAG with small-scale LLMs.",
    ),
    "DCMI: A Differential Calibration Membership Inference Attack Against Retrieval-Augmented Generation.": (
        "include_evidence",
        "adversarial_corruption",
        "attack",
        "system control",
        "membership inference / calibration attack",
        "Security venue paper; relevant to RAG attack surface and calibration/privacy risks.",
    ),
    "Benchmarking Foundation Models with Retrieval-Augmented Generation in Olympic-Level Physics Problem Solving": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "physics benchmark",
        "Domain benchmark without central evidence-reliability or robustness analysis.",
    ),
    "Controlled Retrieval-augmented Context Evaluation for Long-form {RAG}": (
        "include_evidence",
        "evaluation_benchmark;distraction",
        "benchmark/evaluation",
        "evaluation",
        "long-form RAG context evaluation",
        "Directly evaluates controlled context conditions for long-form RAG.",
    ),
    "{A}uto{E}volve: Automatically Evolving Queries for Applicable and Scalable Retrieval-Augmented Generation Benchmarking": (
        "include_evidence",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "query evolution for benchmarking",
        "Relevant benchmark-generation work for scalable RAG evaluation.",
    ),
    "{K}o-{L}ong{RAG}: A {K}orean Long-Context {RAG} Benchmark Built with a Retrieval-Free Approach": (
        "include_background",
        "evaluation_benchmark;ood_uncertainty",
        "benchmark/evaluation",
        "evaluation",
        "Korean long-context RAG benchmark",
        "Useful boundary paper for multilingual/long-context scope; not central text robustness evidence.",
    ),
    "{P}areto{RAG}: Leveraging Sentence-Context Attention for Robust and Efficient Retrieval-Augmented Generation": (
        "include_evidence",
        "noisy_retrieval;calibration_control",
        "method",
        "generator",
        "robust and efficient RAG",
        "Directly targets robust/efficient RAG with sentence-context attention.",
    ),
    "{R}ev{PRAG}: Revealing Poisoning Attacks in Retrieval-Augmented Generation through {LLM} Activation Analysis": (
        "duplicate_existing",
        "adversarial_corruption",
        "attack",
        "generator",
        "poisoning analysis",
        "Duplicate venue metadata for RevPRAG already present through DBLP survey entry.",
    ),
    "{VLM} Is a Strong Reranker: Advancing Multimodal Retrieval-augmented Generation via Knowledge-enhanced Reranking and Noise-injected Training": (
        "include_background",
        "noisy_retrieval",
        "method",
        "retriever/context",
        "multimodal reranking / noise-injected training",
        "Relevant adjacent multimodal RAG robustness paper; kept as boundary background for text-based scope.",
    ),
    "{CORAL}: Benchmarking Multi-turn Conversational Retrieval-Augmented Generation": (
        "include_evidence",
        "evaluation_benchmark;calibration_control",
        "benchmark/evaluation",
        "evaluation",
        "multi-turn conversational RAG",
        "Venue-linked benchmark for conversational RAG evaluation and action/control settings.",
    ),
    "{MIRAGE}: A Metric-Intensive Benchmark for Retrieval-Augmented Generation Evaluation": (
        "include_evidence",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "metric-intensive RAG benchmark",
        "Directly relevant to RAG metric design.",
    ),
    "Agentic Retrieval-Augmented Generation: Advancing AI-Driven Information Retrieval and Processing": (
        "exclude",
        "survey_related",
        "survey_background",
        "not_applicable",
        "agentic RAG overview",
        "Broad agentic RAG overview; outside text evidence-reliability core.",
    ),
    "Application of Generative Artificial Intelligence Models for Accurate Prescription Label Identification and Information Retrieval for the Elderly in Northern East of Thailand": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "prescription-label application",
        "Application paper, not RAG robustness/evidence reliability.",
    ),
    "IRSC: A Zero-Shot Evaluation Benchmark for Information Retrieval Based on Semantic Comprehension in Retrieval-Augmented Generation Scenarios.": (
        "duplicate_existing",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "IR/RAG semantic-comprehension benchmark",
        "Duplicate of IRSC candidate already triaged from CoRR/SIGIR metadata.",
    ),
    "Improving Dietary Supplement Information Retrieval: Development of a Retrieval-Augmented Generation System With Large Language Models": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "dietary supplement application",
        "Application system, not robust RAG evidence reliability.",
    ),
    "Robust Fine-tuning for Retrieval Augmented Generation against Retrieval Defects.": (
        "include_evidence",
        "noisy_retrieval",
        "defense/mitigation",
        "generator",
        "robust fine-tuning against retrieval defects",
        "Directly studies robust RAG under retrieval defects.",
    ),
    "The LiveRAG Challenge at SIGIR 2025": (
        "include_evidence",
        "evaluation_benchmark",
        "benchmark/evaluation",
        "evaluation",
        "LiveRAG challenge",
        "Venue-linked RAG challenge; relevant to benchmark design.",
    ),
    "Zero-Shot Learning With Large Language Models Enhances Drilling-Information Retrieval": (
        "exclude",
        "other",
        "application",
        "not_applicable",
        "drilling information retrieval",
        "Application paper, not robust RAG evidence reliability.",
    ),
    "RLG-RAG: Guiding the Knowledge Retrieval and Evaluation in Retrieval-Augmented Generation Framework by Reasoning Logic.": (
        "include_evidence",
        "calibration_control;evaluation_benchmark",
        "method",
        "system control",
        "reasoning-guided retrieval/evaluation",
        "Relevant method connecting retrieval guidance and evaluation in RAG.",
    ),
    "WARP: A Word-Level Backdoor Attack Targeting RAG Systems via Retrieval Corpus Poisoning.": (
        "include_evidence",
        "adversarial_corruption",
        "attack",
        "corpus/KB",
        "word-level backdoor via corpus poisoning",
        "Security/ML venue paper directly on retrieval-corpus poisoning.",
    ),
    "Aligning Extraction and Generation for Robust Retrieval-Augmented Generation.": (
        "include_evidence",
        "noisy_retrieval;knowledge_conflict",
        "method",
        "generator",
        "aligning extraction and generation",
        "Directly targets robust RAG by aligning extraction and generation.",
    ),
    "When to Trust: A Causality-Aware Calibration Framework for Accurate Knowledge Graph Retrieval-Augmented Generation.": (
        "promote_to_evidence",
        "calibration_control;knowledge_conflict",
        "control/calibration",
        "system control",
        "causality-aware trust calibration",
        "Already in survey set; promoted into venue-audited evidence extension.",
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    coverage = read_csv(SUPP / "venue_coverage_audit.csv")
    survey = read_csv(SUPP / "survey300_full.csv")
    evidence = read_csv(SUPP / "evidence_map.csv")

    decision_rows = []
    evidence_extension = []
    survey_extension = []
    unknown = []

    existing_survey_titles = {row["title"] for row in survey}
    existing_evidence_titles = {row["title"] for row in evidence}

    for idx, row in enumerate(coverage, start=1):
        decision = DECISIONS.get(row["title"])
        if not decision:
            if row.get("in_evidence_map") == "True":
                decision = (
                    "retain_existing",
                    "",
                    "",
                    "",
                    "",
                    "Already present in the base evidence map; no venue-triage action needed.",
                )
            elif row.get("in_survey300") == "True":
                decision = (
                    "retain_survey_only",
                    "",
                    "",
                    "",
                    "",
                    "Already present in the base survey set; no evidence-map promotion decision made.",
                )
            else:
                unknown.append(row["title"])
                continue
        decision_name, cats, method, intervention, task, reason = decision
        decision_row = {
            **row,
            "triage_decision": decision_name,
            "taxonomy_categories": cats,
            "method_family": method,
            "intervention_point": intervention,
            "benchmark_or_task": task,
            "triage_reason": reason,
        }
        decision_rows.append(decision_row)

        include_in_survey = decision_name in {"include_evidence", "include_background"}
        include_in_evidence = decision_name in {"include_evidence", "promote_to_evidence"}

        if include_in_survey and row["title"] not in existing_survey_titles:
            survey_extension.append(
                {
                    "cite_key": f"venue{idx:03d}",
                    "title": row["title"],
                    "authors": "",
                    "year": row["year"],
                    "source_or_venue": row["venue_text"],
                    "url": row["url"],
                    "taxonomy_categories": cats,
                    "failure_or_risk_type": cats.split(";")[0],
                    "method_family": method,
                    "intervention_point": intervention,
                    "benchmark_or_task": task,
                    "metrics_reported_or_relevant": "",
                    "core100": "False",
                    "actual_contribution": reason,
                    "limitation_or_note": "Added by venue follow-up triage; authors/metadata should be fully normalized before camera-ready.",
                }
            )
        if include_in_evidence and row["title"] not in existing_evidence_titles:
            evidence_extension.append(
                {
                    "cite_key": f"venue{idx:03d}",
                    "title": row["title"],
                    "authors": "",
                    "year": row["year"],
                    "source_or_venue": row["venue_text"],
                    "url": row["url"],
                    "taxonomy_categories": cats,
                    "failure_or_risk_type": cats.split(";")[0],
                    "method_family": method,
                    "intervention_point": intervention,
                    "benchmark_or_task": task,
                    "metrics_reported_or_relevant": "",
                    "core100": "False",
                    "actual_contribution": reason,
                    "limitation_or_note": "Added by venue follow-up triage; field labels are author triage, not independent human-adjudicated labels.",
                }
            )

    if unknown:
        raise SystemExit("Missing triage decisions for: " + "; ".join(unknown))

    decision_fields = list(decision_rows[0].keys())
    write_csv(SUPP / "venue_triage_decisions.csv", decision_rows, decision_fields)

    extension_fields = list(evidence[0].keys())
    write_csv(SUPP / "venue_audited_extension.csv", survey_extension, extension_fields)
    write_csv(SUPP / "evidence_map_venue_extension.csv", evidence_extension, extension_fields)
    write_csv(SUPP / "survey_set_venue_audited.csv", survey + survey_extension, extension_fields)
    write_csv(SUPP / "evidence_map_venue_audited.csv", evidence + evidence_extension, extension_fields)

    summary = {
        "total_candidates": len(decision_rows),
        "not_in_original_survey300": sum(r["in_survey300"] == "False" for r in decision_rows),
        "decision_counts": dict(Counter(r["triage_decision"] for r in decision_rows)),
        "new_survey_extension_rows": len(survey_extension),
        "new_evidence_extension_rows": len(evidence_extension),
        "venue_audited_survey_set_size": len(survey) + len(survey_extension),
        "venue_audited_evidence_map_size": len(evidence) + len(evidence_extension),
    }
    with (SUPP / "venue_triage_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
