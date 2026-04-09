"""Tests for clean-sweep async migration fixes (#6369).

Covers round 1:
- routers/memories.py: critical_executor for persona updates (not threading.Thread)
- routers/imports.py: storage_executor for long-running import batch (not critical_executor/Thread)
- utils/other/hume.py: httpx migration with follow_redirects and RequestError handling
- utils/llm/knowledge_graph.py: threading import present, storage_executor for batch rebuild

Covers round 2:
- routers/sync.py: requests → httpx for audio download
- utils/app_integrations.py: requests → httpx for GitHub docs
- utils/stt/speaker_embedding.py: requests → httpx for embedding API
- utils/stt/vad.py: requests → httpx for hosted VAD
- utils/stt/speech_profile.py: requests → httpx for speech profile matching
- utils/conversations/location.py: requests → httpx for Google Maps geocoding

Covers round 3:
- routers/action_items.py: threading.Thread → critical_executor
- routers/calendar_onboarding.py: requests → httpx, threading → critical_executor
- routers/chat.py: threading.Thread → critical_executor for goal progress
- routers/developer.py: threading.Thread → critical_executor for persona update
- routers/mcp.py: threading.Thread → critical_executor for persona update
- routers/wrapped.py: threading.Thread → critical_executor for wrapped generation
- utils/chat.py: threading.Thread → storage_executor for file cleanup
- utils/conversations/postprocess_conversation.py: threading.Thread → storage_executor
- utils/other/notifications.py: threading.Thread → critical_executor for webhooks
- utils/other/storage.py: ad-hoc ThreadPoolExecutor → storage_executor
- utils/retrieval/tools/calendar_tools.py: requests → httpx, time.sleep → asyncio.sleep
- utils/retrieval/tools/google_utils.py: requests → httpx for OAuth refresh
- utils/retrieval/tools/perplexity_tools.py: requests → httpx async for web search
"""

import inspect
import os
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_source(rel_path: str) -> str:
    """Read source file directly to avoid import-time side effects (Firestore init, etc.)."""
    with open(os.path.join(BACKEND_DIR, rel_path)) as f:
        return f.read()


class TestMemoriesExecutorMigration:
    """Verify memories router uses critical_executor for persona updates."""

    def test_create_memory_uses_critical_executor(self):
        """create_memory route dispatches persona update via critical_executor."""
        src = _read_source('routers/memories.py')
        assert 'critical_executor.submit(update_personas_async' in src

    def test_update_visibility_uses_critical_executor(self):
        """update_memory_visibility uses critical_executor, not threading.Thread."""
        src = _read_source('routers/memories.py')
        # Find the update_memory_visibility function and check its body
        func_start = src.index('def update_memory_visibility')
        func_body = src[func_start : func_start + 500]
        assert 'critical_executor.submit(update_personas_async' in func_body

    def test_no_threading_thread_in_memories(self):
        """No bare threading.Thread usage in memories router."""
        src = _read_source('routers/memories.py')
        assert 'threading.Thread' not in src


class TestImportsExecutorMigration:
    """Verify imports router uses storage_executor for batch import work."""

    def test_import_uses_storage_executor(self):
        """Limitless import dispatched to storage_executor (batch I/O, not latency-sensitive)."""
        src = _read_source('routers/imports.py')
        assert 'storage_executor.submit(process_limitless_import' in src

    def test_import_does_not_use_critical_executor(self):
        """Long-running import must not use critical_executor (would starve request-path)."""
        src = _read_source('routers/imports.py')
        assert 'critical_executor' not in src

    def test_no_threading_thread_in_imports(self):
        """No bare threading.Thread usage in imports router."""
        src = _read_source('routers/imports.py')
        assert 'threading.Thread' not in src


