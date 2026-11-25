"""Synthetic summary freshness, writer lease and chat-compatible frame contracts."""

from database import conversations_v3_leases as leases

import base64
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from fastapi import HTTPException

import pytest

from utils.conversations.v3 import summary
from utils.conversations import process_conversation as process
from models.structured import Structured
from routers import conversations as routes
from tests.unit.test_conversations_v3_transactions import strict  # noqa: F401
from utils.conversations.v3 import service

AT = datetime(2026, 11, 16, tzinfo=timezone.utc)


@pytest.fixture
def outline_gateway(monkeypatch, stall):
    import asyncio
    import httpx

    # The first OpenAI chat client loads the SDK's entire resource package.
    # Charge that one-time import to fixture setup instead of stream execution.
    import openai.resources  # noqa: F401

    from utils.conversations.v3 import models

    class GatewayStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            chunk = {'id': 'test', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'test'}
            chunk['choices'] = [{'index': 0, 'delta': {'role': 'assistant', 'content': 'outline'}}]
            yield f'data: {json.dumps(chunk)}\n\n'.encode()
            if stall:
                await asyncio.Event().wait()
            chunk['choices'] = [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]
            yield f'data: {json.dumps(chunk)}\n\n'.encode()
            yield b'data: [DONE]\n\n'

        async def aclose(self):
            self.closed = True

    stream = GatewayStream()

    async def gateway(request):
        assert json.loads(request.content)['stream'] is True
        assert request.extensions['timeout']['read'] == 30
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'}, stream=stream)

    monkeypatch.setattr(models, 'OUTLINE_DEADLINE_SECONDS', 0.25 if stall else 5)
    monkeypatch.setattr(models, 'require_current_generated_compute', lambda *a, **kw: None)
    monkeypatch.setattr(
        models, 'DefaultAsyncHttpxClient', lambda: httpx.AsyncClient(transport=httpx.MockTransport(gateway))
    )

    return models, stream


@pytest.mark.parametrize('stall', [False, True])
def test_paid_outline_stream_deadline_discards_partial_reply_and_closes_stream(outline_gateway, stall):
    models, stream = outline_gateway
    assert models.outline('u', [('human', 'synthetic speech')]) == ('' if stall else 'outline')
    assert stream.closed


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
    monkeypatch.setattr(leases, 'acquire', lambda *a, **kw: 'token')
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
    'words,covered,expect_short',
    [(19, False, False), (20, False, True), (299, False, True), (300, True, False), (599, True, False)],
)
@pytest.mark.parametrize('word', ['speech ', '界', 'あ'])
def test_short_threshold_and_covered_summary(monkeypatch, word, words, covered, expect_short):
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
        transcript_segments=[{'text': word * words, 'start': 0, 'end': 30, 'is_user': True}],
    )
    with process.v3_service.models.notes_mode('u', foreground=False):
        structured, discarded = process._get_structured('u', 'en', row)
    assert discarded is (words < 20)
    assert bool(calls) is expect_short
    assert structured.sections[0].body_markdown == 'Real notes.'
    assert summary.summary_eligible(row.model_dump()) is (words >= 300)


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
    finish = asyncio.Event()

    def renew(*args):
        calls.append(args)
        if len(calls) == 2:
            finish.set()

    monkeypatch.setattr(service.leases, 'renew', renew)
    worker = asyncio.create_task(asyncio.wait_for(finish.wait(), timeout=2))
    await service.renew_until_done('u', 'summary-c', 'token', worker)
    assert await worker
    assert len(calls) >= 2
    assert all(call == ('u', 'summary-c', 'token') for call in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('headers', [{}, {'X-Omi-Recording-Detail': '1'}])
async def test_summary_route_returns_409_before_streaming_response(monkeypatch, headers):
    from fastapi import HTTPException

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: {'id': 'c'})
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)
    monkeypatch.setattr(leases, 'acquire', lambda *a, **kw: None)
    monkeypatch.setattr(routes, 'StreamingResponse', lambda *a, **kw: pytest.fail('headers already sent'))
    with pytest.raises(HTTPException) as error:
        await routes.conversation_summary_stream('c', 'u', request=SimpleNamespace(headers=headers))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_explicit_read_only_summary_serves_stored_row_without_paid_work(monkeypatch):
    row = {
        'id': 'c',
        'finished_at': AT,
        'summary_covers_through': AT - timedelta(minutes=10),
        'structured': {'title': 'Stored'},
    }

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)
    monkeypatch.setattr(service, 'reconcile', lambda *a, **kw: pytest.fail('ordinary read reconciled'))
    monkeypatch.setattr(summary, 'prepare', lambda *a, **kw: pytest.fail('ordinary read prepared paid work'))

    response = await routes.conversation_summary_stream(
        'c', 'u', request=SimpleNamespace(headers={'X-Omi-Recording-Detail': '0'})
    )
    (frame,) = [event async for event in response.body_iterator]
    payload = json.loads(base64.b64decode(frame[6:].strip()))
    assert payload['structured']['title'] == 'Stored'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'config, detail',
    [('uid:someone-else', 'live_recap_unavailable'), ('uid:u', 'use_live_recap_stream')],
)
async def test_legacy_summary_does_not_generate_from_live_v3_rows(monkeypatch, config, detail):
    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    row = {
        'id': 'c',
        'v3_derived': True,
        'status': 'in_progress',
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=1),
    }
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT', config)
    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: pytest.fail('legacy live touched quota'))
    monkeypatch.setattr(service, 'reconcile', lambda *a, **kw: pytest.fail('legacy live used the outline'))
    monkeypatch.setattr(summary, 'prepare', lambda *a: pytest.fail('legacy live prepared notes'))
    with pytest.raises(HTTPException) as error:
        await routes.conversation_summary_stream('c', 'u')
    assert (error.value.status_code, error.value.detail) == (404, detail)


