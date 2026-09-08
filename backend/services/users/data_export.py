from __future__ import annotations

import json
import base64
import tempfile
from datetime import datetime
from itertools import chain
from typing import IO, Any, Callable, Iterable, Iterator, Mapping, Sequence, cast

from database import chat as chat_db
from database import conversations as conversations_db
from database import _client as database_client
from database.action_items import get_action_items as get_standalone_action_items
from utils.retrieval.frame_request_storage import download_frame_request_pixels
from database.users import get_people, get_user_profile
from utils.memory.memory_service import MemoryService

JsonRecord = dict[str, Any]


class PortabilityExportIncomplete(RuntimeError):
    """A retained user-data object could not be included in the export."""


# Primary/user-visible task intelligence records. Derived projections, leases,
# idempotency receipts, and outboxes are intentionally excluded: they are
# implementation state, not additional user-authored product data.
TASK_EXPORT_COLLECTIONS = (
    'candidates',
    'goals',
    'workstreams',
    'staged_tasks',
    'task_recurrence_inbox',
    'task_feedback',
    'task_outcomes',
    'task_interventions',
    'task_attention_overrides',
    'task_context_snapshots',
    'task_open_loop_snapshots',
    'chat_first_proactive_intents',
    'chat_first_dead_letters',
    'chat_first_deferrals',
)

# User-visible history/evidence nested beneath its owning Goal or Workstream.
# Projection heads, mutation receipts, leases, and outboxes stay excluded as
# rebuildable implementation state.
TASK_NESTED_EXPORT_COLLECTIONS = (
    ('goal_events', 'goals', 'events'),
    ('goal_history', 'goals', 'goal_history'),
    ('workstream_events', 'workstreams', 'events'),
    ('workstream_artifact_refs', 'workstreams', 'artifact_refs'),
    ('workstream_continuation_checkpoints', 'workstreams', 'continuation_checkpoints'),
)

# The daily memory sweep persists bounded model output in user-owned
# subcollections. These rows contain transcript-derived candidates and must
# be included in export even though they are not product-facing collections.
MEMORY_SWEEP_EXPORT_COLLECTIONS = (
    'daily_memory_sweep_sources',
    'daily_memory_sweep_daily_summary_staged',
    'daily_memory_sweep_onboarding_staged',
    'daily_memory_sweep_model_invocations',
)

# JIT is user-visible product history, not disposable implementation state.
# Export the content-free feedback and proactivity ledgers so a portability
# export can reconstruct what was shown, reserved, and explicitly corrected.
JIT_EXPORT_COLLECTIONS = (
    'jit_trigger_feedback',
    'jit_proactivity_events',
    'jit_proactivity_daily_budgets',
    'jit_proactivity_candidate_turns',
)

# Review decisions and corrections are retained user-owned memory history.
# Pending/accepted rows can contain candidate text, evidence, corrections, and
# explicit user reasons, so they belong in portability export rather than being
# treated as rebuildable projections. Privacy-scrubbed rows remain portable as
# content-free audit history.
MEMORY_REVIEW_EXPORT_COLLECTIONS = (
    'memory_review_queue',
    'memory_corrections',
)

# Account-lifetime canonical ledger history and lineage authority. These rows
# are retained independently of the user-facing MemoryDB projection and must
# remain portable, including content-free tombstones and receipts.
MEMORY_LEDGER_EXPORT_COLLECTIONS = (
    'memory_items',
    'memory_operations',
    'memory_commits',
    'memory_deletion_receipts',
    'memory_source_replacements',
    'memory_ledger_reopens',
    'memory_lineage',
    'memory_historical_overrides',
    'memory_evidence',
)


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _iter_paginated(
    fetch_page: Callable[[int, int], Sequence[Mapping[str, Any]]], *, batch_size: int = 1000
) -> Iterator[Mapping[str, Any]]:
    offset = 0
    while True:
        page = fetch_page(batch_size, offset)
        if not page:
            break
        yield from page
        if len(page) < batch_size:
            break
        offset += batch_size


