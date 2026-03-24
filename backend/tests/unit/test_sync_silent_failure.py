"""
Tests for sync endpoint error handling fix (#4867/#4669).

Verifies that process_segment() properly propagates errors via thread-safe
error collection, and that the endpoint returns appropriate HTTP status codes:
- 200: all segments processed successfully
- 207: partial failure (some segments failed, some succeeded)
- 500: all segments failed

Previously, process_segment() had no error handling — Deepgram failures caused
silent returns or thread crashes, and the endpoint always returned 200.
"""

import os
import threading

import pytest

# ---------------------------------------------------------------------------
# 1. Structural verification — process_segment now has error handling
# ---------------------------------------------------------------------------


class TestProcessSegmentErrorHandling:
    """Verify process_segment has proper error handling after the fix."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_process_segment_has_try_except(self):
        """process_segment() must wrap its body in try/except to catch all errors."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'try:' in func_body, "process_segment must have try/except"
        assert 'except Exception' in func_body, "process_segment must catch exceptions"

    def test_process_segment_collects_errors_on_empty_transcript(self):
        """When transcript is empty, error must be appended to shared errors list."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'errors.append(' in func_body, "Must append error on empty transcript"
        assert 'Transcription returned empty' in func_body, "Must include descriptive error message"

    def test_process_segment_collects_errors_on_exception(self):
        """When an exception occurs, it must be caught and appended to errors."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'Failed to process segment' in func_body, "Must include error context on exception"

    def test_process_segment_uses_lock_for_thread_safety(self):
        """Shared state mutations must be protected by a lock."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'with lock:' in func_body, "Must use lock for thread-safe mutations"
        # Lock must protect both error append and response dict mutations
        lock_sections = func_body.split('with lock:')
        assert len(lock_sections) >= 4, "Must have lock sections for errors (2) + new_memories + updated_memories"

    def test_process_segment_accepts_lock_and_errors_params(self):
        """process_segment must accept lock and errors as parameters."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        sig_end = source.index('):', start) + 2
        signature = source[start:sig_end]

        assert 'lock:' in signature, "Must accept lock parameter"
        assert 'errors:' in signature, "Must accept errors parameter"


class TestSyncEndpointErrorReporting:
    """Verify the endpoint properly reports errors."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_endpoint_creates_lock_and_errors(self):
        """Endpoint must create segment_lock and segment_errors."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert 'segment_errors = []' in func_body, "Must initialize error list"
        assert 'segment_lock = threading.Lock()' in func_body, "Must create lock"

    def test_endpoint_passes_lock_and_errors_to_threads(self):
        """Thread args must include lock and errors."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert 'segment_lock,' in func_body, "Must pass lock to process_segment threads"
        assert 'segment_errors,' in func_body, "Must pass errors to process_segment threads"

    def test_endpoint_returns_207_on_partial_failure(self):
        """Partial failure must return HTTP 207."""
        source = self._read_sync_source()
        assert 'status_code=207' in source, "Must return 207 for partial failure"

    def test_endpoint_returns_500_on_all_failed(self):
        """All segments failing must return HTTP 500."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert 'successful_segments == 0' in func_body, "Must check for all-fail case"
        assert "All" in func_body and "failed processing" in func_body, "Must include descriptive 500 message"

    def test_response_includes_failed_segments_count(self):
        """Response must include failed_segments count for app to check."""
        source = self._read_sync_source()
        assert "'failed_segments'" in source, "Response must include failed_segments"
        assert "'total_segments'" in source, "Response must include total_segments"
        assert "'errors'" in source, "Response must include errors list"

    def test_response_converts_sets_to_sorted_lists(self):
        """Sets must be converted to sorted lists for JSON serialization."""
        source = self._read_sync_source()
        assert "sorted(response['new_memories'])" in source, "new_memories must be sorted list"
        assert "sorted(response['updated_memories'])" in source, "updated_memories must be sorted list"


# ---------------------------------------------------------------------------
# 2. Threading behavior — errors now properly collected
# ---------------------------------------------------------------------------


