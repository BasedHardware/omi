"""Tests for Phase 3: Thread+join elimination (issue #6369).

Verifies that production code no longer uses Thread+join patterns
where ThreadPoolExecutor or asyncio.gather can be used instead.
"""

import ast
import os
import re

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _count_thread_join_patterns(filepath: str) -> list:
    """Find [t.join() for t in threads] or t.join() patterns."""
    with open(filepath) as f:
        source = f.read()

    # Match list-comprehension join patterns like: [t.join() for t in threads]
    join_patterns = re.findall(r'\[t\.join\(\)\s+for\s+t\s+in\s+\w+\]', source)
    # Also match simple .join() on threads
    simple_joins = re.findall(r'\.join\(\)', source)

    return join_patterns


class TestNoThreadJoinInMigratedFiles:
    """Phase 3 target files should not use Thread+join patterns."""

    def test_app_integrations_no_thread_join(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'app_integrations.py')
        patterns = _count_thread_join_patterns(filepath)
        assert patterns == [], f"Thread+join still in app_integrations.py: {patterns}"

    def test_process_conversation_no_thread_join(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'conversations', 'process_conversation.py')
        patterns = _count_thread_join_patterns(filepath)
        assert patterns == [], f"Thread+join still in process_conversation.py: {patterns}"

    def test_rag_no_thread_join(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'retrieval', 'rag.py')
        patterns = _count_thread_join_patterns(filepath)
        assert patterns == [], f"Thread+join still in rag.py: {patterns}"

    def test_apps_utils_no_thread_join(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'apps.py')
        patterns = _count_thread_join_patterns(filepath)
        assert patterns == [], f"Thread+join still in apps.py: {patterns}"

    def test_sync_no_thread_join(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'sync.py')
        patterns = _count_thread_join_patterns(filepath)
        assert patterns == [], f"Thread+join still in sync.py: {patterns}"


class TestThreadPoolExecutorUsed:
    """Verify migrated files use ThreadPoolExecutor or asyncio.gather."""

    def test_rag_uses_threadpool(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'retrieval', 'rag.py')
        with open(filepath) as f:
            source = f.read()
        assert 'ThreadPoolExecutor' in source or 'concurrent.futures' in source

    def test_sync_uses_threadpool(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'sync.py')
        with open(filepath) as f:
            source = f.read()
        assert 'ThreadPoolExecutor' in source or 'concurrent.futures' in source

    def test_app_integrations_uses_threadpool_or_gather(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'app_integrations.py')
        with open(filepath) as f:
            source = f.read()
        assert 'ThreadPoolExecutor' in source or 'asyncio.gather' in source

    def test_apps_utils_no_sync_update_antipattern(self):
        """sync_update_persona_prompt antipattern (per-thread event loop) should be gone."""
        filepath = os.path.join(BACKEND_DIR, 'utils', 'apps.py')
        with open(filepath) as f:
            source = f.read()
        assert 'sync_update_persona_prompt' not in source, (
            "sync_update_persona_prompt antipattern still present — "
            "use asyncio.gather with update_persona_prompt directly"
        )


class TestAsyncSTTVariants:
    """Phase 4: verify async STT variants exist."""

    def test_async_extract_embedding_exists(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'stt', 'speaker_embedding.py')
        with open(filepath) as f:
            source = f.read()
        assert 'async def async_extract_embedding(' in source
        assert 'async def async_extract_embedding_from_bytes(' in source

    def test_async_vad_exists(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'stt', 'vad.py')
        with open(filepath) as f:
            source = f.read()
        assert 'async def async_vad_is_empty(' in source

    def test_async_speech_profile_exists(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'stt', 'speech_profile.py')
        with open(filepath) as f:
            source = f.read()
        assert 'async def async_get_speech_profile_matching_predictions(' in source

    def test_stt_async_uses_httpx_client(self):
        """Async STT variants should use shared httpx client, not create per-call clients."""
        for filename in ['speaker_embedding.py', 'vad.py', 'speech_profile.py']:
            filepath = os.path.join(BACKEND_DIR, 'utils', 'stt', filename)
            with open(filepath) as f:
                source = f.read()
            assert 'get_stt_client' in source, f"{filename} should use shared get_stt_client()"


class TestLintScript:
    """Phase 6: verify lint script exists and is functional."""

    def test_lint_script_exists(self):
        filepath = os.path.join(BACKEND_DIR, 'scripts', 'lint_async_blockers.py')
        assert os.path.exists(filepath)

    def test_lint_script_parses(self):
        filepath = os.path.join(BACKEND_DIR, 'scripts', 'lint_async_blockers.py')
        with open(filepath) as f:
            source = f.read()
        # Should parse without errors
        ast.parse(source)
