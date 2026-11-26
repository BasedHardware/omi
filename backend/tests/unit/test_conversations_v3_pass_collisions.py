"""A lost v3 grouping pass says which document it lost to and which writer changed it.

``raced`` is a pass thrown away because a loaded document changed; ``lock_retried`` a commit the SDK ran
again after a lock abort; ``lock_failed`` a commit that gave up on a lock. Each is one counter step and one
``event=v3_pass_collision`` line naming the kind of document, the changed field names and the writer family.
Nothing here may change what a commit does.
"""

import logging
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from google.api_core.exceptions import Aborted, InvalidArgument

from database import conversations_v3 as store, conversations_v3_collisions as collisions
from database import conversations_v3_leases as leases
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.unit.test_conversations_v3_transactions import L, R, strict  # noqa: F401
from utils.conversations.v3 import Conflict

AT = datetime(2026, 11, 25, 18, 33, tzinfo=timezone.utc)
UID = 'synthetic'
C = (*R[:-1], 'c')


@pytest.fixture(autouse=True)
def quiet(monkeypatch, caplog):
    monkeypatch.setattr(collisions, 'SETTLE_SECONDS', 0)
    caplog.set_level(logging.INFO, logger=collisions.logger.name)


def count(outcome, doc, writer, lane='builder'):
    return collisions.COLLISIONS.labels(outcome, doc, writer, lane)._value.get()


def lines(caplog):
    return [record.getMessage() for record in caplog.records if 'event=v3_pass_collision' in record.getMessage()]


def loaded(raw, cid):
    """A row as the pass loads it: decoded content plus the revision, fence and field tokens."""
    return {
        **deepcopy(raw),
        'id': cid,
        '_v3_revision': raw.get('_test_revision', 1),
        '_v3_fence': store.source_fence(raw),
        collisions.FIELDS_KEY: collisions.fingerprint(raw),
    }


@pytest.fixture
def scene(strict):
    """One recording row and one conversation, loaded by a pass that holds the builder lease."""
    strict.rows[R] = {
        'recording': True,
        'v3_pending': True,
        'status': 'in_progress',
        'started_at': AT,
        'transcript_segments': [{'text': 'one', 'start': 0, 'end': 1}],
    }
    strict.rows[C] = {
        'v3_derived': True,
        'status': 'processing',
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=1),
        'v3_recording_ids': ['r'],
        'structured': {'title': 'old'},
        'tile_state': 'writing',
        'home_source_version': 'a',
    }
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    recordings, existing = {'r': loaded(strict.rows[R], 'r')}, {'c': loaded(strict.rows[C], 'c')}

    def commit():
        return store.commit_projection(UID, token, recordings, existing, [], [], firestore_client=strict)

    return SimpleNamespace(client=strict, commit=commit, recordings=recordings, existing=existing)


def another_writer(client, path, **fields):
    client.rows[path].update(fields, _test_revision=client.rows[path].get('_test_revision', 1) + 1)


def sdk_reruns(monkeypatch, client, between, *, error=None):
    """A commit that loses its lock and is run again: the body runs, its writes are undone, ``between``
    lands (the writer that won the lock), and the body runs again. With ``error`` every attempt ends that
    way instead: the commit's retry (three fresh transactions) calls this once per attempt, then gives up."""

    def transactional(body):
        def run(tx, *args, **kwargs):
            saved = deepcopy(client.rows)
            body(tx, *args, **kwargs)
            client.rows.clear()
            client.rows.update(saved)
            # The writer that beat this try lands its write after the try was aborted.
            between()
            tx.has_written = False
            if error is not None:
                raise error
            return body(tx, *args, **kwargs)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)


# --- field tokens ---------------------------------------------------------------------------------------


def test_field_tokens_carry_no_content_and_ignore_key_order():
    first = collisions.fingerprint({'structured': {'title': 'secret', 'emoji': 'x'}, 'at': AT, 'blob': b'\x00secret'})
    second = collisions.fingerprint({'blob': b'\x00secret', 'at': AT, 'structured': {'emoji': 'x', 'title': 'secret'}})
    assert first == second
    assert 'secret' not in repr(first)


