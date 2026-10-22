"""Agentic meeting notes: budget gate, owner-scoped read-only tools, forced submit, cache-stable
prefix, format validator, and a synthetic end-to-end replay (no real user data)."""

import asyncio
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from llm_gateway.gateway.accounting import rate_card_for

from utils.conversations import notes_agent_tools as tools
from utils.conversations.screen_people_leads import screen_people_leads
from utils.llm import conversation_processing as notes
from utils.llm import notes_agent as agent
from utils.llm import notes_agent_policy as policy
from utils.llm import notes_agent_prompt as prompt
from utils.llm import notes_agent_serving as serving
from utils.llm import shaped_agent
from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage
from utils.llm.notes_output_contract import check_notes, nested_bullet_count, repair_notes

FIXTURE = Path(__file__).parent / 'fixtures' / 'notes_agent' / 'weekly_sync_replay.json'
OWNER = 'synthetic-owner'
START = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (policy.FLAG, policy.PERCENT, policy.UID_ALLOWLIST):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------- budget gate


def plan(**overrides):
    values = dict(uid=OWNER, conversation_id='conv-1', words=2000)
    values.update(overrides)
    return policy.plan_notes_agent(**values)


def test_long_transcript_runs_with_value_proportional_budget():
    short, mid, long = plan(words=400, has_calendar=True), plan(words=2000), plan(words=9000)
    assert (short.run, mid.run, long.run) == (True, True, True)
    assert short.budget.max_tool_calls < mid.budget.max_tool_calls < long.budget.max_tool_calls == 15
    assert {d.budget.max_cost_usd for d in (short, mid, long)} == {0.02}
    assert mid.reason == 'long_transcript'


@pytest.mark.parametrize(
    'overrides,reason',
    [
        (dict(words=1499), 'below_threshold'),
        (dict(words=299, has_calendar=True), 'below_threshold'),
        (dict(words=400), 'below_threshold'),
        (dict(words=400, has_call_screen=True), 'meeting_evidence'),
        (dict(words=400, capture_sources=2), 'multi_source'),
        (dict(transport_ready=False), 'transport'),
    ],
)
def test_gate_reasons(overrides, reason):
    assert plan(**overrides).reason == reason


@pytest.mark.parametrize('value', ['false', 'off', '0', 'NO'])
def test_kill_switch_returns_everything_to_one_shot(monkeypatch, value):
    monkeypatch.setenv(policy.FLAG, value)
    assert plan(words=20000).run is False and plan().reason == 'disabled'


def test_unknown_kill_switch_value_stays_on(monkeypatch):
    monkeypatch.setenv(policy.FLAG, 'garbage')
    assert plan().run is True


def test_percent_cohort_is_stable_and_allowlist_always_in(monkeypatch):
    monkeypatch.setenv(policy.PERCENT, '5')
    admitted = [cid for cid in (f'conv-{index}' for index in range(400)) if plan(conversation_id=cid).run]
    assert 5 <= len(admitted) <= 40
    assert admitted == [cid for cid in (f'conv-{index}' for index in range(400)) if plan(conversation_id=cid).run]
    monkeypatch.setenv(policy.UID_ALLOWLIST, f'someone,{OWNER}')
    assert all(plan(conversation_id=f'conv-{index}').run for index in range(50))
    monkeypatch.setenv(policy.PERCENT, 'garbage')
    monkeypatch.delenv(policy.UID_ALLOWLIST)
    assert not any(plan(conversation_id=f'conv-{index}').run for index in range(50))


def test_cost_estimate_uses_luna_card():
    # 15k uncached at $0.10/M, 5k cached at $0.01/M, 1.5k output at $0.60/M.
    assert policy.estimate_cost_usd(20000, 5000, 1500) == pytest.approx(0.00245)


def test_mirrored_prices_match_the_gateway_rate_card():
    rates = rate_card_for(policy.PRICE_PROVIDER, policy.PRICE_MODEL).effective_rates(1000)
    assert rates.input_micro_usd_per_million == round(policy.INPUT_USD_PER_MILLION * 1_000_000)
    assert rates.cached_input_micro_usd_per_million == round(policy.CACHED_INPUT_USD_PER_MILLION * 1_000_000)
    assert rates.output_micro_usd_per_million == round(policy.OUTPUT_USD_PER_MILLION * 1_000_000)


