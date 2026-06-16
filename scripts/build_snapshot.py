#!/usr/bin/env python3
"""
One-time script to build the Daytona compliance-scanner snapshot.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

from daytona import AsyncDaytona, CreateSnapshotParams, Image  
SNAPSHOT_NAME = os.environ.get("DAYTONA_SCANNER_SNAPSHOT", "compliance-scanner-v1")


async def main() -> None:
    image = (
        Image.debian_slim("3.12")
        .run_commands(
            "apt-get update && apt-get install -y git curl",
            "pip install semgrep checkov",
            "curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog"
            "/main/scripts/install.sh | sh -s -- -b /usr/local/bin",
        )
    )

    print(f"Building snapshot '{SNAPSHOT_NAME}' — this may take a few minutes...")

    async with AsyncDaytona() as daytona:
        snapshot = await daytona.snapshot.create(
            CreateSnapshotParams(name=SNAPSHOT_NAME, image=image),
            timeout=600,
        )

    print(f"\nSnapshot created: {snapshot.name}")
    print(f"\nAdd this to your .env file:")
    print(f"DAYTONA_SCANNER_SNAPSHOT={snapshot.name}")


if __name__ == "__main__":
    if not os.environ.get("DAYTONA_API_KEY"):
        print("ERROR: DAYTONA_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main())
