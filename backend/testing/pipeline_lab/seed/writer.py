"""Write a :class:`StartState` into the lab emulator.

:class:`ProductSeedWriter` writes through the product's own database helpers so
storage shape, encryption and derived indexes match what the product reads back.
It must run inside :func:`testing.pipeline_lab.stack.env.lab_environment`.

:func:`reset_lab_user` deletes the lab user's documents before a re-seed. It is
guarded by :func:`assert_lab_target`: only ``local-dev-user`` on a loopback
emulator of a ``demo-*`` project can ever be deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Callable, Protocol

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
    """Delete ``users/<uid>`` and everything under it. Guarded; returns the count."""
    assert_lab_target(uid, environ=environ, project=getattr(client, 'project', None))
    user_ref = client.collection('users').document(uid)
    deleted = _delete_tree(user_ref)
    user_ref.delete()
    return deleted + 1


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
    """Write via ``database.*`` helpers. Emulator only; verified by the lead on a real stack."""

    client: Any
    on_error: Callable[[str, Exception], None] | None = None
    errors: dict[str, int] = field(default_factory=dict)

    def _fail(self, kind: str, error: Exception) -> None:
        self.errors[kind] = self.errors.get(kind, 0) + 1
        if self.on_error is not None:
            self.on_error(kind, error)
        else:
            raise error

    def write(self, state: StartState) -> dict[str, int]:
        assert_lab_target(state.uid, project=getattr(self.client, 'project', None))
        from database import action_items as action_items_db
        from database import conversations as conversations_db
        from database import daily_summaries as daily_summaries_db
        from database import memories as memories_db
        from database import notifications as notification_db
        from database import users as users_db
        from database import goals as goals_db

        uid = state.uid
        counts: dict[str, int] = {}
        self.client.collection('users').document(uid).set(restore_times(dict(state.profile)), merge=True)
        counts['profile'] = 1
        notification_db.save_token(uid, dict(state.fcm_token), firestore_client=self.client)
        counts['fcm_tokens'] = 1
        state_rows = {kind: [restore_times(row) for row in rows] for kind, rows in state.entities().items()}
        for kind, rows, write_one in (
            ('people', state_rows['people'], lambda row: users_db.create_person(uid, row)),
            (
                'conversations',
                state_rows['conversations'],
                lambda row: conversations_db.upsert_conversation_with_lifecycle(uid, row),
            ),
            (
                'goals',
                state_rows['goals'],
                lambda row: goals_db.create_goal(uid, row, max_goals=10_000, firestore_client=self.client),
            ),
            (
                'daily_summaries',
                state_rows['daily_summaries'],
                lambda row: daily_summaries_db.create_daily_summary(uid, row),
            ),
        ):
            counts[kind] = 0
            for row in rows:
                try:
                    write_one(dict(row))
                    counts[kind] += 1
                except Exception as error:  # noqa: BLE001 - reported per kind
                    self._fail(kind, error)
        counts['memories'] = 0
        for start in range(0, len(state_rows['memories']), 200):
            chunk = [dict(row) for row in state_rows['memories'][start : start + 200]]
            try:
                memories_db.save_memories(uid, chunk, firestore_client=self.client)
                counts['memories'] += len(chunk)
            except Exception as error:  # noqa: BLE001
                self._fail('memories', error)
        counts['action_items'] = 0
        for start in range(0, len(state_rows['action_items']), 200):
            chunk = [dict(row) for row in state_rows['action_items'][start : start + 200]]
            try:
                action_items_db.create_action_items_batch(uid, chunk, document_ids=[row.get('id') for row in chunk])
                counts['action_items'] += len(chunk)
            except Exception as error:  # noqa: BLE001
                self._fail('action_items', error)
        meetings = self.client.collection('users').document(uid).collection('meetings')
        counts['meetings'] = 0
        for row in state_rows['meetings']:
            if row.get('id'):
                meetings.document(row['id']).set(dict(row))
                counts['meetings'] += 1
        return counts


def seed_start_state(
    state: StartState, writer: SeedWriter, *, reset: Callable[[], int] | None = None
) -> dict[str, Any]:
    """Optionally reset the lab user, then write the state. Returns a seed report."""
    report: dict[str, Any] = {'start_state': state.report.as_dict()}
    if reset is not None:
        report['reset_deleted'] = reset()
    report['written'] = writer.write(state)
    return report
