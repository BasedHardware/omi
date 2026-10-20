"""chat_sessions router must validate doc ids, guard store calls, and survive
non-string LLM content.

`backend/routers/chat_sessions.py` forwarded `session_id` / `message_id` /
`app_id` / `cursor` straight into Firestore paths, called the data layer bare,
and did `response.content.strip()` on an LLM reply typed `str | list | None`:

* `POST /v2/chat/generate-title` raised `AttributeError: 'list' object has no
  attribute 'strip'` whenever the model returned content blocks,
* a `/` in an id retargeted the document path; `.`/`..`/`__x__`/oversized keys
  reached Firestore and surfaced as an opaque 500,
* `PATCH` accepted `{}` and whitespace-only titles, overwriting a real title,
* `text="   "` passed `min_length=1` and stored an empty message,
* a failing analytics write inside the rating PATCH failed the whole request
  after the rating itself was already persisted.

Run with:

    PYTHONPATH=backend python3 backend/tests/unit/test_chat_sessions_hardening.py
"""

import os
import sys
import types

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

CALLS: list = []
FAIL_WITH: BaseException | None = None
RESULT: object = None
ANALYTICS_ERROR: BaseException | None = None


def _record(name):
    def _fn(*args, **kwargs):
        CALLS.append((name, args, kwargs))
        if FAIL_WITH is not None:
            raise FAIL_WITH
        return RESULT

    return _fn


def _load_module_under_test() -> types.ModuleType:
    """Import ``routers/chat_sessions.py`` with every collaborator stubbed."""
    import importlib.util
    from pathlib import Path

    from testing.import_isolation import AutoMockModule, stub_modules

    chat = AutoMockModule('database.chat')

    class ClientMessageIdPayloadConflict(Exception):
        pass

    class MessageReconcileCursorError(Exception):
        pass

    chat.ClientMessageIdPayloadConflict = ClientMessageIdPayloadConflict
    chat.MessageReconcileCursorError = MessageReconcileCursorError
    for name in (
        'create_chat_session',
        'get_chat_sessions',
        'get_chat_session_by_id',
        'update_chat_session',
        'delete_chat_session',
        'save_message',
        'get_messages',
        'get_messages_reconcile_page',
        'delete_messages',
        'update_message_rating',
        'get_message_count',
    ):
        setattr(chat, name, _record(name))

    llm_usage = AutoMockModule('database.llm_usage')
    llm_usage.record_chat_quota_question = _record('record_chat_quota_question')

    users = AutoMockModule('database.users')

    def _rating_score(*args, **kwargs):
        if ANALYTICS_ERROR is not None:
            raise ANALYTICS_ERROR
        return None

    users.set_chat_message_rating_score = _rating_score

    from pydantic import BaseModel, ConfigDict

    models_chat = AutoMockModule('models.chat')

    class Message(BaseModel):
        """Pydantic model: FastAPI rejects non-BaseModel response annotations."""

        model_config = ConfigDict(extra='allow')

        id: str = ''
        text: str = ''

        @staticmethod
        def deserialize_many_safe(rows, on_error=None):
            return rows

    models_chat.Message = Message

    models_feedback = AutoMockModule('models.feedback')
    models_feedback.MAX_COMMENT_LENGTH = 1000
    models_feedback.FeedbackReason = str
    models_feedback.FeedbackSurface = types.SimpleNamespace(
        chat_text='chat_text', chat_voice='chat_voice', chat_notification='chat_notification'
    )

    feedback = AutoMockModule('utils.feedback')

    def _record_feedback(*args, **kwargs):
        if ANALYTICS_ERROR is not None:
            raise ANALYTICS_ERROR
        return None

    feedback.record_chat_message_feedback = _record_feedback

    models_session = AutoMockModule('models.chat_session')
    for name in (
        'ChatSessionResponse',
        'DeleteMessagesResponse',
        'GenerateTitleResponse',
        'InitialMessageResponse',
        'SaveMessageResponse',
    ):

        class _Resp(BaseModel):
            model_config = ConfigDict(extra='allow')

        setattr(models_session, name, _Resp)

    models_shared = AutoMockModule('models.shared')

    class StatusResponse(BaseModel):
        model_config = ConfigDict(extra='allow')

        status: str = 'ok'

    models_shared.StatusResponse = StatusResponse

    utils_chat = AutoMockModule('utils.chat')
    utils_chat.initial_message_util = _record('initial_message_util')

    triage = AutoMockModule('utils.chat_rating_triage')
    triage.extract_rating_triage_fields = lambda snapshot: {}

    clients = AutoMockModule('utils.llm.clients')
    clients.get_llm = lambda name: types.SimpleNamespace(invoke=lambda prompt: RESULT)

    usage_tracker = AutoMockModule('utils.llm.usage_tracker')
    usage_tracker.Features = types.SimpleNamespace(CHAT='chat')
    usage_tracker.track_usage = lambda uid, feature: _nullcontext()

    generated = AutoMockModule('utils.generated_compute')
    generated.require_generated_compute = lambda uid, feature: None

    auth = AutoMockModule('utils.other.endpoints')
    auth.get_current_user_uid = lambda: 'uid1'
    auth.with_rate_limit = lambda fn, key: fn

    metrics = AutoMockModule('utils.product_metrics')
    metrics.record_product_event = lambda *a, **k: None

    path = Path(__file__).resolve().parents[2] / 'routers' / 'chat_sessions.py'
    spec = importlib.util.spec_from_file_location('_chat_sessions_under_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with stub_modules(
        {
            'database.chat': chat,
            'database.llm_usage': llm_usage,
            'database.users': users,
            'models.chat': models_chat,
            'models.feedback': models_feedback,
            'models.chat_session': models_session,
            'models.shared': models_shared,
            'utils.chat': utils_chat,
            'utils.chat_rating_triage': triage,
            'utils.llm.clients': clients,
            'utils.llm.usage_tracker': usage_tracker,
            'utils.generated_compute': generated,
            'utils.other.endpoints': auth,
            'utils.product_metrics': metrics,
        }
    ):
        spec.loader.exec_module(module)

    return module


