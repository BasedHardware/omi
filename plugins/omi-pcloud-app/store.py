"""Encrypted durable state for the standalone, persistent-volume deployment.

SQLite transactions own nonce consumption, job admission and worker leases.
Per-account OS locks serialize settings/disconnect with each provider operation.
There is no automatic fallback from a failed production store to local files.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

DEFAULT_SETTINGS = {
    'folder_name': 'Omi Conversations',
    'save_summary': True,
    'save_transcript': False,
    'save_audio': False,
    'consent_version': 0,
}
JOB_RETENTION_SECONDS = 7 * 86400


class Store:
    def __init__(self, path: str, keys: list[str]):
        if not Path(path).is_absolute() or not keys:
            raise ValueError('Configure an absolute PCLOUD_DB_PATH and PCLOUD_ENCRYPTION_KEYS')
        self.path = Path(path)
        self.cipher = MultiFernet([Fernet(key.encode()) for key in keys])

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        os.chmod(self.path, 0o600)
        try:
            conn.execute('PRAGMA busy_timeout=5000')
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute(
                'CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, uid TEXT, blob BLOB, expires REAL, PRIMARY KEY(kind,id))'
            )
            conn.execute(
                'CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, uid TEXT, blob BLOB, state TEXT, due REAL, lease TEXT, expires REAL)'
            )
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def seal(self, uid: str, data: dict) -> bytes:
        return self.cipher.encrypt(json.dumps({'uid': uid, 'data': data}, ensure_ascii=True).encode())

    def open(self, uid: str, blob: bytes) -> dict:
        envelope = json.loads(self.cipher.decrypt(blob))
        if envelope.get('uid') != uid:
            raise ValueError('Stored principal does not match record owner')
        return envelope['data']

    @contextmanager
    def account_lock(self, uid: str):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        digest = hashlib.sha256(uid.encode()).hexdigest()
        with (self.path.parent / f'.account-{digest}.lock').open('a+b') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def get(self, kind: str, identity: str, *, consume: bool = False) -> dict | None:
        with self.transaction() as conn:
            row = conn.execute(
                'SELECT uid,blob,expires FROM records WHERE kind=? AND id=?',
                (kind, identity),
            ).fetchone()
            if row is None:
                return None
            if consume or row[2] <= time.time():
                conn.execute('DELETE FROM records WHERE kind=? AND id=?', (kind, identity))
            if row[2] <= time.time():
                return None
            return self.open(row[0], row[1])

    def put(
        self,
        kind: str,
        identity: str,
        uid: str,
        data: dict,
        ttl: int = JOB_RETENTION_SECONDS,
    ):
        with self.transaction() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)',
                (kind, identity, uid, self.seal(uid, data), time.time() + ttl),
            )

    def delete(self, kind: str, identity: str):
        with self.transaction() as conn:
            conn.execute('DELETE FROM records WHERE kind=? AND id=?', (kind, identity))

    def consume_nonce(self, identity: str, uid: str, ttl: int) -> bool:
        with self.transaction() as conn:
            conn.execute('DELETE FROM records WHERE expires<=?', (time.time(),))
            try:
                conn.execute(
                    'INSERT INTO records VALUES (?,?,?,?,?)',
                    ('used', identity, uid, self.seal(uid, {}), time.time() + ttl),
                )
            except sqlite3.IntegrityError:
                return False
            return True

    def settings(self, uid: str) -> dict:
        settings = {**DEFAULT_SETTINGS, **(self.get('settings', uid) or {})}
        # Old/missing consent versions are never treated as a transcript/audio grant.
        if settings.get('consent_version') != 1:
            settings.update(save_transcript=False, save_audio=False)
        return settings

    def check_ready(self):
        with self.transaction() as conn:
            row = conn.execute(
                'SELECT uid,blob FROM records WHERE kind=? AND id=?',
                ('meta', 'encryption-canary'),
            ).fetchone()
            if row is None:
                sample = conn.execute('SELECT uid,blob FROM records LIMIT 1').fetchone()
                if sample:
                    self.open(sample[0], sample[1])
                conn.execute(
                    'INSERT INTO records VALUES (?,?,?,?,?)',
                    (
                        'meta',
                        'encryption-canary',
                        '__service__',
                        self.seal('__service__', {'schema': 1}),
                        time.time() + 10 * 365 * 86400,
                    ),
                )
            else:
                self.open(row[0], row[1])

    # An expired or canceled backup is a scrubbed tombstone, not a delivery to
    # deduplicate: a fresh authenticated delivery (re-export, or reconnect after
    # disconnect) replaces it. Active, failed, completed and unreadable rows keep
    # deduplicating so a backup is never uploaded twice or a restore is lost.
    REPLACEABLE_JOB_STATES = ('expired', 'canceled')

    def enqueue(self, uid: str, conversation_id: str, payload: dict) -> str:
        identity = hashlib.sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest()
        with self.transaction() as conn:
            row = conn.execute('SELECT state FROM jobs WHERE id=?', (identity,)).fetchone()
            if row and row[0] not in self.REPLACEABLE_JOB_STATES:
                return identity
            count = conn.execute(
                'SELECT COUNT(*) FROM jobs WHERE uid=? AND state NOT IN (?,?,?)',
                (uid, 'completed', 'canceled', 'expired'),
            ).fetchone()[0]
            if count >= 100:
                raise OverflowError('Too many unfinished backups. Review failed backups before trying again.')
            payload.update(id=identity, attempt=0, uploaded=[], error=None)
            now = time.time()
            if row:
                conn.execute(
                    'UPDATE jobs SET blob=?,state=?,due=?,lease=?,expires=? WHERE id=?',
                    (self.seal(uid, payload), 'pending', now, '', now + JOB_RETENTION_SECONDS, identity),
                )
                return identity
            conn.execute(
                'INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                (
                    identity,
                    uid,
                    self.seal(uid, payload),
                    'pending',
                    now,
                    '',
                    now + JOB_RETENTION_SECONDS,
                ),
            )
        return identity

    def jobs(self, uid: str) -> list[dict]:
        # The 30 most recent jobs, plus every older one the owner can still act on.
        # Unfinished jobs are capped at 100 per account, so this stays bounded.
        with self.transaction() as conn:
            rows = conn.execute(
                'SELECT id,blob,state,expires FROM jobs WHERE uid=? AND ('
                'rowid IN (SELECT rowid FROM jobs WHERE uid=? ORDER BY rowid DESC LIMIT 30) '
                'OR state IN (?,?)) ORDER BY rowid DESC',
                (uid, uid, 'failed', 'pending'),
            ).fetchall()
            result = []
            for identity, blob, state, expires in rows:
                try:
                    payload = self.open(uid, blob)
                except (InvalidToken, ValueError, TypeError):
                    payload = {
                        'uploaded': [],
                        'error': 'Stored backup cannot be read. Contact the app administrator to restore it from backup.',
                    }
                    state = 'unreadable'
                result.append({**payload, 'id': identity, 'state': state, 'expires': expires})
            return result

    def job_state(self, uid: str, identity: str) -> str:
        with self.transaction() as conn:
            row = conn.execute('SELECT state FROM jobs WHERE uid=? AND id=?', (uid, identity)).fetchone()
            return row[0] if row else 'missing'

    def claim(self) -> tuple[str, str, str, dict] | None:
        with self.transaction() as conn:
            now = time.time()
            conn.execute('DELETE FROM records WHERE expires<=?', (now,))
            conn.execute('DELETE FROM jobs WHERE expires<?', (now - 30 * 86400,))
            # Expiry removes private job payloads, not just their queue visibility.
            # Completed and canceled jobs hold no payload, only their per-file
            # receipts, which must stay visible until the row is removed.
            for identity, uid in conn.execute(
                'SELECT id,uid FROM jobs WHERE expires<=? AND state NOT IN (?,?,?)',
                (now, 'expired', 'completed', 'canceled'),
            ).fetchall():
                conn.execute(
                    'UPDATE jobs SET blob=?,state=?,lease=? WHERE id=?',
                    (
                        self.seal(
                            uid,
                            {
                                'id': identity,
                                'uploaded': [],
                                'error': 'Backup expired after seven days. Re-export the conversation from Omi.',
                            },
                        ),
                        'expired',
                        '',
                        identity,
                    ),
                )
            row = conn.execute(
                'SELECT id,uid,blob FROM jobs WHERE state IN (?,?) AND due<=? AND expires>? ORDER BY due LIMIT 1',
                ('pending', 'running', now, now),
            ).fetchone()
            if row is None:
                return None
            identity, uid, blob = row
            try:
                payload = self.open(uid, blob)
            except (InvalidToken, ValueError, TypeError):
                # Preserve the original ciphertext for restore; do not strand
                # unrelated accounts behind one unreadable queue head.
                conn.execute('UPDATE jobs SET state=? WHERE id=?', ('unreadable', identity))
                return None
            lease = secrets.token_urlsafe(24)
            conn.execute(
                'UPDATE jobs SET state=?,due=?,lease=? WHERE id=?',
                ('running', now + 300, lease, identity),
            )
            return identity, uid, lease, payload

    def settle(
        self,
        identity: str,
        uid: str,
        lease: str,
        payload: dict,
        state: str,
        delay: int = 0,
    ):
        with self.transaction() as conn:
            changed = conn.execute(
                'UPDATE jobs SET blob=?,state=?,due=? WHERE id=? AND uid=? AND lease=?',
                (
                    self.seal(uid, payload),
                    state,
                    time.time() + delay,
                    identity,
                    uid,
                    lease,
                ),
            ).rowcount
            if changed != 1:
                raise RuntimeError('Backup worker lease is no longer current')

    def retry(self, uid: str, identity: str) -> bool:
        with self.transaction() as conn:
            row = conn.execute(
                'SELECT blob,state,expires FROM jobs WHERE uid=? AND id=?',
                (uid, identity),
            ).fetchone()
            if not row or row[1] not in ('failed', 'pending') or row[2] <= time.time():
                return False
            payload = self.open(uid, row[0])
            payload.update(attempt=0, error=None)
            conn.execute(
                'UPDATE jobs SET blob=?,state=?,due=?,lease=? WHERE uid=? AND id=?',
                (self.seal(uid, payload), 'pending', time.time(), '', uid, identity),
            )
            return True

    def cancel_jobs(self, uid: str):
        with self.transaction() as conn:
            rows = conn.execute(
                'SELECT id,blob FROM jobs WHERE uid=? AND state NOT IN (?,?,?)',
                (uid, 'completed', 'canceled', 'expired'),
            ).fetchall()
            for identity, blob in rows:
                try:
                    previous = self.open(uid, blob)
                except (InvalidToken, ValueError, TypeError, KeyError):
                    previous = {}
                # Keep truthful receipts, not private export payloads or tokens.
                receipt = {
                    'id': identity,
                    'title': previous.get('title', 'Conversation'),
                    'uploaded': previous.get('uploaded', []),
                    'error': 'Backup canceled on disconnect.',
                }
                conn.execute(
                    'UPDATE jobs SET state=?,blob=?,lease=? WHERE id=?',
                    (
                        'canceled',
                        self.seal(uid, receipt),
                        '',
                        identity,
                    ),
                )

    def rotate_keys(self):
        """Rewrap all ciphertext with the first configured key, atomically."""
        with self.transaction() as conn:
            for kind, identity, blob in conn.execute('SELECT kind,id,blob FROM records').fetchall():
                conn.execute(
                    'UPDATE records SET blob=? WHERE kind=? AND id=?',
                    (self.cipher.rotate(blob), kind, identity),
                )
            for identity, blob in conn.execute('SELECT id,blob FROM jobs').fetchall():
                conn.execute(
                    'UPDATE jobs SET blob=? WHERE id=?',
                    (self.cipher.rotate(blob), identity),
                )


def configured_store() -> Store:
    return Store(
        os.environ.get('PCLOUD_DB_PATH', ''),
        json.loads(os.environ.get('PCLOUD_ENCRYPTION_KEYS', '[]')),
    )
