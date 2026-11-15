"""Separate-database routing authority and cross-user indexes (no serving callers).

Transaction retry discipline adapted from jobstore/postgres_store.py. All times
are supplied by the caller. Pool construction and enrollment belong to B2.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from database.jobstore.connection import Pool

T = TypeVar('T')


@dataclass(frozen=True)
class Space:
    space_id: str
    kind: str
    cell: str
    region: str | None
    epoch: int
    signup_platform: str | None
    signup_os: str | None
    signup_platform_at: float | None
    created_at: float
    updated_at: float
    ramp_bucket: float | None = None
    ramp_revision: int | None = None


@dataclass(frozen=True)
class OwnerTombstone:
    uid: str
    wipe_epoch: int
    cell: str | None
    created_at: float


class OwnerTombstoned(RuntimeError):
    """A wiped identity cannot enroll again, even from an admitted old request."""


@dataclass(frozen=True)
class Membership:
    space_id: str
    uid: str
    role: str
    state: str
    created_at: float
    revoked_at: float | None


@dataclass(frozen=True)
class TokenRow:
    uid: str
    device_key: str
    token: str
    time_zone: str | None
    created_at: float
    updated_at: float


class DirectoryStore:
    def __init__(self, pool: Pool):
        self.pool = pool

    def _run(self, body: Callable[[Any], T]) -> T:
        last: Exception | None = None
        for attempt in range(8):
            if attempt:
                time.sleep(random.uniform(0, min(0.2, 0.005 * 2**attempt)))
            try:
                with self.pool.connection() as conn, conn.transaction():
                    conn.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                    conn.execute("SET LOCAL lock_timeout = '2s'")
                    return body(conn)
            except Exception as exc:
                if getattr(exc, 'sqlstate', None) not in {'40001', '40P01', '55P03'}:
                    raise
                last = exc
        raise RuntimeError('directory transaction kept conflicting') from last

    def get_or_create_personal_space(
        self,
        uid: str,
        *,
        now: float,
        cell: str,
        ramp_bucket: float | None = None,
        ramp_revision: int | None = None,
        signup_platform: str | None = None,
        signup_os: str | None = None,
        signup_platform_at: float | None = None,
    ) -> Space:
        def body(conn: Any) -> Space:
            self._lock_live_owner(conn, uid)
            conn.execute(
                'INSERT INTO spaces (space_id, cell, ramp_bucket, ramp_revision, signup_platform, signup_os, '
                'signup_platform_at, created_at, updated_at) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (space_id) DO NOTHING',
                (uid, cell, ramp_bucket, ramp_revision, signup_platform, signup_os, signup_platform_at, now, now),
            )
            conn.execute(
                "INSERT INTO memberships (space_id, uid, role, created_at) VALUES (%s,%s,'owner',%s) "
                'ON CONFLICT (space_id, uid) DO NOTHING',
                (uid, uid, now),
            )
            return Space(*conn.execute('SELECT * FROM spaces WHERE space_id=%s', (uid,)).fetchone())

        return self._run(body)

    @staticmethod
    def _lock_owner(conn: Any, uid: str) -> None:
        # Also serializes absent-row enrollment against the durable wipe fence.
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('owner:' + uid,))

    @classmethod
    def _lock_live_owner(cls, conn: Any, uid: str) -> None:
        cls._lock_owner(conn, uid)
        if conn.execute('SELECT 1 FROM owner_tombstones WHERE uid=%s', (uid,)).fetchone():
            raise OwnerTombstoned('directory owner is tombstoned')

    def enroll_cell(self, uid: str, enroll: Callable[[], None]) -> None:
        """Hold admission through cell enrollment so a missing head cannot race wipe."""

        def body(conn: Any) -> None:
            self._lock_live_owner(conn, uid)
            enroll()

        self._run(body)

    def tombstone_owner(self, uid: str, *, now: float) -> OwnerTombstone:
        """Retain the original route and wipe epoch across purge and retries."""

        def body(conn: Any) -> OwnerTombstone:
            self._lock_owner(conn, uid)
            space = conn.execute('SELECT cell, epoch FROM spaces WHERE space_id=%s FOR UPDATE', (uid,)).fetchone()
            conn.execute(
                'INSERT INTO owner_tombstones (uid, wipe_epoch, cell, created_at) VALUES (%s,%s,%s,%s) '
                'ON CONFLICT (uid) DO NOTHING',
                (uid, space[1] + 1 if space else 1, space[0] if space else None, now),
            )
            fence = OwnerTombstone(*conn.execute('SELECT * FROM owner_tombstones WHERE uid=%s', (uid,)).fetchone())
            conn.execute(
                "UPDATE spaces SET cell='disabled', epoch=greatest(epoch,%s), updated_at=%s WHERE space_id=%s",
                (fence.wipe_epoch, now, uid),
            )
            return fence

        return self._run(body)

    def get_space(self, space_id: str) -> Space | None:
        with self.pool.connection() as conn:
            row = conn.execute('SELECT * FROM spaces WHERE space_id=%s', (space_id,)).fetchone()
        return Space(*row) if row else None

    def set_routing(
        self,
        space_id: str,
        *,
        cell: str | None = None,
        region: str | None = None,
        bump_epoch: bool = False,
        now: float,
    ) -> Space:
        def body(conn: Any) -> Space:
            self._lock_live_owner(conn, space_id)
            row = conn.execute(
                'UPDATE spaces SET cell=coalesce(%s,cell), region=coalesce(%s,region), epoch=epoch+%s, '
                'updated_at=%s WHERE space_id=%s RETURNING *',
                (cell, region, int(bump_epoch), now, space_id),
            ).fetchone()
            if row is None:
                raise LookupError('space is not registered')
            return Space(*row)

        return self._run(body)

    def add_member(self, space_id: str, uid: str, *, now: float, role: str = 'member') -> None:
        def body(conn: Any) -> None:
            for owner in sorted({space_id, uid}):
                self._lock_live_owner(conn, owner)
            conn.execute(
                'INSERT INTO memberships (space_id, uid, role, created_at) VALUES (%s,%s,%s,%s) '
                "ON CONFLICT (space_id, uid) DO UPDATE SET role=EXCLUDED.role, state='active', revoked_at=NULL",
                (space_id, uid, role, now),
            )

        self._run(body)

    def revoke_member(self, space_id: str, uid: str, *, now: float) -> bool:
        return self._run(
            lambda conn: conn.execute(
                "UPDATE memberships SET state='revoked', revoked_at=%s WHERE space_id=%s AND uid=%s AND state='active'",
                (now, space_id, uid),
            ).rowcount
            > 0
        )

    def is_active_owner(self, space_id: str, uid: str) -> bool:
        with self.pool.connection() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM memberships WHERE space_id=%s AND uid=%s AND state='active' AND role='owner'",
                    (space_id, uid),
                ).fetchone()
                is not None
            )

    def memberships_for_space(self, space_id: str, *, active_only: bool = True) -> list[Membership]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM memberships WHERE space_id=%s AND (NOT %s OR state='active') ORDER BY uid",
                (space_id, active_only),
            ).fetchall()
        return [Membership(*row) for row in rows]

    def memberships_for_uid(self, uid: str, *, active_only: bool = True) -> list[Membership]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM memberships WHERE uid=%s AND (NOT %s OR state='active') ORDER BY space_id",
                (uid, active_only),
            ).fetchall()
        return [Membership(*row) for row in rows]

    def upsert_token(
        self,
        uid: str,
        device_key: str,
        token: str,
        *,
        now: float,
        time_zone: str | None = None,
    ) -> None:
        def body(conn: Any) -> None:
            self._lock_live_owner(conn, uid)
            # Serialize recycled-token moves even when no row exists yet; a unique
            # index alone would reject one of two concurrent first registrations.
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('fcm:' + token,))
            conn.execute(
                'DELETE FROM fcm_tokens WHERE token=%s AND (uid,device_key)<>(%s,%s)', (token, uid, device_key)
            )
            conn.execute(
                'INSERT INTO fcm_tokens (uid, device_key, token, time_zone, created_at, updated_at) '
                'VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (uid,device_key) DO UPDATE SET '
                'token=EXCLUDED.token, time_zone=EXCLUDED.time_zone, updated_at=EXCLUDED.updated_at',
                (uid, device_key, token, time_zone, now, now),
            )

        self._run(body)

    def remove_token(self, token: str) -> bool:
        return self._run(lambda conn: conn.execute('DELETE FROM fcm_tokens WHERE token=%s', (token,)).rowcount > 0)

    def tokens_for_uid(self, uid: str) -> list[TokenRow]:
        with self.pool.connection() as conn:
            rows = conn.execute('SELECT * FROM fcm_tokens WHERE uid=%s ORDER BY device_key', (uid,)).fetchall()
        return [TokenRow(*row) for row in rows]

    def register_public_conversation(
        self,
        conversation_id: str,
        owner_space_id: str,
        *,
        visibility: str,
        now: float,
    ) -> None:
        def body(conn: Any) -> None:
            self._lock_live_owner(conn, owner_space_id)
            conn.execute(
                'INSERT INTO public_conversations (conversation_id, owner_space_id, visibility, created_at, updated_at) '
                'VALUES (%s,%s,%s,%s,%s) ON CONFLICT (conversation_id) DO UPDATE SET '
                'owner_space_id=EXCLUDED.owner_space_id, visibility=EXCLUDED.visibility, updated_at=EXCLUDED.updated_at',
                (conversation_id, owner_space_id, visibility, now, now),
            )

        self._run(body)

    def unregister_public_conversation(self, conversation_id: str) -> None:
        self._run(
            lambda conn: conn.execute('DELETE FROM public_conversations WHERE conversation_id=%s', (conversation_id,))
        )

    def public_conversation_owner(self, conversation_id: str) -> str | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                'SELECT owner_space_id FROM public_conversations WHERE conversation_id=%s', (conversation_id,)
            ).fetchone()
        return row[0] if row else None

    def purge_owner(self, uid: str, *, now: float) -> int:
        """Raise on any error; FK cascades and cross-space memberships commit atomically.

        The caller tombstones admission and drains writers first. Owner tombstones
        deliberately survive this content purge, preventing identity resurrection.
        """

        def body(conn: Any) -> int:
            conn.execute('SET LOCAL statement_timeout = 30000')
            total = conn.execute(
                'SELECT (SELECT count(*) FROM spaces WHERE space_id=%s) + '
                '(SELECT count(*) FROM memberships WHERE space_id=%s OR uid=%s) + '
                '(SELECT count(*) FROM public_conversations WHERE owner_space_id=%s) + '
                '(SELECT count(*) FROM fcm_tokens WHERE uid=%s)',
                (uid, uid, uid, uid, uid),
            ).fetchone()[0]
            conn.execute('DELETE FROM spaces WHERE space_id=%s', (uid,))
            conn.execute('DELETE FROM fcm_tokens WHERE uid=%s', (uid,))
            conn.execute('DELETE FROM memberships WHERE uid=%s', (uid,))
            return total

        return self._run(body)
