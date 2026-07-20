"""Batching behaviour of jobs.l2_promotion_selector.select_promotion_work_items.

The selector groups completed-session L1 candidates into bounded work items. It is a pure
function over dataclasses — no Firestore, no clock beyond the injected `now`.

The batch bounds exist to cap the size of a single promotion job, not to discard work:
every pending candidate must appear in exactly one returned work item.
"""

from datetime import datetime, timedelta, timezone

from jobs.l2_promotion_selector import (
    L1PromotionCandidate,
    PromotionSelectorConfig,
    select_promotion_work_items,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def _candidate(uid, session_id, index, created_at=None):
    return L1PromotionCandidate(
        uid=uid,
        l1_item_id=f'{session_id}-item-{index}',
        session_id=session_id,
        content=f'content {index}',
        created_at=created_at or (NOW - timedelta(hours=1)),
        session_status='completed',
    )


def _all_ids(work_items):
    return [item_id for work_item in work_items for item_id in work_item.l1_item_ids]


class TestBatching:
    def test_a_small_completed_session_becomes_one_work_item(self):
        candidates = [_candidate('u1', 's1', i) for i in range(3)]
        work_items = select_promotion_work_items(candidates, now=NOW)
        assert len(work_items) == 1
        assert work_items[0].uid == 'u1'
        assert work_items[0].session_ids == ['s1']
        assert len(work_items[0].l1_item_ids) == 3

    def test_sessions_are_split_once_the_session_cap_is_reached(self):
        cfg = PromotionSelectorConfig(max_sessions_per_batch=2)
        candidates = [_candidate('u1', f's{s}', i) for s in range(3) for i in range(2)]
        work_items = select_promotion_work_items(candidates, now=NOW, config=cfg)
        assert [len(w.session_ids) for w in work_items] == [2, 1]
        # Session overflow is carried into a new work item, never dropped.
        assert len(_all_ids(work_items)) == 6

    def test_different_users_never_share_a_work_item(self):
        candidates = [_candidate('u1', 's1', 0), _candidate('u2', 's2', 0)]
        work_items = select_promotion_work_items(candidates, now=NOW)
        assert sorted(w.uid for w in work_items) == ['u1', 'u2']

    def test_incomplete_sessions_are_not_selected(self):
        recent = L1PromotionCandidate(
            uid='u1',
            l1_item_id='fresh',
            session_id='s1',
            content='c',
            created_at=NOW,  # still inside the inactivity window, no completed marker
        )
        assert select_promotion_work_items([recent], now=NOW) == []


class TestNoCandidateIsDropped:
    def test_item_cap_splits_a_batch_across_two_sessions(self):
        cfg = PromotionSelectorConfig(max_l1_items_per_batch=4)
        candidates = [_candidate('u1', 's1', i) for i in range(3)] + [_candidate('u1', 's2', i) for i in range(3)]
        work_items = select_promotion_work_items(candidates, now=NOW, config=cfg)
        assert len(_all_ids(work_items)) == 6
        assert len(set(_all_ids(work_items))) == 6
