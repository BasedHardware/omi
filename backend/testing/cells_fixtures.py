"""B1-owned Postgres harness; the shared jobstore fixture remains unchanged."""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from database.cells import CellStore
from database.directory import DirectoryStore
from database.jobstore.connection import Pool, dial
from database.jobstore.migrate import migrate
from testing.store_fixtures import BackendUnavailable, postgres_dsn, required_backends

_state: dict[str, str] = {}
_lock = threading.Lock()


def _dsn(kind: str) -> str:
    if os.getenv('OMI_TEST_POSTGRES_IAM'):
        raise BackendUnavailable('B1 fixtures do not support IAM conformance')
    with _lock:
        if kind not in _state:
            base = postgres_dsn()
            name = f'omi_{kind}_test'
            with dial(base) as conn:
                if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
                    conn.execute(f'CREATE DATABASE {name}')  # fixed names, never caller SQL
                # libpq accepts the last occurrence of a setting. Preserve private
                # socket host/port while replacing only the database.
                # URI DSNs need a keyword expansion instead of string concatenation.
                params = dict(conn.info.get_parameters())
                params['dbname'] = name
                target = ' '.join(
                    f"{k}='" + v.replace('\\', '\\\\').replace("'", "\\'") + "'" for k, v in params.items()
                )
            with dial(target) as conn:
                migrate(conn, directory=Path(__file__).parents[1] / 'database' / kind / 'migrations')
            _state[kind] = target
        return _state[kind]


def cells_dsn() -> str:
    return _dsn('cells')


def directory_dsn() -> str:
    return _dsn('directory')


@dataclass
class Harness:
    store: Any
    prefix: str
    seeded: set[str] = field(default_factory=lambda: set[str]())

    def uid(self, label: str = 'space') -> str:
        uid = f'{self.prefix}-{label}'
        self.seeded.add(uid)
        return uid

    def close(self) -> None:
        try:
            for uid in self.seeded:
                if isinstance(self.store, CellStore):
                    self.store.purge_space(uid)
                else:
                    self.store.purge_owner(uid, now=0)
        finally:
            self.store.pool.close()


def _make(kind: str) -> Harness:
    try:
        dsn = cells_dsn() if kind == 'cells' else directory_dsn()
    except BackendUnavailable as exc:
        if 'postgres' in required_backends():
            pytest.fail(str(exc))
        pytest.skip(str(exc))
    pool = Pool(dsn, size=2)
    store = CellStore(pool) if kind == 'cells' else DirectoryStore(pool)
    return Harness(store, 'b1-' + uuid.uuid4().hex[:12])


def make_cell_store() -> Harness:
    return _make('cells')


def make_directory() -> Harness:
    return _make('directory')
