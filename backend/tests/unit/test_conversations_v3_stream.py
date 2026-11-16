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
    from utils.conversations.v3 import service

    calls = []

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', blocking)
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

    async def reconcile(*a, **kw):
        pytest.fail('reconcile was awaited without the time bound')

    async def bounded(awaitable, timeout):
        assert timeout == 8
        awaitable.close()
        raise asyncio.TimeoutError

    async def prepare(uid, stored):
        assert stored is row
        return None

    monkeypatch.setattr(service, 'reconcile', reconcile)
    monkeypatch.setattr(routes.asyncio, 'wait_for', bounded)
    monkeypatch.setattr(summary, 'prepare', prepare)
    response = await routes.conversation_summary_stream('c', 'u')
    assert response.status_code == 200 and response.media_type == 'text/event-stream'
