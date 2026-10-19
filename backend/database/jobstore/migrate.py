"""Versioned, expand-only SQL migrations for the job store.

Files are ``migrations/NNNN_name.sql`` applied in order, each in one transaction, serialized across
processes by a session advisory lock. ``schema_migrations`` records each file's checksum: editing an
applied migration is refused, never silently re-run. A migration may not contract the schema
(DROP / RENAME / ALTER ... TYPE / SET NOT NULL) unless the file carries the explicit
``-- contract: <reason>`` marker; contract steps ship one train after the expand (plan A risk 4).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / 'migrations'
_NAME = re.compile(r'^(\d{4})_([a-z0-9_]+)\.sql$')
_CONTRACTING = re.compile(
    r'\b(DROP\s+(TABLE|COLUMN|INDEX|SCHEMA|CONSTRAINT)|RENAME\s+(TO|COLUMN)|ALTER\s+COLUMN\s+\w+\s+(TYPE|SET\s+NOT\s+NULL)|TRUNCATE)\b',
    re.IGNORECASE,
)
_LOCK_ID = 0x6F6D6A73  # 'omjs'


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


def _strip_comments(sql: str) -> str:
    return re.sub(r'--[^\n]*', '', sql)


def load(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    found: list[Migration] = []
    for path in sorted(directory.glob('*.sql')):
        match = _NAME.match(path.name)
        if not match:
            raise MigrationError(f'bad migration file name: {path.name}')
        found.append(Migration(int(match.group(1)), match.group(2), path.read_text()))
    versions = [m.version for m in found]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(f'migration versions must be contiguous from 1, got {versions}')
    for migration in found:
        if _CONTRACTING.search(_strip_comments(migration.sql)) and '-- contract:' not in migration.sql:
            raise MigrationError(f'{migration.version:04d}_{migration.name} contracts the schema without a marker')
    return found


def migrate(conn: Any, directory: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply pending migrations; return the versions applied by this call."""
    migrations = load(directory)
    applied_now: list[int] = []
    conn.execute('SELECT pg_advisory_lock(%s)', (_LOCK_ID,))
    try:
        conn.execute(
            'CREATE TABLE IF NOT EXISTS schema_migrations ('
            'version int PRIMARY KEY, name text NOT NULL, checksum text NOT NULL, '
            'applied_at timestamptz NOT NULL DEFAULT now())'
        )
        done = {row[0]: row[1] for row in conn.execute('SELECT version, checksum FROM schema_migrations').fetchall()}
        unknown = set(done) - {m.version for m in migrations}
        if unknown:
            raise MigrationError(f'database has migrations this build does not know: {sorted(unknown)}')
        for migration in migrations:
            if migration.version in done:
                if done[migration.version] != migration.checksum:
                    raise MigrationError(f'applied migration {migration.version:04d} was edited')
                continue
            with conn.transaction():
                conn.execute(migration.sql)
                conn.execute(
                    'INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)',
                    (migration.version, migration.name, migration.checksum),
                )
            applied_now.append(migration.version)
    finally:
        conn.execute('SELECT pg_advisory_unlock(%s)', (_LOCK_ID,))
    return applied_now


def current_version(conn: Any) -> int:
    exists = conn.execute("SELECT to_regclass('schema_migrations') IS NOT NULL").fetchone()[0]
    if not exists:
        return 0
    return conn.execute('SELECT coalesce(max(version), 0) FROM schema_migrations').fetchone()[0]