# ---------------------------------------------------------------- tool scoping


CHAT_WRITE_TOOLS = {
    'create_action_item',
    'update_action_item',
    'complete_action_item',
    'delete_action_item',
    'create_memory',
    'edit_memory',
    'delete_memory',
    'rename_person',
    'propose_edit',
    'learn_term',
}


def test_tool_catalog_is_read_only_plus_terminal_submit():
    names = {schema['function']['name'] for schema in prompt.TOOL_SCHEMAS}
    assert names == set(prompt.READ_TOOL_NAMES) | {prompt.SUBMIT}
    assert not names & CHAT_WRITE_TOOLS
    for schema in prompt.TOOL_SCHEMAS:
        assert 'uid' not in json.dumps(schema['function']['parameters'])


class FakeOwnerSearch:
    def __init__(self):
        self.requests, self.reads = [], []

    async def search(self, request, *, byte_budget):
        self.requests.append(request)
        return {'results': [{'ref': 'conversations/past-1', 'snippet': 'Weekly sync with Maya'}]}

    async def read(self, ref):
        self.reads.append(ref)
        return {'structured': {'title': 'Weekly sync', 'sections': [{'heading': 'H', 'body_markdown': '- x'}]}}


@pytest.fixture
def toolbox(monkeypatch):
    calls = []

    def recorder(name, value):
        def fake(uid, *args, **kwargs):
            calls.append((name, uid))
            return value

        return fake

    monkeypatch.setattr(
        tools.screen_activity_db,
        'get_screen_activity',
        recorder(
            'screen',
            [
                {'timestamp': 't1', 'appName': 'zoom.us', 'windowTitle': 'Zoom Meeting', 'ocrText': 'Maya Okafor'},
                {'timestamp': 't2', 'appName': 'Slack', 'windowTitle': 'DM', 'ocrText': 'private chat text'},
            ],
        ),
    )
    monkeypatch.setattr(tools.calendar_db, 'get_meetings_in_time_range', recorder('calendar', []))
    monkeypatch.setattr(tools, 'load_people_documents', recorder('people', [{'id': 'p1', 'name': 'Maya Okafor'}]))
    monkeypatch.setattr(tools.action_items_db, 'get_action_items', recorder('tasks', []))
    frame = NotesFrameImage(frame_id='frame-1', offset_label='00:02', data_url='data:image/jpeg;base64,AAAA')
    box = tools.NotesToolbox(
        uid=OWNER,
        conversation_id='conv-1',
        started_at=START,
        finished_at=START + timedelta(minutes=30),
        frames=(frame,),
        _search=FakeOwnerSearch(),
    )
    return box, calls


def run(coro):
    return asyncio.run(coro)


def test_every_reader_is_bound_to_the_owner(toolbox):
    box, calls = toolbox
    for name, args in (
        ('get_screen_activity', {'start': START.isoformat(), 'end': (START + timedelta(hours=1)).isoformat()}),
        ('get_calendar', {}),
        ('search_people', {'query': 'maya'}),
        ('search_past_meetings', {'person': 'Maya Okafor'}),
        ('get_past_meeting', {'conversation_id': 'past-1'}),
    ):
        outcome = run(box.call(name, args))
        assert 'error' not in json.loads(outcome.content), name
    assert calls and {uid for _name, uid in calls} == {OWNER}
    assert box._search.requests[0].person_ref == 'people/p1'
    assert box._search.reads == ['conversations/past-1']


def test_screen_tool_drops_messaging_text_and_caps_window(toolbox):
    box, _calls = toolbox
    rows = json.loads(run(box.call('get_screen_activity', {'start': START.isoformat(), 'end': '2027-01-01'})).content)
    assert {row['app'] for row in rows['rows']} == {'zoom.us', 'Slack'}
    assert all('text' not in row for row in rows['rows'] if row['app'] == 'Slack')
    lo, hi = box._window(START, START + timedelta(days=30))
    assert hi - lo == timedelta(hours=tools.MAX_WINDOW_HOURS)