def _yield_json_array(items: Iterable[Mapping[str, Any]]) -> Iterator[str]:
    yield '[\n'
    first = True
    for item in items:
        if not first:
            yield ',\n'
        first = False
        yield '    ' + json.dumps(item, default=_json_default, indent=4)
    yield '\n  ]'


def _spool_export_memories_json(uid: str) -> IO[str]:
    """Materialize the memories JSON array before any bytes reach the client.

    Spools to a bounded in-memory buffer with automatic disk spillover so large
    exports stay scalable without emitting partial JSON when iteration fails.
    """
    # 8 MiB before spilling to disk keeps typical exports in memory while
    # bounding resident size for very large accounts.
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+", encoding="utf-8")
    try:
        spool.write("[\n")
        first = True
        for memory in MemoryService().iter_portability_export_memories(uid, include_archive=True):
            if not first:
                spool.write(",\n")
            first = False
            spool.write("    " + json.dumps(memory.model_dump(mode="json"), default=_json_default, indent=4))
        spool.write("\n  ]")
        spool.seek(0)
        return spool
    except BaseException:
        spool.close()
        raise


def _iter_user_subcollection(uid: str, collection_name: str) -> Iterator[Mapping[str, Any]]:
    """Stream one user-owned primary collection without loading it in memory."""

    collection = database_client.db.collection('users').document(uid).collection(collection_name)
    for snapshot in collection.stream():
        payload = snapshot.to_dict()
        if not isinstance(payload, dict):
            continue
        row = dict(payload)
        row.setdefault('id', snapshot.id)
        yield row


def _iter_user_nested_subcollection(
    uid: str,
    parent_collection_name: str,
    child_collection_name: str,
) -> Iterator[Mapping[str, Any]]:
    """Stream user-visible records nested below one user-owned collection."""

    parents = database_client.db.collection('users').document(uid).collection(parent_collection_name)
    for parent_snapshot in parents.stream():
        for child_snapshot in parent_snapshot.reference.collection(child_collection_name).stream():
            payload = child_snapshot.to_dict()
            if not isinstance(payload, dict):
                continue
            row = dict(payload)
            row.setdefault('id', child_snapshot.id)
            row['parent_id'] = parent_snapshot.id
            yield row


def _export_photo_manifest(
    uid: str, conversation_id: str, photo: Mapping[str, Any], *, require_bytes: bool = True
) -> JsonRecord:
    """Return a portable photo manifest, including durable bytes when present.

    ``require_bytes`` controls the no-reference case: frame requests in a
    retained state must abort (their bytes are known to exist, so omitting
    them would silently drop durable data), while legacy conversation photo
    rows can legitimately hold no bytes anywhere and must not permanently
    deny the user their export.
    """

    result: JsonRecord = {
        "conversation_id": conversation_id,
        "photo_id": photo.get("id"),
        "content_type": photo.get("content_type"),
        "created_at": photo.get("created_at"),
        "storage_id": photo.get("storage_id"),
        "bytes_available": False,
    }
    inline = photo.get("base64")
    # Some retained records have been migrated to durable storage while still
    # carrying the legacy empty inline marker. An empty marker is therefore
    # equivalent to an absent one, but a non-empty malformed inline payload is
    # authoritative and must fail closed rather than falling back to another
    # representation.
    if inline not in (None, ""):
        if not isinstance(inline, str):
            raise PortabilityExportIncomplete("retained inline image bytes are malformed")
        try:
            decoded = base64.b64decode(inline, validate=True)
        except Exception as exc:
            raise PortabilityExportIncomplete("retained inline image bytes are malformed") from exc
        if not decoded:
            raise PortabilityExportIncomplete("retained inline image bytes are empty")
        result["bytes_base64"] = inline
        result["bytes_available"] = True
        return result
    storage_id = photo.get("storage_id")
    if isinstance(storage_id, str) and storage_id:
        # A retained image is part of the portability boundary.  If its bytes
        # cannot be read, abort the export so the job can retry; returning a
        # nominally successful archive with ``bytes_available: false`` would
        # silently omit durable user data.
        payload = download_frame_request_pixels(uid, storage_id)
        if not payload:
            raise PortabilityExportIncomplete("retained image object is empty")
        result["bytes_base64"] = base64.b64encode(payload).decode("ascii")
        result["bytes_available"] = True
        return result
    if require_bytes:
        raise PortabilityExportIncomplete("retained image bytes reference is missing or malformed")
    # A conversation photo row with neither inline bytes nor a storage
    # reference holds no durable image anywhere — there is nothing to omit.
    result["bytes_unavailable_reason"] = "no_retained_bytes_reference"
    return result


