"""Real decode and CAS retries against generation-enforcing GCS snapshots."""

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from types import SimpleNamespace

from google.api_core.exceptions import NotFound, PreconditionFailed
import pytest
import yaml
import re

from utils.other import audio_frame_table as table, audio_gcs_reads as reads, raw_audio_read as raw
from utils.other import relay_archive_recovery as recovery
from utils.batch_pipeline import record_projection_rebuild as projection


@dataclass
class Object:
    data: bytes
    metadata: dict
    generation: int = 1
    metageneration: int = 1


class Blob:
    def __init__(self, bucket, name, generation=None, *, loaded=False):
        self.bucket, self.name = bucket, name
        self.generation = generation
        self.metageneration = self.metadata = self.size = None
        if loaded:
            self._load()

    def _load(self):
        obj = self.bucket.objects.get(self.name)
        if obj is None or (self.generation is not None and self.generation != obj.generation):
            raise NotFound('missing generation')
        self.generation, self.metageneration = obj.generation, obj.metageneration
        self.metadata, self.size = deepcopy(obj.metadata), len(obj.data)

    def reload(self, **kwargs):
        self.bucket.events.append(('metadata', self.name))
        self._load()
        self._check(kwargs)

    def _check(self, kwargs):
        obj = self.bucket.objects.get(self.name)
        if obj is None:
            raise NotFound('missing object')
        for key, actual in [('if_generation_match', obj.generation), ('if_metageneration_match', obj.metageneration)]:
            if key in kwargs and kwargs[key] != actual:
                raise PreconditionFailed('object changed')
        return obj

    def download_as_bytes(self, **kwargs):
        self.bucket.events.append(('read', self.name))
        self.bucket.downloads.append((self.name, kwargs))
        if self.bucket.before_download is not None:
            self.bucket.before_download(self.name)
        return self._check(kwargs).data


class Bucket:
    name = 'synthetic-sync'

    def __init__(self):
        self.objects, self.events, self.downloads = {}, [], []
        self.before_download = None

    def blob(self, name, generation=None):
        return Blob(self, name, generation)

    def list_blobs(self, *, prefix, **kwargs):
        self.events.append(('list', prefix))
        return [Blob(self, name, loaded=True) for name in self.objects if name.startswith(prefix)]


def capture(*, gapped=False):
    bucket = Bucket()
    path, manifest_path = 'raw-live/u/c/pack/media.bin', 'audio-outbox/u/c/pack/receipt.bin'
    pcm = b'\x01\x00' * 320 * (2 if gapped else 1)
    frames = [{'start': 1000.0, 'samples': 320, 'sequence': 0, 'gap_before': False}]
    if gapped:
        frames.append({'start': 1002.0, 'samples': 320, 'sequence': 1, 'gap_before': True})
    metadata = {
        'conversation_id': 'c',
        'capture_start': '1000',
        'capture_end': '1002.02' if gapped else '1000.02',
        'sample_rate': '16000',
        'channels': '1',
        'source_layout': 'mono',
        'codec': 'pcm16',
        'format': 'pcm16le',
        'gap_count': '1' if gapped else '0',
        'custody_schema': 'audio_custody_v1',
        'clock_source': 'server_projected',
        'sha256': hashlib.sha256(pcm).hexdigest(),
    }
    if not gapped:
        metadata.update(frame_schema=table.FRAME_SCHEMA, custody_manifest_path=manifest_path)
    manifest = {
        'schema': 'audio_custody_v1',
        'capture': metadata,
        'frames': frames,
        'media': {'bucket': bucket.name, 'path': path, 'generation': '1', 'sha256': metadata['sha256']},
    }
    body = json.dumps(manifest).encode()
    bucket.objects[path] = Object(pcm, metadata)
    bucket.objects[manifest_path] = Object(
        body,
        {
            'sha256': hashlib.sha256(body).hexdigest(),
            'format': 'audio-custody-manifest-v1',
        },
    )
    return bucket, path, manifest_path, pcm


