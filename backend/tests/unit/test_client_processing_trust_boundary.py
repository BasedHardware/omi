"""S4 named proof (b): client_processing never reaches intelligence plumbing.

A projection is display. This file is a grep-the-plumbing logic test, not an eval.

What the METADATA enforces:
- ``PINNED_CONVERSATION_FIELDS`` is the exact ``Conversation`` field set. A new
  unclassified field fails until the author decides whether it is
  projection-family.
- ``render.PROJECTION_FAMILY_FIELDS`` is the single production classification.
  The integration redactor iterates it (``pop``, not null assignment), so
  classifying a field is what strips it from app/user webhooks. This file
  does not keep a parallel copy.
- The generated sink test then runs every classified field against every
  denylist sink. A field that is only classified, and not actually cleared
  by persist-strip / transcript-edit / in-memory-drop, fails here. That is
  the mechanical connection the pin-only counter-proposal lacked: adding
  ``client_processing_v2`` to the model and both sets, changing nothing else,
  used to keep the pin green while the full dump leaked; it now fails.

What the METADATA does not cover:
- Persist-strip, transcript-edit clear, and in-memory drop still hardcode
  ``client_processing`` in production. They do not import
  ``PROJECTION_FAMILY_FIELDS``. The generated test is what fails until those
  functions actually clear a newly classified field. They cannot all share
  render.py's constant: ``database/`` must not import ``utils/``, and
  ``projection_payload`` is kept coordinator-free (render.py pulls
  database.folders / database.users). A shared leaf home is
  ``models/client_processing.py`` (or ``models/conversation.py``).
- Static dump-scan holes below. Files not in ``_SCAN_FILES``.

What the STATIC identifier scan can see: literal identifier reads — ``ast.Name``,
``ast.Attribute``, argument names, keywords, import aliases, string constants,
and matching function/class names — of ``client_processing`` /
``ClientProcessing`` and the sibling projection identifiers. A hit outside
``_ALLOWED_SCOPES`` or a new triple not in ``PINNED_REFERENCES`` fails.

What the STATIC dump scan can see: any Call of ``.model_dump()`` / ``.dict()``
in a scanned file, regardless of receiver name, unless it passes ``include=``
as a statically-verifiable literal field collection (a Set/List/Tuple of
string constants, or a Dict whose keys are string constants). A Call of
``conversation_to_dict`` / ``as_dict_cleaned_dates`` is always a site. A hit
not in ``PINNED_CONVERSATION_DUMPS`` fails, exact-set, the way a new
identifier does. ``include=None`` and ``include=<Name>`` are not exemptions:
the AST cannot prove what they contain.

What the STATIC dump scan cannot see:
- ``getattr(obj, 'model_dump')()`` / ``model_dump(**kwargs)`` where ``include``
  is smuggled through a dict
- forwarding a dict that was dumped elsewhere (Firestore docs, already-
  serialized payloads)
- files not in ``_SCAN_FILES``

What the DYNAMIC sentinel proves: a Conversation whose projection carries a
unique token is checked against ``str(structured)``, ``get_transcript()``,
``conversations_to_string``, the citation collector + ``Message`` serializer,
and every integration payload (``conversation_to_dict`` then
``redact_conversation_for_integration``), locked or not. The token must be
absent from those surfaces. Generated sink cases additionally inject each
classified field into each denylist sink.

Isolation: ``stub_modules`` + ``load_module_fresh`` for render.py (it imports
database.folders / database.users at module top). Stubs do not leak.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, FrozenSet, NamedTuple
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from models.chat import Message, MessageConversation, MessageSender, MessageType
from models.client_processing import (
    ClientProcessing,
    ProjectedActionItem,
    ProjectedEvent,
    ProjectedSection,
    ProjectedStructure,
    ProjectionProvenance,
)
from models.conversation import Conversation
from models.conversation_enums import CategoryEnum
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import load_module_fresh, stub_modules
from utils.conversations.factory import deserialize_conversation

_BACKEND = Path(__file__).resolve().parents[2]

# Unique token that must never leak into structured / transcript / RAG cards.
# First-upper, rest-lower so Structured.__str__ / conversations_to_string
# ``.capitalize()`` do not hide it (the red-proof relies on the token surviving).
SENTINEL = 'Zxq_projection_sentinel_trust_boundary_9f3a'

_SCAN_IDENTIFIERS = frozenset(
    {
        'client_processing',
        'ClientProcessing',
        'client_projection',
        'ProjectedActionItem',
        'ProjectedSection',
        'ProjectedEvent',
        'ProjectedStructure',
        'ProjectionProvenance',
        'CLIENT_PROCESSING_SCHEMA_VERSION',
    }
)

_SCHEMA_MODULE = 'models/client_processing.py'

# Explicit list — do not rglob. Covers the named plumbing in the S4 brief plus
# goals, action-item stores, chat-RAG, and the daily recap (which may render
# structured, never the projection field).
_SCAN_FILES: tuple[str, ...] = (
    # Allowlisted storage / schema / wire (hits here must still match PINNED_REFERENCES).
    'models/client_processing.py',
    'models/conversation.py',
    'routers/developer.py',
    'utils/conversations/process_conversation.py',
    'utils/conversations/projection_payload.py',
    # Named intelligence plumbing.
    'utils/conversations/render.py',
    'utils/conversations/search.py',
    'utils/conversations/transcript_for_llm.py',
    'utils/conversations/memories.py',
    'database/vector_db.py',
    'database/conversations.py',
    'database/memories.py',
    'utils/llm/memories.py',
    'utils/llms/memory.py',
    'utils/apps.py',
    'utils/app_integrations.py',
    'utils/webhooks.py',
    'utils/llm/external_integrations.py',
    'utils/memory/daily_memory_sweep.py',
    'utils/other/notifications.py',
    # Goals.
    'utils/llm/goals.py',
    'utils/goals_response.py',
    'routers/goals.py',
    'database/goals.py',
    # Action-item / task stores that feed intelligence.
    'database/action_items.py',
    'database/staged_tasks.py',
    'database/task_recommendations.py',
    'utils/mcp_action_items.py',
    'utils/task_intelligence/conversation_capture.py',
    'utils/task_intelligence/backend_capture.py',
    'utils/task_intelligence/contracts.py',
    # Chat RAG / retrieval (explicit, not a tree walk).
    'utils/retrieval/rag.py',
    'utils/retrieval/hybrid.py',
    'utils/retrieval/agentic.py',
    'utils/retrieval/chat_scope.py',
    'utils/retrieval/graph.py',
    'utils/retrieval/safety.py',
    'utils/retrieval/tool_result_boundaries.py',
    'utils/retrieval/web_search_gate.py',
    'utils/retrieval/keyframe_policy.py',
    'utils/retrieval/frame_request_storage.py',
    'utils/retrieval/frame_request_policy.py',
    'utils/retrieval/frame_request_authority.py',
    'utils/retrieval/tool_services/conversations.py',
    'utils/retrieval/tool_services/memories.py',
    'utils/retrieval/tool_services/action_items.py',
    'utils/retrieval/tools/__init__.py',
    'utils/retrieval/tools/conversation_tools.py',
    'utils/retrieval/tools/conversation_jit.py',
    'utils/retrieval/tools/conversation_jit_gate.py',
    'utils/retrieval/tools/memory_tools.py',
    'utils/retrieval/tools/action_item_tools.py',
    'utils/retrieval/tools/app_tools.py',
    'utils/retrieval/tools/calendar_tools.py',
    'utils/retrieval/tools/gmail_tools.py',
    'utils/retrieval/tools/file_tools.py',
    'utils/retrieval/tools/web_tools.py',
    'utils/retrieval/tools/perplexity_tools.py',
    'utils/retrieval/tools/omi_tools.py',
    'utils/retrieval/tools/preference_tools.py',
    'utils/retrieval/tools/notification_settings_tools.py',
    'utils/retrieval/tools/screen_activity_tools.py',
    'utils/retrieval/tools/graph_tools.py',
    'utils/retrieval/tools/knowledge_ledger_tools.py',
    'utils/retrieval/tools/knowledge_ledger_write_tools.py',
    'utils/retrieval/tools/entity_timeline_tools.py',
    'utils/retrieval/tools/chart_tools.py',
    'utils/retrieval/tools/apple_health_tools.py',
    'utils/retrieval/tools/frame_request_tools.py',
    'utils/retrieval/tools/integration_base.py',
    'utils/retrieval/tools/google_utils.py',
    'utils/retrieval/tools/result_bounds.py',
    'routers/conversations.py',
)

# (relpath, innermost scope). Scope '*' allows every scope in that file.
# A hit outside this set is a trust-boundary regression.
_ALLOWED_SCOPES: FrozenSet[tuple[str, str]] = frozenset(
    {
        (_SCHEMA_MODULE, '*'),
        ('models/conversation.py', '<module>'),
        ('models/conversation.py', 'Conversation'),
        ('routers/developer.py', '<module>'),
        ('routers/developer.py', 'CreateConversationFromTranscriptRequest'),
        ('routers/developer.py', '_accepted_client_projection'),
        ('routers/developer.py', '_create_conversation_from_segments'),
        ('utils/conversations/process_conversation.py', '<module>'),
        ('utils/conversations/process_conversation.py', 'process_conversation'),
        ('utils/conversations/process_conversation.py', '_attach_client_projection'),
        ('utils/conversations/process_conversation.py', '_store_projected_conversation'),
        ('utils/conversations/process_conversation.py', '_store_deterministic_minimum'),
        ('utils/conversations/process_conversation.py', '_store_deferred_conversation'),
        ('utils/conversations/projection_payload.py', 'strip_client_processing'),
        ('utils/conversations/projection_payload.py', 'client_processing_mutation'),
        # Serialization sink: family-set definition + integration redaction.
        ('utils/conversations/render.py', '<module>'),
        ('utils/conversations/render.py', 'redact_conversation_for_integration'),
        # Worker B: developer from-segments bind/parse/late-retry helpers.
        ('routers/developer.py', '_parse_client_projection'),
        ('routers/developer.py', '_bind_projection_to_segments'),
        ('routers/developer.py', '_bind_late_client_projection'),
        # Worker C finalize/ingest scopes.
        ('routers/conversations.py', '<module>'),
        ('routers/conversations.py', 'ProcessConversationRequest'),
        ('routers/conversations.py', 'finalize_conversation'),
        ('routers/conversations.py', 'process_in_progress_conversation'),
        ('routers/conversations.py', '_accepted_client_projection'),
        ('routers/conversations.py', '_echo_submitted_projection_if_bound'),
        ('routers/conversations.py', '_bind_late_client_projection'),
        ('routers/conversations.py', '_drop_display_projection'),
        # Transcript-edit genuine clear of the stored projection.
        ('database/conversations.py', '_invalidate_client_processing'),
        # Live-capture write: opt-out still clears a projection that is actually present
        # (finalize overlap). A read of the stored field, then the same genuine clear.
        ('database/conversations.py', '_write_segments'),
    }
)


class Reference(NamedTuple):
    relpath: str
    scope: str
    identifier: str


# Exact reviewed set. A new triple fails until it is inspected against the
# display-only trust boundary and added here. Schema-module hits collapse to one
# wildcard so the Pydantic field list can evolve without a pin churn.
#
# Reviewed production hits: schema + Conversation field + developer request
# field + process_conversation storage/coordinator seams + locked-integration
# redaction + transcript-edit genuine clear + live-capture overlap clear.
# ``_get_structured``, ``extract_memories``, ``save_structured_vector``,
# and RAG are absent. ``conversation_to_dict`` is a dump without a named read.
PINNED_REFERENCES: FrozenSet[Reference] = frozenset(
    {
        Reference(_SCHEMA_MODULE, '*', '*'),
        Reference('models/conversation.py', '<module>', 'ClientProcessing'),
        Reference('models/conversation.py', 'Conversation', 'client_processing'),
        Reference('models/conversation.py', 'Conversation', 'ClientProcessing'),
        Reference('routers/developer.py', '<module>', 'ClientProcessing'),
        Reference('routers/developer.py', 'CreateConversationFromTranscriptRequest', 'client_processing'),
        Reference('routers/developer.py', '_accepted_client_projection', 'ClientProcessing'),
        Reference('routers/developer.py', '_accepted_client_projection', 'client_processing'),
        Reference('routers/developer.py', '_parse_client_projection', 'ClientProcessing'),
        Reference('routers/developer.py', '_bind_projection_to_segments', 'ClientProcessing'),
        Reference('routers/developer.py', '_bind_late_client_projection', 'client_processing'),
        Reference('routers/developer.py', '_create_conversation_from_segments', 'client_projection'),
        Reference('routers/conversations.py', '<module>', 'ClientProcessing'),
        Reference('routers/conversations.py', 'ProcessConversationRequest', 'client_processing'),
        Reference('routers/conversations.py', '_accepted_client_projection', 'ClientProcessing'),
        Reference('routers/conversations.py', 'finalize_conversation', 'client_processing'),
        Reference('routers/conversations.py', 'finalize_conversation', 'client_projection'),
        Reference('routers/conversations.py', '_echo_submitted_projection_if_bound', 'ClientProcessing'),
        Reference('routers/conversations.py', '_echo_submitted_projection_if_bound', 'client_processing'),
        Reference('routers/conversations.py', '_echo_submitted_projection_if_bound', 'client_projection'),
        Reference('routers/conversations.py', 'process_in_progress_conversation', 'client_processing'),
        Reference('routers/conversations.py', 'process_in_progress_conversation', 'client_projection'),
        Reference('utils/conversations/process_conversation.py', '<module>', 'ClientProcessing'),
        Reference('utils/conversations/process_conversation.py', 'process_conversation', 'ClientProcessing'),
        Reference('utils/conversations/process_conversation.py', 'process_conversation', 'client_projection'),
        Reference('utils/conversations/process_conversation.py', 'process_conversation', 'client_processing'),
        Reference('utils/conversations/process_conversation.py', '_attach_client_projection', 'ClientProcessing'),
        Reference('utils/conversations/process_conversation.py', '_attach_client_projection', 'client_processing'),
        Reference('utils/conversations/process_conversation.py', '_attach_client_projection', 'client_projection'),
        Reference('utils/conversations/process_conversation.py', '_store_projected_conversation', 'ClientProcessing'),
        Reference('utils/conversations/process_conversation.py', '_store_projected_conversation', 'client_projection'),
        Reference('utils/conversations/process_conversation.py', '_store_deterministic_minimum', 'ClientProcessing'),
        Reference('utils/conversations/process_conversation.py', '_store_deterministic_minimum', 'client_projection'),
        Reference('utils/conversations/process_conversation.py', '_store_deferred_conversation', 'ClientProcessing'),
        Reference('utils/conversations/process_conversation.py', '_store_deferred_conversation', 'client_projection'),
        Reference(
            'utils/conversations/projection_payload.py',
            'client_processing_mutation',
            'client_processing',
        ),
        Reference(
            'routers/conversations.py',
            '_bind_late_client_projection',
            'client_processing',
        ),
    }
)


def _iter_identifier_nodes(node: ast.AST) -> Iterator[str]:
    if isinstance(node, ast.Name) and node.id in _SCAN_IDENTIFIERS:
        yield node.id
    elif isinstance(node, ast.Attribute) and node.attr in _SCAN_IDENTIFIERS:
        yield node.attr
    elif isinstance(node, ast.arg) and node.arg in _SCAN_IDENTIFIERS:
        yield node.arg
    elif isinstance(node, ast.keyword) and node.arg in _SCAN_IDENTIFIERS:
        yield node.arg
    elif isinstance(node, ast.alias):
        if node.name in _SCAN_IDENTIFIERS:
            yield node.name
        if node.asname in _SCAN_IDENTIFIERS:
            yield node.asname
    elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in _SCAN_IDENTIFIERS:
        yield node.value
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in _SCAN_IDENTIFIERS:
        yield node.name


def collect_references(relpath: str, source: str) -> FrozenSet[Reference]:
    """Return unique (relpath, innermost-scope, identifier) hits in ``source``."""
    tree = ast.parse(source, filename=relpath)
    found: set[Reference] = set()
    scope_stack: list[str] = []

    def current_scope() -> str:
        return scope_stack[-1] if scope_stack else '<module>'

    def visit(node: ast.AST) -> None:
        for identifier in _iter_identifier_nodes(node):
            found.add(Reference(relpath, current_scope(), identifier))
        pushed = False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope_stack.append(node.name)
            pushed = True
        for child in ast.iter_child_nodes(node):
            visit(child)
        if pushed:
            scope_stack.pop()

    visit(tree)
    if relpath == _SCHEMA_MODULE and found:
        return frozenset({Reference(_SCHEMA_MODULE, '*', '*')})
    return frozenset(found)


# Any ``.model_dump()`` / ``.dict()`` in a scanned file is a site unless
# ``include=`` is a statically-verifiable literal field collection. Receiver
# names are not a filter: ``payload = conv; payload.model_dump()`` must be a
# hit. Helper calls (``conversation_to_dict`` / ``as_dict_cleaned_dates``)
# are always sites.
_CONVERSATION_DUMP_METHODS = frozenset({'model_dump', 'dict'})
_CONVERSATION_DUMP_HELPERS = frozenset({'conversation_to_dict', 'as_dict_cleaned_dates'})


class DumpSite(NamedTuple):
    relpath: str
    scope: str
    method: str


def _is_literal_field_collection(node: ast.AST) -> bool:
    """True when ``node`` is a field collection whose members are visible in the AST."""
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return all(isinstance(elt, ast.Constant) and isinstance(elt.value, str) for elt in node.elts)
    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return False
        return all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in node.keys)
    return False


def _static_include_allowlist(call: ast.Call) -> bool:
    """True only when ``include=`` is a literal field collection we can read from the AST.

    ``include=None`` and ``include=fields`` cannot be verified statically, so they
    do not exempt the call. A Set/List/Tuple of string constants, or a Dict
    with string-constant keys, does.
    """
    for kw in call.keywords:
        if kw.arg == 'include':
            return _is_literal_field_collection(kw.value)
    return False


def collect_conversation_dumps(relpath: str, source: str) -> FrozenSet[DumpSite]:
    """Return unique serialization sites in ``source``.

    A hit is any Call of ``.model_dump()`` / ``.dict()`` that does not pass a
    statically-verifiable ``include=`` literal, or a Call of
    ``conversation_to_dict`` / ``as_dict_cleaned_dates``. Receiver names do
    not matter.
    """
    tree = ast.parse(source, filename=relpath)
    found: set[DumpSite] = set()
    scope_stack: list[str] = []

    def current_scope() -> str:
        return scope_stack[-1] if scope_stack else '<module>'

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _CONVERSATION_DUMP_METHODS:
                if not _static_include_allowlist(node):
                    found.add(DumpSite(relpath, current_scope(), func.attr))
            elif isinstance(func, ast.Attribute) and func.attr in _CONVERSATION_DUMP_HELPERS:
                found.add(DumpSite(relpath, current_scope(), func.attr))
            elif isinstance(func, ast.Name) and func.id in _CONVERSATION_DUMP_HELPERS:
                found.add(DumpSite(relpath, current_scope(), func.id))
        pushed = False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope_stack.append(node.name)
            pushed = True
        for child in ast.iter_child_nodes(node):
            visit(child)
        if pushed:
            scope_stack.pop()

    visit(tree)
    return frozenset(found)


def _scan_production() -> FrozenSet[Reference]:
    hits: set[Reference] = set()
    missing: list[str] = []
    for relpath in _SCAN_FILES:
        path = _BACKEND / relpath
        if not path.is_file():
            missing.append(relpath)
            continue
        hits.update(collect_references(relpath, path.read_text(encoding='utf-8')))
    if missing:
        raise AssertionError('scan list names files that do not exist:\n' + '\n'.join(missing))
    return frozenset(hits)


_PRODUCTION_HITS = _scan_production()


def _scan_dumps() -> FrozenSet[DumpSite]:
    hits: set[DumpSite] = set()
    missing: list[str] = []
    for relpath in _SCAN_FILES:
        path = _BACKEND / relpath
        if not path.is_file():
            missing.append(relpath)
            continue
        hits.update(collect_conversation_dumps(relpath, path.read_text(encoding='utf-8')))
    if missing:
        raise AssertionError('scan list names files that do not exist:\n' + '\n'.join(missing))
    return frozenset(hits)


_PRODUCTION_DUMPS = _scan_dumps()


# Storage/persist dumps that copy the projection on purpose (display field on
# the conversation document) plus every other ``.model_dump()`` / ``.dict()``
# in a scanned file, reviewed as either projection-bearing or as noise. A new
# dump in a scanned file fails until reviewed — receiver name is not a filter.
PINNED_CONVERSATION_DUMPS: FrozenSet[DumpSite] = frozenset(
    {
        # Daily-summary stats payloads (`DailySummaryDayStatsPayload`), not
        # conversations: the scanner keys on the call, not the receiver's type,
        # so these two land here. Reviewed 2026-09-04 — neither dump can carry
        # `client_processing`, because neither subject is a `Conversation`.
        DumpSite('utils/llm/external_integrations.py', '_basic_daily_summary', 'model_dump'),
        DumpSite('utils/llm/external_integrations.py', 'generate_comprehensive_daily_summary', 'model_dump'),
        DumpSite('models/conversation.py', 'project_shared_conversation', 'model_dump'),
        DumpSite('models/conversation.py', 'as_dict_cleaned_dates', 'model_dump'),
        DumpSite('utils/conversations/render.py', 'conversation_to_dict', 'model_dump'),
        DumpSite('utils/app_integrations.py', '_single', 'conversation_to_dict'),
        DumpSite('utils/webhooks.py', '_build_conversation_webhook_payload_sync', 'conversation_to_dict'),
        DumpSite('routers/developer.py', 'get_memories', 'model_dump'),
        DumpSite('routers/developer.py', '_create_conversation_from_segments', 'model_dump'),
        DumpSite('routers/developer.py', 'update_goal', 'model_dump'),
        # DailySummaryDayStatsPayload aggregates (counts/minutes watched), not
        # conversation content; transcripts reach the LLM via
        # conversations_to_string. Reviewed with the daily-summary work (#12636).
        DumpSite('utils/llm/external_integrations.py', '_basic_daily_summary', 'model_dump'),
        DumpSite('utils/llm/external_integrations.py', 'generate_comprehensive_daily_summary', 'model_dump'),
        DumpSite(
            'utils/conversations/projection_payload.py',
            'client_processing_mutation',
            'model_dump',
        ),
        DumpSite('utils/conversations/process_conversation.py', '_get_conversation_obj', 'dict'),
        DumpSite('utils/conversations/process_conversation.py', 'execute_app', 'dict'),
        DumpSite(
            'utils/conversations/process_conversation.py',
            '_canonical_conversation_write_payload',
            'model_dump',
        ),
        DumpSite('utils/conversations/process_conversation.py', 'save_transcript_chunk_vectors', 'dict'),
        DumpSite('utils/conversations/process_conversation.py', 'save_structured_vector', 'dict'),
        DumpSite('utils/conversations/process_conversation.py', '_store_deferred_conversation', 'dict'),
        DumpSite('utils/conversations/process_conversation.py', '_terminal_persist_payload', 'dict'),
        DumpSite('utils/conversations/process_conversation.py', '_normal_persist_payload', 'dict'),
        DumpSite('utils/conversations/process_conversation.py', '_store_meeting_context', 'model_dump'),
        DumpSite('utils/conversations/process_conversation.py', '_emit_derived_effects', 'dict'),
        DumpSite('utils/conversations/process_conversation.py', '_emit_derived_effects', 'model_dump'),
        DumpSite('utils/conversations/process_conversation.py', 'process_user_emotion', 'dict'),
        DumpSite(
            'utils/conversations/process_conversation.py',
            'process_user_expression_measurement_callback',
            'dict',
        ),
        DumpSite('routers/conversations.py', 'process_in_progress_conversation', 'model_dump'),
        DumpSite('routers/conversations.py', 'finalize_conversation', 'model_dump'),
        DumpSite('routers/conversations.py', 'link_calendar_event', 'model_dump'),
        DumpSite('routers/conversations.py', 'auto_link_calendar_event', 'model_dump'),
        DumpSite('routers/conversations.py', 'set_conversation_events_state', 'model_dump'),
        DumpSite('routers/conversations.py', 'set_action_item_status', 'model_dump'),
        DumpSite('routers/conversations.py', 'update_action_item_description', 'model_dump'),
        DumpSite('routers/conversations.py', 'delete_action_item', 'model_dump'),
        DumpSite('routers/conversations.py', 'set_assignee_conversation_segment', 'model_dump'),
        DumpSite('routers/conversations.py', 'assign_segments_bulk', 'model_dump'),
        DumpSite('routers/conversations.py', 'get_conversation_suggested_apps', 'model_dump'),
        DumpSite('database/conversations.py', 'store_model_segments_result', 'model_dump'),
        DumpSite('database/conversations.py', '_store', 'model_dump'),
        DumpSite('database/goals.py', 'normalize_goal_storage', 'model_dump'),
        DumpSite('database/goals.py', '_new_goal_payload', 'model_dump'),
        DumpSite('database/goals.py', 'update_goal', 'model_dump'),
        DumpSite('database/goals.py', 'apply', 'model_dump'),
        DumpSite('database/task_recommendations.py', 'create_intervention', 'model_dump'),
        DumpSite('database/task_recommendations.py', 'publish', 'model_dump'),
        DumpSite('database/task_recommendations.py', 'create_feedback', 'model_dump'),
        DumpSite('database/task_recommendations.py', 'apply', 'model_dump'),
        DumpSite('database/task_recommendations.py', 'create_outcome', 'model_dump'),
        DumpSite('database/task_recommendations.py', 'replace_context_snapshot', 'model_dump'),
        DumpSite('database/task_recommendations.py', 'replace_open_loop_snapshot', 'model_dump'),
        DumpSite('utils/apps.py', 'upsert_app_payment_link', 'model_dump'),
        DumpSite('utils/apps.py', 'update_persona_prompt', 'dict'),
        DumpSite('utils/memory/daily_memory_sweep.py', 'digest', 'model_dump'),
        DumpSite('utils/memory/daily_memory_sweep.py', 'reconcile', 'model_dump'),
        DumpSite('utils/memory/daily_memory_sweep.py', '_bounded_candidate_channel', 'model_dump'),
        DumpSite('utils/memory/daily_memory_sweep.py', 'build_candidate_page', 'model_dump'),
        DumpSite(
            'utils/memory/daily_memory_sweep.py',
            '_load_or_stage_onboarding_candidates',
            'model_dump',
        ),
        DumpSite(
            'utils/memory/daily_memory_sweep.py',
            '_load_or_stage_daily_summary_candidates',
            'model_dump',
        ),
        DumpSite('utils/task_intelligence/backend_capture.py', 'policy_signals', 'model_dump'),
        DumpSite('utils/task_intelligence/conversation_capture.py', 'canonical_fields', 'model_dump'),
        # Daily-summary stats payload (not Conversation); scanner matches any model_dump.
        DumpSite('utils/llm/external_integrations.py', '_basic_daily_summary', 'model_dump'),
        DumpSite('utils/llm/external_integrations.py', 'generate_comprehensive_daily_summary', 'model_dump'),
        DumpSite('routers/goals.py', 'create_goal', 'model_dump'),
        DumpSite('routers/goals.py', 'create_canonical_goal', 'model_dump'),
        DumpSite('routers/goals.py', 'update_goal', 'model_dump'),
    }
)


# Exact Conversation field set. A new field fails until the author classifies
# it: projection-family (untrusted client-authored display) or not. Classification
# is ``render.PROJECTION_FAMILY_FIELDS``, which the integration redactor iterates.
# The generated sink test then requires every other denylist sink to actually
# clear each classified field — not assertion text.
PINNED_CONVERSATION_FIELDS: FrozenSet[str] = frozenset(
    {
        'id',
        'created_at',
        'updated_at',
        'started_at',
        'finished_at',
        'source',
        'language',
        'uses_custom_stt',
        'structured',
        'client_processing',
        # S3 (§1.7): server-authored, NOT projection-family. It says why
        # `structured` is the deterministic minimum; it carries no client text,
        # so the integration redactor must not strip it.
        'processing_state',
        'transcript_segments',
        'transcript_segments_compressed',
        'geolocation',
        'photos',
        'audio_files',
        'conversation_audio',
        'private_cloud_sync_enabled',
        'screenshot_sharing_enabled',
        'apps_results',
        'suggested_summarization_apps',
        'plugins_results',
        'external_data',
        'app_id',
        'discarded',
        'imported',
        'visibility',
        'starred',
        'processing_memory_id',
        'processing_conversation_id',
        'status',
        'is_locked',
        'deferred',
        'data_protection_level',
        'folder_id',
        'call_id',
        'calendar_event',
        'client_device_id',
        'client_platform',
        'meeting_treatment_eligible',
        'meeting_treatment_reason',
        'meeting_duration_s',
        'meeting_dedup_speech_s',
    }
)


class ProjectionSink(NamedTuple):
    """One denylist sink the generated family-field test must actually invoke."""

    name: str
    outcome: str  # 'key_absent' | 'delete_field' | 'attr_none'
    fixture_key: str


PROJECTION_SINKS: tuple[ProjectionSink, ...] = (
    ProjectionSink(
        'utils.conversations.render.redact_conversation_for_integration',
        'key_absent',
        'redact',
    ),
    ProjectionSink(
        'utils.conversations.projection_payload.strip_client_processing',
        'key_absent',
        'strip',
    ),
    ProjectionSink(
        'database.conversations._invalidate_client_processing',
        'delete_field',
        'invalidate',
    ),
    ProjectionSink(
        'routers.conversations._drop_display_projection',
        'attr_none',
        'drop',
    ),
)


def _scope_allowed(hit: Reference) -> bool:
    return (hit.relpath, '*') in _ALLOWED_SCOPES or (hit.relpath, hit.scope) in _ALLOWED_SCOPES


def _make_projection() -> ClientProcessing:
    return ClientProcessing(
        schema_version=1,
        transcript_sha256='ab' * 32,
        structure=ProjectedStructure(
            title=SENTINEL,
            overview=f'{SENTINEL} overview',
            emoji='🧠',
            category=CategoryEnum.other,
            sections=[ProjectedSection(heading=f'{SENTINEL} heading', body_markdown=f'{SENTINEL} body')],
            events=[
                ProjectedEvent(
                    title=f'{SENTINEL} event',
                    description=f'{SENTINEL} event-desc',
                    start=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
                    duration=30,
                )
            ],
        ),
        action_items=[ProjectedActionItem(description=f'{SENTINEL} action')],
        provenance=ProjectionProvenance(
            model_id='local-test-model',
            runtime='test-runtime',
            device_class='test-device',
            generated_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        ),
    )


def _make_conversation(
    *,
    projection: bool = True,
    structured_overview: str = '',
    is_locked: bool = False,
) -> Conversation:
    return Conversation(
        id='conv-trust-boundary',
        created_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc),
        structured={
            'title': 'Recording title',
            'overview': structured_overview,
            'category': CategoryEnum.other,
        },
        transcript_segments=[
            TranscriptSegment(
                text='Hello from the captured words',
                speaker='SPEAKER_00',
                is_user=True,
                start=0.0,
                end=1.0,
            )
        ],
        client_processing=_make_projection() if projection else None,
        is_locked=is_locked,
    )


@pytest.fixture(scope='module')
def projection_sink_fns() -> dict[str, Any]:
    """Load denylist sinks outside each test's timed call phase.

    Must be set up before ``render_mod`` stubs ``database.users`` /
    ``database.folders``, so the real router and persist helpers bind to
    production modules.
    """
    from google.cloud import firestore as google_firestore

    # Another suite collected into this process can leave a module-scope stub
    # over these names, and then the real sink functions are unimportable here.
    # Evict any stub (a module with no __file__, or one whose file is not the
    # production source) so this fixture always binds the REAL sinks -- skipping
    # or tolerating a stub would silently drop the coverage this file exists for.
    for package in ('database', 'routers'):
        parent = sys.modules.get(package)
        if parent is None:
            continue
        paths = [os.path.realpath(entry) for entry in getattr(parent, '__path__', [])]
        if os.path.realpath(str(_BACKEND / package)) not in paths:
            # A stubbed parent package cannot resolve its real submodules.
            for stale in [name for name in sys.modules if name == package or name.startswith(package + '.')]:
                sys.modules.pop(stale, None)
    for name, relpath in (
        ('database.conversations', ('database', 'conversations.py')),
        ('routers.conversations', ('routers', 'conversations.py')),
    ):
        module = sys.modules.get(name)
        if module is None:
            continue
        module_file = getattr(module, '__file__', None)
        if not module_file or os.path.realpath(module_file) != os.path.realpath(str(_BACKEND.joinpath(*relpath))):
            sys.modules.pop(name, None)

    import database.conversations as conversations_db
    import routers.conversations as conversations_router
    from utils.conversations.projection_payload import strip_client_processing

    return {
        'strip': strip_client_processing,
        'invalidate': getattr(conversations_db, '_invalidate_client_processing'),
        'drop': getattr(conversations_router, '_drop_display_projection'),
        'delete_field': google_firestore.DELETE_FIELD,
    }


@pytest.fixture(scope='module')
def render_mod(projection_sink_fns: dict[str, Any]) -> Iterator[ModuleType]:
    del projection_sink_fns  # dependency: real sink imports must precede stubs
    folders = ModuleType('database.folders')
    setattr(folders, 'get_folders', MagicMock(return_value=[]))
    users = ModuleType('database.users')
    setattr(users, 'get_user_profile', MagicMock(return_value={'name': 'TestUser'}))
    setattr(users, 'get_people_by_ids', MagicMock(return_value=[]))
    fakes: dict[str, ModuleType | None] = {'database.folders': folders, 'database.users': users}
    with stub_modules(fakes):
        render = load_module_fresh(
            'utils.conversations.render',
            os.path.join(str(_BACKEND), 'utils', 'conversations', 'render.py'),
        )
        yield render


@pytest.fixture(scope='module')
def conversations_to_string(render_mod: ModuleType) -> Callable[..., str]:
    return getattr(render_mod, 'conversations_to_string')


@pytest.fixture(scope='module')
def dart_gen() -> ModuleType:
    from scripts import generate_dart_models

    return generate_dart_models


@pytest.fixture(scope='module')
def app_client_spec() -> dict[str, Any]:
    spec_path = _BACKEND.parent / 'docs' / 'api-reference' / 'app-client-openapi.json'
    loaded = json.loads(spec_path.read_text(encoding='utf-8'))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope='module')
def conversation_dart(dart_gen: ModuleType, app_client_spec: dict[str, Any]) -> str:
    return dart_gen.build_output(app_client_spec, 'conversation')


@contextmanager
def _dart_schema_group(dart_gen: ModuleType, group: str, schemas: tuple[str, ...]) -> Iterator[None]:
    original = dart_gen.SCHEMA_GROUPS[group]
    dart_gen.SCHEMA_GROUPS[group] = {**original, 'schemas': schemas}
    try:
        yield
    finally:
        dart_gen.SCHEMA_GROUPS[group] = original


def test_scan_covers_required_plumbing() -> None:
    """The explicit list must include every surface the S4 brief named."""
    required = {
        'utils/conversations/process_conversation.py',
        'database/vector_db.py',
        'utils/llm/memories.py',
        'utils/conversations/render.py',
        'utils/apps.py',
        'utils/app_integrations.py',
        'utils/llm/external_integrations.py',
        'utils/memory/daily_memory_sweep.py',
        'utils/retrieval/rag.py',
        'utils/llm/goals.py',
        'database/goals.py',
        'database/action_items.py',
        'utils/webhooks.py',
    }
    listed = set(_SCAN_FILES)
    missing = required - listed
    assert not missing, f'scan list omitted required plumbing: {sorted(missing)}'


def test_projection_identifiers_only_in_allowed_scopes() -> None:
    """Trust boundary: a named projection read outside the allowlist fails."""
    leaked = sorted(hit for hit in _PRODUCTION_HITS if not _scope_allowed(hit))
    assert leaked == [], 'projection identifier leaked into intelligence plumbing:\n' + '\n'.join(
        f'  {hit.relpath} :: {hit.scope} :: {hit.identifier}' for hit in leaked
    )


def test_pinned_reference_set_is_exact() -> None:
    """A new reference anywhere (even in an allowed file/scope) fails until reviewed."""
    new = sorted(_PRODUCTION_HITS - PINNED_REFERENCES)
    gone = sorted(PINNED_REFERENCES - _PRODUCTION_HITS)
    assert _PRODUCTION_HITS == PINNED_REFERENCES, (
        'client_processing reference set changed; review each hit against the '
        'display-only trust boundary before updating PINNED_REFERENCES.\n'
        f'new: {new}\n'
        f'gone: {gone}'
    )


def test_pinned_conversation_dump_set_is_exact() -> None:
    """A new ``.model_dump()`` / ``.dict()`` in a scanned file fails until reviewed."""
    new = sorted(_PRODUCTION_DUMPS - PINNED_CONVERSATION_DUMPS)
    gone = sorted(PINNED_CONVERSATION_DUMPS - _PRODUCTION_DUMPS)
    assert _PRODUCTION_DUMPS == PINNED_CONVERSATION_DUMPS, (
        'serialization site set changed; review each dump against the '
        'display-only trust boundary before updating PINNED_CONVERSATION_DUMPS. '
        'A storage dump that should carry the projection is fine once pinned. '
        'An unreviewed dump in an intelligence path is the leak this test exists to catch.\n'
        f'new: {new}\n'
        f'gone: {gone}'
    )


def test_conversation_field_set_is_pinned(render_mod: ModuleType) -> None:
    """A new Conversation field cannot ship until it is classified.

    The integration payload is a full dump plus a denylist, not an allowlist.
    Classification is ``render.PROJECTION_FAMILY_FIELDS`` (the redactor
    iterates it). Adding a projection-family sibling without that
    classification used to leak into every denylist sink until this pin
    failed; classifying it without the sinks actually clearing it now fails
    the generated sink test instead of the pin.
    """
    family: FrozenSet[str] = getattr(render_mod, 'PROJECTION_FAMILY_FIELDS')
    current = frozenset(Conversation.model_fields)
    new = sorted(current - PINNED_CONVERSATION_FIELDS)
    gone = sorted(PINNED_CONVERSATION_FIELDS - current)
    assert family <= PINNED_CONVERSATION_FIELDS
    assert family <= current
    assert current == PINNED_CONVERSATION_FIELDS, (
        f'Conversation gained field(s) {new} (removed {gone}). Decide whether '
        'each new field is projection-family — an untrusted client-authored '
        'display sibling of client_processing. If it is, add it to '
        'utils.conversations.render.PROJECTION_FAMILY_FIELDS so the integration '
        'redactor strips it, then the generated sink test must pass against: '
        + '; '.join(sink.name for sink in PROJECTION_SINKS)
        + '. Then add the field to PINNED_CONVERSATION_FIELDS.'
    )


def test_conversation_tools_has_no_full_conversation_dump() -> None:
    """The citation collector must not serialize a whole Conversation."""
    tools_dumps = {site for site in _PRODUCTION_DUMPS if site.relpath.endswith('conversation_tools.py')}
    assert tools_dumps == set()


def test_red_proof_render_client_processing_read_fails_static_scan() -> None:
    """Mutation: add a fake ``conversation.client_processing`` read into RAG-format logic.

    The static assertion must fail on that scratch copy (proving the scanner sees
    the attribute). Production render.py names the identifier NOWHERE: the
    redactor iterates ``PROJECTION_FAMILY_FIELDS``, which is imported from
    ``models.client_processing`` so every sink strips a newly classified sibling
    without a code change. An empty production hit set is therefore the
    expected state, and any hit here is a new hardcoded read to review.
    """
    render_path = _BACKEND / 'utils' / 'conversations' / 'render.py'
    source = render_path.read_text(encoding='utf-8')
    needle = 'conversation_str += f"{str(conversation.structured.title).capitalize()}\\n"'
    assert needle in source, 'render.py title-format site moved; update this red-proof needle'
    poisoned = source.replace(
        needle,
        'conversation_str += f"{str(conversation.client_processing.structure.title)}\\n"',
        1,
    )
    assert 'client_processing' in poisoned
    hits = collect_references('utils/conversations/render.py', poisoned)
    assert Reference('utils/conversations/render.py', 'conversations_to_string', 'client_processing') in hits
    production_render = {hit for hit in _PRODUCTION_HITS if hit.relpath.endswith('render.py')}
    assert production_render == set()


def test_red_proof_full_conversation_dump_fails_dump_scan() -> None:
    """Mutation: add ``conv.model_dump()`` without ``include=`` in the citation collector.

    The dump scan must flag that site. Production conversation_tools uses the
    allowlisted helper and must not appear in PINNED_CONVERSATION_DUMPS.
    """
    tools_path = _BACKEND / 'utils' / 'retrieval' / 'tools' / 'conversation_tools.py'
    source = tools_path.read_text(encoding='utf-8')
    needle = 'conversations_collected.append(conversation_to_citation_card(conv))'
    assert needle in source, 'citation collector site moved; update this red-proof needle'
    poisoned = source.replace(needle, 'conversations_collected.append(conv.model_dump())', 1)
    dumps = collect_conversation_dumps('utils/retrieval/tools/conversation_tools.py', poisoned)
    assert DumpSite('utils/retrieval/tools/conversation_tools.py', 'get_conversations_tool', 'model_dump') in dumps
    assert all(site.relpath != 'utils/retrieval/tools/conversation_tools.py' for site in _PRODUCTION_DUMPS)


def test_red_proof_aliased_receiver_dump_fails_dump_scan() -> None:
    """Mutation: ``payload = conv; payload.model_dump()`` in the citation collector.

    Receiver names are not a filter. This dump must be a site, and production
    conversation_tools must still have none.
    """
    tools_path = _BACKEND / 'utils' / 'retrieval' / 'tools' / 'conversation_tools.py'
    source = tools_path.read_text(encoding='utf-8')
    needle = 'conversations_collected.append(conversation_to_citation_card(conv))'
    assert needle in source, 'citation collector site moved; update this red-proof needle'
    poisoned = source.replace(
        needle,
        'payload = conv; conversations_collected.append(payload.model_dump())',
        1,
    )
    dumps = collect_conversation_dumps('utils/retrieval/tools/conversation_tools.py', poisoned)
    assert DumpSite('utils/retrieval/tools/conversation_tools.py', 'get_conversations_tool', 'model_dump') in dumps
    assert all(site.relpath != 'utils/retrieval/tools/conversation_tools.py' for site in _PRODUCTION_DUMPS)


def test_red_proof_include_none_dump_fails_dump_scan() -> None:
    """Mutation: ``conv.model_dump(include=None)`` is a full dump, not an allowlist."""
    tools_path = _BACKEND / 'utils' / 'retrieval' / 'tools' / 'conversation_tools.py'
    source = tools_path.read_text(encoding='utf-8')
    needle = 'conversations_collected.append(conversation_to_citation_card(conv))'
    assert needle in source, 'citation collector site moved; update this red-proof needle'
    poisoned = source.replace(needle, 'conversations_collected.append(conv.model_dump(include=None))', 1)
    dumps = collect_conversation_dumps('utils/retrieval/tools/conversation_tools.py', poisoned)
    assert DumpSite('utils/retrieval/tools/conversation_tools.py', 'get_conversations_tool', 'model_dump') in dumps
    scratch = 'def f(conv):\n    return conv.model_dump(include=None)\n'
    assert collect_conversation_dumps('scratch.py', scratch) == frozenset({DumpSite('scratch.py', 'f', 'model_dump')})


def test_red_proof_dynamic_include_dump_fails_dump_scan() -> None:
    """Mutation: ``conv.model_dump(include=fields)`` cannot be verified statically."""
    tools_path = _BACKEND / 'utils' / 'retrieval' / 'tools' / 'conversation_tools.py'
    source = tools_path.read_text(encoding='utf-8')
    needle = 'conversations_collected.append(conversation_to_citation_card(conv))'
    assert needle in source, 'citation collector site moved; update this red-proof needle'
    poisoned = source.replace(needle, 'conversations_collected.append(conv.model_dump(include=fields))', 1)
    dumps = collect_conversation_dumps('utils/retrieval/tools/conversation_tools.py', poisoned)
    assert DumpSite('utils/retrieval/tools/conversation_tools.py', 'get_conversations_tool', 'model_dump') in dumps
    scratch = 'def f(conv, fields):\n    return conv.model_dump(include=fields)\n'
    assert collect_conversation_dumps('scratch.py', scratch) == frozenset({DumpSite('scratch.py', 'f', 'model_dump')})


def test_red_proof_allowlisted_dump_is_invisible_to_dump_scan() -> None:
    """Mutation contrast: a statically-verifiable ``include=`` literal is not a full dump."""
    source = 'def f(conv):\n    return conv.model_dump(include={"id", "structured"})\n'
    assert collect_conversation_dumps('scratch.py', source) == frozenset()
    aliased = 'def f(payload):\n    return payload.model_dump(include=["id", "structured"])\n'
    assert collect_conversation_dumps('scratch.py', aliased) == frozenset()
    full = 'def f(conv):\n    return conv.model_dump()\n'
    assert collect_conversation_dumps('scratch.py', full) == frozenset({DumpSite('scratch.py', 'f', 'model_dump')})


def test_red_proof_new_conversation_field_fails_until_classified() -> None:
    """Mutation: add ``projected_summary`` to the live field set → pin comparison fails."""
    mutated = frozenset(Conversation.model_fields) | {'projected_summary'}
    new = sorted(mutated - PINNED_CONVERSATION_FIELDS)
    assert new == ['projected_summary']
    assert mutated != PINNED_CONVERSATION_FIELDS


def test_integration_redactor_consults_projection_family_fields() -> None:
    """The redactor must iterate the production set, not hardcode a name.

    red-proof: replace the loop with ``conv.pop('client_processing', None)``
    and this fails because the function no longer names PROJECTION_FAMILY_FIELDS.
    """
    source = (_BACKEND / 'utils' / 'conversations' / 'render.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    fn: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'redact_conversation_for_integration':
            fn = node
            break
    assert fn is not None, 'redact_conversation_for_integration not at module body'
    names = {child.id for child in ast.walk(fn) if isinstance(child, ast.Name)}
    assert 'PROJECTION_FAMILY_FIELDS' in names


def test_every_projection_family_field_is_stripped_by_every_sink(
    render_mod: ModuleType,
    projection_sink_fns: dict[str, Any],
) -> None:
    """Every classified field against every sink, generated from the metadata.

    Hand-listing ``client_processing`` here would re-create the pin-only hole:
    adding ``client_processing_v2`` to the model plus both sets would stay
    green while persist-strip / invalidate / drop still only touch the old
    name. Cases are generated from ``render.PROJECTION_FAMILY_FIELDS``.

    red-proof: add ``client_processing_v2`` to Conversation,
    PINNED_CONVERSATION_FIELDS, and PROJECTION_FAMILY_FIELDS, change nothing
    else. This test fails on the sinks that still hardcode the old name.
    """
    family: FrozenSet[str] = getattr(render_mod, 'PROJECTION_FAMILY_FIELDS')
    assert family, 'PROJECTION_FAMILY_FIELDS must not be empty'
    assert family <= frozenset(Conversation.model_fields)
    failures: list[str] = []
    delete_field = projection_sink_fns['delete_field']
    for field in sorted(family):
        for sink in PROJECTION_SINKS:
            if sink.outcome == 'attr_none':
                conv = _make_conversation(projection=True)
                if field != 'client_processing':
                    setattr(conv, field, SENTINEL)
                projection_sink_fns[sink.fixture_key](conv)
                if getattr(conv, field, SENTINEL) is not None:
                    failures.append(f'{sink.name} left {field!r} on the Conversation')
                continue
            payload = render_mod.conversation_to_dict(_make_conversation(projection=True, is_locked=False))
            payload[field] = SENTINEL
            if sink.fixture_key == 'redact':
                result = render_mod.redact_conversation_for_integration(payload)
            else:
                projection_sink_fns[sink.fixture_key](payload)
                result = payload
            if sink.outcome == 'key_absent':
                if field in result:
                    failures.append(f'{sink.name} left key {field!r} (value={result.get(field)!r})')
            elif sink.outcome == 'delete_field':
                if result.get(field) is not delete_field:
                    failures.append(f'{sink.name} did not DELETE_FIELD {field!r} (value={result.get(field)!r})')
            else:
                failures.append(f'unknown sink outcome {sink.outcome!r} for {sink.name}')
    assert not failures, 'classified projection-family field not cleared by a denylist sink:\n' + '\n'.join(
        f'  {item}' for item in failures
    )


def test_projection_sentinel_is_invisible_to_structured_transcript_and_render(
    conversations_to_string: Callable[..., str],
) -> None:
    """Existing readers of structured/transcript are projection-blind by construction."""
    conv = _make_conversation(projection=True)
    projection = conv.client_processing
    assert projection is not None
    assert SENTINEL in projection.structure.title
    assert SENTINEL in projection.structure.overview
    assert SENTINEL in projection.action_items[0].description

    structured_text = str(conv.structured)
    transcript_text = conv.get_transcript(include_timestamps=False)
    rendered = conversations_to_string([conv])
    rendered_with_transcript = conversations_to_string([conv], use_transcript=True)

    assert SENTINEL not in structured_text
    assert SENTINEL not in transcript_text
    assert SENTINEL not in rendered
    assert SENTINEL not in rendered_with_transcript


def test_red_proof_sentinel_in_structured_is_visible(conversations_to_string: Callable[..., str]) -> None:
    """Mutation: put the sentinel into structured → the dynamic assertion sees the text."""
    assert SENTINEL.capitalize() == SENTINEL
    conv = _make_conversation(projection=False, structured_overview=SENTINEL)
    assert SENTINEL in str(conv.structured)
    assert SENTINEL in conversations_to_string([conv])


def test_model_dump_copies_projection_and_integration_redaction_drops_it(render_mod: ModuleType) -> None:
    """``conversation_to_dict`` is a full dump; integration redaction must remove it.

    The AST identifier pin list cannot see this path. The sentinel in the dump
    is the proof that serialization copies the projection; its absence after
    redaction is the proof no webhook / app payload can leak it — locked or
    unlocked. Removal, not null: ``None`` would add a key the public contract
    never had.
    """
    conv = _make_conversation(projection=True, is_locked=True)
    dumped = render_mod.conversation_to_dict(conv)
    assert SENTINEL in str(dumped)
    assert dumped.get('client_processing') is not None

    payload = render_mod.redact_conversation_for_integration(dumped)
    assert 'client_processing' not in payload
    assert SENTINEL not in str(payload)
    assert payload['structured']['title'] == ''
    assert payload['structured']['overview'] == ''


def test_unlocked_integration_payload_drops_projection(render_mod: ModuleType) -> None:
    """Unlocked integrations must not receive the projection either.

    An app's returned message is stored back onto the conversation; an
    untrusted summary as automation input is the promotion step section 1.1
    forbids. Canonical title/overview stay; the projection does not.
    """
    conv = _make_conversation(projection=True, is_locked=False)
    payload = render_mod.redact_conversation_for_integration(render_mod.conversation_to_dict(conv))
    assert 'client_processing' not in payload
    assert SENTINEL not in str(payload)
    assert payload['structured']['title'] == 'Recording title'


def test_red_proof_unlocked_passthrough_would_leak_projection(render_mod: ModuleType) -> None:
    """Mutation: skip the projection strip (old unlocked passthrough) → sentinel is visible."""
    conv = _make_conversation(projection=True, is_locked=False)
    dumped = render_mod.conversation_to_dict(conv)
    dumped.pop('geolocation', None)
    assert dumped.get('client_processing') is not None
    assert SENTINEL in str(dumped)


def test_red_proof_null_assignment_keeps_the_projection_key(render_mod: ModuleType) -> None:
    """Mutation: assign ``None`` instead of ``pop`` → the key is present on every payload.

    That is the public-contract change the redactor must not make. Production
    removal is asserted by ``'client_processing' not in payload`` above.
    """
    dumped = render_mod.conversation_to_dict(_make_conversation(projection=True, is_locked=False))
    dumped['client_processing'] = None
    assert 'client_processing' in dumped
    assert dumped['client_processing'] is None
    payload = render_mod.redact_conversation_for_integration(
        render_mod.conversation_to_dict(_make_conversation(projection=True, is_locked=False))
    )
    assert 'client_processing' not in payload


def test_citation_card_helper_excludes_projection(render_mod: ModuleType) -> None:
    """Allowlisted citation shape cannot carry projection text."""
    conv = _make_conversation(projection=True)
    card = render_mod.conversation_to_citation_card(conv)
    assert 'client_processing' not in card
    assert set(card) == {'id', 'created_at', 'started_at', 'finished_at', 'structured'}
    assert SENTINEL not in str(card)
    assert card['structured']['title'] == 'Recording title'


def test_red_proof_denylist_dump_leaks_projection_into_citation_shape(render_mod: ModuleType) -> None:
    """Mutation: the old dump-then-pop denylist lets the sentinel through."""
    conv = _make_conversation(projection=True)
    leaked = conv.model_dump()
    leaked.pop('transcript_segments', None)
    leaked.pop('photos', None)
    leaked.pop('audio_files', None)
    assert SENTINEL in str(leaked)
    assert leaked.get('client_processing') is not None
    card = render_mod.conversation_to_citation_card(conv)
    assert SENTINEL not in str(card)


def _assert_cards_and_message_are_projection_free(cards: list[dict[str, Any]]) -> None:
    assert cards, 'collector produced no citation cards'
    blob = str(cards)
    assert SENTINEL not in blob
    assert all('client_processing' not in card for card in cards)
    memories = [MessageConversation(**card) for card in cards]
    msg = Message(
        id='msg-citation-sentinel',
        text='answer [1]',
        created_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        memories=memories,
    )
    serialized = msg.model_dump()
    assert SENTINEL not in str(serialized)
    assert 'client_processing' not in str(serialized)


def test_citation_collector_and_message_serializer_exclude_projection(render_mod: ModuleType) -> None:
    """Drive the collector body and the Message serializer: projection text cannot appear.

    Both tool sites append ``conversation_to_citation_card(conv)``. This test
    runs that loop on a deserialized Conversation (the same conversion the
    tools perform) and then the voice/text ``Message.memories`` serializer.
    """
    tools_source = (_BACKEND / 'utils' / 'retrieval' / 'tools' / 'conversation_tools.py').read_text(encoding='utf-8')
    helper_call = 'conversations_collected.append(conversation_to_citation_card(conv))'
    assert tools_source.count(helper_call) == 2
    assert 'conv.model_dump()' not in tools_source

    conv = _make_conversation(projection=True)
    conv_data = conv.model_dump()
    assert SENTINEL in str(conv_data.get('client_processing'))
    conversations = [deserialize_conversation(conv_data)]
    conversations_collected: list[dict[str, Any]] = []
    for item in conversations:
        conversations_collected.append(render_mod.conversation_to_citation_card(item))
    _assert_cards_and_message_are_projection_free(conversations_collected)


def _divergent_output_spec() -> dict[str, Any]:
    return {
        'components': {
            'schemas': {
                'Widget': {
                    'type': 'object',
                    'properties': {'name': {'type': 'string'}},
                    'required': ['name'],
                },
                'Widget-Output': {
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string'},
                        'extra': {'type': 'integer'},
                    },
                    'required': ['name', 'extra'],
                },
                'Holder': {
                    'type': 'object',
                    'properties': {'widget': {'$ref': '#/components/schemas/Widget-Output'}},
                    'required': ['widget'],
                },
            }
        }
    }


def _matching_output_spec() -> dict[str, Any]:
    widget = {
        'type': 'object',
        'title': 'Widget',
        'properties': {'name': {'type': 'string', 'title': 'Name'}},
        'required': ['name'],
    }
    widget_output = {
        'type': 'object',
        'title': 'WidgetOutput',
        'description': 'serializer sibling',
        'properties': {'name': {'type': 'string', 'title': 'Name'}},
        'required': ['name'],
    }
    return {
        'components': {
            'schemas': {
                'Widget': widget,
                'Widget-Output': widget_output,
                'Holder': {
                    'type': 'object',
                    'properties': {'widget': {'$ref': '#/components/schemas/Widget-Output'}},
                    'required': ['widget'],
                },
            }
        }
    }


def test_dart_generator_fails_when_output_schema_diverges(dart_gen: ModuleType) -> None:
    """A serializer-specific -Output with extra required fields must not alias silently."""
    with _dart_schema_group(dart_gen, 'messages', ('Widget', 'Holder')):
        with pytest.raises(ValueError, match='Widget-Output'):
            dart_gen.build_output(_divergent_output_spec(), 'messages')


def test_dart_generator_aliases_output_schema_when_structurally_equal(dart_gen: ModuleType) -> None:
    """Identical -Output refs still generate against the input class."""
    with _dart_schema_group(dart_gen, 'messages', ('Widget', 'Holder')):
        generated = dart_gen.build_output(_matching_output_spec(), 'messages')
    assert 'class GeneratedWidget {' in generated
    assert 'GeneratedWidgetOutput' not in generated
    assert 'widget: _required(_readFieldValue<GeneratedWidget>' in generated


def test_dart_generator_still_emits_real_conversation_client_processing(
    dart_gen: ModuleType,
    app_client_spec: dict[str, Any],
    conversation_dart: str,
) -> None:
    """The production projection generates one Dart class, whatever pydantic emits.

    Whether the spec carries a serializer-specific ``ClientProcessing-Output``
    sibling is pydantic's business, not an invariant: once every projection
    datetime became a timezone-aware string, input and output serialization
    coincided and the sibling stopped being emitted. Pin the guarantee that
    actually matters — the client decodes ONE shape — and assert the alias
    contract only when the spec really does carry the pair. The fixture tests
    above own the divergence-refusal behaviour.
    """
    schemas = app_client_spec['components']['schemas']
    assert 'ClientProcessing' in schemas
    if 'ClientProcessing-Output' in schemas:
        assert dart_gen.schemas_structurally_equal(schemas['ClientProcessing'], schemas['ClientProcessing-Output'])
        aliased = dart_gen.resolve_output_ref_alias(
            'ClientProcessing-Output',
            dart_gen.SCHEMA_GROUPS['conversation']['schemas'],
            schemas,
        )
        assert aliased == 'ClientProcessing'
    assert 'class GeneratedClientProcessing' in conversation_dart
    assert 'GeneratedClientProcessingOutput' not in conversation_dart
    assert 'clientProcessing: _readFieldValue<GeneratedClientProcessing>' in conversation_dart


# Any call site that opts out of transcript-mutation invalidation must be listed
# here with a reviewed reason. Live capture appends to an in-progress conversation
# that cannot yet hold a projection; everything else must invalidate.
PINNED_INVALIDATION_OPT_OUTS: FrozenSet[tuple[str, str]] = frozenset(
    {
        ('routers/listen/transcripts.py', 'update_conversation_segments'),
    }
)

_SEGMENT_MUTATION_FILES: tuple[str, ...] = (
    'routers/conversations.py',
    'routers/listen/transcripts.py',
    'utils/sync/pipeline.py',
    'utils/conversations/process_conversation.py',
)


def _invalidation_call_name(node: ast.Call) -> str:
    """Name the function whose invalidation is being opted out of.

    Live capture dispatches through a wrapper -- ``persistence.call(db_fn, ...)``
    -- so the call node's own name is the wrapper's. When a positional argument
    is itself a reference to a segment-mutation function, that is the real
    callee and the name worth pinning.
    """
    target = node.func
    direct = target.attr if isinstance(target, ast.Attribute) else getattr(target, 'id', '')
    if 'segment' in direct:
        return direct
    for argument in node.args:
        referenced = ''
        if isinstance(argument, ast.Attribute):
            referenced = argument.attr
        elif isinstance(argument, ast.Name):
            referenced = argument.id
        if referenced.startswith('update_conversation_segment'):
            return referenced
    return direct or '<dynamic>'


def test_transcript_mutation_invalidation_cannot_be_opted_out_silently() -> None:
    """A projection must not outlive the transcript it was hash-bound to.

    ``update_conversation_segments`` defaults to invalidating, so a new call
    site is safe by default. This pins the inverse: an explicit
    ``invalidate_client_processing=False`` anywhere outside the reviewed
    allowlist fails, because that is how a stale projection would start
    rendering against text it no longer describes.

    red-proof: add ``invalidate_client_processing=False`` to the sync pipeline's
    ``update_conversation_segments`` call and this test fails naming it.
    """
    found: set[tuple[str, str]] = set()
    for relpath in _SEGMENT_MUTATION_FILES:
        path = _BACKEND / relpath
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != 'invalidate_client_processing':
                    continue
                value = keyword.value
                if isinstance(value, ast.Constant) and value.value is False:
                    found.add((relpath, _invalidation_call_name(node)))
    assert found == PINNED_INVALIDATION_OPT_OUTS, (
        'transcript-mutation invalidation opt-outs changed; a projection that outlives its '
        'transcript renders a summary of text that no longer exists. Review each site before '
        f'pinning it.\nnew: {sorted(found - PINNED_INVALIDATION_OPT_OUTS)}\n'
        f'gone: {sorted(PINNED_INVALIDATION_OPT_OUTS - found)}'
    )


def test_update_conversation_segments_defaults_to_invalidating() -> None:
    """The default is the guarantee; opt-in would leave every call site buggy.

    Read from source rather than importing ``database.conversations``: this
    module is deliberately import-free and AST-based, and importing a database
    module here breaks when another suite in the same process has stubbed it.

    red-proof: flip the default back to False and this fails.
    """
    source = (_BACKEND / 'database' / 'conversations.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'update_conversation_segments':
            names = [argument.arg for argument in node.args.kwonlyargs]
            index = names.index('invalidate_client_processing')
            default = node.args.kw_defaults[index]
            assert isinstance(default, ast.Constant) and default.value is True, (
                'update_conversation_segments must invalidate by default: its job is replacing '
                'the transcript a projection was hash-bound to, and an opt-in default leaves '
                'every existing and future call site silently keeping a stale projection.'
            )
            return
    raise AssertionError('update_conversation_segments not found in database/conversations.py')


# Durable-intent returns that skip snapshot-bound projection write. Empty by
# construction: every return lives inside the try whose finally is the choke
# point. A return with no conversation snapshot still belongs in that try
# (the helper no-ops when conversation is None). Pinning a new signature
# means reviewing why a 200 may discard a valid later projection.
PINNED_UNBOUND_INTENT_RETURNS: FrozenSet[str] = frozenset()

_INTENT_TXN_NAME = '_create_or_get_finalization_intent_txn'
_INTENT_CHOKE_POINT = '_apply_snapshot_bound_projection'
_INTENT_TXN_RELPATH = 'database/conversation_finalization_jobs.py'
_PROTECTED_INTENT_TXN_NAMES = frozenset({'transaction', 'conversation_ref'})
_FIRESTORE_WRITE_PRIMITIVES = frozenset({'update', 'set', 'create', 'delete'})

# Callees in ``_create_or_get_finalization_intent_txn`` that receive
# ``transaction`` or ``conversation_ref`` (as a method receiver, positional
# argument, or keyword). Measured from the function body. A new callee is a
# write surface this function cannot see: review whether it writes the
# conversation, and whether it binds first.
PINNED_INTENT_TXN_CALLEES: FrozenSet[str] = frozenset(
    {
        'conversation_ref.get',
        '_conversation_has_finalization_content',
        'existing_ref.get',
        'job_ref.get',
        'transaction.set',
        '_record_projection_delta',
        '_apply_snapshot_bound_projection',
    }
)


def _is_call_to(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == name
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return False


def _try_finally_calls(try_node: ast.Try, name: str) -> bool:
    return any(_is_call_to(child, name) for stmt in try_node.finalbody for child in ast.walk(stmt))


def _node_is_name(node: ast.AST, name: str) -> bool:
    if isinstance(node, ast.Name):
        return node.id == name
    if isinstance(node, ast.Starred):
        return _node_is_name(node.value, name)
    return False


def _iter_direct_name_ids(node: ast.AST | None) -> Iterator[str]:
    """Names bound or aliased directly, not names used inside a Call."""
    if node is None:
        return
    if isinstance(node, ast.Name):
        yield node.id
        return
    if isinstance(node, ast.Starred):
        yield from _iter_direct_name_ids(node.value)
        return
    if isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            yield from _iter_direct_name_ids(elt)


def _call_passes_name(call: ast.Call, name: str) -> bool:
    """True when ``name`` is a positional, keyword, or starred argument of ``call``."""
    for arg in call.args:
        if _node_is_name(arg, name):
            return True
    for keyword in call.keywords:
        if _node_is_name(keyword.value, name):
            return True
    return False


def _call_receiver_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id
    return ''


def _call_callee_id(call: ast.Call) -> str:
    """Stable id for a Call: ``receiver.attr`` or a bare name, else ``<dynamic>``."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return f'{func.value.id}.{func.attr}'
        return f'<dynamic>.{func.attr}'
    return '<dynamic>'


