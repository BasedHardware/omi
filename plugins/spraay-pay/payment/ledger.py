"""SQLite transaction log, pending confirmations and memory audit trail.

Limit checks and state changes share one write transaction, so concurrent requests
cannot both pass the daily limit or both claim one confirmation code.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

PENDING, EXECUTING, SETTLED = "pending", "executing", "settled"
FAILED, UNKNOWN, CANCELLED = "failed", "unknown", "cancelled"
NO_PAYMENT = "no_payment_required"
# UNKNOWN counts as spent: a signed payment may still have settled.
_SPENT_STATUSES = (EXECUTING, SETTLED, UNKNOWN)
MAX_CODE_ATTEMPTS = 5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY, uid TEXT NOT NULL, amount_micro INTEGER NOT NULL,
    target TEXT NOT NULL, description TEXT NOT NULL, source TEXT NOT NULL,
    status TEXT NOT NULL, code TEXT, attempts INTEGER NOT NULL DEFAULT 0,
    tx_hash TEXT, error TEXT, created_at REAL NOT NULL, expires_at REAL,
    executed_at REAL
);
CREATE INDEX IF NOT EXISTS payments_uid_status ON payments (uid, status);
CREATE TABLE IF NOT EXISTS memory_mentions (
    uid TEXT NOT NULL, memory_id TEXT NOT NULL, position INTEGER NOT NULL,
    pattern TEXT NOT NULL, excerpt TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY (uid, memory_id, position)
);
"""

Check = Callable[[int, str, int], str | None]


class LimitExceeded(Exception):
    pass


@dataclass(frozen=True)
class Payment:
    id: str
    uid: str
    amount_micro: int
    target: str
    description: str
    source: str
    status: str


def _start_of_utc_day(now: float) -> float:
    return now - now % 86_400


class Ledger:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def _spent(conn: sqlite3.Connection, uid: str, now: float) -> int:
        marks = ",".join("?" * len(_SPENT_STATUSES))
        row = conn.execute(
            f"SELECT COALESCE(SUM(amount_micro), 0) FROM payments "
            f"WHERE uid = ? AND status IN ({marks}) AND executed_at >= ?",
            (uid, *_SPENT_STATUSES, _start_of_utc_day(now)),
        ).fetchone()
        return int(row[0])

    def spent_today(self, uid: str) -> int:
        conn = self._connect()
        try:
            return self._spent(conn, uid, time.time())
        finally:
            conn.close()

    def create_pending(
        self, uid: str, amount_micro: int, target: str, description: str, source: str, code: str, ttl: int
    ) -> str | None:
        """Store a confirmation, or return None if the same one is already open."""
        now = time.time()
        payment_id = uuid.uuid4().hex
        with self._write() as conn:
            duplicate = conn.execute(
                "SELECT 1 FROM payments WHERE uid = ? AND amount_micro = ? AND target = ? "
                "AND status = ? AND expires_at > ?",
                (uid, amount_micro, target, PENDING, now),
            ).fetchone()
            if duplicate:
                return None
            conn.execute(
                "INSERT INTO payments (id, uid, amount_micro, target, description, source, "
                "status, code, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (payment_id, uid, amount_micro, target, description, source, PENDING, code, now, now + ttl),
            )
        return payment_id

    def reserve(
        self, uid: str, amount_micro: int, target: str, description: str, source: str, check: Check
    ) -> Payment:
        """Record an auto-approved payment as executing if ``check`` passes."""
        now = time.time()
        payment_id = uuid.uuid4().hex
        with self._write() as conn:
            if denial := check(amount_micro, target, self._spent(conn, uid, now)):
                raise LimitExceeded(denial)
            conn.execute(
                "INSERT INTO payments (id, uid, amount_micro, target, description, source, "
                "status, created_at, executed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (payment_id, uid, amount_micro, target, description, source, EXECUTING, now, now),
            )
        return Payment(payment_id, uid, amount_micro, target, description, source, EXECUTING)

    def claim(self, uid: str, code: str, check: Check) -> Payment | None:
        """Atomically move the pending payment matching ``code`` to executing.

        Returns None for a wrong or expired code. Repeated wrong codes cancel the
        user's open confirmations so a code cannot be guessed.
        """
        now = time.time()
        with self._write() as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE uid = ? AND code = ? AND status = ? AND expires_at > ?",
                (uid, code, PENDING, now),
            ).fetchone()
            if row is None:
                conn.execute(
                    "UPDATE payments SET attempts = attempts + 1 WHERE uid = ? AND status = ?",
                    (uid, PENDING),
                )
                conn.execute(
                    "UPDATE payments SET status = ? WHERE uid = ? AND status = ? AND attempts >= ?",
                    (CANCELLED, uid, PENDING, MAX_CODE_ATTEMPTS),
                )
                return None
            if denial := check(row["amount_micro"], row["target"], self._spent(conn, uid, now)):
                conn.execute("UPDATE payments SET status = ?, error = ? WHERE id = ?", (CANCELLED, denial, row["id"]))
                return Payment(row["id"], uid, row["amount_micro"], row["target"], row["description"], row["source"], f"denied:{denial}")
            conn.execute(
                "UPDATE payments SET status = ?, executed_at = ? WHERE id = ?", (EXECUTING, now, row["id"])
            )
            return Payment(row["id"], uid, row["amount_micro"], row["target"], row["description"], row["source"], EXECUTING)

    def finish(self, payment_id: str, status: str, tx_hash: str | None = None, error: str | None = None) -> None:
        with self._write() as conn:
            conn.execute(
                "UPDATE payments SET status = ?, tx_hash = ?, error = ? WHERE id = ?",
                (status, tx_hash, error, payment_id),
            )

    def cancel_pending(self, uid: str) -> int:
        with self._write() as conn:
            cursor = conn.execute(
                "UPDATE payments SET status = ? WHERE uid = ? AND status = ? AND expires_at > ?",
                (CANCELLED, uid, PENDING, time.time()),
            )
            return cursor.rowcount

    def get_status(self, payment_id: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT status FROM payments WHERE id = ?", (payment_id,)).fetchone()
            return row["status"] if row else None
        finally:
            conn.close()

    def record_mentions(self, uid: str, memory_id: str, mentions: list[tuple[str, str]]) -> None:
        """Store (pattern, excerpt) pairs. Omi redelivery of a memory is idempotent."""
        now = time.time()
        with self._write() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO memory_mentions (uid, memory_id, position, pattern, excerpt, created_at) "
                "VALUES (?,?,?,?,?,?)",
                [(uid, memory_id, i, pattern, excerpt, now) for i, (pattern, excerpt) in enumerate(mentions)],
            )

    def recurring_patterns(self, uid: str, minimum: int = 2) -> list[dict[str, object]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT pattern, COUNT(DISTINCT memory_id) AS seen FROM memory_mentions "
                "WHERE uid = ? GROUP BY pattern HAVING seen >= ? ORDER BY seen DESC, pattern",
                (uid, minimum),
            ).fetchall()
            return [{"pattern": row["pattern"], "occurrences": row["seen"]} for row in rows]
        finally:
            conn.close()
