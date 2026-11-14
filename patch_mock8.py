with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

import re

# find the whole test_run_success function
match = re.search(r"def test_run_success.*?EOF", content, re.DOTALL)
if match:
    pass

new_func = """def test_run_success(monkeypatch, tmp_path):
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

    # Mock load_pyannote_pair
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

    # Mock decode_pcm16_wav
    monkeypatch.setattr(qualify, 'decode_pcm16_wav', lambda b: np.zeros(16000 * 2, dtype=np.float32))
    monkeypatch.setattr(qualify, 'cut_units', lambda s, u: [np.zeros(16000 * 2, dtype=np.float32)])

    # Mock ChainMemoryProbe
    class MockProbe:
        def begin(self): return 1
        def finish(self, b): return {'gpu_allocated_baseline_bytes': 100, 'gpu_allocated_peak_bytes': 110}
    monkeypatch.setattr(qualify, 'ChainMemoryProbe', MockProbe)

    # Mock PyannoteVAD and PyannoteDiarizer
    monkeypatch.setattr(qualify, 'PyannoteVAD', lambda v: lambda c: [(0.0, 1.0)])
    monkeypatch.setattr(qualify, 'PyannoteDiarizer', lambda d: lambda c: {'turns': []})

    # Mock FlightPyannote
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

    # Create temp audio file
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"mock audio")

    # Run
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
"""

content = re.sub(r"def test_run_success.*?assert unit\['full_unit'\]\['turns_identical'\] is True\n", new_func, content, flags=re.DOTALL)

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
