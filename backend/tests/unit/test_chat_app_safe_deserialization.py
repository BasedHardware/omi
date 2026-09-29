"""Hermetic unit tests for safe App deserialization across chat routing surfaces.

Validates that chat routers do not invoke raw App(**...) constructors, preventing
unhandled ValidationError (HTTP 500) crashes when apps contain legacy or corrupt records.
"""

import ast
from pathlib import Path
import pytest
from models.app import App


def test_app_deserialize_safe_handles_malformed_records():
    """Verify App.deserialize_safe contract for corrupt app records."""
    malformed_records = [
        None,
        {},
        {"id": "bad_app"},  # Missing required name, author, description, etc.
        {"id": "bad_app_2", "name": "Missing other required fields"},
    ]
    for record in malformed_records:
        assert App.deserialize_safe(record) is None


def test_chat_routers_have_no_raw_app_instantiation():
    """Ensure raw App(**...) calls are eliminated from chat routers."""
    backend_dir = Path(__file__).resolve().parents[2]
    target_files = [
        backend_dir / "routers" / "chat.py",
        backend_dir / "routers" / "chat_generation.py",
    ]

    for target_path in target_files:
        assert target_path.exists(), f"Target file not found: {target_path}"
        tree = ast.parse(target_path.read_text(encoding="utf-8"))

        raw_app_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "App":
                # Check if it unpacks kwargs via **
                has_star_args = any(kw.arg is None for kw in node.keywords)
                if has_star_args:
                    raw_app_calls.append(node.lineno)

        assert not raw_app_calls, (
            f"Raw App(**...) constructor found in {target_path.name} at lines {raw_app_calls}. "
            "Use App.deserialize_safe(...) instead."
        )
