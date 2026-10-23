"""V4's persisted status rows retain their meaning through M's read adapter."""

from datetime import datetime, timezone

import pytest

from utils.daily_summary_read_contract import summary_read_payload


@pytest.mark.parametrize('status', ['no_recordings', 'not_generated', 'failed', 'pending'])
def test_created_stub_is_never_reported_as_generated(status):
    row = {'status': status, 'generated_at': None, 'created_at': datetime(2026, 10, 20, tzinfo=timezone.utc)}
    payload = summary_read_payload(row)
    assert payload['status'] == status
    assert payload['generated_at'] is None


def test_generated_timestamp_is_preserved_and_legacy_success_uses_creation_time():
    created = datetime(2026, 10, 20, tzinfo=timezone.utc)
    generated = datetime(2026, 10, 21, tzinfo=timezone.utc)
    assert summary_read_payload({'created_at': created})['generated_at'] == created
    assert (
        summary_read_payload({'status': 'generated', 'created_at': created, 'generated_at': generated})['generated_at']
        == generated
    )
    assert (
        summary_read_payload({'status': 'generated', 'created_at': created, 'generated_at': None})['generated_at']
        is None
    )
