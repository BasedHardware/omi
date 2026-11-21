"""Observe an ordered metadata prefix after a real lease commits."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from threading import BoundedSemaphore
from time import monotonic
from typing import TypeGuard

from prometheus_client import Counter, Histogram

from config import batch_pipeline_packing as config
from config.plan_catalog_generated import PAID_PLAN_IDS
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from database.batch_pipeline_coalescing_identity import compatibility_key, digest
from database.firestore_read_origin import read_origin
from utils.batch_pipeline.audio import RATE
from utils.executors import db_executor, submit_with_context
from utils.marketplace_reviewers import is_marketplace_reviewer
from utils.sync.capture_clock import is_early_capture_time

ENTITLEMENTS = ('paid', 'trial', 'exempt', 'free', 'unknown')
AGES = ('under_1h', '1h_to_6h', '6h_to_1d', 'over_1d', 'unknown')
_READ_SLOT = BoundedSemaphore(1)


def _number(value) -> TypeGuard[int | float]:
    return type(value) in (int, float) and math.isfinite(value)


def entitlement_class(uid, subscription, release, now):
    if uid == 'omi-release-probe' or is_marketplace_reviewer(uid):
        return 'exempt'
    if release == 'trial':
        return 'trial'
    if release == 'conversion':
        return 'paid'
    if not isinstance(subscription, dict):
        return 'unknown'
    plan, status = subscription.get('plan'), subscription.get('status')
    if plan in ('basic', 'free') and status == 'active':
        return 'free'
    # The legacy Stripe projection folds trialing into active. Its active paid
    # plan alone cannot distinguish an active trial from a paid period.
    end = subscription.get('current_period_end')
    if type(plan) is str and plan in PAID_PLAN_IDS and _number(end) and end >= now:
        if status == 'trialing':
            return 'trial'
        if status == 'inactive' or (status == 'active' and not subscription.get('stripe_subscription_id')):
            return 'paid'
    return 'unknown'


def _age_bucket(now, end):
    if not _number(end) or end > now:
        return 'unknown'
    age = now - end
    if age < 3600:
        return 'under_1h'
    if age < 21600:
        return '1h_to_6h'
    return '6h_to_1d' if age < 86400 else 'over_1d'


def intake_observations(arguments, bounds, *, subscription, protection, policy, priority, release, now, packable):
    """Freeze only bounded telemetry metadata on the original admission write."""
    context = arguments.get('intake_context') or {}
    entitlement = entitlement_class(arguments['uid'], subscription, release, now)
    device = arguments['client_device_id']
    session = context.get('recording_session_id')
    conversation = arguments['conversation_id']
    trusted = bool(device and bounds and all(bound is not None for bound, _ in bounds.values()))
    newest = max(bound[1] for bound, _ in bounds.values() if bound is not None) if trusted else None
    age = _age_bucket(now, newest)
    scope = (
        digest([arguments['uid'], conversation, session, device])
        if trusted and conversation and type(session) is str and 0 < len(session) <= 128
        else None
    )
    period = _period(subscription, entitlement, now)
    can_pack = packable and scope is not None and period is not None and entitlement != 'unknown'
    observations, keys = {}, {}
    for segment, (bound, proof) in bounds.items():
        observation = {'version': 1, 'entitlement': entitlement, 'age': age}
        observations[segment] = observation
        if bound is None:
            continue
        start, end, seconds = bound
        observation.update(start=start, end=end, seconds=seconds)
        if scope is not None:
            observation['scope'] = scope
        language, evidence = proof.get('stt_language'), proof.get('stt_language_evidence')
        if can_pack and language and language != 'multi' and evidence:
            key = language, evidence
            if key not in keys:
                base = compatibility_key(
                    arguments,
                    privacy_level=protection.level,
                    generation=protection.generation,
                    language=language,
                    policy_id=policy.policy_id,
                    priority=priority,
                )
                keys[key] = digest([base, entitlement, period, release, evidence])
            observation['key'] = keys[key]
    return observations


def source_bounds(unit, *, trustworthy):
    # The canonical WAL decoder's last sample is original audio. Internal
    # inserted gap silence is accounted for separately by source_frames.
    if (
        not trustworthy
        or getattr(unit, 'stored_capture_at', None) is not None
        or getattr(unit, 'recovery_id', None)
        or getattr(unit, 'source_reuse_key', None)
        or not _number(unit.capture_at)
        or is_early_capture_time(unit.capture_at)
    ):
        return None
    frames = getattr(unit, 'source_frames', None)
    if type(frames) is int and 0 < frames <= round(unit.duration_seconds * RATE):
        return unit.capture_at, unit.capture_at + unit.duration_seconds, frames / RATE
    return None


class IntakePacking:
    """Collect evidence alongside the intake's existing decode and admission."""

    def __init__(self, arguments, *, canonical_decode):
        self.arguments = arguments
        context = arguments['intake_context'] or {}
        # Receipt-clock uploads retain the existing job document shape.
        self.enabled = bool(config.sample_rate()) and context.get('capture_received_at') is None
        self.trustworthy = bool(
            arguments['client_device_id']
            and canonical_decode
            and arguments['recording_age_seconds'] is not None
            and not context.get('capture_clock_policy')
        )
        self.bounds = {}

    def note_alias(self, segment):
        if self.enabled:
            self.bounds[segment] = (None, {})

    def note(self, segment, unit, proof):
        if self.enabled:
            self.bounds[segment] = (source_bounds(unit, trustworthy=self.trustworthy), proof)

    def observations(
        self, *, subscription, protection, policy, priority, release, now, excluded, input_language, language
    ):
        if not self.enabled:
            return None
        context = self.arguments['intake_context'] or {}
        try:
            return intake_observations(
                self.arguments,
                self.bounds,
                subscription=subscription,
                protection=protection,
                policy=policy,
                priority=priority,
                release=release,
                now=now,
                packable=not (
                    any(excluded)
                    or self.arguments['byok_enabled']
                    or input_language != language
                    or language not in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3']
                    or context.get('capture_evidence_claims')
                    or not self.arguments['client_platform']
                ),
            )
        except Exception:
            return None  # A diagnostic stamp cannot refuse upload custody.