def _call_hands_protected_name(call: ast.Call) -> bool:
    """True when the call receives ``transaction`` or ``conversation_ref``.

    Receivers count: ``transaction.set(job_ref, job)`` does not pass
    ``transaction`` as an argument, but it is still a callee that can write.
    """
    if _call_receiver_name(call) in _PROTECTED_INTENT_TXN_NAMES:
        return True
    return any(_call_passes_name(call, name) for name in _PROTECTED_INTENT_TXN_NAMES)


def _function_unpacked_call_arguments(fn: ast.FunctionDef) -> list[str]:
    """Calls in ``fn`` whose argument list cannot be read statically.

    ``transaction.set(*(conversation_ref, payload), merge=True)`` hands the
    conversation ref to an already-pinned callee inside a starred container.
    Every scanner here reads argument expressions by name, so an unpacked
    argument list is opaque to all of them at once: the write is invisible,
    the callee stays pinned, and the return stays covered. Ban the
    construct rather than try to evaluate it.
    """
    found: list[str] = []

    def visit(node: ast.AST) -> None:
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Call):
            unpacked = any(isinstance(arg, ast.Starred) for arg in node.args) or any(
                keyword.arg is None for keyword in node.keywords
            )
            if unpacked:
                found.append(f'{_call_callee_id(node)}:{node.lineno}')
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(fn)
    return found


