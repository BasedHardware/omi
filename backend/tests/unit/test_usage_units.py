from datetime import datetime, timezone
from decimal import Decimal
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import hashlib
from typing import Any
import pytest
from tests.unit.fixtures.shadow_usage_firestore import Store, merge


@pytest.fixture(scope='module')
def units():
    from database import usage_units

    return usage_units


def test_normalize_old_and_new_attribution_without_mutating_history(units):
    old: dict[str, Any] = {
        'plan_usage.plus.transcription_seconds': 70,
        'plan_usage.plus._metadata.cost_status_counts.missing': 1,
        'plan_usage': {'plus': {'transcription_seconds': 30, '_metadata': {'cost_status_counts': {'missing': 2}}}},
    }
    result = units.normalize_plan_usage(old)
    assert result['plus']['transcription_seconds'] == 100
    assert result['plus']['_metadata']['cost_status_counts']['missing'] == 3
    assert old['plan_usage']['plus']['transcription_seconds'] == 30


def test_stt_fractional_funding_and_estimation_are_distinct(units):
    accepted = {}
    merge(
        accepted,
        units.hourly_shadow(
            {'transcription_seconds': 1},
            {'provider': 'modulate', 'funding': 'omi', 'source': 'test', 'accepted_speech_seconds': '0.03125'},
        ),
    )
    leaf = accepted['shadow_v1']['features']['transcription']['funding']['omi']
    assert accepted['shadow_v1']['rate_card_version'] == 'v1'
    assert leaf['rate_card_version'] == 'v1'
    assert leaf['micro_units'] > 0 and leaf['status_counts'] == {'complete': 1}
    estimate = {}
    merge(
        estimate,
        units.hourly_shadow(
            {'transcription_seconds': 100}, {'provider': 'parakeet', 'funding': 'omi', 'source': 'listen'}
        ),
    )
    assert estimate['shadow_v1']['features']['transcription']['funding']['omi']['status_counts'] == {'estimated': 1}
    byok = {}
    merge(
        byok,
        units.hourly_shadow(
            {'transcription_seconds': 100}, {'provider': 'deepgram', 'funding': 'byok', 'source': 'listen'}
        ),
    )
    assert byok['shadow_v1']['features']['transcription']['funding']['byok']['micro_units'] == 0


def test_read_joins_hourly_and_gateway_rollups_without_attempt_scan(units, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 17, tzinfo=timezone.utc)

    monkeypatch.setattr(units, 'datetime', Clock)
    uid = 'u'
    month = datetime(2026, 10, 15, tzinfo=timezone.utc)
    e = {
        'payer': 'omi',
        'provider': 'openai',
        'configured_model': 'gpt-6-luna',
        'usage_status': 'confirmed',
        'feature': 'chat_agent',
        'uncached_input_tokens': 2048,
        'output_tokens': 512,
        'occurred_at': '2026-10-01T08:00:00+00:00',
        'date': '2026-10-01',
    }
    annotation, rollup = units.gateway_shadow(e)
    stt = {}
    merge(
        stt,
        units.hourly_shadow(
            {'transcription_seconds': 100}, {'provider': 'parakeet', 'funding': 'omi', 'source': 'test'}
        ),
    )
    stt.update(year=2026, month=10)
    day = {}
    merge(day, rollup)
    store = Store(
        {
            'users/u': {'subscription': {'plan': 'basic'}},
            'users/u/hourly_usage/2026-10-01-08': stt,
            'llm_gateway_user_days/2026-10-01_' + hashlib.sha256(uid.encode()).hexdigest()[:16]: day,
        }
    )
    result = units.get_usage_units(uid, month, firestore_client=store)
    speech = stt['shadow_v1']['features']['transcription']['funding']['omi']['micro_units']
    assert result['used_units'] == float(Decimal(speech + annotation['micro_units']) / 1_000_000)
    assert result['budget_units'] is None
    assert result['by_feature']['chat'] > 0 and result['by_feature']['transcription'] > 0
    assert result['completeness']['status'] == 'partial'
    assert store.writes == 0 and store.reads == 19
    planned = units.get_usage_units(
        uid,
        month,
        firestore_client=store,
        entitlements={
            'budget': {'kind': 'rate_card_mix', 'speech_seconds': 18000, 'chat_messages': 30, 'chat_tier': 'standard'},
            'entitlement_version': 'ladder_v1',
        },
    )
    assert planned['budget_units'] == 4853


