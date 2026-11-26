"""Write a :class:`StartState` into the lab emulator.

:class:`ProductSeedWriter` writes through the product's own database helpers so
storage shape, encryption and derived indexes match what the product reads back.
It must run inside :func:`testing.pipeline_lab.stack.env.lab_environment`.

Conversations are history, not new processing results: each row is encoded with the
product's harness seam ``database.conversations.encode_conversation_for_write`` (the exact
stored shape) and written in batches. The per-row processing upsert would re-run title
stability, the processing backlog, summary delivery and a search-index sync for every
historical row (seconds each, and wrong for rows that finished long ago). Refs without the
seam fall back to that upsert.

A row that cannot be written is never dropped silently: it is counted per kind and reason
in ``skipped`` and surfaced as a run warning. Fields the lab cannot read (blobs still sealed
under production's key) are cleared and counted in ``cleared``; the product reads an
undecodable blob as absent, so a cleared one behaves the same.

:func:`reset_lab_user` deletes the lab user's documents before a re-seed. It is
guarded by :func:`assert_lab_target`: only ``local-dev-user`` on a loopback
emulator of a ``demo-*`` project can ever be deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
from typing import Any, Callable, Mapping, Protocol

from testing.pipeline_lab.stack import LAB_UID
from testing.pipeline_lab.seed.start_state import StartState
from testing.pipeline_lab.stack.io import parse_time

TIME_KEYS = frozenset({'start_time', 'end_time', 'timestamp', 'date_time'})


def restore_times(value: Any, key: str = '') -> Any:
    """ISO strings back to datetimes for time-named keys only (``*_at`` and a few others).

    Field-aware on purpose: a title that happens to look like a date stays a string.
    """
    if isinstance(value, dict):
        return {k: restore_times(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [restore_times(item, key) for item in value]
    if isinstance(value, str) and (key.endswith('_at') or key in TIME_KEYS) and 'T' in value:
        parsed = parse_time(value)
        return parsed if parsed is not None else value
    return value


# Protected JSON blobs the product decodes with the owner's key: (field, compressed marker, empty value).
# A snapshot keeps them as stored, so one written under enhanced protection is production ciphertext.
SEALED_BLOBS: tuple[tuple[str, str, Any], ...] = (
    ('open_loop_extractions', 'open_loop_extractions_compressed', None),
    ('manual_speaker_assignments', 'manual_speaker_assignments_compressed', {}),
    ('user_corrections', 'user_corrections_compressed', []),
)
BATCH_SIZE = 200  # under Firestore's 500-write batch limit, with room for large encoded rows


def clear_sealed_blobs(row: dict[str, Any]) -> list[str]:
    """Clear blobs that are still ciphertext (a string where the product expects JSON). Returns their names."""
    cleared = []
    for name, marker, empty in SEALED_BLOBS:
        if isinstance(row.get(name), (str, bytes)) and row.get(name):
            row[name] = empty
            if marker in row:
                row[marker] = None
            cleared.append(name)
    return cleared


def _too_large(error: BaseException) -> bool:
    text = str(error).lower()
    return 'maximum entity size' in text or 'request payload size exceeds' in text or 'too big' in text


def _reason(error: BaseException) -> str:
    """A short, content-free reason: the exception type and its message up to the first colon."""
    message = str(error).split(':', 1)[0].strip()[:80]
    return f'{type(error).__name__}: {message}' if message else type(error).__name__


REVIVED_TIME_FIELDS = ('summary_covers_through', 'v3_pending_since', 'recorded_start', 'recorded_end')


def revive_claim_times(row: dict[str, Any]) -> dict[str, Any]:
    """A v3 recording's ``claims`` hold Firestore timestamps; the corpus stores them as ISO strings.

    The planner compares claim spans with segment datetimes (``planner._contains_line``), so a
    string span fails with ``TypeError`` on every reconcile.
    """
    # Product time fields whose names don't end in ``_at``; refinement compares
    # ``summary_covers_through >= finished_at`` and a string fails every pass with ``TypeError``.
    for key in REVIVED_TIME_FIELDS:
        if isinstance(row.get(key), str):
            parsed = parse_time(row[key])
            if parsed is not None:
                row[key] = parsed
    claims = row.get('claims')
    if isinstance(claims, list):
        row['claims'] = [
            (
                {**c, **{k: parse_time(c[k]) for k in ('start', 'end') if isinstance(c.get(k), str)}}
                if isinstance(c, dict)
                else c
            )
            for c in claims
        ]
    return row


class SeedTargetRefused(PermissionError):
    pass


def assert_lab_target(uid: str, *, environ: dict[str, str] | None = None, project: str | None = None) -> None:
    env = os.environ if environ is None else environ
    if uid != LAB_UID:
        raise SeedTargetRefused('the lab only writes or deletes the synthetic lab uid')
    host = env.get('FIRESTORE_EMULATOR_HOST', '')
    name, _, port = host.rpartition(':')
    if name not in ('127.0.0.1', 'localhost') or not port.isdigit():
        raise SeedTargetRefused('seeding requires a loopback FIRESTORE_EMULATOR_HOST')
    project = project if project is not None else env.get('GOOGLE_CLOUD_PROJECT', '')
    if not project.startswith('demo-'):
        raise SeedTargetRefused('seeding requires a demo-* emulator project')


def _delete_tree(document_ref: Any, *, batch_size: int = 200) -> int:
    deleted = 0
    for collection in document_ref.collections():
        while True:
            docs = list(collection.limit(batch_size).stream())
            if not docs:
                break
            for doc in docs:
                deleted += _delete_tree(doc.reference, batch_size=batch_size)
                doc.reference.delete()
                deleted += 1
    return deleted


def reset_lab_user(client: Any, uid: str = LAB_UID, *, environ: dict[str, str] | None = None) -> int:
    """Delete ``users/<uid>`` and everything under it. Guarded; returns the count.

    A real client deletes with ``recursive_delete`` (bulk writes); a test double walks the tree.
    """
    assert_lab_target(uid, environ=environ, project=getattr(client, 'project', None))
    user_ref = client.collection('users').document(uid)
    if callable(getattr(client, 'recursive_delete', None)):
        deleted = int(client.recursive_delete(user_ref) or 0)
        user_ref.delete()
        return deleted
    deleted = _delete_tree(user_ref)
    user_ref.delete()
    return deleted + 1


def _uid_hash(uid: str) -> str:
    import hashlib

    return hashlib.sha256(uid.encode('utf-8')).hexdigest()


def _delete_ref(client: Any, ref: Any) -> int:
    if callable(getattr(client, 'recursive_delete', None)):
        deleted = int(client.recursive_delete(ref) or 0)  # counts the document itself when it had one
        ref.delete()
        return max(deleted, 1)
    deleted = _delete_tree(ref)
    ref.delete()
    return deleted + 1


# ``users`` is reset as a tree; the privacy authority must survive deletion (database.batch_privacy_write_fence).
KEPT_ON_RESET = frozenset({'users', 'batch_pipeline_privacy'})


# A scenario run on a shared redis-server owns one database number, held by this lease key in that
# database (value: the run id). See ``scenario/stack.py`` (``RedisSlots``).
REDIS_LEASE_KEY = 'pipeline_lab:lease'


def redis_db_of(redis_client: Any) -> int:
    kwargs = getattr(getattr(redis_client, 'connection_pool', None), 'connection_kwargs', None) or {}
    return int(kwargs.get('db') or 0)


def reset_leased_redis_db(redis_client: Any, run_id: str) -> int:
    """Delete every key in the client's database but the lease, only while ``run_id`` holds it.

    Refuses database 0 (a dev stack's) and a database another run holds: the reset must never reach
    past this run's namespace.
    """
    db = redis_db_of(redis_client)
    if db == 0:
        raise SeedTargetRefused('a leased reset never touches Redis database 0')
    holder = redis_client.get(REDIS_LEASE_KEY)
    if isinstance(holder, bytes):
        holder = holder.decode()
    if holder != run_id:
        raise SeedTargetRefused(f'Redis database {db} is not leased to this run')
    deleted, batch = 0, []
    for key in redis_client.scan_iter(count=1000):
        if (key.decode() if isinstance(key, bytes) else key) == REDIS_LEASE_KEY:
            continue
        batch.append(key)
        if len(batch) >= 500:
            deleted += int(redis_client.delete(*batch) or 0)
            batch = []
    if batch:
        deleted += int(redis_client.delete(*batch) or 0)
    return deleted


def reset_lab_state(
    client: Any,
    redis_client: Any = None,
    uid: str = LAB_UID,
    *,
    environ: dict[str, str] | None = None,
    redis_lease: str | None = None,
) -> dict[str, int]:
    """Everything a previous run left for the lab uid, so a re-run starts from the same state. Guarded.

    - ``users/<uid>`` and its subcollections;
    - top-level documents owned by the uid: field ``uid == uid`` (finalization jobs, routing), or a
      document id equal to the uid or its sha256 (dream schedule, memory maintenance, privacy memo);
    - Redis keys naming the uid or its sha256 (locks such as ``daily_summary_lock:<date>``, caches).

    With ``redis_lease`` (a run id holding the client's Redis database, see ``reset_leased_redis_db``),
    the whole database but the lease is cleared instead: on an isolated run, global keys are the run's too.

    Global counters and shards are not per user and stay, and so does ``batch_pipeline_privacy``: the
    product's write fence keeps that authority through deletion on purpose. A delete the product
    still refuses is counted in ``refused``. Without this reset, a second run of the same day finds
    the first run's finalization jobs and daily-summary lock and takes different product paths.
    """
    assert_lab_target(uid, environ=environ, project=getattr(client, 'project', None))
    counts = {'user_tree': reset_lab_user(client, uid, environ=environ), 'top_level': 0, 'redis': 0, 'refused': 0}
    hashed = _uid_hash(uid)
    collections = getattr(client, 'collections', None)
    if callable(collections):
        from google.cloud.firestore_v1 import FieldFilter

        def delete(ref: Any) -> None:
            try:
                counts['top_level'] += _delete_ref(client, ref)
            except Exception:  # noqa: BLE001 - a product fence refused it; counted, never fatal
                counts['refused'] += 1

        for collection in collections():
            if collection.id in KEPT_ON_RESET:
                continue
            for doc in collection.where(filter=FieldFilter('uid', '==', uid)).stream():
                delete(doc.reference)
            for doc_id in (uid, hashed):
                ref = collection.document(doc_id)
                if ref.get().exists:
                    delete(ref)
    if redis_client is not None and redis_lease is not None:
        counts['redis'] = reset_leased_redis_db(redis_client, redis_lease)
    elif redis_client is not None:
        for pattern in (f'*{uid}*', f'*{hashed}*'):
            batch = []
            for key in redis_client.scan_iter(match=pattern, count=1000):
                batch.append(key)
                if len(batch) >= 500:
                    counts['redis'] += int(redis_client.delete(*batch) or 0)
                    batch = []
            if batch:
                counts['redis'] += int(redis_client.delete(*batch) or 0)
    return counts


class SeedWriter(Protocol):
    def write(self, state: StartState) -> dict[str, int]: ...


@dataclass
class RecordingSeedWriter:
    """Test double: records what would be written."""

    written: dict[str, list[Any]] = field(default_factory=dict)

    def write(self, state: StartState) -> dict[str, int]:
        self.written = {'profile': [state.profile], 'fcm_tokens': [state.fcm_token], **state.entities()}
        return {kind: len(rows) for kind, rows in self.written.items()}


@dataclass
class ProductSeedWriter:
    """Write via ``database.*`` helpers. Emulator only.

    ``on_error`` (kind, error) observes every failed write; with ``strict=True`` a failure raises.
    After :meth:`write`: ``skipped`` {kind: {reason: n}}, ``cleared`` {field: n}, ``timings`` {phase: s}.
    """

    client: Any
    on_error: Callable[[str, Exception], None] | None = None
    strict: bool = False
    errors: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, dict[str, int]] = field(default_factory=dict)
    cleared: dict[str, int] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)

    def _fail(self, kind: str, error: Exception) -> None:
        self.errors[kind] = self.errors.get(kind, 0) + 1
        reasons = self.skipped.setdefault(kind, {})
        reasons[_reason(error)] = reasons.get(_reason(error), 0) + 1
        if self.on_error is not None:
            self.on_error(kind, error)
        if self.strict:
            raise error

    def _timed(self, phase: str, started: float) -> None:
        self.timings[phase] = round(self.timings.get(phase, 0.0) + time.perf_counter() - started, 3)

    def write_conversations(self, uid: str, rows: list[dict[str, Any]], conversations_db: Any = None) -> int:
        if conversations_db is None:
            from database import conversations as conversations_db

        encode = getattr(conversations_db, 'encode_conversation_for_write', None)
        collection = self.client.collection('users').document(uid).collection('conversations')
        written = 0
        batch, pending = self.client.batch(), 0
        for row in rows:
            row = revive_claim_times(dict(row))
            for name in clear_sealed_blobs(row):
                self.cleared[name] = self.cleared.get(name, 0) + 1
            if encode is None:
                try:
                    conversations_db.upsert_conversation_with_lifecycle(uid, row)
                    written += 1
                except Exception as error:  # noqa: BLE001 - reported per kind and reason
                    self._fail('conversations', error)
                continue
            for name in ('updated_at', 'audio_base64_url', 'photos'):  # as the product's upsert does
                row.pop(name, None)
            try:
                data = encode(uid, row, str(row.get('data_protection_level') or 'standard'))
            except Exception as error:  # noqa: BLE001
                self._fail('conversations', error)
                continue
            batch.set(collection.document(str(row['id'])), data)
            pending += 1
            if pending >= BATCH_SIZE:
                written += self._commit(batch, pending, 'conversations')
                batch, pending = self.client.batch(), 0
        if pending:
            written += self._commit(batch, pending, 'conversations')
        return written

    def _commit(self, batch: Any, size: int, kind: str) -> int:
        try:
            batch.commit()
            return size
        except Exception as error:  # noqa: BLE001
            for _ in range(size):
                self._fail(kind, error)
            return 0

    def index_conversations(self, uid: str, rows: list[Mapping[str, Any]]) -> int:
        """Search-index the seeded rows when the product's index writes are on (the upsert did this per row)."""
        try:
            from utils.conversations import typesense_index
        except Exception:  # noqa: BLE001 - refs without the dual-write index
            return 0
        if not typesense_index.conversation_index_writes_enabled():
            return 0
        return sum(
            1 for row in rows if typesense_index.sync_conversation_index_after_write(uid, str(row['id'])) is True
        )

    def write(self, state: StartState) -> dict[str, int]:
        assert_lab_target(state.uid, project=getattr(self.client, 'project', None))
        from database import action_items as action_items_db
        from database import daily_summaries as daily_summaries_db
        from database import memories as memories_db
        from database import notifications as notification_db
        from database import users as users_db
        from database import goals as goals_db

        uid = state.uid
        counts: dict[str, int] = {}
        started = time.perf_counter()
        self.client.collection('users').document(uid).set(restore_times(dict(state.profile)), merge=True)
        counts['profile'] = 1
        notification_db.save_token(uid, dict(state.fcm_token), firestore_client=self.client)
        counts['fcm_tokens'] = 1
        state_rows = {kind: [restore_times(row) for row in rows] for kind, rows in state.entities().items()}
        self._timed('profile', started)

        started = time.perf_counter()
        counts['conversations'] = self.write_conversations(uid, state_rows['conversations'])
        self._timed('conversations', started)
        started = time.perf_counter()
        counts['conversations_indexed'] = self.index_conversations(uid, state_rows['conversations'])
        self._timed('conversations_index', started)

        for kind, rows, write_one in (
            ('people', state_rows['people'], lambda row: users_db.create_person(uid, row)),
            ('goals', state_rows['goals'], lambda row: self.write_goal(goals_db, uid, row)),
            (
                'daily_summaries',
                state_rows['daily_summaries'],
                lambda row: daily_summaries_db.create_daily_summary(uid, row),
            ),
        ):
            started = time.perf_counter()
            counts[kind] = 0
            for row in rows:
                try:
                    write_one(dict(row))
                    counts[kind] += 1
                except Exception as error:  # noqa: BLE001 - reported per kind
                    self._fail(kind, error)
            self._timed(kind, started)
        started = time.perf_counter()
        counts['memories'] = 0
        for start in range(0, len(state_rows['memories']), BATCH_SIZE):
            chunk = [dict(row) for row in state_rows['memories'][start : start + BATCH_SIZE]]
            counts['memories'] += self.save_memories(
                lambda rows: memories_db.save_memories(uid, rows, firestore_client=self.client), chunk
            )
        self._timed('memories', started)
        started = time.perf_counter()
        counts['action_items'] = 0
        for start in range(0, len(state_rows['action_items']), BATCH_SIZE):
            chunk = [dict(row) for row in state_rows['action_items'][start : start + BATCH_SIZE]]
            try:
                action_items_db.create_action_items_batch(uid, chunk, document_ids=[row.get('id') for row in chunk])
                counts['action_items'] += len(chunk)
            except Exception as error:  # noqa: BLE001
                for _ in chunk:
                    self._fail('action_items', error)
        self._timed('action_items', started)
        meetings = self.client.collection('users').document(uid).collection('meetings')
        counts['meetings'] = 0
        for row in state_rows['meetings']:
            if row.get('id'):
                meetings.document(row['id']).set(dict(row))
                counts['meetings'] += 1
        return counts

    def save_memories(self, save: Callable[[list[dict[str, Any]]], Any], chunk: list[dict[str, Any]]) -> int:
        """One ledger commit per chunk; a commit over Firestore's entity limit is split in half until it fits.

        The memory ledger records every fact of a commit in one document, so 200 long memories can exceed
        1 MiB. Only a single memory that still fails is counted as not written.
        """
        try:
            save(chunk)
            return len(chunk)
        except Exception as error:  # noqa: BLE001
            if len(chunk) > 1 and _too_large(error):
                middle = len(chunk) // 2
                return self.save_memories(save, chunk[:middle]) + self.save_memories(save, chunk[middle:])
            for _ in chunk:
                self._fail('memories', error)
            return 0

    def write_goal(self, goals_db: Any, uid: str, row: dict[str, Any]) -> None:
        """Create the goal; a focused one is created in the background and then focused, as the product requires."""
        focused = row.get('status') == 'focused'
        if not focused:
            goals_db.create_goal(uid, row, max_goals=10_000, firestore_client=self.client)
            return
        created = goals_db.create_goal(
            uid, {**row, 'status': 'background', 'focus_rank': None}, max_goals=10_000, firestore_client=self.client
        )
        goal_id = str((created or {}).get('goal_id') or (created or {}).get('id') or row.get('goal_id') or row['id'])
        goals_db.focus_goal(
            uid,
            goal_id,
            idempotency_key=f'pipeline-lab-seed-{goal_id}',
            account_generation=int(row.get('account_generation') or 0),
            focus_rank=row.get('focus_rank'),
            firestore_client=self.client,
        )

    def warnings(self) -> list[str]:
        out = [
            f'seed: {n} {kind} row(s) not written ({reason})'
            for kind, reasons in sorted(self.skipped.items())
            for reason, n in sorted(reasons.items())
        ]
        out += [
            f'seed: {field_name} cleared on {n} conversation(s) (sealed under the production key; the product reads it as absent)'
            for field_name, n in sorted(self.cleared.items())
        ]
        return out


def seed_start_state(
    state: StartState, writer: SeedWriter, *, reset: Callable[[], Any] | None = None
) -> dict[str, Any]:
    """Optionally reset the lab user, then write the state. Returns a seed report with timings and warnings."""
    report: dict[str, Any] = {'start_state': state.report.as_dict()}
    timings: dict[str, float] = {}
    if reset is not None:
        started = time.perf_counter()
        deleted = reset()
        report['reset_deleted'] = sum(deleted.values()) if isinstance(deleted, dict) else deleted
        if isinstance(deleted, dict):
            report['reset'] = deleted
        timings['reset'] = round(time.perf_counter() - started, 3)
    report['written'] = writer.write(state)
    timings.update(getattr(writer, 'timings', {}) or {})
    report['timings'] = timings
    for name in ('skipped', 'cleared'):
        value = getattr(writer, name, None)
        if value:
            report[name] = value
    warnings = writer.warnings() if callable(getattr(writer, 'warnings', None)) else []
    if warnings:
        report['warnings'] = warnings
    return report
