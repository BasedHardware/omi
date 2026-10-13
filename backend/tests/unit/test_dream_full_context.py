"""Full-context behavior through real Dream paths, using invented evidence only."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from config.dream_agent import Caps, context_mode, FULL_CONTEXT_WINDOW, FULL_PASS_SECONDS, FULL_DRAIN_SECONDS
from database import dream_store, review_store
from models.dream_agent import Plan, Edit, Feedback
from utils import (
    dream_agent,
    dream_context,
    dream_guards,
    dream_prompt,
    dream_reads,
    dream_transport,
    dream_tools,
    dream_metrics,
)
from utils.llm.shaped_agent import Turn

UID = 'synthetic-full-owner'
NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def full(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'full')
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', ' someone-else, ' + UID + ', ')
    return Caps().for_uid(UID)


def conversation(words='toy garden ' * 40):
    return {
        'created_at': NOW,
        'structured': {'title': '', 'overview': '', 'sections': []},
        'transcript_segments': [{'speaker': 'SPEAKER_01', 'text': words}],
    }


def edit(kind='title', target='conversations/a', **kw):
    return Edit(
        kind=kind, target=target, after='Toy garden project', reason='Synthetic evidence', evidence=[target], **kw
    )


def test_allowlist_defaults_and_budgets(monkeypatch, full):
    assert context_mode(UID) == 'full'
    assert full.tokens == 416000 and full.completion_tokens == 16000 and full.edits == 25
    assert Caps().for_uid('stranger') == Caps()
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'unknown')
    assert context_mode(UID) == 'bounded'
    monkeypatch.delenv('DREAM_AGENT_CONTEXT_MODE')
    assert context_mode(UID) == 'bounded'
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'full')
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', '')
    assert Caps().for_uid(UID) == Caps()


def test_hard_budget_cannot_be_raised(monkeypatch, full):
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_TOKENS', '999999999')
    monkeypatch.setenv('DREAM_AGENT_FULL_COMPLETION_TOKENS', '999999999')
    caps = Caps().for_uid(UID)
    assert caps.tokens == FULL_CONTEXT_WINDOW
    assert caps.completion_tokens == 16000
    huge = {'memory_items/large': {'content': '界' * 400000}}
    assert not dream_prompt.fits_full(huge, caps)
    assert dream_prompt.select_full_records(huge, caps) == {}


def test_whole_records_and_one_reasoning_turn(full):
    words = 'toy garden ' * 900 + 'middle sentinel ' + 'toy garden ' * 900
    row = conversation(words)
    row['structured'] = {'title': 'title' * 200, 'overview': 'overview' * 400, 'sections': [{'body_markdown': words}]}
    records = dream_context.EvidenceRecords(
        {
            'conversations/a': row,
            'people/p': {'name': 'Invented', 'aliases': ['Example'], 'extra_field': {'full': words}},
            'memory_items/m': {'content': words, 'slot': 'garden', 'provenance': [{'kind': 'conversation', 'id': 'a'}]},
            'action_items/t': {'description': words, 'created_at': NOW, 'custom': words},
        },
        targets=['conversations/a'],
    )
    before = deepcopy(records)
    calls = []

    async def turn(uid, lane, mount, messages):
        assert lane == dream_transport.MAIN_LANE and mount.schema is Plan
        assert mount.budget.deadline_seconds == 480
        payload = json.loads(messages[-1]['content'])
        assert 'roles' not in payload
        for ref, stored in records.items():
            projected = json.loads(payload['records'][ref])
            assert all(
                projected[k] == json.loads(json.dumps(v, default=str))
                for k, v in stored.items()
                if k != 'transcript_segments'
            )
        segment = json.loads(payload['records']['conversations/a'])['transcript_segments'][0]
        assert segment['text'] == words and segment['speaker_label'] == 'SPEAKER_01'
        calls.append(lane)
        return Turn(
            value=Plan(
                edits=[
                    Edit(
                        kind='spelling',
                        target='people/p',
                        before='Invented',
                        after='Example',
                        reason='Synthetic',
                        evidence=['people/p'],
                    )
                ]
            ),
            tokens=123,
        )

    result = asyncio.run(dream_agent.dry_run(UID, records, turn=turn))
    assert calls == [dream_transport.MAIN_LANE]
    assert records == before
    assert len(result['plan']['edits']) == 1
    assert result['plan']['edits'][0]['policy'] == 'suggest'
    assert len(result['plan']['questions']) == 1
    assert 'context_target' not in result['guard_decisions']
    assert result['raw_plan']['edits'][0]['target'] == 'people/p'
    assert result['input_tokens_estimate'] > 1000


def test_drop_whole_records_by_priority_and_do_not_edit_dropped(full, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_TOKENS', '5000')
    caps = Caps().for_uid(UID)
    records = dream_context.EvidenceRecords(
        {
            'memory_items/context': {'content': 'c' * 15000},
            'memory_items/huge': {'content': 'h' * 60000},
            'memory_items/target': {'content': 't' * 6000},
            'memory_items/small': {'content': 'tail'},
        },
        targets=['memory_items/huge', 'memory_items/target', 'memory_items/small'],
    )
    selected = dream_prompt.select_full_records(records, caps)
    assert list(selected) == ['memory_items/target', 'memory_items/small']
    assert selected['memory_items/target']['content'] == 't' * 6000

    async def turn(*args):
        return Turn(value=Plan(edits=[edit('memory', 'memory_items/context')]), tokens=100)

    result = asyncio.run(dream_agent.dry_run(UID, records, turn=turn))
    assert len(result['raw_plan']['edits']) == 1 and not result['plan']['edits']
    assert result['guard_decisions'] == {'invalid_evidence': 1}


def test_full_guards_and_tool_backstop(full):
    records = dream_context.EvidenceRecords(
        {
            'conversations/a': conversation(),
            'conversations/later': {**conversation(), 'created_at': NOW + timedelta(hours=1)},
            'action_items/t': {'created_at': NOW, 'status': 'active'},
        },
        targets=['conversations/a'],
    )
    records.context_mode = 'full'
    placeholder = edit().model_copy(update={'after': 'This conversation toy garden'})
    retirement = Edit(kind='retire_task', target='action_items/t', reason='Synthetic', evidence=['conversations/later'])
    feedback = Feedback(
        component='notes',
        failure_class='success',
        severity='info',
        count=1,
        latency_ms=0,
        error_rate=0,
        reproduction='English translation is correct.',
    )
    plan = Plan(edits=[placeholder, retirement], feedback=[feedback])
    assert len(dream_guards.filter_plan(plan, records).edits) == 2
    assert dream_guards.filter_plan(plan, records).feedback == [feedback]
    dream_tools.validate_edit(retirement, records)
    dream_tools.validate_edit(placeholder, records)
    bounded = dream_context.EvidenceRecords(records, targets=set(records))
    bounded.context_mode = 'bounded'
    reasons = {}
    dream_guards.filter_plan(plan, bounded, usage_sink=reasons)
    assert reasons['rejected'] == {'placeholder': 1, 'task_too_recent': 1, 'not_a_failure': 1}
    records['conversations/a']['structured']['title'] = 'Existing'
    stale = retirement.model_copy(update={'evidence': ['conversations/a']})
    reasons = {}
    assert not dream_guards.filter_plan(Plan(edits=[placeholder, stale]), records, usage_sink=reasons).edits
    assert reasons['rejected'] == {'nonempty_field': 1, 'stale_task_evidence': 1}
    with pytest.raises(review_store.ReviewConflict, match='summary changed'):
        dream_tools.validate_edit(placeholder, records)


def test_full_dry_run_privacy_caps_and_raw_plan(full, monkeypatch):
    records = {'conversations/a': conversation()}
    private = Feedback(
        component='notes',
        failure_class='spelling',
        severity='warning',
        count=1,
        latency_ms=0,
        error_rate=0,
        reproduction='toy garden toy garden',
    )
    plan = Plan(edits=[edit() for _ in range(30)], feedback=[private])

    async def turn(*args):
        return Turn(value=plan, tokens=100)

    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: pytest.fail('dry run acquired lease'))
    result = asyncio.run(dream_agent.dry_run(UID, records, turn=turn))
    assert len(result['plan']['edits']) == 25
    assert not result['plan']['feedback']
    assert len(result['raw_plan']['edits']) == 30 and len(result['raw_plan']['feedback']) == 1
    assert result['guard_decisions'] == {'edit_cap': 5, 'privacy_rejected': 1}


def test_dirty_admits_all_fitting_targets_and_full_neighbours(full, monkeypatch):
    records = {f'conversations/{i}': conversation('toy garden ' * 300) for i in range(32)}
    dirty = [
        SimpleNamespace(
            to_dict=lambda i=i: {'collection': 'conversations', 'id': str(i), 'version': str(i), 'last_changed_at': NOW}
        )
        for i in range(32)
    ]
    monkeypatch.setattr(dream_store, 'dirty_refs', lambda *a, **k: dirty)
    monkeypatch.setattr(dream_reads, 'cached_reader', lambda *a: lambda uid, ref: records[ref])
    monkeypatch.setattr(dream_reads, 'add_seed_safely', lambda uid, records, *a, **k: records)
    neighbour = {'content': 'neighbour ' * 1000}
    monkeypatch.setattr(
        dream_reads, 'context_candidates', lambda *a, **k: iter([('memory_items/n', neighbour, 'links')])
    )
    diagnostics = {}
    admitted, consumed = dream_reads.read_changes(UID, {'started_at': NOW}, full, diagnostics=diagnostics)
    assert len(consumed) == 32 and len(admitted.targets) == 32 and len(admitted) == 33
    assert admitted['memory_items/n'] == neighbour and admitted.context_mode == 'full'
    assert diagnostics['dirty_counts']['budget_deferred'] == 0
    assert dream_prompt.fits_full(admitted, full)


def test_context_skips_oversized_whole_record_then_admits_small(full):
    targets = dream_context.EvidenceRecords({'memory_items/t': {'content': 'target'}})
    targets.context_mode = 'full'
    candidates = [
        ('memory_items/huge', {'content': 'x' * 1100000}, 'links'),
        ('memory_items/small', {'content': 'small'}, 'links'),
    ]
    records = dream_context.add_context(targets, candidates, full)
    assert list(records) == ['memory_items/t', 'memory_items/small']


def test_gateway_full_completion_and_timeout(full, monkeypatch):
    client = SimpleNamespace(
        post=AsyncMock(
            return_value=httpx.Response(
                200,
                request=httpx.Request('POST', 'https://synthetic.invalid'),
                json={
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 100},
                    'choices': [{'message': {'content': '{}'}}],
                },
            )
        )
    )
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    monkeypatch.setattr(dream_transport.dream_capacity, 'available_model', AsyncMock(return_value='synthetic-reserved'))
    asyncio.run(
        dream_transport.model_turn(
            UID, dream_transport.MAIN_LANE, dream_prompt.full_mount(full), [], completion_limit=full.completion_tokens
        )
    )
    assert client.post.call_args.kwargs['json']['max_completion_tokens'] == 16000
    assert client.post.call_args.kwargs['timeout'].read == 480
    assert client.post.call_args.kwargs['json']['model'] == dream_transport.MAIN_LANE


def test_metrics_closed_counts_only(full, caplog):
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass(
            {
                'status': 'complete',
                'context_mode': 'full',
                'input_tokens_estimate': 400000,
                'targets': 32,
                'records': 35,
                'rejected': {'nonempty_field': 2, 'private sentinel': 4},
                'raw_plan': {'private': 'private sentinel'},
                'proposed': {'private': 'private sentinel'},
            }
        )
    assert 'context_mode=full input_tokens_estimate=400000 targets=32 records=35' in caplog.text
    assert '"nonempty_field": 2' in caplog.text
    assert 'private sentinel' not in caplog.text


def test_pass_and_drain_deadlines_and_slots(full, monkeypatch):
    claim = AsyncMock(return_value=('slot', 'token'))
    monkeypatch.setattr(dream_agent.dream_capacity, 'claim', claim)
    monkeypatch.setattr(dream_agent.dream_capacity, 'release', AsyncMock())
    run = AsyncMock(return_value={'status': 'complete'})
    monkeypatch.setattr(dream_agent, '_run_admitted_pass', run)
    asyncio.run(dream_agent.run_pass(UID))
    assert run.call_args.kwargs['timeout_seconds'] == FULL_PASS_SECONDS
    assert claim.call_args.kwargs['slot_seconds'] == FULL_DRAIN_SECONDS
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setattr(dream_agent.dream_capacity, 'available_model', AsyncMock(return_value='reserved'))
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: [UID])
    assert asyncio.run(dream_agent.drain()) == [{'status': 'complete'}]


def test_proposal_acceptance_retains_full_guard_mode(full, monkeypatch):
    records = {'action_items/t': {'created_at': NOW}, 'conversations/later': {'created_at': NOW + timedelta(hours=1)}}
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: deepcopy(snapshot))
    validated = dream_tools.revalidate_proposal(UID, {'records': records, 'context_mode': 'full'})
    assert validated.context_mode == 'full'
    retirement = Edit(kind='retire_task', target='action_items/t', reason='Synthetic', evidence=['conversations/later'])
    assert dream_guards.task_rejection(retirement, records[retirement.target], validated) is None
