"""Hourly parked GPU page census on the held-dead-letter maintenance lane."""

import json
import logging
import math
import time
from collections import Counter

from google.cloud import firestore

from config.batch_pipeline import parked_job_sweeper_enabled
from database.firestore_read_origin import read_origin
from database.rpc_deadline import bind_firestore_client, rpc_deadline
from utils.batch_pipeline.errors import WORKER_VALIDATION_REASONS

CONTROL = 'parked_job_sweep'
PAGE_SIZE = 100  # Two indexed streams, at most 200 document reads together.
PASS_SECONDS = 10
HOUR_SECONDS = 3600
logger = logging.getLogger(__name__)


def mapping(value):
    return value if isinstance(value, dict) else {}


def reason(job):
    recovery = mapping(job.get('recovery'))
    if recovery.get('started_at') and mapping(recovery.get('failure')).get('reason') == 'empty_asr':
        return 'post_submit_empty_asr'
    diagnostic = mapping(job.get('quarantine_diagnostic'))
    if diagnostic.get('exception_class') == 'lease_expired':
        return 'lease_expired'
    worker = diagnostic.get('worker_reason')
    return worker if isinstance(worker, str) and worker in WORKER_VALIDATION_REASONS else 'unknown'


def summarize(rows, now):
    counts, owners = Counter(), set()
    oldest = None
    for job in rows:
        stamp = job.get('quarantined_at')
        age = None
        if type(stamp) in (float, int) and 0 < stamp <= now and math.isfinite(stamp):
            age = now - stamp
            oldest = age if oldest is None else max(age, oldest)
        if age is None:
            bucket = 'unknown'
        elif age < HOUR_SECONDS:
            bucket = 'under_1h'
        elif age < 24 * HOUR_SECONDS:
            bucket = 'under_24h'
        else:
            bucket = 'at_least_24h'
        counts[(reason(job), bucket)] += 1
        owner = job.get('owner_key')
        if isinstance(owner, str) and owner:
            owners.add(owner)
    return {
        'reason_age': [
            {'reason': why, 'age_bucket': bucket, 'units': count} for (why, bucket), count in sorted(counts.items())
        ],
        'oldest_age_seconds': oldest,
        'distinct_known_owners': len(owners),
    }


def parked_page(client, namespace, *, expired, after):
    jobs = client.collection(f'{namespace}_jobs')
    if expired:
        query = jobs.where('state', '==', 'dead').where('dead_letter_reason', '==', 'held_expired')
    else:
        query = jobs.where('state', '==', 'quarantined')
    query = query.order_by('__name__')
    if after:
        query = query.start_after({'__name__': jobs.document(after)})
    fields = [
        'owner_key',
        'quarantined_at',
        'quarantine_diagnostic',
        'recovery.started_at',
        'recovery.failure.reason',
        'stt_route.stt_route',
        'policy.stt_route',
    ]
    return query.select(fields).limit(PAGE_SIZE).stream(retry=None)


class ParkedSweep:
    def __init__(self, store):
        self.store = store
        self.last_attempt_hour = -1

    @read_origin('job:batch_pipeline_parked_sweep')
    def tick(self, now):
        hour = int(now // HOUR_SECONDS)
        if not parked_job_sweeper_enabled() or hour <= self.last_attempt_hour:
            return
        self.last_attempt_hour = hour
        scanned = {'quarantined': 0, 'held_expired': 0}
        report = None
        outcome = 'dependency_failure'
        try:
            remaining_in_slot = (hour + 1) * HOUR_SECONDS - time.time()
            with rpc_deadline(time.monotonic() + min(PASS_SECONDS, remaining_in_slot)):
                client = bind_firestore_client(self.store.client)
                control = client.collection(f'{self.store.namespace}_leases').document(CONTROL)

                @firestore.transactional
                def admit(tx):
                    state = control.get(transaction=tx).to_dict() or {}
                    if (
                        not parked_job_sweeper_enabled()
                        or state.get('disabled') is True
                        or state.get('hour', -1) >= hour
                    ):
                        return None
                    tx.set(control, {**state, 'hour': hour})
                    return mapping(state.get('cursors'))

                # One attempt each for the reservation and checkpoint. Reserve
                # their document operations before invoking each transaction.
                cursors = admit(client.transaction(max_attempts=1))
                if cursors is None:
                    outcome = 'not_admitted'
                    return
                next_cursors, coverage, rows = {}, {}, []
                for name in scanned:
                    if not parked_job_sweeper_enabled():
                        outcome = 'disabled'
                        return
                    after = cursors.get(name)
                    docs = parked_page(client, self.store.namespace, expired=name == 'held_expired', after=after)
                    last_id = None
                    for doc in docs:
                        scanned[name] += 1
                        last_id = doc.id
                        job = doc.to_dict() or {}
                        route = mapping(job.get('stt_route')).get('stt_route')
                        if route not in ('parakeet', 'provider'):
                            route = mapping(job.get('policy')).get('stt_route')
                        if route != 'provider':
                            rows.append(job)
                    wrapped = scanned[name] < PAGE_SIZE
                    next_cursors[name] = None if wrapped else last_id
                    coverage[name] = {'started_at_head': not after, 'reached_end': wrapped}

                sample = {
                    **summarize(rows, now),
                    'coverage': coverage,
                    'scanned': scanned,
                    'sampled_at': now,
                    'expires_at': (hour + 1) * HOUR_SECONDS,
                }

                @firestore.transactional
                def checkpoint(tx):
                    state = control.get(transaction=tx).to_dict() or {}
                    if not parked_job_sweeper_enabled() or state.get('disabled') is True or state.get('hour') != hour:
                        return False
                    tx.set(control, {**state, 'cursors': next_cursors, 'latest_page_sample': sample})
                    return True

                if checkpoint(client.transaction(max_attempts=1)):
                    report = sample
                    outcome = 'sampled'
                else:
                    outcome = 'checkpoint_refused'
        finally:
            logger.info(
                'event=batch_parked_gpu_page hour=%d outcome=%s scanned=%s sample=%s',
                hour,
                outcome,
                json.dumps(scanned, sort_keys=True),
                json.dumps(report, sort_keys=True),
            )
