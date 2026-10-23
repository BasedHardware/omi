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
    sidecar.reload.side_effect = NotFound('not published yet')
    events = []
    sidecar.upload_from_string.side_effect = lambda *a, **kw: events.append('manifest')
    blob.upload_from_string.side_effect = lambda *a, **kw: events.append('audio')
    # Long manifests must not hit GCS's 8 KiB custom metadata ceiling.
    spans = [dict(file_id=str(i), wall_offset=i, artifact_offset=i, len=1) for i in range(1000)]
    cache.write_once(blob, b'mp3', spans=spans)
    assert events == ['manifest', 'audio']
    assert blob.metadata == {'playback_manifest': 'v1'}
    sidecar.reload.side_effect = None
    sidecar.download_as_bytes.return_value = json.dumps(spans).encode()
    assert cache.cached_manifest(blob) == (3, spans)


def test_missing_artifact_returns_cache_miss():
    blob = Mock()
    blob.reload.side_effect = NotFound('expired')
    blob.bucket.blob.return_value.reload.side_effect = NotFound('expired')
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
    assert row['conversation_audio_artifact_fingerprint'] in published

    # The pre-fix reader has no private artifact-key field. Its existing
    # source-identity stamp path must still locate the published immutable MP3.
    legacy_row = {key: value for key, value in row.items() if key != 'conversation_audio_artifact_fingerprint'}
    lookup = Mock(return_value='cached')
    monkeypatch.setattr(sync.sync_playback, 'get_conversation_playback_signed_url', lookup)
    monkeypatch.setattr(sync.sync_playback, 'get_conversation_playback_unavailable_fingerprint', lambda *_: None)
    monkeypatch.setattr(sync.sync_playback, 'enqueue_conversation_artifact_build', Mock())
    result = sync.sync_playback._conversation_audio_urls_entry(
        'synthetic', 'conversation', row['audio_files'], legacy_row
    )
    assert result['status'] == 'cached'
    lookup.assert_called_once_with(
        'synthetic', 'conversation', fingerprint=row['conversation_audio']['audio_files_fingerprint']
    )


