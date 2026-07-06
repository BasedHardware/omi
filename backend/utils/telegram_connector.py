"""Telegram connector.

The desktop app runs an on-device MTProto client (Telethon) that reads the user's
Telegram messages — bootstrapped from the already-logged-in Telegram Desktop
session — normalizes new threads, and POSTs them here. This module turns those
threads into real Omi conversations (with per-message speaker + person
attribution), resolves each sender to a canonical Person, and reuses the normal
conversation post-processing pipeline (summary + memory + knowledge graph).

There is no OAuth — the MTProto session lives on the user's Mac, so connecting IS
the consent signal. All ingested content is gated behind stored consent
(`enabled`) and per-sender opt-out (`opted_out_handles`).

Correctness mirrors the iMessage connector (see database/telegram.py):

- **Durable per-message ledger.** Every ingested message is claimed with an atomic
  Firestore create at `users/{uid}/integrations/telegram/processed_messages/{key}`
  BEFORE its conversation is persisted, so a failed conversation stays retryable
  and concurrent ingests can't duplicate a message.
- **Deterministic day-windowing.** New messages are grouped by (chat_id, calendar
  day) into a conversation with a deterministic id, so messages from the same
  chat+day across multiple syncs converge into ONE conversation. The first sync of
  a window CREATES + fully post-processes it; later syncs APPEND raw segments and
  extend finished_at (no second memory/summary run — see _enrich_conversations).

The platform-agnostic segment/window helpers are imported from imessage_connector
to avoid duplicating that logic; only the ledger, integration key, ConversationSource,
and Person source differ.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import database.conversations as conversations_db
from database import telegram as telegram_db
from database import users as users_db
from database.document_ids import document_id_from_seed
from models.conversation import Conversation
from models.conversation_enums import ConversationSource
from models.structured import Structured
from models.telegram import (
    TelegramIngestRequest,
    TelegramIngestResponse,
    TelegramSettings,
    TelegramStatus,
    TelegramThread,
)
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation

# Reuse the platform-agnostic segment/window helpers (no ledger/source coupling).
from utils.imessage_connector import (
    _append_to_conversation,
    _build_segments,
    _norm_dt,
    _window_day,
)
from utils.executors import db_executor, llm_executor, postprocess_executor, run_blocking, start_background_task
from utils.llm.person_profile import generate_person_profile
from utils.memory.person_messaging_enrichment import enrich_persons_from_conversation
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

INTEGRATION_KEY = 'telegram'
PERSON_SOURCE = 'telegram'


# ---------------------------------------------------------------------------
# Pure id derivation (no I/O).
# ---------------------------------------------------------------------------


def processed_message_key(chat_id: str, message_id: str) -> str:
    """Stable ledger doc id for a single message within a chat thread."""
    return document_id_from_seed(f"{chat_id}:{message_id}")


def telegram_conversation_id(uid: str, chat_id: str, day: str) -> str:
    """Deterministic conversation id for a (chat, calendar-day) window so the same
    chat+day converges into ONE conversation across syncs. ``day`` is ``YYYY-MM-DD``."""
    return document_id_from_seed(f"{uid}:{chat_id}:{day}")


# ---------------------------------------------------------------------------
# State (stored in users/{uid}/integrations/telegram)
# ---------------------------------------------------------------------------


def _get_doc(uid: str) -> dict:
    return users_db.get_integration(uid, INTEGRATION_KEY) or {}


def _save_doc(uid: str, patch: dict) -> None:
    doc = _get_doc(uid)
    doc.update(patch)
    users_db.set_integration(uid, INTEGRATION_KEY, doc)


def get_settings(uid: str) -> TelegramSettings:
    doc = _get_doc(uid)
    return TelegramSettings(
        enabled=bool(doc.get('enabled', False)),
        opted_out_handles=list(doc.get('opted_out_handles') or []),
        backfill_days=int(doc.get('backfill_days', 90)),
    )


def update_settings(uid: str, settings: TelegramSettings) -> TelegramSettings:
    _save_doc(
        uid,
        {
            'enabled': settings.enabled,
            'opted_out_handles': settings.opted_out_handles,
            'backfill_days': settings.backfill_days,
        },
    )
    return get_settings(uid)


def get_status(uid: str) -> TelegramStatus:
    doc = _get_doc(uid)
    last_synced = doc.get('last_synced_at')
    if isinstance(last_synced, str):
        try:
            last_synced = datetime.fromisoformat(last_synced)
        except ValueError:
            last_synced = None
    return TelegramStatus(
        connected=bool(doc.get('connected', False)),
        enabled=bool(doc.get('enabled', False)),
        last_synced_at=last_synced,
        conversations_ingested=int(doc.get('conversations_ingested', 0)),
    )


def disconnect(uid: str) -> None:
    users_db.delete_integration(uid, INTEGRATION_KEY)


# ---------------------------------------------------------------------------
# Conversation construction
# ---------------------------------------------------------------------------


def _build_new_conversation(
    conv_id: str,
    started_at: datetime,
    finished_at: datetime,
    segments: List[TranscriptSegment],
    language: Optional[str],
) -> Conversation:
    """A Conversation carrying the deterministic id + telegram source. Passing a
    Conversation (not a CreateConversation) makes process_conversation reuse this id
    instead of minting a random uuid, which lets same-chat+day windows converge."""
    if finished_at <= started_at:
        finished_at = started_at
    return Conversation(
        id=conv_id,
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        transcript_segments=segments,
        source=ConversationSource.telegram,
        language=language or 'en',
        structured=Structured(),  # overwritten by process_conversation
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
    chat_id: str,
    messages: List,
    handle_to_person: Dict[str, str],
    language: Optional[str],
) -> _WindowResult:
    """Synchronously and durably persist one (chat, day) window — insert-first.

    1. Claim each message atomically FIRST so two concurrent ingests can never turn
       the same message into duplicate conversations/segments.
    2. Durably write the won messages' conversation (create for a new window, else
       append). NO LLM work happens here.
    3. If that durable write fails, RELEASE the just-won claims so the messages are
       retried on the next sync.
    """
    won: List = []
    won_keys: List[str] = []
    race_skipped = 0
    for m in messages:
        key = processed_message_key(chat_id, m.message_id)
        if telegram_db.claim_message(uid, key, chat_id, m.message_id):
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
        # Same chat+day already ingested earlier: append new segments, extend
        # finished_at. Appends deliberately do NOT re-run the pipeline.
        existing = conversations_db.get_conversation(uid, conv_id)
        appended = existing is not None and _append_to_conversation(uid, conv_id, existing, won, handle_to_person)
        if not appended:
            # The target conversation vanished between the create-check and the append
            # (rare delete race), so nothing was stored. Raise to hit the except-handler
            # below: it releases these claims so the messages are resent, and the window is
            # reported failed (all_persisted=False) rather than silently counted as
            # persisted.
            raise RuntimeError(f'append target conversation missing uid={uid} conv={conv_id}')
        return _WindowResult(created=False, conversation=None, persisted=len(won), race_skipped=race_skipped)
    except Exception:
        for key in won_keys:
            telegram_db.release_message(uid, key)
        raise


async def _enrich_conversations(
    uid: str,
    language: Optional[str],
    created_conversations: List,
    person_ids: List[str],
) -> None:
    """Best-effort background enrichment for conversations already persisted.

    Runs the full post-processing pipeline (summary + memory + action-item
    extraction) on each NEWLY created conversation, then refreshes person profiles.
    Every conversation here is already durable, so a failure only means the
    summary/memories are missing (retryable later) — it NEVER drops content.

    Limited to the CREATE case on purpose: re-running process_conversation on an
    appended conversation re-pushes external task integrations, so appends only
    extend the transcript.
    """
    for conversation in created_conversations:
        try:
            await run_blocking(postprocess_executor, process_conversation, uid, language or 'en', conversation)
        except Exception as e:
            logger.error(
                f'telegram: enrichment failed (content already durable) uid={uid} '
                f'conv={getattr(conversation, "id", "?")}: {sanitize(str(e))}'
            )
        # Absorb per-person durable facts (Phase 1). Content is already durable, so a
        # failure here only means the person-keyed facts are missing (retryable later).
        try:
            await run_blocking(llm_executor, enrich_persons_from_conversation, uid, conversation, language or 'en')
        except Exception as e:
            logger.warning(
                f'telegram: person enrichment failed uid={uid} '
                f'conv={getattr(conversation, "id", "?")}: {sanitize(str(e))}'
            )

    for person_id in person_ids:
        try:
            await run_blocking(llm_executor, generate_person_profile, uid, person_id)
        except Exception as e:
            logger.warning(f'telegram: profile generation failed uid={uid} person={person_id}: {sanitize(str(e))}')


async def ingest_threads(uid: str, req: TelegramIngestRequest) -> TelegramIngestResponse:
    """Accept normalized Telegram threads, populate People, and kick off conversation
    post-processing in the background."""
    settings = await run_blocking(db_executor, get_settings, uid)
    opted_out = set(settings.opted_out_handles)

    doc = await run_blocking(db_executor, _get_doc, uid)

    # 1. Gather candidate messages (non-empty, not opted out) with their ledger key.
    candidates: List[Tuple[TelegramThread, object, str]] = []
    for thread in req.threads:
        for m in thread.messages:
            if not (m.text and m.text.strip()):
                continue
            if (not m.is_from_me) and m.handle and m.handle in opted_out:
                continue
            candidates.append((thread, m, processed_message_key(thread.chat_id, m.message_id)))

    # 2. Durable-ledger dedup (batched read).
    all_keys = [key for (_, _, key) in candidates]
    claimed = await run_blocking(db_executor, telegram_db.filter_claimed_keys, uid, all_keys)
    ledger_skipped = sum(1 for (_, _, key) in candidates if key in claimed)
    candidates = [(t, m, key) for (t, m, key) in candidates if key not in claimed]

    # 3. Group surviving messages by (chat_id, calendar day).
    groups: Dict[Tuple[str, str], Dict] = {}
    for thread, m, _key in candidates:
        gkey = (thread.chat_id, _window_day(m.timestamp))
        g = groups.setdefault(gkey, {'thread': thread, 'messages': []})
        g['messages'].append(m)

    # 4. Resolve people per window and build the work list.
    windows: List[Tuple[str, str, List, Dict[str, str]]] = []
    people_ids = set()
    for (chat_id, day), g in groups.items():
        thread = g['thread']
        msgs = g['messages']
        handle_to_person: Dict[str, str] = {}
        handles = {m.handle for m in msgs if (not m.is_from_me) and m.handle}
        for h in handles:
            display_name = thread.display_name if not thread.is_group else None
            person = await run_blocking(
                db_executor, users_db.get_or_create_person_by_handle, uid, h, display_name, PERSON_SOURCE
            )
            handle_to_person[h] = person['id']
            people_ids.add(person['id'])
        conv_id = telegram_conversation_id(uid, chat_id, day)
        windows.append((conv_id, chat_id, msgs, handle_to_person))

    # 5. Durably persist each window synchronously BEFORE responding.
    conversations_created = 0
    messages_ingested = 0
    race_skipped = 0
    failed_windows = 0
    created_conversations: List = []
    for conv_id, chat_id, msgs, handle_to_person in windows:
        try:
            result = await run_blocking(
                db_executor, _persist_window, uid, conv_id, chat_id, msgs, handle_to_person, req.language
            )
        except Exception as e:
            # Claims were released inside _persist_window, so these messages must be
            # resent. Record the failure so the response reports all_persisted=False —
            # Telegram events/backfills are the only source of these payloads, so the
            # client must retry rather than treat a partial-persist batch as done.
            failed_windows += 1
            logger.error(f'telegram: window persist failed uid={uid} conv={conv_id}: {sanitize(str(e))}')
            continue
        messages_ingested += result.persisted
        race_skipped += result.race_skipped
        if result.created:
            conversations_created += 1
            if result.conversation is not None:
                created_conversations.append(result.conversation)

    all_persisted = failed_windows == 0

    # Persist state: mark connected/consented, bump the durable created counter.
    patch = {
        'connected': True,
        'enabled': True,  # connecting + sending data is the consent signal
        'last_synced_at': datetime.now(timezone.utc).isoformat(),
    }
    if conversations_created:
        patch['conversations_ingested'] = int(doc.get('conversations_ingested', 0)) + conversations_created
    await run_blocking(db_executor, _save_doc, uid, patch)

    # Enrichment is best-effort and runs after the durable writes above.
    if created_conversations or people_ids:
        start_background_task(
            _enrich_conversations(uid, req.language, created_conversations, list(people_ids)),
            name=f'telegram_enrich_{uid}',
        )

    skipped = ledger_skipped + race_skipped
    logger.info(
        f'telegram ingest uid={uid} threads={len(req.threads)} windows={len(windows)} '
        f'people={len(people_ids)} msgs={messages_ingested} created={conversations_created} '
        f'skipped={skipped} failed_windows={failed_windows}'
    )
    return TelegramIngestResponse(
        success=True,
        conversations_created=conversations_created,
        people_upserted=len(people_ids),
        messages_ingested=messages_ingested,
        skipped_duplicates=skipped,
        all_persisted=all_persisted,
    )
