from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from unittest.mock import patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from tests.unit.test_process_conversation_duplicate_capture import BACKEND_DIR, _STUBBED
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment

from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.recovery import structured_is_rich, verified_recovery_discard

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)
STALE_FINISHED = NOW - timedelta(hours=3)


@pytest.fixture(scope='module')
def isolated_processing_module():
    # One fresh load per module: re-importing the stubbed graph per test trips
    # jsonschema's rpds extension on the second load.
    fakes = {name: AutoMockModule(name) for name in _STUBBED}
    for name in fakes:
        if name == 'langchain_core' or name.startswith('langchain_core.'):
            fakes[name].__path__ = []
    fakes['database._client'].document_id_from_seed = lambda seed: seed
    with stub_modules(fakes):
        pc = load_module_fresh(
            'utils.conversations.process_conversation',
            str(BACKEND_DIR / 'utils' / 'conversations' / 'process_conversation.py'),
        )
        try:
            yield pc
        finally:
            sys.modules.pop('utils.conversations.process_conversation', None)


def test_recovery_rule_discard_records_explicit_discard_without_paid_structuring(
    monkeypatch, isolated_processing_module
):
    monkeypatch.setenv('LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED', 'true')
    pc = isolated_processing_module
    conversation = Conversation(
        id='recovery-conv',
        created_at=STALE_FINISHED,
        started_at=STALE_FINISHED,
        finished_at=NOW,
        structured=Structured(),
        transcript_segments=[
            TranscriptSegment(
                id='seg-1',
                text='hmm',
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
    with (
        patch.object(pc, 'conversation_transcripts_for_llm', return_value=('hmm', 'hmm', {})),
        patch.object(pc, 'has_structural_wake_word_marker', return_value=False),
        patch.object(pc, 'is_release_probe_uid', return_value=False),
        patch.object(pc, '_calendar_overlap_retains_conversation', return_value=False),
        patch.object(pc, 'get_conversation_notes') as paid_notes,
    ):
        decisions = []
        structured, discarded = pc._get_structured(
            'uid-recovery',
            'en',
            conversation,
            trigger=ProcessingTrigger.SERVER_RECOVERY,
            relevance_observer=decisions.append,
        )

    # Same verdict ordinary capture-end processing reaches, recorded as an
    # explicit server-recovery discard so the job terminates as accepted
    # instead of dead-lettering a visible untitled row.
    assert discarded
    assert structured_is_rich(structured) is False
    assert conversation.transcript_segments[0].text == 'hmm'
    paid_notes.assert_not_called()
    assert [(d.verdict, d.decided_by, d.reason, d.trigger) for d in decisions] == [
        ('discard', 'rule', 'filler_only', ProcessingTrigger.SERVER_RECOVERY)
    ]
    assert verified_recovery_discard(True, decisions[0].as_record())


def _empty_recovery_conversation() -> Conversation:
    return Conversation(
        id='recovery-empty',
        created_at=STALE_FINISHED,
        started_at=STALE_FINISHED,
        finished_at=STALE_FINISHED,
        structured=Structured(),
        transcript_segments=[],
        source=ConversationSource.omi,
        status=ConversationStatus.processing,
    )


def test_recovery_empty_transcript_is_explicit_discard(monkeypatch, isolated_processing_module):
    """The dominant stranded-row shape: audio uploaded, no transcript, no photos."""
    monkeypatch.setenv('LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED', 'true')
    pc = isolated_processing_module
    decisions = []
    with (
        patch.object(pc, 'conversation_transcripts_for_llm', return_value=('', '', {})),
        patch.object(pc, 'has_structural_wake_word_marker', return_value=False),
        patch.object(pc, 'is_release_probe_uid', return_value=False),
        patch.object(pc, '_calendar_overlap_retains_conversation', return_value=False),
        patch.object(pc, 'get_conversation_notes') as paid_notes,
    ):
        structured, discarded = pc._get_structured(
            'uid-recovery',
            'en',
            _empty_recovery_conversation(),
            trigger=ProcessingTrigger.SERVER_RECOVERY,
            relevance_observer=decisions.append,
        )

    assert discarded
    assert structured_is_rich(structured) is False
    paid_notes.assert_not_called()
    assert [(d.verdict, d.reason) for d in decisions] == [('discard', 'empty_transcript')]
    assert verified_recovery_discard(True, decisions[0].as_record())


def test_recovery_calendar_overlap_does_not_take_the_rule_discard(monkeypatch, isolated_processing_module):
    """A scrap inside a booked meeting is evidence, never an explicit recovery discard."""
    monkeypatch.setenv('LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED', 'true')
    pc = isolated_processing_module
    decisions = []
    with (
        patch.object(pc, 'conversation_transcripts_for_llm', return_value=('', '', {})),
        patch.object(pc, 'has_structural_wake_word_marker', return_value=False),
        patch.object(pc, 'is_release_probe_uid', return_value=False),
        patch.object(pc, '_calendar_overlap_retains_conversation', return_value=True),
        patch.object(pc, 'get_conversation_notes', return_value=Structured()),
        patch.object(pc, 'get_reprocess_transcript_structure', return_value=Structured()),
        patch.object(pc, 'get_transcript_structure', return_value=Structured(), create=True),
    ):
        _structured, discarded = pc._get_structured(
            'uid-recovery',
            'en',
            _empty_recovery_conversation(),
            trigger=ProcessingTrigger.SERVER_RECOVERY,
            relevance_observer=decisions.append,
        )

    assert not discarded
    assert all(d.trigger is not ProcessingTrigger.SERVER_RECOVERY or not d.discard for d in decisions)
