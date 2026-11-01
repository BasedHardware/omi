"""Edit-level value judge: stratified owner-independent sampling, blind input, content-free records."""

import asyncio
import json
import logging

import pytest

from models.agent_tools import Verification, VerificationBatch
from models.review import ChangeRef, ReviewChange
from tests.unit.test_dream_cleanup_edits import UID
from tests.unit.test_dream_harness_runtime import runtime, store  # noqa: F401  (fixtures)
from tests.unit.test_dream_session import call
from utils import dream_agent, dream_judge, dream_telemetry
from utils.dream_harness_transport import MAIN_LANE, VERIFY_LANE
from utils.llm.shaped_agent import Turn


def test_rare_kinds_are_always_judged_and_common_kinds_by_a_salted_key_share():
    assert dream_judge.stratum('merge_people', 'agent:merge_people:x', percent=0) == 'always'
    assert dream_judge.stratum('dismiss_person', 'agent:dismiss_person:x', percent=0) is None
    assert dream_judge.stratum('dismiss_person', 'agent:dismiss_person:x', percent=100) == 'sampled'
    keys = [f'agent:spelling:{index}' for index in range(4000)]
    share = sum(dream_judge.stratum('spelling', key, percent=2) == 'sampled' for key in keys) / len(keys)
    assert 0.01 < share < 0.03
    # Deterministic per edit key; nothing about the owner enters the choice.
    assert [dream_judge.stratum('spelling', key, percent=2) for key in keys[:50]] == [
        dream_judge.stratum('spelling', key, percent=2) for key in keys[:50]
    ]


def test_env_controls_fail_closed(monkeypatch):
    monkeypatch.setenv(dream_judge.MODE_ENV, 'serve')
    assert dream_judge.mode() == 'off'
    monkeypatch.delenv(dream_judge.MODE_ENV)
    assert dream_judge.mode() == 'shadow'
    monkeypatch.setenv(dream_judge.COMMON_PERCENT_ENV, 'many')
    assert dream_judge.common_percent() == 0.0
    monkeypatch.setenv(dream_judge.TOKENS_ENV, '-5')
    assert dream_judge.token_allowance() == 0


def test_projection_is_the_owner_visible_change_without_the_proposer_reason():
    change = ReviewChange(
        change_id='c1',
        kind='other',
        title='Dismiss person',
        reason='Proposer says this is junk',
        edit_kind='dismiss_person',
        before='Canadian',
        after='(dismissed)',
        refs=[ChangeRef(type='person', id='junk', label='Canadian')],
        created_at='2026-10-31T00:00:00Z',
    )
    projection = dream_judge.projection(change)
    assert projection == {
        'kind': 'dismiss_person',
        'before': 'Canadian',
        'after': '(dismissed)',
        'speech': [],
        'refs': ['Canadian'],
    }
    assert 'Proposer' not in json.dumps(projection)


def test_judge_keeps_only_supplied_ids_and_fails_open():
    async def answer(mount, messages):
        rows = json.loads(messages[-1]['content'].split('\n', 1)[1])
        decisions = [
            dream_judge.Judgment(id=row['id'], grounded=2, owner_appropriate=2, useful=1, verdict='good')
            for row in rows
        ]
        decisions.append(
            dream_judge.Judgment(id='stranger', grounded=0, owner_appropriate=0, useful=0, verdict='harmful')
        )
        return Turn(tokens=10, value=dream_judge.JudgmentBatch(decisions=decisions))

    async def boom(mount, messages):
        raise RuntimeError('synthetic')

    rows = [('a', {'kind': 'spelling'})]
    assert set(asyncio.run(dream_judge.judge(rows, answer, tokens=10000, deadline_seconds=5))) == {'a'}
    assert asyncio.run(dream_judge.judge(rows, boom, tokens=10000, deadline_seconds=5)) == {}
    assert asyncio.run(dream_judge.judge(rows, answer, tokens=500, deadline_seconds=5)) == {}


def test_judge_record_is_content_free(caplog):
    with caplog.at_level(logging.INFO, logger='utils.dream_telemetry'):
        dream_judge.record(
            'merge_people',
            'always',
            dream_judge.Judgment(id='x', grounded=2, owner_appropriate=1, useful=0, verdict='neutral'),
        )
        dream_judge.record('people/Anna', 'weird', None)
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.getMessage().startswith('{')]
    assert lines == [
        {
            'event': 'dream_judge',
            'kind': 'merge_people',
            'stratum': 'always',
            'verdict': 'neutral',
            'grounded': 2,
            'owner_appropriate': 1,
            'useful': 0,
        },
        {
            'event': 'dream_judge',
            'kind': 'other',
            'stratum': 'other',
            'verdict': 'unjudged',
            'grounded': -1,
            'owner_appropriate': -1,
            'useful': -1,
        },
    ]


