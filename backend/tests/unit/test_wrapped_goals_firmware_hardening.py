import re
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


@contextmanager
def _wrapped_module_ctx():
    conversations_db_stub = types.ModuleType('database.conversations')
    conversations_db_stub.get_conversations_without_photos = MagicMock(return_value=[])
    action_items_db_stub = types.ModuleType('database.action_items')
    action_items_db_stub.get_action_items = MagicMock(return_value=[])
    wrapped_db_stub = types.ModuleType('database.wrapped')
    wrapped_db_stub.WrappedStatus = types.SimpleNamespace(
        PROCESSING='processing',
        DONE='done',
        ERROR='error',
    )
    wrapped_db_stub.update_wrapped_progress = MagicMock()
    wrapped_db_stub.update_wrapped_status = MagicMock()

    conv_models_stub = types.ModuleType('models.conversation')
    conv_models_stub.Conversation = object
    conv_Enums_stub = types.ModuleType('models.conversation_enums')
    conv_Enums_stub.CategoryEnum = types.SimpleNamespace()

    factory_stub = types.ModuleType('utils.conversations.factory')
    factory_stub.deserialize_conversations = MagicMock(side_effect=lambda items: items)

    llm_clients_stub = types.ModuleType('utils.llm.clients')
    llm_clients_stub.get_llm = MagicMock()

    notifications_stub = types.ModuleType('utils.notifications')
    notifications_stub.send_notification = MagicMock()

    stubs = {
        'database': types.ModuleType('database'),
        'database.conversations': conversations_db_stub,
        'database.action_items': action_items_db_stub,
        'database.wrapped': wrapped_db_stub,
        'models': types.ModuleType('models'),
        'models.conversation': conv_models_stub,
        'models.conversation_enums': conv_Enums_stub,
        'utils': types.ModuleType('utils'),
        'utils.conversations': types.ModuleType('utils.conversations'),
        'utils.conversations.factory': factory_stub,
        'utils.llm': types.ModuleType('utils.llm'),
        'utils.llm.clients': llm_clients_stub,
        'utils.notifications': notifications_stub,
    }
    with stub_modules(stubs):
        yield load_module_fresh(
            'wrapped_generate_2025_under_test',
            str(BACKEND_DIR / 'utils' / 'wrapped' / 'generate_2025.py'),
        )


@contextmanager
def _goals_llm_module_ctx():
    goals_db_stub = types.ModuleType('database.goals')
    goals_db_stub.get_goal_by_id = MagicMock(return_value=None)
    goals_db_stub.get_user_goals = MagicMock(return_value=[])
    goals_db_stub.update_goal_progress = MagicMock()

    conversations_db_stub = types.ModuleType('database.conversations')
    conversations_db_stub.get_conversations_by_id = MagicMock(return_value=[])
    conversations_db_stub.get_conversations = MagicMock(return_value=[])

    chat_db_stub = types.ModuleType('database.chat')
    chat_db_stub.get_messages = MagicMock(return_value=[])

    client_stub = types.ModuleType('database._client')
    client_stub.db = MagicMock()

    vector_db_stub = types.ModuleType('database.vector_db')
    vector_db_stub.query_vectors = MagicMock(return_value=[])

    llm_clients_stub = types.ModuleType('utils.llm.clients')
    llm_clients_stub.get_llm = MagicMock()

    @contextmanager
    def _track_usage(*args, **kwargs):
        yield

    usage_tracker_stub = types.ModuleType('utils.llm.usage_tracker')
    usage_tracker_stub.track_usage = _track_usage
    usage_tracker_stub.Features = types.SimpleNamespace(GOALS='goals')

    memory_service_stub = types.ModuleType('utils.memory.memory_service')
    memory_service_stub.MemoryService = MagicMock()

    stubs = {
        'database': types.ModuleType('database'),
        'database.goals': goals_db_stub,
        'database.conversations': conversations_db_stub,
        'database.chat': chat_db_stub,
        'database._client': client_stub,
        'database.vector_db': vector_db_stub,
        'utils': types.ModuleType('utils'),
        'utils.llm': types.ModuleType('utils.llm'),
        'utils.llm.clients': llm_clients_stub,
        'utils.llm.usage_tracker': usage_tracker_stub,
        'utils.memory': types.ModuleType('utils.memory'),
        'utils.memory.memory_service': memory_service_stub,
    }
    with stub_modules(stubs):
        yield load_module_fresh(
            'goals_llm_under_test',
            str(BACKEND_DIR / 'utils' / 'llm' / 'goals.py'),
        )


