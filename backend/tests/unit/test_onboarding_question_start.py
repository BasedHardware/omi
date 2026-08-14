from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.listen.receiver import ListenReceiver
from utils.onboarding import ONBOARDING_QUESTIONS, OnboardingHandler


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_start_sends_question_zero_once_after_client_request():
    events = []
    transcript_batches = []

    async def send_message(event):
        events.append(event)

    handler = OnboardingHandler('user-1', send_message, transcript_batches.append)

    await handler.start()
    await handler.start()

    assert events == [
        {
            'type': 'onboarding_question',
            'question': ONBOARDING_QUESTIONS[0]['question'],
            'question_index': 0,
            'total_questions': len(ONBOARDING_QUESTIONS),
            'question_segment_id': events[0]['question_segment_id'],
        }
    ]
    assert len(transcript_batches) == 1
    assert transcript_batches[0][0]['text'] == ONBOARDING_QUESTIONS[0]['question']


@pytest.mark.anyio
async def test_receiver_routes_explicit_onboarding_start_to_handler():
    handler = SimpleNamespace(start=AsyncMock(), completed=False)
    receiver = object.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(onboarding_handler=handler, use_custom_stt=False)

    await receiver._handle_text('{"type":"start_onboarding"}')

    handler.start.assert_awaited_once_with()


@pytest.mark.anyio
async def test_receiver_records_valid_finalization_reason_for_rotation():
    receiver = object.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(
        onboarding_handler=None,
        use_custom_stt=False,
        state=SimpleNamespace(finalization_reason=None),
    )

    await receiver._handle_text('{"type":"finalization_reason","reason":"max_duration_rotation"}')

    assert receiver.host.state.finalization_reason == 'max_duration_rotation'


@pytest.mark.anyio
async def test_receiver_ignores_unknown_finalization_reason():
    receiver = object.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(
        onboarding_handler=None,
        use_custom_stt=False,
        state=SimpleNamespace(finalization_reason=None),
    )

    await receiver._handle_text('{"type":"finalization_reason","reason":"not-a-reason"}')

    assert receiver.host.state.finalization_reason is None
