"""A6 backfill, staging dry run: census the Firestore batch documents against their Postgres copies, then
(``apply``) copy every missing or differing one.

Firestore stays the primary and the only authority. Each copy goes through the A2 mirror's own path
(``DualStore.copy_current``): the key's Postgres advisory lock, then a fresh, lock-free ``get_all`` of the
primary's current state. A backfill page therefore never regresses a row that a live mirror updated after the
census read it, and a document deleted meanwhile is deleted from Postgres too. Rerunnable and idempotent.

Only the eight mirrored batch tables are read; customer documents (``conversations``, ``content``) never
are. The report holds counts only, never a key, id or value. Postgres-only rows are counted, not deleted.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Iterator

from database.jobstore.dual_store import MIRRORED_TABLES, DualStore, ShadowParityOutcome, compare, read_current

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
COPY_BUDGET_S = 10.0
_TYPED = {'jobs', 'results', 'control'}


@dataclass
class TableReport:
    firestore: int = 0
    match: int = 0
    mismatch: int = 0
    missing: int = 0
    uncomparable: int = 0
    postgres_only: int = 0
    copied: int = 0
    copy_errors: int = 0


def _pages(client: Any, collection: str, page_size: int) -> Iterator[list[Any]]:
    """Firestore snapshots of ``collection`` in document-id order, one page at a time."""
    from google.cloud.firestore_v1.field_path import FieldPath

    query = client.collection(collection).order_by(FieldPath.document_id()).limit(page_size)
    last = None
    while True:
        page = list((query.start_after(last) if last is not None else query).stream())
        if not page:
            return
        yield page
        if len(page) < page_size:
            return
        last = page[-1]


def postgres_keys(conn: Any, namespace: str, table: str) -> set[str]:
    if table in _TYPED:
        rows = conn.execute(f'SELECT key FROM {table} WHERE namespace = %s', (namespace,)).fetchall()
    else:
        rows = conn.execute('SELECT key FROM docs WHERE namespace = %s AND tbl = %s', (namespace, table)).fetchall()
    return {row[0] for row in rows}


def backfill_table(dual: DualStore, client: Any, table: str, *, apply: bool, page_size: int = PAGE_SIZE) -> TableReport:
    if table not in MIRRORED_TABLES:
        raise ValueError(f'{table} is not a mirrored batch table')
    shadow, namespace = dual.shadow, dual.shadow.namespace
    report = TableReport()
    seen: set[str] = set()
    for page in _pages(client, f'{namespace}_{table}', page_size):
        stale: list[tuple[str, str]] = []
        with shadow.pool.connection(timeout=COPY_BUDGET_S) as conn:
            for snapshot in page:
                key = snapshot.id
                seen.add(key)
                report.firestore += 1
                outcome = compare(snapshot.to_dict() or {}, shadow.read_doc(conn, table, key))
                if outcome is ShadowParityOutcome.MATCH:
                    report.match += 1
                    continue
                if outcome is ShadowParityOutcome.UNCOMPARABLE:
                    report.uncomparable += 1
                    continue
                report.missing += outcome is ShadowParityOutcome.MISSING
                report.mismatch += outcome is ShadowParityOutcome.MISMATCH
                stale.append((table, key))
        if apply and stale:
            try:
                with shadow.pool.connection(timeout=COPY_BUDGET_S) as conn:
                    with conn.transaction():
                        dual.copy_current(conn, sorted(stale), reader=read_current)
                report.copied += len(stale)
            except Exception as exc:  # counted per page; the rerun picks the page up again
                report.copy_errors += len(stale)
                logger.warning(
                    'event=jobstore_backfill outcome=copy_error table=%s error=%s', table, type(exc).__name__
                )
    with shadow.pool.connection(timeout=COPY_BUDGET_S) as conn:
        report.postgres_only = len(postgres_keys(conn, namespace, table) - seen)
    return report


def backfill(
    dual: DualStore, client: Any, tables: list[str], *, apply: bool, page_size: int = PAGE_SIZE
) -> dict[str, dict]:
    return {table: asdict(backfill_table(dual, client, table, apply=apply, page_size=page_size)) for table in tables}