def _function_nested_definitions(fn: ast.FunctionDef) -> list[str]:
    """Nested def/class inside ``fn``. The scanners stop at these.

    A nested helper is an unreadable write surface: ``return _helper()`` is a
    covered return, ``has_choke`` stays True and ``direct_updates`` stays
    empty, while the helper writes raw ``client_processing``. A module-scope
    helper is the same hole: the callee pin is what closes it.
    """
    found: list[str] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.append(f'{child.name}:{child.lineno}')
                continue
            visit(child)

    visit(fn)
    return found


def _function_transaction_rebinds(fn: ast.FunctionDef) -> list[str]:
    """Sites that rebind ``transaction`` / ``conversation_ref`` or alias them.

    Write scans match those literal names as receiver or argument. An alias
    (``txn = transaction`` / ``ref = conversation_ref``) or a rebind moves
    a conversation write out of their reach and past the bind.

    An assignment expression is the same escape inside a single expression:
    ``(txn := transaction).set((ref := conversation_ref), payload, merge=True)``
    binds and writes at once, so there is no statement for the target/value
    scan to see. Any ``:=`` mentioning either name is rejected outright rather
    than analysed.
    """
    found: list[str] = []

    def targets(node: ast.AST) -> list[ast.expr]:
        if isinstance(node, ast.Assign):
            return list(node.targets)
        if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor)):
            return [node.target]
        if isinstance(node, (ast.With, ast.AsyncWith)):
            return [item.optional_vars for item in node.items if item.optional_vars is not None]
        return []

    for node in ast.walk(fn):
        if isinstance(node, ast.NamedExpr):
            for name in ast.walk(node):
                if isinstance(name, ast.Name) and name.id in _PROTECTED_INTENT_TXN_NAMES:
                    found.append(f'walrus:{name.id}:{node.lineno}')
        for target in targets(node):
            for name in ast.walk(target):
                if isinstance(name, ast.Name) and name.id in _PROTECTED_INTENT_TXN_NAMES:
                    found.append(f'rebind:{name.id}:{name.lineno}')
        if targets(node):
            value = getattr(node, 'value', None)
            lineno = getattr(node, 'lineno', 0)
            for bound in _iter_direct_name_ids(value):
                if bound in _PROTECTED_INTENT_TXN_NAMES:
                    found.append(f'alias:{bound}:{lineno}')
    return sorted(set(found))


