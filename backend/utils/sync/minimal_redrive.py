"""Operator-only minimal redrive of preserved legacy sync audio.

A Cloud Tasks payload carrying ``redrive_mode: 'minimal'`` (written only by
operator redrive tooling, never parsed from a client request) runs the normal
sync job with three cost cuts: Parakeet-only STT with no paid recovery, an
attach-first explicit target, and one cheap title call per newly created row
instead of full post-processing. The ledger, dedupe and receipts are unchanged.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from typing import Any, Callable, Optional

from config.prerecorded_stt import PrerecordedSTTService, TranscriptionOutcome
from config.stt_provider_policy import (
    PARAKEET_PROVIDER,
    STTServingSurface,
    normalized_stt_language,
    parakeet_supports_language,
    provider_is_enabled,
)
from google.cloud import firestore

from database import conversations as conversations_db
from utils.byok import set_byok_keys
from utils.conversations import lifecycle as lifecycle_service
from utils.observability.fallback import record_fallback
from utils.stt.outcomes import TranscriptionFailure, is_destructive_operation_in_progress
from utils.sync import empty_recovery
from utils.sync.clock_run import SYNC_CLOCK_RUN_FIELD
from utils.sync.live_overlap import compatible_capture

logger = logging.getLogger(__name__)

MINIMAL = 'minimal'
TITLE_FEATURE = 'sync_redrive_title'
PROVIDER_UNAVAILABLE = 'sync_minimal_provider_unavailable'
ATTACH_WINDOW_SECONDS = 600
_TRANSCRIPT_CHARS = 8000
_FENCED_IDS = '_fenced_conversation_ids'
_PROMPT = (
    'Write a short title (at most 8 words) and a one- or two-sentence overview for this recorded '
    'conversation, in the language it is spoken in. Reply with JSON only: {"title": "...", "overview": "..."}.'
    '\n\nTranscript:\n'
)


class ProviderUnavailable(TranscriptionFailure):
    """Typed retryable job failure; segment and gather boundaries re-raise it to the task handler."""

    def __init__(self) -> None:
        super().__init__(TranscriptionOutcome.UPSTREAM_ERROR, provider='parakeet', retryable=True)
        self.error_code = PROVIDER_UNAVAILABLE


def parse_mode(payload: Any) -> Optional[str]:
    """Only the exact value ``'minimal'`` selects this mode; anything else is the normal path."""
    return MINIMAL if isinstance(payload, dict) and payload.get('redrive_mode') == MINIMAL else None


def enabled() -> bool:
    """Kill switch: unset means on. Off refuses minimal jobs retryably at the task boundary."""
    return os.getenv('SYNC_MINIMAL_REDRIVE_ENABLED', 'true').strip().lower() not in ('false', '0', 'off', 'no')


def parakeet_service(req_language: str) -> tuple[str, str, str]:
    """Pin Parakeet, or fail retryably. Never select a paid provider.

    Falling back to the owner's paid language provider would be a later,
    explicit operator opt-in; this mode never makes that choice itself.
    """
    language = normalized_stt_language(req_language) or 'en'
    if provider_is_enabled(PARAKEET_PROVIDER, STTServingSurface.PRERECORDED) and parakeet_supports_language(
        STTServingSurface.PRERECORDED, language
    ):
        return PrerecordedSTTService.PARAKEET, language, 'parakeet'
    raise ProviderUnavailable()


def select_service(
    redrive_mode: Optional[str], req_language: str, dispatch: dict, select: Callable[[str], tuple]
) -> tuple:
    """Minimal pins Parakeet into ``dispatch['selected_service']``; otherwise the normal selection."""
    if redrive_mode != MINIMAL:
        return select(req_language)
    dispatch['selected_service'] = parakeet_service(req_language)
    return dispatch['selected_service']


def paid_recovery_enabled(redrive_mode: Optional[str]) -> bool:
    """Minimal never buys empty-segment recovery: a double empty is silence."""
    return redrive_mode != MINIMAL and empty_recovery.enabled()


def segment_target(
    redrive_mode: Optional[str],
    target_id: Optional[str],
    lineage_binding: Optional[str],
    uid: str,
    start: float,
    end: float,
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
    clock_run: Optional[str] = None,
) -> Optional[str]:
    """The caller's explicit target wins; minimal mode adds an attach-first target."""
    if target_id or lineage_binding is not None or redrive_mode != MINIMAL:
        return target_id
    capture = {'source': getattr(source, 'value', source), 'client_device_id': client_device_id, 'is_locked': is_locked}
    if clock_run:
        capture[SYNC_CLOCK_RUN_FIELD] = clock_run
    return attach_target(uid, start, end, capture)


