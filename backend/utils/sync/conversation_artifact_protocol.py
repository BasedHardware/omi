import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple

from utils.cloud_tasks import enqueue_audio_merge_job

logger = logging.getLogger(__name__)

FinalizationIdentity = Tuple[Optional[str], Optional[str], Optional[int]]


def conversation_finalization_identity(conversation: Optional[Dict[str, Any]]) -> Optional[FinalizationIdentity]:
    """Return the durable row identity when a conversation read carries one."""
    if not conversation:
        return None
    incarnation_id = conversation.get('finalization_incarnation_id')
    finalization_job_id = conversation.get('finalization_job_id')
    finalization_revision = conversation.get('finalization_revision')
    if not isinstance(incarnation_id, str) or not incarnation_id:
        return None
    if finalization_job_id is not None and not isinstance(finalization_job_id, str):
        return None
    if finalization_revision is not None and (
        not isinstance(finalization_revision, int) or isinstance(finalization_revision, bool)
    ):
        return None
    return incarnation_id, finalization_job_id, finalization_revision


def conversation_playback_artifact_generation_id(
    fingerprint: str,
    expected_finalization_identity: Optional[FinalizationIdentity],
) -> str:
    """Derive an opaque object/task generation from content and row identity."""
    source = {
        'fingerprint': fingerprint,
        'finalization_identity': list(expected_finalization_identity) if expected_finalization_identity else None,
    }
    return hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:32]


def enqueue_conversation_artifact_build(
    uid: str,
    conversation_id: str,
    fingerprint: str,
    caller: str,
    *,
    expected_finalization_identity: Optional[FinalizationIdentity] = None,
    require_delivery: bool = False,
) -> None:
    """Enqueue one generation-fenced conversation artifact build."""
    artifact_generation_id = conversation_playback_artifact_generation_id(
        fingerprint,
        expected_finalization_identity,
    )
    payload: Dict[str, Any] = {
        'schema_version': 2,
        'uid': uid,
        'conversation_id': conversation_id,
        'fingerprint': fingerprint,
        'artifact_generation_id': artifact_generation_id,
        'caller': caller,
    }
    if expected_finalization_identity is not None:
        payload['expected_finalization_identity'] = list(expected_finalization_identity)
    try:
        enqueue_audio_merge_job(payload)
    except Exception:
        logger.error('audio_merge: conversation enqueue failed conv=%s', conversation_id)
        if require_delivery:
            raise
