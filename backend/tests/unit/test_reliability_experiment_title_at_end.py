"""Experiment ``title_at_end``: an open conversation is not named before it ends.

On main an open conversation that holds three minutes of speech gets a one-off title from a small
model call (``CONVERSATIONS_V3_LIVE_TITLE``, default on), so a conversation still being recorded reads
as if it were already summarised. On, that step does nothing: no attempt is claimed on the row, no
model is called, no title is written, and the outline names the conversation when it ends. Off (the
default) the step runs exactly as on main.
"""

import pytest

from config import reliability_experiments
from utils.conversations.v3 import service

EXPERIMENT = 'title_at_end'
UID = 'owner-1'


def speech(count, step=30.0):
    return [
        {'id': f's{i}', 'text': 'word ' * 12, 'start': i * step, 'end': i * step + step - 2, 'is_user': True}
        for i in range(count)
    ]


def open_row():
    # Eight half-minute lines: past the three minutes of speech the live title waits for.
    return {'id': 'open', 'sync_content_revision': 3, 'transcript_segments': speech(8)}


@pytest.fixture
def calls(monkeypatch):
    """Every store call and model call the step makes, in order."""
    seen = []

    async def run_blocking(executor, function, *args, **kwargs):
        seen.append(('store', getattr(function, '__name__', str(function)), kwargs.get('title')))
        return True

    async def leased_work(uid, key, token, executor, function, *args):
        seen.append(('model', getattr(function, '__name__', str(function)), None))
        return 'Launch plan review'

    monkeypatch.setattr(service, 'run_blocking', run_blocking)
    monkeypatch.setattr(service, 'leased_work', leased_work)
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_TITLE', 'on')
    return seen


def test_the_experiment_is_registered_and_off_by_default(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    assert EXPERIMENT in reliability_experiments.EXPERIMENTS
    assert not reliability_experiments.enabled(EXPERIMENT)


@pytest.mark.asyncio
async def test_off_an_open_conversation_is_named_as_on_main(monkeypatch, calls):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)

    await service._maybe_publish_live_title(UID, 'builder', 'token', open_row())

    assert calls == [
        ('store', 'write_live_title_preview', None),
        ('model', 'live_title', None),
        ('store', 'write_live_title_preview', 'Launch plan review'),
    ]


@pytest.mark.asyncio
async def test_on_nothing_is_claimed_called_or_written(monkeypatch, calls):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)

    await service._maybe_publish_live_title(UID, 'builder', 'token', open_row())

    assert calls == []
