"""Persist-payload and log helpers for the untrusted client display projection.

These live outside ``process_conversation`` on purpose. They are pure, they are
needed by two routers as well as the coordinator, and importing them must not
drag in the coordinator's module graph — a test that stubs
``utils.conversations.process_conversation`` would otherwise silently receive a
MagicMock in place of a security-relevant helper and still pass.

The module is the shared home of the generic persist-payload discipline: every
builder that serializes a Conversation for a Firestore persist passes its dict
through these helpers, wherever it lives.
"""

from __future__ import annotations

import unicodedata
from typing import Any

PROVENANCE_LOG_MAX_CHARS = 64
_UNSAFE_LOG_CHAR_CATEGORIES = frozenset({'Cc', 'Cf', 'Cs', 'Co', 'Cn', 'Zl', 'Zp'})


def sanitize_untrusted_provenance_field(value: Any) -> str:
    """Bound a rejected-payload provenance field for a single-line log record.

    The reject log is the one place these values are known-untrusted. Non-strings
    and any control / line-separator characters become ``<invalid>``; oversize
    values are truncated. Never returns transcript or projection body.
    """
    if value is None:
        return 'None'
    if not isinstance(value, str):
        return '<invalid>'
    if any(unicodedata.category(ch) in _UNSAFE_LOG_CHAR_CATEGORIES for ch in value):
        return '<invalid>'
    if len(value) > PROVENANCE_LOG_MAX_CHARS:
        return value[:PROVENANCE_LOG_MAX_CHARS]
    return value


def strip_client_processing(payload: dict[str, Any]) -> dict[str, Any]:
    """Generic persists never write ``client_processing``.

    ``Conversation.dict()`` / ``model_dump()`` always emit the field, including
    a stale in-memory value a long-running processor captured before a later
    ingest write. Persist uses ``merge=True``, so any presence of the key —
    null or non-null — would last-writer-wins over a newer projection or a
    genuine clear. Strip unconditionally. The field is written only by
    ``client_processing_mutation`` at an ingest-owner site — never by a
    processor persist of a conversation that already exists.
    """
    # Imported here, not at module scope. This module is deliberately import-light
    # (see the module docstring), and a module-scope `from models.client_processing
    # import ...` makes merely *collecting* an unrelated test file fail whenever any
    # earlier test has stubbed the `models` package in sys.modules -- seven suites in
    # tests/unit currently do. The import then resolves at call time, by which point
    # the stub is long torn down. See #12779.
    from models.client_processing import PROJECTION_FAMILY_FIELDS

    for field in PROJECTION_FAMILY_FIELDS:
        payload.pop(field, None)
    return payload


