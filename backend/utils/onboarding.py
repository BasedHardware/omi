import asyncio
import time
import uuid
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

    # Special speaker ID for Omi question segments (use 99 to avoid conflicts with real speakers)
    OMI_SPEAKER_ID = 99

    def __init__(self, uid: str, send_message: Callable, stream_transcript: Optional[Callable] = None):
        self.uid = uid
        self.send_message = send_message
        self.stream_transcript = stream_transcript  # Callback to inject segments into transcript stream
        self.questions = ONBOARDING_QUESTIONS.copy()
        self.current_question_index = 0
        self.answers: List[Dict] = []
        self.current_transcript = ''
        self.silence_timer: Optional[asyncio.Task] = None
        self.is_checking_answer = False
        self.completed = False
        self.start_time: Optional[float] = None  # Track when onboarding started
        self.last_segment_end: float = 0.0  # Track end time for question segment timing

    @property
    def current_question(self) -> Optional[Dict]:
        if self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    def _get_elapsed_time(self) -> float:
        """Get elapsed time since onboarding started."""
        if self.start_time is None:
            self.start_time = time.time()
        return time.time() - self.start_time

    def _create_question_segment(self) -> Optional[Dict]:
        """Create a transcript segment for the current question."""
        if not self.current_question:
            return None

        # Question segment starts after last segment ended, with small gap
        start_time = self.last_segment_end + 0.5 if self.last_segment_end > 0 else 0.0
        # Estimate end time based on question length (rough: 150 words per minute)
        words = len(self.current_question['question'].split())
        duration = max(1.0, words / 2.5)  # At least 1 second
        end_time = start_time + duration

        return {
            'id': str(uuid.uuid4()),
            'text': self.current_question['question'],
            'start': start_time,
            'end': end_time,
            'speaker': f'SPEAKER_{self.OMI_SPEAKER_ID}',  # Use consistent format with STT output
            'speaker_id': self.OMI_SPEAKER_ID,
            'is_user': False,
            'person_id': None,
        }

    def update_segment_timing(self, segments: List[dict]):
        """Update timing tracking based on received segments."""
        for segment in segments:
            end_time = segment.get('end', 0)
            if end_time > self.last_segment_end:
                self.last_segment_end = end_time

    def on_segments_received(self, segments: List[dict]):
        """Called when new transcript segments are received"""
        if self.completed or self.is_checking_answer:
            return

        # Update timing tracking
        self.update_segment_timing(segments)

        # Accumulate transcript for current question (ignore Omi segments)
        new_text = ' '.join(
            s.get('text', '') for s in segments
            if s.get('speaker_id') != self.OMI_SPEAKER_ID
        ).strip()
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
        """Send current question to client and inject as transcript segment"""
        if self.current_question:
            # Create and inject question segment into transcript stream
            question_segment = self._create_question_segment()
            if question_segment and self.stream_transcript:
                self.stream_transcript([question_segment])
                # Update last_segment_end to account for the question segment
                self.last_segment_end = question_segment['end']

            await self._send_event(
                'onboarding_question',
                {
                    'question': self.current_question['question'],
                    'question_index': self.current_question_index,
                    'total_questions': len(self.questions),
                    'question_segment_id': question_segment['id'] if question_segment else None,
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
