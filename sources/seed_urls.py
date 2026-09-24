"""Curated, keyless, official sources for the 5 required upgrades.

Each project maps to:
- `github_repo`: "owner/repo" used by tools/github.py to pull releases and
  search issues/PRs (keyless, GitHub's public REST API).
- `registry`: optional (package_manager, package_name) used by
  tools/registry.py to pull PyPI/npm metadata.
- `seed_urls`: hand-picked official documents (release notes, changelogs,
  deprecation guides, migration guides). These are trusted by construction -
  a human picked them because they are the project's own documentation - so
  the pipeline does NOT run them through the LLM triage step used for
  GitHub-discovered candidates (see prompts/triage.md and
  pipeline/stages.py::stage1_gather).

This assignment only needs to support 5 specific upgrades, so the list is
hardcoded rather than generically derived from version ranges - see
DESIGN_NOTE.md for how this would generalize to arbitrary projects/versions.
"""

from __future__ import annotations

from typing import TypedDict


class SeedUrl(TypedDict):
    url: str
    source_type: str
    title: str


class ProjectConfig(TypedDict, total=False):
    display_name: str
    github_repo: str
    registry: tuple[str, str] | None
    seed_urls: list[SeedUrl]
    github_search_terms: list[str]


PROJECT_CONFIGS: dict[str, ProjectConfig] = {
    "django": {
        "display_name": "Django",
        "github_repo": "django/django",
        "registry": ("pypi", "django"),
        "seed_urls": [
            {
                "url": "https://raw.githubusercontent.com/django/django/main/docs/releases/4.2.txt",
                "source_type": "official_release_notes",
                "title": "Django 4.2 release notes",
            },
            {
                "url": "https://raw.githubusercontent.com/django/django/main/docs/releases/4.1.txt",
                "source_type": "official_release_notes",
                "title": "Django 4.1 release notes",
            },
            {
                "url": "https://raw.githubusercontent.com/django/django/main/docs/releases/4.0.txt",
                "source_type": "official_release_notes",
                "title": "Django 4.0 release notes",
            },
            {
                "url": "https://raw.githubusercontent.com/django/django/main/docs/internals/deprecation.txt",
                "source_type": "deprecation_notice",
                "title": "Django deprecation timeline",
            },
        ],
        "github_search_terms": ["deprecat", "removed", "breaking"],
    },
    "react": {
        "display_name": "React",
        "github_repo": "facebook/react",
        "registry": ("npm", "react"),
        "seed_urls": [
            {
                "url": "https://raw.githubusercontent.com/facebook/react/main/CHANGELOG.md",
                "source_type": "official_changelog",
                "title": "React CHANGELOG.md",
            },
            {
                "url": "https://react.dev/blog/2022/03/08/react-18-upgrade-guide",
                "source_type": "official_migration_guide",
                "title": "How to Upgrade to React 18",
            },
            {
                "url": "https://react.dev/blog/2022/03/29/react-v18",
                "source_type": "official_release_notes",
                "title": "React v18.0 release announcement",
            },
        ],
        "github_search_terms": ["deprecat", "removed", "breaking change", "18.0"],
    },
    "kubernetes": {
        "display_name": "Kubernetes",
        "github_repo": "kubernetes/kubernetes",
        "registry": None,
        "seed_urls": [
            {
                "url": "https://kubernetes.io/docs/reference/using-api/deprecation-guide/",
                "source_type": "deprecation_notice",
                "title": "Kubernetes Deprecated API Migration Guide",
            },
            {
                "url": "https://raw.githubusercontent.com/kubernetes/kubernetes/master/CHANGELOG/CHANGELOG-1.29.md",
                "source_type": "official_changelog",
                "title": "Kubernetes 1.29 CHANGELOG",
            },
            {
                "url": "https://raw.githubusercontent.com/kubernetes/kubernetes/master/CHANGELOG/CHANGELOG-1.24.md",
                "source_type": "official_changelog",
                "title": "Kubernetes 1.24 CHANGELOG",
            },
        ],
        "github_search_terms": ["removed api", "deprecat", "1.29"],
    },
    "postgresql": {
        "display_name": "PostgreSQL",
        "github_repo": "postgres/postgres",
        "registry": None,
        "seed_urls": [
            {
                "url": "https://www.postgresql.org/docs/16/release-16.html",
                "source_type": "official_release_notes",
                "title": "PostgreSQL 16 release notes",
            },
            {
                "url": "https://www.postgresql.org/docs/16/release-15.html",
                "source_type": "official_release_notes",
                "title": "PostgreSQL 15 release notes",
            },
            {
                "url": "https://www.postgresql.org/docs/16/release-14.html",
                "source_type": "official_release_notes",
                "title": "PostgreSQL 14 release notes",
            },
        ],
        "github_search_terms": [],
    },
    "next.js": {
        "display_name": "Next.js",
        "github_repo": "vercel/next.js",
        "registry": ("npm", "next"),
        "seed_urls": [
            {
                "url": "https://nextjs.org/docs/app/guides/upgrading/version-14",
                "source_type": "official_migration_guide",
                "title": "Next.js: upgrading from 13 to 14",
            },
            {
                "url": "https://nextjs.org/blog/next-13",
                "source_type": "official_release_notes",
                "title": "Next.js 13 announcement",
            },
            {
                "url": "https://nextjs.org/blog/next-14",
                "source_type": "official_release_notes",
                "title": "Next.js 14 announcement",
            },
        ],
        "github_search_terms": ["deprecat", "removed", "breaking change"],
    },
}


def resolve_project(project: str) -> tuple[str, ProjectConfig]:
    """Looks up a project config by (case/punctuation-insensitive) name."""
    key = project.strip().lower()
    if key in PROJECT_CONFIGS:
        return key, PROJECT_CONFIGS[key]
    aliases = {"nextjs": "next.js", "next": "next.js", "postgres": "postgresql", "k8s": "kubernetes"}
    if key in aliases:
        resolved = aliases[key]
        return resolved, PROJECT_CONFIGS[resolved]
    raise KeyError(
        f"No curated source config for project {project!r}. "
        f"Known projects: {', '.join(PROJECT_CONFIGS)}"
    )