def test_hourly_write_keeps_root_meter_and_finops_counters_and_recovers_dotted_history(units, monkeypatch):
    from database import user_usage

    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'plus')
    date = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    path = 'users/u/hourly_usage/2026-10-01-08'
    store = Store(
        {
            path: {
                'id': '2026-10-01-08',
                'year': 2026,
                'month': 10,
                'transcription_seconds': 70,
                'plan_usage.plus.transcription_seconds': 70,
            }
        }
    )
    user_usage.update_hourly_usage(
        'u',
        date,
        {'transcription_seconds': 12},
        firestore_client=store,
        usage_metadata={'provider': 'parakeet', 'funding': 'omi', 'source': 'test'},
    )
    assert store.writes == 1
    data = store.docs[path]
    assert data['transcription_seconds'] == 82
    assert data['plan_usage.plus.transcription_seconds'] == 70
    assert data['plan_usage']['plus']['transcription_seconds'] == 12
    assert units.normalize_plan_usage(data)['plus']['transcription_seconds'] == 82
    fields = [t.field_path for w in store.wire for t in w.update_transforms]
    assert 'plan_usage.plus.transcription_seconds' in fields
    assert '`plan_usage.plus.transcription_seconds`' not in fields
    monkeypatch.setattr(user_usage, 'db', store)
    assert user_usage.get_monthly_usage_stats_since('u', date, date)['transcription_seconds'] == 82
    monkeypatch.setattr(user_usage, 'get_monthly_chat_usage', lambda *a, **k: {'usage_by_plan': {}})
    assert user_usage.get_usage_by_plan('u', now=date, firestore_client=store)['plus']['transcription_seconds'] == 82


def test_gateway_keeps_two_existing_writes_and_no_duplicate_charge(units, monkeypatch):
    from database import llm_gateway_accounting as ledger

    monkeypatch.setattr(ledger, 'resolve_usage_plan_id', lambda *a, **k: 'plus')
    store = Store({'users/u': {'subscription': {'plan': 'plus'}}})
    event: dict[str, Any] = {
        'attempt_id': 'one',
        'user_uid': 'u',
        'payer': 'omi',
        'provider': 'openai',
        'configured_model': 'gpt-6-luna',
        'usage_status': 'confirmed',
        'feature': 'chat_agent',
        'uncached_input_tokens': 2048,
        'output_tokens': 512,
        'occurred_at': '2026-10-01T08:00:00+00:00',
        'date': '2026-10-01',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 100,
    }
    assert ledger.record_llm_gateway_attempt(event, firestore_client=store)
    assert store.writes == 2
    assert not ledger.record_llm_gateway_attempt(event, firestore_client=store)
    assert store.writes == 2
    annotation = store.docs['llm_gateway_attempts/one']['usage_units_v1']
    assert annotation['micro_units'] == 1059799
    assert annotation['rate_card_version'] == 'v1'
    result = units.get_usage_units('u', datetime(2026, 10, 1, tzinfo=timezone.utc), firestore_client=store)
    assert result['used_units'] == 1.059799
    event.update(attempt_id='byok', payer='byok', estimated_cost_micro_usd=None, cost_status='not_omi_cost')
    assert ledger.record_llm_gateway_attempt(event, firestore_client=store)
    assert store.writes == 4
    result = units.get_usage_units('u', datetime(2026, 10, 1, tzinfo=timezone.utc), firestore_client=store)
    assert result['used_units'] == 1.059799
    assert result['by_funding']['byok'] == 0


