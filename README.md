# Upgrade Buddy

Upgrade buddy is a batch pipeline that extracts structured "upgrade risk paths" from public documentation for open-source software upgrades. See [below](#upgrade-risk-extraction-pipeline)
for setup/usage, and `DESIGN_NOTE.md` for the architecture writeup.

## Prerequisites

- Python 3.9+
- Anthropic API Key

## Setup

### Step 1: Configure the environment variables

1. Create or edit the `.env` file in the project root and verify that the following variables are set correctly:

```
ANTHROPIC_API_KEY=""  # Enter your Anthropic API secret key
```

### Step 2: Install dependencies

#### Option 1: Setup with uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver.

1. Install uv, if not already installed:

```bash
pip install uv
```

2. Create and activate a virtual environment:

```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
uv pip install -e .
```

4. Run the project

```bash
uv run main.py
```

#### Option 2: Setup without uv

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install anthropic python-dotenv
```

3. Run the project

```bash
python main.py
```

## Upgrade Risk Extraction Pipeline

Given a project name, current version, and target version, this pipeline
gathers public documentation (official release notes, changelogs,
migration guides, deprecation notices, GitHub releases/issues, package
registry metadata) and extracts a structured, evidence-grounded JSON
"upgrade risk model" - see `DESIGN_NOTE.md` for the full architecture and
answers to the required design questions.

### Running it

```bash
uv run extract_upgrade_risks.py --project Django --current-version 3.2 --target-version 4.2
```

Currently-curated projects (see `sources/seed_urls.py::PROJECT_CONFIGS`):
`Django`, `React`, `Kubernetes`, `PostgreSQL`, `Next.js`. Run all 5 required
upgrades with:

```bash
uv run extract_upgrade_risks.py --project Django      --current-version 3.2  --target-version 4.2
uv run extract_upgrade_risks.py --project React       --current-version 17   --target-version 18
uv run extract_upgrade_risks.py --project Kubernetes   --current-version 1.23 --target-version 1.29
uv run extract_upgrade_risks.py --project PostgreSQL   --current-version 13   --target-version 16
uv run extract_upgrade_risks.py --project Next.js      --current-version 12   --target-version 14
```

### Output

Each run writes, per upgrade, into `data/`:
- `data/output/<Project>.json` - the final Part-5-shaped upgrade risk model.
- `data/output/<Project>_sources.json` - the Part-1-shaped source inventory.
- `data/output/<Project>_evidence_summary.json` - the Part-4-shaped evidence summary.
- `data/intermediate/<project>/` - every stage's raw artifact (fetched docs,
  chunked/classified candidates, raw vs. grounded risk paths), for
  debugging and for inspecting what the pipeline actually saw.

### Validation

```bash
uv run pytest
```

Runs three checks against every `data/output/<Project>.json` present
(skipped for any upgrade not yet generated):
1. Schema validation against `schema/risk_model.py::UpgradeRiskModel`.
2. Every condition has non-empty, source-inventory-referencing evidence
   (a Python re-check of the pipeline's own deterministic gate).
3. Every risk path has >=1 target-version condition, and >=1
   application/deployment-facing condition when its `affected_surface`
   implies one.

### Assumptions and limitations

- Scoped to exactly the 5 required upgrades' curated seed sources; scaling
  to arbitrary projects/versions would need either a generic seed-URL
  discovery step or a real search API key (see `DESIGN_NOTE.md`, question 7).
- GitHub's anonymous API rate limit (~60 req/hr) is not handled with
  backoff/retry - fine for a handful of runs, not for bulk use.
- HTML-to-text conversion (`tools/fetch.py`) is a lightweight custom parser,
  not a full readability/boilerplate-removal library; it works well for the
  doc sites this pipeline targets but may need adjustment for other sites.
- Chunk-level near-duplicate detection is an exact-match fingerprint over
  normalized text, not fuzzy/semantic dedup.
- Every LLM stage is grounded in the fetched documentation; nothing was
  fabricated or filled in from general model knowledge about these
  frameworks - if a fact isn't in a fetched chunk, it isn't cited.
