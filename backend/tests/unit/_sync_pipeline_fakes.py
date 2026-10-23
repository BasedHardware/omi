"""Shared stub set for loading the legacy segment core (``utils/sync/legacy_segment_core.py``) in isolation.

Moved out of the deleted ``test_sync_geolocation_enrichment.py`` (legacy-retire C11): every leaf the core
imports that pulls real heavyweight clients (GCS/Firestore protos, SDK clients) is stubbed, so nothing
heavy loads real inside the stub window.
"""

import importlib
from types import ModuleType
from unittest.mock import AsyncMock

from testing.import_isolation import AutoMockModule


def _build_pipeline_fakes() -> dict:
    """Minimal stub set for importing ``utils.sync.legacy_segment_core`` in isolation.

    Heavy leaves are AutoMocked; the real ``utils`` package tree stays intact
    so light enum modules the core needs by value (``utils.stt.outcomes``,
    ``utils.sync.lanes``, ``utils.sync.telemetry``) keep their real semantics.
    ``database``/``models`` get package markers with dead paths so their real
    ``__init__``s never run (same trick as the transcription-prefs fakes).
    """
    # These light leaves register process-global Prometheus collectors. Load
    # them before the isolation window so teardown does not evict them and a
    # later core fixture cannot register the same collectors a second time.
    for name in (
        'utils.speakers.context',
        'utils.stt.batch_language',
        'utils.batch_pipeline.language_metrics',
    ):
        importlib.import_module(name)
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
        'database.sync_empty_recovery',
        'database.owner_profile_updates',
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
        'utils.dream_vocabulary',
        'utils.sync.bridge',
        'utils.executors',
        'utils.fair_use',
        'utils.http_client',
        'utils.metrics',
        'utils.observability.fallback',
        'utils.observability.transcription',
        'utils.other.storage',
        'utils.speaker_learning_jobs',
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
    fakes['utils.dream_vocabulary'].keyterms = AsyncMock(side_effect=lambda uid, existing: existing)
    # Files that hold this module-scoped stub set open (e.g. the reprocess
    # coalesce tests) also import routers/sync.py inside it: its import-time
    # handler-budget resolution compares these constants inside min(), so they
    # must be real numbers rather than auto-mocked attributes.
    fakes['database.sync_jobs'].RUN_LOCK_TTL_SECONDS = 1800
    fakes['database.sync_jobs'].STALE_THRESHOLD_SECONDS = 600
    fakes['database.sync_jobs'].QUEUED_DISPATCH_STALE_SECONDS = 1800
    fakes['utils.cloud_tasks'].DISPATCH_DEADLINE_SECONDS = 1500
    return fakes
