import json
from pathlib import Path

import pytest

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "output"

REQUIRED_UPGRADES = ["Django", "React", "Kubernetes", "PostgreSQL", "Next.js"]


def _load_output(project: str) -> dict | None:
    path = OUTPUT_DIR / f"{project}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


@pytest.fixture(params=REQUIRED_UPGRADES)
def upgrade_output(request) -> dict:
    data = _load_output(request.param)
    if data is None:
        pytest.skip(f"data/output/{request.param}.json not generated yet - run extract_upgrade_risks.py first")
    return data