def test_timeline_origin_change_invalidates_immutable_playback(monkeypatch):
    from utils.other import storage
    from utils.sync import playback

    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    files = [dict(id='part', chunk_timestamps=[1000.0])]
    row = dict(
        started_at=1000.0,
        conversation_audio=dict(
            audio_files_fingerprint=storage.compute_audio_files_fingerprint(files),
        ),
    )
    row['conversation_audio_artifact_fingerprint'] = storage.compute_audio_files_fingerprint(
        files, origin=1000.0, source_identity=True
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


class _Bucket:
    """GCS fake with immutable generation snapshots and real precondition checks."""

    def __init__(self):
        self.objects = {}
        self.serial = 0
        self.deletes = []

    def blob(self, name):
        return _Blob(self, name)

    def put(self, name, data, metadata=None):
        self.serial += 1
        self.objects[name] = (self.serial, data, metadata)


class _Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name
        self.generation, self.metadata, self.size = None, None, None

    def exists(self):
        return self.name in self.bucket.objects

    def reload(self):
        if not self.exists():
            raise NotFound('missing')
        self.generation, data, self.metadata = self.bucket.objects[self.name]
        self.size = len(data)

    def _check(self, generation):
        if not self.exists():
            raise NotFound('missing')
        if self.bucket.objects[self.name][0] != generation:
            raise PreconditionFailed('generation changed')

    def download_as_bytes(self, *, if_generation_match):
        self._check(if_generation_match)
        return self.bucket.objects[self.name][1]

    def delete(self, *, if_generation_match):
        self._check(if_generation_match)
        self.bucket.deletes.append((self.name, if_generation_match))
        del self.bucket.objects[self.name]

    def upload_from_string(self, data, *, content_type, if_generation_match):
        assert if_generation_match == 0
        if self.exists():
            raise PreconditionFailed('already exists')
        self.bucket.put(self.name, data, self.metadata)


_SPANS = [dict(file_id='part', wall_offset=0, artifact_offset=0, len=1)]


@pytest.mark.parametrize(
    'bad_manifest',
    [b'{', b'\xff', b'[]', b'{}', b'[{}]', b'[null]', b'[1]', b'[{"len":NaN}]']
    + [json.dumps([dict(_SPANS[0], len=value)]).encode() for value in (float('nan'), 10**400)],
)
@pytest.mark.parametrize('audio_present', [False, True])
def test_corrupt_manifest_pair_is_generation_matched_miss_then_rebuilt(bad_manifest, audio_present):
    bucket = _Bucket()
    blob = bucket.blob('playback/synthetic/conversation.mp3')
    if audio_present:
        bucket.put(blob.name, b'bad-audio', {'playback_manifest': 'v1'})
    manifest_name = blob.name + '.manifest.json'
    bucket.put(manifest_name, bad_manifest)
    observed = {name: obj[0] for name, obj in bucket.objects.items()}
    assert cache.cached_manifest(blob) is None
    assert dict(bucket.deletes) == observed
    assert not bucket.objects
    assert cache.write_once(blob, b'mp3', spans=_SPANS)
    assert cache.cached_manifest(blob) == (3, _SPANS)


@pytest.mark.parametrize('replacement', ['audio', 'manifest'])
def test_corruption_repair_never_deletes_concurrent_replacement(monkeypatch, replacement):
    bucket = _Bucket()
    blob = bucket.blob('playback/synthetic/conversation.mp3')
    bucket.put(blob.name, b'bad-audio')
    sidecar = bucket.blob(blob.name + '.manifest.json')
    bucket.put(sidecar.name, b'{')
    original = _Blob.delete
    repaired = []

    def replace_then_delete(target, *, if_generation_match):
        if not repaired:
            repaired.append(True)
            if replacement == 'audio':
                bucket.put(blob.name, b'replacement')
            bucket.put(sidecar.name, json.dumps(_SPANS).encode())
        return original(target, if_generation_match=if_generation_match)

    monkeypatch.setattr(_Blob, 'delete', replace_then_delete)
    assert cache.cached_manifest(blob) is None
    assert bucket.objects[sidecar.name][1] == json.dumps(_SPANS).encode()
    if replacement == 'audio':
        assert bucket.objects[blob.name][1] == b'replacement'
        assert not bucket.deletes
    else:
        assert [name for name, _ in bucket.deletes] == [blob.name]
    cache.write_once(blob, b'mp3', spans=_SPANS)
    assert cache.cached_manifest(blob)[1] == _SPANS


def test_legacy_blob_missing_sidecar_needs_only_one_reencode(monkeypatch):
    bucket = _Bucket()
    blob = bucket.blob('playback/synthetic/conversation.mp3')
    bucket.put(blob.name, b'mp3')  # no metadata marker, no sidecar
    encoder = Mock(return_value=(b'mp3', _SPANS))
    monkeypatch.setattr(build, 'build_conversation_playback_artifact', encoder)
    monkeypatch.setattr(build, 'get_conversation_playback_manifest', lambda *_: cache.cached_manifest(blob))
    monkeypatch.setattr(
        build, 'upload_conversation_playback_artifact', lambda *a, spans: cache.write_once(blob, a[2], spans=spans)
    )
    generation = bucket.objects[blob.name][0]
    for _ in range(2):  # a failed Firestore stamp retries through the same path
        assert build.ensure_conversation_artifact('synthetic', 'conversation', [], 0, 'version') == (3, _SPANS)
    encoder.assert_called_once()
    assert bucket.objects[blob.name][0] == generation
    assert not bucket.deletes


@pytest.mark.parametrize('version,demand', [(1, False), (2, False), (2, True)])
@pytest.mark.asyncio
async def test_http_superseded_tasks_do_no_artifact_work(monkeypatch, route_app, version, demand):
    import httpx

    app, sync = route_app
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'true' if demand else 'false')
    row = dict(started_at=1000.0, audio_files=[dict(id='current', chunk_timestamps=[1000.0])])
    release, file_lookup, conversation_lookup, file_build, conversation_build, stamp = (Mock() for _ in range(6))
    monkeypatch.setattr(sync, 'try_acquire_job_run_lock', lambda *_: 'token')
    monkeypatch.setattr(sync, 'release_job_run_lock', release)
    monkeypatch.setattr(sync, 'should_skip_background_account_mutation', lambda *_: False)
    monkeypatch.setattr(sync.conversations_db, 'get_conversation', lambda *_: row)
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', stamp)
    monkeypatch.setattr(sync, 'get_playback_artifact_signed_url', file_lookup)
    monkeypatch.setattr(sync, 'get_conversation_playback_signed_url', conversation_lookup)
    monkeypatch.setattr(sync.sync_playback, 'build_playback_artifact', file_build)
    monkeypatch.setattr(build, 'ensure_conversation_artifact', conversation_build)
    payload = dict(schema_version=version, uid='synthetic', conversation_id='conversation', on_demand=demand)
    payload.update(dict(audio_file_id='obsolete', timestamps=[999.0]) if version == 1 else dict(fingerprint='obsolete'))
    before = cache.PLAYBACK_WRITES.labels('skipped')._value.get()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = await client.post('/v2/audio-merge-jobs/run', json=payload)
    assert result.status_code == 200 and result.json() == {'status': 'superseded'}
    for work in (file_lookup, conversation_lookup, file_build, conversation_build, stamp):
        work.assert_not_called()
    release.assert_called_once()
    assert cache.PLAYBACK_WRITES.labels('skipped')._value.get() == before + 1


