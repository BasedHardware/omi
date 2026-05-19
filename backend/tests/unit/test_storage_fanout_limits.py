"""Tests for bounded fan-out concurrency limits in storage operations (#7387).

Verifies that storage_executor submissions are gated by semaphores to prevent
queue spikes from unbounded parallel chunk downloads and audio file precaching.

Source-level tests (no heavy module imports) — checks code structure, not runtime.
"""

import os


def _read_source(rel_path):
    base = os.path.join(os.path.dirname(__file__), '..', '..')
    with open(os.path.join(base, rel_path)) as f:
        return f.read()


class TestChunkDownloadSlidingWindow:
    """download_audio_chunks_and_merge must use a sliding window, not submit all at once."""

    def test_chunk_semaphore_exists_at_module_level(self):
        """Module must define _STORAGE_CHUNK_SEM."""
        src = _read_source('utils/other/storage.py')
        assert '_STORAGE_CHUNK_SEM' in src
        assert 'BoundedSemaphore' in src

    def test_chunk_window_size_defined(self):
        """Module must define _CHUNK_WINDOW_SIZE = 8."""
        src = _read_source('utils/other/storage.py')
        assert '_CHUNK_WINDOW_SIZE = 8' in src

    def test_global_chunk_semaphore_is_32(self):
        """Global chunk semaphore must be BoundedSemaphore(32)."""
        src = _read_source('utils/other/storage.py')
        assert 'BoundedSemaphore(32)' in src

    def test_sliding_window_uses_wait_first_completed(self):
        """download_audio_chunks_and_merge must use FIRST_COMPLETED wait for sliding window."""
        src = _read_source('utils/other/storage.py')
        assert 'FIRST_COMPLETED' in src
        func_start = src.index('def download_audio_chunks_and_merge')
        next_def = src.index('\ndef ', func_start + 1)
        func_body = src[func_start:next_def]
        assert 'FIRST_COMPLETED' in func_body

    def test_chunk_sem_acquired_before_submit(self):
        """Chunk semaphore must be acquired before storage_executor.submit, not inside the task."""
        src = _read_source('utils/other/storage.py')
        func_start = src.index('def download_audio_chunks_and_merge')
        next_def = src.index('\ndef ', func_start + 1)
        func_body = src[func_start:next_def]
        assert '_STORAGE_CHUNK_SEM.acquire()' in func_body

    def test_chunk_sem_released_in_done_callback(self):
        """Chunk semaphore must be released via done callback for exception safety."""
        src = _read_source('utils/other/storage.py')
        func_start = src.index('def download_audio_chunks_and_merge')
        next_def = src.index('\ndef ', func_start + 1)
        func_body = src[func_start:next_def]
        assert '_STORAGE_CHUNK_SEM.release()' in func_body
        assert 'add_done_callback' in func_body

    def test_no_unbounded_dict_comprehension_submit(self):
        """Old pattern of submitting all futures via dict comprehension must be gone."""
        src = _read_source('utils/other/storage.py')
        func_start = src.index('def download_audio_chunks_and_merge')
        next_def = src.index('\ndef ', func_start + 1)
        func_body = src[func_start:next_def]
        assert 'storage_executor.submit(download_single_chunk, ts): ts for ts' not in func_body
        assert '{storage_executor.submit' not in func_body

    def test_combined_job_stream(self):
        """Individual chunks and batch blobs must be treated as one job stream."""
        src = _read_source('utils/other/storage.py')
        func_start = src.index('def download_audio_chunks_and_merge')
        next_def = src.index('\ndef ', func_start + 1)
        func_body = src[func_start:next_def]
        assert "('individual'" in func_body or "('batch'" in func_body


class TestPrecacheFileSemaphore:
    """Audio file precache operations must be gated by _PRECACHE_FILE_SEM."""

    def test_precache_file_semaphore_exists(self):
        """Module must define _PRECACHE_FILE_SEM."""
        src = _read_source('utils/other/storage.py')
        assert '_PRECACHE_FILE_SEM' in src

    def test_precache_file_semaphore_is_4(self):
        """Global precache file semaphore must be BoundedSemaphore(4)."""
        src = _read_source('utils/other/storage.py')
        assert 'BoundedSemaphore(4)' in src

    def test_precache_conversation_audio_uses_semaphore(self):
        """precache_conversation_audio must gate submissions with _PRECACHE_FILE_SEM."""
        src = _read_source('utils/other/storage.py')
        func_start = src.index('def precache_conversation_audio')
        next_def_idx = src.find('\ndef ', func_start + 1)
        if next_def_idx == -1:
            func_body = src[func_start:]
        else:
            func_body = src[func_start:next_def_idx]
        assert '_PRECACHE_FILE_SEM.acquire()' in func_body
        assert '_PRECACHE_FILE_SEM.release()' in func_body

    def test_precache_sem_released_on_submit_failure(self):
        """Semaphore must be released in except block if submit() raises."""
        src = _read_source('utils/other/storage.py')
        func_start = src.index('def precache_conversation_audio')
        next_def_idx = src.find('\ndef ', func_start + 1)
        if next_def_idx == -1:
            func_body = src[func_start:]
        else:
            func_body = src[func_start:next_def_idx]
        acquire_idx = func_body.index('_PRECACHE_FILE_SEM.acquire()')
        except_block = func_body[acquire_idx:]
        assert 'except' in except_block
        release_after_except = except_block.index('except')
        assert '_PRECACHE_FILE_SEM.release()' in except_block[release_after_except:]


