"""Five-minute surface-scoped inverse receipts. Never replay ambiguous inverses."""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from google.cloud import firestore
from database.messaging import MessagingStore
from utils import encryption
from utils.messaging.projection import surface_runtime

UNDO_MINUTES = 5


class UndoStore:
    def __init__(self, store=None):
        self.store = store or MessagingStore()

    def ref(self, uid, session):
        return (
            self.store.user(uid)
            .collection('chat_sessions')
            .document(session)
            .collection('channel_undo')
            .document('last')
        )

    def record(self, uid, session, kind, object_id, before, after):
        runtime = surface_runtime.get()
        if runtime is None or runtime.surface == 'app':
            return
        runtime.principal.authorize(uid)
        if runtime.guard:
            runtime.guard()
        self.fenced_set(
            uid,
            session,
            {
                'id': str(uuid4()),
                'state': 'ready',
                'expires_at': datetime.now(timezone.utc) + timedelta(minutes=UNDO_MINUTES),
                'payload': encryption.encrypt(
                    json.dumps(dict(kind=kind, object_id=object_id, before=before, after=after), default=str), uid
                ),
            },
        )

    def fenced_set(self, uid, session, payload):
        ref = self.ref(uid, session)
        session_ref = self.store.user(uid).collection('chat_sessions').document(session)

        @firestore.transactional
        def apply(tx):
            current = session_ref.get(transaction=tx).to_dict() or {}
            if not current.get('channel_link_id'):
                raise PermissionError('Channel session removed')
            self.store.assert_session_link(tx, uid, current)
            tx.set(ref, payload)

        run_with_transaction_contention_retry(
            self.store.db.transaction, apply, operation_name='channel_inverse_receipt'
        )

    def undo(self, uid, session):
        ref = self.ref(uid, session)

        @firestore.transactional
        def claim(tx):
            row = ref.get(transaction=tx).to_dict() or {}
            if row.get('state') != 'ready' or row.get(
                'expires_at', datetime.min.replace(tzinfo=timezone.utc)
            ) <= datetime.now(timezone.utc):
                return None
            session_row = (
                self.store.user(uid).collection('chat_sessions').document(session).get(transaction=tx).to_dict() or {}
            )
            if not session_row.get('channel_link_id'):
                raise PermissionError('Channel session removed')
            self.store.assert_session_link(tx, uid, session_row)
            tx.update(ref, {'state': 'running'})
            return row

        row = run_with_transaction_contention_retry(
            self.store.db.transaction, claim, operation_name='channel_undo_claim'
        )
        if row is None:
            return 'There is no reversible write from the last 5 minutes in this chat.'
        payload = json.loads(encryption.decrypt(row['payload'], uid))
        payload['operation_id'] = row['id']
        # A failure leaves running; it may have applied effects and must not be retried.
        apply_inverse(uid, payload)
        ref.update({'state': 'done', 'payload': firestore.DELETE_FIELD})
        return 'Undid the last write in this chat.'


def record_write(uid, kind, object_id, before, after):
    runtime = surface_runtime.get()
    if runtime is None or runtime.surface == 'app':
        return ''
    try:
        UndoStore().record(uid, runtime.session_id, kind, object_id, before, after)
    except Exception:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='other',
            from_mode='channel_inverse_receipt',
            to_mode='write_report',
            reason='dependency_unavailable',
            outcome='exhausted',
        )
        report = kind.title() + ' write completed, but undo is unavailable for this write.'
        if runtime.write_reports is not None:
            runtime.write_reports.append(report)
        return '\n' + report
    report = kind.title() + ' write completed. Reply undo within 5 minutes to reverse it.'
    if runtime.write_reports is not None:
        runtime.write_reports.append(report)
    return '\n' + report


def record_created_memory(uid, memory_id):
    runtime = surface_runtime.get()
    if runtime is None or runtime.surface == 'app':
        return ''
    from database._client import get_data_plane_firestore_client
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item

    item = read_canonical_memory_item(uid, memory_id, db_client=get_data_plane_firestore_client())
    if item is None:
        raise RuntimeError('Memory inverse readback unavailable')
    return record_write(uid, 'memory', memory_id, None, item.content)


def apply_inverse(uid, payload):
    kind, object_id = payload['kind'], payload['object_id']
    if kind == 'task':
        from database import action_items
        from utils.notifications import sync_action_item_reminder

        before = payload['before']
        if not action_items.restore_channel_write(uid, object_id, payload['after'], before):
            raise PermissionError('Task changed after this write; undo refused')
        restored = before or {}
        sync_action_item_reminder(
            uid,
            object_id,
            restored.get('description', ''),
            bool(restored.get('completed')),
            _date(restored.get('due_at')),
            status=restored.get('status'),
            deleted=before is None,
        )
    elif kind == 'memory_closed':
        from database._client import get_data_plane_firestore_client
        from utils.memory.memory_service import MemoryService

        MemoryService(db_client=get_data_plane_firestore_client()).reopen_standalone_closed_ledger_fact(
            uid, object_id, payload['operation_id']
        )
    elif kind == 'memory':
        from database._client import get_data_plane_firestore_client
        from utils.memory.canonical_memory_adapter import read_canonical_memory_item
        from utils.memory.memory_service import MemoryService
        from utils.memory.memory_system import MemorySystem

        db = get_data_plane_firestore_client()
        current = read_canonical_memory_item(uid, object_id, db_client=db)
        if (
            current is None
            or current.content != payload['after']
            or current.superseded_by
            or current.status.value != 'active'
        ):
            raise PermissionError('Memory changed after this write; undo refused')
        service = MemoryService(db_client=db)
        if payload['before'] is None:
            service.delete_external_memory(
                uid,
                object_id,
                memory_system=MemorySystem.CANONICAL,
                consumer='channel_undo',
                operation='undo_channel_write',
            )
        else:
            # Canonical service appends a correction for ledger facts, maintaining history.
            service.update_external_memory_content(
                uid,
                object_id,
                payload['before'],
                memory_system=MemorySystem.CANONICAL,
                consumer='channel_undo',
                operation='undo_channel_write',
            )
    else:
        raise ValueError('Unsupported inverse')


def _date(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


async def prepare_channel_write(uid, tool_name):
    runtime = surface_runtime.get()
    if (
        runtime is None
        or runtime.surface == 'app'
        or tool_name
        not in {
            'save_user_preference_tool',
            'create_action_item_tool',
            'update_action_item_tool',
            'save_playbook',
            'create_standing_trigger',
            'close_fact_tool',
        }
    ):
        return
    from utils.executors import db_executor, run_blocking

    runtime.principal.authorize(uid, tool_name)

    def reserve():
        if runtime.guard:
            runtime.guard()
        # Invalidate the old last-write receipt before a new mutation. If this
        # cannot persist, the tool never executes. Post-write recording failure
        # therefore cannot make an older write look like the last one.
        UndoStore().fenced_set(uid, runtime.session_id, {'state': 'preparing', 'at': datetime.now(timezone.utc)})

    await run_blocking(db_executor, reserve)
