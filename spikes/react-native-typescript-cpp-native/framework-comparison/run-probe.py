#!/usr/bin/env python3
"""Dependency-free comparison probe for the disposable framework spike.

This intentionally validates the shared contract matrix, not framework runtime
support. A framework build must be run separately before claiming runtime proof.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent
MANIFEST = ROOT / "frameworks.json"
REQUIRED = {"name", "language", "mobile", "desktop", "native_boundary", "status"}


def main() -> int:
    data = json.loads(MANIFEST.read_text())
    candidates = data["candidates"]
    names = [item["name"] for item in candidates]
    assert len(names) == len(set(names)), "candidate names must be unique"
    assert {"lynx", "makepad"} <= set(names), "Lynx and Makepad must be included"
    assert "swift-native" in names, "Swift comparison must remain explicit"

    for candidate in candidates:
        missing = REQUIRED - candidate.keys()
        assert not missing, f"{candidate.get('name', '<unknown>')} missing {sorted(missing)}"
        assert candidate["mobile"] or candidate["desktop"] or candidate["name"] == "web-moonshine"
        assert candidate["native_boundary"]

    print(f"framework candidates: {len(candidates)}")
    print("contract probe: PASS")
    print("runtime claim: NOT MADE (framework-specific builds are separate evidence)")
    for candidate in candidates:
        targets = ",".join(target for target, enabled in (("mobile", candidate["mobile"]), ("desktop", candidate["desktop"])) if enabled) or "web"
        print(f"- {candidate['name']}: {targets}; {candidate['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
