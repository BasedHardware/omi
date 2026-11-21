"""Device seams must preserve production models and refuse implicit fallback."""

from types import SimpleNamespace

import pytest

from diarizer import batch_pipeline_startup as startup


def test_cpu_fp32_loader_keeps_pins_and_real_adapter_composition(monkeypatch):
    calls = []
    asr = SimpleNamespace(
        to=lambda precision: calls.append(('precision', precision)) or asr,
        eval=lambda: asr,
    )
    diarizer, vad = object(), object()
    monkeypatch.setattr(startup, 'torch', SimpleNamespace(float32='fp32', bfloat16='bf16'))
    monkeypatch.setattr(
        startup,
        'hf_hub_download',
        lambda repo, name, **kw: calls.append(('checkpoint', repo, name, kw['revision'])) or 'checkpoint',
    )
    monkeypatch.setattr(
        startup,
        'nemo_asr',
        SimpleNamespace(
            models=SimpleNamespace(
                ASRModel=SimpleNamespace(
                    restore_from=lambda path, **kw: calls.append(('restore', path, kw['map_location'])) or asr
                )
            )
        ),
    )
    monkeypatch.setattr(
        startup,
        'load_pyannote_pair',
        lambda batch_size, **kw: calls.append(('pyannote', batch_size, kw['device'])) or (diarizer, vad),
    )
    composed = {}
    monkeypatch.setattr(startup, 'create_local_worker', lambda **kw: composed.update(kw) or composed)
    artifacts = SimpleNamespace(fetch_audio=object(), persist_result=object())
    worker = startup.load_local_worker(artifacts)
    assert ('precision', 'fp32') in calls
    assert ('restore', 'checkpoint', 'cpu') in calls
    assert ('pyannote', 1, 'cpu') in calls
    assert ('checkpoint', 'nvidia/parakeet-tdt-0.6b-v3', 'parakeet-tdt-0.6b-v3.nemo', startup.ASR_REVISION) in calls
    assert worker == dict(
        fetch_audio=artifacts.fetch_audio,
        persist_result=artifacts.persist_result,
        vad_model=vad,
        parakeet_model=asr,
        pyannote_model=diarizer,
    )


@pytest.mark.parametrize('device,dtype', [('mps', 'float32'), ('cpu', 'bfloat16'), ('cuda:0', 'float32')])
def test_local_loader_refuses_implicit_numerical_fallback(device, dtype, monkeypatch):
    monkeypatch.setattr(startup, 'hf_hub_download', lambda *a, **kw: pytest.fail('invalid configuration loaded model'))
    with pytest.raises(ValueError, match='cpu/float32'):
        startup.load_local_models(device=device, dtype=dtype)


@pytest.mark.parametrize('batch_size', [0, 33, True, '1', 1.5])
def test_local_loader_validates_batch_before_model_download(batch_size, monkeypatch):
    monkeypatch.setattr(startup, 'hf_hub_download', lambda *a, **kw: pytest.fail('invalid batch downloaded model'))
    with pytest.raises(ValueError, match='model_batch_size'):
        startup.load_local_models(model_batch_size=batch_size)


def test_cpu_pyannote_pair_uses_pinned_pipeline_and_shared_fp32_segmentation(monkeypatch):
    calls = []
    segmentation = SimpleNamespace(float=lambda: calls.append('fp32') or segmentation, eval=lambda: segmentation)
    diarizer = SimpleNamespace(
        _segmentation=SimpleNamespace(model=segmentation),
        segmentation_batch_size=32,
        embedding_batch_size=32,
        to=lambda device: calls.append(('diarizer', device)) or diarizer,
    )
    vad = SimpleNamespace(
        _segmentation=SimpleNamespace(batch_size=32),
        instantiate=lambda params: calls.append(('vad-params', params)),
        to=lambda device: calls.append(('vad', device)) or vad,
    )
    monkeypatch.setattr(startup, 'torch', SimpleNamespace(device=lambda value: value))
    monkeypatch.setattr(
        startup,
        'Pipeline',
        SimpleNamespace(from_pretrained=lambda repo, **kw: calls.append(('pin', repo, kw['revision'])) or diarizer),
    )
    monkeypatch.setattr(
        startup, 'VoiceActivityDetection', lambda **kw: calls.append(('shared', kw['segmentation'])) or vad
    )
    assert startup.load_pyannote_pair(1, device='cpu') == (diarizer, vad)
    assert ('pin', 'pyannote/speaker-diarization-community-1', startup.DIARIZER_REVISION) in calls
    assert ('diarizer', 'cpu') in calls and ('vad', 'cpu') in calls
    assert 'fp32' in calls and ('shared', segmentation) in calls
    assert diarizer.segmentation_batch_size == diarizer.embedding_batch_size == vad._segmentation.batch_size == 1