def test_unseen_conversations_and_foreign_frames_are_refused(toolbox):
    box, _calls = toolbox
    assert 'error' in json.loads(run(box.call('get_past_meeting', {'conversation_id': 'someone-elses'})).content)
    assert 'error' in json.loads(run(box.call('view_screenshot', {'frame_id': 'other-frame'})).content)
    assert box._search.reads == []
    outcome = run(box.call('view_screenshot', {'frame_id': 'frame-1'}))
    assert outcome.image is not None and outcome.image.frame_id == 'frame-1'


def test_bad_arguments_and_reader_failures_never_raise(toolbox, monkeypatch):
    box, _calls = toolbox
    assert 'error' in json.loads(run(box.call('search_people', {'nope': 1})).content)

    def boom(*_args, **_kwargs):
        raise RuntimeError('store down')

    monkeypatch.setattr(tools.calendar_db, 'get_meetings_in_time_range', boom)
    assert 'unavailable' in json.loads(run(box.call('get_calendar', {})).content)['error']


# ---------------------------------------------------------------- loop and forced submit


GOOD_BODY = '- Point\n  - detail one\n  - detail two'


def submission(**overrides):
    value = {
        'title': 'Maya: pricing',
        'overview': 'Pricing talk.',
        'participants': [],
        'sections': [{'heading': 'Pricing', 'body_markdown': GOOD_BODY}],
        'action_items': [],
    }
    value.update(overrides)
    return value


def call(name, arguments, index=0):
    return {'id': f'{name}-{index}', 'name': name, 'arguments': json.dumps(arguments)}


class ScriptedModel:
    """Looks things up until forced; records the tool_choice of every turn."""

    def __init__(self, *, lookups_per_turn=1, prompt_tokens=1000, cached=0, completion=100, final=None):
        self.choices, self.requests = [], []
        self.lookups_per_turn = lookups_per_turn
        self.usage = (prompt_tokens, cached, completion)
        self.final = final or submission()

    async def __call__(self, messages, tool_choice):
        self.choices.append(tool_choice)
        self.requests.append(json.loads(json.dumps(messages, default=str)))
        prompt_tokens, cached, completion = self.usage
        if isinstance(tool_choice, dict):
            calls = [call(prompt.SUBMIT, self.final, len(self.choices))]
        else:
            calls = [
                call('search_people', {'query': 'maya'}, len(self.choices) * 10 + index)
                for index in range(self.lookups_per_turn)
            ]
        return agent.CompletionTurn(
            tool_calls=calls, prompt_tokens=prompt_tokens, cached_tokens=cached, completion_tokens=completion
        )


class CountingToolbox:
    names = prompt.READ_TOOL_NAMES

    def __init__(self):
        self.calls = 0

    async def call(self, name, arguments):
        self.calls += 1
        return tools.ToolOutcome(json.dumps({'people': []}))


OWNER_MESSAGE = prompt.owner_message(lexicon='', owner_name='Riley', owner_profile='', explicit_cache=True)
SEED = prompt.conversation_seed({'LENGTH': 'short'}, 'FULL TRANSCRIPT\nhello', explicit_cache=True)


def run_agent(model, budget, **kwargs):
    return run(
        agent.run_notes_agent(
            owner=OWNER_MESSAGE,
            seed=SEED,
            complete=model,
            toolbox=kwargs.pop('toolbox', CountingToolbox()),
            budget=budget,
            transcript_words=kwargs.pop('words', 400),
            **kwargs,
        )
    )


def test_tool_cap_forces_submit_and_answers_overflow_with_submit_now():
    toolbox = CountingToolbox()
    model = ScriptedModel(lookups_per_turn=4)
    result = run_agent(model, policy.NotesAgentBudget(max_turns=9, max_tool_calls=6), toolbox=toolbox)
    assert result.stop == 'forced_submit' and result.submission['title'] == 'Maya: pricing'
    assert toolbox.calls == result.tool_calls == 6
    assert model.choices[:2] == ['required', 'required']
    assert model.choices[2] == {'type': 'function', 'function': {'name': prompt.SUBMIT}}
    overflow = [m for m in model.requests[2] if m.get('role') == 'tool' and 'budget exhausted' in m['content']]
    assert len(overflow) == 2


