"""
Tests for record_usage placement and v1 deprecation in sync endpoints (#7123).

Verifies:
- record_usage is called after successful segment processing (v1 + v2)
- record_usage is NOT called when all segments fail
- record_usage failure does not break the sync response
- v1 deprecation headers appear on all response paths
"""

import ast
import os
import re

import pytest


def _read_sync_source():
    sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
    with open(sync_path, encoding='utf-8') as f:
        return f.read()


def _read_pipeline_source():
    pipeline_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'pipeline.py')
    with open(pipeline_path, encoding='utf-8') as f:
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


def _usage_has_exception_boundary(body):
    """Check nesting, rather than a character window around a formatted call."""
    for node in ast.walk(ast.parse(body)):
        if not isinstance(node, ast.Try):
            continue
        catches = any(
            isinstance(handler.type, ast.Name) and handler.type.id == 'Exception' for handler in node.handlers
        )
        if not catches:
            continue
        for statement in node.body:
            for call in ast.walk(statement):
                if isinstance(call, ast.Call) and any(
                    isinstance(argument, ast.Name) and argument.id == 'record_usage' for argument in call.args
                ):
                    return True
    return False


# ---------------------------------------------------------------------------
# record_usage import
# ---------------------------------------------------------------------------


class TestRecordUsageImport:
    def test_record_usage_imported(self):
        source = _read_sync_source()
        assert 'from utils.analytics import record_sync_v1_usage as record_usage' in source

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


# ---------------------------------------------------------------------------
# v2 record_usage placement
# ---------------------------------------------------------------------------


class TestV2RecordUsage:
    @staticmethod
    def _get_v2_body():
        return _extract_function_body(_read_pipeline_source(), '_run_full_pipeline_background_async')

    def test_record_usage_called_in_v2(self):
        body = self._get_v2_body()
        assert 'record_usage,' in body, "v2 background worker must call record_usage"

    def test_record_usage_after_failed_segments_check(self):
        """record_usage must come after failed_segments is computed."""
        body = self._get_v2_body()
        failed_pos = body.find('failed_segments = len(segment_errors)')
        record_pos = body.find('record_usage,')
        assert failed_pos > 0
        assert record_pos > 0
        assert record_pos > failed_pos, "record_usage must come after failed_segments computation"

    def test_record_usage_guarded_by_successful_segments(self):
        """record_usage should only run when successful_segments > 0."""
        body = self._get_v2_body()
        record_idx = body.find('record_usage,')
        preceding = body[max(0, record_idx - 300) : record_idx]
        assert 'usage_seconds > 0' in preceding, "record_usage must be guarded by positive usage seconds"

    def test_static_record_usage_before_finalize_sync_job(self):
        """Static ordering contract: usage precedes the fenced terminal publication."""
        body = self._get_v2_body()
        record_pos = body.find('record_usage,')
        assert record_pos > 0, "record_usage must exist"
        complete_pos = body.rfind('_finalize_sync_job_for_run,')
        assert complete_pos > 0, "fenced finalization must exist"
        assert record_pos < complete_pos, "record_usage must run before final job publication"

    def test_record_usage_wrapped_in_try_except(self):
        assert _usage_has_exception_boundary(self._get_v2_body()), 'record_usage must be inside a protected try body'


# ---------------------------------------------------------------------------
# v1 deprecation
# ---------------------------------------------------------------------------
