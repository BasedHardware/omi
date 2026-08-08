"""Behavioral tests for ``database.llm_usage`` over the neutral storage port (WP2, ADR-0002).

Before the storage-port migration this module talked to the raw Firestore client. These tests drive
the *real* functions through a ``FakeDocumentStore`` injected at the ``_store`` seam, asserting on
returned values and stored state (including the collection-group ``get_global_top_features`` path).
"""

from datetime import datetime, timezone

import pytest

import database.llm_usage as llm_usage
from tests.store_fakes import FakeDocumentStore


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(llm_usage, "_store", lambda: fake)
    return fake


def _today_id() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}-{now.day:02d}"


# ---------------------------------------------------------------------------
# record_llm_usage — model-name sanitization + zero-token short circuit
# ---------------------------------------------------------------------------


def test_record_llm_usage_sanitizes_model_with_dots(store):
    """Model names with dots are sanitized before use as nested field keys."""
    llm_usage.record_llm_usage(
        uid="test-user", feature="chat", model="gpt-4.1-mini", input_tokens=100, output_tokens=50
    )

    data = store.get(f"users/test-user/llm_usage/{_today_id()}").to_dict()
    assert data["chat"]["gpt-4_1-mini"]["input_tokens"] == 100
    assert data["chat"]["gpt-4_1-mini"]["output_tokens"] == 50


def test_record_llm_usage_sanitizes_model_with_slash(store):
    """Model names with slashes are sanitized (e.g., google/gemini-flash-1.5-8b)."""
    llm_usage.record_llm_usage(
        uid="test-user",
        feature="chat",
        model="google/gemini-flash-1.5-8b",
        input_tokens=200,
        output_tokens=100,
    )

    data = store.get(f"users/test-user/llm_usage/{_today_id()}").to_dict()
    assert data["chat"]["google_gemini-flash-1_5-8b"]["input_tokens"] == 200
    assert data["chat"]["google_gemini-flash-1_5-8b"]["output_tokens"] == 100


def test_record_llm_usage_sanitizes_all_special_chars(store):
    """All Firestore-disallowed characters are sanitized: . / ~ * [ ] `."""
    llm_usage.record_llm_usage(
        uid="test-user",
        feature="chat",
        model="foo/bar~baz*qux[quux]corge`grault.garply",
        input_tokens=10,
        output_tokens=5,
    )

    data = store.get(f"users/test-user/llm_usage/{_today_id()}").to_dict()
    assert "foo_bar_baz_qux_quux_corge_grault_garply" in data["chat"]


def test_record_llm_usage_skips_zero_tokens(store):
    """Zero token usage is not recorded (no document written)."""
    llm_usage.record_llm_usage(
        uid="test-user", feature="chat", model="gpt-4.1-mini", input_tokens=0, output_tokens=0
    )

    assert store._docs == {}


def test_record_llm_usage_nonzero_input_only(store):
    """Usage is recorded when only input tokens are non-zero."""
    llm_usage.record_llm_usage(
        uid="test-user", feature="rag", model="gpt-4", input_tokens=100, output_tokens=0
    )

    data = store.get(f"users/test-user/llm_usage/{_today_id()}").to_dict()
    assert data["rag"]["gpt-4"]["input_tokens"] == 100


def test_record_llm_usage_nonzero_output_only(store):
    """Usage is recorded when only output tokens are non-zero."""
    llm_usage.record_llm_usage(
        uid="test-user", feature="rag", model="gpt-4", input_tokens=0, output_tokens=50
    )

    data = store.get(f"users/test-user/llm_usage/{_today_id()}").to_dict()
    assert data["rag"]["gpt-4"]["output_tokens"] == 50


def test_record_llm_usage_increments_accumulate(store):
    """Repeated records atomically accumulate via neutral Increment sentinels."""
    for _ in range(3):
        llm_usage.record_llm_usage(
            uid="u1", feature="chat", model="gpt-4", input_tokens=10, output_tokens=5
        )

    data = store.get(f"users/u1/llm_usage/{_today_id()}").to_dict()
    assert data["chat"]["gpt-4"]["input_tokens"] == 30
    assert data["chat"]["gpt-4"]["output_tokens"] == 15
    assert data["chat"]["gpt-4"]["call_count"] == 3