def test_last_turn_and_cost_cap_force_submit():
    model = ScriptedModel()
    result = run_agent(model, policy.NotesAgentBudget(max_turns=3, max_tool_calls=15))
    assert model.choices[-1]['function']['name'] == prompt.SUBMIT and result.turns == 3
    # ~$0.0101 per turn: the second turn would cross the 2-cent cap, so it must submit.
    pricey = ScriptedModel(prompt_tokens=100000, completion=200)
    result = run_agent(pricey, policy.NotesAgentBudget(max_turns=9, max_tool_calls=15))
    assert result.turns == 2 and isinstance(pricey.choices[1], dict) and result.submission is not None


def test_wall_clock_forces_submit():
    ticks = iter([0, 0, 100, 100, 100, 100, 100, 100, 100, 100])
    model = ScriptedModel()
    result = run_agent(model, policy.NotesAgentBudget(max_turns=9, max_tool_calls=15), clock=lambda: next(ticks, 100))
    assert isinstance(model.choices[1], dict) and result.stop == 'forced_submit'


def test_bad_submission_is_returned_once_per_failure_class_then_repaired():
    bad = submission(
        sections=[
            {'heading': 'Discussion', 'body_markdown': 'A prose paragraph about pricing.'},
            {'heading': 'Action items', 'body_markdown': '- Send the deck'},
        ]
    )

    class TwiceBad(ScriptedModel):
        async def __call__(self, messages, tool_choice):
            self.choices.append(tool_choice)
            self.requests.append(json.loads(json.dumps(messages, default=str)))
            return agent.CompletionTurn(tool_calls=[call(prompt.SUBMIT, bad, len(self.choices))], prompt_tokens=10)

    model = TwiceBad()
    result = run_agent(model, policy.NotesAgentBudget(max_turns=5, max_tool_calls=6), words=2000)
    # Format goes back first, alone; then the length (content) check gets its own send-back.
    assert len(result.rejections) == 2 and 'Action items' in result.rejections[0]
    assert 'at least' not in result.rejections[0] and 'at least 480' in result.rejections[1]
    assert [s['heading'] for s in result.submission['sections']] == ['Discussion']
    assert 'action_section_dropped' in result.repairs


def test_text_only_reply_is_nudged_into_a_forced_submit():
    class Chatty(ScriptedModel):
        async def __call__(self, messages, tool_choice):
            self.choices.append(tool_choice)
            if isinstance(tool_choice, dict):
                return agent.CompletionTurn(tool_calls=[call(prompt.SUBMIT, submission())])
            return agent.CompletionTurn(content='Here are the notes...')

    model = Chatty()
    result = run_agent(model, policy.NotesAgentBudget(max_turns=4, max_tool_calls=6))
    assert result.submission is not None and isinstance(model.choices[1], dict)


# ---------------------------------------------------------------- cache-stable prefix


def test_prefix_is_byte_stable_across_conversations_and_turns():
    first = prompt.owner_message(
        lexicon='Known: Quorbi', owner_name='Riley', owner_profile='Founder', explicit_cache=True
    )
    second = prompt.owner_message(
        lexicon='Known: Quorbi', owner_name='Riley', owner_profile='Founder', explicit_cache=True
    )
    assert first == second
    assert first['content'][-1]['prompt_cache_breakpoint'] == {'mode': 'explicit'}
    key = serving.prefix_cache_key(prompt.PROMPT_VERSION, prompt.cache_key_material(first), owner_uid=OWNER)
    assert key == serving.prefix_cache_key(prompt.PROMPT_VERSION, prompt.cache_key_material(second), owner_uid=OWNER)
    assert key != serving.prefix_cache_key(prompt.PROMPT_VERSION, prompt.cache_key_material(first), owner_uid='other')
    # No dates, clocks or per-conversation values in the shared instructions.
    assert not re.search(r'\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|20\d\d', prompt.INSTRUCTIONS)
    model = ScriptedModel()
    before = shaped_agent.PREFIX_VIOLATIONS.labels(reason='messages')._value.get()
    run_agent(model, policy.NotesAgentBudget(max_turns=4, max_tool_calls=6))
    assert shaped_agent.PREFIX_VIOLATIONS.labels(reason='messages')._value.get() == before
    head = [json.dumps(message, sort_keys=True) for message in model.requests[0]]
    for later in model.requests[1:]:
        assert [json.dumps(message, sort_keys=True) for message in later[: len(head)]] == head
    assert model.requests[0][1] == OWNER_MESSAGE and model.requests[0][2] == SEED


