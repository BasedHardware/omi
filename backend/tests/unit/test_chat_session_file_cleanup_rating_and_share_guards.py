from contextlib import contextmanager
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import shutil

import pytest
from fastapi import HTTPException, UploadFile

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

import database.chat as chat_db
import utils.other.chat_file as chat_file
from models.chat import RateMessageRequest, ShareChatMessagesRequest

BACKEND_DIR = Path(__file__).resolve().parents[2]


@contextmanager
def stub_modules(stubs: dict):
    saved = dict(sys.modules)
    try:
        for mod_name, attrs in stubs.items():
            parts = mod_name.split('.')
            for i in range(1, len(parts)):
                pkg_name = '.'.join(parts[:i])
                if pkg_name not in sys.modules:
                    pkg = ModuleType(pkg_name)
                    pkg.__path__ = [str(BACKEND_DIR.joinpath(*parts[:i]))]
                    sys.modules[pkg_name] = pkg
            mod = ModuleType(mod_name)
            for k, v in attrs.items():
                setattr(mod, k, v)
            sys.modules[mod_name] = mod
            if len(parts) > 1:
                parent = sys.modules.get('.'.join(parts[:-1]))
                if parent is not None:
                    setattr(parent, parts[-1], mod)
        yield
    finally:
        for name in [k for k in sys.modules if k not in saved]:
            del sys.modules[name]
        for name, mod in saved.items():
            sys.modules[name] = mod


def load_module_fresh(dotted_name: str):
    rel_path = Path(*dotted_name.split('.')).with_suffix('.py')
    spec = importlib.util.spec_from_file_location(dotted_name, BACKEND_DIR / rel_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)
    return module