def _period(subscription, entitlement, now):
    if entitlement in ('free', 'exempt'):
        return datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m')
    subscription = subscription if isinstance(subscription, dict) else {}
    bounds = [subscription.get('current_period_start'), subscription.get('current_period_end')]
    if all(_number(value) for value in bounds):
        return bounds
    return None


def job_observation(row):
    raw = row.get('packing_observation')
    return raw if isinstance(raw, dict) and raw.get('version') == 1 else {}


def _cohort(observation):
    entitlement, age = observation.get('entitlement'), observation.get('age')
    return entitlement if entitlement in ENTITLEMENTS else 'unknown', age if age in AGES else 'unknown'


def sampled(token, rate):
    return rate > 0 and int(token[:8], 16) < rate * 2**32


@dataclass(frozen=True)
class Pack:
    members: int
    seconds: float
    stop: str


def _due(row, when, later_ready):
    return (
        (row.get('state') == 'ready' or row.get('segment_id') in later_ready)
        and _number(row.get('available_at'))
        and row['available_at'] <= when
        and not row.get('last_policy_hold')
    )


def _gap(previous, following):
    if not previous.get('scope') or following.get('scope') != previous['scope']:
        return None
    if not _number(previous.get('end')) or not _number(following.get('start')):
        return None
    return round((following['start'] - previous['end']) * RATE) / RATE


def build_pack(anchor, following, *, when, max_gap, max_seconds, predecessor, capped, later_ready=frozenset()):
    duration = anchor.get('duration_seconds')
    if not _number(duration):
        return Pack(0, 0.0, 'unknown_duration')
    first = job_observation(anchor)
    seconds = first.get('seconds')
    if not _number(seconds) or seconds <= 0:
        return Pack(0, 0.0, 'unknown_source')
    if duration > max_seconds:
        return Pack(0, 0.0, 'size')
    if predecessor:
        return Pack(1, seconds, 'predecessor')
    if not first.get('key'):
        return Pack(1, seconds, 'incompatible_key')
    previous, members = first, 1
    for row in following:
        candidate = job_observation(row)
        if not _due(row, when, later_ready):
            stop = 'not_ready'
        elif candidate.get('key') != first['key']:
            stop = 'incompatible_key'
        elif (gap := _gap(previous, candidate)) is None or not 0 <= gap <= max_gap:
            stop = 'gap'
        elif not _number(candidate_duration := row.get('duration_seconds')):
            stop = 'unknown_duration'
        elif duration + candidate_duration > max_seconds:
            stop = 'size'
        elif members == config.MAX_MEMBERS:
            stop = 'count'
        elif not _number(candidate.get('seconds')) or candidate['seconds'] <= 0:
            stop = 'unknown_source'
        else:
            previous = candidate
            members += 1
            seconds += candidate['seconds']
            duration += candidate_duration
            continue
        return Pack(members, seconds, stop)
    return Pack(members, seconds, 'scan_cap' if capped else 'exhausted')


