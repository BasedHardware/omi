"""
Per-person profile generation.

Builds a concise profile of a person the user talks to — who they are, the user's
history with them, and (importantly) HOW THE USER writes to that specific person —
from their conversations and attributed facts. Stored on the Person doc and surfaced
by get_person_context_tool and the reply drafter.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import conversations as conversations_db
from database import memories as memories_db
from database import users as users_db
from database.entities import person_entity_id
from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.llm.clients import get_llm
from utils.llm.local_shim import local_cli_llm_text

logger = logging.getLogger(__name__)

PROFILE_STALE_DAYS = 7
MIN_SEGMENTS_FOR_PROFILE = 6


def _needs_refresh(person: dict) -> bool:
    if not person.get('profile_summary'):
        return True
    updated = person.get('profile_updated_at')
    if not updated:
        return True
    if isinstance(updated, str):
        try:
            updated = datetime.fromisoformat(updated)
        except ValueError:
            return True
    try:
        return (datetime.now(timezone.utc) - updated) > timedelta(days=PROFILE_STALE_DAYS)
    except TypeError:
        return True


def _extract_json(text: str) -> Optional[dict]:
    t = (text or '').strip()
    if t.startswith('```'):
        newline = t.find('\n')
        if newline != -1:
            t = t[newline + 1 :]
        if t.endswith('```'):
            t = t[:-3]
    start = t.find('{')
    end = t.rfind('}')
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(t[start : end + 1])
    except Exception:
        return None


def generate_person_profile(uid: str, person_id: str, force: bool = False) -> bool:
    """Regenerate and store a person's profile. Returns True if updated.

    Self-gates on staleness so it's safe to call opportunistically after each
    ingest. Never fabricates — if there isn't enough material, it does nothing.
    """
    person = users_db.get_person(uid, person_id)
    if not person:
        return False
    if not force and not _needs_refresh(person):
        return False

    name = person.get('name') or 'this person'
    convos = conversations_db.get_conversations_by_person_id(uid, person_id, limit=15)
    facts = memories_db.get_memories_by_subject_entity(uid, person_entity_id(person_id), limit=30)

    people = [Person(**person)]
    transcript_blocks = []
    total_segments = 0
    for convo in convos:
        segments = [TranscriptSegment(**s) for s in (convo.get('transcript_segments') or [])]
        total_segments += len(segments)
        block = TranscriptSegment.segments_as_string(segments, people=people)
        if block:
            transcript_blocks.append(block)

    if total_segments < MIN_SEGMENTS_FOR_PROFILE and not facts:
        return False

    transcript_text = "\n\n---\n\n".join(transcript_blocks)[:8000] or "(none)"
    facts_text = "\n".join(f"- {f.get('content')}" for f in facts if f.get('content'))[:2000] or "(none)"

    prompt = (
        f"You are building a concise profile of {name} for the user, based on their messages "
        f"together. Use ONLY the material below — never invent details.\n\n"
        f"CONVERSATIONS (the user is \"User\"; the other person is \"{name}\"):\n{transcript_text}\n\n"
        f"KNOWN FACTS ABOUT {name}:\n{facts_text}\n\n"
        "Respond ONLY with valid JSON (no markdown, no code fences):\n"
        "{\n"
        f"  \"relationship\": \"one short phrase for who {name} is to the user "
        "(e.g. 'brother', 'coworker', 'close friend'), or empty string if unclear\",\n"
        f"  \"profile_summary\": \"2-4 sentences: who {name} is, what's going on with them, "
        "and the user's history with them\",\n"
        f"  \"tone_notes\": \"1-2 sentences on HOW THE USER writes to {name} specifically "
        "(formality, emoji, in-jokes, typical length)\"\n"
        "}"
    )

    try:
        content = local_cli_llm_text(prompt)
        if content is None:
            response = get_llm('memories').invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
        parsed = _extract_json(content)
    except Exception as e:
        logger.warning(f"generate_person_profile LLM failed uid={uid} person={person_id}: {e}")
        return False

    if not parsed:
        return False

    users_db.update_person_profile(
        uid,
        person_id,
        {
            'relationship': (parsed.get('relationship') or '').strip() or None,
            'profile_summary': (parsed.get('profile_summary') or '').strip() or None,
            'tone_notes': (parsed.get('tone_notes') or '').strip() or None,
            'profile_updated_at': datetime.now(timezone.utc),
            'message_count': total_segments,
        },
    )
    return True
