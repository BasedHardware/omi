"""Ordered durable result log. Projection consumers must use stable segment IDs."""

import logging
import time

from google.api_core.exceptions import FailedPrecondition, GoogleAPICallError

from config.batch_pipeline import merge_catch_up_depth, merge_head_wait_seconds, recovered_merge_release_enabled
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import Store
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.metrics import QueueMetrics
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# A missing head-wait index falls back to strict order; retry the query after this.
HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS = 300
# Pending fresh rows read per probe (the query cap); an owner rarely has more in flight.
FRESH_PROBE_ROWS = 32
# Content siblings a recovery wake may release with the recovered unit.
RELEASE_SIBLINGS_MAX = 32
_HEAD_STATES = frozenset({'ready', 'leased', 'retry', 'record_pending', 'privacy_blocked'})
_FRESH_FIRST_HEAD_STATES = _HEAD_STATES | {'result_ready'}
_RELEASE_HEAD_STATES = _FRESH_FIRST_HEAD_STATES | {'held'}
_WAIT_BUCKETS = (60, 120, 300, 600, 1800)


class HeadWaitUnavailable(Exception):
    """The head-wait query has no serving index; the merge keeps strict order."""


def _wait_bucket(seconds: float) -> str:
    return next((f'lt{bound}' for bound in _WAIT_BUCKETS if seconds < bound), f'ge{_WAIT_BUCKETS[-1]}')


def _catch_up(job: dict) -> bool:
    # Only rows classified at admission; record-lane and older rows keep the plain order.
    return job.get('fresh_capture') is False


def _fresh_pick(rows: list[dict], now: float, wait: float) -> tuple[dict | None, dict | None]:
    """The earliest pending fresh row once ready. If it is not, and a ready fresh
    row has waited ``wait`` behind it, the earliest ready one (the bounded head
    wait among fresh rows; the skipped row appends later as late_capture)."""
    if not rows:
        return None, None
    if rows[0].get('state') == 'result_ready':
        return rows[0], None
    ready = [row for row in rows if row.get('state') == 'result_ready']
    waited = max((now - row['ready_at'] for row in ready if row.get('ready_at') is not None), default=None)
    if wait > 0 and waited is not None and waited >= wait:
        earlier = [row['segment_id'] for row in rows[: rows.index(ready[0])]]
        return ready[0], {'segment_ids': earlier, 'state': rows[0].get('state'), 'waited': waited}
    return None, None


def _awaiting_projection(tx, owner: dict) -> int:
    """Committed rows not yet projected. A missing watermark row never holds a commit."""
    sequence = owner.get('log_sequence', 0)
    projected = owner.get('projection_watermark')
    if not projected:
        return sequence
    done = tx.get('results', projected).get('log_sequence')
    return sequence - done if done else 0