@pytest.mark.asyncio
@pytest.mark.parametrize('becomes_live', [False, True])
async def test_legacy_summary_reconciles_other_v3_rows_and_rechecks_live_admission(monkeypatch, becomes_live):
    row = {
        'id': 'c',
        'v3_derived': True,
        'status': 'in_progress',
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=1),
        'home_hidden': True,
    }
    reconciles = []
    prepares = []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def reconcile(uid, **kwargs):
        reconciles.append((uid, kwargs))
        if becomes_live:
            row['home_hidden'] = False

    async def prepare(uid, stored, *, promote_llm):
        assert promote_llm
        prepares.append((uid, stored))

    monkeypatch.delenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT', raising=False)
    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: deepcopy(row))
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)
    monkeypatch.setattr(service, 'reconcile', reconcile)
    monkeypatch.setattr(summary, 'prepare', prepare)
    if becomes_live:
        with pytest.raises(HTTPException) as error:
            await routes.conversation_summary_stream(
                'c', 'u', request=SimpleNamespace(headers={'X-Omi-Recording-Detail': '1'})
            )
        assert (error.value.status_code, error.value.detail) == (404, 'live_recap_unavailable')
        assert not prepares
    else:
        assert (
            await routes.conversation_summary_stream(
                'c', 'u', request=SimpleNamespace(headers={'X-Omi-Recording-Detail': '1'})
            )
        ).status_code == 200
        assert prepares == [('u', row)]
    assert reconciles == [('u', {'on_open': True, 'promote_llm': True, 'conversation_id': 'c'})]


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
@pytest.mark.parametrize('reason', ['fresh', 'ineligible'])
async def test_early_stream_exit_releases_preacquired_summary_token(monkeypatch, reason):
    async def blocking(pool, fn, *a, **kw):
        return fn(*a, **kw)

    released = []
    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'acquire', lambda *a, **kw: 'token')
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
    monkeypatch.setattr(service.store, 'save_outline', lambda *a: None)
    monkeypatch.setattr(service.store, 'adoptable', lambda *a: {})
    monkeypatch.setattr(service.store, 'backoff_state', lambda *a: (None, None))
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


_LIVE_PATH = ('users', 'synthetic', 'conversations', 'live')


