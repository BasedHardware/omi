"""Tests for Phase 3: Thread+join elimination (issue #6369).

Verifies that production code no longer uses Thread+join patterns
where ThreadPoolExecutor or asyncio.gather can be used instead.
"""

import ast
import importlib.util
import os
import re
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_lint_module():
    """Load the lint_async_blockers module without executing __main__ block."""
    lint_path = os.path.join(BACKEND_DIR, 'scripts', 'lint_async_blockers.py')
    spec = importlib.util.spec_from_file_location('lint_async_blockers', lint_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _count_thread_join_patterns(filepath: str) -> list:
    """Find Thread+join patterns: list-comp joins and direct .join() on thread variables."""
    with open(filepath) as f:
        source = f.read()

    patterns = []
    # Match list-comprehension join patterns like: [t.join() for t in threads]
    patterns.extend(re.findall(r'\[t\.join\(\)\s+for\s+t\s+in\s+\w+\]', source))
    # Match direct thread.join() calls (e.g. thread.join(), t.join())
    # but exclude string.join() and os.path.join() via context check
    for match in re.finditer(r'(\w+)\.join\(\)', source):
        var_name = match.group(1)
        if var_name in ('thread', 't', 'thr') or var_name.startswith('thread'):
            patterns.append(match.group(0))

    return patterns


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

    def test_rag_uses_shared_executor(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'retrieval', 'rag.py')
        with open(filepath) as f:
            source = f.read()
        assert 'critical_executor' in source

    def test_sync_uses_shared_executor_or_gather(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'sync.py')
        with open(filepath) as f:
            source = f.read()
        assert 'critical_executor' in source or 'storage_executor' in source or 'asyncio.gather' in source

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


class TestAsyncGatherInBackgroundThread:
    """Verify asyncio.gather _batch() wrapper pattern works in background threads."""

    def test_apps_update_personas_async_uses_batch_wrapper(self):
        """apps.py update_personas_async must use async _batch() wrapper for gather."""
        filepath = os.path.join(BACKEND_DIR, 'utils', 'apps.py')
        with open(filepath) as f:
            source = f.read()
        assert 'async def _batch()' in source, "update_personas_async must wrap asyncio.gather in async _batch() helper"
        assert (
            'set_event_loop' in source
        ), "update_personas_async must call asyncio.set_event_loop(loop) before run_until_complete"

    def test_process_conversation_uses_batch_wrapper(self):
        """process_conversation.py _update_personas_async must use async _batch() wrapper."""
        filepath = os.path.join(BACKEND_DIR, 'utils', 'conversations', 'process_conversation.py')
        with open(filepath) as f:
            source = f.read()
        assert (
            'async def _batch()' in source
        ), "_update_personas_async must wrap asyncio.gather in async _batch() helper"
        assert (
            'set_event_loop' in source
        ), "_update_personas_async must call asyncio.set_event_loop(loop) before run_until_complete"

    def test_gather_batch_pattern_works_in_thread(self):
        """Runtime test: asyncio.gather inside _batch() wrapper works from a background thread."""
        import asyncio
        import threading

        results = []
        errors = []

        async def fake_coro(x):
            await asyncio.sleep(0.001)
            return x * 2

        def worker():
            async def _batch():
                return await asyncio.gather(*[fake_coro(i) for i in range(5)])

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results.extend(loop.run_until_complete(_batch()))
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5)

        assert not errors, f"_batch() pattern raised in thread: {errors}"
        assert results == [0, 2, 4, 6, 8], f"Unexpected results: {results}"


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

    def test_stt_async_offloads_file_io(self):
        """Async STT variants should offload file reads via run_in_executor."""
        for filename in ['speaker_embedding.py', 'vad.py', 'speech_profile.py']:
            filepath = os.path.join(BACKEND_DIR, 'utils', 'stt', filename)
            with open(filepath) as f:
                source = f.read()
            assert 'run_in_executor' in source, f"{filename} should offload file I/O via run_in_executor"


