"""
Tests for ordered conversation assignment in offline sync (#6551, #5747).

Bug: sync_local_files (v1) and the v2 background pipeline processed VAD segments
fully in parallel. Each process_segment() call independently ran
get_closest_conversation_to_timestamps() and, finding nothing (none of its
timestamp-adjacent siblings had persisted a conversation yet), created its own
conversation — so a pendant backlog of chunks separated by seconds became many
separate conversations instead of merging.

Fix: segments are sorted chronologically and an _OrderedTurnstile serializes the
conversation lookup/create/merge step in timestamp order (STT stays parallel).
Conversations that gained segments are reprocessed once per batch so their
summary covers the merged content.
"""

import os
import threading
import time
from collections import deque
from typing import List

SYNC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')


def _read_sync_source():
    with open(SYNC_PATH) as f:
        return f.read()


def _function_body(source: str, name: str) -> str:
    start = source.index(f'def {name}(')
    next_def = source.index('\ndef ', start + 1)
    return source[start:next_def]


def _async_function_body(source: str, name: str) -> str:
    start = source.index(f'async def {name}(')
    end = source.find('\nasync def ', start + 1)
    end2 = source.find('\ndef ', start + 1)
    candidates = [e for e in (end, end2) if e != -1]
    return source[start : min(candidates)] if candidates else source[start:]


def _load_turnstile_class():
    """Extract and exec the _OrderedTurnstile class without importing routers.sync
    (which pulls in firestore/opuslib/etc.)."""
    source = _read_sync_source()
    start = source.index('class _OrderedTurnstile')
    end = source.index('\ndef ', start)
    class_src = source[start:end]
    namespace = {'deque': deque, 'threading': threading, 'List': List}
    exec('ORDERED_ASSIGNMENT_WAIT_SECONDS = 600\n' + class_src, namespace)
    return namespace['_OrderedTurnstile']


# ---------------------------------------------------------------------------
# 1. _OrderedTurnstile behavior
# ---------------------------------------------------------------------------


class TestOrderedTurnstile:
    def test_serializes_in_given_order_despite_reverse_readiness(self):
        """Threads become ready newest-first; assignment order must still be oldest-first."""
        Turnstile = _load_turnstile_class()
        keys = ['t1.wav', 't2.wav', 't3.wav', 't4.wav']
        turnstile = Turnstile(keys)
        order = []
        order_lock = threading.Lock()

        def worker(key, stt_delay):
            time.sleep(stt_delay)  # simulated parallel STT, newest finishes first
            try:
                assert turnstile.wait_turn(key, timeout=10)
                with order_lock:
                    order.append(key)
            finally:
                turnstile.complete(key)

        threads = [
            threading.Thread(target=worker, args=(key, delay)) for key, delay in zip(keys, [0.2, 0.15, 0.1, 0.05])
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert order == keys, f'assignment must be chronological, got {order}'

    def test_early_complete_without_wait_unblocks_followers(self):
        """A segment that short-circuits (silence) completes without waiting and must
        not block later segments."""
        Turnstile = _load_turnstile_class()
        turnstile = Turnstile(['a', 'b'])
        # 'a' never calls wait_turn (early return path) — only complete()
        turnstile.complete('a')
        assert turnstile.wait_turn('b', timeout=1), "'b' must proceed after 'a' completed early"

    def test_wait_times_out_fail_open(self):
        """If an earlier segment hangs, wait_turn returns False instead of deadlocking."""
        Turnstile = _load_turnstile_class()
        turnstile = Turnstile(['a', 'b'])
        t0 = time.monotonic()
        assert turnstile.wait_turn('b', timeout=0.2) is False
        assert time.monotonic() - t0 < 5

    def test_first_key_proceeds_immediately(self):
        Turnstile = _load_turnstile_class()
        turnstile = Turnstile(['a', 'b', 'c'])
        assert turnstile.wait_turn('a', timeout=0.1) is True

    def test_out_of_order_completion_converges(self):
        """Completions arriving in arbitrary order still release the queue head correctly."""
        Turnstile = _load_turnstile_class()
        turnstile = Turnstile(['a', 'b', 'c'])
        turnstile.complete('b')  # later key done first (early return)
        turnstile.complete('a')
        assert turnstile.wait_turn('c', timeout=1) is True


# ---------------------------------------------------------------------------
# 2. Structural guards — callers actually use the turnstile
# ---------------------------------------------------------------------------


class TestCallersUseOrderedAssignment:
    def test_process_segment_accepts_turnstile_and_releases_it(self):
        body = _function_body(_read_sync_source(), 'process_segment')
        assert 'turnstile' in body.split('):')[0], 'process_segment must accept a turnstile param'
        assert 'wait_turn' in body, 'process_segment must wait its chronological turn'
        assert 'finally:' in body and 'turnstile.complete(path)' in body, (
            'process_segment must always release its turn (finally), ' 'or followers deadlock on early returns/errors'
        )

    def test_wait_turn_precedes_conversation_lookup(self):
        body = _function_body(_read_sync_source(), 'process_segment')
        assert body.index('wait_turn') < body.index(
            'get_closest_conversation_to_timestamps'
        ), 'turn must be acquired before the closest-conversation lookup'

    def test_v1_sorts_segments_and_passes_turnstile(self):
        body = _async_function_body(_read_sync_source(), 'sync_local_files')
        assert 'sorted(segmented_paths, key=get_timestamp_from_path)' in body
        assert '_OrderedTurnstile(' in body
        assert 'assignment_turnstile,' in body, 'v1 must pass the turnstile to process_segment'

    def test_v2_sorts_segments_and_passes_turnstile(self):
        body = _async_function_body(_read_sync_source(), '_run_full_pipeline_background_async')
        assert 'sorted(segmented_paths, key=get_timestamp_from_path)' in body
        assert '_OrderedTurnstile(' in body
        assert 'assignment_turnstile,' in body, 'v2 must pass the turnstile to process_segment'

    def test_both_pipelines_reprocess_merged_conversations(self):
        source = _read_sync_source()
        v1 = _async_function_body(source, 'sync_local_files')
        v2 = _async_function_body(source, '_run_full_pipeline_background_async')
        assert '_reprocess_merged_conversations' in v1
        assert '_reprocess_merged_conversations' in v2

    def test_merge_path_records_merged_conversation(self):
        body = _function_body(_read_sync_source(), 'process_segment')
        assert "_merged" in body, 'merge path must record conversations that gained segments'

    def test_reprocess_helper_is_fail_safe(self):
        body = _function_body(_read_sync_source(), '_reprocess_merged_conversations')
        assert "pop('_merged'" in body, 'must pop the internal key so it never leaks into responses'
        assert 'except Exception' in body, 'one failed reprocess must not fail the batch'
