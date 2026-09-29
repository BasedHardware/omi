"""Unit tests verifying defensive deserialization in advice router.

Ensures that malformed, legacy, or incomplete advice records in Firestore
do not crash the list or patch endpoints with an HTTP 500, but instead skip
the broken row (or 404 on single item update) and log a safe identifier.
"""

from datetime import datetime, timezone
import importlib.util
import logging
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


# Stub minimal dependencies hermetically
_pkg("fastapi")
_fastapi = _mod("fastapi")


class FakeAPIRouter:
    def get(self, *a, **kw):
        return lambda f: f

    def post(self, *a, **kw):
        return lambda f: f

    def patch(self, *a, **kw):
        return lambda f: f

    def delete(self, *a, **kw):
        return lambda f: f


_fastapi.APIRouter = FakeAPIRouter
_fastapi.Depends = lambda x: x
_fastapi.Query = lambda default=None, **kw: default


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


_fastapi.HTTPException = HTTPException

_pkg("pydantic")
_pydantic = _mod("pydantic")


class FakeValidationError(Exception):
    pass


_pydantic.ValidationError = FakeValidationError


class FakeBaseModel:
    def __init__(self, **data):
        for k, v in data.items():
            setattr(self, k, v)

    @classmethod
    def model_validate(cls, data):
        if not isinstance(data, dict):
            raise FakeValidationError("Expected dict")
        required = ["id", "content", "category", "created_at", "updated_at"]
        for field in required:
            if field not in data or data[field] is None:
                raise FakeValidationError(f"Missing required field: {field}")
        conf = data.get("confidence")
        if conf is not None and (conf < 0.0 or conf > 1.0):
            raise FakeValidationError("confidence out of bounds 0..1")
        return cls(**data)


_pydantic.BaseModel = FakeBaseModel
_pydantic.Field = lambda *a, **kw: None

_pkg("database")
_db_advice = _mod("database.advice")
_db_advice.get_advice = MagicMock()
_db_advice.update_advice = MagicMock()
_db_advice.create_advice = MagicMock()
_db_advice.delete_advice = MagicMock()
_db_advice.mark_all_advice_read = MagicMock()

_pkg("models")
_models_advice = _mod("models.advice")


class Advice(FakeBaseModel):
    pass


_models_advice.Advice = Advice

_models_shared = _mod("models.shared")
_models_shared.StatusResponse = dict

_pkg("utils")
_pkg("utils.other")
_auth_mod = _mod("utils.other.endpoints")
_auth_mod.get_current_user_uid = MagicMock(return_value="test-uid-456")

_log_sanitizer = _mod("utils.log_sanitizer")
_log_sanitizer.sanitize = lambda s: s


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


advice_router = _load(
    "routers._advice_deserialization_test",
    "routers/advice.py",
)


class TestAdviceDeserializationResilience(unittest.TestCase):
    def setUp(self):
        self.uid = "test-uid-456"
        self.now = datetime.now(timezone.utc)
        self.valid_doc_1 = {
            "id": "adv-1",
            "content": "Take a 5-minute break",
            "category": "wellness",
            "confidence": 0.9,
            "created_at": self.now,
            "updated_at": self.now,
            "is_read": False,
            "is_dismissed": False,
        }
        self.valid_doc_2 = {
            "id": "adv-2",
            "content": "Review action items before standup",
            "category": "productivity",
            "confidence": 0.85,
            "created_at": self.now,
            "updated_at": self.now,
            "is_read": False,
            "is_dismissed": False,
        }

    def test_get_advice_returns_valid_items(self):
        with patch.object(advice_router.advice_db, "get_advice", return_value=[self.valid_doc_1, self.valid_doc_2]):
            results = advice_router.get_advice(uid=self.uid)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].id, "adv-1")
            self.assertEqual(results[1].id, "adv-2")

    def test_get_advice_skips_malformed_items_without_500(self):
        corrupted_missing_content = {
            "id": "adv-bad-1",
            "category": "wellness",
            "created_at": self.now,
            "updated_at": self.now,
        }
        corrupted_invalid_confidence = {
            "id": "adv-bad-2",
            "content": "Invalid confidence score",
            "category": "wellness",
            "confidence": 3.5,
            "created_at": self.now,
            "updated_at": self.now,
        }
        raw_stream = [self.valid_doc_1, corrupted_missing_content, self.valid_doc_2, corrupted_invalid_confidence]

        with patch.object(advice_router.advice_db, "get_advice", return_value=raw_stream), \
             patch.object(advice_router.logger, "warning") as mock_warn:
            results = advice_router.get_advice(uid=self.uid)

            # Both valid items are preserved; corrupted items are skipped
            self.assertEqual(len(results), 2)
            self.assertEqual([r.id for r in results], ["adv-1", "adv-2"])

            # Warnings were logged for skipped items with safe identifiers
            self.assertEqual(mock_warn.call_count, 2)
            warn_logged_ids = [call[0][2] for call in mock_warn.call_args_list]
            self.assertIn("adv-bad-1", warn_logged_ids)
            self.assertIn("adv-bad-2", warn_logged_ids)

    def test_get_advice_handles_all_malformed_records(self):
        all_bad = [
            {"id": "bad-1"},
            {"id": "bad-2", "content": None},
        ]
        with patch.object(advice_router.advice_db, "get_advice", return_value=all_bad):
            results = advice_router.get_advice(uid=self.uid)
            self.assertEqual(results, [])

    def test_update_advice_404_when_stored_record_is_malformed(self):
        bad_updated_record = {
            "id": "adv-1",
            # missing required content, category, etc.
            "is_read": True,
        }
        req = advice_router.UpdateAdviceRequest(is_read=True)

        with patch.object(advice_router.advice_db, "update_advice", return_value=bad_updated_record), \
             patch.object(advice_router.logger, "warning") as mock_warn:
            with self.assertRaises(advice_router.HTTPException) as ctx:
                advice_router.update_advice("adv-1", req, uid=self.uid)
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertEqual(ctx.exception.detail, "Advice not found")
            mock_warn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
