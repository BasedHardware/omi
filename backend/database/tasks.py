import logging
from typing import Any, Dict, Optional

from google.cloud.firestore_v1 import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)

TASKS_COLLECTION = 'tasks'


def _clean_id(id_val: Optional[str], name: str = 'id') -> str:
    cleaned = (id_val or '').strip()
    if not cleaned:
        raise ValueError(f'{name} cannot be empty')
    if '/' in cleaned:
        raise ValueError(f'{name} cannot contain path delimiters')
    return cleaned


def create(task_data: Dict[str, Any], *, firestore_client: Any = None) -> None:
    if not isinstance(task_data, dict):
        raise ValueError('task_data must be a dictionary')
    task_id = _clean_id(task_data.get('id'), 'id')
    client = firestore_client if firestore_client is not None else db
    task_ref = client.collection(TASKS_COLLECTION).document(task_id)
    task_ref.set(task_data)


def update(task_id: str, task_data: Dict[str, Any], *, firestore_client: Any = None) -> None:
    cleaned_id = _clean_id(task_id, 'task_id')
    if not isinstance(task_data, dict):
        raise ValueError('task_data must be a dictionary')
    client = firestore_client if firestore_client is not None else db
    task_ref = client.collection(TASKS_COLLECTION).document(cleaned_id)
    task_ref.set(task_data, merge=True)


def get_task_by_action_request(
    action: str, request_id: str, *, firestore_client: Any = None
) -> Optional[Dict[str, Any]]:
    clean_action = (action or '').strip()
    clean_request_id = (request_id or '').strip()
    if not clean_action or not clean_request_id:
        return None

    client = firestore_client if firestore_client is not None else db
    try:
        query = (
            client.collection(TASKS_COLLECTION)
            .where(filter=FieldFilter('action', '==', clean_action))
            .where(filter=FieldFilter('request_id', '==', clean_request_id))
            .limit(1)
        )
        for item in query.stream():
            raw = item.to_dict()
            if isinstance(raw, dict):
                return raw
    except Exception as e:
        logger.error(f'Error querying task by action and request_id: {e}', exc_info=True)
        return None

    return None
