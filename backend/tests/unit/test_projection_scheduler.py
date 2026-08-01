"""Ambient projection cadence and duplicate prevention."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from utils.projections import scheduler
from utils.projections.errors import NoProjectionSubject


def _install_reservation_store(monkeypatch):
    reservations: dict[str, str] = {}
    stored: dict[str, dict] = {}

    def reserve(uid, projection_id, cadence_key, attempt_token, **_kwargs):
        if projection_id in stored or projection_id in reservations:
            return False
        reservations[projection_id] = attempt_token
        return True

    def finalize(uid, projection, attempt_token, **_kwargs):
        projection_id = projection['id']
        if reservations.get(projection_id) != attempt_token:
            return False
        stored[projection_id] = projection
        return True

    monkeypatch.setattr(scheduler.projections_db, 'reserve_projection_generation', reserve)
    monkeypatch.setattr(scheduler.projections_db, 'finalize_projection_generation', finalize)
    return reservations, stored


def test_rollout_cohort_is_explicit_and_deduplicated(monkeypatch):
    monkeypatch.delenv(scheduler.PROJECTION_ENABLED_USERS_ENV, raising=False)
    assert scheduler.enabled_user_ids() == ()
    assert scheduler.should_run_job() is False

    monkeypatch.setenv(scheduler.PROJECTION_ENABLED_USERS_ENV, ' owner-a,owner-b,owner-a, ')
    assert scheduler.enabled_user_ids() == ('owner-a', 'owner-b')
    assert scheduler.should_run_job() is True


def test_daily_generation_converges_on_one_durable_projection(monkeypatch):
    _, stored = _install_reservation_store(monkeypatch)
    generated: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', lambda uid, key: True)

    def generate(uid: str, *, projection_id: str, cadence_key: str, attempt_token: str):
        generated.append((uid, projection_id, cadence_key, attempt_token))
        return {
            'id': projection_id,
            'cadence_key': cadence_key,
            'image_path': f'{uid}/{projection_id}/{attempt_token}.png',
        }

    monkeypatch.setattr(scheduler, 'generate_projection', generate)
    local_date = date(2026, 7, 28)

    assert scheduler.generate_daily_projection('owner-a', local_date) is True
    assert scheduler.generate_daily_projection('owner-a', local_date) is False
    assert len(generated) == 1
    assert len(stored) == 1
    assert generated[0][1] == scheduler.daily_projection_id('owner-a', local_date)


def test_redis_failure_falls_back_to_firestore_reservation(monkeypatch):
    _, stored = _install_reservation_store(monkeypatch)
    fallback_events: list[dict] = []

    def unavailable(_uid: str, _key: str):
        raise ConnectionError('redis unavailable')

    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', unavailable)
    monkeypatch.setattr(scheduler, 'record_fallback', lambda **kwargs: fallback_events.append(kwargs))
    monkeypatch.setattr(
        scheduler,
        'generate_projection',
        lambda uid, *, projection_id, cadence_key, attempt_token: {
            'id': projection_id,
            'cadence_key': cadence_key,
            'image_path': f'{uid}/{projection_id}/{attempt_token}.png',
        },
    )

    local_date = date(2026, 7, 28)
    assert scheduler.generate_daily_projection('owner-a', local_date) is True
    assert scheduler.generate_daily_projection('owner-a', local_date) is False
    assert list(stored) == [scheduler.daily_projection_id('owner-a', local_date)]
    assert [
        {key: event[key] for key in ('component', 'from_mode', 'to_mode', 'reason', 'outcome')}
        for event in fallback_events
    ] == [
        {
            'component': 'projections',
            'from_mode': 'redis_lease',
            'to_mode': 'firestore_reservation',
            'reason': 'provider_unavailable',
            'outcome': 'degraded',
        },
        {
            'component': 'projections',
            'from_mode': 'redis_lease',
            'to_mode': 'firestore_reservation',
            'reason': 'provider_unavailable',
            'outcome': 'degraded',
        },
    ]


def test_no_grounded_subject_is_a_normal_scheduled_skip(monkeypatch):
    _, persisted = _install_reservation_store(monkeypatch)
    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', lambda uid, key: True)
    monkeypatch.setattr(
        scheduler,
        'generate_projection',
        lambda uid, *, projection_id, cadence_key, attempt_token: (_ for _ in ()).throw(
            NoProjectionSubject('no evidence')
        ),
    )

    assert scheduler.generate_daily_projection('owner-a', date(2026, 7, 28)) is False
    assert persisted == {}


def test_transient_failure_releases_redis_lease_for_job_retry(monkeypatch):
    released: list[tuple[str, str]] = []
    _install_reservation_store(monkeypatch)
    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', lambda uid, key: True)
    monkeypatch.setattr(
        scheduler.redis_db,
        'release_projection_generation_lock',
        lambda uid, key: released.append((uid, key)),
    )
    monkeypatch.setattr(
        scheduler,
        'generate_projection',
        lambda uid, *, projection_id, cadence_key, attempt_token: (_ for _ in ()).throw(
            TimeoutError('gateway timeout')
        ),
    )

    with pytest.raises(TimeoutError, match='gateway timeout'):
        scheduler.generate_daily_projection('owner-a', date(2026, 7, 28))

    assert released == [('owner-a', '2026-07-28')]


@pytest.mark.asyncio
async def test_hourly_cron_runs_users_at_or_after_the_owned_local_hour(monkeypatch):
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)
    monkeypatch.setenv(scheduler.PROJECTION_ENABLED_USERS_ENV, 'owner-central,owner-hawaii,owner-invalid')
    time_zones = {
        'owner-central': 'America/Chicago',
        'owner-hawaii': 'Pacific/Honolulu',
        'owner-invalid': 'Not/AZone',
    }
    calls: list[tuple[str, date]] = []

    async def direct_run(_executor, function, *args):
        return function(*args)

    monkeypatch.setattr(scheduler, 'run_blocking', direct_run)
    monkeypatch.setattr(scheduler.notifications_db, 'get_user_time_zone', lambda uid: time_zones[uid])
    monkeypatch.setattr(
        scheduler,
        'generate_daily_projection',
        lambda uid, local_date: calls.append((uid, local_date)) or True,
    )

    result = await scheduler.start_cron_job(now=datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc))

    assert calls == [('owner-central', date(2026, 7, 28))]
    assert result == scheduler.ProjectionCronResult(eligible=1, generated=1, skipped=0, errors=0)


@pytest.mark.asyncio
async def test_hosted_ambient_generation_refuses_local_disk_fallback(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'notifications-job')
    monkeypatch.setattr(scheduler, 'uses_gcs', lambda: False)

    with pytest.raises(RuntimeError, match='BUCKET_PROJECTION_IMAGES'):
        await scheduler.start_cron_job(now=datetime(2026, 7, 28, 13, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_cron_reraises_non_exception_base_exception_results(monkeypatch):
    class FatalGenerationSignal(BaseException):
        pass

    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)
    monkeypatch.setenv(scheduler.PROJECTION_ENABLED_USERS_ENV, 'owner-a')
    gather_results = iter([['UTC'], [FatalGenerationSignal('stop')]])

    async def gathered(*_awaitables, return_exceptions):
        assert return_exceptions is True
        return next(gather_results)

    monkeypatch.setattr(scheduler.asyncio, 'gather', gathered)
    monkeypatch.setattr(scheduler, 'run_blocking', lambda *_args: None)

    with pytest.raises(FatalGenerationSignal, match='stop'):
        await scheduler.start_cron_job(now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc))
