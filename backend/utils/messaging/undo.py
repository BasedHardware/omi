"""Five-minute surface-scoped inverse receipts. Never replay ambiguous inverses."""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from google.cloud import firestore
from database.messaging import MessagingStore
from utils import encryption
from utils.messaging.projection import surface_runtime
from utils.messaging.contracts import ActionReceipt, UndoResult

UNDO_MINUTES = 5


class UndoStore:
    def __init__(self, store=None):
        self.store = store or MessagingStore()

    def ref(self, uid, session, receipt_id="last"):
        return (
            self.store.user(uid)
            .collection('chat_sessions')
            .document(session)
            .collection('channel_undo')
            .document(receipt_id)
        )

    def record(self, uid, session, kind, object_id, before, after) -> ActionReceipt:
        runtime = surface_runtime.get()
        if runtime is None or runtime.surface == 'app':
            raise PermissionError('Action receipts require an admitted channel turn')
        runtime.principal.authorize(uid)
        if runtime.guard:
            runtime.guard()
        self.prune_expired(uid, session)
        receipt_id = uuid4().hex
        receipt = action_receipt(receipt_id, kind, object_id, before, after)
        self.fenced_set(
            uid,
            session,
            {
                'id': receipt_id,
                'state': 'ready',
                'expires_at': datetime.now(timezone.utc) + timedelta(minutes=UNDO_MINUTES),
                'presentation': encryption.encrypt(json.dumps(dict(text=receipt.text)), uid),
                'payload': encryption.encrypt(
                    json.dumps(dict(kind=kind, object_id=object_id, before=before, after=after), default=str), uid
                ),
            },
            receipt_id=receipt_id,
            turn_id=runtime.turn_id or receipt_id,
        )
        return receipt

    def prune_expired(self, uid, session, *, now=None):
        # Opportunistic, bounded cleanup on each write. Keep one day beyond the
        # undo window for in-flight cleanup/edit reconciliation; no TTL IAM needed.
        # Deleting an old running receipt cannot replay it or recreate the fence.
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=1)
        collection = self.ref(uid, session).parent
        expired = list(collection.where('expires_at', '<=', cutoff).limit(100).stream())
        if expired:
            batch = self.store.db.batch()
            for row in expired:
                batch.delete(row.reference)
            batch.commit()
        return len(expired)

    def fenced_set(self, uid, session, payload, *, receipt_id="last", turn_id=None):
        ref = self.ref(uid, session, receipt_id)
        session_ref = self.store.user(uid).collection('chat_sessions').document(session)

        @firestore.transactional
        def apply(tx):
            current = session_ref.get(transaction=tx).to_dict() or {}
            if not current.get('channel_link_id'):
                raise PermissionError('Channel session removed')
            self.store.assert_session_link(tx, uid, current)
            pointer_ref = self.ref(uid, session)
            pointer = (pointer_ref.get(transaction=tx).to_dict() or {}) if turn_id else {}
            tx.set(ref, payload)
            if turn_id:
                ids = list(pointer.get('receipt_ids', ())) if pointer.get('turn_id') == turn_id else []
                ids.append(receipt_id)
                tx.set(
                    pointer_ref,
                    {
                        'turn_id': turn_id,
                        'receipt_ids': ids,
                        'state': 'ready' if len(ids) == 1 else 'ambiguous',
                        'receipt_id': receipt_id if len(ids) == 1 else None,
                    },
                )

        run_with_transaction_contention_retry(
            self.store.db.transaction, apply, operation_name='channel_inverse_receipt'
        )

    def reserve_selection(self, uid, session, turn_id):
        ref = self.ref(uid, session)
        session_ref = self.store.user(uid).collection('chat_sessions').document(session)

        @firestore.transactional
        def reserve(tx):
            current = session_ref.get(transaction=tx).to_dict() or {}
            self.store.assert_session_link(tx, uid, current)
            pointer = ref.get(transaction=tx).to_dict() or {}
            ids = pointer.get('receipt_ids', []) if pointer.get('turn_id') == turn_id else []
            tx.set(ref, {'state': 'preparing', 'turn_id': turn_id, 'receipt_ids': ids})

        run_with_transaction_contention_retry(
            self.store.db.transaction, reserve, operation_name='channel_inverse_reserve'
        )

    def bind_bubble(self, uid, session, receipt_id, bubble_id):
        self.ref(uid, session, receipt_id).update({'bubble_id': str(bubble_id)})

    def mark_edited(self, uid, session, receipt_id):
        if receipt_id:
            self.ref(uid, session, receipt_id).update({'edited_at': datetime.now(timezone.utc)})

    def undo(self, uid, session, receipt_id=None):
        if receipt_id is None:
            pointer = self.ref(uid, session).get().to_dict() or {}
            receipt_id = pointer.get('receipt_id') if pointer.get('state') == 'ready' else None
        if not receipt_id:
            return UndoResult('unavailable', 'There is no unambiguous reversible action in this chat.')
        ref = self.ref(uid, session, receipt_id)

        @firestore.transactional
        def claim(tx):
            row = ref.get(transaction=tx).to_dict() or {}
            if row.get('state') == 'done':
                return row
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
            return UndoResult('unavailable', 'This action cannot be undone now. It may have expired or changed.')
        presentation = json.loads(encryption.decrypt(row['presentation'], uid))
        if row['state'] == 'done':
            return UndoResult(
                'already_undone',
                'Already undone.',
                None if row.get('edited_at') else row.get('bubble_id'),
                presentation['text'] + ' — Undone',
            )
        payload = json.loads(encryption.decrypt(row['payload'], uid))
        payload['operation_id'] = row['id']
        # A failure leaves this inverse running; it is never replayed. The chat
        # turn itself can finish and release its lease after the operation unwinds.
        apply_inverse(uid, payload)
        ref.update({'state': 'done', 'payload': firestore.DELETE_FIELD})
        return UndoResult('undone', 'Undone.', row.get('bubble_id'), presentation['text'] + ' — Undone')


