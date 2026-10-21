"""Best-effort rendezvous, never a queue. All writes are shadow control/outcomes.

Four offers share the existing four-node fleet. No ordinary scheduler, content
ledger, owner ring, user quota, projection receipt or legacy lock is mutated.
"""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import time

from config.batch_pipeline_shadow import paid_recovery_limit, shadow_percent
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.shadow_metrics import OUTCOMES, PAID, PAID_AUDIO, record

MAX_OFFERS = 4
OFFER_SECONDS = 6
STAGING_SECONDS = 120


def identity(uid, content_id):
    return 'sh_' + hashlib.sha256(f'{uid}\0{content_id}'.encode()).hexdigest()


class ShadowStore:
    def __init__(self, store, *, clock=time.time, busy=None):
        self.store, self.clock = store, clock
        self.busy = busy or self._busy

    def _busy(self):
        # Single-field index, no new production index or scan. Any admitted
        # ordinary GPU work wins, including a flight prefetched by another lane.
        return bool(
            list(
                self.store.client.collection(f'{self.store.namespace}_jobs')
                .where('state', 'in', ['ready', 'leased', 'retry', 'record_pending'])
                .limit(1)
                .stream()
            )
        )

    def _finish(self, tx, segment, outcome, *, speech=0.0, vad='unknown'):
        job = tx.get('shadow_jobs', segment)
        if not job or job.get('state') == 'settled':
            return None
        row = {
            'shadow': True,
            'state': 'settled',
            'owner_key': job['owner_key'],
            'class': job['class'],
            'outcome': outcome,
            'vad': vad,
            **({'reason_code': 'shadow_paid_skipped'} if outcome == 'paid_skipped' else {}),
            'speech_seconds': float(speech),
            'speech_loss_seconds': float(speech) if outcome != 'recovered' else 0.0,
            'settled_at': self.clock(),
            'expires_at': datetime.fromtimestamp(self.clock(), timezone.utc) + timedelta(days=7),
        }
        tx.put('shadow_jobs', segment, row)
        return row

    def finish(self, segment, outcome, *, speech=0.0, vad='unknown'):
        if outcome not in OUTCOMES:
            raise ValueError('closed shadow outcome required')
        row = self.store.run(lambda tx: self._finish(tx, segment, outcome, speech=speech, vad=vad))
        if row:
            record(row)

    def offer(self, worker, *, close=False):
        """Refresh one idle offer, or revoke it immediately for ordinary work."""
        now = self.clock()
        closed = close or not shadow_percent() or self.busy()

        def update(tx):
            slots = [tx.get('shadow_slots', str(i)) for i in range(MAX_OFFERS)]
            own = next((i for i, slot in enumerate(slots) if slot.get('worker') == worker), None)
            if closed and own is None:
                return None
            index = (
                own
                if own is not None
                else next((i for i, slot in enumerate(slots) if slot.get('until', 0) <= now), None)
            )
            if index is None:
                return None
            slot = slots[index]
            segment = slot.get('segment')
            # Read every possibly stale job before buffering writes.
            job = tx.get('shadow_jobs', segment) if segment else {}
            if not closed and own is not None and slot.get('state') in {'staging', 'ready'} and slot['until'] > now:
                return None
            row = self._finish(tx, segment, 'dropped') if job and job.get('state') != 'settled' else None
            tx.put(
                'shadow_slots',
                str(index),
                {
                    'worker': worker,
                    'state': 'closed' if closed else 'idle',
                    'until': now if closed else now + OFFER_SECONDS,
                },
            )
            return row

        row = self.store.run(update)
        if row:
            record(row)

    def reserve(self, uid, content_id, class_name):
        now, segment = self.clock(), identity(uid, content_id)
        busy = not shadow_percent() or self.busy()

        def claim(tx):
            prior = tx.get('shadow_jobs', segment)
            slots = [tx.get('shadow_slots', str(i)) for i in range(MAX_OFFERS)]
            if prior:
                return None, None
            index = (
                None
                if busy
                else next(
                    (i for i, slot in enumerate(slots) if slot.get('state') == 'idle' and slot['until'] > now), None
                )
            )
            tx.put(
                'shadow_jobs',
                segment,
                {
                    'shadow': True,
                    'owner_key': hashlib.sha256(uid.encode()).hexdigest(),
                    'class': class_name,
                    'state': 'staging',
                    'created_at': now,
                    'expires_at': datetime.fromtimestamp(now, timezone.utc) + timedelta(hours=2),
                },
            )
            if index is None:
                return None, self._finish(tx, segment, 'dropped')
            tx.put(
                'shadow_slots',
                str(index),
                {
                    **slots[index],
                    'state': 'staging',
                    'segment': segment,
                    'until': now + STAGING_SECONDS,
                },
            )
            return (segment, str(index)), None

        reservation, row = self.store.run(claim)
        if row:
            record(row)
        return reservation

    def ready(self, reservation, item, language):
        segment, index = reservation
        now = self.clock()

        def publish(tx):
            slot, job = tx.get('shadow_slots', index), tx.get('shadow_jobs', segment)
            if slot.get('segment') != segment or slot.get('state') != 'staging' or slot.get('until', 0) <= now:
                return False
            if (
                not item.shadow
                or item.segment_id != segment
                or job.get('owner_key') != hashlib.sha256(item.owner_id.encode()).hexdigest()
            ):
                raise ValueError('shadow identity required')
            tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            tx.put('shadow_jobs', segment, {**job, 'state': 'ready', 'item': asdict(item), 'language': language})
            tx.put('shadow_slots', index, {**slot, 'state': 'ready', 'until': now + OFFER_SECONDS})
            return True

        return self.store.run(publish)

    def take(self, worker):
        if not shadow_percent() or self.busy():
            self.offer(worker, close=True)
            return None
        now = self.clock()

        def claim(tx):
            slots = [tx.get('shadow_slots', str(i)) for i in range(MAX_OFFERS)]
            index = next((i for i, slot in enumerate(slots) if slot.get('worker') == worker), None)
            if index is None:
                return None
            slot = slots[index]
            if slot.get('state') != 'ready' or slot['until'] <= now:
                return None
            segment = slot['segment']
            job = tx.get('shadow_jobs', segment)
            if job.get('state') != 'ready' or job.get('shadow') is not True:
                return None
            item = WorkItem(**job['item'])
            tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            tx.put('shadow_jobs', segment, {**job, 'state': 'running', 'started_at': now})
            tx.put('shadow_slots', str(index), {'worker': worker, 'state': 'closed', 'until': now})
            return item

        return self.store.run(claim)

    def paid(self, segment, provider):
        """Each provider is reserved once, across replicas/retries and hour rollover."""
        if provider not in {'modulate', 'deepgram'} or not shadow_percent():
            return False
        now, limit = self.clock(), paid_recovery_limit()
        hour = str(int(now // 3600))

        def reserve(tx):
            job, budget = tx.get('shadow_jobs', segment), tx.get('shadow_spend', hour)
            calls = job.get('paid', [])
            if job.get('state') != 'recovering' or provider in calls or budget.get('units', 0) >= limit:
                return None
            item = WorkItem(**job['item'])
            tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            tx.put('shadow_jobs', segment, {**job, 'paid': [*calls, provider]})
            tx.put(
                'shadow_spend',
                hour,
                {
                    'units': budget.get('units', 0) + 1,
                    'expires_at': datetime.fromtimestamp(now, timezone.utc) + timedelta(days=2),
                },
            )
            return job['item']['duration_seconds']

        seconds = self.store.run(reserve)
        if seconds is not None:
            PAID.labels(provider).inc()
            PAID_AUDIO.labels(provider).inc(seconds)
        return seconds is not None

    def start_recovery(self, segment):
        def start(tx):
            job = tx.get('shadow_jobs', segment)
            if not shadow_percent() or job.get('shadow') is not True or job.get('state') != 'running':
                return None
            item = WorkItem(**job['item'])
            tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            tx.put('shadow_jobs', segment, {**job, 'state': 'recovering'})
            return job

        return self.store.run(start)

    def reap(self):
        # Bounded, single-field query. Crashed processes cannot leave sensitive
        # rendezvous metadata or uncounted pending work indefinitely.
        cutoff = self.clock() - 3600
        rows = (
            self.store.client.collection(f'{self.store.namespace}_shadow_jobs')
            .where('created_at', '<=', cutoff)
            .limit(100)
            .stream()
        )
        for row in rows:
            self.finish(row.id, 'error')
