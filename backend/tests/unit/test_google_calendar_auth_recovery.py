import asyncio
import importlib.util
import re
from pathlib import Path

from google.api_core.exceptions import NotFound

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROCESS_CONVERSATION = BACKEND_DIR / 'utils' / 'conversations' / 'process_conversation.py'
GOOGLE_UTILS = BACKEND_DIR / 'utils' / 'retrieval' / 'tools' / 'google_utils.py'


class _TokenResponse:
    def __init__(self, status_code: int, text: str = '', payload: dict | None = None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class _AuthClient:
    def __init__(self, response: _TokenResponse):
        self.response = response

    async def post(self, *args, **kwargs):
        return self.response


def _load_google_utils():
    spec = importlib.util.spec_from_file_location('google_utils_under_test', GOOGLE_UTILS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_conversation_processing_calendar_auto_link_is_opt_in():
    source = PROCESS_CONVERSATION.read_text(encoding='utf-8')

    assert 'GOOGLE_CALENDAR_AUTO_LINK_ENABLED' in source
    assert 'def _calendar_auto_link_enabled()' in source
    assert re.search(r'_calendar_auto_link_enabled\(\)\s+and\s+not\s+discarded', source)


def test_refresh_google_token_marks_missing_refresh_token_reauth_required(monkeypatch):
    google_utils = _load_google_utils()
    writes = []

    async def _run_blocking(_executor, fn, *args):
        writes.append((fn, args))

    monkeypatch.setattr(google_utils, 'run_blocking', _run_blocking)

    result = asyncio.run(
        google_utils.refresh_google_token(
            'uid-calendar',
            {'connected': True, 'access_token': 'old-token'},
        )
    )

    assert result is None
    assert writes[0][1][:2] == (
        'uid-calendar',
        'google_calendar',
    )
    assert writes[0][1][2] == {
        'connected': False,
        'reauth_required': True,
        'reauth_reason': 'missing_refresh_token',
        'access_token': google_utils.firestore.DELETE_FIELD,
    }


def test_refresh_google_token_marks_invalid_grant_reauth_required(monkeypatch):
    google_utils = _load_google_utils()
    writes = []

    async def _run_blocking(_executor, fn, *args):
        writes.append((fn, args))

    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'client-id')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'client-secret')
    monkeypatch.setattr(google_utils, 'run_blocking', _run_blocking)
    monkeypatch.setattr(
        google_utils,
        'get_auth_client',
        lambda: _AuthClient(_TokenResponse(400, '{"error":"invalid_grant"}')),
    )

    result = asyncio.run(
        google_utils.refresh_google_token(
            'uid-calendar',
            {'connected': True, 'access_token': 'old-token', 'refresh_token': 'refresh-token'},
        )
    )

    assert result is None
    assert writes[0][1][:2] == (
        'uid-calendar',
        'google_calendar',
    )
    assert writes[0][1][2] == {
        'connected': False,
        'reauth_required': True,
        'reauth_reason': 'invalid_grant',
        'access_token': google_utils.firestore.DELETE_FIELD,
    }


def test_refresh_google_token_does_not_demote_user_for_missing_runtime_config(monkeypatch):
    google_utils = _load_google_utils()
    writes = []

    async def _run_blocking(_executor, fn, *args):
        writes.append((fn, args))

    monkeypatch.delenv('GOOGLE_CLIENT_ID', raising=False)
    monkeypatch.delenv('GOOGLE_CLIENT_SECRET', raising=False)
    monkeypatch.setattr(google_utils, 'run_blocking', _run_blocking)

    result = asyncio.run(
        google_utils.refresh_google_token(
            'uid-calendar',
            {'connected': True, 'access_token': 'old-token', 'refresh_token': 'refresh-token'},
        )
    )

    assert result is None
    assert writes == []


class _DocRef:
    """Firestore document stand-in that records writes and can be 'already deleted'."""

    def __init__(self, exists: bool):
        self.exists = exists
        self.updates = []
        self.sets = []

    def update(self, payload):
        if not self.exists:
            raise NotFound('missing document')
        self.updates.append(payload)

    def set(self, payload, merge=False):
        self.sets.append(payload)

    def collection(self, _name):
        return self

    def document(self, _name):
        return self


class _Db:
    def __init__(self, doc_ref):
        self.doc_ref = doc_ref

    def collection(self, _name):
        return self

    def document(self, _name):
        return self.doc_ref


def _run_refresh_with_db(google_utils, monkeypatch, doc_ref):
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'client-id')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'client-secret')
    monkeypatch.setattr(google_utils, 'db', _Db(doc_ref))
    monkeypatch.setattr(
        google_utils,
        'get_auth_client',
        lambda: _AuthClient(_TokenResponse(200, payload={'access_token': 'new-token'})),
    )

    async def _run_blocking(_executor, fn, *args):
        return fn(*args)

    monkeypatch.setattr(google_utils, 'run_blocking', _run_blocking)

    return asyncio.run(
        google_utils.refresh_google_token(
            'uid-calendar',
            {'connected': True, 'access_token': 'old-token', 'refresh_token': 'refresh-token'},
        )
    )


def test_refresh_writes_only_the_new_token_onto_the_live_integration(monkeypatch):
    google_utils = _load_google_utils()
    doc_ref = _DocRef(exists=True)

    assert _run_refresh_with_db(google_utils, monkeypatch, doc_ref) == 'new-token'

    assert doc_ref.sets == []
    assert len(doc_ref.updates) == 1
    written = doc_ref.updates[0]
    assert written['access_token'] == 'new-token'
    assert 'refresh_token' not in written
    assert 'connected' not in written


def test_refresh_does_not_resurrect_an_integration_the_user_disconnected(monkeypatch):
    google_utils = _load_google_utils()
    doc_ref = _DocRef(exists=False)

    assert _run_refresh_with_db(google_utils, monkeypatch, doc_ref) == 'new-token'

    assert doc_ref.updates == []
    assert doc_ref.sets == []
