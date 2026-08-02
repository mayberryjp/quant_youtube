from __future__ import annotations

import runpy
import sys
import time
from pathlib import Path

MIGRATION_MARKER = Path("/tmp/allin-migrations.done")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m app.services.run_after_migrations <module>")

    target_module = sys.argv[1]
    while not MIGRATION_MARKER.exists():
        time.sleep(1)

    runpy.run_module(target_module, run_name="__main__")


if __name__ == "__main__":
    main()
