"""Derived, rebuildable workstream retrieval index maintenance."""

from collections.abc import Callable
from typing import Optional

import database.workstreams as workstreams_db
from database.vector_db import (
    delete_workstream_association_vector,
    reset_workstream_association_vectors,
    upsert_workstream_association_vector,
)
from models.workstream import Workstream, WorkstreamStatus
from models.workstream_association import WorkstreamIndexRebuildReport
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.observability.fallback import record_fallback


def refresh_workstream_association_index(
    uid: str,
    workstream_id: str,
    *,
    firestore_client=None,
    hydrate: Callable[..., Optional[Workstream]] = workstreams_db.get_workstream,
    upsert_index: Callable[..., bool] = upsert_workstream_association_vector,
    delete_index: Callable[..., bool] = delete_workstream_association_vector,
) -> bool:
    if resolve_memory_system(uid, db_client=firestore_client) != MemorySystem.CANONICAL:
        return False
    try:
        control = workstreams_db.get_task_workflow_control(uid, firestore_client=firestore_client)
        workstream = hydrate(
            uid,
            workstream_id,
            account_generation=control.account_generation,
            firestore_client=firestore_client,
        )
        if workstream is None or workstream.status != WorkstreamStatus.open:
            return delete_index(uid, workstream_id, account_generation=control.account_generation)
        return upsert_index(
            uid,
            workstream.workstream_id,
            objective=workstream.objective,
            current_state_summary=workstream.current_state_summary,
            account_generation=control.account_generation,
        )
    except Exception:
        record_fallback(
            component='other',
            from_mode='workstream_authority',
            to_mode='association_index_stale',
            reason='other',
            outcome='degraded',
        )
        return False


def rebuild_workstream_association_index(
    uid: str,
    *,
    firestore_client=None,
    list_source: Callable[..., list[Workstream]] = workstreams_db.list_open_workstreams,
    reset_index: Callable[..., bool] = reset_workstream_association_vectors,
    upsert_index: Callable[..., bool] = upsert_workstream_association_vector,
) -> WorkstreamIndexRebuildReport:
    if resolve_memory_system(uid, db_client=firestore_client) != MemorySystem.CANONICAL:
        return WorkstreamIndexRebuildReport(uid=uid, source_count=0, indexed_count=0)
    control = workstreams_db.get_task_workflow_control(uid, firestore_client=firestore_client)
    workstreams = [
        item
        for item in list_source(
            uid,
            account_generation=control.account_generation,
            firestore_client=firestore_client,
        )
        if item.status == WorkstreamStatus.open
    ]
    reset_index(uid, account_generation=control.account_generation)
    indexed_count = 0
    failed: list[str] = []
    for workstream in workstreams:
        if upsert_index(
            uid,
            workstream.workstream_id,
            objective=workstream.objective,
            current_state_summary=workstream.current_state_summary,
            account_generation=control.account_generation,
        ):
            indexed_count += 1
        else:
            failed.append(workstream.workstream_id)
    return WorkstreamIndexRebuildReport(
        uid=uid,
        source_count=len(workstreams),
        indexed_count=indexed_count,
        failed_workstream_ids=failed,
    )


__all__ = ['rebuild_workstream_association_index', 'refresh_workstream_association_index']
