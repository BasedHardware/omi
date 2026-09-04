"""Ratchet: listed production drain modules must call the substrate drain."""

from __future__ import annotations

from pathlib import Path

from database.durable_queue_age import QUEUE_AGE_SAMPLERS
from utils.metrics import OMI_QUEUE_NAMES

REPO = Path(__file__).resolve().parents[3]

# Checked-in inventory. Do not replace this with a repo-wide grep.
PRODUCTION_DRAIN_MODULES = (
    ('backend/database/memory_outbox_worker.py', 'drain_isolated('),
    ('backend/database/memory_vector_repair_outbox_worker.py', 'drain_isolated('),
    ('backend/utils/task_intelligence/candidate_service.py', 'drain_isolated('),
    ('backend/database/candidate_integration_outbox.py', 'decide_attempt('),
    ('backend/database/chat_first_intent_queue.py', 'drain_isolated('),
    ('backend/database/chat_first_intents.py', 'drain_intent_batch('),
    ('backend/utils/chat_first_materialize_queue.py', 'drain_isolated('),
    ('backend/utils/memory/daily_memory_sweep_queue.py', 'drain_isolated('),
    ('backend/utils/memory/daily_memory_sweep.py', 'drain_sweep_uids('),
    ('backend/utils/other/notifications.py', 'drain_isolated_async('),
    ('backend/utils/task_intelligence/workstream_association.py', 'drain_isolated('),
    ('backend/database/frame_requests.py', 'drain_isolated('),
    ('backend/database/projection_repair.py', 'drain_isolated('),
    ('backend/utils/pusher_finalization.py', 'decide_attempt('),
    ('desktop/macos/agent/src/runtime/conversation-journal.ts', 'drainIsolated('),
    ('desktop/macos/agent/src/runtime/journal-outbox-pump.ts', 'drainIsolated('),
)

MODULES_THAT_MUST_NOT_OBSERVE_GAUGE = (
    'backend/database/memory_outbox_worker.py',
    'backend/database/memory_vector_repair_outbox_worker.py',
    'backend/utils/task_intelligence/candidate_service.py',
    'backend/database/candidate_integration_outbox.py',
    'backend/database/chat_first_intents.py',
    'backend/routers/chat_first.py',
    'backend/utils/memory/daily_memory_sweep.py',
    'backend/utils/memory/daily_memory_sweep_queue.py',
    'backend/utils/other/notifications.py',
    'backend/utils/task_intelligence/workstream_association.py',
    'backend/database/frame_requests.py',
    'backend/database/projection_repair.py',
    'backend/services/conversation_finalization.py',
    'backend/utils/memory/short_term_promotion.py',
    'backend/main.py',
)

GAUGE_PUBLISHER = 'backend/utils/durable_queue_metrics.py'


def test_listed_production_drains_call_the_substrate() -> None:
    missing: list[str] = []
    for relative, token in PRODUCTION_DRAIN_MODULES:
        source = (REPO / relative).read_text(encoding='utf-8')
        if token not in source:
            missing.append(f'{relative} (missing {token})')
    assert not missing, 'production drain modules lost the substrate: ' + '; '.join(missing)


def test_omi_queue_names_match_age_samplers() -> None:
    assert set(OMI_QUEUE_NAMES) == set(QUEUE_AGE_SAMPLERS)


def test_omi_queue_family_is_not_labels_touched_at_import() -> None:
    source = (REPO / 'backend/utils/metrics.py').read_text(encoding='utf-8')
    assert 'OMI_QUEUE_OLDEST_READY_AGE_SECONDS.labels' not in source
    from utils.metrics import generate_latest

    exported = generate_latest().decode()
    assert 'omi_queue_oldest_ready_age_seconds{' not in exported


def test_only_the_periodic_publisher_observes_the_gauge() -> None:
    publisher = (REPO / GAUGE_PUBLISHER).read_text(encoding='utf-8')
    assert 'def observe_oldest_ready_age' in publisher
    offenders: list[str] = []
    for relative in MODULES_THAT_MUST_NOT_OBSERVE_GAUGE:
        source = (REPO / relative).read_text(encoding='utf-8')
        if 'observe_oldest_ready_age' in source:
            offenders.append(relative)
    assert not offenders, 'drain/request modules still observe the gauge: ' + ', '.join(offenders)
    assert 'publish_all_queue_oldest_ready_ages' in (REPO / 'backend/main.py').read_text(encoding='utf-8')
    assert 'publish_all_queue_oldest_ready_ages' in (REPO / 'backend/database/durable_queue_age.py').read_text(
        encoding='utf-8'
    )