def test_v1_and_v2_usage_projections_keep_separate_card_identity(units, monkeypatch):
    from database import llm_gateway_accounting as ledger

    monkeypatch.setattr(ledger, 'resolve_usage_plan_id', lambda *a, **k: 'plus')
    event = {
        'attempt_id': 'v2-price',
        'user_uid': 'u',
        'payer': 'omi',
        'provider': 'gemini',
        'configured_model': 'gemini-2.5-flash',
        'usage_status': 'confirmed',
        'feature': 'chat_agent',
        'uncached_input_tokens': 1_000_000,
        'cached_input_tokens': 0,
        'output_tokens': 0,
        'occurred_at': '2026-10-01T08:00:00+00:00',
        'date': '2026-10-01',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 100,
    }
    store = Store({'users/u': {'subscription': {'plan': 'plus'}}})

    monkeypatch.setenv('RATE_CARD_VERSION', 'v1')
    v1_annotation, v1_rollup = units.gateway_shadow(event)
    v1_hourly = units.hourly_shadow(
        {'transcription_seconds': 10}, {'provider': 'parakeet', 'funding': 'omi', 'source': 'test'}
    )

    monkeypatch.setenv('RATE_CARD_VERSION', 'v2')
    event['attempt_id'] = 'v2-price-selected'
    v2_annotation, v2_rollup = units.gateway_shadow(event)
    v2_hourly = units.hourly_shadow(
        {'transcription_seconds': 10}, {'provider': 'parakeet', 'funding': 'omi', 'source': 'test'}
    )
    assert v1_annotation['rate_card_version'] == 'v1'
    assert v2_annotation['rate_card_version'] == 'v2'
    # v2's corrected 2.5 Flash card carries v1's Standard rates, so the same
    # Flash event prices identically; only the card identity differs.
    assert v2_annotation['micro_units'] == v1_annotation['micro_units']
    assert v1_rollup['shadow_v1']['rate_card_version'] == 'v1'
    assert v2_rollup['shadow_v2']['rate_card_version'] == 'v2'
    assert v1_hourly['shadow_v1']['features']['transcription']['funding']['omi']['rate_card_version'] == 'v1'
    assert v2_hourly['shadow_v2']['features']['transcription']['funding']['omi']['rate_card_version'] == 'v2'

    hourly = {}
    merge(hourly, v1_hourly)
    merge(hourly, v2_hourly)
    hourly.update(year=2026, month=10, transcription_seconds=20)
    day = {}
    merge(day, v1_rollup)
    merge(day, v2_rollup)
    day['attempts'] = 2
    uid_hash = hashlib.sha256(b'u').hexdigest()[:16]
    store.docs['users/u/hourly_usage/2026-10-01-08'] = hourly
    store.docs[f'llm_gateway_user_days/2026-10-01_{uid_hash}'] = day

    v1 = units.get_usage_units(
        'u', datetime(2026, 10, 1, tzinfo=timezone.utc), firestore_client=store, rate_card_version='v1'
    )
    v2 = units.get_usage_units(
        'u', datetime(2026, 10, 1, tzinfo=timezone.utc), firestore_client=store, rate_card_version='v2'
    )
    assert v1['rate_card_version'] == 'v1'
    assert v2['rate_card_version'] == 'v2'
    assert v2['used_units'] == v1['used_units']
    combined = units.get_usage_units('u', datetime(2026, 10, 1, tzinfo=timezone.utc), firestore_client=store)
    assert combined['rate_card_version'] == 'v2'
    assert combined['rate_card_versions'] == ['v1', 'v2']
    assert combined['used_units'] == pytest.approx(v1['used_units'] + v2['used_units'])

    attempt_store = Store({'users/u': {'subscription': {'plan': 'plus'}}})
    event['attempt_id'] = 'persist-v2'
    assert ledger.record_llm_gateway_attempt(event, firestore_client=attempt_store)
    attempt = attempt_store.docs['llm_gateway_attempts/persist-v2']
    assert attempt['usage_units_v2']['rate_card_version'] == 'v2'
    assert 'usage_units_v1' not in attempt


def test_sync_marker_and_nested_usage_remain_in_existing_two_write_transaction(units, monkeypatch):
    from database import user_usage

    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'plus')
    original = user_usage._update_hourly_usage_once_transaction.to_wrap  # pyright: ignore[reportPrivateUsage]

    class Transaction:
        def set(self, ref, data, merge=False):
            ref.set(data, merge=merge)

    monkeypatch.setattr(
        user_usage, '_update_hourly_usage_once_transaction', lambda tx, m, u, d: original(Transaction(), m, u, d)
    )
    store = Store()
    date = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    kwargs: dict[str, Any] = {
        'firestore_client': store,
        'usage_metadata': {'provider': 'parakeet', 'funding': 'omi', 'source': 'sync_v2'},
    }
    assert user_usage.update_hourly_usage_once('u', date, {'transcription_seconds': 60}, 'capture', **kwargs)
    assert store.writes == 2
    assert not user_usage.update_hourly_usage_once('u', date, {'transcription_seconds': 60}, 'capture', **kwargs)
    assert store.writes == 2
    assert store.docs['users/u/hourly_usage/2026-10-01-08']['plan_usage']['plus']['transcription_seconds'] == 60