# ---------------------------------------------------------------------------
# get_daily_usage
# ---------------------------------------------------------------------------


def test_get_daily_usage_returns_empty_when_not_exists(store):
    assert llm_usage.get_daily_usage("test-user") == {}


def test_get_daily_usage_returns_data_when_exists(store):
    expected_data = {
        "chat": {"gpt-4_1-mini": {"input_tokens": 100, "output_tokens": 50}},
        "last_updated": "2026-01-27T00:00:00Z",
    }
    store.set(f"users/test-user/llm_usage/{_today_id()}", expected_data)

    assert llm_usage.get_daily_usage("test-user") == expected_data


# ---------------------------------------------------------------------------
# get_top_features / get_usage_summary
# ---------------------------------------------------------------------------


def test_get_top_features_returns_sorted_list(store):
    store.set(
        f"users/test-user/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
            "rag": {"gpt-4": {"input_tokens": 500, "output_tokens": 200, "call_count": 10}},
            "last_updated": "2026-01-27T00:00:00Z",
            "date": _today_id(),
        },
    )

    result = llm_usage.get_top_features("test-user", days=30, limit=2)

    assert len(result) == 2
    # RAG should be first (700 total tokens vs 150)
    assert result[0]["feature"] == "rag"
    assert result[0]["total_tokens"] == 700
    assert result[1]["feature"] == "chat"
    assert result[1]["total_tokens"] == 150


def test_get_top_features_limit_boundary_exact(store):
    store.set(
        f"users/test-user/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
            "rag": {"gpt-4": {"input_tokens": 500, "output_tokens": 200, "call_count": 10}},
            "date": _today_id(),
        },
    )

    result = llm_usage.get_top_features("test-user", days=30, limit=1)

    assert len(result) == 1
    assert result[0]["feature"] == "rag"


def test_get_top_features_limit_exceeds_available(store):
    store.set(
        f"users/test-user/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
            "date": _today_id(),
        },
    )

    result = llm_usage.get_top_features("test-user", days=30, limit=10)

    assert len(result) == 1
    assert result[0]["feature"] == "chat"


def test_get_top_features_no_data_returns_empty(store):
    result = llm_usage.get_top_features("test-user", days=30, limit=3)
    assert result == []


def test_get_usage_summary_aggregates_multiple_days(store):
    store.set(
        "users/test-user/llm_usage/day-a",
        {
            "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
            "date": _today_id(),
        },
    )
    store.set(
        "users/test-user/llm_usage/day-b",
        {
            "chat": {"gpt-4": {"input_tokens": 200, "output_tokens": 100, "call_count": 10}},
            "date": _today_id(),
        },
    )

    result = llm_usage.get_usage_summary("test-user", days=30)

    assert result["chat"]["input_tokens"] == 300
    assert result["chat"]["output_tokens"] == 150
    assert result["chat"]["call_count"] == 15


def test_get_usage_summary_aggregates_multiple_models(store):
    store.set(
        f"users/test-user/llm_usage/{_today_id()}",
        {
            "chat": {
                "gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5},
                "gpt-3_5": {"input_tokens": 200, "output_tokens": 80, "call_count": 20},
            },
            "date": _today_id(),
        },
    )

    result = llm_usage.get_usage_summary("test-user", days=30)

    assert result["chat"]["input_tokens"] == 300
    assert result["chat"]["output_tokens"] == 130
    assert result["chat"]["call_count"] == 25


def test_get_usage_summary_skips_date_field(store):
    store.set(
        f"users/test-user/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
            "date": _today_id(),
            "last_updated": "2026-01-27T12:00:00Z",
        },
    )

    result = llm_usage.get_usage_summary("test-user", days=30)

    assert "date" not in result
    assert "last_updated" not in result
    assert "chat" in result