@pytest.fixture
def catchup(strict, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT', 'uid:synthetic')
    row = {
        'id': 'live',
        'status': 'in_progress',
        'v3_derived': True,
        'kind': 'conversation',
        'v3_recording_ids': ['raw'],
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=10),
        'transcript_segments': [{'text': 'discussion ' * 300, 'start': 0.0, 'end': 10.0}],
        '_test_revision': 1,
    }
    strict.rows[_LIVE_PATH] = row

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def exact_row(uid, cid, **kwargs):
        return deepcopy(strict.rows[('users', uid, 'conversations', cid)])

    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'run_blocking', blocking)
    monkeypatch.setattr(summary.store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(summary.store, 'decode_row', lambda uid, snapshot: snapshot.to_dict())
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', exact_row)
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)
    monkeypatch.setattr(service, 'reconcile', lambda *a, **kw: pytest.fail('catch-up ran the paid outline path'))
    monkeypatch.setattr(summary, '_wake_created', lambda *a: pytest.fail('live catch-up woke the background builder'))
    return row


async def catchup_frames():
    response = await routes.conversation_live_catchup_stream('live', 'synthetic')
    return [frame async for frame in response.body_iterator]


@pytest.mark.asyncio
async def test_live_catchup_concurrent_taps_reuse_input_and_same_clock_edits_refresh(catchup, monkeypatch):
    calls = []

    def model(uid, row, emit):
        calls.append(row['transcript_segments'][0]['text'])
        emit('Uncommitted preview fragment')
        return {'overview': 'Outcome', 'sections': [{'heading': 'Decision', 'body_markdown': 'Ship Friday.'}]}

    monkeypatch.setattr(summary, 'write', model)
    first = await routes.conversation_live_catchup_stream('live', 'synthetic')
    with pytest.raises(HTTPException) as busy:
        await routes.conversation_live_catchup_stream('live', 'synthetic')
    assert busy.value.status_code == 409
    frames = [frame async for frame in first.body_iterator]
    assert frames[-1].startswith('done:')
    assert all('Uncommitted' not in frame for frame in frames)
    assert len(calls) == 1
    assert 'structured' not in catchup and 'summary_covers_through' not in catchup
    assert 'Ship Friday.' not in catchup['v3_live_summary']['ciphertext']
    preview = routes.get_conversation_by_id(
        'live', source=None, include_discarded=None, uid='synthetic', include_translations=False
    )['live_summary']
    assert preview['structured']['sections'][0]['body_markdown'] == 'Ship Friday.'
    replay = await catchup_frames()
    assert len(replay) == 1 and replay[0].startswith('done:') and len(calls) == 1

    # A correction to the owner's notes instructions also invalidates a recap
    # even with identical transcript text and coverage.
    catchup['user_corrections'] = [{'correction': 'Use the revised project name'}]
    catchup['_test_revision'] += 1
    assert summary.writers.read_live_summary('synthetic', catchup) is None
    assert (await catchup_frames())[-1].startswith('done:') and len(calls) == 2

    # Word/clock thresholds alone cannot see this correction.
    catchup['transcript_segments'][0]['text'] = 'corrected ' * 300
    catchup['_test_revision'] += 1
    changed = await catchup_frames()
    assert changed[-1].startswith('done:') and len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'change',
    [
        'strict_append',
        'equal_boundary',
        'owner_correction_append',
        'overlap',
        'correction',
        'removed',
        'replaced',
        'ended',
    ],
)
async def test_live_catchup_publishes_only_to_the_still_eligible_covered_input(catchup, monkeypatch, change):
    def model(uid, row, emit):
        emit('Uncommitted preview fragment')
        catchup['_test_revision'] += 1
        if change == 'owner_correction_append':
            catchup['user_corrections'] = [{'correction': 'Use the revised project name'}]
            catchup['transcript_segments'].append({'text': 'New tail', 'start': 11.0, 'end': 20.0})
            catchup['finished_at'] = AT + timedelta(seconds=20)
        elif change in {'strict_append', 'equal_boundary', 'overlap'}:
            start = {'strict_append': 11.0, 'equal_boundary': 10.0, 'overlap': 9.5}[change]
            catchup['transcript_segments'].append({'text': 'New tail', 'start': start, 'end': 20.0})
            catchup['finished_at'] = AT + timedelta(seconds=20)
        elif change == 'correction':
            catchup['transcript_segments'][0]['text'] = 'Replacement'
        elif change == 'removed':
            catchup['transcript_segments'].clear()
        elif change == 'replaced':
            catchup['v3_recording_ids'] = ['successor']
            catchup['transcript_segments'].append({'text': 'Next conversation', 'start': 11.0, 'end': 20.0})
        else:
            catchup['status'] = 'completed'
        return {'overview': 'Outcome'}

    monkeypatch.setattr(summary, 'write', model)
    frames = await catchup_frames()
    assert all('Uncommitted' not in frame for frame in frames)
    if change in {'strict_append', 'equal_boundary'}:
        assert frames[-1].startswith('done:')
        preview = summary.writers.read_live_summary('synthetic', catchup)
        assert preview['summary_covers_through'] == AT + timedelta(seconds=10)
        assert catchup['finished_at'] == AT + timedelta(seconds=20)
        assert summary.writers.read_live_summary('synthetic', catchup, exact=True) is None
        assert 'summary_covers_through' not in catchup
    else:
        assert frames[-1].startswith('error:')
        assert 'v3_live_summary' not in catchup


