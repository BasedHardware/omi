"""All seven document-holding readers preserve their legacy results and IO footprint."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import _client, conversations, processing_attention
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import live
from utils.conversations import fragment_visibility, phase_shadow, summary_delivery
from utils.episodes import composer, home_read

T0 = datetime(2026, 11, 3, tzinfo=timezone.utc)
ROWS = [
    {
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'record_audio_closed': True,
        'finalization_status': 'queued',
        'structured': {'title_provenance': 'server_minimum'},
    },
    {'status': 'completed', 'summary_output_present': True, 'structured': {'title': 'T', 'overview': 'O'}},
    {'status': 'completed', 'discarded': True},
    {'status': 'processing', 'finalization_status': 'queued'},
    {'status': 'completed', 'finalization_status': 'dead_letter'},
    {
        'status': 'completed',
        'summary_title_provenance': 'server_minimum',
        'transcript_segments': [{'text': 'Durable text'}],
    },
    {'status': 'completed', 'deleted': True, 'sync_merged_into': 'other'},
]


def fail(*args, **kwargs):
    raise RuntimeError('synthetic shadow failure')


def counter(reader):
    return phase_shadow.ERRORS.labels(reader)._value.get()


@pytest.fixture
def no_firestore(monkeypatch):
    """A strict fixture spy fails even on reference construction: zero new IO."""
    store = StrictFirestore()
    blocked = Mock(side_effect=AssertionError('unexpected Firestore access'))
    for name in ('collection', 'document', 'transaction', 'get_all'):
        monkeypatch.setattr(store, name, blocked)
    monkeypatch.setattr(_client, 'get_firestore_client', blocked)
    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(processing_attention, 'db', store)
    yield blocked
    blocked.assert_not_called()


@pytest.mark.parametrize('reader', ['home_visibility', 'settling_hold', 'summary_repair', 'episode_composer'])
def test_predicates_match_without_shadow_with_shadow_and_with_derivation_failure(monkeypatch, no_firestore, reader):
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'true')
    monkeypatch.setenv('EPISODE_COMPOSER', 'on')
    fn = {
        'home_visibility': conversations.is_visible_conversation,
        'settling_hold': fragment_visibility.is_settling_fragment,
        'summary_repair': summary_delivery.refusal,
        'episode_composer': composer.needs_compose,
    }[reader]
    rows = (
        ROWS
        if reader != 'episode_composer'
        else [
            {'status': 'live'},
            {'status': 'closed'},
            {'status': 'closed', 'composed_fingerprint': 'fp', 'summary_needs_regeneration': True},
            {'status': 'closed', 'composed_fingerprint': 'fp', 'composed_notes': 'old'},
            {'status': 'closed', 'recorded_merged_into': 'ep2'},
        ]
    )
    for fixture in rows:
        row = {'started_at': T0, 'finished_at': T0 + timedelta(seconds=30), **fixture}
        before = deepcopy(row)
        kwargs = {'now': T0.timestamp() + 60} if reader == 'settling_hold' else {}
        expected = fn.__wrapped__(row, **kwargs)
        monkeypatch.setenv('PHASE_SHADOW_ENABLED', 'false')
        assert fn(row, **kwargs) == expected
        errors = counter(reader)
        monkeypatch.setenv('PHASE_SHADOW_ENABLED', 'true')
        assert fn(row, **kwargs) == expected
        assert counter(reader) == errors
        with monkeypatch.context() as ctx:
            ctx.setattr(phase_shadow, 'derive_conversation_phase', fail)
            ctx.setattr(phase_shadow, 'derive_episode_phase', fail)
            assert fn(row, **kwargs) == expected
        assert counter(reader) == errors + 1
        assert row == before


@pytest.mark.parametrize('list_row', [False, True])
def test_episode_member_projection_is_identical(monkeypatch, no_firestore, list_row):
    rows = {
        str(i): {'id': str(i), 'started_at': T0, 'finished_at': T0 + timedelta(seconds=30), **row}
        for i, row in enumerate(ROWS)
    }
    episode = {'id': 'ep', 'status': 'closed', 'started_at': T0, 'conversation_ids': list(rows)}
    before = deepcopy((episode, rows))
    monkeypatch.setenv('PHASE_SHADOW_ENABLED', 'false')
    expected = home_read.project_episode('u', episode, members=rows, list_row=list_row)
    monkeypatch.setenv('PHASE_SHADOW_ENABLED', 'true')
    assert home_read.project_episode('u', episode, members=rows, list_row=list_row) == expected
    errors = counter('episode_member')
    monkeypatch.setattr(phase_shadow, 'derive_conversation_phase', fail)
    assert home_read.project_episode('u', episode, members=rows, list_row=list_row) == expected
    assert counter('episode_member') == errors + len(rows)
    assert (episode, rows) == before


def test_attention_projection_is_identical_and_reuses_the_same_query_footprint(monkeypatch):
    # Compare the complete footprint: three candidate sources with Home projection on, one off.
    store = Mock()
    query = store.collection.return_value.document.return_value.collection.return_value
    query.where.return_value.limit.return_value.stream.side_effect = lambda: iter(
        SimpleNamespace(id=str(i), to_dict=lambda row=row: deepcopy(row)) for i, row in enumerate(ROWS)
    )
    monkeypatch.setattr(processing_attention, 'db', store)

    def read(mode):
        monkeypatch.setenv('PHASE_SHADOW_ENABLED', mode)
        store.reset_mock()
        result = processing_attention.pending_conversations('u')
        return result, [call[0] for call in store.mock_calls]

    expected, calls = read('false')
    assert read('true') == (expected, calls)
    errors = counter('processing_attention')
    monkeypatch.setattr(phase_shadow, 'derive_conversation_phase', fail)
    assert read('true') == (expected, calls)
    assert counter('processing_attention') == errors + len(ROWS)


@pytest.mark.asyncio
@pytest.mark.parametrize('closed', [False, True])
async def test_admission_barrier_result_and_io_are_identical(monkeypatch, closed):
    row = {**ROWS[0], 'record_audio_closed': closed}
    store = StrictFirestore({('users', 'u', 'conversations', 'c'): row})
    get = Mock(wraps=store.collection('users').document('u').collection('conversations').document('c').get)
    client = Mock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value.get = get
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    # Stop immediately AFTER the legacy barrier, before any audio staging. A sentinel
    # proves the accepted branch still advances and the refused branch does not.
    staging = Mock(side_effect=RuntimeError('legacy staging reached'))
    monkeypatch.setattr(live, 'create_storage_client', staging)

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(live, 'run_blocking', run_blocking)
    pending = {'owner_id': 'u', 'conversation_id': 'c', 'record_snapshot': row, 'record_content_id': 'content'}
    results = []
    errors = counter('batch_admission')
    for mode in ('false', 'true', 'raising'):
        monkeypatch.setenv('PHASE_SHADOW_ENABLED', 'false' if mode == 'false' else 'true')
        if mode == 'raising':
            monkeypatch.setattr(phase_shadow, 'derive_conversation_phase', fail)
        client.reset_mock()
        get.reset_mock()
        staging.reset_mock()
        with pytest.raises((ValueError, RuntimeError)) as caught:
            await live.admit_recording(SimpleNamespace(client=client), pending, now=100)
        results.append(
            (type(caught.value), str(caught.value), list(client.mock_calls), get.call_count, staging.call_count)
        )
    assert counter('batch_admission') == errors + 1
    assert results[0] == results[1] == results[2]
    assert results[0][3:] == (1, int(closed))
    assert store.rows[('users', 'u', 'conversations', 'c')] == row
