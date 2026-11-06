"""Current-state device feed; sequence allocation lives only in store.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from database.cells._validation import validate_id
from database.cells.errors import CellWriteError
from database.jobstore.connection import Pool

DEVICE_STALE_S = 90 * 24 * 3600.0
FEED_RETENTION_S = 30 * 24 * 3600.0
PULL_LIMIT_MAX = 500


class ResyncRequired(CellWriteError):
    """The client needs a fresh snapshot (mapped to HTTP 425 by the future router)."""

    def __init__(self, space_id: str, floor: int, epoch: int):
        super().__init__(space_id, 'cursor requires resync')
        self.floor = floor
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


def _floor(conn: Any, space_id: str, now: float) -> tuple[int, int]:
    row = conn.execute(
        'SELECT h.next_seq, h.epoch, '
        '(SELECT min(last_seq) FROM sync_cursors WHERE space_id=h.space_id AND last_seen_at>%s), '
        '(SELECT min(seq) FROM change_log WHERE space_id=h.space_id AND ts>%s) '
        'FROM space_heads h WHERE h.space_id=%s',
        (now - DEVICE_STALE_S, now - FEED_RETENTION_S, space_id),
    ).fetchone()
    if row is None:
        return 0, 0
    head, epoch, device, first_recent = row
    # A cursor is the last APPLIED seq: cursor=first_recent-1 can still
    # consume every retained entry. Using first_recent rejects initial pulls.
    time_floor = max(0, first_recent - 1) if first_recent is not None else head
    return min(device, time_floor) if device is not None else time_floor, epoch


class Feed:
    pool: Pool

    def floor(self, space_id: str, *, now: float) -> int:
        validate_id(space_id)
        with self.pool.connection() as conn:
            return _floor(conn, space_id, now)[0]

    def pull(self, space_id: str, *, cursor: int, limit: int = 200, now: float) -> PullPage:
        validate_id(space_id)
        if cursor < 0:
            raise ValueError('cursor must be nonnegative')
        with self.pool.connection() as conn:
            floor, epoch = _floor(conn, space_id, now)
            if cursor < floor:
                raise ResyncRequired(space_id, floor, epoch)
            raw = conn.execute(
                'SELECT seq, entity, entity_id, op, rev, actor_uid, client_mutation_id, ts '
                'FROM change_log WHERE space_id=%s AND seq>%s AND feed ORDER BY seq LIMIT %s',
                (space_id, cursor, max(1, min(limit, PULL_LIMIT_MAX))),
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
            head = conn.execute('SELECT next_seq, epoch FROM space_heads WHERE space_id=%s', (space_id,)).fetchone()
        return PullPage(entries, rows, raw[-1][0] if raw else cursor, head[0] if head else 0, head[1] if head else 0)

    def set_cursor(self, space_id: str, device_id: str, *, last_seq: int, now: float) -> None:
        validate_id(space_id)
        validate_id(device_id)
        if last_seq < 0:
            raise ValueError('last_seq must be nonnegative')
        with self.pool.connection() as conn, conn.transaction():
            floor, epoch = _floor(conn, space_id, now)
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
            floor, _epoch = _floor(conn, space_id, now)
            return conn.execute(
                "DELETE FROM change_log WHERE space_id=%s AND seq<%s AND op='upsert'",
                (space_id, floor),
            ).rowcount
