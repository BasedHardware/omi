"""Synthetic summary freshness, writer lease and chat-compatible frame contracts."""

from database import conversations_v3_leases as leases

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from utils.conversations.v3 import summary
from utils.conversations import process_conversation as process
from models.structured import Structured
from routers import conversations as routes

AT = datetime(2026, 11, 16, tzinfo=timezone.utc)


def test_section_frames_carry_newlines_as_the_chat_crlf_marker():
    frame = summary.section_frame('## Decisions\n- Ship Friday\n- Freeze Thursday')
    assert frame == 'data: ## Decisions__CRLF__- Ship Friday__CRLF__- Freeze Thursday\n\n'
    assert '\\n' not in frame


def test_on_open_summary_refresh_threshold():
    assert summary.fresh({'summary_covers_through': AT, 'finished_at': AT + timedelta(minutes=5)}) is False
    assert (
        summary.fresh({'summary_covers_through': AT, 'finished_at': AT + timedelta(minutes=5, microseconds=-1)}) is True
    )
    assert summary.fresh({'finished_at': AT}) is False


@pytest.mark.asyncio
async def test_stored_summary_returns_chat_done_without_a_writer(monkeypatch):
    monkeypatch.setattr(leases, 'acquire', lambda *a: pytest.fail('fresh summary acquired a writer'))
    row = {'structured': {'title': 'Stable'}, 'summary_covers_through': AT, 'finished_at': AT}
    frames = [frame async for frame in summary.stream('synthetic', row)]
    assert len(frames) == 1 and frames[0].startswith('done: ')
    payload = json.loads(base64.b64decode(frames[0][6:].strip()))
    assert payload['structured']['title'] == 'Stable'


@pytest.mark.asyncio
async def test_competing_writer_returns_pollable_error(monkeypatch):
    from fastapi import HTTPException

    async def blocking(pool, fn, *args, **kwargs):
        return None

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    with pytest.raises(HTTPException) as error:
        await summary.prepare('synthetic', {'id': 'c'})
    assert error.value.status_code == 409
    assert error.value.detail == 'summary_in_progress'


@pytest.mark.asyncio
@pytest.mark.parametrize('exhausted', [True, False])
async def test_on_open_respects_the_custom_stt_paid_notes_allowance(monkeypatch, exhausted):
    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'should_skip_omi_paid_postprocessing', lambda *a, **kw: exhausted)
    monkeypatch.setattr(leases, 'acquire', lambda *a: 'token')
    row = {'id': 'c', 'uses_custom_stt': True, 'source': 'omi', 'transcript_segments': [{'text': 'word ' * 400}]}
    assert await summary.prepare('u', row) == (None if exhausted else 'token')


@pytest.mark.asyncio
async def test_refused_custom_stt_stream_serves_stored_row_without_model_work(monkeypatch):
    """The route hands stream() the refused prepare() result; consuming it must spend no notes call."""

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'should_skip_omi_paid_postprocessing', lambda *a, **kw: True)
    monkeypatch.setattr(leases, 'acquire', lambda *a: pytest.fail('refused summary acquired a writer'))
    monkeypatch.setattr(summary, 'write', lambda *a, **kw: pytest.fail('refused summary ran the notes model'))
    row = {
        'id': 'c',
        'uses_custom_stt': True,
        'source': 'omi',
        'finished_at': AT,
        'structured': {'title': 'Stored'},
        'transcript_segments': [{'text': 'word ' * 400}],
    }
    token = await summary.prepare('u', row)
    frames = [frame async for frame in summary.stream('u', row, token=token)]
    assert len(frames) == 1 and frames[0].startswith('done: ')
    assert json.loads(base64.b64decode(frames[0][6:].strip()))['structured']['title'] == 'Stored'


def test_on_open_done_uses_the_locked_row_title(monkeypatch):
    monkeypatch.setattr(
        process, '_get_structured', lambda *a, **kw: (Structured(title='Model replacement', emoji='🔧'), False)
    )
    row = {
        'id': 'c',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT,
        'title_locked': True,
        'structured': {'title': 'Original', 'emoji': '🌳'},
    }
    result = summary.write('synthetic', row, lambda text: None)
    assert result['title'] == 'Original' and result['emoji'] == '🌳'


