import os
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
import tiktoken
import uvicorn

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

encoding = tiktoken.encoding_for_model('gpt-4')
chat = ChatOpenAI(model='gpt-4o', temperature=0)

MAX_PROMPT_TOKENS = 30000
MIN_TRANSCRIPT_CHARS = 50
MIN_ACADEMIC_SCORE = 2

# --- Data Models ---
# Mirrors the Omi webhook payload structure.
# See: plugins/example/models.py and docs/doc/developer/apps/Integrations.mdx


class TranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = 'SPEAKER_00'
    speaker_id: Optional[int] = None
    is_user: bool
    person_id: Optional[str] = None
    start: float
    end: float

    def __init__(self, **data):
        super().__init__(**data)
        try:
            self.speaker_id = int(self.speaker.split('_')[1]) if self.speaker else 0
        except (IndexError, ValueError):
            self.speaker_id = 0


class Structured(BaseModel):
    title: str
    overview: str
    emoji: str = ''
    category: str = 'other'


class Conversation(BaseModel):
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = []
    structured: Structured
    discarded: bool

    def get_transcript(self, include_timestamps: bool = False) -> str:
        transcript = ''
        for segment in self.transcript_segments:
            segment_text = segment.text.strip()
            if include_timestamps:
                start_dur = timedelta(seconds=int(segment.start))
                end_dur = timedelta(seconds=int(segment.end))
                timestamp_str = f'[{str(start_dur).split(".")[0]} - {str(end_dur).split(".")[0]}] '
            else:
                timestamp_str = ''
            speaker_label = 'User' if segment.is_user else f'Speaker {segment.speaker_id}'
            transcript += f'{timestamp_str}{speaker_label}: {segment_text}\n\n'
        return transcript.strip()


class EndpointResponse(BaseModel):
    message: str = Field(description='A short message to be sent as notification to the user, if needed.', default='')


# --- Structured Output Models ---


class KeyConcept(BaseModel):
    term: str = Field(description='The concept or term')
    definition: str = Field(description='Brief definition or explanation')


class LectureNotes(BaseModel):
    is_academic: bool = Field(
        description='Whether this conversation contains academic or educational content worth taking notes on'
    )
    subject: str = Field(description='The academic subject or course topic detected', default='')
    key_concepts: List[KeyConcept] = Field(
        description='Key concepts and their definitions extracted from the content', default=[]
    )
    main_topics: List[str] = Field(description='Main topics or themes covered in the conversation', default=[])
    summary: str = Field(description='A concise summary of the lecture or academic discussion', default='')
    questions: List[str] = Field(
        description='Important questions raised during the conversation or worth exploring further', default=[]
    )
    action_items: List[str] = Field(
        description='Homework, assignments, readings, or other action items mentioned', default=[]
    )
    study_tips: List[str] = Field(
        description='Study suggestions generated based on the content and topics discussed', default=[]
    )


# --- Academic Content Detection ---
# Heuristic pre-filter to avoid unnecessary LLM calls on casual conversations.
# Uses keyword density, speaker asymmetry, duration, and content volume.

ACADEMIC_KEYWORDS = {
    'lecture',
    'professor',
    'class',
    'exam',
    'homework',
    'assignment',
    'chapter',
    'theorem',
    'proof',
    'equation',
    'hypothesis',
    'textbook',
    'syllabus',
    'semester',
    'midterm',
    'final',
    'quiz',
    'grade',
    'curriculum',
    'course',
    'research',
    'paper',
    'thesis',
    'dissertation',
    'lab',
    'experiment',
    'algorithm',
    'function',
    'variable',
    'matrix',
    'integral',
    'derivative',
    'biology',
    'chemistry',
    'physics',
    'calculus',
    'statistics',
    'economics',
    'philosophy',
    'literature',
    'history',
    'psychology',
    'sociology',
    'definition',
    'concept',
    'theory',
    'analysis',
    'methodology',
    'slides',
    'review',
    'tutorial',
    'section',
    'campus',
    'prerequisite',
    'credit',
    'enrollment',
    'degree',
    'major',
    'hypothesis',
    'coefficient',
    'regression',
    'probability',
    'inference',
    'compiler',
    'syntax',
    'runtime',
    'abstraction',
    'recursion',
    'genome',
    'protein',
    'molecule',
    'catalyst',
    'entropy',
}


