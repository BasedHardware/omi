"""Minimal bounded connection pool for the job store.

Cloud Run instances cap the pool at 4 (plan A risk 3: connection storms). psycopg 3 is imported
lazily so importing this package never requires the driver in processes that do not select
Postgres. IAM / Cloud SQL connector auth (A2, staging) plugs in through ``connect=``; the default
dials a DSN directly.
"""

from __future__ import annotations

import queue
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator

MAX_POOL_SIZE = 4


def _psycopg():
    try:
        import psycopg  # pyright: ignore[reportMissingImports]  # psycopg joins the lockfile separately
    except ImportError as exc:  # pragma: no cover - exercised only where the driver is absent
        raise RuntimeError('psycopg 3 is required to use the Postgres job store') from exc
    return psycopg


def dial(dsn: str) -> Any:
    psycopg = _psycopg()
    # autocommit: transaction boundaries are explicit (BEGIN ... COMMIT) in PostgresStore.
    return psycopg.connect(dsn, autocommit=True)


class Pool:
    def __init__(self, dsn: str, *, size: int = MAX_POOL_SIZE, connect: Callable[[], Any] | None = None):
        if not 1 <= size <= MAX_POOL_SIZE:
            raise ValueError(f'pool size must be 1..{MAX_POOL_SIZE}')
        self._connect = connect or (lambda: dial(dsn))
        self._idle: queue.LifoQueue = queue.LifoQueue()
        self._slots = threading.BoundedSemaphore(size)
        self._closed = False

    @contextmanager
    def connection(self, timeout: float = 30.0) -> Iterator[Any]:
        if not self._slots.acquire(timeout=timeout):
            raise TimeoutError('job store pool exhausted')
        conn = None
        try:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                conn = self._connect()
            yield conn
        except BaseException:
            # A connection that failed mid-flight is not reused.
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
            raise
        finally:
            if conn is not None and not self._closed:
                self._idle.put(conn)
            elif conn is not None:
                conn.close()
            self._slots.release()

    def close(self) -> None:
        self._closed = True
        while True:
            try:
                self._idle.get_nowait().close()
            except queue.Empty:
                return