def _function_direct_transaction_updates(fn: ast.FunctionDef) -> list[str]:
    """Conversation-write sites in ``fn``, excluding nested defs.

    ``transaction.update`` is always a hit, any target: that is the original
    scanner. ``set`` / ``create`` / ``delete`` (and ``update`` on a document
    reference) are hits when they target ``conversation_ref`` — as
    ``transaction.<op>(conversation_ref, ...)``, as
    ``conversation_ref.<op>(...)``, or as any other receiver that is passed
    ``conversation_ref``. ``transaction.set(job_ref, job)`` is not a
    conversation write.
    """
    sites: list[str] = []

    def visit(node: ast.AST) -> None:
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _FIRESTORE_WRITE_PRIMITIVES:
                receiver = _call_receiver_name(node)
                targets_conversation = _call_passes_name(node, 'conversation_ref') or receiver == 'conversation_ref'
                any_transaction_update = receiver == 'transaction' and func.attr == 'update'
                if any_transaction_update or targets_conversation:
                    sites.append(f'{_call_callee_id(node)}:{node.lineno}')
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(fn)
    return sites


def _function_intent_txn_callees(fn: ast.FunctionDef) -> FrozenSet[str]:
    """Callees that receive ``transaction`` or ``conversation_ref`` in ``fn``."""
    found: set[str] = set()

    def visit(node: ast.AST) -> None:
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Call) and _call_hands_protected_name(node):
            found.add(_call_callee_id(node))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(fn)
    return frozenset(found)


