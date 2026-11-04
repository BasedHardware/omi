"""Fence cached Home policy around member mutations, before the write commits.

A lost process leaves a deadline-stamped dirty barrier, so readers use the
legacy policy path until the sweeper refreshes that member after the deadline.
"""

import inspect
from functools import partial, wraps
from uuid import uuid4

from config import episode_log as config
from database import episode_log as store


def home_policy_write(*, firestore_client):
    return partial(_decorate, client_factory=firestore_client)


def _decorate(fn, *, client_factory):
    signature = inspect.signature(fn)

    @wraps(fn)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs).arguments
        uid = bound.get('uid')
        if not uid:
            return fn(*args, **kwargs)
        cid = bound.get('conversation_id')
        if not cid:
            data = bound.get('conversation_data') or {}
            cid = data.get('id') if isinstance(data, dict) else None
        if not cid or not config.enabled(uid) or not config.home_enabled():
            return fn(*args, **kwargs)
        # Shadow rows stay fresh before read admission. Join the writer's data
        # plane, and do not create logs for users without any episode facts.
        client = client_factory()
        if not store.state(uid, firestore_client=client):
            return fn(*args, **kwargs)
        token = uuid4().hex
        store.policy_barrier(uid, cid, token, entering=True, firestore_client=client)
        try:
            return fn(*args, **kwargs)
        finally:
            # Even a failed write refreshes current policy before releasing the
            # fence. If this fails the durable barrier keeps reads on legacy.
            store.policy_barrier(uid, cid, token, entering=False, firestore_client=client)

    return wrapped
