"""Best-effort rendezvous, never a queue. All writes are shadow control/outcomes.

Four offers share the existing four-node fleet. No ordinary scheduler, content
ledger, owner ring, user quota, projection receipt or legacy lock is mutated.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import time

from google.api_core.exceptions import Aborted, AlreadyExists, FailedPrecondition
from google.cloud import firestore

from config.batch_pipeline_shadow import paid_recovery_limit, shadow_percent
from config.batch_pipeline import shadow_slot_cas_enabled
from config.policy import resolve_stage_policy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import is_allowance_policy_hold
from database.batch_pipeline_transaction_labels import shadow_operation
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
BUSY_HOLD_SCAN_LIMIT = 500
RECORD_PENDING_BUSY_SECONDS = 120.0
OFFER_SECONDS = 6
STAGING_SECONDS = 120
logger = logging.getLogger(__name__)


def identity(uid, content_id):
    return 'sh_' + hashlib.sha256(f'{uid}\0{content_id}'.encode()).hexdigest()


def _has_dispatchable(rows):
    for index, document in enumerate(rows):
        if index >= BUSY_HOLD_SCAN_LIMIT:
            return True  # A held prefix cannot certify an unmeasured tail idle.
        if not is_allowance_policy_hold(document.to_dict()):
            return True  # Missing/unknown authority remains ordinary-work priority.
    return False


def pool_busy(client, namespace, *, now=None):
    """Yield to runnable ordinary work, rather than durable parked obligations.

    A future retry, expired lease or old recording placeholder cannot occupy a
    GPU now. Use the scheduler's existing state/time indexes; no age-based
    exclusion of due retries. Local GPU/normal-flight checks remain mandatory.
    """
    now = time.time() if now is None else now
    jobs = client.collection(f'{namespace}_jobs')
    if list(jobs.where('state', '==', 'leased').where('lease_until', '>', now).limit(1).stream()):
        return True
    # Preserve nonempty unknown decisions: a subfield mask could turn one into
    # an absent decision and incorrectly revive a stale allowance hold.
    fields = ('compute_decision', 'last_policy_hold.reason')
    if _has_dispatchable(jobs.where('state', '==', 'ready').select(fields).limit(BUSY_HOLD_SCAN_LIMIT + 1).stream()):
        return True
    # Scheduler.recover promotes every due retry, including one whose attempt
    # counter reached the cap outside the serving retry-cap cohort. Only the
    # authoritative terminal state releases its ordinary-work priority.
    if _has_dispatchable(
        jobs.where('state', '==', 'retry')
        .where('available_at', '<=', now)
        .select(fields)
        .limit(BUSY_HOLD_SCAN_LIMIT + 1)
        .stream()
    ):
        return True
    return bool(
        list(
            jobs.where('state', '==', 'record_pending')
            .where('enqueued_at', '>', now - RECORD_PENDING_BUSY_SECONDS)
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
        # Existing scheduler indexes; bounded held-prefix scans. Runnable
        # ordinary GPU work wins, including a flight prefetched by another lane.
        return pool_busy(self.store.client, self.store.namespace, now=self.clock())

    def _run(self, operation, body):
        with shadow_operation(operation):
            return self.store.run(body)

    def _slot_ref(self, index):
        collection = self.store.client.collection(f'{self.store.namespace}_shadow_slots')
        return collection.document(str(index))

    def _read_slot(self, index):
        """One plain point read; this lane shares no transaction read set."""
        snapshot = self._slot_ref(index).get()
        return ((snapshot.to_dict() or {}), getattr(snapshot, 'update_time', None))

    def _write_slot(self, index, value, update_time):
        """One conditional write; the update-time fence makes it the arbiter.

        The write commits only if no other writer touched the slot document
        since this read, so two workers racing for the same ring index share
        no transaction, cannot abort one another, and exactly one wins.
        """
        try:
            if update_time is None:
                # A create cannot delete fields: on a fresh namespace there is
                # nothing to clear, so the sentinel must not ride along.
                self._slot_ref(index).create(
                    {key: value for key, value in value.items() if value is not firestore.DELETE_FIELD}
                )
            else:
                self._slot_ref(index).update(value, option=firestore.LastUpdateOption(update_time), retry=None)
            return True
        except (AlreadyExists, FailedPrecondition, Aborted):
            logger.info('event=batch_shadow_slot outcome=busy slot=%s', index)
            return False

    def _finish_one(self, segment, outcome, **fields):
        """Settle one job in its own transaction, keyed only by that job.

        The read set is the single job document — never the slot ring — so a
        settlement cannot abort or be aborted by concurrent rendezvous
        traffic. At-most-once settlement is the transaction's job.
        """
        row = self._run('finish', lambda tx: self._finish(tx, segment, outcome, **fields))
        if row:
            record(row)
        return row

    def _claim_slot(self, worker, *, closed, now):
        """Occupy one ring index with one conditional write, no ring transaction.

        Plain reads mirror the transactional ring's exact index choice; the
        update-time fence makes the write itself the arbiter, so concurrent
        claimers share no transaction read set and cannot abort one another.
        A loser's write fails its precondition and the worker simply skips
        this offer cycle — the next cycle re-reads and re-chooses.
        """
        choices = []
        own = None
        for index in range(MAX_OFFERS):
            slot, update_time = self._read_slot(index)
            if slot.get('worker') == worker:
                own = index
            choices.append((index, slot, update_time))
        if closed and own is None:
            return None
        index = own if own is not None else next((i for i, slot, _ in choices if slot.get('until', 0) <= now), None)
        if index is None:
            return None
        chosen_slot, update_time = choices[index][1:]
        if (
            not closed
            and own is not None
            and chosen_slot.get('state') in {'staging', 'ready'}
            and chosen_slot['until'] > now
        ):
            # A live staging/ready offer keeps its slot, exactly like the
            # transactional ring's early return.
            return None
        segment = chosen_slot.get('segment')
        value = {
            'worker': worker,
            'state': 'closed' if closed else 'idle',
            'until': now if closed else now + OFFER_SECONDS,
            # The transactional ring replaced the whole slot document; a
            # conditional update merges, so a displaced pointer is deleted
            # explicitly and can never leak onto a new owner.
            'segment': firestore.DELETE_FIELD,
        }
        if not self._write_slot(index, value, update_time):
            return None
        return index, segment, chosen_slot

    def _displaced_job_held(self, segment) -> bool:
        """True when a displaced slot pointer names work an owner still runs.

        ``take`` closes its slot the moment it hands the job over, and
        ``recovery_transport_failed`` already documents that an active
        backend request owns settlement for a recovering job, so a
        ``running``/``recovering`` job is never the ring's to drop: its
        owner, the bounded reap sweep or the recovery settlement path
        settles it. One plain job read decides; the fence analysis above
        makes the racy window unreachable in production.
        """
        if not segment:
            return False
        snapshot = self.store.client.collection(f'{self.store.namespace}_shadow_jobs').document(segment).get()
        return (snapshot.to_dict() or {}).get('state') in {'running', 'recovering'}

    def _settle_displaced_job(self, segment):
        """Drop a displaced offer-cycle job unless an owner still holds it.

        The slot is already safe under its fence when this runs; the drop is
        its own single-job transaction, so it cannot abort against or be
        aborted by ring traffic, and losing the race to a newer offer cycle
        costs nothing (the next cycle re-reads).
        """
        if self._displaced_job_held(segment):
            return
        self._finish_one(segment, 'dropped')

    def _consume_slot(self, worker, index, *, now):
        """Consume a ready offer with one generation-fenced write.

        The fence is the at-most-one-consumer arbiter: a slot the ring
        re-primed or another consumer took cannot be consumed twice. The
        displaced pointer is deleted explicitly — a conditional update
        merges, unlike the transactional ring's whole-row replace.
        """
        slot, update_time = self._read_slot(index)
        if slot.get('state') != 'ready' or slot.get('until', 0) <= now:
            return False
        return self._write_slot(
            index,
            {'worker': worker, 'state': 'closed', 'until': now, 'segment': firestore.DELETE_FIELD},
            update_time,
        )

    def _verify_ready(self, tx, segment):
        """Re-read one job inside its own transaction: state, identity, privacy.

        Nothing is written, so a refusal consumes nothing — the conditional
        slot write happens only after this transaction commits.
        """
        job = tx.get('shadow_jobs', segment)
        if job.get('state') != 'ready' or job.get('shadow') is not True:
            return None
        item = WorkItem(**job['item'])
        if not item.shadow or item.segment_id != segment:
            raise ValueError('shadow identity required')
        tx.check_privacy(
            item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
        )
        return job

    def _pin_running(self, tx, segment, item, now):
        job = tx.get('shadow_jobs', segment)
        if job.get('state') != 'ready' or job.get('shadow') is not True:
            return None  # A newer offer dropped it; the consumed slot expired.
        if not item.shadow or item.segment_id != segment:
            raise ValueError('shadow identity required')
        tx.check_privacy(
            item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
        )
        tx.put('shadow_jobs', segment, {**job, 'state': 'running', 'started_at': now})
        return item

    def _take_cas(self, worker, now):
        """Consume a ready offer without a ring-wide transaction read set.

        Plain slot reads choose this worker's offer; the generation-fenced
        slot write is the at-most-one-consumer arbiter; the single-job
        transaction then re-verifies the job at commit (identity, state,
        privacy) before pinning it running. A privacy refusal or lost race
        leaves the job for the bounded reap sweep — shadow metadata only,
        never audio custody.
        """
        own = None
        for index in range(MAX_OFFERS):
            slot, _ = self._read_slot(index)
            if slot.get('worker') == worker:
                own = (index, slot)
                break
        if own is None:
            return None
        index, slot = own
        segment = slot.get('segment')
        if slot.get('state') != 'ready' or slot.get('until', 0) <= now or not segment:
            return None
        # Verify identity and privacy before consuming anything, exactly like
        # the transactional ring: a refused consumer leaves the offer intact.
        job = self._run(
            'take',
            lambda tx: self._verify_ready(tx, segment),
        )
        if job is None:
            return None
        item = WorkItem(**job['item'])
        if not item.shadow or item.segment_id != segment:
            raise ValueError('shadow identity required')
        if not self._consume_slot(worker, index, now=now):
            return None
        return self._run('take', lambda tx: self._pin_running(tx, segment, item, now))

    def _admit_job_row(self, uid, class_name, segment, now, *, projected):
        row = {
            'shadow': True,
            'owner_key': hashlib.sha256(uid.encode()).hexdigest(),
            'class': class_name,
            'state': 'staging',
            'created_at': now,
            'expires_at': datetime.fromtimestamp(now, timezone.utc) + timedelta(hours=2),
        }
        if projected:
            row['projection_reserved_at'] = now
        return row

    def _bind_spend(self, tx, hour, expires_at):
        """Bind the hour counter after the slot fence, never before it.

        A double bind across concurrent reserve winners is a harmless
        over-admission counted against the same hourly budget — shadow spend
        is best effort, unlike the job create which refuses duplicates.
        """
        budget = tx.get('shadow_spend', hour)
        current = budget.get('units', 0)
        if type(current) is not int or current < 0:
            return None  # Uncertain cost authority; admission already committed.
        tx.put('shadow_spend', hour, {'units': current + 1, 'expires_at': expires_at})
        return current

    def _reserve_cas(self, uid, class_name, segment, busy, hour, now):
        """Admit a shadow unit without reading the slot ring in a transaction.

        The duplicate check and hourly spend read are plain single-document
        transactions; atomicity lives in conditional writes — the job create
        refuses a duplicate segment, and the generation-fenced slot write
        refuses a ring a concurrent offer has already re-primed since the
        read. Winning the slot fence commits admission order.
        """
        prior = self._run('reserve', lambda tx: dict(tx.get('shadow_jobs', segment)) or None)
        if prior:
            return None, None
        budget = self._run('reserve', lambda tx: dict(tx.get('shadow_spend', hour)) or None)
        used = (budget or {}).get('units', 0)
        if type(used) is not int or used < 0:
            return None, None  # Uncertain cost authority never admits work.
        index = None
        if not busy and used < 200:
            for candidate in range(MAX_OFFERS):
                slot, update_time = self._read_slot(candidate)
                if slot.get('state') == 'idle' and slot['until'] > now:
                    job_row = self._admit_job_row(uid, class_name, segment, now, projected=True)
                    try:
                        self.store.client.collection(f'{self.store.namespace}_shadow_jobs').document(segment).create(
                            job_row, retry=None
                        )
                    except AlreadyExists:
                        return None, None
                    staged = {**slot, 'state': 'staging', 'segment': segment, 'until': now + STAGING_SECONDS}
                    if not self._write_slot(candidate, staged, update_time):
                        logger.info('event=batch_shadow_slot outcome=busy slot=%s', candidate)
                        self._finish_one(segment, 'dropped')
                        return None, None
                    index = candidate
                    break
        job_row = self._admit_job_row(uid, class_name, segment, now, projected=index is not None)
        if index is None:
            try:
                self.store.client.collection(f'{self.store.namespace}_shadow_jobs').document(segment).create(
                    job_row, retry=None
                )
            except AlreadyExists:
                return None, None
            return None, self._finish_one(segment, 'dropped')
        bound = self._run(
            'reserve',
            lambda tx: self._bind_spend(tx, hour, datetime.fromtimestamp(now, timezone.utc) + timedelta(days=2)),
        )
        return (segment, str(index)), bound

    def _finish_cas(self, segment, outcome, **fields):
        """Settle one shadow job without touching the slot ring's read set."""
        return self._finish_one(segment, outcome, **fields)

    def slot_cas_enabled(self) -> bool:
        """The CAS rendezvous is on by default; the kill switch restores the ring.

        ``BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false`` restores the
        transactional ring that reads all four slot documents in one
        transaction in one step.
        """
        return shadow_slot_cas_enabled()

    def finish(self, segment, outcome, *, speech=0.0, vad='unknown', recognizers=None, projection_status=None):
        if outcome not in OUTCOMES:
            raise ValueError('closed shadow outcome required')
        if projection_status is not None and projection_status not in {
            'planned',
            'empty',
            'not_eligible',
            'budget_skipped',
            'busy',
            'error',
        }:
            raise ValueError('closed shadow projection status required')
        if self.slot_cas_enabled():
            row = self._finish_cas(
                segment,
                outcome,
                speech=speech,
                vad=vad,
                recognizers=recognizers,
                projection_status=projection_status,
            )
        else:
            row = self._run(
                'finish',
                lambda tx: self._finish(
                    tx,
                    segment,
                    outcome,
                    speech=speech,
                    vad=vad,
                    recognizers=recognizers,
                    projection_status=projection_status,
                ),
            )
        if row:
            record(row)

    def _finish(self, tx, segment, outcome, *, speech=0.0, vad='unknown', recognizers=None, projection_status=None):
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
            'created_at': job.get('created_at'),
            **({'projection_status': projection_status} if projection_status is not None else {}),
            'vad': vad,
            'paid_providers': job.get('paid', []),
            **({'recognizers': recognizers} if recognizers is not None else {}),
            **({'reason_code': 'shadow_paid_skipped'} if outcome == 'paid_skipped' else {}),
            'speech_seconds': float(speech),
            'speech_loss_seconds': float(speech) if outcome != 'recovered' else 0.0,
            'settled_at': self.clock(),
            'expires_at': datetime.fromtimestamp(self.clock(), timezone.utc) + timedelta(days=7),
        }
        tx.put('shadow_jobs', segment, row)
        return row

    def offer(self, worker, *, close=False):
        """Refresh one idle offer, or revoke it immediately for ordinary work."""
        now = self.clock()
        closed = close or not shadow_percent() or self.busy()
        if self.slot_cas_enabled():
            claimed = self._claim_slot(worker, closed=closed, now=now)
            if claimed is None:
                return
            _index, segment, _chosen = claimed
            if segment:
                # The displaced pointer was cleared under the same fence that
                # reset the slot; the drop is its own single-job transaction
                # and skips jobs an owner still runs (a take closes its slot
                # the moment it hands the job over — the consumer, not the
                # next offer cycle, owns that settlement).
                self._settle_displaced_job(segment)
            return

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

        row = self._run('offer', update)
        if row:
            record(row)

    def reserve(self, uid, content_id, class_name):
        now, segment = self.clock(), identity(uid, content_id)
        busy = not shadow_percent() or self.busy()
        hour = 'projection-' + str(int(now // 3600))
        if self.slot_cas_enabled():
            return self._reserve_cas(uid, class_name, segment, busy, hour, now)[0]

        def claim(tx):
            prior = tx.get('shadow_jobs', segment)
            slots = [tx.get('shadow_slots', str(i)) for i in range(MAX_OFFERS)]
            budget = tx.get('shadow_spend', hour)
            if prior:
                return None, None
            used = budget.get('units', 0)
            if type(used) is not int or used < 0:
                return None, None  # Uncertain cost authority never admits work.
            index = (
                None
                if busy or used >= 200
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
                    **({'projection_reserved_at': now} if index is not None else {}),
                    'expires_at': datetime.fromtimestamp(now, timezone.utc) + timedelta(hours=2),
                },
            )
            if index is None:
                return None, self._finish(tx, segment, 'dropped')
            tx.put(
                'shadow_spend',
                hour,
                {'units': used + 1, 'expires_at': datetime.fromtimestamp(now, timezone.utc) + timedelta(days=2)},
            )
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

        reservation, row = self._run('reserve', claim)
        if row:
            record(row)
        return reservation

    def ready(self, reservation, item, language, *, projection_context=None):
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
            tx.put(
                'shadow_jobs',
                segment,
                {
                    **job,
                    'state': 'ready',
                    'item': item.to_dict(),
                    'language': language,
                    'projection_context': projection_context or {},
                },
            )
            tx.put('shadow_slots', index, {**slot, 'state': 'ready', 'until': now + OFFER_SECONDS})
            return True

        return self._run('ready', publish)

    def projection_input(self, segment):
        """Use the intake reservation once, even across an hour rollover."""
        if not shadow_percent():
            return None
        now = self.clock()

        def reserve(tx):
            job = tx.get('shadow_jobs', segment)
            if (
                job.get('shadow') is not True
                or job.get('state') not in {'running', 'recovering'}
                or 'projection_attempted_at' in job
                or 'projection_reserved_at' not in job
            ):
                return None
            item = WorkItem(**job['item'])
            tx.check_privacy(
                item.owner_id, (item.conversation_id,) if item.conversation_id else (), item.privacy_generation
            )
            tx.put('shadow_jobs', segment, {**job, 'projection_attempted_at': now})
            return job

        return self._run('projection_input', reserve)

    def take(self, worker):
        if not shadow_percent() or self.busy():
            self.offer(worker, close=True)
            return None
        now = self.clock()
        if self.slot_cas_enabled():
            return self._take_cas(worker, now)

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

        return self._run('take', claim)

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
            seconds = self._run('paid', reserve)
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

        return self._run('handoff', prepare)

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

        return self._run('start_recovery', pin_shadow_recovery)

    def recovery_transport_failed(self, segment):
        def settle(tx):
            job = tx.get('shadow_jobs', segment)
            if job.get('state') in {'recovering', 'settled'}:
                return None  # An active backend request owns settlement.
            return self._finish(tx, segment, 'error' if shadow_percent() else 'dropped')

        row = self._run('recovery_transport_failed', settle)
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

            settled = self._run('reap', reap_one)
            if settled:
                record(settled)