class IntentTxnReturn(NamedTuple):
    signature: str
    lineno: int
    covered: bool


def collect_intent_txn_returns(source: str) -> tuple[list[IntentTxnReturn], bool, list[str]]:
    """Enumerate returns of the durable-intent transaction.

    A return is covered when it sits in the ``try`` whose ``finally`` calls
    ``_apply_snapshot_bound_projection``. Returns in that ``finally``, or
    anywhere else in the function, are uncovered.
    """
    tree = ast.parse(source)
    fn: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == _INTENT_TXN_NAME:
            fn = node
            break
    if fn is None:
        raise AssertionError(f'{_INTENT_TXN_NAME} not found at module body')

    choke_tries: list[ast.Try] = []

    def find_choke_tries(node: ast.AST) -> None:
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Try) and _try_finally_calls(node, _INTENT_CHOKE_POINT):
            choke_tries.append(node)
        for child in ast.iter_child_nodes(node):
            find_choke_tries(child)

    find_choke_tries(fn)
    choke_try_ids = {id(node) for node in choke_tries}

    found: list[IntentTxnReturn] = []
    try_stack: list[ast.Try] = []

    def in_choke_try_body() -> bool:
        for try_node in reversed(try_stack):
            if id(try_node) in choke_try_ids:
                return True
        return False

    def visit(node: ast.AST, *, in_choke_finally: bool = False) -> None:
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Return):
            found.append(
                IntentTxnReturn(
                    ast.unparse(node).strip(),
                    node.lineno,
                    covered=in_choke_try_body() and not in_choke_finally,
                )
            )
            return
        if isinstance(node, ast.Try):
            try_stack.append(node)
            is_choke = id(node) in choke_try_ids
            for child in node.body:
                visit(child, in_choke_finally=in_choke_finally)
            for handler in node.handlers:
                # A return from the choke try's own handler runs while the
                # frame is failing, so the finally's ``not raised`` guard
                # skips the bind. Uncovered on purpose.
                visit(handler, in_choke_finally=in_choke_finally or is_choke)
            for child in node.orelse:
                visit(child, in_choke_finally=in_choke_finally)
            for child in node.finalbody:
                visit(child, in_choke_finally=in_choke_finally or is_choke)
            try_stack.pop()
            return
        for child in ast.iter_child_nodes(node):
            visit(child, in_choke_finally=in_choke_finally)

    visit(fn)
    return found, bool(choke_tries), _function_direct_transaction_updates(fn)


