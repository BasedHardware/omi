"""Synthetic producer rows for tests of the kept v2 ledger/budget machinery.

The production registry (`config/proactivity_v2_producers.json`) was emptied
when the mentor and commitment producers were deleted (2026-10-26). The item
ledger, Budget Authority, gateway attribution and metric verdicts remain in
production and their unit tests still need Producer rows, so tests install
these synthetic rows instead of reading the (empty) registry.
"""

from __future__ import annotations

import pytest

import config.proactivity_v2 as registry

MENTOR_V2 = {
    "name": "conversation_mentor_v2",
    "version": 1,
    "enabled": True,
    "paid_only": True,
    "signal": "conversation_revision",
    "trigger": "eligible_segment",
    "dedupe_scope": "source_id:source_revision:source_event_id",
    "max_calls_per_user_utc_day": 60,
    "max_calls_per_item": 6,
    "gateway_lane": "omi:auto:proactive-notification",
    "max_request_bytes": 32768,
    "max_output_tokens": 2048,
    "expected_micro_usd_per_delivery": 60000,
    "measurement_status": "provisional",
    "measurement_reference": "synthetic test producer",
    "min_acted_24h_rate": 0.1,
    "max_micro_usd_per_acted_item": 250000,
    "kill_min_deliveries": 200,
    "evaluation_window_days": 7,
    "push_earned": True,
    "push_evidence_reference": "synthetic",
}

COMMITMENT_FOLLOWUP = {
    "name": "commitment_followup",
    "version": 1,
    "enabled": True,
    "paid_only": True,
    "signal": "action_item_due_revision",
    "trigger": "action_item_reminder",
    "dedupe_scope": "source_id:source_revision:source_event_id",
    "max_calls_per_user_utc_day": 9,
    "max_calls_per_item": 1,
    "gateway_lane": "omi:auto:proactive-notification",
    "max_request_bytes": 8192,
    "max_output_tokens": 512,
    "expected_micro_usd_per_delivery": 2000,
    "measurement_status": "provisional",
    "measurement_reference": "synthetic test producer",
    "min_acted_24h_rate": 0.1,
    "max_micro_usd_per_acted_item": 250000,
    "kill_min_deliveries": 200,
    "evaluation_window_days": 7,
    "push_earned": False,
    "push_evidence_reference": "",
}


def install_synthetic_producers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the synthetic rows from config.proactivity_v2.producers()."""
    rows = {row["name"]: registry.Producer.model_validate(row) for row in (MENTOR_V2, COMMITMENT_FOLLOWUP)}
    monkeypatch.setattr(registry, "producers", lambda: rows)


@pytest.fixture(autouse=True)
def synthetic_producers(monkeypatch):
    install_synthetic_producers(monkeypatch)
