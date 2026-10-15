import unittest

from pydantic import ValidationError

from models.audio_file import AudioFile, ChunkSpan


class TestAudioFileModelValidation(unittest.TestCase):
    def test_chunk_span_valid(self):
        span = ChunkSpan(start=0.0, end=15.5)
        self.assertEqual(span.start, 0.0)
        self.assertEqual(span.end, 15.5)

    def test_chunk_span_negative_start_rejected(self):
        with self.assertRaises(ValidationError):
            ChunkSpan(start=-1.0, end=5.0)

    def test_chunk_span_negative_end_rejected(self):
        with self.assertRaises(ValidationError):
            ChunkSpan(start=0.0, end=-5.0)

    def test_chunk_span_inverted_rejected(self):
        with self.assertRaises(ValidationError):
            ChunkSpan(start=10.0, end=5.0)

    def test_audio_file_valid(self):
        af = AudioFile(
            id="a1",
            uid="u1",
            conversation_id="c1",
            chunk_timestamps=[0.0, 10.5, 20.0],
            duration=30.0,
            chunk_spans=[ChunkSpan(start=0.0, end=30.0)],
        )
        self.assertEqual(af.duration, 30.0)
        self.assertEqual(len(af.chunk_timestamps), 3)

    def test_audio_file_negative_duration_rejected(self):
        with self.assertRaises(ValidationError):
            AudioFile(
                id="a1",
                uid="u1",
                conversation_id="c1",
                chunk_timestamps=[0.0],
                duration=-5.0,
            )

    def test_audio_file_negative_chunk_timestamp_rejected(self):
        with self.assertRaises(ValidationError):
            AudioFile(
                id="a1",
                uid="u1",
                conversation_id="c1",
                chunk_timestamps=[0.0, -1.0],
                duration=10.0,
            )


if __name__ == "__main__":
    unittest.main()