class PackingMetrics:
    def __init__(self, registry):
        prefix = 'omi_batch_pipeline_packing_'
        self.samples = Counter(prefix + 'samples_total', 'Lease sample dispositions', ['outcome'], registry=registry)
        self.stops = Counter(
            prefix + 'stops_total', 'First stop in the counterfactual', ['gap', 'size', 'reason'], registry=registry
        )
        self.members = Histogram(
            prefix + 'members',
            'Members per counterfactual unit',
            ['gap', 'size'],
            buckets=(0, 1, 2, 4, 8, config.MAX_MEMBERS),
            registry=registry,
        )
        self.seconds = Counter(
            prefix + 'eligible_seconds_total',
            'Original PCM seconds in the counterfactual',
            ['gap', 'size'],
            registry=registry,
        )
        self.gaps = Histogram(
            prefix + 'capture_gap_seconds',
            'Validated absolute gap between adjacent sources in the same scope',
            ['kind'],
            buckets=(0, 1, 10, 30, 60, 300, 3600),
            registry=registry,
        )
        self.depth = Histogram(
            prefix + 'due_depth',
            'Observed due depth in the owner priority partition, including the anchor',
            ['coverage'],
            buckets=(1, 2, 4, 8, config.PAGE_ROWS),
            registry=registry,
        )
        self.cohorts = Counter(
            prefix + 'cohort_units_total',
            'Confirmed lease samples and unique completions by intake cohort',
            ['event', 'entitlement', 'source_age'],
            registry=registry,
        )

    def complete(self, observation):
        if config.sample_rate():
            self.cohorts.labels('completed', *_cohort(observation)).inc()

    def observe(self, store, owner, segment, priority, attempt, when, ceiling, later):
        if not _READ_SLOT.acquire(blocking=False):
            self.samples.labels('busy').inc()
            return
        try:
            future = submit_with_context(
                db_executor, self._read, store, owner, segment, priority, attempt, when, ceiling, monotonic(), later
            )
        except Exception:
            _READ_SLOT.release()
            self.samples.labels('unavailable').inc()
        else:
            future.add_done_callback(lambda _: _READ_SLOT.release())

    def _read(self, store, owner, segment, priority, attempt, when, ceiling, submitted, later):
        try:
            if not config.sample_rate():
                return
            if monotonic() - submitted > config.READ_TIMEOUT_SECONDS:
                self.samples.labels('stale').inc()
                return
            with read_origin('job:batch_packing_counterfactual'):
                rows = store.packing_candidates(owner)
            self._record(rows, segment, priority, attempt, when, ceiling, later)
        except Exception:
            # A probe failure has no path back into the issued lease. Avoid
            # exception text, which can contain a document path.
            self.samples.labels('unavailable').inc()

    def _record(self, rows, segment, priority, attempt, when, ceiling, later):
        capped = len(rows) == config.PAGE_ROWS
        partition = [
            row
            for row in rows
            if row.get('priority') == priority and _number(row.get('enqueued_at')) and row['enqueued_at'] <= when
        ]
        later_ready = frozenset(
            row['segment_id']
            for row in partition
            if row.get('state') == 'leased'
            and (attempt_at_commit := later.get(row['segment_id'])) is not None
            and row.get('attempt') == attempt_at_commit
        )
        index = next((i for i, row in enumerate(partition) if row['segment_id'] == segment), None)
        if index is None or partition[index].get('state') != 'leased' or partition[index].get('attempt') != attempt:
            self.samples.labels('anchor_missing').inc()
            return
        anchor, following = partition[index], partition[index + 1 :]
        self.samples.labels('observed').inc()
        self.cohorts.labels('leased_sample', *_cohort(job_observation(anchor))).inc()
        self.depth.labels('capped' if capped else 'complete').observe(
            1 + sum(_due(row, when, later_ready) for row in partition)
        )
        previous_by_scope = {}
        for row in partition:
            observation = job_observation(row)
            scope = observation.get('scope')
            gap = _gap(previous_by_scope.get(scope, {}), observation)
            if gap is not None:
                self.gaps.labels('overlap' if gap < 0 else 'gap').observe(abs(gap))
            if scope:
                previous_by_scope[scope] = observation
        for gap in config.GAP_SECONDS:
            for size in config.PACK_SECONDS:
                pack = build_pack(
                    anchor,
                    following,
                    when=when,
                    max_gap=gap,
                    max_seconds=min(size, ceiling),
                    predecessor=index > 0,
                    capped=capped,
                    later_ready=later_ready,
                )
                self.stops.labels(gap, size, pack.stop).inc()
                self.members.labels(gap, size).observe(pack.members)
                self.seconds.labels(gap, size).inc(pack.seconds)
