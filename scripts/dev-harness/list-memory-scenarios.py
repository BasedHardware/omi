#!/usr/bin/env python3
"""List synthetic local memory emulator scenarios."""

from __future__ import annotations

from dev_harness.memory_scenarios import main

if __name__ == "__main__":
    raise SystemExit(main(["list"]))
