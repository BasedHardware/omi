import json
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from config.refactor_modes import mode
from models.capture_coverage import AdmitResult, CaptureKey, FrameRange
from routers import developer_segments as intake
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


class Segment(BaseModel):
    text: str = 'synthetic'
    speaker: int
    start: int
    end: int


class Request(intake.ContinuationFields):
    client_session_id: str | None = None
    started_at: str | None = '2026-01-01T00:00:00Z'
    finished_at: str | None = '2026-01-01T01:00:00Z'
    source: str = 'desktop'
    transcript_segments: list[Segment] = Field(max_length=500)
    client_processing: dict | None = None


def chunk(index=0, count=2, **kwargs):
    return Request(
        client_session_id='session',
        chunk_index=index,
        chunk_count=count,
        transcript_segments=[Segment(speaker=index % 2, start=index, end=index + 1)],
        **kwargs
    )


@pytest.fixture
def store(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(intake.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(intake.encryption, 'encrypt', lambda value, owner: 'encrypted:' + value)
    monkeypatch.setattr(intake.encryption, 'decrypt', lambda value, owner: value.removeprefix('encrypted:'))
    monkeypatch.setattr(intake, 'get_firestore_client', lambda: client)
    return client


def test_chunks_are_durable_ordered_and_idempotent(store):
    owner = uuid4().hex
    assert intake.stage_chunk(owner, 'c', chunk(1)) is None
    assert intake.stage_chunk(owner, 'c', chunk(1)) is None
    result = intake.stage_chunk(owner, 'c', chunk(0))
    assert [segment['speaker'] for segment in result['transcript_segments']] == [0, 1]
    assert len(store.rows) == 2
    assert all(row['payload'].startswith('encrypted:') for row in store.rows.values())
    assert intake.stage_chunk(owner, 'c', chunk(0)) == result


def test_different_content_at_same_index_is_rejected(store):
    owner = uuid4().hex
    first = chunk()
    intake.stage_chunk(owner, 'c', first)
    other = first.model_copy(update={'transcript_segments': [Segment(speaker=9, start=0, end=1)]})
    with pytest.raises(HTTPException) as error:
        intake.stage_chunk(owner, 'c', other)
    assert error.value.status_code == 409


def test_metadata_cannot_change_between_continuations(store):
    owner = uuid4().hex
    intake.stage_chunk(owner, 'c', chunk())
    with pytest.raises(HTTPException):
        intake.stage_chunk(owner, 'c', chunk(1).model_copy(update={'source': 'phone'}))


def test_assembly_exceeds_wire_cap_without_merging_speakers(store, monkeypatch):
    owner = uuid4().hex
    monkeypatch.setenv(intake.CONTINUATION_FLAG_KEY, 'serve')
    calls = []
    for index in range(3):
        body = chunk(index, count=3).model_dump()
        body['transcript_segments'] = [
            Segment(speaker=i % 2, start=i, end=i + 1).model_dump()
            for i in range(index * 500, min((index + 1) * 500, 1100))
        ]
        intake.continuation(owner, Request.model_validate(body), 'c', calls.append, lambda **kw: kw)
    assert len(calls) == 1
    assert len(calls[0].transcript_segments) == 1100
    assert [s.speaker for s in calls[0].transcript_segments] == [i % 2 for i in range(1100)]


@pytest.mark.parametrize('value', ['off', 'shadow', 'typo'])
def test_nonserving_server_explicitly_rejects_chunks(monkeypatch, value):
    monkeypatch.setenv(intake.CONTINUATION_FLAG_KEY, value)
    with pytest.raises(HTTPException) as error:
        intake.continuation(uuid4().hex, chunk(), 'c', lambda r: None, dict)
    assert error.value.status_code == 409
    assert mode(intake.CONTINUATION_FLAG_KEY) == ('shadow' if value == 'typo' else value)


@pytest.mark.parametrize(
    'overrides',
    [
        {'chunk_index': 2},
        {'chunk_count': None},
        {'client_session_id': None},
        {'started_at': None},
        {'chunk_count': 129},
    ],
)
def test_invalid_chunk_metadata_rejected(overrides):
    with pytest.raises(ValidationError):
        Request.model_validate({**chunk().model_dump(), **overrides})


def test_coverage_shadow_logs_and_serving_suppresses_only_covered_segments(monkeypatch):
    request = chunk().model_copy(
        update={'capture_key': CaptureKey(capture_root='root'), 'capture_segment_ranges': [FrameRange(start=0, end=10)]}
    )
    seen = []

    def admit(owner, key, ranges, *, origin):
        seen.append(origin)
        return AdmitResult(uncovered=[], covered=ranges, covering_conversation_id='existing', basis='frames')

    monkeypatch.setitem(sys.modules, 'utils.capture.coverage', SimpleNamespace(admit=admit))
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'shadow')
    assert intake.admit_segments(uuid4().hex, request, dict) == (request, None)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    _, result = intake.admit_segments(uuid4().hex, request, dict)
    assert result['id'] == 'existing'
    assert seen == ['desktop', 'desktop']


def test_partial_frame_overlap_retains_custody(monkeypatch):
    request = chunk().model_copy(
        update={'capture_key': CaptureKey(capture_root='root'), 'capture_segment_ranges': [FrameRange(start=0, end=10)]}
    )
    monkeypatch.setitem(
        sys.modules,
        'utils.capture.coverage',
        SimpleNamespace(
            admit=lambda *a, **kw: AdmitResult(
                uncovered=[FrameRange(start=5, end=10)], covered=[FrameRange(start=0, end=5)]
            )
        ),
    )
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    with pytest.raises(HTTPException) as error:
        intake.admit_segments(uuid4().hex, request, dict)
    assert error.value.status_code == 409


def test_chunk_write_is_fenced_by_account_and_conversation_deletion(store):
    for collection in ['account_deletions', 'deleted_conversations']:
        owner = uuid4().hex
        path = ('account_deletions', owner) if collection == 'account_deletions' else ('users', owner, collection, 'c')
        store.rows[path] = {'deleted': True}
        with pytest.raises(HTTPException):
            intake.stage_chunk(owner, 'c', chunk())
        assert not any(key[:2] == ('users', owner) and key[2] == 'from_segments_chunks' for key in store.rows)


def test_shadow_metric_outcomes_are_closed():
    intake.observe('bounded_test', 'unrecognized')
    samples = [sample for metric in intake.SHADOW.collect() for sample in metric.samples]
    outcomes = {sample.labels['outcome'] for sample in samples if sample.labels.get('check') == 'bounded_test'}
    assert outcomes == {'error'}


def test_staging_ttl_is_seven_days_and_expired_parts_cannot_complete_assembly(store):
    from datetime import datetime, timedelta, timezone

    owner = uuid4().hex
    before = datetime.now(timezone.utc)
    assert intake.stage_chunk(owner, 'c', chunk(0)) is None
    first = store.rows[('users', owner, 'from_segments_chunks', 'c-000')]
    assert before + timedelta(days=7) <= first['expires_at'] <= datetime.now(timezone.utc) + timedelta(days=7)
    first['expires_at'] = before - timedelta(seconds=1)
    assert intake.stage_chunk(owner, 'c', chunk(1)) is None
    assert intake.stage_chunk(owner, 'c', chunk(0)) is not None
    assert first is not store.rows[('users', owner, 'from_segments_chunks', 'c-000')]


@pytest.mark.parametrize('updates', [{'start': 1, 'end': 1}, {'start': -1}, {'text': ' '}])
def test_bad_early_chunk_never_enters_staging(store, updates):
    request = chunk()
    request.transcript_segments[0] = request.transcript_segments[0].model_copy(update=updates)
    with pytest.raises(HTTPException) as error:
        intake.stage_chunk(uuid4().hex, 'synthetic', request)
    assert error.value.status_code == 422
    assert store.rows == {} and not store.transactions
