from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import pytest
from tests.unit.fixtures.shadow_usage_firestore import Store, merge


@pytest.fixture(scope='module')
def units():
    from database import usage_units

    return usage_units


def test_normalize_old_and_new_attribution_without_mutating_history(units):
    old = {
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


def test_read_joins_hourly_and_gateway_rollups_without_attempt_scan(units):
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
    assert store.writes == 0 and store.reads == 33
    planned = units.get_usage_units(
        uid,
        month,
        firestore_client=store,
        entitlements={'budget': {'kind': 'rate_card_mix'}, 'entitlement_version': 'ladder_v1'},
    )
    assert planned['budget_units'] == 217


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
    event = {
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
    result = units.get_usage_units('u', datetime(2026, 10, 1, tzinfo=timezone.utc), firestore_client=store)
    assert result['used_units'] == 1.059799
    event.update(attempt_id='byok', payer='byok', estimated_cost_micro_usd=None, cost_status='not_omi_cost')
    assert ledger.record_llm_gateway_attempt(event, firestore_client=store)
    assert store.writes == 4
    result = units.get_usage_units('u', datetime(2026, 10, 1, tzinfo=timezone.utc), firestore_client=store)
    assert result['used_units'] == 1.059799
    assert result['by_funding']['byok'] == 0


def test_sync_marker_and_nested_usage_remain_in_existing_two_write_transaction(units, monkeypatch):
    from database import user_usage

    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'plus')
    original = user_usage._update_hourly_usage_once_transaction.to_wrap

    class Transaction:
        def set(self, ref, data, merge=False):
            ref.set(data, merge=merge)

    monkeypatch.setattr(
        user_usage, '_update_hourly_usage_once_transaction', lambda tx, m, u, d: original(Transaction(), m, u, d)
    )
    store = Store()
    date = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    kwargs = {
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
    assert source.live_usage_metadata(host) == {'funding': 'omi', 'provider': 'unknown', 'source': 'listen'}


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
