from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from jobs.l2_promotion_orchestrator import L2PromotionOrchestratorConfig
from jobs.l2_promotion_worker import L2PromotionWorkerConfig, run_l2_promotion_worker

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _candidate(uid: str, session_id: str, l1_item_id: str) -> dict:
    return {
        'uid': uid,
        'session_id': session_id,
        'l1_item_id': l1_item_id,
        'content': 'User uses Warp daily.',
        'created_at': (_NOW - timedelta(hours=2)).isoformat(),
        'session_status': 'completed',
        'session_completed_at': (_NOW - timedelta(hours=1)).isoformat(),
    }


def test_run_l2_promotion_worker_requires_run_id():
    config = L2PromotionWorkerConfig(orchestrator=L2PromotionOrchestratorConfig(whitelisted_uids={'uid-1'}))
    with pytest.raises(ValueError, match='run_id is required'):
        run_l2_promotion_worker(
            run_id='',
            config=config,
            candidate_fetcher=lambda uid, mode, limit: [],
            l1_item_fetcher=lambda uid, ids: [],
        )


def test_backfill_mode_requires_enable_backfill():
    with pytest.raises(ValueError, match='enable_backfill'):
        L2PromotionOrchestratorConfig(mode='backfill', enable_backfill=False)


def test_per_item_failure_is_reported_without_stopping_worker():
    config = L2PromotionWorkerConfig(orchestrator=L2PromotionOrchestratorConfig(whitelisted_uids={'uid-1', 'uid-2'}))

    def candidate_fetcher(uid, mode, limit):
        if uid == 'uid-1':
            return [_candidate('uid-1', 's1', 'l1')]
        return [_candidate('uid-2', 's2', 'l2')]

    def l1_item_fetcher(uid, ids):
        if uid == 'uid-1':
            raise RuntimeError('boom')
        return [{'id': ids[0], 'content': 'fact'}]

    bundle = {'uid': 'uid-2', 'session_ids': ['s2'], 'l1_items': []}
    with patch(
        'jobs.l2_promotion_worker.build_promotion_bundle', return_value=MagicMock(to_dict=lambda: bundle)
    ), patch('jobs.l2_promotion_worker.enforce_grounded_promotion_bundle', return_value={'ok': True}), patch(
        'jobs.l2_promotion_worker.run_l2_promotion_agent', return_value={'promoted': True}
    ):
        report = run_l2_promotion_worker(
            run_id='run-1',
            config=config,
            candidate_fetcher=candidate_fetcher,
            l1_item_fetcher=l1_item_fetcher,
            llm=MagicMock(),
        )

    assert report.schema_version == 'l2_promotion_worker_report.v1'
    assert report.run_id == 'run-1'
    assert len(report.errors) == 1
    assert report.errors[0]['error_type'] == 'RuntimeError'
    assert len(report.traces) == 1
    assert report.trace_count == 1
