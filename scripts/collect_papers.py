#!/usr/bin/env python3
"""Collect open-access PDFs for a Robust RAG survey corpus.

The collector intentionally uses open sources only (primarily arXiv plus a
small set of verified open conference PDFs) and writes metadata alongside the
downloaded PDFs.
"""

from __future__ import annotations

import csv
import hashlib
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]  # repository root
PDF_DIR = ROOT / "pdfs"
META_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"
TARGET_DOWNLOADS = 220
MAX_CANDIDATES = 700
USER_AGENT = "robust-rag-survey-collector/0.1 (open-access literature collection)"

ARXIV_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


@dataclass
class Paper:
    key: str
    title: str
    authors: list[str]
    year: str
    source: str
    url: str
    pdf_url: str
    abstract: str = ""
    published: str = ""
    categories: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    score: int = 0
    local_pdf: str = ""
    download_status: str = "pending"
    error: str = ""


TOPIC_PATTERNS: dict[str, list[str]] = {
    "rag-core": [
        "retrieval augmented generation",
        "retrieval-augmented generation",
        "retrieval augmented language",
        "retrieval-augmented language",
        "retrieval augmentation",
        "rag",
    ],
    "noisy-retrieval": [
        "noise",
        "noisy",
        "irrelevant",
        "hard negative",
        "distractor",
        "distracting",
        "retrieval error",
        "imperfect retrieval",
        "missing evidence",
    ],
    "knowledge-conflict": [
        "knowledge conflict",
        "conflicting knowledge",
        "parametric knowledge",
        "context compliance",
        "counterfactual",
        "faithful",
        "faithfulness",
        "contextual faithfulness",
    ],
    "adversarial-corruption": [
        "adversarial",
        "attack",
        "poison",
        "poisoning",
        "backdoor",
        "trojan",
        "prompt injection",
        "jailbreak",
        "corruption",
        "malicious",
        "security",
        "privacy",
    ],
    "uncertainty-ood": [
        "uncertainty",
        "out-of-distribution",
        "ood",
        "distribution shift",
        "ambiguous",
        "ambiguity",
        "unanswerable",
        "unknown",
        "scarcity",
    ],
    "calibration-control": [
        "calibration",
        "calibrated",
        "confidence",
        "abstain",
        "abstention",
        "selective",
        "when to retrieve",
        "adaptive retrieval",
        "self-reflective",
        "self-rag",
        "corrective",
    ],
    "evaluation-benchmark": [
        "benchmark",
        "evaluation",
        "stress test",
        "robustness",
        "trustworthy",
        "trustworthiness",
        "reliability",
        "reliable",
    ],
}