@pytest.mark.asyncio
async def test_short_on_open_does_not_store_empty_outline_as_fresh(monkeypatch):
    monkeypatch.setattr(leases, 'acquire', lambda *a: pytest.fail('short summary model lease'))
    row = {
        'id': 'c',
        'v3_derived': True,
        'kind': 'conversation',
        'transcript_segments': [{'text': 'word ' * 299}],
        'structured': {'sections': [{'heading': 'Plan', 'body_markdown': ''}]},
    }
    assert await summary.prepare('u', row) is None
    frames = [f async for f in summary.stream('u', row)]
    assert len(frames) == 1 and frames[0].startswith('done: ')
    assert 'summary_covers_through' not in row


def test_v3_short_path_obeys_content_minimum(monkeypatch):
    from models.conversation import Conversation

    minimum = Structured(title='Noise minimum')
    monkeypatch.setattr(process, 'is_release_probe_uid', lambda uid: False)
    monkeypatch.setattr(process, 'content_minimum', lambda *a, **kw: minimum)
    monkeypatch.setattr(process, 'noise_hidden_from_home', lambda *a, **kw: False)
    monkeypatch.setattr(process.v3_service.models, 'short_tasks', lambda *a: pytest.fail('noise bought tasks'))
    row = Conversation(
        id='c',
        created_at=AT,
        started_at=AT,
        finished_at=AT,
        v3_derived=True,
        structured={},
        transcript_segments=[{'text': 'noise ' * 350, 'start': 0, 'end': 10, 'is_user': True}],
    )
    assert process._get_structured('u', 'en', row)[0].title == 'Noise minimum'


@pytest.mark.parametrize(
    'words,covered,foreground,expect_short',
    [(299, False, False, True), (300, True, False, False), (599, True, False, False)],
)
def test_short_threshold_and_covered_summary(monkeypatch, words, covered, foreground, expect_short):
    from models.conversation import Conversation

    monkeypatch.setattr(process, 'content_minimum', lambda *a, **kw: None)
    monkeypatch.setattr(process, 'quiet_minimum', lambda *a, **kw: None)
    monkeypatch.setattr(process.notification_db, 'get_user_time_zone', lambda *a: 'UTC')
    monkeypatch.setattr(process, 'resolve_output_language', lambda *a: 'en')
    monkeypatch.setattr(process, 'selected_summary_app', lambda *a: False)
    calls = []
    monkeypatch.setattr(
        process.v3_service.models, 'short_tasks', lambda uid, row: calls.append(row.id) or row.structured
    )
    row = Conversation(
        id='c',
        created_at=AT,
        started_at=AT,
        finished_at=AT,
        v3_derived=True,
        summary_covers_through=AT if covered else None,
        structured={'title': 'Existing', 'sections': [{'heading': 'Plan', 'body_markdown': 'Real notes.'}]},
        transcript_segments=[{'text': 'speech ' * words, 'start': 0, 'end': 30, 'is_user': True}],
    )
    with process.v3_service.models.notes_mode('u', foreground=foreground):
        structured, _ = process._get_structured('u', 'en', row)
    assert bool(calls) is expect_short
    assert structured.sections[0].body_markdown == 'Real notes.'


@pytest.mark.asyncio
async def test_summary_renews_lease_until_model_finishes(monkeypatch):
    import asyncio
    from utils.conversations.v3 import service, renewal

    calls = []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(renewal, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'LEASE_SECONDS', 0.003)
    monkeypatch.setattr(service.leases, 'renew', lambda *a: calls.append(a))
    worker = asyncio.create_task(asyncio.sleep(0.015))
    await service.renew_until_done('u', 'summary-c', 'token', worker)
    assert len(calls) >= 2
    assert all(call == ('u', 'summary-c', 'token') for call in calls)