def test_changed_fields_names_what_differs_and_skips_the_stamp_of_every_write():
    before = collisions.fingerprint({'structured': {'title': 'a'}, 'tile_state': 'writing', 'home_source_version': 1})
    after = collisions.fingerprint({'structured': {'title': 'b'}, 'folder_id': 'f', 'home_source_version': 2})
    assert collisions.changed_fields(before, after) == ['folder_id', 'structured', 'tile_state']
    assert collisions.changed_fields(before, before) == []
    assert collisions.changed_fields(None, after) is None


@pytest.mark.parametrize(
    'doc, fields, writer',
    [
        # A summary write also sets the tile and the revision: the summary is what gets named.
        (collisions.CONVERSATION, ['structured', 'summary_due_at', 'tile_state'], 'summary'),
        (collisions.CONVERSATION, ['structured', 'summary_due_at', 'user_title'], 'user_edit'),
        (collisions.OPEN_CONVERSATION, ['tile_state', 'v3_process_pending'], 'processing'),
        (collisions.OPEN_CONVERSATION, ['v3_live_title_state', 'structured'], 'live_title'),
        (collisions.OPEN_CONVERSATION, ['v3_live_summary'], 'live_summary'),
        (collisions.CONVERSATION, ['conversation_audio'], 'audio'),
        (collisions.CONVERSATION, ['deleted', 'structured'], 'delete'),
        (collisions.CONVERSATION, ['a_field_nobody_listed'], 'other'),
        (collisions.CONVERSATION, [], 'no_value_change'),
        (collisions.CONVERSATION, None, 'unknown'),
        # Attaching an uploaded unit moves the start and re-arms the pass: the attach step is named.
        (
            collisions.RECORDING_ROW,
            ['started_at', 'sync_recorded_end_at', 'transcript_segments', 'v3_pending'],
            'upload_attach',
        ),
        (collisions.RECORDING_ROW, ['last_speech_at', 'transcript_segments', 'v3_pending_since'], 'live_append'),
        (collisions.RECORDING_ROW, ['started_at', 'transcript_segments'], 'speech'),
        (collisions.RECORDING_ROW, ['v3_manual_end', 'v3_pending'], 'end'),
        (collisions.RECORDING_ROW, ['claims', 'v3_pending'], 'ownership'),
        (collisions.RECORDING_ROW, ['record_sealed_at'], 'record_lane'),
        (collisions.RECORDING_ROW, ['v3_pending', 'v3_pending_since'], 'owes_a_pass'),
        (collisions.MISSING, None, 'delete'),
        (collisions.LEASE, ['until'], 'lease'),
    ],
)
def test_the_writer_family_follows_the_changed_fields(doc, fields, writer):
    assert collisions.writer_of(doc, fields) == writer


def test_a_decoded_row_carries_its_field_tokens_and_a_commit_never_stores_them(monkeypatch, scene):
    raw = {'structured': {'title': 'old'}, 'transcript_segments': []}
    monkeypatch.setattr(store.conversations, 'decode_transcript_segments_verified', lambda *a: [])
    monkeypatch.setattr(store.conversations, 'prepare_conversation_for_read', lambda data, uid: dict(data))
    snapshot = SimpleNamespace(exists=True, id='x', update_time=1, to_dict=lambda: deepcopy(raw))
    row = store.decode_row(UID, snapshot)
    assert row[collisions.FIELDS_KEY] == collisions.fingerprint(raw)

    planned = {**scene.existing['c'], 'status': 'processing'}
    token = scene.client.rows[L]['token']
    store.commit_projection(UID, token, scene.recordings, scene.existing, [planned], [], firestore_client=scene.client)
    assert not any(key.startswith('_v3_') for key in scene.client.rows[C])


# --- raced ----------------------------------------------------------------------------------------------