def _nullcontext():
    import contextlib

    return contextlib.nullcontext()


cs = _load_module_under_test()
HTTPException = cs.HTTPException


def _reset(error=None, result=None, analytics_error=None) -> None:
    global FAIL_WITH, RESULT, ANALYTICS_ERROR
    CALLS.clear()
    FAIL_WITH = error
    RESULT = result
    ANALYTICS_ERROR = analytics_error


def _raises(fn, status: int):
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == status, f'expected {status}, got {exc.status_code}'
        return exc
    raise AssertionError(f'expected HTTPException {status}')


# --- doc id validation -------------------------------------------------------


def test_clean_doc_id_rejects_unsafe_values():
    for bad in ['', '   ', '.', '..', 'a/b', 'a\\b', 'x\x00y', '__name__']:
        _raises(lambda b=bad: cs._clean_doc_id(b, 'session_id'), 400)
    _raises(lambda: cs._clean_doc_id(None, 'session_id'), 400)
    _raises(lambda: cs._clean_doc_id(5, 'session_id'), 400)


def test_clean_doc_id_rejects_oversized_ids():
    _raises(lambda: cs._clean_doc_id('a' * (cs.MAX_DOC_ID_LENGTH + 1), 'session_id'), 400)


def test_clean_optional_doc_id_keeps_absent_absent():
    assert cs._clean_optional_doc_id(None, 'app_id') is None
    assert cs._clean_optional_doc_id(' app1 ', 'app_id') == 'app1'


def test_traversal_session_id_never_reaches_the_store():
    _reset(result=None)
    _raises(lambda: cs.get_chat_session('../../users/uid1', uid='uid1'), 400)
    assert CALLS == []


def test_traversal_message_id_never_reaches_the_store():
    _reset(result=None)
    request = cs.RateMessageRequest(rating=1)
    _raises(lambda: cs.rate_message('a/b', request, uid='uid1'), 400)
    assert CALLS == []


# --- PATCH body validation ---------------------------------------------------


