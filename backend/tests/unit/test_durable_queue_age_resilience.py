"""Unit tests for database durable_queue_age sampling, error boundaries, and resilience."""

from datetime import datetime, timezone
import math
from unittest.mock import MagicMock, patch
import pytest

from database.durable_queue_age import (
    QUEUE_AGE_SAMPLERS,
    _created_ats_from_page,
    _parse_created_at,
    _sample_status_page,
    publish_all_queue_oldest_ready_ages,
    sample_store_wide_oldest_ready_ages,
)


class TestDurableQueueAgeParsing:
    """Tests for timestamp parsing and boundary normalization."""

    def test_parse_created_at_datetime(self):
        # Aware datetime
        aware = datetime(2026, 9, 30, 8, 0, 0, tzinfo=timezone.utc)
        assert _parse_created_at(aware) == aware

        # Naive datetime normalized to UTC
        naive = datetime(2026, 9, 30, 8, 0, 0)
        parsed = _parse_created_at(naive)
        assert parsed is not None
        assert parsed.tzinfo == timezone.utc
        assert parsed.year == 2026 and parsed.hour == 8

    def test_parse_created_at_iso_string(self):
        # Valid ISO strings with Z and offset
        res1 = _parse_created_at("2026-09-30T08:00:00Z")
        assert res1 is not None and res1.tzinfo is not None
        assert res1.hour == 8

        res2 = _parse_created_at("2026-09-30T08:00:00+00:00")
        assert res2 is not None and res2.tzinfo is not None

        # Whitespace
        res3 = _parse_created_at("  2026-09-30T08:00:00Z  ")
        assert res3 is not None

        # Invalid strings
        assert _parse_created_at("invalid-date") is None
        assert _parse_created_at("") is None
        assert _parse_created_at("   ") is None

    def test_parse_created_at_numeric_epoch(self):
        # Numeric epoch timestamps
        ts = 1759200000.0
        parsed = _parse_created_at(ts)
        assert parsed is not None and parsed.tzinfo == timezone.utc

        parsed_int = _parse_created_at(1759200000)
        assert parsed_int is not None

        # Bools, NaNs, Infs, and negatives
        assert _parse_created_at(True) is None
        assert _parse_created_at(False) is None
        assert _parse_created_at(float("nan")) is None
        assert _parse_created_at(float("inf")) is None
        assert _parse_created_at(-100) is None
        assert _parse_created_at(0) is None
        assert _parse_created_at(None) is None


class TestDurableQueueAgePageSampling:
    """Tests for snapshot extraction and query pagination."""

    def test_created_ats_from_page_basic(self):
        class FakeSnap:
            def __init__(self, data):
                self._data = data

            def to_dict(self):
                return self._data

        t1 = datetime(2026, 9, 30, 8, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 30, 8, 5, 0, tzinfo=timezone.utc)

        snaps = [
            FakeSnap({"created_at": t1}),
            FakeSnap({"created_at": t2}),
            FakeSnap({"created_at": "not-a-date"}),
            FakeSnap("not-a-dict"),
        ]

        res = _created_ats_from_page(snaps, created_at_field="created_at")
        assert len(res) == 2
        assert res[0] == t1
        assert res[1] == t2

    def test_created_ats_from_page_with_event_type(self):
        t1 = datetime(2026, 9, 30, 8, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 30, 8, 1, 0, tzinfo=timezone.utc)

        snaps = [
            {"created_at": t1, "event_type": "vector_repair_purge"},
            {"created_at": t2, "event_type": "other_event"},
        ]

        res = _created_ats_from_page(snaps, created_at_field="created_at", event_type="vector_repair_purge")
        assert len(res) == 1
        assert res[0] == t1

    def test_created_ats_from_page_handles_exceptions(self):
        assert _created_ats_from_page(None, created_at_field="created_at") == []

        class BrokenSnap:
            def to_dict(self):
                raise RuntimeError("Failed to deserialize")

        res = _created_ats_from_page([BrokenSnap()], created_at_field="created_at")
        assert res == []

    def test_sample_status_page_null_or_missing_client(self):
        spec = QUEUE_AGE_SAMPLERS["memory_outbox"]
        with pytest.raises(Exception):
            _sample_status_page(None, spec)
        with pytest.raises(Exception):
            _sample_status_page(object(), spec)

    def test_sample_status_page_query_with_statuses(self):
        mock_client = MagicMock()
        mock_query = MagicMock()
        t1 = datetime(2026, 9, 30, 8, 0, 0, tzinfo=timezone.utc)
        mock_query.stream.return_value = [{"created_at": t1}]
        mock_client.collection_group.return_value.where.return_value.limit.return_value = mock_query

        spec = {
            "collection": "test_queue",
            "status_field": "status",
            "ready_statuses": ("pending", "retryable"),
            "created_at_field": "created_at",
        }
        res = _sample_status_page(mock_client, spec, page_size=50)
        assert len(res) == 2  # Once for each status
        assert res[0] == t1
        mock_client.collection_group.assert_called_with("test_queue")

    def test_sample_status_page_exception_fallbacks(self):
        mock_client = MagicMock()
        mock_client.collection_group.side_effect = RuntimeError("Firestore unavailable")
        spec = QUEUE_AGE_SAMPLERS["memory_outbox"]
        with pytest.raises(RuntimeError):
            _sample_status_page(mock_client, spec)

    def test_sampler_failure_leaves_the_queue_absent(self):
        class _Boom:
            def collection_group(self, _name: str):
                raise RuntimeError("firestore unavailable")

        now = datetime(2026, 9, 30, 8, 10, 0, tzinfo=timezone.utc)
        ages = sample_store_wide_oldest_ready_ages(
            now=now,
            firestore_client=_Boom(),
            finalization_summary={"oldest_nonterminal_age_seconds": 1},
        )
        assert "memory_outbox" not in ages
        assert ages["daily_memory_sweep"] == 0.0
        assert ages["conversation_finalization_jobs"] == 1.0


