"""Synthetic summary freshness, writer lease and chat-compatible frame contracts."""

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from utils.conversations.v3 import summary
from utils.conversations import process_conversation as process
from models.structured import Structured

AT = datetime(2026, 11, 16, tzinfo=timezone.utc)


def test_on_open_summary_refresh_threshold():
    assert summary.fresh({'summary_covers_through': AT, 'finished_at': AT + timedelta(minutes=5)}) is False
    assert (
        summary.fresh({'summary_covers_through': AT, 'finished_at': AT + timedelta(minutes=5, microseconds=-1)}) is True
    )
    assert summary.fresh({'finished_at': AT}) is False


@pytest.mark.asyncio
async def test_stored_summary_returns_chat_done_without_a_writer(monkeypatch):
    monkeypatch.setattr(summary.store, 'acquire', lambda *a: pytest.fail('fresh summary acquired a writer'))
    row = {'structured': {'title': 'Stable'}, 'summary_covers_through': AT, 'finished_at': AT}
    frames = [frame async for frame in summary.stream('synthetic', row)]
    assert len(frames) == 1 and frames[0].startswith('done: ')
    payload = json.loads(base64.b64decode(frames[0][6:].strip()))
    assert payload['structured']['title'] == 'Stable'


@pytest.mark.asyncio
async def test_competing_writer_returns_pollable_error(monkeypatch):
    async def blocking(pool, fn, *args, **kwargs):
        return None

    monkeypatch.setattr(summary, 'run_blocking', blocking)
    frames = [frame async for frame in summary.stream('synthetic', {'id': 'c'})]
    assert frames == ['error: {"detail":"Summary is being written; poll conversation detail"}\n\n']


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