@pytest.mark.asyncio
async def test_live_preview_drops_undecryptable_raw_cache(catchup, monkeypatch):
    monkeypatch.setattr(summary, 'write', lambda *a: {'overview': 'Live only'})
    assert (await catchup_frames())[-1].startswith('done:')
    catchup['v3_live_summary']['ciphertext'] = '{"overview":"Raw fallback text"}'
    monkeypatch.setattr(summary.writers, 'decrypt', lambda encrypted, uid: encrypted)
    assert summary.writers.read_live_summary('synthetic', catchup) is None


@pytest.mark.asyncio
async def test_live_preview_never_satisfies_the_final_notes_gate(catchup, monkeypatch):
    monkeypatch.setattr(summary, 'write', lambda *a: {'overview': 'Live only'})
    assert (await catchup_frames())[-1].startswith('done:')
    catchup['status'] = 'processing'
    assert summary.writers.read_live_summary('synthetic', catchup) is None
    assert not summary.fresh(catchup)
    token = await summary.prepare('synthetic', catchup)
    assert token
    leases.release('synthetic', 'summary-live', token)


@pytest.mark.asyncio
async def test_denied_live_catchup_never_acquires_a_lease_or_uses_old_notes(catchup, monkeypatch):
    catchup.update(uses_custom_stt=True, structured={'overview': 'Old notes'}, summary_covers_through=AT)
    monkeypatch.setattr(summary, 'should_skip_omi_paid_postprocessing', lambda *a, **kw: True)
    monkeypatch.setattr(leases, 'acquire', lambda *a: pytest.fail('denied catch-up acquired a writer'))
    monkeypatch.setattr(summary, 'write', lambda *a: pytest.fail('denied catch-up ran the notes model'))
    (frame,) = await catchup_frames()
    assert frame.startswith('error:')
    assert json.loads(frame[6:].strip()) == {'detail': 'live_recap_unavailable'}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'change', [{'status': 'completed'}, {'home_hidden': True}, {'data_protection_level': 'private'}]
)
async def test_live_catchup_stale_or_hidden_identity_is_not_available(catchup, monkeypatch, change):
    catchup.update(change)
    monkeypatch.setattr(leases, 'acquire', lambda *a: pytest.fail('refused source acquired a writer'))
    with pytest.raises(HTTPException) as error:
        await routes.conversation_live_catchup_stream('live', 'synthetic')
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_live_catchup_does_not_start_notes_after_target_closes_before_stream(catchup, monkeypatch):
    response = await routes.conversation_live_catchup_stream('live', 'synthetic')
    catchup.update(status='completed', _test_revision=2)
    monkeypatch.setattr(summary, 'write', lambda *a: pytest.fail('closed capture ran the notes model'))
    (frame,) = [event async for event in response.body_iterator]
    assert frame.startswith('error:')
    assert leases.acquire('synthetic', 'summary-live')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'config',
    [None, '', 'uid:someone-else', 'uid:synthetic,garbage', 'all', 'pct:100', 'uid:synthetic,uid:*'],
)
async def test_live_recap_cohort_refusal_never_loads_cache_or_admits_paid_work(catchup, monkeypatch, config):
    if config is None:
        monkeypatch.delenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT')
    else:
        monkeypatch.setenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT', config)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: pytest.fail('denied request read a row'))
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: pytest.fail('denied request read quota'))
    monkeypatch.setattr(summary, 'prepare', lambda *a, **kw: pytest.fail('denied request prepared notes'))
    with pytest.raises(HTTPException) as error:
        await routes.conversation_live_catchup_stream('live', 'synthetic')
    assert (error.value.status_code, error.value.detail) == (404, 'live_recap_unavailable')