def add_peer_pack(bucket, *, gapped=False):
    peer, old_path, old_manifest, _ = capture(gapped=gapped)
    path, manifest_path = old_path.replace('/pack/', '/peer/'), old_manifest.replace('/pack/', '/peer/')
    media = peer.objects[old_path]
    body = json.loads(peer.objects[old_manifest].data)
    for frame in body['frames']:
        frame['start'] += 10
    for bound in ('capture_start', 'capture_end'):
        media.metadata[bound] = str(float(media.metadata[bound]) + 10)
    if not gapped:
        media.metadata['custody_manifest_path'] = manifest_path
    body['capture'] = media.metadata
    body['media']['path'] = path
    encoded = json.dumps(body).encode()
    bucket.objects[path] = media
    bucket.objects[manifest_path] = Object(
        encoded, {'sha256': hashlib.sha256(encoded).hexdigest(), 'format': 'audio-custody-manifest-v1'}
    )
    return path


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    raw._indexes.clear()
    recovery._proofs.clear()
    yield
    raw._indexes.clear()
    recovery._proofs.clear()


@pytest.mark.parametrize('target', ['media', 'manifest'])
@pytest.mark.parametrize('fault', ['generation', 'metageneration', 'missing'])
def test_loaded_metadata_skips_reload_but_changed_or_missing_object_refuses(target, fault):
    bucket, path, manifest, _ = capture()
    name = path if target == 'media' else manifest
    blob = Blob(bucket, name, loaded=True)
    if fault == 'missing':
        del bucket.objects[name]
    else:
        setattr(bucket.objects[name], fault, 2)
    with pytest.raises((PreconditionFailed, NotFound)):
        if target == 'media':
            raw.read_pack(bucket, path, 'u', blob=blob)
        else:
            table._manifest(bucket, 'u', manifest, blob=blob)
    assert [obj for op, obj in bucket.events if op == 'metadata'] == ([manifest] if target == 'media' else [])
    assert bucket.downloads[-1][1]['if_generation_match'] == 1
    assert bucket.downloads[-1][1]['if_metageneration_match'] == 1


@pytest.mark.parametrize('loaded', [True, False])
def test_pack_read_loads_metadata_only_when_missing_and_always_pins_body(loaded):
    bucket, path, _, pcm = capture()
    blob = Blob(bucket, path, loaded=loaded)
    assert raw.read_pack(bucket, path, 'u', blob=blob) == pcm
    assert sum(op == 'metadata' and name == path for op, name in bucket.events) == (0 if loaded else 1)
    assert all(kw['if_generation_match'] == 1 and kw['if_metageneration_match'] == 1 for _, kw in bucket.downloads)


@pytest.mark.parametrize('fault', ['generation', 'metageneration', 'missing'])
def test_mutation_after_reload_still_refuses(fault):
    bucket, path, _, _ = capture()

    def mutate(name):
        if name == path:
            if fault == 'missing':
                del bucket.objects[path]
            else:
                setattr(bucket.objects[path], fault, 2)

    bucket.before_download = mutate
    with pytest.raises((PreconditionFailed, NotFound)):
        raw.read_pack(bucket, path, 'u')


@pytest.mark.parametrize('gapped', [False, True])
def test_validation_uses_one_metadata_get_after_listing_and_never_reloads_for_decode(gapped):
    bucket, path, _, pcm = capture(gapped=gapped)
    with reads.rebuilding():
        raw.list_packs(bucket, 'u', 'c', fresh=True, strict=True)
        bucket.events.clear()
        proven = recovery.validated_uncovered_packs(bucket, 'u', 'c', [])
        assert all(isinstance(expiry, float) for expiry in reads.current().proofs.values())
    assert sum(item['span']['samples'] for item in proven) == len(pcm) // 2
    assert [name for op, name in bucket.events if op == 'metadata'] == [path]
    assert sum(op == 'read' and name == path for op, name in bucket.events) == 1


def wire_rebuild(bucket, monkeypatch, *, after_conflict=None):
    monkeypatch.setattr(projection, 'projection_owner_gone', lambda *a: False)
    monkeypatch.setattr(projection.jobs, 'preflight_projection', lambda *a: True)
    monkeypatch.setattr(projection.audio_archive, 'admitted', lambda *a: True)
    monkeypatch.setattr(projection.storage, 'get_private_cloud_sync_bucket', lambda: bucket)
    monkeypatch.setattr(projection.conversations_db, 'get_conversation_raw_snapshot', lambda *a, **kw: {})
    monkeypatch.setattr(projection.storage, 'list_audio_chunks', lambda *a, **kw: [])
    monkeypatch.setattr(
        projection.conversations_db,
        'create_audio_files_from_chunks',
        lambda *a, listed_chunks: [SimpleNamespace(model_dump=lambda item=item: item) for item in listed_chunks],
    )
    attempts = []

    def apply(*a, **kw):
        attempts.append({**kw, 'payload': a[2]})
        if len(attempts) == 1:
            if after_conflict is not None:
                after_conflict()
            raise projection.conversations_db.AudioFilesChanged('synthetic peer CAS')
        return True

    monkeypatch.setattr(projection.jobs, 'apply_projection', apply)
    return attempts


