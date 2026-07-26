from typing import Optional

from google.cloud.exceptions import NotFound as BlobNotFound

from utils.other.storage import (
    PLAYBACK_ARTIFACT_PREFIX,
    delete_private_cloud_sync_prefix,
    get_private_cloud_sync_blob,
    get_storage_signed_url,
)

_CONVERSATION_ARTIFACT_NAME = 'conversation'


def _playback_prefix_component(value: str, name: str) -> str:
    if not value or '/' in value:
        raise ValueError(f'invalid conversation playback {name}')
    return value


def _conversation_playback_blob(
    uid: str,
    conversation_id: str,
    extension: str,
    artifact_generation_id: Optional[str],
):
    if artifact_generation_id is not None and (
        len(artifact_generation_id) != 32 or any(char not in '0123456789abcdef' for char in artifact_generation_id)
    ):
        raise ValueError('invalid conversation playback artifact generation')
    parts = [
        PLAYBACK_ARTIFACT_PREFIX,
        _playback_prefix_component(uid, 'uid'),
        _playback_prefix_component(conversation_id, 'conversation id'),
    ]
    if artifact_generation_id is not None:
        parts.append(artifact_generation_id)
    path = '/'.join(parts + [f'{_CONVERSATION_ARTIFACT_NAME}.{extension}'])
    return get_private_cloud_sync_blob(path)


def delete_conversation_playback_artifacts(uid: str, conversation_id: str) -> None:
    """Delete every generation owned by one exact conversation."""
    uid = _playback_prefix_component(uid, 'uid')
    conversation_id = _playback_prefix_component(conversation_id, 'conversation id')
    delete_private_cloud_sync_prefix(f'{PLAYBACK_ARTIFACT_PREFIX}/{uid}/{conversation_id}/')


def delete_all_conversation_playback_artifacts(uid: str) -> None:
    """Delete every conversation playback generation owned by one account."""
    uid = _playback_prefix_component(uid, 'uid')
    delete_private_cloud_sync_prefix(f'{PLAYBACK_ARTIFACT_PREFIX}/{uid}/')


def get_conversation_playback_signed_url(
    uid: str,
    conversation_id: str,
    artifact_generation_id: Optional[str] = None,
):
    blob = _conversation_playback_blob(uid, conversation_id, 'mp3', artifact_generation_id)
    if not blob.exists():
        return None
    return get_storage_signed_url(blob, 60)


def upload_conversation_playback_artifact(
    uid: str,
    conversation_id: str,
    mp3_data: bytes,
    artifact_generation_id: Optional[str] = None,
) -> None:
    blob = _conversation_playback_blob(uid, conversation_id, 'mp3', artifact_generation_id)
    blob.upload_from_string(mp3_data, content_type='audio/mpeg')


def mark_conversation_playback_unavailable(
    uid: str,
    conversation_id: str,
    fingerprint: str,
    reason: str,
    artifact_generation_id: Optional[str] = None,
) -> None:
    blob = _conversation_playback_blob(uid, conversation_id, 'unavailable', artifact_generation_id)
    blob.upload_from_string(f'{fingerprint}:{reason}', content_type='text/plain')


def get_conversation_playback_unavailable_fingerprint(
    uid: str,
    conversation_id: str,
    artifact_generation_id: Optional[str] = None,
) -> Optional[str]:
    blob = _conversation_playback_blob(uid, conversation_id, 'unavailable', artifact_generation_id)
    try:
        content = blob.download_as_bytes().decode()
    except BlobNotFound:
        return None
    return content.split(':', 1)[0] if content else None
