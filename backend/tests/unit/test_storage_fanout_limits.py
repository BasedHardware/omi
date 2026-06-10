"""Tests for bounded fan-out concurrency limits in storage operations (#7387).

Verifies that storage_executor submissions are gated by semaphores to prevent
queue spikes from unbounded parallel chunk downloads and audio file precaching.

Source-level tests (no heavy module imports) — checks code structure, not runtime.
Behavioral tests use a standalone sliding-window implementation to verify the pattern.
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED


def _read_source(rel_path):
    base = os.path.join(os.path.dirname(__file__), '..', '..')
    with open(os.path.join(base, rel_path), encoding='utf-8') as f:
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

    def test_precache_file_semaphore_is_2(self):
        """Global precache file semaphore must be BoundedSemaphore(2)."""
        src = _read_source('utils/other/storage.py')
        assert 'BoundedSemaphore(2)' in src

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


class TestNotificationsFanOut:
    """notifications.py must not use storage_executor for summary work."""

    def test_bulk_summary_uses_postprocess_executor(self):
        """_send_bulk_summary_notification must use postprocess_executor, not storage_executor."""
        src = _read_source('utils/other/notifications.py')
        func_start = src.index('async def _send_bulk_summary_notification')
        func_body = src[func_start : func_start + 400]
        assert 'postprocess_executor' in func_body
        assert 'storage_executor' not in func_body

    def test_bulk_summary_is_batched(self):
        """_send_bulk_summary_notification must process users in batches."""
        src = _read_source('utils/other/notifications.py')
        func_start = src.index('async def _send_bulk_summary_notification')
        func_body = src[func_start : func_start + 400]
        assert '_BATCH_SIZE' in func_body


class TestSlidingWindowBehavior:
    """Behavioral tests verifying the sliding-window + semaphore pattern at runtime."""

    def test_sliding_window_caps_inflight(self):
        """Sliding window must never have more than WINDOW_SIZE futures in-flight."""
        WINDOW_SIZE = 4
        GLOBAL_SEM = threading.BoundedSemaphore(16)
        executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="test-sw")
        high_water = {'max': 0}
        active = {'count': 0}
        lock = threading.Lock()

        def tracked_work(idx):
            with lock:
                active['count'] += 1
                if active['count'] > high_water['max']:
                    high_water['max'] = active['count']
            time.sleep(0.02)
            with lock:
                active['count'] -= 1
            return idx

        jobs = list(range(20))
        results = []

        def submit_job(job):
            GLOBAL_SEM.acquire()
            try:
                f = executor.submit(tracked_work, job)
                f.add_done_callback(lambda _: GLOBAL_SEM.release())
                return f
            except Exception:
                GLOBAL_SEM.release()
                raise

        pending = {}
        job_iter = iter(jobs)
        for job in job_iter:
            f = submit_job(job)
            pending[f] = job
            if len(pending) >= WINDOW_SIZE:
                break

        while pending:
            done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                results.append(future.result())
                del pending[future]
            for job in job_iter:
                f = submit_job(job)
                pending[f] = job
                if len(pending) >= WINDOW_SIZE:
                    break

        executor.shutdown(wait=True)
        assert high_water['max'] <= WINDOW_SIZE + 1, f"High water {high_water['max']} exceeds window {WINDOW_SIZE}"
        assert sorted(results) == list(range(20)), "All jobs must complete"

    def test_semaphore_released_on_exception(self):
        """Semaphore must not leak when submitted tasks raise exceptions."""
        SEM = threading.BoundedSemaphore(4)
        executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="test-exc")

        def failing_work(idx):
            if idx % 2 == 0:
                raise RuntimeError(f"fail-{idx}")
            return idx

        futures = []
        for i in range(8):
            SEM.acquire()
            try:
                f = executor.submit(failing_work, i)
                f.add_done_callback(lambda _: SEM.release())
                futures.append(f)
            except Exception:
                SEM.release()
                raise

        for f in futures:
            try:
                f.result()
            except RuntimeError:
                pass

        executor.shutdown(wait=True)

        available = 0
        while SEM.acquire(blocking=False):
            available += 1
        for _ in range(available):
            SEM.release()
        assert available == 4, f"Semaphore leaked: {available} slots available, expected 4"

    def test_global_semaphore_limits_cross_request(self):
        """Global semaphore must limit total inflight across concurrent callers."""
        GLOBAL_SEM = threading.BoundedSemaphore(6)
        executor = ThreadPoolExecutor(max_workers=12, thread_name_prefix="test-global")
        high_water = {'max': 0}
        active = {'count': 0}
        lock = threading.Lock()

        def tracked_work(idx):
            with lock:
                active['count'] += 1
                if active['count'] > high_water['max']:
                    high_water['max'] = active['count']
            time.sleep(0.02)
            with lock:
                active['count'] -= 1
            return idx

        def run_batch(start, count):
            futures = []
            for i in range(start, start + count):
                GLOBAL_SEM.acquire()
                try:
                    f = executor.submit(tracked_work, i)
                    f.add_done_callback(lambda _: GLOBAL_SEM.release())
                    futures.append(f)
                except Exception:
                    GLOBAL_SEM.release()
                    raise
            return [f.result() for f in futures]

        threads = []
        results = [None, None, None]
        for batch_idx in range(3):

            def worker(idx=batch_idx):
                results[idx] = run_batch(idx * 10, 10)

            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        executor.shutdown(wait=True)
        assert high_water['max'] <= 6 + 1, f"Global high water {high_water['max']} exceeds cap 6"
        for r in results:
            assert r is not None and len(r) == 10
