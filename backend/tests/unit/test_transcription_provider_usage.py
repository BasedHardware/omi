from datetime import datetime, timezone
import sys
import types
from unittest.mock import MagicMock

import pytest

_google_module = sys.modules.setdefault('google', types.ModuleType('google'))
_google_cloud_module = sys.modules.setdefault('google.cloud', types.ModuleType('google.cloud'))
_google_firestore_module = types.ModuleType('google.cloud.firestore')
_google_firestore_module.Increment = lambda value: {'__increment': value}
_google_firestore_v1_module = types.ModuleType('google.cloud.firestore_v1')
_google_firestore_v1_module.FieldFilter = lambda field, op, value: (field, op, value)
sys.modules['google.cloud.firestore'] = _google_firestore_module
sys.modules['google.cloud.firestore_v1'] = _google_firestore_v1_module
setattr(_google_module, 'cloud', _google_cloud_module)
setattr(_google_cloud_module, 'firestore', _google_firestore_module)
_mock_client_module = MagicMock()
_mock_client_module.db = MagicMock()
sys.modules['database._client'] = _mock_client_module
_prometheus_module = types.ModuleType('prometheus_client')
_metric_factory = lambda *args, **kwargs: MagicMock(labels=MagicMock(return_value=MagicMock()))
_prometheus_module.Counter = _metric_factory
_prometheus_module.Gauge = _metric_factory
_prometheus_module.Histogram = _metric_factory
_prometheus_module.generate_latest = lambda: b''
_prometheus_module.CONTENT_TYPE_LATEST = 'text/plain'
sys.modules['prometheus_client'] = _prometheus_module
_fastapi_module = types.ModuleType('fastapi')
_fastapi_module.Response = lambda content=None, media_type=None: {'content': content, 'media_type': media_type}
sys.modules['fastapi'] = _fastapi_module

from database import transcription_provider_usage as usage
from utils import metrics


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.reference = MagicMock()

    def to_dict(self):
        return self._data


class _FakeDoc:
    def __init__(self, doc_id):
        self.id = doc_id
        self.set_calls = []

    def set(self, data, merge=False):
        self.set_calls.append({'data': data, 'merge': merge})


class _FakeCollection:
    def __init__(self, name, docs):
        self.name = name
        self.docs = docs
        self.filters = []

    def document(self, doc_id):
        return self.docs.setdefault((self.name, doc_id), _FakeDoc(doc_id))

    def where(self, filter=None, *args, **kwargs):
        self.filters.append(filter)
        return self

    def stream(self):
        return iter([])


class _FakeDb:
    def __init__(self):
        self.docs = {}
        self.collections = {}
        self.batch_ref = MagicMock()

    def collection(self, name):
        return self.collections.setdefault(name, _FakeCollection(name, self.docs))

    def batch(self):
        return self.batch_ref


def _inc(value):
    return {'__increment': value}