ARXIV_QUERIES: list[tuple[str, int]] = [
    ('all:"retrieval augmented generation"', 320),
    ('all:"retrieval-augmented generation"', 320),
    ('all:"retrieval augmented" AND all:"large language model"', 220),
    ('all:"retrieval-augmented" AND all:"large language models"', 220),
    ('all:"retrieval augmented" AND all:robustness', 120),
    ('all:"retrieval augmented" AND all:noisy', 100),
    ('all:"retrieval augmented" AND all:irrelevant', 100),
    ('all:"retrieval augmented" AND all:distractor', 80),
    ('all:"retrieval augmented" AND all:"knowledge conflict"', 80),
    ('all:"retrieval augmented" AND all:"parametric knowledge"', 80),
    ('all:"retrieval augmented" AND all:adversarial', 100),
    ('all:"retrieval augmented" AND all:poisoning', 100),
    ('all:"retrieval augmented" AND all:"prompt injection"', 80),
    ('all:"retrieval augmented" AND all:uncertainty', 100),
    ('all:"retrieval augmented" AND all:calibration', 100),
    ('all:"retrieval augmented" AND all:abstain', 80),
    ('all:"retrieval augmented" AND all:"adaptive retrieval"', 100),
    ('all:"retrieval augmented" AND all:faithfulness', 100),
    ('all:"retrieval augmented" AND all:hallucination', 160),
    ('all:"retrieval augmented" AND all:trustworthy', 120),
    ('all:"retrieval augmented" AND all:security', 120),
    ('all:"retrieval augmented" AND all:privacy', 100),
    ('all:"open-domain question answering" AND all:"retrieval augmented"', 120),
    ('all:"retrieval-augmented generation" AND all:"noise robustness"', 120),
    ('all:"retrieval-augmented generation" AND all:"noisy context"', 120),
    ('all:"retrieval-augmented generation" AND all:"irrelevant context"', 120),
    ('all:"retrieval-augmented generation" AND all:"hard negative"', 100),
    ('all:"retrieval-augmented generation" AND all:"context conflict"', 100),
    ('all:"retrieval-augmented generation" AND all:"knowledge corruption"', 100),
    ('all:"retrieval-augmented generation" AND all:"data poisoning"', 100),
    ('all:"retrieval-augmented generation" AND all:"indirect prompt"', 100),
    ('all:"retrieval-augmented generation" AND all:"unanswerable"', 100),
    ('all:"retrieval-augmented generation" AND all:"selective generation"', 100),
    ('all:"retrieval-augmented generation" AND all:"confidence estimation"', 100),
    ('all:"retrieval-augmented generation" AND all:"uncertainty quantification"', 100),
    ('all:"retrieval-augmented generation" AND all:"trust calibration"', 80),
    ('all:"retrieval-augmented generation" AND all:"negative rejection"', 80),
    ('all:"retrieval-augmented generation" AND all:"information integration"', 80),
    ('all:"retrieval-augmented generation" AND all:"counterfactual robustness"', 80),
    ('all:"retrieval-augmented generation" AND all:"context faithfulness"', 120),
    ('all:"retrieval-augmented generation" AND all:"groundedness"', 120),
    ('all:"retrieval-augmented generation" AND all:"citation"', 100),
    ('all:"retrieval-augmented generation" AND all:"self correction"', 100),
    ('all:"retrieval-augmented generation" AND all:"verification"', 100),
    ('all:"retrieval-augmented generation" AND all:"fact checking"', 100),
    ('all:"retrieval-augmented generation" AND all:"open-domain question answering"', 160),
    ('all:"retrieval augmented language models" AND all:robustness', 160),
    ('all:"retrieval augmented language models" AND all:faithfulness', 140),
    ('all:"retrieval augmented language models" AND all:adversarial', 140),
    ('all:"large language models" AND all:"retrieval" AND all:"knowledge conflict"', 120),
    ('all:"large language models" AND all:"retrieval" AND all:"calibration"', 120),
    ('all:"large language models" AND all:"retrieval" AND all:"abstention"', 120),
    ('all:"large language models" AND all:"retrieval" AND all:"uncertainty"', 160),
    ('all:"large language models" AND all:"retrieval" AND all:"poisoning"', 140),
    ('all:"large language models" AND all:"retrieval" AND all:"prompt injection"', 140),
]

