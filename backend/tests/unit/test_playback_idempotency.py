"""Regression coverage for repeated manifests, retry after publication, and races."""

import json
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from utils.other import playback_cache as cache
from utils.sync import playback_build as build


@pytest.mark.parametrize('race', [False, True])
def test_write_is_create_only_and_counts_outcome(race):
    blob = Mock()
    blob.exists.return_value = False
    if race:
        blob.upload_from_string.side_effect = PreconditionFailed('another writer won')
    outcome = 'cache_hit' if race else 'generated'
    before = cache.PLAYBACK_WRITES.labels(outcome)._value.get()
    assert cache.write_once(blob, b'mp3') is (not race)
    blob.upload_from_string.assert_called_once_with(b'mp3', content_type='audio/mpeg', if_generation_match=0)
    assert cache.PLAYBACK_WRITES.labels(outcome)._value.get() == before + 1


def test_existing_artifact_is_never_overwritten():
    blob = Mock()
    blob.exists.return_value = True
    assert cache.write_once(blob, b'reencoded') is False
    blob.upload_from_string.assert_not_called()


def test_manifest_precedes_audio_and_recovers_without_firestore_stamp():
    blob = Mock(name='blob')
    blob.name = 'playback/synthetic/conversation-version.mp3'
    blob.exists.return_value = False
    blob.size = 3
    sidecar = blob.bucket.blob.return_value
    events = []
    sidecar.upload_from_string.side_effect = lambda *a, **kw: events.append('manifest')
    blob.upload_from_string.side_effect = lambda *a, **kw: events.append('audio')
    # Long manifests must not hit GCS's 8 KiB custom metadata ceiling.
    spans = [dict(file_id=str(i), wall_offset=i, artifact_offset=i, len=1) for i in range(1000)]
    cache.write_once(blob, b'mp3', spans=spans)
    assert events == ['manifest', 'audio']
    assert blob.metadata == {'playback_manifest': 'v1'}
    sidecar.download_as_bytes.return_value = json.dumps(spans).encode()
    assert cache.cached_manifest(blob) == (3, spans)


def test_missing_artifact_returns_cache_miss():
    blob = Mock()
    blob.reload.side_effect = NotFound('expired')
    assert cache.cached_manifest(blob) is None


def test_retry_after_upload_does_no_encoding(monkeypatch):
    spans = [dict(file_id='file', wall_offset=0, artifact_offset=0, len=1)]
    monkeypatch.setattr(build, 'get_conversation_playback_manifest', lambda *_: (3, spans))
    encoder, writer = Mock(), Mock()
    monkeypatch.setattr(build, 'build_conversation_playback_artifact', encoder)
    monkeypatch.setattr(build, 'upload_conversation_playback_artifact', writer)
    assert build.ensure_conversation_artifact('synthetic', 'conversation', [], 0, 'version') == (3, spans)
    encoder.assert_not_called()
    writer.assert_not_called()


def test_changed_version_gets_immutable_key_and_strict_source_validation(monkeypatch):
    monkeypatch.setattr(build, 'get_conversation_playback_manifest', lambda *_: None)
    spans = [dict(file_id='file', wall_offset=0, artifact_offset=0, len=1)]
    encoder, writer = Mock(return_value=(b'mp3', spans)), Mock()
    monkeypatch.setattr(build, 'build_conversation_playback_artifact', encoder)
    monkeypatch.setattr(build, 'upload_conversation_playback_artifact', writer)
    files = [dict(id='file', source_fingerprint='source')]
    assert build.ensure_conversation_artifact('synthetic', 'conversation', files, 0, 'version') == (3, spans)
    assert encoder.call_args.kwargs['strict_sources'] is True
    writer.assert_called_once_with('synthetic', 'conversation', b'mp3', 'version', spans=spans)


@pytest.fixture
def route_app():
    from fastapi import FastAPI
    from routers import sync

    app = FastAPI()
    app.include_router(sync.router)
    app.dependency_overrides[sync.verify_audio_merge_cloud_tasks_oidc] = lambda: 0
    return app, sync