def test_rebuild_relists_and_decodes_once_across_cas_retry(monkeypatch):
    bucket, path, _, _ = capture()
    # Eviction of the process proof cache must not cause another decode in this rebuild.
    attempts = wire_rebuild(bucket, monkeypatch, after_conflict=recovery._proofs.clear)
    before = {
        op: reads.OPERATIONS.labels(scope='rebuild', operation=op)._value.get()
        for op in ('rebuild', 'list', 'metadata', 'read')
    }
    assert projection.rebuild('u', 'c') is True
    assert len(attempts) == 2
    counts = Counter(op for op, _ in bucket.events)
    assert counts == {'list': 2, 'metadata': 3, 'read': 5}
    assert sum(op == 'read' and name == path for op, name in bucket.events) == 1
    assert reads.current() is None
    for op, count in {**counts, 'rebuild': 1}.items():
        assert reads.OPERATIONS.labels(scope='rebuild', operation=op)._value.get() - before[op] == count


@pytest.mark.parametrize('fault', ['generation', 'metageneration', 'manifest-generation', 'manifest-missing'])
def test_cas_retry_does_not_hide_changed_or_missing_objects(monkeypatch, fault):
    bucket, path, manifest, _ = capture()

    def change():
        name = manifest if fault.startswith('manifest-') else path
        if fault.endswith('missing'):
            del bucket.objects[name]
        elif fault == 'metageneration':
            bucket.objects[name].metageneration += 1
            bucket.objects[name].metadata['sample_rate'] = '8000'
        else:
            bucket.objects[name].generation += 1

    attempts = wire_rebuild(bucket, monkeypatch, after_conflict=change)
    with pytest.raises((PreconditionFailed, NotFound, ValueError)):
        projection.rebuild('u', 'c')
    assert len(attempts) == 1
    assert reads.current() is None


@pytest.mark.parametrize('condition', ['old', 'permissive', 'expired', 'invalidated'])
def test_strict_rebuild_will_not_reuse_unqualified_index(monkeypatch, condition):
    bucket, _, _, _ = capture()
    if condition in {'old', 'permissive'}:
        raw.list_packs(bucket, 'u', 'c', strict=condition == 'old')
    with reads.rebuilding() as _:
        scope = reads.current()
        assert scope is not None
        if condition in {'expired', 'invalidated'}:
            raw.list_packs(bucket, 'u', 'c', strict=True)
            if condition == 'invalidated':
                raw.invalidate_pack_index(bucket, 'u', 'c')
            else:
                key = (bucket.name, 'u', 'c')
                raw._indexes[key] = (0, *raw._indexes[key][1:])
        bucket.events.clear()
        assert recovery.validated_uncovered_packs(bucket, 'u', 'c', [])
    assert sum(op == 'list' and name.startswith('raw-live/') for op, name in bucket.events) == 1


def test_required_archive_read_still_forces_fresh_listing():
    calls = []
    raw.raw_chunks_for_listing(
        object(), 'u', 'c', [], enabled=True, require_archive=True, list_raw=lambda *a, **kw: calls.append(kw) or []
    )
    assert calls[0]['fresh'] is True


def test_sync_and_shared_collectors_keep_operation_counter():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for profile in ('cloud_run_gmp_sync.yaml', 'cloud_run_gmp_sidecar.yaml'):
        doc = yaml.safe_load((root / 'backend/deploy' / profile).read_text())
        rules = doc['spec']['endpoints'][0]['metricRelabeling']
        for rule in rules:
            labels = {'__name__': 'omi_sync_audio_gcs_operations_total'}
            value = ';'.join(labels.get(label, '') for label in rule.get('sourceLabels', []))
            matches = re.fullmatch(rule.get('regex', '.*'), value) is not None
            assert rule['action'] != 'keep' or matches
            assert rule['action'] != 'drop' or not matches


