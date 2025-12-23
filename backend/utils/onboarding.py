import asyncio
from typing import Callable, Dict, List, Optional

from utils.llm.clients import llm_mini

ONBOARDING_QUESTIONS = [
    {'question': "How old are you?", 'category': 'age'},
    {'question': "Where do you live?", 'category': 'location'},
    {'question': "What do you do for work?", 'category': 'work'},
    {'question': "What is your long-term goal?", 'category': 'long_term_goal'},
    {'question': "What are your goals this month?", 'category': 'monthly_goals'},
    {'question': "What do you have planned for today?", 'category': 'daily_plans'},
]


class OnboardingHandler:
    """Handles onboarding question flow via websocket"""

    def __init__(self, uid: str, send_message: Callable):
        self.uid = uid
        self.send_message = send_message
        self.questions = ONBOARDING_QUESTIONS.copy()
        self.current_question_index = 0
        self.answers: List[Dict] = []
        self.current_transcript = ''
        self.silence_timer: Optional[asyncio.Task] = None
        self.is_checking_answer = False
        self.completed = False

    @property
    def current_question(self) -> Optional[Dict]:
        if self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    def on_segments_received(self, segments: List[dict]):
        """Called when new transcript segments are received"""
        if self.completed or self.is_checking_answer:
            return

        # Accumulate transcript for current question
        new_text = ' '.join(s.get('text', '') for s in segments).strip()
        if new_text:
            if self.current_transcript:
                self.current_transcript += ' ' + new_text
            else:
                self.current_transcript = new_text

        # Reset silence timer
        if self.silence_timer:
            self.silence_timer.cancel()

        # Start new silence timer (2 seconds)
        self.silence_timer = asyncio.create_task(self._silence_check())

    async def _silence_check(self):
        """Check answer after 2 seconds of silence"""
        await asyncio.sleep(2.0)

        if self.completed or self.is_checking_answer:
            return

        if not self.current_transcript.strip():
            return

        await self._check_answer()

    async def skip_current_question(self):
        """Skip the current question and move to the next one"""
        if self.completed or self.is_checking_answer:
            return

        # Cancel any pending silence timer
        if self.silence_timer:
            self.silence_timer.cancel()
            self.silence_timer = None

        # Record that this question was skipped
        if self.current_question:
            self.answers.append(
                {
                    'question': self.current_question['question'],
                    'answer': self.current_transcript.strip() if self.current_transcript.strip() else '[skipped]',
                    'category': self.current_question['category'],
                    'skipped': True,
                }
            )

        # Send event to app
        await self._send_event(
            'question_skipped',
            {
                'question_index': self.current_question_index,
            },
        )

        # Move to next question
        self.current_question_index += 1
        self.current_transcript = ''

        if self.current_question_index >= len(self.questions):
            await self._complete_onboarding()
        else:
            await self.send_current_question()

    async def _check_answer(self):
        """Use AI to check if question was answered"""
        if self.is_checking_answer or not self.current_question:
            return

        self.is_checking_answer = True

        try:
            question = self.current_question['question']
            transcript = self.current_transcript.strip()

            # Check with AI if enough content
            word_count = len(transcript.split())
            answered = False

            if word_count >= 2:
                answered = await self._ai_check_answer(question, transcript)

            if answered:
                # Save answer
                self.answers.append(
                    {
                        'question': question,
                        'answer': transcript,
                        'category': self.current_question['category'],
                    }
                )

                # Send event to app
                await self._send_event(
                    'question_answered',
                    {
                        'question_index': self.current_question_index,
                        'answered': True,
                    },
                )

                # Move to next question
                self.current_question_index += 1
                self.current_transcript = ''

                if self.current_question_index >= len(self.questions):
                    await self._complete_onboarding()
                else:
                    await self.send_current_question()

        finally:
            self.is_checking_answer = False

    async def _ai_check_answer(self, question: str, transcript: str) -> bool:
        """Use AI to determine if answer is valid"""
        try:
            prompt = f"""Determine if this transcript answers the question. Be lenient - any attempt to answer counts.
Question: "{question}"
Transcript: "{transcript}"

Reply with only "yes" or "no"."""

            response = await asyncio.to_thread(llm_mini.invoke, prompt)
            return 'yes' in response.content.lower()
        except Exception as e:
            print(f"AI check error: {e}")
            # Fallback: 2+ words is an answer
            return len(transcript.split()) >= 2

    async def _send_event(self, event_type: str, data: dict):
        """Send message event to client"""
        event = {'type': event_type, **data}
        await self.send_message(event)

    async def send_current_question(self):
        """Send current question to client"""
        if self.current_question:
            await self._send_event(
                'onboarding_question',
                {
                    'question': self.current_question['question'],
                    'question_index': self.current_question_index,
                    'total_questions': len(self.questions),
                },
            )

    async def _complete_onboarding(self):
        """Signal completion when all questions answered.

        The conversation is already being created/updated by the normal
        transcription flow in transcribe.py. We just signal completion
        so the client can finalize the speech profile and trigger
        conversation processing.
        """
        self.completed = True

        await self._send_event(
            'onboarding_complete',
            {
                'answers_count': len(self.answers),
            },
        )

    def cleanup(self):
        """Cleanup resources"""
        if self.silence_timer:
            self.silence_timer.cancel()
