"""Verification budget hold, unverified reasons and the liberal-verifier lever."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from config import dream_levers
from config.dream_session import SessionLimits
from models.agent_tools import Verification, VerificationBatch
from tests.unit.test_dream_cleanup_edits import records, UID
from tests.unit.test_dream_harness_runtime import runtime, store  # noqa: F401  (fixtures)
from tests.unit.test_dream_session import call
from utils import dream_agent, dream_seed, dream_telemetry
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.dream_harness_transport import MAIN_LANE, VERIFY_LANE
from utils.dream_verify import verify
from utils.llm.shaped_agent import Turn

LIMITS = SessionLimits(bucket='light', turns=16, tools=16, read_bytes=640000, read_call_bytes=64000, tokens=400000)


def _limited(runtime, monkeypatch):
    owner_records = EvidenceRecords(records(runtime))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(owner_records), 'vocabulary': []}, owner_records, [], LIMITS),
    )


def _spender(votes=(True, True), late=False):
    """Stage one dismissal, then read until the budget stops the loop.

    ``late`` stages the dismissal together with finish on the turn that reaches the
    budget edge instead of on the first turn. A ``None`` vote is a failed call.
    """
    main = []
    verified = []

    async def model(uid, lane, mount, messages):
        if lane == VERIFY_LANE:
            batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
            vote = votes[len(verified)]
            verified.append(1)
            if vote is None:
                raise RuntimeError('synthetic transport failure')
            return Turn(
                tokens=200,
                prompt_tokens=200,
                value=VerificationBatch(
                    decisions=[Verification(id=row['id'], agree=vote, reason='Synthetic check') for row in batch]
                ),
            )
        assert lane == MAIN_LANE
        main.append(1)
        step = len(main)
        # 400k budget at 150k per turn: the third turn spends everything the hold leaves.
        edge = step == 3
        calls = [call('read', {'refs': ['conversations/one']}, index=step)]
        if late and edge:
            calls = [call('finish', {'summary': 'Checked synthetic records', 'notes': ''}, index=step)]
        if (late and edge) or (not late and step == 1):
            calls.insert(
                0,
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
                    index=100,
                ),
            )
        # Spend the weighted budget the turn was allowed, as a long uncached prompt would.
        spend = max(0, min(150000, (mount.budget.tokens or 0) - 500))
        return Turn(
            tokens=1000,
            prompt_tokens=1000,
            completion_tokens=0,
            cached_tokens=0,
            price_weighted_tokens=spend,
            tool_calls=tuple(calls),
            messages=({'role': 'assistant', 'content': None, 'tool_calls': calls},),
        )

    return model, verified


def _status(report):
    return [row['status'] for row in report['outcomes'] if row.get('kind') == 'dismiss_person']


def test_verify_hold_serves_by_default_and_verifies_budget_stopped_work(runtime, monkeypatch):
    monkeypatch.delenv(dream_levers.VERIFY_HOLD_MODE_ENV, raising=False)
    _limited(runtime, monkeypatch)
    model, verified = _spender()
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', report
    assert report['stop_reason'] == 'dream_input_token_budget'
    assert len(verified) == 2 and _status(report) == ['applied']
    hold = report['levers']['verify_hold']
    assert hold['arm'] == 'serve' and hold['held'] > 0
    assert report['verify_reasons'] == {}


def test_without_the_hold_budget_stopped_work_is_dropped_with_a_reason(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.VERIFY_HOLD_MODE_ENV, 'off')
    monkeypatch.setenv(dream_levers.LIBERAL_VERIFIER_MODE_ENV, 'off')
    _limited(runtime, monkeypatch)
    model, verified = _spender()
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert not verified and _status(report) == ['verifier_unverified']
    assert report['verify_reasons'] == {'budget_tokens': 1}
    assert 'verify_hold' not in report['levers']
    assert dream_telemetry.pass_payload(report)['verify_reasons'] == {'budget_tokens': 1}


def test_verify_hold_shadow_measures_without_changing_the_budget(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.VERIFY_HOLD_MODE_ENV, 'shadow')
    monkeypatch.setenv(dream_levers.LIBERAL_VERIFIER_MODE_ENV, 'off')
    _limited(runtime, monkeypatch)
    model, verified = _spender()
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert not verified and _status(report) == ['verifier_unverified']
    assert report['levers']['verify_hold']['arm'] == 'shadow' and report['levers']['verify_hold']['held'] > 0


def test_hold_covers_a_proposal_staged_with_finish_at_the_budget_edge(runtime, monkeypatch):
    monkeypatch.delenv(dream_levers.VERIFY_HOLD_MODE_ENV, raising=False)
    _limited(runtime, monkeypatch)
    model, verified = _spender(late=True)
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert len(verified) == 2 and _status(report) == ['applied'], report['verify_reasons']


@pytest.mark.parametrize('arm,status', [('shadow', 'verifier_unverified'), ('serve', 'applied')])
def test_liberal_verifier_applies_one_agree_and_one_failed_call_only_in_serve(runtime, monkeypatch, arm, status):
    monkeypatch.setenv(dream_levers.LIBERAL_VERIFIER_MODE_ENV, arm)
    _limited(runtime, monkeypatch)
    model, _ = _spender(votes=(True, None))
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert _status(report) == [status] and report['verify_reasons'] == {'call_failed': 1}
    lever = report['levers']['liberal_verifier']
    assert lever['would_apply'] == 1 and lever['applied'] == (1 if arm == 'serve' else 0)


@pytest.mark.parametrize('votes', [(False, None), (None, None)])
def test_liberal_verifier_never_applies_without_an_agree_or_after_a_disagree(runtime, monkeypatch, votes):
    monkeypatch.setenv(dream_levers.LIBERAL_VERIFIER_MODE_ENV, 'serve')
    _limited(runtime, monkeypatch)
    model, _ = _spender(votes=votes)
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert _status(report) == ['verifier_unverified']
    assert report['levers']['liberal_verifier']['would_apply'] == 0


def test_liberal_verifier_never_applies_zero_vote_budget_items(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.VERIFY_HOLD_MODE_ENV, 'off')
    monkeypatch.setenv(dream_levers.LIBERAL_VERIFIER_MODE_ENV, 'serve')
    _limited(runtime, monkeypatch)
    model, verified = _spender()
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert not verified and _status(report) == ['verifier_unverified']
    assert report['verify_reasons'] == {'budget_tokens': 1}


def test_liberal_verifier_defaults_to_shadow(monkeypatch):
    monkeypatch.delenv(dream_levers.LIBERAL_VERIFIER_MODE_ENV, raising=False)
    assert dream_levers.arm(dream_levers.LIBERAL_VERIFIER_MODE_ENV, 'synthetic-owner') == 'shadow'
    assert dream_levers.arm(dream_levers.VERIFY_HOLD_MODE_ENV, 'synthetic-owner') == 'serve'


# --- per-item unverified reasons ---------------------------------------------------------------


def _item(id_='synthetic-proposal', name='Canadian'):
    return SimpleNamespace(
        id=id_,
        refs=('people/junk',),
        records={'people/junk': {'name': name}},
        payload=lambda: {'id': id_, 'kind': 'dismiss_person', 'operation': {'reason': 'Junk'}},
    )


def _reasons(turn, items, **kwargs):
    telemetry = {}
    asyncio.run(verify(items, turn, telemetry=telemetry, **kwargs))
    return telemetry.get('unverified_reasons', {})


def test_reasons_name_oversized_invalid_ids_failed_calls_and_budget():
    async def agree(mount, messages):
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=10,
            value=VerificationBatch(decisions=[Verification(id=row['id'], agree=True, reason='ok') for row in batch]),
        )

    async def no_ids(mount, messages):
        return Turn(tokens=10, value=VerificationBatch(decisions=[]))

    async def boom(mount, messages):
        raise RuntimeError('synthetic transport failure')

    assert _reasons(agree, [_item()], tokens=100000, deadline_seconds=5) == {}
    assert _reasons(agree, [_item(name='x' * 30000)], tokens=100000, deadline_seconds=5) == {
        'synthetic-proposal': 'oversized'
    }
    assert _reasons(no_ids, [_item()], tokens=100000, deadline_seconds=5) == {'synthetic-proposal': 'ids_invalid'}
    assert _reasons(boom, [_item()], tokens=100000, deadline_seconds=5) == {'synthetic-proposal': 'call_failed'}
    assert _reasons(agree, [_item()], tokens=500, deadline_seconds=5) == {'synthetic-proposal': 'budget_tokens'}
    assert _reasons(agree, [_item()], tokens=100000, deadline_seconds=0) == {'synthetic-proposal': 'budget_deadline'}

    async def refused(mount, messages):
        raise ValueError('dream_input_token_budget')

    async def slow(mount, messages):
        await asyncio.sleep(2.0)
        return await agree(mount, messages)

    assert _reasons(refused, [_item()], tokens=100000, deadline_seconds=5) == {'synthetic-proposal': 'budget_tokens'}
    assert _reasons(slow, [_item()], tokens=100000, deadline_seconds=0.5) == {'synthetic-proposal': 'budget_deadline'}


def test_reserve_pays_two_calls_per_batch():
    from utils.dream_cost import VERIFIER_CALL_FLOOR, verification_hold_tokens, verification_reserve_tokens

    one = verification_reserve_tokens([_item()], completion_tokens=256)
    many = verification_reserve_tokens([_item(id_=f'p{index}') for index in range(30)], completion_tokens=256)
    assert one == 2 * VERIFIER_CALL_FLOOR
    # 30 items split into two batches of at most 25.
    assert many >= 2 * one
    # Headroom for the next turn's proposals, capped at 10% of the pass budget.
    assert verification_hold_tokens([], completion_tokens=256, pass_tokens=10000) == 1000


def test_light_pass_headroom_funds_one_full_batch():
    from config.dream_session import LIGHT_TOKENS
    from utils.dream_cost import verification_hold_tokens, verification_reserve_tokens

    # Largest evidence the verifier accepts (just under its 24000-byte ceiling).
    largest = _item(name='n' * 23700)
    assert verification_hold_tokens([], completion_tokens=4096, pass_tokens=LIGHT_TOKENS) >= (
        verification_reserve_tokens([largest], completion_tokens=4096)
    )


def test_budget_limited_skip_is_budget_tokens_and_per_call_timeout_is_deadline():
    async def agree(mount, messages):
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=10,
            value=VerificationBatch(decisions=[Verification(id=row['id'], agree=True, reason='ok') for row in batch]),
        )

    async def slow(mount, messages):
        await asyncio.sleep(2.0)
        return await agree(mount, messages)

    # Within the verifier ceiling but beyond what this budget affords: a budget skip.
    assert _reasons(agree, [_item(name='n' * 6000)], tokens=6000, deadline_seconds=5) == {
        'synthetic-proposal': 'budget_tokens'
    }
    assert _reasons(slow, [_item()], tokens=100000, deadline_seconds=5, verifier_seconds=0.5) == {
        'synthetic-proposal': 'budget_deadline'
    }


def test_second_call_stop_names_its_cause_and_early_timeout_is_a_failed_call():
    async def spend_most(mount, messages):
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=9000,
            price_weighted_tokens=9000,
            value=VerificationBatch(decisions=[Verification(id=row['id'], agree=True, reason='ok') for row in batch]),
        )

    async def early_timeout(mount, messages):
        raise TimeoutError('synthetic provider timeout')

    assert _reasons(spend_most, [_item()], tokens=10000, deadline_seconds=5) == {'synthetic-proposal': 'budget_tokens'}
    assert _reasons(early_timeout, [_item()], tokens=100000, deadline_seconds=5) == {
        'synthetic-proposal': 'call_failed'
    }


def test_verifier_payload_is_the_compact_utf8_form_the_reserve_measures():
    from utils.agent_capabilities.session import serialized_bytes
    from utils.dream_verify import compact_json, evidence

    item = _item(name='名前' * 50)
    sent = []

    async def capture(mount, messages):
        sent.append(messages[-1]['content'].split('\n', 1)[1])
        batch = json.loads(sent[-1])
        return Turn(
            tokens=10,
            value=VerificationBatch(decisions=[Verification(id=row['id'], agree=True, reason='ok') for row in batch]),
        )

    assert _reasons(capture, [item], tokens=100000, deadline_seconds=5) == {}
    assert sent[0] == compact_json([evidence(item)])
    assert len(sent[0].encode()) == serialized_bytes([evidence(item)])


def test_small_verify_budget_still_batches_ordinary_evidence():
    # The old tokens // 8 ceiling dropped ordinary evidence as oversized whenever the
    # verify budget was a tight hold; a hold sized for the evidence must verify it.
    item = _item(name='n' * 6000)
    seen = []

    async def agree(mount, messages):
        seen.append(1)
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=10,
            value=VerificationBatch(decisions=[Verification(id=row['id'], agree=True, reason='ok') for row in batch]),
        )

    assert _reasons(agree, [item], tokens=2 * (6000 // 3 + 4096 + 200), deadline_seconds=5) == {}
    assert len(seen) == 2