class TestPrecacheSyncImport:
    """sync.py must import and use _PRECACHE_FILE_SEM from storage."""

    def test_sync_imports_precache_file_sem(self):
        """routers/sync.py must import _PRECACHE_FILE_SEM."""
        src = _read_source('routers/sync.py')
        assert '_PRECACHE_FILE_SEM' in src

    def test_sync_precache_all_uses_semaphore(self):
        """_precache_all_parallel in sync.py must reference _PRECACHE_FILE_SEM."""
        src = _read_source('routers/sync.py')
        func_start = src.index('def _precache_all_parallel')
        func_body = src[func_start : func_start + 600]
        assert '_PRECACHE_FILE_SEM' in func_body

    def test_sync_cache_uncached_uses_semaphore(self):
        """_cache_uncached_parallel in sync.py must reference _PRECACHE_FILE_SEM."""
        src = _read_source('routers/sync.py')
        func_start = src.index('def _cache_uncached_parallel')
        func_body = src[func_start : func_start + 600]
        assert '_PRECACHE_FILE_SEM' in func_body


class TestKGRebuildExecutorAndSemaphore:
    """rebuild_knowledge_graph must use llm_executor with bounded concurrency."""

    def test_kg_uses_llm_executor(self):
        """KG rebuild must submit to llm_executor, not storage_executor."""
        src = _read_source('utils/llm/knowledge_graph.py')
        func_start = src.index('def rebuild_knowledge_graph')
        func_body = src[func_start:]
        assert 'llm_executor.submit' in func_body
        assert 'storage_executor' not in func_body

    def test_kg_rebuild_semaphore_defined(self):
        """KG module must define _KG_REBUILD_SEM as BoundedSemaphore(4)."""
        src = _read_source('utils/llm/knowledge_graph.py')
        assert '_KG_REBUILD_SEM' in src
        assert 'BoundedSemaphore(4)' in src

    def test_kg_rebuild_acquires_semaphore(self):
        """rebuild_knowledge_graph must acquire _KG_REBUILD_SEM before each submit."""
        src = _read_source('utils/llm/knowledge_graph.py')
        func_start = src.index('def rebuild_knowledge_graph')
        func_body = src[func_start:]
        assert '_KG_REBUILD_SEM.acquire()' in func_body

    def test_kg_rebuild_releases_semaphore_in_callback(self):
        """_KG_REBUILD_SEM must be released via done callback."""
        src = _read_source('utils/llm/knowledge_graph.py')
        func_start = src.index('def rebuild_knowledge_graph')
        func_body = src[func_start:]
        assert '_KG_REBUILD_SEM.release()' in func_body
        assert 'add_done_callback' in func_body

    def test_kg_rebuild_releases_on_submit_failure(self):
        """Semaphore must be released in except block if submit() raises."""
        src = _read_source('utils/llm/knowledge_graph.py')
        func_start = src.index('def rebuild_knowledge_graph')
        func_body = src[func_start:]
        acquire_idx = func_body.index('_KG_REBUILD_SEM.acquire()')
        except_block = func_body[acquire_idx:]
        assert 'except' in except_block
        release_after_except = except_block.index('except')
        assert '_KG_REBUILD_SEM.release()' in except_block[release_after_except:]

    def test_kg_imports_llm_executor(self):
        """knowledge_graph.py must import llm_executor, not storage_executor."""
        src = _read_source('utils/llm/knowledge_graph.py')
        assert 'from utils.executors import' in src
        import_line_start = src.index('from utils.executors import')
        import_line_end = src.index('\n', import_line_start)
        import_line = src[import_line_start:import_line_end]
        assert 'llm_executor' in import_line
        assert 'storage_executor' not in import_line


class TestSpeakerIdentificationPool:
    """speaker_identification must not use storage_executor as parent for download_audio_chunks_and_merge."""

    def test_speaker_id_uses_sync_executor_for_merge(self):
        """Parent call to download_audio_chunks_and_merge must use sync_executor, not storage_executor."""
        src = _read_source('utils/speaker_identification.py')
        merge_idx = src.index('download_audio_chunks_and_merge')
        context = src[max(0, merge_idx - 200) : merge_idx + 50]
        assert 'sync_executor' in context