def _load_chat_router():
    with stub_modules(
        {
            'python_multipart': {'__version__': '0.0.20'},
            'multipart': {'__version__': '0.0.20'},
            'multipart.multipart': {'shutil': shutil, 'parse_options_header': MagicMock()},
            'utils.chat_turn': {
                'run_chat_turn': MagicMock(),
                'TurnOptions': MagicMock(),
                'MobileReplySink': MagicMock(),
                'record_chat_quota_question_best_effort': MagicMock(),
                '_required_chat_quota_provider': MagicMock(return_value='openai'),
            },
            'utils.messaging.contracts': {'Principal': MagicMock()},
            'database.notifications': {},
            'utils.chat_session_target': {'resolve_chat_target': MagicMock()},
            'database.llm_usage': {},
            'database.apps': {'record_app_usage': MagicMock()},
            'utils.apps': {'get_available_app_by_id': MagicMock()},
            'utils.device_tools': {
                'UnknownDeviceToolCall': type('UnknownDeviceToolCall', (Exception,), {}),
                'store_device_tool_result': MagicMock(),
            },
            'utils.conversation_helpers': {'extract_memory_ids': MagicMock()},
            'utils.chat': {
                'acquire_chat_session': MagicMock(),
                'emit_stream_error_fallback': MagicMock(),
                'initial_message_util': MagicMock(),
                'process_voice_message_segment_stream': MagicMock(),
                'resolve_voice_message_language': MagicMock(),
                'transcribe_voice_message_segment': MagicMock(),
                'transcribe_pcm_bytes': MagicMock(),
            },
            'utils.sync.files': {'retrieve_file_paths': MagicMock(), 'decode_files_to_wav': MagicMock()},
            'utils.stt.streaming': {
                'STTService': MagicMock(),
                'connect_stt_socket_with_fallback': MagicMock(),
                'drain_stt_socket': MagicMock(),
                'get_stt_service_for_language': MagicMock(),
                'process_audio_modulate': MagicMock(),
                'process_audio_parakeet': MagicMock(),
            },
            'utils.stt.provider_resilience': {
                'close_rejected_socket': MagicMock(),
                'fallback_socket_is_serving': MagicMock(),
            },
            'utils.stt.pre_recorded': {'get_prerecorded_service': MagicMock()},
            'config.prerecorded_stt': {'TranscriptionOutcome': str},
            'config.stt_provider_policy': {
                'MODULATE_PROVIDER': 'modulate',
                'STTServingSurface': MagicMock(),
                'provider_for_service': MagicMock(),
            },
            'utils.stt.outcomes': {
                'TranscriptionFailure': Exception,
                'bounded_provider': MagicMock(),
                'failure_from_exception': MagicMock(),
            },
            'utils.observability.transcription': {'TranscriptionAttempt': MagicMock()},
            'utils.llm.goals': {'extract_and_update_goal_progress': MagicMock()},
            'database.redis_db': {
                'try_acquire_goal_extraction_lock': MagicMock(),
                'check_rate_limit': MagicMock(),
                'store_chat_share': MagicMock(),
                'get_chat_share': MagicMock(),
            },
            'database.users': {'set_chat_message_rating_score': MagicMock()},
            'utils.chat_rating_triage': {'extract_rating_triage_fields': MagicMock(return_value={})},
            'utils.feedback': {'record_chat_message_feedback': MagicMock()},
            'utils.rate_limit_config': {'get_effective_limit': MagicMock(), 'RATE_LIMIT_SHADOW': False},
            'utils.llm.gateway_client': {
                'CHAT_AGENT_ROUTE_DIRECT': 'direct',
                'get_chat_agent_route': MagicMock(return_value='direct'),
            },
            'utils.subscription': {'enforce_chat_quota': MagicMock(), 'is_trial_paywalled': MagicMock()},
            'utils.share_links': {'build_share_url': lambda path: f'https://omi.me{path}'},
            'utils.other.endpoints': {
                'get_current_user_uid': lambda: 'u1',
                'get_current_user_uid_ws_listen': lambda: 'u1',
                'with_rate_limit': lambda fn, _policy: fn,
            },
            'utils.other.storage': {'upload_multi_chat_files': MagicMock(return_value={})},
            'utils.retrieval.graph': {'execute_chat_stream': MagicMock()},
            'utils.llm.usage_tracker': {
                'set_usage_context': MagicMock(),
                'reset_usage_context': MagicMock(),
                'Features': MagicMock(),
            },
            'utils.users': {'get_user_display_name': MagicMock(return_value='Alice')},
            'utils.log_sanitizer': {'sanitize_pii': lambda x: x},
            'utils.chat_followup': {'followup_content_blocks': MagicMock()},
            'utils.observability': {'submit_langsmith_feedback': MagicMock()},
            'utils.observability.fallback': {'record_fallback': MagicMock()},
            'utils.journey_metrics_contract': {
                'resolve_client_kind': MagicMock(),
                'resolve_client_kind_from_headers': MagicMock(),
            },
            'utils.product_metrics': {
                'extract_app_build': MagicMock(return_value='unknown'),
                'record_product_event': MagicMock(),
            },
            'utils.observability.journeys': {'ClientJourneyAttempt': MagicMock(), 'JourneyAttempt': MagicMock()},
            'utils.voice_duration_limiter': {
                'MAX_SESSION_DURATION_S': 60,
                'compute_pcm_duration_ms': MagicMock(),
                'read_wav_duration_ms': MagicMock(),
                'try_consume_budget': MagicMock(),
                'try_reserve_session_budget': MagicMock(),
                'settle_reserved_duration': MagicMock(),
                'record_actual_duration': MagicMock(),
            },
            'utils.stt.failure_diagnostics': {'transcription_failure_categories': MagicMock()},
            'testing.parity_pack_v0.live_capture': {'SurfaceParityCapture': MagicMock()},
        }
    ):
        return load_module_fresh('routers.chat')


def _load_chat_sessions_router():
    with stub_modules(
        {
            'database.llm_usage': {'record_chat_quota_question': MagicMock()},
            'database.users': {'set_chat_message_rating_score': MagicMock()},
            'utils.feedback': {'record_chat_message_feedback': MagicMock()},
            'utils.chat': {'initial_message_util': MagicMock()},
            'utils.chat_rating_triage': {'extract_rating_triage_fields': MagicMock(return_value={})},
            'utils.llm.clients': {'get_llm': MagicMock()},
            'utils.llm.usage_tracker': {'Features': MagicMock(), 'track_usage': MagicMock()},
            'utils.other.endpoints': {
                'get_current_user_uid': lambda: 'u1',
                'with_rate_limit': lambda fn, _policy: fn,
            },
            'utils.product_metrics': {'record_product_event': MagicMock()},
        }
    ):
        return load_module_fresh('routers.chat_sessions')