def test_live_funding_follows_serving_provider_not_other_byok_keys(monkeypatch):
    from types import SimpleNamespace
    from utils import usage_provenance as source

    monkeypatch.delenv('DEEPGRAM_SELF_HOSTED_ENABLED', raising=False)
    monkeypatch.setattr(source, 'get_byok_key', lambda p: 'test-not-a-real-key' if p == 'deepgram' else None)
    host = SimpleNamespace(use_custom_stt=False, stt_service='deepgram')
    assert source.live_usage_metadata(host)['funding'] == 'byok'
    host.stt_service = 'parakeet'
    assert source.live_usage_metadata(host)['funding'] == 'omi'
    host.use_custom_stt = True
    assert source.live_usage_metadata(host)['funding'] == 'custom'
    host.use_custom_stt = False
    host.stt_service = 'deepgram'
    monkeypatch.setenv('DEEPGRAM_SELF_HOSTED_ENABLED', 'true')
    assert source.live_usage_metadata(host) == {
        'funding': 'omi',
        'provider': 'deepgram_self_hosted',
        'source': 'listen',
    }


def test_missing_history_and_shadow_price_failure_do_not_hide_gaps_or_break_legacy_write(units, monkeypatch):
    from database import user_usage

    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'plus')

    def broken(*a, **k):
        raise ValueError('test')

    monkeypatch.setattr(units, 'price_transcription', broken)
    store = Store()
    date = datetime(2026, 10, 1, tzinfo=timezone.utc)
    user_usage.update_hourly_usage(
        'u',
        date,
        {'transcription_seconds': 5},
        firestore_client=store,
        usage_metadata={'funding': 'omi', 'provider': 'parakeet', 'source': 'test'},
    )
    assert store.writes == 1
    data = store.docs['users/u/hourly_usage/2026-10-01-00']
    assert data['transcription_seconds'] == 5
    assert data['shadow_v1']['features']['transcription']['funding']['omi']['status_counts'] == {'missing': 1}
    store.docs['users/u/hourly_usage/2026-10-02-00'] = {'year': 2026, 'month': 10, 'transcription_seconds': 100}
    result = units.get_usage_units('u', date, firestore_client=store)
    assert result['used_units'] == 0
    assert result['completeness']['unprojected_hourly_docs'] == 1
    with pytest.raises(ValueError):
        units.get_usage_units('u', datetime(2026, 10, 1), firestore_client=store)


def test_finops_pull_still_uses_root_counters_with_both_attribution_shapes(monkeypatch):
    from scripts.finops import pull_hourly_usage as pull

    pages = [
        {
            'document': {
                'name': 'projects/test/databases/(default)/documents/users/u/hourly_usage/2026-10-01-08',
                'fields': {
                    'id': {'stringValue': '2026-10-01-08'},
                    'transcription_seconds': {'integerValue': '82'},
                    'speech_seconds': {'integerValue': '32'},
                    'words_transcribed': {'integerValue': '5'},
                    'plan_usage.plus.transcription_seconds': {'integerValue': '70'},
                    'plan_usage': {
                        'mapValue': {
                            'fields': {
                                'plus': {'mapValue': {'fields': {'transcription_seconds': {'integerValue': '12'}}}}
                            }
                        }
                    },
                },
            }
        }
    ]
    monkeypatch.setattr(pull.fs, 'post', lambda *a, **k: pages)
    acc = {}
    assert pull.pull(2026, 10, 1, 31, acc) == {'seen': 1, 'kept': 1}
    row = next(iter(acc.values()))
    assert row[:3] == [82, 32, 5]
    assert 'plan_usage' not in str(pull.SEL)


def test_byok_search_excludes_provider_tokens_but_host_infra_is_omi_funded(units):
    event = {
        'payer': 'byok',
        'provider': 'perplexity',
        'configured_model': 'sonar-pro',
        'feature': 'web_search',
        'occurred_at': '2026-10-01T08:00:00+00:00',
        'date': '2026-10-01',
    }
    annotation, update = units.gateway_shadow(event)
    data = {}
    merge(data, update)
    features = data['shadow_v1']['hours']['08']['features']
    assert annotation['micro_units'] == 0
    assert features['web_search']['funding']['byok']['micro_units'] == 0
    assert features['web_search_tool']['funding']['omi']['micro_units'] == 1000000


