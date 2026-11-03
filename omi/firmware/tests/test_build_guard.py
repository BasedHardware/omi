#!/usr/bin/env python3
"""Execute the same CMake guard production includes; no compiler required."""
from pathlib import Path
import subprocess

GUARD = Path(__file__).resolve().parents[1] / "omi/cmake/safe-mode-build.cmake"
for fault, debug, development, expected in (
    (False, False, False, 0),
    (True, False, False, 1),
    (True, True, False, 1),
    (True, False, True, 1),
    (True, True, True, 0),
):
    proc = subprocess.run([
        "cmake", f"-DCONFIG_OMI_FAULT_INJECT={'ON' if fault else 'OFF'}",
        f"-DCONFIG_DEBUG={'ON' if debug else 'OFF'}",
        f"-DOMI_DEVELOPMENT_BUILD={'ON' if development else 'OFF'}", "-P", str(GUARD)
    ], capture_output=True, text=True)
    assert (proc.returncode != 0) == bool(expected), proc.stdout + proc.stderr
print("Release fault-injection guard: all 5 build configurations passed")
