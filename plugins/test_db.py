import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Stub redis if not installed
try:
    import redis
except ImportError:
    redis_stub = types.ModuleType("redis")
    redis_stub.Redis = mock.MagicMock
    sys.modules["redis"] = redis_stub

# Stub models if not installed
try:
    from models import TranscriptSegment
except ImportError:
    class TranscriptSegment:
        def __init__(self, text, speaker="SPEAKER_00", is_user=True, start=0.0, end=1.0):
            self.text = text
            self.speaker = speaker
            self.is_user = is_user
            self.start = start
            self.end = end

        def dict(self):
            return {
                "text": self.text,
                "speaker": self.speaker,
                "is_user": self.is_user,
                "start": self.start,
                "end": self.end,
            }

    models_stub = types.ModuleType("models")
    models_stub.TranscriptSegment = TranscriptSegment
    sys.modules["models"] = models_stub

import db
from models import TranscriptSegment


class TestPluginDb(unittest.TestCase):

    @mock.patch.object(db, 'r')
    def test_literal_eval_safe_parsing(self, mock_redis):
        # 1. Normal list of segments
        mock_redis.get.return_value = "[{'text': 'hello', 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0.0, 'end': 1.0}]"
        
        new_segment = TranscriptSegment(
            text="world",
            speaker="SPEAKER_00",
            is_user=True,
            start=1.0,
            end=2.0
        )
        
        result = db.get_upsert_segment_to_transcript_plugin("test_plugin", "test_session", [new_segment])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].text, "hello")
        self.assertEqual(result[1].text, "world")

    @mock.patch.object(db, 'r')
    def test_malicious_code_execution_prevented(self, mock_redis):
        # 2. Malicious payload attempting code execution (__import__ call)
        mock_redis.get.return_value = "__import__('os').system('echo hacked')"
        
        new_segment = TranscriptSegment(
            text="safe text",
            speaker="SPEAKER_00",
            is_user=False,
            start=0.0,
            end=1.0
        )
        
        result = db.get_upsert_segment_to_transcript_plugin("test_plugin", "test_session", [new_segment])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "safe text")

    @mock.patch.object(db, 'r')
    def test_non_list_literal_defaults_to_empty(self, mock_redis):
        # 3. Non-list literal stored in Redis
        mock_redis.get.return_value = "'just a string'"
        
        new_segment = TranscriptSegment(
            text="first segment",
            speaker="SPEAKER_00",
            is_user=True,
            start=0.0,
            end=1.0
        )
        
        result = db.get_upsert_segment_to_transcript_plugin("test_plugin", "test_session", [new_segment])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "first segment")

    @mock.patch.object(db, 'r')
    def test_bytes_response_handling(self, mock_redis):
        # 4. Redis returning bytes
        mock_redis.get.return_value = b"[{'text': 'byte text', 'speaker': 'SPEAKER_00', 'is_user': False, 'start': 0.0, 'end': 1.0}]"
        
        result = db.get_upsert_segment_to_transcript_plugin("test_plugin", "test_session", [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "byte text")


if __name__ == '__main__':
    unittest.main()