def test_get_usage_summary_excludes_docs_before_cutoff(store):
    """The date-field filter excludes documents older than the cutoff window."""
    store.set(
        "users/test-user/llm_usage/old",
        {
            "chat": {"gpt-4": {"input_tokens": 999, "output_tokens": 999, "call_count": 9}},
            "date": "2000-01-01",
        },
    )
    store.set(
        f"users/test-user/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 10, "output_tokens": 5, "call_count": 1}},
            "date": _today_id(),
        },
    )

    result = llm_usage.get_usage_summary("test-user", days=30)

    assert result["chat"]["input_tokens"] == 10  # old doc excluded


# ---------------------------------------------------------------------------
# get_global_top_features (collection-group)
# ---------------------------------------------------------------------------


def test_get_global_top_features_aggregates_across_users(store):
    store.set(
        f"users/u1/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 100, "output_tokens": 50, "call_count": 5}},
            "date": _today_id(),
        },
    )
    store.set(
        f"users/u2/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 200, "output_tokens": 100, "call_count": 10}},
            "rag": {"gpt-4": {"input_tokens": 50, "output_tokens": 25, "call_count": 2}},
            "date": _today_id(),
        },
    )

    result = llm_usage.get_global_top_features(days=30, limit=3)

    assert len(result) == 2
    # Chat should be first (450 total vs 75)
    assert result[0]["feature"] == "chat"
    assert result[0]["total_tokens"] == 450
    assert result[1]["feature"] == "rag"
    assert result[1]["total_tokens"] == 75


def test_get_global_top_features_respects_limit(store):
    store.set(
        f"users/u1/llm_usage/{_today_id()}",
        {
            "chat": {"gpt-4": {"input_tokens": 300, "output_tokens": 100, "call_count": 10}},
            "rag": {"gpt-4": {"input_tokens": 200, "output_tokens": 50, "call_count": 5}},
            "notifications": {"gpt-4": {"input_tokens": 100, "output_tokens": 20, "call_count": 2}},
            "date": _today_id(),
        },
    )

    result = llm_usage.get_global_top_features(days=30, limit=2)

    assert len(result) == 2
    assert result[0]["feature"] == "chat"
    assert result[1]["feature"] == "rag"


# ---------------------------------------------------------------------------
# record_chat_quota_question (transactional idempotency) + bucket helpers
# ---------------------------------------------------------------------------


def test_record_chat_quota_question_is_idempotent(store):
    first = llm_usage.record_chat_quota_question("u1", "key-1", source="mobile")
    second = llm_usage.record_chat_quota_question("u1", "key-1", source="mobile")

    assert first is True
    assert second is False  # same idempotency key → not counted twice

    data = store.get(f"users/u1/llm_usage/{_today_id()}").to_dict()
    assert data["backend_chat"]["quota_questions"] == 1


def test_record_chat_quota_question_requires_key(store):
    with pytest.raises(ValueError):
        llm_usage.record_chat_quota_question("u1", "", source="mobile")


def test_record_llm_usage_bucket_and_total_cost(store):
    llm_usage.record_llm_usage_bucket(
        "u1", input_tokens=10, output_tokens=5, cost_usd=0.25, bucket="desktop_chat", account="omi"
    )
    llm_usage.record_llm_usage_bucket(
        "u1", input_tokens=20, output_tokens=8, cost_usd=0.75, bucket="desktop_chat", account="omi"
    )

    data = store.get(f"users/u1/llm_usage/{_today_id()}").to_dict()
    assert data["desktop_chat"]["input_tokens"] == 30
    assert data["desktop_chat"]["call_count"] == 2
    # per-account alias is dual-written
    assert data["desktop_chat_omi"]["input_tokens"] == 30

    # Only the primary bucket is summed (no double-counting with the alias).
    assert llm_usage.get_total_llm_cost("u1", bucket="desktop_chat") == 1.0
