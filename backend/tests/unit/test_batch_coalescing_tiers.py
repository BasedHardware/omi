"""Class, capacity and mixed-version boundaries, using synthetic custody only."""

from copy import deepcopy

import pytest

from config import batch_pipeline_coalescing as config
from database import batch_coalescing_capabilities as capabilities
from database import batch_pipeline_coalescing as rows
from tests.unit.test_batch_upload_coalescing import group, member, store


def ready(s, now=10):
    release = 'a' * 40
    s.rows['coalesce_capabilities', 'roster'] = {
        'inventory_complete': True,
        'verified_at': now,
        'valid_until': now + 900,
        'reader_releases': [release],
    }
    s.rows['coalesce_capabilities', release] = {'protocol': 2, 'max_members': 16}


@pytest.mark.parametrize('entitlement', ['paid', 'trial', 'unknown', 'free'])
@pytest.mark.parametrize('backlog', [False, True])
@pytest.mark.parametrize(
    'value,expected',
    [
        (None, 60),
        ('60', 60),
        ('300', 300),
        ('900', 900),
        ('901', 900),
        ('nan', 60),
        ('inf', 60),
        ('true', 60),
        ('59', 60),
        ('', 60),
    ],
)
def test_class_windows_preserve_protected_and_unset(monkeypatch, entitlement, backlog, value, expected):
    for name in ('FREE', 'BACKLOG'):
        key = f'BATCH_PIPELINE_COALESCING_{name}_WINDOW_SECONDS'
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    assert config.window_seconds(entitlement, backlog=backlog) == (expected if entitlement == 'free' else 60)


@pytest.mark.parametrize('defect', ['missing', 'old_reader', 'expired', 'future', 'overlong', 'incomplete'])
def test_no_extended_custody_without_every_advertised_reader(defect):
    s = store()
    ready(s)
    roster = s.rows['coalesce_capabilities', 'roster']
    if defect == 'missing':
        del s.rows['coalesce_capabilities', 'roster']
    elif defect == 'old_reader':
        roster['reader_releases'].append('b' * 40)  # Old binary cannot advertise v2.
    elif defect == 'expired':
        roster.update(verified_at=-1000, valid_until=0)
    elif defect == 'future':
        roster['verified_at'] = 11
    elif defect == 'overlong':
        roster['valid_until'] = 10000
    else:
        roster['inventory_complete'] = False
    candidate = member('original', hold_seconds=300, upload_entitlement='free')
    assert rows.enqueue(s, candidate, 'key', 10) == 'bp_original'
    assert group(s)['profile'] == 'legacy'
    assert group(s)['release_by'] == 70
    for i in range(1, 4):
        assert rows.enqueue(
            s, member(str(i), start=100 + 10 * i, hold_seconds=300, upload_entitlement='free'), 'key', 10
        ) == 'bp_' + str(i)
    assert rows.enqueue(s, member('fifth', start=140, hold_seconds=300, upload_entitlement='free'), 'key', 10) == 'wait'
    assert len(group(s)['members']) == 4  # All created manifests fit old completion.


def test_long_window_does_not_slide_and_16_members_are_capture_bounded():
    s = store()
    ready(s)
    for i in range(16):
        m = member(
            str(i),
            start=100 + 37.5 * i,
            seconds=37.5,
            end=137.5 + 37.5 * i,
            hold_seconds=300,
            upload_entitlement='free',
        )
        assert rows.enqueue(s, m, 'key', 10) == 'bp_' + str(i)
    g = group(s)
    assert g['seconds'] == 600
    assert g['release_by'] == 310
    assert rows.claim(s, g['id'], 309, producer_enabled=True) is None
    sealed = rows.claim(s, g['id'], 310, producer_enabled=True)
    assert sealed['mode'] == 'merged' and len(sealed['members']) == 16


def test_capture_span_bounds_gaps_even_when_source_seconds_fit():
    s = store()
    ready(s)
    rows.enqueue(s, member('a', hold_seconds=300, upload_entitlement='free'), 'key', 10)
    assert rows.enqueue(s, member('b', start=691, hold_seconds=300, upload_entitlement='free'), 'key', 11) == 'wait'
    assert group(s)['release_by'] == 11
    assert len(group(s)['members']) == 1


def test_plan_upgrade_releases_free_predecessor_without_overtaking():
    s = store()
    ready(s)
    rows.enqueue(s, member('a', hold_seconds=300, upload_entitlement='free'), 'key', 10)
    assert rows.enqueue(s, member('b', start=120, upload_entitlement='paid'), 'key', 11) == 'wait'
    assert group(s)['release_by'] == 11
    assert ('content', 'owner/b') not in s.rows


@pytest.mark.parametrize('owner_full', [False, True])
def test_quota_exhaustion_is_exactly_legacy_fallback_not_refusal(owner_full):
    s = store()
    ready(s)
    quota = s.rows['coalesce_quota', 'global']
    quota.update(groups=64 if not owner_full else 2, owners={'owner-hash': 2} if owner_full else {})
    before = deepcopy(s.rows)
    assert rows.enqueue(s, member('a', hold_seconds=300, upload_entitlement='free'), 'key', 10) is None
    assert s.rows == before  # None enters today's per-upload admission; no 503/custody.


def test_extended_off_and_crash_resume_keep_frozen_membership():
    s = store()
    ready(s)
    for i in range(5):
        rows.enqueue(s, member(str(i), start=100 + 10 * i, hold_seconds=300, upload_entitlement='free'), 'key', 10)
    sealed = rows.claim(s, group(s)['id'], 11, producer_enabled=False)
    assert sealed['mode'] == 'individual'
    resumed = rows.claim(s, sealed['id'], sealed['lease_until'] + 1, producer_enabled=True)
    assert resumed['mode'] == 'individual'
    assert resumed['members'] == sealed['members']


def test_capability_advertisement_is_release_bound_and_never_publishes_roster(monkeypatch):
    s = store()
    capabilities._ADVERTISED.clear()
    monkeypatch.setenv('OMI_BACKEND_RELEASE_SHA', 'a' * 40)
    capabilities.advertise(s)
    assert s.rows['coalesce_capabilities', 'a' * 40] == {'protocol': 2, 'max_members': 16}
    assert ('coalesce_capabilities', 'roster') not in s.rows
