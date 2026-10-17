"""Freeze encrypted VAD pieces and lineage before any held-audio dispatch."""

import hashlib
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from utils.executors import run_blocking, storage_executor
from utils.sync import cap_hold
from utils.sync.files import get_wav_duration


class PlanFenced(RuntimeError):
    pass


def persist_piece(uid: str, hold_id: str, path: str, context: dict[str, Any]) -> dict[str, Any]:
    identity = hashlib.sha256(
        (hold_id + cap_hold.capture_identity(path, context) + json.dumps(context, sort_keys=True)).encode()
    ).hexdigest()
    return {**cap_hold.upload_held_audio(uid, path, identity, context), 'seconds': get_wav_duration(path)}


async def ensure_plan(
    uid: str,
    snapshot: Any,
    row: dict[str, Any],
    meta: dict[str, Any],
    directory: Any,
    prepare_audio: Callable[..., Awaitable[tuple[set, dict, dict, dict]]],
    save: Callable[..., Awaitable[bool]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    if 'piece_plan' in row:
        return row['piece_plan'], {}, {}
    name = Path(meta.get('file_name') or f"{meta['timestamp']}.wav").name
    path = str(Path(directory.name) / name)
    await run_blocking(storage_executor, cap_hold.read_audio, uid, row, path)
    paths, source_maps, targets, bindings = await prepare_audio(uid, path, meta)
    plan, local_paths, contexts = {}, {}, {}
    for path in sorted(paths):
        name = Path(path).name
        if name in plan:
            raise ValueError('held piece identity collision')
        context = {
            'target_conversation_id': targets.get(path, meta.get('target_conversation_id')),
            'source_position_map': source_maps.get(path),
            'lineage_binding': bindings.get(path, meta.get('lineage_binding')),
        }
        plan[name] = await run_blocking(storage_executor, persist_piece, uid, snapshot.id, path, context)
        local_paths[name], contexts[name] = path, context
    if not await save(uid, snapshot, row, {'piece_plan': plan}):
        raise PlanFenced('held piece plan ownership changed')
    return plan, local_paths, contexts


async def stage_piece(
    uid: str,
    name: str,
    entry: dict[str, Any],
    directory: Any,
    local_paths: dict[str, str],
    contexts: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    if name in local_paths:
        return local_paths[name], contexts[name]
    path = str(Path(directory.name) / Path(name).name)
    context = await run_blocking(storage_executor, cap_hold.metadata, uid, entry)
    await run_blocking(storage_executor, cap_hold.read_audio, uid, entry, path)
    position = context.get('source_position_map')
    context['source_position_map'] = tuple(position) if position else None
    return path, context
