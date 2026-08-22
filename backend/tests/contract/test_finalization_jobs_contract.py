"""Dual-backend contract for the conversation-finalization outbox (ADR-0044 facade + ADR-0002 port).

`database/conversation_finalization_jobs.py` is joint-top of the uncovered worklist (ADR-0060) and it
carries the one shape NO contract suite touched: a **collection group** query.

    collection_group   get_stale_processing_orphan_candidates: a cross-user sweep for conversations in
                       status 'processing', deliberately not collection-scoped — it must reach every
                       users/{uid}/conversations subcollection at once
    cursor             the same sweep pages with start_after(<document snapshot>) so a stable prefix of
                       excluded rows cannot starve a later eligible orphan
    transaction        create_or_get_finalization_intent: reads the conversation and the job inside
                       @firestore.transactional before writing both
    atomic_field_ops   the same transaction adds Increment(delta) to a sharded projection counter

A collection group is exactly the shape a facade can get subtly wrong: Firestore matches by the LAST
path segment across every parent, so an implementation that scopes to one parent, or that matches a
top-level collection of the same name, returns a plausible-looking wrong answer. Nothing proved it
against Mongo until now.

Runs the real chain — the module -> the client each posture deploys -> the live backend. Binding and
skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test must appear TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(hours=6)
STALE_AFTER = timedelta(minutes=30)


@pytest.fixture
def sweep(bind_store, monkeypatch):
    """Three users, each with one conversation stuck in `processing`, plus rows that must be skipped.

    The point of the fixture is the SHAPE: the eligible rows live under three DIFFERENT parents, so a
    query that is scoped to one of them finds at most a third of them.
    """
    import database.conversation_finalization_jobs as jobs_db

    monkeypatch.setattr(jobs_db, '_now', lambda: NOW)

    run = uuid.uuid4().hex[:8]
    uids = [f'fin{i}-{run}' for i in range(3)]
    paths: list[str] = []

    def _seed(uid: str, conversation_id: str, **fields):
        path = f'users/{uid}/conversations/{conversation_id}'
        document = {'id': conversation_id, 'status': 'processing', 'processing_admitted_at': OLD}
        document.update(fields)
        bind_store.set(path, document)
        paths.append(path)
        return path

    eligible = [_seed(uid, f'c-{run}') for uid in uids]
    # Same collection name, same status — but excluded for a reason the sweep applies in Python.
    skipped = {
        'deferred': _seed(uids[0], f'skip-deferred-{run}', deferred=True),
        'owned': _seed(uids[0], f'skip-owned-{run}', finalization_job_id='job-1'),
        'fresh': _seed(uids[1], f'skip-fresh-{run}', processing_admitted_at=NOW - timedelta(minutes=1)),
        'done': _seed(uids[2], f'skip-done-{run}', status='completed'),
    }

    yield {'uids': uids, 'eligible': eligible, 'skipped': skipped, 'store': bind_store, 'run': run}

    for path in paths:
        bind_store.delete(path)


# --- collection group -----------------------------------------------------------------------------


def test_the_sweep_crosses_every_user(sweep):
    """The whole reason the query is a collection group. Three eligible rows under three parents."""
    import database.conversation_finalization_jobs as jobs_db

    result = jobs_db.get_stale_processing_orphan_candidates(stale_after=STALE_AFTER)

    found = {(candidate['uid'], candidate['conversation_id']) for candidate in result['candidates']}
    expected = {(uid, f"c-{sweep['run']}") for uid in sweep['uids']}
    assert expected <= found, f'the cross-user sweep missed {expected - found}'


def test_the_sweep_applies_its_exclusions(sweep):
    """Deferred, already-owned, still-fresh and non-processing rows sit in the same collection group and
    must not come back. A backend that ignored the status filter would return the completed one."""
    import database.conversation_finalization_jobs as jobs_db

    result = jobs_db.get_stale_processing_orphan_candidates(stale_after=STALE_AFTER)

    returned = {candidate['conversation_id'] for candidate in result['candidates']}
    for reason, path in sweep['skipped'].items():
        assert path.rsplit('/', 1)[-1] not in returned, f'a {reason} row came back from the sweep'


def test_a_top_level_collection_of_the_same_name_is_not_swept(sweep):
    """A collection group matches the LAST path segment under any parent — `conversations/{id}` at the
    ROOT is a different thing, and Firestore does include it. What must NOT happen is the sweep
    returning it as a user's conversation: _uid_from_conversation_path rejects a 2-segment path, so it
    is dropped. This pins that the two backends agree on which paths the group query yields."""
    import database.conversation_finalization_jobs as jobs_db

    stray = f"conversations/root-{sweep['run']}"
    sweep['store'].set(stray, {'id': 'root', 'status': 'processing', 'processing_admitted_at': OLD})
    try:
        result = jobs_db.get_stale_processing_orphan_candidates(stale_after=STALE_AFTER)
        assert all(c['conversation_id'] != 'root' for c in result['candidates'])
        assert all(c['uid'] for c in result['candidates']), 'every candidate must carry a real uid'
    finally:
        sweep['store'].delete(stray)


# --- cursor ---------------------------------------------------------------------------------------


def test_paging_resumes_after_the_cursor_instead_of_restarting(sweep):
    """`limit` caps the page; `resume_after_path` must continue from there. If start_after were ignored,
    the second call would return the first row again and the sweep would never reach the tail."""
    import database.conversation_finalization_jobs as jobs_db

    first = jobs_db.get_stale_processing_orphan_candidates(stale_after=STALE_AFTER, limit=1)

    assert len(first['candidates']) == 1
    assert first['resume_after_path'], 'a bounded page must hand back where to resume'

    second = jobs_db.get_stale_processing_orphan_candidates(
        stale_after=STALE_AFTER, limit=1, resume_after_path=first['resume_after_path']
    )

    assert len(second['candidates']) == 1
    assert second['candidates'][0] != first['candidates'][0], 'the cursor was ignored — same row twice'


def test_a_vanished_cursor_wraps_instead_of_failing(sweep):
    """The documented behaviour: a resume path whose document is gone re-scans from the top rather than
    raising. Both backends must agree, or a deleted conversation stalls the sweep on one of them."""
    import database.conversation_finalization_jobs as jobs_db

    result = jobs_db.get_stale_processing_orphan_candidates(
        stale_after=STALE_AFTER, resume_after_path=f"users/{sweep['uids'][0]}/conversations/gone-{sweep['run']}"
    )

    assert result['candidates'], 'a vanished cursor must not empty the sweep'


# --- transaction + atomic field ops -------------------------------------------------------------


@pytest.fixture
def intent(bind_store, monkeypatch):
    import database.conversation_finalization_jobs as jobs_db

    monkeypatch.setattr(jobs_db, '_now', lambda: NOW)
    run = uuid.uuid4().hex[:8]
    uid, conversation_id = f'fin-int-{run}', f'conv-{run}'
    bind_store.set(
        f'users/{uid}/conversations/{conversation_id}',
        {'id': conversation_id, 'status': 'processing', 'processing_admitted_at': OLD, 'has_content': True},
    )

    yield {'uid': uid, 'conversation_id': conversation_id, 'store': bind_store}

    bind_store.delete(f'users/{uid}/conversations/{conversation_id}')


def _admits(_conversation):
    # fanout_key must be truthy: the transaction refuses an admission without one.
    return {'accepted': True, 'terminal': False, 'reason': 'ok', 'fanout_key': 'k'}


def test_creating_an_intent_is_idempotent_across_the_transaction(intent):
    """Two calls, one job. The transaction reads the conversation and the job before writing; if the
    read did not see the first write, the second call would allocate a second job for the same
    conversation — a duplicate finalization."""
    import database.conversation_finalization_jobs as jobs_db

    first = jobs_db.create_or_get_finalization_intent(
        intent['uid'], intent['conversation_id'], requires_byok=False, finalization_admission=_admits
    )
    second = jobs_db.create_or_get_finalization_intent(
        intent['uid'], intent['conversation_id'], requires_byok=False, finalization_admission=_admits
    )

    try:
        assert first['created'] is True and first['job_id']
        assert second['job_id'] == first['job_id']
        assert second['created'] is False, 'the second call must adopt the existing job, not create one'
    finally:
        intent['store'].delete(f"finalization_jobs/{first['job_id']}")


def test_the_projection_counter_increments_atomically(intent):
    """`Increment(1)` on a sharded counter, inside the same transaction. Measured as a DELTA: the shard
    collection is a shared aggregate that other tests in this file also feed, and an absolute assertion
    would depend on execution order. A backend that translated the increment as a plain set would leave
    every shard at 1 however many jobs were admitted, so the delta would come out short."""
    import database.conversation_finalization_jobs as jobs_db

    def _totals():
        sums = {'accepted': 0, 'queued': 0}
        for document in intent['store'].query(jobs_db.FINALIZATION_PROJECTION_COLLECTION):
            for key in sums:
                sums[key] += int(document.data.get(key, 0))
        return sums

    before = _totals()
    created = []
    for index in range(3):
        conversation_id = f"{intent['conversation_id']}-{index}"
        intent['store'].set(
            f"users/{intent['uid']}/conversations/{conversation_id}",
            {'id': conversation_id, 'status': 'processing', 'processing_admitted_at': OLD, 'has_content': True},
        )
        result = jobs_db.create_or_get_finalization_intent(
            intent['uid'], conversation_id, requires_byok=False, finalization_admission=_admits
        )
        created.append((conversation_id, result['job_id']))
        assert result['created'] is True, 'precondition: each conversation must produce a NEW job'

    try:
        after = _totals()
        assert after['accepted'] - before['accepted'] == 3, 'three admissions must add three'
        assert after['queued'] - before['queued'] == 3, 'the second counter in the same call must add too'
    finally:
        for conversation_id, job_id in created:
            intent['store'].delete(f"users/{intent['uid']}/conversations/{conversation_id}")
            intent['store'].delete(f'finalization_jobs/{job_id}')
