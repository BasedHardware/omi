"""Sync-path geolocation enrichment: raw coordinates must gain an address at the pipeline boundary.

Offline-synced conversations were created with raw coordinates and no address
(the sync path never ran ``resolve_geolocation`` like REST create, developer
API, integration ingest, and live finalization do), so recap timeline rows for
synced conversations showed "Unknown". ``_run_full_pipeline_background_async``
— the single coordinator both the inline and Cloud Tasks dispatch branches
call — now enriches the job's geolocation once, before any segment is
processed.

Behavioral test against the real coordinator: the module is loaded fresh with
its heavy dependencies stubbed (sanctioned Tier-2 isolation, see
``backend/docs/test_isolation.md``), the geocoder seam is faked, and the test
asserts on the geolocation each processed segment receives.

The fakes here are deliberately self-contained (not shared with another test
module): every leaf the pipeline imports that pulls real heavyweight clients
(GCS/Firestore protos, SDK clients) is stubbed, so nothing heavy loads real
inside the stub window — importing a sibling test module's fixture set left
real modules behind that later files could not re-import cleanly.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


class _FakeGeolocation:
    def __init__(self, latitude, longitude, address=None, google_place_id=None):
        self.latitude = latitude
        self.longitude = longitude
        self.address = address
        self.google_place_id = google_place_id


def _build_pipeline_fakes() -> dict:
    """Minimal stub set for importing ``utils.sync.pipeline`` in isolation.

    Heavy leaves are AutoMocked; the real ``utils`` package tree stays intact
    so light enum modules the coordinator needs by value (``utils.stt.outcomes``,
    ``utils.sync.lanes``, ``utils.sync.telemetry``) keep their real semantics.
    ``database``/``models`` get package markers with dead paths so their real
    ``__init__``s never run (same trick as the transcription-prefs fakes).
    """
    fakes: dict = {}

    for parent in ('database', 'models'):
        pkg = ModuleType(parent)
        pkg.__path__ = [parent]  # dead path: submodule resolution only via fakes
        fakes[parent] = pkg

    heavy_leaves = [
        'database.conversations',
        'database.users',
        'database.sync_jobs',
        'database.sync_ledger',
        'database.firestore_read_metrics',
        'models.conversation',
        'models.conversation_enums',
        'models.geolocation',
        'models.transcript_segment',
        'utils.analytics',
        'utils.byok',
        'utils.cloud_tasks',
        'utils.conversations.factory',
        'utils.conversations.lifecycle',
        'utils.conversations.location',
        'utils.conversations.process_conversation',
        'utils.sync.bridge',
        'utils.executors',
        'utils.fair_use',
        'utils.http_client',
        'utils.metrics',
        'utils.observability.fallback',
        'utils.observability.transcription',
        'utils.other.storage',
        'utils.speaker_assignment',
        'utils.speaker_identification',
        'utils.stt.pre_recorded',
        'utils.stt.speaker_embedding',
        'utils.stt.vad',
        'utils.sync.backfill',
        'utils.sync.content_id',
        'utils.sync.files',
        'utils.sync.merge_audio',
        'utils.sync.merge_dedupe',
        'pydub',
    ]
    for name in heavy_leaves:
        fakes[name] = AutoMockModule(name)
    return fakes


@pytest.fixture(scope="module")
def pipeline():
    fakes = _build_pipeline_fakes()
    with stub_modules(fakes):
        yield load_module_fresh(
            "utils.sync.pipeline",
            os.path.join(str(_BACKEND), "utils", "sync", "pipeline.py"),
        )


def _prepare(pipeline, wav_paths):
    """Reduce the coordinator to decode→VAD→process_segment with fakes."""

    async def _passthrough_run_blocking(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    pipeline.run_blocking = _passthrough_run_blocking
    pipeline.decode_files_to_wav = MagicMock(return_value=list(wav_paths))
    pipeline.retrieve_vad_segments = MagicMock(
        side_effect=lambda path, segmented, errors, **_kwargs: segmented.add(path)
    )
    pipeline._cleanup_files = MagicMock()
    pipeline.get_timestamp_from_path = MagicMock(return_value=123)
    pipeline.get_prerecorded_service = MagicMock(return_value=('deepgram', 'multi', 'nova-3'))
    pipeline.get_sync_job = MagicMock(return_value={})
    pipeline.bind_or_converge_sync_ledger_completion = MagicMock(return_value=None)
    pipeline._reprocess_merged_conversations = MagicMock()
    pipeline._load_sync_segment_context = _fake_load_segment_context
    pipeline.FAIR_USE_ENABLED = False

    captured = []

    def _capture_process_segment(path, uid, response, lock, errors, *args, **kwargs):
        captured.append(kwargs.get('geolocation'))
        return True

    pipeline.process_segment = _capture_process_segment
    return captured


async def _fake_load_segment_context(_uid):
    return False, None, {}


@pytest.mark.asyncio
async def test_coordinator_enriches_geolocation_once_before_segments(pipeline):
    captured = _prepare(pipeline, ['/tmp/a.wav', '/tmp/b.wav'])
    raw = _FakeGeolocation(latitude=37.7829, longitude=-122.4103)
    enriched = _FakeGeolocation(
        latitude=37.7829, longitude=-122.4103, address='85 2nd St, San Francisco', google_place_id='ChIJ_test'
    )
    resolver_calls = []

    async def _fake_resolver(geolocation):
        resolver_calls.append(geolocation)
        return enriched

    pipeline.async_resolve_geolocation = _fake_resolver

    await pipeline._run_full_pipeline_background_async(
        'job-geo-1', 'uid', ['/tmp/a.opus', '/tmp/b.opus'], 'omi', False, '/tmp/job-geo-1', geolocation=raw
    )

    # One geocode per job, not per segment.
    assert resolver_calls == [raw]
    # Every segment's conversation creation sees the enriched geolocation.
    assert captured == [enriched, enriched]


@pytest.mark.asyncio
async def test_coordinator_keeps_raw_geolocation_when_geocode_fails(pipeline):
    captured = _prepare(pipeline, ['/tmp/a.wav'])
    raw = _FakeGeolocation(latitude=51.5007, longitude=-0.1246)

    async def _failing_resolver(geolocation):
        # The real resolver returns its input unchanged on any miss/error.
        return geolocation

    pipeline.async_resolve_geolocation = _failing_resolver

    await pipeline._run_full_pipeline_background_async(
        'job-geo-2', 'uid', ['/tmp/a.opus'], 'omi', False, '/tmp/job-geo-2', geolocation=raw
    )

    # The pin survives without an address — never dropped to None.
    assert captured == [raw]


@pytest.mark.asyncio
async def test_coordinator_without_geolocation_never_attempts_a_geocode(pipeline):
    """A job without geolocation must not spend a geocode attempt.

    Proves the coordinator passes None straight through to the resolver (it
    does not skip the call), and that the composite contract stays short-
    circuiting: the real resolver returns immediately on falsy input without
    touching the geocoder — modeled here by a fake that records an attempt
    only for truthy input.
    """
    captured = _prepare(pipeline, ['/tmp/a.wav'])
    resolver_calls = []
    geocode_attempts = []

    async def _resolver(geolocation):
        resolver_calls.append(geolocation)
        if not geolocation:
            return None  # the real resolver short-circuits falsy input
        geocode_attempts.append(geolocation)
        return geolocation

    pipeline.async_resolve_geolocation = _resolver

    await pipeline._run_full_pipeline_background_async(
        'job-geo-3', 'uid', ['/tmp/a.opus'], 'omi', False, '/tmp/job-geo-3'
    )

    assert resolver_calls == [None]  # called exactly once, with None
    assert geocode_attempts == []  # zero geocode attempts
    assert captured == [None]  # segments still receive no geolocation


@pytest.mark.asyncio
@pytest.mark.parametrize('fenced', [False, True])
async def test_partial_batch_carries_one_strike_and_keeps_the_healthy_sibling(pipeline, fenced):
    """One classified persistence failure beside a healthy sibling still earns
    the batch a strike; the sibling's result and checkpoint are preserved, and
    every segment is attempted (no per-segment guard short-circuits STT)."""
    _prepare(pipeline, ['/tmp/a.wav', '/tmp/b.wav'])
    pipeline.get_sync_content_partial_result = MagicMock(return_value={})
    pipeline.get_processed_sync_segment_ids = MagicMock(return_value=set())
    pipeline.compute_sync_segment_id = lambda uid, path: Path(path).stem
    fingerprint = 'persistence:document_size_limit'
    pipeline.checkpoint_sync_content_partial_result = MagicMock(return_value=True)
    pipeline.add_processed_sync_segment_id = MagicMock(return_value=True)
    pipeline._finalize_sync_job_for_run = MagicMock()
    pipeline.release_sync_content_claim = MagicMock(return_value=True)
    pipeline.release_sync_content_claim_after_job_retired = MagicMock(return_value=True)
    pipeline.mark_sync_content_completed = MagicMock()
    pipeline._record_sync_job_outcome_async = _noop_job_metric
    called = []

    def process(path, uid, response, lock, errors, *args, **kwargs):
        called.append(path)
        kwargs.get('deferred_outcome', {}).update(
            outcome=(
                pipeline.TranscriptionOutcome.UPSTREAM_ERROR
                if path.endswith('a.wav')
                else pipeline.TranscriptionOutcome.SUCCESS
            ),
            phase='persistence',
            provider='unknown',
            model='unknown',
            retryable=False,
        )
        # The real process_segment releases the assignment slot in finally.
        args[5].complete(path)
        if path.endswith('a.wav'):
            errors.append('sync_persistence_failed')
            kwargs['deferred_outcome'].update(
                repeat_failure_key='persistent_persistence',
                repeat_failure_fingerprint=fingerprint,
            )
            return False
        response['new_memories'].add('synthetic-sibling')
        return True

    pipeline.process_segment = process
    await pipeline._run_full_pipeline_background_async(
        'job-partial-strike',
        'uid',
        ['/tmp/a.opus'],
        'omi',
        False,
        '/tmp/job-partial-strike',
        content_id='batch',
        content_run_bound=True,
        ledger_fence_active=fenced,
    )
    assert sorted(called) == ['/tmp/a.wav', '/tmp/b.wav']
    # The healthy path adds no ledger read per segment.
    pipeline.get_processed_sync_segment_ids.assert_called_once()
    pipeline.get_sync_content_partial_result.assert_called_once()
    # Only the successful sibling is checkpointed as processed.
    assert [call.args[3] for call in pipeline.add_processed_sync_segment_id.call_args_list] == ['b']
    pipeline.checkpoint_sync_content_partial_result.assert_called_once()
    pipeline.mark_sync_content_completed.assert_not_called()
    result = pipeline._finalize_sync_job_for_run.call_args.args[2]
    assert result['failed_segments'] == 1 and result['total_segments'] == 2
    assert result['repeat_failure_fingerprint'] == fingerprint
    assert result['provider'] == result['model'] == 'unknown'
    assert result['new_memories'] == ['synthetic-sibling']
    release = pipeline.release_sync_content_claim_after_job_retired if fenced else pipeline.release_sync_content_claim
    assert release.call_args.kwargs['failure_fingerprint'] == fingerprint


async def _noop_job_metric(*args, **kwargs):
    pass
