#!/usr/bin/env python3
"""Seed a named synthetic local memory emulator scenario."""

from __future__ import annotations

import os
import sys

from dev_harness.memory_scenarios import main

if __name__ == "__main__":
    scenario = os.environ.get("SCENARIO") or (sys.argv[1] if len(sys.argv) > 1 else "happy_path")
    extra = sys.argv[2:] if len(sys.argv) > 2 else []
    raise SystemExit(main(["seed", scenario, *extra]))
