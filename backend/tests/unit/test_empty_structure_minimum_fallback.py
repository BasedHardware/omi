"""Recovery with no enriched structure completes on the deterministic minimum for kept conversations.

Replaces the dead letter for a kept, decoded, plain conversation whose enrichment
returned nothing. Every other case keeps the typed refusal. One process loads
process_conversation (file-isolated CI), so the module is loaded once and shared.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from utils.conversations import empty_structure_minimum as eligibility
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.recovery import RecoveryStructureUnavailableError

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)
STALE_FINISHED = NOW - timedelta(hours=3)


class _RecoveryProbeReached(Exception):
    """Raised by the record_decision probe: the guard let the recovery continue."""


@pytest.fixture(scope='module')
def pc():
    with _process_conversation_module_loaded() as module:
        yield module


@contextmanager
def _process_conversation_module_loaded():
    import sys

    from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
    from tests.unit.test_process_conversation_duplicate_capture import BACKEND_DIR, _STUBBED

    fakes: dict = {}
    for name in _STUBBED:
        module = AutoMockModule(name)
        if name == 'langchain_core' or name.startswith('langchain_core.'):
            module.__path__ = []
        fakes[name] = module
    fakes['database._client'].document_id_from_seed = lambda seed: seed
    # Its import-time Prometheus Gauge would register a second time on every fresh load.
    fakes['utils.conversations.demand_processing'] = AutoMockModule('utils.conversations.demand_processing')
    with stub_modules(fakes):
        pc = load_module_fresh(
            'utils.conversations.process_conversation',
            str(BACKEND_DIR / 'utils' / 'conversations' / 'process_conversation.py'),
        )
        try:
            yield pc
        finally:
            sys.modules.pop('utils.conversations.process_conversation', None)


def _empty_structure_conversation(**overrides):
    from models.conversation import Conversation
    from models.conversation_enums import ConversationSource, ConversationStatus
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    values = dict(
        id='recovery-conv',
        created_at=STALE_FINISHED,
        started_at=STALE_FINISHED,
        finished_at=NOW,
        structured=Structured(),
        transcript_segments=[
            TranscriptSegment(
                id='seg-1',
                text='a captured line followed by enough words to stay above the conservative recovery floor today',
                speaker='SPEAKER_00',
                speaker_id=0,
                is_user=True,
                start=0.0,
                end=1.0,
            )
        ],
        source=ConversationSource.omi,
        status=ConversationStatus.processing,
    )
    values.update(overrides)
    return Conversation(**values)


def _empty_structure_relevance(verdict='keep'):
    from types import SimpleNamespace

    return SimpleNamespace(
        discard=verdict == 'discard',
        verdict=verdict,
        as_record=lambda: {'trigger': 'server_recovery', 'verdict': verdict},
    )


def _run_empty_structure_recovery(pc, conversation, *, verdict='keep', captured=None):
    """Run SERVER_RECOVERY to the first call after the guard, with no structure from enrichment."""
    from models.structured import Structured

    def get_structured(*args, **kwargs):
        kwargs['relevance_observer'](_empty_structure_relevance(verdict))
        return Structured(), False

    def get_conversation_obj(uid, structured, conv, **kwargs):
        if captured is not None:
            captured['structured'] = structured
        return conv

    with (
        patch.object(eligibility, 'is_release_probe_uid', MagicMock(return_value=False)),
        patch.object(pc, 'should_skip_omi_paid_postprocessing', MagicMock(return_value=False)),
        patch.object(pc, '_enrich_meeting_context', MagicMock()),
        patch.object(pc, '_get_structured', side_effect=get_structured),
        patch.object(pc, '_get_conversation_obj', side_effect=get_conversation_obj),
        patch.object(pc, '_attach_client_projection', MagicMock()),
        patch.object(eligibility.notification_db, 'get_user_time_zone', MagicMock(return_value='UTC')),
        patch.object(pc, 'record_decision', side_effect=_RecoveryProbeReached()),
    ):
        return pc.process_conversation(
            'uid-recovery',
            'en',
            conversation,
            trigger=ProcessingTrigger.SERVER_RECOVERY,
        )


def test_empty_structure_keep_completes_on_deterministic_minimum(pc, capsys, monkeypatch):
    monkeypatch.delenv('LISTEN_FINALIZATION_EMPTY_STRUCTURE_MINIMUM_ENABLED', raising=False)
    captured: dict = {}
    with pytest.raises(_RecoveryProbeReached):
        _run_empty_structure_recovery(pc, _empty_structure_conversation(), captured=captured)

    structured = captured['structured']
    assert structured.title.strip()
    assert structured.title_provenance == 'server_minimum'
    assert structured.overview == ''
    assert structured.action_items == []
    events = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert [e for e in events if e.get('event') == 'selfheal_guard' and e.get('outcome') == 'refused'] == []
    assert [e for e in events if e.get('event') == 'selfheal_guard' and e.get('outcome') == 'minimum_fallback'] == [
        {
            'event': 'selfheal_guard',
            'outcome': 'minimum_fallback',
            'reason': 'empty_structured',
            'structure_reason': 'no_enriched_structure',
            'relevance_verdict': 'keep',
            'uid': 'uid-recovery',
            'conversation_id': 'recovery-conv',
        }
    ]


@pytest.mark.parametrize('value', ['false', '0', 'off', 'NO'])
def test_empty_structure_kill_switch_restores_the_typed_refusal(pc, capsys, monkeypatch, value):
    monkeypatch.setenv('LISTEN_FINALIZATION_EMPTY_STRUCTURE_MINIMUM_ENABLED', value)
    with pytest.raises(RecoveryStructureUnavailableError):
        _run_empty_structure_recovery(pc, _empty_structure_conversation())
    events = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert [e['outcome'] for e in events if e.get('event') == 'selfheal_guard'] == ['refused']


def test_empty_structure_discard_verdict_keeps_the_refusal(pc, monkeypatch):
    monkeypatch.delenv('LISTEN_FINALIZATION_EMPTY_STRUCTURE_MINIMUM_ENABLED', raising=False)
    with pytest.raises(RecoveryStructureUnavailableError):
        _run_empty_structure_recovery(pc, _empty_structure_conversation(), verdict='discard')


def _set_attribute(attribute, value):
    def mutate(conversation):
        setattr(conversation, attribute, value)

    return mutate


def _set_content_free_transcript(conversation):
    conversation.transcript_segments = [SimpleNamespace(text='testing the microphone one two three')]


def _set_stored_structure(conversation, **fields):
    from models.structured import Structured

    conversation.structured = Structured(**fields)


@pytest.mark.parametrize(
    'mutate,kwargs',
    [
        (lambda conversation: None, {'app_id': 'app-1'}),
        (lambda conversation: None, {'recovery_transcript_decoded': False}),
        (lambda conversation: None, {'recovery_minimum_fallback': True}),
        (lambda conversation: None, {'final_attempt': False}),
        (_set_content_free_transcript, {}),
        (lambda conversation: None, {'discarded': True}),
        (lambda conversation: None, {'decisions': []}),
        (_set_attribute('photos', [SimpleNamespace(description='described photo')]), {}),
        (lambda conversation: _set_stored_structure(conversation, title='Stored title'), {}),
        (lambda conversation: _set_stored_structure(conversation, title='', overview='Stored overview'), {}),
        (_set_attribute('transcript_segments', []), {}),
    ],
)
def test_empty_structure_minimum_eligibility_is_narrow(monkeypatch, mutate, kwargs):
    from models.structured import Structured

    monkeypatch.delenv('LISTEN_FINALIZATION_EMPTY_STRUCTURE_MINIMUM_ENABLED', raising=False)
    conversation = _empty_structure_conversation()
    mutate(conversation)
    structured = Structured()
    arguments = _eligibility_arguments(conversation, structured, **kwargs)
    with patch.object(eligibility, 'is_release_probe_uid', return_value=False):
        result, applied = eligibility.apply_empty_structure_minimum(**arguments)
    assert applied is False
    assert result is structured


def test_empty_structure_minimum_keeps_a_trusted_wake_word_mic_check(monkeypatch):
    from models.structured import Structured

    monkeypatch.delenv('LISTEN_FINALIZATION_EMPTY_STRUCTURE_MINIMUM_ENABLED', raising=False)
    conversation = _empty_structure_conversation()
    _set_content_free_transcript(conversation)
    with (
        patch.object(eligibility, 'find_wake_word_matches', return_value=[object()]),
        patch.object(eligibility, 'is_release_probe_uid', return_value=False),
        patch.object(eligibility.notification_db, 'get_user_time_zone', MagicMock(return_value='UTC')),
    ):
        _, applied = eligibility.apply_empty_structure_minimum(**_eligibility_arguments(conversation, Structured()))
    assert applied is True


def test_empty_structure_minimum_eligible_for_plain_kept_recovery(monkeypatch):
    from models.structured import Structured

    monkeypatch.delenv('LISTEN_FINALIZATION_EMPTY_STRUCTURE_MINIMUM_ENABLED', raising=False)
    conversation = _empty_structure_conversation()
    with patch.object(eligibility, 'is_release_probe_uid', return_value=False), patch.object(
        eligibility.notification_db, 'get_user_time_zone', MagicMock(return_value='UTC')
    ):
        result, applied = eligibility.apply_empty_structure_minimum(
            **_eligibility_arguments(conversation, Structured())
        )
        assert applied is True
        assert result.title_provenance == 'server_minimum'
        ignored, applied = eligibility.apply_empty_structure_minimum(
            **_eligibility_arguments(conversation, Structured(), recovery_minimum_fallback=True)
        )
        assert applied is False
    other_trigger = _eligibility_arguments(conversation, Structured())
    other_trigger['trigger'] = ProcessingTrigger.CAPTURE_END
    with patch.object(eligibility, 'is_release_probe_uid', return_value=False):
        assert eligibility.apply_empty_structure_minimum(**other_trigger)[1] is False


def _eligibility_arguments(conversation, structured, **overrides):
    arguments = dict(
        uid='uid-recovery',
        trigger=ProcessingTrigger.SERVER_RECOVERY,
        conversation=conversation,
        structured=structured,
        discarded=False,
        decisions=[_empty_structure_relevance('keep')],
        app_id=None,
        recovery_transcript_decoded=True,
        recovery_minimum_fallback=False,
    )
    arguments.update(overrides)
    return arguments