def action_receipt(receipt_id, kind, object_id, before, after):
    # Same canonical IDs and block schemas as in-app chat, never model-parsed text.
    from models.chat_first import MemoryLinkSpec, TaskCardSpec

    if kind == 'task':
        block = TaskCardSpec(type='taskCard', task_id=object_id).model_dump()
        text = ('Task added: ' if before is None else 'Task updated: ') + after.get('description', 'Task')
        if after.get('due_at'):
            due = _date(after['due_at'])
            text += ' — due ' + due.strftime('%b %d, %H:%M %z')
    else:
        summary = str(after or before or 'Memory')
        block = MemoryLinkSpec(type='memoryLink', memory_id=object_id, summary=summary[:200]).model_dump()
        text = (
            'Memory closed: ' if kind == 'memory_closed' else 'New memory: ' if before is None else 'Memory updated: '
        ) + summary
    return ActionReceipt(receipt_id, dict(block, id=receipt_id), text)


def record_write(uid, kind, object_id, before, after):
    runtime = surface_runtime.get()
    if runtime is None or runtime.surface == 'app':
        return ''
    receipt = action_receipt(uuid4().hex, kind, object_id, before, after)
    try:
        receipt = UndoStore().record(uid, runtime.session_id, kind, object_id, before, after)
    except Exception:
        from dataclasses import replace
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='other',
            from_mode='channel_inverse_receipt',
            to_mode='write_report',
            reason='dependency_unavailable',
            outcome='exhausted',
        )
        receipt = replace(receipt, reversible=False, text=receipt.text + ' (Undo unavailable)')
    if runtime.action_receipts is not None:
        runtime.action_receipts.append(receipt)
    # The tool already returns its confirmed outcome. Undo mechanics belong to
    # the adapter, and must never enter the model's tool result or prose.
    return ''


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
        # Invalidate text-undo selection before mutation; specific receipts survive.
        # A failed write must not make an older action appear to be its result.
        UndoStore().reserve_selection(uid, runtime.session_id, runtime.turn_id)

    await run_blocking(db_executor, reserve)