def test_a_pass_thrown_away_by_a_summary_write_names_the_conversation_and_the_summary(scene, caplog):
    another_writer(scene.client, C, structured={'title': 'new'}, tile_state='done', home_source_version='b')
    before = count('raced', 'conversation', 'summary')
    with pytest.raises(Conflict, match='source_changed'):
        scene.commit()
    assert count('raced', 'conversation', 'summary') == before + 1
    (line,) = lines(caplog)
    assert (
        'outcome=raced lane=builder doc=conversation writer=summary fields=structured,tile_state '
        'phase=documents attempt=1' in line
    )
    # Names of fields only: nothing a user said or a title reaches the log.
    assert 'new' not in line.split('fields=')[1].split(' ')[0]


def test_an_open_conversation_and_a_deleted_one_are_told_apart(scene, caplog):
    scene.client.rows[C]['status'] = 'in_progress'
    scene.existing['c'] = loaded(scene.client.rows[C], 'c')
    another_writer(scene.client, C, tile_state='done')
    with pytest.raises(Conflict, match='source_changed'):
        scene.commit()
    assert 'doc=open_conversation writer=processing fields=tile_state' in lines(caplog)[-1]

    del scene.client.rows[C]
    with pytest.raises(Conflict, match='source_changed'):
        scene.commit()
    assert 'doc=missing writer=delete fields=?' in lines(caplog)[-1]


def test_a_recording_row_that_only_got_more_speech_is_not_a_collision(scene, caplog):
    another_writer(scene.client, R, transcript_segments=[{'text': 'one'}, {'text': 'two'}])
    assert scene.commit() == {'r'}
    assert lines(caplog) == []


def test_a_recording_row_whose_ownership_changed_throws_the_pass_away_and_says_so(scene, caplog):
    another_writer(scene.client, R, claims=[{'conversation_id': 'z', 'start': AT, 'end': AT}])
    before = count('raced', 'recording_row', 'ownership')
    with pytest.raises(Conflict, match='source_changed'):
        scene.commit()
    assert count('raced', 'recording_row', 'ownership') == before + 1
    assert 'doc=recording_row writer=ownership fields=claims' in lines(caplog)[0]


def test_a_row_loaded_without_field_tokens_still_reports_the_document(scene, caplog):
    del scene.existing['c'][collisions.FIELDS_KEY]
    another_writer(scene.client, C, structured={'title': 'new'})
    with pytest.raises(Conflict, match='source_changed'):
        scene.commit()
    assert 'doc=conversation writer=unknown fields=?' in lines(caplog)[0]


def test_a_broken_report_never_changes_the_outcome_of_a_commit(scene, monkeypatch):
    monkeypatch.setattr(collisions, 'fingerprint', lambda raw: 1 / 0)
    monkeypatch.setattr(collisions.COLLISIONS, 'labels', lambda *a: 1 / 0)
    another_writer(scene.client, C, structured={'title': 'new'})
    with pytest.raises(Conflict, match='source_changed'):
        scene.commit()
    collisions.report('raced', 'conversation', ['x'])


# --- lock contention ------------------------------------------------------------------------------------


def test_a_commit_the_sdk_ran_again_names_the_document_that_moved_between_the_tries(scene, monkeypatch, caplog):
    sdk_reruns(
        monkeypatch,
        scene.client,
        lambda: another_writer(scene.client, R, v3_pending=True, v3_pending_since=AT, v3_speech_landed_at=AT),
    )
    before = count('lock_retried', 'recording_row', 'speech')
    assert scene.commit() == {'r'}
    assert count('lock_retried', 'recording_row', 'speech') == before + 1
    (line,) = lines(caplog)
    assert 'outcome=lock_retried' in line and 'doc=recording_row writer=speech' in line
    # The try that lost is the first, and the SDK only re-runs a try that was aborted at its commit.
    assert 'fields=v3_pending_since,v3_speech_landed_at' in line and 'phase=commit attempt=1 ' in line


def test_a_retried_commit_where_nothing_it_read_moved_says_unknown(scene, monkeypatch, caplog):
    sdk_reruns(monkeypatch, scene.client, lambda: None)
    scene.commit()
    assert 'outcome=lock_retried lane=builder doc=unknown writer=no_visible_write fields=?' in lines(caplog)[0]