class OrderedMerge:
    def __init__(
        self,
        store: Store,
        *,
        metrics: QueueMetrics | None = None,
        commit_source: str = 'ordered_merge',
        head_wait_seconds: float | None = None,
        catch_up_depth: int | None = None,
    ):
        self.store = store
        self.metrics = metrics
        self.commit_source = commit_source
        # None reads BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS on every commit.
        self.head_wait_seconds = head_wait_seconds
        # None reads BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH on every commit.
        self.catch_up_depth = catch_up_depth
        self._head_wait_retry_at = 0.0
        self._fresh_first_retry_at = 0.0
        # Owners whose last commit attempt found them at the projection depth
        # cap with rows pending. Maintenance re-offers them by owner: a held
        # backlog can fill the global result_ready page and hide them.
        self.held_owners: set[str] = set()
        self._marked_after: str | None = None

    def _head_wait(self) -> float:
        if time.monotonic() < self._head_wait_retry_at:
            return 0.0
        return self.head_wait_seconds if self.head_wait_seconds is not None else merge_head_wait_seconds()

    def _catch_up_depth(self) -> int:
        if time.monotonic() < self._fresh_first_retry_at:
            return 0
        return self.catch_up_depth if self.catch_up_depth is not None else merge_catch_up_depth()

    def release_hold(self, key: str, *, force: bool = False) -> None:
        """Clear an owner's durable hold marker once it is below the depth cap (or has nothing pending)."""
        depth = self._catch_up_depth()

        def clear(tx):
            mark = tx.get('merge_holds', key)
            if mark.get('held') and (force or not depth or _awaiting_projection(tx, tx.get('owners', key)) < depth):
                tx.put('merge_holds', key, {**mark, 'held': False})

        self.store.run(clear)

    def marked_page(self, limit: int = 50) -> list[tuple[str, str | None]]:
        """The next page of durable hold markers; the cursor rotates so every
        marked owner is reached however many stay held."""
        page = self.store.held_merge_owners(limit, after=self._marked_after)
        self._marked_after = page[-1][0] if len(page) >= limit else None
        return page

    def reoffer_marked(self, drain, limit: int = 50) -> None:
        """Leader maintenance: re-offer owners holding durable markers, which an
        in-memory set loses on restart and the global ready page can hide."""
        for key, owner_id in self.marked_page(limit):
            try:
                if owner_id:
                    drain(owner_id)
                self.release_hold(key, force=not owner_id)
            except Exception as error:
                # One fenced or failing owner must not starve the rest of the page.
                logger.warning(
                    'event=batch_merge action=held_reoffer outcome=retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )

    def _head_wait_unavailable(self) -> None:
        self._head_wait_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
        logger.warning('event=batch_merge outcome=head_wait_unavailable source=%s count=1', self.commit_source)
        record_fallback(
            component='firestore_read',
            from_mode='head_wait',
            to_mode='strict_order',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
        return None

    def release_set(self, segment_id: str) -> list[str]:
        """The recovered unit first, then its content's other units (bounded).

        A recovery wake passes this to ``commit_next(release=...)``. Only rows
        still pending and ready are ever committed from it."""
        job = self.store.run(lambda tx: tx.get('jobs', segment_id))
        siblings = (job.get('projection_binding') or {}).get('segment_ids') or []
        return [segment_id, *[sid for sid in siblings if sid != segment_id][:RELEASE_SIBLINGS_MAX]]

    def _next_release(self, key: str, release: list[str]) -> str | None:
        """Drop release rows that are not this owner's pending, ready rows; return the first that is."""
        while release:
            segment = release[0]
            job = self.store.run(lambda tx: tx.get('jobs', segment))
            if job.get('owner_key') == key and job.get('merge_pending') and job.get('state') == 'result_ready':
                return segment
            release.pop(0)
        return None

    def commit_next(self, owner_id: str, now: float, *, release: list[str] | None = None) -> dict | None:
        """Commit the owner's next result-log row, or return None.

        ``release`` (a recovery wake's ``release_set``, consumed in place):
        when strict order, fresh-first and the head wait commit nothing, the
        first still-pending ready row in it commits at once. Recovered units
        already waited out quarantine and recovery, so the set skips the head
        wait; only the recovered unit also passes the catch-up depth hold. The
        body, late marking and chain are the same as every other commit."""
        key = owner_key(owner_id)
        wait = self._head_wait()
        depth = self._catch_up_depth()
        blocked: dict = {}
        bypass: dict = {}
        fresh_first: dict = {}
        released: dict = {}
        held: dict = {}
        head: dict = {}

        def commit(
            tx,
            waiter: dict | None = None,
            fresh: dict | None = None,
            skipped: dict | None = None,
            exact: str | None = None,
        ):
            blocked.clear()  # Firestore may retry this callback.
            bypass.clear()
            fresh_first.clear()
            released.clear()
            held.clear()
            head.clear()
            owner = tx.get('owners', key)
            # Terminal quarantine atomically removes merge_pending; it never
            # enters this success log or the projection predecessor chain.
            candidate = tx.first_pending(key)
            if candidate and candidate.get('shadow'):
                return None
            over_cap = bool(depth and candidate and _awaiting_projection(tx, owner) >= depth)
            if candidate:
                head['catch_up'] = _catch_up(candidate)
            if exact is not None:
                # Recovered release: the wake's row must still be this owner's
                # pending, ready row. It appends at the tail like any commit;
                # anything it passes appends later, as late_capture if behind.
                current = tx.get('jobs', exact)
                if current.get('shadow'):
                    return None
                if not (
                    current.get('owner_key') == key
                    and current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                ):
                    return None
                if candidate and candidate.get('segment_id') != exact:
                    released['head_state'] = candidate['state']
                else:
                    released['head_state'] = 'held' if over_cap else 'ready'
                # Only the recovered unit itself (it already waited out
                # quarantine and recovery) passes the catch-up depth hold;
                # its content siblings keep it, so a wake cannot pile up to
                # 33 rows past the cap ahead of a later fresh row.
                released['recovered'] = current.get('recovery_state') == 'recovered'
                candidate = current
            elif over_cap and waiter is None and fresh is None:
                # At the depth cap with rows pending, whatever the head's state:
                # maintenance re-offers this owner, and the durable marker
                # (owner key only) survives a restart.
                held['over_cap'] = True
                if not tx.get('merge_holds', key).get('held'):
                    tx.put('merge_holds', key, {'held': True, 'held_at': now})
            if fresh is not None:
                # Fresh-first (David's fresh bar, 2026-10-20): the probed fresh
                # row must still be pending and ready behind a catch-up head;
                # it commits ahead of that backlog, which appends later as
                # late_capture through the unchanged body below.
                current = tx.get('jobs', fresh['segment_id'])
                if not (
                    candidate
                    and _catch_up(candidate)
                    and current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                    and current.get('fresh_capture') is True
                ):
                    return None
                if skipped is not None:
                    # Every skipped earlier fresh row must still be unready;
                    # otherwise the next drain commits them in capture order.
                    for earlier in skipped['segment_ids']:
                        row = tx.get('jobs', earlier)
                        if row.get('merge_pending') and row.get('state') == 'result_ready':
                            return None
                    bypass.update(head_state=skipped['state'], waited=skipped['waited'])
                fresh_first.update(head_state=candidate['state'])
                candidate = current
            elif candidate and candidate['state'] != 'result_ready':
                if waiter is None:
                    blocked.update(head_state=candidate['state'], catch_up=_catch_up(candidate))
                    return None
                # Bounded head wait (David, 2026-10-20): the probed waiter must
                # still be pending and ready; then release the owner's ready
                # rows in capture order. The bypassed head later appends as
                # late_capture through the unchanged body below.
                current = tx.get('jobs', waiter['segment_id'])
                if not (
                    current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                    and current.get('ready_at') == waiter['ready_at']
                ):
                    return None
                bypass.update(head_state=candidate['state'], waited=now - waiter['ready_at'])
                try:
                    candidate = tx.first_ready_pending(key)
                except FailedPrecondition as error:
                    raise HeadWaitUnavailable from error
            if not candidate or candidate['state'] != 'result_ready':
                return None
            if over_cap and not fresh_first and not released.get('recovered') and _catch_up(candidate):
                # Keep the owner's unprojected log short so a fresh row lands
                # near the projection head.
                held['catch_up'] = True
                return None
            job = tx.get('jobs', candidate['segment_id'])
            existing = tx.get('results', job['segment_id'])
            if existing:
                raise RuntimeError('result log exists for pending job; reconciliation required')
            watermark = owner.get('watermark')
            position = {'capture_at': job['capture_at'], 'segment_id': job['segment_id']}
            late = bool(
                watermark
                and (position['capture_at'], position['segment_id'])
                <= (watermark['capture_at'], watermark['segment_id'])
            )
            tail = owner.get('log_tail', watermark['segment_id'] if watermark else None)
            entry = {
                **position,
                'protocol_version': job['protocol_version'],
                'owner_key': key,
                'owner_id': job['owner_id'],
                'conversation_id': job.get('conversation_id'),
                'privacy_generation': job.get('privacy_generation'),
                'previous_segment_id': tail,
                'late_capture': late,
                'log_sequence': owner.get('log_sequence', 0) + 1,
                'result': job['result'],
                'committed_at': now,
                'projection_state': 'pending',
            }
            if job.get('recovery_state') == 'recovered' or (job.get('stt_route') or {}).get('stt_route') == 'provider':
                entry['recovery_version'] = 1
            if bypass:
                entry['head_wait_bypass'] = True
            if fresh_first:
                entry['fresh_first'] = True
            if released:
                entry['recovered_release'] = True
            tx.put('results', job['segment_id'], entry)
            job.update(state='committed', merge_pending=False)
            tx.put('jobs', job['segment_id'], job)
            owner.update(
                watermark=watermark if late else position,
                log_tail=job['segment_id'],
                log_sequence=entry['log_sequence'],
                revision=owner.get('revision', 0) + 1,
            )
            tx.put('owners', key, owner)
            return entry

        fenced: BatchPrivacyBlocked | None = None
        try:
            entry = self.store.run(commit)
        except BatchPrivacyBlocked as error:
            entry, fenced = None, error
        strict_blocked, strict_catch_up = dict(blocked), bool(held.get('catch_up'))
        if held.get('over_cap'):
            self.held_owners.add(owner_id)
        else:
            self.held_owners.discard(owner_id)
        if fenced is not None and not (depth and head.get('catch_up')):
            # A fenced catch-up head must not hide the owner's ready fresh rows;
            # any other fence keeps its strict-order behaviour.
            raise fenced
        if entry is None and depth and (strict_catch_up or strict_blocked.get('catch_up') or fenced):
            # A catch-up row heads the owner. Probe for a ready fresh row
            # outside the strict transaction (no transactional query lock);
            # only a ready one opens a second, re-verifying transaction.
            try:
                pending = self.store.fresh_pending(key, FRESH_PROBE_ROWS)
            except FailedPrecondition:
                # Without the fresh query a catch-up hold would also hold fresh
                # rows: take the plain order now and retry the query later.
                self._fresh_first_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
                logger.warning(
                    'event=batch_merge outcome=fresh_first_unavailable source=%s count=1', self.commit_source
                )
                record_fallback(
                    component='firestore_read',
                    from_mode='fresh_first',
                    to_mode='ordered_merge',
                    reason='unavailable',
                    outcome='degraded',
                    log=logger,
                )
                self.held_owners.discard(owner_id)
                return self.commit_next(owner_id, now, release=release)
            except GoogleAPICallError as error:
                # A transient probe read keeps the strict result; the next drain probes again.
                logger.warning(
                    'event=batch_merge outcome=fresh_first_probe_retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )
                pending = []
            fresh, skipped = _fresh_pick(pending, now, wait)
            if fresh is not None:
                try:
                    entry = self.store.run(lambda tx: commit(tx, fresh=fresh, skipped=skipped))
                except BatchPrivacyBlocked:
                    # A fence on that fresh row refuses only it; the head wait
                    # below still releases the owner's other ready rows.
                    entry = None
                    fresh_first.clear()
                    bypass.clear()
        if entry is None and fenced is not None:
            raise fenced
        if entry is None and release and recovered_merge_release_enabled():
            # Recovery wake: commit the recovered unit (then its content's
            # ready siblings) now instead of after the head wait or the depth
            # hold. Run 18: 46 of 54 wakes advanced no row; held recovered
            # units waited 65-86 s for the head wait plus a maintenance tick.
            segment = self._next_release(key, release)
            if segment is not None:
                try:
                    entry = self.store.run(lambda tx: commit(tx, exact=segment))
                    if entry is not None and entry['segment_id'] == segment:
                        release.pop(0)  # Committed: the next call need not re-read it.
                except BatchPrivacyBlocked:
                    # A fence refuses only this row; strict order commits nothing here.
                    release.pop(0)
                    entry = None
                    released.clear()
        if entry is None and strict_blocked and wait > 0:
            # The strict transaction issues no head-wait query. Probe outside
            # it so a blocked owner takes no extra transactional query lock;
            # only an expired wait opens a second, re-verifying transaction.
            # Every early return below is strict order's result: the head is not ready.
            try:
                waiter = self.store.longest_ready_pending(key)
            except FailedPrecondition:
                return self._head_wait_unavailable()
            except GoogleAPICallError as error:
                # A transient probe read must not fail a drain strict order would finish.
                logger.warning(
                    'event=batch_merge outcome=head_wait_probe_retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )
                return None
            if not waiter or now - waiter['ready_at'] < wait:
                return None
            try:
                entry = self.store.run(lambda tx: commit(tx, waiter))
            except BatchPrivacyBlocked:
                # An owner-wide fence (often the reason the head is blocked)
                # also refuses the successor; strict order commits nothing here.
                return None
            except HeadWaitUnavailable:
                return self._head_wait_unavailable()
            if held:
                # The released ready row is catch-up and the owner is at depth.
                self.held_owners.add(owner_id)
        if entry:
            record_correctness('committed', source=self.commit_source)
            if self.metrics:
                self.metrics.record('committed')
            if fresh_first:
                head_state = (
                    fresh_first['head_state'] if fresh_first['head_state'] in _FRESH_FIRST_HEAD_STATES else 'other'
                )
                logger.info(
                    'event=batch_merge outcome=fresh_first source=%s head_state=%s count=1',
                    self.commit_source,
                    head_state,
                )
            if released:
                head_state = released['head_state'] if released['head_state'] in _RELEASE_HEAD_STATES else 'other'
                logger.info(
                    'event=batch_merge outcome=recovered_release source=%s head_state=%s count=1',
                    self.commit_source,
                    head_state,
                )
            if bypass:
                head_state = bypass['head_state'] if bypass['head_state'] in _HEAD_STATES else 'other'
                logger.info(
                    'event=batch_merge outcome=head_wait_bypass source=%s head_state=%s wait_bucket=%s count=1',
                    self.commit_source,
                    head_state,
                    _wait_bucket(bypass['waited']),
                )
        return entry

    def committed_result(self, segment_id: str) -> dict:
        """Idempotent re-read after a lost commit reply; no external side effects."""
        return self.store.run(lambda tx: tx.get('results', segment_id))
