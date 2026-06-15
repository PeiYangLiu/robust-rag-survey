#!/usr/bin/env python3
"""Build a 100-paper venue-linked collection for multimodal/scenario RAG.

The goal is to complement the text/document-grounded robust-RAG survey with
published/open PDFs covering multimodal, graph, table, agentic, code/tool,
domain-specific, and long-context RAG scenarios.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
OUT_DIR = PDF_DIR / "multimodal_rag_100"
META = ROOT / "metadata"
VENUE200 = META / "venue_200_opus_citation_audit.csv"
ACCEPTED = META / "venue_accepts_rag_related.csv"
OUT_MANIFEST = META / "multimodal_rag_100_manifest.csv"
OUT_SUMMARY = META / "multimodal_rag_100_summary.json"
TARGET = 100


SCENARIOS = {
    "vision_multimodal": [
        "multimodal", "visual", "vision", "image", "vqa", "video", "mllm", "vlm",
        "lvlm", "vision-language", "visually", "perception", "motion",
    ],
    "graph_kg": ["graph", "knowledge graph", "kg", "subgraph", "graphqa", "textual graph"],
    "table_structured": ["table", "tabular", "database", "structured", "sql", "text-to-sql"],
    "agent_memory_tool": [
        "agent", "agents", "memory", "tool", "web-search", "web search", "search",
        "planner", "planning", "interactive",
    ],
    "code_math_symbolic": [
        "code", "program", "symbolic", "theorem", "lean", "math", "mathematical",
        "symbolic regression",
    ],
    "domain_biomed_legal_finance": [
        "medical", "medicine", "biomedical", "health", "clinical", "legal", "law",
        "finance", "financial", "patent", "e-commerce", "molecular",
    ],
    "long_context_doc": [
        "long-context", "long context", "long document", "document", "million-token",
        "long-form", "large context",
    ],
}

EXCLUDE_TITLE = [
    "diffusion models",
    "ad auctions",
    "enzyme generation",
    "time series",
    "tutorial books",
    "linear estimation",
    "espresso sentence embeddings",
    "generative representational instruction tuning",
    "kv cache",
    "block-attention",
    "conformal prediction",
    "gradient-free calibration",
    "label shift",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def norm_title(title: str) -> str:
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    title = re.sub(r"\b(a|an|the)\b", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def slug(text: str, max_len: int = 90) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").lower()).strip("_")
    return value[:max_len].strip("_") or "paper"


def scenario_for(row: dict[str, str]) -> tuple[str, list[str]]:
    text = " ".join([
    row.get("title", ""),
    row.get("abstract", ""),
    row.get("matched_terms", ""),
    ]).lower()
    hits = []
    for name, terms in SCENARIOS.items():
        if any(term in text for term in terms):
            hits.append(name)
    if not hits:
        return "other_rag", []
    # Prefer explicitly non-text settings over broad long-context/doc hits.
    priority = [
        "vision_multimodal",
        "graph_kg",
        "table_structured",
        "agent_memory_tool",
        "code_math_symbolic",
        "domain_biomed_legal_finance",
        "long_context_doc",
    ]
    return sorted(hits, key=priority.index)[0], hits


def relevant(row: dict[str, str]) -> bool:
    text = " ".join([row.get("title", ""), row.get("abstract", ""), row.get("matched_terms", "")]).lower()
    if any(term in row.get("title", "").lower() for term in EXCLUDE_TITLE):
        return False
    title = row.get("title", "").lower()
    strong_rag = any(term in text for term in ["retrieval augmented generation", "retrieval-augmented generation", " rag ", "rag:", "rag-", "rag.", "rag,"])
    title_retrieval = any(term in title for term in ["retrieval", "retriever", "rag", "search"])
    has_rag = strong_rag or title_retrieval
    scenario, _ = scenario_for(row)
    return has_rag and scenario != "other_rag"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_pdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 10_000:
        return False
    return b"%PDF" in path.read_bytes()[:2048]


def request_pdf(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "robust-rag-survey-multimodal100/0.1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def copy_or_download(row: dict[str, str], index: int) -> dict[str, str] | None:
    title = row.get("title", "")
    year = row.get("year", "")
    venue = row.get("venue", "")
    scenario, scenario_hits = scenario_for(row)
    dest = OUT_DIR / f"{index:03d}_{slug(scenario, 24)}_{slug(year + '_' + venue, 34)}_{slug(title)}.pdf"
    src = None
    for key in ["curated_pdf", "local_pdf", "source_local_pdf"]:
        if row.get(key):
            candidate = ROOT / row[key]
            if is_pdf(candidate):
                src = candidate
                break
    status = "copied_existing"
    if src:
        shutil.copy2(src, dest)
    else:
        url = row.get("pdf_url") or row.get("venue_pdf_url") or row.get("url") or ""
        if not url:
            return None
        try:
            time.sleep(0.15)
            data = request_pdf(url)
            if b"%PDF" not in data[:2048]:
                return None
            dest.write_bytes(data)
            status = "downloaded"
        except Exception:
            return None
    if not is_pdf(dest):
        dest.unlink(missing_ok=True)
        return None
    return {
        "index": str(index),
        "scenario": scenario,
        "scenario_hits": ";".join(scenario_hits),
        "title": title,
        "year": year,
        "venue": venue,
        "selection_source": row.get("selection_source", row.get("source", "")),
        "pdf_url": row.get("pdf_url", row.get("url", "")),
        "landing_url": row.get("landing_url", ""),
        "related_score": row.get("related_score", ""),
        "opus_decision": row.get("decision", ""),
        "opus_perspective": row.get("primary_perspective", ""),
        "opus_reason": row.get("reason", ""),
        "curated_pdf": str(dest.relative_to(ROOT)),
        "bytes": str(dest.stat().st_size),
        "sha256": sha256(dest),
        "status": status,
    }


def candidate_rows() -> list[dict[str, str]]:
    out = []
    for row in read_csv(VENUE200):
        if row.get("decision") == "exclude":
            continue
        if relevant(row):
            row = dict(row)
            row["candidate_source"] = "venue200_opus"
            priority = int(row.get("cite_priority") or 0) + 40
            row["_priority"] = str(priority)
            out.append(row)
    for row in read_csv(ACCEPTED):
        if not relevant(row):
            continue
        row = dict(row)
        row["candidate_source"] = "accepted_metadata"
        row["_priority"] = str(int(row.get("related_score") or 0))
        out.append(row)
    # Deduplicate by title, keeping highest priority.
    best: dict[str, dict[str, str]] = {}
    for row in out:
        nt = norm_title(row.get("title", ""))
        if not nt:
            continue
        if nt not in best or int(row.get("_priority") or 0) > int(best[nt].get("_priority") or 0):
            best[nt] = row
    rows = list(best.values())
    rows.sort(key=lambda r: (-int(r.get("_priority") or 0), scenario_for(r)[0], r.get("title", "")))
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.pdf"):
        old.unlink()
    candidates = candidate_rows()
    selected: list[dict[str, str]] = []
    selected_titles: set[str] = set()
    by_scenario: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        by_scenario[scenario_for(row)[0]].append(row)
    scenario_order = list(SCENARIOS) + ["other_rag"]
    # First pass: balance scenarios.
    per_scenario_floor = 10
    for scenario in scenario_order:
        for row in by_scenario.get(scenario, []):
            if len([r for r in selected if r["scenario"] == scenario]) >= per_scenario_floor:
                break
            nt = norm_title(row.get("title", ""))
            if nt in selected_titles:
                continue
            rec = copy_or_download(row, len(selected) + 1)
            if rec:
                selected.append(rec)
                selected_titles.add(nt)
    # Second pass: fill by priority.
    for row in candidates:
        if len(selected) >= TARGET:
            break
        nt = norm_title(row.get("title", ""))
        if nt in selected_titles:
            continue
        rec = copy_or_download(row, len(selected) + 1)
        if rec:
            selected.append(rec)
            selected_titles.add(nt)

    fields = [
        "index", "scenario", "scenario_hits", "title", "year", "venue", "selection_source",
        "pdf_url", "landing_url", "related_score", "opus_decision", "opus_perspective",
        "opus_reason", "curated_pdf", "bytes", "sha256", "status",
    ]
    with OUT_MANIFEST.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    summary = {
        "target": TARGET,
        "selected": len(selected),
        "collection_dir": str(OUT_DIR.relative_to(ROOT)),
        "manifest": str(OUT_MANIFEST.relative_to(ROOT)),
        "scenario_counts": dict(Counter(r["scenario"] for r in selected)),
        "venue_counts": dict(Counter(r["venue"] for r in selected).most_common(50)),
        "year_counts": dict(Counter(r["year"] for r in selected).most_common()),
        "status_counts": dict(Counter(r["status"] for r in selected)),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if len(selected) < TARGET:
        raise SystemExit(f"selected {len(selected)} < target {TARGET}")


if __name__ == "__main__":
    OUT_MANIFEST = META / "multimodal_rag_100_manifest.csv"
    OUT_SUMMARY = META / "multimodal_rag_100_summary.json"
    main()
