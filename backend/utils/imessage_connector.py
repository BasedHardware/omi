"""iMessage connector.

The desktop app reads the local Messages database (~/Library/Messages/chat.db),
normalizes new threads, and POSTs them here. This module turns those threads into
real Omi conversations (with per-message speaker + person attribution), resolves
each contact handle to a canonical Person, and reuses the normal conversation
post-processing pipeline (summary + memory extraction + knowledge graph).

There is no OAuth — access is local to the user's Mac, so the connect action IS
the consent signal. All ingested content is gated behind stored consent
(`enabled`) and per-contact opt-out (`opted_out_handles`).
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from database import users as users_db
from models.conversation import CreateConversation
from models.conversation_enums import ConversationSource
from models.imessage import (
    IMessageIngestRequest,
    IMessageIngestResponse,
    IMessageSettings,
    IMessageStatus,
    IMessageThread,
)
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation
from utils.executors import db_executor, llm_executor, postprocess_executor, run_blocking, start_background_task
from utils.llm.person_profile import generate_person_profile
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

INTEGRATION_KEY = 'imessage'
# Bound the per-user processed-GUID set so the integration doc stays small.
MAX_PROCESSED_GUIDS = 5000


# ---------------------------------------------------------------------------
# State (stored in users/{uid}/integrations/imessage)
# ---------------------------------------------------------------------------


def _get_doc(uid: str) -> dict:
    return users_db.get_integration(uid, INTEGRATION_KEY) or {}


def _save_doc(uid: str, patch: dict) -> None:
    doc = _get_doc(uid)
    doc.update(patch)
    users_db.set_integration(uid, INTEGRATION_KEY, doc)


def get_settings(uid: str) -> IMessageSettings:
    doc = _get_doc(uid)
    return IMessageSettings(
        enabled=bool(doc.get('enabled', False)),
        opted_out_handles=list(doc.get('opted_out_handles') or []),
        backfill_days=int(doc.get('backfill_days', 90)),
    )


def update_settings(uid: str, settings: IMessageSettings) -> IMessageSettings:
    _save_doc(
        uid,
        {
            'enabled': settings.enabled,
            'opted_out_handles': settings.opted_out_handles,
            'backfill_days': settings.backfill_days,
        },
    )
    return get_settings(uid)


def get_status(uid: str) -> IMessageStatus:
    doc = _get_doc(uid)
    last_synced = doc.get('last_synced_at')
    if isinstance(last_synced, str):
        try:
            last_synced = datetime.fromisoformat(last_synced)
        except ValueError:
            last_synced = None
    return IMessageStatus(
        connected=bool(doc.get('connected', False)),
        enabled=bool(doc.get('enabled', False)),
        last_synced_at=last_synced,
        last_rowid=doc.get('last_rowid'),
        conversations_ingested=int(doc.get('conversations_ingested', 0)),
    )


def disconnect(uid: str) -> None:
    users_db.delete_integration(uid, INTEGRATION_KEY)


# ---------------------------------------------------------------------------
# Thread -> Conversation
# ---------------------------------------------------------------------------


def _build_conversation(
    thread: IMessageThread,
    new_messages: List,
    handle_to_person: Dict[str, str],
    language: Optional[str],
) -> Optional[CreateConversation]:
    """Turn a list of new messages in a thread into a CreateConversation with
    per-message speaker + person attribution. Returns None if nothing usable."""
    usable = [m for m in new_messages if m.text and m.text.strip()]
    if not usable:
        return None

    started_at = min(m.timestamp for m in usable)
    finished_at = max(m.timestamp for m in usable)
    if finished_at <= started_at:
        finished_at = started_at

    # Deterministic speaker index per contact handle (SPEAKER_00 is always the user).
    handle_to_speaker: Dict[str, int] = {}
    segments: List[TranscriptSegment] = []
    for m in usable:
        offset = max(0.0, (m.timestamp - started_at).total_seconds())
        if m.is_from_me:
            speaker = 'SPEAKER_00'
            person_id = None
            is_user = True
        else:
            person_id = handle_to_person.get(m.handle or '')
            idx = handle_to_speaker.setdefault(m.handle or '?', len(handle_to_speaker) + 1)
            speaker = f'SPEAKER_{idx:02d}'
            is_user = False
        segments.append(
            TranscriptSegment(
                text=m.text.strip(),
                speaker=speaker,
                is_user=is_user,
                person_id=person_id,
                start=offset,
                end=offset + 1.0,
                stt_provider='imessage',
            )
        )

    return CreateConversation(
        started_at=started_at,
        finished_at=finished_at,
        transcript_segments=segments,
        source=ConversationSource.imessage,
        language=language or 'en',
    )


async def _process_conversations(
    uid: str,
    language: Optional[str],
    conversations: List[Tuple[CreateConversation, List[str]]],
    person_ids: List[str],
) -> None:
    """Background coordinator: run the full post-processing pipeline per conversation,
    then refresh each involved person's profile (now that their conversations are
    stored and indexed).

    Each conversation carries the message GUIDs that produced it. GUIDs are only
    promoted into ``processed_guids`` after their conversation succeeds, so a
    failed conversation stays retryable on the next sync instead of being silently
    dropped forever."""
    processed = 0
    succeeded_guids: List[str] = []
    for create, guids in conversations:
        try:
            await run_blocking(postprocess_executor, process_conversation, uid, language or 'en', create)
            processed += 1
            succeeded_guids.extend(guids)
        except Exception as e:
            logger.error(f'imessage: process_conversation failed uid={uid}: {sanitize(str(e))}')

    for person_id in person_ids:
        try:
            await run_blocking(llm_executor, generate_person_profile, uid, person_id)
        except Exception as e:
            logger.warning(f'imessage: profile generation failed uid={uid} person={person_id}: {sanitize(str(e))}')

    if not processed and not succeeded_guids:
        return

    doc = await run_blocking(db_executor, _get_doc, uid)
    patch: dict = {}
    if succeeded_guids:
        # Keep the stored list in insertion order for the cap slice (so the newest
        # GUIDs survive trimming); use a set only for O(1) dedup membership.
        merged = list(doc.get('processed_guids') or [])
        seen = set(merged)
        for guid in succeeded_guids:
            if guid not in seen:
                merged.append(guid)
                seen.add(guid)
        patch['processed_guids'] = merged[-MAX_PROCESSED_GUIDS:]
    if processed:
        patch['conversations_ingested'] = int(doc.get('conversations_ingested', 0)) + processed
    if patch:
        await run_blocking(db_executor, _save_doc, uid, patch)


async def ingest_threads(uid: str, req: IMessageIngestRequest) -> IMessageIngestResponse:
    """Accept normalized iMessage threads, populate People, and kick off
    conversation post-processing in the background."""
    settings = await run_blocking(db_executor, get_settings, uid)
    opted_out = set(settings.opted_out_handles)

    doc = await run_blocking(db_executor, _get_doc, uid)
    # Set only for O(1) dedup membership; the stored ordered list is trimmed later.
    processed_guids = set(doc.get('processed_guids') or [])

    # Each entry pairs a conversation with the GUIDs that produced it, so the
    # background pipeline can promote GUIDs to processed only after success.
    conversations: List[Tuple[CreateConversation, List[str]]] = []
    people_ids = set()
    messages_ingested = 0
    skipped = 0

    for thread in req.threads:
        new_messages = []
        for m in thread.messages:
            if m.guid in processed_guids:
                skipped += 1
                continue
            if (not m.is_from_me) and m.handle and m.handle in opted_out:
                continue
            new_messages.append(m)
        if not new_messages:
            continue

        # Resolve each distinct contact handle in this thread to a Person.
        handle_to_person: Dict[str, str] = {}
        handles = {m.handle for m in new_messages if (not m.is_from_me) and m.handle}
        for h in handles:
            display_name = thread.display_name if not thread.is_group else None
            person = await run_blocking(db_executor, users_db.get_or_create_person_by_handle, uid, h, display_name)
            handle_to_person[h] = person['id']
            people_ids.add(person['id'])

        create = _build_conversation(thread, new_messages, handle_to_person, req.language)
        if create is None:
            continue
        conversations.append((create, [m.guid for m in new_messages]))
        messages_ingested += len(new_messages)

    # Persist state: mark connected/consented and advance cursor. GUIDs are NOT
    # recorded here — the background pipeline promotes them into processed_guids
    # only after each conversation succeeds, so a failed conversation stays
    # retryable on the next sync instead of being dropped forever.
    patch = {
        'connected': True,
        'enabled': True,  # clicking Connect + sending data is the consent signal
        'last_synced_at': datetime.now(timezone.utc).isoformat(),
    }
    if req.last_rowid is not None:
        patch['last_rowid'] = req.last_rowid
    await run_blocking(db_executor, _save_doc, uid, patch)

    if conversations:
        start_background_task(
            _process_conversations(uid, req.language, conversations, list(people_ids)),
            name=f'imessage_ingest_{uid}',
        )

    logger.info(
        f'imessage ingest uid={uid} threads={len(req.threads)} convs={len(conversations)} '
        f'people={len(people_ids)} msgs={messages_ingested} skipped={skipped}'
    )
    return IMessageIngestResponse(
        success=True,
        conversations_created=len(conversations),
        people_upserted=len(people_ids),
        messages_ingested=messages_ingested,
        skipped_duplicates=skipped,
    )
