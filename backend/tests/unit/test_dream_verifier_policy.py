"""Pluggable verifier chains stay fail-closed and default to the two strong calls."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.agent_tools import Verification, VerificationBatch
from config.jev_decisions import JEV_MAX_STATE_CHARS, JEV_MODEL
from utils.agent_capabilities import verifiers
from utils.dream_verify import INSTRUCTIONS, disposition, evidence, verify
from utils.llm.shaped_agent import Turn

SPEECH = 'alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november'


def staged(kind, operation, records, item_id='proposal-1'):
    operation_dump = {
        'kind': kind,
        'target': getattr(operation, 'target', ''),
        'other': getattr(operation, 'other', ''),
        'before': getattr(operation, 'before', ''),
        'after': getattr(operation, 'after', ''),
        'reason': 'Synthetic',
        'evidence': list(getattr(operation, 'evidence', []) or []),
    }

    def payload():
        return {'id': item_id, 'kind': kind, 'operation': dict(operation_dump)}

    return SimpleNamespace(id=item_id, kind=kind, operation=operation, records=records, refs=(), payload=payload)


def spelling(before, after, text, records=None, target='conversations/one#seg'):
    records = records or {
        'conversations/one': {'transcript_segments': [{'id': 'seg', 'text': text}]},
    }
    operation = SimpleNamespace(kind='spelling', target=target, other='', before=before, after=after, evidence=[target])
    return staged('spelling', operation, records)


async def agreeing_turn(mount, messages):
    return Turn(
        tokens=4,
        value=VerificationBatch(decisions=[Verification(id='proposal-1', agree=True, reason='Synthetic support')]),
    )


def test_unset_policy_keeps_two_strong_verifiers(monkeypatch):
    monkeypatch.delenv('DREAM_VERIFIER_POLICY', raising=False)
    calls = []

    async def turn(mount, messages):
        calls.append(mount.instructions)
        return await agreeing_turn(mount, messages)

    votes, count = asyncio.run(
        verify([spelling('Omni', 'Omi', 'Ask Omni about the launch.')], turn, tokens=8000, deadline_seconds=5)
    )
    assert count == 2 and disposition(votes['proposal-1']) == 'agree'
    assert calls[0] != calls[1]


def test_explicit_strong_policy_matches_the_default_chain(monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', json.dumps([{'strategy': 'strong_model'}]))
    calls = []

    async def turn(mount, messages):
        calls.append(1)
        return await agreeing_turn(mount, messages)

    votes, count = asyncio.run(
        verify([spelling('Omni', 'Omi', 'Ask Omni about the launch.')], turn, tokens=8000, deadline_seconds=5)
    )
    assert count == 2 and len(calls) == 2 and disposition(votes['proposal-1']) == 'agree'


def test_deterministic_reject_skips_the_model_and_does_not_apply(monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'spelling': [{'strategy': 'deterministic'}, {'strategy': 'strong_model'}]}),
    )

    async def turn(mount, messages):
        raise AssertionError('model must not run after a deterministic reject')

    item = spelling('Omni', 'Omi', 'Hello there from the synthetic room.')
    votes, count = asyncio.run(verify([item], turn, tokens=8000, deadline_seconds=5))
    assert count == 0 and disposition(votes['proposal-1']) == 'disagree'


def test_trusted_spelling_does_not_authorize_until_marked_sufficient(monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'spelling': [{'strategy': 'deterministic'}, {'strategy': 'strong_model'}]}),
    )
    calls = []

    async def turn(mount, messages):
        calls.append(1)
        return await agreeing_turn(mount, messages)

    records = {
        'people/ada': {'name': 'Omi', 'speech_samples': ['synthetic/sample']},
        'conversations/one': {'transcript_segments': [{'id': 'seg', 'text': 'Ask Omni about the launch.'}]},
    }
    votes, count = asyncio.run(
        verify([spelling('Omni', 'Omi', 'Ask Omni about the launch.', records)], turn, tokens=8000, deadline_seconds=5)
    )
    assert count == 2 and len(calls) == 2 and disposition(votes['proposal-1']) == 'agree'


def test_deterministic_sufficient_agreement_skips_the_model(monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps(
            {
                'spelling': {
                    'chain': [{'strategy': 'deterministic'}],
                    'deterministic_sufficient': True,
                }
            }
        ),
    )

    async def turn(mount, messages):
        raise AssertionError('sufficient deterministic agreement does not need a model')

    records = {
        'people/ada': {'name': 'Omi', 'speech_samples': ['synthetic/sample']},
        'conversations/one': {'transcript_segments': [{'id': 'seg', 'text': 'Ask Omni about the launch.'}]},
    }
    votes, count = asyncio.run(
        verify([spelling('Omni', 'Omi', 'Ask Omni about the launch.', records)], turn, tokens=8000, deadline_seconds=5)
    )
    assert count == 0 and disposition(votes['proposal-1']) == 'agree'


def test_attested_spelling_is_agreement_only_when_sufficient(monkeypatch):
    verdict = verifiers.run_deterministic(
        spelling(
            'Omni',
            'Omi',
            'Meet Omni tomorrow at the dock.',
            {
                'conversations/one': {
                    'transcript_segments': [{'id': 'seg', 'text': 'Meet Omni tomorrow at the dock.'}]
                },
                'conversations/two': {
                    'transcript_segments': [{'id': 'other', 'text': 'Meet Omi tomorrow at the dock.'}]
                },
            },
        ),
        verifiers.VerifierStep('deterministic', ('spelling',)),
    )
    assert verdict.status == 'agree' and verdict.reason == 'spelling_attested'
    assert verifiers.authorizes(verifiers.VerifierStep('deterministic'), verifiers.VerifierPolicy(), verdict) is False


def test_duplicate_capture_reject_and_pass(monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'merge_conversations': [{'strategy': 'deterministic'}]}),
    )

    def capture(hour, speech=SPEECH):
        return {
            'status': 'completed',
            'started_at': datetime(2026, 10, 14, hour, 0, tzinfo=timezone.utc),
            'finished_at': datetime(2026, 10, 14, hour, 30, tzinfo=timezone.utc),
            'transcript_segments': [{'text': speech}],
        }

    operation = SimpleNamespace(
        kind='merge_conversations',
        target='conversations/left',
        other='conversations/right',
        before='',
        after='',
        evidence=['conversations/left'],
    )

    async def turn(mount, messages):
        raise AssertionError('duplicate reject must not call a model')

    apart = staged(
        'merge_conversations',
        operation,
        {'conversations/left': capture(12), 'conversations/right': capture(18)},
    )
    votes, count = asyncio.run(verify([apart], turn, tokens=8000, deadline_seconds=5))
    assert count == 0 and disposition(votes['proposal-1']) == 'disagree'

    together = staged(
        'merge_conversations',
        operation,
        {
            'conversations/left': capture(12),
            'conversations/right': {
                **capture(12),
                'started_at': datetime(2026, 10, 14, 12, 10, tzinfo=timezone.utc),
                'finished_at': datetime(2026, 10, 14, 12, 40, tzinfo=timezone.utc),
            },
        },
    )
    verdict = verifiers.run_deterministic(together, verifiers.VerifierStep('deterministic', ('duplicate_capture',)))
    assert verdict.status == 'agree' and verdict.reason == 'duplicate_overlap_ok'


def test_language_tag_shape_rejects_or_defers(monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'set_language': [{'strategy': 'deterministic'}, {'strategy': 'strong_model'}]}),
    )
    operation = SimpleNamespace(
        kind='set_language',
        target='conversations/one',
        other='',
        before='',
        after='not-a-language',
        evidence=['conversations/one'],
    )

    async def turn(mount, messages):
        raise AssertionError('invalid language tag must not call a model')

    votes, count = asyncio.run(
        verify(
            [staged('set_language', operation, {'conversations/one': {'language': ''}})],
            turn,
            tokens=8000,
            deadline_seconds=5,
        )
    )
    assert count == 0 and disposition(votes['proposal-1']) == 'disagree'

    calls = []

    async def later(mount, messages):
        calls.append(1)
        return await agreeing_turn(mount, messages)

    operation.after = 'vi'
    votes, count = asyncio.run(
        verify(
            [staged('set_language', operation, {'conversations/one': {'language': ''}})],
            later,
            tokens=8000,
            deadline_seconds=5,
        )
    )
    assert count == 2 and len(calls) == 2 and disposition(votes['proposal-1']) == 'agree'


def test_invalid_policy_does_not_auto_apply(monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', '{')

    async def turn(mount, messages):
        raise AssertionError('invalid policy must not call a model')

    votes, count = asyncio.run(
        verify([spelling('Omni', 'Omi', 'Ask Omni about the launch.')], turn, tokens=8000, deadline_seconds=5)
    )
    assert count == 0 and disposition(votes['proposal-1']) == 'unverified'


def test_unconfigured_cheap_and_disabled_jev_continue_to_strong(monkeypatch):
    monkeypatch.delenv('DREAM_VERIFIER_JEV', raising=False)
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps(
            {
                'spelling': [
                    {'strategy': 'deterministic'},
                    {'strategy': 'cheap_model'},
                    {'strategy': 'jev'},
                    {'strategy': 'strong_model'},
                ]
            }
        ),
    )
    calls = []

    async def turn(mount, messages):
        calls.append(1)
        return await agreeing_turn(mount, messages)

    def boom(*args, **kwargs):
        raise AssertionError('disabled jev must not call the client')

    monkeypatch.setattr(verifiers, 'ask_jev', boom)
    votes, count = asyncio.run(
        verify([spelling('Omni', 'Omi', 'Ask Omni about the launch.')], turn, tokens=8000, deadline_seconds=5)
    )
    assert count == 2 and len(calls) == 2 and disposition(votes['proposal-1']) == 'agree'


def test_configured_cheap_disagreement_stops_the_chain(monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps(
            {'spelling': [{'strategy': 'cheap_model', 'lane': 'synthetic-cheap'}, {'strategy': 'strong_model'}]}
        ),
    )

    async def cheap(mount, messages):
        return Turn(
            tokens=2,
            value=VerificationBatch(decisions=[Verification(id='proposal-1', agree=False, reason='Synthetic reject')]),
        )

    async def strong(mount, messages):
        raise AssertionError('cheap disagreement stops the chain')

    votes, count = asyncio.run(
        verify(
            [spelling('Omni', 'Omi', 'Ask Omni about the launch.')],
            strong,
            tokens=8000,
            deadline_seconds=5,
            cheap_turn=cheap,
        )
    )
    assert count == 1 and disposition(votes['proposal-1']) == 'disagree'


def test_metrics_use_reason_codes_not_content(monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', json.dumps({'spelling': [{'strategy': 'deterministic'}]}))
    before = verifiers.VERDICTS.labels(
        kind='spelling', strategy='deterministic', verdict='disagree', reason='spelling_before_missing'
    )._value.get()

    async def turn(mount, messages):
        raise AssertionError('reject does not call a model')

    asyncio.run(
        verify([spelling('Omni', 'Omi', 'Hello there from the synthetic room.')], turn, tokens=8000, deadline_seconds=5)
    )
    after = verifiers.VERDICTS.labels(
        kind='spelling', strategy='deterministic', verdict='disagree', reason='spelling_before_missing'
    )._value.get()
    assert after == before + 1
    for metric in verifiers.VERDICTS.collect():
        for sample in metric.samples:
            blob = ' '.join(sample.labels.values())
            assert 'Omni' not in blob and 'synthetic room' not in blob


@pytest.mark.parametrize(
    'votes, expected',
    [([True, True], 'agree'), ([False, False], 'disagree'), ([True, False], 'split'), ([None, None], 'unverified')],
)
def test_disposition_contract_is_unchanged(votes, expected):
    assert disposition(votes) == expected


def _cited(text):
    target = 'conversations/one#seg'
    item = spelling('Omni', 'Omi', text, target=target)
    item.refs = (target,)
    return item


def test_jev_state_is_the_full_immutable_evidence():
    speech = 'Meet Omni at the synthetic launch review.'
    item = _cited(speech)
    state = verifiers._jev_state(item, evidence)
    encoded = json.dumps(evidence(item), ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    assert state == verifiers._JEV_FRAMING + '\n\n' + encoded
    assert speech in state
    assert 'Synthetic' not in state


def test_oversized_jev_evidence_is_uncertain_and_not_truncated(monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_JEV', '1')
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', json.dumps([{'strategy': 'jev'}]))
    speech = 'Omni ' + ('synthetic ' * 4000)
    item = _cited(speech)
    state = verifiers._jev_state(item, evidence)
    assert len(state) > JEV_MAX_STATE_CHARS and speech in state

    def boom(*args, **kwargs):
        raise AssertionError('oversized evidence must not be sent or truncated')

    monkeypatch.setattr(verifiers, 'ask_jev', boom)
    votes, count = asyncio.run(verify([item], agreeing_turn, tokens=8000, deadline_seconds=5))
    assert count == 0 and disposition(votes['proposal-1']) == 'unverified'


class _Answers:
    def __init__(self, score, usage, served=JEV_MODEL):
        self.served_model = served
        self.usage = usage
        self.score = score

    def noul(self, name):
        assert name == 'safe'
        return self.score


def test_jev_thresholds_default_to_the_benchmark_and_keep_the_receipt(monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_JEV', '1')
    monkeypatch.delenv('DREAM_VERIFIER_JEV_AGREE', raising=False)
    monkeypatch.delenv('DREAM_VERIFIER_JEV_DISAGREE', raising=False)
    item = _cited('Ask Omni about the synthetic launch.')
    seen = {}

    def ask(state, questions, **kwargs):
        seen['state'] = state
        seen['questions'] = questions
        seen['kwargs'] = kwargs
        return _Answers(
            0.5, {'prompt_tokens': 11, 'completion_tokens': 2, 'prompt_tokens_details': {'cached_tokens': 0}}
        )

    monkeypatch.setattr(verifiers, 'ask_jev', ask)
    verdict = asyncio.run(verifiers.run_jev(item, evidence, INSTRUCTIONS))
    assert verdict.status == 'uncertain' and verdict.reason == 'jev_uncertain'
    assert verdict.served_model == JEV_MODEL
    assert verdict.usage_receipt == (('prompt_tokens', 11), ('completion_tokens', 2), ('cached_tokens', 0))
    assert verdict.tokens == 13 and verdict.calls == 1
    assert seen['kwargs']['max_attempts'] == 1
    assert seen['questions']['safe']['instructions'] == INSTRUCTIONS + verifiers._JEV_ASK
    assert 'Ask Omni about the synthetic launch.' in seen['state']

    monkeypatch.setattr(verifiers, 'ask_jev', lambda *args, **kwargs: _Answers(0.995, {'prompt_tokens': 4}))
    agreed = asyncio.run(verifiers.run_jev(item, evidence, INSTRUCTIONS))
    assert agreed.status == 'agree' and agreed.usage_receipt == (('prompt_tokens', 4),)

    monkeypatch.setattr(verifiers, 'ask_jev', lambda *args, **kwargs: _Answers(0.005, {}))
    rejected = asyncio.run(verifiers.run_jev(item, evidence, INSTRUCTIONS))
    assert rejected.status == 'disagree' and rejected.usage_receipt == () and rejected.tokens == 0

    monkeypatch.setattr(
        verifiers, 'ask_jev', lambda *args, **kwargs: _Answers(0.995, {'prompt_tokens': 3}, served='other-model')
    )
    mismatched = asyncio.run(verifiers.run_jev(item, evidence, INSTRUCTIONS))
    assert mismatched.status == 'uncertain' and mismatched.reason == 'jev_model_mismatch'
    assert mismatched.served_model == 'other-model' and mismatched.usage_receipt == (('prompt_tokens', 3),)

    monkeypatch.setenv('DREAM_VERIFIER_JEV_AGREE', '0.4')
    monkeypatch.setenv('DREAM_VERIFIER_JEV_DISAGREE', '0.1')
    monkeypatch.setattr(verifiers, 'ask_jev', lambda *args, **kwargs: _Answers(0.5, {'total_tokens': 9}))
    overridden = asyncio.run(verifiers.run_jev(item, evidence, INSTRUCTIONS))
    assert (
        overridden.status == 'agree' and overridden.usage_receipt == (('total_tokens', 9),) and overridden.tokens == 9
    )

    monkeypatch.setenv('DREAM_VERIFIER_JEV_AGREE', 'low')
    monkeypatch.setattr(verifiers, 'ask_jev', boom_if_called)
    invalid = asyncio.run(verifiers.run_jev(item, evidence, INSTRUCTIONS))
    assert invalid.status == 'uncertain' and invalid.reason == 'jev_threshold_invalid' and invalid.calls == 0


def boom_if_called(*args, **kwargs):
    raise AssertionError('invalid thresholds must not call Jev')
