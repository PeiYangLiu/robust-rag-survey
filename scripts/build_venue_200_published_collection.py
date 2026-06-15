#!/usr/bin/env python3
"""Build a 200-paper venue-linked PDF collection for the robust-RAG survey.

The collection is intentionally separate from the preprint-heavy evidence map.
It prioritizes open-access, venue/proceedings-linked PDFs from ACL/TACL,
ICLR/OpenReview, ICML/PMLR, NeurIPS, and related formal venues. Existing local
PDFs are copied into a curated directory; additional accepted-conference PDFs are
downloaded when needed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
OUT_DIR = PDF_DIR / "venue_200_published"
META = ROOT / "metadata"
OUT_MANIFEST = META / "venue_200_published_manifest.csv"
OUT_SUMMARY = META / "venue_200_published_summary.json"
TARGET = 200

INPUT_MANIFESTS = [
    ("authoritative_foundations", META / "authoritative_foundations_downloads.csv"),
    ("venue_accepts_downloads", META / "venue_accepts_downloads.csv"),
    ("venue_accepts_extra", META / "venue_accepts_additional_keep_downloads.csv"),
]
ACCEPTED_CANDIDATES = META / "venue_accepts_rag_related.csv"

POSITIVE_TERMS = [
    "retrieval augmented generation",
    "retrieval-augmented generation",
    "retrieval augmented",
    "retrieval-augmented",
    "rag",
    "retriever",
    "retrieval",
    "question answering",
    "open-domain",
    "open domain",
    "grounded",
    "grounding",
    "faithfulness",
    "faithful",
    "hallucination",
    "attribution",
    "citation",
    "evidence",
    "context",
    "calibration",
    "uncertainty",
    "selective",
    "abstain",
    "answerability",
    "unanswerable",
    "poison",
    "prompt injection",
    "adversarial",
    "corruption",
    "trustworthy",
    "robust",
    "long context",
    "counterfactual",
]

EXCLUDE_TITLE_TERMS = [
    "diffusion",
    "video generation",
    "molecular",
    "vehicle routing",
    "ad auctions",
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


def looks_relevant(row: dict[str, str]) -> bool:
    text = " ".join([row.get("title", ""), row.get("abstract", ""), row.get("matched_terms", ""), row.get("reason", "")]).lower()
    title = row.get("title", "").lower()
    if any(term in title for term in EXCLUDE_TITLE_TERMS):
        return False
    return any(term in text for term in POSITIVE_TERMS)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def request_pdf(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "robust-rag-survey-venue200/0.1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def is_pdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 10_000:
        return False
    head = path.read_bytes()[:2048]
    return b"%PDF" in head


def copy_to_collection(src: Path, index: int, row: dict[str, str], source: str, selected: list[dict[str, str]]) -> bool:
    if not is_pdf(src):
        return False
    venue = row.get("venue") or row.get("source_or_venue") or "venue"
    year = row.get("year") or "na"
    title = row.get("title") or row.get("venue_title") or src.stem
    dest = OUT_DIR / f"{index:03d}_{slug(year + '_' + venue, 36)}_{slug(title)}.pdf"
    shutil.copy2(src, dest)
    selected.append({
        "index": str(index),
        "title": title,
        "year": year,
        "venue": venue,
        "selection_source": source,
        "pdf_url": row.get("url") or row.get("pdf_url") or row.get("venue_pdf_url") or "",
        "landing_url": row.get("landing_url") or row.get("venue_landing_url") or "",
        "related_score": row.get("related_score") or row.get("score") or "",
        "matched_terms": row.get("matched_terms") or row.get("reason") or "",
        "source_local_pdf": str(src.relative_to(ROOT)) if src.is_relative_to(ROOT) else str(src),
        "curated_pdf": str(dest.relative_to(ROOT)),
        "bytes": str(dest.stat().st_size),
        "sha256": sha256(dest),
        "status": "copied_existing",
    })
    return True


def download_to_temp(row: dict[str, str]) -> Path | None:
    url = row.get("pdf_url") or row.get("venue_pdf_url") or row.get("url") or ""
    if not url:
        return None
    tmp = OUT_DIR / f"_tmp_{slug(row.get('title', 'paper'))}.pdf"
    try:
        time.sleep(0.2)
        data = request_pdf(url)
        if b"%PDF" not in data[:2048]:
            return None
        tmp.write_bytes(data)
        return tmp if is_pdf(tmp) else None
    except Exception:
        return None


def add_existing(selected: list[dict[str, str]], seen_titles: set[str]) -> int:
    index = len(selected) + 1
    for source, manifest in INPUT_MANIFESTS:
        for row in read_csv(manifest):
            title = row.get("title", "")
            nt = norm_title(title)
            if not nt or nt in seen_titles or not looks_relevant(row):
                continue
            status = (row.get("status") or row.get("download_status") or "").split(":")[0]
            if status not in {"exists", "downloaded"}:
                continue
            local = row.get("local_pdf", "")
            if not local:
                continue
            src = ROOT / local
            if copy_to_collection(src, index, row, source, selected):
                seen_titles.add(nt)
                index += 1
                if len(selected) >= TARGET:
                    return index
    return index


def add_downloaded_candidates(selected: list[dict[str, str]], seen_titles: set[str]) -> None:
    candidates = read_csv(ACCEPTED_CANDIDATES)
    candidates.sort(key=lambda r: (-int(r.get("related_score") or 0), r.get("venue", ""), r.get("year", ""), r.get("title", "")))
    index = len(selected) + 1
    for row in candidates:
        if len(selected) >= TARGET:
            break
        title = row.get("title", "")
        nt = norm_title(title)
        if not nt or nt in seen_titles or not looks_relevant(row):
            continue
        if int(row.get("related_score") or 0) < 25:
            continue
        # Reuse an existing venue_accept filename if prior scripts already downloaded it.
        existing = PDF_DIR / f"venue_accept_{row.get('venue','')}_{row.get('year','')}_{slug(title)}.pdf"
        src = existing if is_pdf(existing) else download_to_temp(row)
        if src and copy_to_collection(src, index, row, "venue_accepts_rag_related_download", selected):
            if src.name.startswith("_tmp_"):
                src.unlink(missing_ok=True)
            selected[-1]["status"] = "downloaded_or_copied_candidate"
            seen_titles.add(nt)
            index += 1


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.pdf"):
        old.unlink()
    selected: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    add_existing(selected, seen_titles)
    add_downloaded_candidates(selected, seen_titles)

    fields = [
        "index", "title", "year", "venue", "selection_source", "pdf_url", "landing_url",
        "related_score", "matched_terms", "source_local_pdf", "curated_pdf", "bytes", "sha256", "status"
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
        "source_counts": {},
        "venue_counts": {},
        "year_counts": {},
    }
    for key in ["selection_source", "venue", "year"]:
        counts: dict[str, int] = {}
        for row in selected:
            counts[row.get(key, "")] = counts.get(row.get(key, ""), 0) + 1
        summary[key.replace("selection_", "") + "_counts"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:50])
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if len(selected) < TARGET:
        raise SystemExit(f"Only selected {len(selected)} PDFs; target is {TARGET}")


if __name__ == "__main__":
    main()
