"""Tests for safe App deserialization in conversation suggested-apps endpoint.

Regression test for GET /v1/conversations/{conversation_id}/suggested-apps:
If a conversation references an app whose stored document in Firestore is malformed
(e.g., missing required fields like category, author, image, description, or capabilities),
instantiating `App(**app_data)` raised an unhandled `pydantic.ValidationError`, returning
an HTTP 500 Internal Server Error to mobile/web clients and blocking the user from viewing
any suggested apps for that conversation.

Using safe deserialization (`App.deserialize_safe`) ensures that malformed or legacy app records
are logged and skipped, returning only valid suggested applications.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
import unittest

from pydantic import ValidationError
from models.app import App


def _valid_app_dict(app_id: str = "app_valid") -> dict[str, Any]:
    return {
        "id": app_id,
        "name": f"Valid App {app_id}",
        "category": "productivity",
        "author": "BasedHardware",
        "description": "A valid test application for conversation summaries.",
        "image": "https://example.com/icon.png",
        "capabilities": ["chat", "memories"],
        "approved": True,
        "uid": "user_1",
    }


class TestSuggestedAppsSafeDeserialization(unittest.TestCase):
    """Unit tests verifying safe App deserialization in conversation suggested-apps."""

    def test_raw_instantiation_raises_on_malformed_doc(self):
        """Confirm that bare App(**data) raises ValidationError on missing required fields."""
        malformed_docs = [
            {"id": "corrupt_1"},  # missing name, category, author, description, image, capabilities
            {"id": "corrupt_2", "name": "Missing Required"},  # missing category, author, image, etc.
            {"id": "corrupt_3", "name": "Bad Caps", "capabilities": 123},  # invalid capabilities type
        ]

        for doc in malformed_docs:
            with self.assertRaises(ValidationError):
                _ = App(**doc)

    def test_deserialize_safe_returns_none_for_malformed_doc(self):
        """Confirm that App.deserialize_safe returns None without raising on malformed docs."""
        malformed_docs = [
            None,
            {},
            {"id": "corrupt_1"},
            {"id": "corrupt_2", "name": "Missing Fields"},
            {"id": "corrupt_3", "name": "Bad Caps", "capabilities": 123},
        ]

        for doc in malformed_docs:
            app = App.deserialize_safe(doc)
            self.assertIsNone(app)

    def test_deserialize_safe_returns_app_for_valid_doc(self):
        """Confirm that App.deserialize_safe properly parses a valid app dict."""
        valid_dict = _valid_app_dict("app_prod_1")
        app = App.deserialize_safe(valid_dict)

        self.assertIsNotNone(app)
        self.assertEqual(app.id, "app_prod_1")
        self.assertEqual(app.name, "Valid App app_prod_1")
        self.assertEqual(app.category, "productivity")
        self.assertTrue(app.has_capability("chat"))

    def test_suggested_apps_loop_skips_malformed_and_missing_records(self):
        """Simulate get_conversation_suggested_apps resolution loop over mixed records."""
        suggested_app_ids = ["app_good_1", "app_corrupt", "app_missing", "app_good_2"]

        records = {
            "app_good_1": _valid_app_dict("app_good_1"),
            "app_corrupt": {"id": "app_corrupt", "name": "Incomplete"},
            "app_good_2": _valid_app_dict("app_good_2"),
        }

        def mock_get_available_app(aid: str, uid: str):
            return records.get(aid)

        suggested_apps = []
        for app_id in suggested_app_ids:
            app_data = mock_get_available_app(app_id, "user_1")
            if app_data:
                app = app_data if isinstance(app_data, App) else App.deserialize_safe(app_data)
                if not app:
                    continue
                suggested_apps.append(app)

        self.assertEqual(len(suggested_apps), 2)
        self.assertEqual([a.id for a in suggested_apps], ["app_good_1", "app_good_2"])

    def test_suggested_apps_preserves_pre_instantiated_app_objects(self):
        """Confirm that if app_data is already an App instance, it is safely retained."""
        valid_app = App(**_valid_app_dict("app_prebuilt"))

        app_data = valid_app
        app = app_data if isinstance(app_data, App) else App.deserialize_safe(app_data)

        self.assertIsNotNone(app)
        self.assertIs(app, valid_app)
        self.assertEqual(app.id, "app_prebuilt")

    def test_ast_check_conversations_router_uses_safe_deserialization(self):
        """Static check verifying routers/conversations.py does not use bare App(**app_data)."""
        router_path = Path(__file__).resolve().parents[2] / "routers" / "conversations.py"
        source = router_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_conversation_suggested_apps":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        # Ensure no bare App(**...) calls
                        if isinstance(child.func, ast.Name) and child.func.id == "App":
                            has_double_star = any(kw.arg is None for kw in child.keywords)
                            self.assertFalse(
                                has_double_star,
                                "get_conversation_suggested_apps must not call bare App(**...); use App.deserialize_safe",
                            )


if __name__ == "__main__":
    unittest.main()
