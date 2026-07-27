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
        '- Archit works with David on the trial engagement. (relevance: 0.62, category: interesting, date: 2026-07-27)\n'
        # Below the 0.15 floor: this is the random tail, not a weak-but-real hit.
        '- A barely related note about something else. (relevance: 0.04, category: system, date: 2026-07-08)\n'
    )
    lines = _clean_bullets(raw)
    assert lines == ['Archit works with David on the trial engagement.']
    assert 'relevance' not in ' '.join(lines)


def test_bullets_come_back_strongest_first():
    raw = (
        '- The middling fact about a thing. (relevance: 0.50)\n'
        '- The best fact about a thing. (relevance: 0.90)\n'
        '- Another good fact about a thing. (relevance: 0.70)\n'
    )
    assert _clean_bullets(raw) == [
        'The best fact about a thing.',
        'Another good fact about a thing.',
        'The middling fact about a thing.',
    ]


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
async def test_a_temporal_question_does_not_use_a_server_side_date_window():
    """Date filtering happens here, not in the query -- on purpose.

    Measured on the live account, the same question cost 13.5s with a
    start_date/end_date window and 3.1s without. 13.5s is past the timeout this
    whole path exists to beat, so the window would have made the answer correct
    and invisible.
    """
    client = FakeClient(conversations='- something')
    await fast_answer(client, 'What did I do yesterday?')
    payload = client.payloads['conversations/search']
    assert 'start_date' not in payload, 'a server-side window makes this 4x slower'
    assert payload['limit'] >= 8, 'fetch wider, since filtering happens client-side'


@pytest.mark.asyncio
async def test_results_from_the_wrong_day_are_filtered_out():
    """The correctness the server-side window used to provide, done locally."""
    conversations = (
        "Found 2 conversations matching 'x':\n\n"
        'Conversation #1\n'
        '04 Jul 2026 at 12:00 America/New_York (Social)\n'
        'Friends share burgers on july fourth\n\n'
        'Conversation #2\n'
        '23 Jul 2026 at 16:08 America/New_York (Technology)\n'
        'Archit investigates web search\n'
    )
    client = FakeClient(conversations=conversations)
    answer = await fast_answer(client, 'What did I do on 4 July?')
    assert 'burgers' in answer
    assert 'web search' not in answer, 'a conversation from another day leaked through'


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


# --------------------------------------------------- garbled speech guard


@pytest.mark.parametrize(
    'question',
    ['ping', 'uh', 'hm', 'the a of', '', '   ', 'ok', 'yeah'],
)
@pytest.mark.asyncio
async def test_a_fragment_returns_a_prompt_not_a_random_memory(question):
    """Speech-to-text emits fragments, and vector search answers every one.

    Asking "ping" surfaced an unrelated obscenity from an old transcript. On a
    display worn on your face, nothing beats nearest-neighbour noise.
    """
    client = FakeClient(memories='- Something unrelated. (relevance: 0.55)')
    answer = await fast_answer(client, question)
    assert 'Ask me something' in answer
    assert 'unrelated' not in answer


@pytest.mark.asyncio
async def test_a_real_short_question_still_works():
    """The guard must not swallow genuine brief questions."""
    client = FakeClient(memories='- David is your colleague. (relevance: 0.80)')
    answer = await fast_answer(client, 'Who is David?')
    assert 'David is your colleague.' in answer


# ------------------------------------------- the dominant retrieval failure


def test_indexed_file_paths_are_never_returned_as_memories():
    """The single biggest cause of useless answers.

    An indexer files every local document into the memory store as a `system`
    memory. Measured against the live account, those were 7/10 results for
    "pickleball", 9/10 for "burgers", and 10/10 for "what I learned in July" --
    which is why that question answered "nothing at all".
    """
    raw = (
        "Found 4 memories matching 'burgers':\n\n"
        "- The user's local downloads include ~/Downloads/cheese/groundedshakes.md (md). "
        '(relevance: 0.24, category: system, date: 2026-07-07)\n'
        '- The user works on a local project named lecture01-code. '
        '(relevance: 0.26, category: system, date: 2026-07-08)\n'
        '- Liiban organized a group dinner at Wally with Aryaveer and Archit. '
        '(relevance: 0.22, category: system, date: 2026-07-05)\n'
    )
    lines = _clean_bullets(raw)
    assert lines == ['Liiban organized a group dinner at Wally with Aryaveer and Archit.']
    assert not any('Downloads' in line or 'lecture01' in line for line in lines)


def test_a_real_memory_below_the_old_threshold_survives():
    """The relevance floor was set to 0.40 and was simply wrong.

    Genuinely useful memories score 0.22-0.48 on this account, so that floor
    discarded most of the good ones and left only file-path noise, which scored
    no worse. Category is the real discriminator, not the number.
    """
    raw = (
        '- Liiban organized a group dinner at Wally with Aryaveer and Archit. '
        '(relevance: 0.22, category: interesting, date: 2026-07-05)\n'
    )
    assert _clean_bullets(raw), 'a 0.22 memory is useful and must not be dropped'


def test_conversation_titles_are_extracted_for_merging():
    """Conversations carry what happened; memories carry standing facts.

    Searching memories alone answered "burgers" with a downloads-folder path
    while conversations held "A group orders fast food ... burgers, fries".
    """
    from fastpath import _conversation_titles

    raw = (
        "Found 1 conversations matching 'burgers':\n\n"
        'Conversation #1\n'
        '05 Jul 2026 at 19:00 America/New_York (Social)\n'
        'A group orders fast food and discusses burgers, fries and sauces\n'
        '- Some detail line\n'
    )
    titles = _conversation_titles(raw)
    assert titles == ['A group orders fast food and discusses burgers, fries and sauces']


def test_a_real_memory_in_the_system_category_is_kept():
    """`system` is the DEFAULT extraction category, not a noise marker.

    Rejecting the category wholesale -- which is the obvious first move -- throws
    away real memories, because the backend labels most extracted facts `system`
    (utils/memory_ingestion/adapters/typed_extraction_prompt.py:201). The backend's
    own cleanup keys on content instead, and so does this.
    """
    raw = (
        '- Archit and Sami courted Pasha at A1 Base for a partnership. '
        '(relevance: 0.30, category: system, date: 2026-07-02)\n'
    )
    assert _clean_bullets(raw) == ['Archit and Sami courted Pasha at A1 Base for a partnership.']


@pytest.mark.parametrize(
    'line',
    [
        "- The user's local documents include ~/Documents/x/y.md (md). (relevance: 0.4)",
        '- The user works on a local project named lecture01-code. (relevance: 0.4)',
        '- 2,800 local files indexed across their machine. (relevance: 0.4)',
        '- focused on Terminal for 40 minutes (relevance: 0.4)',
        '- distracted on Twitter for 10 minutes (relevance: 0.4)',
    ],
)
def test_local_file_inventory_lines_are_dropped(line):
    assert _clean_bullets(line) == []


def test_a_project_mention_without_a_path_survives():
    """The double anchor: mentioning a project is real, a path makes it inventory."""
    raw = '- Archit is building the omi-even bridge for smart glasses. (relevance: 0.35)\n'
    assert _clean_bullets(raw), 'a genuine project memory must not be swept up'
