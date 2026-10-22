"""Synthetic regressions at the integration seams identified by GLM review."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from utils.capture import batch_coverage, sync_coverage
from utils.conversations.duplicate_capture import capture_record
from routers.listen import coverage


@pytest.mark.parametrize('mode,fetches', [('off', 0), ('shadow', 0), ('invalid', 0), ('serve', 1)])
def test_provider_projection_never_downloads_audio_just_to_shadow(monkeypatch, mode, fetches):
    from utils.batch_pipeline import audio

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.delenv('CAPTURE_COVERAGE_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S', raising=False)
    fetch = Mock(return_value='synthetic-path')
    monkeypatch.setattr(audio, 'read_context', lambda _: {'proof': True})
    assert batch_coverage.optional_manifest(
        SimpleNamespace(fetch_audio=fetch), SimpleNamespace(owner_id='synthetic'), None
    ) == ({'proof': True} if fetches else None)
    assert fetch.call_count == fetches


def test_shadow_uses_prefetched_manifest_without_downloading(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'shadow')
    fetch = Mock(side_effect=AssertionError('unexpected download'))
    hint = SimpleNamespace(prefetched=SimpleNamespace(manifest={'already': 'available'}))
    assert (
        batch_coverage.optional_manifest(
            SimpleNamespace(fetch_audio=fetch), SimpleNamespace(owner_id='synthetic'), hint
        )
        == hint.prefetched.manifest
    )


@pytest.mark.asyncio
async def test_serving_trim_tracks_generated_and_retired_paths(monkeypatch):
    from utils.sync import wal_audio_coverage

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setattr(wal_audio_coverage, 'build_sync_source_frame_maps', lambda *a: {})
    monkeypatch.setattr(sync_coverage, 'trim_maps', lambda *a, **kw: (['derived'], {}, {'derived'}))

    async def blocking(pool, fn, *args, **kw):
        return fn(*args, **kw)

    cleanup = set()
    paths, _, _ = await sync_coverage.apply_sync_coverage(
        'synthetic',
        None,
        False,
        None,
        None,
        {},
        ['retired'],
        {},
        cleanup_paths=cleanup,
        run_blocking=blocking,
        db_executor=None,
    )
    assert paths == ['derived'] and cleanup == {'retired', 'derived'}


@pytest.mark.parametrize('mode,accepted', [('off', False), ('shadow', False), ('invalid', False), ('serve', True)])
def test_duplicate_capture_timestamp_widening_is_serve_only(monkeypatch, mode, accepted):
    monkeypatch.setenv('LIFECYCLE_V2_MODE', mode)
    monkeypatch.delenv('LIFECYCLE_V2_MODE_SERVE_PERCENT', raising=False)
    row = {
        'id': 'synthetic',
        'status': 'completed',
        'source': 'phone',
        'started_at': '2026-10-22T00:00:00+00:00',
        'finished_at': '2026-10-22T00:01:00+00:00',
    }
    assert (capture_record(row, 'synthetic') is not None) == accepted
    row.update(
        started_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
        finished_at=datetime(2026, 10, 22, 0, 1, tzinfo=timezone.utc),
    )
    assert capture_record(row, 'synthetic') is not None


@pytest.mark.parametrize('runs', [[None], ['bad'], [5], {'bad': 'shape'}])
def test_malformed_post_commit_runs_never_fail_the_durable_flush(monkeypatch, runs):
    from utils.committed_capture import PROOF_KIND

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    assert coverage.record_committed('synthetic', 'synthetic', {'proof': PROOF_KIND, 'runs': runs}) == []