def test_delete_chat_session_cascades_context_generation_and_cleans_up_session_files(monkeypatch):
    # 1. Router DELETE /v2/chat-sessions/{session_id} cleans up attached files before deleting session
    real_delete_chat_session = chat_db.delete_chat_session
    sessions_router = _load_chat_sessions_router()
    call_order = []

    class _FakeFileChatTool:
        def __init__(self, uid, session_id):
            call_order.append(('init_file_tool', uid, session_id))

        def cleanup(self):
            call_order.append(('cleanup_files',))

    monkeypatch.setattr(chat_file, 'FileChatTool', _FakeFileChatTool)
    monkeypatch.setattr(
        sessions_router.chat_db,
        'delete_chat_session',
        lambda uid, sid, cascade_messages=False: call_order.append(('delete_session', uid, sid, cascade_messages)),
    )

    resp = sessions_router.delete_chat_session('sess-1', uid='u1')
    assert resp == {'status': 'ok'}
    assert call_order == [
        ('init_file_tool', 'u1', 'sess-1'),
        ('cleanup_files',),
        ('delete_session', 'u1', 'sess-1', True),
    ]
    monkeypatch.setattr(chat_db, 'delete_chat_session', real_delete_chat_session)

    # 2. Database delete_chat_session bumps chat_context_generation without exceeding BATCH_LIMIT (500)
    batches = []

    class _Batch:
        def __init__(self):
            self.ops = []
            batches.append(self)

        def delete(self, ref):
            self.ops.append(('delete', ref))

        def update(self, ref, data):
            self.ops.append(('update', ref, data))

        def commit(self):
            assert len(self.ops) <= chat_db.BATCH_LIMIT

    session_ref = MagicMock()
    session_ref.get.return_value.exists = True
    msg_col = MagicMock()
    msg_col.document.side_effect = lambda doc_id: f'msg:{doc_id}'
    query = MagicMock()
    msg_col.where.return_value = query
    query.limit.return_value = query
    # Exact 500-doc page followed by empty page: generation bump must land in a second batch
    page_500 = [SimpleNamespace(id=f'm{i}') for i in range(chat_db.BATCH_LIMIT)]
    query.stream.side_effect = [page_500, []]

    user_ref = MagicMock()
    user_ref.collection.side_effect = lambda name: (
        SimpleNamespace(document=lambda _sid: session_ref) if name == 'chat_sessions' else msg_col
    )
    fake_db = SimpleNamespace(
        collection=lambda _name: SimpleNamespace(document=lambda _uid: user_ref),
        batch=_Batch,
    )
    monkeypatch.setattr(chat_db, 'db', fake_db)

    chat_db.delete_chat_session('u1', 'sess-1', cascade_messages=True)
    assert len(batches) == 2
    assert len(batches[0].ops) == 500
    assert len(batches[1].ops) == 1
    assert batches[1].ops[0][0] == 'update'
    assert batches[1].ops[0][1] is user_ref
    assert 'chat_context_generation' in batches[1].ops[0][2]
    session_ref.delete.assert_called_once()


