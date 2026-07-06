"""Phase 1 orchestrator: absorb per-person facts from a messaging conversation.

After a texting-source conversation (iMessage/Telegram/WhatsApp) is ingested and
post-processed, this extracts HIGH-RECALL durable facts ABOUT each person present in the
thread and writes them keyed to that person's `subject_entity_id` with
`SubjectAttribution.third_party` — a per-person "constantly updated brain".

This closes a real gap: `infer_subject_from_segments` returns `unknown` for any 1:1 thread
(user + one person both present), so today's user-keyed extraction never person-keys
messaging facts.

Fully guarded — it NEVER raises into the caller (the connector's background enrichment).
"""

import logging
from typing import Dict, List, Optional

from database import memories as memories_db
from database import users as users_db
from database.entities import person_entity_id
from models.conversation_enums import ConversationSource
from models.memories import SubjectAttribution
from utils.llm.person_messaging import extract_person_messaging_memories
from utils.llms.memory import get_prompt_memories
from utils.memory.subject_memory_writer import write_subject_memories

logger = logging.getLogger(__name__)

# Text-messaging sources this enrichment applies to (mirrors reply_draft._TEXTING_SOURCES).
_TEXTING_SOURCES = frozenset(
    {
        ConversationSource.imessage.value,
        ConversationSource.telegram.value,
        ConversationSource.whatsapp.value,
    }
)

# Bound how many of the person's existing facts we feed the extractor as dedup context.
_EXISTING_FACTS_LIMIT = 100


def _source_value(conversation) -> Optional[str]:
    source = getattr(conversation, 'source', None)
    return source.value if hasattr(source, 'value') else source


def _person_ids_for(conversation) -> List[str]:
    person_ids = list(getattr(conversation, 'person_ids', None) or [])
    if person_ids:
        return person_ids
    segments = getattr(conversation, 'transcript_segments', None) or []
    return sorted({s.person_id for s in segments if getattr(s, 'person_id', None)})


def _existing_facts_str(uid: str, subject_entity_id: str) -> str:
    try:
        existing = memories_db.get_memories_by_subject_entity(uid, subject_entity_id, limit=_EXISTING_FACTS_LIMIT)
    except Exception as e:
        logger.warning(f'person_messaging: existing facts lookup failed uid={uid} subject={subject_entity_id}: {e}')
        return ''
    lines = []
    for fact in existing or []:
        content = fact.get('content') if isinstance(fact, dict) else getattr(fact, 'content', None)
        if content:
            lines.append(f'- {content}')
    return '\n'.join(lines)


def _transcript_artifact_ref(conversation) -> dict:
    segments = getattr(conversation, 'transcript_segments', None) or []
    return {
        'kind': 'transcript_segments',
        'conversation_id': getattr(conversation, 'id', None),
        'segment_ids': [segment.id for segment in segments if getattr(segment, 'id', None)],
        'start': min((segment.start for segment in segments), default=None),
        'end': max((segment.end for segment in segments), default=None),
    }


def enrich_persons_from_conversation(uid: str, conversation, language: Optional[str] = None) -> Dict[str, int]:
    """Extract + persist per-person durable facts for a texting-source conversation.

    Returns {person_id: memories_written}. Never raises."""
    results: Dict[str, int] = {}
    try:
        if _source_value(conversation) not in _TEXTING_SOURCES:
            return results

        segments = getattr(conversation, 'transcript_segments', None) or []
        if not segments:
            return results

        person_ids = _person_ids_for(conversation)
        if not person_ids:
            return results

        # The user's name is needed only to render the transcript readably; person-specific
        # dedup context is fetched per person below.
        user_name, _ = get_prompt_memories(uid)
        artifact_ref = _transcript_artifact_ref(conversation)
        source_id = getattr(conversation, 'id', None)

        for person_id in person_ids:
            try:
                person = users_db.get_person(uid, person_id)
                if not person:
                    continue
                person_name = person.get('name') or 'Contact'
                subject_entity_id = person_entity_id(person_id)
                memories_str = _existing_facts_str(uid, subject_entity_id)

                memories = extract_person_messaging_memories(
                    uid,
                    person_name,
                    segments,
                    user_name=user_name,
                    memories_str=memories_str,
                    language=language,
                )
                if not memories:
                    results[person_id] = 0
                    continue

                written = write_subject_memories(
                    uid,
                    memories,
                    subject_entity_id=subject_entity_id,
                    subject_attribution=SubjectAttribution.third_party,
                    source_id=source_id,
                    artifact_ref=artifact_ref,
                    language=language,
                )
                results[person_id] = written
            except Exception as e:
                logger.warning(
                    f'person_messaging: enrichment failed for person={person_id} uid={uid} '
                    f'conv={getattr(conversation, "id", "?")}: {e}'
                )
    except Exception as e:
        logger.error(f'person_messaging: enrichment failed uid={uid} conv={getattr(conversation, "id", "?")}: {e}')
    return results
