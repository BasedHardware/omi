"""Hourly shadow-unit projection piggybacked on existing durable writes."""

from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from config.plan_catalog import resolve_subscription_entitlements
from config.ladder_v1 import enabled, budget_enforcement_enabled
from config.rate_card import (
    budget_units,
    normalize_transcription_provider,
    price_llm_attempt,
    price_request,
    price_transcription,
    standard_chat_units,
    EXCLUDED_FUNDING,
)
from database._client import get_customer_firestore_client
from utils.observability.fallback import record_fallback

FEATURES = (
    'transcription',
    'conversation_extraction',
    'chat',
    'proactive',
    'screen',
    'realtime_voice',
    'web_search',
    'mcp_api',
    'other_llm',
)
STATUSES = ('complete', 'estimated', 'provisional', 'missing')
COVERAGE_GAPS = (
    'mcp_api_request_quantities_not_persisted',
    'stt_paths_without_hourly_writers',
    'direct_llm_without_attempts',
    'gateway_delivery_best_effort',
    'search_vendor_request_fees',
)


def feature_class(raw: Any) -> str:
    raw = str(raw or '')
    if raw.startswith(('chat', 'persona', 'desktop_chat', 'public_shared_conversation_chat', 'file_chat')):
        return 'chat'
    if 'realtime' in raw or 'voice' in raw:
        return 'realtime_voice'
    if 'web_search' in raw:
        return 'web_search'
    if raw.startswith(('proactive', 'proactivity', 'mentor', 'commitment')):
        return 'proactive'
    if any(s in raw for s in ('screen', 'desktop_proactivity', 'livenotes')):
        return 'screen'
    if raw.startswith(('conv_', 'memories', 'memory', 'external_structure')):
        return 'conversation_extraction'
    return 'other_llm'


