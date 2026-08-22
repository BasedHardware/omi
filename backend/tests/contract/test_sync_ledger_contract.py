"""Dual-backend contract for the sync ledger (ADR-0044 facade + ADR-0002 store port).

`database/sync_ledger.py` is the ownership record for a piece of syncing content: who is processing it,
what has already been processed, and whether it is done. Everything it does is one of two shapes:

    transaction        every state change re-reads the entry and refuses unless the caller still owns
                       it — claim, bind, checkpoint, complete, release. The module says why in its own
                       words: "a stale worker can otherwise read an old claim, let a newer upload acquire
                       it, then overwrite that newer owner with a plain set"
    atomic_field_ops   ArrayUnion for the processed-segment set (a retry must not re-add), and
                       DELETE_FIELD to strip ownership on release — the sentinel our port has to
                       translate rather than store literally

The failure modes are all quiet: a segment processed twice, an owner overwritten by a worker that no
longer holds the claim, or a released entry that still carries a dead job_id and can never be re-claimed.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest

# The shape `is_valid_completed_sync_content_result` accepts: an all-success batch. A malformed one is
# refused at the transaction boundary, which is its own test below.
RESULT = {'failed_segments': 0, 'total_segments': 2, 'errors': [], 'outcome': 'success'}


@pytest.fixture
def ledger(bind_store):
    run = uuid.uuid4().hex[:8]
    uid, content_id = f'sync-{run}', f'c-{run}'

    yield {'uid': uid, 'content_id': content_id, 'run': run, 'store': bind_store}

    bind_store.delete(f'users/{uid}/sync_content_ledger/{content_id}')


def _entry(ledger):
    stored = ledger['store'].get(f"users/{ledger['uid']}/sync_content_ledger/{ledger['content_id']}")
    return stored.data if stored is not None and stored.exists else None


# --- transaction: ownership ------------------------------------------------------------------------


def test_a_first_claim_is_owned(ledger):
    import database.sync_ledger as sync_db

    outcome = sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert outcome == {'outcome': 'owned'}
    assert _entry(ledger)['job_id'] == 'job-1'
    assert _entry(ledger)['status'] == 'processing'


def test_a_second_worker_is_told_the_entry_is_busy(ledger):
    """The invariant the transaction exists for: one owner at a time. A second claim must NOT overwrite
    the first, or two workers process the same content and both write results."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')
    outcome = sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-2', 'fresh')

    assert outcome == {'outcome': 'busy'}
    assert _entry(ledger)['job_id'] == 'job-1', 'the incumbent must keep the claim'


def test_the_same_worker_reclaiming_is_idempotent(ledger):
    """A retried claim from the owner is not a conflict."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh') == {'outcome': 'owned'}


def test_a_completed_entry_hands_back_its_result_instead_of_reprocessing(ledger):
    """The point of the ledger: work already done is not done again."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')
    assert sync_db.mark_sync_content_completed(ledger['uid'], ledger['content_id'], 'job-1', RESULT) is True

    outcome = sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-2', 'fresh')

    assert outcome == {'outcome': 'completed', 'result': RESULT}


def test_a_worker_that_lost_the_claim_cannot_publish_a_result(ledger):
    """Completion is a durable cross-worker proof, so it is fenced on ownership. A stale worker writing
    its result would make the replacement owner converge on the wrong output."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert sync_db.mark_sync_content_completed(ledger['uid'], ledger['content_id'], 'job-stale', RESULT) is False
    assert _entry(ledger)['status'] == 'processing', 'the entry must not be marked done by a non-owner'


def test_a_malformed_result_is_refused(ledger):
    """Validated at the transaction boundary, not only in the caller: an alternate caller must not be
    able to publish something that later LOOKS terminal."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert sync_db.mark_sync_content_completed(ledger['uid'], ledger['content_id'], 'job-1', {'nope': True}) is False
    assert _entry(ledger)['status'] == 'processing'


# --- atomic field ops -------------------------------------------------------------------------------


def test_processed_segments_union_instead_of_duplicating(ledger):
    """ArrayUnion. A retry re-reporting a segment must not make it appear twice, or the caller's
    'already processed' check starts disagreeing with itself."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert sync_db.add_processed_sync_segment_id(ledger['uid'], ledger['content_id'], 'job-1', 's1') is True
    assert sync_db.add_processed_sync_segment_id(ledger['uid'], ledger['content_id'], 'job-1', 's2') is True
    assert sync_db.add_processed_sync_segment_id(ledger['uid'], ledger['content_id'], 'job-1', 's1') is False

    assert sorted(_entry(ledger)['processed_segment_ids']) == ['s1', 's2']


def test_a_non_owner_cannot_add_a_processed_segment(ledger):
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert sync_db.add_processed_sync_segment_id(ledger['uid'], ledger['content_id'], 'job-stale', 's1') is False
    assert not _entry(ledger).get('processed_segment_ids')


def test_releasing_a_claim_strips_the_owner_fields(ledger):
    """DELETE_FIELD, and the reason it must actually delete: an entry left carrying a dead job_id looks
    owned to the next claimant, which then gets 'busy' forever and the content never syncs again."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert sync_db.release_sync_content_claim(ledger['uid'], ledger['content_id'], 'job-1') is True

    entry = _entry(ledger)
    assert entry['status'] == 'retryable'
    assert 'job_id' not in entry, 'a released entry must not keep the dead owner'
    assert sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-2', 'fresh') == {'outcome': 'owned'}


def test_a_non_owner_cannot_release(ledger):
    """The scenario in the module's own comment: a stale worker releasing a claim a newer upload has
    since acquired."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')

    assert sync_db.release_sync_content_claim(ledger['uid'], ledger['content_id'], 'job-stale') is False
    assert _entry(ledger)['job_id'] == 'job-1'


def test_a_retryable_entry_keeps_its_checkpoints_when_reclaimed(ledger):
    """Reclaiming after a release must not discard the work already done — that is the difference
    between a retry and a restart, and the processed-segment set is what makes it one."""
    import database.sync_ledger as sync_db

    sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-1', 'fresh')
    sync_db.add_processed_sync_segment_id(ledger['uid'], ledger['content_id'], 'job-1', 's1')
    sync_db.release_sync_content_claim(ledger['uid'], ledger['content_id'], 'job-1')

    assert sync_db.claim_sync_content(ledger['uid'], ledger['content_id'], 'job-2', 'fresh') == {'outcome': 'owned'}
    assert _entry(ledger)['processed_segment_ids'] == ['s1'], 'a retry resumes, it does not restart'
    assert sync_db.get_processed_sync_segment_ids(ledger['uid'], ledger['content_id']) == {'s1'}
