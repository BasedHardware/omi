"""Backend-owned estimates and explicit backlog intent, additive behind admission flags."""

from typing import Any
import math
import time

from config.rate_card import recording_units_per_hour, standard_chat_units, budget_units
from config.plan_catalog import resolve_subscription_entitlements, allocation_limit
from config.stt_cap_dispatch import recovery_cohort_admits
from datetime import datetime, timezone
from models.users import ProcessingBacklog
from utils import funded_processing


def whole_percent(value: float) -> int:
    """Half-up whole percent. 12.5 displays as 13; a non-positive ratio is 0."""
    if not value or value <= 0:
        return 0
    return int(math.floor(value + 0.5))


def defer_estimate(conversation: Any) -> dict:
    start, end = getattr(conversation, 'started_at', None), getattr(conversation, 'finished_at', None)
    seconds = max(0, (end - start).total_seconds()) if start and end else 0
    text = getattr(conversation, 'text', '') or ' '.join(
        getattr(s, 'text', '') for s in (getattr(conversation, 'transcript_segments', None) or [])
    )
    # A conservative standard-work bundle, scaled for long transcripts. This
    # estimates LLM processing only: on-device text is never charged STT again.
    units = float(standard_chat_units()) * 8 * max(1, len(text) / 12000)
    return {'seconds': seconds, 'units': units, 'version': 'standard_bundle_v1'}


def snapshot(uid: str, *, allowance=None, audio=None, summary=None) -> ProcessingBacklog | None:
    if not funded_processing.enabled(uid):
        return None
    from database import processing_backlog as store
    from utils.sync import cap_hold

    allowance = allowance if allowance is not None else funded_processing.allowance(uid)
    summary = summary if summary is not None else store.read(uid)
    audio = audio if audio is not None else cap_hold.ensure_summary(uid)
    seconds = max(0, int(round(audio.get('seconds', 0))))
    count = max(0, int(audio.get('count', 0)))
    deferred = max(0, int(summary.get('count', 0)))
    rate = float(recording_units_per_hour('batch'))
    estimate = seconds * rate / 3600 + max(0, summary.get('units', 0))
    remaining, budget = funded_processing.capacity(allowance)
    active = summary.get('state') == 'processing' and summary.get('period') == funded_processing.period_id()
    state = (
        'capped'
        if not allowance.managed
        else 'none' if count + deferred == 0 else 'processing' if active else 'waiting_choice'
    )
    return ProcessingBacklog(
        state=state,
        budget_exhausted=not allowance.managed
        and getattr(allowance, 'reason', 'usage_budget_exhausted')
        in {'usage_budget_exhausted', 'plan_allowance_exhausted'},
        held_audio_count=count,
        held_audio_seconds=seconds,
        deferred_conversations=deferred,
        deferred_seconds=max(0, int(round(summary.get('seconds', 0)))),
        estimated_units=round(estimate, 6),
        estimated_hours=estimate / rate,
        estimated_percent=whole_percent(100 * estimate / budget) if budget else 0,
        remaining_units=remaining,
        exceeds_remaining=remaining is not None and estimate > remaining,
    )


def choose(uid: str, *, request_key: str, automatic: bool = False, intent_at: Any = None) -> dict | None:
    if not recovery_cohort_admits(uid) or not funded_processing.enabled(uid):
        return None
    from database import processing_backlog as store

    # Pin the grant's month before reads: rollover between validation and the
    # write must expire this grant, never stamp old intent with a new budget.
    period = funded_processing.period_id()
    allowance = funded_processing.allowance(uid)
    result = snapshot(uid, allowance=allowance)
    if result is None:
        return None
    # The first delivery of an old payment event is not fresh upgrade consent.
    # Record declined intent too, so retries cannot reinterpret it after reset.
    intent_period = None
    if automatic:
        try:
            moment = (
                intent_at if isinstance(intent_at, datetime) else datetime.fromtimestamp(float(intent_at), timezone.utc)
            )
            intent_period = moment.astimezone(timezone.utc).strftime('%Y-%m')
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    begin = result.state not in {'none', 'capped'} and (
        not automatic or intent_period == period and not result.exceeds_remaining
    )
    if not begin and not automatic:
        return None
    chosen = store.start(
        uid,
        period=period,
        remaining=result.remaining_units,
        cutoff=time.time(),
        request_key=request_key,
        automatic=automatic,
        begin=begin,
    )
    return chosen if begin else None


def is_active(row: dict) -> bool:
    return row.get('state') == 'processing' and row.get('period') == funded_processing.period_id()


def allowance_increased(previous: Any, current: Any) -> bool:
    """Compare catalog allocations, never Stripe amounts or a calendar renewal.

    Period validity is normalized for identity comparison only. This cannot
    authorize work: choose() separately resolves the real funded allowance.
    """

    def fields(value):
        if value is None:
            return {'plan': 'basic'}
        return dict(value) if isinstance(value, dict) else value.model_dump()

    old, new = fields(previous), fields(current)
    if old.get('plan') == new.get('plan') and old.get('current_price_id') == new.get('current_price_id'):
        return False

    def limit(value):
        identity = {
            **value,
            'status': 'active',
            'current_period_end': int(datetime.now(timezone.utc).timestamp()) + 86400,
        }
        entitlement = resolve_subscription_entitlements(identity)
        units = budget_units(entitlement)
        if units is not None:
            return float(units)
        seconds = allocation_limit(entitlement['plan_id'], 'transcription')
        return None if seconds is None else seconds * float(recording_units_per_hour('batch')) / 3600

    before, after = limit(old), limit(new)
    return before is not None and (after is None or after > before)
