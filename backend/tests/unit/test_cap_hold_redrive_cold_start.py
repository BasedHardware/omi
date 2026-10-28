"""Cold-start behavior for the sampled cap-hold fleet gauge."""

from types import SimpleNamespace

import pytest

from utils.sync import cap_hold_redrive

_EMPTY_FLEET = {
    'pending_count': 0,
    'pending_seconds': 0.0,
    'oldest_listed_at': None,
    'undated_pending': 0,
    'backlog_items': 0,
}


@pytest.fixture(autouse=True)
def _reset_snapshot_gate():
    cap_hold_redrive._snapshot_gate.update(inflight=False, attempt_at=None)
    yield
    cap_hold_redrive._snapshot_gate.update(inflight=False, attempt_at=None)


async def test_fleet_snapshot_starts_before_first_interval_on_cold_process(monkeypatch):
    calls = []

    def snapshot(firestore_client=None):
        calls.append(firestore_client)
        return dict(_EMPTY_FLEET)

    monkeypatch.setattr(cap_hold_redrive, 'time', SimpleNamespace(monotonic=lambda: 30.0))
    monkeypatch.setattr(cap_hold_redrive.store, 'fleet_snapshot', snapshot)
    task = cap_hold_redrive._schedule_fleet_snapshot()
    assert task is not None
    await task
    assert calls == [None]