@pytest.mark.asyncio
async def test_summary_route_returns_409_before_streaming_response(monkeypatch):
    from fastapi import HTTPException

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: {'id': 'c'})
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)
    monkeypatch.setattr(leases, 'acquire', lambda *a: None)
    monkeypatch.setattr(routes, 'StreamingResponse', lambda *a, **kw: pytest.fail('headers already sent'))
    with pytest.raises(HTTPException) as error:
        await routes.conversation_summary_stream('c', 'u')
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_on_open_reconcile_timeout_streams_stored_row(monkeypatch):
    import asyncio
    from utils.conversations.v3 import service

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    row = {'id': 'c', 'v3_derived': True, 'status': 'in_progress', 'structured': {'title': 'Stored'}}
    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)

    released, finished = asyncio.Event(), asyncio.Event()

    async def reconcile(*a, **kw):
        try:
            await released.wait()
        finally:
            finished.set()

    original_wait = asyncio.wait_for

    async def bounded(awaitable, timeout):
        assert timeout == 8
        return await original_wait(awaitable, 0.001)

    async def prepare(uid, stored):
        assert stored is row
        return None

    monkeypatch.setattr(service, 'reconcile', reconcile)
    monkeypatch.setattr(routes.asyncio, 'wait_for', bounded)
    monkeypatch.setattr(summary, 'prepare', prepare)
    try:
        response = await routes.conversation_summary_stream('c', 'u')
        assert response.status_code == 200 and response.media_type == 'text/event-stream'
        assert not finished.is_set(), 'timeout cancelled the lease holder'
    finally:
        released.set()
        await original_wait(finished.wait(), 1)


@pytest.mark.parametrize('locked', [True, False])
def test_persisted_title_lock_wins_after_generated_title_cleanup(monkeypatch, locked):
    from models.conversation import Conversation

    row = Conversation(
        id='c',
        created_at=AT,
        started_at=AT,
        finished_at=AT,
        title_locked=locked,
        v3_derived=True,
        structured=Structured(title='Original', emoji='🌳'),
    )

    def cleaned(*args, **kwargs):
        return Structured(title='Cleaned generated title', emoji='🔧')

    monkeypatch.setattr(process, 'finish_home_salience', cleaned)
    result = process._get_conversation_obj('synthetic', Structured(title='Draft'), row)
    assert result.structured.title == ('Original' if locked else 'Cleaned generated title')
    assert result.structured.emoji == ('🌳' if locked else '🔧')


@pytest.fixture
def real_notes_seam(monkeypatch):
    from utils.conversations.v3 import context

    monkeypatch.setattr(context, 'summary', lambda *a: 'synthetic background')
    from contextlib import nullcontext
    from utils.conversations.relevance import RelevanceDecision
    from utils.conversations import llm_input_dedupe

    called = []
    monkeypatch.setattr(process, 'is_release_probe_uid', lambda *a: False)
    monkeypatch.setattr(process, 'content_minimum', lambda *a, **k: pytest.fail('intent took content minimum'))
    monkeypatch.setattr(process, 'quiet_minimum', lambda *a, **k: pytest.fail('intent took quiet minimum'))
    monkeypatch.setattr(process.v3_service.models, 'short_tasks', lambda *a: pytest.fail('intent took short path'))
    monkeypatch.setattr(process.notification_db, 'get_user_time_zone', lambda *a: 'UTC')
    monkeypatch.setattr(process, 'resolve_output_language', lambda *a: 'en')
    monkeypatch.setattr(process, 'selected_summary_app', lambda *a: False)
    monkeypatch.setattr(process, 'conversation_transcripts_for_llm', lambda *a: ('speech', 'speech', {}))
    monkeypatch.setattr(process, 'relevance_arm', lambda *a: 'legacy')
    monkeypatch.setattr(process, 'relevance_experiment_active', lambda: False)
    monkeypatch.setattr(
        process, 'decide_relevance', lambda **k: RelevanceDecision('keep', 'policy', 'user_kept', k['trigger'])
    )
    monkeypatch.setattr(process, 'before_notes', lambda *a, **k: None)
    monkeypatch.setattr(process.member_notes, 'before_model', lambda *a, **k: None)
    monkeypatch.setattr(process, 'rich_notes_inputs', lambda *a, **k: (None, None, False, None, 0))
    monkeypatch.setattr(process, 'build_conversation_prompt_prefix', lambda **k: 'synthetic prompt')
    monkeypatch.setattr(process, 'conversation_known_spellings', lambda *a: [])
    monkeypatch.setattr(process, '_fetch_dedup_candidates_for_query', lambda *a: [])
    monkeypatch.setattr(process, 'notes_agent_inputs', lambda *a: {})
    monkeypatch.setattr(process, 'track_usage', lambda *a, **k: nullcontext())

    def notes(*args, **kwargs):
        called.append(args)
        return Structured(
            title='An intentional plan',
            overview='You made a plan.',
            sections=[{'heading': 'Plan', 'body_markdown': 'Meet tomorrow.'}],
        )

    monkeypatch.setattr(llm_input_dedupe, 'notes', notes)
    return called


