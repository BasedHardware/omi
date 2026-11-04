"""Replay real privacy readers/writers against isolated durable authority and time."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, ExitStack
from contextvars import copy_context
import os
import json
import threading
from unittest.mock import patch

from testing.replay_harness.report import StageResult, record_exception
from testing.replay_harness.stages.privacy_scenarios import scenario, validate_rows

OFFSETS = (0, 1, 59, 60, 61, 300)
LEVERS = (
    'deletion_marker_cache',
    'tombstone_negative_cache',
    'legal_hold_fence_cache',
    'bpp_generation_memo',
    'batch_privacy_memoize',
    'privacy_session_token',
    'subscription_cache',
    'request_read_dedupe',
)


class FaultRedis:
    """Lose writer invalidations while keeping warmed entries reachable by readers."""

    def __init__(self, redis, fault):
        self.redis, self.fault = redis, fault
        self.active = False
        self.calls = Counter()
        self.begins = 0
        self.condition = threading.Condition()
        self.release = threading.Event()

    def eval(self, script, *args):
        from database import fsr_read_cache as cache

        operation = {cache._BEGIN: 'begin', cache._END: 'end', cache._READ: 'read', cache._PUBLISH: 'publish'}[script]
        if self.active:
            self.calls[operation] += 1
            if (
                self.fault == 'redis_down'
                or (self.fault == 'drop_invalidation' and operation in ('begin', 'end'))
                or (self.fault == 'begin_loss' and operation == 'begin')
            ):
                raise ConnectionError('synthetic Redis fault')
        result = self.redis.eval(script, *args)
        if self.active and self.fault in ('concurrent', 'reader_during_writer') and operation == 'begin':
            with self.condition:
                self.begins += 1
                self.condition.notify_all()
            if not self.release.wait(15):
                raise TimeoutError('privacy writer overlap deadline')
        return result


def clock_and_cache(environment, fault, events):
    from database import fsr_read_cache as cache
    from database import privacy_check_metrics as metrics
    import fakeredis._basefakesocket as sockets
    import fakeredis._commands as commands
    import fakeredis.commands_mixins.server_mixin as server

    stack = ExitStack()
    redis = FaultRedis(environment.redis, fault)
    clock = environment.clock.module()
    cache._redis.cache_clear()
    stack.callback(cache._redis.cache_clear)
    stack.enter_context(patch.object(cache, '_redis', lambda: redis))
    for module in (cache, sockets, commands, server):
        stack.enter_context(patch.object(module, 'time', clock))
    stack.enter_context(patch.dict(os.environ, {'FIRESTORE_READ_LEVERS': json.dumps(dict.fromkeys(LEVERS, 100))}))
    # Observe real cache behavior; never replace a decision or writer.
    original_event, original_memo = cache._event, metrics.memo_result

    def event(family, result):
        events[(family, result)] += 1
        original_event(family, result)

    def memo(family, result):
        events[(family, 'memo_' + result)] += 1
        original_memo(family, result)

    stack.enter_context(patch.object(cache, '_event', event))
    stack.enter_context(patch.object(metrics, 'memo_result', memo))
    return stack, redis


def overlapping_writes(redis, write, read, *, writers, fenced):
    """Hold real BEGIN fences open while the reader probes, then join all writers."""
    observations = []
    with ThreadPoolExecutor(max_workers=writers) as pool:
        futures = [pool.submit(copy_context().run, write) for _ in range(writers)]
        try:
            if fenced:
                with redis.condition:
                    if not redis.condition.wait_for(lambda: redis.begins >= writers, timeout=15):
                        raise TimeoutError('privacy writers did not reach BEGIN')
            observations.append(read())
        finally:
            redis.release.set()
        # Propagate every writer failure; a failed write is never a passing sample.
        for future in futures:
            future.result(timeout=30)
    return observations


def summary():
    return {
        'transitions': 0,
        'probes': 0,
        'mismatches': 0,
        'early_mismatches': 0,
        'overlap_probes': 0,
        'max_observed_staleness_seconds': {},
        'families': {},
        'faults': {},
        'cache_events': {},
        'redis_fault_calls': {},
    }


class PrivacyCacheDriver:
    async def run(self, case, environment=None):
        from database.privacy_check_metrics import with_session_census

        rows = validate_rows(case.corpus)  # Reject unknown labels before infrastructure.
        details = summary()
        for row in rows:
            try:
                result = await with_session_census('listen')(self.transition)(row, details)
            except Exception as error:
                return StageResult(
                    'privacy_cache', 'stopped', details={**details, **row}, **record_exception(error, 'privacy_cache')
                )
            if result is not None:
                return result
        return StageResult('privacy_cache', 'pass', details=details)

    async def transition(self, row, details):
        from database import fsr_read_cache as cache
        from database.batch_privacy_attempt import batch_privacy_attempt
        from testing.replay_harness.env import replay_environment

        events = Counter()
        with replay_environment() as environment:
            patches, redis = clock_and_cache(environment, row['fault'], events)
            with patches, batch_privacy_attempt():
                uid, read, write, truth = scenario(row, environment)
                async with AsyncExitStack() as request_stack:
                    if row['fault'] == 'request_memo':
                        scope = cache.request_read_scope()
                        await scope.__anext__()
                        request_stack.push_async_callback(scope.aclose)
                    before = truth()
                    if read() != before or read() != before:
                        raise AssertionError('privacy warm differs from authority')
                    # Valid cacheable baselines must publish or hit a real memo.
                    eligible = (
                        (row['family'] in ('subscription', 'batch_privacy') and row['kind'] != 'finish')
                        or (row['family'] == 'tombstone' and row['kind'] == 'create')
                        or (row['family'] == 'deletion_marker' and row['kind'] in ('grace_intent', 'wipe_intent'))
                        or (row['family'] == 'legal_hold' and row['kind'] in ('place', 'release', 'acquire'))
                    )
                    cache_family = {
                        'deletion_marker': 'deletion_marker_cache',
                        'tombstone': 'tombstone_negative_cache',
                        'legal_hold': 'legal_hold_fence_cache',
                        'subscription': 'subscription_cache',
                    }.get(row['family'])
                    warm_event = (
                        ('batch', 'memo_hit') if row['family'] == 'batch_privacy' else (cache_family, 'publish')
                    )
                    if eligible and not events[warm_event]:
                        raise AssertionError('privacy cache baseline was not exercised')
                    redis.active = True
                    overlap = []
                    if row['fault'] in ('concurrent', 'reader_during_writer'):
                        overlap = overlapping_writes(
                            redis,
                            write,
                            read,
                            writers=2 if row['fault'] == 'concurrent' else 1,
                            fenced=row['family'] in ('deletion_marker', 'tombstone', 'legal_hold', 'subscription'),
                        )
                    else:
                        write()
                    after = truth()
                    # Retry-after-purge is intentionally idempotent. Every other
                    # generated arc must actually change its observed state.
                    if before == after and row['kind'] != 'retry_after_purge':
                        raise AssertionError('privacy transition was a no-op')
                    if any(value != before and value != after for value in overlap):
                        raise AssertionError('overlapping reader returned neither durable state')
                    details['overlap_probes'] += len(overlap)
                    if row['fault'] == 'request_memo':
                        holder = cache._request.get()
                        if any(key[0] == uid for key in holder.values):
                            raise AssertionError('writer retained request memo')
                    # Faults persist through all probes, including Redis-down.
                    # Only virtual cache clocks move; Firestore stays authoritative.
                    start = environment.clock.time()
                    details['transitions'] += 1
                    family = row['family']
                    details['families'][family] = details['families'].get(family, 0) + 1
                    details['faults'][row['fault']] = details['faults'].get(row['fault'], 0) + 1
                    details['max_observed_staleness_seconds'].setdefault(family, 0)
                    for offset in OFFSETS:
                        environment.clock.advance(start + offset - environment.clock.time())
                        observed, expected = read(), truth()
                        details['probes'] += 1
                        if expected != after:
                            raise AssertionError('authority changed outside replayed writer')
                        if observed != expected:
                            details['max_observed_staleness_seconds'][family] = max(
                                details['max_observed_staleness_seconds'][family], offset
                            )
                            if offset >= 60:
                                details['mismatches'] += 1
                                return StageResult(
                                    'privacy_cache',
                                    'stopped',
                                    reason='privacy_cache:staleness_bound_exceeded',
                                    details={**details, **row, 'offset_seconds': offset},
                                )
                            details['early_mismatches'] += 1
                    for operation, count in redis.calls.items():
                        label = f'{row["fault"]}:{operation}'
                        details['redis_fault_calls'][label] = details['redis_fault_calls'].get(label, 0) + count
                    for (cache_family, event), count in events.items():
                        label = f'{cache_family}:{event}'
                        details['cache_events'][label] = details['cache_events'].get(label, 0) + count
        return None