@pytest.mark.asyncio
async def test_live_recap_cohort_rollback_hides_saved_preview_preserving_transcript_and_finished_notes(
    catchup, monkeypatch
):
    monkeypatch.setattr(summary, 'write', lambda *a: {'title': 'Preview', 'overview': 'Saved preview'})
    assert (await catchup_frames())[-1].startswith('done:')
    before = routes.get_conversation_by_id(
        'live', source=None, include_discarded=None, uid='synthetic', include_translations=False
    )
    assert before['live_summary']['structured']['overview'] == 'Saved preview'

    monkeypatch.delenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT')
    monkeypatch.setattr(summary.writers, 'read_live_summary', lambda *a, **kw: pytest.fail('rollback read preview'))
    monkeypatch.setattr(leases, 'acquire', lambda *a: pytest.fail('rollback acquired a lease'))
    monkeypatch.setattr(summary, 'write', lambda *a: pytest.fail('rollback ran the model'))
    hidden = routes.get_conversation_by_id(
        'live', source=None, include_discarded=None, uid='synthetic', include_translations=False
    )
    assert 'live_summary' not in hidden and 'v3_live_summary' not in hidden
    assert hidden['transcript_segments'] == before['transcript_segments']
    listing = {**catchup, 'live_summary': before['live_summary']}
    routes.redact_conversations_for_list([listing])
    assert 'live_summary' not in listing and 'v3_live_summary' not in listing

    catchup.update(
        status='completed',
        structured={'title': 'Finished', 'overview': 'Final summary'},
        summary_covers_through=catchup['finished_at'],
    )
    finished = await routes.conversation_summary_stream('live', 'synthetic')
    (frame,) = [event async for event in finished.body_iterator]
    assert frame.startswith('done:')
    assert json.loads(base64.b64decode(frame[6:].strip()))['structured']['overview'] == 'Final summary'


@pytest.mark.asyncio
@pytest.mark.parametrize('cached', [False, True])
async def test_live_recap_cohort_revoked_after_headers_yields_no_saved_or_generated_notes(catchup, monkeypatch, cached):
    if cached:
        monkeypatch.setattr(summary, 'write', lambda *a: {'title': 'Preview', 'overview': 'Cached notes'})
        assert (await catchup_frames())[-1].startswith('done:')
    response = await routes.conversation_live_catchup_stream('live', 'synthetic')
    await_before_rollback = leases.acquire('synthetic', 'summary-live')
    assert (await_before_rollback is not None) is cached
    if await_before_rollback:
        leases.release('synthetic', 'summary-live', await_before_rollback)

    monkeypatch.delenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT')
    monkeypatch.setattr(
        summary.writers, 'read_live_summary', lambda *a, **kw: pytest.fail('revoked request read cache')
    )
    monkeypatch.setattr(summary, 'write', lambda *a: pytest.fail('revoked request ran the model'))
    (frame,) = [frame async for frame in response.body_iterator]
    assert frame == 'error: {"detail":"live_recap_unavailable"}\n\n'
    released = leases.acquire('synthetic', 'summary-live')
    assert released
    leases.release('synthetic', 'summary-live', released)


