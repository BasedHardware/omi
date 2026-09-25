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
    return payload


def client_processing_mutation(projection: Any) -> dict[str, Any]:
    """The only persist payload that may write ``client_processing``.

    Ingress-owned mutation: that field alone. ``projection`` is a validated
    ``ClientProcessing`` or its JSON dump.

    Contract — two call shapes, both ingress, never a processor completing
    an existing row:

    1. Merge into a document-create payload (``create_processing_conversation``
       / ``create_completed_conversation`` when this persist IS the conversation's
       first write). ``_store_projected_conversation`` /
       ``_store_deterministic_minimum`` do this only for
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