class TestHumeHttpxMigration:
    """Verify Hume client uses httpx, not requests."""

    def test_hume_uses_httpx_not_requests(self):
        """HumeClient should import httpx, not requests."""
        src = _read_source('utils/other/hume.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_hume_uses_follow_redirects(self):
        """httpx.post call must include follow_redirects=True (requests follows by default)."""
        src = _read_source('utils/other/hume.py')
        assert 'follow_redirects=True' in src

    def test_hume_catches_request_error(self):
        """Exception handler should catch httpx.RequestError (closest to requests.RequestException)."""
        src = _read_source('utils/other/hume.py')
        assert 'httpx.RequestError' in src

    def test_hume_catches_timeout(self):
        """Exception handler should catch httpx.TimeoutException."""
        src = _read_source('utils/other/hume.py')
        assert 'httpx.TimeoutException' in src

    def test_hume_catches_too_many_redirects(self):
        """Exception handler should catch httpx.TooManyRedirects."""
        src = _read_source('utils/other/hume.py')
        assert 'httpx.TooManyRedirects' in src


class TestKnowledgeGraphMigration:
    """Verify knowledge_graph uses threading import and storage_executor for batch rebuild."""

    def test_threading_imported(self):
        """threading module must be imported (needed for Lock in rebuild)."""
        src = _read_source('utils/llm/knowledge_graph.py')
        assert 'import threading' in src

    def test_rebuild_uses_threading_lock(self):
        """rebuild_knowledge_graph must use threading.Lock for node coordination."""
        src = _read_source('utils/llm/knowledge_graph.py')
        func_start = src.index('def rebuild_knowledge_graph')
        func_body = src[func_start:]
        assert 'threading.Lock()' in func_body

    def test_rebuild_uses_storage_executor(self):
        """Batch rebuild must use storage_executor (not critical_executor)."""
        src = _read_source('utils/llm/knowledge_graph.py')
        func_start = src.index('def rebuild_knowledge_graph')
        func_body = src[func_start:]
        assert 'storage_executor.submit' in func_body

    def test_rebuild_does_not_use_critical_executor(self):
        """Batch rebuild must not use critical_executor (would monopolize request-path)."""
        src = _read_source('utils/llm/knowledge_graph.py')
        func_start = src.index('def rebuild_knowledge_graph')
        func_body = src[func_start:]
        assert 'critical_executor' not in func_body

    def test_module_imports_both_executors(self):
        """Module imports both critical_executor (single extraction) and storage_executor (batch)."""
        src = _read_source('utils/llm/knowledge_graph.py')
        assert 'critical_executor' in src
        assert 'storage_executor' in src


# Round 2: requests → httpx migrations in 6 more files


class TestSyncHttpxMigration:
    """Verify sync router uses httpx, not requests."""

    def test_sync_uses_httpx(self):
        src = _read_source('routers/sync.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_download_audio_uses_httpx_get(self):
        src = _read_source('routers/sync.py')
        assert 'httpx.get(' in src

    def test_download_audio_has_float_timeout(self):
        src = _read_source('routers/sync.py')
        assert 'timeout=60.0' in src


class TestAppIntegrationsHttpxMigration:
    """Verify app_integrations uses httpx, not requests."""

    def test_app_integrations_uses_httpx(self):
        src = _read_source('utils/app_integrations.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_github_docs_uses_httpx_get(self):
        src = _read_source('utils/app_integrations.py')
        assert 'httpx.get(' in src


class TestSpeakerEmbeddingHttpxMigration:
    """Verify speaker_embedding sync functions use httpx, not requests."""

    def test_speaker_embedding_uses_httpx(self):
        src = _read_source('utils/stt/speaker_embedding.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_extract_embedding_uses_httpx_post(self):
        src = _read_source('utils/stt/speaker_embedding.py')
        assert 'httpx.post(' in src

    def test_extract_embedding_has_float_timeout(self):
        src = _read_source('utils/stt/speaker_embedding.py')
        assert 'timeout=300.0' in src


class TestVadHttpxMigration:
    """Verify VAD sync functions use httpx, not requests."""

    def test_vad_uses_httpx(self):
        src = _read_source('utils/stt/vad.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_vad_hosted_uses_httpx_post(self):
        src = _read_source('utils/stt/vad.py')
        assert 'httpx.post(' in src

    def test_vad_has_float_timeout(self):
        src = _read_source('utils/stt/vad.py')
        assert 'timeout=300.0' in src


class TestSpeechProfileHttpxMigration:
    """Verify speech_profile sync functions use httpx, not requests."""

    def test_speech_profile_uses_httpx(self):
        src = _read_source('utils/stt/speech_profile.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_speech_profile_uses_httpx_post(self):
        src = _read_source('utils/stt/speech_profile.py')
        assert 'httpx.post(' in src


class TestLocationHttpxMigration:
    """Verify location geocoding uses httpx, not requests."""

    def test_location_uses_httpx(self):
        src = _read_source('utils/conversations/location.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_location_uses_httpx_get(self):
        src = _read_source('utils/conversations/location.py')
        assert 'httpx.get(' in src


# Round 3: threading.Thread → executor and more requests → httpx


class TestActionItemsExecutorMigration:
    """Verify action_items uses critical_executor, not threading.Thread."""

    def test_no_threading_thread(self):
        src = _read_source('routers/action_items.py')
        assert 'threading.Thread' not in src

    def test_uses_critical_executor(self):
        src = _read_source('routers/action_items.py')
        assert 'critical_executor.submit(' in src


class TestCalendarOnboardingMigration:
    """Verify calendar_onboarding uses httpx and critical_executor."""

    def test_uses_httpx(self):
        src = _read_source('routers/calendar_onboarding.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_no_threading_thread(self):
        src = _read_source('routers/calendar_onboarding.py')
        assert 'threading.Thread' not in src

    def test_uses_critical_executor(self):
        src = _read_source('routers/calendar_onboarding.py')
        assert 'critical_executor' in src


class TestChatExecutorMigration:
    """Verify chat router uses critical_executor for goal progress."""

    def test_no_threading_thread(self):
        src = _read_source('routers/chat.py')
        assert 'threading.Thread' not in src

    def test_uses_critical_executor(self):
        src = _read_source('routers/chat.py')
        assert 'critical_executor.submit(' in src


class TestDeveloperExecutorMigration:
    """Verify developer router uses critical_executor for persona update."""

    def test_no_threading_thread(self):
        src = _read_source('routers/developer.py')
        assert 'threading.Thread' not in src

    def test_uses_critical_executor(self):
        src = _read_source('routers/developer.py')
        assert 'critical_executor.submit(' in src


class TestMcpExecutorMigration:
    """Verify mcp router uses critical_executor for persona update."""

    def test_no_threading_thread(self):
        src = _read_source('routers/mcp.py')
        assert 'threading.Thread' not in src

    def test_uses_critical_executor(self):
        src = _read_source('routers/mcp.py')
        assert 'critical_executor.submit(' in src


class TestWrappedExecutorMigration:
    """Verify wrapped router uses critical_executor."""

    def test_no_threading_thread(self):
        src = _read_source('routers/wrapped.py')
        assert 'threading.Thread' not in src

    def test_uses_critical_executor(self):
        src = _read_source('routers/wrapped.py')
        assert 'critical_executor' in src


class TestChatUtilsExecutorMigration:
    """Verify utils/chat.py uses storage_executor for file cleanup."""

    def test_no_threading_thread(self):
        src = _read_source('utils/chat.py')
        assert 'threading.Thread' not in src

    def test_uses_storage_executor(self):
        src = _read_source('utils/chat.py')
        assert 'storage_executor.submit(' in src


class TestPostprocessExecutorMigration:
    """Verify postprocess_conversation uses storage_executor for audio cleanup."""

    def test_no_threading_thread(self):
        src = _read_source('utils/conversations/postprocess_conversation.py')
        assert 'threading.Thread' not in src

    def test_uses_storage_executor(self):
        src = _read_source('utils/conversations/postprocess_conversation.py')
        assert 'storage_executor.submit(' in src


class TestNotificationsExecutorMigration:
    """Verify notifications uses critical_executor, not threading.Thread."""

    def test_no_threading_thread(self):
        src = _read_source('utils/other/notifications.py')
        assert 'threading.Thread' not in src

    def test_uses_critical_executor(self):
        src = _read_source('utils/other/notifications.py')
        assert 'critical_executor' in src


class TestStorageExecutorMigration:
    """Verify storage uses storage_executor, not ad-hoc ThreadPoolExecutor."""

    def test_no_ad_hoc_thread_pool_executor(self):
        src = _read_source('utils/other/storage.py')
        assert 'ThreadPoolExecutor(' not in src

    def test_uses_storage_executor(self):
        src = _read_source('utils/other/storage.py')
        assert 'storage_executor' in src


class TestCalendarToolsHttpxMigration:
    """Verify calendar_tools uses httpx and asyncio.sleep."""

    def test_uses_httpx(self):
        src = _read_source('utils/retrieval/tools/calendar_tools.py')
        assert 'import httpx' in src
        assert 'import requests' not in src

    def test_no_time_sleep(self):
        src = _read_source('utils/retrieval/tools/calendar_tools.py')
        assert 'time.sleep' not in src


class TestGoogleUtilsHttpxMigration:
    """Verify google_utils uses httpx, not requests."""

    def test_uses_httpx(self):
        src = _read_source('utils/retrieval/tools/google_utils.py')
        assert 'import httpx' in src
        assert 'import requests' not in src


class TestPerplexityHttpxMigration:
    """Verify perplexity_tools uses httpx, not requests."""

    def test_uses_httpx(self):
        src = _read_source('utils/retrieval/tools/perplexity_tools.py')
        assert 'import httpx' in src
        assert 'import requests' not in src


class TestNoRequestsInProductionCode:
    """Global check: zero import requests in non-test, non-script production code."""

    def test_no_import_requests_in_routers(self):
        routers_dir = os.path.join(BACKEND_DIR, 'routers')
        for fname in os.listdir(routers_dir):
            if fname.endswith('.py'):
                src = _read_source(f'routers/{fname}')
                assert 'import requests' not in src, f'routers/{fname} still imports requests'

    def test_no_import_requests_in_utils(self):
        for root, dirs, files in os.walk(os.path.join(BACKEND_DIR, 'utils')):
            for fname in files:
                if fname.endswith('.py'):
                    rel = os.path.relpath(os.path.join(root, fname), BACKEND_DIR)
                    src = _read_source(rel)
                    assert 'import requests' not in src, f'{rel} still imports requests'

    def test_no_threading_thread_start_in_routers(self):
        routers_dir = os.path.join(BACKEND_DIR, 'routers')
        for fname in os.listdir(routers_dir):
            if fname.endswith('.py'):
                src = _read_source(f'routers/{fname}')
                assert 'threading.Thread(' not in src, f'routers/{fname} still uses threading.Thread'
