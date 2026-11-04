"""The oversized-rollover probe must bind only a real awaitable escape.

``transcripts.process_loop``'s oversized-persist arm probes
``host.conversations.rollover_after_transcript_decode_failure`` as the
generation escape for a conversation whose every content write is permanently
rejected. The old ``callable(escape)`` guard awaited whatever callable it
found: a mistyped attribute (a plain callable from a test double or a future
refactor) raised ``TypeError: object ... can't be used in 'await' expression``
inside the probe, the probe's error arm swallowed it, and the session never
took the proven plain-rollover fallback — the over-limit conversation kept
burning persist attempts on every probe window.

Fix (PR #24592 review item): a typed resolver (``_resolve_rollover_escape``)
binds coroutine functions only; any other attribute shape resolves to ``None``
and the loop falls back to ``create_new_in_progress_conversation(rollover=True)``.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from functools import partial
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import InvalidArgument

from database import conversations as db
from routers.listen import transcripts
from tests.unit.test_live_oversized_persist_recovery import (
    _processor as _base_processor,
    _raw_segments,
    _run_until,
)
from tests.unit.test_manual_speaker_assignments import world


async def _proper_escape() -> None:
    return None


def test_coroutine_function_is_bound():
    conversations = SimpleNamespace(rollover_after_transcript_decode_failure=_proper_escape)
    assert transcripts._resolve_rollover_escape(conversations) is _proper_escape


def test_bound_async_method_is_bound():
    class _Controller:
        async def rollover_after_transcript_decode_failure(self) -> None:
            return None

    conversations = SimpleNamespace(
        rollover_after_transcript_decode_failure=_Controller().rollover_after_transcript_decode_failure
    )
    bound = transcripts._resolve_rollover_escape(conversations)
    assert bound is not None
    assert asyncio.iscoroutinefunction(bound)


def test_partial_of_coroutine_function_is_bound():
    conversations = SimpleNamespace(rollover_after_transcript_decode_failure=partial(_proper_escape))
    assert transcripts._resolve_rollover_escape(conversations) is not None


def test_plain_callable_resolves_to_none():
    conversations = SimpleNamespace(rollover_after_transcript_decode_failure=lambda: None)
    assert transcripts._resolve_rollover_escape(conversations) is None


def test_non_callable_resolves_to_none():
    conversations = SimpleNamespace(rollover_after_transcript_decode_failure=object())
    assert transcripts._resolve_rollover_escape(conversations) is None


def test_absent_attribute_resolves_to_none():
    assert transcripts._resolve_rollover_escape(SimpleNamespace()) is None


def test_none_attribute_resolves_to_none():
    conversations = SimpleNamespace(rollover_after_transcript_decode_failure=None)
    assert transcripts._resolve_rollover_escape(conversations) is None


# ---------------------------------------------------------------------------
# Probe selection inside the loop (the oversized-persist harness).
# ---------------------------------------------------------------------------


def _size_limit_error() -> InvalidArgument:
    return InvalidArgument(
        "Document 'projects/based-hardware/databases/(default)/documents/users/uid/conversations/conv' "
        'cannot be written because its size (1,069,442 bytes) exceeds the maximum allowed size of '
        '1,048,576 bytes.'
    )


@pytest.mark.asyncio
async def test_mistyped_plain_callable_escape_takes_the_plain_rollover_fallback(world, monkeypatch):
    """A plain-callable escape attr must route to the plain rollover fallback.

    Pre-fix, the oversized arm's probe awaited the plain callable, burned on a
    swallowed ``TypeError``, and never escaped; the fallback below never ran and
    the drain never landed on a fresh generation.
    """
    store, old_path, _ = world
    fresh_path = (*old_path[:-1], 'fresh')
    original = deepcopy(store.rows[old_path])
    attempts: list[str] = []
    commits: list[tuple[str, list[str]]] = []
    fallback_calls: list[int] = []
    retained = _raw_segments(8)

    async def update(_conversation, segments, _photos, _finished, _started):
        owner = state.current_conversation_id
        attempts.append(owner)
        if owner == 'c':
            raise _size_limit_error()
        incoming = [dict(id=s.id, text=s.text, start=s.start, end=s.end, is_user=False) for s in segments]
        db.update_conversation_segments('u', owner, [], live_segments=incoming)
        commits.append((owner, [s.id for s in segments]))
        return SimpleNamespace(id=owner), [], []

    async def rollover(**kwargs):
        assert kwargs == {'rollover': True}
        fallback_calls.append(len(attempts))
        store.rows[fresh_path] = dict(id='fresh', status='in_progress', transcript_segments=[])
        state.current_conversation_id = 'fresh'

    processor, state, clock = _base_processor(
        monkeypatch, segments=deepcopy(retained), update=update, rollover=rollover
    )
    processor.host.conversations.rollover_after_transcript_decode_failure = lambda: None
    state.current_conversation_id = 'c'
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, clock, lambda: bool(commits), max_ticks=250)

    assert fallback_calls, 'a mistyped escape must fall back to the plain rollover'
    committed_ids = [seg_id for _owner, ids in commits for seg_id in ids]
    assert committed_ids, 'the drain must land on the fresh generation'
    assert commits[-1][0] == 'fresh'
    # The oversized arm may shrink the retained batch before the probe fires;
    # whatever escapes must be exactly once, on the fresh generation.
    assert set(committed_ids) <= {raw['id'] for raw in retained}
    assert len(committed_ids) == len(set(committed_ids)), 'no speech replayed or duplicated'
    assert not processor.segment_buffer
    assert store.rows[old_path] == original


@pytest.mark.asyncio
async def test_coroutine_escape_is_used_and_fallback_is_not(world, monkeypatch):
    store, old_path, _ = world
    fresh_path = (*old_path[:-1], 'fresh')
    attempts: list[str] = []
    commits: list[tuple[str, list[str]]] = []
    escape_calls: list[int] = []
    fallback_calls: list[int] = []
    retained = _raw_segments(8)

    async def update(_conversation, segments, _photos, _finished, _started):
        owner = state.current_conversation_id
        attempts.append(owner)
        if owner == 'c':
            raise _size_limit_error()
        incoming = [dict(id=s.id, text=s.text, start=s.start, end=s.end, is_user=False) for s in segments]
        db.update_conversation_segments('u', owner, [], live_segments=incoming)
        commits.append((owner, [s.id for s in segments]))
        return SimpleNamespace(id=owner), [], []

    async def rollover(**kwargs):
        fallback_calls.append(kwargs)

    async def escape():
        escape_calls.append(len(attempts))
        store.rows[fresh_path] = dict(id='fresh', status='in_progress', transcript_segments=[])
        state.current_conversation_id = 'fresh'

    processor, state, clock = _base_processor(
        monkeypatch, segments=deepcopy(retained), update=update, rollover=rollover
    )
    processor.host.conversations.rollover_after_transcript_decode_failure = escape
    state.current_conversation_id = 'c'
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, clock, lambda: bool(commits), max_ticks=250)

    assert escape_calls, 'the bound coroutine escape is the production shape'
    assert fallback_calls == []
    committed_ids = [seg_id for _owner, ids in commits for seg_id in ids]
    assert committed_ids, 'the drain must land on the fresh generation'
    assert commits[-1][0] == 'fresh'
    assert set(committed_ids) <= {raw['id'] for raw in retained}
    assert len(committed_ids) == len(set(committed_ids)), 'no speech replayed or duplicated'


@pytest.mark.asyncio
async def test_non_callable_escape_attr_also_takes_the_fallback(world, monkeypatch):
    store, old_path, _ = world
    fresh_path = (*old_path[:-1], 'fresh')
    attempts: list[str] = []
    commits: list[tuple[str, list[str]]] = []
    fallback_calls: list[int] = []
    retained = _raw_segments(8)

    async def update(_conversation, segments, _photos, _finished, _started):
        owner = state.current_conversation_id
        attempts.append(owner)
        if owner == 'c':
            raise _size_limit_error()
        incoming = [dict(id=s.id, text=s.text, start=s.start, end=s.end, is_user=False) for s in segments]
        db.update_conversation_segments('u', owner, [], live_segments=incoming)
        commits.append((owner, [s.id for s in segments]))
        return SimpleNamespace(id=owner), [], []

    async def rollover(**kwargs):
        assert kwargs == {'rollover': True}
        fallback_calls.append(len(attempts))
        store.rows[fresh_path] = dict(id='fresh', status='in_progress', transcript_segments=[])
        state.current_conversation_id = 'fresh'

    processor, state, clock = _base_processor(
        monkeypatch, segments=deepcopy(retained), update=update, rollover=rollover
    )
    processor.host.conversations.rollover_after_transcript_decode_failure = object()
    state.current_conversation_id = 'c'
    processor._oversized_rollover_probe_at = 0.0

    await _run_until(processor, clock, lambda: bool(commits), max_ticks=250)

    assert fallback_calls, 'a non-callable escape attr must fall back to the plain rollover'
    committed_ids = [seg_id for _owner, ids in commits for seg_id in ids]
    assert committed_ids, 'the drain must land on the fresh generation'
    assert commits[-1][0] == 'fresh'
    assert set(committed_ids) <= {raw['id'] for raw in retained}
    assert len(committed_ids) == len(set(committed_ids)), 'no speech replayed or duplicated'