def test_create_and_finalize_provider_run_writes_ledger_rollup_and_metrics(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(usage, 'db', fake_db)
    monkeypatch.setattr(usage.firestore, 'Increment', _inc)
    emitted = []
    monkeypatch.setattr(
        usage,
        'emit_provider_run_metrics',
        lambda **kwargs: emitted.append(kwargs),
    )

    started_at = datetime(2026, 5, 20, 23, 59, 58, tzinfo=timezone.utc)
    completed_at = datetime(2026, 5, 21, 0, 0, 3, tzinfo=timezone.utc)
    run_id = usage.create_provider_run(
        uid='user-1',
        provider='assemblyai',
        model='universal-2',
        workload='background',
        run_id='run-1',
        conversation_id='conv-1',
        artifact_refs={'provider_result': 'gs://bucket/result.json'},
        started_at=started_at,
    )
    usage.finalize_provider_run(
        run_id=run_id,
        provider='assemblyai',
        model='universal-2',
        workload='background',
        status='success',
        started_at=started_at,
        completed_at=completed_at,
        raw_audio_seconds=60.0,
        speech_active_seconds=42.0,
        billable_seconds=60.0,
        estimated_cost_usd=0.37,
        retry_count=1,
        fallback_count=0,
        transcript_segment_count=12,
        transcript_word_count=140,
        speaker_cluster_count=3,
        identified_speaker_cluster_count=2,
        identity_confidence_summary={'high': 2, 'unknown': 1},
        artifact_refs={'provider_result': 'gs://bucket/result.json'},
    )

    run_doc = fake_db.docs[(usage.RUNS_COLLECTION, 'run-1')]
    assert run_doc.set_calls[0]['merge'] is False
    assert run_doc.set_calls[0]['data']['status'] == 'started'
    assert run_doc.set_calls[0]['data']['expires_at'] is not None
    assert run_doc.set_calls[1]['merge'] is True
    finalized = run_doc.set_calls[1]['data']
    assert finalized['status'] == 'success'
    assert finalized['timing']['latency_ms'] == 5000
    assert 'transcript_text' not in finalized
    assert 'words' not in finalized

    rollup_doc = fake_db.docs[(usage.DAILY_USAGE_COLLECTION, '2026-05-21:assemblyai:universal-2:background')]
    rollup = rollup_doc.set_calls[0]['data']
    assert rollup['run_count'] == {'__increment': 1}
    assert rollup['raw_audio_seconds'] == {'__increment': 60.0}
    assert rollup['identity_confidence_counts.high'] == {'__increment': 2}
    assert emitted[0]['latency_seconds'] == 5.0
    assert emitted[0]['billable_seconds'] == 60.0


def test_rejects_transcript_text_and_chunk_payloads():
    with pytest.raises(ValueError):
        usage._reject_forbidden_payload_keys({'transcript_text': 'hello'})
    with pytest.raises(ValueError):
        usage._reject_forbidden_payload_keys({'chunks': [{'start': 0}]})
    with pytest.raises(ValueError):
        usage._reject_forbidden_payload_keys({'artifact_refs': {'transcript': 'gs://bucket/transcript.txt'}})


def test_utc_daily_bucket_and_rollup_rebuild(monkeypatch):
    fake_db = _FakeDb()
    collection = fake_db.collection(usage.RUNS_COLLECTION)
    included = _FakeSnapshot(
        {
            'provider': 'assemblyai',
            'model': 'universal-2',
            'workload': 'background',
            'status': 'success',
            'timing': {'completed_at': datetime(2026, 5, 21, 0, 1, tzinfo=timezone.utc)},
            'raw_audio_seconds': 10,
            'speech_active_seconds': 6,
            'billable_seconds': 10,
            'estimated_cost_usd': 0.1,
            'retry_count': 1,
            'fallback_count': 0,
            'transcript_segment_count': 4,
            'transcript_word_count': 40,
            'speaker_cluster_count': 2,
            'identified_speaker_cluster_count': 1,
            'identity_confidence_summary': {'high': 1},
        }
    )
    excluded = _FakeSnapshot(
        {
            'timing': {'completed_at': datetime(2026, 5, 22, 0, 1, tzinfo=timezone.utc)},
            'status': 'success',
            'raw_audio_seconds': 999,
        }
    )
    collection.stream = lambda: iter([included, excluded])
    monkeypatch.setattr(usage, 'db', fake_db)

    assert usage.utc_day_bucket(datetime(2026, 5, 21, 7, 1)) == '2026-05-21'
    assert (
        usage.daily_rollup_doc_id('2026-05-21', 'provider', 'model/v1', 'sync') == '2026-05-21:provider:model_v1:sync'
    )

    rollup = usage.rebuild_daily_rollup_from_runs('2026-05-21', 'assemblyai', 'universal-2', 'background')

    assert rollup['run_count'] == 1
    assert rollup['raw_audio_seconds'] == 10.0
    assert rollup['status_counts'] == {'success': 1}
    assert rollup['identity_confidence_counts'] == {'high': 1}


def test_purge_provider_runs_for_user_deletes_top_level_run_records(monkeypatch):
    fake_db = _FakeDb()
    collection = fake_db.collection(usage.RUNS_COLLECTION)
    docs = [_FakeSnapshot({'uid': 'user-1'}), _FakeSnapshot({'uid': 'user-1'})]
    collection.stream = lambda: iter(docs)
    monkeypatch.setattr(usage, 'db', fake_db)

    deleted = usage.purge_provider_runs_for_user('user-1')

    assert deleted == 2
    assert fake_db.batch_ref.delete.call_count == 2
    fake_db.batch_ref.commit.assert_called_once()


def test_metrics_reject_high_cardinality_labels():
    assert metrics.identity_confidence_bucket(None) == 'unknown'
    assert metrics.identity_confidence_bucket(0.91) == 'very_high'
    with pytest.raises(ValueError):
        metrics._provider_metric_labels(provider='assemblyai', user_id='user-1')
    with pytest.raises(ValueError):
        metrics._provider_metric_labels(provider='assemblyai', transcript_text='hello world')


def test_fallback_metric_records_failed_provider_to_fallback_provider(monkeypatch):
    observed = []
    monkeypatch.setattr(usage, 'observe_transcription_provider_request', lambda *args, **kwargs: None)
    monkeypatch.setattr(usage, 'observe_transcription_provider_audio_seconds', lambda *args, **kwargs: None)
    monkeypatch.setattr(usage, 'observe_transcription_provider_retry', lambda *args, **kwargs: None)
    monkeypatch.setattr(usage, 'observe_transcription_provider_speaker_clusters', lambda *args, **kwargs: None)
    monkeypatch.setattr(usage, 'observe_transcription_provider_identity_confidence', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        usage,
        'observe_transcription_provider_fallback',
        lambda *args, **kwargs: observed.append((args, kwargs)),
    )

    usage.emit_provider_run_metrics(
        provider='deepgram',
        model='nova-3',
        workload='sync',
        status='succeeded',
        latency_seconds=1.0,
        raw_audio_seconds=2.0,
        speech_active_seconds=2.0,
        billable_seconds=2.0,
        retry_count=0,
        fallback_count=1,
        speaker_cluster_count=0,
        identified_speaker_cluster_count=0,
        fallback_provider='assemblyai',
    )

    assert observed == [(('assemblyai', 'deepgram', 'sync', 'provider_failure', 1), {})]


def test_provider_metrics_source_does_not_define_forbidden_label_names():
    forbidden_labels = {
        "['provider', 'model', 'workload', 'user_id']",
        "['provider', 'model', 'workload', 'conversation_id']",
        "['provider', 'model', 'workload', 'provider_job_id']",
        "['provider', 'model', 'workload', 'transcript_text']",
    }
    source = metrics.__loader__.get_source(metrics.__name__)
    for label_list in forbidden_labels:
        assert label_list not in source
