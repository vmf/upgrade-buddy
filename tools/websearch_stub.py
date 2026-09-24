"""Optional pluggable web-search fallback.

The 5 required upgrades are fully covered by curated seed URLs + the GitHub
and registry tools (see sources/seed_urls.py), so this tool is a documented
no-op unless a SEARCH_API_KEY is configured in .env. It exists so the
pipeline can scale to projects that don't have a curated seed list (see
DESIGN_NOTE.md, "scaling to thousands of projects") without changing any
other stage - stage1_gather calls this the same way it calls the other
tools, and simply gets an empty result set today.
"""

from __future__ import annotations

import os

TOOL_SCHEMA = {
    "name": "web_search",
    "description": "Search the public web for documentation about a project/version. No-op unless a search API key is configured.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}


def web_search(query: str) -> list[dict]:
    api_key = os.getenv("SEARCH_API_KEY")
    if not api_key:
        return []
    # Plug in a real provider here (Brave Search, Tavily, SerpAPI, ...) once
    # SEARCH_API_KEY is set. Left unimplemented: none of the 5 required
    # upgrades need it, and guessing at a provider's request shape without
    # being able to test it against a real key would be worse than an
    # honest no-op.
    return []


def run_tool(tool_input: dict) -> list[dict]:
    return web_search(tool_input["query"])
