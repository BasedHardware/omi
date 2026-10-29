from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from database.candidate_integration_outbox import (
    abandon_candidate_integration_dispatch,
    claim_candidate_integration_dispatch,
    complete_candidate_integration_dispatch,
    dead_letter_malformed_candidate_integration,
    list_candidate_integration_dispatches,
    list_candidate_integration_sweep_rows,
    note_candidate_integration_provider_attempt,
    redrive_candidate_integration_dead_letter,
    refresh_candidate_integration_lease,
)


class _MockSnapshot:
    def __init__(self, data: dict[str, Any] | None, exists: bool = True):
        self._data = data or {}
        self.exists = exists
        self.reference = MagicMock()

    def to_dict(self) -> dict[str, Any]:
        return self._data


def _build_mock_client() -> MagicMock:
    client = MagicMock()
    users_col = MagicMock()
    user_doc = MagicMock()
    outbox_col = MagicMock()
    outbox_doc = MagicMock()
    ctrl_col = MagicMock()
    ctrl_doc = MagicMock()

    client.collection.return_value = users_col
    users_col.document.return_value = user_doc

    def _col_side_effect(name: str) -> MagicMock:
        if name == "candidate_integration_outbox":
            return outbox_col
        if name in ("task_workflow_control", "task_intelligence_control"):
            return ctrl_col
        return MagicMock()

    user_doc.collection.side_effect = _col_side_effect
    outbox_col.document.return_value = outbox_doc
    ctrl_col.document.return_value = ctrl_doc

    return client


def test_candidate_integration_outbox_id_validation() -> None:
    client = _build_mock_client()
    invalid_ids = ["", "   ", "bad/slash", "bad\\backslash", "bad..traversal", "bad\x00null", "x" * 150, 999, None]

    for bad_id in invalid_ids:
        with pytest.raises(ValueError):
            claim_candidate_integration_dispatch(
                bad_id, "cand1", account_generation=1, firestore_client=client  # type: ignore[arg-type]
            )

        with pytest.raises(ValueError):
            claim_candidate_integration_dispatch(
                "u1", bad_id, account_generation=1, firestore_client=client  # type: ignore[arg-type]
            )

        with pytest.raises(ValueError):
            refresh_candidate_integration_lease(
                bad_id, "cand1", lease_token="tok", firestore_client=client  # type: ignore[arg-type]
            )

        with pytest.raises(ValueError):
            abandon_candidate_integration_dispatch(
                "u1", bad_id, reason="in_doubt", firestore_client=client  # type: ignore[arg-type]
            )


def test_claim_candidate_integration_dispatch_naive_datetime_alignment() -> None:
    client = _build_mock_client()
    outbox_doc = client.collection().document().collection("candidate_integration_outbox").document()
    ctrl_doc = client.collection().document().collection("task_workflow_control").document()

    # Naive datetime from legacy snapshot
    naive_claimed_at = datetime(2026, 10, 29, 12, 0, 0)
    outbox_doc.get.return_value = _MockSnapshot(
        {
            "status": "processing",
            "account_generation": 1,
            "claimed_at": naive_claimed_at,
            "attempt_count": 1,
        }
    )
    ctrl_doc.get.return_value = _MockSnapshot({"account_generation": 1})

    # Aware datetime comparison in claim_time
    aware_now = datetime(2026, 10, 29, 12, 2, 0, tzinfo=timezone.utc)
    token = claim_candidate_integration_dispatch(
        "u1",
        "cand1",
        account_generation=1,
        now=aware_now,
        lease_seconds=300,
        firestore_client=client,
    )
    # Should not crash with TypeError and should report live lease (None token)
    assert token is None


def test_list_candidate_integration_dispatches_naive_available_at_alignment() -> None:
    client = _build_mock_client()
    users_col = client.collection("users")
    user_doc = users_col.document("u1")
    outbox_col = user_doc.collection("candidate_integration_outbox")
    query_mock = MagicMock()
    outbox_col.where.return_value.where.return_value.limit.return_value = query_mock

    # Naive available_at in the future
    naive_future = datetime(2030, 1, 1, 0, 0, 0)
    query_mock.stream.return_value = [_MockSnapshot({"available_at": naive_future, "status": "failed"})]

    rows = list_candidate_integration_dispatches(
        "u1", account_generation=1, firestore_client=client
    )
    assert rows == []


def test_parameter_clamping_lease_and_limit() -> None:
    client = _build_mock_client()

    # Reject non-positive or bool limits
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        list_candidate_integration_dispatches("u1", account_generation=1, limit=0, firestore_client=client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        list_candidate_integration_dispatches("u1", account_generation=1, limit=-5, firestore_client=client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        list_candidate_integration_dispatches(
            "u1", account_generation=1, limit=True, firestore_client=client  # type: ignore[arg-type]
        )


def test_client_injection_on_redrive_and_dead_letter() -> None:
    client = _build_mock_client()
    outbox_doc = client.collection().document().collection("candidate_integration_outbox").document()
    outbox_doc.get.return_value = _MockSnapshot({"status": "dead_letter", "account_generation": 1})

    res = redrive_candidate_integration_dead_letter(
        "u1", "cand1", account_generation=1, firestore_client=client
    )
    assert res is True

    outbox_doc.get.return_value = _MockSnapshot({"status": "pending", "account_generation": 1})
    res_dead = dead_letter_malformed_candidate_integration(
        "u1", "cand1", account_generation=1, error_text="bad payload", firestore_client=client
    )
    assert res_dead is True