def test_mixed_old_and_new_hour_and_day_documents_report_unprojected_residuals(units):
    uid = 'u'
    store = Store()
    month = datetime(2026, 10, 1, tzinfo=timezone.utc)
    hourly = {}
    merge(
        hourly,
        units.hourly_shadow(
            {'transcription_seconds': 12}, {'funding': 'omi', 'provider': 'parakeet', 'source': 'test'}
        ),
    )
    hourly.update(year=2026, month=10, transcription_seconds=82)
    store.docs['users/u/hourly_usage/2026-10-01-08'] = hourly
    _, rollup = units.gateway_shadow(
        {
            'payer': 'omi',
            'feature': 'web_search',
            'usage_status': 'not_reported',
            'occurred_at': '2026-10-01T08:00:00+00:00',
            'date': '2026-10-01',
        }
    )
    day = {}
    merge(day, rollup)
    day['attempts'] = 6
    store.docs['llm_gateway_user_days/2026-10-01_' + hashlib.sha256(uid.encode()).hexdigest()[:16]] = day
    result = units.get_usage_units(uid, month, firestore_client=store)
    completeness = result['completeness']
    assert completeness['unprojected_transcription_seconds'] == 70
    assert completeness['unprojected_hourly_docs'] == 1
    assert completeness['unprojected_gateway_attempts'] == 5
    assert type(completeness['unprojected_gateway_attempts']) is int
    assert completeness['unprojected_gateway_days'] == 1


@pytest.mark.parametrize('accepted', ['invalid', 'NaN', 'Infinity', '1e1000'])
@pytest.mark.parametrize('price_accepts', [False, True])
def test_invalid_accepted_speech_never_suppresses_legacy_hourly_write(units, monkeypatch, accepted, price_accepts):
    from database import user_usage

    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'plus')
    if price_accepts:
        # Even a price result that did not reject the quantity cannot escape the conversion boundary.
        monkeypatch.setattr(
            units, 'price_transcription', lambda *a, **k: {'micro_units': 1, 'status': 'complete', 'reasons': []}
        )
    store = Store()
    user_usage.update_hourly_usage(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        {'transcription_seconds': 5},
        firestore_client=store,
        usage_metadata={
            'funding': 'omi',
            'provider': 'parakeet',
            'source': 'test',
            'accepted_speech_seconds': accepted,
        },
    )
    assert store.writes == 1
    data = store.docs['users/u/hourly_usage/2026-10-01-00']
    assert data['transcription_seconds'] == 5
    leaf = data['shadow_v1']['features']['transcription']['funding']['omi']
    assert leaf['status_counts'] == {'missing': 1}
    assert 'shadow_pricing_failed' in leaf['reasons']
    assert 'accepted_speech_seconds' not in leaf


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('desktop_chat_realtime', 'chat'),
        ('desktop_chat_screen', 'chat'),
        ('public_shared_conversation_chat', 'chat'),
        ('file_chat_summary', 'chat'),
        ('chat_agent', 'chat'),
        ('persona_chat', 'chat'),
        ('realtime_voice', 'realtime_voice'),
        ('screen_analysis', 'screen'),
        ('web_search', 'web_search'),
        ('conv_summary', 'conversation_extraction'),
    ],
)
def test_feature_class_keeps_chat_prefixes_ahead_of_modalities(units, raw, expected):
    assert units.feature_class(raw) == expected


def test_hourly_deepgram_runtime_alias_uses_canonical_cloud_rate(units):
    data = {}
    merge(
        data,
        units.hourly_shadow(
            {'transcription_seconds': 100}, {'provider': 'dg-nova-3', 'funding': 'omi', 'source': 'listen'}
        ),
    )
    leaf = data['shadow_v1']['features']['transcription']['funding']['omi']
    assert leaf['providers'] == ['deepgram']
    assert 'provider_unknown' not in leaf['reasons']


