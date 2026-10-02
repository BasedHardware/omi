"""GET /v2/desktop/messages/reconcile must skip a malformed stored message, not 500 the journal page.

`get_messages_reconcile_page` returns raw Firestore dicts (only the `reported` flag is
filtered), and the reconcile endpoint fed them straight into
`DesktopMessageReconcilePageResponse.messages: list[Message]`. `Message` requires
`id`/`text`/`created_at`/`sender`/`type`, so a single legacy or corrupted row made
FastAPI raise `ResponseValidationError` — HTTP 500 — for the entire desktop journal
sync, while the sibling GET /v2/desktop/messages endpoint was already guarded by
`Message.deserialize_many_safe`. The fix routes the reconcile page through the same
guard.

Test isolation: heavy imports (database.chat, utils.llm.clients, ...) are stubbed with
MagicMocks before the router module is loaded via importlib, matching the harness in
test_desktop_message_quota_router.py. No network, no services.
"""

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')


def _install_package(name: str, path: Path) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def _install_module(name: str, module=None):
    module = module or MagicMock()
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


def _valid_message_record(message_id='msg-1', **overrides):
    record = {
        'id': message_id,
        'text': 'hello from the desktop',
        'created_at': '2026-09-30T10:00:00+00:00',
        'sender': 'human',
        'type': 'text',
        'reported': False,
    }
    record.update(overrides)
    return record


def _make_client(reconcile_rows):
    saved = {k: v for k, v in sys.modules.items()}

    _install_package('database', BACKEND_DIR / 'database')
    _install_package('utils', BACKEND_DIR / 'utils')
    _install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    _install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')

    chat_db = _install_module('database.chat')
    chat_db.ClientMessageIdPayloadConflict = type('ClientMessageIdPayloadConflict', (ValueError,), {})
    chat_db.MessageReconcileCursorError = type('MessageReconcileCursorError', (ValueError,), {})
    chat_db.save_message = MagicMock()
    chat_db.get_messages = MagicMock(return_value=[])
    chat_db.get_messages_reconcile_page = MagicMock(return_value=(list(reconcile_rows), 'cursor-last', True))
    chat_db.delete_messages = MagicMock(return_value=0)
    chat_db.create_chat_session = MagicMock()
    chat_db.get_chat_sessions = MagicMock()
    chat_db.get_chat_session_by_id = MagicMock()
    chat_db.update_chat_session = MagicMock()
    chat_db.delete_chat_session = MagicMock()
    chat_db.update_message_rating = MagicMock()
    chat_db.get_message_count = MagicMock(return_value=0)

    llm_usage_db = _install_module('database.llm_usage')
    llm_usage_db.record_chat_quota_question = MagicMock(return_value=True)
    users_db = _install_module('database.users')
    users_db.set_chat_message_rating_score = MagicMock()
    feedback_utils = _install_module('utils.feedback', ModuleType('utils.feedback'))
    feedback_utils.record_chat_message_feedback = MagicMock()
    product_metrics = _install_module('utils.product_metrics', ModuleType('utils.product_metrics'))
    product_metrics.extract_app_build = MagicMock(return_value='unknown')
    product_metrics.record_product_event = MagicMock()

    chat_utils = _install_module('utils.chat', ModuleType('utils.chat'))
    chat_utils.initial_message_util = MagicMock()
    triage = _install_module('utils.chat_rating_triage', ModuleType('utils.chat_rating_triage'))
    triage.extract_rating_triage_fields = MagicMock(return_value={})
    llm_clients = _install_module('utils.llm.clients', ModuleType('utils.llm.clients'))
    llm_clients.get_llm = MagicMock()
    usage_tracker = _install_module('utils.llm.usage_tracker', ModuleType('utils.llm.usage_tracker'))
    usage_tracker.Features = MagicMock()
    usage_tracker.track_usage = MagicMock()

    auth = _install_module('utils.other.endpoints', ModuleType('utils.other.endpoints'))
    auth.get_current_user_uid = lambda: 'test-uid'
    auth.with_rate_limit = lambda func, _policy: func

    sys.modules.pop('routers.chat_sessions', None)
    spec = importlib.util.spec_from_file_location('routers.chat_sessions', BACKEND_DIR / 'routers' / 'chat_sessions.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['routers.chat_sessions'] = module
    spec.loader.exec_module(module)

    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app, raise_server_exceptions=False), module, saved


