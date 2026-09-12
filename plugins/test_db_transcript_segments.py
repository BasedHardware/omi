"""Regression tests for plugins/db.py transcript-segment persistence.

The session transcript buffer is stored in Redis. The value must be parsed as
data, never executed: a stored payload that is not a plain literal must raise
instead of running code in the plugin process.
"""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


class _FakeRedisClient:
    """In-memory stand-in for redis.Redis; get() returns bytes like redis-py."""

    def __init__(self, *args, **kwargs):
        self.store = {}

    def get(self, key):
        value = self.store.get(key)
        return value.encode() if isinstance(value, str) else value

    def set(self, key, value, ex=None):
        self.store[key] = value

    def expire(self, key, seconds):
        return True


class _FakeTranscriptSegment:
    def __init__(self, **data):
        self._data = dict(data)

    def dict(self):
        return dict(self._data)


def _load_db_module():
    fake_redis = types.ModuleType('redis')
    fake_redis.Redis = _FakeRedisClient
    fake_models = types.ModuleType('models')
    fake_models.TranscriptSegment = _FakeTranscriptSegment
    saved = {name: sys.modules.get(name) for name in ('redis', 'models')}
    sys.modules['redis'] = fake_redis
    sys.modules['models'] = fake_models
    try:
        spec = importlib.util.spec_from_file_location(
            'plugins_db_under_test', str(Path(__file__).parent / 'db.py')
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, module_value in saved.items():
            if module_value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module_value
    return module


class TranscriptSegmentPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = _load_db_module()

    def setUp(self):
        self.db.r.store.clear()

    def _segment(self, text):
        return _FakeTranscriptSegment(
            text=text, speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0
        )

    def test_segments_round_trip_through_store(self):
        result = self.db.get_upsert_segment_to_transcript_plugin('mentor-01', 's1', [self._segment('hello')])
        self.assertEqual([s.dict()['text'] for s in result], ['hello'])

        again = self.db.get_upsert_segment_to_transcript_plugin('mentor-01', 's1', [self._segment('world')])
        self.assertEqual([s.dict()['text'] for s in again], ['hello', 'world'])

    def test_stored_payload_is_parsed_not_executed(self):
        pwned = Path(tempfile.gettempdir()) / 'omi_db_eval_pwned'
        pwned.unlink(missing_ok=True)
        self.db.r.store['plugin:mentor-01:session:s1:transcript_segments'] = (
            f"__import__('pathlib').Path({str(pwned)!r}).touch() or []"
        )
        try:
            with self.assertRaises((ValueError, SyntaxError)):
                self.db.get_upsert_segment_to_transcript_plugin('mentor-01', 's1', [])
            self.assertFalse(pwned.exists(), 'stored Redis payload executed code')
        finally:
            pwned.unlink(missing_ok=True)

    def test_value_written_by_previous_version_still_reads(self):
        legacy = str([{'text': 'hi', 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0.0, 'end': 1.0}])
        self.db.r.store['plugin:mentor-01:session:s1:transcript_segments'] = legacy
        result = self.db.get_upsert_segment_to_transcript_plugin('mentor-01', 's1', [])
        self.assertEqual([s.dict()['text'] for s in result], ['hi'])


if __name__ == '__main__':
    unittest.main()