def test_cache_does_not_hide_a_changed_gapped_pack_gate(monkeypatch):
    bucket, _, _, pcm = capture(gapped=True)
    with reads.rebuilding():
        monkeypatch.setenv('RAW_LIVE_GAPPED_PACKS_ENABLED', 'off')
        assert raw.list_packs(bucket, 'u', 'c', strict=True) == []
        monkeypatch.setenv('RAW_LIVE_GAPPED_PACKS_ENABLED', 'true')
        proven = recovery.validated_uncovered_packs(bucket, 'u', 'c', [])
    assert sum(p['span']['samples'] for p in proven) == len(pcm) // 2
    assert sum(op == 'list' and name.startswith('raw-live/') for op, name in bucket.events) == 2


def test_fresh_strict_listing_enforces_the_object_scan_budget():
    bucket, _, _, _ = capture()
    bucket.objects['raw-live/u/c/legacy'] = Object(b'x', {'clock_source': 'arrival_estimate'})
    with reads.rebuilding():
        assert len(raw.list_packs(bucket, 'u', 'c', strict=True)) == 1
        with pytest.raises(TimeoutError, match='index budget'):
            raw.list_packs(bucket, 'u', 'c', strict=True, max_count=1)


def test_metadata_without_metageneration_is_refreshed_before_decode():
    bucket, path, _, pcm = capture()
    blob = Blob(bucket, path, loaded=True)
    blob.metageneration = None
    assert raw.read_pack(bucket, path, 'u', blob=blob) == pcm
    assert ('metadata', path) in bucket.events


def test_cas_retry_sees_peer_pack_committed_after_first_inventory(monkeypatch):
    bucket, original, _, _ = capture()
    owner = {'audio_files': []}
    peer_projection = [{'path': 'peer-committed-projection'}]
    peer_paths = []

    def peer_commit():
        peer_paths.append(add_peer_pack(bucket))
        owner['audio_files'] = peer_projection

    attempts = wire_rebuild(bucket, monkeypatch, after_conflict=peer_commit)
    snapshots = []

    def snapshot(*a, **kw):
        snapshots.append(len([event for event in bucket.events if event == ('list', 'raw-live/u/c/')]))
        return deepcopy(owner)

    monkeypatch.setattr(projection.conversations_db, 'get_conversation_raw_snapshot', snapshot)
    assert projection.rebuild('u', 'c') is True
    assert len(attempts) == 2
    # Each snapshot precedes its own LIST, including after the peer's successful write.
    assert snapshots == [0, 1]
    assert attempts[0]['expected_audio_files'] == []
    assert attempts[1]['expected_audio_files'] == peer_projection
    assert {item['path'] for item in attempts[0]['payload']['audio_files']} == {original}
    assert bucket.events.count(('list', 'raw-live/u/c/')) == 2
    # Inspect the actual CAS payload, not just the refreshed expected snapshot.
    assert {item['path'] for item in attempts[1]['payload']['audio_files']} == {original, peer_paths[0]}
    assert original in bucket.objects and peer_paths[0] in bucket.objects


@pytest.mark.parametrize('strict', [False, True])
@pytest.mark.parametrize('gapped', [False, True])
def test_manifest_replaced_during_listing_excludes_only_pack_unless_strict(strict, gapped):
    bucket, path, manifest, _ = capture(gapped=gapped)
    peer = add_peer_pack(bucket, gapped=gapped)

    def replace(name):
        if name == manifest:
            bucket.objects[manifest].generation += 1
            bucket.before_download = None

    bucket.before_download = replace
    if strict:
        with pytest.raises(PreconditionFailed):
            raw.list_packs(bucket, 'u', 'c', fresh=True, strict=True)
    else:
        result = raw.list_packs(bucket, 'u', 'c', fresh=True)
        assert {item['path'] for item in result} == {peer}
        assert all(item['path'] != path for item in result)
    assert bucket.objects[manifest].generation == 2


def test_pack_deleted_between_attempts_returns_no_objects_without_committing(monkeypatch):
    bucket, path, _, _ = capture()
    attempts = wire_rebuild(bucket, monkeypatch, after_conflict=lambda: bucket.objects.pop(path))
    assert projection.rebuild('u', 'c') == 'no_objects'
    assert len(attempts) == 1
    assert bucket.events.count(('list', 'raw-live/u/c/')) == 2
    assert reads.current() is None
