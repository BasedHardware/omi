"""Hermetic regression test for get_upsert_segment_to_transcript_plugin (issue #13663).

Stubs `redis` and `models` in sys.modules so the test runs without the real
Redis server or the omi_plugin_sdk package.
"""

import importlib
import os
import sys
import types
import unittest


class FakeTranscriptSegment:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def dict(self):
        return dict(self.__dict__)

    def __eq__(self, other):
        return isinstance(other, FakeTranscriptSegment) and self.__dict__ == other.__dict__


class FakeRedis:
    def __init__(self, **kwargs):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value.encode('utf-8')

    def expire(self, key, seconds):
        pass


def load_db_module():
    fake_models = types.ModuleType('models')
    fake_models.TranscriptSegment = FakeTranscriptSegment
    sys.modules['models'] = fake_models

    fake_redis_module = types.ModuleType('redis')
    fake_redis_module.Redis = FakeRedis
    sys.modules['redis'] = fake_redis_module

    sys.path.insert(0, os.path.dirname(__file__))
    sys.modules.pop('db', None)
    return importlib.import_module('db')


class TranscriptSegmentEvalTest(unittest.TestCase):
    def setUp(self):
        self.db = load_db_module()
        self.db.r = FakeRedis()

    def test_round_trip_through_literal_eval(self):
        seg = FakeTranscriptSegment(text='hello', speaker='SPEAKER_0', is_user=False, start=0.0, end=1.0)
        result = self.db.get_upsert_segment_to_transcript_plugin('p1', 's1', [seg])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].__dict__['text'], 'hello')

        # A second call must read back what the first call wrote via ast.literal_eval.
        seg2 = FakeTranscriptSegment(text='world', speaker='SPEAKER_1', is_user=True, start=1.0, end=2.0)
        result2 = self.db.get_upsert_segment_to_transcript_plugin('p1', 's1', [seg2])
        self.assertEqual(len(result2), 2)
        self.assertEqual(result2[1].__dict__['text'], 'world')

    def test_malicious_payload_does_not_execute(self):
        key = 'plugin:p1:session:s1:transcript_segments'
        sentinel = os.path.join(os.path.dirname(__file__), '.exploit-sentinel-should-not-exist')
        if os.path.exists(sentinel):
            os.remove(sentinel)
        payload = f"__import__('os').system('touch {sentinel}')"
        self.db.r.store[key] = payload.encode('utf-8')

        seg = FakeTranscriptSegment(text='hi', speaker='SPEAKER_0', is_user=False, start=0.0, end=1.0)
        result = self.db.get_upsert_segment_to_transcript_plugin('p1', 's1', [seg])

        self.assertFalse(os.path.exists(sentinel), 'payload executed -- eval() is still reachable')
        # A non-literal/malformed stored value resets to an empty buffer instead of crashing.
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].__dict__['text'], 'hi')

    def test_non_list_literal_resets_to_empty_buffer(self):
        key = 'plugin:p1:session:s1:transcript_segments'
        self.db.r.store[key] = b"'not-a-list'"

        seg = FakeTranscriptSegment(text='hi', speaker='SPEAKER_0', is_user=False, start=0.0, end=1.0)
        result = self.db.get_upsert_segment_to_transcript_plugin('p1', 's1', [seg])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].__dict__['text'], 'hi')


if __name__ == '__main__':
    unittest.main()