def omit_null_processing_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Generic persist payloads never write a null ``processing_state``.

    ``Conversation.dict()`` / ``model_dump()`` always emit the modeled field,
    including its None default. Persist is ``merge=True``, so that emitted None
    is a real Firestore key: missing versus explicit-null is a distinction the
    dark rollout must respect (``terminal_no_derived_effects`` is written only
    by the branch that owns it; this field is the same discipline). Drop the
    key whenever nothing wrote a real state. A real value — the flag-on
    minimum's ``local_pending`` — passes through untouched.

    Clearing a stale state on enrichment is the opposite write and cannot be
    an omission: an omitted key survives the merge. The enrichment persist
    writes the explicit null itself (see ``_normal_persist_payload``).
    """
    if payload.get('processing_state') is None:
        payload.pop('processing_state', None)
    # Same discipline for the dead-letter's ``summary_retryable`` marker: only
    # the finalization dead-letter writes it, never a generic persist's null.
    if payload.get('summary_retryable') is None:
        payload.pop('summary_retryable', None)
    return payload


def clear_summary_retryable(payload: dict[str, Any]) -> dict[str, Any]:
    """A processing result answers a pending summary retry.

    Used by the enrichment persists: a row that carried
    ``summary_retryable=True`` now holds the outcome of a new processing pass,
    so the retry affordance must go. merge=True keeps an omitted key, so a set
    marker is cleared with an explicit null; an absent or null marker is
    omitted so enrichment never stamps a new key onto every conversation.
    """
    if payload.get('summary_retryable') is None:
        payload.pop('summary_retryable', None)
    else:
        payload['summary_retryable'] = None
    return payload


def client_processing_mutation(projection: Any) -> dict[str, Any]:
    """The only persist payload that may write ``client_processing``.

    Ingress-owned mutation: that field alone. ``projection`` is a validated
    ``ClientProcessing`` or its JSON dump.

    Contract — two call shapes, both ingress, never a processor completing
    an existing row:

    1. Merge into a document-create payload (``create_processing_conversation``
       / ``create_completed_conversation`` when this persist IS the conversation's
       first write). ``_store_budget_waiting`` do this only for
       ``CreateConversation`` / ``ExternalIntegrationCreateConversation``.
    2. Pass to ``update_conversation`` after the coordinator returns. This is
       the working way for a route whose conversation already exists (from-segments
       post-create stamp, late-bind, synchronous finalize): the coordinator's
       existing-conversation persist always omits the field, so the route must
       stamp through this mutation or the projection is not in Firestore.

    Mixing this dict into ``persist_processed_conversation`` (or any other
    existing-row processor persist) is the stale-overwrite hole: a later
    ingest mutation would last-writer-lose to an in-memory snapshot.
    """
    dumped = projection.model_dump(mode='json') if hasattr(projection, 'model_dump') else projection
    return {'client_processing': dumped}


def custom_stt_source_token(conversation: Any) -> str | None:
    """Extract normalized string source token from a conversation or create payload."""
    raw = getattr(conversation, 'source', None)
    token = getattr(raw, 'value', raw)
    return token if isinstance(token, str) else None


def should_skip_custom_stt_postprocessing(
    uid: str,
    conversation: Any,
    skip_fn: Any,
    *,
    strict_bool: bool = False,
) -> bool:
    """Check whether Omi-paid post-processing is skipped for a custom-STT conversation."""
    raw_flag = getattr(conversation, 'uses_custom_stt', False)
    custom_stt = (raw_flag is True) if strict_bool else bool(raw_flag)
    if not custom_stt:
        return False
    return bool(skip_fn(uid, uses_custom_stt=custom_stt, source=custom_stt_source_token(conversation)))


def complete_exhausted_custom_stt_conversation(
    uid: str,
    conversation: Any,
    *,
    generated_conversation_id: str | None,
    client_projection: Any,
    has_refresh_fence: bool,
    hooks: tuple[Any, Any, Any, Any],
    on_persisted: Any,
) -> Any:
    """Persist a zero-LLM completed conversation when custom-STT processing credits are exhausted.

    Live `/v4/listen?custom_stt=enabled` and ingress creates intentionally bypass managed-STT
    credit checks at capture time, then hit `should_skip_omi_paid_postprocessing` during
    post-processing. Mutating `status` only in memory left Firestore rows stranded in
    `status='processing'` with blank titles and caused durable finalization to fence as
    `lifecycle persistence lost` (#23923). Reprocesses of already-completed enriched rows still
    preserve their existing summaries without overwriting them.
    """
    from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation
    from models.conversation_enums import ConversationStatus
    from utils.conversations.recovery import TERMINAL_NO_DERIVED_EFFECTS_FIELD
    from utils.conversations.sync_hold_completion import defer_held_budget_denial
    from utils.free_tier_processing_policy import client_summaries_at_cap_enabled

    build_structured, materialize_conversation, lifecycle_service, log = hooks
    is_initial_creation = isinstance(conversation, (CreateConversation, ExternalIntegrationCreateConversation))

    log.info(
        'custom-STT processing budget exhausted: skipping Omi-paid post-processing uid=%s conv=%s',
        uid,
        getattr(conversation, 'id', '?'),
    )
    if not is_initial_creation and not isinstance(conversation, Conversation):
        on_persisted(False, None)
        return conversation

    existing_structured = getattr(conversation, 'structured', None)
    has_existing_title = bool((getattr(existing_structured, 'title', '') or '').strip())
    if not is_initial_creation and (
        has_refresh_fence or (conversation.status == ConversationStatus.completed and has_existing_title)
    ):
        defer_held_budget_denial()
        on_persisted(False, None)
        return conversation

    structured = existing_structured if has_existing_title else build_structured(conversation)
    result = materialize_conversation(
        uid,
        structured,
        conversation,
        generated_conversation_id,
        relevance_discarded=False,
    )
    allow_projection = bool(client_summaries_at_cap_enabled())
    effective_projection = (
        client_projection
        if allow_projection and client_projection is not None
        else getattr(conversation, 'client_processing', None)
    )
    if effective_projection is not None:
        result.client_processing = effective_projection
    had_summary_retryable = getattr(result, 'summary_retryable', None) is not None
    result.deferred = False
    result.discarded = False
    result.status = ConversationStatus.completed
    if getattr(result, 'processing_state', None) is not None:
        result.processing_state = None
    result.summary_retryable = None
    payload = omit_null_processing_state(strip_client_processing(result.model_dump()))
    if had_summary_retryable:
        payload['summary_retryable'] = None
    payload[TERMINAL_NO_DERIVED_EFFECTS_FIELD] = True
    if is_initial_creation:
        if allow_projection and client_projection is not None:
            payload.update(client_processing_mutation(client_projection))
        persisted = lifecycle_service.create_completed_conversation(uid, payload, idempotent=True)
    else:
        persisted = lifecycle_service.persist_processed_conversation(uid, payload)
    on_persisted(persisted, result)
    return result
