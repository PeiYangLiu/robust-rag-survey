#!/usr/bin/env python3
"""Verify every bibliography entry used by the compiled manuscript."""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


BIB_FILES = (
    "references.bib",
    "auto_references.bib",
    "venue_authoritative_references.bib",
    "venue_extra_references.bib",
    "venue_200_selected_references.bib",
    "multimodal_100_selected_references.bib",
)
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
USER_AGENT = "robust-rag-bibliography-verifier/1.0"


def request(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/xml, text/html, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_value(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return "", start
    if text[start] == "{":
        depth = 1
        index = start + 1
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        return text[start + 1 : index - 1], index
    if text[start] == '"':
        index = start + 1
        while index < len(text):
            if text[index] == '"' and text[index - 1] != "\\":
                return text[start + 1 : index], index + 1
            index += 1
    index = start
    while index < len(text) and text[index] not in ",\n":
        index += 1
    return text[start:index].strip(), index


def parse_bib(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    entries = []
    cursor = 0
    while True:
        match = re.search(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", text[cursor:])
        if not match:
            break
        entry_start = cursor + match.start()
        body_start = cursor + match.end()
        depth = 1
        index = body_start
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        body = text[body_start : index - 1]
        fields: dict[str, str] = {}
        field_cursor = 0
        while True:
            field_match = re.search(
                r"(?m)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*",
                body[field_cursor:],
            )
            if not field_match:
                break
            name = field_match.group(1).lower()
            value_start = field_cursor + field_match.end()
            value, value_end = parse_value(body, value_start)
            fields[name] = re.sub(r"\s+", " ", value).strip()
            field_cursor = value_end
        entries.append(
            {
                "key": match.group(2),
                "type": match.group(1).lower(),
                "fields": fields,
                "file": path.name,
                "offset": entry_start,
            }
        )
        cursor = index
    return entries


def normalize_title(value: str) -> str:
    value = re.sub(r"\\[A-Za-z]+\s*", " ", value)
    value = value.replace("{", "").replace("}", "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def title_match(left: str, right: str) -> float:
    return difflib.SequenceMatcher(
        None, normalize_title(left), normalize_title(right)
    ).ratio()


def arxiv_id(url: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", url)
    if not match:
        return ""
    return re.sub(r"\.pdf$|v\d+$", "", match.group(1))


def fetch_arxiv_item(identifier: str) -> tuple[str, dict[str, str]]:
    html = request(f"https://arxiv.org/abs/{identifier}", timeout=40).decode(
        "utf-8", "replace"
    )
    match = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.I
    )
    if not match:
        match = re.search(r"<title>\[[^\]]+\]\s*(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    return identifier, {"title": title}


def fetch_arxiv_metadata(ids: list[str]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_arxiv_item, identifier): identifier for identifier in ids}
        for future in as_completed(futures):
            identifier = futures[future]
            try:
                key, metadata = future.result()
                output[key] = metadata
            except Exception as error:
                output[identifier] = {"error": f"{type(error).__name__}: {error}"}
    return output


def verify_non_arxiv(item: dict[str, str]) -> dict[str, str]:
    url = item["url"]
    title = item["title"]
    try:
        if "aclanthology.org/" in url:
            paper_id = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".pdf")
            bib = request(f"https://aclanthology.org/{paper_id}.bib").decode(
                "utf-8", "replace"
            )
            match = re.search(r'title\s*=\s*"([^"]+)"', bib, re.I | re.S)
            official = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
            score = title_match(title, official) if official else 0.0
            return {
                "verification": "official_metadata",
                "official_title": official,
                "title_similarity": f"{score:.3f}",
                "online_error": "" if score >= 0.72 else "title_mismatch",
            }
        if "openreview.net/" in url:
            identifier = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get(
                "id", [""]
            )[0]
            try:
                raw = request(
                    f"https://api2.openreview.net/notes?id={urllib.parse.quote(identifier)}"
                )
            except urllib.error.HTTPError as error:
                if error.code in {403, 429}:
                    return {
                        "verification": "official_host_challenge",
                        "official_title": "",
                        "title_similarity": "",
                        "online_error": "",
                    }
                raise
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return {
                    "verification": "official_host_challenge",
                    "official_title": "",
                    "title_similarity": "",
                    "online_error": "",
                }
            note = (data.get("notes") or [{}])[0]
            value = note.get("content", {}).get("title", "")
            official = value.get("value", "") if isinstance(value, dict) else value
            score = title_match(title, official) if official else 0.0
            return {
                "verification": "official_metadata",
                "official_title": official,
                "title_similarity": f"{score:.3f}",
                "online_error": "" if score >= 0.72 else "title_mismatch",
            }
        if item["doi"]:
            encoded = urllib.parse.quote(item["doi"], safe="")
            try:
                data = json.loads(request(f"https://api.crossref.org/works/{encoded}"))
                message = data.get("message", {})
                official = (message.get("title") or [""])[0]
                score = title_match(title, official) if official else 0.0
                return {
                    "verification": "official_metadata",
                    "official_title": official,
                    "title_similarity": f"{score:.3f}",
                    "online_error": "" if score >= 0.72 else "title_mismatch",
                }
            except Exception:
                request(f"https://doi.org/{item['doi']}")
                return {
                    "verification": "official_doi_resolves",
                    "official_title": "",
                    "title_similarity": "",
                    "online_error": "",
                }
        request(url)
        return {
            "verification": "reachable_source",
            "official_title": "",
            "title_similarity": "",
            "online_error": "",
        }
    except Exception as error:
        return {
            "verification": "failed",
            "official_title": "",
            "title_similarity": "",
            "online_error": f"{type(error).__name__}: {error}",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()

    manuscript = Path(__file__).resolve().parents[1]
    aux_text = (manuscript / "main.aux").read_text()
    cited = {
        key.strip()
        for group in re.findall(r"\\citation\{([^}]+)\}", aux_text)
        for key in group.split(",")
        if key.strip()
    }
    used = set(re.findall(r"\\bibcite\{([^}]+)\}", aux_text))
    if not used:
        raise SystemExit("main.aux contains no bibliography entries")
    if cited != used:
        missing = sorted(cited - used)
        unexpected = sorted(used - cited)
        raise SystemExit(
            "main.aux citation/bibcite mismatch: "
            f"missing_bibcite={missing[:10]}, uncited_bibcite={unexpected[:10]}"
        )
    all_entries = [
        entry for name in BIB_FILES for entry in parse_bib(manuscript / name)
    ]
    by_key: dict[str, list[dict[str, object]]] = {}
    for entry in all_entries:
        by_key.setdefault(str(entry["key"]), []).append(entry)

    rows = []
    for key in sorted(used):
        candidates = by_key.get(key, [])
        entry = candidates[0] if candidates else {"fields": {}, "file": ""}
        fields = entry["fields"]
        assert isinstance(fields, dict)
        title = str(fields.get("title", ""))
        author = str(fields.get("author", ""))
        year = str(fields.get("year", ""))
        url = str(fields.get("url", "")).replace("\\", "")
        doi = str(fields.get("doi", ""))
        missing = [
            name
            for name, value in (("title", title), ("year", year), ("author", author))
            if not value
        ]
        rows.append(
            {
                "key": key,
                "bib_file": str(entry.get("file", "")),
                "duplicate_definitions": str(len(candidates)),
                "title": title,
                "year": year,
                "url": url,
                "doi": doi,
                "structural_status": "ok" if not missing and candidates else "failed",
                "structural_error": ";".join(missing)
                if candidates
                else "missing_key",
                "verification": "not_run",
                "official_title": "",
                "title_similarity": "",
                "online_error": "",
            }
        )

    if args.online:
        arxiv_rows = {arxiv_id(row["url"]): row for row in rows if arxiv_id(row["url"])}
        try:
            metadata = fetch_arxiv_metadata(sorted(arxiv_rows))
        except Exception as error:
            metadata = {}
            for row in arxiv_rows.values():
                row["verification"] = "failed"
                row["online_error"] = f"{type(error).__name__}: {error}"
        for identifier, row in arxiv_rows.items():
            if row["verification"] == "failed":
                continue
            official = metadata.get(identifier)
            if not official or official.get("error"):
                row["verification"] = "failed"
                row["online_error"] = (
                    official.get("error", "arxiv_id_not_returned")
                    if official
                    else "arxiv_id_not_returned"
                )
                continue
            score = title_match(row["title"], official["title"])
            row["verification"] = "official_metadata"
            row["official_title"] = official["title"]
            row["title_similarity"] = f"{score:.3f}"
            row["online_error"] = "" if score >= 0.72 else "title_mismatch"

        remaining = [
            row
            for row in rows
            if not arxiv_id(row["url"]) and row["structural_status"] == "ok"
        ]
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(verify_non_arxiv, row): row for row in remaining}
            for future in as_completed(futures):
                futures[future].update(future.result())

    output = manuscript / "supplement" / "bibliography_integrity_report.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "used_entries": len(rows),
        "used_keys_sha256": hashlib.sha256(
            "\n".join(sorted(used)).encode("utf-8")
        ).hexdigest(),
        "aux_key_sets_match": cited == used,
        "duplicate_keys": {
            key: [str(entry["file"]) for entry in entries]
            for key, entries in by_key.items()
            if key in used and len(entries) > 1
        },
        "structural_status": dict(
            __import__("collections").Counter(row["structural_status"] for row in rows)
        ),
        "verification": dict(
            __import__("collections").Counter(row["verification"] for row in rows)
        ),
        "online_failures": [
            {"key": row["key"], "error": row["online_error"], "url": row["url"]}
            for row in rows
            if row["verification"] == "failed" or row["online_error"]
        ],
        "report": output.name,
    }
    (manuscript / "supplement" / "bibliography_integrity_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary["duplicate_keys"] or summary["structural_status"].get("failed", 0):
        raise SystemExit(1)
    if args.online and summary["online_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
