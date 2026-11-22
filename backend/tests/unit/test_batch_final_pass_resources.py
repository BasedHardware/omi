"""Admission, real SDK deadlines and peak decoded memory without external IO."""

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import time
import tracemalloc
from uuid import NAMESPACE_URL, uuid5

from google.api_core.exceptions import DeadlineExceeded
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import BatchGetDocumentsResponse, Document
import httpx
import pytest

from config.policy import ProjectionPolicy
from database import batch_final_pass as references, batch_pipeline_privacy as privacy
from database.batch_pipeline_store import FirestoreStore
from tests.unit.test_batch_final_pass import (  # noqa: F401
    UID,
    lane,
    prod_shaped,
    reference_store,
    retry_state,
    run_prod,
    wav,
)
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.artifacts import ProtectionContext
from tests.unit.test_batch_pipeline_artifacts import ObjectClient
from utils.conversations import final_pass_batch as batch, final_pass_pyannote as final
from utils.stt import diarization


def test_candidate_limit_precedes_all_reference_and_artifact_reads(prod_shaped, monkeypatch):
    template = prod_shaped.conversation.transcript_segments[0]
    prod_shaped.conversation.transcript_segments = [
        template.model_copy(update={'id': str(i), 'speaker_id_scope': f'final:batch:fragment-{i}'})
        for i in range(batch.MAX_UNITS + 1)
    ]
    monkeypatch.setattr(batch, 'FirestoreStore', lambda *_: pytest.fail('over-cap pass constructed a store'))
    monkeypatch.setattr(batch, 'load_reference', lambda *a, **kw: pytest.fail('over-cap reference read'))
    result = run_prod(prod_shaped)
    assert (result['outcome'], result['reason']) == ('failed_too_long', 'unit limit')
    assert not prod_shaped.gpu


def test_non_batch_scopes_do_not_consume_reference_admission(prod_shaped):
    template = prod_shaped.conversation.transcript_segments[0]
    prod_shaped.conversation.transcript_segments.extend(
        template.model_copy(update={'id': str(i), 'speaker_id_scope': f'final:batch:sync:upload-{i}'})
        for i in range(batch.MAX_UNITS + 1)
    )
    result = run_prod(prod_shaped)
    assert result['outcome'] == 'success'
    assert set(prod_shaped.reads) == {'unit-a'}
    assert all(
        s.speaker_id_scope.startswith('final:batch:sync:') for s in prod_shaped.conversation.transcript_segments[1:]
    )


def test_metadata_plan_keeps_valid_decode_and_capture_rounding_at_audio_cap(prod_shaped, monkeypatch):
    first = prod_shaped.items['unit-a']
    last = replace(first, segment_id='unit-b', capture_at=8199.00003, duration_seconds=1.10005)
    items = {'unit-a': replace(first, duration_seconds=1), 'unit-b': last}
    template = prod_shaped.conversation.transcript_segments[0]
    prod_shaped.conversation.transcript_segments.append(
        template.model_copy(update={'id': 'last', 'speaker_id_scope': 'final:batch:unit-b'})
    )
    monkeypatch.setattr(
        batch,
        'load_reference',
        lambda store, uid, unit, cid, **kw: (
            items[unit],
            'gs://fake/result#1',
            prod_shaped.binding,
            ProjectionPolicy(),
        ),
    )
    budget = ArtifactReadBudget(time.monotonic() + 180, 320 * 1024**2, 1440)
    stream = batch._units(UID, prod_shaped.conversation, budget, deadline=time.monotonic() + 600)
    # A 1-second decoded tail is within tolerance and rounds to exactly 7200s;
    # raw metadata alone overstates the end by 0.10008 seconds.
    assert stream.capacity == 7200 * 32000
    assert not prod_shaped.reads and not prod_shaped.gpu