def test_a_clean_commit_reports_nothing_and_reads_nothing_more(scene, monkeypatch, caplog):
    reads = []
    plain = scene.client.get_all
    monkeypatch.setattr(
        scene.client, 'get_all', lambda refs, **kw: reads.append(kw.get('transaction')) or plain(refs, **kw)
    )
    scene.commit()
    assert lines(caplog) == []
    assert reads and all(tx is not None for tx in reads)


def exhausted():
    # What one fresh transaction (max_attempts=1) raises when its commit is aborted on a lock.
    error = ValueError('Failed to commit transaction in 1 attempts.')
    error.__cause__ = Aborted('Transaction lock timeout.')
    return error


def test_a_commit_that_gives_up_on_a_lock_names_what_moved_while_it_was_failing(scene, monkeypatch, caplog):
    error = exhausted()
    landed = iter(range(1, 10))
    sdk_reruns(
        monkeypatch,
        scene.client,
        lambda: another_writer(scene.client, R, v3_pending=True, v3_pending_since=AT + timedelta(seconds=next(landed))),
        error=error,
    )
    before = count('lock_failed', 'recording_row', 'owes_a_pass')
    with pytest.raises(FirestoreContentionExhausted) as raised:
        scene.commit()
    # The last attempt's own error rides along as the cause.
    assert raised.value.__cause__ is error
    assert count('lock_failed', 'recording_row', 'owes_a_pass') == before + 1
    failed = [line for line in lines(caplog) if 'outcome=lock_failed' in line]
    assert len(failed) == 1
    assert 'doc=recording_row writer=owes_a_pass fields=v3_pending_since' in failed[0]
    # Three fresh transactions, each aborted at its commit.
    assert 'phase=commit attempt=3' in failed[0] and 'cause=contention' in failed[0]
    # A failed commit is a fault (kept in full in production logs); a raced or retried one is information.
    levels = {
        record.getMessage().split('outcome=')[1].split(' ')[0]: record.levelno
        for record in caplog.records
        if 'event=v3_pass_collision' in record.getMessage()
    }
    assert levels == {'lock_retried': logging.INFO, 'lock_failed': logging.WARNING}


def test_a_lock_lost_while_reading_names_the_step_and_what_changed_since_the_pass_loaded(scene, monkeypatch, caplog):
    # An abort raised by a read is retried on a fresh transaction like one raised at commit.
    another_writer(scene.client, R, v3_pending=True, v3_pending_since=AT)

    def aborted(*args, **kwargs):
        raise Aborted('Aborted due to cross-transaction contention.')

    monkeypatch.setattr(store, '_projection_snapshots', aborted)
    with pytest.raises(FirestoreContentionExhausted) as raised:
        scene.commit()
    assert isinstance(raised.value.__cause__, Aborted)
    (line,) = lines(caplog)
    assert 'outcome=lock_failed' in line and 'phase=documents attempt=3' in line
    assert 'doc=recording_row writer=owes_a_pass fields=v3_pending_since' in line


def test_a_failed_commit_where_nothing_moved_says_unknown(scene, monkeypatch, caplog):
    sdk_reruns(monkeypatch, scene.client, lambda: None, error=exhausted())
    with pytest.raises(FirestoreContentionExhausted):
        scene.commit()
    assert 'outcome=lock_failed lane=builder doc=unknown writer=no_visible_write' in lines(caplog)[-1]


def test_a_failure_that_is_not_a_lock_reads_nothing_and_reports_nothing(scene, monkeypatch, caplog):
    sdk_reruns(monkeypatch, scene.client, lambda: None, error=InvalidArgument('synthetic'))
    plain_reads = []
    plain = scene.client.get_all

    def get_all(refs, **kw):
        if kw.get('transaction') is None:
            plain_reads.append(len(refs))
        return plain(refs, **kw)

    monkeypatch.setattr(scene.client, 'get_all', get_all)
    with pytest.raises(InvalidArgument):
        scene.commit()
    assert plain_reads == []
    assert [line for line in lines(caplog) if 'outcome=lock_failed' in line] == []