def collect_intent_txn_write_surface(source: str) -> tuple[list[str], list[str], list[str]]:
    """Nested definitions, protected-name rebinds/aliases, and unpacked call arguments."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == _INTENT_TXN_NAME:
            return (
                _function_nested_definitions(node),
                _function_transaction_rebinds(node),
                _function_unpacked_call_arguments(node),
            )
    raise AssertionError(f'{_INTENT_TXN_NAME} not found at module body')


def collect_intent_txn_callees(source: str) -> FrozenSet[str]:
    """Callees that receive ``transaction`` or ``conversation_ref`` in the intent txn."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == _INTENT_TXN_NAME:
            return _function_intent_txn_callees(node)
    raise AssertionError(f'{_INTENT_TXN_NAME} not found at module body')


_INTENT_TXN_COVERAGE_MESSAGE = (
    'A return from _create_or_get_finalization_intent_txn is not covered by the '
    'snapshot-bound projection write. Returning 200 while silently discarding a '
    'valid later projection is the defect this test exists to prevent (1.7c). '
    'Put the return inside the try so finally calls _apply_snapshot_bound_projection, '
    'which binds projection fields and nothing else. Do not add a conversation write '
    'at the exit. If this exit truly has no conversation snapshot to bind to, it still '
    'belongs in that try (the helper no-ops when conversation is None). Pinning a '
    'signature in PINNED_UNBOUND_INTENT_RETURNS is only for a reviewed exception, '
    'and the next author must explain why a drop on 200 is acceptable.'
)