def test_assembly_reuses_words_and_preserves_gap_overlap_and_decoded_tail():
    first = SimpleNamespace(capture_at=1000)
    second = SimpleNamespace(capture_at=1001)
    third = SimpleNamespace(capture_at=1003)
    word = {'text': 'synthetic', 'timestamp': [0.1, 0.5]}
    budget = ArtifactReadBudget(time.monotonic() + 10, 0, 0)
    check = lambda: True
    stream = batch.UnitStream(
        1000,
        5 * 32000,
        iter(
            [
                (first, b'\x01\0' * 32000, [], check),
                (second, b'\x01\0' * 16000, [], check),
                (third, b'\x02\0' * 16000, [word], check),
            ]
        ),
        budget,
    )
    pcm, words, checks = batch._assemble(stream)
    assert isinstance(pcm, memoryview) and pcm.readonly
    assert len(pcm) == 4 * 32000  # Metadata tolerance is not transmitted as silence.
    assert pcm == b'\x01\0' * 32000 + bytes(32000) + b'\x02\0' * 16000
    assert words[0] is word and word['timestamp'] == [3.1, 3.5]
    assert len(checks) == 3


def test_assembly_stops_at_deadline_before_consuming_the_next_unit(monkeypatch):
    clock = SimpleNamespace(now=100)
    monkeypatch.setattr(time, 'monotonic', lambda: clock.now)
    budget = ArtifactReadBudget(101, 0, 0)

    def units():
        yield SimpleNamespace(capture_at=0), bytes(32000), [], lambda: True
        clock.now = 102
        yield SimpleNamespace(capture_at=1), bytes(32000), [], lambda: True
        pytest.fail('decoder continued after deadline')

    with pytest.raises(ArtifactReadLimit, match='artifact read deadline'):
        batch._assemble(batch.UnitStream(0, 64000, units(), budget))


@pytest.fixture
def sdk_reference(reference_store, monkeypatch):
    """Real document/transaction SDK, synthetic GAPIC transport (no sockets)."""
    _, strict = reference_store
    clock = SimpleNamespace(now=100)
    monkeypatch.setattr(time, 'monotonic', lambda: clock.now)
    calls = []
    state = SimpleNamespace(stall=None)

    def rpc(kind, kwargs):
        assert kwargs['retry'] is None
        assert 0 < kwargs['timeout'] <= 10
        calls.append((kind, kwargs['timeout']))
        if state.stall and kind.startswith(state.stall):
            clock.now += kwargs['timeout']
            raise DeadlineExceeded('synthetic transport deadline')
        clock.now += 0.001

    def begin(**kwargs):
        rpc('begin', kwargs)
        assert kwargs['request']['options'] == {'read_only': {}}
        return SimpleNamespace(transaction=b'bounded-read-only-snapshot')

    def get(**kwargs):
        request = kwargs['request']
        assert request['transaction'] == b'bounded-read-only-snapshot'
        (name,) = request['documents']
        path = name.split('/documents/')[1]
        rpc(path, kwargs)
        data = strict.rows.get(tuple(path.split('/')))
        args = (
            {'found': Document(name=name, fields=_helpers.encode_dict(data))} if data is not None else {'missing': name}
        )
        return iter([BatchGetDocumentsResponse(**args, read_time=datetime.now(timezone.utc))])

    client = firestore.Client(project='synthetic-project', credentials=AnonymousCredentials())
    client._firestore_api_internal = SimpleNamespace(
        begin_transaction=begin, batch_get_documents=get, rollback=lambda **kw: rpc('rollback', kw)
    )
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    return SimpleNamespace(store=store, calls=calls, clock=clock, state=state)


def test_reference_sdk_bounds_all_reads_including_privacy_and_cleanup(sdk_reference, monkeypatch):
    monkeypatch.setattr(privacy, 'lever_enabled', lambda *_: False)
    budget = ArtifactReadBudget(101, 0, 0)
    reference = references.load_reference(sdk_reference.store, UID, 'unit-a', 'conversation', read_budget=budget)
    assert reference[0].segment_id == 'unit-a'
    kinds = [kind for kind, _ in sdk_reference.calls]
    assert kinds[0] == 'begin' and kinds[-1] == 'rollback'
    assert f'users/{UID}' in kinds
    assert any(kind.startswith('batch_pipeline_dev_artifacts/') for kind in kinds)
    assert all(timeout <= 1 for _, timeout in sdk_reference.calls)


@pytest.mark.parametrize('stall', ['begin', 'batch_pipeline_dev_jobs/', 'users/', 'batch_pipeline_dev_artifacts/'])
def test_in_flight_reference_rpc_cannot_outlive_remaining_deadline(sdk_reference, stall):
    sdk_reference.state.stall = stall
    budget = ArtifactReadBudget(100.25, 0, 0)
    with pytest.raises(ArtifactReadLimit, match='artifact read deadline'):
        references.load_reference(sdk_reference.store, UID, 'unit-a', 'conversation', read_budget=budget)
    assert sdk_reference.clock.now == pytest.approx(budget.deadline)
    assert sdk_reference.calls[-1][0].startswith(stall)
    assert all(timeout <= 0.25 for _, timeout in sdk_reference.calls)