MANUAL_OPEN_PDFS: list[Paper] = [
    Paper(
        key="acl-2024-raat",
        title="Enhancing Noise Robustness of Retrieval-Augmented Language Models with Adaptive Adversarial Training",
        authors=["Feiteng Fang", "Yuelin Bai", "Shiwen Ni", "Min Yang", "Xiaojun Chen", "Ruifeng Xu"],
        year="2024",
        source="ACL Anthology",
        url="https://aclanthology.org/2024.acl-long.540/",
        pdf_url="https://aclanthology.org/2024.acl-long.540.pdf",
    ),
    Paper(
        key="acl-2025-query-robustness",
        title="Investigating the Robustness of Retrieval-Augmented Generation at the Query Level",
        authors=["Sezen Percin", "Xin Su", "Qutub Sha Syed", "Phillip Howard", "Aleksei Kuvshinov", "Leo Schwinn", "Kay-Ulrich Scholl"],
        year="2025",
        source="ACL Anthology",
        url="https://aclanthology.org/2025.gem-1.38/",
        pdf_url="https://aclanthology.org/2025.gem-1.38.pdf",
    ),
    Paper(
        key="acl-2025-faithfulrag",
        title="FaithfulRAG: Fact-Level Conflict Modeling for Context-Faithful Retrieval-Augmented Generation",
        authors=["Qinggang Zhang", "Zhishang Xiang", "Yilin Xiao", "Le Wang", "Junhui Li", "Xinrun Wang", "Jinsong Su"],
        year="2025",
        source="ACL Anthology",
        url="https://aclanthology.org/2025.acl-long.1062/",
        pdf_url="https://aclanthology.org/2025.acl-long.1062.pdf",
    ),
    Paper(
        key="acl-2025-astute-rag",
        title="Astute RAG: Overcoming Imperfect Retrieval Augmentation and Knowledge Conflicts for Large Language Models",
        authors=["Fei Wang", "Xingchen Wan", "Ruoxi Sun", "Jiefeng Chen", "Sercan O Arik"],
        year="2025",
        source="ACL Anthology",
        url="https://aclanthology.org/2025.acl-long.1476/",
        pdf_url="https://aclanthology.org/2025.acl-long.1476.pdf",
    ),
    Paper(
        key="acl-2025-ctrla",
        title="CtrlA: Adaptive Retrieval-Augmented Generation via Inherent Control",
        authors=["Liu Huanshuo", "Hao Zhang", "Zhijiang Guo", "Jing Wang", "Kuicai Dong", "Xiangyang Li", "Yi Quan Lee", "Cong Zhang", "Yong Liu"],
        year="2025",
        source="ACL Anthology",
        url="https://aclanthology.org/2025.findings-acl.652/",
        pdf_url="https://aclanthology.org/2025.findings-acl.652.pdf",
    ),
    Paper(
        key="acl-2025-do-not-abstain",
        title="Do not Abstain! Identify and Solve the Uncertainty",
        authors=["Jingyu Liu", "Jingquan Peng", "Xiaopeng Wu", "Xubin Li", "Tiezheng Ge", "Bo Zheng", "Yong Liu"],
        year="2025",
        source="ACL Anthology",
        url="https://aclanthology.org/2025.acl-long.840/",
        pdf_url="https://aclanthology.org/2025.acl-long.840.pdf",
    ),
    Paper(
        key="emnlp-2024-glue-pizza",
        title="Glue pizza and eat rocks -- Exploiting Vulnerabilities in Retrieval-Augmented Generative Models",
        authors=["Zhen Tan", "Chengshuai Zhao", "Raha Moraffah", "Yifan Li", "Song Wang", "Jundong Li", "Tianlong Chen", "Huan Liu"],
        year="2024",
        source="ACL Anthology",
        url="https://aclanthology.org/2024.emnlp-main.96/",
        pdf_url="https://aclanthology.org/2024.emnlp-main.96.pdf",
    ),
    Paper(
        key="emnlp-2024-garag",
        title="Typos that Broke the RAG's Back: Genetic Attack on RAG Pipeline by Simulating Documents in the Wild via Low-level Perturbations",
        authors=["Sukmin Cho", "Soyeong Jeong", "Jeongyeon Seo", "Taeho Hwang", "Jong C. Park"],
        year="2024",
        source="ACL Anthology",
        url="https://aclanthology.org/2024.findings-emnlp.161/",
        pdf_url="https://aclanthology.org/2024.findings-emnlp.161.pdf",
    ),
    Paper(
        key="usenix-2025-poisonedrag",
        title="PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models",
        authors=["Wei Zou", "Runpeng Geng", "Binghui Wang", "Jinyuan Jia"],
        year="2025",
        source="USENIX Security",
        url="https://www.usenix.org/conference/usenixsecurity25/presentation/zou-poisonedrag",
        pdf_url="https://www.usenix.org/system/files/usenixsecurity25-zou-poisonedrag.pdf",
    ),
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def slugify(text: str, max_len: int = 120) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", text.lower()).strip("_")
    return text[:max_len].strip("_") or "paper"


def request_url(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def arxiv_pdf_url(arxiv_id: str) -> str:
    clean_id = arxiv_id.split("/")[-1]
    return f"https://arxiv.org/pdf/{clean_id}"


def parse_arxiv_id(entry_id: str) -> str:
    return entry_id.rstrip("/").split("/")[-1]


def fetch_arxiv(query: str, max_results: int) -> list[Paper]:
    encoded = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = f"http://export.arxiv.org/api/query?{encoded}"
    data = request_url(url, timeout=90)
    root = ET.fromstring(data)
    papers: list[Paper] = []
    for entry in root.findall("a:entry", ARXIV_NS):
        entry_id = entry.findtext("a:id", default="", namespaces=ARXIV_NS)
        arxiv_id = parse_arxiv_id(entry_id)
        title = normalize_text(entry.findtext("a:title", default="", namespaces=ARXIV_NS))
        abstract = normalize_text(entry.findtext("a:summary", default="", namespaces=ARXIV_NS))
        published = entry.findtext("a:published", default="", namespaces=ARXIV_NS)
        year = published[:4] if published else ""
        authors = [
            normalize_text(author.findtext("a:name", default="", namespaces=ARXIV_NS))
            for author in entry.findall("a:author", ARXIV_NS)
        ]
        categories = [
            c.attrib.get("term", "")
            for c in entry.findall("arxiv:primary_category", ARXIV_NS)
            if c.attrib.get("term")
        ]
        for cat in entry.findall("a:category", ARXIV_NS):
            term = cat.attrib.get("term", "")
            if term and term not in categories:
                categories.append(term)

        pdf_url = ""
        for link in entry.findall("a:link", ARXIV_NS):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
                break
        if not pdf_url:
            pdf_url = arxiv_pdf_url(arxiv_id)

        papers.append(
            Paper(
                key=f"arxiv-{arxiv_id}",
                title=title,
                authors=[a for a in authors if a],
                year=year,
                source="arXiv",
                url=f"https://arxiv.org/abs/{arxiv_id}",
                pdf_url=pdf_url,
                abstract=abstract,
                published=published,
                categories=categories,
            )
        )
    return papers


def assign_topics_and_score(paper: Paper) -> None:
    haystack = f"{paper.title} {paper.abstract}".lower()
    topics: list[str] = []
    score = 0
    for topic, patterns in TOPIC_PATTERNS.items():
        matches = sum(1 for pattern in patterns if pattern in haystack)
        if matches:
            topics.append(topic)
            score += matches

    if "retrieval augmented generation" in haystack or "retrieval-augmented generation" in haystack:
        score += 8
    elif "retrieval augmented" in haystack or "retrieval-augmented" in haystack:
        score += 5
    elif re.search(r"\brag\b", haystack) and ("large language" in haystack or "llm" in haystack):
        score += 4

    if any(t in topics for t in ["noisy-retrieval", "knowledge-conflict", "adversarial-corruption", "uncertainty-ood", "calibration-control"]):
        score += 6
    if "survey" in haystack or "benchmark" in haystack or "evaluation" in haystack:
        score += 2
    if "retrieval" not in haystack and "rag" not in haystack:
        score -= 10
    if "image generation" in haystack or "video generation" in haystack:
        score -= 3

    paper.topics = topics
    paper.score = score


def dedupe_key(paper: Paper) -> str:
    if paper.key.startswith("arxiv-"):
        return paper.key
    return slugify(paper.title, max_len=160)


def merge_papers(papers: Iterable[Paper]) -> list[Paper]:
    merged: dict[str, Paper] = {}
    title_seen: dict[str, str] = {}
    for paper in papers:
        assign_topics_and_score(paper)
        key = dedupe_key(paper)
        title_key = slugify(paper.title, max_len=180)
        existing_key = title_seen.get(title_key, key)
        if existing_key in merged:
            existing = merged[existing_key]
            if paper.score > existing.score:
                if existing.local_pdf:
                    paper.local_pdf = existing.local_pdf
                    paper.download_status = existing.download_status
                merged[existing_key] = paper
            continue
        merged[key] = paper
        title_seen[title_key] = key

    return sorted(
        merged.values(),
        key=lambda p: (
            p.score,
            p.year or "0000",
            p.title.lower(),
        ),
        reverse=True,
    )


def safe_pdf_name(paper: Paper) -> str:
    author = slugify(paper.authors[0] if paper.authors else "unknown", 36)
    title = slugify(paper.title, 88)
    digest = hashlib.sha1((paper.key + paper.title).encode("utf-8")).hexdigest()[:8]
    year = paper.year or "na"
    return f"{year}_{author}_{title}_{digest}.pdf"


def download_pdf(paper: Paper) -> None:
    filename = safe_pdf_name(paper)
    path = PDF_DIR / filename
    if path.exists() and path.stat().st_size > 20_000:
        paper.local_pdf = str(path.relative_to(ROOT))
        paper.download_status = "exists"
        return

    try:
        data = request_url(paper.pdf_url, timeout=120)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        paper.download_status = "failed"
        paper.error = f"{type(exc).__name__}: {exc}"
        return

    if not data.startswith(b"%PDF"):
        paper.download_status = "failed"
        paper.error = "download did not look like a PDF"
        return
    if len(data) < 20_000:
        paper.download_status = "failed"
        paper.error = f"PDF too small ({len(data)} bytes)"
        return

    path.write_bytes(data)
    paper.local_pdf = str(path.relative_to(ROOT))
    paper.download_status = "downloaded"


def write_metadata(papers: list[Paper], selected: list[Paper], downloaded: list[Paper]) -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at": timestamp,
        "target_downloads": TARGET_DOWNLOADS,
        "candidate_count": len(papers),
        "selected_count": len(selected),
        "downloaded_count": len(downloaded),
        "root": str(ROOT),
        "notes": "Only open-access PDF URLs were used. Paywalled sources were intentionally excluded.",
    }
    (META_DIR / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    def row(p: Paper) -> dict[str, str | int]:
        return {
            "key": p.key,
            "title": p.title,
            "authors": "; ".join(p.authors),
            "year": p.year,
            "source": p.source,
            "url": p.url,
            "pdf_url": p.pdf_url,
            "local_pdf": p.local_pdf,
            "topics": "; ".join(p.topics),
            "score": p.score,
            "download_status": p.download_status,
            "error": p.error,
            "abstract": p.abstract,
        }

    for name, rows in [
        ("all_candidates.csv", papers),
        ("selected_papers.csv", selected),
        ("downloaded_papers.csv", downloaded),
    ]:
        with (META_DIR / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row(rows[0]).keys()) if rows else list(row(Paper("", "", [], "", "", "", "")).keys()))
            writer.writeheader()
            for paper in rows:
                writer.writerow(row(paper))

    with (META_DIR / "papers.json").open("w", encoding="utf-8") as handle:
        json.dump([row(p) for p in downloaded], handle, indent=2, ensure_ascii=False)

    with (LOG_DIR / "download_report.txt").open("w", encoding="utf-8") as handle:
        handle.write(f"Generated at: {timestamp}\n")
        handle.write(f"Candidates: {len(papers)}\n")
        handle.write(f"Selected: {len(selected)}\n")
        handle.write(f"Downloaded/available PDFs: {len(downloaded)}\n\n")
        failures = [p for p in selected if p.download_status == "failed"]
        if failures:
            handle.write("Failures:\n")
            for p in failures:
                handle.write(f"- {p.title} | {p.pdf_url} | {p.error}\n")


def main() -> int:
    global TARGET_DOWNLOADS, MAX_CANDIDATES
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=TARGET_DOWNLOADS, help="Number of PDFs to download/keep available.")
    parser.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES, help="Maximum ranked candidates to attempt.")
    parser.add_argument("--query-sleep", type=float, default=3.2, help="Seconds to sleep between arXiv queries.")
    parser.add_argument("--download-sleep", type=float, default=0.25, help="Seconds to sleep between PDF downloads.")
    args = parser.parse_args()
    TARGET_DOWNLOADS = args.target
    MAX_CANDIDATES = args.max_candidates

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    collected: list[Paper] = list(MANUAL_OPEN_PDFS)
    for idx, (query, max_results) in enumerate(ARXIV_QUERIES, start=1):
        print(f"[{idx}/{len(ARXIV_QUERIES)}] arXiv query: {query} (max {max_results})", flush=True)
        try:
            batch = fetch_arxiv(query, max_results)
            print(f"  -> {len(batch)} results", flush=True)
            collected.extend(batch)
        except Exception as exc:  # noqa: BLE001 - log and continue across independent queries.
            print(f"  !! query failed: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(args.query_sleep)

    papers = merge_papers(collected)
    eligible = [
        p
        for p in papers
        if p.score >= 8
        and p.pdf_url
        and (
            "rag-core" in p.topics
            or "retrieval augmented" in f"{p.title} {p.abstract}".lower()
            or "retrieval-augmented" in f"{p.title} {p.abstract}".lower()
        )
    ]
    if len(eligible) < TARGET_DOWNLOADS:
        eligible = [p for p in papers if p.score >= 5 and p.pdf_url]

    selected = eligible[:MAX_CANDIDATES]
    downloaded: list[Paper] = []
    print(f"Selected {len(selected)} candidates; target {TARGET_DOWNLOADS} PDFs.", flush=True)

    for i, paper in enumerate(selected, start=1):
        if len(downloaded) >= TARGET_DOWNLOADS:
            break
        print(f"[{i}/{len(selected)}] downloading ({paper.score}) {paper.title[:100]}", flush=True)
        download_pdf(paper)
        if paper.download_status in {"downloaded", "exists"}:
            downloaded.append(paper)
        else:
            print(f"  !! failed: {paper.error}", flush=True)
        time.sleep(args.download_sleep)

    write_metadata(papers, selected, downloaded)
    print(f"Done. Downloaded/available PDFs: {len(downloaded)}", flush=True)
    print(f"Metadata written to {META_DIR}", flush=True)
    return 0 if len(downloaded) >= TARGET_DOWNLOADS else 2


if __name__ == "__main__":
    raise SystemExit(main())
