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


def _export_photo_manifest(uid: str, conversation_id: str, photo: Mapping[str, Any]) -> JsonRecord:
    """Return a portable photo manifest, including durable bytes when present."""

    result: JsonRecord = {
        "conversation_id": conversation_id,
        "photo_id": photo.get("id"),
        "content_type": photo.get("content_type"),
        "created_at": photo.get("created_at"),
        "storage_id": photo.get("storage_id"),
        "bytes_available": False,
    }
    inline = photo.get("base64")
    if isinstance(inline, str) and inline:
        result["bytes_base64"] = inline
        result["bytes_available"] = True
        return result
    storage_id = photo.get("storage_id")
    if isinstance(storage_id, str) and storage_id:
        try:
            payload = download_frame_request_pixels(uid, storage_id)
        except Exception:
            # The manifest remains explicit when an external object cannot be
            # read; never silently claim that export contains image bytes.
            return result
        result["bytes_base64"] = base64.b64encode(payload).decode("ascii")
        result["bytes_available"] = True
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
            # Do not trust the marker alone: legacy conversations may have a
            # photo subcollection without ``has_photos``.
            conversation_id = str(conv.get("id") or "")
            if conversation_id:
                for photo in conversations_db.get_conversation_photos(uid, conversation_id) or []:
                    if not isinstance(photo, Mapping):
                        continue
                    if photo_count:
                        photo_spool.write(",\n")
                    photo_spool.write("    ")
                    json.dump(
                        _export_photo_manifest(uid, conversation_id, photo),
                        photo_spool,
                        default=_json_default,
                        indent=4,
                    )
                    photo_count += 1
        yield "\n  ],\n"

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
            if isinstance(storage_id, str) and storage_id:
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


def _iter_user_data_export_and_close_spool(uid: str, memories_spool: IO[str]) -> Iterator[str]:
    try:
        yield from _iter_user_data_export_from_spool(uid, memories_spool)
    finally:
        memories_spool.close()


def iter_user_data_export(uid: str) -> Iterator[str]:
    # Build the remote/authority-sensitive section before the first response
    # byte. A canonical memory read failure can then become the real HTTP error
    # instead of a 200 response containing truncated JSON. This function must
    # remain a regular function: making it a generator defers this preflight
    # until after StreamingResponse has committed its status and headers.
    memories_spool = _spool_export_memories_json(uid)
    return _iter_user_data_export_and_close_spool(uid, memories_spool)
