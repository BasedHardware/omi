"""Count committed donor transitions, never transaction or bridge cleanup attempts."""

from copy import deepcopy
import hashlib
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from database import conversations as db
from config.merge_before_processing import already_processed
from models.conversation_enums import ConversationSource
from tests.unit.test_sync_bridge_lifecycle import dependencies as dependencies, system as system
from tests.unit.test_sync_cross_job_assignment import chunk
from tests.unit.test_sync_live_overlap import live_row
from utils.sync import bridge
from utils.sync import assignment
from utils.conversations import lifecycle
from utils.sync import absorption_metrics as metrics


def count(**labels):
    return metrics.ABSORBED_TOTAL.labels(**labels)._value.get()


@pytest.mark.parametrize('processed', [False, True])
@pytest.mark.parametrize('pending', [False, True])
def test_absorbed_donor_counts_its_stored_pre_redirect_state_once(system, monkeypatch, processed, pending):
    # Exercise the existing rollback path too: default-on policy now preserves
    # already enriched donors. Instrumentation must observe, never bypass it.
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'false')
    store, ingest, _, _ = system
    ingest(0)
    ingest(4)
    donor = store.rows[('users', 'u', 'conversations', 'chunk-004')]
    if processed:
        donor['structured'] = {'title': 'Stored title', 'overview': 'Stored summary'}
    if pending:
        donor['sync_bridge_pending'] = {'target_id': 'live', 'expires_at': 1}
    labels = dict(source_kind='omi', pending=str(pending).lower(), processed=str(processed).lower())
    before = count(**labels)
    result, _, _ = ingest(2)
    assert store.rows[('users', 'u', 'conversations', 'chunk-004')]['sync_merged_into'] == result['id']
    assert count(**labels) == before + 1
    ingest(2)
    ingest(4)
    assert count(**labels) == before + 1
    assert metrics.OBSERVATIONS_FIELD not in result
    assert all(metrics.OBSERVATIONS_FIELD not in row for row in store.rows.values())


def test_default_policy_preserves_enriched_row_without_counting_it(system, monkeypatch):
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'true')
    store, ingest, _, _ = system
    ingest(0)
    ingest(4)
    store.rows[('users', 'u', 'conversations', 'chunk-004')]['structured'] = {'title': 'Protected notes'}
    labels = dict(source_kind='omi', pending='false', processed='true')
    before = count(**labels)
    ingest(2)
    assert not store.rows[('users', 'u', 'conversations', 'chunk-004')].get('deleted')
    assert count(**labels) == before


def test_pending_live_resolution_uses_the_same_committed_counter(system):
    store, _, _, _ = system
    store.rows[('users', 'u', 'conversations', 'live')] = live_row('completed')
    store.rows[('users', 'u', 'conversations', 'wal')] = dict(
        chunk('wal', 1002),
        data_protection_level='standard',
        sync_content_revision=1,
        sync_bridge_pending={'target_id': 'live', 'expires_at': 1},
    )
    labels = dict(source_kind='omi', pending='true', processed='false')
    before = count(**labels)
    assert bridge._finish_pending_live_bridge('u', 'wal') == 'live'
    assert count(**labels) == before + 1
    assert bridge.finish_sync_bridges('u', 'wal') == 'live'
    assert bridge.finish_sync_bridges('u', 'wal') == 'live'
    assert count(**labels) == before + 1


def test_cleanup_failure_and_retry_do_not_double_count(system):
    _, ingest, retract, _ = system
    ingest(0)
    ingest(4)
    labels = dict(source_kind='omi', pending='false', processed='false')
    before = count(**labels)
    retract.side_effect = RuntimeError('cleanup unavailable')
    with pytest.raises(RuntimeError, match='cleanup unavailable'):
        ingest(2)
    assert count(**labels) == before + 1
    retract.side_effect = None
    ingest(2)
    assert count(**labels) == before + 1


@pytest.mark.parametrize('commit_fails', [False, True])
def test_only_successful_transaction_result_emits(system, monkeypatch, commit_fails):
    store, ingest, _, _ = system
    ingest(0)
    ingest(4)
    run = db.run_sync_assignment
    labels = dict(source_kind='omi', pending='false', processed='false')
    before = count(**labels)

    def replay(client, assign, full_ids, **kwargs):
        # Model the runner's discarded body result followed by rollback/replay.
        # StrictFirestore verifies read ordering, not SDK contention semantics.
        saved = deepcopy(store.rows)
        failed_result = run(client, assign, full_ids, **kwargs)
        assert failed_result[0][metrics.OBSERVATIONS_FIELD] == [('omi', 'false', 'false')]
        assert count(**labels) == before
        store.rows.clear()
        store.rows.update(saved)
        if commit_fails:
            raise RuntimeError('commit refused')
        return run(client, assign, full_ids, **kwargs)

    monkeypatch.setattr(db, 'run_sync_assignment', replay)
    if commit_fails:
        with pytest.raises(RuntimeError, match='commit refused'):
            ingest(2)
        assert count(**labels) == before
    else:
        ingest(2)
        assert count(**labels) == before + 1


