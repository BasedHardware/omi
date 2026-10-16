"""Unit tests for shared hourly usage updates, plan attribution, and sanitization."""

from datetime import datetime, timedelta, timezone
import pytest
from google.cloud import firestore
from database import hourly_usage_updates


def test_prepare_hourly_usage_updates_basic():
    date = datetime(2026, 10, 16, 14, 30, tzinfo=timezone.utc)
    updates = {'transcription_seconds': 120, 'words_transcribed': 350}
    res = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, 'basic', cost_usd=0.04)

    assert res['id'] == '2026-10-16-14'
    assert res['year'] == 2026
    assert res['month'] == 10
    assert res['day'] == 16
    assert res['hour'] == 14
    assert isinstance(res['transcription_seconds'], firestore.Increment)
    assert isinstance(res['words_transcribed'], firestore.Increment)
    assert 'basic' in res['plan_usage']
    assert isinstance(res['plan_usage']['basic']['transcription_seconds'], firestore.Increment)
    assert isinstance(res['plan_usage']['basic']['cost_usd'], firestore.Increment)
    assert res['plan_usage']['basic']['_metadata']['last_cost_status'] == 'missing'


@pytest.mark.parametrize(
    ('plan_key', 'expected_key'),
    [
        ('pro.monthly', 'pro_monthly'),
        ('tier.1.v2', 'tier_1_v2'),
        ('enterprise/plus', 'enterprise_plus'),
        ('plan*test~special', 'plan_test_special'),
        ('[custom]`plan', '_custom__plan'),
        ('', '_unattributed'),
        ('   ', '_unattributed'),
        (None, '_unattributed'),
    ],
)
def test_prepare_hourly_usage_updates_sanitizes_plan_key(plan_key, expected_key):
    date = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    updates = {'transcription_seconds': 60}
    res = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, plan_key)

    assert expected_key in res['plan_usage']
    assert isinstance(res['plan_usage'][expected_key]['transcription_seconds'], firestore.Increment)
    # Ensure no broken nested hierarchy was created by dot-splitting
    if '.' in str(plan_key):
        first_segment = plan_key.split('.')[0]
        assert first_segment not in res['plan_usage'] or first_segment == expected_key


def test_prepare_hourly_usage_updates_normalizes_timezone_to_utc():
    # 20:45 in UTC+5 is 15:45 UTC
    dt_offset_pos = datetime(2026, 10, 16, 20, 45, tzinfo=timezone(timedelta(hours=5)))
    res_pos = hourly_usage_updates.prepare_hourly_usage_updates(dt_offset_pos, {'transcription_seconds': 10}, 'basic')
    assert res_pos['hour'] == 15
    assert res_pos['id'] == '2026-10-16-15'

    # 02:15 in UTC-5 on the 17th is 07:15 UTC on the 17th
    dt_offset_neg = datetime(2026, 10, 17, 2, 15, tzinfo=timezone(timedelta(hours=-5)))
    res_neg = hourly_usage_updates.prepare_hourly_usage_updates(dt_offset_neg, {'speech_seconds': 25}, 'basic')
    assert res_neg['hour'] == 7
    assert res_neg['id'] == '2026-10-17-07'


def test_prepare_hourly_usage_updates_type_guards_increments():
    date = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    # Booleans, strings, and non-positive numbers must be safely ignored
    bad_updates = {
        'transcription_seconds': True,
        'words_transcribed': '100',
        'insights_gained': -5,
        'memories_created': 0,
    }
    res = hourly_usage_updates.prepare_hourly_usage_updates(date, bad_updates, 'basic')
    assert res == {}

    # Mixed valid and invalid values: only valid positive numbers are incremented
    mixed_updates = {
        'transcription_seconds': 50,
        'words_transcribed': True,
        'insights_gained': -1,
        'speech_seconds': False,
    }
    res_mixed = hourly_usage_updates.prepare_hourly_usage_updates(date, mixed_updates, 'basic')
    assert 'transcription_seconds' in res_mixed
    assert 'words_transcribed' not in res_mixed
    assert 'insights_gained' not in res_mixed
    assert 'speech_seconds' not in res_mixed


def test_prepare_hourly_usage_updates_cost_usd_guards():
    date = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    updates = {'transcription_seconds': 30}

    # Negative cost
    res_neg = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, 'basic', cost_usd=-0.50)
    assert 'cost_usd' not in res_neg['plan_usage']['basic']

    # NaN cost
    res_nan = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, 'basic', cost_usd=float('nan'))
    assert 'cost_usd' not in res_nan['plan_usage']['basic']

    # Inf cost
    res_inf = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, 'basic', cost_usd=float('inf'))
    assert 'cost_usd' not in res_inf['plan_usage']['basic']

    # Boolean cost
    res_bool = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, 'basic', cost_usd=True)
    assert 'cost_usd' not in res_bool['plan_usage']['basic']

    # Valid zero and positive cost
    res_zero = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, 'basic', cost_usd=0.0)
    assert isinstance(res_zero['plan_usage']['basic']['cost_usd'], firestore.Increment)

    res_pos = hourly_usage_updates.prepare_hourly_usage_updates(date, updates, 'basic', cost_usd=0.075)
    assert isinstance(res_pos['plan_usage']['basic']['cost_usd'], firestore.Increment)


def test_prepare_hourly_usage_updates_cost_status_and_exclusion_sanitization():
    date = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    updates = {'transcription_seconds': 10}

    res = hourly_usage_updates.prepare_hourly_usage_updates(
        date,
        updates,
        'basic',
        cost_status='partial',
        cost_exclusion='provider.rate/exceeded*tier',
    )
    meta = res['plan_usage']['basic']['_metadata']
    assert meta['last_cost_status'] == 'partial'
    assert 'provider_rate_exceeded_tier' in meta['cost_exclusions']
    assert isinstance(meta['cost_exclusions']['provider_rate_exceeded_tier'], firestore.Increment)


def test_prepare_hourly_usage_updates_empty_returns_empty_dict():
    date = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    assert hourly_usage_updates.prepare_hourly_usage_updates(date, {}, 'basic') == {}
    assert hourly_usage_updates.prepare_hourly_usage_updates(date, {'unrelated_key': 10}, 'basic') == {}
