#!/usr/bin/env python3
"""Fail-closed Stable pointer preflight, including one acknowledged lost response."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _fields(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("fields", {}) if isinstance(data, dict) else {}


def _text(fields: dict, name: str) -> str:
    return fields.get(name, {}).get("stringValue", "")


def _generation(fields: dict) -> int:
    return int(fields.get("generation", {}).get("integerValue", "0"))


def verify(*, beta: dict, stable: dict, release_id: str, expected_release_id: str, expected_generation: int, operation: str) -> None:
    current_id = _text(stable, "release_id")
    current_generation = _generation(stable)
    if current_id == release_id:
        if current_generation != expected_generation + 1:
            raise ValueError("acknowledged Stable retry has unrelated generation drift")
        return
    if operation == "promote" and _text(beta, "release_id") != release_id:
        raise ValueError("Stable promotion requires the exact current qualified beta release ID")
    if current_id != expected_release_id or current_generation != expected_generation:
        raise ValueError(
            f"Stable pointer CAS mismatch: expected {expected_release_id!r}/{expected_generation}, "
            f"current {current_id!r}/{current_generation}"
        )
    if operation == "repoint" and not current_id:
        raise ValueError("repoint requires an existing stable pointer")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beta", type=Path, required=True)
    parser.add_argument("--stable", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--expected-release-id", default="")
    parser.add_argument("--expected-generation", type=int, required=True)
    parser.add_argument("--operation", choices=("promote", "repoint"), required=True)
    args = parser.parse_args()
    verify(beta=_fields(args.beta), stable=_fields(args.stable), release_id=args.release_id, expected_release_id=args.expected_release_id, expected_generation=args.expected_generation, operation=args.operation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
