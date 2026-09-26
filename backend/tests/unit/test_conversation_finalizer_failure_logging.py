"""A dead-lettered finalization emits a bounded, privacy-safe reason.

The handler in ``utils/conversations/finalizer.py`` deliberately keeps provider and validation
messages out of the log because they can quote the transcript. Stable reason
codes distinguish operational classes without turning arbitrary exception
types or messages into labels.
"""

import logging

import pytest

from models.conversation_enums import ConversationStatus
from utils.conversations import finalizer
from utils.conversations.finalizer import ConversationFinalizationError


class _Conversation:
    """The minimum the finalizer touches before the failing step."""

    def __init__(self):
        self.id = "conversation-1"
        self.status = ConversationStatus.processing
        self.source = "omi"
        self.discarded = False
        self.structured = None
        self.geolocation = None


TRANSCRIPT_EXCERPT = "he said the quiet part out loud"


@pytest.fixture
def finalizer_that_fails_on_geolocation(monkeypatch):
    """Let the finalizer reach its try block, then fail inside it with a telltale message."""

    async def fake_run_blocking(_executor, function, *args, **kwargs):
        if function is finalizer.conversations_db.get_conversation:
            return {"id": "conversation-1"}
        if function is finalizer.get_cached_user_geolocation:
            raise LookupError(TRANSCRIPT_EXCERPT)
        raise AssertionError(f"unexpected blocking call: {function!r}")

    monkeypatch.setattr(finalizer, "run_blocking", fake_run_blocking)
    monkeypatch.setattr(finalizer, "deserialize_conversation", lambda _data: _Conversation())


@pytest.mark.asyncio
async def test_dead_letter_log_names_the_bounded_reason(finalizer_that_fails_on_geolocation, caplog, monkeypatch):
    recorded = []
    monkeypatch.setattr(finalizer, 'record_finalization_failure', recorded.append)
    with caplog.at_level(logging.WARNING, logger=finalizer.logger.name):
        with pytest.raises(ConversationFinalizationError) as raised:
            await finalizer.finalize_persisted_conversation(
                "user-1",
                "conversation-1",
                finalization_job_id="job-1",
                dispatch_generation=1,
                lease_epoch=1,
            )

    assert str(raised.value) == "processing_failed"
    failures = [record for record in caplog.records if "failure=processing_failed" in record.getMessage()]
    assert len(failures) == 1
    assert "reason=processing" in failures[0].getMessage()
    # Per-attempt failure is retryable in-flight work: WARNING, not ERROR.
    # Terminality is decided and escalated by the pusher-side handler.
    assert failures[0].levelno == logging.WARNING
    assert recorded == [finalizer.classify_finalization_failure(LookupError())]


@pytest.mark.asyncio
async def test_dead_letter_log_still_withholds_the_exception_message(finalizer_that_fails_on_geolocation, caplog):
    """The class name is safe to log; the message can quote the transcript and must not appear."""
    with caplog.at_level(logging.WARNING, logger=finalizer.logger.name):
        with pytest.raises(ConversationFinalizationError):
            await finalizer.finalize_persisted_conversation(
                "user-1",
                "conversation-1",
                finalization_job_id="job-1",
                dispatch_generation=1,
                lease_epoch=1,
            )

    assert TRANSCRIPT_EXCERPT not in "\n".join(record.getMessage() for record in caplog.records)
    assert 'user-1' not in "\n".join(record.getMessage() for record in caplog.records)
    assert 'conversation-1' not in "\n".join(record.getMessage() for record in caplog.records)
