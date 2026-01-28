"""
Unit tests for LLM usage database operations.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Create mock db before importing the module
mock_db = MagicMock()

# Mock the database client module
mock_client_module = MagicMock()
mock_client_module.db = mock_db
sys.modules["database._client"] = mock_client_module
sys.modules["stripe"] = MagicMock()

_google_module = sys.modules.setdefault("google", types.ModuleType("google"))
_google_cloud_module = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
_google_firestore_module = types.ModuleType("google.cloud.firestore")
_google_firestore_module.Increment = lambda x: {"__increment": x}
sys.modules.setdefault("google.cloud.firestore", _google_firestore_module)
setattr(_google_module, "cloud", _google_cloud_module)
setattr(_google_cloud_module, "firestore", _google_firestore_module)

from database import llm_usage


class _FakeDocSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self):
        self.set_calls = []

    def set(self, data, merge=False):
        self.set_calls.append({"data": data, "merge": merge})

    def get(self):
        return _FakeDocSnapshot({}, exists=False)


class _FakeCollection:
    def __init__(self, doc_ref=None):
        self._doc_ref = doc_ref or _FakeDocRef()

    def document(self, doc_id):
        return self._doc_ref

    def where(self, *args, **kwargs):
        return self


class _FakeUserRef:
    def __init__(self, collection):
        self._collection = collection

    def collection(self, name):
        return self._collection


def test_record_llm_usage_sanitizes_model_with_dots():
    """Test that model names with dots are sanitized."""
    doc_ref = _FakeDocRef()
    collection = _FakeCollection(doc_ref)
    user_ref = _FakeUserRef(collection)

    # Patch the db used by llm_usage module
    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value = user_ref

        llm_usage.record_llm_usage(
            uid="test-user",
            feature="chat",
            model="gpt-4.1-mini",
            input_tokens=100,
            output_tokens=50,
        )

    assert len(doc_ref.set_calls) == 1
    call = doc_ref.set_calls[0]
    assert call["merge"] is True
    # Check that '.' is replaced with '_'
    assert "chat.gpt-4_1-mini.input_tokens" in call["data"]
    assert "chat.gpt-4_1-mini.output_tokens" in call["data"]


def test_record_llm_usage_sanitizes_model_with_slash():
    """Test that model names with slashes are sanitized (e.g., google/gemini-flash-1.5-8b)."""
    doc_ref = _FakeDocRef()
    collection = _FakeCollection(doc_ref)
    user_ref = _FakeUserRef(collection)

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value = user_ref

        llm_usage.record_llm_usage(
            uid="test-user",
            feature="chat",
            model="google/gemini-flash-1.5-8b",
            input_tokens=200,
            output_tokens=100,
        )

    assert len(doc_ref.set_calls) == 1
    call = doc_ref.set_calls[0]
    assert call["merge"] is True
    # Check that both '/' and '.' are replaced with '_'
    assert "chat.google_gemini-flash-1_5-8b.input_tokens" in call["data"]
    assert "chat.google_gemini-flash-1_5-8b.output_tokens" in call["data"]


def test_record_llm_usage_skips_zero_tokens():
    """Test that zero token usage is not recorded."""
    doc_ref = _FakeDocRef()

    with patch.object(llm_usage, 'db') as patched_db:
        llm_usage.record_llm_usage(
            uid="test-user",
            feature="chat",
            model="gpt-4.1-mini",
            input_tokens=0,
            output_tokens=0,
        )

    assert len(doc_ref.set_calls) == 0


def test_get_daily_usage_returns_empty_when_not_exists():
    """Test that get_daily_usage returns empty dict when no data exists."""
    mock_doc = _FakeDocSnapshot({}, exists=False)
    doc_ref = MagicMock()
    doc_ref.get.return_value = mock_doc

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

        result = llm_usage.get_daily_usage("test-user")

    assert result == {}


def test_get_daily_usage_returns_data_when_exists():
    """Test that get_daily_usage returns data when it exists."""
    expected_data = {
        "chat": {"gpt-4_1-mini": {"input_tokens": 100, "output_tokens": 50}},
        "last_updated": "2026-01-27T00:00:00Z",
    }
    mock_doc = _FakeDocSnapshot(expected_data, exists=True)
    doc_ref = MagicMock()
    doc_ref.get.return_value = mock_doc

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

        result = llm_usage.get_daily_usage("test-user")

    assert result == expected_data


def test_get_top_features_returns_sorted_list():
    """Test that get_top_features returns features sorted by total tokens."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
                "rag": {"gpt-4": {"input_tokens": 500, "output_tokens": 200, "call_count": 10}},
                "last_updated": "2026-01-27T00:00:00Z",
                "date": "2026-01-27",
            }
        )
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = iter(
            mock_docs
        )

        result = llm_usage.get_top_features("test-user", days=30, limit=2)

    assert len(result) == 2
    # RAG should be first (700 total tokens vs 150)
    assert result[0]["feature"] == "rag"
    assert result[0]["total_tokens"] == 700
    assert result[1]["feature"] == "chat"
    assert result[1]["total_tokens"] == 150


def test_record_llm_usage_sanitizes_all_special_chars():
    """Test that all Firestore-disallowed characters are sanitized: . / ~ * [ ] `."""
    doc_ref = _FakeDocRef()
    collection = _FakeCollection(doc_ref)
    user_ref = _FakeUserRef(collection)

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value = user_ref

        llm_usage.record_llm_usage(
            uid="test-user",
            feature="chat",
            model="foo/bar~baz*qux[quux]corge`grault.garply",
            input_tokens=10,
            output_tokens=5,
        )

    assert len(doc_ref.set_calls) == 1
    call = doc_ref.set_calls[0]
    # All special chars should be replaced with '_'
    assert "chat.foo_bar_baz_qux_quux_corge_grault_garply.input_tokens" in call["data"]


