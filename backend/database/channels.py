import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client, run_transactional
from database.firestore_index_registry import CHANNEL_BINDINGS_BY_UID_CHANNEL_QUERY

CHANNELS = frozenset({'telegram', 'imessage', 'sms'})
LINK_TOKEN_TTL = timedelta(minutes=15)
LINK_TOKEN_PATTERN = re.compile(r'^[0-9a-f]{48}$')


class ChannelLinkError(ValueError):
    pass


class ChannelBindingConflict(ChannelLinkError):
    pass


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _binding_id(channel: str, channel_user_id: str, channel_chat_id: Optional[str] = None) -> str:
    identity = channel_chat_id or channel_user_id
    return hashlib.sha256(f'{channel}\0{identity}'.encode('utf-8')).hexdigest()


def _event_id(channel: str, provider_event_id: str) -> str:
    return hashlib.sha256(f'{channel}\0{provider_event_id}'.encode('utf-8')).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def issue_link_token(
    uid: str,
    channel: str,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Tuple[str, datetime]:
    if channel not in CHANNELS:
        raise ChannelLinkError('unsupported channel')
    created_at = now or datetime.now(timezone.utc)
    expires_at = created_at + LINK_TOKEN_TTL
    client = _client(firestore_client)
    for _ in range(3):
        token = secrets.token_hex(24)
        ref = client.collection('channel_link_tokens').document(_token_hash(token))
        try:
            ref.create(
                {
                    'channel': channel,
                    'uid': uid,
                    'token_kind': 'link',
                    'created_at': created_at,
                    'expires_at': expires_at,
                    'consumed_at': None,
                }
            )
            return token, expires_at
        except AlreadyExists:
            continue
    raise ChannelLinkError('could not issue a link token')


def issue_claim_token(
    channel: str,
    channel_user_id: str,
    channel_chat_id: str,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Tuple[str, datetime]:
    if channel not in CHANNELS or not channel_user_id or not channel_chat_id:
        raise ChannelLinkError('invalid claim identity')
    created_at = now or datetime.now(timezone.utc)
    expires_at = created_at + LINK_TOKEN_TTL
    client = _client(firestore_client)
    for _ in range(3):
        token = secrets.token_hex(24)
        ref = client.collection('channel_link_tokens').document(_token_hash(token))
        try:
            ref.create(
                {
                    'channel': channel,
                    'uid': None,
                    'token_kind': 'claim',
                    'claim_channel_user_id': channel_user_id,
                    'claim_channel_chat_id': channel_chat_id,
                    'created_at': created_at,
                    'expires_at': expires_at,
                    'consumed_at': None,
                }
            )
            return token, expires_at
        except AlreadyExists:
            continue
    raise ChannelLinkError('could not issue a claim token')


def consume_link_token(
    channel: str,
    token: str,
    channel_user_id: str,
    channel_chat_id: str,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    if channel not in CHANNELS or not LINK_TOKEN_PATTERN.fullmatch(token):
        raise ChannelLinkError('invalid link token')
    consumed_at = now or datetime.now(timezone.utc)
    client = _client(firestore_client)
    token_ref = client.collection('channel_link_tokens').document(_token_hash(token))
    binding_ref = client.collection('channel_bindings').document(_binding_id(channel, channel_user_id, channel_chat_id))

    @firestore.transactional
    def apply(transaction: Any) -> Dict[str, Any]:
        token_snapshot = token_ref.get(transaction=transaction)
        if not token_snapshot.exists:
            raise ChannelLinkError('invalid link token')
        token_data = _typed_doc(token_snapshot)
        expires_at = token_data.get('expires_at')
        if (
            token_data.get('channel') != channel
            or token_data.get('token_kind', 'link') != 'link'
            or token_data.get('consumed_at') is not None
        ):
            raise ChannelLinkError('invalid link token')
        if not isinstance(expires_at, datetime) or expires_at <= consumed_at:
            raise ChannelLinkError('expired link token')

        existing_snapshot = binding_ref.get(transaction=transaction)
        if existing_snapshot.exists:
            existing = _typed_doc(existing_snapshot)
            if existing.get('revoked_at') is None and existing.get('uid') != token_data.get('uid'):
                raise ChannelBindingConflict('channel is already linked to another account')

        binding = {
            'channel': channel,
            'uid': token_data['uid'],
            'channel_user_id': channel_user_id,
            'channel_chat_id': channel_chat_id,
            'linked_at': consumed_at,
            'revoked_at': None,
        }
        transaction.update(token_ref, {'consumed_at': consumed_at})
        transaction.set(binding_ref, binding)
        return binding

    return run_transactional(client, apply)


def claim_link_token(
    uid: str,
    channel: str,
    token: str,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Dict[str, Any]:
    if channel not in CHANNELS or not LINK_TOKEN_PATTERN.fullmatch(token):
        raise ChannelLinkError('invalid link token')
    claimed_at = now or datetime.now(timezone.utc)
    client = _client(firestore_client)
    token_ref = client.collection('channel_link_tokens').document(_token_hash(token))

    @firestore.transactional
    def apply(transaction: Any) -> Dict[str, Any]:
        token_snapshot = token_ref.get(transaction=transaction)
        if not token_snapshot.exists:
            raise ChannelLinkError('invalid link token')
        token_data = _typed_doc(token_snapshot)
        expires_at = token_data.get('expires_at')
        channel_user_id = token_data.get('claim_channel_user_id')
        channel_chat_id = token_data.get('claim_channel_chat_id')
        if (
            token_data.get('channel') != channel
            or token_data.get('token_kind') != 'claim'
            or token_data.get('uid') is not None
            or token_data.get('consumed_at') is not None
            or not isinstance(channel_user_id, str)
            or not isinstance(channel_chat_id, str)
        ):
            raise ChannelLinkError('invalid link token')
        if not isinstance(expires_at, datetime) or expires_at <= claimed_at:
            raise ChannelLinkError('expired link token')

        binding_ref = client.collection('channel_bindings').document(
            _binding_id(channel, channel_user_id, channel_chat_id)
        )
        existing_snapshot = binding_ref.get(transaction=transaction)
        if existing_snapshot.exists:
            existing = _typed_doc(existing_snapshot)
            if existing.get('revoked_at') is None and existing.get('uid') != uid:
                raise ChannelBindingConflict('channel is already linked to another account')

        binding = {
            'channel': channel,
            'uid': uid,
            'channel_user_id': channel_user_id,
            'channel_chat_id': channel_chat_id,
            'linked_at': claimed_at,
            'revoked_at': None,
        }
        transaction.update(token_ref, {'uid': uid, 'consumed_at': claimed_at})
        transaction.set(binding_ref, binding)
        return binding

    return run_transactional(client, apply)


def get_binding(
    channel: str,
    channel_user_id: str,
    channel_chat_id: Optional[str] = None,
    *,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    if channel not in CHANNELS:
        return None
    identities = (
        [channel_chat_id, channel_user_id]
        if channel_chat_id and channel_chat_id != channel_user_id
        else [channel_user_id]
    )
    collection = _client(firestore_client).collection('channel_bindings')
    for identity in identities:
        if not identity:
            continue
        snapshot = collection.document(_binding_id(channel, channel_user_id, identity)).get()
        if not snapshot.exists:
            continue
        binding = _typed_doc(snapshot)
        if binding.get('revoked_at') is None:
            return binding
    return None


def list_bindings(uid: str, *, firestore_client: Any = None) -> List[Dict[str, Any]]:
    rows = _client(firestore_client).collection('channel_bindings').where('uid', '==', uid).stream()
    return [binding for binding in (_typed_doc(row) for row in rows) if binding.get('revoked_at') is None]


def revoke_channel(uid: str, channel: str, *, now: Optional[datetime] = None, firestore_client: Any = None) -> int:
    if channel not in CHANNELS:
        raise ChannelLinkError('unsupported channel')
    revoked_at = now or datetime.now(timezone.utc)
    client = _client(firestore_client)
    rows = CHANNEL_BINDINGS_BY_UID_CHANNEL_QUERY.build(
        client.collection('channel_bindings'),
        {'uid': uid, 'channel': channel},
        field_filter_factory=FieldFilter,
    ).stream()
    refs = [row.reference for row in rows if _typed_doc(row).get('revoked_at') is None]
    if not refs:
        return 0
    batch = client.batch()
    for ref in refs:
        batch.update(ref, {'revoked_at': revoked_at})
    batch.commit()
    return len(refs)


def revoke_binding(
    channel: str,
    channel_user_id: str,
    channel_chat_id: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> bool:
    binding = get_binding(channel, channel_user_id, channel_chat_id, firestore_client=firestore_client)
    if not binding:
        return False
    binding_identity = binding.get('channel_chat_id') or channel_user_id
    ref = _client(firestore_client).collection('channel_bindings').document(_binding_id(channel, binding_identity))
    ref.update({'revoked_at': now or datetime.now(timezone.utc)})
    return True


def claim_webhook_event(
    channel: str,
    provider_event_id: str,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    received_at = now or datetime.now(timezone.utc)
    ref = _client(firestore_client).collection('channel_webhook_events').document(_event_id(channel, provider_event_id))
    try:
        ref.create(
            {
                'channel': channel,
                'provider_event_id': provider_event_id,
                'status': 'processing',
                'received_at': received_at,
                'updated_at': received_at,
            }
        )
        return True, None
    except AlreadyExists:
        snapshot = ref.get()
        return False, _typed_doc(snapshot) if snapshot.exists else None


def update_webhook_event(
    channel: str,
    provider_event_id: str,
    updates: Dict[str, Any],
    *,
    firestore_client: Any = None,
) -> None:
    payload = dict(updates)
    payload['updated_at'] = datetime.now(timezone.utc)
    ref = _client(firestore_client).collection('channel_webhook_events').document(_event_id(channel, provider_event_id))
    ref.update(payload)
