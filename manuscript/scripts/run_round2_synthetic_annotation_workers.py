#!/usr/bin/env python3
"""Run synthetic model annotations for the round2 comparability protocol.

This script intentionally labels every output as synthetic/model-generated.
It must not be used to populate fields that are represented as human judgments.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = (
    REPO
    / "manuscript"
    / "human_coding"
    / "human_round2_evidence274_results"
    / "adjudicated_evidence274_round2_final_full.csv"
)
DEFAULT_PROTOCOL = (
    REPO
    / "manuscript"
    / "human_coding"
    / "annotation_protocol_round2_v2_CLEARER_20260615.md"
)
DEFAULT_OUT_DIR = (
    REPO
    / "manuscript"
    / "human_coding"
    / "round2_v2_CLEARER_synthetic_opus48_20260615"
)

VERDICTS = ["valid", "partial", "invalid", "under-specified"]
RUBRIC_LABELS = ["can_rank", "rank_with_caveats", "cannot_rank", "not_enough_info"]
RUBRIC_TO_VERDICT = {
    "can_rank": "valid",
    "rank_with_caveats": "partial",
    "cannot_rank": "invalid",
    "not_enough_info": "under-specified",
}

FORBIDDEN_INDEPENDENT_WORDS = [
    "failure",
    "assumption",
    "intervention",
    "metric",
    "action",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def norm_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def yes(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y"}


def stable_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def mapped_failure(row: dict[str, str]) -> str:
    value = row.get("primary_failure_type", "")
    mapping = {
        "noisy_retrieval": "relevance/noise",
        "distraction": "relevance/noise",
        "knowledge_conflict": "consistency/conflict",
        "adversarial_corruption": "integrity/adversarial",
        "calibration_control": "uncertainty/OOD",
        "evaluation_benchmark": "sufficiency",
    }
    return mapping.get(value, "U")


def mapped_assumption(row: dict[str, str]) -> str:
    failure = row.get("primary_failure_type", "")
    family = row.get("method_family", "")
    attacker = row.get("attacker_capability", "").strip().lower()
    if failure == "adversarial_corruption" or family == "attack":
        if not attacker or attacker in {"n/a", "na", "not_applicable", "unclear", "unknown"}:
            return "U"
        return "attacker-created"
    if failure == "knowledge_conflict":
        return "natural conflict"
    if failure in {"noisy_retrieval", "distraction", "evaluation_benchmark"}:
        return "benchmark stressor"
    if failure == "calibration_control":
        return "benchmark stressor"
    return "U"


def mapped_intervention(row: dict[str, str]) -> str:
    mapping = {
        "corpus_kb": "corpus/index",
        "retriever": "retriever",
        "context_assembly": "context assembly/compression",
        "generator": "generator prompt/train",
        "system_control": "system-control",
        "evaluation": "evaluation-only",
        "mixed": "U",
        "not_applicable": "U",
    }
    return mapping.get(row.get("intervention_point", ""), "U")


def mapped_metric(row: dict[str, str]) -> str:
    mapping = {
        "attack_success": "attack success",
        "defense_bypass": "attack success",
        "qa_accuracy": "answer correctness",
        "calibration_selective_risk": "calibration/selective risk",
        "faithfulness_hallucination": "evidence support",
        "benchmark_only": "evaluation-only",
        "retrieval_metric": "retrieval recall",
        "not_applicable": "U",
        "other": "U",
    }
    return mapping.get(row.get("evaluation_type", ""), "U")


def row_quality(row: dict[str, str]) -> int:
    score = 0
    for col in [
        "notes",
        "attacker_capability",
        "retriever_generator_setup",
        "metrics_reported",
        "reproducibility_evidence",
    ]:
        if norm_text(row.get(col)):
            score += 1
    if yes(row.get("is_core_candidate")):
        score += 2
    if row.get("evidence_strength") == "peer_reviewed_proceedings":
        score += 1
    try:
        score += int(row.get("confidence_1_to_5") or 0)
    except ValueError:
        pass
    return score


def enrich(row: dict[str, str]) -> dict[str, str]:
    row = dict(row)
    row["_failure"] = mapped_failure(row)
    row["_assumption"] = mapped_assumption(row)
    row["_intervention"] = mapped_intervention(row)
    row["_metric"] = mapped_metric(row)
    row["_quality"] = str(row_quality(row))
    row["_sig"] = "|".join(
        [
            row["_failure"],
            row["_assumption"],
            row["_intervention"],
            row["_metric"],
            row.get("method_family", ""),
        ]
    )
    row["_underspecified_flag"] = "1" if any(
        row.get(c) in {"U", "", "not_applicable", "other"}
        for c in ["_failure", "_assumption", "_intervention", "_metric"]
    ) else "0"
    if not norm_text(row.get("metrics_reported")) or not norm_text(row.get("retriever_generator_setup")):
        row["_underspecified_flag"] = "1"
    return row


def choose_pairs(rows: list[dict[str, str]], per_class: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    filtered = [
        enrich(r)
        for r in rows
        if yes(r.get("screen_in_scope"))
        and yes(r.get("include_in_evidence_map"))
        and norm_text(r.get("paper_id"))
        and norm_text(r.get("title"))
    ]
    filtered.sort(key=lambda r: (-int(r["_quality"]), r["paper_id"]))
    by_sig: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    by_failure: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    under_rows: list[dict[str, str]] = []
    for row in filtered:
        by_sig[row["_sig"]].append(row)
        by_failure[row["_failure"]].append(row)
        if row["_underspecified_flag"] == "1":
            under_rows.append(row)

    chosen: list[dict[str, object]] = []
    used_pairs: set[tuple[str, str]] = set()

    def add_pair(a: dict[str, str], b: dict[str, str], expected: str, reason: str) -> bool:
        if a["paper_id"] == b["paper_id"]:
            return False
        key = stable_key(a["paper_id"], b["paper_id"])
        if key in used_pairs:
            return False
        used_pairs.add(key)
        chosen.append(
            {
                "expected_verdict_heuristic": expected,
                "construction_note": reason,
                "paper_a": a,
                "paper_b": b,
            }
        )
        return True

    # Valid candidates: exact metadata signature match, avoiding ambiguous U values.
    sigs = list(by_sig.items())
    rng.shuffle(sigs)
    sigs.sort(key=lambda item: (-len(item[1]), item[0]))
    for sig, group in sigs:
        if len([p for p in chosen if p["expected_verdict_heuristic"] == "valid"]) >= per_class:
            break
        if "U" in sig:
            continue
        group = sorted(group, key=lambda r: (-int(r["_quality"]), r["paper_id"]))
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                if add_pair(group[i], group[j], "valid", "same mapped failure/assumption/intervention/metric/method-family signature"):
                    break
            if len([p for p in chosen if p["expected_verdict_heuristic"] == "valid"]) >= per_class:
                break

    # Partial candidates: same broad failure/assumption, but one downstream dimension differs.
    for failure, group in sorted(by_failure.items(), key=lambda item: (-len(item[1]), item[0])):
        if len([p for p in chosen if p["expected_verdict_heuristic"] == "partial"]) >= per_class:
            break
        group = sorted(group, key=lambda r: (-int(r["_quality"]), r["paper_id"]))
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["_assumption"] != b["_assumption"] or "U" in {a["_failure"], b["_failure"], a["_assumption"], b["_assumption"]}:
                    continue
                downstream_diff = (
                    a["_intervention"] != b["_intervention"]
                    or a["_metric"] != b["_metric"]
                    or a.get("method_family") != b.get("method_family")
                )
                if downstream_diff and add_pair(a, b, "partial", "same broad evidence problem but downstream dimensions differ"):
                    break
            if len([p for p in chosen if p["expected_verdict_heuristic"] == "partial"]) >= per_class:
                break

    # Invalid candidates: incompatible scientific games, especially attacker-created vs non-adversarial or different broad failures.
    candidates = filtered[:]
    for a in candidates:
        if len([p for p in chosen if p["expected_verdict_heuristic"] == "invalid"]) >= per_class:
            break
        for b in candidates:
            if a["paper_id"] == b["paper_id"]:
                continue
            incompatible = (
                (a["_assumption"] == "attacker-created" and b["_assumption"] not in {"attacker-created", "U"})
                or (b["_assumption"] == "attacker-created" and a["_assumption"] not in {"attacker-created", "U"})
                or (a["_failure"] != b["_failure"] and "U" not in {a["_failure"], b["_failure"]})
            )
            role_conflict = {a.get("method_family"), b.get("method_family")} == {"attack", "defense_mitigation"}
            if (incompatible or role_conflict) and add_pair(a, b, "invalid", "broad problem or role is incompatible for direct ranking"):
                break

    # Under-specified candidates: at least one paper has missing or ambiguous required metadata.
    under_rows = sorted(under_rows, key=lambda r: (-int(r["_quality"]), r["paper_id"]))
    for a in under_rows:
        if len([p for p in chosen if p["expected_verdict_heuristic"] == "under-specified"]) >= per_class:
            break
        partner_pool = by_failure.get(a["_failure"], filtered)
        partner_pool = sorted(partner_pool, key=lambda r: (-int(r["_quality"]), r["paper_id"]))
        for b in partner_pool:
            if add_pair(a, b, "under-specified", "one or both papers lack a required coordinate in available metadata"):
                break

    counts = collections.Counter(p["expected_verdict_heuristic"] for p in chosen)
    missing = {v: per_class - counts.get(v, 0) for v in VERDICTS if counts.get(v, 0) < per_class}
    if missing:
        raise SystemExit(f"Could not construct balanced pair set; missing {missing}")

    # Keep exactly per_class per heuristic class and shuffle final order.
    final = []
    for verdict in VERDICTS:
        final.extend([p for p in chosen if p["expected_verdict_heuristic"] == verdict][:per_class])
    rng.shuffle(final)
    for idx, pair in enumerate(final, 1):
        pair["pair_id"] = f"R2-20260615-{idx:03d}"
        pair["area"] = pair["paper_a"]["_failure"] if pair["paper_a"]["_failure"] == pair["paper_b"]["_failure"] else "mixed"
    return final


def materialize_pairs(pairs: list[dict[str, object]], out_dir: Path) -> None:
    annotation_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    hidden_rows: list[dict[str, object]] = []
    for pair in pairs:
        a = pair["paper_a"]
        b = pair["paper_b"]
        assert isinstance(a, dict) and isinstance(b, dict)
        base = {
            "pair_id": pair["pair_id"],
            "area": pair["area"],
            "paper_a_key": a["paper_id"],
            "paper_a_title": a["title"],
            "paper_b_key": b["paper_id"],
            "paper_b_title": b["title"],
        }
        annotation_rows.append(base)
        context = dict(base)
        for prefix, row in [("a", a), ("b", b)]:
            for col in [
                "authors",
                "year",
                "source_or_venue",
                "url",
                "primary_failure_type",
                "method_family",
                "intervention_point",
                "evaluation_type",
                "evidence_strength",
                "notes",
                "attacker_capability",
                "retriever_generator_setup",
                "metrics_reported",
                "reproducibility_evidence",
            ]:
                context[f"paper_{prefix}_{col}"] = row.get(col, "")
        context_rows.append(context)
        hidden = dict(base)
        hidden.update(
            {
                "expected_verdict_heuristic": pair["expected_verdict_heuristic"],
                "construction_note": pair["construction_note"],
                "paper_a_mapped_failure": a["_failure"],
                "paper_a_mapped_assumption": a["_assumption"],
                "paper_a_mapped_intervention": a["_intervention"],
                "paper_a_mapped_metric": a["_metric"],
                "paper_b_mapped_failure": b["_failure"],
                "paper_b_mapped_assumption": b["_assumption"],
                "paper_b_mapped_intervention": b["_intervention"],
                "paper_b_mapped_metric": b["_metric"],
            }
        )
        hidden_rows.append(hidden)

    write_csv(
        out_dir / "paper_pairs_for_annotation.csv",
        annotation_rows,
        ["pair_id", "area", "paper_a_key", "paper_a_title", "paper_b_key", "paper_b_title"],
    )
    write_csv(out_dir / "paper_pairs_with_context_for_model.csv", context_rows, list(context_rows[0].keys()))
    write_csv(out_dir / "coordinator_hidden_pair_key_synthetic_heuristic.csv", hidden_rows, list(hidden_rows[0].keys()))


def read_completed(raw_path: Path) -> dict[str, dict[str, object]]:
    completed: dict[str, dict[str, object]] = {}
    if not raw_path.exists():
        return completed
    with raw_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("task_key")
            if key and row.get("ok"):
                completed[str(key)] = row
    return completed


def json_from_text(text: str) -> dict[str, object]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def clamp_int(value: object, low: int, high: int, default: int) -> int:
    try:
        i = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, i))


def clean_choice(value: object, choices: list[str], default: str) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "underspecified": "under_specified",
        "under_specified": "under_specified",
        "not_enough_information": "not_enough_info",
        "insufficient_info": "not_enough_info",
        "cant_tell": "not_enough_info",
        "can't_tell": "not_enough_info",
        "cannot_tell": "not_enough_info",
        "unclear": "not_enough_info",
        "low_risk": "can_rank",
        "some_risk": "rank_with_caveats",
        "somewhat_risk": "rank_with_caveats",
        "medium_risk": "rank_with_caveats",
        "high_risk": "cannot_rank",
        "risky": "cannot_rank",
    }
    raw = aliases.get(raw, raw)
    normalized_choices = {c.lower().replace(" ", "_").replace("-", "_"): c for c in choices}
    return normalized_choices.get(raw, default)


def bounded_text(value: object, limit: int = 1200) -> str:
    return norm_text(str(value or ""))[:limit]


def protocol_context(row: dict[str, str]) -> str:
    return f"""Pair ID: {row['pair_id']}

