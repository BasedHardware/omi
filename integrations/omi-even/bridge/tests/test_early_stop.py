"""Tests for stopping the chat stream once the display is already full.

Omi writes for a phone. Measured against the live account, answers ran 929-1511
characters where the glasses show ~380, and waiting for that unseen tail cost
2.7-3.4s per question. Cutting the stream once a screenful has arrived took
"Who is David Zhang?" from 18.4s to 6.1s.

The first implementation of the predicate was silently wrong and is the reason
this file exists. It asked:

    len(fit_for_glasses(raw, limit=DISPLAY_LIMIT)) >= DISPLAY_LIMIT

but `fit_for_glasses` *truncates* to at most `limit`, and usually a few
characters below it after landing on a word boundary. So the comparison was
essentially never true, the stream never stopped early, and the optimisation
looked present while doing nothing -- latency barely moved and the bridge went
on receiving 1100+ characters. The fix strips markup with an unbounded budget so
the length being measured is the stripped length, not the truncated one.

That failure mode is invisible to a test that only checks "long text returns
True" against text far above the limit, so these pin the boundary specifically.
"""

from __future__ import annotations

import pytest

import server
from display import DEFAULT_LIMIT, fit_for_glasses


def test_short_text_does_not_stop_the_stream():
    assert server._display_is_full('Short answer.') is False


def test_text_well_over_the_limit_stops_the_stream():
    assert server._display_is_full('This is a sentence. ' * 60) is True


def test_text_just_over_the_limit_stops_the_stream():
    """The regression: a truncating comparison fails right here.

    Text a little longer than one screen is the realistic case -- an answer that
    overflows by 10% is exactly what we want to stop on, and exactly what the
    original predicate missed.
    """
    raw = 'word ' * ((DEFAULT_LIMIT // 5) + 6)  # ~30 chars past the limit
    assert len(raw) > DEFAULT_LIMIT
    assert server._display_is_full(raw) is True


def test_the_predicate_is_not_defeated_by_truncation():
    """Directly asserts the bug cannot come back.

    `fit_for_glasses` at the display limit can never exceed it, so any predicate
    written in terms of that value is dead code. If someone reintroduces it, this
    fails.
    """
    raw = 'This is a sentence. ' * 60
    truncated = fit_for_glasses(raw, limit=DEFAULT_LIMIT)
    assert len(truncated) <= DEFAULT_LIMIT
    # The naive comparison the bug used:
    naive = len(truncated) >= DEFAULT_LIMIT
    # ...disagrees with the correct answer for this input, which is what made the
    # optimisation silently inert.
    assert server._display_is_full(raw) is True
    assert naive is False, 'if this ever holds, the naive check stopped being wrong by accident'


def test_markup_heavy_text_is_measured_after_stripping():
    """A screenful of tags is not a screenful of words.

    Raw length alone would stop the stream on an answer that renders almost
    empty, cutting off the actual content.
    """
    raw = '<cite index="1-1"></cite>' * 40  # long raw, no visible text
    assert len(raw) > DEFAULT_LIMIT
    assert server._display_is_full(raw) is False


def test_empty_and_whitespace_never_stop_the_stream():
    for raw in ('', '   ', '\n\n\n'):
        assert server._display_is_full(raw) is False


@pytest.mark.asyncio
async def test_the_agent_path_passes_the_predicate_through(monkeypatch):
    """Wiring check: forgetting `enough=` costs seconds and changes nothing visible."""
    # The endpoint now prefers the fast retrieval path, which returns before the
    # agent is ever consulted. This test is about the agent path, so ask for it.
    monkeypatch.setenv('OMI_EVEN_FULL_AGENT', '1')
    seen = {}

    class FakeOmi:
        async def chat(self, text, app_id=None, deadline_s=None, enough=None):
            seen['enough'] = enough
            from omi_client import ChatResult

            return ChatResult(text='ok')

    monkeypatch.setattr(server, 'omi', FakeOmi())
    await server._answer_for_glasses('anything')

    assert seen['enough'] is not None, 'the agent path stopped passing the early-stop predicate'
    assert seen['enough']('This is a sentence. ' * 60) is True
