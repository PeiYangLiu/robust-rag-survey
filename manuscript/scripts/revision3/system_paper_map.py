#!/usr/bin/env python3
"""Resolve gazetteer system names to the locally held full text of the paper
that introduced them.

The privileged adjudication reference (``run_privileged_adjudication.py``) needs
the *cited* paper, not only the citing one.  This module supplies that mapping
and, crucially, verifies it: a mapping is retained only if the system name
occurs in the title-and-abstract region of the mapped full text, so a typo or a
mis-resolution fails loudly rather than silently supplying the wrong paper to an
adjudicator.

The map is hand-curated because system names are not recoverable from titles
(``Self-RAG`` is introduced by a paper whose title does not contain the string,
``RobustRAG`` by ``Certifiably Robust RAG against Retrieval Corruption``).  It
is released with the frame so a third party can check every entry.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEXT_DIR = REPO / "manuscript" / "citation_audit" / "expanded_texts"

# system name -> cite key of the paper that introduced it.  Every entry is
# checked by ``verified_map`` against the mapped text's own abstract region.
CURATED: dict[str, str] = {
    "PoisonedRAG": "poisonedRAG2024",
    "Phantom": "phantom2024",
    # Spelling variants the automatic variant generator does not produce
    # (it inserts no space that the surface form omits).  Each inherits its
    # verification from the canonical spelling listed in ``ALIASES``.
    "BadRAG": "badRAG2024",
    "AgentPoison": "rrag053",
    "GARAG": "rrag048",
    "AIP": "aip2025",
    "Corpus Poisoning": "poisoningRetrievalCorpora2023",
    "RobustRAG": "certifiedRAG2024",
    "CertifiedRAG": "certifiedRAG2024",
    "AstuteRAG": "astuteRAG2025",
    "Astute": "astuteRAG2025",
    "TrustRAG": "rrag013",
    "Self-RAG": "selfRAG2023",
    "SelfRAG": "selfRAG2023",
    "CRAG": "crag2024",
    "Self-CRAG": "crag2024",
    "CtrlA": "ctrla2025",
    "Chain-of-Note": "chainOfNote2023",
    "CoN": "chainOfNote2023",
    "RAAT": "raat2024",
    "RGB": "rgb2023",
    "ClashEval": "rrag038",
    "FaithEval": "rrag040",
    "RAGTruth": "ragTruth2024",
    "Sufficient Context": "sufficientContext2024",
    "ParamMute": "rrag024",
    "SKR": "rrag210",
    "GraphRAG": "rrag051",
    "Adaptive-RAG": "rrag191",
}

# Systems deliberately left unresolved: generic retrievers and families whose
# defining paper is not in the local corpus.  Naming them here keeps the
# exclusion declared rather than implicit.
DECLARED_UNRESOLVED = [    "BM25", "DPR", "Contriever", "ColBERT", "SPLADE", "FiD", "REALM", "RETRO",
    "Atlas", "Atlas-11B", "REPLUG", "kNN-LM", "FLARE", "DRAGIN", "InstructRAG",
    "RECALL", "RAGAS", "ARES", "RAGChecker", "LongRAG", "RQ-RAG", "SearChain",
    "IRCoT", "ReAct", "Toolformer", "Self-Ask", "Chain-of-Verification", "CoVe",
    "RARR", "Verify-and-Edit", "SEER", "Speculative RAG", "Blended RAG",
    "HippoRAG", "RAPTOR", "Self-Reflective", "Corrective Retrieval", "MuRAG",
    "GASLITE", "Jamming", "Prompt Injection", "MuRAG",
]


def _variants(name: str) -> set[str]:
    return {
        v
        for v in {name, name.replace("-", " "), name.replace(" ", "-"), name.replace("-", "")}
        if v
    }


def _pattern(name: str) -> re.Pattern[str]:
    alts = "|".join(re.escape(v) for v in sorted(_variants(name)))
    return re.compile(rf"(?<![\w-])(?:{alts})(?![\w-])", re.I)


# Surface spellings that denote the same system as a canonical name but that the
# variant generator cannot produce, because it never *inserts* a separator the
# surface form omits.  An alias is accepted iff its canonical form verifies.
ALIASES = {
    "AstuteRAG": "Astute RAG",
    "CertifiedRAG": "Certifiably Robust RAG",
    "Self-CRAG": "CRAG",
}


def verified_map(head_lines: int = 160) -> tuple[dict[str, str], list[str]]:
    """Return the subset of ``CURATED`` whose target text exists and names the
    system in its own opening region, plus the list of rejected entries."""
    good: dict[str, str] = {}
    rejected: list[str] = []
    for name, key in CURATED.items():
        path = TEXT_DIR / f"{key}.txt"
        if not path.exists():
            rejected.append(f"{name}->{key}: no local text")
            continue
        head = "\n".join(
            path.read_text(encoding="utf-8", errors="replace").splitlines()[:head_lines]
        )
        probe = ALIASES.get(name, name)
        if _pattern(probe).search(head):
            good[name] = key
        else:
            rejected.append(f"{name}->{key}: name absent from opening region")
    return good, rejected


if __name__ == "__main__":
    good, rejected = verified_map()
    print(f"verified {len(good)} of {len(CURATED)} curated entries")
    for name in sorted(good):
        print(f"  {name:22s} -> {good[name]}")
    if rejected:
        print("rejected:")
        for r in rejected:
            print(f"  {r}")