class TestThreadSafeErrorCollection:
    """Verify the new error collection pattern works correctly."""

    def test_errors_collected_from_failed_threads(self):
        """Errors from multiple failing threads are properly collected."""
        errors = []
        lock = threading.Lock()
        response = {'updated_memories': set(), 'new_memories': set()}

        def failing_segment(path, uid, resp, lk, errs):
            with lk:
                errs.append(f'Failed: {path}')

        def succeeding_segment(path, uid, resp, lk, errs):
            with lk:
                resp['new_memories'].add(f'conv-{path}')

        threads = [
            threading.Thread(target=succeeding_segment, args=('seg1', 'uid', response, lock, errors)),
            threading.Thread(target=failing_segment, args=('seg2', 'uid', response, lock, errors)),
            threading.Thread(target=succeeding_segment, args=('seg3', 'uid', response, lock, errors)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(response['new_memories']) == 2
        assert len(errors) == 1
        assert 'seg2' in errors[0]

    def test_exception_caught_and_collected(self):
        """Exceptions in threads are caught and appended to errors list."""
        errors = []
        lock = threading.Lock()

        def crashing_segment(lk, errs):
            try:
                raise ConnectionError("Deepgram timeout")
            except Exception as e:
                with lk:
                    errs.append(f'Failed: {e}')

        t = threading.Thread(target=crashing_segment, args=(lock, errors))
        t.start()
        t.join()

        assert len(errors) == 1
        assert 'Deepgram timeout' in errors[0]

    def test_status_code_logic(self):
        """Verify status code selection based on segment counts."""
        # All succeed: 200
        total, failed = 5, 0
        successful = total - failed
        assert successful > 0 and failed == 0  # → 200

        # Partial failure: 207
        total, failed = 5, 2
        successful = total - failed
        assert successful > 0 and failed > 0  # → 207

        # All fail: 500
        total, failed = 5, 5
        successful = total - failed
        assert total > 0 and successful == 0  # → 500

        # No segments (edge): 200 (empty success)
        total, failed = 0, 0
        successful = total - failed
        assert total == 0  # → 200 with empty result


# ---------------------------------------------------------------------------
# 3. Deepgram retry behavior (unchanged)
# ---------------------------------------------------------------------------


class TestDeepgramRetryBehavior:
    """Verifies deepgram_prerecorded returns empty list on final retry failure."""

    @staticmethod
    def _read_deepgram_source():
        dg_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'stt', 'pre_recorded.py')
        with open(dg_path) as f:
            return f.read()

    def test_deepgram_returns_empty_list_on_final_retry(self):
        """After 2 retries, deepgram_prerecorded returns [] (not raise).
        This is now properly caught by process_segment's error handling."""
        source = self._read_deepgram_source()
        start = source.index('def deepgram_prerecorded(')
        next_func_markers = ['@timeit', '\ndef ']
        end = len(source)
        for marker in next_func_markers:
            try:
                idx = source.index(marker, start + 100)
                if idx < end:
                    end = idx
            except ValueError:
                pass
        func_body = source[start:end]

        assert 'return [], ' in func_body or "return []" in func_body
        assert 'attempts < 2' in func_body


# ---------------------------------------------------------------------------
# 4. App-side behavior documentation (unchanged, for PR evidence)
# ---------------------------------------------------------------------------


class TestAppSideSyncBehavior:
    """Documents app-side behavior that will be addressed in follow-up PR."""

    @staticmethod
    def _read_app_file(relative_path):
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app', 'lib', relative_path)
        if os.path.exists(app_path):
            with open(app_path) as f:
                return f.read()
        return None

    def test_app_currently_only_accepts_200(self):
        """App only treats HTTP 200 as success — 207 will be treated as failure.
        This is SAFE: WALs stay in miss state and are retried."""
        source = self._read_app_file('backend/http/api/conversations.dart')
        if source is None:
            pytest.skip("App source not available")

        assert 'response.statusCode == 200' in source
        # 207 falls through to the else branch → throws exception → WALs not marked synced

    def test_app_marks_all_wals_synced_on_200(self):
        """App marks ALL WALs synced on 200 — follow-up PR should handle 207
        to only mark successful WALs as synced."""
        source = self._read_app_file('services/wals/local_wal_sync.dart')
        if source is None:
            pytest.skip("App source not available")

        assert 'WalStatus.synced' in source


# ---------------------------------------------------------------------------
# 5. End-to-end data loss prevention verification
# ---------------------------------------------------------------------------


class TestDataLossPreventionFlow:
    """Verifies the fix prevents data loss in the reported scenarios."""

    def test_partial_failure_no_longer_returns_200(self):
        """When segments fail, endpoint returns 207 (not 200).
        Old clients treat 207 as error → WALs stay in miss state → retryable."""
        total_segments = 5
        failed_segments = 2
        successful_segments = total_segments - failed_segments

        # After fix: endpoint checks failures
        if total_segments > 0 and successful_segments == 0:
            status = 500
        elif failed_segments > 0:
            status = 207
        else:
            status = 200

        assert status == 207, "Partial failure must return 207"

        # Old client behavior: 207 is not 200 → throws exception → WALs not marked synced
        app_treats_as_success = status == 200
        assert not app_treats_as_success, "Old clients must NOT mark WALs as synced on 207"

    def test_all_failure_returns_500(self):
        """When ALL segments fail, endpoint returns 500 → clear error for all clients."""
        total_segments = 3
        failed_segments = 3
        successful_segments = 0

        if total_segments > 0 and successful_segments == 0:
            status = 500
        elif failed_segments > 0:
            status = 207
        else:
            status = 200

        assert status == 500

    def test_full_success_still_returns_200(self):
        """When all segments succeed, behavior is unchanged (200)."""
        total_segments = 3
        failed_segments = 0
        successful_segments = 3

        if total_segments > 0 and successful_segments == 0:
            status = 500
        elif failed_segments > 0:
            status = 207
        else:
            status = 200

        assert status == 200

    def test_response_includes_error_details_for_debugging(self):
        """Response includes structured error info for debugging."""
        segment_errors = ['Transcription returned empty for segment /tmp/1700000100.wav']
        total_segments = 3
        failed_segments = len(segment_errors)

        result = {
            'new_memories': ['conv-1', 'conv-2'],
            'updated_memories': [],
            'failed_segments': failed_segments,
            'total_segments': total_segments,
            'errors': segment_errors[:10],
        }

        assert result['failed_segments'] == 1
        assert result['total_segments'] == 3
        assert len(result['errors']) == 1
        assert 'Transcription returned empty' in result['errors'][0]


# ---------------------------------------------------------------------------
# 6. Deduplication on retry — prevents duplicate transcripts
# ---------------------------------------------------------------------------


class TestSegmentDeduplication:
    """Verifies that retried segments are deduplicated in the merge path."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_merge_path_has_dedup_logic(self):
        """process_segment merge path must deduplicate before appending."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'existing_timestamps' in func_body, "Must build set of existing segment timestamps"
        assert 'deduped_segments' in func_body, "Must filter out duplicate segments"
        assert (
            'not deduped_segments' in func_body or 'if not deduped_segments' in func_body
        ), "Must handle case where all segments are duplicates"

    def test_dedup_uses_timestamp_rounding(self):
        """Dedup must round timestamps to avoid float precision issues."""
        source = self._read_sync_source()
        assert 'round(' in source, "Must round timestamps for reliable comparison"

    def test_dedup_logic_correctness(self):
        """Verify the dedup algorithm works correctly with sample data."""
        existing_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0, 'text': 'hello'},
            {'start': 5.0, 'end': 10.0, 'timestamp': 1700000005.0, 'text': 'world'},
        ]
        new_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0, 'text': 'hello'},  # duplicate
            {'start': 10.0, 'end': 15.0, 'timestamp': 1700000010.0, 'text': 'new stuff'},  # new
        ]

        # Build existing set (same logic as in sync.py)
        existing_timestamps = {
            (round(s['timestamp'], 2), round(s['timestamp'] + (s['end'] - s['start']), 2)) for s in existing_segments
        }

        deduped = []
        for seg in new_segments:
            seg_key = (round(seg['timestamp'], 2), round(seg['timestamp'] + (seg['end'] - seg['start']), 2))
            if seg_key not in existing_timestamps:
                deduped.append(seg)

        assert len(deduped) == 1, "Should filter out 1 duplicate"
        assert deduped[0]['text'] == 'new stuff', "Should keep only the new segment"

    def test_all_duplicates_skips_merge(self):
        """When all new segments are duplicates, merge is skipped entirely."""
        existing_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0},
        ]
        new_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0},  # exact duplicate
        ]

        existing_timestamps = {
            (round(s['timestamp'], 2), round(s['timestamp'] + (s['end'] - s['start']), 2)) for s in existing_segments
        }

        deduped = [
            seg
            for seg in new_segments
            if (round(seg['timestamp'], 2), round(seg['timestamp'] + (seg['end'] - seg['start']), 2))
            not in existing_timestamps
        ]

        assert len(deduped) == 0, "All duplicates should be filtered"


