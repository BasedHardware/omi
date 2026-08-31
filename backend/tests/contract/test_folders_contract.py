"""Dual-backend contract for conversation folders (ADR-0044 facade + ADR-0002 store port).

`database/folders.py` keeps a derived counter and repoints conversations in bulk — an aggregation and a
batch, and both are visible to the user:

    aggregation   update_folder_conversation_count counts with `.count()` behind TWO equality filters
                  (folder_id AND discarded == False), and writes the number onto the folder. It is the
                  badge the user reads, so a count that ignores a filter is a number they can see is
                  wrong.
    batch         delete_folder repoints every conversation off the folder before removing it, chunking
                  at 450, and reorder_folders writes the whole ordering in one commit. A conversation
                  the batch misses keeps pointing at a document that no longer exists — the module's own
                  comment records that a stale pointer used to 500 every later move of that
                  conversation.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def folders(bind_store):
    """Two folders — one default — and four conversations: three filed, one discarded."""
    run = uuid.uuid4().hex[:8]
    uid = f'fold-{run}'
    work, other = f'work-{run}', f'other-{run}'
    conversations = [f'c{i}-{run}' for i in range(4)]
    paths: list[str] = []

    def _set(path, data):
        bind_store.set(path, data)
        paths.append(path)

    _set(f'users/{uid}/folders/{work}', {'id': work, 'name': 'Work', 'order': 0, 'is_default': False})
    _set(f'users/{uid}/folders/{other}', {'id': other, 'name': 'Other', 'order': 1, 'is_default': True})
    for index, conversation in enumerate(conversations):
        _set(
            f'users/{uid}/conversations/{conversation}',
            {'id': conversation, 'folder_id': work, 'discarded': index == 3, 'created_at': NOW},
        )

    yield {'uid': uid, 'work': work, 'other': other, 'conversations': conversations, 'store': bind_store}

    for path in paths:
        bind_store.delete(path)


def _doc(folders, path):
    stored = folders['store'].get(f"users/{folders['uid']}/{path}")
    return stored.data if stored is not None and stored.exists else None


# --- aggregation ------------------------------------------------------------------------------------


def test_the_folder_count_excludes_discarded_conversations(folders):
    """Two equality filters in one `.count()`. Four conversations are in the folder and one is
    discarded, so the badge must read 3 — a backend that dropped the second filter would show 4 and the
    user would count the difference themselves."""
    import database.folders as folders_db

    count = folders_db.update_folder_conversation_count(folders['uid'], folders['work'])

    assert count == 3
    assert _doc(folders, f"folders/{folders['work']}")['conversation_count'] == 3


def test_an_empty_folder_counts_zero_rather_than_nothing(folders):
    """`.count()` over a query that matches nothing must yield a zero row, not an empty result — the
    caller reads `result[0][0].value` and would raise on the latter."""
    import database.folders as folders_db

    assert folders_db.update_folder_conversation_count(folders['uid'], folders['other']) == 0
    assert _doc(folders, f"folders/{folders['other']}")['conversation_count'] == 0


def test_counting_a_folder_that_no_longer_exists_does_not_raise(folders):
    """Derived state on a document that may have been deleted: the refresh must not fail the move that
    triggered it."""
    import database.folders as folders_db

    assert folders_db.update_folder_conversation_count(folders['uid'], f"ghost-{folders['work']}") == 0


# --- batch ------------------------------------------------------------------------------------------


def test_deleting_a_folder_repoints_every_conversation_to_the_default(folders):
    """The batch, and the reason it exists: a conversation left pointing at a deleted folder used to 500
    on every later move."""
    import database.folders as folders_db

    assert folders_db.delete_folder(folders['uid'], folders['work']) is True

    for conversation in folders['conversations']:
        assert _doc(folders, f'conversations/{conversation}')['folder_id'] == folders['other']
    assert _doc(folders, f"folders/{folders['work']}") is None, 'the folder itself is gone'


def test_the_default_folder_count_is_refreshed_after_the_move(folders):
    """The two shapes meet here: the batch repoints, then the aggregation re-counts. Three visible
    conversations arrive, the discarded one does not count."""
    import database.folders as folders_db

    folders_db.delete_folder(folders['uid'], folders['work'])

    assert _doc(folders, f"folders/{folders['other']}")['conversation_count'] == 3


def test_deleting_a_folder_with_an_explicit_target_uses_it(folders):
    import database.folders as folders_db

    third = f"third-{folders['uid']}"
    folders['store'].set(f"users/{folders['uid']}/folders/{third}", {'id': third, 'name': 'Third', 'order': 2})
    try:
        folders_db.delete_folder(folders['uid'], folders['work'], move_to_folder_id=third)

        for conversation in folders['conversations']:
            assert _doc(folders, f'conversations/{conversation}')['folder_id'] == third
    finally:
        folders['store'].delete(f"users/{folders['uid']}/folders/{third}")


def test_a_repoint_larger_than_one_chunk_leaves_nothing_behind(bind_store):
    """500 conversations, so the module rolls over into a second batch at 450.

    What this holds is COMPLETENESS: not one conversation may be left pointing at a folder that is about
    to be deleted, and delete_folder returns True either way so nothing else would notice. It does NOT
    hold the chunking itself — neither the emulator nor Mongo enforces Firestore's 500-writes-per-commit
    limit, so a build that never rolled over passes here too (verified by mutation, same as the
    staged-tasks suite). The rollover belongs to the unit suite; this holds what a user would see.
    """
    import database.folders as folders_db

    run = uuid.uuid4().hex[:8]
    uid = f'fold-bulk-{run}'
    work, other = f'work-{run}', f'other-{run}'
    total = 500
    bind_store.set(f'users/{uid}/folders/{work}', {'id': work, 'name': 'Work', 'order': 0})
    bind_store.set(f'users/{uid}/folders/{other}', {'id': other, 'name': 'Other', 'order': 1, 'is_default': True})
    for index in range(total):
        bind_store.set(
            f'users/{uid}/conversations/b{index}-{run}',
            {'id': f'b{index}-{run}', 'folder_id': work, 'discarded': False, 'created_at': NOW},
        )

    try:
        folders_db.delete_folder(uid, work)

        stragglers = [
            document.path
            for document in bind_store.query(f'users/{uid}/conversations')
            if (document.data or {}).get('folder_id') != other
        ]
        assert not stragglers, f'{len(stragglers)} conversations still point at the deleted folder'
    finally:
        for index in range(total):
            bind_store.delete(f'users/{uid}/conversations/b{index}-{run}')
        bind_store.delete(f'users/{uid}/folders/{other}')
        bind_store.delete(f'users/{uid}/folders/{work}')


def test_reordering_writes_every_folder_in_one_commit(folders):
    import database.folders as folders_db

    assert folders_db.reorder_folders(folders['uid'], [folders['other'], folders['work']]) is True

    assert _doc(folders, f"folders/{folders['other']}")['order'] == 0
    assert _doc(folders, f"folders/{folders['work']}")['order'] == 1
