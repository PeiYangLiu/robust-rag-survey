#!/usr/bin/env python3
"""Download older venue-linked / peer-reviewed foundations for robust RAG.

Downloads only openly accessible PDFs. The goal is to strengthen the corpus with
pre-2025 archival work from ACL/EMNLP/NAACL/EACL/COLING/TACL, NeurIPS, ICML/PMLR,
ICLR/OpenReview, and related venues.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
OUT = ROOT / "metadata" / "authoritative_foundations_downloads.csv"
PDF_DIR.mkdir(exist_ok=True)
OUT.parent.mkdir(exist_ok=True)

ACL_BIB_URL = "https://aclanthology.org/anthology+abstracts.bib.gz"

TERMS = {
    "retrieval augmented": 8,
    "retrieval-augmented": 8,
    "retrieval augmented generation": 12,
    "retrieval-augmented generation": 12,
    "dense passage retrieval": 10,
    "open-domain question answering": 6,
    "open domain question answering": 6,
    "question answering": 2,
    "faithfulness": 7,
    "hallucination": 7,
    "attribution": 6,
    "citation": 6,
    "fact verification": 6,
    "fever": 5,
    "scifact": 5,
    "unanswerable": 7,
    "answerability": 7,
    "selective": 4,
    "calibration": 6,
    "uncertainty": 5,
    "adversarial": 5,
    "poison": 8,
    "prompt injection": 8,
    "distractor": 6,
    "irrelevant context": 9,
    "knowledge conflict": 9,
    "counterfactual": 5,
    "robust": 4,
}

VENUE_HINTS = [
    "ACL",
    "EMNLP",
    "NAACL",
    "EACL",
    "COLING",
    "LREC",
    "TACL",
    "Findings",
]

MANUAL_PAPERS = [
    {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "year": "2020",
        "venue": "NeurIPS 2020",
        "url": "https://proceedings.neurips.cc/paper_files/paper/2020/file/6b493230205f780e1bc26945df7481e5-Paper.pdf",
        "reason": "foundational RAG architecture",
    },
    {
        "title": "REALM: Retrieval-Augmented Language Model Pre-Training",
        "year": "2020",
        "venue": "ICML 2020",
        "url": "https://proceedings.mlr.press/v119/guu20a/guu20a.pdf",
        "reason": "retrieval-augmented pretraining foundation",
    },
    {
        "title": "On Calibration of Modern Neural Networks",
        "year": "2017",
        "venue": "ICML 2017",
        "url": "https://proceedings.mlr.press/v70/guo17a/guo17a.pdf",
        "reason": "calibration foundation",
    },
    {
        "title": "Selective Classification for Deep Neural Networks",
        "year": "2017",
        "venue": "NeurIPS 2017",
        "url": "https://proceedings.neurips.cc/paper_files/paper/2017/file/4a8423d5e91fda00bb7e46540e2b0cf1-Paper.pdf",
        "reason": "selective prediction foundation",
    },
    {
        "title": "Improving language models by retrieving from trillions of tokens",
        "year": "2022",
        "venue": "ICML 2022",
        "url": "https://proceedings.mlr.press/v162/borgeaud22a/borgeaud22a.pdf",
        "reason": "retrieval-augmented LM foundation",
    },
    {
        "title": "Lost in the Middle: How Language Models Use Long Contexts",
        "year": "2024",
        "venue": "TACL 2024",
        "url": "https://aclanthology.org/2024.tacl-1.9.pdf",
        "reason": "long-context evidence-use foundation",
    },
    {
        "title": "BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models",
        "year": "2021",
        "venue": "NeurIPS 2021",
        "url": "https://openreview.net/pdf?id=wCu6T5xFjeJ",
        "reason": "retrieval evaluation foundation",
    },
]


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def slug(value: str, max_len: int = 90) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.lower()).strip("_")
    return value[:max_len].strip("_") or "paper"


def request(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "robust-rag-survey-authoritative-pass/0.1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def split_bib_entries(text: str) -> list[str]:
    starts = [m.start() for m in re.finditer(r"(?m)^@\w+\{", text)]
    return [text[s : starts[i + 1] if i + 1 < len(starts) else len(text)] for i, s in enumerate(starts)]


def field(entry: str, name: str) -> str:
    pattern = rf"(?is)\b{name}\s*=\s*[\{{\"](.*?)[\}}\"]\s*,\s*(?:\n\s*\w+\s*=|\n\}})"
    m = re.search(pattern, entry)
    return norm_text(m.group(1).replace("\n", " ")) if m else ""


def score_entry(title: str, abstract: str, booktitle: str) -> int:
    low = f"{title} {abstract} {booktitle}".lower()
    score = 0
    for term, weight in TERMS.items():
        if term in low:
            score += weight
    if "retrieval" in low and ("generation" in low or "question answering" in low):
        score += 8
    if "rag" in low:
        score += 6
    return score


def acl_pdf_url(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith(".pdf"):
        return url
    return url + ".pdf"


def collect_acl_candidates() -> list[dict[str, str]]:
    raw = request(ACL_BIB_URL)
    text = gzip.decompress(raw).decode("utf-8", errors="replace")
    candidates = []
    for entry in split_bib_entries(text):
        year = field(entry, "year")
        if not year or int(year) > 2024 or int(year) < 2017:
            continue
        title = field(entry, "title").replace("{", "").replace("}", "")
        abstract = field(entry, "abstract")
        booktitle = field(entry, "booktitle") or field(entry, "journal")
        url = field(entry, "url")
        if not url:
            continue
        if not any(v.lower() in booktitle.lower() or v.lower() in url.lower() for v in VENUE_HINTS):
            continue
        score = score_entry(title, abstract, booktitle)
        if score < 12:
            continue
        candidates.append(
            {
                "title": title,
                "year": year,
                "venue": booktitle,
                "url": acl_pdf_url(url),
                "reason": f"ACL Anthology keyword score {score}",
                "score": str(score),
            }
        )
    candidates.sort(key=lambda r: (-int(r["score"]), r["year"], r["title"]))
    # Keep a broad but bounded set; this is a download pass, not final inclusion.
    return candidates[:90]


def download_one(row: dict[str, str], index: int) -> dict[str, str]:
    title = row["title"]
    year = row.get("year", "na")
    venue = row.get("venue", "venue")
    filename = f"authoritative_{year}_{slug(venue, 24)}_{slug(title)}.pdf"
    path = PDF_DIR / filename
    out = {
        **row,
        "local_pdf": str(path.relative_to(ROOT)),
        "status": "",
        "bytes": "",
    }
    if path.exists() and path.stat().st_size > 10_000:
        out["status"] = "exists"
        out["bytes"] = str(path.stat().st_size)
        return out
    try:
        time.sleep(0.25)
        data = request(row["url"])
        if not data.startswith(b"%PDF"):
            # OpenReview sometimes returns PDF after redirects but still PDF; if not, keep a failure.
            if b"%PDF" not in data[:1024]:
                raise ValueError("downloaded content does not look like a PDF")
        path.write_bytes(data)
        out["status"] = "downloaded"
        out["bytes"] = str(len(data))
    except Exception as exc:
        out["status"] = f"failed: {exc!r}"
    return out


def main() -> None:
    candidates = MANUAL_PAPERS + collect_acl_candidates()
    seen: set[str] = set()
    deduped = []
    for row in candidates:
        key = row["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    results = [download_one(row, i) for i, row in enumerate(deduped, 1)]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["title", "year", "venue", "url", "reason", "score", "local_pdf", "status", "bytes"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    summary = Counter(r["status"].split(":")[0] for r in results)
    print(json.dumps({"total": len(results), "summary": dict(summary), "manifest": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
