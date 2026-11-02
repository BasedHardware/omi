"""Scoped read of canonical saved audio, not an independent capture buffer."""

import jwt
from fastapi import HTTPException

from database.conversations import get_conversation
from utils.apps import is_user_app_enabled, get_available_app_by_id
from utils.other.endpoints import enforce_account_deletion_http_access
from utils.plugin_transport import plugin_transport
from utils.sync.playback import get_audio_signed_urls


def backup_audio_manifest(app_id: str, conversation_id: str, authorization: str, *, include_audio: bool = True) -> dict:
    try:
        transport = plugin_transport(app_id)
        if transport is None:
            raise ValueError('Unregistered plugin')
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer':
            raise ValueError('Missing bearer token')
        claims = transport.decode(token, 'audio')
        if claims.get('conversation_id') != conversation_id:
            raise ValueError('Wrong conversation')
    except (ValueError, jwt.PyJWTError):
        raise HTTPException(status_code=401, detail='Invalid or expired backup audio authorization')
    uid = claims['sub']
    enforce_account_deletion_http_access(uid)
    if not get_available_app_by_id(app_id, uid) or not is_user_app_enabled(uid, app_id):
        raise HTTPException(status_code=403, detail='This backup app is no longer enabled')
    conversation = get_conversation(uid, conversation_id)
    if (
        not conversation
        or conversation.get('discarded')
        or conversation.get('is_locked')
        or conversation.get('deleted')
    ):
        raise HTTPException(status_code=404, detail='This conversation is not available for backup')
    if not include_audio:
        return {'authorized': True}
    return get_audio_signed_urls(uid, conversation_id, conversation.get('audio_files') or [], conversation)