@pytest.mark.parametrize('proven_final', [False, True])
def test_legacy_generated_live_sections_are_read_redacted_with_owner_overview_preserved(
    catchup, monkeypatch, proven_final
):
    legacy = {
        'overview': 'Preserve editable overview',
        'sections': [{'heading': 'Generated heading', 'body_markdown': 'Generated body'}],
    }
    catchup.update(
        structured=deepcopy(legacy),
        summary_covers_through=catchup['finished_at'],
        v3_notes_written=proven_final,
    )

    def read_detail():
        return routes.get_conversation_by_id(
            'live', source=None, include_discarded=None, uid='synthetic', include_translations=False
        )

    assert read_detail()['structured'] == legacy
    monkeypatch.delenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT')
    detail = read_detail()
    listed = deepcopy(catchup)
    routes.redact_conversations_for_list([listed])
    for row in [detail, listed]:
        assert row['structured']['overview'] == legacy['overview']
        assert ('sections' in row['structured']) is proven_final
        assert row['transcript_segments'] == catchup['transcript_segments']
    assert catchup['structured'] == legacy


@pytest.mark.parametrize('edited_overview', [False, True])
@pytest.mark.parametrize('version', ['4', '5'])
def test_completed_note_detail_repairs_uuid_citations_without_rewriting_storage(
    catchup, monkeypatch, edited_overview, version
):
    known = f'11111111-2222-{version}333-8444-555555555555'
    orphan = f'aaaaaaaa-bbbb-{version}ccc-addd-eeeeeeeeeeee'
    body = f'- The group took photos. ({orphan})\n- They shared them ({known}). (aside)'
    clean = '- The group took photos.\n- They shared them. (aside)'
    edited = f'Owner text ({orphan})'
    existing = 'existing-source'
    sources = [existing, known] if edited_overview else [existing]
    catchup.update(
        status='completed',
        v3_notes_written=True,
        structured={
            'title': 'Photos',
            'overview': edited if edited_overview else f'## Sharing\n\n{body}',
            'sections': [{'heading': 'Sharing', 'body_markdown': body, 'source_segment_ids': sources}],
        },
        transcript_segments=[
            {'id': existing, 'text': 'They took photos.', 'start': 0, 'end': 1},
            {'id': known, 'text': 'They shared them.', 'start': 1, 'end': 2},
        ],
        apps_results=[{'app_id': 'custom', 'content': edited}],
    )
    fetched = deepcopy(catchup)
    before = deepcopy(fetched)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *args, **kwargs: fetched)

    detail = routes.get_conversation_by_id(
        'live', source=None, include_discarded=None, uid='synthetic', include_translations=False
    )

    assert detail['structured']['sections'][0]['body_markdown'] == clean
    assert detail['structured']['overview'] == (edited if edited_overview else f'## Sharing\n\n{clean}')
    assert detail['structured']['sections'][0]['source_segment_ids'] == [
        segment['id'] for segment in detail['transcript_segments']
    ]
    assert detail['apps_results'] == before['apps_results']
    assert fetched['structured'] == before['structured']


@pytest.mark.asyncio
@pytest.mark.parametrize('detail_intent', [None, '1'])
async def test_summary_open_locks_configured_preview_with_live_recap_present(monkeypatch, detail_intent):
    row = {
        'id': 'c',
        'v3_derived': True,
        'v3_unlocked': True,
        'status': 'in_progress',
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=1),
    }
    reconciles = []
    prepared = []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def reconcile(uid, *, on_open, promote_llm, conversation_id):
        reconciles.append((on_open, promote_llm, conversation_id))
        row.update(status='processing', v3_unlocked=False)

    async def prepare(uid, current, *, promote_llm):
        prepared.append((promote_llm, current.copy()))

    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT', 'uid:synthetic')
    monkeypatch.setattr(routes, 'run_blocking', blocking)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    monkeypatch.setattr(routes, 'require_generated_compute', lambda *a: None)
    monkeypatch.setattr(service, 'reconcile', reconcile)
    monkeypatch.setattr(summary, 'prepare', prepare)

    headers = {} if detail_intent is None else {'X-Omi-Recording-Detail': detail_intent}
    response = await routes.conversation_summary_stream('c', 'synthetic', request=SimpleNamespace(headers=headers))
    assert response.media_type == 'text/event-stream'
    assert reconciles == [(True, detail_intent == '1', 'c')]
    assert prepared[0][0] is (detail_intent == '1')
    assert prepared[0][1]['status'] == 'processing' and not prepared[0][1]['v3_unlocked']


