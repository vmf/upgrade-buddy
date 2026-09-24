"""URL fetching tool.

Uses only the standard library (urllib) so the pipeline has zero extra
runtime dependencies. Handles two kinds of public documentation:
- Plain text / Markdown / reStructuredText (e.g. raw.githubusercontent.com
  files): returned as-is.
- HTML pages (e.g. official doc sites): converted to a lightweight
  "pseudo-markdown" text where heading tags become '#'-prefixed lines, so
  the same heading-based chunker in pipeline/chunking.py works for both
  kinds of source uniformly.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "upgrade-buddy-research/0.1 (public docs risk extraction tool)"
MAX_BYTES = 2_000_000

_SKIP_TAGS = {"script", "style", "noscript", "svg", "header", "nav", "footer"}
_BLOCK_TAGS = {"p", "div", "li", "tr", "pre", "blockquote", "section", "article", "br"}
_HEADING_TAGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}


class _HtmlToPseudoMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._pending_heading_prefix: str | None = None
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _HEADING_TAGS:
            self.chunks.append("\n\n" + _HEADING_TAGS[tag] + " ")
        elif tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _HEADING_TAGS or tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.chunks.append(data)


def html_to_text(html: str) -> str:
    parser = _HtmlToPseudoMarkdown()
    parser.feed(html)
    text = "".join(parser.chunks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def http_get(url: str, timeout: float = 15.0) -> tuple[str, str]:
    """Returns (content_type, decoded_text). Raises on network/HTTP errors."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(MAX_BYTES)
        text = raw.decode("utf-8", errors="replace")
    return content_type, text


def fetch_document(url: str, timeout: float = 15.0) -> dict:
    """Fetches a URL and returns plain, chunker-ready text.

    Returns: {"url", "text", "content_type", "error"} - "error" is None on
    success, or a short message on failure (never raises, so a single dead
    seed URL doesn't abort the whole gather stage).
    """
    try:
        content_type, raw_text = http_get(url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"url": url, "text": "", "content_type": "", "error": str(exc)}

    is_html = "html" in content_type.lower() or raw_text.lstrip().lower().startswith(("<!doctype html", "<html"))
    text = html_to_text(raw_text) if is_html else raw_text
    return {"url": url, "text": text, "content_type": content_type, "error": None}


TOOL_SCHEMA = {
    "name": "fetch_url",
    "description": (
        "Fetch a public URL (official docs, changelog, migration guide) and "
        "return its content as plain text, with HTML converted to a "
        "lightweight markdown-like representation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The URL to fetch."}},
        "required": ["url"],
    },
}


def run_tool(tool_input: dict) -> dict:
    return fetch_document(tool_input["url"])
