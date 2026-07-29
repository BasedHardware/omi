"""Ambient projection cadence and duplicate prevention."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from utils.projections import scheduler
from utils.projections.errors import NoProjectionSubject


def test_rollout_cohort_is_explicit_and_deduplicated(monkeypatch):
    monkeypatch.delenv(scheduler.PROJECTION_ENABLED_USERS_ENV, raising=False)
    assert scheduler.enabled_user_ids() == ()
    assert scheduler.should_run_job() is False

    monkeypatch.setenv(scheduler.PROJECTION_ENABLED_USERS_ENV, ' owner-a,owner-b,owner-a, ')
    assert scheduler.enabled_user_ids() == ('owner-a', 'owner-b')
    assert scheduler.should_run_job() is True


def test_daily_generation_converges_on_one_durable_projection(monkeypatch):
    stored: dict[str, dict] = {}
    generated: list[tuple[str, str, str]] = []

    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', lambda uid, key: True)
    monkeypatch.setattr(
        scheduler.projections_db, 'get_projection', lambda uid, projection_id: stored.get(projection_id)
    )
    monkeypatch.setattr(
        scheduler.projections_db,
        'create_projection',
        lambda uid, projection: stored.setdefault(projection['id'], projection),
    )

    def generate(uid: str, *, projection_id: str, cadence_key: str):
        generated.append((uid, projection_id, cadence_key))
        return {'id': projection_id, 'cadence_key': cadence_key}

    monkeypatch.setattr(scheduler, 'generate_projection', generate)
    local_date = date(2026, 7, 28)

    assert scheduler.generate_daily_projection('owner-a', local_date) is True
    assert scheduler.generate_daily_projection('owner-a', local_date) is False
    assert len(generated) == 1
    assert len(stored) == 1
    assert generated[0][1] == scheduler.daily_projection_id('owner-a', local_date)


def test_redis_failure_falls_back_to_deterministic_durable_guard(monkeypatch):
    stored: dict[str, dict] = {}

    def unavailable(_uid: str, _key: str):
        raise ConnectionError('redis unavailable')

    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', unavailable)
    monkeypatch.setattr(
        scheduler.projections_db, 'get_projection', lambda uid, projection_id: stored.get(projection_id)
    )
    monkeypatch.setattr(
        scheduler.projections_db,
        'create_projection',
        lambda uid, projection: stored.setdefault(projection['id'], projection),
    )
    monkeypatch.setattr(
        scheduler,
        'generate_projection',
        lambda uid, *, projection_id, cadence_key: {'id': projection_id, 'cadence_key': cadence_key},
    )

    local_date = date(2026, 7, 28)
    assert scheduler.generate_daily_projection('owner-a', local_date) is True
    assert scheduler.generate_daily_projection('owner-a', local_date) is False
    assert list(stored) == [scheduler.daily_projection_id('owner-a', local_date)]


def test_no_grounded_subject_is_a_normal_scheduled_skip(monkeypatch):
    persisted: list[dict] = []
    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', lambda uid, key: True)
    monkeypatch.setattr(scheduler.projections_db, 'get_projection', lambda uid, projection_id: None)
    monkeypatch.setattr(
        scheduler.projections_db,
        'create_projection',
        lambda uid, projection: persisted.append(projection),
    )
    monkeypatch.setattr(
        scheduler,
        'generate_projection',
        lambda uid, *, projection_id, cadence_key: (_ for _ in ()).throw(NoProjectionSubject('no evidence')),
    )

    assert scheduler.generate_daily_projection('owner-a', date(2026, 7, 28)) is False
    assert persisted == []


def test_transient_failure_releases_redis_lease_for_job_retry(monkeypatch):
    released: list[tuple[str, str]] = []
    monkeypatch.setattr(scheduler.redis_db, 'try_acquire_projection_generation_lock', lambda uid, key: True)
    monkeypatch.setattr(scheduler.projections_db, 'get_projection', lambda uid, projection_id: None)
    monkeypatch.setattr(
        scheduler.redis_db,
        'release_projection_generation_lock',
        lambda uid, key: released.append((uid, key)),
    )
    monkeypatch.setattr(
        scheduler,
        'generate_projection',
        lambda uid, *, projection_id, cadence_key: (_ for _ in ()).throw(TimeoutError('gateway timeout')),
    )

    with pytest.raises(TimeoutError, match='gateway timeout'):
        scheduler.generate_daily_projection('owner-a', date(2026, 7, 28))

    assert released == [('owner-a', '2026-07-28')]


@pytest.mark.asyncio
async def test_hourly_cron_only_runs_users_at_the_owned_local_hour(monkeypatch):
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)
    monkeypatch.setenv(scheduler.PROJECTION_ENABLED_USERS_ENV, 'owner-chicago,owner-lisbon,owner-invalid')
    time_zones = {
        'owner-chicago': 'America/Chicago',
        'owner-lisbon': 'Europe/Lisbon',
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

    result = await scheduler.start_cron_job(now=datetime(2026, 7, 28, 13, 0, tzinfo=timezone.utc))

    assert calls == [('owner-chicago', date(2026, 7, 28))]
    assert result == scheduler.ProjectionCronResult(eligible=1, generated=1, skipped=0, errors=0)


@pytest.mark.asyncio
async def test_hosted_ambient_generation_refuses_local_disk_fallback(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'notifications-job')
    monkeypatch.setattr(scheduler, 'uses_gcs', lambda: False)

    with pytest.raises(RuntimeError, match='BUCKET_PROJECTION_IMAGES'):
        await scheduler.start_cron_job(now=datetime(2026, 7, 28, 13, 0, tzinfo=timezone.utc))
