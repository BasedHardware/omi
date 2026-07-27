"""Tests for the fast retrieval path used by Even AI.

Even's custom-agent client times out well before Omi's agent can answer. Proven
on hardware: a 0.4s reply renders on the glasses; 5.6-8.4s replies return 200 OK
and are never seen. This path reads Omi's stores directly and lands in 0.5-2.8s.

Most of these tests exist because a specific wrong answer shipped and had to be
walked back. Each is named for the failure it prevents.
"""

from __future__ import annotations

import pytest

import fastpath
from fastpath import (
    _classify,
    _clean_bullets,
    _compact_conversations,
    _date_window,
    _looks_relevant,
    fast_answer,
)


class FakeClient:
    def __init__(self, memories='', conversations='', actions=None, fail=()):
        self.memories = memories
        self.conversations = conversations
        self.actions = actions or []
        self.fail = fail
        self.payloads: dict[str, dict] = {}

    async def tool_search(self, tool, payload):
        self.payloads[tool] = payload
        if tool in self.fail:
            raise RuntimeError(f'{tool} reported an error')
        return self.conversations if 'conversations' in tool else self.memories

    async def action_items(self, limit=20):
        return list(self.actions)


# ------------------------------------------------------------------ routing


@pytest.mark.parametrize(
    ('question', 'expected'),
    [
        ('What am I behind on?', 'actions'),
        ("What's on my plate?", 'actions'),
        ('What tasks do I have?', 'actions'),
        ('What did I do yesterday?', 'conversations'),
        ('What did we discuss in the meeting?', 'conversations'),
        ('Who is David Zhang?', 'memories'),
        ('Tell me about my cofounder', 'memories'),
    ],
)
def test_questions_route_to_the_right_store(question, expected):
    assert _classify(question) == expected


def test_temporal_questions_beat_the_task_wording():
    """"What did I do yesterday" contains "do" but is not a task question."""
    assert _classify('What did I do yesterday?') == 'conversations'


# ------------------------------------------------------------- date windows


def test_date_bounds_carry_a_timezone():
    """The search tool rejects a bare date.

    It requires `YYYY-MM-DDTHH:MM:SS+HH:MM`. Sending `2026-07-20` came back as an
    error, and because the tool reports "no results" the same way it reports a
    failure, the bad format silently produced "nothing recorded" for days that
    had plenty. That is a wrong answer, not a missing one.
    """
    window = _date_window('What did I do yesterday?')
    assert window, 'yesterday must produce a window'
    for value in window.values():
        assert 'T' in value, f'{value} has no time component'
        # An offset (+05:00 / -04:00) or Z must be present after the time.
        assert value[-6] in '+-' or value.endswith('Z'), f'{value} has no timezone'


def test_a_day_window_spans_the_whole_day():
    window = _date_window('What did I do yesterday?')
    assert window['start_date'] < window['end_date']
    assert 'T00:00:00' in window['start_date']
    assert 'T23:59:59' in window['end_date']


def test_a_question_with_no_time_reference_has_no_window():
    assert _date_window('Who is David Zhang?') == {}


# ---------------------------------------------------------------- cleaning


def test_relevance_metadata_is_stripped_and_weak_hits_dropped():
    raw = (
        "Found 3 memories matching 'x':\n\n"
        '- A strong fact. (relevance: 0.62, category: interesting, date: 2026-07-27)\n'
        '- A weak fact. (relevance: 0.31, category: system, date: 2026-07-08)\n'
    )
    lines = _clean_bullets(raw)
    assert lines == ['A strong fact.']
    assert 'relevance' not in ' '.join(lines)


def test_bullets_come_back_strongest_first():
    raw = (
        '- Middling. (relevance: 0.50)\n'
        '- Best. (relevance: 0.90)\n'
        '- Also good. (relevance: 0.70)\n'
    )
    assert _clean_bullets(raw) == ['Best.', 'Also good.', 'Middling.']