def test_intent_txn_returns_are_covered_by_projection_choke_point() -> None:
    """A new exit from the durable intent txn cannot skip binding.

    Four review rounds bound create, then two existing-job returns, then
    terminal, then the reviewer named already_finalizing / no_content /
    deferred. Per-exit binding is the bug. The choke point is a finally
    that calls _apply_snapshot_bound_projection; a new return inside the
    try is covered automatically.

    red-proof: add ``return _no_finalization_intent('scratch')`` before the
    try, or remove the finally call, and this fails naming the return.
    ``transaction.set(conversation_ref, extra_updates, merge=True)`` is a
    conversation write the update-only scanner missed. A module-scope
    helper that receives ``transaction`` or ``conversation_ref`` is the
    other miss — the nested-def assertion used to tell authors to move it
    there.
    """
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    returns, has_choke, direct_updates = collect_intent_txn_returns(source)
    assert has_choke, (
        '_create_or_get_finalization_intent_txn must bind projections in a finally '
        'that calls _apply_snapshot_bound_projection. That is the choke point: a new '
        'return inside the try is then covered automatically. Restoring per-exit '
        'binding is how later-projection drops survived four review rounds.'
    )
    assert not direct_updates, (
        f'{_INTENT_TXN_NAME} must not write the conversation itself; conversation '
        f'writes go through {_INTENT_CHOKE_POINT}. Direct writes at {direct_updates} '
        'are a second path that can persist an unbound projection on 200. The scanner '
        'matches every Firestore write primitive (update, set, create, delete) '
        'targeting conversation_ref, on either receiver: '
        'transaction.<op>(conversation_ref, ...) or conversation_ref.<op>(...). '
        'transaction.update is banned for any target. A job write '
        'transaction.set(job_ref, ...) is not a conversation write. Move a conversation '
        f'write into {_INTENT_CHOKE_POINT} so it is snapshot-bound, or drop the payload.'
    )
    nested, rebinds, unpacked = collect_intent_txn_write_surface(source)
    assert not nested, (
        f'{_INTENT_TXN_NAME} must not define nested functions or classes ({nested}). '
        'The return scanner and the write scanners both stop at a nested def, so a '
        'helper defined here is an unreadable write surface: "return _helper()" is a '
        'covered return while _helper writes raw client_processing. Do not extract a '
        'helper that writes the conversation — not nested, and not at module scope. '
        f'Conversation writes belong only in {_INTENT_CHOKE_POINT}. A new callee that '
        'receives transaction or conversation_ref must be reviewed: does it write '
        'the conversation, and does it bind first?'
    )
    assert not rebinds, (
        f'{_INTENT_TXN_NAME} must not rebind or alias "transaction" or "conversation_ref" '
        f'({rebinds}). Write scans match those literal names as receiver or argument; '
        'an alias (txn = transaction, ref = conversation_ref) moves a conversation '
        'write out of their reach and past the bind. An assignment expression is the '
        'same escape with no statement to see — (txn := transaction).set(...) — so any '
        ':= mentioning either name is rejected here rather than analysed.'
    )
    callees = collect_intent_txn_callees(source)
    assert callees == PINNED_INTENT_TXN_CALLEES, (
        f'{_INTENT_TXN_NAME} may only hand transaction or conversation_ref to reviewed '
        'callees. A new callee that receives either name is a write surface this '
        'function cannot see: the helper can persist an unbound projection while the '
        'caller return stays covered. Review it: does it write the conversation, and '
        f'does it bind first? If it writes, the write belongs in {_INTENT_CHOKE_POINT}, '
        'not in a helper — nested or module-scope. If it only reads, add it to '
        'PINNED_INTENT_TXN_CALLEES after that review.\n'
        f'new: {sorted(callees - PINNED_INTENT_TXN_CALLEES)}\n'
        f'gone: {sorted(PINNED_INTENT_TXN_CALLEES - callees)}'
    )
    assert not unpacked, (
        f'{_INTENT_TXN_NAME} must not call anything with a starred or **-unpacked '
        f'argument list ({unpacked}). Every scanner in this test reads argument '
        'expressions by name, so an unpacked list hides them all at once: '
        'transaction.set(*(conversation_ref, payload), merge=True) is an unbound '
        'conversation write whose callee is already pinned and whose return stays '
        'covered. Write the arguments out.'
    )
    uncovered = frozenset(item.signature for item in returns if not item.covered)
    assert uncovered == PINNED_UNBOUND_INTENT_RETURNS, (
        _INTENT_TXN_COVERAGE_MESSAGE + f'\nnew: {sorted(uncovered - PINNED_UNBOUND_INTENT_RETURNS)}\n'
        f'gone: {sorted(PINNED_UNBOUND_INTENT_RETURNS - uncovered)}\n'
        f'all returns: {[(item.lineno, item.covered, item.signature) for item in returns]}'
    )
    assert returns, f'{_INTENT_TXN_NAME} has no return statements; the scanner missed the function'