def _pass_model(judged):
    async def model(uid, lane, mount, messages):
        if lane == MAIN_LANE:
            calls = [
                call(
                    'propose_edit',
                    {
                        'edit': {
                            'kind': 'dismiss_person',
                            'target': 'people/junk',
                            'evidence': ['conversations/one'],
                            'reason': 'Synthetic junk profile',
                            'value': 4,
                        }
                    },
                ),
                call('finish', {'summary': 'Checked synthetic records', 'notes': ''}, 2),
            ]
            return Turn(
                tokens=10,
                tool_calls=tuple(calls),
                messages=({'role': 'assistant', 'content': None, 'tool_calls': calls},),
            )
        assert lane == VERIFY_LANE
        rows = json.loads(messages[-1]['content'].split('\n', 1)[1])
        if mount.schema is dream_judge.JudgmentBatch:
            judged.append(messages[-1]['content'])
            return Turn(
                tokens=20,
                value=dream_judge.JudgmentBatch(
                    decisions=[
                        dream_judge.Judgment(id=row['id'], grounded=2, owner_appropriate=2, useful=1, verdict='good')
                        for row in rows
                    ]
                ),
            )
        return Turn(
            tokens=20,
            value=VerificationBatch(decisions=[Verification(id=row['id'], agree=True, reason='ok') for row in rows]),
        )

    return model


@pytest.mark.parametrize('percent,expected', [('100', 1), ('0', 0)])
def test_applied_common_edit_is_judged_only_when_sampled(runtime, monkeypatch, percent, expected):
    monkeypatch.setenv(dream_judge.COMMON_PERCENT_ENV, percent)
    records = []
    monkeypatch.setattr(dream_judge, 'record', lambda kind, label, judgment: records.append((kind, label, judgment)))
    judged = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_pass_model(judged)))
    assert report['outcomes'][0]['status'] == 'applied', report
    assert len(judged) == expected and len(records) == expected
    if expected:
        assert records[0][0] == 'dismiss_person' and records[0][2].verdict == 'good'
        assert 'Synthetic junk profile' not in judged[0]
        assert report['levers']['value_judge'] == {'arm': 'shadow', 'sent': 1, 'judged': 1, 'harmful': 0}


def test_judge_off_makes_no_extra_call(runtime, monkeypatch):
    monkeypatch.setenv(dream_judge.MODE_ENV, 'off')
    monkeypatch.setenv(dream_judge.COMMON_PERCENT_ENV, '100')
    judged = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_pass_model(judged)))
    assert report['outcomes'][0]['status'] == 'applied' and judged == []
    assert 'value_judge' not in report['levers']


def test_pass_telemetry_keeps_the_judge_counts():
    payload = dream_telemetry.pass_payload(
        {'status': 'complete', 'levers': {'value_judge': {'arm': 'shadow', 'sent': 2, 'judged': 2, 'harmful': 1}}}
    )
    assert payload['levers']['value_judge'] == {'arm': 'shadow', 'sent': 2, 'judged': 2, 'harmful': 1}


def _export_module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / 'scripts' / 'dream-label-export.py'
    spec = importlib.util.spec_from_file_location('dream_label_export', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_calibration_export_puts_rare_kinds_first_and_hides_the_judge_verdict():
    export = _export_module()
    rows = [('dismiss_person', {'edit_key': f'agent:dismiss_person:{i}'}, {'change_id': f'd{i}'}) for i in range(10)]
    rows.append(('merge_people', {'edit_key': 'agent:merge_people:m'}, {'change_id': 'm1'}))
    picked = export.sample(rows, 4, seed='2026-W44')
    assert picked[0] == (rows[-1], 'always') and len(picked) == 4
    assert [stratum for _row, stratum in picked[1:]] == ['random'] * 3
    assert export.sample(rows, 4, seed='2026-W44') == picked
    judgment = dream_judge.Judgment(id='0', grounded=2, owner_appropriate=2, useful=0, verdict='neutral')
    item = export.item(
        'merge_people',
        {'edit_key': 'agent:merge_people:m', 'created_at': '2026-10-30'},
        {'change_id': 'm1', 'before': 'Anna, Ana', 'after': 'Anna', 'reason': 'Proposer reason', 'undone': True},
        'always',
        judgment,
    )
    assert item['id'] == 'm1' and item['content']['type'] == 'proposal'
    assert item['content']['change'] == {'kind': 'Merge people', 'before': 'Anna, Ana', 'after': 'Anna'}
    assert item['hidden']['judge']['verdict'] == 'neutral' and item['hidden']['undone'] is True
    # Blind: no model output or proposer reason outside hidden.
    visible = json.dumps({key: value for key, value in item.items() if key != 'hidden'})
    assert 'neutral' not in visible and 'Proposer reason' not in visible


def test_projection_keeps_cited_speech_with_speakers():
    from models.review import SpellingContext, SpellingContextSegment

    change = ReviewChange(
        change_id='c2',
        kind='other',
        title='Spelling',
        edit_kind='spelling',
        before='kiesh',
        after='quiche',
        context=SpellingContext(
            conversation_title='Lunch',
            segments=[
                SpellingContextSegment(text='What should we eat?', speaker_label='Anna'),
                SpellingContextSegment(text='Maybe kiesh tonight.', is_user=True),
            ],
            main_index=1,
        ),
        created_at='2026-10-31T00:00:00Z',
    )
    assert dream_judge.projection(change)['speech'] == [
        {'speaker': 'Anna', 'text': 'What should we eat?'},
        {'speaker': 'owner', 'text': 'Maybe kiesh tonight.', 'cited': True},
    ]


def test_one_call_covers_every_edit_a_pass_can_apply():
    from config.dream_agent import Caps

    assert dream_judge.MAX_ITEMS >= Caps().edits


def test_judge_calls_are_capped_per_sweep(monkeypatch):
    monkeypatch.setenv(dream_judge.CALLS_PER_SWEEP_ENV, '2')
    dream_judge._sweep_calls.clear()
    assert [dream_judge.take_call('sweep-a') for _ in range(3)] == [True, True, False]
    assert dream_judge.take_call('sweep-b') is True
    monkeypatch.setenv(dream_judge.CALLS_PER_SWEEP_ENV, 'x')
    assert dream_judge.take_call('sweep-c') is False


def test_manual_runs_are_not_judged(runtime, monkeypatch):
    monkeypatch.setenv(dream_judge.COMMON_PERCENT_ENV, '100')
    dream_judge._sweep_calls.clear()
    judged = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_pass_model(judged), trigger='manual'))
    assert report['outcomes'][0]['status'] == 'applied' and judged == []


