"""A whole-content retry must not reprocess already projected siblings."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from database.batch_pipeline_artifact_missing import ArtifactMissingStore
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_staging import artifact_id
from database import sync_ledger
from tests.unit.test_batch_pipeline_artifact_missing import mark
from tests.unit.test_batch_pipeline_quarantine_recovery import setup, row, ledger_row, PARTIAL_ACCOUNTING
from utils.sync.content_id import compute_sync_segment_id
from utils.batch_pipeline.audio import audio_unit, read_context
from utils.stt import batch_language
from utils.stt.batch_language import LanguageDecision
from utils.batch_pipeline.repair_lineage import LINEAGE_KEYS, lineage_record, recorded_lineage

ORIGINAL_LANGUAGE = {
    'stt_language': 'en',
    'stt_language_evidence': 'audio_lid',
    'stt_language_confidence': 0.97,
    'stt_language_probe_seconds': 12.0,
}
ORIGINAL_LINEAGE = {
    'recording_session_id': 'original',
    'audio_start_seconds': 100.0,
    'audio_end_seconds': 160.0,
    'geolocation': {'latitude': 1.5, 'longitude': 2.5},
    'capture_evidence_claims': {'a.bin': [[0, 1], [2, 3]]},
}
# A legitimate retry: the router's skew offset shrank, so both bounds moved (Luna r2).
RETRY_LINEAGE = {**ORIGINAL_LINEAGE, 'audio_start_seconds': 104.0, 'audio_end_seconds': 164.0}


def test_batch_checkpoint_is_not_a_legacy_reupload_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'synthetic-content-secret')
    audio = tmp_path / 'audio_1000_pcm16.wav'
    audio.write_bytes(b'synthetic original bytes')
    batch_segment = hashlib.sha256(b'content:0').hexdigest()
    legacy_segment = compute_sync_segment_id('synthetic-owner', str(audio))
    existing = {
        'status': 'processing',
        'job_id': 'retry',
        'ledger_run_token': 'token',
        'ledger_run_epoch': 1,
        'processed_segment_ids': [batch_segment],
    }
    snapshot = SimpleNamespace(exists=True, to_dict=lambda: deepcopy(existing))
    ref = SimpleNamespace(get=lambda transaction=None: snapshot)
    writes = []
    transaction = SimpleNamespace(set=lambda *a, **kw: writes.append(a))
    outcome = sync_ledger._checkpoint_and_mark_transaction.to_wrap(
        transaction, ref, 'retry', {}, legacy_segment, datetime.now(timezone.utc), 'token', 1
    )
    # Characterization: reopening the ledger as legacy really marks this as NEW.
    # It therefore cannot serve as the recovery implementation's dedupe proof.
    assert legacy_segment != batch_segment and outcome == sync_ledger.SEGMENT_MARKED


def staged(client, binding, uri):
    client.rows[('batch_pipeline_prod_artifacts', artifact_id('bad', uri))] = {
        'owner_id': binding.owner_id,
        'privacy_generation': binding.privacy_generation,
        'segment_id': 'bad',
        'kind': 'audio',
        'uri': uri,
    }


def test_reupload_reclaims_only_missing_span_without_resetting_siblings_or_paid_intent(setup, monkeypatch):
    from database import batch_pipeline_store

    # StrictFirestore covers write ordering; service-frontier aggregation is
    # exercised by the real-emulator restore/queue/projection integration test.
    monkeypatch.setattr(batch_pipeline_store, 'service_frontier', lambda *a, **kw: 0.0)
    row(setup[0])['recovery'] = {
        'token': 'synthetic-spent-once',
        'epoch': 1,
        'privacy_generation': 0,
        'started_at': 50,
        'settled_at': 60,
        'failure': {'reason': 'provider_failed'},
    }
    client, store, binding, _ = mark(setup)
    projection = ProjectionStore(store)
    projection.complete_partial(binding, 102, PARTIAL_ACCOUNTING)
    ledger_row(client, binding)['processed_segment_ids'] = ['good']
    snapshot = deepcopy(row(client))
    good = deepcopy(row(client, 'jobs', 'good'))
    receipt = deepcopy(row(client, 'results', 'good'))
    uri = 'gs://synthetic/restored#8'
    staged(client, binding, uri)
    assert (
        ArtifactMissingStore(store).restore_reupload(
            binding.owner_id, binding.content_id, {'bad': snapshot}, {'bad': uri}, 103
        )
        == binding.job_id
    )
    actual = {
        'queued_units': [sid for sid in binding.segment_ids if row(client, sid=sid).get('state') == 'ready'],
        'unchanged_projected_job': row(client, 'jobs', 'good') == good,
        'unchanged_projection_receipt': row(client, 'results', 'good') == receipt,
        'processed_segment_ids': ledger_row(client, binding)['processed_segment_ids'],
        'same_job_owner': ledger_row(client, binding)['job_id'] == binding.job_id,
        'ledger_status': ledger_row(client, binding)['status'],
        'charged_seconds': ledger_row(client, binding)['usage_committed_seconds'],
        'disposition': row(client)['artifact_disposition']['state'],
        'old_paid_intent_unchanged': row(client).get('recovery') == snapshot.get('recovery'),
        'job_complete': row(client).get('client_status') == 'completed',
    }
    expected = json.loads((Path(__file__).parents[1] / 'fixtures/artifact_missing_reupload.json').read_text())
    assert actual == expected
    assert row(client)['audio_uri'] == uri and row(client)['merge_pending'] is True
    setup[3].fetch_audio.assert_not_called()
    setup[4].assert_not_called()


@pytest.mark.parametrize('change', ['owner', 'content', 'snapshot', 'unregistered', 'result', 'open_intent'])
def test_reupload_never_reclaims_other_content_or_changed_work(setup, change):
    client, store, binding, _ = mark(setup)
    snapshot = deepcopy(row(client))
    uri = 'gs://synthetic/restored#8'
    staged(client, binding, uri)
    owner, content = binding.owner_id, binding.content_id
    if change == 'owner':
        owner = 'different-owner'
    elif change == 'content':
        content = 'different-content'
    elif change == 'snapshot':
        row(client)['attempt'] = 99
    elif change == 'unregistered':
        client.rows.pop(('batch_pipeline_prod_artifacts', artifact_id('bad', uri)))
    elif change == 'result':
        client.rows[('batch_pipeline_prod_results', 'bad')] = {'projection': {'state': 'ready'}}
    else:
        row(client)['terminal_disposition'] = {'state': 'prepared'}
        snapshot = deepcopy(row(client))
    before = deepcopy(client.rows)
    with pytest.raises(ProjectionBlocked):
        ArtifactMissingStore(store).restore_reupload(owner, content, {'bad': snapshot}, {'bad': uri}, 103)
    assert client.rows == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'change',
    ['none', 'retry_lineage_moved', 'boundary', 'extra_unit', 'foreign_device', 'open_intent', 'no_language', 'legacy'],
)
async def test_whole_upload_repairs_only_absent_unit_then_replays_without_staging(setup, monkeypatch, change):
    from database import batch_pipeline_store
    from utils.batch_pipeline import intake
    from tests.unit.test_batch_pipeline_intake import upload_arguments

    client, store, binding, _ = mark(setup)
    # The admission record a repair reads its original lineage and language from.
    if change != 'legacy':
        intake_key = ('batch_pipeline_prod_intakes', binding.job_id)
        client.rows[intake_key] = {
            **client.rows.get(intake_key, {}),
            'repair_lineage': lineage_record(ORIGINAL_LINEAGE),
            'repair_languages': {} if change == 'no_language' else {'bad': ORIGINAL_LANGUAGE},
        }
    ProjectionStore(store).complete_partial(binding, 102, PARTIAL_ACCOUNTING)
    monkeypatch.setattr(batch_pipeline_store, 'service_frontier', lambda *a, **kw: 0.0)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'prod')
    probes, staged_ids, contexts = [], [], []

    def classify(language, wav, **kwargs):
        probes.append(wav)
        return LanguageDecision('en', 1.0, 'explicit')

    def stage(item, body):
        staged_ids.append(item.segment_id)
        contexts.append(read_context(body))
        uri = 'gs://synthetic/restored#8'
        staged(client, binding, uri)
        return uri

    artifacts = SimpleNamespace(stage_audio=stage)
    monkeypatch.setattr(intake, 'artifacts_for', lambda store: artifacts)
    monkeypatch.setattr(batch_language, 'resolve_language', classify)
    units = [audio_unit(1, b'\0\0' * (5 * 16000)), audio_unit(10, b'\0\0' * (5 * 16000))]
    if change == 'boundary':
        units[0] = audio_unit(2, b'\0\0' * (5 * 16000))
    if change == 'extra_unit':
        units.append(audio_unit(20, b'\0\0' * 16000))
    if change == 'open_intent':
        row(client)['terminal_disposition'] = {'state': 'prepared'}
    arguments = {
        **upload_arguments(),
        'client_platform': binding.client_platform,
        'client_device_id': 'foreign-device' if change == 'foreign_device' else binding.client_device_id,
        # The router re-normalizes clock bounds against the current server time on every retry.
        'intake_context': RETRY_LINEAGE if change == 'retry_lineage_moved' else ORIGINAL_LINEAGE,
    }
    before_good = deepcopy(row(client, 'jobs', 'good'))
    response = await intake.accept_upload(**arguments, decode=lambda ceiling: iter(units))
    if change not in {'none', 'retry_lineage_moved'}:
        assert response.status_code == 503
        assert row(client)['state'] == 'quarantined' and row(client)['artifact_disposition']['state'] == 'missing'
        assert row(client, 'jobs', 'good') == before_good
        assert not probes
        if change in {'no_language', 'legacy'}:
            assert not staged_ids  # evidence holds before any decode or staging
        return
    assert response.status_code == 202
    body = json.loads(response.body)
    assert body['job_id'] == binding.job_id and body['status'] == 'processing'
    # Repair replays the original language decision; it never probes (paid or self).
    assert staged_ids == ['bad'] and not probes
    assert contexts[0]['job_id'] == binding.job_id and contexts[0]['segment_id'] == 'bad'
    assert {key: contexts[0][key] for key in ORIGINAL_LANGUAGE} == ORIGINAL_LANGUAGE
    # Restaged with the lineage frozen at admission, never the retried request's.
    assert {key: contexts[0][key] for key in LINEAGE_KEYS} == ORIGINAL_LINEAGE
    assert row(client, 'jobs', 'good') == before_good
    assert 'artifact_missing_units' not in ledger_row(client, binding)

    def no_decode(ceiling):
        raise AssertionError('a replay must not decode or stage another copy')

    replay = await intake.accept_upload(**arguments, decode=no_decode)
    assert replay.status_code == 202 and json.loads(replay.body)['job_id'] == binding.job_id
    assert staged_ids == ['bad'] and not probes


def evidence_store(intake):
    tx = SimpleNamespace(get=lambda table, key: deepcopy(intake) if (table, key) == ('intakes', 'job') else None)
    return SimpleNamespace(run=lambda read: read(tx))


BINDING = SimpleNamespace(job_id='job')


def held_reason(store, context):
    from utils.batch_pipeline.artifact_reupload import _repair_evidence

    with pytest.raises(ProjectionBlocked) as error:
        _repair_evidence(store, BINDING, {'bad': {}}, context)
    return error.value.block_reason


def test_repair_restages_the_recorded_lineage_and_language_whatever_the_retry_sends():
    from utils.batch_pipeline.artifact_reupload import _repair_evidence

    intake = {'repair_lineage': lineage_record(ORIGINAL_LINEAGE), 'repair_languages': {'bad': ORIGINAL_LANGUAGE}}
    store = evidence_store(intake)
    for retried in (
        ORIGINAL_LINEAGE,
        RETRY_LINEAGE,
        {k: v for k, v in ORIGINAL_LINEAGE.items() if k != 'recording_session_id'},
        {**ORIGINAL_LINEAGE, 'capture_evidence_claims': None},
        None,
    ):
        context, languages = _repair_evidence(store, BINDING, {'bad': {}}, {**(retried or {}), 'filenames': ['a.bin']})
        assert context == {**ORIGINAL_LINEAGE, 'filenames': ['a.bin']}
        assert languages == {'bad': ORIGINAL_LANGUAGE}
    for proofs in ({}, {'bad': None}, {'bad': {'stt_language': None}}):
        assert held_reason(evidence_store({**intake, 'repair_languages': proofs}), None) == 'language_unproven'
    for record in ('not json', '[]', '{"recording_session_id": "x"}', 7):
        assert held_reason(evidence_store({**intake, 'repair_lineage': record}), None) == 'lineage_unreadable'


def test_recorded_lineage_survives_nested_claim_arrays_as_one_string():
    # Firestore rejects arrays of arrays; the record is a single canonical JSON string.
    record = lineage_record(ORIGINAL_LINEAGE)
    assert isinstance(record, str) and recorded_lineage(record) == ORIGINAL_LINEAGE


def test_recorded_lineage_expires_with_the_intake_receipt_and_never_mirrors():
    # It lives on the intake document, so the receipt TTL deletes it; the Postgres mirror, which no TTL
    # reaches, never holds a copy (lead ebf868, Luna r3).
    from database.jobstore.dual_store import UNMIRRORED_FIELDS

    policy = json.loads(
        (Path(__file__).resolve().parents[2] / 'deploy' / 'batch-pipeline' / 'retention.json').read_text()
    )
    assert policy['field'] == 'expires_at'
    assert {'batch_pipeline_prod_intakes', 'batch_pipeline_dev_intakes'} <= set(policy['collection_groups'])
    assert 'repair_lineage' in UNMIRRORED_FIELDS


@pytest.mark.parametrize('intake', [None, {}, {'repair_languages': {'bad': ORIGINAL_LANGUAGE}}])
def test_legacy_intake_without_recorded_lineage_always_holds(intake):
    # The original context lived only in the missing artifact; nothing durable records it.
    for context in (ORIGINAL_LINEAGE, None):
        assert held_reason(evidence_store(intake), context) == 'legacy_lineage_unproven'


@pytest.mark.parametrize('capable', [False, True])
def test_only_capable_clients_receive_terminal_missing_retry(setup, monkeypatch, capable):
    from utils.batch_pipeline import intake

    client, store, binding, _ = mark(setup)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'prod')
    status = intake.get_durable_job_status(binding.job_id, binding.owner_id, artifact_retry=capable)
    assert status['status'] == ('failed' if capable else 'processing')
    assert status['reason_code'] == 'batch_artifact_missing'
    assert status['poll_after_ms'] == (0 if capable else 300000)


@pytest.mark.asyncio
async def test_repair_job_identity_cannot_admit_changed_content(setup, monkeypatch):
    from utils.batch_pipeline import intake
    from tests.unit.test_batch_pipeline_intake import upload_arguments

    client, store, binding, _ = mark(setup)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'prod')
    before = deepcopy(client.rows)
    response = await intake.accept_upload(
        **{**upload_arguments(), 'content_id': 'changed-content'}, repair_job_id=binding.job_id
    )
    assert response.status_code == 409
    assert json.loads(response.body)['code'] == 'sync_repair_bundle_changed'
    assert client.rows == before
