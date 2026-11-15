"""Late intake reply regressions, derived from the persistrca failing repro.

Exercise the production assignment encode/invalidate and normal read decoder;
only the external post-commit effects and Firestore transport are isolated.
"""

from datetime import datetime, timedelta, timezone
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.cloud.firestore_v1.transforms import Sentinel

from database import conversations as conversations_db
from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment
from routers.listen import transcripts
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_live_oversized_persist_recovery import _processor, _raw_segments, _run_until
from utils.episodes import finalize as episode_finalize
from utils.sync import late_audio

T0 = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


@pytest.fixture
def intake(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'stop_quiet_check_for_conversation', lambda *a, **k: None)
    monkeypatch.setattr(conversations_db, 'index_sync_assignment', lambda *a, **k: None)
    monkeypatch.setattr(conversations_db, 'db', store)
    monkeypatch.setattr(late_audio.outbox, 'mark', lambda *a, **k: None)
    monkeypatch.setattr(episode_finalize, 'schedule_synced_intake_attach', lambda *a: None)
    calls = []

    def assign(uid, incoming):
        # A stable candidate exercises create first, then its idempotent update.
        result = conversations_db.assign_sync_conversation(
            uid, incoming, target_id=calls[0][0]['id'] if calls else None, firestore_client=store
        )
        calls.append(result)
        # StrictFirestore deliberately does not model server transforms. Apply
        # the delete transform generically, without a protected-field allowlist.
        for path, row in store.rows.items():
            if len(path) != 4 or path[2] != 'conversations':
                continue
            for key, value in list(row.items()):
                if isinstance(value, Sentinel):
                    assert value.description == 'Value used to delete a field in a document.'
                    row.pop(key)
            row['has_photos'] = False
        return result

    monkeypatch.setattr(late_audio.lifecycle, 'ingest_sync_conversation', assign)
    return store, calls


def processor(level='standard', *, v2=False):
    async def call(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    p = object.__new__(transcripts.TranscriptProcessor)
    p.host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        state=SimpleNamespace(capture_timeline_v2=v2),
        persistence=SimpleNamespace(call=call),
    )
    p.cache = SimpleNamespace(protection_level=level)
    p._v2_committed_ids = set()
    return p


def live():
    return Conversation(
        id='live-generation',
        created_at=T0,
        started_at=T0,
        finished_at=None,
        status='in_progress',
        source='omi',
        structured={'title': 'Recording'},
    )


def speech():
    return [TranscriptSegment(id='late-word', start=5, end=20, text='Historical synthetic words.', is_user=False)]


@pytest.mark.asyncio
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
async def test_create_update_and_dedupe_reply_use_real_codec(intake, level):
    store, calls = intake
    p = processor(level)
    first, _, _ = await p._update_live_conversation(live(), speech(), [], T0 + timedelta(hours=2), T0)
    assert calls[0][1] is True
    path = ('users', 'u', 'conversations', first.id)
    stored = store.rows[path]
    assert isinstance(stored['transcript_segments'], bytes if level == 'standard' else str)
    # Add both historically problematic fields through the production encoder.
    row = conversations_db.get_conversation('u', first.id)
    corrections = [{'kind': 'text', 'text': 'Synthetic correction'}]
    row['user_corrections'] = corrections
    row['client_processing'] = {'old_projection': True}
    store.rows[path] = conversations_db._prepare_conversation_for_write(row, 'u', level)
    assert isinstance(store.rows[path]['user_corrections'], bytes if level == 'standard' else str)
    more_speech = [
        *speech(),
        TranscriptSegment(id='later-word', start=25, end=30, text='More synthetic speech.', is_user=False),
    ]
    second, _, _ = await p._update_live_conversation(live(), more_speech, [], T0 + timedelta(hours=2), T0)
    assert calls[1][1] is False
    # Real invalidation writes a transform; the logical return can still carry
    # the obsolete projection and opaque retained corrections. Neither is a reply.
    patches = [patch for tx in store.transactions for target, patch in tx.updates if target == path]
    assert isinstance(patches[-1]['client_processing'], Sentinel)
    assert second.id == first.id
    assert second.client_processing is None
    assert second.user_corrections == corrections
    assert [s.id for s in second.transcript_segments] == ['late-word', 'later-word']
    assert second.transcript_segments[0].text == 'Historical synthetic words.'
    retry, _, _ = await p._update_live_conversation(live(), more_speech, [], T0 + timedelta(hours=2), T0)
    assert [s.id for s in retry.transcript_segments] == ['late-word', 'later-word']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['read', 'missing', 'validation'])
@pytest.mark.parametrize('v2', [False, True])
async def test_reply_failure_is_explicitly_post_commit(intake, monkeypatch, fault, v2):
    store, calls = intake
    p = processor(v2=v2)

    def failed_read(*a, **k):
        if fault == 'read':
            raise RuntimeError('read unavailable')
        return None if fault == 'missing' else {'client_processing': 'invalid'}

    monkeypatch.setattr(conversations_db, 'get_conversation', failed_read)
    with pytest.raises(transcripts.LateTranscriptReplyError):
        await p._update_live_conversation(live(), speech(), [], T0 + timedelta(hours=2), T0)
    assert len(calls) == 1
    assert store.rows[('users', 'u', 'conversations', calls[0][0]['id'])]
    assert p._v2_committed_ids == ({'late-word'} if v2 else set())


@pytest.mark.asyncio
@pytest.mark.parametrize('committed', [False, True])
async def test_loop_only_requeues_write_failures(monkeypatch, committed):
    attempts = []

    async def update(*args):
        attempts.append(True)
        if committed:
            raise transcripts.LateTranscriptReplyError()
        raise RuntimeError('write unavailable')

    p, _, clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=AsyncMock())
    await _run_until(p, clock, lambda: len(attempts) >= (1 if committed else 2))
    assert len(p.segment_buffer) == (0 if committed else 1)
    assert len(attempts) == (1 if committed else 2)


@pytest.mark.asyncio
async def test_v2_drain_does_not_reroute_committed_reply_failure(intake, monkeypatch):
    _, calls = intake
    p = processor(v2=True)
    p.segment_buffer = deque()
    p.host.state.current_conversation_id = live().id
    p.host.state.conversation_capture_origins = {}
    p.host.onboarding_handler = None
    p.cache.get = AsyncMock(return_value={**live().model_dump(), 'audio_timeline': {'version': 2}})
    p.speaker_id_allocator = SimpleNamespace(
        hydrate=lambda *a: None, hydrate_receipt=lambda *a: None, assign=lambda *a: None
    )
    p._reroute_unplaced = AsyncMock()
    p._deliver_live_updates = AsyncMock()
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda *a, **kw: None)
    monkeypatch.setattr(transcripts, 'datetime', SimpleNamespace(now=lambda *a: T0 + timedelta(hours=2)))
    raw = speech()[0].model_dump()
    raw.pop('speech_profile_processed')
    raw['_conversation_id'] = live().id
    raw['start'] += T0.timestamp()
    raw['end'] += T0.timestamp()
    await p._process_v2_batches([raw], [], {})
    assert len(calls) == 1
    assert p._v2_committed_ids == {'late-word'}
    p._reroute_unplaced.assert_not_called()
    p._deliver_live_updates.assert_not_called()
