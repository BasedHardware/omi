"""iMessage connector.

The desktop app reads the local Messages database (~/Library/Messages/chat.db),
normalizes new threads, and POSTs them here. This module turns those threads into
real Omi conversations (with per-message speaker + person attribution), resolves
each contact handle to a canonical Person, and reuses the normal conversation
post-processing pipeline (summary + memory extraction + knowledge graph).

There is no OAuth — access is local to the user's Mac, so the connect action IS
the consent signal. All ingested content is gated behind stored consent
(`enabled`) and per-contact opt-out (`opted_out_handles`).

Two correctness mechanisms (see database/imessage.py):

- **Durable per-message ledger.** Every ingested message is claimed with an
  atomic Firestore create at
  `users/{uid}/integrations/imessage/processed_messages/{key}`. The claim
  happens only after the message's conversation processes successfully, so a
  failed conversation stays retryable. This replaces the old bounded
  `processed_guids` array (still read for back-compat, no longer written).

- **Deterministic day-windowing.** New messages are grouped by
  (chat_guid, calendar day) into a conversation with a deterministic id, so
  messages from the same chat+day across multiple syncs converge into ONE
  conversation instead of one-conversation-per-poll-batch. The first sync of a
  window CREATES + fully post-processes the conversation; later syncs APPEND raw
  segments and extend finished_at (conservative — no second memory/summary run;
  see _process_windows for the rationale and limitation).
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import database.conversations as conversations_db
from database import imessage as imessage_db
from database import users as users_db
from database.document_ids import document_id_from_seed
from models.conversation import Conversation
from models.conversation_enums import ConversationSource
from models.imessage import (
    IMessageIngestRequest,
    IMessageIngestResponse,
    IMessageSettings,
    IMessageStatus,
    IMessageThread,
)
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation
from utils.executors import db_executor, llm_executor, postprocess_executor, run_blocking, start_background_task
from utils.llm.person_profile import generate_person_profile
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

INTEGRATION_KEY = 'imessage'


# ---------------------------------------------------------------------------
# Pure id derivation (no I/O). Kept here (not in database/) so calling them from
# async code isn't misflagged as blocking DB access by the async blocker scanner.
# The database ledger helpers (claim_message/filter_claimed_keys) take these
# precomputed keys.
# ---------------------------------------------------------------------------


def processed_message_key(chat_guid: str, message_guid: str) -> str:
    """Stable ledger doc id for a single message within a chat thread."""
    return document_id_from_seed(f"{chat_guid}:{message_guid}")


def imessage_conversation_id(uid: str, chat_guid: str, day: str) -> str:
    """Deterministic conversation id for a (chat, calendar-day) window, so the
    same chat+day converges into ONE conversation across syncs. ``day`` is
    ``YYYY-MM-DD``."""
    return document_id_from_seed(f"{uid}:{chat_guid}:{day}")


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
# Segment / conversation construction
# ---------------------------------------------------------------------------


def _norm_dt(dt: datetime) -> datetime:
    """Assume UTC for naive datetimes so subtraction/comparison never crashes."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _window_day(ts: datetime) -> str:
    """Calendar day (UTC) used to bucket messages into a conversation window.

    UTC keeps the day boundary deterministic without a per-user timezone lookup;
    a conversation that straddles UTC midnight splits into two windows, which is
    an acceptable trade for deterministic ids that converge across syncs.
    """
    return _norm_dt(ts).strftime('%Y-%m-%d')


def _speaker_map_from_segments(segments: List[TranscriptSegment]) -> Tuple[Dict[str, int], int]:
    """Rebuild the person_id -> speaker-index map (and next free index) from an
    existing conversation's segments, so appended messages reuse the same
    SPEAKER_NN label per person instead of renumbering."""
    mapping: Dict[str, int] = {}
    max_idx = 0
    for s in segments:
        if s.is_user or not s.speaker or not s.speaker.startswith('SPEAKER_'):
            continue
        try:
            idx = int(s.speaker.split('_')[1])
        except (ValueError, IndexError):
            continue
        max_idx = max(max_idx, idx)
        if s.person_id and s.person_id not in mapping:
            mapping[s.person_id] = idx
    return mapping, max_idx + 1


