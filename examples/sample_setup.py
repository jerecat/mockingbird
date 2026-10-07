#!/usr/bin/env python3
"""Tiny project setup with an optional user-controlled failure marker."""
from pathlib import Path
import sys

root = Path("work/setup-demo")
root.mkdir(parents=True, exist_ok=True)
if (root / "force-setup-failure").exists():
    print("Sample setup failure: remove work/setup-demo/force-setup-failure and retry setup.", file=sys.stderr)
    raise SystemExit(7)
(root / "ready.txt").write_text("Project preparation completed.\n")
print(f"Prepared {root / 'ready.txt'}")
