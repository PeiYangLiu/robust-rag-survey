#!/usr/bin/env python3
"""Regenerate the all-in-one TeX source and self-contained Overleaf source."""

from __future__ import annotations

import re
import shutil
import hashlib
import zipfile
from pathlib import Path


INPUT_RE = re.compile(r"\\input\{([^}]+)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
BIB_FILES = (
    "references.bib",
    "auto_references.bib",
    "venue_authoritative_references.bib",
    "venue_extra_references.bib",
    "venue_200_selected_references.bib",
    "multimodal_100_selected_references.bib",
)


def inline_tex(path: Path, manuscript_root: Path, stack: tuple[Path, ...]) -> str:
    resolved = path.resolve()
    if resolved in stack:
        cycle = " -> ".join(item.name for item in (*stack, resolved))
        raise ValueError(f"Cyclic TeX input: {cycle}")
    text = path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        relative = Path(match.group(1))
        if relative.suffix == "":
            relative = relative.with_suffix(".tex")
        child = manuscript_root / relative
        if not child.is_file():
            raise FileNotFoundError(f"Missing TeX input: {child}")
        body = inline_tex(child, manuscript_root, (*stack, resolved))
        return body.rstrip() + "\n"

    return INPUT_RE.sub(replace, text)


def resolve_graphic(manuscript_root: Path, value: str) -> Path:
    candidate = manuscript_root / value
    if candidate.is_file():
        return candidate
    for suffix in (".pdf", ".png", ".jpg", ".jpeg"):
        with_suffix = candidate.with_suffix(suffix)
        if with_suffix.is_file():
            return with_suffix
    raise FileNotFoundError(f"Missing graphic referenced by generated TeX: {value}")


def main() -> None:
    manuscript_root = Path(__file__).resolve().parents[1]
    repo_root = manuscript_root.parent
    source = manuscript_root / "main.tex"
    generated = manuscript_root / "main_all_in_one.tex"
    overleaf_root = repo_root / "overleaf_package"
    staging_root = repo_root / ".overleaf_package.staging"
    release_version = (
        manuscript_root / "supplement" / "RELEASE_VERSION.txt"
    ).read_text(encoding="utf-8").strip()

    text = inline_tex(source, manuscript_root, ())
    text = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    remaining_inputs = INPUT_RE.findall(text)
    if remaining_inputs:
        raise ValueError(f"Unexpanded TeX inputs remain: {remaining_inputs[:5]}")
    generated.write_text(text, encoding="utf-8")

    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True)
    shutil.copy2(generated, staging_root / "main.tex")
    for name in (*BIB_FILES, "acl.sty", "acl_natbib.bst"):
        shutil.copy2(manuscript_root / name, staging_root / name)
    for name in ("LICENSE", "DATA_LICENSE.md"):
        shutil.copy2(repo_root / name, staging_root / name)

    copied_graphics: set[str] = set()
    for value in GRAPHICS_RE.findall(text):
        graphic = resolve_graphic(manuscript_root, value)
        relative = graphic.relative_to(manuscript_root)
        destination = staging_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(graphic, destination)
        copied_graphics.add(relative.as_posix())

    readme = (
        "Self-contained Overleaf source for When Are Robust-RAG Results Comparable?\n"
        f"Release: {release_version}\n\n"
        "Compile entry point: main.tex\n"
        "Compiler: pdfLaTeX + BibTeX\n\n"
        "This directory is generated deterministically by\n"
        "manuscript/scripts/build_submission_sources.py. Do not edit it directly.\n"
        "Build artifacts (AUX, BBL, logs, and PDF) are intentionally excluded.\n"
    )
    (staging_root / "README_OVERLEAF.txt").write_text(readme, encoding="utf-8")
    manifest_lines = []
    for path in sorted(item for item in staging_root.rglob("*") if item.is_file()):
        relative = path.relative_to(staging_root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {relative}")
    (staging_root / "MANIFEST.sha256").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )

    if overleaf_root.exists():
        shutil.rmtree(overleaf_root)
    staging_root.rename(overleaf_root)

    archive_path = repo_root / "robust-rag-survey-overleaf.zip"
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in sorted(item for item in overleaf_root.rglob("*") if item.is_file()):
            relative = path.relative_to(overleaf_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 7, 26, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())

    print(f"Wrote {generated}")
    print(f"Wrote {overleaf_root / 'main.tex'}")
    print(f"Wrote {archive_path}")
    print(f"Copied {len(copied_graphics)} referenced graphics")


if __name__ == "__main__":
    main()