def test_file_chat_tool_cleanup_clears_session_file_ids_and_upload_unlinks_temp_thumb_on_error(monkeypatch, tmp_path):
    # 1. FileChatTool.cleanup clears file_ids on the session document
    updated_sessions = []
    monkeypatch.setattr(
        chat_file.chat_db,
        'get_chat_session_by_id',
        lambda uid, sid: {'id': sid, 'file_ids': ['f1'], 'created_at': datetime.now(timezone.utc)},
    )
    monkeypatch.setattr(
        chat_file.chat_db,
        'get_chat_files',
        lambda uid, file_ids: [{'id': 'f1', 'openai_file_id': 'oai-1'}],
    )
    monkeypatch.setattr(chat_file.chat_db, 'delete_multi_files', lambda uid, files: None)
    monkeypatch.setattr(
        chat_file.chat_db,
        '_update_chat_session_if_exists',
        lambda uid, sid, values, what: updated_sessions.append((uid, sid, values, what)) or True,
    )
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(delete=lambda file_id, **_kw: None))

    tool = chat_file.FileChatTool('u1', 'sess-1')
    tool.cleanup()
    assert updated_sessions == [('u1', 'sess-1', {'file_ids': []}, 'file cleanup')]
    assert tool.chat_session.file_ids == []

    # 2. FileChatTool.upload unlinks generated thumbnail when openai.files.create fails
    img_path = tmp_path / 'sample.png'
    thumb_path = tmp_path / 'sample_thumbnail.png'
    img_path.write_bytes(b'fake-image')

    def _fake_generate_thumbnail(self, size=(128, 128)):
        thumb_path.write_bytes(b'fake-thumb')
        self.thumbnail_name = 'sample_thumbnail.png'
        self.thumbnail_path = str(thumb_path)

    monkeypatch.setattr(chat_file.File, 'generate_thumbnail', _fake_generate_thumbnail)
    monkeypatch.setattr(
        chat_file.openai,
        'files',
        SimpleNamespace(create=MagicMock(side_effect=RuntimeError('OpenAI upload outage'))),
    )

    with pytest.raises(RuntimeError, match='OpenAI upload outage'):
        chat_file.FileChatTool.upload(img_path, file_name='sample.png')

    assert not thumb_path.exists()


def test_upload_file_chat_cleans_up_earlier_thumbnails_when_later_file_or_storage_fails(monkeypatch, tmp_path):
    chat_router = _load_chat_router()
    thumb1 = tmp_path / 'thumb1.png'
    thumb1.write_bytes(b'thumb-bytes')

    calls = {'count': 0}

    def _fake_upload(temp_file, file_name=None):
        calls['count'] += 1
        if calls['count'] == 1:
            return {
                'file_name': 'first.png',
                'file_id': 'oai-1',
                'mime_type': 'image/png',
                'thumbnail': str(thumb1),
                'thumbnail_name': 'thumb1.png',
            }
        raise chat_router.UnsupportedChatFileError("Unsupported attachment: 'ogg' files are not supported in chat.")

    monkeypatch.setattr(chat_router.FileChatTool, 'upload', staticmethod(_fake_upload))

    f1 = UploadFile(filename='first.png', file=MagicMock())
    f2 = UploadFile(filename='second.ogg', file=MagicMock())
    monkeypatch.setattr(chat_router.shutil, 'copyfileobj', lambda src, dst: None)

    with pytest.raises(HTTPException) as exc_info:
        chat_router.upload_file_chat(files=[f1, f2], uid='u1')

    assert exc_info.value.status_code == 400
    assert not thumb1.exists()


def test_rate_message_rejects_invalid_rating_and_missing_message_and_uses_snapshot_run_id(monkeypatch):
    chat_router = _load_chat_router()
    score_calls = []
    feedback_calls = []
    langsmith_calls = []
    get_message_calls = []

    monkeypatch.setattr(chat_router, 'set_chat_message_rating_score', lambda *a, **kw: score_calls.append((a, kw)))
    monkeypatch.setattr(chat_router, 'record_chat_message_feedback', lambda *a, **kw: feedback_calls.append((a, kw)))
    monkeypatch.setattr(chat_router, 'submit_langsmith_feedback', lambda **kw: langsmith_calls.append(kw))
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_message',
        lambda uid, mid: get_message_calls.append((uid, mid)) or None,
    )

    # 1. Invalid rating=0 is rejected with 400 before touching DB or analytics
    with pytest.raises(HTTPException) as exc_400:
        chat_router.rate_message('msg-1', RateMessageRequest(rating=0), uid='u1')
    assert exc_400.value.status_code == 400
    assert score_calls == []
    assert feedback_calls == []

    # 2. Missing message raises 404 without writing analytics or feedback ledger rows
    monkeypatch.setattr(chat_router.chat_db, 'update_message_rating', lambda uid, mid, r: None)
    with pytest.raises(HTTPException) as exc_404:
        chat_router.rate_message('missing-msg', RateMessageRequest(rating=-1), uid='u1')
    assert exc_404.value.status_code == 404
    assert score_calls == []
    assert feedback_calls == []

    # 3. Valid rating uses snapshot['langsmith_run_id'] without a second chat_db.get_message read
    monkeypatch.setattr(
        chat_router.chat_db,
        'update_message_rating',
        lambda uid, mid, r: {'id': mid, 'rating': r, 'langsmith_run_id': 'run-123'},
    )
    res = chat_router.rate_message(
        'msg-1',
        RateMessageRequest(rating=1),
        x_app_platform=None,
        x_app_version=None,
        x_app_build=None,
        uid='u1',
    )
    assert res == {'status': 'ok'}
    assert len(score_calls) == 1
    assert len(feedback_calls) == 1
    assert langsmith_calls == [{'run_id': 'run-123', 'score': 1.0, 'key': 'chat_message_rating'}]
    assert get_message_calls == []


