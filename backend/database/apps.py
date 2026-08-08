from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from ulid import ULID

from models.app import UsageHistoryType
from database.store import Filter, get_document_store
from database.store.sentinels import ArrayRemove, ArrayUnion
import logging

logger = logging.getLogger(__name__)


def _store():
    return get_document_store()


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


# *****************************
# ********** CRUD *************
# *****************************

apps_collection = 'plugins_data'
app_analytics_collection = 'plugins'
testers_collection = 'testers'


def _app_path(app_id: str) -> str:
    return f'{apps_collection}/{app_id}'


def _usage_history_path(app_id: str) -> str:
    return f'{app_analytics_collection}/{app_id}/usage_history'


def _api_keys_path(app_id: str) -> str:
    return f'{apps_collection}/{app_id}/api_keys'


def get_app_by_id_db(app_id: str) -> Optional[Dict[str, Any]]:
    doc = _store().get(_app_path(app_id))
    if doc.exists:
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_audio_apps_count(app_ids: List[str]) -> int:
    if not app_ids or len(app_ids) == 0:
        return 0
    filters: List[Filter] = [('id', 'in', app_ids), ('external_integration.triggers_on', '==', 'audio_bytes')]
    return _store().count(apps_collection, filters=filters)


def get_private_apps_db(uid: str) -> List[Dict[str, Any]]:
    filters: List[Filter] = [('uid', '==', uid), ('private', '==', True)]
    return [_typed_doc(doc) for doc in _store().query(apps_collection, filters=filters)]


# This returns public unapproved apps of all users
def get_unapproved_public_apps_db() -> List[Dict[str, Any]]:
    filters: List[Filter] = [('approved', '==', False), ('private', '==', False)]
    return [_typed_doc(doc) for doc in _store().query(apps_collection, filters=filters)]


def get_public_approved_apps_db() -> List[Dict[str, Any]]:
    filters: List[Filter] = [('approved', '==', True), ('private', '==', False)]
    return [_typed_doc(doc) for doc in _store().query(apps_collection, filters=filters)]


def get_popular_apps_db() -> List[Dict[str, Any]]:
    filters: List[Filter] = [('approved', '==', True), ('is_popular', '==', True)]
    return [_typed_doc(doc) for doc in _store().query(apps_collection, filters=filters)]


def set_app_popular_db(app_id: str, popular: bool) -> None:
    _store().update(_app_path(app_id), {'is_popular': popular})