def test_gateway_pricing_failure_preserves_attempt_and_day_writes(units, monkeypatch):
    from database import llm_gateway_accounting as ledger

    monkeypatch.setattr(ledger, 'resolve_usage_plan_id', lambda *a, **k: 'plus')

    def broken(*a, **k):
        raise ValueError('test pricing failure')

    monkeypatch.setattr(units, 'price_llm_attempt', broken)
    store = Store({'users/u': {'subscription': {'plan': 'plus'}}})
    event = {
        'attempt_id': 'pricing-failed',
        'user_uid': 'u',
        'payer': 'omi',
        'provider': 'openai',
        'configured_model': 'gpt-6-luna',
        'feature': 'desktop_chat_realtime',
        'usage_status': 'confirmed',
        'uncached_input_tokens': 100,
        'output_tokens': 10,
        'occurred_at': '2026-10-01T08:00:00+00:00',
        'date': '2026-10-01',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 100,
    }
    assert ledger.record_llm_gateway_attempt(event, firestore_client=store)
    assert store.writes == 2
    attempt = store.docs['llm_gateway_attempts/pricing-failed']
    assert attempt['estimated_cost_micro_usd'] == 100
    assert attempt['usage_units_v1']['status'] == 'missing'
    assert attempt['usage_units_v1']['reasons'] == ['shadow_pricing_failed']
    day = next(doc for path, doc in store.docs.items() if path.startswith('llm_gateway_user_days/'))
    assert day['attempts'] == 1
    assert day['shadow_v1']['hours']['08']['features']['chat']['funding']['omi']['status_counts'] == {'missing': 1}
    assert not ledger.record_llm_gateway_attempt(event, firestore_client=store)
    assert store.writes == 2


@pytest.mark.parametrize('enforce', [False, True])
def test_ladder_residuals_are_charged_conservatively_only_when_enforcing(units, monkeypatch, enforce):
    from config.rate_card import price_transcription, standard_chat_units

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(enforce).lower())
    store = Store()
    month = datetime(2026, 10, 1, tzinfo=timezone.utc)
    hourly = {}
    merge(
        hourly,
        units.hourly_shadow(
            {'transcription_seconds': 12},
            {'funding': 'omi', 'provider': 'parakeet', 'source': 'test'},
        ),
    )
    hourly.update(year=2026, month=10, transcription_seconds=82)
    store.docs['users/u/hourly_usage/2026-10-01-08'] = hourly
    store.docs['users/u/hourly_usage/2026-10-02-08'] = dict(year=2026, month=10, transcription_seconds=100)
    store.docs['llm_gateway_user_days/2026-10-01_' + hashlib.sha256(b'u').hexdigest()[:16]] = {'attempts': 2}
    entitlement = {'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 10}}
    before = repr(store.docs)
    result = units.get_usage_units('u', month, firestore_client=store, entitlements=entitlement)
    projected = hourly['shadow_v1']['features']['transcription']['funding']['omi']['micro_units']
    residual = price_transcription(170, provider='unknown', accepted=True)['micro_units']
    attempts = int(2 * standard_chat_units() * 1_000_000)
    expected = projected + (residual + attempts if enforce else 0)
    assert result['used_units'] == float(Decimal(expected) / 1_000_000)
    assert result['by_funding']['omi'] == result['used_units']
    assert result['completeness']['unprojected_transcription_seconds'] == 170
    assert result['completeness']['unprojected_gateway_attempts'] == 2
    assert ('ambiguous_priced_transcription_seconds' in result['completeness']) is enforce
    assert ('ambiguous_priced_gateway_attempts' in result['completeness']) is enforce
    assert repr(store.docs) == before and store.writes == 0
    # Legacy reads remain shadow-only with either switch setting.
    entitlement['entitlement_version'] = 'legacy'
    legacy = units.get_usage_units('u', month, firestore_client=store, entitlements=entitlement)
    assert legacy['used_units'] == float(Decimal(projected) / 1_000_000)
    assert 'ambiguous_priced_transcription_seconds' not in legacy['completeness']
    assert 'ambiguous_priced_gateway_attempts' not in legacy['completeness']


def test_ladder_missing_price_and_unknown_funding_do_not_claim_coverage(units, monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    store = Store()
    for hour, funding, status in [(1, 'omi', 'missing'), (2, 'unknown', 'missing'), (3, 'byok', 'complete')]:
        store.docs[f'users/u/hourly_usage/2026-10-01-0{hour}'] = {
            'year': 2026,
            'month': 10,
            'transcription_seconds': 60,
            'shadow_v1': {
                'features': {
                    'transcription': {
                        'funding': {
                            funding: {
                                'micro_units': 0,
                                'legacy_counter_seconds': 60,
                                'status_counts': {status: 1},
                            }
                        }
                    }
                }
            },
        }
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 10}},
    )
    assert result['completeness']['unprojected_transcription_seconds'] == 120
    assert (
        result['used_units']
        == units.price_transcription(120, provider='unknown', accepted=True)['micro_units'] / 1_000_000
    )