def _safe_price(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except Exception:
        # Shadow pricing cannot suppress an existing usage/attempt write.
        record_fallback(
            component='other',
            from_mode='shadow_pricing',
            to_mode='incomplete_shadow',
            reason='invalid_config',
            outcome='degraded',
        )
        return {'micro_units': 0, 'status': 'missing', 'reasons': ['shadow_pricing_failed']}


def _price_hourly_transcription(seconds: Any, *, provider: str, funding: str, accepted: bool) -> dict[str, Any]:
    priced = price_transcription(seconds, provider=provider, funding=funding, accepted=accepted)
    if accepted and funding == 'omi' and priced['status'] != 'missing':
        value = float(seconds)
        if not math.isfinite(value) or value < 0:
            raise ValueError('accepted speech must be finite and nonnegative')
        priced['accepted_speech_seconds'] = value
    return priced


def _leaf(priced: Mapping[str, Any], *, provider: str = 'unknown', source: str = 'unknown') -> dict[str, Any]:
    status = str(priced['status'])
    leaf = {
        'micro_units': firestore.Increment(int(priced['micro_units'])),
        'quantity_attributed_micro_units': firestore.Increment(int(priced['micro_units'])),
        'quantity_attributed_missing_events': firestore.Increment(1 if status == 'missing' else 0),
        'events': firestore.Increment(1),
        'status_counts': {status: firestore.Increment(1)},
        'providers': firestore.ArrayUnion([provider]),
        'sources': firestore.ArrayUnion([source]),
    }
    if priced['reasons']:
        leaf['reasons'] = firestore.ArrayUnion(list(priced['reasons']))
    return leaf


def hourly_shadow(updates: Mapping[str, Any], metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    accepted = metadata.get('accepted_speech_seconds')
    elapsed = updates.get('transcription_seconds', 0)
    if accepted is None and not elapsed and not updates.get('speech_seconds', 0):
        return {}
    funding = str(metadata.get('funding', 'unknown'))
    if funding not in {'omi', 'byok', 'custom', 'on_device'}:
        funding = 'unknown'
    raw_provider = metadata.get('provider', 'unknown')
    provider = normalize_transcription_provider(raw_provider)
    if provider not in {'deepgram', 'deepgram_self_hosted', 'modulate', 'parakeet', 'soniox'}:
        provider = 'unknown'
    source = str(metadata.get('source', 'unknown'))
    if source not in {'listen', 'sync_v1', 'sync_v2', 'parakeet_proxy', 'test'}:
        source = 'unknown'
    priced = _safe_price(
        _price_hourly_transcription,
        accepted if accepted is not None else elapsed,
        provider=provider,
        funding=funding,
        accepted=accepted is not None,
    )
    if provider == 'deepgram_self_hosted':
        priced['reasons'] = ['provider_rate_unavailable' if r == 'provider_unknown' else r for r in priced['reasons']]
    if accepted is None and funding == 'omi':
        priced['reasons'].append('accepted_speech_unavailable')
        if source in {'sync_v1', 'sync_v2'}:
            priced['reasons'].append('initial_vad_counter_ratio_estimate')
    leaf = _leaf(priced, provider=provider, source=source)
    leaf['legacy_counter_seconds'] = firestore.Increment(elapsed or 0)
    leaf['quantity_attributed_seconds'] = firestore.Increment(elapsed or 0)
    # Status alone is not coverage: a missing annotation can still carry priced
    # units. Persist disjoint unpriced quantities in the same atomic increment.
    leaf['unpriced_counter_seconds'] = firestore.Increment(
        (elapsed or 0) if priced['status'] == 'missing' and not priced['micro_units'] else 0
    )
    if 'accepted_speech_seconds' in priced:
        leaf['accepted_speech_seconds'] = firestore.Increment(priced['accepted_speech_seconds'])
    lane = (
        'on_device'
        if funding == 'on_device'
        else (
            'live'
            if source == 'listen'
            else 'batch' if source in {'sync_v1', 'sync_v2', 'parakeet_proxy'} else 'unknown'
        )
    )
    shadow: dict[str, Any] = {'rate_card': 'v1', 'features': {'transcription': {'funding': {funding: leaf}}}}
    if enabled('LADDER_V1_LANE_METERING_ENABLED'):
        shadow['lanes'] = {
            lane: {
                'micro_units': firestore.Increment(int(priced['micro_units'])),
                'speech_seconds': firestore.Increment(priced.get('accepted_speech_seconds', 0)),
                'accepted_events': firestore.Increment(1 if 'accepted_speech_seconds' in priced else 0),
            }
        }
    return {'shadow_v1': shadow}


def gateway_shadow(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    priced = _safe_price(price_llm_attempt, data)
    funding = str(data.get('payer', 'unknown'))
    if funding not in {'omi', 'byok', 'custom', 'on_device'}:
        funding = 'unknown'
    feature = feature_class(data.get('feature'))
    try:
        stamp = datetime.fromisoformat(str(data['occurred_at']).replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.astimezone(timezone.utc).date().isoformat() != data.get('date'):
            raise ValueError('inconsistent event date')
        hour = stamp.astimezone(timezone.utc).strftime('%H')
    except (ValueError, KeyError):
        hour = 'unknown'
        priced['status'] = 'missing'
        priced['reasons'].append('event_hour_unknown')
    provider = str(data.get('provider', 'unknown'))
    if provider not in {'openai', 'gemini', 'anthropic', 'perplexity', 'openrouter'}:
        provider = 'unknown'
    leaf = _leaf(priced, provider=provider, source='gateway_attempt')
    leaf['quantity_attributed_events'] = firestore.Increment(1)
    leaf['unpriced_events'] = firestore.Increment(
        1 if priced['status'] == 'missing' and not priced['micro_units'] else 0
    )
    features = {feature: {'funding': {funding: leaf}}}
    if feature == 'web_search':
        # Each vendor synthesis attempt is a web request; retries remain separate infra attempts.
        # Provider BYOK excludes model/vendor cost, not Omi-hosted request infrastructure.
        request = _safe_price(price_request, 'web_search_tool', funding='omi')
        if funding == 'omi':
            request['reasons'].append('search_vendor_request_fee_unmeasured')
        features['web_search_tool'] = {'funding': {'omi': _leaf(request, source='gateway_attempt')}}
    annotation = {**priced, 'rate_card': 'v1', 'funding': funding, 'feature': feature, 'hour': hour}
    return annotation, {'shadow_v1': {'rate_card': 'v1', 'hours': {hour: {'features': features}}}}


def normalize_plan_usage(data: Mapping[str, Any]) -> dict[str, Any]:
    """Add disjoint old literal dotted increments to new nested attribution."""
    plans: dict[str, Any] = {}
    existing = data.get('plan_usage')
    if isinstance(existing, dict):
        plans = deepcopy(existing)
    for key, value in data.items():
        if not key.startswith('plan_usage.'):
            continue
        *parents, leaf = key.split('.')[1:]
        if not parents:
            continue
        cursor = plans
        for segment in parents:
            branch = cursor.get(segment)
            if not isinstance(branch, dict):
                branch = {}
                cursor[segment] = branch
            cursor = branch
        prior = cursor.get(leaf)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            cursor[leaf] = (prior if isinstance(prior, (int, float)) else 0) + value
        elif prior is None:
            cursor[leaf] = value
    return plans


def _historical_quantity(leaf, quantity):
    attributed = 'quantity_attributed_seconds' if quantity == 'legacy_counter_seconds' else 'quantity_attributed_events'
    amount = max(0, float(leaf.get(quantity, 0)) - float(leaf.get(attributed, 0)))
    units = max(0, int(leaf.get('micro_units', 0)) - int(leaf.get('quantity_attributed_micro_units', 0)))
    missing = max(
        0, int(leaf.get('status_counts', {}).get('missing', 0)) - int(leaf.get('quantity_attributed_missing_events', 0))
    )
    return amount, units, missing


def _ambiguous_quantity(leaf, quantity):
    amount, units, missing = _historical_quantity(leaf, quantity)
    if not units or not missing:
        return 0
    return min(int(amount), missing) if quantity == 'events' else amount


def _covered_quantity(leaf, funding, quantity, unpriced, enforcing):
    total = float(leaf.get(quantity, 0))
    if not enforcing or funding in EXCLUDED_FUNDING:
        return int(total) if quantity == 'events' else total
    historical, units, missing = _historical_quantity(leaf, quantity)
    covered = max(0, total - historical - float(leaf.get(unpriced, 0)))
    # Only historical units may establish historical coverage. A new priced
    # write must not hide an old zero-unit gap in the same aggregated leaf.
    # Mixed historical priced statuses remain ambiguous, never double-billed.
    if units or funding == 'omi' and not missing:
        covered += historical
    return int(covered) if quantity == 'events' else covered


def get_usage_units(
    uid: str, period: datetime, *, firestore_client: Any | None = None, entitlements: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Read one UTC calendar month; annual plans still use monthly budgets.

    period selects the month. Uses one existing year/month query and at most
    two day-rollups per elapsed day in one batched RPC, without immutable attempt
    scans. Missing records and known producer gaps make this a lower-bound shadow total. Flagged ladder
    enforcement adds conservative residual-second and attempt estimates in memory;
    legacy and flag-off reads retain the shadow-only total.
    """
    if period.tzinfo is None:
        raise ValueError('timezone-aware period required')
    period = period.astimezone(timezone.utc)
    start = period.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    client = firestore_client or get_customer_firestore_client()
    user = client.collection('users').document(uid)
    if entitlements is None:
        snap = user.get(['subscription'])
        data = snap.to_dict() or {}
        entitlements = resolve_subscription_entitlements(data.get('subscription') or {})
    enforcing = budget_enforcement_enabled() and entitlements['entitlement_version'] == 'ladder_v1'
    totals: dict[str, int] = {}
    statuses: dict[str, dict[str, int]] = {}
    funding_totals: dict[str, int] = {}
    missing_hourly = 0
    missing_days = 0
    missing_attempts = 0
    missing_seconds = 0.0
    ambiguous_seconds = 0.0
    ambiguous_attempts = 0
    lane_totals: dict[str, int] = {}
    lane_seconds: dict[str, float] = {}
    lane_accepted: dict[str, int] = {}

    def consume(features: Mapping[str, Any]) -> None:
        for feature, feature_data in features.items():
            if not isinstance(feature_data, Mapping):
                continue
            for funding, leaf in feature_data.get('funding', {}).items():
                units = int(leaf.get('micro_units', 0))
                totals[feature] = totals.get(feature, 0) + units
                funding_totals[funding] = funding_totals.get(funding, 0) + units
                counts = statuses.setdefault(feature, {})
                for status, count in leaf.get('status_counts', {}).items():
                    counts[status] = counts.get(status, 0) + int(count)

    query = (
        user.collection('hourly_usage')
        .where(filter=FieldFilter('year', '==', start.year))
        .where(filter=FieldFilter('month', '==', start.month))
    )
    for snap in query.select(['shadow_v1', 'transcription_seconds', 'speech_seconds']).stream():
        data = snap.to_dict() or {}
        shadow = data.get('shadow_v1')
        if isinstance(shadow, Mapping):
            features = shadow.get('features', {})
            consume(features)
            for lane, values in shadow.get('lanes', {}).items():
                lane_totals[lane] = lane_totals.get(lane, 0) + int(values.get('micro_units', 0))
                lane_seconds[lane] = lane_seconds.get(lane, 0) + float(values.get('speech_seconds', 0))
                lane_accepted[lane] = lane_accepted.get(lane, 0) + int(values.get('accepted_events', 0))
            covered = sum(
                _covered_quantity(leaf, funding, 'legacy_counter_seconds', 'unpriced_counter_seconds', enforcing)
                for funding, leaf in features.get('transcription', {}).get('funding', {}).items()
            )
            ambiguous_seconds += sum(
                _ambiguous_quantity(leaf, 'legacy_counter_seconds')
                for funding, leaf in features.get('transcription', {}).get('funding', {}).items()
                if funding not in EXCLUDED_FUNDING
            )
            residual = max(float(data.get('transcription_seconds', 0)) - covered, 0)
            missing_seconds += residual
            if residual:
                missing_hourly += 1
        elif data.get('transcription_seconds') or data.get('speech_seconds'):
            missing_hourly += 1
            missing_seconds += float(data.get('transcription_seconds', 0))
    hashed = hashlib.sha256(uid.encode()).hexdigest()[:16]
    # Batch explicit day refs in one RPC. Missing docs still cost a read, so
    # never request future dates (including the future tail of this month).
    through = min(
        end, datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    )
    days = []
    day = start
    while day < through:
        days.append(day.date().isoformat())
        day += timedelta(days=1)
    refs = [client.collection('llm_gateway_user_days').document(f'{day}_{hashed}') for day in days]
    if entitlements['entitlement_version'] == 'ladder_v1':
        refs.extend(user.collection('ladder_v1_api_days').document(day) for day in days)
    documents = (
        {
            snap.id: snap.to_dict() or {}
            for snap in client.get_all(refs, field_paths=['shadow_v1', 'attempts', 'micro_units', 'requests'])
        }
        if refs
        else {}
    )
    for day in days:
        data = documents.get(f'{day}_{hashed}', {})
        shadow = data.get('shadow_v1')
        projected = 0
        if isinstance(shadow, Mapping):
            for hour in shadow.get('hours', {}).values():
                features = hour.get('features', {})
                consume(features)
                ambiguous_attempts += sum(
                    _ambiguous_quantity(leaf, 'events')
                    for feature, row in features.items()
                    if feature != 'web_search_tool'
                    for funding, leaf in row.get('funding', {}).items()
                    if funding not in EXCLUDED_FUNDING
                )
                projected += sum(
                    _covered_quantity(leaf, funding, 'events', 'unpriced_events', enforcing)
                    for feature, row in features.items()
                    if feature != 'web_search_tool'
                    for funding, leaf in row.get('funding', {}).items()
                )
        residual = max(int(data.get('attempts', 0)) - projected, 0)
        if residual:
            missing_days += 1
            missing_attempts += residual
        # New daily API quantities are priced separately from tool/model attempts.
        if entitlements['entitlement_version'] == 'ladder_v1':
            api = documents.get(day, {})
            if api.get('micro_units'):
                consume(
                    {
                        'mcp_api': {
                            'funding': {
                                'omi': {
                                    'micro_units': api['micro_units'],
                                    'status_counts': {'provisional': api.get('requests', 0)},
                                }
                            }
                        }
                    }
                )
    if enforcing:
        # Treat every residual second as speech at the pinned unknown-provider
        # provisional rate. Do not apply the historical elapsed/silence ratio.
        # Unknown attempt sizes use the same provisional standard-chat quantity
        # as the Free budget. These are estimates, never repaired ledger writes.
        speech_proxy = price_transcription(missing_seconds, provider='unknown', funding='omi', accepted=True)
        attempt_proxy = int(Decimal(missing_attempts) * standard_chat_units() * 1_000_000)
        for feature, amount in [('transcription', speech_proxy['micro_units']), ('other_llm', attempt_proxy)]:
            consume({feature: {'funding': {'omi': {'micro_units': amount, 'status_counts': {}}}}})
    return {
        'used_units': float(Decimal(sum(totals.values())) / 1_000_000),
        'budget_units': budget_units(entitlements),
        'by_feature': {k: float(Decimal(v) / 1_000_000) for k, v in totals.items()},
        'by_lane': {
            k: {
                'units': float(Decimal(v) / 1_000_000),
                'speech_seconds': lane_seconds.get(k, 0),
                'live_hours': lane_seconds.get(k, 0) / 3600 if k == 'live' and lane_accepted.get(k, 0) else None,
            }
            for k, v in lane_totals.items()
        },
        'by_funding': {k: float(Decimal(v) / 1_000_000) for k, v in funding_totals.items()},
        'completeness': {
            'status': 'partial',
            'by_feature': statuses,
            'unprojected_hourly_docs': missing_hourly,
            'unprojected_gateway_days': missing_days,
            'unprojected_gateway_attempts': missing_attempts,
            'unprojected_transcription_seconds': missing_seconds,
            **(
                {
                    'ambiguous_priced_transcription_seconds': ambiguous_seconds,
                    'ambiguous_priced_gateway_attempts': ambiguous_attempts,
                }
                if enforcing
                else {}
            ),
            'coverage_gaps': list(COVERAGE_GAPS),
        },
        'entitlement_version': entitlements['entitlement_version'],
        'rate_card_version': 'v1',
    }