def test_update_rejects_empty_body():
    _reset(result={})
    _raises(lambda: cs.update_chat_session('s1', cs.UpdateChatSessionRequest(), uid='uid1'), 400)
    assert CALLS == []


def test_update_rejects_blank_title():
    _reset(result={})
    _raises(lambda: cs.update_chat_session('s1', cs.UpdateChatSessionRequest(title='   '), uid='uid1'), 400)
    assert CALLS == []


def test_update_trims_title_and_passes_it():
    _reset(result={'id': 's1'})
    cs.update_chat_session('s1', cs.UpdateChatSessionRequest(title='  Sprint  '), uid='uid1')
    assert CALLS[-1][2]['title'] == 'Sprint'


# --- message payload ---------------------------------------------------------


def test_blank_message_text_is_rejected():
    try:
        cs.SaveMessageRequest(text='   ', sender='human')
    except Exception as exc:  # pydantic ValidationError
        assert 'blank' in str(exc).lower()
        return
    raise AssertionError('blank text must be rejected')


def test_non_blank_message_text_is_accepted():
    req = cs.SaveMessageRequest(text='hi', sender='human')
    assert req.text == 'hi'


# --- title extraction --------------------------------------------------------


def test_title_from_plain_string():
    assert cs._title_from_content('  "Sprint Planning"  ') == 'Sprint Planning'


def test_title_from_content_blocks():
    content = [{'type': 'text', 'text': 'Sprint'}, {'type': 'text', 'text': 'Planning'}]
    assert cs._title_from_content(content) == 'Sprint Planning'


def test_title_from_none_and_unknown_shapes():
    for bad in (None, 5, {}, [{'image': 'x'}]):
        assert cs._title_from_content(bad) == ''


def test_title_from_list_of_strings():
    assert cs._title_from_content(['a', 'b']) == 'a b'


def test_generate_title_survives_content_blocks():
    _reset(result=types.SimpleNamespace(content=[{'type': 'text', 'text': 'Sprint Planning'}]))
    out = cs.generate_session_title(
        cs.GenerateTitleRequest(session_id='s1', messages=[cs.TitleMessageInput(text='hi', sender='human')]),
        uid='uid1',
    )
    assert out == {'title': 'Sprint Planning'}
    assert CALLS[-1][0] == 'update_chat_session'


def test_generate_title_survives_none_content():
    _reset(result=types.SimpleNamespace(content=None))
    out = cs.generate_session_title(
        cs.GenerateTitleRequest(session_id='s1', messages=[cs.TitleMessageInput(text='hi', sender='human')]),
        uid='uid1',
    )
    assert out == {'title': 'New Chat'}


# --- error boundaries --------------------------------------------------------


def test_store_failure_is_a_sanitized_500():
    _reset(error=RuntimeError('firestore 10.1.2.3 refused password=hunter2'))
    exc = _raises(lambda: cs.get_chat_session('s1', uid='uid1'), 500)
    assert 'hunter2' not in exc.detail and '10.1.2.3' not in exc.detail


def test_rating_succeeds_even_when_analytics_fails():
    _reset(result={'id': 'm1'}, analytics_error=RuntimeError('analytics down'))
    out = cs.rate_message('m1', cs.RateMessageRequest(rating=1), uid='uid1')
    assert out == {'status': 'ok'}


def test_rating_404_still_passes_through():
    _reset(result=None)
    _raises(lambda: cs.rate_message('m1', cs.RateMessageRequest(rating=-1), uid='uid1'), 404)


def test_delete_messages_validates_both_ids():
    _reset(result=0)
    _raises(lambda: cs.delete_messages(app_id='a/b', session_id=None, uid='uid1'), 400)
    assert CALLS == []


def test_message_count_is_guarded():
    _reset(error=ValueError('boom'))
    _raises(lambda: cs.get_chat_message_count(uid='uid1'), 500)


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f'PASS {test.__name__}')
        except AssertionError as exc:
            failures += 1
            print(f'FAIL {test.__name__}: {exc}')
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f'ERROR {test.__name__}: {type(exc).__name__}: {exc}')
    print(f'\n{len(tests) - failures}/{len(tests)} tests passed')
    sys.exit(1 if failures else 0)
