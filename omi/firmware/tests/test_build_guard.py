#!/usr/bin/env python3
"""Execute the same CMake guard production includes; no compiler required."""
from pathlib import Path
import subprocess

GUARD = Path(__file__).resolve().parents[1] / "omi/cmake/safe-mode-build.cmake"
for fault, debug, development, kind, expected in (
    (False, False, False, "Release", 0),
    (True, False, False, "", 1),
    (True, True, False, "", 1),
    (True, False, True, "", 1),
    (True, True, True, "Debug", 0),
    (True, True, True, "Release", 1),
    (True, True, True, "RelWithDebInfo", 1),
    (True, True, True, "MinSizeRel", 1),
):
    proc = subprocess.run([
        "cmake", f"-DCONFIG_OMI_FAULT_INJECT={'ON' if fault else 'OFF'}",
        f"-DCONFIG_DEBUG={'ON' if debug else 'OFF'}",
        f"-DCMAKE_BUILD_TYPE={kind}",
        f"-DOMI_DEVELOPMENT_BUILD={'ON' if development else 'OFF'}", "-P", str(GUARD)
    ], capture_output=True, text=True)
    assert (proc.returncode != 0) == bool(expected), proc.stdout + proc.stderr
print("Release fault-injection guard: all 8 build configurations passed")

# Sysbuild jig builds opt in through the environment; any other value fails closed.
import os
for value, expected in (("1", 0), ("", 1), ("ON", 1), ("0", 1)):
    env = dict(os.environ, OMI_DEVELOPMENT_BUILD=value)
    proc = subprocess.run([
        "cmake", "-DCONFIG_OMI_FAULT_INJECT=ON", "-DCONFIG_DEBUG=ON", "-DCMAKE_BUILD_TYPE=Debug",
        "-P", str(GUARD)
    ], capture_output=True, text=True, env=env)
    assert (proc.returncode != 0) == bool(expected), proc.stdout + proc.stderr
print("Development opt-in through the environment: all 4 values passed")

# Recovery must never compile with the image-target rejection hook missing.
for notification, status, upload in ((True, True, True), (False, True, True),
                                      (True, False, True), (True, True, False)):
    proc = subprocess.run([
        "cmake", "-DCONFIG_MCUMGR=ON",
        f"-DCONFIG_MCUMGR_MGMT_NOTIFICATION_HOOKS={'ON' if notification else 'OFF'}",
        f"-DCONFIG_MCUMGR_GRP_IMG_STATUS_HOOKS={'ON' if status else 'OFF'}",
        f"-DCONFIG_MCUMGR_GRP_IMG_UPLOAD_CHECK_HOOK={'ON' if upload else 'OFF'}",
        "-P", str(GUARD)
    ], capture_output=True, text=True)
    assert (proc.returncode == 0) == (notification and status and upload), proc.stdout + proc.stderr
print("Recovery callback guard: all 4 hook configurations passed")
