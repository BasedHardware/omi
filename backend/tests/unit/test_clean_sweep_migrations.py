"""Tests for clean-sweep async migration fixes (#6369).

Covers:
- routers/memories.py: critical_executor for persona updates (not threading.Thread)
- routers/imports.py: storage_executor for long-running import batch (not critical_executor/Thread)
- utils/other/hume.py: httpx migration with follow_redirects and RequestError handling
- utils/llm/knowledge_graph.py: threading import present, storage_executor for batch rebuild
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
