"""
Tests for the bounded first-file cache wait in GET /v1/sync/audio/{id}/urls (#7325).

The endpoint used to merge the first uncached audio file synchronously in the
request thread. Large merges (hundreds of chunks, or GCS pushback) took 60-115s+
in prod, exceeding the 120s timeout middleware and client timeouts, so the
request appeared to hang with zero bytes. The merge is now submitted to
sync_executor and waited on for at most FIRST_FILE_CACHE_WAIT_SECONDS; on
timeout the file is reported as pending while the merge finishes in the
background (and lands in the GCS cache for subsequent calls).

routers/sync.py has a heavy import chain (opuslib, pydub, STT/LLM stacks), so
following the precedent of test_sync_v2.py these are structural tests over the
source, plus logic tests of the exact wait/timeout primitive used.
"""

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

SYNC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')


def _read_sync_source():
    with open(SYNC_PATH, encoding='utf-8') as f:
        return f.read()


def _urls_endpoint_body(source):
    start = source.index('def get_audio_signed_urls_endpoint')
    next_section = source.find('\n@router.', start + 1)
    if next_section == -1:
        next_section = len(source)
    return source[start:next_section]


class TestUrlsEndpointStructure:
    def test_first_file_merge_is_bounded(self):
        """The first-file cache must be waited on with a timeout, not called inline."""
        body = _urls_endpoint_body(_read_sync_source())
        assert 'submit_with_context(' in body, "first-file cache must run on an executor"
        assert re.search(
            r'\.result\(timeout=FIRST_FILE_CACHE_WAIT_SECONDS\)', body
        ), "first-file cache wait must be bounded by FIRST_FILE_CACHE_WAIT_SECONDS"
        assert 'FuturesTimeoutError' in body, "timeout must be handled (file reported pending)"

    def test_no_inline_first_file_merge(self):
        """The unbounded inline call that caused #7325 must not come back."""
        body = _urls_endpoint_body(_read_sync_source())
        assert not re.search(
            r'^\s*_precache_audio_file\(', body, re.MULTILINE
        ), "_precache_audio_file must not be called inline in the request thread"

    def test_coordinator_not_on_storage_executor(self):
        """_precache_audio_file fans out to storage_executor, so the bounded wait
        must submit it to a different pool (deadlock rule 3 in AGENTS.md)."""
        body = _urls_endpoint_body(_read_sync_source())
        m = re.search(r'submit_with_context\(\s*(\w+),\s*_precache_audio_file', body)
        assert m, "first-file cache must be submitted via submit_with_context"
        assert (
            m.group(1) != 'storage_executor'
        ), "coordinator must not share storage_executor with its chunk-download children"

    def test_wait_budget_is_under_middleware_timeout(self):
        """The wait budget must stay well under the 120s HTTP timeout middleware."""
        source = _read_sync_source()
        m = re.search(r'^FIRST_FILE_CACHE_WAIT_SECONDS\s*=\s*([0-9.]+)', source, re.MULTILINE)
        assert m, "FIRST_FILE_CACHE_WAIT_SECONDS constant must exist at module level"
        assert 0 < float(m.group(1)) <= 60, "wait budget must be positive and well under 120s"


class TestBoundedWaitPrimitive:
    """The endpoint relies on Future.result(timeout=) leaving the task running
    after a timeout — verify that contract so the background-completion claim holds."""

    def test_timeout_leaves_merge_running_to_completion(self):
        completed = []

        def slow_merge():
            time.sleep(0.3)
            completed.append(True)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(slow_merge)
            with pytest.raises(FuturesTimeoutError):
                future.result(timeout=0.05)
            assert not completed, "merge should still be running after the bounded wait"
            future.result(timeout=2)
        assert completed, "merge must finish in the background after the wait times out"

    def test_fast_merge_returns_within_budget(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: 'cached')
            assert future.result(timeout=1) == 'cached'
