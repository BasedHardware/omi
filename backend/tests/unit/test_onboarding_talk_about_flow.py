"""The app shows the speech-profile questions together as "Talk About" topics,
so one stretch of speech may answer several of them. The handler must keep the
accumulated transcript across questions and advance through every question it
answers, instead of discarding the transcript after the first answer."""

import pytest

from utils.onboarding import ONBOARDING_QUESTIONS, OnboardingHandler


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _handler(events, ai_answers):
    async def send_message(event):
        events.append(event)

    handler = OnboardingHandler('user-1', send_message)

    async def fake_ai_check(question, transcript):
        return ai_answers.pop(0)

    handler._ai_check_answer = fake_ai_check  # type: ignore[method-assign]
    return handler


@pytest.mark.anyio
async def test_one_transcript_can_answer_every_topic():
    events = []
    handler = _handler(events, [True, True, True])
    transcript = 'I live in Austin, I work as an engineer, and my long-term goal is to start a company.'
    handler.current_transcript = transcript

    await handler._check_answer()

    assert handler.completed is True
    assert [a['question'] for a in handler.answers] == [q['question'] for q in ONBOARDING_QUESTIONS]
    assert all(a['answer'] == transcript for a in handler.answers)
    assert [e['type'] for e in events] == [
        'question_answered',
        'onboarding_question',
        'question_answered',
        'onboarding_question',
        'question_answered',
        'onboarding_complete',
    ]


@pytest.mark.anyio
async def test_transcript_is_kept_for_the_next_topic_when_it_stops_answering():
    events = []
    handler = _handler(events, [True, False])
    handler.current_transcript = 'I live in Austin.'

    await handler._check_answer()

    assert handler.completed is False
    assert handler.current_question_index == 1
    assert handler.current_transcript == 'I live in Austin.'
    assert [e['type'] for e in events] == ['question_answered', 'onboarding_question']
