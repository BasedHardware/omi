"""Replay real privacy readers/writers against isolated durable authority and time."""

from collections import Counter
from contextlib import AsyncExitStack, ExitStack
import os
import json
import threading
from unittest.mock import patch

from testing.replay_harness.report import StageResult, record_exception
from testing.replay_harness.privacy_report import OFFSETS, summary, observe_probe, observe_expiry, observe_transition
from testing.replay_harness.privacy_faults import FSR_FAMILIES, not_applicable_reason, fault_applied
from testing.replay_harness.stages.privacy_overlap import overlapping_writes
from testing.replay_harness.stages.privacy_scenarios import scenario, validate_rows

LEVERS = (
    'deletion_marker_cache',
    'tombstone_negative_cache',
    'legal_hold_fence_cache',
    'bpp_generation_memo',
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
        self.total_calls = Counter()
        self.injected = Counter()
        self.successful = Counter()
        self.begins = 0
        self.condition = threading.Condition()
        self.release = threading.Event()

    def eval(self, script, *args):
        from database import fsr_read_cache as cache

        operation = {cache._BEGIN: 'begin', cache._END: 'end', cache._READ: 'read', cache._PUBLISH: 'publish'}[script]
        self.total_calls[operation] += 1
        if self.active:
            self.calls[operation] += 1
            if (
                self.fault == 'redis_down'
                or (self.fault == 'drop_invalidation' and operation in ('begin', 'end'))
                or (self.fault == 'begin_loss' and operation == 'begin')
            ):
                self.injected[operation] += 1
                raise ConnectionError('synthetic Redis fault')
        result = self.redis.eval(script, *args)
        if self.active:
            self.successful[operation] += 1
        if self.active and self.fault in ('concurrent', 'reader_during_writer') and operation == 'begin':
            with self.condition:
                self.begins += 1
                self.condition.notify_all()
            if not self.release.wait(15):
                raise TimeoutError('privacy writer overlap deadline')
        return result


def clock_and_cache(environment, fault, events, *, ttl_override_s=None):
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
    if ttl_override_s is not None:
        from database import users

        families = {'deletion_marker_cache', 'tombstone_negative_cache', 'legal_hold_fence_cache', 'subscription_cache'}
        env_names = {cache._CACHE_TTLS[family][0] for family in families}
        original_ttl, original_read = cache.ttl, cache.cached_read

        def ttl(name, default):
            return ttl_override_s if name in env_names else original_ttl(name, default)

        def cached_read(family, *args, **kwargs):
            if family in families:
                kwargs['seconds'] = ttl_override_s
            return original_read(family, *args, **kwargs)

        stack.enter_context(patch.object(cache, 'ttl', ttl))
        stack.enter_context(patch.object(cache, 'cached_read', cached_read))
        # users imports these helpers by value. Patch that actual call site as
        # well, irrespective of module import order in a long replay process.
        stack.enter_context(patch.object(users, 'ttl', ttl))
        stack.enter_context(patch.object(users, 'cached_read', cached_read))
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


class PrivacyCacheDriver:
    def __init__(self, *, ttl_override_s=None, runtime_env=None):
        if ttl_override_s is not None and (type(ttl_override_s) is not int or not 1 <= ttl_override_s <= 86400):
            raise ValueError('test TTL override must be an integer in [1, 86400]')
        self.ttl_override_s = ttl_override_s
        self.runtime_env = runtime_env

    async def run(self, case, environment=None):
        from database.privacy_check_metrics import with_session_census

        rows = validate_rows(case.corpus)  # Reject unknown labels before infrastructure.
        bound = case.manifest.stages['privacy_cache'].get('bound_s', 60.0)
        minimum = case.manifest.stages['privacy_cache'].get('min_verified_transitions', 1000)
        details = summary(bound, self.ttl_override_s, minimum)
        for index, row in enumerate(rows):
            details['attempted_transitions'] += 1
            record = {
                **row,
                'index': index,
                'fault_applicable': not not_applicable_reason(row['family'], row['fault']),
                'fault_applied': False,
                'completed': False,
                'probe_errors': 0,
                'evidence': {},
            }
            details['transition_results'].append(record)
            try:
                await with_session_census('listen')(self.transition)(row, details, record)
                details['completed_transitions'] += 1
                record['completed'] = True
            except Exception as error:
                details['errors'].append({**row, **record_exception(error, 'privacy_cache')})
            observe_transition(details, record)
        details['qualification_met'] = (
            details['verified_transitions'] >= 1000
            and not details['mismatches']
            and not details['errors']
            and not details['unverified_transitions']
        )
        reason = None
        if details['mismatches']:
            reason = 'privacy_cache:staleness_bound_exceeded'
        elif details['errors']:
            reason = 'privacy_cache:transition_errors'
        elif details['unverified_transitions']:
            reason = 'privacy_cache:unverified_fault'
        elif details['verified_transitions'] < minimum:
            reason = 'privacy_cache:insufficient_verified_transitions'
        return StageResult('privacy_cache', 'stopped' if reason else 'pass', reason=reason, details=details)

    async def transition(self, row, details, record):
        from database import fsr_read_cache as cache
        from database.batch_privacy_attempt import batch_privacy_attempt
        from testing.replay_harness.env import replay_environment

        events = Counter()
        with replay_environment(self.runtime_env) as environment:
            patches, redis = clock_and_cache(environment, row['fault'], events, ttl_override_s=self.ttl_override_s)
            with patches, batch_privacy_attempt():
                uid, read, write, truth = scenario(row, environment)
                async with AsyncExitStack() as request_stack:
                    if row['fault'] == 'request_memo':
                        scope = cache.request_read_scope()
                        await scope.__anext__()
                        request_stack.push_async_callback(scope.aclose)
                    marker_request = row['fault'] == 'request_memo' and row['family'] == 'deletion_marker'
                    before = truth()
                    warm_reads = redis.total_calls['read']
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
                    expiries = [
                        environment.redis.pexpiretime(key)
                        for key in environment.redis.scan_iter(match='fsr:s4:v2:*:data:*')
                    ]
                    evidence = record['evidence']
                    if marker_request:
                        reader_holder = cache._request.get()
                        evidence.update(
                            request_memo_absent=not any(key[0] == uid for key in reader_holder.values),
                            request_redis_warm_reads=redis.total_calls['read'] - warm_reads,
                            request_redis_probe_reads=[],
                            request_deletion_observed=True,
                            reader_scope_preserved=True,
                        )
                    elif row['fault'] == 'request_memo' and record['fault_applicable']:
                        holder = cache._request.get()
                        evidence['request_memo_warmed'] = any(key[0] == uid for key in holder.values)
                        evidence['request_memo_hit'] = bool(events[('request_read_dedupe', 'hit')])
                    redis.active = True
                    overlap = []
                    if row['fault'] in ('concurrent', 'reader_during_writer'):
                        overlap, overlap_evidence = overlapping_writes(
                            redis,
                            environment.store.client,
                            write,
                            read,
                            writers=2 if row['fault'] == 'concurrent' else 1,
                            fenced=row['family'] in FSR_FAMILIES,
                        )
                        evidence.update(overlap_evidence)
                    elif marker_request:
                        # Another request cannot clear the original reader's memo.
                        # Keep the reader open while the real writer fences Redis.
                        writer_scope = cache.request_read_scope()
                        await anext(writer_scope)
                        try:
                            evidence['independent_writer_scope'] = cache._request.get() is not reader_holder
                            write()
                        finally:
                            await writer_scope.aclose()
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
                    if row['fault'] == 'request_memo' and record['fault_applicable'] and not marker_request:
                        holder = cache._request.get()
                        if any(key[0] == uid for key in holder.values):
                            raise AssertionError('writer retained request memo')
                        evidence['request_memo_cleared'] = True
                    # Faults persist through all probes, including Redis-down.
                    # Only virtual cache clocks move; Firestore stays authoritative.
                    start = environment.clock.time()
                    details['transitions'] += 1
                    family = row['family']
                    details['families'][family] = details['families'].get(family, 0) + 1
                    details['faults'][row['fault']] = details['faults'].get(row['fault'], 0) + 1
                    for expiry_ms in expiries:
                        if expiry_ms >= 0:
                            observe_expiry(details, family, start, expiry_ms)
                    for offset in sorted(set((*OFFSETS, details['bound_s']))):
                        environment.clock.advance(start + offset - environment.clock.time())
                        try:
                            probe_reads = redis.total_calls['read']
                            observed = read()
                            if marker_request:
                                evidence['request_redis_probe_reads'].append(redis.total_calls['read'] - probe_reads)
                                evidence['request_deletion_observed'] &= observed == after
                                evidence['reader_scope_preserved'] &= (
                                    cache._request.get() is reader_holder and not reader_holder.closed
                                )
                                evidence['request_memo_absent'] &= not any(
                                    key[0] == uid for key in reader_holder.values
                                )
                            expected = truth()
                            if expected != after:
                                raise AssertionError('authority changed outside replayed writer')
                            observe_probe(details, row, offset, observed, expected, before)
                        except Exception as error:
                            cell = details['by_family_fault_offset'][family][row['fault']][str(float(offset))]
                            cell['probes'] += 1
                            cell['errors'] += 1
                            record['probe_errors'] += 1
                            details['probes'] += 1
                            details['errors'].append(
                                {**row, 'offset_s': offset, **record_exception(error, 'privacy_cache')}
                            )
                    evidence['injected'] = dict(redis.injected)
                    evidence['successful'] = dict(redis.successful)
                    record['fault_applied'] = record['fault_applicable'] and fault_applied(
                        row['fault'], evidence, family=row['family']
                    )
                    for operation, count in redis.calls.items():
                        label = f'{row["fault"]}:{operation}'
                        details['redis_fault_calls'][label] = details['redis_fault_calls'].get(label, 0) + count
                    for (cache_family, event), count in events.items():
                        label = f'{cache_family}:{event}'
                        details['cache_events'][label] = details['cache_events'].get(label, 0) + count
        return None
