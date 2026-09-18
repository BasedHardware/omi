"""Hermetic regression tests for Linear OAuth state signing.

Before this fix, /auth/linear/callback did `uid = state` verbatim — the
state was never signed, so an attacker could initiate OAuth with a
victim's uid and the callback bound the attacker's workspace grant to
that uid. Runs under stdlib unittest without third-party dependencies.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class App:
    def __init__(self, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def mount(self, *args, **kwargs):
        pass


class Response:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error


def load_app():
    modules = {}
    definitions = {
        'fastapi': dict(FastAPI=App, HTTPException=Exception, Request=object, Query=Mock()),
        'fastapi.responses': dict(HTMLResponse=object, RedirectResponse=Mock(), JSONResponse=Mock()),
        'fastapi.staticfiles': dict(StaticFiles=Mock()),
        'fastapi.templating': dict(Jinja2Templates=Mock()),
        'dotenv': dict(load_dotenv=lambda: None),
        'requests': dict(post=Mock(), get=Mock(), RequestException=Exception),
        'db': {name: Mock() for name in (
            'store_linear_tokens', 'get_linear_tokens', 'delete_linear_tokens', 'is_token_expired',
            'store_default_team', 'get_default_team', 'get_user_settings')},
        'models': {name: Response if name == 'ChatToolResponse' else SimpleNamespace for name in (
            'ChatToolResponse', 'LinearIssue', 'LinearTeam', 'LinearProject', 'LinearComment', 'LinearUser', 'WorkflowState')},
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location('linear_oauth_state_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    return module


linear = load_app()


class TestSignedState(unittest.TestCase):
    def test_round_trip(self):
        state = linear._oauth_state_for("uid-abc")
        self.assertEqual(linear._oauth_state_uid(state), "uid-abc")

    def test_tampered_uid_rejected(self):
        state = linear._oauth_state_for("uid-abc")
        self.assertIsNone(linear._oauth_state_uid("uid-xyz" + state[7:]))

    def test_tampered_signature_rejected(self):
        state = linear._oauth_state_for("uid-abc")
        self.assertIsNone(linear._oauth_state_uid(state[:-2] + "00"))

    def test_unsigned_state_rejected(self):
        self.assertIsNone(linear._oauth_state_uid("uid-abc"))
        self.assertIsNone(linear._oauth_state_uid(""))
        self.assertIsNone(linear._oauth_state_uid(":sig"))


class TestCallbackGuardsState(unittest.TestCase):
    def setUp(self):
        self.templates_patcher = patch.object(linear, "templates")
        self.mock_templates = self.templates_patcher.start()
        self.addCleanup(self.templates_patcher.stop)
        self.post_patcher = patch.object(linear.requests, "post")
        self.mock_post = self.post_patcher.start()
        self.addCleanup(self.post_patcher.stop)

    def test_unsigned_callback_never_reaches_token_exchange(self):
        asyncio.run(
            linear.linear_callback(Mock(), code="c", state="victim-uid", error=None)
        )
        self.mock_post.assert_not_called()
        ctx = self.mock_templates.TemplateResponse.call_args[0][1]
        self.assertEqual(ctx["error"], "Invalid OAuth state")

    def test_signed_callback_reaches_token_exchange(self):
        self.mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"access_token": "t", "expires_in": 100}),
        )
        state = linear._oauth_state_for("uid-abc")
        asyncio.run(
            linear.linear_callback(Mock(), code="c", state=state, error=None)
        )
        self.mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
