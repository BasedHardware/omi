"""Bounded playback-metadata maintenance pass for the existing repair CronJob."""

from collections import Counter
from datetime import datetime, timezone

from google.api_core.exceptions import FailedPrecondition, NotFound

from database import record_projection_rebuild as jobs
from database._client import get_firestore_client
from utils.batch_pipeline.record_projection_rebuild import durable_debt_enabled, rebuild


def run(*, mode='apply', budget, firestore_client=None):
    if mode not in {'apply', 'plan'}:
        raise ValueError('invalid projection repair mode')
    if not durable_debt_enabled():
        return {'event': 'record_projection_rebuild', 'outcome': 'disabled'}
    client = firestore_client if firestore_client is not None else get_firestore_client()
    counts = Counter()
    # One ordered field uses Firestore's automatic single-field index. Rotate
    # refused work to the tail so chronic failures cannot starve later markers.
    query = client.collection(jobs.COLLECTION).order_by('requested_at').limit(128)
    page = list(query.stream(timeout=budget.timeout(), retry=None))
    for doc in page:
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
            if result is not None:
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
    return {'event': 'record_projection_rebuild', 'outcome': 'ok', 'dispositions': dict(counts)}


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
