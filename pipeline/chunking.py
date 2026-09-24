"""Deterministic document processing: heading-based chunking, near-duplicate
detection, and a keyword pre-filter. No embeddings, no LLM calls - this is
the "deterministic parsing" half of Part 2 (see prompts/classify_chunk.md
for the LLM half: turning a candidate chunk into a risk category).

Chunking understands two heading styles so it works uniformly across both
raw-fetched-text sources and the html_to_text() output in tools/fetch.py:
- Markdown: lines starting with 1-6 '#'.
- reStructuredText: a title line followed by an underline made of repeated
  punctuation (Django's own docs use this format).
Falls back to fixed-size paragraph grouping when no headings are found.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHUNK_CHARS = 6000
_RST_UNDERLINE_RE = re.compile(r'^([=\-~^"\'*+#:.])\1{2,}\s*$')
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

RISK_KEYWORDS = [
    "deprecat", "remov", "breaking", "backwards incompat", "backward incompat",
    "no longer", "renamed", "changed default", "changed the default",
    "migrat", "requires", "minimum", "unsupported", "drop support",
    "dropped support", "must ", "required to", "behavior change",
    "behaviour change", "incompatib", "upgrad",
]


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    heading: str
    text: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "heading": self.heading,
            "text": self.text,
        }


def _find_heading_boundaries(lines: list[str]) -> list[tuple[int, str]]:
    boundaries: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        md_match = _MD_HEADING_RE.match(line)
        if md_match:
            boundaries.append((i, md_match.group(2).strip()))
            continue
        if i > 0 and _RST_UNDERLINE_RE.match(line) and lines[i - 1].strip():
            title = lines[i - 1].strip()
            underline_len = len(line.strip())
            if underline_len >= max(3, len(title) * 0.4):
                boundaries.append((i - 1, title))
    # de-dup + sort by line index, drop a heading immediately followed by
    # another (RST overline+title+underline triples would otherwise double-count)
    seen_lines: set[int] = set()
    result = []
    for idx, heading in sorted(boundaries, key=lambda b: b[0]):
        if idx in seen_lines:
            continue
        seen_lines.add(idx)
        result.append((idx, heading))
    return result


def _split_oversized(heading: str, text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    paragraphs = re.split(r"\n\s*\n", text)
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) > MAX_CHUNK_CHARS:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        parts.append(current)
    return parts or [text[:MAX_CHUNK_CHARS]]


def chunk_document(source_id: str, text: str) -> list[Chunk]:
    if not text.strip():
        return []
    lines = text.splitlines()
    boundaries = _find_heading_boundaries(lines)

    sections: list[tuple[str, str]] = []
    if not boundaries:
        sections.append(("(no heading)", text))
    else:
        for i, (line_idx, heading) in enumerate(boundaries):
            end_idx = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(lines)
            body = "\n".join(lines[line_idx + 1 : end_idx]).strip()
            if body:
                sections.append((heading, body))

    chunks: list[Chunk] = []
    for section_idx, (heading, body) in enumerate(sections):
        parts = _split_oversized(heading, body)
        for part_idx, part_text in enumerate(parts):
            suffix = f"::{part_idx}" if len(parts) > 1 else ""
            chunk_id = f"{source_id}::chunk{section_idx}{suffix}"
            chunks.append(Chunk(chunk_id=chunk_id, source_id=source_id, heading=heading, text=part_text))
    return chunks


def keyword_prefilter(chunks: list[Chunk], keywords: list[str] = RISK_KEYWORDS) -> list[Chunk]:
    """Deterministic pre-filter before the classify_chunk LLM call - drops
    chunks that mention none of the risk-adjacent keywords, so the LLM only
    has to classify plausible candidates rather than every chunk of every
    fetched document (which for e.g. the Kubernetes deprecation guide can be
    hundreds of sections).
    """
    kept = []
    for chunk in chunks:
        haystack = (chunk.heading + "\n" + chunk.text).lower()
        if any(keyword in haystack for keyword in keywords):
            kept.append(chunk)
    return kept
