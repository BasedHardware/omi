"""Offline startup observations. Never imports a device API or opens hardware."""
import hashlib
import json
import re
import struct
from pathlib import Path

MILESTONES = {
    "main": "Starting omi", "watchdog": "Watchdog initialized",
    "settings": "Settings initialized.", "battery": "Battery initialized",
    "storage": "Storage service initialized", "hci": "Transport bluetooth initialized",
    "advertising": "Advertising successfully started", "microphone": "Microphone started",
    "initialized": "Device initialized successful",
}

def load_fixture(directory, index):
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported fixture schema")
    row = manifest["records"][index]
    path = root / row["file"]
    if path.resolve().parent != root.resolve():
        raise ValueError("fixture escapes root")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError("fixture hash mismatch")
    return data.decode("utf-8"), row

def observe(text):
    clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).replace("\r", "")
    found = {name: token in clean for name, token in MILESTONES.items()}
    errors = [line for line in clean.splitlines()
              if any(token in line for token in ("<err>", "ASSERTION FAIL", "FATAL ERROR"))]
    warnings = [line for line in clean.splitlines() if "<wrn>" in line]
    return {"state": "error_reported" if errors else
            "initialization_reported" if all(found.values()) else "incomplete_observation",
            "milestones": found, "errors": errors, "warnings": warnings,
            "independent_ble_verified": False, "audio_health_verified": False,
            "storage_integrity_verified": False, "continuous_stability_verified": False}

def decode_snapshot(control, buffer, expected_address=0x20002010, expected_size=4096):
    if len(control) != 48 or not control[:16].startswith(b"SEGGER RTT\0"):
        raise ValueError("uninitialized or unknown RTT header; boot outcome unknown")
    up, down = struct.unpack_from("<II", control, 16)
    name, address, size, write, read, flags = struct.unpack_from("<IIIIII", control, 24)
    if (up, down, address, size, flags) != (3, 3, expected_address, expected_size, 0):
        raise ValueError("unexpected descriptor")
    if len(buffer) != size or not 0 <= write < size or not 0 <= read < size:
        raise ValueError("invalid offsets or buffer size")
    raw = buffer[read:write] if write >= read else buffer[read:] + buffer[:write]
    return {"raw": raw, "buffer_can_drop_later_output": True,
            "target_writes": 0, "atomic_snapshot": False,
            "observation": observe(raw.decode("utf-8", errors="replace"))}

def compare_observations(first, second):
    return {name: {"first": first["milestones"][name], "repeat": second["milestones"][name]}
            for name in MILESTONES}

def decision_at(observations, now, deadline):
    """Virtual host-time policy; a missing/delayed observation never proves failed boot."""
    eligible = [row for row in observations if row["host_seconds"] <= now]
    for row in reversed(eligible):
        if row.get("valid_header"):
            state = observe(row.get("text", ""))["state"]
            return state if state in ("initialization_reported", "error_reported") else "capture_incomplete"
    return "observation_timeout_unknown" if now >= deadline else "waiting"
