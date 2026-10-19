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
        # psycopg joins the lockfile separately; until then pyright cannot resolve it.
        import psycopg  # pyright: ignore[reportMissingImports]
    except ImportError as exc:  # pragma: no cover - exercised only where the driver is absent
        raise RuntimeError('psycopg 3 is required to use the Postgres job store') from exc
    return psycopg


def configure(conn: Any) -> Any:
    """Per-connection setup: restore Firestore-native values (datetime, bytes) when reading jsonb."""
    from psycopg.types.json import set_json_loads  # pyright: ignore[reportMissingImports]

    import database.jobstore.codec as codec

    set_json_loads(codec.loads, conn)
    return conn


def dial(dsn: str) -> Any:
    psycopg = _psycopg()
    # autocommit: transaction boundaries are explicit (BEGIN ... COMMIT) in PostgresStore.
    return psycopg.connect(dsn, autocommit=True)


def iam_connector(host: str, database: str, user: str, *, port: int = 5432) -> Callable[[], Any]:
    """Connect to Cloud SQL over its private IP with IAM database auth, no connector library.

    The password is a short-lived OAuth token with the ``sqlservice.login`` scope, minted per connection
    from application default credentials (the service account running the job); TLS is required.
    ``user`` is the IAM database user, e.g. ``staging-runtime@based-hardware-dev.iam`` (the service
    account email without ``.gserviceaccount.com``).
    """

    def connect() -> Any:
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/sqlservice.login'])
        credentials.refresh(Request())
        return _psycopg().connect(
            host=host, port=port, dbname=database, user=user, password=credentials.token, sslmode='require',
            autocommit=True, connect_timeout=10,
        )  # fmt: skip

    return connect


class Pool:
    def __init__(self, dsn: str, *, size: int = MAX_POOL_SIZE, connect: Callable[[], Any] | None = None):
        if not 1 <= size <= MAX_POOL_SIZE:
            raise ValueError(f'pool size must be 1..{MAX_POOL_SIZE}')
        raw = connect or (lambda: dial(dsn))
        self._connect = lambda: configure(raw())
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