def test_record_llm_usage_nonzero_input_only():
    """Test that usage is recorded when only input tokens are non-zero."""
    doc_ref = _FakeDocRef()
    collection = _FakeCollection(doc_ref)
    user_ref = _FakeUserRef(collection)

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value = user_ref

        llm_usage.record_llm_usage(
            uid="test-user",
            feature="rag",
            model="gpt-4",
            input_tokens=100,
            output_tokens=0,
        )

    assert len(doc_ref.set_calls) == 1


def test_record_llm_usage_nonzero_output_only():
    """Test that usage is recorded when only output tokens are non-zero."""
    doc_ref = _FakeDocRef()
    collection = _FakeCollection(doc_ref)
    user_ref = _FakeUserRef(collection)

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value = user_ref

        llm_usage.record_llm_usage(
            uid="test-user",
            feature="rag",
            model="gpt-4",
            input_tokens=0,
            output_tokens=50,
        )

    assert len(doc_ref.set_calls) == 1


def test_get_top_features_limit_boundary_exact():
    """Test get_top_features with limit=1 returns exactly one feature."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
                "rag": {"gpt-4": {"input_tokens": 500, "output_tokens": 200, "call_count": 10}},
                "date": "2026-01-27",
            }
        )
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = iter(
            mock_docs
        )

        result = llm_usage.get_top_features("test-user", days=30, limit=1)

    assert len(result) == 1
    assert result[0]["feature"] == "rag"


def test_get_top_features_limit_exceeds_available():
    """Test get_top_features when limit > number of features returns all features."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
                "date": "2026-01-27",
            }
        )
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = iter(
            mock_docs
        )

        result = llm_usage.get_top_features("test-user", days=30, limit=10)

    assert len(result) == 1
    assert result[0]["feature"] == "chat"


def test_get_top_features_no_data_returns_empty():
    """Test get_top_features returns empty list when no usage data exists."""
    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = iter(
            []
        )

        result = llm_usage.get_top_features("test-user", days=30, limit=3)

    assert result == []


def test_get_usage_summary_aggregates_multiple_days():
    """Test that get_usage_summary aggregates data across multiple days."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
                "date": "2026-01-26",
            }
        ),
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 200, "output_tokens": 100, "call_count": 10}},
                "date": "2026-01-27",
            }
        ),
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = iter(
            mock_docs
        )

        result = llm_usage.get_usage_summary("test-user", days=30)

    assert "chat" in result
    assert result["chat"]["input_tokens"] == 300
    assert result["chat"]["output_tokens"] == 150
    assert result["chat"]["call_count"] == 15


def test_get_usage_summary_aggregates_multiple_models():
    """Test that get_usage_summary aggregates usage from different models within same feature."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {
                    "gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5},
                    "gpt-3_5": {"input_tokens": 200, "output_tokens": 80, "call_count": 20},
                },
                "date": "2026-01-27",
            }
        ),
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = iter(
            mock_docs
        )

        result = llm_usage.get_usage_summary("test-user", days=30)

    assert result["chat"]["input_tokens"] == 300
    assert result["chat"]["output_tokens"] == 130
    assert result["chat"]["call_count"] == 25


def test_get_usage_summary_skips_date_field():
    """Test that get_usage_summary does not include 'date' as a feature."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
                "date": "2026-01-27",
                "last_updated": "2026-01-27T12:00:00Z",
            }
        ),
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value.stream.return_value = iter(
            mock_docs
        )

        result = llm_usage.get_usage_summary("test-user", days=30)

    assert "date" not in result
    assert "last_updated" not in result
    assert "chat" in result


def test_get_global_top_features_aggregates_across_users():
    """Test that get_global_top_features aggregates usage across all users."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
                "date": "2026-01-27",
            }
        ),
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 200, "output_tokens": 100, "call_count": 10}},
                "rag": {"gpt-4": {"input_tokens": 50, "output_tokens": 25, "call_count": 2}},
                "date": "2026-01-27",
            }
        ),
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection_group.return_value.where.return_value.stream.return_value = iter(mock_docs)

        result = llm_usage.get_global_top_features(days=30, limit=3)

    assert len(result) == 2
    # Chat should be first (450 total vs 75)
    assert result[0]["feature"] == "chat"
    assert result[0]["total_tokens"] == 450
    assert result[1]["feature"] == "rag"
    assert result[1]["total_tokens"] == 75


def test_get_global_top_features_respects_limit():
    """Test that get_global_top_features respects the limit parameter."""
    mock_docs = [
        _FakeDocSnapshot(
            {
                "chat": {"gpt-4": {"input_tokens": 300, "output_tokens": 100, "call_count": 10}},
                "rag": {"gpt-4": {"input_tokens": 200, "output_tokens": 50, "call_count": 5}},
                "notifications": {"gpt-4": {"input_tokens": 100, "output_tokens": 20, "call_count": 2}},
                "date": "2026-01-27",
            }
        ),
    ]

    with patch.object(llm_usage, 'db') as patched_db:
        patched_db.collection_group.return_value.where.return_value.stream.return_value = iter(mock_docs)

        result = llm_usage.get_global_top_features(days=30, limit=2)

    assert len(result) == 2
    assert result[0]["feature"] == "chat"
    assert result[1]["feature"] == "rag"