def test_harness_counts_cached_and_uncached_input():
    counter = shaped_agent.INPUT_TOKENS
    cached = counter.labels(feature=agent.FEATURE, kind='cached')._value.get()
    uncached = counter.labels(feature=agent.FEATURE, kind='uncached')._value.get()
    run_agent(ScriptedModel(prompt_tokens=1000, cached=800), policy.NotesAgentBudget(max_turns=2, max_tool_calls=6))
    assert counter.labels(feature=agent.FEATURE, kind='cached')._value.get() - cached == 1600
    assert counter.labels(feature=agent.FEATURE, kind='uncached')._value.get() - uncached == 400


# ---------------------------------------------------------------- validator


def test_validator_requires_nesting_bullets_and_no_action_sections_for_long_meetings():
    flat = submission(sections=[{'heading': 'Pricing', 'body_markdown': '- one\n- two'}])
    assert any('Nest' in problem for problem in check_notes(flat, transcript_words=3000).problems)
    assert check_notes(flat, transcript_words=800).ok
    filled = submission(sections=[{'heading': 'Pricing', 'body_markdown': GOOD_BODY + ' ' + ' '.join(['word'] * 500)}])
    assert check_notes(filled, transcript_words=3000).ok
    for heading in ('Action Items', 'Next steps', 'To-dos', 'Follow-ups'):
        bad = submission(sections=[*submission()['sections'], {'heading': heading, 'body_markdown': '- x'}])
        assert not check_notes(bad, transcript_words=800).ok
    assert nested_bullet_count('- a\n  - b\n\t- c\n- d') == 2


def test_validator_flags_thin_notes_on_long_meetings():
    problems = check_notes(submission(), transcript_words=6000).problems
    assert any('at least 650' in problem for problem in problems)
    assert check_notes(submission(), transcript_words=900).ok


def test_long_meetings_must_investigate_before_submitting():
    class Eager(ScriptedModel):
        # Submits immediately unless told to investigate; then looks up and resubmits.
        async def __call__(self, messages, tool_choice):
            self.choices.append(tool_choice)
            told = any(
                m.get('role') == 'tool' and 'Investigate before submitting' in str(m.get('content')) for m in messages
            )
            looked = sum(m.get('role') == 'tool' and 'people' in str(m.get('content')) for m in messages)
            if told and looked < 4 and not isinstance(tool_choice, dict):
                calls = [call('search_people', {'query': 'x'}, len(self.choices) * 10 + i) for i in range(4)]
            else:
                calls = [call(prompt.SUBMIT, submission(), len(self.choices))]
            return agent.CompletionTurn(tool_calls=calls, prompt_tokens=100)

    toolbox = CountingToolbox()
    result = run_agent(Eager(), policy.budget_for_words(2000), toolbox=toolbox, words=800)
    assert 'Investigate before submitting' in result.rejections[0]
    assert toolbox.calls == 4 and result.submission is not None
    assert policy.budget_for_words(9000).min_tool_calls == 5


def test_validator_flags_overlong_notes():
    body = '- point\n  - ' + ' '.join(['word'] * 1200)
    long = submission(sections=[{'heading': 'H', 'body_markdown': body}])
    assert any('ceiling' in problem for problem in check_notes(long, transcript_words=3000).problems)