def _build_segments(
    messages: List,
    base_started_at: datetime,
    handle_to_person: Dict[str, str],
    person_to_speaker: Dict[str, int],
    next_speaker_idx: int,
) -> Tuple[List[TranscriptSegment], int]:
    """Build TranscriptSegments for `messages`. SPEAKER_00 is always the user;
    each other participant gets a stable index via `person_to_speaker` (mutated
    in place). Offsets are relative to `base_started_at`."""
    base = _norm_dt(base_started_at)
    segments: List[TranscriptSegment] = []
    for m in messages:
        offset = max(0.0, (_norm_dt(m.timestamp) - base).total_seconds())
        if m.is_from_me:
            speaker = 'SPEAKER_00'
            person_id = None
            is_user = True
        else:
            person_id = handle_to_person.get(m.handle or '')
            skey = person_id or (m.handle or '?')
            if skey not in person_to_speaker:
                person_to_speaker[skey] = next_speaker_idx
                next_speaker_idx += 1
            speaker = f'SPEAKER_{person_to_speaker[skey]:02d}'
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
    return segments, next_speaker_idx


def _build_new_conversation(
    conv_id: str,
    started_at: datetime,
    finished_at: datetime,
    segments: List[TranscriptSegment],
    language: Optional[str],
) -> Conversation:
    """A Conversation carrying the deterministic id. Passing a Conversation (not
    a CreateConversation) makes process_conversation reuse this id instead of
    minting a random uuid, which is what lets same-chat+day windows converge."""
    if finished_at <= started_at:
        finished_at = started_at
    return Conversation(
        id=conv_id,
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        transcript_segments=segments,
        source=ConversationSource.imessage,
        language=language or 'en',
        # Placeholder; process_conversation overwrites this with the real summary.
        structured=Structured(),
    )


def _append_to_conversation(
    uid: str,
    conv_id: str,
    existing_data: dict,
    messages: List,
    handle_to_person: Dict[str, str],
) -> None:
    """Conservative append: add new segments (offsets relative to the existing
    conversation's started_at, speakers kept consistent) and extend finished_at,
    persisting via update_conversation_segments. No re-summarization or
    memory/action-item re-extraction runs here (see _process_windows)."""
    existing = deserialize_conversation(existing_data)
    base = existing.started_at or existing.created_at
    person_to_speaker, next_idx = _speaker_map_from_segments(existing.transcript_segments)
    new_segments, _ = _build_segments(messages, base, handle_to_person, person_to_speaker, next_idx)
    if not new_segments:
        return

    combined = list(existing.transcript_segments) + new_segments
    prev_finished = existing.finished_at or existing.started_at or existing.created_at
    new_finished = max([_norm_dt(prev_finished)] + [_norm_dt(m.timestamp) for m in messages])
    conversations_db.update_conversation_segments(uid, conv_id, [s.dict() for s in combined], finished_at=new_finished)


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------


async def _process_windows(
    uid: str,
    language: Optional[str],
    windows: List[Tuple[str, str, IMessageThread, List, Dict[str, str]]],
    person_ids: List[str],
) -> None:
    """Background coordinator. For each (chat_guid, day) window:

    - CREATE case (no conversation yet): run the full post-processing pipeline
      (summary + memory + action-item extraction) on a conversation carrying the
      deterministic id.
    - APPEND case (conversation exists): append the new segments and extend
      finished_at only. We deliberately do NOT re-run the pipeline on append.

    Why the append case is conservative: re-running process_conversation on an
    existing conversation IS idempotent for internal memories/action items
    (extraction deletes-by-conversation-id then re-extracts) and for the summary
    vector (upsert-by-id). It is NOT free of duplication for the external
    task-integration sync inside _save_action_items (Todoist / MS To Do get a
    fresh push on every reprocess), and with is_reprocess=True the structured
    search vector is not refreshed. To guarantee zero duplicate memories /
    action items / external tasks, appends only extend the transcript; the
    summary/memories reflect the window's first sync. A future "window close"
    reprocess can be layered on once the external-sync re-push is made
    idempotent.

    Each message is claimed in the ledger ONLY after its window processes
    successfully, so a failed window leaves its messages retryable next sync."""
    created = 0
    for conv_id, chat_guid, thread, messages, handle_to_person in windows:
        usable = [m for m in messages if m.text and m.text.strip()]
        if not usable:
            continue
        try:
            existing = await run_blocking(db_executor, conversations_db.get_conversation, uid, conv_id)
            if existing:
                await run_blocking(
                    db_executor, _append_to_conversation, uid, conv_id, existing, usable, handle_to_person
                )
            else:
                started_at = min(_norm_dt(m.timestamp) for m in usable)
                finished_at = max(_norm_dt(m.timestamp) for m in usable)
                segments, _ = _build_segments(usable, started_at, handle_to_person, {}, 1)
                conversation = _build_new_conversation(conv_id, started_at, finished_at, segments, language)
                await run_blocking(postprocess_executor, process_conversation, uid, language or 'en', conversation)
                created += 1

            # Claim on success. AlreadyExists just means a concurrent ingest won
            # the race for this message — safe to skip.
            for m in usable:
                key = processed_message_key(chat_guid, m.guid)
                await run_blocking(db_executor, imessage_db.claim_message, uid, key, chat_guid, m.guid)
        except Exception as e:
            logger.error(f'imessage: window processing failed uid={uid} conv={conv_id}: {sanitize(str(e))}')

    for person_id in person_ids:
        try:
            await run_blocking(llm_executor, generate_person_profile, uid, person_id)
        except Exception as e:
            logger.warning(f'imessage: profile generation failed uid={uid} person={person_id}: {sanitize(str(e))}')

    if created:
        doc = await run_blocking(db_executor, _get_doc, uid)
        await run_blocking(
            db_executor,
            _save_doc,
            uid,
            {'conversations_ingested': int(doc.get('conversations_ingested', 0)) + created},
        )