def test_reserved_only_transport_forces_reserved_capacity(monkeypatch):
    from utils import dream_harness_transport as transport

    seen = []

    async def available(mode, owner_allowlisted):
        seen.append(mode)
        return None

    async def warm(uid):
        return None

    monkeypatch.setattr(transport, 'generated_compute_configured', lambda: False)
    monkeypatch.setattr(transport, 'admission_for', lambda uid: ('on_demand', True))
    monkeypatch.setattr(transport, 'warm_rollout_cohorts', warm)
    monkeypatch.setattr(transport.dream_capacity, 'available_model', available)
    from utils.llm.shaped_agent import Budget, Mount

    mount = Mount(
        instructions='x', schema=dream_judge.JudgmentBatch, budget=Budget(turns=1, tokens=10000, deadline_seconds=5)
    )
    for reserved_only in (False, True):
        with pytest.raises(transport.CapacityWait):
            asyncio.run(
                transport.model_turn(
                    'synthetic-owner',
                    transport.VERIFY_LANE,
                    mount,
                    [{'role': 'user', 'content': 'x'}],
                    reserved_only=reserved_only,
                )
            )
    assert seen == ['on_demand', 'reserved']


def test_export_requires_explicit_owner_consent():
    from config.refactor_modes import uid_digest

    export = _export_module()
    assert export.consented('owner-a', environ={}) is False
    assert export.consented('owner-a', environ={export.CONSENT_ENV: uid_digest('owner-b')}) is False
    assert export.consented('owner-a', environ={export.CONSENT_ENV: 'x,' + uid_digest('owner-a').upper()}) is True


def test_overlapping_sweeps_keep_their_own_counts(monkeypatch):
    monkeypatch.setenv(dream_judge.CALLS_PER_SWEEP_ENV, '1')
    dream_judge._sweep_calls.clear()
    assert dream_judge.take_call('sweep-a') is True
    assert dream_judge.take_call('sweep-b') is True
    # sweep-b starting did not reset sweep-a.
    assert dream_judge.take_call('sweep-a') is False


def test_operator_runs_with_judge_false_are_not_judged(runtime, monkeypatch):
    monkeypatch.setenv(dream_judge.COMMON_PERCENT_ENV, '100')
    dream_judge._sweep_calls.clear()
    judged = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_pass_model(judged), judge=False))
    assert report['outcomes'][0]['status'] == 'applied' and judged == []


def test_export_stops_spending_after_a_failed_call(monkeypatch):
    export = _export_module()
    calls = []

    async def failing(*args, **kwargs):
        calls.append(kwargs.get('reserved_only'))
        raise RuntimeError('synthetic billed failure')

    monkeypatch.setattr(export.dream_harness_transport, 'model_turn', failing)
    rows = [(('spelling', {}, {'edit_kind': 'spelling'}), 'random') for _ in range(dream_judge.MAX_ITEMS + 1)]
    assert asyncio.run(export.judged('owner-a', rows)) == {}
    # The second batch had no allowance left, so only the first batch called out, reserved-only.
    assert calls == [True]


def test_export_segments_keep_speaker_names():
    export = _export_module()
    change = {
        'change_id': 'c3',
        'edit_kind': 'spelling',
        'before': 'kiesh',
        'after': 'quiche',
        'context': {
            'conversation_title': 'Lunch',
            'segments': [
                {'text': 'What should we eat?', 'speaker_label': 'Anna'},
                {'text': 'Maybe kiesh.', 'is_user': True},
            ],
            'main_index': 1,
        },
    }
    item = export.item('spelling', {'edit_key': 'agent:spelling:c3'}, change, 'random', None)
    segments = item['content']['evidence'][0]['segments']
    assert [(s['name'], s['is_user']) for s in segments] == [('Anna', False), ('You', True)]
    assert item['content']['evidence'][0]['cited'] == ['1']