@contextmanager
def _firmware_module_ctx():
    gh_releases_stub = types.ModuleType('utils.github_releases')
    gh_releases_stub.get_omi_github_releases = AsyncMock(return_value=[])

    def _extract_kv(body):
        if not body:
            return {}
        out = {}
        for match in re.finditer(r'<!--\s*KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END\s*-->', body, re.DOTALL):
            for line in match.group(1).split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    out[k.strip()] = v.strip()
        return out

    gh_releases_stub.extract_key_value_pairs = _extract_kv
    stubs = {
        'utils': types.ModuleType('utils'),
        'utils.github_releases': gh_releases_stub,
    }
    with stub_modules(stubs):
        yield load_module_fresh(
            'firmware_router_under_test',
            str(BACKEND_DIR / 'routers' / 'firmware.py'),
        )


@contextmanager
def _github_releases_module_ctx():
    redis_stub = types.ModuleType('database.redis_db')
    redis_stub.get_generic_cache = MagicMock(return_value=None)
    redis_stub.set_generic_cache = MagicMock()

    executors_stub = types.ModuleType('utils.executors')
    executors_stub.db_executor = MagicMock()

    async def _run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    executors_stub.run_blocking = _run_blocking

    http_client_stub = types.ModuleType('utils.http_client')
    http_client_stub.get_web_fetch_client = MagicMock()

    log_sanitizer_stub = types.ModuleType('utils.log_sanitizer')
    log_sanitizer_stub.sanitize = lambda s: s

    stubs = {
        'database': types.ModuleType('database'),
        'database.redis_db': redis_stub,
        'utils': types.ModuleType('utils'),
        'utils.executors': executors_stub,
        'utils.http_client': http_client_stub,
        'utils.log_sanitizer': log_sanitizer_stub,
    }
    with stub_modules(stubs):
        yield load_module_fresh(
            'github_releases_under_test',
            str(BACKEND_DIR / 'utils' / 'github_releases.py'),
        )


def test_wrapped_duration_handles_none_and_non_numeric_end():
    with _wrapped_module_ctx() as mod:
        seg1 = types.SimpleNamespace(end=None)
        seg2 = types.SimpleNamespace(end=True)
        seg3 = types.SimpleNamespace(end=125.5)
        conv = types.SimpleNamespace(
            transcript_segments=[seg1, seg2, seg3],
            started_at=None,
            finished_at=None,
        )
        assert mod._compute_conversation_duration(conv) == 125.5

        conv_only_none = types.SimpleNamespace(
            transcript_segments=[seg1],
            started_at=datetime(2025, 5, 1, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2025, 5, 1, 10, 5, tzinfo=timezone.utc),
        )
        assert mod._compute_conversation_duration(conv_only_none) == 300.0


def test_wrapped_excludes_locked_conversations_and_action_items():
    with _wrapped_module_ctx() as mod:
        unlocked_seg = types.SimpleNamespace(is_user=True, text='let us ship it', end=60.0)
        locked_seg = types.SimpleNamespace(is_user=True, text='secret passphrase phrase', end=120.0)

        unlocked_conv = types.SimpleNamespace(
            id='c-unlocked',
            is_locked=False,
            created_at=datetime(2025, 6, 10, 12, 0, tzinfo=timezone.utc),
            started_at=None,
            finished_at=None,
            transcript_segments=[unlocked_seg],
            structured=types.SimpleNamespace(
                title='Public sprint planning',
                overview='Discussed shipping the new release',
                category=types.SimpleNamespace(value='work'),
            ),
        )
        locked_conv = types.SimpleNamespace(
            id='c-locked',
            is_locked=True,
            created_at=datetime(2025, 6, 11, 12, 0, tzinfo=timezone.utc),
            started_at=None,
            finished_at=None,
            transcript_segments=[locked_seg],
            structured=types.SimpleNamespace(
                title='Secret diary entry',
                overview='Confidential personal notes',
                category=types.SimpleNamespace(value='personal'),
            ),
        )

        context = mod._build_conversations_context([unlocked_conv, locked_conv])
        assert 'Public sprint planning' in context
        assert 'Secret diary entry' not in context
        assert 'Confidential personal notes' not in context

        phrases = mod._find_signature_phrases(
            [unlocked_conv, locked_conv, locked_conv, locked_conv],
        )
        assert 'secret' not in phrases.get('phrase', '')

        mod.conversations_db.get_conversations_without_photos.return_value = [
            {'id': 'c-unlocked', 'is_locked': False, '_obj': unlocked_conv},
            {'id': 'c-locked', 'is_locked': True, '_obj': locked_conv},
        ]
        mod.deserialize_conversations.side_effect = lambda items: [i['_obj'] for i in items]
        mod.action_items_db.get_action_items.return_value = [
            {'id': 'a1', 'completed': True, 'is_locked': False},
            {'id': 'a2', 'completed': True, 'is_locked': True},
            {'id': 'a3', 'completed': False, 'is_locked': True},
        ]
        mod.get_llm.return_value = MagicMock(
            invoke=MagicMock(return_value=types.SimpleNamespace(content='{"most_fun_day": null, "struggle": null}'))
        )

        mod.generate_wrapped_2025('user-1', 2025)

        mod.wrapped_db.update_wrapped_status.assert_called_once()
        args, kwargs = mod.wrapped_db.update_wrapped_status.call_args
        assert args[2] == mod.wrapped_db.WrappedStatus.DONE
        saved_result = kwargs['result']
        assert saved_result['total_conversations'] == 1
        assert saved_result['total_action_items'] == 1
        assert saved_result['completed_action_items'] == 1
        assert isinstance(saved_result['memorable_days']['most_fun_day'], dict)
        assert isinstance(saved_result['struggle'], dict)
        assert isinstance(saved_result['personal_win'], dict)


