import asyncio
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable
import uuid

import database.conversations as conversations_db
import database.memories as memories_db
from models.conversation import ConversationStatus, ConversationSource
from models.memories import MemoryDB, MemoryCategory
from utils.llm.clients import llm_mini


ONBOARDING_QUESTIONS = [
    {
        'question': "What should I call you?",
        'category': 'name'
    },
    {
        'question': "Where do you live?",
        'category': 'location'
    },
    {
        'question': "What do you do for work?",
        'category': 'work'
    },
    {
        'question': "What kind of work or projects are you passionate about?",
        'category': 'work_passion'
    },
    {
        'question': "What are some hobbies or interests you enjoy outside of work?",
        'category': 'hobbies'
    },
    {
        'question': "What's something you'd love to have more time for?",
        'category': 'time_wishes'
    },
    {
        'question': "What's a challenge you're currently working through?",
        'category': 'current_challenges'
    },
    {
        'question': "What is your long-term goal?",
        'category': 'long_term_goal'
    },
    {
        'question': "How do you hope I can help you in your daily life?",
        'category': 'omi_expectations'
    },
    {
        'question': "What's on your mind for today or this week?",
        'category': 'immediate_focus'
    },
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

        # Start new silence timer (4 seconds)
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
            self.answers.append({
                'question': self.current_question['question'],
                'answer': self.current_transcript.strip() if self.current_transcript.strip() else '[skipped]',
                'category': self.current_question['category'],
                'skipped': True,
            })

        # Send event to app
        await self._send_event('question_skipped', {
            'question_index': self.current_question_index,
        })

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
                self.answers.append({
                    'question': question,
                    'answer': transcript,
                    'category': self.current_question['category'],
                })

                # Send event to app
                await self._send_event('question_answered', {
                    'question_index': self.current_question_index,
                    'answered': True,
                })

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
            await self._send_event('onboarding_question', {
                'question': self.current_question['question'],
                'question_index': self.current_question_index,
                'total_questions': len(self.questions),
            })

    async def _complete_onboarding(self):
        """Create conversation and memories when all questions answered"""
        self.completed = True

        try:
            conversation_id = await self._create_conversation()
            await self._create_memories(conversation_id)

            await self._send_event('onboarding_complete', {
                'conversation_id': conversation_id,
                'memories_created': len(self.answers),
            })
        except Exception as e:
            print(f"Error completing onboarding: {e}")
            await self._send_event('onboarding_complete', {'error': str(e)})

    async def _create_conversation(self) -> str:
        """Create onboarding conversation in database"""
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Build transcript segments
        transcript_segments = []
        current_time = 0.0

        for qa in self.answers:
            transcript_segments.append({
                'text': qa['question'],
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'is_user': False,
                'start': current_time,
                'end': current_time + 2.0,
            })
            current_time += 2.0

            transcript_segments.append({
                'text': qa['answer'],
                'speaker': 'SPEAKER_01',
                'speaker_id': 1,
                'is_user': True,
                'start': current_time,
                'end': current_time + 5.0,
            })
            current_time += 5.0

        overview = await self._generate_overview()

        conversation_data = {
            'id': conversation_id,
            'created_at': now,
            'started_at': now,
            'finished_at': now,
            'source': ConversationSource.onboarding.value,
            'language': 'en',
            'structured': {
                'title': 'Getting to Know You',
                'overview': overview,
                'emoji': '👋',
                'category': 'personal',
                'action_items': [],
                'events': [],
            },
            'transcript_segments': transcript_segments,
            'plugins_results': [],
            'apps_results': [],
            'geolocation': None,
            'photos': [],
            'status': ConversationStatus.completed.value,
            'discarded': False,
        }

        conversations_db.upsert_conversation(self.uid, conversation_data)
        return conversation_id

    async def _generate_overview(self) -> str:
        """Generate overview using LLM"""
        try:
            summary_parts = [f"Q: {qa['question']}\nA: {qa['answer']}" for qa in self.answers]
            prompt = f"""Based on these onboarding Q&A, write a brief 1-2 sentence overview:

{chr(10).join(summary_parts)}

Return ONLY the overview text."""

            response = await asyncio.to_thread(llm_mini.invoke, prompt)
            return response.content.strip()
        except:
            return "Onboarding conversation where the user shared personal information and goals."

    async def _create_memories(self, conversation_id: str):
        """Create memories from answers"""
        now = datetime.now(timezone.utc)

        for qa in self.answers:
            # Skip creating memories for skipped questions with no real answer
            if qa.get('skipped') and qa.get('answer') == '[skipped]':
                continue

            memory_data = MemoryDB(
                id=str(uuid.uuid4()),
                uid=self.uid,
                content=f"{qa['question']} - {qa['answer']}",
                category=MemoryCategory.interesting,
                created_at=now,
                updated_at=now,
                conversation_id=conversation_id,
                reviewed=False,
                manually_added=False,
                visibility='private',
            )
            memory_data.scoring = MemoryDB.calculate_score(memory_data)

            try:
                memories_db.create_memory(self.uid, memory_data.dict())
            except Exception as e:
                print(f"Error creating memory: {e}")

    def cleanup(self):
        """Cleanup resources"""
        if self.silence_timer:
            self.silence_timer.cancel()