class TestAsyncSTTBehavior:
    """Runtime behavior tests for async STT variants."""

    @pytest.mark.asyncio
    async def test_async_extract_embedding_from_bytes_short_audio_rejected(self):
        """Short audio should raise ValueError before any HTTP call."""
        from unittest.mock import patch, AsyncMock

        # 44-byte WAV header with 0 data frames = 0s duration
        short_wav = (
            b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00'
            b'\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00'
            b'\x02\x00\x10\x00data\x00\x00\x00\x00'
        )

        with pytest.raises(ValueError, match="Audio too short"):
            # Import here to avoid module-level side effects
            import importlib

            mod = importlib.import_module('utils.stt.speaker_embedding')
            await mod.async_extract_embedding_from_bytes(short_wav)

    @pytest.mark.asyncio
    async def test_async_vad_local_fallback(self):
        """When hosted VAD URL is unset, async_vad_is_empty should fall back to local VAD."""
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            # Ensure HOSTED_VAD_API_URL is not set
            os.environ.pop('HOSTED_VAD_API_URL', None)
            import importlib

            mod = importlib.import_module('utils.stt.vad')
            # _local_vad should be called via run_in_executor(critical_executor, ...)
            with patch.object(mod, '_local_vad', return_value=[]) as mock_local:
                result = await mod.async_vad_is_empty('/tmp/nonexistent.wav')
                mock_local.assert_called_once_with('/tmp/nonexistent.wav')
                assert result is True  # empty segments = True


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


class TestLintScriptDetection:
    """Verify the lint script detects actual violations and clears clean code."""

    @staticmethod
    def _scan_source(code: str) -> list:
        """Write code to a temp file and run scan_file on it."""
        mod = _load_lint_module()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(textwrap.dedent(code))
            tmp_path = Path(f.name)
        try:
            return mod.scan_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_detects_requests_get_in_async(self):
        """requests.get inside an async function must be a violation."""
        code = """\
            import requests

            async def fetch(url):
                return requests.get(url)
        """
        violations = self._scan_source(code)
        assert len(violations) >= 1, f"Expected at least 1 violation, got: {violations}"
        assert any('requests' in msg for _, msg in violations), f"Expected requests violation, got: {violations}"

    def test_detects_time_sleep_in_async(self):
        """time.sleep() inside an async function must be a violation."""
        code = """\
            import time

            async def pause():
                time.sleep(1)
        """
        violations = self._scan_source(code)
        assert len(violations) >= 1, f"Expected at least 1 violation, got: {violations}"
        assert any('time.sleep' in msg for _, msg in violations), f"Expected time.sleep violation, got: {violations}"

    def test_detects_thread_start_in_async(self):
        """Thread().start() inside an async function must be a violation."""
        code = """\
            from threading import Thread

            async def spawn():
                Thread(target=lambda: None).start()
        """
        violations = self._scan_source(code)
        assert len(violations) >= 1, f"Expected at least 1 violation, got: {violations}"
        assert any('Thread' in msg for _, msg in violations), f"Expected Thread violation, got: {violations}"

    def test_clean_code_has_no_violations(self):
        """Code with no blocking patterns must produce zero violations."""
        code = """\
            import asyncio
            import httpx

            async def fetch(url: str) -> dict:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                return response.json()

            async def pause():
                await asyncio.sleep(1)

            def sync_helper():
                import time
                time.sleep(0.1)  # OK — not in async function
        """
        violations = self._scan_source(code)
        assert violations == [], f"Expected no violations for clean code, got: {violations}"

    def test_sync_function_with_blocking_is_clean(self):
        """Blocking calls in ordinary (non-async) functions must not be flagged."""
        code = """\
            import requests

            def sync_fetch(url):
                return requests.get(url)
        """
        violations = self._scan_source(code)
        assert violations == [], f"Blocking in sync function should not be flagged, got: {violations}"
