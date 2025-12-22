from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
import json
from datetime import datetime, timezone

import database.conversations as conversations_db
import database.memories as memories_db
from models.conversation import ConversationStatus
from models.transcript_segment import TranscriptSegment
from models.memories import MemoryDB, MemoryCategory

from utils.other import endpoints as auth
from utils.llm.clients import llm_mini

router = APIRouter()


class CheckAnswerRequest(BaseModel):
    question: str
    transcript: str


class CheckAnswerResponse(BaseModel):
    answered: bool
    extracted_answer: Optional[str] = None
    confidence: float = 0.0


class QuestionAnswer(BaseModel):
    question: str
    answer: str
    category: str


class CreateOnboardingConversationRequest(BaseModel):
    questions_answers: List[QuestionAnswer]


class CreateOnboardingConversationResponse(BaseModel):
    conversation: Optional[dict] = None
    memories_created: int = 0


@router.post("/v1/onboarding/check-answer", response_model=CheckAnswerResponse, tags=['onboarding'])
async def check_question_answered(
    request: CheckAnswerRequest,
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    Check if a question has been answered based on the transcript using AI.
    """
    if not request.transcript or len(request.transcript.strip()) < 3:
        return CheckAnswerResponse(answered=False, confidence=0.0)

    prompt = f"""You are analyzing a conversation transcript to determine if a question has been answered.

Question: "{request.question}"

User's response transcript: "{request.transcript}"

Analyze if the user has provided a meaningful answer to the question. The answer doesn't need to be perfect, 
but should show an attempt to respond to the question asked.

Respond ONLY with valid JSON (no markdown, no explanation):
{{"answered": true, "extracted_answer": "The key part of the answer extracted from the transcript", "confidence": 0.9}}

Or if not answered:
{{"answered": false, "extracted_answer": null, "confidence": 0.0}}

Only return "answered": true if the transcript contains a relevant response to the question.
Consider that the transcript may have some speech recognition errors, so be lenient with exact wording.
"""

    try:
        response = llm_mini.invoke(prompt)
        response_text = response.content.strip()
        
        # Try to parse JSON from the response
        try:
            result = json.loads(response_text)
            return CheckAnswerResponse(
                answered=result.get('answered', False),
                extracted_answer=result.get('extracted_answer'),
                confidence=result.get('confidence', 0.0)
            )
        except json.JSONDecodeError:
            pass
    except Exception as e:
        print(f"Error checking answer: {e}")
    
    # Fallback: simple heuristic - if transcript has more than 5 words, consider it answered
    words = request.transcript.strip().split()
    if len(words) >= 5:
        return CheckAnswerResponse(
            answered=True,
            extracted_answer=request.transcript.strip(),
            confidence=0.6
        )
    
    return CheckAnswerResponse(answered=False, confidence=0.0)


@router.post("/v1/onboarding/conversation", response_model=CreateOnboardingConversationResponse, tags=['onboarding'])
async def create_onboarding_conversation(
    request: CreateOnboardingConversationRequest,
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    Create an onboarding conversation and memories from the user's answers to onboarding questions.
    """
    if not request.questions_answers:
        raise HTTPException(status_code=400, detail="No questions/answers provided")

    # Build transcript segments from Q&A
    transcript_segments = []
    current_time = 0.0
    
    for qa in request.questions_answers:
        # Add question as a segment (from "Omi")
        transcript_segments.append({
            'text': qa.question,
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
            'start': current_time,
            'end': current_time + 2.0,
        })
        current_time += 2.0
        
        # Add answer as a segment (from user)
        transcript_segments.append({
            'text': qa.answer,
            'speaker': 'SPEAKER_01', 
            'speaker_id': 1,
            'is_user': True,
            'start': current_time,
            'end': current_time + 5.0,
        })
        current_time += 5.0

    # Create structured summary from answers
    summary_parts = []
    for qa in request.questions_answers:
        summary_parts.append(f"Q: {qa.question}\nA: {qa.answer}")
    
    overview = "Onboarding conversation where the user shared information about themselves including their age, location, work, and goals."
    
    # Generate a better overview using LLM
    try:
        overview_prompt = f"""Based on these onboarding questions and answers, write a brief 1-2 sentence overview:

{chr(10).join(summary_parts)}

Write a friendly, personalized overview that captures the key information shared. Return ONLY the overview text, nothing else."""
        
        response = llm_mini.invoke(overview_prompt)
        if response and response.content:
            overview = response.content.strip()
    except Exception as e:
        print(f"Error generating overview: {e}")

    # Create the conversation
    conversation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    conversation_data = {
        'id': conversation_id,
        'created_at': now,
        'started_at': now,
        'finished_at': now,
        'source': 'onboarding',
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
        'deleted': False,
    }

    # Save conversation to database
    conversations_db.upsert_conversation(uid, conversation_data)

    # Create memories from the answers
    memories_created = 0

    for qa in request.questions_answers:
        memory_content = f"{qa.question} - {qa.answer}"
        
        memory_data = MemoryDB(
            id=str(uuid.uuid4()),
            uid=uid,
            content=memory_content,
            category=MemoryCategory.interesting,
            created_at=now,
            updated_at=now,
            conversation_id=conversation_id,
            reviewed=False,
            manually_added=False,
            visibility='private',
        )
        # Calculate and set the scoring field
        memory_data.scoring = MemoryDB.calculate_score(memory_data)
        
        try:
            memories_db.create_memory(uid, memory_data.dict())
            memories_created += 1
        except Exception as e:
            print(f"Error creating memory: {e}")

    return CreateOnboardingConversationResponse(
        conversation=conversation_data,
        memories_created=memories_created
    )

