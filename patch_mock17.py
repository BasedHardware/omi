with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

new_mock = """
def test_evaluate_gate_unknown_config():
    import pytest
    with pytest.raises(ValueError, match="unknown configuration"):
        qualify.evaluate_gate([], configuration="invalid", min_agreement=0.99, min_multispeaker_units=2, max_peak_ratio=1.1, memory=memory(10, 10))

def test_speech_only_call_no_env_before(monkeypatch):
    monkeypatch.delenv(qualify.SPEECH_ONLY_ENV, raising=False)
    harness = qualify._SpeechOnly(diarizer=object())
    harness.worker.diarize = lambda samples: {'turns': []}
    samples = np.zeros(60 * RATE, dtype=np.float32)
    harness(samples, [(10.0, 12.0), (40.0, 41.0)])
    assert qualify.SPEECH_ONLY_ENV not in qualify.os.environ

def test_score():
    serial = {'turns': [{'speaker': 'SPEAKER_00', 'start': 0, 'end': 1}]}
    packed = {'turns': [{'speaker': 'SPEAKER_00', 'start': 0, 'end': 1}]}
    res = qualify._score(serial, packed)
    assert res['serial_speakers'] == 1
    assert res['packed_speakers'] == 1
    assert res['turns_identical'] is True

    err_res = qualify._score(serial, ValueError("test"))
    assert err_res['serial_speakers'] == 1
    assert err_res['packed_speakers'] == -1
    assert err_res['packed_error'] == 'ValueError'

def test_guarded():
    assert qualify._guarded(lambda: 42) == 42
    err = qualify._guarded(lambda: 1/0)
    assert isinstance(err, ZeroDivisionError)

def test_file():
    import torch
    res = qualify._file(np.zeros(10, dtype=np.float32))
    assert res['sample_rate'] == 16000
    assert res['waveform'].shape == (1, 10)
    assert isinstance(res['waveform'], torch.Tensor)

def test_timed(monkeypatch):
    class MockProbe:
        def begin(self): return 1
        def finish(self, baseline): return 2

    class MockTorch:
        class cuda:
            @staticmethod
            def synchronize(): pass

    monkeypatch.setattr(qualify, 'torch', MockTorch)

    res, elapsed, probe_res = qualify._timed(MockProbe(), lambda: "done")
    assert res == "done"
    assert elapsed >= 0
    assert probe_res == 2

def test_run_missing_torch(monkeypatch):
    monkeypatch.setattr(qualify, 'torch', None)
    import pytest
    with pytest.raises(RuntimeError, match="CUDA"):
        qualify.run([], [10], 1800, 8)

class MockTorchCUDA:
    @staticmethod
    def is_available(): return False

class MockTorchModule:
    cuda = MockTorchCUDA()

def test_run_missing_cuda(monkeypatch):
    monkeypatch.setattr(qualify, 'torch', MockTorchModule())
    import pytest
    with pytest.raises(RuntimeError, match="CUDA"):
        qualify.run([], [10], 1800, 8)

def test_run_success(monkeypatch, tmp_path):
    class MockTorchCUDA:
        @staticmethod
        def is_available(): return True
        @staticmethod
        def get_device_name(idx): return "mock_device"
        @staticmethod
        def synchronize(): pass

    class MockTorchModule:
        cuda = MockTorchCUDA()
        __version__ = "2.1.0"
        @staticmethod
        def from_numpy(arr):
            import torch
            return torch.from_numpy(arr)

    monkeypatch.setattr(qualify, 'torch', MockTorchModule())

    class MockDiarizer:
        def __init__(self):
            self.embedding_exclude_overlap = False

            class SegModel:
                receptive_field = 1.0

            class SegFunc:
                def __init__(self, parent):
                    self.model = SegModel()
                    self.parent = parent
                def __call__(self, f):
                    class Seg:
                        model = self.model
                        data = np.array([[[1.0]]])
                        shape = (1, 1, 1)
                    return Seg()

            self._segmentation = SegFunc(self)

        def speaker_count(self, seg, ref, warm_up):
            class Count:
                data = np.array([1.0])
            return Count()

        def get_embeddings(self, f, seg, exclude_overlap):
            return np.array([1.0, 2.0])

    monkeypatch.setattr(qualify, 'load_pyannote_pair', lambda b: (MockDiarizer(), None))
    monkeypatch.setattr(qualify, 'decode_pcm16_wav', lambda b: np.zeros(16000 * 2, dtype=np.float32))
    monkeypatch.setattr(qualify, 'cut_units', lambda s, u: [np.zeros(16000 * 2, dtype=np.float32)])

    class MockProbe:
        def begin(self): return 1
        def finish(self, b): return {'gpu_allocated_baseline_bytes': 100, 'gpu_allocated_peak_bytes': 110}
    monkeypatch.setattr(qualify, 'ChainMemoryProbe', MockProbe)

    monkeypatch.setattr(qualify, 'PyannoteVAD', lambda v: lambda c: [(0.0, 1.0)])
    monkeypatch.setattr(qualify, 'PyannoteDiarizer', lambda d: lambda c: {'turns': []})

    class MockFlightPyannote:
        shared_trunk = True
        counts = {'x': 1}
        @classmethod
        def create(cls, d, v, budget_seconds): return cls()
        def segment(self, clips):
            class _Seg:
                data = np.array([[[1.0]]])
                shape = (1, 1, 1)
            class Feature:
                pass
            f = Feature()
            f.segmentation = _Seg()
            return [f]
        def vad_spans(self, c, f): return [(0.0, 1.0)]
        def diarize_many(self, pairs): return [{'turns': []}]
        def embed_group(self, files, segs): return [np.array([1.0, 2.0])]
    monkeypatch.setattr(qualify, 'FlightPyannote', MockFlightPyannote)

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"mock audio")

    receipt = qualify.run([str(audio_path)], [2.0], 1800.0, 8)

    assert receipt['diarizer_revision'] == qualify.DIARIZER_REVISION
    assert receipt['model_batch_size'] == 8
    assert receipt['budget_seconds'] == 1800.0
    assert len(receipt['units']) == 1
    unit = receipt['units'][0]
    assert unit['seconds'] == 2.0
    assert unit['packed'] is True
    assert unit['vad_spans_equal'] is True
    assert unit['full_unit']['turns_identical'] is True

def test_flight_packing_refused(monkeypatch, tmp_path):
    class MockTorchCUDA:
        @staticmethod
        def is_available(): return True
        @staticmethod
        def get_device_name(idx): return "mock_device"
        @staticmethod
        def synchronize(): pass

    class MockTorchModule:
        cuda = MockTorchCUDA()
        __version__ = "2.1.0"
        @staticmethod
        def from_numpy(arr):
            import torch
            return torch.from_numpy(arr)

    monkeypatch.setattr(qualify, 'torch', MockTorchModule())

    class MockDiarizer:
        def __init__(self):
            self.embedding_exclude_overlap = False
            class SegModel:
                receptive_field = 1.0
            class SegFunc:
                def __init__(self, parent):
                    self.model = SegModel()
                    self.parent = parent
                def __call__(self, f):
                    class Seg:
                        model = self.model
                        data = np.array([[[1.0]]])
                        shape = (1, 1, 1)
                    return Seg()
            self._segmentation = SegFunc(self)
        def speaker_count(self, seg, ref, warm_up):
            class Count:
                data = np.array([1.0])
            return Count()
        def get_embeddings(self, f, seg, exclude_overlap):
            return np.array([1.0, 2.0])

    monkeypatch.setattr(qualify, 'load_pyannote_pair', lambda b: (MockDiarizer(), None))
    monkeypatch.setattr(qualify, 'decode_pcm16_wav', lambda b: np.zeros(16000 * 2, dtype=np.float32))
    monkeypatch.setattr(qualify, 'cut_units', lambda s, u: [np.zeros(16000 * 2, dtype=np.float32)])

    class MockProbe:
        def begin(self): return 1
        def finish(self, b): return {'gpu_allocated_baseline_bytes': 100, 'gpu_allocated_peak_bytes': 110}
    monkeypatch.setattr(qualify, 'ChainMemoryProbe', MockProbe)
    monkeypatch.setattr(qualify, 'PyannoteVAD', lambda v: lambda c: [(0.0, 1.0)])
    monkeypatch.setattr(qualify, 'PyannoteDiarizer', lambda d: lambda c: {'turns': []})

    class MockFlightPyannote:
        @classmethod
        def create(cls, d, v, budget_seconds): return None
    monkeypatch.setattr(qualify, 'FlightPyannote', MockFlightPyannote)

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"mock audio")

    import pytest
    with pytest.raises(RuntimeError, match="flight packing refused this model layout"):
        qualify.run([str(audio_path)], [2.0], 1800.0, 8)

def test_main_sys_exit(monkeypatch):
    import sys

    mock_exit_code = []
    def mock_exit(code):
        mock_exit_code.append(code)

    monkeypatch.setattr(sys, 'exit', mock_exit)
    monkeypatch.setattr(qualify, 'main', lambda argv: 42)

def test_import_error_torch(monkeypatch):
    import sys
    import importlib

    monkeypatch.setitem(sys.modules, 'torch', None)

    import diarizer.batch_pipeline_flight_qualify
    importlib.reload(diarizer.batch_pipeline_flight_qualify)

    assert diarizer.batch_pipeline_flight_qualify.torch is None

    monkeypatch.undo()
    importlib.reload(diarizer.batch_pipeline_flight_qualify)

def test_main_block():
    import subprocess
    import sys
    import os

    env = os.environ.copy()
    env['PYTHONPATH'] = '.'

    result = subprocess.run([sys.executable, 'diarizer/batch_pipeline_flight_qualify.py', '--help'], env=env, capture_output=True, text=True)
    assert result.returncode == 0
"""

content += "\n" + new_mock.strip() + "\n"
content = "import pytest\n" + content

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
