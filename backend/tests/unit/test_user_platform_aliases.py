"""Tests for X-App-Platform normalization without importing Firestore clients."""

from __future__ import annotations

import ast
from pathlib import Path


USERS_SRC = Path(__file__).resolve().parents[2] / "database" / "users.py"


def _platform_aliases() -> dict[str, str]:
    module = ast.parse(USERS_SRC.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "_PLATFORM_ALIASES" for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError("_PLATFORM_ALIASES not found")


def test_linux_platform_header_records_desktop_activity():
    aliases = _platform_aliases()

    assert aliases["linux"] == "desktop"
