"""
Shared service for per-person context retrieval.

Assembles everything Omi knows about a specific person the user talks to: the
stored per-person profile (relationship / summary / tone), facts attributed to
them, and recent conversation snippets. Used by the agentic chat tool and (later)
the reply drafter so both share one implementation.
"""

import logging
from typing import Optional

import database.conversations as conversations_db
import database.memories as memories_db
import database.users as users_db
from database.entities import person_entity_id
from models.other import Person
from models.transcript_segment import TranscriptSegment

logger = logging.getLogger(__name__)


def resolve_person(uid: str, name_or_id: str) -> Optional[dict]:
    """Resolve a person by document id, then display name, then handle."""
    if not name_or_id:
        return None
    person = users_db.get_person(uid, name_or_id)
    if person:
        return person
    person = users_db.get_person_by_name(uid, name_or_id)
    if person:
        return person
    return users_db.get_person_by_handle(uid, name_or_id)


def get_person_context(uid: str, name_or_id: str, max_conversations: int = 5, max_memories: int = 20) -> str:
    person = resolve_person(uid, name_or_id)
    if not person:
        return f"I don't have anyone matching '{name_or_id}' in your people yet."

    person_id = person['id']
    name = person.get('name') or name_or_id
    lines = [f"# Context about {name}"]

    if person.get('relationship'):
        lines.append(f"Relationship: {person['relationship']}")
    if person.get('profile_summary'):
        lines.append(f"\n{person['profile_summary']}")
    if person.get('tone_notes'):
        lines.append(f"\nHow you talk with {name}: {person['tone_notes']}")

    # Facts attributed to this person.
    try:
        facts = memories_db.get_memories_by_subject_entity(uid, person_entity_id(person_id), limit=max_memories)
    except Exception as e:
        logger.warning(f"person_service: memories lookup failed for uid={uid}: {e}")
        facts = []
    fact_lines = [f.get('content') for f in facts if f.get('content')]
    if fact_lines:
        lines.append(f"\n## Known facts about {name}")
        lines.extend(f"- {c}" for c in fact_lines)

    # Recent conversations involving this person.
    try:
        convos = conversations_db.get_conversations_by_person_id(uid, person_id, limit=max_conversations)
    except Exception as e:
        logger.warning(f"person_service: conversations lookup failed for uid={uid}: {e}")
        convos = []
    if convos:
        people = [Person(**person)]
        lines.append(f"\n## Recent conversations with {name}")
        for c in convos:
            title = (c.get('structured') or {}).get('title') or 'Conversation'
            raw_segments = c.get('transcript_segments') or []
            segments = [TranscriptSegment(**s) for s in raw_segments][:12]
            snippet = TranscriptSegment.segments_as_string(segments, people=people)
            if snippet:
                lines.append(f"\n### {title}\n{snippet[:1200]}")

    if len(lines) == 1:
        return f"I don't have much context about {name} yet."
    return "\n".join(lines)