def test_mixed_six_events_only_reprices_the_unpriced_hundred_seconds(units, monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    hourly = dict(year=2026, month=10, transcription_seconds=600)
    for _ in range(5):
        merge(
            hourly,
            units.hourly_shadow(
                {'transcription_seconds': 100},
                {'funding': 'omi', 'provider': 'modulate', 'source': 'test', 'accepted_speech_seconds': 100},
            ),
        )
    original = units.price_transcription
    monkeypatch.setattr(units, 'price_transcription', lambda *a, **k: dict(micro_units=0, status='missing', reasons=[]))
    merge(hourly, units.hourly_shadow({'transcription_seconds': 100}, {'funding': 'omi', 'source': 'test'}))
    monkeypatch.setattr(units, 'price_transcription', original)
    store = Store({'users/u/hourly_usage/2026-10-01-08': hourly})
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 100}},
    )
    priced = hourly['shadow_v1']['features']['transcription']['funding']['omi']['micro_units']
    assert result['completeness']['unprojected_transcription_seconds'] == 100
    assert result['used_units'] == (priced + original(100, accepted=True)['micro_units']) / 1_000_000


def test_missing_gateway_annotation_with_priced_units_is_never_charged_twice(units, monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setattr(
        units, 'price_llm_attempt', lambda *args, **kwargs: dict(micro_units=123456, status='missing', reasons=[])
    )
    _, patch = units.gateway_shadow({'payer': 'omi', 'feature': 'chat_agent', 'occurred_at': 'bad'})
    day = {'attempts': 1}
    merge(day, patch)
    store = Store({'llm_gateway_user_days/2026-10-01_' + hashlib.sha256(b'u').hexdigest()[:16]: day})
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 100}},
    )
    assert result['used_units'] == 0.123456
    assert result['completeness']['unprojected_gateway_attempts'] == 0


@pytest.mark.parametrize('month,day,elapsed', [(10, 1, 1), (10, 17, 17), (11, 1, 31)])
def test_month_reader_batches_only_elapsed_days(units, monkeypatch, month, day, elapsed):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, month, day, tzinfo=timezone.utc)

    monkeypatch.setattr(units, 'datetime', Clock)
    store = Store()
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 100}},
    )
    assert store.reads == 2 * elapsed
    assert store.batch_reads == 1
    assert result['used_units'] == 0


@pytest.mark.parametrize('priced', [123456, 1_000_000_000])
@pytest.mark.parametrize('attributed', [0, 2_000_000_000])
def test_historical_mixed_priced_leaf_charges_once_at_the_conservative_max(units, monkeypatch, priced, attributed):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    leaf = {
        'micro_units': priced + attributed,
        'legacy_counter_seconds': 600 + (100 if attributed else 0),
        'status_counts': {'complete': 5, 'missing': 1},
        'quantity_attributed_seconds': 100 if attributed else 0,
        'quantity_attributed_micro_units': attributed,
    }
    hourly = {
        'year': 2026,
        'month': 10,
        'transcription_seconds': 600 + (100 if attributed else 0),
        'shadow_v1': {'features': {'transcription': {'funding': {'omi': leaf}}}},
    }
    store = Store({'users/u/hourly_usage/2026-10-01-08': hourly})
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 100}},
    )
    assert (
        result['used_units']
        == (attributed + max(priced, units.price_transcription(600, accepted=True)['micro_units'])) / 1_000_000
    )
    assert result['completeness']['unprojected_transcription_seconds'] == 0
    assert result['completeness']['ambiguous_priced_transcription_seconds'] == 600