def test_conversation_scaffolding_is_removed():
    """Timestamps repeated three times ate most of a 380-character screen."""
    raw = (
        "Found 1 conversations matching 'x':\n\n"
        'Conversation #1\n'
        '23 Jul 2026 at 16:08 America/New_York (Technology)\n'
        'Started: 23 Jul 2026 at 16:08 America/New_York\n'
        'Finished: 23 Jul 2026 at 21:21 America/New_York\n'
        'Archit investigates web search\n'
        '## Screen Check\n'
        '- Asked to test freezing.\n'
    )
    out = _compact_conversations(raw)
    assert 'Started:' not in out and 'Finished:' not in out
    assert 'Conversation #1' not in out
    assert 'America/New_York' not in out
    assert 'Archit investigates web search' in out
    assert 'Screen Check' in out  # heading kept, its '##' removed


@pytest.mark.parametrize(
    'body',
    [
        "No conversations found matching 'x' in the specified date range.",
        'No memories found.',
        'Error: Invalid start_date format',
    ],
)
def test_a_no_results_sentence_is_not_echoed_as_an_answer(body):
    """These tools phrase emptiness as prose; repeating it reads as a bug."""
    assert _compact_conversations(body) == ''


# -------------------------------------------------------------- relevance


def test_a_single_shared_word_cannot_carry_an_unrelated_result():
    """The live failure: "who is the president of the USA" returned a
    conversation about wallpapers, which really did contain "USA"."""
    text = 'Wallpapers spark playful relationship talk. A trip across the USA.'
    assert _looks_relevant('Who is the president of the USA?', text) is False


def test_a_genuine_match_still_passes():
    text = 'David Zhang and Archit debugged the iMessage integration together.'
    assert _looks_relevant('What did I promise David Zhang?', text) is True


def test_a_question_of_only_stopwords_is_not_blocked():
    assert _looks_relevant('what is it', 'anything at all') is True


# ------------------------------------------------------------- end to end


@pytest.mark.asyncio
async def test_open_tasks_are_returned_newest_first():
    client = FakeClient(
        actions=[
            {'description': 'old thing', 'completed': False, 'created_at': '2026-01-01'},
            {'description': 'new thing', 'completed': False, 'created_at': '2026-07-27'},
            {'description': 'done thing', 'completed': True, 'created_at': '2026-07-26'},
        ]
    )
    answer = await fast_answer(client, 'What am I behind on?')
    assert answer.index('new thing') < answer.index('old thing')
    assert 'done thing' not in answer


@pytest.mark.asyncio
async def test_a_general_knowledge_question_admits_it_does_not_know():
    """Answering from whatever was nearest in vector space is worse than silence.

    The fast path has no LLM, so a question needing world knowledge cannot be
    answered -- and must not be answered wrongly.
    """
    client = FakeClient(memories='', conversations='Wallpapers and a USA road trip.')
    answer = await fast_answer(client, 'Who is the president of the USA?')
    assert 'Nothing in your memories' in answer
    assert 'Wallpaper' not in answer


@pytest.mark.asyncio
async def test_a_temporal_question_sends_a_date_window():
    client = FakeClient(conversations='- something')
    await fast_answer(client, 'What did I do yesterday?')
    payload = client.payloads['conversations/search']
    assert 'start_date' in payload and 'T' in payload['start_date']


@pytest.mark.asyncio
async def test_a_failing_tool_does_not_raise():
    """A raised error here falls back to the 6s agent path, which is the very
    latency this exists to avoid."""
    client = FakeClient(fail=('memories/search',))
    answer = await fast_answer(client, 'Who is David Zhang?')
    assert answer  # a message, not an exception


@pytest.mark.asyncio
async def test_an_empty_day_says_so_without_falling_back():
    client = FakeClient(conversations='')
    answer = await fast_answer(client, 'What did I do yesterday?')
    assert 'Nothing recorded' in answer


@pytest.mark.asyncio
async def test_the_answer_stays_within_a_screenful():
    client = FakeClient(
        actions=[
            {'description': f'task number {i} with a fairly long description', 'completed': False,
             'created_at': f'2026-07-{i:02d}'}
            for i in range(1, 20)
        ]
    )
    answer = await fast_answer(client, 'What am I behind on?')
    assert len(answer.splitlines()) <= 4
