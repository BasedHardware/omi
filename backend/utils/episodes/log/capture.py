"""Best-effort capture AFTER the SDK commits the serving write.

An instance-local commit observer adds no log reads, writes or locks to the
serving transaction. Each SDK attempt replaces its intent; an aborted attempt
never appends. Log contention/retries cannot retry the committed serving write.
"""

import logging
from uuid import uuid4

from config import episode_log as config

logger = logging.getLogger(__name__)


def dropped(error, *, uid=None, client=None, cid=None, token=None):
    if not config.capture_possible():
        return
    from utils.observability.fallback import record_fallback

    try:
        record_fallback(
            component='sync_dispatch',
            from_mode='episode_capture',
            to_mode='legacy',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    except Exception:
        logger.warning('event=episode_capture outcome=dropped')
    if uid:
        from database import episode_log as store

        try:
            store.invalidate(uid, firestore_client=client, cid=cid, token=token)
        except Exception as marker_error:
            logger.error(
                'event=episode_capture outcome=invalidation_failed exception_type=%s', type(marker_error).__name__
            )


def submit(fn):
    from utils.executors import get_episode_capture_executor, submit_with_context

    return submit_with_context(get_episode_capture_executor(), fn)


def dispatch(fn, *, uid, client):
    """No capacity wait. Overflow/cancellation is counted and durably fenced."""
    if not config.capture_possible():
        return

    def admitted():
        if config.capture_possible():
            fn()

    try:
        future = submit(admitted)
        future.add_done_callback(lambda done: dropped(None, uid=uid, client=client) if done.cancelled() else None)
    except Exception as error:
        dropped(error, uid=uid, client=client)


class DeferredCapture:
    def __init__(self, client, uid):
        self.client, self.uid = client, uid
        self.events = []
        self.existing_only = False
        self.stage_error = None

    def stage(self, events, **kwargs):
        # Only keep immutable content-free intent while the serving transaction
        # is open. Size checks, encryption and all IO happen after its commit.
        try:
            from utils.episodes.log.facts import compact_events

            self.events.extend(compact_events(events))
        except Exception as error:
            self.stage_error = error  # No IO or marker transaction inside serving.

    def flush(self):
        if not config.capture_possible():
            return
        from database import episode_log as store

        if self.stage_error:
            dropped(self.stage_error, uid=self.uid, client=self.client)
        elif self.events:
            try:
                if not config.enabled(self.uid):
                    return
                if self.existing_only and not store.state(self.uid, firestore_client=self.client):
                    return
                store.append(self.uid, uuid4().hex, self.events, firestore_client=self.client)
            except Exception as error:
                dropped(error, uid=self.uid, client=self.client)


def prepare_capture(transaction, client, uid):
    try:
        # Global admission may refresh the control-plane flag cache. It never
        # reads customer data; per-UID admission is still checked after commit.
        if not config.capture_possible() or not config.episodes_enabled_for(uid):
            return None
        capture = DeferredCapture(client, uid)
        if not hasattr(transaction, '_episode_capture_commit'):
            original = transaction._commit

            def committed(*args, **kwargs):
                result = original(*args, **kwargs)
                try:
                    intent = transaction._episode_capture
                    if config.capture_possible() and (intent.events or intent.stage_error):
                        dispatch(intent.flush, uid=uid, client=client)
                except Exception as error:
                    dropped(error, uid=uid, client=client)
                return result

            transaction._episode_capture_commit = original
            transaction._commit = committed
        transaction._episode_capture = capture
        return capture
    except Exception as error:
        dropped(error, uid=uid, client=client)
        return None