@pytest.mark.parametrize('old_priced', [False, True])
@pytest.mark.parametrize('new_status,new_units', [('missing', 0), ('complete', 0), ('complete', 2000000)])
def test_historical_and_new_seconds_remain_disjoint(units, monkeypatch, old_priced, new_status, new_units):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    old = {
        'micro_units': 1000000 if old_priced else 0,
        'legacy_counter_seconds': 100,
        'status_counts': {'complete' if old_priced else 'missing': 1},
    }
    hourly = {
        'year': 2026,
        'month': 10,
        'transcription_seconds': 200,
        'shadow_v1': {'features': {'transcription': {'funding': {'omi': old}}}},
    }
    original = units.price_transcription
    monkeypatch.setattr(
        units,
        'price_transcription',
        lambda *a, **k: {'micro_units': new_units, 'status': new_status, 'reasons': []},
    )
    merge(hourly, units.hourly_shadow({'transcription_seconds': 100}, {'funding': 'omi', 'source': 'test'}))
    monkeypatch.setattr(units, 'price_transcription', original)
    store = Store({'users/u/hourly_usage/2026-10-01-08': hourly})
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 100}},
    )
    residual = 100 * ((not old_priced) + (new_status == 'missing'))
    expected = (1000000 if old_priced else 0) + new_units + original(residual, accepted=True)['micro_units']
    assert result['completeness']['unprojected_transcription_seconds'] == residual
    assert result['completeness']['ambiguous_priced_transcription_seconds'] == 0
    assert result['used_units'] == expected / 1_000_000


@pytest.mark.parametrize('old_priced', [False, True])
@pytest.mark.parametrize('new_status,new_units', [('missing', 0), ('complete', 0), ('complete', 2000000)])
def test_historical_and_new_gateway_attempts_remain_disjoint(units, monkeypatch, old_priced, new_status, new_units):
    from config.rate_card import standard_chat_units

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    old = {
        'micro_units': 1000000 if old_priced else 0,
        'events': 1,
        'status_counts': {'complete' if old_priced else 'missing': 1},
    }
    day = {'attempts': 2, 'shadow_v1': {'hours': {'08': {'features': {'chat': {'funding': {'omi': old}}}}}}}
    monkeypatch.setattr(
        units,
        'price_llm_attempt',
        lambda *a, **k: {'micro_units': new_units, 'status': new_status, 'reasons': []},
    )
    _, patch = units.gateway_shadow(
        {'payer': 'omi', 'feature': 'chat_agent', 'occurred_at': '2026-10-01T08:00:00Z', 'date': '2026-10-01'}
    )
    merge(day, patch)
    store = Store({'llm_gateway_user_days/2026-10-01_' + hashlib.sha256(b'u').hexdigest()[:16]: day})
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 100}},
    )
    residual = (not old_priced) + (new_status == 'missing')
    expected = (1000000 if old_priced else 0) + new_units + int(residual * standard_chat_units() * 1_000_000)
    assert result['completeness']['unprojected_gateway_attempts'] == residual
    assert type(result['completeness']['unprojected_gateway_attempts']) is int
    assert result['completeness']['ambiguous_priced_gateway_attempts'] == 0
    assert result['used_units'] == expected / 1_000_000


@pytest.mark.parametrize('priced', [123456, 2_000_000])
@pytest.mark.parametrize('attributed', [0, 20_000_000])
def test_ambiguous_gateway_historical_max_does_not_absorb_new_priced_attempts(units, monkeypatch, priced, attributed):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    leaf = {
        'micro_units': priced + attributed,
        'events': 6 + bool(attributed),
        'status_counts': {'complete': 5 + bool(attributed), 'missing': 1},
        'quantity_attributed_events': int(bool(attributed)),
        'quantity_attributed_micro_units': attributed,
    }
    day = {
        'attempts': 6 + bool(attributed),
        'shadow_v1': {'hours': {'08': {'features': {'chat': {'funding': {'omi': leaf}}}}}},
    }
    store = Store({'llm_gateway_user_days/2026-10-01_' + hashlib.sha256(b'u').hexdigest()[:16]: day})
    result = units.get_usage_units(
        'u',
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements={'entitlement_version': 'ladder_v1', 'budget': {'kind': 'units', 'value': 100}},
    )
    proxy = int(units.standard_chat_units() * 1_000_000)
    assert result['used_units'] == (attributed + max(priced, proxy)) / 1_000_000
    assert result['completeness']['unprojected_gateway_attempts'] == 0
    assert result['completeness']['ambiguous_priced_gateway_attempts'] == 1
