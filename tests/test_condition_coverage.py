"""Validation mechanism #2 (required by the assignment): every risk path
must have at least one target-version condition, and at least one
application/deployment-facing condition when the risk's affected_surface
implies application/deployment relevance.

This is a regression check on pipeline/stages.py::_enforce_coverage_rules,
which enforces the same rule deterministically before a risk path can ever
reach data/output/ - see schema/risk_model.py for the shared category/
surface sets so the two can't silently drift apart.
"""

from schema.risk_model import APPLICATION_OR_DEPLOYMENT_CATEGORIES, APPLICATION_OR_DEPLOYMENT_SURFACES


def test_every_risk_path_has_a_version_condition(upgrade_output: dict) -> None:
    for path in upgrade_output["risk_paths"]:
        categories = {c["category"] for c in path["conditions"]}
        assert "version" in categories, (
            f"risk path {path['path_id']!r} has no condition checking the target version"
        )


def test_application_deployment_surfaces_have_a_matching_condition(upgrade_output: dict) -> None:
    for path in upgrade_output["risk_paths"]:
        if path["affected_surface"] not in APPLICATION_OR_DEPLOYMENT_SURFACES:
            continue
        categories = {c["category"] for c in path["conditions"]}
        assert categories & APPLICATION_OR_DEPLOYMENT_CATEGORIES, (
            f"risk path {path['path_id']!r} affects {path['affected_surface']!r} but has no "
            "application/deployment-facing condition"
        )