@pytest.mark.parametrize(
    'patch, expected',
    [
        ({'status': 'processing', 'structured': {'title': 'Old title'}}, 'false'),
        ({'structured': None}, 'false'),
        ({'structured': 'malformed'}, 'false'),
        ({'structured': {'overview': 'Stored summary'}}, 'true'),
        ({'structured': {'title': 'Stored title'}}, 'true'),
        ({'structured': {'title': 'Recording', 'title_provenance': 'server_minimum'}}, 'false'),
        ({'structured': {'title': 'Recording'}, 'summary_title_provenance': 'server_minimum'}, 'false'),
        ({'summary_completed_at': 1}, 'true'),
        ({'summary_output_present': True}, 'true'),
        ({'notes_llm_input_hash': 'stored-hash'}, 'true'),
        ({'notes_llm_output_hash': 'stored-hash'}, 'true'),
        ({'structured': {'action_items': [{}]}}, 'true'),
        ({'structured': {'events': [{}]}}, 'true'),
        ({'summary_output_present': False, 'structured': {'overview': 'old output'}}, 'false'),
        ({'summary_completed_at': 1, 'structured': {'title_provenance': 'server_minimum'}}, 'true'),
        ({'summary_completed_at': 1, 'status': 'processing'}, 'false'),
    ],
)
def test_processed_definition(patch, expected):
    row = {'status': 'completed', **patch}
    assert metrics.donor_labels(row) == ('other', 'false', expected)
    assert (expected == 'true') == (row['status'] == 'completed' and already_processed(row))


@pytest.mark.parametrize('extraction', ['absorption_observations', 'row_labels'])
def test_telemetry_preparation_failure_cannot_abort_absorption(system, monkeypatch, extraction):
    store, ingest, _, _ = system
    ingest(0)
    ingest(4)

    def fail(*args):
        raise ValueError('unexpected telemetry shape')

    monkeypatch.setattr(metrics, extraction, fail)
    result, created, survivors = ingest(2)
    assert not created and survivors
    assert store.rows[('users', 'u', 'conversations', 'chunk-004')]['sync_merged_into'] == result['id']
    assert len(result['transcript_segments']) == 3


def test_malformed_plan_capture_is_best_effort():
    conversation = {}
    metrics.capture_assignment_metrics(conversation, [object()])
    assert conversation == {}


@pytest.mark.parametrize('field', [metrics.OBSERVATIONS_FIELD, metrics.PUBLISHED_FIELD])
def test_malformed_emission_is_best_effort(field):
    conversation = {field: [None]}
    metrics.record_assignment_metrics(conversation)
    assert field not in conversation


