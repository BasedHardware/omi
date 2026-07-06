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
from utils.memory.person_messaging_enrichment import enrich_persons_from_conversation
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
) -> bool:
    """Conservative append: add new segments (offsets relative to the existing
    conversation's started_at, speakers kept consistent) and extend finished_at,
    persisting via append_transcript_segments. No re-summarization or
    memory/action-item re-extraction runs here (see _process_windows).

    Returns True when the segments were durably stored (or there was nothing to add),
    False when the target conversation vanished before the write landed — the caller
    must treat False as a persist failure so the messages are resent, not counted as
    stored."""
    existing = deserialize_conversation(existing_data)
    base = existing.started_at or existing.created_at
    person_to_speaker, next_idx = _speaker_map_from_segments(existing.transcript_segments)
    new_segments, _ = _build_segments(messages, base, handle_to_person, person_to_speaker, next_idx)
    if not new_segments:
        return True

    prev_finished = existing.finished_at or existing.started_at or existing.created_at
    new_finished = max([_norm_dt(prev_finished)] + [_norm_dt(m.timestamp) for m in messages])
    # Append transactionally: two concurrent (chat, day) appends must not overwrite
    # each other's already-persisted segments. update_conversation_segments does a
    # non-atomic read-modify-write of the single segments blob (last writer wins,
    # silently dropping the loser's claimed messages); append_transcript_segments
    # re-reads and concatenates inside a Firestore transaction instead.
    return conversations_db.append_transcript_segments(
        uid, conv_id, [s.dict() for s in new_segments], finished_at=new_finished
    )


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------


class _WindowResult:
    """Outcome of durably persisting one (chat, day) window (see _persist_window)."""

    def __init__(self, created: bool, conversation, persisted: int, race_skipped: int):
        self.created = created  # True only when a NEW conversation doc was created
        self.conversation = conversation  # the created Conversation to enrich later (None on append)
        self.persisted = persisted  # messages this request durably stored
        self.race_skipped = race_skipped  # messages a concurrent ingest claimed first


def _persist_window(
    uid: str,
    conv_id: str,
    chat_guid: str,
    messages: List,
    handle_to_person: Dict[str, str],
    language: Optional[str],
) -> _WindowResult:
    """Synchronously and durably persist one (chat, day) window — insert-first.

    Runs entirely before the ingest HTTP response, so a 200 means the messages
    are durably accepted (the desktop ROWID cursor is only an optimization, never
    the correctness mechanism):

    1. Claim each message atomically FIRST (``claim_message``). Only messages this
       request wins proceed, so two concurrent ingests can never turn the same
       message into duplicate conversations/segments.
    2. Durably write the won messages' conversation with its raw segments —
       ``create_conversation_if_absent`` for a new (chat, day) window, or append to
       an existing one. NO LLM work happens here.
    3. If that durable write fails, RELEASE the just-won claims so the messages are
       retried on the next sync (never stranded as claimed-but-unstored).

    Summary/memory/action-item enrichment runs later, best-effort, and its failure
    must NOT undo these claims — the raw content is already durable.
    """
    won: List = []
    won_keys: List[str] = []
    race_skipped = 0
    for m in messages:
        key = processed_message_key(chat_guid, m.guid)
        if imessage_db.claim_message(uid, key, chat_guid, m.guid):
            won.append(m)
            won_keys.append(key)
        else:
            race_skipped += 1
    if not won:
        return _WindowResult(created=False, conversation=None, persisted=0, race_skipped=race_skipped)

    try:
        started_at = min(_norm_dt(m.timestamp) for m in won)
        finished_at = max(_norm_dt(m.timestamp) for m in won)
        segments, _ = _build_segments(won, started_at, handle_to_person, {}, 1)
        conversation = _build_new_conversation(conv_id, started_at, finished_at, segments, language)
        created = conversations_db.create_conversation_if_absent(uid, conversation.dict())
        if created:
            return _WindowResult(created=True, conversation=conversation, persisted=len(won), race_skipped=race_skipped)
        # Same chat+day already ingested on an earlier sync: append the new
        # segments and extend finished_at. Appends deliberately do NOT re-run the
        # pipeline (see _enrich_conversations for the rationale).
        existing = conversations_db.get_conversation(uid, conv_id)
        appended = existing is not None and _append_to_conversation(uid, conv_id, existing, won, handle_to_person)
        if not appended:
            # The target conversation vanished between the create-check and the append
            # (rare delete race), so nothing was stored. Raise to hit the except-handler
            # below: it releases these claims so the messages are resent, and the window is
            # reported failed (all_persisted=False) rather than silently counted as
            # persisted with the cursor advancing past dropped messages.
            raise RuntimeError(f'append target conversation missing uid={uid} conv={conv_id}')
        return _WindowResult(created=False, conversation=None, persisted=len(won), race_skipped=race_skipped)
    except Exception:
        # Durable write failed — release claims so these messages retry next sync.
        for key in won_keys:
            imessage_db.release_message(uid, key)
        raise


