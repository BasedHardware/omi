"""Transaction-owned, target-bound checkpoints. Never log instances or SQL errors."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from database.jobstore.dual_store import MIRRORED_TABLES
from database.jobstore.reconcile import PageResult, decode_cursor


@dataclass(frozen=True)
class CursorScope:
    namespace: str
    source: str
    table: str
    mode: str
    target_identity: str = field(repr=False)

    @classmethod
    def for_target(cls, namespace: str, source: str, table: str, apply: bool, target: tuple[str, str, str]):
        if source not in {'primary', 'copy'} or table not in MIRRORED_TABLES or not all(target):
            raise ValueError('invalid retirement scope')
        identity = hashlib.sha256(json.dumps(target, separators=(',', ':')).encode()).hexdigest()
        return cls(namespace, source, table, 'apply' if apply else 'dry_run', identity)

    @property
    def params(self) -> tuple:
        return self.namespace, self.source, self.table, self.mode, self.target_identity


class CursorPage:
    def __init__(self, scope: CursorScope):
        self.scope = scope
        self._loaded = False
        self._cursor = None
        self._version = None
        self.timestamps = None

    def load(self, conn: Any) -> str | None:
        conn.execute(
            'INSERT INTO jobstore_retirement_cursor (namespace, source, tbl, mode, target_identity) '
            'VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING',
            self.scope.params,
        )
        row = conn.execute(
            'SELECT cursor, version FROM jobstore_retirement_cursor '
            'WHERE namespace = %s AND source = %s AND tbl = %s AND mode = %s AND target_identity = %s FOR UPDATE',
            self.scope.params,
        ).fetchone()
        if row is None:
            raise RuntimeError('retirement cursor disappeared')
        self._cursor, self._version = row
        decode_cursor(self._cursor, self.scope.namespace, self.scope.source, self.scope.table)
        self._loaded = True
        return self._cursor

    def advance(self, conn: Any, result: PageResult) -> None:
        if not self._loaded:
            raise RuntimeError('retirement cursor must be locked before advance')
        previous = decode_cursor(self._cursor, self.scope.namespace, self.scope.source, self.scope.table)
        following = decode_cursor(result.cursor, self.scope.namespace, self.scope.source, self.scope.table)
        if result.end_of_pass != (following is None) or (
            not result.end_of_pass and (following is None or (previous is not None and following <= previous))
        ):
            raise ValueError('retirement cursor regression refused')
        row = conn.execute(
            'UPDATE jobstore_retirement_cursor SET cursor = %s, version = version + 1, passes = passes + %s, '
            'updated_at = clock_timestamp(), '
            'rotation_completed_at = CASE WHEN %s THEN clock_timestamp() ELSE rotation_completed_at END '
            'WHERE namespace = %s AND source = %s AND tbl = %s AND mode = %s AND target_identity = %s '
            'AND version = %s AND cursor IS NOT DISTINCT FROM %s '
            'RETURNING created_at, rotation_completed_at, updated_at',
            (
                result.cursor,
                int(result.end_of_pass),
                result.end_of_pass,
                *self.scope.params,
                self._version,
                self._cursor,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError('retirement cursor compare-and-set refused')
        self.timestamps = row
        self._loaded = False
