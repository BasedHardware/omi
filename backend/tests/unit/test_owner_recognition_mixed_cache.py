"""New writer / verbatim pre-PR consumer compatibility during image overlap."""

import ast
import contextlib
import subprocess
import types
from pathlib import Path

import numpy as np

from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _span_flags,
    _capture_shifted_conversation,
    FakeAudio,
    _admit_any_inventory,
)
from utils.conversations import speaker_resolution as stage
from utils.other import storage

OLD_SHA = '3012ec5070af86b79ae28cc36716e744657bf872'


def _old_source(path):
    return subprocess.run(
        ['git', 'show', f'{OLD_SHA}:backend/{path}'],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_new_short_evidence_cache_is_invisible_to_old_pusher_on_reprocess(env, monkeypatch):
    # A complete 30s inventory in thirty one-second chunks; midpoint extraction
    # produces one physical second. Exercise the actual processing/cache writer.
    _span_flags(monkeypatch)
    audio = FakeAudio([0], seconds=30.2, chunk_seconds=1.0, offset=180.0)
    monkeypatch.setattr(stage, '_verified_read_session', lambda *a, **kw: _admit_any_inventory(*a, audio=[audio], **kw))
    monkeypatch.setattr(stage, 'iter_audio_chunk_pcm', audio)
    owner = np.eye(1, 64)[0]
    query = owner * 0.6
    query[1] = 0.8
    monkeypatch.setattr(stage.users_db, 'get_user_speaker_embedding', lambda uid: owner.tolist())
    calls = []
    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', lambda *a, **kw: calls.append(1) or query)
    blobs = {}

    class Blob:
        def __init__(self, path):
            self.path = path
            self.bucket = None

        def download_as_bytes(self):
            if self.path not in blobs:
                raise storage.BlobNotFound('missing fixture cache')
            return blobs[self.path]

        def upload_from_string(self, data, **kwargs):
            blobs[self.path] = data

    bucket = types.SimpleNamespace(blob=Blob)
    monkeypatch.setattr(storage, '_get_storage_client', lambda: types.SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda *a: contextlib.nullcontext())
    monkeypatch.setattr(storage.encryption, 'encrypt_audio_chunk', lambda data, uid: data)
    monkeypatch.setattr(storage.encryption, 'decrypt_audio_file', lambda data, uid: data)
    # Do not replace the stage's chosen writer: this is what the old image sees.
    # env replaces these functions with lambdas, so use their unmocked import
    # bindings from the source, executing just the import (no service startup).
    stage_source = Path(stage.__file__).read_text()
    bindings = {}
    for node in ast.parse(stage_source).body:
        if isinstance(node, ast.ImportFrom) and node.module == 'utils.other.storage':
            exec(ast.get_source_segment(stage_source, node), bindings)
    monkeypatch.setattr(stage, 'upload_speaker_embedding_cache', bindings['upload_speaker_embedding_cache'])
    monkeypatch.setattr(stage, 'download_speaker_embedding_cache', bindings['download_speaker_embedding_cache'])

    # Execute exactly the old storage reader and old identity policy, rather than
    # emulating the current code with its duration check disabled.
    legacy = {
        '_get_storage_client': storage._get_storage_client,
        'private_cloud_sync_bucket': storage.private_cloud_sync_bucket,
        'SPEAKER_EMBEDDING_CACHE_NAME': 'speaker-embeddings.v1.enc',
        'encryption': storage.encryption,
        'BlobNotFound': storage.BlobNotFound,
        'Optional': __import__('typing').Optional,
    }
    source = _old_source('utils/other/storage.py')
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in (
            '_speaker_embedding_cache_blob',
            'download_speaker_embedding_cache',
        ):
            exec(ast.get_source_segment(source, node), legacy)
    old_engine = types.ModuleType('owner_review_old_cache_engine')
    monkeypatch.setitem(__import__('sys').modules, old_engine.__name__, old_engine)
    exec(
        compile(_old_source('utils/stt/conversation_speakers.py'), 'old_conversation_speakers.py', 'exec'),
        old_engine.__dict__,
    )
    for _ in range(2):
        conv = _capture_shifted_conversation([0], seconds=30.2)
        stage.resolve_speakers_for_processing('u1', conv)
        assert not any(s.is_user for s in conv.transcript_segments)
        old_bytes = legacy['download_speaker_embedding_cache']('u1', 'c1')
        durations = {}
        cache = stage.decode_cache(old_bytes, durations)
        vectors = {s.id: cache[key][1] for s in conv.transcript_segments for key in cache if s.id in key}
        old_result = old_engine.resolve_conversation_speakers(
            conv.model_dump()['transcript_segments'],
            vectors,
            voiceprints={'user': owner},
            embedding_seconds={s.id: 1.0 for s in conv.transcript_segments},
        )
        assert (
            old_result is None or not old_result.voice_identities
        ), 'old pusher must not see the new short-evidence vector'
    assert len(calls) == 1, 'new consumer can reuse its unknown voice without publishing it to old pusher'

    # The new writer neither overwrites nor invalidates an existing v1 object.
    legacy_path = 'audio/u1/c1/speaker-embeddings.v1.enc'
    legacy_bytes = stage.encode_cache({'legacy': (6.0, owner)})
    blobs[legacy_path] = legacy_bytes
    assert legacy['download_speaker_embedding_cache']('u1', 'c1') == legacy_bytes
    assert storage.download_owner_evidence_cache('u1', 'c1') != legacy_bytes
    del blobs[f'audio/u1/c1/{storage.OWNER_EVIDENCE_CACHE_NAME}']
    assert storage.download_owner_evidence_cache('u1', 'c1') == legacy_bytes
