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
        from utils.episodes.log.capture import dropped, dispatch

        if not cid:
            return fn(*args, **kwargs)
        token = uuid4().hex
        try:
            admitted = config.enabled(uid) and config.home_enabled()
        except Exception as error:
            dropped(error, uid=uid, cid=cid, token=token)
            admitted = False
        if not admitted:
            return fn(*args, **kwargs)
        client, has_log = None, True
        try:
            client = client_factory()
            has_log = bool(store.state(uid, firestore_client=client))
            if has_log:
                store.policy_barrier(uid, cid, token, entering=True, firestore_client=client)
        except Exception as error:
            # Keep a deadline-stamped fence while the original writer is still
            # running, even when the ordinary barrier append failed. Otherwise
            # a repair could race ahead of that writer and clear the gap early.
            dropped(error, uid=uid, client=client, cid=cid, token=token)
        if not has_log:
            return fn(*args, **kwargs)
        try:
            return fn(*args, **kwargs)
        finally:
            # Even a failed write refreshes current policy before releasing the
            # fence. If this fails the durable barrier keeps reads on legacy.
            def refresh():
                try:
                    refresh_client = client if client is not None else client_factory()
                    if not config.enabled(uid):
                        return
                    store.policy_barrier(uid, cid, token, entering=False, firestore_client=refresh_client)
                except Exception as error:
                    dropped(error, uid=uid, client=client)

            dispatch(refresh, uid=uid, client=client)

    return wrapped
