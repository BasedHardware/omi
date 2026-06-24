from __future__ import annotations

"""Canonical non active route report module (WS-G8a).

Canonical admin/benchmark seam for non-active route audit reports.
"""


from typing import Iterable, Optional

from database._client import db
from database.memory_collections import MemoryCollections
from utils.memory.non_active_route_audit import NonActiveRouteAuditReport, build_non_active_route_audit_report


def fetch_non_active_route_audit_report(
    uid: str,
    *,
    run_id: Optional[str] = None,
    expected_source_ids: Optional[Iterable[str]] = None,
    db_client=db,
) -> NonActiveRouteAuditReport:
    """Fetch route-store docs and build the memory non-active no-silent-loss audit report.

    This is the narrow admin/benchmark caller seam for T17-R: it reads only the
    durable `non_active_memory_routes` collection for a user (optionally scoped to
    a run), then delegates all accounting/default-visibility checks to the shared
    no-DB audit helper. It intentionally does not read `memory_items`, so default
    Long-term visibility remains unaffected and internal routes such as
    `context_only` are audit-visible without becoming user-visible.
    """

    route_docs = _fetch_non_active_route_docs(uid, run_id=run_id, db_client=db_client)
    return build_non_active_route_audit_report(uid, route_docs, expected_source_ids=expected_source_ids)


def _fetch_non_active_route_docs(uid: str, *, run_id: Optional[str], db_client=db):
    collection_path = MemoryCollections(uid=uid).non_active_memory_routes
    query = db_client.collection(collection_path)
    if run_id:
        query = query.where("run_id", "==", run_id)
    return [snapshot.to_dict() or {} for snapshot in query.stream()]
