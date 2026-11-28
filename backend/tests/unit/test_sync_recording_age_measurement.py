"""Refused recording ages are measured without admitting or consuming audio."""

from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families

from tests.unit.test_sync_capture_time_skew import client, _default_skew, _filename, _post_sync  # noqa: F401
from routers import sync as router


@pytest.mark.parametrize('days', [31, 45, 61])
def test_refused_age_is_observed_before_return_without_storage_or_jobs(client, monkeypatch, days):
    monkeypatch.setenv('SYNC_BACKFILL_ENABLED', 'true')
    monkeypatch.delenv('SYNC_BACKFILL_MAX_AGE_SECONDS', raising=False)
    age = router.OMI_SYNC_RECORDING_AGE_SECONDS.labels(lane='backfill')
    before = age._sum.get()
    archive = Mock(side_effect=AssertionError('refused audio must not be archived'))
    job = Mock(side_effect=AssertionError('refused audio must not be admitted'))
    monkeypatch.setattr(router, 'archive_mobile_batch_raw_files', archive)
    monkeypatch.setattr(router, 'accept_batch_upload', job)
    response = _post_sync(client, _filename(-days * 86400))
    assert response.status_code == 422, response.text
    assert response.json()['code'] == 'backfill_lookback_exceeded'
    assert abs(age._sum.get() - before - days * 86400) < 5
    archive.assert_not_called()
    job.assert_not_called()


def test_sixty_day_bucket_exports_with_existing_lane_labels():
    age = router.OMI_SYNC_RECORDING_AGE_SECONDS.labels(lane='backfill')
    registry = CollectorRegistry()
    registry.register(router.OMI_SYNC_RECORDING_AGE_SECONDS)

    def bucket_count():
        wire = generate_latest(registry).decode()
        return next(
            sample.value
            for family in text_string_to_metric_families(wire)
            for sample in family.samples
            if sample.name == 'omi_sync_recording_age_seconds_bucket'
            and sample.labels.get('lane') == 'backfill'
            and float(sample.labels['le']) == 5184000
        )

    before = bucket_count()
    age.observe(45 * 86400)
    assert bucket_count() == before + 1