def test_repair_drops_owner_and_unnamed_participants():
    payload = submission(
        participants=[
            {'name': 'Riley Tan', 'evidence': 'owner'},
            {'name': 'Other attendee', 'evidence': 'voice'},
            {'name': "Riley's partner", 'evidence': 'voice'},
            {'name': 'Maya Okafor', 'evidence': 'Zoom tile'},
        ]
    )
    repaired, repairs = repair_notes(payload, open_tasks=[], owner_names=['Riley Tan'])
    assert [person['name'] for person in repaired['participants']] == ['Maya Okafor']
    assert repairs == ['participant_dropped']


def test_repair_keeps_only_new_commitments():
    payload = submission(
        action_items=[
            {'description': 'Follow up on Quorbi pilot pricing'},
            {'description': 'Close the old task', 'candidate_action': 'complete', 'target_task_id': 't1'},
            {'description': 'Email Maya the deck'},
            {'description': 'email maya the deck'},
        ]
    )
    repaired, repairs = repair_notes(payload, open_tasks=[{'description': 'Follow up on the Quorbi pilot pricing'}])
    assert [item['description'] for item in repaired['action_items']] == ['Email Maya the deck']
    assert set(repairs) == {
        'duplicate_open_task_dropped',
        'task_reconciliation_dropped',
        'duplicate_action_item_dropped',
    }


# ---------------------------------------------------------------- synthetic replay through the writer


def test_synthetic_replay_through_shaped_notes_writer(monkeypatch):
    fixture = json.loads(FIXTURE.read_text())
    lines = [f'[{sid} {spk}] {text}' for sid, spk, text in fixture['segments']] * fixture['repeat']
    prefix = build_conversation_prompt_prefix(
        conversation_id='synthetic-conversation',
        transcript='\n'.join(lines),
        started_at=START,
        timezone_name='UTC',
        language_code='en',
        speaker_map={0: fixture['owner_name'], 1: None},
        transcript_segment_ids=[sid for sid, _spk, _text in fixture['segments']],
        known_spellings='Known spellings\n{"spelling": "Quorbi"}',
    )
    frame = NotesFrameImage(data_url='data:image/jpeg;base64,AAAA', **fixture['frame'])
    turns = iter(fixture['turns'])
    seen = []

    def fake_complete(model, *, cache_options=None, cache_key=None):
        seen.append((cache_options, cache_key))

        async def complete(messages, tool_choice):
            turn = next(turns)
            return agent.CompletionTurn(
                tool_calls=[
                    call(item['name'], item['arguments'], index) for index, item in enumerate(turn['tool_calls'])
                ],
                prompt_tokens=4000,
                cached_tokens=3000,
                completion_tokens=500,
            )

        return complete

    @asynccontextmanager
    async def isolated(model):
        yield model

    monkeypatch.setattr(notes, 'get_llm', lambda *args, **kwargs: object())
    monkeypatch.setattr(serving, 'transport_ready', lambda model: True)
    monkeypatch.setattr(serving, 'model_supports_explicit_cache', lambda model: True)
    monkeypatch.setattr(serving, 'langchain_complete', fake_complete)
    monkeypatch.setattr(serving, 'isolated_notes_model', isolated)
    monkeypatch.setattr(serving, 'owner_profile', lambda uid: 'Founder of a hardware startup.')
    monkeypatch.setattr(tools.calendar_db, 'get_meetings_in_time_range', lambda *a, **k: [])
    monkeypatch.setattr(tools.screen_activity_db, 'get_screen_activity', lambda *a, **k: [])
    monkeypatch.setattr(tools, 'load_people_documents', lambda uid: [{'id': 'p1', 'name': 'Maya Okafor'}])

    structured = notes._get_shaped_conversation_notes(
        prefix,
        uid=OWNER,
        started_at=START,
        finished_at=START + timedelta(minutes=25),
        language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
        existing_action_items=[{'description': 'Follow up on Quorbi pilot pricing'}],
        screen_frames=(frame,),
        rich_context_enabled=False,
    )
    assert structured.title.startswith('Maya Okafor')
    assert [participant.name for participant in structured.participants] == ['Maya Okafor']
    assert structured.participants[0].evidence.startswith('Zoom tile')
    assert all(nested_bullet_count(section.body_markdown) for section in structured.sections)
    assert [item.description for item in structured.action_items] == ['Check the firmware fix status with the team']
    assert seen and seen[0][0] == serving.EXPLICIT_CACHE_OPTIONS and seen[0][1].startswith(prompt.PROMPT_VERSION)