def attach_target(uid: str, start: float, end: float, capture: dict) -> Optional[str]:
    """Closest same-partition, non-deleted completed row within 10 minutes of the segment.

    A hint only: the assignment transaction re-reads the explicit target and
    owns deletion and provenance. Reuses the indexed temporal query shape.
    """

    def eligible(row: dict) -> bool:
        return (
            compatible_capture(row, capture)
            and not row.get('deleted')
            and not row.get('sync_merged_into')
            and row.get('status') == 'completed'
        )

    row = conversations_db.get_closest_conversation_to_timestamps(
        uid, int(start), int(end), window_seconds=ATTACH_WINDOW_SECONDS, eligible=eligible
    )
    return row['id'] if row else None


def _company_title_call(uid: str, prompt: str) -> Any:
    # Deferred like the pipeline's other leaf imports: stubbed coordinator
    # harnesses load this module without the LLM client stack.
    from utils.llm.clients import get_llm

    # Operator work never bills or routes through a user's own key: with no
    # BYOK key in scope get_llm stays on the company gpt-5-nano lane.
    set_byok_keys({})
    return get_llm('sync_redrive_title', uid=uid).invoke(prompt)


def generate_title(uid: str, transcript: str) -> tuple[str, str]:
    # A copied context keeps the BYOK reset local to this one call.
    reply = contextvars.copy_context().run(_company_title_call, uid, _PROMPT + transcript[:_TRANSCRIPT_CHARS])
    text = str(getattr(reply, 'content', reply))
    parsed = json.loads(text[text.index('{') : text.rindex('}') + 1])
    title, overview = str(parsed.get('title') or '').strip(), str(parsed.get('overview') or '').strip()
    if not title or not overview:
        raise ValueError('incomplete title response')
    return title[:120], overview[:600]


def _title_new_conversation(uid: str, conversation_id: str) -> str:
    data = conversations_db.get_conversation(uid, conversation_id)
    if (
        not data
        or data.get('deleted')
        or data.get('discarded')
        or data.get('sync_relevance') == 'review'
        or (data.get('structured') or {}).get('overview')
    ):
        return 'skipped'  # Gone, filler, or already titled by an earlier attempt.
    transcript = '\n'.join(str(segment.get('text') or '') for segment in data.get('transcript_segments') or [])
    try:
        title, overview = generate_title(uid, transcript)
    except Exception as error:
        if is_destructive_operation_in_progress(error):
            raise
        # Intake already stored build_deterministic_minimum_structured: zero further LLM.
        record_fallback(
            component='sync_dispatch', from_mode='llm', to_mode='deterministic', reason='other', outcome='degraded'
        )
        return 'deterministic'
    payload: dict[str, Any] = {
        'id': conversation_id,
        'status': 'completed',
        # The generated title is no longer the disposable server minimum.
        'structured': {'title': title, 'overview': overview, 'title_provenance': firestore.DELETE_FIELD},
    }
    if data.get('data_protection_level') is not None:
        # Keep the row's stored level; never re-stamp it from the current profile.
        payload['data_protection_level'] = data['data_protection_level']
    if data.get('sync_content_revision') is not None:
        payload['sync_content_revision'] = data['sync_content_revision']
    return 'titled' if lifecycle_service.persist_processed_conversation(uid, payload) else 'fenced'


def finalize(uid: str, response: dict) -> None:
    """Replace post-processing: updated rows keep the intake append; new rows get one cheap title.

    No memories, action items, apps, goals, folders, vectors, webhooks or notifications.
    """
    response.pop('_merged', None)
    created = set(response.get('new_memories') or ()) - set(response.get(_FENCED_IDS) or ())
    outcomes = [_title_new_conversation(uid, conversation_id) for conversation_id in sorted(created)]
    logger.info(
        'event=sync_minimal_redrive_finalize created=%d updated=%d titled=%d deterministic=%d',
        len(created),
        len(set(response.get('updated_memories') or ()) - created),
        outcomes.count('titled'),
        outcomes.count('deterministic'),
    )