async def _enrich_conversations(
    uid: str,
    language: Optional[str],
    created_conversations: List,
    person_ids: List[str],
) -> None:
    """Best-effort background enrichment for conversations already persisted.

    Runs the full post-processing pipeline (summary + memory + action-item
    extraction) on each NEWLY created conversation, then refreshes person
    profiles. Every conversation here is already durable, so a failure only means
    the summary/memories are missing (retryable later) — it NEVER drops content.

    Enrichment is limited to the CREATE case on purpose: re-running
    process_conversation on an appended conversation is idempotent for internal
    memories/action items and the summary vector, but NOT for the external
    task-integration sync (Todoist / MS To Do get a fresh push on every
    reprocess). So appends only extend the transcript; a future idempotent
    "window close" reprocess can enrich them later."""
    for conversation in created_conversations:
        try:
            await run_blocking(postprocess_executor, process_conversation, uid, language or 'en', conversation)
        except Exception as e:
            logger.error(
                f'imessage: enrichment failed (content already durable) uid={uid} '
                f'conv={getattr(conversation, "id", "?")}: {sanitize(str(e))}'
            )
        # Absorb per-person durable facts (Phase 1). Content is already durable, so a
        # failure here only means the person-keyed facts are missing (retryable later).
        try:
            await run_blocking(llm_executor, enrich_persons_from_conversation, uid, conversation, language or 'en')
        except Exception as e:
            logger.warning(
                f'imessage: person enrichment failed uid={uid} '
                f'conv={getattr(conversation, "id", "?")}: {sanitize(str(e))}'
            )

    for person_id in person_ids:
        try:
            await run_blocking(llm_executor, generate_person_profile, uid, person_id)
        except Exception as e:
            logger.warning(f'imessage: profile generation failed uid={uid} person={person_id}: {sanitize(str(e))}')


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
    windows: List[Tuple[str, str, List, Dict[str, str]]] = []
    people_ids = set()
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
        windows.append((conv_id, chat_guid, msgs, handle_to_person))

    # 5. Durably persist each window synchronously (insert-first claim + write)
    #    BEFORE responding, so a 200 means the messages are safely accepted and the
    #    desktop can advance its cursor without risking data loss. Only best-effort
    #    LLM enrichment is deferred to the background.
    conversations_created = 0
    messages_ingested = 0
    race_skipped = 0
    failed_windows = 0
    created_conversations: List = []
    for conv_id, chat_guid, msgs, handle_to_person in windows:
        try:
            result = await run_blocking(
                db_executor, _persist_window, uid, conv_id, chat_guid, msgs, handle_to_person, req.language
            )
        except Exception as e:
            # Claims were released inside _persist_window, so these messages must be
            # resent. Record the failure so we do NOT advance the cursor past this
            # batch below — otherwise the desktop would skip them and they'd be lost.
            failed_windows += 1
            logger.error(f'imessage: window persist failed uid={uid} conv={conv_id}: {sanitize(str(e))}')
            continue
        messages_ingested += result.persisted
        race_skipped += result.race_skipped
        if result.created:
            conversations_created += 1
            if result.conversation is not None:
                created_conversations.append(result.conversation)

    all_persisted = failed_windows == 0

    # Persist state: mark connected/consented, advance cursor, and bump the durable
    # created-conversation counter (all content above is already durable).
    patch = {
        'connected': True,
        'enabled': True,  # clicking Connect + sending data is the consent signal
        'last_synced_at': datetime.now(timezone.utc).isoformat(),
    }
    # Advance the durable cursor ONLY when every window persisted. On any failure the
    # batch is not durable, so leaving last_rowid where it was makes the desktop resend
    # it next sync (the ledger dedups the windows that already landed).
    if all_persisted and req.last_rowid is not None:
        patch['last_rowid'] = req.last_rowid
    if conversations_created:
        patch['conversations_ingested'] = int(doc.get('conversations_ingested', 0)) + conversations_created
    await run_blocking(db_executor, _save_doc, uid, patch)

    # Enrichment is best-effort and runs after the durable writes above.
    if created_conversations or people_ids:
        start_background_task(
            _enrich_conversations(uid, req.language, created_conversations, list(people_ids)),
            name=f'imessage_enrich_{uid}',
        )

    skipped = legacy_skipped + ledger_skipped + race_skipped
    logger.info(
        f'imessage ingest uid={uid} threads={len(req.threads)} windows={len(windows)} '
        f'people={len(people_ids)} msgs={messages_ingested} created={conversations_created} '
        f'skipped={skipped} failed_windows={failed_windows}'
    )
    return IMessageIngestResponse(
        success=True,
        conversations_created=conversations_created,
        people_upserted=len(people_ids),
        messages_ingested=messages_ingested,
        skipped_duplicates=skipped,
        all_persisted=all_persisted,
    )
