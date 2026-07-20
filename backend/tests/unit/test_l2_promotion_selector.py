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

    def test_a_session_larger_than_one_batch_is_split_not_truncated(self):
        """Overflow ids must move to a new work item, not disappear.

        The selector consumed only `max_l1_items_per_batch - len(batch)` ids from a
        session and dropped the rest on the floor, so a session with more candidates
        than one batch holds silently lost the excess: those L1 items were never
        promoted to L2. Session overflow was already carried forward correctly; item
        overflow was not.
        """
        candidates = [_candidate('u1', 's1', i) for i in range(60)]
        work_items = select_promotion_work_items(candidates, now=NOW)

        emitted = _all_ids(work_items)
        assert len(emitted) == 60, f'{60 - len(emitted)} candidates were dropped'
        assert set(emitted) == {c.l1_item_id for c in candidates}
        assert len(set(emitted)) == 60, 'a candidate was emitted more than once'
        assert [len(w.l1_item_ids) for w in work_items] == [50, 10]
        assert all(w.session_ids == ['s1'] for w in work_items)

    def test_every_candidate_survives_an_awkward_split(self):
        cfg = PromotionSelectorConfig(max_l1_items_per_batch=7, max_sessions_per_batch=10)
        candidates = [_candidate('u1', 's1', i) for i in range(23)]
        work_items = select_promotion_work_items(candidates, now=NOW, config=cfg)

        emitted = _all_ids(work_items)
        assert sorted(emitted) == sorted(c.l1_item_id for c in candidates)
        assert all(len(w.l1_item_ids) <= 7 for w in work_items)

    def test_batches_never_exceed_the_item_cap_when_a_session_spans_them(self):
        cfg = PromotionSelectorConfig(max_l1_items_per_batch=5, max_sessions_per_batch=10)
        candidates = [_candidate('u1', 's1', i) for i in range(4)] + [_candidate('u1', 's2', i) for i in range(9)]
        work_items = select_promotion_work_items(candidates, now=NOW, config=cfg)

        assert len(_all_ids(work_items)) == 13
        assert all(len(w.l1_item_ids) <= 5 for w in work_items)
