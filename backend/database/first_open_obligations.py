"""Durable, owner-generation-fenced first-open conversation obligations."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client, run_transactional
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.firestore_index_registry import FIRST_OPEN_FOLDER_CONVERSATION_COUNT_QUERY
from database.read_boundary import parse_snapshot_strict

if TYPE_CHECKING:
    from models.memory_apply import MemoryControlState

CONVERSATIONS_COLLECTION = 'conversations'
FIRST_OPEN_EFFECTS = ('folder_assignment', 'goal_progress', 'app_fanout')


def _refs(client: Any, uid: str) -> tuple[Any, Any, Any]:
    user = client.collection('users').document(uid)
    return (
        user,
        client.collection('account_deletions').document(uid),
        user.collection('memory_state').document('apply_control'),
    )


def _memory_control_state_model() -> type[Any]:
    """Load the JIT control model only at the first-open execution boundary.

    ``database.conversations`` is also imported by narrow legacy query seams
    which intentionally stub the rest of the backend model graph. Importing
    the control model while that module is merely loaded couples those reads
    to JIT execution dependencies they never exercise.
    """

    from models.memory_apply import MemoryControlState

    return MemoryControlState


def _authority(transaction: Any, client: Any, uid: str) -> Optional[MemoryControlState]:
    user_ref, deletion_ref, control_ref = _refs(client, uid)
    user = user_ref.get(transaction=transaction)
    deletion = deletion_ref.get(transaction=transaction)
    control_snapshot = control_ref.get(transaction=transaction)
    payload = deletion.to_dict() if deletion.exists else None
    status = normalize_account_deletion_status(
        marker_exists=deletion.exists,
        raw_status=payload.get('wipe_status') if isinstance(payload, Mapping) else None,
    )
    if not user.exists or account_deletion_blocks_access(status) or not control_snapshot.exists:
        return None
    try:
        control = parse_snapshot_strict(_memory_control_state_model(), control_snapshot)
    except Exception:
        return None
    return control if control.uid == uid else None


def _matches(state: Mapping[str, Any], control: MemoryControlState) -> bool:
    return (
        state.get('account_generation') == control.account_generation
        and state.get('source_generation') == control.source_generation
    )


def _effects(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = state.get('effects')
    if not isinstance(raw, Mapping):
        return {effect: {'state': 'pending'} for effect in FIRST_OPEN_EFFECTS}
    return {
        effect: dict(raw[effect]) if isinstance(raw.get(effect), Mapping) else {'state': 'pending'}
        for effect in FIRST_OPEN_EFFECTS
    }


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION).document(conversation_id)


def initialize_first_open_work(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    client = firestore_client or get_firestore_client()
    ref = _conversation_ref(client, uid, conversation_id)

    @firestore.transactional
    def initialize(transaction):
        snapshot = ref.get(transaction=transaction)
        control = _authority(transaction, client, uid)
        if not snapshot.exists or control is None:
            return False
        existing = (snapshot.to_dict() or {}).get('jit_first_open')
        if existing is not None:
            return isinstance(existing, Mapping) and _matches(existing, control)
        transaction.update(
            ref,
            {
                'jit_first_open': {
                    'version': 1,
                    'state': 'pending',
                    'attempt': 0,
                    'account_generation': control.account_generation,
                    'source_generation': control.source_generation,
                    'effects': {effect: {'state': 'pending'} for effect in FIRST_OPEN_EFFECTS},
                    'updated_at': firestore.SERVER_TIMESTAMP,
                }
            },
        )
        return True

    return bool(run_transactional(client, initialize))


def _live_effect(snapshot: Any, control: Optional[MemoryControlState], token: str, effect: str) -> bool:
    if not snapshot.exists or control is None or effect not in FIRST_OPEN_EFFECTS:
        return False
    state = (snapshot.to_dict() or {}).get('jit_first_open') or {}
    return (
        _matches(state, control)
        and state.get('state') == 'in_flight'
        and state.get('lease_token') == token
        and _effects(state)[effect].get('state') != 'complete'
    )


def first_open_effect_is_authorized(
    uid: str, conversation_id: str, token: str, effect: str, *, firestore_client: Any = None
) -> bool:
    client = firestore_client or get_firestore_client()
    ref = _conversation_ref(client, uid, conversation_id)

    @firestore.transactional
    def authorize(transaction):
        snapshot = ref.get(transaction=transaction)
        return _live_effect(snapshot, _authority(transaction, client, uid), token, effect)

    return bool(run_transactional(client, authorize))


def commit_first_open_conversation_patch(
    uid: str,
    conversation_id: str,
    token: str,
    effect: str,
    patch: Mapping[str, Any],
    *,
    firestore_client: Any = None,
) -> bool:
    if not patch:
        return False
    client = firestore_client or get_firestore_client()
    ref = _conversation_ref(client, uid, conversation_id)

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        if not _live_effect(snapshot, _authority(transaction, client, uid), token, effect):
            return False
        transaction.update(ref, dict(patch))
        return True

    return bool(run_transactional(client, commit))


def commit_first_open_app_result(
    uid: str,
    conversation_id: str,
    token: str,
    app_id: str,
    patch: Mapping[str, Any],
    *,
    firestore_client: Any = None,
) -> bool:
    """Persist an app result and its resumable receipt in one transaction."""
    if not app_id or not patch:
        return False
    client = firestore_client or get_firestore_client()
    ref = _conversation_ref(client, uid, conversation_id)

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        control = _authority(transaction, client, uid)
        if not _live_effect(snapshot, control, token, 'app_fanout'):
            return False
        row = snapshot.to_dict() or {}
        state = row.get('jit_first_open') or {}
        effects = _effects(state)
        app_effect = effects['app_fanout']
        raw_receipts = app_effect.get('app_receipts')
        receipts = dict(raw_receipts) if isinstance(raw_receipts, Mapping) else {}
        prior = receipts.get(app_id)
        receipt = dict(prior) if isinstance(prior, Mapping) else {}
        receipts[app_id] = {**receipt, 'result_persisted': True}
        effects['app_fanout'] = {**app_effect, 'app_receipts': receipts}
        transaction.update(
            ref,
            {
                **dict(patch),
                'jit_first_open': {**state, 'effects': effects, 'updated_at': firestore.SERVER_TIMESTAMP},
            },
        )
        return True

    return bool(run_transactional(client, commit))


def complete_first_open_effect(
    uid: str,
    conversation_id: str,
    token: str,
    effect: str,
    *,
    conversation_patch: Optional[Mapping[str, Any]] = None,
    firestore_client: Any = None,
) -> bool:
    if effect not in FIRST_OPEN_EFFECTS:
        raise ValueError(f'unknown first-open effect: {effect}')
    client = firestore_client or get_firestore_client()
    ref = _conversation_ref(client, uid, conversation_id)

    @firestore.transactional
    def complete(transaction):
        snapshot = ref.get(transaction=transaction)
        control = _authority(transaction, client, uid)
        if not snapshot.exists or control is None:
            return False
        row = snapshot.to_dict() or {}
        state = row.get('jit_first_open') or {}
        if not _matches(state, control) or state.get('state') != 'in_flight' or state.get('lease_token') != token:
            return False
        effects = _effects(state)
        if effects[effect].get('state') == 'complete':
            return True
        if effect == 'app_fanout':
            raw_receipts = effects[effect].get('app_receipts')
            receipts = raw_receipts if isinstance(raw_receipts, Mapping) else {}
            app_results = row.get('apps_results', [])
            if not isinstance(app_results, list):
                return False
            for result in app_results:
                if not isinstance(result, Mapping) or not isinstance(result.get('app_id'), str):
                    return False
                receipt = receipts.get(result['app_id'])
                if not isinstance(receipt, Mapping) or not (
                    receipt.get('result_persisted') is True and receipt.get('usage_persisted') is True
                ):
                    return False
        effects[effect] = {**effects[effect], 'state': 'complete', 'completed_at': firestore.SERVER_TIMESTAMP}
        patch: dict[str, Any] = {
            'jit_first_open': {**state, 'effects': effects, 'updated_at': firestore.SERVER_TIMESTAMP}
        }
        if conversation_patch:
            patch.update(dict(conversation_patch))
        transaction.update(ref, patch)
        return True

    return bool(run_transactional(client, complete))


def commit_first_open_folder_count(
    uid: str, conversation_id: str, token: str, folder_id: str, *, firestore_client: Any = None
) -> bool:
    client = firestore_client or get_firestore_client()
    user = client.collection('users').document(uid)
    query = FIRST_OPEN_FOLDER_CONVERSATION_COUNT_QUERY.build(
        user.collection(CONVERSATIONS_COLLECTION),
        {'folder_id': folder_id, 'discarded': False},
        field_filter_factory=FieldFilter,
    )
    count = int(query.count().get()[0][0].value or 0)
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    folder_ref = user.collection('folders').document(folder_id)

    @firestore.transactional
    def commit(transaction):
        conversation = conversation_ref.get(transaction=transaction)
        control = _authority(transaction, client, uid)
        folder = folder_ref.get(transaction=transaction)
        if not folder.exists or not _live_effect(conversation, control, token, 'folder_assignment'):
            return False
        transaction.update(folder_ref, {'conversation_count': count})
        return True

    return bool(run_transactional(client, commit))


def commit_first_open_app_usage(
    uid: str,
    conversation_id: str,
    token: str,
    app_id: str,
    usage_type: str,
    *,
    firestore_client: Any = None,
) -> bool:
    client = firestore_client or get_firestore_client()
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    plugin_ref = client.collection('plugins_data').document(app_id)
    usage_ref = client.collection('plugins').document(app_id).collection('usage_history').document(conversation_id)

    @firestore.transactional
    def commit(transaction):
        conversation = conversation_ref.get(transaction=transaction)
        plugin = plugin_ref.get(transaction=transaction)
        if not _live_effect(conversation, _authority(transaction, client, uid), token, 'app_fanout'):
            return False
        row = conversation.to_dict() or {}
        state = row.get('jit_first_open') or {}
        effects = _effects(state)
        app_effect = effects['app_fanout']
        raw_receipts = app_effect.get('app_receipts')
        receipts = dict(raw_receipts) if isinstance(raw_receipts, Mapping) else {}
        prior = receipts.get(app_id)
        receipt = dict(prior) if isinstance(prior, Mapping) else {}
        if receipt.get('result_persisted') is not True:
            return False
        if receipt.get('usage_persisted') is True:
            return True
        if not plugin.exists:
            return False
        receipts[app_id] = {**receipt, 'usage_persisted': True}
        effects['app_fanout'] = {**app_effect, 'app_receipts': receipts}
        transaction.set(
            usage_ref,
            {
                'uid': uid,
                'memory_id': conversation_id,
                'message_id': None,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'type': usage_type,
            },
        )
        transaction.update(
            conversation_ref,
            {'jit_first_open': {**state, 'effects': effects, 'updated_at': firestore.SERVER_TIMESTAMP}},
        )
        return True

    return bool(run_transactional(client, commit))


def claim_first_open_work(
    uid: str,
    conversation_id: str,
    *,
    lease_seconds: int = 300,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Optional[str]:
    client = firestore_client or get_firestore_client()
    ref = _conversation_ref(client, uid, conversation_id)
    current_time = now or datetime.now(timezone.utc)
    token = str(uuid.uuid4())

    @firestore.transactional
    def claim(transaction):
        snapshot = ref.get(transaction=transaction)
        control = _authority(transaction, client, uid)
        state = (snapshot.to_dict() or {}).get('jit_first_open') or {} if snapshot.exists else {}
        if not snapshot.exists or control is None or not _matches(state, control) or state.get('state') == 'complete':
            return None
        expires = state.get('lease_expires_at')
        if state.get('state') == 'in_flight' and isinstance(expires, datetime) and expires > current_time:
            return None
        attempt = state.get('attempt', 0)
        attempt = attempt if type(attempt) is int and attempt >= 0 else 0
        transaction.update(
            ref,
            {
                'jit_first_open': {
                    **state,
                    'version': 1,
                    'effects': _effects(state),
                    'state': 'in_flight',
                    'attempt': attempt + 1,
                    'lease_token': token,
                    'lease_expires_at': current_time + timedelta(seconds=max(30, lease_seconds)),
                    'updated_at': firestore.SERVER_TIMESTAMP,
                }
            },
        )
        return token

    return run_transactional(client, claim)


def claim_authorized_first_open_work(uid: str, conversation_id: str, source: str | None) -> Optional[str]:
    from utils.jit_first_open_policy import outstanding_first_open_work_permitted

    if not outstanding_first_open_work_permitted(uid=uid, source=source):
        return None
    return claim_first_open_work(uid, conversation_id)


def finish_first_open_work(
    uid: str,
    conversation_id: str,
    token: str,
    *,
    succeeded: bool,
    firestore_client: Any = None,
) -> bool:
    del succeeded
    client = firestore_client or get_firestore_client()
    ref = _conversation_ref(client, uid, conversation_id)

    @firestore.transactional
    def finish(transaction):
        snapshot = ref.get(transaction=transaction)
        control = _authority(transaction, client, uid)
        if not snapshot.exists or control is None:
            return False
        state = (snapshot.to_dict() or {}).get('jit_first_open') or {}
        if not _matches(state, control) or state.get('state') != 'in_flight' or state.get('lease_token') != token:
            return False
        effects = _effects(state)
        next_state = {
            **state,
            'effects': effects,
            'state': 'complete' if all(value.get('state') == 'complete' for value in effects.values()) else 'pending',
            'updated_at': firestore.SERVER_TIMESTAMP,
        }
        next_state.pop('lease_token', None)
        next_state.pop('lease_expires_at', None)
        transaction.update(ref, {'jit_first_open': next_state})
        return True

    return bool(run_transactional(client, finish))
