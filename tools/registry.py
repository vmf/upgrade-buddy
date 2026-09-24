"""Package registry metadata tool (PyPI / npm, both keyless)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from tools.fetch import USER_AGENT


def _get_json(url: str, timeout: float = 15.0):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def pypi_metadata(package: str, target_version: str | None = None) -> dict:
    """Returns metadata for `target_version` when PyPI has that exact release,
    plus the registry's current "latest" for context. The two are kept
    distinct so callers never mistake "latest today" for "as of the target
    version" - PyPI's index has moved on since these upgrades shipped.
    """
    try:
        latest_data = _get_json(f"https://pypi.org/pypi/{package}/json")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return {}
    latest_info = latest_data.get("info", {})

    target_info = None
    if target_version:
        try:
            target_data = _get_json(f"https://pypi.org/pypi/{package}/{target_version}/json")
            target_info = target_data.get("info", {})
        except (urllib.error.URLError, TimeoutError, ValueError):
            target_info = None

    chosen = target_info or latest_info
    return {
        "package": package,
        "queried_version": target_version if target_info else None,
        "latest_version": latest_info.get("version"),
        "requires_python": chosen.get("requires_python"),
        "classifiers": [c for c in chosen.get("classifiers", []) if "Python ::" in c],
        "project_urls": chosen.get("project_urls") or {},
        "summary": chosen.get("summary"),
    }


def npm_metadata(package: str, target_version: str | None = None) -> dict:
    """Same target-version-vs-latest distinction as pypi_metadata, using the
    npm registry's per-package document which embeds every published version.
    """
    try:
        data = _get_json(f"https://registry.npmjs.org/{package}")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return {}
    versions = data.get("versions") or {}
    latest = (data.get("dist-tags") or {}).get("latest")

    target_key = None
    if target_version:
        candidates = [v for v in versions if v == target_version or v.startswith(f"{target_version}.")]
        stable = [v for v in candidates if "-" not in v]  # drop alpha/beta/rc pre-releases
        pool = stable or candidates
        if pool:
            # Prefer the first stable release of that version line (e.g. 18.0.0
            # over 18.2.0) since that's what "upgrading to 18" means.
            def _sort_key(v: str) -> tuple:
                parts = v.split("-")[0].split(".")
                return tuple(int(p) if p.isdigit() else 0 for p in parts)

            target_key = sorted(pool, key=_sort_key)[0]

    chosen_key = target_key or latest
    chosen_info = versions.get(chosen_key, {}) if chosen_key else {}
    return {
        "package": package,
        "queried_version": target_key,
        "latest_version": latest,
        "engines": chosen_info.get("engines") or {},
        "deprecated": chosen_info.get("deprecated"),
        "peer_dependencies": chosen_info.get("peerDependencies") or {},
    }


TOOL_SCHEMA = {
    "name": "registry_metadata",
    "description": "Look up package registry metadata (PyPI or npm): latest version, runtime/engine requirements, deprecation flags.",
    "input_schema": {
        "type": "object",
        "properties": {
            "registry": {"type": "string", "enum": ["pypi", "npm"]},
            "package": {"type": "string"},
            "target_version": {"type": "string"},
        },
        "required": ["registry", "package"],
    },
}


def run_tool(tool_input: dict) -> dict:
    target_version = tool_input.get("target_version")
    if tool_input["registry"] == "pypi":
        return pypi_metadata(tool_input["package"], target_version)
    return npm_metadata(tool_input["package"], target_version)