@pytest.mark.asyncio
async def test_http_corrupt_sidecar_recovers_on_last_attempt_without_unavailable_marker(monkeypatch, route_app):
    import httpx
    from utils.other import storage

    app, sync = route_app
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    row = dict(started_at=1000.0, audio_files=[dict(id='part', chunk_timestamps=[1000.0])])
    bucket = _Bucket()
    blob = bucket.blob('playback/synthetic/conversation.mp3')
    bucket.put(blob.name, b'bad-audio', {'playback_manifest': 'v1'})
    bucket.put(blob.name + '.manifest.json', b'[]')
    monkeypatch.setattr(storage, '_conversation_playback_blob', lambda *_: blob)
    monkeypatch.setattr(sync, 'try_acquire_job_run_lock', lambda *_: 'token')
    monkeypatch.setattr(sync, 'release_job_run_lock', lambda *_: None)
    monkeypatch.setattr(sync, 'should_skip_background_account_mutation', lambda *_: False)
    monkeypatch.setattr(sync.conversations_db, 'get_conversation', lambda *_: row)
    monkeypatch.setattr(sync.conversations_db, 'update_conversation', lambda u, c, data: row.update(data) or True)
    marker = Mock()
    monkeypatch.setattr(sync, 'mark_conversation_playback_unavailable', marker)
    monkeypatch.setattr(sync, 'get_sync_tasks_max_attempts', lambda: 3)
    app.dependency_overrides[sync.verify_audio_merge_cloud_tasks_oidc] = lambda: 2
    encoder = Mock(return_value=(b'mp3', _SPANS))
    monkeypatch.setattr(build, 'build_conversation_playback_artifact', encoder)
    payload = dict(
        schema_version=2,
        uid='synthetic',
        conversation_id='conversation',
        fingerprint=storage.compute_audio_files_fingerprint(row['audio_files']),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = await client.post(
            '/v2/audio-merge-jobs/run', json=payload, headers={'X-CloudTasks-TaskRetryCount': '2'}
        )
    assert result.status_code == 200 and result.json()['status'] == 'done'
    marker.assert_not_called()
    encoder.assert_called_once()
    assert cache.cached_manifest(blob) == (3, _SPANS)