Paper A
- Key: {row['paper_a_key']}
- Title: {row['paper_a_title']}
- Summary: {row.get('paper_a_notes', '')}
- Setup/benchmark: {row.get('paper_a_retriever_generator_setup', '')}
- Reported outcomes: {row.get('paper_a_metrics_reported', '')}
- Threat/action details when stated: {row.get('paper_a_attacker_capability', '')}

Paper B
- Key: {row['paper_b_key']}
- Title: {row['paper_b_title']}
- Summary: {row.get('paper_b_notes', '')}
- Setup/benchmark: {row.get('paper_b_retriever_generator_setup', '')}
- Reported outcomes: {row.get('paper_b_metrics_reported', '')}
- Threat/action details when stated: {row.get('paper_b_attacker_capability', '')}
"""


def independent_context(row: dict[str, str]) -> str:
    return f"""Pair ID: {row['pair_id']}

Paper A
- Key: {row['paper_a_key']}
- Title: {row['paper_a_title']}
- Source/year: {row.get('paper_a_source_or_venue', '')} {row.get('paper_a_year', '')}
- Short description: {row.get('paper_a_notes', '')}
- Reported study details: {row.get('paper_a_retriever_generator_setup', '')}
- Reported outcomes: {row.get('paper_a_metrics_reported', '')}
- Extra details when stated: {row.get('paper_a_attacker_capability', '')}

