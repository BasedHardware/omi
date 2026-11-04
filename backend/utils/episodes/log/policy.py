"""Fence cached Home policy around member mutations, before the write commits.

A lost process leaves a deadline-stamped dirty barrier, so readers use the
legacy policy path until the sweeper refreshes that member after the deadline.
"""

import inspect
from functools import wraps
from uuid import uuid4

from config import episode_log as config
from database import episode_log as store


def _tracked(uid):
    if not config.enabled(uid) or not config.home_enabled():
        return False
    # Shadow rows must stay fresh before read admission. Do not create a new
    # log for a user who has never produced an episode fact.
    return bool(store.state(uid))


def home_policy_write(fn):
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
        if not cid or not _tracked(uid):
            return fn(*args, **kwargs)
        token = uuid4().hex
        store.policy_barrier(uid, cid, token, entering=True)
        try:
            return fn(*args, **kwargs)
        finally:
            # Even a failed write refreshes current policy before releasing the
            # fence. If this fails the durable barrier keeps reads on legacy.
            store.policy_barrier(uid, cid, token, entering=False)

    return wrapped
