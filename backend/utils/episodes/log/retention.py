"""Read-only TTL preconditions. Never activates or changes a retention policy."""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_cache = {}
_guard_until = {}
CACHE_SECONDS = 60


def ttl_active(project, database='(default)'):
    from google.cloud import firestore_admin_v1

    field = firestore_admin_v1.FirestoreAdminClient().get_field(
        request={'name': f'projects/{project}/databases/{database}/collectionGroups/episode_facts/fields/expires_at'},
        timeout=3,
        retry=None,
    )
    return field.ttl_config.state == firestore_admin_v1.Field.TtlConfig.State.ACTIVE


def active(client):
    # Synthetic loopback tests have no TTL admin surface and never reach cloud.
    if os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        return True
    key = (client.project, client._database)
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        try:
            allowed = ttl_active(*key)
        except Exception as error:
            logger.warning('event=episode_log_ttl outcome=unknown exception_type=%s', type(error).__name__)
            allowed = False
        if len(_cache) >= 16:
            _cache.clear()
        _cache[key] = (now + CACHE_SECONDS, allowed)
    return allowed


def require_active(client):
    if not active(client):
        raise RuntimeError('episode_facts_ttl_not_active')


def guard(client):
    """No data probe while capture is off; admitted probes run at most once/minute."""
    from config import episode_log as config

    if not config.capture_possible():
        return
    key = (getattr(client, 'project', None), getattr(client, '_database', '(default)'))
    now = time.monotonic()
    with _lock:
        if _guard_until.get(key, 0) > now:
            return
        if len(_guard_until) >= 16:
            _guard_until.clear()
        _guard_until[key] = now + CACHE_SECONDS
    allowed = active(client)
    from utils.episodes.log.metrics import FACTS_WITHOUT_TTL

    exists = not allowed and bool(list(client.collection_group('episode_facts').select([]).limit(1).stream()))
    FACTS_WITHOUT_TTL.set(int(exists))
    if exists:
        logger.error('event=episode_log_ttl outcome=facts_without_active_ttl capture=refused')
