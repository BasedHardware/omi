"""Measure the unreadable first summary through the real enrichment push route."""

import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from routers import enrichment
from testing.fakes.cloud_tasks_queue import CloudTasksQueue, QueueConfig
from testing.finalization_replay.metrics import suspend_meter
from utils import cloud_tasks
from utils.enrichment import age_gate, outbox

UNREADABLE = 'unreadable-ciphertext-dead-letters'


def check_ciphertext(before, after):
    if (
        not isinstance(before.get('transcript_segments'), str)
        or not before.get('transcript_segments')
        or before['transcript_segments'] != after.get('transcript_segments')
        or before.get('transcript_segments_compressed') != after.get('transcript_segments_compressed')
        or after.get('discarded')
        or after.get('deleted')
    ):
        raise RuntimeError('unreadable ciphertext custody changed')


def retry_to_park(state, worker_backend):
    with suspend_meter():
        original = state.conversation.get().to_dict()
    created = original['created_at'].timestamp()
    epoch = max(created, original['finished_at'].timestamp()) + 1
    clock = SimpleNamespace(time=lambda: epoch, monotonic=time.monotonic)
    queue_name = 'enrichment'
    handler_url = 'https://replay.invalid/v2/enrichment/run'
    queues = yaml.safe_load((Path(worker_backend) / 'deploy/ops/prod.yaml').read_text())['cloud_tasks']
    config = queues[queue_name]
    max_attempts = config['max_attempts']
    policies = Counter()
    payloads = {}

    def deliver(task, elapsed):
        clock.time = lambda: epoch + elapsed

        async def body():
            return payloads[task.name]

        request = SimpleNamespace(json=body, headers={'X-CloudTasks-QueueName': queue_name})
        response = asyncio.run(enrichment.run_enrichment_task(request, _retry_count=task.attempts - 1))
        outcome = json.loads(response.body)
        reason = outcome.get('reason')
        if (response.status_code, reason) not in {(409, 'callback_pending'), (200, age_gate.REASON)}:
            raise RuntimeError(f'unexpected unreadable replay result: {response.status_code} {reason}')
        policies[reason] += 1
        return response.status_code, 0

    queue = CloudTasksQueue(
        deliver,
        QueueConfig(
            # The shared fake takes a positive cap. The replay's age gate bounds
            # the simulation for a deployed queue with unlimited attempts.
            max_attempts=sys.maxsize if max_attempts == -1 else max_attempts,
            min_backoff_s=float(config['min_backoff'].removesuffix('s')),
            max_backoff_s=float(config['max_backoff'].removesuffix('s')),
        ),
        tick_s=1.0,
    )

    def enqueue(queue_id, handler, name, payload, *, audience, invoker_sa, schedule_at):
        if queue_id != queue_name or handler != handler_url or audience != handler_url:
            raise RuntimeError('unreadable replay wake escaped its queue binding')
        payloads[name] = payload
        return queue.create_task(name, payload['kind'], delay_s=max(0.0, schedule_at - clock.time()))

    with (
        patch.dict(
            os.environ,
            {
                'ENRICHMENT_ROUTE': 'enrichment_queue',
                'ENRICHMENT_TASKS_QUEUE': queue_name,
                'ENRICHMENT_FRESH_TASKS_QUEUE': '',
                'ENRICHMENT_TASKS_HANDLER_URL': handler_url,
                'ENRICHMENT_TASKS_OIDC_AUDIENCE': handler_url,
                'ENRICHMENT_TASKS_INVOKER_SA': 'replay@example.invalid',
            },
        ),
        patch.object(cloud_tasks, 'enqueue_named_task', enqueue),
        patch.object(enrichment, 'time', clock),
        patch.object(age_gate, 'time', clock),
    ):
        # Match the Go replay's admission boundary. Meter dispatches, including
        # the terminal park, after the synthetic obligation has been admitted.
        with suspend_meter():
            outbox.mark(state.uid, state.cid, original.get('language') or 'en', now=epoch, snapshot_summary=True)
        max_age = age_gate.max_age_seconds()
        if max_age <= 0:
            raise RuntimeError('unreadable replay requires a configured age cap')
        stats = queue.run_until(max_age + queue.config.max_backoff_s + 2)

    with suspend_meter():
        check_ciphertext(original, state.conversation.get().to_dict())
        parked = state.client.collection(outbox.COLLECTION).document(outbox.key(state.uid, state.cid)).get().to_dict()
    if (
        stats.created != 1
        or stats.completed != 1
        or stats.dropped
        or queue.pending()
        or policies['callback_pending'] == 0
        or policies[age_gate.REASON] != 1
        or not parked
        or not parked.get('dormant')
        or not parked.get('age_gate_parked')
        or parked.get('deferred_reason') != age_gate.REASON
        or parked.get('claim_attempts') != policies['callback_pending']
        or parked.get('owner')
        or parked.get('lease_until') != 0
    ):
        raise RuntimeError('unreadable replay did not finish with a durable custody park')
    task = next(iter(queue.tasks.values()))
    return {
        'outcome': 'parked',
        'reason': age_gate.REASON,
        'ciphertext_kept': True,
        'attempts': task.attempts,
        'callback_pending_attempts': policies['callback_pending'],
        'elapsed_seconds': task.done_at,
        'max_age_seconds': max_age,
        'queue_max_attempts': max_attempts,
    }
