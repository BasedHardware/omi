"""Contract: the delivered-share drill, Grafana rule, dashboard row and backfill agree."""

import json
from pathlib import Path

import pytest
from database.batch_pipeline_delivered_share import TARGET_SECONDS
from scripts import batch_pipeline_delivered_share_report as report
from utils.batch_pipeline import delivered_share as module

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / 'backend/charts/monitoring'
RULE_UID = 'omi-batch-delivered-share-language'
DASHBOARD = MONITORING / 'dashboards/general/omi-core-features.json'


def _rules(path):
    return {rule['uid']: rule for rule in json.loads(path.read_text())}


def test_split_and_combined_exports_carry_the_rule_identically():
    split = _rules(MONITORING / 'alerts/batch-delivered-share.json')
    combined = _rules(MONITORING / 'alert-rules.json')
    assert RULE_UID in split and split[RULE_UID] == combined[RULE_UID]


def test_rule_thresholds_match_the_sampler_constants():
    rule = _rules(MONITORING / 'alerts/batch-delivered-share.json')[RULE_UID]
    expr = rule['data'][0]['model']['expr']
    assert f'{module.BASELINE_FACTOR:g} *' in expr
    assert f'>= {module.MIN_VOLUME}' in expr
    assert 'omi_batch_pipeline_delivered_share_ratio' in expr
    assert 'omi_batch_pipeline_delivered_share_admitted_units' in expr
    assert rule['labels']['tier'] == 'agent'
    assert rule['for'] == '30m'
    assert rule['noDataState'] == 'OK'
    # The baseline is a peak, not an average: a sustained dip cannot lower it.
    assert 'max_over_time' in expr


def test_dashboard_row_names_the_signal_and_reads_the_same_metrics():
    doc = json.loads(DASHBOARD.read_text())
    row = next(panel for panel in doc['panels'] if panel.get('title') == 'Did the user get a transcript?')
    assert row['type'] == 'row'
    children = [panel for panel in doc['panels'] if panel['gridPos']['y'] > row['gridPos']['y']][:3]
    exprs = ' '.join(target['expr'] for panel in children for target in panel.get('targets', []))
    assert 'omi_batch_pipeline_delivered_share_ratio' in exprs
    assert 'omi_batch_pipeline_delivered_share_units' in exprs
    assert 'omi_batch_pipeline_delivered_share_admitted_units' in exprs


def test_delivered_at_prefers_the_receipt_then_the_latest_part():
    assert report._delivered_at(None) is None
    assert report._delivered_at({'projection_state': 'pending', 'projection': {'persisted_at': 5}}) is None
    assert report._delivered_at({'projection_state': 'completed', 'projection': {'persisted_at': 5}}) == 5
    assert (
        report._delivered_at(
            {
                'projection_state': 'completed',
                'projection_parts': {'0': {'persisted_at': 5}, '1': {'persisted_at': 9}},
            }
        )
        == 9
    )


class Snapshot:
    def __init__(self, doc_id, row):
        self.id, self._row = doc_id, row

    def to_dict(self):
        return self._row


class Query:
    def __init__(self, client):
        self.client = client

    def where(self, *args):
        return self

    def order_by(self, *args):
        return self

    def select(self, fields):
        return self

    def limit(self, value):
        return self

    def document(self, doc_id):
        return doc_id

    def stream(self, *, timeout, retry):
        return [Snapshot(row['segment_id'], row) for row in self.client.jobs]


class Client:
    def __init__(self, jobs, results):
        self.jobs, self.results = jobs, results

    def collection(self, name):
        assert name.startswith('batch_pipeline_dev_')
        return Query(self)

    def get_all(self, refs, *, field_paths, timeout, retry):
        assert field_paths == ('projection_state', 'projection.persisted_at', 'projection_parts')
        assert timeout == 10 and retry is None
        return [Snapshot(doc_id, self.results[doc_id]) for doc_id in refs]