def test_the_look_after_a_failed_commit_cannot_replace_the_commit_error(scene, monkeypatch):
    error = exhausted()
    sdk_reruns(monkeypatch, scene.client, lambda: None, error=error)
    plain = scene.client.get_all

    def get_all(refs, **kw):
        if kw.get('transaction') is None:
            raise RuntimeError('diagnostic read failed')
        return plain(refs, **kw)

    monkeypatch.setattr(scene.client, 'get_all', get_all)
    with pytest.raises(FirestoreContentionExhausted) as raised:
        scene.commit()
    assert raised.value.__cause__ is error


def test_a_document_changed_before_the_commit_began_did_not_hold_its_lock():
    watch = collisions.CommitWatch('builder', {})
    assert watch._in_window(datetime.now(timezone.utc))
    assert not watch._in_window(datetime.now(timezone.utc) - timedelta(seconds=30))


# --- the other side of the lock: marking a recording row as owing a pass ---------------------------------


def marks(outcome, lock='clean'):
    return collisions.MARKS.labels(outcome, lock)._value.get()


def test_marking_a_row_says_whether_the_write_changed_anything(strict):
    strict.rows[R] = {'recording': True, 'v3_pending': False}
    armed, already, skipped = marks('armed'), marks('already_pending'), marks('skipped')
    assert store.mark_pending(UID, 'r', firestore_client=strict) is True
    assert marks('armed') == armed + 1
    since = strict.rows[R]['v3_pending_since']
    # The row is already marked: the second write takes its lock and changes nothing.
    assert store.mark_pending(UID, 'r', firestore_client=strict) is True
    assert marks('already_pending') == already + 1
    assert strict.rows[R] == {'recording': True, 'v3_pending': True, 'v3_pending_since': since}
    # An End on a marked row does change it.
    assert store.mark_pending(UID, 'r', manual_end=True, firestore_client=strict) is True
    assert marks('armed') == armed + 2
    strict.rows[R]['deleted'] = True
    assert store.mark_pending(UID, 'r', firestore_client=strict) is False
    assert marks('skipped') == skipped + 1


def test_a_mark_the_sdk_ran_again_or_that_failed_on_a_lock_is_counted_and_logged(strict, monkeypatch, caplog):
    strict.rows[R] = {'recording': True, 'v3_pending': True, 'v3_pending_since': AT}

    def twice(body):
        def run(tx, *args, **kwargs):
            body(tx, *args, **kwargs)
            tx.has_written = False
            return body(tx, *args, **kwargs)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', twice)
    retried = marks('already_pending', 'retried')
    assert store.mark_pending(UID, 'r', firestore_client=strict) is True
    assert marks('already_pending', 'retried') == retried + 1
    assert 'event=v3_mark_pending_collision outcome=already_pending lock=retried attempts=2' in caplog.text

    def aborted(body):
        def run(tx, *args, **kwargs):
            body(tx, *args, **kwargs)
            raise Aborted('Aborted due to cross-transaction contention.')

        return run

    monkeypatch.setattr(store.firestore, 'transactional', aborted)
    failed = marks('failed', 'failed')
    with pytest.raises(Aborted):
        store.mark_pending(UID, 'r', firestore_client=strict)
    assert marks('failed', 'failed') == failed + 1
    assert 'event=v3_mark_pending_collision outcome=failed lock=failed attempts=1' in caplog.text


# --- production readout ---------------------------------------------------------------------------------


def test_the_counter_leaves_backend_sync_where_the_pass_runs():
    config = yaml.safe_load((Path(__file__).resolve().parents[2] / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    keep = next(rule for rule in config['spec']['endpoints'][0]['metricRelabeling'] if rule['action'] == 'keep')
    for name in (
        'omi_conversations_v3_pass_collision_total',
        'omi_conversations_v3_mark_pending_total',
        'omi_conversations_v3_reconciles_total',
    ):
        assert re.fullmatch(keep['regex'], name), name


def test_labels_are_closed_sets():
    assert {name for table in collisions.WRITERS.values() for name, _, _ in table} <= collisions.WRITER_NAMES
    collisions.report('raced', 'conversation', ['x'], writer='not a writer family')
    assert count('raced', 'conversation', 'other') >= 1
