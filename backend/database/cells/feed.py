"""Current-state device feed; sequence allocation lives only in store.py."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from database.cells._validation import validate_id
from database.cells.errors import CellSpaceUnavailable, CellWriteError
from database.jobstore.connection import Pool
from database.cells.purge import lock_writable_space

DEVICE_STALE_S = 90 * 24 * 3600.0
FEED_RETENTION_S = 30 * 24 * 3600.0
PULL_LIMIT_MAX = 500


class ResyncRequired(CellWriteError):
    """The client needs a fresh snapshot (mapped to HTTP 425 by the future router)."""

    def __init__(self, space_id: str, floor: int, epoch: int):
        super().__init__(space_id, 'cursor requires resync')
        self.floor = floor
        self.epoch = epoch


class CursorAhead(CellWriteError):
    """The cursor exceeds committed history; the future HTTP layer requests resync."""

    def __init__(self, space_id: str, head: int, epoch: int):
        super().__init__(space_id, 'cursor is ahead of space head')
        self.head = head
        self.epoch = epoch


@dataclass(frozen=True)
class ChangeEntry:
    seq: int
    entity: str
    entity_id: str
    op: str
    rev: int
    actor_uid: str
    client_mutation_id: str | None
    ts: float


@dataclass
class PullPage:
    entries: list[ChangeEntry]
    rows: dict[tuple[str, str], dict[str, Any] | None]
    next_cursor: int
    head: int
    epoch: int


@dataclass
class SnapshotPage:
    rows: list[dict[str, Any]]
    entries: list[ChangeEntry]
    next_page_token: str | None
    head: int
    epoch: int


def read_enrolled_head(conn: Any, space_id: str) -> tuple[int, int]:
    row = conn.execute('SELECT next_seq, epoch, tombstoned FROM space_heads WHERE space_id=%s', (space_id,)).fetchone()
    if row is None or row[2]:
        raise CellSpaceUnavailable(space_id)
    return row[0], row[1]


def _floor(conn: Any, space_id: str, now: float) -> tuple[int, int, int]:
    row = conn.execute(
        'SELECT h.next_seq, h.epoch, '
        '(SELECT min(last_seq) FROM sync_cursors WHERE space_id=h.space_id AND last_seen_at>%s), '
        '(SELECT min(seq) FROM change_log WHERE space_id=h.space_id AND ts>%s) '
        'FROM space_heads h WHERE h.space_id=%s',
        (now - DEVICE_STALE_S, now - FEED_RETENTION_S, space_id),
    ).fetchone()
    if row is None:
        return 0, 0, 0
    head, epoch, device, first_recent = row
    # A cursor is the last APPLIED seq: cursor=first_recent-1 can still
    # consume every retained entry. Using first_recent rejects initial pulls.
    time_floor = max(0, first_recent - 1) if first_recent is not None else head
    return min(device, time_floor) if device is not None else time_floor, epoch, head


class Feed:
    pool: Pool

    def floor(self, space_id: str, *, now: float) -> int:
        validate_id(space_id)
        with self.pool.connection() as conn:
            return _floor(conn, space_id, now)[0]

    def pull(self, space_id: str, *, cursor: int, limit: int = 200, now: float) -> PullPage:
        """Read a consistent committed page. A racing purge may yield a stale page;
        the next request observes its fence. Head and entries share a snapshot so
        advancing past a feed=false tail can never skip a concurrent feed write.
        """
        validate_id(space_id)
        limit = max(1, min(limit, PULL_LIMIT_MAX))
        if cursor < 0:
            raise ValueError('cursor must be nonnegative')
        with self.pool.connection() as conn, conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            read_enrolled_head(conn, space_id)
            floor, epoch, head_seq = _floor(conn, space_id, now)
            if cursor > head_seq:
                raise CursorAhead(space_id, head_seq, epoch)
            if cursor < floor:
                raise ResyncRequired(space_id, floor, epoch)
            raw = conn.execute(
                'SELECT seq, entity, entity_id, op, rev, actor_uid, client_mutation_id, ts '
                'FROM change_log WHERE space_id=%s AND seq>%s AND feed ORDER BY seq LIMIT %s',
                (space_id, cursor, limit),
            ).fetchall()
            latest = {(r[1], r[2]): ChangeEntry(*r) for r in raw}
            entries = sorted(latest.values(), key=lambda entry: entry.seq)
            rows: dict[tuple[str, str], dict[str, Any] | None] = {address: None for address in latest}
            if rows:
                # Parallel unnest avoids psycopg's unregistered anonymous-record array.
                # This is one read-set statement, scoped to the page's distinct keys.
                found = conn.execute(
                    'SELECT entity, entity_id, author_id, rev, doc, updated_at FROM cell_docs '
                    'WHERE space_id=%s AND (entity, entity_id) IN '
                    '(SELECT * FROM unnest(%s::text[], %s::text[]))',
                    (space_id, [a[0] for a in rows], [a[1] for a in rows]),
                ).fetchall()
                for entity, entity_id, author, rev, doc, updated in found:
                    rows[(entity, entity_id)] = dict(
                        space_id=space_id,
                        entity=entity,
                        entity_id=entity_id,
                        author_id=author,
                        rev=rev,
                        doc=doc,
                        updated_at=updated,
                    )
            head, epoch = read_enrolled_head(conn, space_id)
        next_cursor = raw[-1][0] if len(raw) == limit else head
        return PullPage(entries, rows, next_cursor, head, epoch)

    def snapshot(
        self,
        space_id: str,
        *,
        after: tuple[str, str] | None = None,
        limit: int = 200,
        since: int = 0,
        now: float,
    ) -> SnapshotPage:
        """Read keyset pages of current state (not historical documents).

        Clients retain page 1's head as the post-snapshot cursor, never the last
        page's head, and restart if epoch changes between pages. Commit-ordered
        sequences ensure every change through page 1's head is reflected in
        later pages; a subsequent pull catches changes to earlier pages.
        A purge racing a page may yield a stale page; the next hits the fence.
        Rows and latest deletion entries share one address-keyed page budget.
        Recreated rows suppress older tombstones. Deletes are retained by
        compaction, so snapshot?since alone can reconcile deleted local rows.
        """
        validate_id(space_id)
        if since < 0:
            raise ValueError('since must be nonnegative')
        limit = max(1, min(limit, PULL_LIMIT_MAX))
        with self.pool.connection() as conn, conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            read_enrolled_head(conn, space_id)
            found = conn.execute(
                'SELECT entity, entity_id, author_id, rev, doc, updated_at, '
                'seq, op, actor_uid, client_mutation_id, ts FROM ('
                'SELECT entity, entity_id, author_id, rev, doc, updated_at, '
                'NULL::bigint AS seq, NULL::text AS op, NULL::text AS actor_uid, '
                'NULL::text AS client_mutation_id, NULL::float8 AS ts '
                'FROM cell_docs WHERE space_id=%s AND rev>%s '
                'UNION ALL '
                'SELECT d.entity, d.entity_id, NULL, d.rev, NULL::jsonb, NULL::float8, '
                'd.seq, d.op, d.actor_uid, d.client_mutation_id, d.ts FROM ('
                'SELECT DISTINCT ON (entity, entity_id) '
                'entity, entity_id, seq, op, rev, actor_uid, client_mutation_id, ts '
                "FROM change_log WHERE space_id=%s AND seq>%s AND op='delete' "
                'ORDER BY entity, entity_id, seq DESC) d '
                'WHERE NOT EXISTS (SELECT 1 FROM cell_docs c '
                'WHERE c.space_id=%s AND c.entity=d.entity AND c.entity_id=d.entity_id)'
                ') state WHERE (%s::text IS NULL OR (entity, entity_id)>(%s,%s)) '
                'ORDER BY entity, entity_id LIMIT %s',
                (
                    space_id,
                    since,
                    space_id,
                    since,
                    space_id,
                    after[0] if after else None,
                    after[0] if after else None,
                    after[1] if after else None,
                    limit,
                ),
            ).fetchall()
            head, epoch = read_enrolled_head(conn, space_id)
        rows = [
            dict(entity=r[0], entity_id=r[1], author_id=r[2], rev=r[3], doc=r[4], updated_at=r[5])
            for r in found
            if r[6] is None
        ]
        entries = [ChangeEntry(r[6], r[0], r[1], r[7], r[3], r[8], r[9], r[10]) for r in found if r[6] is not None]
        token = base64.b64encode(json.dumps(list(found[-1][:2])).encode()).decode() if len(found) == limit else None
        return SnapshotPage(rows, entries, token, head, epoch)

    def set_cursor(self, space_id: str, device_id: str, *, last_seq: int, now: float) -> None:
        validate_id(space_id)
        validate_id(device_id)
        if last_seq < 0:
            raise ValueError('last_seq must be nonnegative')
        with self.pool.connection() as conn, conn.transaction():
            lock_writable_space(conn, space_id)
            floor, epoch, head = _floor(conn, space_id, now)
            if last_seq > head:
                raise CursorAhead(space_id, head, epoch)
            if last_seq < floor:
                raise ResyncRequired(space_id, floor, epoch)
            conn.execute(
                'INSERT INTO sync_cursors (space_id, device_id, last_seq, last_seen_at) VALUES (%s,%s,%s,%s) '
                'ON CONFLICT (space_id, device_id) DO UPDATE SET '
                'last_seq=greatest(sync_cursors.last_seq, EXCLUDED.last_seq), '
                'last_seen_at=greatest(sync_cursors.last_seen_at, EXCLUDED.last_seen_at)',
                (space_id, device_id, last_seq, now),
            )

    def compact(self, space_id: str, *, now: float) -> int:
        validate_id(space_id)
        with self.pool.connection() as conn, conn.transaction():
            floor, _epoch, _head = _floor(conn, space_id, now)
            return conn.execute(
                "DELETE FROM change_log WHERE space_id=%s AND seq<%s AND op='upsert'",
                (space_id, floor),
            ).rowcount
