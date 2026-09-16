"""Hermetic regression for ambiguous/unresolved voice channel resolution (#14176).

Voice commands named a channel; after exact lookup failed, the first fuzzy
match was picked (posting to #dev-ops when the user said "dev" in a workspace
with #dev-ops and #frontend-dev), and a named-but-unresolved channel fell back
to the user's default channel, still sending the message somewhere.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import unittest


class Response:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_detector(ai_content='CHANNEL: dev\nMESSAGE: The build is green'):
    """Load the real message_detector.py with openai/dotenv stubbed."""
    openai = ModuleType('openai')

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=ai_content))]))))

    openai.AsyncOpenAI = FakeClient
    dotenv = ModuleType('dotenv')
    dotenv.load_dotenv = lambda: None
    with patch.dict(sys.modules, {'openai': openai, 'dotenv': dotenv}):
        return load('message_detector_under_test', 'message_detector.py')


CHANNELS = [{'id': 'C_OPS', 'name': 'dev-ops'}, {'id': 'C_FRONT', 'name': 'frontend-dev'},
            {'id': 'C_DEFAULT', 'name': 'general'}]
CHANNEL_MAP = {ch['name']: ch['id'] for ch in CHANNELS}


class ResolveChannelTests(unittest.TestCase):
    def setUp(self):
        self.detector = load_detector()

    def test_exact_match_wins_over_fuzzy_candidates(self):
        cid, name, candidates = self.detector.MessageDetector.resolve_channel('#dev-ops', CHANNEL_MAP)
        self.assertEqual((cid, name), ('C_OPS', 'dev-ops'))
        self.assertEqual(candidates, ['dev-ops'])

    def test_single_fuzzy_candidate_resolves(self):
        cid, name, candidates = self.detector.MessageDetector.resolve_channel('ops', CHANNEL_MAP)
        self.assertEqual((cid, name), ('C_OPS', 'dev-ops'))
        self.assertEqual(candidates, ['dev-ops'])

    def test_ambiguous_fuzzy_match_returns_candidates(self):
        cid, name, candidates = self.detector.MessageDetector.resolve_channel('dev', CHANNEL_MAP)
        self.assertIsNone(cid)
        self.assertEqual(name, 'dev')
        self.assertEqual(sorted(candidates), ['dev-ops', 'frontend-dev'])

    def test_unmatched_name_returns_no_candidates(self):
        cid, name, candidates = self.detector.MessageDetector.resolve_channel('random', CHANNEL_MAP)
        self.assertIsNone(cid)
        self.assertEqual(name, 'random')
        self.assertEqual(candidates, [])

    def test_empty_name_never_resolves(self):
        self.assertEqual(self.detector.MessageDetector.resolve_channel('', CHANNEL_MAP), (None, None, []))
        self.assertEqual(self.detector.MessageDetector.resolve_channel(None, CHANNEL_MAP), (None, None, []))

    def test_ai_extract_never_picks_first_fuzzy_match(self):
        module = load_detector(ai_content='CHANNEL: dev\nMESSAGE: The build is green')
        cid, name, message = asyncio.run(
            module.MessageDetector.ai_extract_message_and_channel('send slack message to dev saying the build is green', CHANNELS))
        self.assertIsNone(cid, 'ambiguous spoken name must not resolve to a channel')
        self.assertEqual(name, 'dev')
        self.assertEqual(message, 'The build is green')

    def test_ai_extract_resolves_unique_fuzzy_match(self):
        module = load_detector(ai_content='CHANNEL: ops\nMESSAGE: The build is green')
        cid, name, message = asyncio.run(
            module.MessageDetector.ai_extract_message_and_channel('send slack message to ops saying the build is green', CHANNELS))
        self.assertEqual((cid, name), ('C_OPS', 'dev-ops'))

    def test_ai_extract_unmatched_channel_reports_name(self):
        module = load_detector(ai_content='CHANNEL: nosuch\nMESSAGE: The build is green')
        cid, name, message = asyncio.run(
            module.MessageDetector.ai_extract_message_and_channel('send slack message to nosuch saying the build is green', CHANNELS))
        self.assertIsNone(cid)
        self.assertEqual(name, 'nosuch')


class ProcessSegmentsSendPathTests(unittest.TestCase):
    """Drive process_segments with the detector stubbed; assert send behavior."""

    def setUp(self):
        framework = ModuleType('fastapi')
        app = Mock()
        for method in ('get', 'post', 'on_event'):
            getattr(app, method).side_effect = lambda *a, **k: lambda f: f
        framework.FastAPI = lambda **kwargs: app
        framework.Request = object
        framework.HTTPException = Exception
        framework.Query = lambda *a, **k: None
        responses = ModuleType('fastapi.responses')
        responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = Response
        storage = ModuleType('simple_storage')
        storage.SimpleUserStorage = Mock()
        session_storage = Mock()
        session_storage.get_session_idle_time = Mock(return_value=None)
        storage.SimpleSessionStorage = session_storage
        detector_mod = ModuleType('message_detector')
        self.detector = Mock()
        self.detector.detect_trigger = Mock(return_value=True)
        self.detector.extract_message_content = Mock(return_value='to dev saying the build is green here')
        self.detector.ai_extract_message_and_channel = AsyncMock(return_value=(None, None, None))
        detector_mod.MessageDetector = Mock(return_value=self.detector)
        dotenv = ModuleType('dotenv')
        dotenv.load_dotenv = lambda: None
        slack = ModuleType('slack_sdk')
        slack.WebClient = Mock()
        errors = ModuleType('slack_sdk.errors')
        errors.SlackApiError = Exception
        requests_mod = ModuleType('requests')
        requests_mod.post = Mock()
        requests_mod.get = Mock()
        modules = {'fastapi': framework, 'fastapi.responses': responses, 'simple_storage': storage,
                   'message_detector': detector_mod, 'dotenv': dotenv, 'requests': requests_mod,
                   'slack_sdk': slack, 'slack_sdk.errors': errors}
        originals = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            self.handler = load('slack_handler_channel_under_test', 'main.py')
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
        self.handler.slack_client = Mock()
        self.handler.slack_client.list_channels = Mock(return_value=CHANNELS)
        self.send = AsyncMock(return_value={'success': True})
        self.handler.slack_client.send_message = self.send
        self.user = {'uid': 'u1', 'access_token': 'token', 'selected_channel': 'C_DEFAULT'}

    def process(self, text, session=None):
        session = session or {'session_id': 'test_session_1', 'uid': 'u1', 'message_mode': 'idle'}
        return asyncio.run(self.handler.process_segments(session, [{'text': text}], self.user))

    def test_ambiguous_channel_never_sends_and_never_falls_back(self):
        self.detector.ai_extract_message_and_channel.return_value = (None, 'dev', 'The build is green here')
        response = self.process('send slack message to dev saying the build is green here')
        self.assertIn('No single channel matches', response)
        self.assertIn('dev', response)
        self.send.assert_not_called()

    def test_unresolved_channel_never_falls_back_to_default(self):
        self.detector.ai_extract_message_and_channel.return_value = (None, 'nosuch', 'The build is green here')
        response = self.process('send slack message to nosuch saying the build is green here')
        self.assertIn('No single channel matches', response)
        self.send.assert_not_called()

    def test_no_channel_named_still_uses_default(self):
        self.detector.ai_extract_message_and_channel.return_value = (None, None, 'The build is green here')
        response = self.process('send slack message saying the build is green here')
        self.assertIn('Message sent to #general', response)
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.kwargs['channel_id'], 'C_DEFAULT')

    def test_resolved_channel_sends_there(self):
        self.detector.ai_extract_message_and_channel.return_value = ('C_OPS', 'dev-ops', 'The build is green here')
        response = self.process('send slack message to dev-ops saying the build is green here')
        self.assertIn('Message sent to #dev-ops', response)
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.kwargs['channel_id'], 'C_OPS')

    def test_five_segment_path_also_refuses_ambiguous_channel(self):
        self.detector.ai_extract_message_and_channel.return_value = (None, 'dev', 'The build is green here')
        session = {'session_id': 'omi_session_u1', 'uid': 'u1', 'message_mode': 'recording',
                   'segments_count': 4, 'accumulated_text': 'send slack message to dev saying the build is green'}
        response = self.process(' the build is green', session=session)
        self.assertIn('No single channel matches', response)
        self.send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