@pytest.mark.asyncio
@pytest.mark.parametrize('gateway_timeout', [False, True])
async def test_background_outline_sends_same_lane_and_explicit_cache_prefix(monkeypatch, gateway_timeout):
    import httpx
    from openai import AsyncOpenAI
    from utils.conversations.v3 import models, outline
    from utils.llm.gateway_client import GatewayContextChatOpenAI

    calls = []

    async def gateway(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert request.headers['x-omi-background-flex-budget-ms'] == '83000'
        assert not payload.get('stream')
        assert payload['model'] == 'omi:auto:conversation-v3-outline'
        assert payload['reasoning_effort'] == 'none'
        assert payload['response_format'] == {'type': 'json_object'}
        assert payload['prompt_cache_options'] == {'mode': 'explicit', 'ttl': '30m'}
        assert payload['messages'][0]['content'][0] == {
            'type': 'text',
            'text': outline.OUTLINE_CACHE_PREFIX,
            'prompt_cache_breakpoint': {'mode': 'explicit'},
        }
        if gateway_timeout:
            return httpx.Response(
                502,
                json={
                    'error': {
                        'message': 'provider request failed',
                        'type': 'api_error',
                        'param': None,
                        'code': 'provider_failure',
                        'failure_class': 'timeout_before_output',
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                'id': 'synthetic',
                'object': 'chat.completion',
                'created': 0,
                'model': 'omi:auto:conversation-v3-outline',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{}'}, 'finish_reason': 'stop'}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(gateway)) as transport:
        async_client = AsyncOpenAI(
            api_key='test', base_url='http://gateway.invalid/v1', http_client=transport, max_retries=0
        )
        model = GatewayContextChatOpenAI(
            api_key='test',
            model='omi:auto:conversation-v3-outline',
            root_async_client=async_client,
            async_client=async_client.chat.completions,
        )
        monkeypatch.setattr(models, 'get_or_create_omi_gateway_llm', lambda *a, **kw: model)
        messages = [('system', outline.OUTLINE_CACHE_PREFIX), ('human', 'Synthetic speech')]

        async def claim():
            return 83_000

        assert await models.background_outline('u', messages, claim=claim) == ('' if gateway_timeout else '{}')
        assert len(calls) == 1


def test_outline_only_budgets_finished_automatic_stretches_with_publication_headroom():
    from time import monotonic

    now = datetime.now(timezone.utc)
    group = {'finished': True, 'manual_end': False, 'end': now - timedelta(minutes=5)}
    budget_deadline = monotonic() + 100
    assert 99_000 < service._outline_flex_budget(group, budget_deadline) <= 100_000
    assert service._outline_flex_budget(group, None) == 0
    assert service._outline_flex_budget({**group, 'finished': False}, budget_deadline) == 0
    assert service._outline_flex_budget({**group, 'manual_end': True}, budget_deadline) == 0
    assert service._outline_flex_budget({**group, 'end': now - timedelta(hours=2)}, budget_deadline) < 0


@pytest.mark.asyncio
@pytest.mark.parametrize('foreground', [False, True])
async def test_summary_model_marks_only_the_background_attempt_preemptible(monkeypatch, foreground):
    from utils.conversations.v3 import models
    from utils.llm import background_flex

    marks = []

    async def blocking(_pool, fn, *args):
        return fn(*args)

    monkeypatch.setattr(models, 'run_blocking', blocking)
    monkeypatch.setattr(leases, 'mark_llm_preemptible', lambda *_args: marks.append(_args))
    now = datetime.now(timezone.utc)
    with models.notes_mode('u', foreground=foreground, background_lease=('c', 'token', now)):
        async with models.summary_model_attempt():
            if foreground:
                assert marks == []
                assert background_flex.budget_ms('conversation_v3_summary') == 0
            else:
                assert marks == [('u', 'summary-c', 'token', True)]
                assert background_flex.budget_ms('conversation_v3_summary') > 54_000
    assert marks == ([] if foreground else [('u', 'summary-c', 'token', True), ('u', 'summary-c', 'token', False)])
    assert background_flex.budget_ms('conversation_v3_summary') == 0