@pytest.mark.parametrize('words', [5, 40])
def test_manual_end_runs_real_notes_path_even_below_short_minimum(real_notes_seam, words):
    from models.conversation import Conversation

    row = Conversation(
        id='c',
        created_at=AT,
        started_at=AT,
        finished_at=AT,
        v3_derived=True,
        manual_end=True,
        kind='conversation',
        structured={},
        transcript_segments=[{'text': 'speech ' * words, 'start': 0, 'end': 10, 'is_user': False}],
    )
    assert summary.summary_eligible(row.model_dump())
    structured, discarded = process._get_structured('synthetic', 'en', row)
    assert len(real_notes_seam) == 1 and not discarded
    assert structured.title and structured.sections[0].body_markdown


def test_explicit_retry_bypasses_short_and_summary_coverage(real_notes_seam):
    from models.conversation import Conversation
    from utils.conversations.processing_trigger import ProcessingTrigger

    row = Conversation(
        id='c',
        created_at=AT,
        started_at=AT,
        finished_at=AT,
        v3_derived=True,
        kind='conversation',
        summary_covers_through=AT,
        structured={'title': 'Old outline'},
        transcript_segments=[{'text': 'speech ' * 40, 'start': 0, 'end': 10, 'is_user': True}],
    )
    result, discarded = process._get_structured('synthetic', 'en', row, trigger=ProcessingTrigger.USER_REPROCESS)
    assert len(real_notes_seam) == 1 and result.overview == 'You made a plan.' and not discarded


@pytest.mark.parametrize('outcome', ['done', 'raises', 'no_write'])
def test_product_retry_uses_own_window_and_settles_tile(monkeypatch, outcome):
    from copy import deepcopy
    from database import conversations_v3 as store, conversations_v3_processing as writers, processing_attention
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.conversations.v3 import service

    path = ('users', 'synthetic', 'conversations', 'window')
    original = {
        'id': 'window',
        'v3_derived': True,
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT,
        'kind': 'conversation',
        'status': 'completed',
        'tile_state': 'failed',
        'summary_retryable': True,
        'sync_content_revision': 1,
        'v3_process_attempts': 2,
        'structured': {'title': 'Old title'},
        'recording_pieces': [{'recording_id': 'recording', 'audio_file_id': 'f', 'start': 10, 'end': 20}],
        'transcript_segments': [{'text': 'Only this window.', 'start': 0, 'end': 10, 'is_user': True}],
    }
    client = StrictFirestore({path: deepcopy(original)})
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(writers.firestore, 'transactional', lambda body: lambda tx: body(tx))
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda uid, cid: deepcopy(client.rows[path]))
    monkeypatch.setattr(processing_attention, 'generation', lambda row: 1)
    monkeypatch.setattr(processing_attention, 'claim', lambda *a, **k: ('operation', True))
    monkeypatch.setattr(processing_attention, 'owns_live_claim', lambda *a: True)
    monkeypatch.setattr(processing_attention, 'finish', lambda *a: None)
    monkeypatch.setattr(routes, 'schedule_reprocessed_learning', lambda uid, row, *a, **k: row)
    called = []

    def processor(uid, language, row, **kwargs):
        called.append(row)
        assert row.id == 'window' and row.transcript_segments[0].text == 'Only this window.'
        assert client.rows[path]['tile_state'] == 'writing'
        assert summary.models.foreground()
        if outcome == 'raises':
            raise RuntimeError('synthetic model failure')
        row.status = 'completed'
        row.structured = Structured(title='Fresh', overview='Fresh notes from this window.')
        if outcome == 'done':
            client.rows[path].update(status='completed', structured=row.structured.model_dump())
        kwargs['persistence_observer'](outcome == 'done')
        return row

    monkeypatch.setattr(routes, 'process_conversation', service.recording_short_path(processor))
    if outcome == 'done':
        result = routes.reprocess_conversation('window', uid='synthetic')
        assert result.tile_state == 'done' and not result.summary_retryable
    else:
        with pytest.raises(RuntimeError):
            routes.reprocess_conversation('window', uid='synthetic')
    assert len(called) == 1
    assert client.rows[path]['tile_state'] == ('done' if outcome == 'done' else 'failed')
    assert client.rows[path]['status'] == 'completed'
    assert client.rows[path]['summary_retryable'] is (outcome != 'done')


