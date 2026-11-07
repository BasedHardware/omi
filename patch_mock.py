with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

new_mock = """
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
"""

content = content.replace("""    # Mock load_pyannote_pair
    class MockDiarizer:
        def __init__(self):
            self.embedding_exclude_overlap = False
            self.model = self
            self.receptive_field = 1.0
        def _segmentation(self, f):
            class Seg:
                model = self
                data = np.array([[[1.0]]])
                shape = (1, 1, 1)
            return Seg()
        def speaker_count(self, seg, ref, warm_up):
            class Count:
                data = np.array([1.0])
            return Count()
        def get_embeddings(self, f, seg, exclude_overlap):
            return np.array([1.0, 2.0])""", new_mock, 1)

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