Paper B
- Key: {row['paper_b_key']}
- Title: {row['paper_b_title']}
- Source/year: {row.get('paper_b_source_or_venue', '')} {row.get('paper_b_year', '')}
- Short description: {row.get('paper_b_notes', '')}
- Reported study details: {row.get('paper_b_retriever_generator_setup', '')}
- Reported outcomes: {row.get('paper_b_metrics_reported', '')}
- Extra details when stated: {row.get('paper_b_attacker_capability', '')}
"""


def build_prompt(role: str, participant_id: str, row: dict[str, str], persona_seed: int) -> tuple[str, str]:
    if role == "independent_gold":
        system = (
            "You are producing a synthetic model annotation for a research-methods audit. "
            "You are not a human participant. Use only the plain-language risk rubric below. "
            "Do not mention or use these words in the rationale: failure, assumption, intervention, metric, action. "
            "Reply only with one concise JSON object; do not include analysis, markdown, or prose outside JSON."
        )
        user = (
            f"Synthetic worker id: {participant_id}; persona seed: {persona_seed}.\n\n"
            f"{independent_context(row)}\n"
            "Plain-language v2 rubric: Assume you can only use the two papers' reported main results to decide "
            "which method you would deploy. Which situation are you in?\n"
            "- can_rank: you can confidently rank them because they measure the same kind of task in the same way.\n"
            "- rank_with_caveats: you can lean toward one side, but only with caveats because the goals or operations are close but not identical.\n"
            "- cannot_rank: you cannot rank them because they are solving different problems; a higher number in one paper would not mean it is better.\n"
            "- not_enough_info: at least one paper leaves out key details, so you cannot judge the comparison.\n\n"
            "The batch was constructed to include all four situations. If everything looks like cannot_rank, re-check the can_rank and rank_with_caveats anchors.\n\n"
            'Return JSON with exactly these keys: {"rubric_label": "...", "confidence_1_5": 1, '
            '"rubric_rationale": "one plain spoken sentence"} Keep the sentence concise.'
        )
        return system, user

    role_line = "ordinary expert judgment without the coordinate codebook" if role == "control" else "the five-coordinate protocol"
    system = (
        "You are producing a synthetic model annotation for a research-methods audit. "
        "You are not a human participant. Decide whether a direct comparison or leaderboard-style ranking of the two papers is valid. "
        "Reply only with one concise JSON object; do not include analysis, markdown, or prose outside JSON."
    )
    protocol_rules = ""
    if role in {"protocol", "coordinate_gold"}:
        protocol_rules = (
            "\nUse the five-coordinate decision tree, but keep it brief.\n"
            "Coordinates: failure_type, evidence_assumption, intervention_point, metric_target, action_policy.\n"
            "Apply in order: missing required coordinate -> under-specified; different failure_type or evidence_assumption -> invalid; "
            "same game and intervention/metric/action all align for a leaderboard -> valid; same game with a downstream mismatch -> partial.\n"
            "Use compact coordinate values such as integrity/adversarial, attacker-created, corpus/index, attack success, answer/filter/abstain/U.\n"
        )
    else:
        protocol_rules = (
            "\nUse ordinary expert judgment only. Do not fill coordinate fields. "
            "Return blank strings for failure_type, evidence_assumption, intervention_point, metric_target, action_policy, and breaking_coordinates.\n"
        )

    extra_gold = ""
    if role == "coordinate_gold":
        extra_gold = ' Include "what_valid_comparison_requires" as a concrete one-sentence requirement for making the comparison valid.'

    user = (
        f"Synthetic worker id: {participant_id}; persona seed: {persona_seed}; role: {role_line}.\n"
        f"{protocol_rules}\n"
        f"{protocol_context(row)}\n"
        "Verdict choices: valid, partial, invalid, under-specified.\n"
        "Return JSON with exactly these keys: "
        '{"verdict": "...", "confidence_1_5": 1, "failure_type": "", "evidence_assumption": "", '
        '"intervention_point": "", "metric_target": "", "action_policy": "", "breaking_coordinates": "", '
        '"rationale": "1-2 concise sentences", "what_valid_comparison_requires": ""}.'
        f"{extra_gold}"
    )
    return system, user


def call_model(endpoint: str, model: str, system: str, user: str, temperature: float, max_tokens: int, retries: int) -> tuple[str, dict[str, object]]:
    is_responses_endpoint = endpoint.rstrip("/").endswith("/responses")
    if is_responses_endpoint:
        body = json.dumps(
            {
                "model": model,
                "stream": False,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "instructions": system,
                "input": user,
            }
        ).encode("utf-8")
    else:
        body = json.dumps(
            {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(endpoint, data=body, headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as response:
                data = json.load(response)
            if is_responses_endpoint:
                content = extract_responses_text(data)
            else:
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"empty choices in response: {json.dumps(data, ensure_ascii=False)[:500]}")
                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, list):
                    content = "\n".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
            content = str(content or "").strip()
            if not content:
                raise RuntimeError(f"empty message content in response: {json.dumps(data, ensure_ascii=False)[:500]}")
            return content, data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"model call failed after {retries} retries: {last_error}")


def extract_responses_text(data: dict[str, object]) -> str:
    output_text = data.get("output_text")
    if output_text:
        return str(output_text)
    texts: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("text"):
                    texts.append(str(part["text"]))
    return "\n".join(texts)


def call_and_parse(
    endpoint: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
    retries: int,
) -> tuple[str, dict[str, object], dict[str, object]]:
    last_error: Exception | None = None
    last_content = ""
    strict_user = user
    for parse_attempt in range(3):
        content, response = call_model(endpoint, model, system, strict_user, temperature, max_tokens, retries)
        last_content = content
        try:
            return content, response, json_from_text(content)
        except Exception as exc:
            last_error = exc
            strict_user = (
                user
                + "\n\nYour previous response was not parseable JSON. Return one raw JSON object only. "
                "No markdown, no prose before or after the JSON."
            )
            temperature = 0
            time.sleep(1 + parse_attempt)
    raise RuntimeError(f"could not parse JSON after strict retries: {last_error}; last_content={last_content[:500]!r}")


def normalize_annotation(role: str, payload: dict[str, object]) -> dict[str, object]:
    if role == "independent_gold":
        label = clean_choice(payload.get("rubric_label"), RUBRIC_LABELS, "not_enough_info")
        rationale = bounded_text(payload.get("rubric_rationale"), 800)
        for word in FORBIDDEN_INDEPENDENT_WORDS:
            rationale = re.sub(rf"\b{re.escape(word)}\b", "[redacted]", rationale, flags=re.I)
        return {
            "rubric_label": label,
            "mapped_verdict": RUBRIC_TO_VERDICT[label],
            "confidence_1_5": clamp_int(payload.get("confidence_1_5"), 1, 5, 3),
            "rubric_rationale": rationale,
        }
    verdict = clean_choice(payload.get("verdict"), VERDICTS, "under-specified")
    row = {
        "verdict": verdict,
        "confidence_1_5": clamp_int(payload.get("confidence_1_5"), 1, 5, 3),
        "failure_type": bounded_text(payload.get("failure_type"), 120),
        "evidence_assumption": bounded_text(payload.get("evidence_assumption"), 180),
        "intervention_point": bounded_text(payload.get("intervention_point"), 160),
        "metric_target": bounded_text(payload.get("metric_target"), 160),
        "action_policy": bounded_text(payload.get("action_policy"), 160),
        "breaking_coordinates": bounded_text(payload.get("breaking_coordinates"), 240),
        "rationale": bounded_text(payload.get("rationale"), 1200),
        "what_valid_comparison_requires": bounded_text(payload.get("what_valid_comparison_requires"), 1200),
    }
    if role == "control":
        for col in ["failure_type", "evidence_assumption", "intervention_point", "metric_target", "action_policy", "breaking_coordinates"]:
            row[col] = ""
    return row


def synthetic_participants() -> list[dict[str, str]]:
    specs = [
        ("control", 8),
        ("protocol", 8),
        ("coordinate_gold", 7),
        ("independent_gold", 7),
    ]
    rows = []
    for role, n in specs:
        for i in range(1, n + 1):
            rows.append(
                {
                    "participant_id": f"synthetic_{role}_{i:03d}",
                    "role": role,
                    "qualification_record_public": "Synthetic local Copilot API model worker; NOT a human annotator; do not mark human-verified.",
                    "condition": role if role in {"control", "protocol"} else "",
                }
            )
    return rows


def task_key(role: str, participant_id: str, pair_id: str) -> str:
    return f"{role}|{participant_id}|{pair_id}"


def run_annotations(args: argparse.Namespace, out_dir: Path) -> None:
    context_rows = read_csv(out_dir / "paper_pairs_with_context_for_model.csv")
    participants = synthetic_participants()
    raw_path = out_dir / "raw_model_annotations.jsonl"
    failed_path = out_dir / "failed_model_annotations.jsonl"
    completed = read_completed(raw_path)
    write_lock = threading.Lock()

    tasks = []
    for participant in participants:
        role = participant["role"]
        for pair in context_rows:
            key = task_key(role, participant["participant_id"], pair["pair_id"])
            if key not in completed:
                tasks.append((key, participant, pair))

    total = len(tasks) + len(completed)
    print(f"synthetic annotation tasks: total={total} completed={len(completed)} remaining={len(tasks)}", file=sys.stderr)

    def worker(item: tuple[str, dict[str, str], dict[str, str]]) -> dict[str, object]:
        key, participant, pair = item
        role = participant["role"]
        persona_seed = int(short_hash(key), 16) % 1_000_000
        system, user = build_prompt(role, participant["participant_id"], pair, persona_seed)
        started = time.time()
        content, response, payload = call_and_parse(
            args.endpoint,
            args.model,
            system,
            user,
            args.temperature,
            args.max_tokens,
            args.retries,
        )
        parsed = normalize_annotation(role, payload)
        elapsed = time.time() - started
        result = {
            "ok": True,
            "task_key": key,
            "role": role,
            "participant_id": participant["participant_id"],
            "pair_id": pair["pair_id"],
            "model": args.model,
            "endpoint": args.endpoint,
            "synthetic": True,
            "elapsed_seconds": round(elapsed, 3),
            "raw_content": content,
            "usage": response.get("usage", {}),
            "annotation": parsed,
        }
        with write_lock:
            with raw_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result

    done_count = len(completed)
    failures = 0
    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(worker, task): task for task in tasks}
            for future in concurrent.futures.as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                    done_count += 1
                    if done_count % 20 == 0 or done_count == total:
                        print(f"progress {done_count}/{total}: {result['task_key']}", file=sys.stderr)
                except Exception as exc:
                    failures += 1
                    key, participant, pair = task
                    error_row = {
                        "ok": False,
                        "task_key": key,
                        "role": participant["role"],
                        "participant_id": participant["participant_id"],
                        "pair_id": pair["pair_id"],
                        "error": repr(exc),
                    }
                    with write_lock:
                        with failed_path.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(error_row, ensure_ascii=False) + "\n")
                    print(f"FAILED {key}: {exc}", file=sys.stderr)
    if failures:
        raise SystemExit(f"{failures} tasks failed; rerun script to resume")


def load_all_raw(raw_path: Path) -> list[dict[str, object]]:
    rows = []
    seen = set()
    if not raw_path.exists():
        return rows
    with raw_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("task_key")
            if row.get("ok") and key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def majority(values: list[str], order: list[str]) -> tuple[str, str]:
    counts = collections.Counter(v for v in values if v)
    if not counts:
        return "", "{}"
    best = sorted(counts.items(), key=lambda item: (-item[1], order.index(item[0]) if item[0] in order else 999, item[0]))[0][0]
    return best, json.dumps(dict(counts), ensure_ascii=False, sort_keys=True)


def emit_tables(out_dir: Path, args: argparse.Namespace) -> None:
    raw_rows = load_all_raw(out_dir / "raw_model_annotations.jsonl")
    pair_context = {r["pair_id"]: r for r in read_csv(out_dir / "paper_pairs_with_context_for_model.csv")}
    participant_rows = synthetic_participants()
    write_csv(
        out_dir / "annotator_metadata_anonymized.csv",
        [
            {
                "participant_id": r["participant_id"],
                "role": r["role"],
                "condition": r["condition"],
                "qualification_record_public": r["qualification_record_public"],
            }
            for r in participant_rows
        ],
        ["participant_id", "role", "condition", "qualification_record_public"],
    )

    arm_rows = []
    coordinate_rows = []
    independent_rows = []
    for raw in raw_rows:
        role = str(raw["role"])
        ann = raw["annotation"]
        assert isinstance(ann, dict)
        pair = pair_context[str(raw["pair_id"])]
        if role in {"control", "protocol"}:
            arm_rows.append(
                {
                    "participant_id": raw["participant_id"],
                    "condition": role,
                    "pair_id": raw["pair_id"],
                    "verdict": ann["verdict"],
                    "confidence_1_5": ann["confidence_1_5"],
                    "decision_time_seconds": raw["elapsed_seconds"],
                    "failure_type": ann["failure_type"],
                    "evidence_assumption": ann["evidence_assumption"],
                    "intervention_point": ann["intervention_point"],
                    "metric_target": ann["metric_target"],
                    "action_policy": ann["action_policy"],
                    "breaking_coordinates": ann["breaking_coordinates"],
                    "rationale": ann["rationale"],
                    "paper_a_id": pair["paper_a_key"],
                    "paper_a_title": pair["paper_a_title"],
                    "paper_b_id": pair["paper_b_key"],
                    "paper_b_title": pair["paper_b_title"],
                    "synthetic_model": raw["model"],
                    "synthetic_not_human": "1",
                }
            )
        elif role == "coordinate_gold":
            coordinate_rows.append(
                {
                    "gold_adjudicator_id": raw["participant_id"],
                    "pair_id": raw["pair_id"],
                    "paper_a_id": pair["paper_a_key"],
                    "paper_a_title": pair["paper_a_title"],
                    "paper_b_id": pair["paper_b_key"],
                    "paper_b_title": pair["paper_b_title"],
                    "gold_verdict": ann["verdict"],
                    "gold_confidence_1_5": ann["confidence_1_5"],
                    "failure_type": ann["failure_type"],
                    "evidence_assumption": ann["evidence_assumption"],
                    "intervention_point": ann["intervention_point"],
                    "metric_target": ann["metric_target"],
                    "action_policy": ann["action_policy"],
                    "breaking_coordinates": ann["breaking_coordinates"],
                    "gold_rationale": ann["rationale"],
                    "what_valid_comparison_requires": ann["what_valid_comparison_requires"],
                    "synthetic_model": raw["model"],
                    "synthetic_not_human": "1",
                }
            )
        elif role == "independent_gold":
            independent_rows.append(
                {
                    "independent_adjudicator_id": raw["participant_id"],
                    "pair_id": raw["pair_id"],
                    "rubric_label": ann["rubric_label"],
                    "mapped_verdict": ann["mapped_verdict"],
                    "confidence_1_5": ann["confidence_1_5"],
                    "rubric_rationale": ann["rubric_rationale"],
                    "synthetic_model": raw["model"],
                    "synthetic_not_human": "1",
                }
            )

    arm_fields = [
        "participant_id",
        "condition",
        "pair_id",
        "verdict",
        "confidence_1_5",
        "decision_time_seconds",
        "failure_type",
        "evidence_assumption",
        "intervention_point",
        "metric_target",
        "action_policy",
        "breaking_coordinates",
        "rationale",
        "paper_a_id",
        "paper_a_title",
        "paper_b_id",
        "paper_b_title",
        "synthetic_model",
        "synthetic_not_human",
    ]
    coord_fields = [
        "gold_adjudicator_id",
        "pair_id",
        "paper_a_id",
        "paper_a_title",
        "paper_b_id",
        "paper_b_title",
        "gold_verdict",
        "gold_confidence_1_5",
        "failure_type",
        "evidence_assumption",
        "intervention_point",
        "metric_target",
        "action_policy",
        "breaking_coordinates",
        "gold_rationale",
        "what_valid_comparison_requires",
        "synthetic_model",
        "synthetic_not_human",
    ]
    ind_fields = [
        "independent_adjudicator_id",
        "pair_id",
        "rubric_label",
        "mapped_verdict",
        "confidence_1_5",
        "rubric_rationale",
        "synthetic_model",
        "synthetic_not_human",
    ]
    write_csv(out_dir / "participant_responses_synthetic_model.csv", sorted(arm_rows, key=lambda r: (r["participant_id"], r["pair_id"])), arm_fields)
    write_csv(out_dir / "coordinate_gold_individual_synthetic_model.csv", sorted(coordinate_rows, key=lambda r: (r["gold_adjudicator_id"], r["pair_id"])), coord_fields)
    write_csv(out_dir / "independent_gold_individual_synthetic_model.csv", sorted(independent_rows, key=lambda r: (r["independent_adjudicator_id"], r["pair_id"])), ind_fields)

    by_pair_coord: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for row in coordinate_rows:
        by_pair_coord[str(row["pair_id"])].append(row)
    coord_consensus = []
    for pair_id, rows in sorted(by_pair_coord.items()):
        verdict, counts = majority([str(r["gold_verdict"]) for r in rows], VERDICTS)
        pair = pair_context[pair_id]
        winners = [r for r in rows if r["gold_verdict"] == verdict]
        chosen = sorted(winners, key=lambda r: (-int(r["gold_confidence_1_5"]), str(r["gold_adjudicator_id"])))[0] if winners else rows[0]
        coord_consensus.append(
            {
                "pair_id": pair_id,
                "gold_verdict": verdict,
                "gold_confidence_1_5": round(sum(int(r["gold_confidence_1_5"]) for r in rows) / len(rows), 3),
                "breaking_coordinates": chosen["breaking_coordinates"],
                "gold_rationale": chosen["gold_rationale"],
                "what_valid_comparison_requires": chosen["what_valid_comparison_requires"],
                "panel_vote_counts": counts,
                "paper_a_id": pair["paper_a_key"],
                "paper_a_title": pair["paper_a_title"],
                "paper_b_id": pair["paper_b_key"],
                "paper_b_title": pair["paper_b_title"],
                "synthetic_model": args.model,
                "synthetic_not_human": "1",
            }
        )
    write_csv(
        out_dir / "coordinate_gold_consensus_synthetic_model.csv",
        coord_consensus,
        [
            "pair_id",
            "gold_verdict",
            "gold_confidence_1_5",
            "breaking_coordinates",
            "gold_rationale",
            "what_valid_comparison_requires",
            "panel_vote_counts",
            "paper_a_id",
            "paper_a_title",
            "paper_b_id",
            "paper_b_title",
            "synthetic_model",
            "synthetic_not_human",
        ],
    )

    by_pair_ind: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for row in independent_rows:
        by_pair_ind[str(row["pair_id"])].append(row)
    ind_consensus = []
    for pair_id, rows in sorted(by_pair_ind.items()):
        label, counts = majority([str(r["rubric_label"]) for r in rows], RUBRIC_LABELS)
        pair = pair_context[pair_id]
        winners = [r for r in rows if r["rubric_label"] == label]
        chosen = sorted(winners, key=lambda r: (-int(r["confidence_1_5"]), str(r["independent_adjudicator_id"])))[0] if winners else rows[0]
        ind_consensus.append(
            {
                "pair_id": pair_id,
                "rubric_label": label,
                "mapped_verdict": RUBRIC_TO_VERDICT.get(label, "under-specified"),
                "rubric_rationale": chosen["rubric_rationale"],
                "panel_vote_counts": counts,
                "paper_a_id": pair["paper_a_key"],
                "paper_a_title": pair["paper_a_title"],
                "paper_b_id": pair["paper_b_key"],
                "paper_b_title": pair["paper_b_title"],
                "synthetic_model": args.model,
                "synthetic_not_human": "1",
            }
        )
    write_csv(
        out_dir / "independent_gold_consensus_synthetic_model.csv",
        ind_consensus,
        [
            "pair_id",
            "rubric_label",
            "mapped_verdict",
            "rubric_rationale",
            "panel_vote_counts",
            "paper_a_id",
            "paper_a_title",
            "paper_b_id",
            "paper_b_title",
            "synthetic_model",
            "synthetic_not_human",
        ],
    )

    manifest = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protocol": str(args.protocol),
        "source": str(args.source),
        "endpoint": args.endpoint,
        "model": args.model,
        "workers": args.workers,
        "synthetic_not_human": True,
        "warning": "Model-generated synthetic annotations. Do not report as human annotation or human-verified evidence.",
        "pair_count": len(pair_context),
        "participant_counts": dict(collections.Counter(r["role"] for r in participant_rows)),
        "raw_annotation_count": len(raw_rows),
        "arm_response_count": len(arm_rows),
        "coordinate_gold_count": len(coordinate_rows),
        "independent_gold_count": len(independent_rows),
        "coordinate_gold_consensus_counts": dict(collections.Counter(r["gold_verdict"] for r in coord_consensus)),
        "independent_gold_consensus_counts": dict(collections.Counter(r["mapped_verdict"] for r in ind_consensus)),
        "files": {
            "paper_pairs_for_annotation": "paper_pairs_for_annotation.csv",
            "paper_pairs_with_context_for_model": "paper_pairs_with_context_for_model.csv",
            "coordinator_hidden_pair_key_synthetic_heuristic": "coordinator_hidden_pair_key_synthetic_heuristic.csv",
            "participant_responses_synthetic_model": "participant_responses_synthetic_model.csv",
            "coordinate_gold_individual_synthetic_model": "coordinate_gold_individual_synthetic_model.csv",
            "coordinate_gold_consensus_synthetic_model": "coordinate_gold_consensus_synthetic_model.csv",
            "independent_gold_individual_synthetic_model": "independent_gold_individual_synthetic_model.csv",
            "independent_gold_consensus_synthetic_model": "independent_gold_consensus_synthetic_model.csv",
            "annotator_metadata_anonymized": "annotator_metadata_anonymized.csv",
            "raw_model_annotations": "raw_model_annotations.jsonl",
        },
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--endpoint", default="http://127.0.0.1:4143/v1/responses")
    parser.add_argument("--model", default="claude-opus-4.8")
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--per-class", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=2200)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--emit-only", action="store_true")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"missing source CSV: {args.source}")
    if not args.protocol.exists():
        raise SystemExit(f"missing protocol: {args.protocol}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if not args.emit_only:
        rows = read_csv(args.source)
        pairs = choose_pairs(rows, args.per_class, args.seed)
        materialize_pairs(pairs, args.out_dir)
        print(f"wrote {len(pairs)} balanced synthetic pair candidates to {args.out_dir}", file=sys.stderr)

    if args.build_only:
        return

    if not args.emit_only:
        run_annotations(args, args.out_dir)
    emit_tables(args.out_dir, args)
    print(f"wrote synthetic annotation tables to {args.out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
