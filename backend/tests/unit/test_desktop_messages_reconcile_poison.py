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
the sanctioned ``testing.import_isolation`` primitives — ``stub_modules`` installs the
fakes and restores the full process state on exit, and ``load_module_fresh`` execs the
router against them — so the stub-fed module never leaks into later test files. No
network, no services.
"""

import logging
import os
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')


def _stub_pkg(name: str) -> AutoMockModule:
    module = AutoMockModule(name)
    module.__path__ = []  # type: ignore[attr-defined]
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


def _reconcile_fakes(reconcile_rows):
    # The feedback ledger and product_metrics reach Firestore through their real
    # import chains; stubbing them before the router import keeps google.cloud
    # (and its protobuf descriptor pool) out of the test process.
    chat_db = AutoMockModule('database.chat')
    chat_db.ClientMessageIdPayloadConflict = type('ClientMessageIdPayloadConflict', (ValueError,), {})
    chat_db.MessageReconcileCursorError = type('MessageReconcileCursorError', (ValueError,), {})
    chat_db.get_messages_reconcile_page = MagicMock(return_value=(list(reconcile_rows), 'cursor-last', True))

    llm_usage_db = AutoMockModule('database.llm_usage')
    llm_usage_db.record_chat_quota_question = MagicMock(return_value=True)

    auth = AutoMockModule('utils.other.endpoints')
    auth.get_current_user_uid = lambda: 'test-uid'
    auth.with_rate_limit = lambda func, _policy: func

    # Parent packages come before their children so stub_modules installs each
    # fake leaf as the stub parent package's attribute (import pkg.sub binding).
    return {
        'database': _stub_pkg('database'),
        'database.chat': chat_db,
        'database.llm_usage': llm_usage_db,
        'database.users': AutoMockModule('database.users'),
        'utils': _stub_pkg('utils'),
        'utils.other': _stub_pkg('utils.other'),
        'utils.other.endpoints': auth,
        'utils.llm': _stub_pkg('utils.llm'),
        'utils.llm.clients': AutoMockModule('utils.llm.clients'),
        'utils.llm.usage_tracker': AutoMockModule('utils.llm.usage_tracker'),
        'utils.chat': AutoMockModule('utils.chat'),
        'utils.chat_rating_triage': AutoMockModule('utils.chat_rating_triage'),
        'utils.feedback': AutoMockModule('utils.feedback'),
        'utils.product_metrics': AutoMockModule('utils.product_metrics'),
    }


def _make_client(reconcile_rows):
    with stub_modules(_reconcile_fakes(reconcile_rows)):
        module = load_module_fresh('routers.chat_sessions', str(BACKEND_DIR / 'routers' / 'chat_sessions.py'))
        app = FastAPI()
        app.include_router(module.router)
        client = TestClient(app, raise_server_exceptions=False)
    # The router module holds direct references to the fakes, so requests made
    # after the stub block exits still hit them; sys.modules is already restored.
    return client, module


def _get_reconcile(client):
    return client.get('/v2/desktop/messages/reconcile')


def test_reconcile_skips_malformed_record_instead_of_500():
    good = _valid_message_record('msg-good')
    bad = {'id': 'msg-bad'}  # missing text/created_at/sender/type -> Message validation error
    client, module = _make_client([bad, good])
    response = _get_reconcile(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [m['id'] for m in payload['messages']] == ['msg-good']


def test_reconcile_missing_text_row_is_dropped():
    no_text = _valid_message_record('msg-bad', text=None)
    client, module = _make_client([no_text])
    response = _get_reconcile(client)
    assert response.status_code == 200, response.text
    assert response.json()['messages'] == []


def test_reconcile_garbage_typed_row_is_dropped():
    garbage = _valid_message_record('msg-bad', sender=123, type={'weird': 'shape'})
    client, module = _make_client([garbage])
    response = _get_reconcile(client)
    assert response.status_code == 200, response.text
    assert response.json()['messages'] == []


def test_reconcile_non_dict_row_is_dropped():
    good = _valid_message_record('msg-good')
    client, module = _make_client(['not-a-dict', None, good])
    response = _get_reconcile(client)
    assert response.status_code == 200, response.text
    assert [m['id'] for m in response.json()['messages']] == ['msg-good']


def test_reconcile_all_valid_rows_survive():
    rows = [_valid_message_record(f'msg-{i}') for i in range(3)]
    client, module = _make_client(rows)
    response = _get_reconcile(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [m['id'] for m in payload['messages']] == ['msg-0', 'msg-1', 'msg-2']
    assert payload['messages'][0]['text'] == 'hello from the desktop'
    assert payload['messages'][0]['sender'] == 'human'


def test_reconcile_pagination_fields_pass_through_untouched():
    good = _valid_message_record('msg-good')
    client, module = _make_client([good])
    response = _get_reconcile(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['next_cursor'] == 'cursor-last'
    assert payload['has_more'] is True


def test_reconcile_next_cursor_survives_when_every_row_is_poisoned():
    bad = {'id': 'msg-bad'}
    client, module = _make_client([bad])
    response = _get_reconcile(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['messages'] == []
    # The caller can still resume the scan from the last inspected document.
    assert payload['next_cursor'] == 'cursor-last'
    assert payload['has_more'] is True


def test_reconcile_skips_are_logged_with_record_id_and_exception_class():
    bad = {'id': 'msg-bad'}
    good = _valid_message_record('msg-good')
    client, module = _make_client([bad, good])
    records: list = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = module.logger
    handler = _Capture()
    logger.addHandler(handler)
    saved_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        module.chat_db.get_messages_reconcile_page.return_value = ([dict(bad), dict(good)], None, False)
        response = _get_reconcile(client)
        assert response.status_code == 200, response.text
        warning_texts = [r.getMessage() for r in records if r.levelno >= logging.WARNING]
        assert any('msg-bad' in text and 'ValidationError' in text for text in warning_texts)
    finally:
        # logging.getLogger names are process-global and outlive sys.modules
        # restoration, so both the handler and the level override must be undone.
        logger.removeHandler(handler)
        logger.setLevel(saved_level)


def test_guard_uses_same_deserializer_as_the_history_endpoint():
    # Structural guard: both desktop message surfaces must route raw records
    # through Message.deserialize_many_safe so future edits cannot drop one side.
    source = (BACKEND_DIR / 'routers' / 'chat_sessions.py').read_text(encoding='utf-8')
    reconcile_body = source.split('def reconcile_messages', 1)[1].split('@router.', 1)[0]
    assert 'Message.deserialize_many_safe' in reconcile_body
