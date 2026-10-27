"""Best-effort rendezvous, never a queue. All writes are shadow control/outcomes.

Four offers share the existing four-node fleet. No ordinary scheduler, content
ledger, owner ring, user quota, projection receipt or legacy lock is mutated.
"""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import time

from config.batch_pipeline_shadow import paid_recovery_limit, shadow_percent
from config.policy import resolve_stage_policy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.contracts import (
    WorkItem,
    RecoveryWork,
    ValidationFailureWork,
    attach_held_vad,
    held_vad_census,
    held_silence_allowed,
)
from utils.batch_pipeline.shadow_metrics import OUTCOMES, PAID, PAID_AUDIO, record

MAX_OFFERS = 4
OFFER_SECONDS = 6
STAGING_SECONDS = 120
logger = logging.getLogger(__name__)


def identity(uid, content_id):
    return 'sh_' + hashlib.sha256(f'{uid}\0{content_id}'.encode()).hexdigest()


def pool_busy(client, namespace):
    return bool(
        list(
            client.collection(f'{namespace}_jobs')
            .where('state', 'in', ['ready', 'leased', 'retry', 'record_pending'])
            .limit(1)
            .stream()
        )
    )


def stale_jobs(client, namespace, before):
    return list(client.collection(f'{namespace}_shadow_jobs').where('created_at', '<=', before).limit(100).stream())


