"""Allowance parking, independent of compute retries and ordered-result discovery.

The owner cursor is a discovery hint, never permission to spend. Every released
unit still goes through the worker's normal, current admission decision.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import uuid

from config.referral_campaign import GRANT_FIELD, campaign_enabled
from database._client import get_data_plane_firestore_client
from database.batch_pipeline_allowance_hold import STATE, OWNERS, enabled, restore_retry
from utils.batch_pipeline.scheduler import Scheduler
from utils.referral_campaign import effective_subscription_payload
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.firestore_read_origin import read_origin

CHECK_SECONDS = 300
CLAIM_SECONDS = 120


def generation(snapshot: dict, now: float) -> str:
    """Effective authority and its reset periods, never usage counters or content."""
    from utils import backfill_hours_cap

    subscription = snapshot.get('subscription') or {}
    end = subscription.get('current_period_end')
    valid = isinstance(end, (int, float)) and end >= now
    clock = datetime.fromtimestamp(now, timezone.utc)
    promotions = campaign_enabled()
    grant = snapshot.get(GRANT_FIELD) if promotions else None
    # These are the grant fields admission composes. Keep its raw authority so
    # extensions are detected even while paid access masks a grant; the shared
    # effective projection also detects starts/ends and paid-coverage edges
    # without requiring a writer at the time boundary.
    grant_authority = (
        {field: grant.get(field) for field in ('campaign_id', 'status', 'starts_at', 'ends_at', 'paid_coverage')}
        if grant
        else None
    )
    effective = effective_subscription_payload(subscription, grant, now=clock)
    # Admission maps the optional backfill day-cap refusal to allowance_exhausted
    # too. Recheck at its UTC reset even without a plan/month change. Admission
    # remains authority: a still-capped release may park again, once per day.
    reset_period = clock.strftime('%Y-%m-%d') if backfill_hours_cap.cap_enabled() else clock.strftime('%Y-%m')
    value = [subscription, valid, promotions, grant_authority, effective, reset_period]
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class AllowanceHolds:
    def __init__(self, store, entitlement):
        self.store = store
        # Returns (generation, eligible). Resolver failures raise, leaving the
        # generation unacknowledged, so a transport fault cannot strand a month.
        self.entitlement = entitlement

    @read_origin('job:batch_allowance_hold:tick')
    def tick(self, now: float, *, owners: int = 20, page_size: int = 100) -> int:
        page_size = max(1, min(page_size, 100))
        if not enabled():
            released = 0
            for segment in self.store.allowance_page(None, None, page_size):

                def rollback(tx):
                    job = tx.get('jobs', segment)
                    if job.get('state') != STATE:
                        return False
                    key = job['owner_key']
                    owner = tx.get(OWNERS, key)
                    restore_retry(job, now)
                    if owner:
                        owner['held_count'] = max(0, owner.get('held_count', 0) - 1)
                        owner['active'] = owner['held_count'] > 0
                        tx.put(OWNERS, key, owner)
                    tx.put('jobs', segment, job)
                    return True

                try:
                    released += self.store.run(rollback)
                except BatchPrivacyBlocked:
                    self._revoke(segment, now)
            return released
        released = 0
        for key in self.store.allowance_owners(now, owners):
            try:
                released += self._owner(key, now, page_size)
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'event=batch_allowance_hold outcome=retry exception_type=%s', type(error).__name__
                )
        return released

    def _revoke(self, segment: str, now: float) -> None:
        if not self.store.quarantine_fenced(segment, now):
            return

        def retire(tx):
            job = tx.get('jobs', segment)
            key = job.get('owner_key')
            if not key:
                return
            owner = tx.get(OWNERS, key)
            if owner:
                owner['held_count'] = max(0, owner.get('held_count', 0) - 1)
                owner['active'] = owner['held_count'] > 0
                tx.put(OWNERS, key, owner)

        self.store.run(retire)

    def _owner(self, key: str, now: float, page_size: int) -> int:
        token = uuid.uuid4().hex

        def claim(tx):
            row = tx.get(OWNERS, key)
            if not row.get('active') or row.get('check_at', 0) > now or row.get('lease_until', 0) > now:
                return None
            row.update(token=token, lease_until=now + CLAIM_SECONDS, check_at=now + CLAIM_SECONDS)
            tx.put(OWNERS, key, row)
            return row

        owner = self.store.run(claim)
        if owner is None:
            return 0
        try:
            # While draining an acknowledged generation, no repeated funded
            # allowance RPC per page. Dispatch still reauthorizes every unit.
            if not owner.get('draining'):
                current, allowed = self.entitlement(owner['owner_id'], now, owner.get('generation'))

                def acknowledge(tx):
                    row = tx.get(OWNERS, key)
                    if row.get('token') != token:
                        return None
                    changed = current != row.get('generation')
                    row.update(
                        generation=current,
                        draining=changed and allowed,
                        after=None,
                        cutoff=now,
                        release_revision=row['revision'],
                    )
                    tx.put(OWNERS, key, row)
                    return row

                owner = self.store.run(acknowledge)
                if owner is None:
                    return 0
            segments = self.store.allowance_page(key, owner.get('after'), page_size) if owner.get('draining') else []
            released, after = 0, owner.get('after')
            for segment in segments:

                def release(tx):
                    row = tx.get(OWNERS, key)
                    job = tx.get('jobs', segment)
                    if row.get('token') != token or row.get('lease_until', 0) <= now:
                        return None
                    if job.get('state') != STATE or job.get('owner_key') != key:
                        return None
                    cursor = [job['capture_at'], job['segment_id']]
                    # A new refusal in this generation must not be reoffered
                    # indefinitely while a large owner's earlier page drains.
                    if job['allowance_held_at'] > owner['cutoff']:
                        return cursor, False
                    Scheduler.release_allowance_in_transaction(tx, job, now)
                    row['held_count'] = max(0, row.get('held_count', 0) - 1)
                    tx.put(OWNERS, key, row)
                    return cursor, True

                try:
                    outcome = self.store.run(release)
                except BatchPrivacyBlocked:
                    self._revoke(segment, now)
                    outcome = None
                if outcome:
                    after, changed = outcome
                    released += changed

            def finish(tx):
                row = tx.get(OWNERS, key)
                if row.get('token') != token:
                    return
                more = len(segments) == page_size
                if not row.get('held_count'):
                    row['active'] = False
                row.update(
                    after=after, draining=more, token='', lease_until=0.0, check_at=now if more else now + CHECK_SECONDS
                )
                tx.put(OWNERS, key, row)

            self.store.run(finish)
            return released
        except Exception:
            # Durable claim expires; no generation is fabricated on read failure.
            raise


def entitlement(uid: str, now: float, previous: str | None) -> tuple[str, bool]:
    # Serving imports this controller before any owner needs entitlement IO.
    # Keep the billing/provider dependency graph at its admission boundary.
    from utils.stt_cap_dispatch import funded_allowance
    from utils.subscription import TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS

    snapshot = (
        get_data_plane_firestore_client()
        .collection('users')
        .document(uid)
        .get(field_paths=['subscription', GRANT_FIELD])
    )
    if not snapshot.exists:
        raise RuntimeError('allowance owner unavailable')
    current = generation(snapshot.to_dict(), now)
    if current == previous:
        return current, False
    allowance = funded_allowance(uid, lane='batch')
    if allowance.reason in TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS:
        raise RuntimeError('allowance unavailable')
    return current, allowance.managed
