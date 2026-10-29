with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

new_mock = """
        # Mock FlightPyannote
        class MockFlightPyannote:
            shared_trunk = True
            counts = {'x': 1}
            @classmethod
            def create(cls, d, v, budget_seconds): return cls()
            def segment(self, clips):
                class Feature:
                    class Segmentation:
                        data = np.array([[[1.0]]])
                        shape = (1, 1, 1)
                    segmentation = Segmentation()
                return [Feature()]
            def vad_spans(self, c, f): return [(0.0, 1.0)]
            def diarize_many(self, pairs): return [{'turns': []}]
            def embed_group(self, files, segs): return [np.array([1.0, 2.0])]
        monkeypatch.setattr(qualify, 'FlightPyannote', MockFlightPyannote)
"""

old_mock = """        # Mock FlightPyannote
        class MockFlightPyannote:
            shared_trunk = True
            counts = {'x': 1}
            @classmethod
            def create(cls, d, v, budget_seconds): return cls()
            def segment(self, clips):
                class Feature:
                    class Segmentation:
                        data = np.array([[[1.0]]])
                        shape = (1, 1, 1)
                    segmentation = Segmentation()
                return [Feature()]
            def vad_spans(self, c, f): return [(0.0, 1.0)]
            def diarize_many(self, pairs):
                return [{'turns': []}]
            def embed_group(self, files, segs): return [np.array([1.0, 2.0])]
        monkeypatch.setattr(qualify, 'FlightPyannote', MockFlightPyannote)"""

content = content.replace(old_mock, new_mock.strip(), 1)
with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