def test_share_and_get_shared_chat_messages_reject_reported_and_deduplicate_ids(monkeypatch):
    chat_router = _load_chat_router()
    now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)

    msg_ok = SimpleNamespace(id='m1', text='Hello', sender='ai', reported=False, created_at=now)
    msg_reported = SimpleNamespace(id='m2', text='Bad output', sender='ai', reported=True, created_at=now)

    # 1. Sharing a reported message is rejected with 404
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_message',
        lambda uid, mid: (msg_reported, 'doc-m2') if mid == 'm2' else ((msg_ok, 'doc-m1') if mid == 'm1' else None),
    )
    with pytest.raises(HTTPException) as exc_rep:
        chat_router.share_chat_messages(ShareChatMessagesRequest(message_ids=['m1', 'm2']), uid='u1')
    assert exc_rep.value.status_code == 404

    # 2. Duplicate and blank IDs are deduplicated when creating a share link
    stored_shares = []
    monkeypatch.setattr(
        chat_router,
        'store_chat_share',
        lambda token, uid, name, mids: stored_shares.append((uid, name, mids)) or True,
    )
    share_res = chat_router.share_chat_messages(
        ShareChatMessagesRequest(message_ids=['m1', 'm1', '']),
        uid='u1',
    )
    assert 'token' in share_res
    assert stored_shares == [('u1', 'Alice', ['m1'])]

    # 3. Public get_shared_chat_messages filters out subsequently reported messages and deduplicates IDs
    monkeypatch.setattr(
        chat_router,
        'get_chat_share',
        lambda token: {'uid': 'u1', 'display_name': 'Alice', 'message_ids': ['m1', 'm1', 'm2']},
    )
    shared = chat_router.get_shared_chat_messages('tok-1')
    assert shared['count'] == 1
    assert [m['id'] for m in shared['messages']] == ['m1']


def test_migrate_chats_level_batch_skips_undecryptable_enhanced_messages(monkeypatch):
    updates = []

    class _Batch:
        def update(self, ref, data):
            updates.append((ref, data))

        def commit(self):
            pass

    good_cipher = chat_db.encryption.encrypt('secret message', 'u1')
    bad_cipher = 'corrupted-ciphertext-from-other-key'

    docs = [
        SimpleNamespace(
            id='msg-good',
            exists=True,
            reference='ref-good',
            to_dict=lambda: {'data_protection_level': 'enhanced', 'text': good_cipher},
        ),
        SimpleNamespace(
            id='msg-bad',
            exists=True,
            reference='ref-bad',
            to_dict=lambda: {'data_protection_level': 'enhanced', 'text': bad_cipher},
        ),
    ]
    fake_db = SimpleNamespace(
        batch=_Batch,
        get_all=lambda refs: docs,
        collection=lambda _name: SimpleNamespace(
            document=lambda _uid: SimpleNamespace(
                collection=lambda _col: SimpleNamespace(document=lambda doc_id: f'ref:{doc_id}')
            )
        ),
    )
    monkeypatch.setattr(chat_db, 'db', fake_db)

    chat_db.migrate_chats_level_batch('u1', ['msg-good', 'msg-bad'], 'standard')

    assert updates == [('ref-good', {'data_protection_level': 'standard', 'text': 'secret message'})]
