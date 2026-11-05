"""Exercise the actual CLI entrypoint; dry-run and production refusal perform no client IO."""

import json
from unittest.mock import Mock

import pytest
from scripts import backfill_episode_log as cli
from utils.episodes.log.codec import dumps

pytestmark = pytest.mark.usefixtures('isolated_episode_capture')


def test_cli_defaults_to_dry_run_without_constructing_a_client(tmp_path, monkeypatch, capsys):
    data = tmp_path / 'synthetic.json'
    data.write_text(
        dumps([{'namespace': 'episode_segment_receipts', 'id': 'synthetic', 'data': {'ids': ['consumed']}}])
    )
    client = Mock(side_effect=AssertionError('dry run constructed a cloud client'))
    monkeypatch.setattr(cli.firestore, 'Client', client)
    assert cli.main(['--uid', 'synthetic-user', '--input', str(data)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['dry_run'] and result['written'] == 0 and result['consumed_ids'] == 1
    client.assert_not_called()


def test_cli_refuses_production_before_any_client_or_scan(monkeypatch):
    client = Mock(side_effect=AssertionError('production client constructed'))
    monkeypatch.setattr(cli.firestore, 'Client', client)
    with pytest.raises(SystemExit) as error:
        cli.main(['--uid', 'synthetic-user', '--project', 'based-hardware', '--apply'])
    assert error.value.code == 2
    client.assert_not_called()
