"""Best-effort capture AFTER the SDK commits the serving write.

An instance-local commit observer adds no log reads, writes or locks to the
serving transaction. Each SDK attempt replaces its intent; an aborted attempt
never appends. Log contention/retries cannot retry the committed serving write.
"""

import logging
from uuid import uuid4

from config import episode_log as config

logger = logging.getLogger(__name__)


def dropped(error):
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


class DeferredCapture:
    def __init__(self, client, uid):
        self.client, self.uid = client, uid
        self.events = []
        self.existing_only = False

    def stage(self, events, **kwargs):
        # Only keep immutable content-free intent while the serving transaction
        # is open. Size checks, encryption and all IO happen after its commit.
        try:
            from utils.episodes.log.facts import compact_events

            self.events.extend(compact_events(events))
        except Exception as error:
            dropped(error)

    def flush(self):
        from database import episode_log as store

        if self.events:
            try:
                if not config.enabled(self.uid):
                    return
                if self.existing_only and not store.state(self.uid, firestore_client=self.client):
                    return
                store.append(self.uid, uuid4().hex, self.events, firestore_client=self.client)
            except Exception as error:
                dropped(error)


def prepare_capture(transaction, client, uid):
    try:
        # Do not resolve a remote flag while the serving transaction is open.
        if not config.episodes_enabled_for(uid):
            return None
        capture = DeferredCapture(client, uid)
        if not hasattr(transaction, '_episode_capture_commit'):
            original = transaction._commit

            def committed(*args, **kwargs):
                result = original(*args, **kwargs)
                try:
                    transaction._episode_capture.flush()
                except Exception as error:
                    dropped(error)
                return result

            transaction._episode_capture_commit = original
            transaction._commit = committed
        transaction._episode_capture = capture
        return capture
    except Exception as error:
        dropped(error)
        return None