def num_tokens_from_string(text: str) -> int:
    return len(encoding.encode(text))


def compute_academic_score(conversation: Conversation) -> int:
    """
    Score how likely a conversation is academic/educational content.
    Combines keyword density, speaker asymmetry (lectures have one dominant speaker),
    conversation duration, and content volume. Higher score = more likely academic.
    """
    transcript_text = conversation.get_transcript().lower()
    words = transcript_text.split()
    total_words = len(words)

    if total_words < 30:
        return 0

    # Keyword density: proportion of recognized academic terms
    academic_hits = sum(1 for w in words if w.strip('.,!?:;()[]"\'') in ACADEMIC_KEYWORDS)
    keyword_density = academic_hits / total_words

    # Speaker asymmetry: lectures typically have one speaker with >70% of talk time
    speaker_durations = {}
    for seg in conversation.transcript_segments:
        speaker = seg.speaker or 'unknown'
        duration = max(seg.end - seg.start, 0)
        speaker_durations[speaker] = speaker_durations.get(speaker, 0) + duration

    total_duration = sum(speaker_durations.values())
    max_speaker_ratio = max(speaker_durations.values()) / total_duration if total_duration > 0 else 0

    # Conversation duration in minutes
    duration_minutes = 0
    if conversation.started_at and conversation.finished_at:
        duration_minutes = (conversation.finished_at - conversation.started_at).total_seconds() / 60

    # Structured category from Omi's own classification
    category = (conversation.structured.category or '').lower()
    educational_categories = {'education', 'science', 'technology', 'academic', 'learning'}

    score = 0

    # Keyword density scoring
    if keyword_density > 0.03:
        score += 3
    elif keyword_density > 0.015:
        score += 2
    elif keyword_density > 0.005:
        score += 1

    # Speaker asymmetry scoring (one dominant speaker suggests lecture format)
    if max_speaker_ratio > 0.75:
        score += 2
    elif max_speaker_ratio > 0.6:
        score += 1

    # Omi's own categorization
    if category in educational_categories:
        score += 2

    # Duration scoring (lectures are typically 15+ minutes)
    if duration_minutes > 30:
        score += 2
    elif duration_minutes > 10:
        score += 1

    # Content volume (substantial transcripts are more likely academic)
    if total_words > 1000:
        score += 1

    return score


# --- Note Formatting ---


def format_notes(notes: LectureNotes) -> str:
    """Format structured LectureNotes into a readable notification message."""
    if not notes.is_academic or not notes.subject:
        return ''

    sections = []
    sections.append(f'LECTURE NOTES | {notes.subject}')
    sections.append('')

    if notes.summary:
        sections.append('Summary')
        sections.append(notes.summary)
        sections.append('')

    if notes.key_concepts:
        sections.append('Key Concepts')
        for kc in notes.key_concepts:
            sections.append(f'  - {kc.term}: {kc.definition}')
        sections.append('')

    if notes.main_topics:
        sections.append('Topics Covered')
        for topic in notes.main_topics:
            sections.append(f'  - {topic}')
        sections.append('')

    if notes.questions:
        sections.append('Questions to Explore')
        for q in notes.questions:
            sections.append(f'  - {q}')
        sections.append('')

    if notes.action_items:
        sections.append('Action Items')
        for item in notes.action_items:
            sections.append(f'  - {item}')
        sections.append('')

    if notes.study_tips:
        sections.append('Study Tips')
        for tip in notes.study_tips:
            sections.append(f'  - {tip}')

    return '\n'.join(sections).strip()


