"""A retained manifest that can never materialize is held once, not retried as a 500 poison loop."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import row, setup  # noqa: F401
from utils.batch_pipeline.source_audio import MAGIC, InvalidRetainedManifest, materialize, read_reference

SOURCE = b'\1\0' * 16000
ITEM = SimpleNamespace(owner_id='o', conversation_id='c', capture_at=1, duration_seconds=1.0)


def manifest(*references):
    body = {'owner_id': 'o', 'conversation_id': 'c', 'capture_at': 1, 'references': list(references), 'context': {}}
    return MAGIC + json.dumps(body).encode()


def ref(start, frames, offset=0):
    digest = hashlib.sha256(SOURCE).hexdigest()
    return {
        'bucket': 'b',
        'path': 'p',
        'generation': 1,
        'pcm_sha256': digest,
        'start_frame': start,
        'offset_frame': offset,
        'frames': frames,
    }


def without(name):
    return {k: v for k, v in ref(0, 8000).items() if k != name}


@pytest.mark.parametrize(
    'body',
    [
        manifest(ref(0, 8000), ref(4000, 4000)),  # overlapping slices
        manifest(ref(0, 0)),  # empty slice
        manifest(ref(0, 8000, offset=12000)),  # exceeds the capture
        manifest(),  # no references
        manifest({k: v for k, v in ref(0, 8000).items() if k != 'frames'}),  # missing slice field
    ],
)
def test_structurally_invalid_manifest_is_a_distinct_permanent_error(body):
    with pytest.raises(InvalidRetainedManifest):
        materialize(body, ITEM, lambda _: SOURCE)


def shaped(**changes):
    body = {'owner_id': 'o', 'conversation_id': 'c', 'capture_at': 1, 'references': [ref(0, 8000)], 'context': {}}
    return MAGIC + json.dumps({**body, **changes}).encode()


@pytest.mark.parametrize(
    'body',
    [
        MAGIC + b'{not json',
        MAGIC + b'\xff\xfe',
        MAGIC + b'[]',
        shaped(references=None),
        shaped(references={'start_frame': 0}),
        shaped(references=[None]),
        shaped(references=[{**ref(0, 8000), 'pcm_sha256': None}]),
        shaped(references=[{**ref(0, 8000), 'path': 7}]),
        shaped(context=None),
    ],
)
def test_malformed_manifest_shape_never_escapes_as_another_error(body):
    """Luna r1: a valid-JSON manifest of the wrong shape must not leak TypeError/KeyError as a 500."""
    fetched = []
    with pytest.raises(InvalidRetainedManifest):
        materialize(body, ITEM, lambda r: fetched.append(r) or SOURCE)
    assert not fetched


def real_reader(ref_):
    # Validation precedes any storage read, so no client is constructed.
    return read_reference(None, ref_, 'o', 'c', {'b'}, b'\0' * 32)


@pytest.mark.parametrize(
    'bad',
    [
        without('path'),
        {**ref(0, 8000), 'path': ''},
        {**ref(0, 8000), 'path': 7},
        {**ref(0, 8000), 'path': 'chunks/other/c/x.bin'},
        {**ref(0, 8000), 'path': 'chunks/o/c/../x.bin'},
        without('generation'),
        {**ref(0, 8000), 'path': 'chunks/o/c/x.bin', 'generation': 0},
        {**ref(0, 8000), 'path': 'chunks/o/c/x.bin', 'generation': 'latest'},
    ],
)
def test_reference_outside_its_owner_scope_is_permanent_at_the_real_reader(bad):
    """Luna r2: a reference missing or outside its pinned owner location is a manifest defect."""
    with pytest.raises(InvalidRetainedManifest):
        materialize(manifest(bad), ITEM, real_reader)


def test_unconfigured_bucket_keeps_the_retryable_error():
    """The allowed buckets are deploy config; a misconfiguration must not mass-hold units."""
    with pytest.raises(ValueError) as error:
        materialize(manifest({**ref(0, 8000), 'bucket': 'other', 'path': 'chunks/o/c/x.bin'}), ITEM, real_reader)
    assert not isinstance(error.value, InvalidRetainedManifest)


def test_valid_manifest_still_materializes():
    assert materialize(manifest(ref(0, 8000), ref(8000, 8000)), ITEM, lambda _: SOURCE)


def test_digest_change_is_not_classified_as_invalid_manifest():
    """A changed source is not a manifest defect; it keeps its existing error path."""
    with pytest.raises(ValueError) as error:
        materialize(manifest(ref(0, 8000)), ITEM, lambda _: b'\2\0' * 16000)
    assert not isinstance(error.value, InvalidRetainedManifest)


def serve(setup, monkeypatch):
    from routers import batch_pipeline as routes
    from utils.batch_pipeline.serving import Serving

    _, store, _, _, _, recovery = setup
    service = Serving(store, recovery=recovery)
    service.reconcile_async = AsyncMock()
    monkeypatch.setattr(routes, 'serving_for_stage', lambda stage: service)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.verify_worker] = lambda: 0
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_manifest_delivery_answers_2xx_holds_once_and_keeps_audio(setup, monkeypatch):
    client, _, binding, artifacts, stt, recovery = setup
    artifacts.fetch_audio.side_effect = InvalidRetainedManifest('invalid retained audio slice')
    http = serve(setup, monkeypatch)
    payload = {'stage': 'prod', 'segment_id': 'bad'}

    response = http.post('/v2/batch-pipeline/recover-quarantine', json=payload)
    assert response.status_code == 200 and response.json() == {'status': 'failed_held'}
    job = row(client)
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'failed_held'
    assert job['recovery']['refusal'] == {'reason': 'invalid_retained_manifest'}
    assert job['recovery']['settled_at'] == 100 and not job['recovery'].get('started_at')
    assert 'result' not in job and job['audio_uri'] == 'gs://synthetic/audio'
    stt.assert_not_called()
    assert not [name for name, *_ in artifacts.mock_calls if 'delete' in name or 'persist' in name]

    # A Cloud Tasks retry or a later sweep cannot prepare a new intent, so no re-wake or re-read.
    assert recovery.protocol.prepare('bad', binding.owner_id, 200) is None
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=payload).json() == {'status': 'held'}
    artifacts.fetch_audio.assert_called_once()
    stt.assert_not_called()


def test_other_audio_errors_keep_their_retryable_path(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = ValueError('retained PCM digest changed')
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 500
    assert row(client)['recovery_state'] == 'prepared' and 'refusal' not in row(client)['recovery']
    stt.assert_not_called()


def test_hold_is_fenced_to_the_unstarted_intent(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert not recovery.protocol.hold_invalid_manifest('bad', 'f' * 32, 100, audio_uri='gs://synthetic/audio')
    assert not recovery.protocol.hold_invalid_manifest('bad', token, 100, audio_uri='gs://synthetic/other')
    assert recovery.protocol.start('bad', token, 100)
    assert not recovery.protocol.hold_invalid_manifest('bad', token, 100, audio_uri='gs://synthetic/audio')
    assert row(client)['recovery_state'] == 'running'
