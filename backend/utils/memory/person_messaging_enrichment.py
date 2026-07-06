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
import os
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

# Only enrich true 1:1 threads by default. A group window would otherwise fire one
# full-transcript extraction PER participant (an M-person, N-window backfill = N*M LLM
# calls, largely redundant), so we cap the participant count. Groups still get the
# existing whole-conversation (subject=unknown) extraction from process_conversation.
_MAX_PERSONS_PER_CONVERSATION = int(os.getenv('PERSON_MESSAGING_MAX_PERSONS', '1'))

# Kill-switch: set PERSON_MESSAGING_ENRICHMENT_ENABLED=false to disable per-person
# messaging extraction independently of the rest of the ingest pipeline (cost control).
_ENRICHMENT_ENABLED = os.getenv('PERSON_MESSAGING_ENRICHMENT_ENABLED', 'true').strip().lower() not in (
    '0',
    'false',
    'no',
)


def _source_value(conversation) -> Optional[str]:
    source = getattr(conversation, 'source', None)
    return source.value if hasattr(source, 'value') else source


def _person_ids_for(conversation) -> List[str]:
    # Dedupe (preserving order) so a duplicated id in conversation.person_ids can't
    # inflate the participant count and wrongly trip the 1:1 cost cap.
    person_ids = list(dict.fromkeys(pid for pid in (getattr(conversation, 'person_ids', None) or []) if pid))
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


def _last_contact_at(conversation):
    """Wall-clock time of the most recent message in this window. Messaging connectors set
    finished_at to the newest message time (they extend it on append), so it is exactly
    'last contacted'; fall back to created_at."""
    return getattr(conversation, 'finished_at', None) or getattr(conversation, 'created_at', None)


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
        if not _ENRICHMENT_ENABLED:
            return results
        if _source_value(conversation) not in _TEXTING_SOURCES:
            return results

        segments = getattr(conversation, 'transcript_segments', None) or []
        if not segments:
            return results

        person_ids = _person_ids_for(conversation)
        if not person_ids:
            return results

        # Cost guard: only enrich threads at/under the participant cap (1:1 by default).
        # Larger group windows would re-extract the full transcript once per participant;
        # they are left to the existing whole-conversation extraction. Bounded, not skipped
        # silently for 1:1 — this only trims the expensive many-participant case.
        if len(person_ids) > _MAX_PERSONS_PER_CONVERSATION:
            logger.info(
                f'person_messaging: skipping {len(person_ids)}-participant conversation '
                f'(cap={_MAX_PERSONS_PER_CONVERSATION}) uid={uid} conv={getattr(conversation, "id", "?")}'
            )
            return results

        # The user's name is needed only to render the transcript readably; person-specific
        # dedup context is fetched per person below.
        user_name, _ = get_prompt_memories(uid)
        artifact_ref = _transcript_artifact_ref(conversation)
        source_id = getattr(conversation, 'id', None)
        last_contact_at = _last_contact_at(conversation)

        for person_id in person_ids:
            try:
                person = users_db.get_person(uid, person_id)
                if not person:
                    continue
                person_name = person.get('name') or 'Contact'

                # Record recency of contact (PIL-style last_contacted_at). Guarded and
                # best-effort — a failure here must not block fact extraction. Only advance
                # it forward so an out-of-order backfill window can't move it backwards.
                if last_contact_at is not None:
                    try:
                        existing_contact = person.get('last_contacted_at')
                        if existing_contact is None or last_contact_at > existing_contact:
                            users_db.update_person_profile(uid, person_id, {'last_contacted_at': last_contact_at})
                    except Exception as e:
                        logger.warning(f'person_messaging: last_contacted_at update failed person={person_id}: {e}')
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