def test_backfill_falls_back_to_the_result_receipt_for_unstamped_rows(monkeypatch):
    jobs = [
        {
            'segment_id': 'delivered',
            'enqueued_at': 1000.0,
            'projection_binding': {'language': 'ja'},
            'policy': {'stt_route': 'provider'},
        },
        {
            'segment_id': 'late',
            'enqueued_at': 1000.0,
            'projection_binding': {'language': 'ja'},
            'policy': {'stt_route': 'provider'},
        },
        {
            'segment_id': 'stamped',
            'enqueued_at': 1000.0,
            'projection_binding': {'language': 'ja'},
            'policy': {'stt_route': 'provider'},
            'delivered_in_target': True,
        },
    ]
    results = {
        'delivered': {'projection_state': 'completed', 'projection': {'persisted_at': 1000.0 + TARGET_SECONDS}},
        'late': {'projection_state': 'completed', 'projection': {'persisted_at': 1000.0 + TARGET_SECONDS + 1}},
    }
    client = Client(jobs, results)
    rows, truncated = report._historical_rows(client, 'batch_pipeline_dev', 2000.0)
    assert truncated is False
    assert {row['segment_id']: row['delivered_in_target'] for row in rows} == {
        'delivered': True,
        'late': False,
        'stamped': True,
    }


@pytest.mark.parametrize('with_baseline', [False, True])
def test_backfill_cli_reads_windows_and_reports_the_japanese_dip(monkeypatch, capsys, with_baseline):
    import sys

    from google.cloud import firestore

    client = object()
    monkeypatch.setattr(firestore, 'Client', lambda **kwargs: client)
    calls = []

    def historical_rows(actual_client, namespace, now):
        assert actual_client is client and namespace == 'batch_pipeline_prod'
        calls.append(now)
        return [
            {
                'policy': {'stt_route': 'provider'},
                'projection_binding': {'language': 'ja'},
                'delivered_in_target': now < report._epoch('2026-11-13T00:00Z'),
            }
            for _ in range(36)
        ], False

    monkeypatch.setattr(report, '_historical_rows', historical_rows)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'report',
            '--project',
            'based-hardware',
            '--from',
            '2026-11-13T00:00Z',
            '--to',
            '2026-11-13T00:15Z',
        ]
        + (['--baseline-from', '2026-11-12T00:00Z', '--baseline-to', '2026-11-12T00:15Z'] if with_baseline else []),
    )
    assert report.main() == 0
    assert calls == [report._epoch('2026-11-13T00:20Z')] + (
        [report._epoch('2026-11-12T00:20Z')] if with_baseline else []
    )
    printed = capsys.readouterr().out
    assert 'provider   ja               36          0   0.000' in printed
    if with_baseline:
        assert 'FIRING provider/ja: 0.000 vs baseline 1.000' in printed


@pytest.mark.parametrize('flag', ['--baseline-from', '--baseline-to'])
def test_backfill_cli_rejects_partial_baseline_before_reading(monkeypatch, capsys, flag):
    import sys

    monkeypatch.setattr(
        sys,
        'argv',
        [
            'report',
            '--project',
            'based-hardware',
            '--from',
            '2026-11-13T00:00Z',
            '--to',
            '2026-11-14T00:00Z',
            flag,
            '2026-11-12T00:00Z',
        ],
    )
    with pytest.raises(SystemExit) as error:
        report.main()
    assert error.value.code == 2
    assert 'must be supplied together' in capsys.readouterr().err


@pytest.mark.slow
def test_drill_shows_the_japanese_dip_and_fires_the_alarm(capsys):
    """The done-true for SCA-2117 exercised hermetically: a Japanese provider
    outage drops that language's row to zero and the baseline rule fires."""
    assert report.drill(None) == 0
    printed = capsys.readouterr().out
    assert 'provider   ja               36         36   1.000' in printed
    assert 'provider   ja               36          0   0.000' in printed
    assert 'FIRING provider/ja: 0.000 vs baseline 1.000' in printed


def test_acknowledge_stamps_the_job_it_already_reads(monkeypatch):
    """The delivery stamp lands on the job row in the acknowledge transaction."""
    from tests.unit.test_batch_pipeline_quarantine import projection_fixture

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client, store, binding = projection_fixture()
    job = client.rows[('batch_pipeline_dev_jobs', 'good')]
    job['enqueued_at'] = 900.0
    client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]['status'] = 'completed'
    client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]['result'] = {
        'failed_segments': 0,
        'total_segments': 1,
        'errors': [],
        'outcome': 'success',
    }
    store.acknowledge('good', binding, 1000.0)
    assert job['delivered_at'] == 1000.0
    assert job['delivered_in_target'] is True
    # A replay after the target keeps the first delivery and never clears it.
    store.acknowledge('good', binding, 1000.0 + TARGET_SECONDS + 1)
    assert job['delivered_at'] == 1000.0
    assert job['delivered_in_target'] is True