# --- FastAPI Application ---

app = FastAPI(title='Omi Lecture Notes Plugin', version='1.0.0')


@app.get('/')
async def root():
    return {
        'app': 'Omi Lecture Notes Plugin',
        'version': '1.0.0',
        'endpoints': {
            'lecture_notes': 'POST /lecture-notes',
            'health': 'GET /health',
        },
    }


@app.get('/health')
async def health():
    return {'status': 'healthy'}


@app.post('/lecture-notes', response_model=EndpointResponse)
async def lecture_notes_endpoint(conversation: Conversation):
    """
    Memory creation trigger endpoint.
    Receives a completed conversation from Omi, analyzes it for academic content,
    and returns structured lecture notes if the content is educational.
    """
    if conversation.discarded:
        return EndpointResponse(message='')

    transcript = conversation.get_transcript(include_timestamps=True)
    if not transcript or len(transcript.strip()) < MIN_TRANSCRIPT_CHARS:
        return EndpointResponse(message='')

    # Stage 1: Heuristic pre-filter to skip clearly non-academic conversations
    academic_score = compute_academic_score(conversation)
    logger.info(f'Academic score: {academic_score} for conversation "{conversation.structured.title}"')

    if academic_score < MIN_ACADEMIC_SCORE:
        return EndpointResponse(message='')

    # Stage 2: Build prompt and check token budget
    prompt = (
        'You are an expert academic note-taker. Analyze the following conversation transcript '
        'and extract structured lecture notes.\n\n'
        'First, determine if this conversation contains meaningful academic or educational content '
        '(lectures, study sessions, tutoring, academic discussions, class discussions, office hours, '
        'research meetings, etc.). If it does NOT contain academic content, set is_academic to false '
        'and leave all other fields empty.\n\n'
        'If it IS academic content, extract comprehensive notes:\n'
        '- Identify the subject or course area\n'
        '- Extract key concepts with clear, concise definitions\n'
        '- List the main topics covered in order of discussion\n'
        '- Write a focused summary (2-3 sentences)\n'
        '- Note important questions raised or worth exploring\n'
        '- Capture action items (homework, readings, assignments, deadlines)\n'
        '- Generate 2-3 actionable study tips specific to this material\n\n'
        f'Conversation Title: {conversation.structured.title}\n'
        f'Conversation Overview: {conversation.structured.overview}\n\n'
        f'Transcript:\n{transcript}'
    )

    token_count = num_tokens_from_string(prompt)
    if token_count > MAX_PROMPT_TOKENS:
        # Truncate transcript to fit within budget, keeping the beginning (intro/context)
        overhead_tokens = num_tokens_from_string(prompt.replace(transcript, ''))
        available_tokens = MAX_PROMPT_TOKENS - overhead_tokens - 500  # buffer
        transcript_tokens = encoding.encode(transcript)
        truncated = encoding.decode(transcript_tokens[:available_tokens])
        prompt = prompt.replace(transcript, truncated + '\n\n[Transcript truncated due to length]')
        logger.info(f'Truncated transcript from {token_count} to ~{MAX_PROMPT_TOKENS} tokens')

    # Stage 3: LLM structured extraction
    try:
        chat_with_parser = chat.with_structured_output(LectureNotes)
        notes: LectureNotes = await chat_with_parser.ainvoke(prompt)
    except Exception as e:
        logger.error(f'LLM extraction failed: {e}')
        return EndpointResponse(message='')

    # Stage 4: Format and return
    message = format_notes(notes)
    if len(message) < 10:
        return EndpointResponse(message='')

    logger.info(f'Generated lecture notes for "{conversation.structured.title}" ({notes.subject})')
    return EndpointResponse(message=message)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    uvicorn.run('main:app', host='0.0.0.0', port=port, reload=True)
