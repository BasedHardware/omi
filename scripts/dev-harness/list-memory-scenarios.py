#!/usr/bin/env python3
"""List synthetic V17 local emulator scenarios."""

from __future__ import annotations

from dev_harness.v17_scenarios import main

if __name__ == "__main__":
    raise SystemExit(main(["list"]))