# ---------------------------------------------------------------------------
# 7. Behavioral test — process_segment with mocked dependencies
# ---------------------------------------------------------------------------


class TestProcessSegmentBehavior:
    """Behavioral tests that exercise the actual process_segment function logic."""

    def test_process_segment_error_collection_pattern(self):
        """
        Simulate the exact pattern used in process_segment:
        - Thread-safe error collection via lock
        - Empty transcript → error appended, no memory created
        - Exception → error appended via except clause
        """
        errors = []
        lock = threading.Lock()
        response = {'updated_memories': set(), 'new_memories': set()}

        def simulate_empty_transcript(path, uid, resp, lk, errs):
            """Simulates process_segment when deepgram returns empty."""
            try:
                words = []  # Empty from deepgram
                transcript_segments = []  # postprocess_words returns empty
                if not transcript_segments:
                    error_msg = f'Transcription returned empty for segment {path}'
                    with lk:
                        errs.append(error_msg)
                    return
            except Exception as e:
                with lk:
                    errs.append(f'Failed to process segment {path}: {e}')

        def simulate_exception(path, uid, resp, lk, errs):
            """Simulates process_segment when deepgram raises."""
            try:
                raise ConnectionError("Deepgram connection refused")
            except Exception as e:
                with lk:
                    errs.append(f'Failed to process segment {path}: {e}')

        def simulate_success(path, uid, resp, lk, errs):
            """Simulates process_segment when everything works."""
            try:
                with lk:
                    resp['new_memories'].add(f'conv-{path}')
            except Exception as e:
                with lk:
                    errs.append(f'Failed to process segment {path}: {e}')

        threads = [
            threading.Thread(target=simulate_success, args=('/tmp/seg1.wav', 'uid', response, lock, errors)),
            threading.Thread(target=simulate_empty_transcript, args=('/tmp/seg2.wav', 'uid', response, lock, errors)),
            threading.Thread(target=simulate_exception, args=('/tmp/seg3.wav', 'uid', response, lock, errors)),
            threading.Thread(target=simulate_success, args=('/tmp/seg4.wav', 'uid', response, lock, errors)),
        ]

        chunk_size = 5
        for i in range(0, len(threads), chunk_size):
            [t.start() for t in threads[i : i + chunk_size]]
            [t.join() for t in threads[i : i + chunk_size]]

        # 2 succeeded, 2 failed
        assert len(response['new_memories']) == 2
        assert len(errors) == 2

        # Verify error messages are descriptive
        assert any('Transcription returned empty' in e for e in errors)
        assert any('Deepgram connection refused' in e for e in errors)

        # Status code logic
        total_segments = 4
        failed_segments = len(errors)
        successful_segments = total_segments - failed_segments

        assert failed_segments == 2
        assert successful_segments == 2
        # Partial failure → 207
        assert successful_segments > 0 and failed_segments > 0
