"""Multi-batch projection commits read their own writes back (2026-11-18 livelock).

Production's Commit hook (home_feed_writer.augment_home_writes) stamps a fresh home_source_version on every
conversation write. The between-batch readback compared every written field, so each stamp looked like an
external change: every pass committed batch 0 and then raced, and the final batch never landed.
"""

from database import conversations_v3_leases as leases

from datetime import datetime, timedelta, timezone
from copy import deepcopy
import importlib
import logging
from uuid import uuid4

import pytest
from google.cloud.firestore_v1.types import Document, DocumentMask, Value, Write

from database import conversations_v3 as store, home_feed_writer
from tests.unit.fixtures import strict_firestore_transaction as fixture
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot

UID = 'synthetic'
AT = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
R = ('users', UID, 'conversations', 'r')
LEASE = ('users', UID, 'conversation_v3_leases', 'builder')


@pytest.fixture(scope='module', autouse=True)
def owners_import():
    return importlib.import_module('utils.conversations.lifecycle')


@pytest.fixture
def strict(monkeypatch):
    client = StrictFirestore()
    revisions = {}

    def transactional(body):
        def run(tx, *args, **kwargs):
            with client.lock:
                return body(tx, *args, **kwargs)

        return run

    original_get = fixture.StrictFirestoreDocument.get

    def get(self, *args, **kwargs):
        snapshot = original_get(self, *args, **kwargs)
        snapshot.path = self.path
        return snapshot

    def stamping(name):
        original = getattr(fixture.StrictFirestoreTransaction, name)

        def write(self, ref, *args, **kwargs):
            result = original(self, ref, *args, **kwargs)
            revisions[ref.path] = revisions.get(ref.path, 1) + 1
            if ref.path[2] == 'conversations' and ref.path in client.rows:
                # What augment_home_writes adds to the same Commit in production.
                client.rows[ref.path]['home_source_version'] = uuid4().hex
                payload = args[0] if args else {}
                if {'transcript_segments', 'user_corrections'} & set(payload):
                    client.rows[ref.path]['home_content_invalidated'] = 'structured' not in payload
            return result

        return write

    monkeypatch.setattr(fixture.StrictFirestoreDocument, 'get', get)
    for name in ('set', 'update'):
        monkeypatch.setattr(fixture.StrictFirestoreTransaction, name, stamping(name))
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda s: revisions.get(getattr(s, 'path', None), 1)),
        raising=False,
    )
    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    monkeypatch.setattr(store, 'encrypt', lambda value, uid: value)
    monkeypatch.setattr(store.conversations, '_prepare_conversation_for_write', lambda row, *a, **kw: deepcopy(row))
    return client


def planned(count, *, text_bytes=60000):
    # Rows rebuilt from a prior carry its stored home stamp, exactly as planner.build merges **existing.
    return [
        {
            'id': f'c{i}',
            'status': 'processing',
            'started_at': AT + timedelta(minutes=i),
            'finished_at': AT + timedelta(minutes=i, seconds=30),
            'v3_recording_ids': ['r'],
            'transcript_segments': [{'text': 'x' * text_bytes}],
            'home_source_version': 'stale-from-prior',
        }
        for i in range(count)
    ]


def commit(strict, rows):
    strict.rows[R] = {'id': 'r', 'recording': True, 'v3_pending': True, 'status': 'completed', 'started_at': AT}
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    strict.rows[LEASE].update(v3_blocked_reason='document_too_large', v3_blocked_count=8, v3_backoff_until=AT)
    source = {**deepcopy(strict.rows[R]), '_v3_revision': 1}
    source['_v3_fence'] = store.source_fence(strict.rows[R])
    return store.commit_projection(UID, token, {'r': source}, {}, rows, [], firestore_client=strict)


def test_multi_batch_commit_reaches_the_final_batch_through_commit_stamps(strict):
    rows = planned(64)
    moved = commit(strict, rows)
    assert moved == set()
    assert all(('users', UID, 'conversations', row['id']) in strict.rows for row in rows)
    # The final batch landed: the obligation is cleared and the owner's park is reset.
    assert strict.rows[R]['v3_pending'] is False
    assert len(strict.rows[R]['claims']) == 64
    assert strict.rows[LEASE]['v3_blocked_reason'] is None and strict.rows[LEASE]['v3_backoff_until'] is None


def test_an_external_change_between_batches_still_conflicts_and_names_the_field(strict, monkeypatch, caplog):
    original = store.firestore.transactional
    calls = []

    def transactional(body):
        wrapped = original(body)

        def run(tx, *args):
            result = wrapped(tx, *args)
            first = strict.rows.get(('users', UID, 'conversations', 'c0'))
            if first is not None and not calls:
                # Someone else edits a row our first batch just wrote, before our readback.
                calls.append(1)
                first['status'] = 'completed'
            return result

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    with caplog.at_level(logging.WARNING, logger=store.logger.name), pytest.raises(
        store.Conflict, match='source_changed'
    ):
        commit(strict, planned(64))
    [message] = [r.getMessage() for r in caplog.records if 'readback changed' in r.getMessage()]
    assert 'kind=derived_row' in message and "'status'" in message and 'c0' not in message


def test_commit_stamped_fields_match_what_the_home_hook_adds():
    owner = 'projects/p/databases/(default)/documents/users/u'
    source = Write(
        update=Document(
            name=f'{owner}/conversations/c',
            fields={'transcript_segments': Value(string_value='encrypted'), 'status': Value(string_value='completed')},
        ),
        update_mask=DocumentMask(field_paths=['transcript_segments', 'status']),
    )
    augmented = home_feed_writer.augment_home_writes([source])
    stamped = set(augmented[0].update.fields) - set(source.update.fields)
    assert stamped and stamped <= home_feed_writer.COMMIT_STAMPED_FIELDS
