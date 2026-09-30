from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from database.durable_queue_age import (
    QUEUE_AGE_SAMPLERS,
    _created_ats_from_page,
    _sample_status_page,
    publish_all_queue_oldest_ready_ages,
    sample_store_wide_oldest_ready_ages,
)


class TestDurableQueueAge(unittest.TestCase):
    def test_created_ats_from_page_with_snapshots(self) -> None:
        t1 = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 30, 10, 5, 0, tzinfo=timezone.utc)

        mock_snap1 = MagicMock()
        mock_snap1.to_dict.return_value = {"created_at": t1, "event_type": "vector_repair_purge"}

        mock_snap2 = MagicMock()
        mock_snap2.to_dict.return_value = {"created_at": t2, "event_type": "other"}

        mock_snap3 = MagicMock()
        mock_snap3.to_dict.return_value = "not-a-dict"

        # Filter by event_type
        res_filtered = _created_ats_from_page(
            [mock_snap1, mock_snap2, mock_snap3],
            created_at_field="created_at",
            event_type="vector_repair_purge",
        )
        self.assertEqual(res_filtered, [t1])

        # Without event_type filter
        res_unfiltered = _created_ats_from_page(
            [mock_snap1, mock_snap2],
            created_at_field="created_at",
        )
        self.assertEqual(res_unfiltered, [t1, t2])

    def test_sample_status_page_with_status_field(self) -> None:
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.collection_group.return_value.where.return_value.limit.return_value = mock_query

        t = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
        snap = MagicMock()
        snap.to_dict.return_value = {"created_at": t}
        mock_query.stream.return_value = [snap]

        spec = {
            "collection": "test_collection",
            "created_at_field": "created_at",
            "status_field": "status",
            "ready_statuses": ("pending", "retryable_failure"),
        }
        res = _sample_status_page(mock_client, spec)
        # 2 statuses queried, each returning [t] -> total 2 items
        self.assertEqual(len(res), 2)
        self.assertEqual(res, [t, t])

    def test_sample_status_page_without_status_field(self) -> None:
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.collection_group.return_value.limit.return_value = mock_query

        t = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
        snap = MagicMock()
        snap.to_dict.return_value = {"created_at": t}
        mock_query.stream.return_value = [snap]

        spec = {
            "collection": "frame_deletion_outbox",
            "created_at_field": "created_at",
            "status_field": None,
            "ready_statuses": (),
        }
        res = _sample_status_page(mock_client, spec)
        self.assertEqual(res, [t])

    def test_sample_store_wide_oldest_ready_ages(self) -> None:
        now = datetime(2026, 9, 30, 12, 10, 0, tzinfo=timezone.utc)
        t_item = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)  # 600s ago

        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.collection_group.return_value.where.return_value.limit.return_value = mock_query
        mock_client.collection_group.return_value.limit.return_value = mock_query

        snap = MagicMock()
        snap.to_dict.return_value = {"created_at": t_item}
        mock_query.stream.return_value = [snap]

        summary = {"oldest_nonterminal_age_seconds": 123.45}
        ages = sample_store_wide_oldest_ready_ages(
            now=now,
            firestore_client=mock_client,
            finalization_summary=summary,
        )

        self.assertIn("memory_outbox", ages)
        self.assertIn("daily_summary_hour_groups", ages)
        self.assertEqual(ages["daily_summary_hour_groups"], 0.0)
        self.assertEqual(ages["conversation_finalization_jobs"], 123.45)
        # Check computed age ~ 600 seconds
        self.assertAlmostEqual(ages["memory_outbox"], 600.0, delta=1.0)

    @patch("utils.durable_queue_metrics.publish_sampled_queue_oldest_ready_ages")
    def test_publish_all_queue_oldest_ready_ages(self, mock_publish: MagicMock) -> None:
        mock_client = MagicMock()
        publish_all_queue_oldest_ready_ages(
            firestore_client=mock_client,
            finalization_summary={"oldest_nonterminal_age_seconds": 50.0},
        )
        mock_publish.assert_called_once()
        args, _ = mock_publish.call_args
        self.assertIsInstance(args[0], dict)


if __name__ == "__main__":
    unittest.main()
