"""Dual-backend contract for memories (ADR-0044 facade + ADR-0002 store port).

`database/memories.py` carries four of the eight shapes the facade has to translate — more than any
module left on the worklist — and it was **deliberately skipped** when the other suites were written,
on the grounds that its write path needs Redis for the data-protection level. That reason does not
survive reading `database/helpers.py`: `set_data_protection_level` short-circuits BEFORE touching Redis
when the payload already carries `data_protection_level`, and at `'standard'` the read path does not
decrypt either. So the module is drivable hermetically after all, and skipping it would now be a
permanent exclusion justified by a stale measurement.

    projection    get_memory_ids uses `.select([])` — the ids-only form, which feeds account deletion
                  and the vector purge, so a row it drops is data the user asked to be gone that stays
    cursor        scan_memories_{updated,created}_at_page page a keyset of (order field, __name__) with
                  `start_after`; a cursor the backend ignores makes the historical scan restart forever
    batch         delete_memories_batch and delete_all_memories chunk their deletes at 499
    transaction   create_memory reads the memory inside the ledger's transaction before writing, so a
                  re-create merges rather than duplicating

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _memory(memory_id: str, index: int, **overrides):
    """A memory the way the module stores one, with the protection level supplied.

    Supplying it is what keeps this hermetic: `set_data_protection_level` only reaches Redis when the
    field is ABSENT, and `'standard'` means the read path returns the document as stored.
    """
    data = {
        'id': memory_id,
        'content': f'memory {index}',
        'category': 'core',
        'created_at': BASE + timedelta(minutes=index),
        'updated_at': BASE + timedelta(minutes=index),
        'user_review': None,
        'deleted': False,
        'visibility': 'public',
        'data_protection_level': 'standard',
    }
    data.update(overrides)
    return data


@pytest.fixture
def memories(bind_store):
    """Five memories for one user, distinct created_at/updated_at so the keyset order is total."""
    run = uuid.uuid4().hex[:8]
    uid = f'mem-{run}'
    ids = [f'm{i}-{run}' for i in range(5)]

    for index, memory_id in enumerate(ids):
        bind_store.set(f'users/{uid}/memories/{memory_id}', _memory(memory_id, index))

    yield {'uid': uid, 'ids': ids, 'run': run, 'store': bind_store}

    for document in bind_store.query(f'users/{uid}/memories'):
        bind_store.delete(document.path)


def _remaining(memories) -> set[str]:
    return {document.id for document in memories['store'].query(f"users/{memories['uid']}/memories")}


# --- projection -------------------------------------------------------------------------------------


def test_the_ids_only_projection_returns_every_memory(memories):
    """`.select([])` asks for documents with NO fields. Every id must still come back: this feeds
    account deletion and the derived-vector purge, so a row the projection drops is data the user asked
    to have deleted that quietly stays."""
    import database.memories as memories_db

    assert sorted(memories_db.get_memory_ids(memories['uid'])) == sorted(memories['ids'])


def test_the_ids_only_projection_of_an_empty_user_is_empty(memories):
    import database.memories as memories_db

    assert memories_db.get_memory_ids(f"nobody-{memories['run']}") == []


# --- cursor -----------------------------------------------------------------------------------------


def test_the_historical_scan_pages_without_repeating_or_skipping(memories):
    """A keyset of (updated_at DESC, __name__ ASC). Two pages of two must yield four DISTINCT memories:
    a cursor the backend ignores repeats the first page forever and the scan never terminates."""
    import database.memories as memories_db

    first, cursors, exhausted = memories_db.scan_memories_updated_at_page(memories['uid'], limit=2)

    assert len(first) == 2 and not exhausted
    assert len(cursors) == 2, 'one cursor per payload, aligned'

    second, _cursors, _exhausted = memories_db.scan_memories_updated_at_page(
        memories['uid'], limit=2, start_after=cursors[-1]
    )

    assert len(second) == 2
    seen = {row['id'] for row in first} | {row['id'] for row in second}
    assert len(seen) == 4, 'the second page repeated something from the first'


def test_the_historical_scan_reports_exhaustion_at_the_tail(memories):
    """`exhausted` is how the caller knows to stop. Getting it wrong is either an endless loop or a
    scan that stops before the oldest memory."""
    import database.memories as memories_db

    rows, _cursors, exhausted = memories_db.scan_memories_updated_at_page(memories['uid'], limit=50)

    assert len(rows) == 5
    assert exhausted is True


def test_the_created_at_stream_pages_the_same_way(memories):
    """The dual stream. Both must page, or half the history is unreachable for memories that have no
    updated_at."""
    import database.memories as memories_db

    first, cursors, _exhausted = memories_db.scan_memories_created_at_page(memories['uid'], limit=2)
    second, _c, _e = memories_db.scan_memories_created_at_page(memories['uid'], limit=2, start_after=cursors[-1])

    assert len({row['id'] for row in first} | {row['id'] for row in second}) == 4


def test_a_blank_cursor_id_is_refused_rather_than_silently_restarting(memories):
    """The module raises on it. Accepting a blank id would restart the scan from the top, which reads as
    progress and never finishes."""
    import database.memories as memories_db

    with pytest.raises(ValueError):
        memories_db.scan_memories_updated_at_page(memories['uid'], limit=2, start_after=(BASE, '  '))


# --- batch ------------------------------------------------------------------------------------------


def test_a_batch_delete_removes_exactly_the_ids_it_was_given(memories):
    import database.memories as memories_db

    memories_db.delete_memories_batch(memories['uid'], memories['ids'][:3])

    assert _remaining(memories) == set(memories['ids'][3:])


def test_a_batch_delete_of_nothing_is_a_no_op(memories):
    import database.memories as memories_db

    memories_db.delete_memories_batch(memories['uid'], [])

    assert _remaining(memories) == set(memories['ids'])


def test_deleting_everything_leaves_nothing(memories):
    """Account deletion goes through here; a memory the sweep misses is retained data."""
    import database.memories as memories_db

    memories_db.delete_all_memories(memories['uid'])

    assert _remaining(memories) == set()


def test_a_delete_larger_than_one_chunk_leaves_nothing(bind_store):
    """600 memories crosses the 499 rollover.

    It holds COMPLETENESS, not the chunking: neither the emulator nor Mongo enforces Firestore's
    500-writes-per-commit limit, so a build that never rolled over passes here too (same as the
    staged-tasks and folders suites). Completeness is the part that matters for account deletion.
    """
    import database.memories as memories_db

    run = uuid.uuid4().hex[:8]
    uid = f'mem-bulk-{run}'
    total = 600
    for index in range(total):
        bind_store.set(f'users/{uid}/memories/b{index}-{run}', _memory(f'b{index}-{run}', index))

    try:
        assert len(memories_db.get_memory_ids(uid)) == total, 'precondition'
        memories_db.delete_all_memories(uid)
        assert memories_db.get_memory_ids(uid) == []
    finally:
        for document in bind_store.query(f'users/{uid}/memories'):
            bind_store.delete(document.path)


# --- transaction ------------------------------------------------------------------------------------


def test_re_creating_a_memory_merges_its_evidence_instead_of_replacing_it(memories):
    """What the in-transaction read is FOR, and the only way to see it.

    A first version of this test asserted only "one document under one id" — which a write that never
    reads also satisfies, so the mutation survived. `_merge_memory_for_write` shows the real contract:
    when the id already exists and the incoming payload carries evidence, the two evidence sets are
    UNIONED and the original `created_at` is kept. Without the read, the second write replaces the first
    and the earlier evidence — the reason the memory was believed — is gone with no error.
    """
    import database.memories as memories_db

    memory_id = f"ev-{memories['run']}"
    first_seen = BASE
    memories_db.create_memory(
        memories['uid'],
        _memory(memory_id, 9, content='first', created_at=first_seen, evidence=[{'conversation_id': 'c1'}]),
    )
    memories_db.create_memory(
        memories['uid'],
        _memory(
            memory_id, 9, content='second', created_at=BASE + timedelta(days=1), evidence=[{'conversation_id': 'c2'}]
        ),
    )

    stored = memories['store'].get(f"users/{memories['uid']}/memories/{memory_id}").data
    conversations = {item.get('conversation_id') for item in (stored.get('evidence') or [])}

    assert conversations == {'c1', 'c2'}, 'the earlier evidence was replaced instead of merged'
    assert stored['created_at'] == first_seen, 'the original first-seen time must survive a re-create'
    assert len([i for i in memories_db.get_memory_ids(memories['uid']) if i == memory_id]) == 1


def test_a_created_memory_is_readable_back_through_the_module(memories):
    """End to end through the real chain: written by create_memory, read by get_memory. At 'standard'
    the read path does not decrypt, so what comes back is what went in."""
    import database.memories as memories_db

    memory_id = f"rt-{memories['run']}"
    memories_db.create_memory(memories['uid'], _memory(memory_id, 7, content='round trip'))

    stored = memories_db.get_memory(memories['uid'], memory_id)

    assert stored is not None
    assert stored['content'] == 'round trip'
