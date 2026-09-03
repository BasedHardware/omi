"""Fail-open contract for wake-word adjudication and capture-policy ordering.

An absent or empty adjudicator verdict must not demote an extractor
``explicit_command``. ``create_direct`` was deleted by INV-TASK-2; an admitted
explicit command proposes as ``pending_candidate``.
"""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

os.environ.setdefault('TYPESENSE_API_KEY', 'test-key-not-real')

from utils.llm import wake_word_adjudication
from utils.llm.wake_word_adjudication import (
    WakeWordAdjudication,
    WakeWordInvocationVerdict,
    adjudicate_wake_word_invocations,
)
from utils.task_intelligence import conversation_capture
from utils.task_intelligence import conversation_capture_policy
from utils.task_intelligence.capture_policy import run_capture_policy


def _action(
    description,
    *,
    capture_kind='explicit_command',
    capture_owner='user',
    concrete_deliverable=True,
    source_segment_ids=None,
):
    return SimpleNamespace(
        description=description,
        capture_kind=capture_kind,
        capture_owner=capture_owner,
        capture_confidence=0.95,
        ownership_confidence=1,
        candidate_action=None,
        target_task_id=None,
        concrete_deliverable=concrete_deliverable,
        source_segment_ids=source_segment_ids or ['wake-segment'],
        due_at=None,
    )


def _empty_gate():
    return conversation_capture_policy.WakeWordCaptureGate(
        matched_segment_ids=frozenset({'wake-segment'}),
        adjudication=WakeWordAdjudication(),
    )


def _wake_conversation():
    return SimpleNamespace(
        id='conversation-1',
        transcript_segments=[
            SimpleNamespace(
                id='wake-segment',
                text='Hey Omi, remind me to send the budget.',
                start=0,
                end=2,
                is_user=True,
                person_id=None,
                speaker_id=0,
            )
        ],
        structured=SimpleNamespace(
            action_items=[
                _action('Send the budget', source_segment_ids=['wake-segment']),
            ]
        ),
    )


def test_empty_adjudication_leaves_extractor_explicit_command_intact():
    signals = conversation_capture_policy.capture_signals_for_action_item(
        _action('Send the budget'),
        _empty_gate(),
    )

    assert signals.explicit_command is True
    assert signals.direct_request is False


def test_adjudicator_exception_leaves_extractor_explicit_command_intact(monkeypatch):
    def boom(_feature):
        raise TimeoutError('provider blip')

    monkeypatch.setattr(wake_word_adjudication, 'get_llm', boom)
    monkeypatch.setattr(wake_word_adjudication, 'record_fallback', lambda **_kwargs: None)

    adjudication = adjudicate_wake_word_invocations(
        marked_transcript='[segment:wake-segment 0.000-2.000] User: Hey Omi, send the budget.',
        matched_segment_ids={'wake-segment'},
        action_items=[_action('Send the budget')],
        speaker_labels=[],
        transcript_segments=[{'id': 'wake-segment', 'text': 'Hey Omi, send the budget.'}],
    )
    gate = conversation_capture_policy.WakeWordCaptureGate(
        matched_segment_ids=frozenset({'wake-segment'}),
        adjudication=adjudication,
    )
    signals = conversation_capture_policy.capture_signals_for_action_item(
        _action('Send the budget'),
        gate,
    )

    assert adjudication.invocations == []
    assert signals.explicit_command is True
    assert signals.direct_request is False


@pytest.mark.parametrize('verdict', ['question', 'quoted_or_meta', 'not_addressed_to_omi', 'abandoned', 'unclear'])
def test_explicit_adverse_verdict_still_demotes_explicit_command(verdict):
    gate = conversation_capture_policy.WakeWordCaptureGate(
        matched_segment_ids=frozenset({'wake-segment'}),
        adjudication=WakeWordAdjudication(
            invocations=[
                WakeWordInvocationVerdict(
                    segment_ids=['wake-segment'],
                    verdict=verdict,
                    evidence_quote='Hey Omi',
                )
            ]
        ),
    )
    signals = conversation_capture_policy.capture_signals_for_action_item(_action('Send the budget'), gate)

    assert signals.explicit_command is False
    assert signals.direct_request is True


def _stub_transcript_renderers(monkeypatch):
    monkeypatch.setattr(conversation_capture, 'conversation_transcript_for_action_items', lambda *_a, **_k: 'marked')
    monkeypatch.setattr(conversation_capture, 'conversation_action_item_speaker_labels', lambda *_a, **_k: [])


def test_kill_switch_off_does_not_call_adjudicator_and_keeps_explicit_command(monkeypatch):
    monkeypatch.setenv('WAKE_WORD_ADJUDICATION_ENABLED', 'false')
    _stub_transcript_renderers(monkeypatch)
    calls = []

    gate = conversation_capture.prepare_wake_word_capture_gate(
        'user-1',
        _wake_conversation(),
        adjudicator=lambda **kwargs: calls.append(kwargs) or WakeWordAdjudication(),
    )
    signals = conversation_capture_policy.capture_signals_for_action_item(
        _action('Send the budget'),
        gate,
    )

    assert gate is None
    assert calls == []
    assert signals.explicit_command is True
    assert signals.direct_request is False


@pytest.mark.parametrize('enabled', [None, 'true', 'on', '1'])
def test_kill_switch_on_still_calls_adjudicator(monkeypatch, enabled):
    if enabled is None:
        monkeypatch.delenv('WAKE_WORD_ADJUDICATION_ENABLED', raising=False)
    else:
        monkeypatch.setenv('WAKE_WORD_ADJUDICATION_ENABLED', enabled)
    _stub_transcript_renderers(monkeypatch)
    calls = []

    gate = conversation_capture.prepare_wake_word_capture_gate(
        'user-1',
        _wake_conversation(),
        adjudicator=lambda **kwargs: calls.append(kwargs) or WakeWordAdjudication(),
    )

    assert gate is not None
    assert len(calls) == 1


def test_explicit_command_wins_over_public_broadcast():
    result = run_capture_policy(
        {
            'explicit_command': True,
            'public_broadcast': True,
            'direct_mention': False,
            'owner': 'user',
            'concrete_deliverable': True,
            'capture_confidence': 0.95,
            'ownership_confidence': 1.0,
        }
    )

    # INV-TASK-2 deleted create_direct; an admitted explicit command proposes.
    assert result.outcome == 'pending_candidate'
    assert result.interruption == 'none'


def test_public_broadcast_without_explicit_command_still_ignored():
    result = run_capture_policy(
        {
            'public_broadcast': True,
            'direct_mention': False,
            'owner': 'user',
            'concrete_deliverable': True,
            'capture_confidence': 0.95,
            'ownership_confidence': 1.0,
        }
    )

    assert result.outcome == 'ignore'


def test_kill_switch_is_declared_on_both_summary_pipeline_services():
    composed = yaml.safe_load((Path(__file__).resolve().parents[2] / 'deploy/runtime_env.yaml').read_text())
    for env_name, environment in composed['environments'].items():
        listen = environment['gke']['backend-listen']['env']['WAKE_WORD_ADJUDICATION_ENABLED']['value']
        backend = environment['cloud_run']['services']['backend']['env']['WAKE_WORD_ADJUDICATION_ENABLED']['value']
        assert listen == backend == 'true', env_name
