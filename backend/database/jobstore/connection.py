"""Minimal bounded connection pool for the job store.

Cloud Run instances cap the pool at 4 (plan A risk 3: connection storms). psycopg 3 is imported
lazily so importing this package never requires the driver in processes that do not select
Postgres. IAM / Cloud SQL connector auth (A2, staging) plugs in through ``connect=``; the default
dials a DSN directly.
"""

from __future__ import annotations

import queue
import time
import math
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


def sql() -> Any:
    """Return psycopg's SQL composition helpers without making the driver a package import requirement."""
    return _psycopg().sql  # pyright: ignore[reportAttributeAccessIssue]


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


def iam_connector(
    host: str, database: str, user: str, *, port: int = 5432, setup_timeout_s: float | None = None
) -> Callable[[], Any]:
    """Connect to Cloud SQL over its private IP with IAM database auth, no connector library.

    The password is a short-lived OAuth token with the ``sqlservice.login`` scope, minted per connection
    from application default credentials (the service account running the job); TLS is required.
    ``user`` is the IAM database user, e.g. ``staging-runtime@based-hardware-dev.iam`` (the service
    account email without ``.gserviceaccount.com``).
    """

    def connect() -> Any:
        import google.auth
        from google.auth.transport.requests import Request

        deadline = time.monotonic() + setup_timeout_s if setup_timeout_s is not None else None
        request = Request()

        def bounded_request(*args, **kwargs):
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('jobstore IAM setup deadline exceeded')
                kwargs['timeout'] = min(float(kwargs.get('timeout') or remaining), remaining)
            return request(*args, **kwargs)

        credentials, _ = google.auth.default(
            scopes=['https://www.googleapis.com/auth/sqlservice.login'], request=bounded_request
        )
        credentials.refresh(bounded_request)
        # libpq's minimum effective connect timeout is two seconds. Refuse a
        # new dial when that minimum cannot fit in the remaining setup budget.
        remaining = deadline - time.monotonic() if deadline is not None else 10.0
        if remaining < 2:
            raise TimeoutError('jobstore IAM setup deadline exceeded')
        conn = _psycopg().connect(
            host=host, port=port, dbname=database, user=user, password=credentials.token, sslmode='require',
            autocommit=True, connect_timeout=max(2, math.floor(remaining)),
        )  # fmt: skip
        if deadline is not None and time.monotonic() >= deadline:
            conn.close()
            raise TimeoutError('jobstore IAM setup deadline exceeded')
        return conn

    return connect


class Pool:
    def __init__(self, dsn: str, *, size: int = MAX_POOL_SIZE, connect: Callable[[], Any] | None = None):
        if not 1 <= size <= MAX_POOL_SIZE:
            raise ValueError(f'pool size must be 1..{MAX_POOL_SIZE}')
        self._connect = connect or (lambda: dial(dsn))
        self._idle: queue.LifoQueue = queue.LifoQueue()
        self._slots = threading.BoundedSemaphore(size)
        self._closed = False

    @contextmanager
    def connection(self, timeout: float = 30.0, *, existing_only: bool = False) -> Iterator[Any]:
        if not self._slots.acquire(timeout=timeout):
            raise TimeoutError('job store pool exhausted')
        conn = None
        try:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                if existing_only:
                    # Observers must not enter unbounded credential refresh/connection setup.
                    raise TimeoutError('job store observation requires a warm connection')
                conn = self._connect()
                # Own the raw connection before setup so failed configuration closes it.
                configure(conn)
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
