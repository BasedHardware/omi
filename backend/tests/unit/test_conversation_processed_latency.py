"""Per-conversation processed latency and the settled stamp on every completed writer.

Synthetic rows only. The histogram is observed once, after the commit that makes a
conversation's first usable summary durable; the settled stamp is written once, by
the writer that first moves a row onto completed.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import InvalidArgument
from prometheus_client import REGISTRY

from database import conversation_terminal_title as terminal
from database import conversations as db
from tests.unit.test_conversation_persistence_transaction_expiry import EXPIRED_MESSAGE, _FakeFirestoreClient
from utils.conversations import summary_delivery as delivery
from utils.conversations import terminal_settled

NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
EARLIER = NOW - timedelta(hours=1)


def processed(lane, basis):
    return REGISTRY.get_sample_value('omi_conversation_processed_seconds_count', {'lane': lane, 'basis': basis}) or 0


def processed_sum(lane, basis):
    return REGISTRY.get_sample_value('omi_conversation_processed_seconds_sum', {'lane': lane, 'basis': basis}) or 0


def unsummarized(lane, reason):
    return (
        REGISTRY.get_sample_value('omi_conversation_settled_unsummarized_total', {'lane': lane, 'reason': reason}) or 0
    )


@pytest.fixture(autouse=True)
def live_lane(monkeypatch):
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_ENABLED', raising=False)
    monkeypatch.delenv(terminal_settled.MODE, raising=False)


# --- the settled stamp helper -------------------------------------------------


def test_settle_stamps_only_the_transition_onto_completed():
    assert terminal_settled.settle({'status': 'processing'}, now=NOW, enabled=True) == {'terminal_family_at': NOW}
    assert terminal_settled.settle({}, now=NOW, enabled=True) == {'terminal_family_at': NOW}
    assert terminal_settled.settle({'status': 'completed'}, now=NOW, enabled=True) == {}
    assert terminal_settled.settle({'status': 'processing', 'terminal_family_at': EARLIER}, now=NOW, enabled=True) == {}
    assert terminal_settled.settle({'status': 'processing'}, now=NOW, enabled=False) == {}


def test_stamp_needs_a_completed_payload_and_never_moves_an_existing_time():
    assert terminal_settled.stamp({'status': 'processing'}, {'status': 'completed'}, now=NOW, enabled=True) == {
        'status': 'completed',
        'terminal_family_at': NOW,
    }
    assert terminal_settled.stamp({'status': 'processing'}, {'status': 'failed'}, now=NOW, enabled=True) == {
        'status': 'failed'
    }
    supplied = {'status': 'completed', 'terminal_family_at': EARLIER}
    assert terminal_settled.stamp({}, dict(supplied), now=NOW, enabled=True) == supplied


def test_stamp_never_writes_a_family_so_a_failure_family_survives():
    current = {'status': 'processing', 'terminal_family': 'dead_letter'}
    updates = terminal_settled.stamp(current, {'status': 'completed'}, now=NOW, enabled=True)
    assert 'terminal_family' not in updates


@pytest.mark.parametrize('mode,expected', [(None, True), ('on', True), ('off', False)])
def test_serving_follows_the_terminal_family_kill_switch(monkeypatch, mode, expected):
    if mode is not None:
        monkeypatch.setenv(terminal_settled.MODE, mode)
    assert terminal_settled.serving('synthetic') is expected


# --- legacy receipt path --------------------------------------------------------


def unsummarized_row(**changes):
    return {'status': 'processing', 'finished_at': NOW - timedelta(seconds=600), **changes}


def rich_write():
    return {'status': 'completed', 'summary_output_present': True}


def test_first_rich_summary_reports_both_bases_without_acceptance_metadata():
    arrival = NOW - timedelta(seconds=120)
    row = unsummarized_row(arrival_at=arrival)
    receipt = delivery.merge_result(row, rich_write(), 'u', now=NOW.timestamp())
    assert receipt['reason'] == 'accept_unknown'
    # Arrival stands in for acceptance, so the closed histogram is timed too.
    assert receipt['closed_latency'] == 120
    assert receipt['processed'] == {'finished': 600, 'end_or_sync': 120}
    before = processed('live', 'finished'), processed('live', 'end_or_sync')
    before_sum = processed_sum('live', 'end_or_sync')
    delivery.emit(receipt)
    assert (processed('live', 'finished'), processed('live', 'end_or_sync')) == (before[0] + 1, before[1] + 1)
    assert processed_sum('live', 'end_or_sync') == before_sum + 120


def test_end_or_sync_falls_back_to_last_speech_without_arrival():
    receipt = delivery.merge_result(unsummarized_row(), rich_write(), 'u', now=NOW.timestamp())
    assert receipt['processed'] == {'finished': 600, 'end_or_sync': 600}
    assert receipt['closed_latency'] is None


@pytest.mark.parametrize(
    'existing',
    [
        {'summary_output_present': True},
        {'summary_completed_at': 1.0},
    ],
)
def test_an_already_summarized_row_is_not_observed_again(existing):
    assert delivery.merge_result(unsummarized_row(**existing), rich_write(), 'u', now=NOW.timestamp()) is None


def test_v3_rows_leave_the_observation_to_their_notes_commit():
    receipt = delivery.merge_result(unsummarized_row(v3_derived=True), rich_write(), 'u', now=NOW.timestamp())
    assert receipt['processed'] is None


def test_future_finish_produces_no_sample():
    row = unsummarized_row(finished_at=NOW + timedelta(seconds=5))
    assert delivery.merge_result(row, rich_write(), 'u', now=NOW.timestamp())['processed'] is None


def test_a_discard_settles_without_a_summary_once():
    write = {'status': 'completed', 'summary_output_present': False, 'discarded': True}
    receipt = delivery.merge_result(unsummarized_row(), write, 'u', now=NOW.timestamp())
    before = unsummarized('live', 'discarded'), processed('live', 'finished')
    delivery.emit(receipt)
    assert unsummarized('live', 'discarded') == before[0] + 1
    assert processed('live', 'finished') == before[1]
    replay = unsummarized_row(summary_discard_receipted=True, discarded=True)
    assert delivery.merge_result(replay, dict(write), 'u', now=NOW.timestamp()) is None


def test_uncommitted_receipts_are_not_observed():
    receipt = delivery.merge_result(unsummarized_row(), rich_write(), 'u', now=NOW.timestamp())
    before = processed('live', 'finished')
    delivery.emit_result('u', False, receipt, None, lambda _: None, persisted=False)
    assert processed('live', 'finished') == before


@pytest.fixture
def store(monkeypatch):
    def install(document, errors=()):
        client = _FakeFirestoreClient(document, list(errors))
        monkeypatch.setattr(db, 'db', client)
        monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda _: None)
        monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *_: None)
        monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *_: None)
        return client

    return install


def processing_row(**changes):
    return {
        'status': 'processing',
        'data_protection_level': 'standard',
        'finished_at': datetime.now(timezone.utc) - timedelta(seconds=90),
        **changes,
    }


def test_processing_write_observes_once_across_a_commit_retry(store):
    client = store(processing_row(), [InvalidArgument(EXPIRED_MESSAGE)])
    before = processed('live', 'finished')
    persisted = db.persist_processing_result_with_lifecycle(
        'u',
        {
            'id': 'c',
            'status': 'completed',
            'data_protection_level': 'standard',
            'structured': {'title': 'Synthetic', 'overview': 'A usable synthetic overview.'},
        },
    )
    # The expired first attempt never commits; only the retried commit reaches emit.
    assert persisted and len(client.transactions) >= 2
    assert processed('live', 'finished') == before + 1
    assert client.commits[-1]['terminal_family_at']


# --- writers that move a row onto completed --------------------------------------


def test_upsert_stamps_a_new_completion_and_keeps_an_existing_time(store):
    client = store(processing_row())
    db.upsert_conversation_with_lifecycle('u', processing_row(id='c', status='completed'))
    assert isinstance(client.commits[-1]['terminal_family_at'], datetime)

    client = store(processing_row(status='completed', terminal_family_at=EARLIER))
    db.upsert_conversation_with_lifecycle('u', processing_row(id='c', status='completed'))
    assert 'terminal_family_at' not in client.commits[-1]


def test_upsert_honours_the_kill_switch(store, monkeypatch):
    monkeypatch.setenv(terminal_settled.MODE, 'off')
    client = store(processing_row())
    db.upsert_conversation_with_lifecycle('u', processing_row(id='c', status='completed'))
    assert 'terminal_family_at' not in client.commits[-1]


def test_create_if_absent_stamps_a_completed_creation(store, monkeypatch):
    store(None)
    created = []

    def run(operation, uid, data, **kwargs):
        created.append(dict(data))
        return True, False

    monkeypatch.setattr(db.transcript_pointer, 'run_preloaded_operation', run)
    db.create_conversation_if_absent_with_lifecycle('u', processing_row(id='c', status='completed'))
    db.create_conversation_if_absent_with_lifecycle('u', processing_row(id='d', status='in_progress'))
    assert isinstance(created[0]['terminal_family_at'], datetime)
    assert 'terminal_family_at' not in created[1]


def terminal_row(**changes):
    return {
        'source': 'omi',
        'id': 'c',
        'status': 'processing',
        'discarded': False,
        'relevance_decision': {},
        'structured': {'title': 'Synthetic'},
        'transcript_segments': [{'text': 'the synthetic budget is approved'}],
        **changes,
    }


@pytest.fixture
def no_calendar(monkeypatch):
    monkeypatch.setattr(terminal, 'calendar_retains', lambda *_: False)
    monkeypatch.setattr(terminal, '_has_described_photo', lambda *_, **__: False)


REF = SimpleNamespace(path='users/u/conversations/c', id='c')


def test_dead_letter_stamps_the_time_and_keeps_its_failure_marker(no_calendar):
    patch = terminal.dead_letter_conversation_updates('u', terminal_row(), REF, object(), 'processing_failed', None)
    assert patch['status'] == 'completed' and patch['finalization_status'] == 'dead_letter'
    assert isinstance(patch['terminal_family_at'], datetime)
    assert 'terminal_family' not in patch

    stamped = terminal_row(terminal_family_at=EARLIER, terminal_family='dead_letter')
    patch = terminal.dead_letter_conversation_updates('u', stamped, REF, object(), 'processing_failed', None)
    assert 'terminal_family_at' not in patch and 'terminal_family' not in patch


def test_kept_row_terminal_stamps_once(no_calendar):
    patch = terminal.kept_row_terminal_update('u', terminal_row(), REF, {'status': 'completed'}, None)
    assert isinstance(patch['terminal_family_at'], datetime)
    patch = terminal.kept_row_terminal_update(
        'u', terminal_row(terminal_family_at=EARLIER), REF, {'status': 'completed'}, None
    )
    assert 'terminal_family_at' not in patch


def test_a_terminal_at_the_size_ceiling_drops_the_stamp_never_the_terminal(no_calendar, monkeypatch):
    monkeypatch.setattr(terminal, 'estimate_firestore_document_bytes', lambda *_: terminal.FIRESTORE_MAX_DOCUMENT_BYTES)
    patch = terminal.kept_row_terminal_update('u', terminal_row(), REF, {'status': 'completed'}, None)
    assert patch['status'] == 'completed' and 'terminal_family_at' not in patch


class _DeferredTransaction:
    def __init__(self):
        self.updates = []

    def update(self, ref, payload):
        self.updates.append(payload)


class _DeferredRef(SimpleNamespace):
    def get(self, transaction=None):
        return SimpleNamespace(exists=True, to_dict=lambda: dict(self.row))


@pytest.mark.parametrize('stamped', [False, True])
def test_deferred_failure_terminal_stamps_once(stamped):
    row = {'status': 'processing', 'deferred': False, **({'terminal_family_at': EARLIER} if stamped else {})}
    transaction = _DeferredTransaction()
    assert terminal.recover_deferred_processing_failure_txn(
        transaction, _DeferredRef(path='users/u/conversations/c', id='c', row=row)
    )
    assert ('terminal_family_at' in transaction.updates[0]) is not stamped


def orphan_capture(**changes):
    from config import server_batch

    return {
        'status': 'in_progress',
        'record_lane_owner': 'batch_live_v1',
        server_batch.MARKER: True,
        'record_audio_closed': True,
        'server_batch_audio_closed': True,
        'server_batch_audio_received': True,
        'has_content': True,
        'server_batch_audio_start': 0.0,
        'server_batch_audio_end': 5.0,
        'transcript_segments': [],
        **changes,
    }


@pytest.mark.parametrize('stamped', [False, True])
def test_orphan_capture_completion_stamps_once(stamped):
    from utils.conversations import lifecycle

    transaction = _DeferredTransaction()
    current = orphan_capture(**({'terminal_family_at': EARLIER} if stamped else {}))
    lifecycle.complete_orphan_batch_capture(transaction, REF, current, {}, now=NOW)
    assert ('terminal_family_at' in transaction.updates[0]) is not stamped
    assert 'terminal_family' not in transaction.updates[0]
