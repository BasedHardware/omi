"""
Tests for record_usage placement and v1 deprecation in sync endpoints (#7123).

Verifies:
- record_usage is called after successful segment processing (v1 + v2)
- record_usage is NOT called when all segments fail
- record_usage failure does not break the sync response
- v1 deprecation headers appear on all response paths
"""

import os
import re

import pytest


def _read_sync_source():
    sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
    with open(sync_path) as f:
        return f.read()


def _extract_function_body(source, func_name):
    """Extract the body of a function from source code."""
    pattern = rf'(async\s+)?def {re.escape(func_name)}\('
    match = re.search(pattern, source)
    if not match:
        return None
    start = match.start()
    # Find the next top-level def or class or decorator at the same indent
    next_def = re.search(r'\n(?:@router\.|def |async def |class )', source[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(source)
    return source[start:end]


# ---------------------------------------------------------------------------
# record_usage import
# ---------------------------------------------------------------------------


class TestRecordUsageImport:
    def test_record_usage_imported(self):
        source = _read_sync_source()
        assert 'from utils.analytics import record_usage' in source

    def test_import_at_module_level(self):
        source = _read_sync_source()
        lines = source.split('\n')
        for line in lines:
            if 'from utils.analytics import record_usage' in line:
                assert not line.startswith(' '), "import must be at module top level"
                break


# ---------------------------------------------------------------------------
# v1 record_usage placement
# ---------------------------------------------------------------------------


class TestV1RecordUsage:
    @staticmethod
    def _get_v1_body():
        return _extract_function_body(_read_sync_source(), 'sync_local_files')

    def test_record_usage_called_in_v1(self):
        body = self._get_v1_body()
        assert 'record_usage(' in body, "v1 must call record_usage"

    def test_record_usage_after_failed_segments_check(self):
        """record_usage must come after the all-segments-failed guard."""
        body = self._get_v1_body()
        all_failed_pos = body.find('successful_segments == 0')
        record_pos = body.find('record_usage(')
        assert all_failed_pos > 0, "all-segments-failed guard must exist"
        assert record_pos > 0, "record_usage must exist"
        assert record_pos > all_failed_pos, "record_usage must come after all-segments-failed check"

    def test_record_usage_not_under_fair_use_guard(self):
        """record_usage must NOT be nested inside fair_use_restrict_dg block."""
        body = self._get_v1_body()
        # Find the record_usage call
        record_idx = body.find('record_usage(')
        # Walk backwards to find the enclosing if-block
        preceding = body[:record_idx]
        lines = preceding.split('\n')
        # The record_usage call should be at try/except level, not under if fair_use_restrict_dg
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith('if fair_use_restrict_dg'):
                # Check if we've left that block's scope
                record_line = body[record_idx:].split('\n')[0]
                record_indent = len(record_line) - len(record_line.lstrip())
                if_indent = len(line) - len(line.lstrip())
                assert record_indent <= if_indent, "record_usage must not be inside fair_use_restrict_dg block"
                break

    def test_record_usage_wrapped_in_try_except(self):
        """record_usage must be protected by try/except."""
        body = self._get_v1_body()
        record_idx = body.find('record_usage(')
        # Check there's a try: before it (within ~5 lines)
        preceding_chunk = body[max(0, record_idx - 200) : record_idx]
        assert 'try:' in preceding_chunk, "record_usage must be inside a try block"
        # Check there's an except after it
        following_chunk = body[record_idx : record_idx + 200]
        assert 'except Exception' in following_chunk, "record_usage must have an except handler"

    def test_record_usage_logs_error_on_failure(self):
        """Error from record_usage must be logged, not silenced."""
        body = self._get_v1_body()
        record_idx = body.find('record_usage(')
        following = body[record_idx : record_idx + 300]
        assert 'logger.error' in following, "record_usage failure must be logged"


# ---------------------------------------------------------------------------
# v2 record_usage placement
# ---------------------------------------------------------------------------


class TestV2RecordUsage:
    @staticmethod
    def _get_v2_body():
        return _extract_function_body(_read_sync_source(), '_process_segments_background')

    def test_record_usage_called_in_v2(self):
        body = self._get_v2_body()
        assert 'record_usage(' in body, "v2 background worker must call record_usage"

    def test_record_usage_after_failed_segments_check(self):
        """record_usage must come after failed_segments is computed."""
        body = self._get_v2_body()
        failed_pos = body.find('failed_segments = len(segment_errors)')
        record_pos = body.find('record_usage(')
        assert failed_pos > 0
        assert record_pos > 0
        assert record_pos > failed_pos, "record_usage must come after failed_segments computation"

    def test_record_usage_guarded_by_successful_segments(self):
        """record_usage should only run when successful_segments > 0."""
        body = self._get_v2_body()
        record_idx = body.find('record_usage(')
        preceding = body[max(0, record_idx - 300) : record_idx]
        assert 'successful_segments > 0' in preceding, "record_usage must be guarded by successful_segments > 0"

    def test_record_usage_before_mark_job_completed(self):
        """record_usage must run before mark_job_completed."""
        body = self._get_v2_body()
        record_pos = body.find('record_usage(')
        complete_pos = body.find('mark_job_completed(')
        assert record_pos > 0
        assert complete_pos > 0
        assert record_pos < complete_pos, "record_usage must run before mark_job_completed"

    def test_record_usage_wrapped_in_try_except(self):
        body = self._get_v2_body()
        record_idx = body.find('record_usage(')
        preceding = body[max(0, record_idx - 200) : record_idx]
        assert 'try:' in preceding, "record_usage must be inside a try block"
        following = body[record_idx : record_idx + 200]
        assert 'except Exception' in following, "record_usage must have an except handler"


# ---------------------------------------------------------------------------
# v1 deprecation
# ---------------------------------------------------------------------------


class TestV1Deprecation:
    @staticmethod
    def _get_v1_body():
        return _extract_function_body(_read_sync_source(), 'sync_local_files')

    def test_v1_endpoint_marked_deprecated(self):
        source = _read_sync_source()
        v1_idx = source.find('"/v1/sync-local-files"')
        decorator_region = source[max(0, v1_idx - 200) : v1_idx + 50]
        assert 'deprecated=True' in decorator_region, "v1 endpoint must have deprecated=True"

    def test_v1_logs_deprecation_warning(self):
        body = self._get_v1_body()
        assert 'logger.warning' in body, "v1 must log a deprecation warning"
        assert 'deprecated' in body.lower(), "warning must mention deprecation"

    def test_v1_sets_deprecation_header(self):
        body = self._get_v1_body()
        assert '_V1_DEPRECATION_HEADERS' in body, "v1 must use deprecation headers constant"

    def test_v1_deprecation_headers_constant_exists(self):
        source = _read_sync_source()
        assert '_V1_DEPRECATION_HEADERS' in source
        assert "'Deprecation'" in source
        assert "'true'" in source
        assert 'successor-version' in source

    def test_v1_httpexceptions_have_deprecation_headers(self):
        """All HTTPException raises in v1 must include deprecation headers."""
        body = self._get_v1_body()
        exceptions = [m.start() for m in re.finditer(r'raise HTTPException\(', body)]
        assert len(exceptions) > 0, "v1 must have HTTPException raises"
        for exc_start in exceptions:
            # Find the matching closing paren (handle nested parens)
            depth = 0
            end = exc_start
            for i, ch in enumerate(body[exc_start:], start=exc_start):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            exc_args = body[exc_start:end]
            assert (
                '_V1_DEPRECATION_HEADERS' in exc_args
            ), f"HTTPException at offset {exc_start} missing deprecation headers: {exc_args[:100]}"

    def test_v1_helper_exceptions_re_raised_with_headers(self):
        """Shared helpers (retrieve_file_paths, decode_files_to_wav) must be wrapped."""
        body = self._get_v1_body()
        assert 'except HTTPException' in body, "v1 must catch helper HTTPExceptions to re-raise with headers"

    def test_v1_jsonresponses_have_deprecation_headers(self):
        """All JSONResponse returns in v1 must include deprecation headers."""
        body = self._get_v1_body()
        json_responses = [m.start() for m in re.finditer(r'return JSONResponse\(', body)]
        for resp_start in json_responses:
            resp_block = body[resp_start : resp_start + 300]
            assert (
                '_V1_DEPRECATION_HEADERS' in resp_block
            ), f"JSONResponse at offset {resp_start} missing deprecation headers"