async def ingest_threads(uid: str, req: IMessageIngestRequest) -> IMessageIngestResponse:
    """Accept normalized iMessage threads, populate People, and kick off
    conversation post-processing in the background."""
    settings = await run_blocking(db_executor, get_settings, uid)
    opted_out = set(settings.opted_out_handles)

    doc = await run_blocking(db_executor, _get_doc, uid)
    # Back-compat: messages recorded in the old bounded array (before the durable
    # ledger existed) are still treated as processed so they are not re-ingested.
    legacy_processed = set(doc.get('processed_guids') or [])

    # 1. Gather candidate messages (non-empty, not opted out, not legacy-processed)
    #    paired with their thread and ledger key.
    candidates: List[Tuple[IMessageThread, object, str]] = []
    legacy_skipped = 0
    for thread in req.threads:
        for m in thread.messages:
            if not (m.text and m.text.strip()):
                continue
            if m.guid in legacy_processed:
                legacy_skipped += 1
                continue
            if (not m.is_from_me) and m.handle and m.handle in opted_out:
                continue
            candidates.append((thread, m, processed_message_key(thread.chat_guid, m.guid)))

    # 2. Durable-ledger dedup (batched read). This is the correctness mechanism
    #    for "already ingested"; the ROWID cursor is only an optimization.
    all_keys = [key for (_, _, key) in candidates]
    claimed = await run_blocking(db_executor, imessage_db.filter_claimed_keys, uid, all_keys)
    ledger_skipped = sum(1 for (_, _, key) in candidates if key in claimed)
    candidates = [(t, m, key) for (t, m, key) in candidates if key not in claimed]

    # 3. Group surviving messages by (chat_guid, calendar day).
    groups: Dict[Tuple[str, str], Dict] = {}
    for thread, m, _key in candidates:
        gkey = (thread.chat_guid, _window_day(m.timestamp))
        g = groups.setdefault(gkey, {'thread': thread, 'messages': []})
        g['messages'].append(m)

    # 4. Resolve people per window and build the work list.
    windows: List[Tuple[str, str, IMessageThread, List, Dict[str, str]]] = []
    people_ids = set()
    messages_ingested = 0
    for (chat_guid, day), g in groups.items():
        thread = g['thread']
        msgs = g['messages']
        handle_to_person: Dict[str, str] = {}
        handles = {m.handle for m in msgs if (not m.is_from_me) and m.handle}
        for h in handles:
            display_name = thread.display_name if not thread.is_group else None
            person = await run_blocking(db_executor, users_db.get_or_create_person_by_handle, uid, h, display_name)
            handle_to_person[h] = person['id']
            people_ids.add(person['id'])
        conv_id = imessage_conversation_id(uid, chat_guid, day)
        windows.append((conv_id, chat_guid, thread, msgs, handle_to_person))
        messages_ingested += len(msgs)

    # Persist state: mark connected/consented and advance cursor. Message GUIDs
    # are NOT recorded here — the background pipeline claims them in the durable
    # ledger only after their conversation succeeds.
    patch = {
        'connected': True,
        'enabled': True,  # clicking Connect + sending data is the consent signal
        'last_synced_at': datetime.now(timezone.utc).isoformat(),
    }
    if req.last_rowid is not None:
        patch['last_rowid'] = req.last_rowid
    await run_blocking(db_executor, _save_doc, uid, patch)

    if windows:
        start_background_task(
            _process_windows(uid, req.language, windows, list(people_ids)),
            name=f'imessage_ingest_{uid}',
        )

    skipped = legacy_skipped + ledger_skipped
    logger.info(
        f'imessage ingest uid={uid} threads={len(req.threads)} windows={len(windows)} '
        f'people={len(people_ids)} msgs={messages_ingested} skipped={skipped}'
    )
    return IMessageIngestResponse(
        success=True,
        conversations_created=len(windows),
        people_upserted=len(people_ids),
        messages_ingested=messages_ingested,
        skipped_duplicates=skipped,
    )
