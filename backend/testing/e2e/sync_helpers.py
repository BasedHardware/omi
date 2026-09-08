"""Shared helpers for hermetic sync v2 e2e coverage."""

from __future__ import annotations

import time

from utils.sync.lanes import CaptureTimeTrust, SyncLane, SyncLaneDecision


def patch_fresh_sync_lane(monkeypatch) -> None:
    """Force sync uploads onto the fresh inline lane for pipeline-focused e2e tests."""
    import routers.sync as sync_router

    now = time.time()

    def _fresh_lane_decision(*_args, **_kwargs) -> SyncLaneDecision:
        return SyncLaneDecision(
            lane=SyncLane.FRESH,
            trust=CaptureTimeTrust.LEGACY,
            reason='e2e_forced_fresh',
            oldest_capture_at=now - 60,
            newest_capture_at=now - 60,
            maximum_age_seconds=60,
        )

    monkeypatch.setattr(sync_router, 'classify_sync_lane', _fresh_lane_decision)
