"""Dev acceptance can never send its signed-in summary to a production host."""

import pytest

from scripts.probe_dev_fleet_telemetry import payload, verify_dev_candidate
from config.fleet_telemetry import validate_summary


def test_dev_probe_uses_the_actual_dev_candidate_and_valid_schema():
    url = 'https://candidate---backend-dev.example.run.app'
    service = {'status': {'url': 'https://backend-dev.example.run.app', 'traffic': [{'url': url}]}}
    verify_dev_candidate(url, service)
    validate_summary(payload())
    for invalid in ('https://api.omi.me', 'https://backend-prod.example.run.app', url + '/other', url + '?x=y'):
        with pytest.raises(ValueError):
            verify_dev_candidate(invalid, service)