class TestStoreWideSamplingResilience:
    """Tests for sample_store_wide_oldest_ready_ages logic and metrics publishing."""

    def test_ephemeral_queues_return_zero_without_client(self):
        ages = sample_store_wide_oldest_ready_ages(firestore_client=None)
        # Ephemeral queues must always be 0.0 even without firestore_client
        assert ages.get("daily_summary_hour_groups") == 0.0
        assert ages.get("daily_memory_sweep") == 0.0

    def test_summary_queue_handling(self):
        # Summary missing -> absent from ages
        ages1 = sample_store_wide_oldest_ready_ages(firestore_client=None, finalization_summary=None)
        assert "conversation_finalization_jobs" not in ages1

        # Summary present with valid float
        summary = {"oldest_nonterminal_age_seconds": 45.5}
        ages2 = sample_store_wide_oldest_ready_ages(firestore_client=None, finalization_summary=summary)
        assert ages2.get("conversation_finalization_jobs") == 45.5

        # Summary present with invalid types (bool, negative, NaN, string) safely handled
        summary_invalid = {"oldest_nonterminal_age_seconds": True}
        ages3 = sample_store_wide_oldest_ready_ages(firestore_client=None, finalization_summary=summary_invalid)
        assert ages3.get("conversation_finalization_jobs") == 0.0

        summary_nan = {"oldest_nonterminal_age_seconds": float("nan")}
        ages4 = sample_store_wide_oldest_ready_ages(firestore_client=None, finalization_summary=summary_nan)
        assert ages4.get("conversation_finalization_jobs") == 0.0

        summary_negative = {"oldest_nonterminal_age_seconds": -15.0}
        ages5 = sample_store_wide_oldest_ready_ages(firestore_client=None, finalization_summary=summary_negative)
        assert ages5.get("conversation_finalization_jobs") == 0.0

    def test_sampling_calculates_oldest_ready_age(self):
        now = datetime(2026, 9, 30, 8, 10, 0, tzinfo=timezone.utc)
        item_time = datetime(2026, 9, 30, 8, 0, 0, tzinfo=timezone.utc)

        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_query.stream.return_value = [{"created_at": item_time}]
        mock_client.collection_group.return_value.where.return_value.limit.return_value = mock_query
        mock_client.collection_group.return_value.limit.return_value = mock_query

        ages = sample_store_wide_oldest_ready_ages(now=now, firestore_client=mock_client)
        # 8:10 - 8:00 = 600.0s
        assert ages.get("memory_outbox") == 600.0

    def test_publish_all_queue_handles_import_or_publish_error(self):
        # When publish_sampled_queue_oldest_ready_ages throws or is missing, must not crash
        with patch(
            "utils.durable_queue_metrics.publish_sampled_queue_oldest_ready_ages",
            side_effect=RuntimeError("Metric sink down"),
        ):
            publish_all_queue_oldest_ready_ages(firestore_client=None)