def test_goal_advice_handles_qualitative_goals():
    with _goals_llm_module_ctx() as mod:
        mod.goals_db.get_goal_by_id.return_value = {
            'id': 'g-1',
            'title': 'Be more mindful',
            'is_active': True,
            'current_value': None,
            'target_value': None,
        }
        llm_mock = MagicMock()
        llm_mock.invoke.return_value = types.SimpleNamespace(content='"Take 5 minutes to meditate each morning."')
        mod.get_llm.return_value = llm_mock

        advice = mod.get_goal_advice('uid-1', 'g-1')
        assert advice == 'Take 5 minutes to meditate each morning.'
        prompt_arg = llm_mock.invoke.call_args[0][0]
        assert 'Qualitative goal (no numeric metric)' in prompt_arg


def test_suggest_goal_skips_llm_when_all_memories_locked_and_sanitizes_null_fields():
    with _goals_llm_module_ctx() as mod:
        locked_mem = MagicMock()
        locked_mem.dict.return_value = {'content': 'Private secret', 'is_locked': True}
        service_instance = MagicMock()
        service_instance.read.return_value = [locked_mem]
        mod.MemoryService.return_value = service_instance

        llm_mock = MagicMock()
        mod.get_llm.return_value = llm_mock

        res = mod.suggest_goal('uid-locked')
        assert res['suggested_title'] == 'Learn something new every day'
        llm_mock.invoke.assert_not_called()

        unlocked_mem = MagicMock()
        unlocked_mem.dict.return_value = {'content': 'Training for a marathon', 'is_locked': False}
        service_instance.read.return_value = [unlocked_mem]
        llm_mock.invoke.return_value = types.SimpleNamespace(
            content='{"suggested_title": "Run 3x weekly", "suggested_type": "numeric", "suggested_target": null, "suggested_min": null, "suggested_max": null, "reasoning": null}'
        )

        res2 = mod.suggest_goal('uid-unlocked')
        assert res2['suggested_title'] == 'Run 3x weekly'
        assert res2['suggested_target'] == 10.0
        assert res2['suggested_min'] == 0.0
        assert res2['suggested_max'] == 10.0
        assert isinstance(res2['reasoning'], str) and len(res2['reasoning']) > 0


def test_firmware_version_parsing_and_candidate_filtering():
    with _firmware_module_ctx() as mod:
        assert mod._parse_firmware_version(' v2.1.3 \x00 ') == (2, 1, 3)
        assert mod._parse_firmware_version('-1.0.0') is None
        assert mod._parse_firmware_version('2.-1.0') is None
        assert mod._parse_firmware_version('   \x00  ') is None

        releases = [
            {
                'tag_name': 'Omi_CV1_v3.0.15',
                'draft': False,
                'prerelease': False,
                'published_at': '2026-09-01T00:00:00Z',
                'body': '<!-- KEY_VALUE_START\nrelease_firmware_version: invalid_ver\nKEY_VALUE_END -->',
            },
            {
                'tag_name': 'Omi_CV1_v3.0.14',
                'draft': False,
                'prerelease': False,
                'published_at': '2026-08-01T00:00:00Z',
                'body': '<!-- KEY_VALUE_START\nrelease_firmware_version: v3.0.14\nKEY_VALUE_END -->',
            },
        ]
        candidates = mod._find_candidate_releases(releases, 'Omi_CV1', current_firmware_tuple=None)
        assert len(candidates) == 1
        assert candidates[0]['tag_name'] == 'Omi_CV1_v3.0.14'


@pytest.mark.asyncio
async def test_github_releases_handles_null_tag_name():
    with _github_releases_module_ctx() as mod:
        page_payload = [
            {'tag_name': None, 'id': 1},
            {'tag_name': 'Omi_CV1_v3.0.14', 'id': 2},
        ]
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = page_payload

        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        mod.get_web_fetch_client.return_value = client

        pattern = re.compile(r'^Omi_CV1_v[0-9]+(?:\.[0-9]+){1,2}$')
        res = await mod.get_omi_github_releases('github_releases_omi', tag_filter=pattern)
        assert len(res) == 1
        assert res[0]['id'] == 2
