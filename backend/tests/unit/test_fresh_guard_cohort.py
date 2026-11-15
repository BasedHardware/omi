"""Acceptance counts use the stored class and the guard's inclusive commit window."""

import json

import pytest

from scripts import fresh_guard_cohort as tool
from tests.unit.test_batch_pipeline_fresh_guard import CountClient


def test_comparison_uses_stored_class_not_capture_age_or_fresh_first():
    client = CountClient(
        [
            {'fresh_capture': True, 'committed_at': 800, 'projection_state': 'pending', 'fresh_first': False},
            {'fresh_capture': True, 'committed_at': 1400, 'projection_state': 'projected'},
            {'fresh_capture': False, 'committed_at': 1000, 'projection_state': 'pending', 'fresh_first': True},
            {'committed_at': 1000, 'projection_state': 'pending', 'fresh_first': True},
            {'fresh_capture': True, 'committed_at': 1401, 'projection_state': 'pending'},
            {'fresh_capture': True, 'committed_at': 799, 'projection_state': 'pending'},
        ]
    )
    assert tool.count_cohort(client, 'dev', 2000) == {
        'sample_time': 2000,
        'window_start': 800,
        'window_end': 1400,
        'total': 2,
        'pending': 1,
        'ratio': 0.5,
    }
    assert len(client.calls) == 2


@pytest.mark.parametrize('fail_at', [None, 1, 2])
def test_cli_empty_and_failed_counts_are_unknown(monkeypatch, capsys, fail_at):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-dev')
    status = tool.main(
        ['--project', 'based-hardware-dev', '--stage', 'dev', '--sample-time', '2000'],
        client_factory=lambda **kwargs: CountClient(fail_at=fail_at),
    )
    captured = capsys.readouterr()
    assert status == (1 if fail_at else 0)
    assert json.loads(captured.err if fail_at else captured.out)['ratio'] is None


def test_cli_refuses_wrong_tier_before_constructing_client(monkeypatch):
    monkeypatch.delenv('GCP_AGENT_TIER', raising=False)

    def forbidden(**kwargs):
        pytest.fail('must not construct a client')

    assert (
        tool.main(
            ['--project', 'based-hardware', '--stage', 'prod', '--sample-time', '2000'],
            client_factory=forbidden,
        )
        == 2
    )
