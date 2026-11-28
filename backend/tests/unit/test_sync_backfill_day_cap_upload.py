"""The unlimited_v2 backfill day cap is enforced once, at upload, and never creates a server hold.

An over-cap historical upload is answered with the retryable 503 ``backfill_capacity``
before any audio is archived or a job exists, so the phone keeps the audio and retries
after the UTC day rolls. Sync segments and batch units never consult the cap.
"""

import inspect
from unittest.mock import Mock

import pytest

from tests.unit.test_sync_capture_time_skew import client, _default_skew, _filename, _post_sync  # noqa: F401
from routers import sync as router
from utils import backfill_hours_cap as day_cap
from utils.batch_pipeline import admission
from utils.sync import legacy_segment_core as pipeline  # process_segment moved out of the deleted pipeline.py
from utils.transcription_allowance import TranscriptionAllowance

DAY = 86400
UNLIMITED = TranscriptionAllowance('managed', None, 'plan_unlimited', limit_seconds=None)


@pytest.fixture
def cap(monkeypatch, client):
    """Cap on, an unlimited_v2 owner, and a settable transcribed-seconds total for the UTC day."""
    day_cap._READ_CACHE.clear()
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    monkeypatch.setenv(day_cap.HOURS_ENV, '24')
    monkeypatch.setenv('SYNC_BACKFILL_ENABLED', 'true')
    monkeypatch.setenv('SYNC_BACKFILL_MAX_AGE_SECONDS', str(60 * DAY))  # prod window
    monkeypatch.setattr(router, 'resolve_transcription_allowance', lambda *_a, **_k: UNLIMITED)
    monkeypatch.setattr(router, 'has_transcription_credits', lambda *_a, **_k: True)
    monkeypatch.setattr(router, 'retry_after_until_next_utc_day', lambda: 4321)
    state = {'plan': 'unlimited_v2', 'seconds': 0, 'reads': 0}

    def plan_for(_uid):
        state['reads'] += 1
        return state['plan']

    monkeypatch.setattr(day_cap, '_plan_for', plan_for)
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *_a, **_k: state['seconds'])
    archive = Mock(return_value=[])
    # Batch is the only admission since C9-C11; the client fixture records it here.
    job = router.accept_batch_upload.calls
    monkeypatch.setattr(router, 'archive_mobile_batch_raw_files', archive)
    state.update(archive=archive, job=job)
    yield state
    day_cap._READ_CACHE.clear()


def test_over_cap_unlimited_backfill_upload_is_deferred_to_next_utc_day_without_consuming(client, cap):
    cap['seconds'] = 24 * 3600
    response = _post_sync(client, _filename(-45 * DAY))
    assert response.status_code == 503, response.text
    assert response.headers['Retry-After'] == '4321'
    assert response.headers['X-Omi-Rate-Limit-Reason'] == 'backfill_capacity'
    assert response.json()['code'] == 'backfill_capacity'
    cap['archive'].assert_not_called()
    cap['job'].assert_not_called()


def test_under_cap_unlimited_backfill_upload_is_admitted(client, cap):
    cap['seconds'] = 24 * 3600 - 60
    response = _post_sync(client, _filename(-45 * DAY))
    assert response.status_code == 202, response.text


@pytest.mark.parametrize('plan', ['basic', 'unlimited', 'operator', 'architect'])
def test_other_plans_are_never_deferred(client, cap, plan):
    cap['plan'] = plan
    cap['seconds'] = 100 * 3600
    response = _post_sync(client, _filename(-45 * DAY))
    assert response.status_code == 202, response.text


def test_exempt_allowances_are_never_deferred(client, cap, monkeypatch):
    byok = TranscriptionAllowance('managed', None, 'byok', limit_seconds=None)
    monkeypatch.setattr(router, 'resolve_transcription_allowance', lambda *_a, **_k: byok)
    cap['seconds'] = 100 * 3600
    response = _post_sync(client, _filename(-45 * DAY))
    assert response.status_code == 202, response.text


def test_cap_off_never_reads_plan_or_meter(client, cap, monkeypatch):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'false')
    cap['seconds'] = 100 * 3600
    response = _post_sync(client, _filename(-45 * DAY))
    assert response.status_code == 202, response.text
    assert cap['reads'] == 0


def test_non_backfill_lane_never_consults_the_cap(monkeypatch):
    seen = []
    monkeypatch.setattr(day_cap, 'refuse', lambda *a, **k: seen.append(k) or a[1])
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    assert not router._backfill_day_cap_defers('uid', router.SyncLane.FRESH, None, UNLIMITED)
    assert not router._backfill_day_cap_defers('uid', router.SyncLane.BACKFILL, 'repair-job', UNLIMITED)
    assert seen == []


def test_sync_segments_never_consult_the_cap():
    # The only sync-plane bound is upload admission: process_segment must not ask the
    # day cap, so it can never park admitted audio in an unrecoverable cap hold.
    source = inspect.getsource(pipeline.process_segment)
    assert 'backfill_hours_cap' not in source
    assert 'backfill=' not in source


def test_batch_units_never_consult_the_cap(monkeypatch):
    seen = {}

    def fake_sync_admission(uid, seconds, provider, *, lane, path, backfill=False):
        seen.update(backfill=backfill)
        return True, 'entitled'

    monkeypatch.setattr(admission, 'sync_admission', fake_sync_admission)
    admission.batch_admission({'owner_id': 'uid', 'policy': {}}, 30, 'parakeet', path=admission.DispatchPath.BATCH_GPU)
    assert seen == {'backfill': False}
    assert 'backfill_hours_cap' not in inspect.getsource(admission)
