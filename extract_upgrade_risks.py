#!/usr/bin/env python3
"""CLI entrypoint for the upgrade risk extraction pipeline.

Usage:
    uv run extract_upgrade_risks.py --project Django --current-version 3.2 --target-version 4.2

See DESIGN_NOTE.md for the pipeline architecture and README.md for setup.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from core.claude import Claude
from pipeline.orchestrator import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Project name, e.g. Django, React, Kubernetes, PostgreSQL, Next.js")
    parser.add_argument("--current-version", required=True, dest="current_version")
    parser.add_argument("--target-version", required=True, dest="target_version")
    args = parser.parse_args()

    load_dotenv()
    claude_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_api_key:
        print("Error: ANTHROPIC_API_KEY is not set. Update .env.", file=sys.stderr)
        return 1

    claude = Claude(model=claude_model)
    run_pipeline(args.project, args.current_version, args.target_version, claude)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
