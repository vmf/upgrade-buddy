"""GitHub REST API tool (keyless, subject to the ~60 req/hour anonymous rate limit).

Provides two capabilities used by the gather stage:
- `list_releases`: official GitHub Releases for a repo (release notes body).
- `search_issues`: issues/PRs matching a query, used as *candidate* sources
  that must pass the LLM triage step (see prompts/triage.md) before being
  trusted, unlike the hand-curated seed URLs in sources/seed_urls.py.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from tools.fetch import USER_AGENT

API_ROOT = "https://api.github.com"


def _get_json(url: str, timeout: float = 15.0):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def list_releases(repo: str, per_page: int = 10) -> list[dict]:
    try:
        data = _get_json(f"{API_ROOT}/repos/{repo}/releases?per_page={per_page}")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []
    return [
        {
            "tag_name": item.get("tag_name", ""),
            "name": item.get("name") or item.get("tag_name", ""),
            "url": item.get("html_url", ""),
            "published_at": item.get("published_at", ""),
            "body": (item.get("body") or "")[:20_000],
        }
        for item in data
        if isinstance(item, dict)
    ]


def search_issues(repo: str, terms: list[str], per_page: int = 8) -> list[dict]:
    if not terms:
        return []
    query = f"repo:{repo} " + " ".join(terms)
    encoded = urllib.parse.quote(query)
    try:
        data = _get_json(f"{API_ROOT}/search/issues?q={encoded}&per_page={per_page}&sort=comments&order=desc")
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    return [
        {
            "number": item.get("number"),
            "title": item.get("title", ""),
            "url": item.get("html_url", ""),
            "state": item.get("state", ""),
            "is_pull_request": "pull_request" in item,
            "body": (item.get("body") or "")[:4_000],
        }
        for item in items
    ]


TOOL_SCHEMAS = [
    {
        "name": "github_releases",
        "description": "List recent GitHub Releases (tag, notes body) for an owner/repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo, e.g. django/django"},
                "per_page": {"type": "integer", "default": 10},
            },
            "required": ["repo"],
        },
    },
    {
        "name": "github_search_issues",
        "description": "Search GitHub issues/PRs in a repo for upgrade-relevant keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "terms": {"type": "array", "items": {"type": "string"}},
                "per_page": {"type": "integer", "default": 8},
            },
            "required": ["repo", "terms"],
        },
    },
]


def run_tool(name: str, tool_input: dict):
    if name == "github_releases":
        return list_releases(tool_input["repo"], tool_input.get("per_page", 10))
    if name == "github_search_issues":
        return search_issues(tool_input["repo"], tool_input.get("terms", []), tool_input.get("per_page", 8))
    raise ValueError(f"Unknown tool: {name}")