@pytest.mark.asyncio
@pytest.mark.parametrize('error', ['source_changed', 'lease_lost', 'storage_unavailable'])
async def test_on_open_reconcile_errors_stream_stored_row(monkeypatch, error):
    from utils.conversations.v3 import service

    async def blocking(pool, fn, *a, **kw):
        return fn(*a, **kw)

    async def reconcile(*a, **kw):
        raise RuntimeError(error)

    row = {'id': 'c', 'v3_derived': True, 'status': 'in_progress'}
    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)
    monkeypatch.setattr(service, 'reconcile', reconcile)

    async def prepare(uid, stored):
        assert stored is row

    monkeypatch.setattr(summary, 'prepare', prepare)
    assert (await routes.conversation_summary_stream('c', 'u')).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['fresh', 'ineligible'])
async def test_early_stream_exit_releases_preacquired_summary_token(monkeypatch, reason):
    async def blocking(pool, fn, *a, **kw):
        return fn(*a, **kw)

    released = []
    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'acquire', lambda *a: 'token')
    monkeypatch.setattr(leases, 'release', lambda *a: released.append(a))
    row = {'id': 'c', 'finished_at': AT}
    token = await summary.prepare('u', row)
    if reason == 'fresh':
        row['summary_covers_through'] = AT
    else:
        row.update(v3_derived=True, kind='media')
    assert [f async for f in summary.stream('u', row, token=token)][0].startswith('done:')
    assert released == [('u', 'summary-c', 'token')]


@pytest.mark.asyncio
async def test_lease_renewal_retries_transient_failure_and_has_lifetime_cap(monkeypatch):
    import asyncio
    from utils.conversations.v3 import renewal
    from unittest.mock import AsyncMock

    attempts = []

    async def blocking(pool, fn, *a, **kw):
        return fn(*a, **kw)

    finish = asyncio.Event()
    worker = asyncio.create_task(finish.wait())

    def renew(*a):
        attempts.append(a)
        if len(attempts) == 1:
            raise OSError('synthetic transient')
        finish.set()

    monkeypatch.setattr(renewal, 'run_blocking', blocking)
    monkeypatch.setattr(renewal.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(leases, 'renew', renew)
    monkeypatch.setattr(leases, 'LEASE_SECONDS', 0.003)
    await renewal.renew_until_done('u', 'builder', 'token', worker)
    await worker
    assert len(attempts) == 2
    monkeypatch.setattr(renewal, 'MAX_RENEWAL_SECONDS', 0)
    worker = asyncio.create_task(asyncio.Event().wait())
    try:
        with pytest.raises(RuntimeError, match='lifetime_exhausted'):
            await renewal.renew_until_done('u', 'builder', 'token', worker)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_builder_keeps_lease_until_paid_outline_exits(monkeypatch):
    import asyncio
    import threading
    from utils.conversations.v3 import service, renewal

    entered, release = threading.Event(), threading.Event()
    held = []

    async def blocking(pool, fn, *a, **kw):
        if fn is service.models.outline:
            return await asyncio.to_thread(fn, *a, **kw)
        return fn(*a, **kw)

    def model(*a):
        entered.set()
        assert release.wait(3)
        return '{"conversations":[{"first_line":1,"title":"A plan","line":"A plan","kind":"conversation"}]}'

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(renewal, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'acquire', lambda *a: held.append('token') or 'token')
    monkeypatch.setattr(leases, 'renew', lambda *a: None)
    monkeypatch.setattr(leases, 'release', lambda *a: held.clear())
    monkeypatch.setattr(
        service.store,
        'load',
        lambda *a, **kw: (
            {
                'r': {
                    'id': 'r',
                    'recording': True,
                    'started_at': AT,
                    'finished_at': AT + timedelta(seconds=10),
                    'transcript_segments': [{'text': 'synthetic speech', 'start': 0, 'end': 10}],
                }
            },
            {},
            [],
        ),
    )
    monkeypatch.setattr(service.store, 'outline_attempt', lambda *a: True)
    monkeypatch.setattr(service.models, 'outline', model)
    task = asyncio.create_task(service.reconcile('u'))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.001)
        assert entered.is_set()
        task.cancel()
        await asyncio.sleep(0.005)
        assert held and not task.done()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert not held
