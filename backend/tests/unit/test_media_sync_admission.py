"""Real sync orchestration: a filtered success settles as silence, without retry/ingest."""

import threading

import pytest

from models.transcript_segment import TranscriptSegment
from tests.unit.test_sync_capture_pipeline import pipeline
from tests.unit.test_sync_cross_job_assignment import conversations
from utils.conversations.relevance_content import FLAG
from utils.stt.transcript_admission import admit_segments


@pytest.mark.parametrize('mode', ['shadow', 'serve', 'off'])
def test_sync_hallucination_settlement_does_not_retry_or_create_empty_card(pipeline, monkeypatch, mode):
    module, store = pipeline
    monkeypatch.setenv(FLAG, mode)
    monkeypatch.delenv(FLAG + '_SERVE_PERCENT', raising=False)
    monkeypatch.delenv(FLAG + '_SERVE_UID_SHA256S', raising=False)
    # The fixture isolates provider/storage leaves; admission is the real authority.
    module.admit_segments = admit_segments
    module.postprocess_words = lambda *_: [
        TranscriptSegment(text='Caption Credit for Synthetic Person', start=0, end=3, is_user=False)
    ]
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    result = module.process_segment(
        '1700000000.wav', 'synthetic-account', response, threading.Lock(), errors, deferred_outcome=outcome
    )
    assert module.prerecorded.call_count == 1
    assert not errors
    if mode == 'serve':
        assert result is False and not conversations(store)
        assert outcome['outcome'].value == 'expected_silence'
        assert not outcome['retryable']
    else:
        assert result is True and len(conversations(store)) == 1
        assert outcome['outcome'].value == 'success'
