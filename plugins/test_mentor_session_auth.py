"""Hermetic tests for mentor webhook session identity and auth (#13665)."""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    FastAPI = None
    TestClient = None

PLUGINS_ROOT = Path(__file__).resolve().parent
TEST_SECRET = 'test-mentor-webhook-secret'


def _make_transcript_segment_model():
    from pydantic import BaseModel

    class FakeTranscriptSegment(BaseModel):
        text: str = ''
        speaker: str = 'SPEAKER_00'
        is_user: bool = True
        start: float = 0.0
        end: float = 0.0

        def dict(self):
            return self.model_dump()

        @staticmethod
        def segments_as_string(segments):
            return '\n'.join(segment.text for segment in segments)

    return FakeTranscriptSegment


class _RecordingTranscriptStore:
    def __init__(self):
        self.buffers = {}

    def upsert(self, plugin_id, buffer_id, new_segments):
        key = f'{plugin_id}:{buffer_id}'
        existing = list(self.buffers.get(key, []))
        for segment in new_segments:
            existing.append(segment.dict() if hasattr(segment, 'dict') else dict(segment))
        self.buffers[key] = existing
        segment_model = _make_transcript_segment_model()
        return [segment_model(**segment) for segment in existing]


def _load_mentor_app(*, transcript_store: _RecordingTranscriptStore):
    fake_redis = types.ModuleType('redis')

    class _FakeRedisClient:
        def __init__(self, *args, **kwargs):
            pass

    fake_redis.Redis = _FakeRedisClient

    saved = {name: sys.modules.get(name) for name in ('redis', 'db', 'basic', 'basic.mentor_webhook_auth', 'basic.mentor')}
    sys.modules['redis'] = fake_redis
    sys.path.insert(0, str(PLUGINS_ROOT))

    basic_pkg = types.ModuleType('basic')
    basic_pkg.__path__ = [str(PLUGINS_ROOT / 'basic')]
    sys.modules['basic'] = basic_pkg

    auth_spec = importlib.util.spec_from_file_location(
        'basic.mentor_webhook_auth', PLUGINS_ROOT / 'basic' / 'mentor_webhook_auth.py'
    )
    auth_module = importlib.util.module_from_spec(auth_spec)
    sys.modules['basic.mentor_webhook_auth'] = auth_module
    auth_spec.loader.exec_module(auth_module)

    from pydantic import BaseModel, Field
    from typing import List

    fake_segment = _make_transcript_segment_model()

    fake_db = types.ModuleType('db')
    fake_db.get_upsert_segment_to_transcript_plugin = transcript_store.upsert
    sys.modules['db'] = fake_db

    class RealtimePluginRequest(BaseModel):
        session_id: str
        segments: List[fake_segment]

    class ProactiveNotificationResponse(BaseModel):
        prompt: str = Field(default='')
        params: List[str] = Field(default=[])

    class ProactiveNotificationEndpointResponse(BaseModel):
        message: str = Field(default='')
        notification: ProactiveNotificationResponse | None = Field(default=None)

    fake_models = types.ModuleType('models')
    fake_models.TranscriptSegment = fake_segment
    fake_models.RealtimePluginRequest = RealtimePluginRequest
    fake_models.ProactiveNotificationEndpointResponse = ProactiveNotificationEndpointResponse
    fake_models.ProactiveNotificationResponse = ProactiveNotificationResponse
    sys.modules['models'] = fake_models

    mentor_spec = importlib.util.spec_from_file_location(
        'basic.mentor', PLUGINS_ROOT / 'basic' / 'mentor.py', submodule_search_locations=[str(PLUGINS_ROOT / 'basic')]
    )
    mentor_module = importlib.util.module_from_spec(mentor_spec)
    sys.modules['basic.mentor'] = mentor_module
    mentor_spec.loader.exec_module(mentor_module)

    app = FastAPI()
    app.include_router(mentor_module.router)
    return app, mentor_module


def _restore_modules(saved):
    for name, module_value in saved.items():
        if module_value is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module_value


def _segment(text: str):
    return {
        'text': text,
        'speaker': 'SPEAKER_00',
        'is_user': True,
        'start': 0.0,
        'end': 1.0,
    }


@unittest.skipIf(TestClient is None, 'fastapi/httpx test dependencies are not installed')
class MentorSessionAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_modules = {name: sys.modules.get(name) for name in ('redis', 'db', 'basic', 'basic.mentor_webhook_auth', 'basic.mentor', 'models')}

    @classmethod
    def tearDownClass(cls):
        _restore_modules(cls._saved_modules)
        if str(PLUGINS_ROOT) in sys.path:
            sys.path.remove(str(PLUGINS_ROOT))

    def setUp(self):
        self._old_secret = os.environ.get('BASIC_MENTOR_WEBHOOK_SECRET')
        os.environ['BASIC_MENTOR_WEBHOOK_SECRET'] = TEST_SECRET
        self.store = _RecordingTranscriptStore()
        self.app, self.mentor_module = _load_mentor_app(transcript_store=self.store)
        self.mentor_module.scan_segment_session.clear()
        self.client = TestClient(self.app)

    def tearDown(self):
        if self._old_secret is None:
            os.environ.pop('BASIC_MENTOR_WEBHOOK_SECRET', None)
        else:
            os.environ['BASIC_MENTOR_WEBHOOK_SECRET'] = self._old_secret

    def test_fails_closed_when_webhook_secret_unconfigured(self):
        os.environ.pop('BASIC_MENTOR_WEBHOOK_SECRET', None)
        response = self.client.post(
            '/mentor?uid=user-a',
            headers={'Authorization': f'Bearer {TEST_SECRET}'},
            json={'session_id': 'user-a', 'segments': [_segment('hey Omi what do you think')]},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.store.buffers, {})

    def test_unauthenticated_cross_session_write_is_blocked(self):
        response = self.client.post(
            '/mentor?uid=victim-uid',
            json={'session_id': 'victim-uid', 'segments': [_segment('hey Omi what do you think poisoned')]},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.store.buffers, {})

    def test_session_id_must_match_authenticated_uid(self):
        response = self.client.post(
            '/mentor?uid=caller-uid',
            headers={'Authorization': f'Bearer {TEST_SECRET}'},
            json={'session_id': 'victim-uid', 'segments': [_segment('hey Omi what do you think')]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.store.buffers, {})

    def test_cross_session_read_is_blocked(self):
        self.store.buffers['mentor-01:victim-uid'] = [_segment('victim secret hey Omi what do you think')]
        response = self.client.post(
            '/mentor?uid=attacker-uid',
            headers={'Authorization': f'Bearer {TEST_SECRET}'},
            json={'session_id': 'victim-uid', 'segments': [_segment('noise')]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('notification', response.json())

    def test_authenticated_matching_uid_can_write_and_read_own_buffer(self):
        first = self.client.post(
            '/mentor?uid=user-a&mentor_webhook_token=' + TEST_SECRET,
            json={'session_id': 'user-a', 'segments': [_segment('planning a launch')]},
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            '/mentor?uid=user-a&mentor_webhook_token=' + TEST_SECRET,
            json={'session_id': 'user-a', 'segments': [_segment('hey Omi what do you think about timing')]},
        )
        self.assertEqual(second.status_code, 200)
        body = second.json()
        self.assertIn('notification', body)
        self.assertIn('planning a launch', body['notification']['prompt'])
        self.assertEqual(list(self.store.buffers.keys()), ['mentor-01:user-a'])


if __name__ == '__main__':
    unittest.main()
