"""Bounded playback-metadata maintenance pass for the existing repair CronJob."""

from collections import Counter
from datetime import datetime, timezone

from prometheus_client import Gauge

from google.api_core.exceptions import FailedPrecondition, NotFound

from config.batch_pipeline_projection_rebuild import enabled as durable_debt_enabled
from database import record_projection_rebuild as jobs
from database._client import get_firestore_client
from utils.batch_pipeline.record_projection_rebuild import rebuild

MAX_PER_PASS = 128
MAX_COLLECTION_MARKERS = 10000
NO_OBJECTS_MAX_AGE_SECONDS = 7 * 86400
BACKLOG = Gauge('omi_projection_rebuild_marker_count', 'Bounded marker count; saturated at collection limit plus one')
OLDEST = Gauge('omi_projection_rebuild_oldest_age_seconds', 'Oldest marker age in the bounded collection scan')
AT_CAPACITY = Gauge('omi_projection_rebuild_at_capacity', 'Marker collection exceeds its maintenance limit')
PRESSURE_BLOCKED = Gauge(
    'omi_projection_rebuild_pressure_blocked',
    'Observed empty-marker retirement blocked by producer fences under pressure',
)


def run(*, mode='apply', budget, firestore_client=None):
    if mode not in {'apply', 'plan'}:
        raise ValueError('invalid projection repair mode')
    if not durable_debt_enabled():
        return {'event': 'record_projection_rebuild', 'outcome': 'disabled'}
    client = firestore_client if firestore_client is not None else get_firestore_client()
    counts = Counter()
    # One ordered field uses Firestore's automatic single-field index. Rotate
    # refused work to the tail so chronic failures cannot starve later markers.
    query = client.collection(jobs.COLLECTION).order_by('requested_at').limit(MAX_COLLECTION_MARKERS + 1)
    page = list(query.stream(timeout=budget.timeout(), retry=None))
    now = datetime.now(timezone.utc)
    ages = {
        doc.id: max(0.0, (now - created).total_seconds())
        for doc in page
        if isinstance(created := getattr(doc, 'create_time', None), datetime)
    }
    at_capacity = len(page) > MAX_COLLECTION_MARKERS
    gauges = {
        'marker_count': len(page),
        'oldest_age_seconds': max(ages.values(), default=0),
        'at_capacity': at_capacity,
    }
    BACKLOG.set(len(page))
    OLDEST.set(gauges['oldest_age_seconds'])
    AT_CAPACITY.set(at_capacity)
    PRESSURE_BLOCKED.set(0)
    for doc in page[:MAX_PER_PASS]:
        budget.check()
        data = doc.to_dict() or {}
        uid, cid = data.get('owner_id'), data.get('conversation_id')
        try:
            # Rotate before identity validation AND discovery: malformed rows or
            # a stuck listing cannot monopolize every bounded page.
            attempt = None
            if mode != 'plan':
                attempt = doc.reference.update(
                    {'requested_at': datetime.now(timezone.utc)},
                    option=client.write_option(last_update_time=doc.update_time),
                    timeout=budget.timeout(),
                    retry=None,
                )
            if (
                not isinstance(uid, str)
                or not isinstance(cid, str)
                or data.get('kind') != jobs.KIND
                or doc.id != jobs.marker_id(uid, cid)
            ):
                counts['invalid'] += 1
                continue
            if mode == 'plan':
                counts['due'] += 1
                continue
            if attempt is None:
                raise RuntimeError('projection repair attempt unavailable')
            result = rebuild(uid, cid)
            budget.check()
            retire_empty = result == 'no_objects' and (ages.get(doc.id, 0) >= NO_OBJECTS_MAX_AGE_SECONDS or at_capacity)
            if retire_empty:
                counts[
                    jobs.retire_empty(uid, cid, observed_update_time=attempt.update_time, firestore_client=client)
                ] += 1
            elif result is True or result is False:
                doc.reference.delete(
                    option=client.write_option(last_update_time=attempt.update_time),
                    timeout=budget.timeout(),
                    retry=None,
                )
                counts['rebuilt' if result else 'owner_gone'] += 1
            else:
                counts['deferred'] += 1
        except (FailedPrecondition, NotFound):
            counts['changed'] += 1  # Never clear a newer socket's debt.
        except Exception:
            budget.check()  # Let the hard deadline unwind the enclosing pass.
            counts['error'] += 1
    gauges['pressure_fenced_count'] = counts['producer_fenced'] if at_capacity else 0
    gauges['pressure_blocked'] = bool(at_capacity and counts['producer_fenced'] and not counts['retired_no_objects'])
    PRESSURE_BLOCKED.set(gauges['pressure_blocked'])
    return {
        'event': 'record_projection_rebuild',
        'outcome': 'error' if counts['error'] else 'capacity_exceeded' if at_capacity else 'ok',
        'gauges': gauges,
        'dispositions': dict(counts),
    }


def run_job():
    from config import record_seal_repair as config
    from utils.batch_pipeline.record_seal_budget import SweepBudget, BudgetExhausted

    if not durable_debt_enabled() or not config.enabled():
        return {'event': 'record_projection_rebuild', 'outcome': 'disabled'}
    config.require_runtime()
    mode = config.settings()[3]
    budget = SweepBudget(60)
    try:
        with budget.interrupt_io():
            return run(mode=mode, budget=budget)
    except BudgetExhausted:
        return {'event': 'record_projection_rebuild', 'outcome': 'budget_exhausted'}
