#!/usr/bin/env python3
"""Runner shim: execute the guard's self-test with the repo's own interpreter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", "-q", str(HERE / "test_workflow_apt_network_bounds.py")])
    )