def search_apps_db(
    uid: str,
    category: str | None = None,
    capability: str | None = None,
    my_apps: bool = False,
    installed_apps: bool = False,
    enabled_app_ids: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Optimized search function that applies filters at database level.
    Uses smart filter ordering to minimize data fetched from the store.

    Note: Rating filter is NOT applied here as rating_avg is calculated from Redis,
    not stored in the document. Apply rating filter after fetching from DB.

    Args:
        uid: User ID for private apps and filtering
        category: Filter by category ID
        capability: Filter by capability ID
        my_apps: Only return user's own apps
        installed_apps: Only return user's enabled apps
        enabled_app_ids: Pre-fetched list of enabled app IDs (for installed_apps filter)

    Returns:
        List of app dictionaries matching the filters
    """
    filters: List[Filter] = []

    # 1. Apply most restrictive filter first
    if my_apps:
        filters.append(('uid', '==', uid))

    elif installed_apps:
        if not enabled_app_ids or len(enabled_app_ids) == 0:
            # User has no enabled apps
            return []

        if len(enabled_app_ids) > 30:
            # 'in' filter limited to 30 items
            # Query public approved apps first, then add user's own apps
            filters.append(('approved', '==', True))
            filters.append(('private', '==', False))
        else:
            # Query by specific IDs
            filters.append(('id', 'in', enabled_app_ids))

    else:
        # Default: Public approved apps
        filters.append(('approved', '==', True))
        filters.append(('private', '==', False))

    # 2. Add category filter
    if category and not my_apps:  # Don't add if already filtering by my_apps
        filters.append(('category', '==', category))

    # 3. Add capability filter
    if capability and not my_apps:
        filters.append(('capabilities', 'array_contains', capability))

    # Execute query with all filters
    apps: List[Dict[str, Any]] = []
    if filters:
        apps = [_typed_doc(doc) for doc in _store().query(apps_collection, filters=filters)]

    # For installed_apps with > 30 enabled apps, we need to also fetch user's own apps
    # because the main query only returns approved+public apps
    if installed_apps and enabled_app_ids and len(enabled_app_ids) > 30:
        enabled_set = set(enabled_app_ids)
        # Filter to only enabled apps from the public approved set
        apps = [app for app in apps if app.get('id') in enabled_set]

        # Also fetch user's own enabled apps (which may be private or unapproved)
        user_apps = [_typed_doc(doc) for doc in _store().query(apps_collection, filters=[('uid', '==', uid)])]

        # Add user's own enabled apps that aren't already in the list
        existing_ids = {app.get('id') for app in apps}
        for user_app in user_apps:
            if user_app.get('id') in enabled_set and user_app.get('id') not in existing_ids:
                apps.append(user_app)

    # Post-filter for category if my_apps is enabled
    if my_apps and category:
        apps = [app for app in apps if app.get('category') == category]

    # Post-filter for capability if my_apps is enabled
    if my_apps and capability:
        apps = [app for app in apps if capability in app.get('capabilities', [])]

    return apps


# This returns public unapproved apps for a user
def get_public_unapproved_apps_db(uid: str) -> List[Dict[str, Any]]:
    filters: List[Filter] = [('approved', '==', False), ('uid', '==', uid), ('private', '==', False)]
    return [_typed_doc(doc) for doc in _store().query(apps_collection, filters=filters)]


def get_apps_for_tester_db(uid: str) -> List[Dict[str, Any]]:
    doc = _store().get(f'{testers_collection}/{uid}')
    if doc.exists:
        apps = _typed_doc(doc).get('apps', [])
        if not apps:
            return []
        filters: List[Filter] = [('approved', '==', False), ('id', 'in', apps)]
        return [_typed_doc(d) for d in _store().query(apps_collection, filters=filters)]
    return []


def add_app_to_db(app_data: Dict[str, Any]) -> None:
    _store().create(_app_path(app_data['id']), app_data)


def upsert_app_to_db(app_data: Dict[str, Any]) -> None:
    _store().set(_app_path(app_data['id']), app_data)


def update_app_in_db(app_data: Dict[str, Any]) -> None:
    _store().update(_app_path(app_data['id']), app_data)


def delete_app_from_db(app_id: str) -> None:
    _store().delete(_app_path(app_id))


def update_app_visibility_in_db(app_id: str, private: bool) -> None:
    store = _store()
    if 'private' in app_id and not private:
        app = _typed_doc(store.get(_app_path(app_id)))
        if not app:
            # The private app document is gone (deleted, or a stale read-cache pointed the caller
            # here). There is nothing to republish, so skip the delete-and-recreate instead of
            # dereferencing None below (which raised TypeError -> 500).
            return
        store.delete(_app_path(app_id))
        new_app_id = app_id.split('-private')[0] + '-' + str(ULID())
        app['id'] = new_app_id
        app['private'] = private
        store.set(_app_path(new_app_id), app)
    else:
        store.update(_app_path(app_id), {'private': private})


def change_app_approval_status(app_id: str, approved: bool) -> None:
    _store().update(_app_path(app_id), {'approved': approved, 'status': 'approved' if approved else 'rejected'})


def get_app_usage_history_db(app_id: str) -> List[Dict[str, Any]]:
    return [_typed_doc(doc) for doc in _store().query(_usage_history_path(app_id))]


def get_app_memory_created_integration_usage_count_db(app_id: str) -> Any:
    return _store().count(
        _usage_history_path(app_id),
        filters=[('type', '==', UsageHistoryType.memory_created_external_integration)],
    )


def get_app_memory_prompt_usage_count_db(app_id: str) -> Any:
    return _store().count(
        _usage_history_path(app_id),
        filters=[('type', '==', UsageHistoryType.memory_created_prompt)],
    )


def get_app_chat_message_sent_usage_count_db(app_id: str) -> Any:
    return _store().count(
        _usage_history_path(app_id),
        filters=[('type', '==', UsageHistoryType.chat_message_sent)],
    )


def get_app_usage_count_db(app_id: str) -> Any:
    return _store().count(_usage_history_path(app_id))


# ********************************
# *********** REVIEWS ************
# ********************************


def set_app_review_in_db(app_id: str, uid: str, review: Dict[str, Any]) -> None:
    _store().set(f'{apps_collection}/{app_id}/reviews/{uid}', review)


# ********************************
# ************ TESTER ************
# ********************************


def add_tester_db(data: Dict[str, Any]) -> None:
    _store().set(f'{testers_collection}/{data["uid"]}', data)


def add_app_access_for_tester_db(app_id: str, uid: str) -> None:
    _store().update(f'{testers_collection}/{uid}', {'apps': ArrayUnion([app_id])})


def remove_app_access_for_tester_db(app_id: str, uid: str) -> None:
    _store().update(f'{testers_collection}/{uid}', {'apps': ArrayRemove([app_id])})


def remove_tester_db(uid: str) -> None:
    _store().delete(f'{testers_collection}/{uid}')


def can_tester_access_app_db(app_id: str, uid: str) -> bool:
    doc = _store().get(f'{testers_collection}/{uid}')
    if doc.exists:
        return app_id in _typed_doc(doc).get('apps', [])
    return False


def is_tester_db(uid: str) -> bool:
    return _store().exists(f'{testers_collection}/{uid}')


# ********************************
# *********** APPS USAGE *********
# ********************************


def record_app_usage(
    uid: str,
    app_id: str,
    usage_type: UsageHistoryType,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    if not conversation_id and not message_id:
        raise ValueError('memory_id or message_id must be provided')

    data: Dict[str, Any] = {
        'uid': uid,
        'memory_id': conversation_id,
        'message_id': message_id,
        'timestamp': datetime.now(timezone.utc) if timestamp is None else timestamp,
        'type': usage_type,
    }

    _store().set(f'{_usage_history_path(app_id)}/{conversation_id or message_id}', data)
    return data


# ********************************
# *********** PERSONAS ***********
# ********************************


def delete_persona_db(persona_id: str) -> None:
    _store().delete(_app_path(persona_id))


def get_personas_by_username_db(persona_id: str) -> Optional[List[Dict[str, Any]]]:
    docs = _store().query(apps_collection, filters=[('username', '==', persona_id)])
    if not docs:
        return None
    return [{**_typed_doc(doc), 'doc_id': doc.id} for doc in docs]


def get_persona_by_username_db(username: str) -> Optional[Dict[str, Any]]:
    filters: List[Filter] = [('username', '==', username), ('capabilities', 'array_contains', 'persona')]
    docs = _store().query(apps_collection, filters=filters, limit=1)
    if not docs:
        return None
    raw: object = docs[0].to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None


def get_persona_by_id_db(persona_id: str) -> Optional[Dict[str, Any]]:
    doc = _store().get(_app_path(persona_id))
    if doc.exists:
        raw: object = doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_persona_by_uid_db(uid: str) -> Optional[Dict[str, Any]]:
    filters: List[Filter] = [('uid', '==', uid), ('capabilities', 'array_contains', 'persona')]
    docs = _store().query(apps_collection, filters=filters, limit=1)
    if not docs:
        return None
    raw: object = docs[0].to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None


def get_user_persona_by_uid(uid: str) -> Optional[Dict[str, Any]]:
    filters: List[Filter] = [
        ('capabilities', 'array_contains', 'persona'),
        ('category', '==', 'personality-emulation'),
        ('uid', '==', uid),
    ]
    docs = _store().query(apps_collection, filters=filters, limit=1)
    if not docs:
        return None
    return {'id': docs[0].id, **_typed_doc(docs[0])}


def get_persona_by_twitter_handle_db(handle: str) -> Optional[Dict[str, Any]]:
    filters: List[Filter] = [('category', '==', 'personality-emulation'), ('twitter.username', '==', handle)]
    docs = _store().query(apps_collection, filters=filters, limit=1)
    if not docs:
        return None
    return {'id': docs[0].id, **_typed_doc(docs[0])}


def get_persona_by_username_twitter_handle_db(username: str, handle: str) -> Optional[Dict[str, Any]]:
    filters: List[Filter] = [
        ('username', '==', username),
        ('category', '==', 'personality-emulation'),
        ('twitter.username', '==', handle),
    ]
    docs = _store().query(apps_collection, filters=filters, limit=1)
    if not docs:
        return None
    return {'id': docs[0].id, **_typed_doc(docs[0])}


def get_omi_personas_by_uid_db(uid: str) -> List[Dict[str, Any]]:
    filters: List[Filter] = [('uid', '==', uid), ('capabilities', 'array_contains', 'persona')]
    docs = _store().query(apps_collection, filters=filters)
    if not docs:
        return []
    typed_docs = [_typed_doc(doc) for doc in docs]
    docs_out = [d for d in typed_docs if 'omi' in d.get('connected_accounts', [])]
    return docs_out


def get_omi_persona_apps_by_uid_db(uid: str) -> List[Dict[str, Any]]:
    filters: List[Filter] = [('uid', '==', uid), ('category', '==', 'personality-emulation')]
    docs = _store().query(apps_collection, filters=filters)
    if not docs:
        return []
    return [_typed_doc(doc) for doc in docs]


def update_persona_in_db(persona_data: Dict[str, Any]) -> None:
    _store().update(_app_path(persona_data['id']), persona_data)


def migrate_app_owner_id_db(new_id: str, old_id: str) -> None:
    store = _store()
    for app in store.query(apps_collection, filters=[('uid', '==', old_id)]):
        store.update(_app_path(app.id), {'uid': new_id})


def create_api_key_db(app_id: str, api_key_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new API key for an app in the database"""
    _store().set(f'{_api_keys_path(app_id)}/{api_key_data["id"]}', api_key_data)
    return api_key_data


def get_api_key_by_hash_db(app_id: str, hashed_key: str) -> Optional[Dict[str, Any]]:
    """Get an API key by its hash value"""
    docs = _store().query(_api_keys_path(app_id), filters=[('hashed', '==', hashed_key)], limit=1)
    if not docs:
        return None
    raw: object = docs[0].to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None


def list_api_keys_db(app_id: str) -> List[Dict[str, Any]]:
    """List all API keys for an app (excluding the hashed values)"""
    docs = _store().query(_api_keys_path(app_id), order_by='created_at', direction='desc')
    return [{k: v for k, v in _typed_doc(doc).items() if k != 'hashed'} for doc in docs]


def delete_api_key_db(app_id: str, key_id: str) -> bool:
    """Delete an API key"""
    _store().delete(f'{_api_keys_path(app_id)}/{key_id}')
    return True