@pytest.mark.asyncio
async def test_http_retry_after_stamp_failure_reuses_published_audio(monkeypatch, route_app):
    import httpx
    from utils.other import storage

    app, sync = route_app

    row = dict(started_at=1000.0, audio_files=[dict(id='part', chunk_timestamps=[1000.0])])
    fingerprint = storage.compute_audio_files_fingerprint(row['audio_files'])
    published = {}
    encoder = Mock(return_value=(b'mp3', [dict(file_id='part', wall_offset=0, artifact_offset=0, len=1)]))
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    monkeypatch.setattr(build, 'build_conversation_playback_artifact', encoder)
    monkeypatch.setattr(build, 'get_conversation_playback_manifest', lambda u, c, fp: published.get(fp))

    def publish(u, c, data, fp, *, spans):
        assert fp not in published
        published[fp] = len(data), spans

    monkeypatch.setattr(build, 'upload_conversation_playback_artifact', publish)
    monkeypatch.setattr(sync, 'try_acquire_job_run_lock', lambda *_: 'token')
    monkeypatch.setattr(sync, 'release_job_run_lock', lambda *_: None)
    monkeypatch.setattr(sync, 'should_skip_background_account_mutation', lambda *_: False)
    monkeypatch.setattr(sync.conversations_db, 'get_conversation', lambda *_: row)
    monkeypatch.setattr(sync, 'get_conversation_playback_signed_url', lambda *a, **kw: 'cached')
    commits = []

    def stamp(u, c, data):
        commits.append(data)
        if len(commits) == 1:
            raise RuntimeError('synthetic transient stamp failure')
        row.update(data)
        return True

    monkeypatch.setattr(sync.conversations_db, 'update_conversation', stamp)
    payload = dict(schema_version=2, uid='synthetic', conversation_id='conversation', fingerprint=fingerprint)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test'
    ) as client:
        assert (await client.post('/v2/audio-merge-jobs/run', json=payload)).status_code == 500
        result = await client.post('/v2/audio-merge-jobs/run', json=payload)
        assert result.status_code == 200 and result.json()['status'] == 'done'
        assert (await client.post('/v2/audio-merge-jobs/run', json=payload)).json()['status'] == 'exists'
    assert len(published) == 1 and len(commits) == 2
    encoder.assert_called_once()
    assert row['conversation_audio']['artifact_fingerprint'] in published


def test_timeline_origin_change_invalidates_immutable_playback(monkeypatch):
    from utils.other import storage
    from utils.sync import playback

    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    files = [dict(id='part', chunk_timestamps=[1000.0])]
    row = dict(
        started_at=1000.0,
        conversation_audio=dict(
            audio_files_fingerprint=storage.compute_audio_files_fingerprint(files),
            artifact_fingerprint=storage.compute_audio_files_fingerprint(files, origin=1000.0, source_identity=True),
        ),
    )
    row['started_at'] = 990.0
    lookup, enqueue = Mock(return_value='stale-url'), Mock()
    monkeypatch.setattr(playback, 'get_conversation_playback_signed_url', lookup)
    monkeypatch.setattr(playback, 'get_conversation_playback_unavailable_fingerprint', lambda *_: None)
    monkeypatch.setattr(playback, 'enqueue_conversation_artifact_build', enqueue)
    assert playback._conversation_audio_urls_entry('synthetic', 'conversation', files, row)['status'] == 'pending'
    lookup.assert_not_called()
    enqueue.assert_called_once()


def test_playback_write_metric_survives_sync_export_filter():
    import re
    from pathlib import Path
    import yaml

    config = yaml.safe_load((Path(__file__).parents[2] / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    keep = next(
        rule['regex'] for rule in config['spec']['endpoints'][0]['metricRelabeling'] if rule['action'] == 'keep'
    )
    assert re.fullmatch(keep, cache.PLAYBACK_WRITES._name + '_total')
    assert cache.PLAYBACK_WRITES._labelnames == ('outcome',)