def test_writer_keeps_one_shot_when_agent_declines(monkeypatch):
    monkeypatch.setattr(notes, 'agentic_notes_payload', lambda **kwargs: None)
    one_shot = []

    async def fake_run_loop(mount, evidence, model_turn, *args, **kwargs):
        one_shot.append(mount)
        return shaped_agent.LoopResult(value={'title': 'One shot'}, reason='stopped', turns=1, tool_calls=0)

    @asynccontextmanager
    async def isolated(model):
        yield model

    monkeypatch.setattr(notes, 'get_llm', lambda *args, **kwargs: object())
    monkeypatch.setattr(notes, 'isolated_notes_model', isolated)
    monkeypatch.setattr(notes, 'run_loop', fake_run_loop)
    prefix = build_conversation_prompt_prefix(
        conversation_id='c',
        transcript='hello there',
        started_at=START,
        timezone_name='UTC',
        language_code='en',
    )
    structured = notes._get_shaped_conversation_notes(
        prefix,
        uid=OWNER,
        started_at=START,
        language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
    )
    assert structured.title == 'One shot' and len(one_shot) == 1 and not one_shot[0].tools


# ---------------------------------------------------------------- naming the other speaker (v5 regression)


CALL_ROWS = [
    # A Telegram call window naming the other party, with the call controls in OCR.
    {
        'timestamp': (START + timedelta(minutes=2)).isoformat(),
        'appName': 'Telegram',
        'windowTitle': '⁨Maya Okafor⁩ – (59627)',
        'ocrText': 'Maya Okafor last seen recently End call',
    },
    # A LinkedIn profile opened from the invite just before the call.
    {
        'timestamp': (START - timedelta(minutes=3)).isoformat(),
        'appName': 'Google Chrome',
        'windowTitle': '(7) Maya Okafor | LinkedIn - Google Chrome',
        'ocrText': 'Founding Engineer',
    },
    {'timestamp': START.isoformat(), 'appName': 'Telegram', 'windowTitle': 'Omi System Updates – (1)', 'ocrText': ''},
    {'timestamp': START.isoformat(), 'appName': 'Telegram', 'windowTitle': 'Redis – (2)', 'ocrText': ''},
    {'timestamp': START.isoformat(), 'appName': 'Telegram', 'windowTitle': 'Riley Tan – (3)', 'ocrText': ''},
    {'timestamp': START.isoformat(), 'appName': 'Google Chrome', 'windowTitle': 'Boardy Boardman | LinkedIn'},
    # Outside the window: an hour before the call.
    {'timestamp': (START - timedelta(hours=1)).isoformat(), 'appName': 'Telegram', 'windowTitle': 'Old Friend – (4)'},
]


def test_screen_leads_name_the_call_party_and_skip_groups_owner_bots_and_old_rows():
    leads = screen_people_leads(
        CALL_ROWS, started_at=START, finished_at=START + timedelta(minutes=30), owner_names=['Riley Tan']
    )
    assert [lead['name'] for lead in leads] == ['Maya Okafor']
    assert leads[0]['evidence'] == ['call_window', 'profile_page'] and leads[0]['first_seen_min'] == -3


def test_packet_carries_screen_leads_in_utc(monkeypatch):
    monkeypatch.setattr(tools.calendar_db, 'get_meetings_in_time_range', lambda *a, **k: [])
    monkeypatch.setattr(tools.screen_activity_db, 'get_screen_activity', lambda *a, **k: CALL_ROWS)
    packet, _seen = tools.build_packet(
        uid=OWNER,
        conversation_id='conv-1',
        started_at=START,
        finished_at=START + timedelta(minutes=30),
        timezone_name='America/Los_Angeles',
        response_language='en',
        length='LENGTH',
        transcript_words=3000,
        account_owner_name='Riley Tan',
        task_intelligence_capture=False,
        open_tasks=[],
        roster=None,
        owner_names=['Riley Tan'],
        background=None,
        frames=(),
    )
    assert [lead['name'] for lead in packet['people_on_screen']] == ['Maya Okafor']
    assert packet['conversation']['started_at'] == '2026-10-01T15:00:00Z'
    assert serving.naming_leads(packet) == ['Maya Okafor']


