"""Leader-owned durable owner walk; failures retain the legacy ready-page path."""

import logging
import time

from google.api_core.exceptions import FailedPrecondition
from config.batch_pipeline import ready_discovery_cursor_enabled, ready_discovery_owners_per_tick
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


class ReadyDiscovery:
    def __init__(self, store, source):
        self.store, self.source = store, source
        self.retry_at = 0.0

    def retry(self, error):
        if isinstance(error, FailedPrecondition):
            self.retry_at = time.monotonic() + 300
        logger.warning(
            'event=batch_merge action=ready_cursor outcome=retry exception_type=%s count=1', type(error).__name__
        )
        record_fallback(
            component='firestore_read',
            from_mode='ready_cursor',
            to_mode='ready_page',
            reason='unavailable',
            outcome='degraded',
        )
        self.log(0, 1, 0)

    def page(self):
        if not ready_discovery_cursor_enabled():
            return None
        if time.monotonic() < self.retry_at:
            self.log(0, 1, 0)
            return None
        try:
            state = self.store.run(lambda tx: tx.get('merge_discovery', 'cursor'))
            budget = ready_discovery_owners_per_tick(state.get('owners_per_tick', 20))
            owners = self.store.ready_owners(state.get('after_owner_key'), budget)
            state = {
                'after_owner_key': owners[-1][0] if owners else None,
                'pass_started_at': state.get('pass_started_at', time.time()) if owners else time.time(),
                'owners_per_tick': budget,
            }
            return owners, state
        except Exception as error:
            self.retry(error)
            return None

    def finish(self, page):
        owners, state = page
        try:
            self.store.run(lambda tx: tx.put('merge_discovery', 'cursor', state))
        except Exception as error:
            self.retry(error)
            return False
        self.log(len(owners), int(len(owners) == state['owners_per_tick']), int(not owners))
        return True

    def log(self, owners, more, wrapped):
        logger.info(
            'event=batch_merge action=ready_cursor owners=%d more=%d wrapped=%d source=%s',
            owners,
            more,
            wrapped,
            self.source,
        )