class ShadowStore:
    def __init__(self, store, *, clock=time.time, busy=None):
        self.store, self.clock = store, clock
        self.busy = busy or self._busy

    def _busy(self):
        # Single-field index, no new production index or scan. Any admitted
        # ordinary GPU work wins, including a flight prefetched by another lane.
        return pool_busy(self.store.client, self.store.namespace)

    def _finish(self, tx, segment, outcome, *, speech=0.0, vad='unknown', recognizers=None):
        job = tx.get('shadow_jobs', segment)
        if job.get('shadow') is not True or job.get('state') == 'settled':
            return None
        context = {'duration_seconds': (job.get('item') or {}).get('duration_seconds'), **job}
        measured = speech if vad in {'strict', 'worker'} else None
        census = held_vad_census(context, measured)
        independent = (
            isinstance(recognizers, dict)
            and set(recognizers) == {'modulate', 'soniox'}
            and all(
                isinstance(r, dict)
                and r.get('provider') == p
                and r.get('outcome') == 'empty'
                and r.get('word_count') == 0
                for p, r in recognizers.items()
            )
        )
        # Positive-VAD historical exhaustion also uses "empty" and retains loss
        # accounting. A zero/unknown silence claim must respect earlier speech.
        if (
            outcome == 'empty'
            and measured in (None, 0)
            and not held_silence_allowed(context, measured, independent=independent)
        ):
            outcome = 'failed_held'
        speech, vad = census or 0.0, (
            vad if measured is not None and census == measured else 'strict' if census is not None else 'unknown'
        )
        row = {
            'shadow': True,
            'state': 'settled',
            'owner_key': job['owner_key'],
            'class': job['class'],
            'outcome': outcome,
            'vad': vad,
            **({'recognizers': recognizers, 'paid_providers': job.get('paid', [])} if recognizers is not None else {}),
            **({'reason_code': 'shadow_paid_skipped'} if outcome == 'paid_skipped' else {}),
            'speech_seconds': float(speech),
            'speech_loss_seconds': float(speech) if outcome != 'recovered' else 0.0,
            'settled_at': self.clock(),
            'expires_at': datetime.fromtimestamp(self.clock(), timezone.utc) + timedelta(days=7),
        }
        tx.put('shadow_jobs', segment, row)
        return row

    def finish(self, segment, outcome, *, speech=0.0, vad='unknown', recognizers=None):
        if outcome not in OUTCOMES:
            raise ValueError('closed shadow outcome required')
        row = self.store.run(
            lambda tx: self._finish(tx, segment, outcome, speech=speech, vad=vad, recognizers=recognizers)
        )
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
            if (
                slot.get('segment') != segment
                or slot.get('state') != 'staging'
                or slot.get('until', 0) <= now
                or job.get('shadow') is not True
                or job.get('state') != 'staging'
            ):
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
            if not item.shadow or item.segment_id != segment:
                raise ValueError('shadow identity required')
            tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            tx.put('shadow_jobs', segment, {**job, 'state': 'running', 'started_at': now})
            tx.put('shadow_slots', str(index), {'worker': worker, 'state': 'closed', 'until': now})
            return item

        return self.store.run(claim)

    def paid(self, segment, provider):
        """Each provider is reserved once, across replicas/retries and hour rollover."""
        if provider not in {'modulate', 'deepgram', 'soniox'} or not shadow_percent():
            return False
        now, limit = self.clock(), paid_recovery_limit()
        hour = str(int(now // 3600))

        def reserve(tx):
            job, budget = tx.get('shadow_jobs', segment), tx.get('shadow_spend', hour)
            calls = job.get('paid', [])
            if (
                job.get('shadow') is not True
                or job.get('state') != 'recovering'
                or provider in calls
                or budget.get('units', 0) >= limit
            ):
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

        try:
            seconds = self.store.run(reserve)
        except BatchPrivacyBlocked:
            raise
        except Exception as error:
            # A contention timeout or lost commit reply is never permission to
            # call a provider. A possibly committed reservation stays consumed.
            logger.info('event=batch_shadow_paid outcome=unavailable exception_type=%s', type(error).__name__)
            return False
        if seconds is not None:
            PAID.labels(provider).inc()
            PAID_AUDIO.labels(provider).inc(seconds)
        return seconds is not None

    def handoff(self, segment, evidence):
        if not isinstance(evidence, (RecoveryWork, ValidationFailureWork)) or evidence.segment_id != segment:
            raise ValueError('typed worker recovery evidence required')

        def prepare(tx):
            job = tx.get('shadow_jobs', segment)
            if job.get('shadow') is not True or job.get('state') != 'running':
                return False
            bound = dict(job['item'])
            bound['measured_held_vad_speech_seconds'] = held_vad_census({**bound, **job})
            attach_held_vad(bound, evidence.measured_held_vad_speech_seconds, evidence.worker_vad_receipt)
            evidence_fields = {
                key: bound[key] for key in ('measured_held_vad_speech_seconds', 'worker_vad_receipt') if key in bound
            }
            if isinstance(evidence, RecoveryWork) and evidence.padded_retry:
                evidence_fields['worker_empty_evidence'] = {'padded_retry': evidence.padded_retry, 'version': 1}
            if isinstance(evidence, ValidationFailureWork):
                evidence_fields['worker_failure'] = {'stage': evidence.stage, 'reason': evidence.reason}
            tx.put('shadow_jobs', segment, {**job, **evidence_fields, 'state': 'recovery_ready'})
            return True

        return self.store.run(prepare)

    def start_recovery(self, segment):
        def pin_shadow_recovery(tx):
            job = tx.get('shadow_jobs', segment)
            if not shadow_percent() or job.get('shadow') is not True or job.get('state') != 'recovery_ready':
                return None
            item = WorkItem(**job['item'])
            tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            policy = resolve_stage_policy(item.owner_id, 'recovery')
            updated = {
                **job,
                'state': 'recovering',
                'recovery_started_at': self.clock(),
                'recovery_policy': policy.to_dict(),
                'expires_at': datetime.fromtimestamp(self.clock(), timezone.utc) + timedelta(hours=2),
            }
            tx.put('shadow_jobs', segment, updated)
            return updated

        return self.store.run(pin_shadow_recovery)

    def recovery_transport_failed(self, segment):
        def settle(tx):
            job = tx.get('shadow_jobs', segment)
            if job.get('state') in {'recovering', 'settled'}:
                return None  # An active backend request owns settlement.
            return self._finish(tx, segment, 'error' if shadow_percent() else 'dropped')

        row = self.store.run(settle)
        if row:
            record(row)

    def reap(self):
        # Bounded, single-field query. Crashed processes cannot leave sensitive
        # rendezvous metadata or uncounted pending work indefinitely.
        cutoff = self.clock() - 3600
        rows = stale_jobs(self.store.client, self.store.namespace, cutoff)
        for row in rows:

            def reap_one(tx):
                job = tx.get('shadow_jobs', row.id)
                # A slow active provider owns its separate bounded recovery
                # window. Never erase its intent based on upload creation time.
                if job.get('state') == 'recovering' and job.get('recovery_started_at', 0) > cutoff:
                    return None
                return self._finish(tx, row.id, 'error')

            settled = self.store.run(reap_one)
            if settled:
                record(settled)
