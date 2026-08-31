"""Dual-backend contract for per-user usage counters (ADR-0044 facade + ADR-0002 store port).

`database/user_usage.py` is what a user sees as "how much have I used Omi", and it carries three shapes
the facade has to translate:

    atomic_field_ops   Increment on flat counters, AND ArrayUnion on `platforms` — the union is the
                       variant nothing else covers: two writes in the same hour from desktop and mobile
                       must accumulate to a set of two, not overwrite each other
    transaction        update_hourly_usage_once reads a ledger marker and writes both the marker and the
                       counters in one commit, so a replayed sync cannot inflate the numbers
    batch              batch_update_hourly_usage writes many hour documents in one commit, chunked at 400

Unlike llm_usage, the field paths here are flat, so the two backends should agree on everything. They
do — this suite asserts it rather than assuming it.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

HOUR = datetime(2026, 4, 2, 15, 0, tzinfo=timezone.utc)
DOC_ID = '2026-04-02-15'


@pytest.fixture
def user(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'uu-{run}'
    paths: list[str] = []

    yield {'uid': uid, 'run': run, 'store': bind_store, 'paths': paths}

    for path in paths:
        bind_store.delete(path)
    bind_store.delete(f'users/{uid}/hourly_usage/{DOC_ID}')


def _hour(user, doc_id: str = DOC_ID):
    """The hour document, or None when it does not exist.

    ``store.get`` returns a StoredDocument with ``exists=False`` for a missing path rather than None, on
    both backends — so ``exists`` is the thing to read, not the object.
    """
    stored = user['store'].get(f"users/{user['uid']}/hourly_usage/{doc_id}")
    return stored.data if stored is not None and stored.exists else None


# --- atomic field ops -----------------------------------------------------------------------------


def test_hourly_counters_accumulate(user):
    """Three writes into the same hour must total. A backend that translated Increment as a set would
    report the last write as the hour's usage — the user's numbers would stop growing."""
    import database.user_usage as usage_db

    for _ in range(3):
        usage_db.update_hourly_usage(user['uid'], HOUR, {'transcription_seconds': 10, 'words_transcribed': 25})

    stored = _hour(user)

    assert stored['transcription_seconds'] == 30
    assert stored['words_transcribed'] == 75


def test_a_zero_or_unknown_field_writes_nothing(user):
    """The guard in the module: only known counters with a positive value are incremented, and a call
    with none of them must not create the document at all. A backend that wrote the metadata anyway
    would leave an hour row claiming activity that never happened."""
    import database.user_usage as usage_db

    usage_db.update_hourly_usage(user['uid'], HOUR, {'transcription_seconds': 0, 'not_a_counter': 5})

    assert _hour(user) is None


def test_the_platform_set_unions_instead_of_overwriting(user):
    """ArrayUnion, the shape no other suite covers. One hour touched from both platforms must end up
    with both — and a repeat must not duplicate."""
    import database.user_usage as usage_db

    usage_db.update_hourly_usage(user['uid'], HOUR, {'transcription_seconds': 5}, platform='mobile')
    usage_db.update_hourly_usage(user['uid'], HOUR, {'transcription_seconds': 5}, platform='desktop')
    usage_db.update_hourly_usage(user['uid'], HOUR, {'transcription_seconds': 5}, platform='mobile')

    stored = _hour(user)

    assert sorted(stored['platforms']) == ['desktop', 'mobile'], 'the union must keep both, exactly once'
    assert stored['transcription_seconds'] == 15, 'and the counter still adds up alongside it'


# --- transaction ----------------------------------------------------------------------------------


def test_a_replayed_sync_counts_once(user):
    """The ledger marker and the counters are written in ONE transaction. If the marker read did not see
    the earlier commit, a retried sync would inflate the user's usage — silently, and in their favour or
    against them depending on the counter."""
    import database.user_usage as usage_db

    key = f"sync-{user['run']}"
    user['paths'].append(f"users/{user['uid']}/sync_content_ledger/{key}")

    first = usage_db.update_hourly_usage_once(user['uid'], HOUR, {'transcription_seconds': 12}, key)
    second = usage_db.update_hourly_usage_once(user['uid'], HOUR, {'transcription_seconds': 12}, key)

    assert first is True and second is False
    assert _hour(user)['transcription_seconds'] == 12, 'the replay must not have added a second 12'


def test_two_different_sync_keys_both_count(user):
    """The other direction, so the test above cannot pass by never counting anything."""
    import database.user_usage as usage_db

    for suffix in ('a', 'b'):
        key = f"sync-{user['run']}-{suffix}"
        user['paths'].append(f"users/{user['uid']}/sync_content_ledger/{key}")
        assert usage_db.update_hourly_usage_once(user['uid'], HOUR, {'transcription_seconds': 12}, key) is True

    assert _hour(user)['transcription_seconds'] == 24


def test_an_update_with_no_countable_field_is_declined_without_touching_the_ledger(user):
    """It returns False BEFORE the transaction. A backend-visible difference would be a burned ledger
    key: the next real sync with that key would then be declined and its usage lost."""
    import database.user_usage as usage_db

    key = f"sync-empty-{user['run']}"
    user['paths'].append(f"users/{user['uid']}/sync_content_ledger/{key}")

    assert usage_db.update_hourly_usage_once(user['uid'], HOUR, {'not_a_counter': 9}, key) is False
    assert not user['store'].get(f"users/{user['uid']}/sync_content_ledger/{key}").exists
    assert usage_db.update_hourly_usage_once(user['uid'], HOUR, {'transcription_seconds': 7}, key) is True


# --- batch ------------------------------------------------------------------------------------------


def test_a_batch_writes_every_hour_it_was_given(user):
    """Several hour documents in one commit."""
    import database.user_usage as usage_db

    hours = {HOUR.replace(hour=h): {'transcription_seconds': h} for h in (9, 10, 11)}
    for date in hours:
        user['paths'].append(f"users/{user['uid']}/hourly_usage/2026-04-02-{date.hour:02d}")

    usage_db.batch_update_hourly_usage(user['uid'], hours)

    for date, updates in hours.items():
        stored = _hour(user, f'2026-04-02-{date.hour:02d}')
        assert stored is not None, f'hour {date.hour} never landed'
        assert stored['transcription_seconds'] == updates['transcription_seconds']
        assert stored['hour'] == date.hour, 'the query fields must be written with it'


def test_a_batch_larger_than_one_chunk_commits_every_document(user):
    """The module chunks at 400 and opens a NEW batch per chunk. 450 hours crosses it, and a chunking
    bug loses the tail without any error — the function returns None either way."""
    import database.user_usage as usage_db

    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    hours = {}
    for index in range(450):
        date = base.replace(day=1 + index // 24, hour=index % 24)
        hours[date] = {'transcription_seconds': 1}
    doc_ids = [f'{d.year}-{d.month:02d}-{d.day:02d}-{d.hour:02d}' for d in hours]
    for doc_id in doc_ids:
        user['paths'].append(f"users/{user['uid']}/hourly_usage/{doc_id}")

    usage_db.batch_update_hourly_usage(user['uid'], hours)

    missing = [doc_id for doc_id in doc_ids if _hour(user, doc_id) is None]
    assert not missing, f'{len(missing)} of {len(doc_ids)} documents were dropped, first: {missing[:3]}'
