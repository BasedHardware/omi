"""Durable, ceiling-bounded owner passes with a cooperative tick deadline."""

import logging
import time

from google.api_core.exceptions import (
    Aborted,
    Cancelled,
    ClientError,
    FailedPrecondition,
    GoogleAPICallError,
    ResourceExhausted,
)
from config.batch_pipeline import (
    ready_discovery_cursor_enabled,
    ready_discovery_owners_per_tick,
    ready_discovery_tick_seconds,
)
from utils.observability.fallback import record_fallback

try:
    from psycopg import OperationalError
except ImportError:  # The driver is optional outside Postgres processes.
    OperationalError = ()

logger = logging.getLogger(__name__)

# Client-class statuses that pass by themselves; any other 4xx (permission, bad argument, not
# found) is a fault to fix, not an outage.
_TRANSIENT_CLIENT = (FailedPrecondition, Aborted, ResourceExhausted, Cancelled)


class ReadyDiscovery:
    def __init__(self, store, source):
        self.store, self.source = store, source
        self.retry_at = 0.0

    def retry(self, error):
        if isinstance(error, FailedPrecondition):
            self.retry_at = time.monotonic() + 300
        permanent = isinstance(error, ClientError) and not isinstance(error, _TRANSIENT_CLIENT)
        unavailable = (isinstance(error, GoogleAPICallError) and not permanent) or isinstance(error, OperationalError)
        logger.log(
            logging.WARNING if unavailable else logging.ERROR,
            'event=batch_merge action=ready_cursor outcome=%s exception_type=%s count=1',
            'retry' if unavailable else 'error',
            type(error).__name__,
        )
        record_fallback(
            component='firestore_read',
            from_mode='ready_cursor',
            to_mode='ready_page',
            reason='unavailable' if unavailable else 'other',
            outcome='degraded',
        )
        self.log(0, 1, 0)

    def page(self):
        if not ready_discovery_cursor_enabled():
            return None
        if time.monotonic() < self.retry_at:
            self.log(0, 1, 0)
            return None
        deadline = time.monotonic() + ready_discovery_tick_seconds()
        try:
            state = self.store.run(lambda tx: tx.get('merge_discovery', 'cursor'))
            expected = dict(state)
            revision = state.get('revision', 0)
            if type(revision) is not int or revision < 0:
                raise ValueError('invalid ready cursor revision')
            state['owners_per_tick'] = ready_discovery_owners_per_tick(state.get('owners_per_tick', 20))
            if not state.get('ceiling_owner_key') and time.monotonic() >= deadline:
                # The cursor read spent the tick: start the pass (its ceiling query) next tick.
                return dict(
                    cursor=state,
                    expected_cursor=expected,
                    deadline=deadline,
                    owners=0,
                    missing=0,
                    spent=1,
                    wrapped=0,
                    failed=False,
                    deferred=True,
                )
            if not state.get('ceiling_owner_key'):
                ceiling = self.store.ready_owners(None, 1, descending=True)
                state.update(
                    after_owner_key=None,
                    ceiling_owner_key=ceiling[0][0] if ceiling else None,
                    pass_started_at=time.time(),
                )
            return dict(
                cursor=state,
                expected_cursor=expected,
                deadline=deadline,
                owners=0,
                missing=0,
                spent=0,
                wrapped=0,
                failed=False,
            )
        except Exception as error:
            self.retry(error)
            return None

    def owners(self, page):
        state = page['cursor']
        if page.get('deferred'):
            return
        try:
            for _ in range(state['owners_per_tick']):
                if not state['ceiling_owner_key'] or state.get('after_owner_key') == state['ceiling_owner_key']:
                    page['wrapped'] = 1
                    break
                if time.monotonic() >= page['deadline']:
                    page['spent'] = 1
                    break
                owners = self.store.ready_owners(
                    state.get('after_owner_key'), 1, ceiling_owner_key=state['ceiling_owner_key']
                )
                if not owners:
                    page['wrapped'] = 1
                    break
                if time.monotonic() >= page['deadline']:
                    page['spent'] = 1
                    break
                key, owner_id = owners[0]
                if owner_id:
                    yield key, owner_id
                    page['owners'] += 1
                else:
                    page['missing'] += 1
                state['after_owner_key'] = key
            if state.get('after_owner_key') == state['ceiling_owner_key']:
                page['wrapped'] = 1
            page['spent'] |= int(time.monotonic() >= page['deadline'])
        except Exception as error:
            page['failed'] = True
            self.retry(error)

    def next_owner(self, page):
        iterator = page.setdefault('iterator', self.owners(page))
        return next(iterator, None)

    def finish(self, page):
        if page['failed']:
            return False
        state = page['cursor']
        if page['wrapped']:
            state.update(after_owner_key=None, ceiling_owner_key=None)

        def save(tx):
            if tx.get('merge_discovery', 'cursor') != page['expected_cursor']:
                return False
            tx.put('merge_discovery', 'cursor', {**state, 'revision': page['expected_cursor'].get('revision', 0) + 1})
            return True

        try:
            saved = self.store.run(save)
        except Exception as error:
            self.retry(error)
            return False
        if not saved:
            # Another tick owns the progress. Do not rewind it or claim a stale wrap.
            page['wrapped'] = 0
            logger.info('event=batch_merge action=ready_cursor outcome=stale_page source=%s count=1', self.source)
        self.log(page['owners'], 1 - page['wrapped'], page['wrapped'], page['spent'], page['missing'])
        return True

    def log(self, owners, more, wrapped, budget_spent=0, missing_owner_id=0):
        logger.info(
            'event=batch_merge action=ready_cursor owners=%d more=%d wrapped=%d source=%s '
            'budget_spent=%d missing_owner_id=%d',
            owners,
            more,
            wrapped,
            self.source,
            budget_spent,
            missing_owner_id,
        )