def test_expired_reference_budget_issues_no_rpc(sdk_reference):
    with pytest.raises(ArtifactReadLimit, match='artifact read deadline'):
        references.load_reference(
            sdk_reference.store, UID, 'unit-a', 'conversation', read_budget=ArtifactReadBudget(99, 0, 0)
        )
    assert not sdk_reference.calls


@pytest.mark.parametrize('stall', ['none', 'before', 'after'])
def test_real_artifact_composition_bounds_pre_and_post_download_privacy(sdk_reference, lane, stall):
    client = ObjectClient()
    artifacts = create_artifact_store(sdk_reference.store, client, 'synthetic-batch-bucket', b'x' * 32)
    item = lane.items['unit-a']
    name = f"{artifacts.owner_prefix(UID)}audio/unit-a/{'a' * 32}.enc"
    sealed = artifacts._seal(item, 'audio', ProtectionContext('standard', 0), b'synthetic PCM')
    client.objects[name] = (7, sealed)
    item = replace(item, audio_uri=f'gs://synthetic-batch-bucket/{name}#7')
    # A budgeted read must not accidentally use the ordinary transaction path.
    artifacts.authorize = lambda *_: pytest.fail('unbounded artifact authorization')
    if stall == 'before':
        sdk_reference.state.stall = 'users/'
    elif stall == 'after':
        client.after_download = lambda: setattr(sdk_reference.state, 'stall', 'users/')
    budget = ArtifactReadBudget(100.25, 1024, 1)
    if stall == 'none':
        assert artifacts.fetch_audio(item, read_budget=budget) == b'synthetic PCM'
        assert [kind for kind, _ in sdk_reference.calls].count('begin') == 2
    else:
        with pytest.raises(ArtifactReadLimit, match='artifact read deadline'):
            artifacts.fetch_audio(item, read_budget=budget)
        assert sdk_reference.clock.now == pytest.approx(budget.deadline)
    assert budget.received_bytes == (0 if stall == 'before' else len(sealed))
    assert client.downloads == (0 if stall == 'before' else 1)
    assert all(timeout <= 0.25 for _, timeout in sdk_reference.calls)


def test_reference_deadline_defers_without_trying_remaining_units(prod_shaped, sdk_reference, retry_state, monkeypatch):
    sdk_reference.state.stall = 'batch_pipeline_dev_jobs/'
    template = prod_shaped.conversation.transcript_segments[0]
    prod_shaped.conversation.transcript_segments.append(
        template.model_copy(update={'id': 'second', 'speaker_id_scope': 'final:batch:unit-b'})
    )
    monkeypatch.setattr(batch, 'FirestoreStore', lambda *_: sdk_reference.store)
    monkeypatch.setattr(batch, 'load_reference', references.load_reference)
    result = run_prod(prod_shaped)
    assert (result['outcome'], result['exception_type']) == ('deferred_transient', 'DeadlineExceeded')
    assert result['failing_unit'] == 'unit-a'
    assert sum(kind.startswith('batch_pipeline_dev_jobs/') for kind, _ in sdk_reference.calls) == 1
    assert not prod_shaped.gpu


def test_http_memoryview_upload_streams_bounded_chunks_and_restarts_retry(monkeypatch):
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'https://synthetic.invalid')
    pcm = memoryview(bytearray(200000))
    received = []

    def post(url, *, content, headers, **kwargs):
        chunks = list(content)
        assert all(type(chunk) is bytes and len(chunk) <= 65536 for chunk in chunks)
        assert headers['Content-Length'] == str(len(pcm))
        received.append(b''.join(chunks))
        if len(received) == 1:
            raise httpx.ReadTimeout('synthetic timeout')
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'turns': [],
                'overlaps': [],
                'centroids': {},
                'embedding_space': 'synthetic-space',
                'version': 'synthetic',
                'provenance': {'backend': 'pyannote'},
            },
        )

    monkeypatch.setattr(diarization.httpx, 'post', post)
    diarization.HttpDiarizer('pyannote').diarize(pcm, deadline=time.monotonic() + 10)
    assert received == [pcm, pcm]