def _iter_user_data_export_from_spool(uid: str, memories_spool: IO[str]) -> Iterator[str]:
    yield "{\n"

    profile = cast(JsonRecord | None, get_user_profile(uid))
    yield ('  "profile": ' + json.dumps(profile if profile else {}, default=_json_default, indent=2) + ",\n")

    # Photo manifests can contain base64 image bytes. Spool them independently
    # while conversations stream so account size cannot turn export into an
    # unbounded resident list.
    photo_spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+", encoding="utf-8")
    photo_count = 0
    try:
        yield '  "conversations": [\n'
        first = True
        for conv in conversations_db.iter_all_conversations(uid, include_discarded=True):
            if conv is None:
                continue
            if not first:
                yield ",\n"
            first = False
            yield "    " + json.dumps(conv, default=_json_default, indent=4)
        yield "\n  ],\n"

        for conversation_id, photo in conversations_db.iter_all_conversation_photos(uid):
            if not isinstance(photo, Mapping):
                continue
            if photo_count:
                photo_spool.write(",\n")
            photo_spool.write("    ")
            json.dump(
                _export_photo_manifest(uid, str(conversation_id), photo, require_bytes=False),
                photo_spool,
                default=_json_default,
                indent=4,
            )
            photo_count += 1

        if photo_count:
            yield '  "conversation_photo_manifest": [\n'
            photo_spool.seek(0)
            while chunk := photo_spool.read(64 * 1024):
                yield chunk
            yield "\n  ],\n"
    finally:
        photo_spool.close()

    # Frame-request metadata is user-owned audit history. Keep it separate from
    # conversation JSON and include a byte manifest for each referenced object.
    def frame_request_rows() -> Iterator[Mapping[str, Any]]:
        for row in _iter_user_subcollection(uid, "frame_requests"):
            if not isinstance(row.get("state"), str):
                continue
            request = dict(row)
            storage_id = request.get("storage_id")
            state = request["state"]
            cleanup_state = request.get("cleanup_state")
            # Uploaded and attached rows necessarily represent retained bytes.
            # A missing/malformed reference must abort before a 200 response;
            # metadata-only terminal states are allowed to omit pixels. Cleanup
            # deliberately preserves storage_id as audit metadata after object
            # deletion, so that stale identifier alone is not byte authority.
            cleanup_converged = cleanup_state in {"deleted", "not_required"}
            if state in {"uploaded", "attached"} or (not cleanup_converged and storage_id is not None):
                request["image_manifest"] = _export_photo_manifest(
                    uid,
                    str(request.get("conversation_id") or ""),
                    {
                        "id": request.get("request_id") or request.get("id"),
                        "storage_id": storage_id,
                        "content_type": request.get("content_type"),
                        "created_at": request.get("created_at"),
                    },
                )
            yield request

    frame_rows = frame_request_rows()
    first_frame = next(frame_rows, None)
    if first_frame is not None:
        yield '  "frame_requests": '
        yield from _yield_json_array(chain((first_frame,), frame_rows))
        yield ",\n"

    # Durable JIT receipts are user data too. They contain no pixels, but the
    # bounded derived vision description and lifecycle metadata remain part of
    # an exhaustive portability export.
    for collection_name, export_name in (
        ("frame_vision_receipts", "frame_vision_receipts"),
        ("conversation_keyframe_jobs", "conversation_keyframe_jobs"),
    ):
        rows = _iter_user_subcollection(uid, collection_name)
        first_row = next(rows, None)
        if first_row is not None:
            yield f'  "{export_name}": '
            yield from _yield_json_array(chain((first_row,), rows))
            yield ",\n"

    yield '  "memories": '
    while chunk := memories_spool.read(64 * 1024):
        yield chunk
    yield ',\n'

    yield '  "memory_review_data": {\n'
    for index, collection_name in enumerate(MEMORY_REVIEW_EXPORT_COLLECTIONS):
        yield f"    {json.dumps(collection_name)}: "
        yield from _yield_json_array(_iter_user_subcollection(uid, collection_name))
        yield ",\n" if index < len(MEMORY_REVIEW_EXPORT_COLLECTIONS) - 1 else "\n"
    yield '  },\n'

    yield '  "memory_ledger_data": {\n'
    for index, collection_name in enumerate(MEMORY_LEDGER_EXPORT_COLLECTIONS):
        yield f"    {json.dumps(collection_name)}: "
        yield from _yield_json_array(_iter_user_subcollection(uid, collection_name))
        yield ",\n" if index < len(MEMORY_LEDGER_EXPORT_COLLECTIONS) - 1 else "\n"
    yield '  },\n'

    # JIT rows are content-free control/history records, but remain part of
    # the user's retained product history and therefore must be portable.
    yield '  "jit_data": {\n'
    for index, collection_name in enumerate(JIT_EXPORT_COLLECTIONS):
        yield f"    {json.dumps(collection_name)}: "
        yield from _yield_json_array(_iter_user_subcollection(uid, collection_name))
        yield ",\n" if index < len(JIT_EXPORT_COLLECTIONS) - 1 else "\n"
    yield '  },\n'

    people = cast(Sequence[Mapping[str, Any]], get_people(uid))
    yield '  "people": ' + json.dumps(people, default=_json_default, indent=2) + ",\n"

    yield '  "action_items": '
    yield from _yield_json_array(
        _iter_paginated(
            lambda limit, offset: cast(
                Sequence[Mapping[str, Any]],
                get_standalone_action_items(uid, limit=limit, offset=offset),
            )
        )
    )
    yield ",\n"

    yield '  "task_data": {\n'
    task_export_sections = [
        (collection_name, _iter_user_subcollection(uid, collection_name)) for collection_name in TASK_EXPORT_COLLECTIONS
    ]
    task_export_sections.extend(
        (
            export_name,
            _iter_user_nested_subcollection(uid, parent_collection_name, child_collection_name),
        )
        for export_name, parent_collection_name, child_collection_name in TASK_NESTED_EXPORT_COLLECTIONS
    )
    task_export_sections.extend(
        (collection_name, _iter_user_subcollection(uid, collection_name))
        for collection_name in MEMORY_SWEEP_EXPORT_COLLECTIONS
    )
    for index, (collection_name, records) in enumerate(task_export_sections):
        yield f"    {json.dumps(collection_name)}: "
        yield from _yield_json_array(records)
        yield ",\n" if index < len(task_export_sections) - 1 else "\n"
    yield "  },\n"

    yield '  "chat_messages": [\n'
    first = True
    for msg in cast(Iterable[Mapping[str, Any]], chat_db.iter_all_messages(uid)):
        if not first:
            yield ",\n"
        first = False
        yield "    " + json.dumps(msg, default=_json_default, indent=4)
    yield "\n  ]\n"

    yield "}\n"


def _iter_spooled_export_and_close(export_spool: IO[str]) -> Iterator[str]:
    try:
        while chunk := export_spool.read(64 * 1024):
            yield chunk
    finally:
        export_spool.close()


def iter_user_data_export(uid: str) -> Iterator[str]:
    # Build the complete export before the first response byte. Every retained
    # image object and every authority-sensitive section must either be present
    # or raise a real HTTP error; a 200 response containing a truncated archive
    # is not a successful portability export. Both spools spill to disk after a
    # bounded in-memory prefix, so this remains safe for large accounts.
    memories_spool = _spool_export_memories_json(uid)
    export_spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+", encoding="utf-8")
    try:
        for chunk in _iter_user_data_export_from_spool(uid, memories_spool):
            export_spool.write(chunk)
        export_spool.seek(0)
    except BaseException:
        export_spool.close()
        raise
    finally:
        memories_spool.close()
    return _iter_spooled_export_and_close(export_spool)
