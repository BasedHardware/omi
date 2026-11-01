"""Harness tool design rules (utils/llm/ARCHITECTURE.md, "Tool design rules").

1. Time windows default to the run's context window.
2. Times shown to the model are UTC ending in Z; time arguments parse leniently or fail clearly.
3. Structured outputs are normalized from the schema's declared aliases before validation.
4. Send-back budgets are kept per failure class.

Synthetic data only.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import ClassVar, List, Optional
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel, ValidationError

from config.dream_session import SessionLimits
from models.agent_tools import Read, Search
from models.structured_extraction import AgentNotesSubmission
from utils.agent_capabilities.session import Session
from utils.conversations import notes_agent_tools as tools
from utils.llm import notes_agent as agent
from utils.llm import notes_agent_policy as policy
from utils.llm import notes_agent_prompt as prompt
from utils.llm.shaped_agent import (
    Problem,
    SendBackBudget,
    model_json,
    model_view,
    normalize_output,
    validate_output,
)
from utils.model_text import TIME_FORMAT_HINT, ContextWindow, ToolTimeError, parse_tool_time, utc_z

UTC = timezone.utc
START = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
END = START + timedelta(minutes=45)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- rule 2: UTC in, Z out


@pytest.mark.parametrize(
    'value, expected',
    [
        ('2026-10-01T15:00:00Z', START),
        ('2026-10-01T15:00:00z', START),
        # The #22853 failure: a -07:00 offset is a real offset and converts, it is not UTC.
        ('2026-10-01T08:00:00-07:00', START),
        ('2026-10-01T15:00:00', START),
        ('2026-10-01 15:00', START),
        ('2026-10-01T15:00:00 UTC', START),
        ('2026-10-01', datetime(2026, 10, 1, tzinfo=UTC)),
        (START.timestamp(), START),
        (int(START.timestamp() * 1000), START),
        (datetime(2026, 10, 1, 15), START),
        (datetime(2026, 10, 1, 17, tzinfo=ZoneInfo('Europe/Berlin')), START),
        (None, None),
        ('  ', None),
    ],
)
def test_tool_times_parse_leniently_to_utc(value, expected):
    assert parse_tool_time(value) == expected


@pytest.mark.parametrize('value', ['yesterday', '2026-13-45T00:00:00Z', '15:00', '0001-01-01', True, {'at': 1}])
def test_unreadable_tool_times_fail_with_the_field_and_expected_format(value):
    with pytest.raises(ToolTimeError) as raised:
        parse_tool_time(value, field='start')
    message = str(raised.value)
    assert message.startswith('start ') and TIME_FORMAT_HINT in message


def test_naive_times_follow_the_zone_the_model_was_shown():
    pacific = ZoneInfo('America/Los_Angeles')
    assert parse_tool_time('2026-10-01T08:00:00', naive_tz=pacific) == START
    with pytest.raises(ToolTimeError, match="user's timezone"):
        parse_tool_time('soon', naive_tz=pacific)


def test_everything_shown_to_the_model_ends_in_z():
    pacific = datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo('America/Los_Angeles'))
    payload = {
        'at': pacific,
        'rows': [{'start': '2026-10-01T08:00:00-07:00', 'title': 'Standup 08:00-07:00'}],
        'naive': datetime(2026, 10, 1, 15, 0),
        'fraction': START.replace(microsecond=250000),
    }
    view = model_view(payload)
    assert view['at'] == '2026-10-01T15:00:00Z'
    assert view['rows'][0]['start'] == '2026-10-01T15:00:00Z'
    # Only whole-string instants are rewritten; free text is left alone.
    assert view['rows'][0]['title'] == 'Standup 08:00-07:00'
    assert view['naive'] == '2026-10-01T15:00:00Z'
    assert view['fraction'] == '2026-10-01T15:00:00.250Z'
    assert json.loads(model_json(payload)) == view
    assert utc_z(START) == '2026-10-01T15:00:00Z'


# ---------------------------------------------------------------- rule 1: context window defaults


def test_context_window_fills_missing_bounds_and_keeps_explicit_ones():
    window = ContextWindow(START, END, 'conversation')
    assert window.resolve() == (START, END)
    later = START + timedelta(minutes=10)
    assert window.resolve(later) == (later, END)
    assert window.resolve(None, later) == (START, later)
    # One explicit bound outside the window keeps the window's span beside it.
    tomorrow = START + timedelta(days=1)
    assert window.resolve(tomorrow) == (tomorrow, tomorrow + window.span)
    assert window.resolve(None, START - timedelta(hours=2)) == (
        START - timedelta(hours=2) - window.span,
        START - timedelta(hours=2),
    )
    # Reversed explicit bounds swap; max_span caps from the start.
    assert window.resolve(END, START) == (START, END)
    assert window.resolve(START, START + timedelta(days=3), max_span=timedelta(hours=12)) == (
        START,
        START + timedelta(hours=12),
    )
    assert window.describe() == {
        'start': '2026-10-01T15:00:00Z',
        'end': '2026-10-01T15:45:00Z',
        'label': 'conversation',
    }
    day = ContextWindow.trailing_day(END)
    assert (day.start, day.end) == (END - timedelta(days=1), END)


@pytest.fixture
def notes_toolbox(monkeypatch):
    windows = []

    def screen(uid, *, start_date, end_date, limit):
        windows.append((start_date, end_date))
        return [{'timestamp': START, 'appName': 'zoom.us', 'windowTitle': 'Zoom Meeting', 'ocrText': 'Maya'}]

    monkeypatch.setattr(tools.screen_activity_db, 'get_screen_activity', screen)
    monkeypatch.setattr(tools.calendar_db, 'get_meetings_in_time_range', lambda uid, lo, hi: windows.append((lo, hi)))
    box = tools.NotesToolbox(uid='synthetic-owner', conversation_id='c1', started_at=START, finished_at=END)
    return box, windows


def test_notes_time_tools_default_to_the_conversation_and_show_z(notes_toolbox):
    box, windows = notes_toolbox
    outcome = run(box.call('get_screen_activity', {}))
    run(box.call('get_calendar', {}))
    assert windows == [(START, END), (START, END)]
    assert json.loads(outcome.content)['rows'][0]['at'] == '2026-10-01T15:00:00Z'
    # An offset the model writes converts; it does not shift the search hours.
    run(box.call('get_screen_activity', {'start': '2026-10-01T08:00:00-07:00', 'end': '2026-10-01T08:45:00-07:00'}))
    assert windows[-1] == (START, END)


def test_notes_unreadable_time_is_a_clear_tool_error_not_a_silent_window(notes_toolbox):
    box, windows = notes_toolbox
    outcome = json.loads(run(box.call('get_screen_activity', {'start': 'this morning'})).content)
    assert outcome['error'].startswith("start 'this morning' is not a time.") and TIME_FORMAT_HINT in outcome['error']
    assert windows == []


def test_notes_agent_mount_carries_the_toolbox_window(notes_toolbox):
    box, _windows = notes_toolbox
    mount = agent.notes_agent_mount(
        policy.NotesAgentBudget(max_turns=3, max_tool_calls=3), {'role': 'system', 'content': ''}, box.window
    )
    assert mount.context_window == ContextWindow(START, END, 'conversation')


class FakeSource:
    def __init__(self):
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        return {'results': [{'ref': 'conversations/c1', 'snippet': 'Synthetic sync', 'at': START}]}

    async def read(self, ref):
        return None


def session(window=None, source=None):
    return Session(
        'synthetic-owner',
        source or FakeSource(),
        SessionLimits(),
        {'targets': []},
        authority='dream',
        context_window=window,
    )


def tool_call(name, arguments, index=1):
    return {'id': f'call-{index}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}


def tool_result(response):
    return json.loads(response['content'].removeprefix('UNTRUSTED TOOL DATA\n'))


def test_dream_temporal_search_defaults_to_the_session_day_and_says_so():
    window = ContextWindow.trailing_day(END, label='dream day')
    source = FakeSource()
    dream = session(window, source)
    [response] = run(dream.execute([tool_call('search', {'mode': 'temporal', 'collections': ['conversations']})]))
    assert (source.requests[0].start, source.requests[0].end) == (window.start, window.end)
    body = tool_result(response)
    assert body['time_window'] == {'start': utc_z(window.start), 'end': utc_z(window.end), 'from': 'dream day'}
    assert body['results'][0]['at'] == '2026-10-01T15:00:00Z'
    # Lexical and semantic time bounds stay optional filters over all history.
    run(dream.execute([tool_call('search', {'query': 'sync', 'collections': ['conversations']}, 2)]))
    assert source.requests[1].start is None and source.requests[1].end is None


def test_dream_search_accepts_offsets_and_naive_times_and_rejects_nonsense():
    source = FakeSource()
    dream = session(source=source)
    run(
        dream.execute(
            [tool_call('search', {'mode': 'temporal', 'start': '2026-10-01T08:00:00-07:00', 'end': '2026-10-01T15:45'})]
        )
    )
    assert (source.requests[0].start, source.requests[0].end) == (START, END)
    [response] = run(dream.execute([tool_call('search', {'mode': 'temporal', 'start': 'last week'}, 2)]))
    body = tool_result(response)
    assert body['status'] == 'rejected' and body['errors'][0]['field'] == 'start'
    assert body['errors'][0]['message'] == TIME_FORMAT_HINT
    with pytest.raises(ValidationError):
        Search.model_validate({'start': 'later'})


def test_dream_seed_shows_its_context_window_in_z():
    window = ContextWindow.trailing_day(END, label='dream day')
    dream = session(window)
    seen = []

    async def model_turn(mount, messages):
        seen.append((mount, messages))
        from utils.llm.shaped_agent import Turn

        return Turn(tokens=1)

    run(dream.run(model_turn, deadline_seconds=5))
    mount, messages = seen[0]
    assert mount.context_window == window
    seed = json.loads(messages[1]['content'][0]['text'].removeprefix('UNTRUSTED SEED DATA\n'))
    assert seed['context_window'] == window.describe()


# ---------------------------------------------------------------- rule 3: declared aliases


def test_notes_section_aliases_normalize_before_validation():
    raw = {
        'title': 'Sync',
        'overview': 'Synthetic.',
        'sections': [
            {'heading': 'Pricing', 'body': '- Point\n  - detail'},
            {'heading': 'Hardware', 'bullets': ['Batch ships', 'Factory date Friday']},
            {'heading': 'Both', 'body_markdown': '- canonical', 'body': '- alias'},
            {'heading': 'Empty canonical', 'body_markdown': '', 'content': '- from content'},
        ],
        'action_items': [],
        'participants': [],
    }
    normalized = normalize_output(AgentNotesSubmission, raw)
    bodies = [section['body_markdown'] for section in normalized['sections']]
    assert bodies == ['- Point\n  - detail', '- Batch ships\n- Factory date Friday', '- canonical', '- from content']
    assert 'body' not in normalized['sections'][0] and normalized['sections'][2]['body'] == '- alias'
    assert raw['sections'][0] == {'heading': 'Pricing', 'body': '- Point\n  - detail'}  # input untouched
    parsed = validate_output(AgentNotesSubmission, json.dumps(raw))
    assert parsed.sections[1].body_markdown == '- Batch ships\n- Factory date Friday'
    # The aliases are declarations, not schema: the one-shot notes prompt bytes are unchanged.
    assert 'output_aliases' not in json.dumps(AgentNotesSubmission.model_json_schema())


class Inner(BaseModel):
    output_aliases: ClassVar[dict[str, tuple[str, ...]]] = {'label': ('name', 'title')}
    label: str


class Outer(BaseModel):
    output_aliases: ClassVar[dict[str, tuple[str, ...]]] = {'items': ('entries',)}
    items: List[Inner] = []
    one: Optional[Inner] = None


def test_alias_maps_recurse_through_nested_and_optional_models():
    normalized = normalize_output(Outer, {'entries': [{'name': 'a'}, {'title': 'b'}], 'one': {'name': 'c'}})
    assert normalized == {'items': [{'label': 'a'}, {'label': 'b'}], 'one': {'label': 'c'}}
    assert Outer.model_validate_json(json.dumps(normalized), strict=True).one.label == 'c'
    assert validate_output(Outer, '{"entries": [{"name": "a"}]}', strict=True).items[0].label == 'a'
    with pytest.raises(ValidationError):
        validate_output(Outer, 'not json')


def test_dream_tool_arguments_use_the_schema_alias_map(monkeypatch):
    monkeypatch.setattr(Read, 'output_aliases', {'refs': ('ref_list',)}, raising=False)
    dream = session()
    [response] = run(dream.execute([tool_call('read', {'ref_list': ['conversations/unknown']})]))
    body = tool_result(response)
    # Validation passed on the aliased key; the read itself reports the unseen ref.
    assert body['errors']['conversations/unknown']['code'] == 'agent_unknown_ref'


# ---------------------------------------------------------------- rule 4: per-class send-backs


def test_send_back_budget_is_per_failure_class():
    budget = SendBackBudget({'format': 1, 'content': 1, 'evidence': 1})
    fmt, thin, unnamed = Problem('format', 'f'), Problem('content', 'c'), Problem('evidence', 'e')
    # Format goes back alone; content and evidence wait for a well-formed resubmission.
    assert budget.review([fmt, thin, unnamed]) == [fmt]
    assert budget.used == {'format': 1}
    assert budget.review([fmt, unnamed]) == [unnamed]  # format spent, evidence still has its retry
    assert budget.review([fmt, unnamed, thin]) == [thin]
    assert budget.review([fmt, unnamed, thin]) == []  # every class spent: accept and repair
    assert budget.review([Problem('format', 'x')], may_send_back=False) == []
    together = SendBackBudget({'content': 1, 'evidence': 1})
    assert together.review([thin, unnamed]) == [thin, unnamed] and together.used == {'content': 1, 'evidence': 1}
    with pytest.raises(ValueError, match='Undeclared failure class'):
        budget.review([Problem('style', 'x')])
    with pytest.raises(ValueError, match='Invalid send-back budget'):
        SendBackBudget({'content': -1})


def test_a_format_send_back_cannot_spend_the_evidence_retry():
    """The #22853 incident: the only send-back went to a format complaint; naming never got its turn."""
    prose = {
        'title': 'Pricing call',
        'overview': 'Pricing.',
        'participants': [],
        'sections': [{'heading': 'Pricing', 'body_markdown': 'The other founder proposed per-seat pricing.'}],
        'action_items': [],
    }
    unnamed = {**prose, 'sections': [{'heading': 'Pricing', 'body': '- The other founder proposed\n  - $40'}]}
    named = {
        **unnamed,
        'title': 'Maya Okafor: pricing',
        'participants': [{'name': 'Maya Okafor', 'speaker': '1', 'evidence': 'Zoom tile'}],
    }
    script = iter([prose, unnamed, named])

    class Toolbox:
        names = prompt.READ_TOOL_NAMES
        window = ContextWindow(START, END, 'conversation')

        async def call(self, name, arguments):
            return tools.ToolOutcome('{}')

    async def complete(messages, tool_choice):
        payload = next(script)
        return agent.CompletionTurn(
            tool_calls=[{'id': f"submit-{payload['title']}", 'name': prompt.SUBMIT, 'arguments': json.dumps(payload)}]
        )

    result = run(
        agent.run_notes_agent(
            owner={'role': 'system', 'content': 'OWNER'},
            seed={'role': 'user', 'content': 'SEED'},
            complete=complete,
            toolbox=Toolbox(),
            budget=policy.NotesAgentBudget(max_turns=5, max_tool_calls=6),
            transcript_words=800,
            naming_leads=['Maya Okafor'],
        )
    )
    # First the format alone, then the naming evidence: the format send-back did not spend it.
    assert len(result.rejections) == 2
    assert 'bullet lists' in result.rejections[0] and 'Maya Okafor' not in result.rejections[0]
    assert 'Maya Okafor' in result.rejections[1] and 'bullet' not in result.rejections[1]
    assert [person['name'] for person in result.submission['participants']] == ['Maya Okafor']
