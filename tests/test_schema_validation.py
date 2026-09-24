"""Validation mechanism #1: every final output must conform to
schema/risk_model.py::UpgradeRiskModel. This is the same pydantic model the
pipeline itself validates against before writing data/output/*.json (see
pipeline/orchestrator.py), re-checked here so a hand-edited or stale output
file would also be caught.
"""

from schema.risk_model import UpgradeRiskModel


def test_output_matches_schema(upgrade_output: dict) -> None:
    UpgradeRiskModel.model_validate(upgrade_output)


def test_every_condition_has_evidence(upgrade_output: dict) -> None:
    """Belt-and-suspenders re-check of the deterministic evidence gate in
    pipeline/stages.py::_filter_unsupported - every condition must cite at
    least one piece of evidence with a source_id present in the inventory.
    """
    valid_source_ids = {s["source_id"] for s in upgrade_output["source_inventory"]}
    for path in upgrade_output["risk_paths"]:
        for condition in path["conditions"]:
            assert condition["evidence"], (
                f"{path['path_id']}/{condition['condition_id']} has no evidence"
            )
            for evidence in condition["evidence"]:
                assert evidence["source_id"] in valid_source_ids, (
                    f"{path['path_id']}/{condition['condition_id']} cites unknown "
                    f"source_id {evidence['source_id']!r}"
                )