@pytest.mark.parametrize('commit_fails', [False, True])
def test_committed_published_counter_includes_every_rollover_once(system, monkeypatch, commit_fails):
    store, _, _, _ = system
    # Real encoding, transactions and post-commit seam; a single intake creates
    # several rows.
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 3400)
    incoming = chunk('oversized', 1000)
    incoming.update(data_protection_level='standard', sync_bridge_pending={'expires_at': 1})
    incoming['transcript_segments'] = [
        {
            'id': f'line-{i}',
            'text': ''.join(hashlib.sha256(f'{i}:{j}'.encode()).hexdigest() for j in range(30)),
            'start': i * 10.0,
            'end': i * 10.0 + 9.5,
        }
        for i in range(6)
    ]
    incoming['finished_at'] = chunk('end', 1050)['finished_at']
    before = {
        label: metrics.PUBLISHED_TOTAL.labels(source_kind='omi', pending=label)._value.get()
        for label in metrics.BOOL_LABELS
    }
    original = deepcopy(store.rows)
    run = db.run_sync_assignment

    def replay(client, assign, full_ids, **kwargs):
        saved = deepcopy(store.rows)
        discarded, _, _ = run(client, assign, full_ids, **kwargs)
        assert len(discarded[metrics.PUBLISHED_FIELD]) > 1
        assert all(
            metrics.PUBLISHED_TOTAL.labels(source_kind='omi', pending=k)._value.get() == v for k, v in before.items()
        )
        store.rows.clear()
        store.rows.update(saved)
        if commit_fails:
            raise RuntimeError('commit refused')
        return run(client, assign, full_ids, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(db, 'run_sync_assignment', replay)
        if commit_fails:
            with pytest.raises(RuntimeError, match='commit refused'):
                lifecycle.ingest_sync_conversation('u', deepcopy(incoming))
            assert store.rows == original
            assert all(
                metrics.PUBLISHED_TOTAL.labels(source_kind='omi', pending=k)._value.get() == v
                for k, v in before.items()
            )
            return
        result, created, _ = lifecycle.ingest_sync_conversation('u', deepcopy(incoming))
    assert created
    rows = [row for path, row in store.rows.items() if path[2] == 'conversations' and path not in original]
    assert len(rows) > 1
    for label, value in before.items():
        expected = sum(str(bool(row.get('sync_bridge_pending'))).lower() == label for row in rows)
        assert metrics.PUBLISHED_TOTAL.labels(source_kind='omi', pending=label)._value.get() == value + expected
    after = {k: metrics.PUBLISHED_TOTAL.labels(source_kind='omi', pending=k)._value.get() for k in before}
    lifecycle.ingest_sync_conversation('u', deepcopy(incoming))
    metrics.record_assignment_metrics(result)
    assert all(metrics.PUBLISHED_TOTAL.labels(source_kind='omi', pending=k)._value.get() == v for k, v in after.items())
    assert all(metrics.PUBLISHED_FIELD not in row for row in store.rows.values())


def test_published_observations_include_created_rollovers_when_primary_is_merged():
    def plan(cid, created, **row):
        return SimpleNamespace(canonical=cid, created=created, result=row, donor_updates={})

    primary = plan('existing', False, source='phone')
    first = plan('rollover-1', True, source='desktop', sync_bridge_pending={'expires_at': 1})
    second = plan('rollover-2', True, source='unbounded-private-source')
    conversation = {}
    metrics.capture_assignment_metrics(conversation, [primary, first, second, first])
    assert conversation == {metrics.PUBLISHED_FIELD: [('desktop', 'true'), ('other', 'false')]}
    before = [metrics.PUBLISHED_TOTAL.labels(*labels)._value.get() for labels in conversation[metrics.PUBLISHED_FIELD]]
    metrics.record_assignment_metrics(conversation)
    metrics.record_assignment_metrics(conversation)
    assert metrics.PUBLISHED_TOTAL.labels('desktop', 'true')._value.get() == before[0] + 1
    assert metrics.PUBLISHED_TOTAL.labels('other', 'false')._value.get() == before[1] + 1


def test_labels_are_bounded_and_observations_exclude_ancestry_and_tombstones():
    assert metrics.donor_labels({'source': ConversationSource.omi}) == ('omi', 'false', 'false')
    row = {'source': 'private-unbounded-value', 'status': 'completed', 'id': 'never-exported'}
    plan = SimpleNamespace(
        matched={'donor': row, 'old': {**row, 'deleted': True, 'sync_merged_into': 'elsewhere'}},
        donor_updates={'donor': {}, 'old': {}},
        ancestor_updates={'ancestor': {}},
    )
    assert metrics.absorption_observations([plan, plan]) == [('other', 'false', 'false')]
    assert metrics.donor_labels({**row, 'source': {'malformed': 'never-exported'}}) == ('other', 'false', 'false')
    conversation = {
        metrics.OBSERVATIONS_FIELD: [('private-unbounded-value', 'uid', 'id')],
        metrics.PUBLISHED_FIELD: [('private-unbounded-value', 'uid')],
    }
    metrics.record_assignment_metrics(conversation)
    metrics.record_assignment_metrics(conversation)
    for counter in (metrics.ABSORBED_TOTAL, metrics.PUBLISHED_TOTAL):
        for sample in counter.collect()[0].samples:
            assert sample.labels['source_kind'] in metrics.SOURCE_KINDS
            assert sample.labels['pending'] in metrics.BOOL_LABELS
            if counter is metrics.ABSORBED_TOTAL:
                assert sample.labels['processed'] in metrics.BOOL_LABELS


def test_startup_primes_every_series_without_sync_traffic():
    script = '''
import utils.metrics
from utils.sync.absorption_metrics import ABSORBED_TOTAL, PUBLISHED_TOTAL, SOURCE_KINDS
for counter, combinations in ((ABSORBED_TOTAL, 4), (PUBLISHED_TOTAL, 2)):
    samples = [s for s in counter.collect()[0].samples if s.name.endswith('_total')]
    assert len(samples) == len(SOURCE_KINDS) * combinations
    assert all(s.value == 0 for s in samples)
'''
    subprocess.run([sys.executable, '-c', script], check=True, cwd=Path(__file__).resolve().parents[2])


@pytest.mark.parametrize('config_name', ['cloud_run_gmp_sync.yaml', 'cloud_run_gmp_sidecar.yaml'])
@pytest.mark.parametrize('metric_name', ['omi_sync_bridge_absorbed_total', 'omi_sync_published_rows_total'])
def test_cloud_run_scrape_keeps_the_counter(config_name, metric_name):
    config = yaml.safe_load((Path(__file__).resolve().parents[2] / 'deploy' / config_name).read_text())
    endpoint = config['spec']['endpoints'][0]
    labels = {'__name__': metric_name, 'component': ''}
    for rule in endpoint.get('metricRelabeling', []):
        value = ';'.join(labels.get(key, '') for key in rule['sourceLabels'])
        matches = re.fullmatch(rule['regex'], value) is not None
        assert not (rule['action'] == 'keep' and not matches)
        assert not (rule['action'] == 'drop' and matches)