def test_red_proof_return_outside_bind_try_fails_choke_point_scan() -> None:
    """Mutation: a new return before the try is uncovered and must fail the pin."""
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    needle = (
        'A new exit inside the ``try`` is therefore bound automatically; do not\n'
        '    add a conversation write, or a return, outside that ``try``.\n'
        '    """\n'
    )
    assert needle in source, 'intent txn docstring moved; update this red-proof needle'
    poisoned = source.replace(
        needle,
        needle + '    return _no_finalization_intent("scratch_unbound_exit")\n',
        1,
    )
    assert 'scratch_unbound_exit' in poisoned
    returns, has_choke, _direct = collect_intent_txn_returns(poisoned)
    assert has_choke
    uncovered = frozenset(item.signature for item in returns if not item.covered)
    assert any('scratch_unbound_exit' in signature for signature in uncovered)
    assert uncovered != PINNED_UNBOUND_INTENT_RETURNS


def test_red_proof_removing_finally_choke_point_uncovers_every_return() -> None:
    """Mutation: rename the finally helper so it is no longer the choke point."""
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    def_needle = f'def {_INTENT_CHOKE_POINT}('
    assert def_needle in source
    call_needle = f'        {_INTENT_CHOKE_POINT}('
    assert call_needle in source, 'finally call site moved; update this red-proof needle'
    poisoned = source.replace(call_needle, '        _not_the_projection_choke_point(', 1)
    returns, has_choke, _direct = collect_intent_txn_returns(poisoned)
    assert has_choke is False
    assert returns
    assert all(item.covered is False for item in returns)


_INTENT_TXN_SNAPSHOT_READ = '        conversation_snapshot = conversation_ref.get(transaction=transaction)\n'


def test_red_proof_transaction_set_on_conversation_ref_fails_write_scan() -> None:
    """Mutation: ``transaction.set(conversation_ref, extra_updates, merge=True)``.

    The update-only scanner stayed green. This is a conversation write of an
    unbound projection that still returns 200.
    """
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    poisoned = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        transaction.set(conversation_ref, extra_updates, merge=True)\n',
        1,
    )
    returns, has_choke, direct_writes = collect_intent_txn_returns(poisoned)
    assert has_choke
    assert all(item.covered for item in returns)
    assert any(site.startswith('transaction.set:') for site in direct_writes)
    nested, rebinds, _unpacked = collect_intent_txn_write_surface(poisoned)
    assert not nested
    assert not rebinds
    assert collect_intent_txn_callees(poisoned) == PINNED_INTENT_TXN_CALLEES


def test_red_proof_conversation_ref_write_receiver_fails_write_scan() -> None:
    """Mutation: ``conversation_ref.set(extra_updates, merge=True)``.

    The receiver is the document, not the transaction. Still a conversation write.
    """
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    poisoned = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        conversation_ref.set(extra_updates, merge=True)\n',
        1,
    )
    _returns, _has_choke, direct_writes = collect_intent_txn_returns(poisoned)
    assert any(site.startswith('conversation_ref.set:') for site in direct_writes)


def test_red_proof_transaction_create_and_delete_on_conversation_ref_fail_write_scan() -> None:
    """Mutation: ``transaction.create`` / ``transaction.delete`` targeting conversation_ref."""
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    created = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        transaction.create(conversation_ref, extra_updates)\n',
        1,
    )
    deleted = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        transaction.delete(conversation_ref)\n',
        1,
    )
    ref_deleted = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        conversation_ref.delete()\n',
        1,
    )
    _returns, _has_choke, create_writes = collect_intent_txn_returns(created)
    _returns, _has_choke, delete_writes = collect_intent_txn_returns(deleted)
    _returns, _has_choke, ref_delete_writes = collect_intent_txn_returns(ref_deleted)
    assert any(site.startswith('transaction.create:') for site in create_writes)
    assert any(site.startswith('transaction.delete:') for site in delete_writes)
    assert any(site.startswith('conversation_ref.delete:') for site in ref_delete_writes)
    production_writes = collect_intent_txn_returns(source)[2]
    assert production_writes == []


def test_red_proof_module_helper_receiving_transaction_fails_callee_pin() -> None:
    """Mutation: a module-scope helper receives transaction and conversation_ref.

    The nested-def assertion used to tell the author to move the helper to
    module scope. That advice is the escape: the caller's return is covered,
    nested/alias/direct-update inventories stay empty, and the helper writes
    the raw payload.
    """
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    helper_def = (
        'def _write_unbound_projection(transaction, conversation_ref, extra_updates):\n'
        '    transaction.set(conversation_ref, extra_updates, merge=True)\n'
        '\n'
        '\n'
    )
    def_needle = f'def {_INTENT_TXN_NAME}('
    assert def_needle in source
    poisoned = source.replace(def_needle, helper_def + def_needle, 1)
    poisoned = poisoned.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        _write_unbound_projection(transaction, conversation_ref, extra_updates)\n',
        1,
    )
    returns, has_choke, direct_writes = collect_intent_txn_returns(poisoned)
    assert has_choke
    assert all(item.covered for item in returns)
    assert direct_writes == []
    nested, rebinds, _unpacked = collect_intent_txn_write_surface(poisoned)
    assert not nested
    assert not rebinds
    callees = collect_intent_txn_callees(poisoned)
    assert '_write_unbound_projection' in callees
    assert callees != PINNED_INTENT_TXN_CALLEES


def test_red_proof_transaction_update_any_target_still_fails_write_scan() -> None:
    """Mutation: ``transaction.update(job_ref, extra_updates)`` is still a hit.

    The original scanner banned every ``transaction.update``, not only ones
    targeting conversation_ref. Do not narrow it.
    """
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    poisoned = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        transaction.update(job_ref, extra_updates)\n',
        1,
    )
    _returns, _has_choke, direct_writes = collect_intent_txn_returns(poisoned)
    assert any(site.startswith('transaction.update:') for site in direct_writes)


def test_red_proof_conversation_ref_alias_fails_rebind_scan() -> None:
    """Mutation: ``ref = conversation_ref`` then write through the alias."""
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    poisoned = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        ref = conversation_ref\n',
        1,
    )
    nested, rebinds, _unpacked = collect_intent_txn_write_surface(poisoned)
    assert not nested
    assert any(site.startswith('alias:conversation_ref:') for site in rebinds)


def test_red_proof_transaction_alias_fails_rebind_scan() -> None:
    """Mutation: ``txn = transaction`` hides later writes from the literal-name scan."""
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    poisoned = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ + '        txn = transaction\n',
        1,
    )
    nested, rebinds, _unpacked = collect_intent_txn_write_surface(poisoned)
    assert not nested
    assert any(site.startswith('alias:transaction:') for site in rebinds)


def test_red_proof_nested_helper_fails_nested_scan() -> None:
    """Mutation: a nested helper writes the conversation while the caller return stays covered."""
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    poisoned = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ
        + '        def _helper(transaction, conversation_ref, extra_updates):\n'
        + '            transaction.set(conversation_ref, extra_updates, merge=True)\n'
        + '        _helper(transaction, conversation_ref, extra_updates)\n',
        1,
    )
    returns, has_choke, direct_writes = collect_intent_txn_returns(poisoned)
    assert has_choke
    assert all(item.covered for item in returns)
    assert direct_writes == []
    nested, rebinds, _unpacked = collect_intent_txn_write_surface(poisoned)
    assert not rebinds
    assert any(site.startswith('_helper:') for site in nested)


def test_red_proof_walrus_alias_fails_rebind_scan() -> None:
    """Mutation: ``(txn := transaction).set((ref := conversation_ref), ...)``.

    An assignment expression binds and writes in one expression, so the
    statement-level target/value scan sees nothing: no rebind, no direct
    write, no unpacking, and the callee set is unchanged. The reviewer
    found this after every other spelling was closed.
    """
    source = (_BACKEND / _INTENT_TXN_RELPATH).read_text(encoding='utf-8')
    assert _INTENT_TXN_SNAPSHOT_READ in source, 'intent txn snapshot read moved; update this red-proof needle'
    poisoned = source.replace(
        _INTENT_TXN_SNAPSHOT_READ,
        _INTENT_TXN_SNAPSHOT_READ
        + '        (txn := transaction).set((ref := conversation_ref), extra_updates or {}, merge=True)\n',
        1,
    )
    nested, rebinds, _unpacked = collect_intent_txn_write_surface(poisoned)
    assert not nested
    assert any(site.startswith('walrus:transaction:') for site in rebinds)
    assert any(site.startswith('walrus:conversation_ref:') for site in rebinds)
    # The production source has no assignment expression to report.
    assert not [site for site in collect_intent_txn_write_surface(source)[1] if site.startswith('walrus:')]