@pytest.mark.parametrize('size', [65536, 200000])
def test_http_buffer_upload_checks_deadline_between_chunks(monkeypatch, size):
    clock = SimpleNamespace(now=100)
    monkeypatch.setattr(time, 'monotonic', lambda: clock.now)
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'https://synthetic.invalid')

    def post(url, *, content, **kwargs):
        assert len(next(content)) == 65536
        clock.now = 102
        next(content)
        pytest.fail('expired upload continued')

    monkeypatch.setattr(diarization.httpx, 'post', post)
    with pytest.raises(TimeoutError):
        diarization.HttpDiarizer('pyannote').diarize(memoryview(bytearray(size)), deadline=101)


@pytest.mark.slow
def test_two_hour_maximum_reconstruction_peak_below_288_mib(prod_shaped, monkeypatch, record_property):
    """480 lazy WAVs, 21,600 words, real reconstruction/assembly/final pass.

    This measures decoded audio/word allocations, not preloaded fixture PCM or
    a fabricated low-rate substitute. GPU/Firestore transports remain synthetic.
    """
    lane = prod_shaped
    # Fix the workload independently of the implementation's limits: changing
    # the policy must not silently shrink this regression to an easier fixture.
    count, seconds = 480, 15
    assert batch.MAX_UNITS == count and batch.MAX_AUDIO_SECONDS == count * seconds
    items = {
        f'fragment-{i:03d}': replace(
            lane.items['unit-a'],
            segment_id=f'fragment-{i:03d}',
            capture_at=1000 + i * seconds,
            duration_seconds=seconds,
        )
        for i in range(count)
    }
    template = lane.conversation.transcript_segments[0]
    lane.conversation.transcript_segments = [
        template.model_copy(
            update={
                'id': str(uuid5(NAMESPACE_URL, f'batch:{unit}:0')),
                'speaker_id_scope': f'final:batch:{unit}',
                'text': ' '.join(['X'] + ['x'] * 44),
            }
        )
        for unit in items
    ]
    # Literal result schema; fixture IDs use the persisted ID contract directly,
    # never projection_segments (the implementation under test).
    payload = {
        'audio_seconds': seconds,
        'words': [{'word': 'x', 'timestamp': [i / 3, (i + 0.8) / 3]} for i in range(45)],
        'diarization': {'turns': [{'start': 0, 'end': seconds, 'speaker': 'SPEAKER_00'}]},
    }
    monkeypatch.setattr(
        batch,
        'load_reference',
        lambda store, uid, unit, cid, **kw: (items[unit], 'gs://fake/result#1', lane.binding, ProjectionPolicy()),
    )
    monkeypatch.setattr(lane.artifacts, 'load_result', lambda *a, **kw: payload)
    monkeypatch.setattr(lane.artifacts, 'fetch_audio', lambda *a, **kw: wav(bytes(round(seconds * 32000))))

    def diarize(pcm, backend, *args, **kwargs):
        lane.gpu.append(pcm)
        return backend.diarize(pcm, **kwargs).model_dump()

    uploaded = []

    def post(url, *, content, headers, **kwargs):
        size = 0
        for chunk in content:
            assert type(chunk) is bytes and len(chunk) <= 65536
            size += len(chunk)
        assert size == int(headers['Content-Length']) == 7200 * 32000
        uploaded.append(size)
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'turns': [{'start': 0, 'end': 7200, 'speaker': 'voice'}],
                'overlaps': [],
                'centroids': {'voice': {'embedding': [1.0, 0.0], 'evidence_seconds': 12}},
                'embedding_space': diarization.OMI_EMBEDDING_SPACE,
                'version': 'synthetic',
                'provenance': {'backend': 'pyannote'},
            },
        )

    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'https://synthetic.invalid')
    monkeypatch.setattr(final, 'diarize_with_speech_compaction', diarize)
    monkeypatch.setattr(diarization.httpx, 'post', post)
    tracemalloc.start()
    try:
        result = run_prod(lane)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    record_property('peak_mib', peak / 1024**2)
    assert result['outcome'] == 'success', result
    assert len(lane.gpu) == 1 and len(lane.gpu[0]) == 7200 * 32000
    assert uploaded == [7200 * 32000]
    assert peak < 288 * 1024**2, f'peak={peak / 1024 ** 2:.2f} MiB'