def _cleanup(saved):
    for name in [k for k in sys.modules if k not in saved]:
        del sys.modules[name]
    for name, module in saved.items():
        sys.modules[name] = module


def _get_reconcile(client):
    return client.get('/v2/desktop/messages/reconcile')


def test_reconcile_skips_malformed_record_instead_of_500():
    good = _valid_message_record('msg-good')
    bad = {'id': 'msg-bad'}  # missing text/created_at/sender/type -> Message validation error
    client, module, saved = _make_client([bad, good])
    try:
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert [m['id'] for m in payload['messages']] == ['msg-good']
    finally:
        _cleanup(saved)


def test_reconcile_missing_text_row_is_dropped():
    no_text = _valid_message_record('msg-bad', text=None)
    client, module, saved = _make_client([no_text])
    try:
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        assert response.json()['messages'] == []
    finally:
        _cleanup(saved)


def test_reconcile_garbage_typed_row_is_dropped():
    garbage = _valid_message_record('msg-bad', sender=123, type={'weird': 'shape'})
    client, module, saved = _make_client([garbage])
    try:
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        assert response.json()['messages'] == []
    finally:
        _cleanup(saved)


def test_reconcile_non_dict_row_is_dropped():
    good = _valid_message_record('msg-good')
    client, module, saved = _make_client(['not-a-dict', None, good])
    try:
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        assert [m['id'] for m in response.json()['messages']] == ['msg-good']
    finally:
        _cleanup(saved)


def test_reconcile_all_valid_rows_survive():
    rows = [_valid_message_record(f'msg-{i}') for i in range(3)]
    client, module, saved = _make_client(rows)
    try:
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert [m['id'] for m in payload['messages']] == ['msg-0', 'msg-1', 'msg-2']
        assert payload['messages'][0]['text'] == 'hello from the desktop'
        assert payload['messages'][0]['sender'] == 'human'
    finally:
        _cleanup(saved)


def test_reconcile_pagination_fields_pass_through_untouched():
    good = _valid_message_record('msg-good')
    client, module, saved = _make_client([good])
    try:
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload['next_cursor'] == 'cursor-last'
        assert payload['has_more'] is True
    finally:
        _cleanup(saved)


def test_reconcile_next_cursor_survives_when_every_row_is_poisoned():
    bad = {'id': 'msg-bad'}
    client, module, saved = _make_client([bad])
    try:
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload['messages'] == []
        # The caller can still resume the scan from the last inspected document.
        assert payload['next_cursor'] == 'cursor-last'
        assert payload['has_more'] is True
    finally:
        _cleanup(saved)


def test_reconcile_skips_are_logged_with_record_id_and_exception_class():
    import logging

    bad = {'id': 'msg-bad'}
    good = _valid_message_record('msg-good')
    client2, module2, saved2 = _make_client([bad, good])
    try:
        records: list = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        module2.logger.addHandler(_Capture())
        module2.logger.setLevel(logging.WARNING)
        module2.chat_db.get_messages_reconcile_page.return_value = ([dict(bad), dict(good)], None, False)
        response = _get_reconcile(client2)
        assert response.status_code == 200, response.text
        warning_texts = [r.getMessage() for r in records if r.levelno >= logging.WARNING]
        assert any('msg-bad' in text and 'ValidationError' in text for text in warning_texts)
    finally:
        _cleanup(saved2)


def test_guard_uses_same_deserializer_as_the_history_endpoint():
    # Structural guard: both desktop message surfaces must route raw records
    # through Message.deserialize_many_safe so future edits cannot drop one side.
    source = (BACKEND_DIR / 'routers' / 'chat_sessions.py').read_text(encoding='utf-8')
    reconcile_body = source.split('def reconcile_messages', 1)[1].split('@router.', 1)[0]
    assert 'Message.deserialize_many_safe' in reconcile_body
