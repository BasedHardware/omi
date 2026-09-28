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
from utils.conversations.recovery import structured_is_rich

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)
STALE_FINISHED = NOW - timedelta(hours=3)


@pytest.fixture
def isolated_processing_module():
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


def test_recovery_rule_discard_skips_paid_structuring_but_keeps_transcript(monkeypatch, isolated_processing_module):
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
        structured, discarded = pc._get_structured(
            'uid-recovery', 'en', conversation, trigger=ProcessingTrigger.SERVER_RECOVERY
        )

    assert not discarded
    assert structured_is_rich(structured) is False
    assert conversation.transcript_segments[0].text == 'hmm'
    paid_notes.assert_not_called()