def test_unnamed_speaker_is_sent_back_and_the_name_reaches_participants_and_notes():
    named = submission(
        title='Maya Okafor: pricing',
        participants=[{'name': 'Maya Okafor', 'speaker': '1', 'evidence_kind': 'screen', 'evidence': 'Telegram call'}],
        sections=[{'heading': 'Pricing', 'body_markdown': '- Maya proposed per-seat pricing\n  - $40 a seat'}],
    )
    unnamed = submission(
        title='Pricing call',
        sections=[{'heading': 'Pricing', 'body': '- The other founder proposed per-seat\n  - $40'}],
    )

    class Model(ScriptedModel):
        async def __call__(self, messages, tool_choice):
            self.choices.append(tool_choice)
            told = any('Maya Okafor' in str(m.get('content')) and m.get('role') == 'tool' for m in messages)
            payload = named if told else unnamed
            return agent.CompletionTurn(tool_calls=[call(prompt.SUBMIT, payload, len(self.choices))], prompt_tokens=10)

    model = Model()
    result = run_agent(
        model, policy.NotesAgentBudget(max_turns=4, max_tool_calls=6), words=800, naming_leads=['Maya Okafor']
    )
    # One send-back, about naming only: the `body` key slip is normalized, not mistaken for prose.
    assert len(result.rejections) == 1 and 'Maya Okafor' in result.rejections[0]
    assert 'prose' not in result.rejections[0]
    structured = agent.AgentNotesSubmission.model_validate(result.submission).to_structured()
    assert [person.name for person in structured.participants] == ['Maya Okafor']
    assert structured.participants[0].evidence == 'Telegram call'
    assert 'Maya' in structured.title and 'Maya' in structured.sections[0].body_markdown


def test_no_send_back_without_leads_or_when_someone_is_named():
    model = ScriptedModel()
    assert not run_agent(model, policy.NotesAgentBudget(max_turns=2, max_tool_calls=6)).rejections


@pytest.mark.parametrize('failure', ['deadline', 'malformed'])
def test_v2_salvages_last_repairable_submission_without_another_writer(failure):
    turns = []

    async def complete(messages, tool_choice):
        turns.append(messages)
        if len(turns) == 1:
            return agent.CompletionTurn(
                tool_calls=[
                    call(
                        prompt.SUBMIT,
                        submission(
                            sections=[{'heading': 'Topic', 'body_markdown': 'A short synthetic detail with no bullet.'}]
                        ),
                    )
                ]
            )
        if failure == 'deadline':
            raise TimeoutError('synthetic deadline')
        return agent.CompletionTurn(tool_calls=[{'id': 'bad', 'name': prompt.SUBMIT, 'arguments': 'not JSON'}])

    budget = policy.NotesAgentBudget(
        max_turns=2,
        max_tool_calls=5,
        min_tool_calls=0,
        max_cost_usd=0.02,
        deadline_seconds=60,
        force_submit_after_seconds=50,
    )
    result = run_agent(complete, budget, contract_v2=True)
    assert result.submission is not None
    assert result.submission['sections'][0]['body_markdown'].startswith('- ')
    assert 'salvaged_submission' in result.repairs
    assert len(turns) == 2


def test_v2_retains_one_shot_fallback_when_no_usable_submission_exists():
    async def complete(messages, tool_choice):
        return agent.CompletionTurn(tool_calls=[{'id': 'bad', 'name': prompt.SUBMIT, 'arguments': 'not JSON'}])

    budget = policy.NotesAgentBudget(
        max_turns=1,
        max_tool_calls=1,
        min_tool_calls=0,
        max_cost_usd=0.02,
        deadline_seconds=60,
        force_submit_after_seconds=50,
    )
    result = run_agent(complete, budget, contract_v2=True)
    assert result.submission is None and 'salvaged_submission' not in result.repairs
