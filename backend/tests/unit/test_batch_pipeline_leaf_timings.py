"""Observe real artifact/model seams without changing custody or model hooks."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import replace
import io
import struct
from types import SimpleNamespace
import wave

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from prometheus_client import CollectorRegistry
import pytest

from diarizer import batch_pipeline_models as models
from diarizer.batch_pipeline_flight import FlightPyannote
from tests.unit.test_batch_pipeline_artifacts import ObjectClient, item, setup
from utils.batch_pipeline import leaf_timings
from utils.batch_pipeline.stage_timings import StageTimings
from utils.batch_pipeline.source_audio import read_reference


@pytest.fixture
def profile(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', 'true')
    registry = CollectorRegistry()
    return StageTimings(registry), registry


def count(registry, stage):
    return registry.get_sample_value('omi_batch_pipeline_stage_seconds_count', {'stage': stage})


def audio():
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0' * 32000)
    return output.getvalue()


def test_encrypted_fetch_decode_and_persist_observe_actual_io_thread(profile):
    timings, registry = profile
    artifacts, _, _ = setup()
    original = item()
    staged = replace(original, audio_uri=artifacts.stage_audio(original, audio()))
    adapter = models.StagedAudio(artifacts.fetch_audio, timings_of=lambda: timings)

    def execute():
        samples = adapter.decode(staged)
        with leaf_timings.active(timings):
            result = artifacts.persist_result(staged, {'words': []})
        return samples, result

    with ThreadPoolExecutor(max_workers=1) as executor:
        samples, uri = executor.submit(execute).result()
    assert len(samples) == 16000 and uri.endswith('#2')
    for stage in ['download_metadata', 'download', 'decrypt', 'decode', 'artifact_register', 'encrypt', 'upload']:
        assert count(registry, stage) == 1
    # Calls outside the worker context never leak into its registry.
    artifacts.fetch_audio(staged)
    assert count(registry, 'decrypt') == 1


def test_authenticated_decryption_failure_is_counted_and_preserved(profile):
    timings, registry = profile
    artifacts, client, _ = setup()
    original = item()
    staged = replace(original, audio_uri=artifacts.stage_audio(original, audio()))
    name = next(iter(client.objects))
    generation, body = client.objects[name]
    client.objects[name] = (generation, body[:-1] + bytes([body[-1] ^ 1]))
    adapter = models.StagedAudio(artifacts.fetch_audio, timings_of=lambda: timings)
    with pytest.raises(InvalidTag):
        adapter.decode(staged)
    assert count(registry, 'decrypt') == 1
    assert count(registry, 'decode') is None


@pytest.mark.parametrize('model_failure', [False, True])
def test_pyannote_embedding_hook_is_restored_on_success_and_failure(profile, monkeypatch, model_failure):
    timings, registry = profile
    failure = RuntimeError('synthetic model failure')

    class Model:
        def get_embeddings(self, file):
            if model_failure:
                raise failure
            return [1]

        def __call__(self, file):
            assert self.get_embeddings(file) == [1]
            return {'turns': []}

    model = Model()
    original = model.get_embeddings
    # Freeze this instance's callable so exact restoration can be asserted.
    model.get_embeddings = original
    monkeypatch.setattr(
        models,
        'torch',
        SimpleNamespace(
            inference_mode=nullcontext, from_numpy=lambda values: SimpleNamespace(unsqueeze=lambda dimension: values)
        ),
    )
    monkeypatch.setattr(models, 'diarization_payload', lambda value: value)
    adapter = models.PyannoteDiarizer(model, timings_of=lambda: timings)
    if model_failure:
        with pytest.raises(RuntimeError) as raised:
            adapter([0])
        assert raised.value is failure
    else:
        assert adapter([0]) == {'turns': []}
    assert model.get_embeddings is original
    assert count(registry, 'embedding') == 1


def test_leaf_clock_failure_does_not_change_artifact_result(profile, monkeypatch):
    timings, registry = profile
    artifacts, _, _ = setup()
    original = item()
    staged = replace(original, audio_uri=artifacts.stage_audio(original, audio()))

    def broken():
        raise RuntimeError('clock failed')

    monkeypatch.setattr(leaf_timings.time, 'perf_counter', broken)
    assert len(models.StagedAudio(artifacts.fetch_audio, timings_of=lambda: timings).decode(staged)) == 16000
    assert count(registry, 'download') is None


def test_context_is_reset_on_failure_and_not_inherited_by_other_threads(profile):
    timings, registry = profile
    with pytest.raises(RuntimeError):
        with leaf_timings.active(timings):
            with ThreadPoolExecutor(max_workers=1) as executor:
                assert executor.submit(leaf_timings.call, 'decode', lambda: 7).result() == 7
            raise RuntimeError('synthetic failure')
    assert leaf_timings.call('decode', lambda: 9) == 9
    assert count(registry, 'decode') is None


def test_packed_embedding_measures_the_forward_not_cached_feature_reads(profile, monkeypatch):
    timings, registry = profile
    flight = object.__new__(FlightPyannote)
    monkeypatch.setattr(flight, '_embed_group', lambda *args, **kwargs: ['features'])
    with leaf_timings.active(timings):
        assert flight.embed_group(['file'], ['segments']) == ['features']
    assert count(registry, 'flight_embedding') == 1


def test_retained_source_download_decrypt_and_resample_are_also_profiled(profile):
    timings, registry = profile
    client = ObjectClient()
    key, nonce = b'a' * 32, b'n' * 12
    pcm = b'\x01\x00' * 8000
    sealed = nonce + AESGCM(key).encrypt(nonce, pcm, None)
    path = 'chunks/synthetic-owner/conversation/audio.pcm.enc'
    client.objects[path] = (1, struct.pack('>I', len(sealed)) + sealed)
    ref = {'bucket': 'synthetic-batch-bucket', 'path': path, 'generation': 1, 'sample_rate': 8000}
    with leaf_timings.active(timings):
        result = read_reference(client, ref, 'synthetic-owner', 'conversation', {'synthetic-batch-bucket'}, key)
    assert len(result) > len(pcm)
    for stage in ['download_metadata', 'download', 'decrypt', 'decode']:
        assert count(registry, stage) == 1
