import math
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class _NotFound(Exception):
    pass


for _p in ["google", "google.cloud", "google.api_core", "database"]:
    _pkg(_p)
_mod("google.api_core.exceptions", NotFound=_NotFound)
_mod("google.cloud.firestore", SERVER_TIMESTAMP=MagicMock(), Query=MagicMock())
_mod("google.cloud.firestore_v1.base_query", FieldFilter=MagicMock())
_mod("database._client", db=MagicMock())


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("database.advice", str(BACKEND_DIR / "database" / "advice.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.advice"] = mod
    spec.loader.exec_module(mod)
    return mod


advice = _load()


def test_validate_uid_rejects_empty():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        advice._validate_uid("")

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        advice._validate_uid("   ")

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        advice._validate_uid(None)


def test_validate_advice_id_rejects_empty():
    with pytest.raises(ValueError, match="advice_id must be a non-empty string"):
        advice._validate_advice_id("")

    with pytest.raises(ValueError, match="advice_id must be a non-empty string"):
        advice._validate_advice_id("   ")


def test_sanitize_content_rejects_empty():
    with pytest.raises(ValueError, match="content must be a non-empty string"):
        advice._sanitize_content("")

    with pytest.raises(ValueError, match="content must be a non-empty string"):
        advice._sanitize_content("   ")


def test_sanitize_category_defaults_to_other():
    assert advice._sanitize_category("") == "other"
    assert advice._sanitize_category("   ") == "other"
    assert advice._sanitize_category(None) == "other"
    assert advice._sanitize_category("productivity") == "productivity"


def test_sanitize_confidence_clamps_and_handles_non_finite():
    assert advice._sanitize_confidence(None) == 0.5
    assert advice._sanitize_confidence(float("nan")) == 0.5
    assert advice._sanitize_confidence(float("inf")) == 0.5
    assert advice._sanitize_confidence(-0.5) == 0.0
    assert advice._sanitize_confidence(1.5) == 1.0
    assert advice._sanitize_confidence(0.75) == 0.75
    assert advice._sanitize_confidence("invalid") == 0.5


def test_create_advice_validates_and_sanitizes():
    doc_mock = MagicMock()
    col_mock = MagicMock()
    col_mock.document.return_value = doc_mock
    with patch.object(advice, "_user_col", return_value=col_mock):
        doc = advice.create_advice("u123", "  Take a break  ", confidence=1.8)

    assert doc["content"] == "Take a break"
    assert doc["confidence"] == 1.0
    assert doc["category"] == "other"
    doc_mock.set.assert_called_once()
