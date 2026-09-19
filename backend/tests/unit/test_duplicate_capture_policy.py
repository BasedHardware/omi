"""Synthetic contract cases through the real durable finalizer and DB writer.

Contract: the cross-device task requires a non-destructive overlap hint, replacing
#13703's content-based auto-discard. External providers and query discovery are
controlled; production matching and strict transaction writes run unchanged.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from database import conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import duplicate_capture as policy
from utils.conversations import finalizer
from utils.conversations import process_conversation as processor

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
UID = 'synthetic-overlap-user'


def row(id, source, start=0, end=600, **extra):
    return {
        'id': id,
        'source': source,
        'status': 'completed',
        'discarded': False,
        'started_at': T0 + timedelta(seconds=start),
        'finished_at': T0 + timedelta(seconds=end),
        'created_at': T0,
        'structured': {},
        'transcript_segments': [],
        'external_data': {'preserved': 'fixture'},
        **extra,
    }


def path(id, uid=UID):
    return ('users', uid, 'conversations', id)


@pytest.fixture
def harness(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, id, **kw: deepcopy(store.rows.get(path(id, uid)))
    )

    def query(uid, *, status, finished_after, limit):
        return sorted(
            [
                deepcopy(r)
                for p, r in store.rows.items()
                if p[:2] == ('users', uid) and r['status'] == status and r['finished_at'] >= finished_after
            ],
            key=lambda r: r['finished_at'],
        )[:limit]

    monkeypatch.setattr(conversations_db, 'get_conversations_finished_after', query)

    async def inline(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def process(uid, language, conversation, **kwargs):
        # Controllable enrichment seam: persist completion, as the coordinator does.
        store.rows[path(conversation.id, uid)]['status'] = 'completed'
        conversation.status = 'completed'
        kwargs['persistence_observer'](True)
        return conversation

    monkeypatch.setattr(finalizer, 'run_blocking', inline)
    monkeypatch.setattr(finalizer, 'process_conversation', process)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(finalizer, 'extract_memories', MagicMock())
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', AsyncMock())
    monkeypatch.setattr(finalizer, 'record_and_persist_finalized_meeting_receipt', MagicMock())
    monkeypatch.setattr(finalizer, 'persist_capture_arrival_intent', MagicMock())
    monkeypatch.setattr(
        finalizer, 'resolve_frame_request_authority', AsyncMock(return_value=SimpleNamespace(enabled=False))
    )
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *a: {'status': 'claimed', 'fanout_key': 'fixture'},
    )
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', lambda *a: True)
    monkeypatch.delenv('CROSS_DEVICE_DEDUP_MIN_OVERLAP_SECONDS', raising=False)
    monkeypatch.delenv('CROSS_DEVICE_DEDUP_MIN_OVERLAP_RATIO', raising=False)
    return store


async def finalize(id):
    return await finalizer.finalize_persisted_conversation(
        UID, id, finalization_job_id='synthetic-job', dispatch_generation=1, lease_epoch=1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('last', ['pendant', 'desktop'])
async def test_finalization_links_shorter_capture_in_either_order_and_replay(harness, last, caplog):
    harness.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    harness.rows[path(last)]['status'] = 'processing'
    before = deepcopy(harness.rows)
    with caplog.at_level(logging.INFO, logger=policy.logger.name):
        assert await finalize(last) == finalizer.ConversationFinalizationDisposition.completed
        await finalize(last)
    before[path(last)]['status'] = 'completed'
    assert harness.rows[path('pendant')] == before[path('pendant')]
    secondary = harness.rows[path('desktop')]
    assert secondary['external_data'] == {
        'preserved': 'fixture',
        'duplicate_capture_of': 'pendant',
        'cross_device_duplicate': {
            'primary_conversation_id': 'pendant',
            'method': 'wall_clock_overlap',
            'overlap_seconds': 490.0,
            'overlap_ratio': 1.0,
        },
    }
    secondary_without_hint = deepcopy(secondary)
    secondary_without_hint['external_data'] = before[path('desktop')]['external_data']
    assert secondary_without_hint == before[path('desktop')]
    events = [r.message for r in caplog.records if 'cross_device_duplicate_detected' in r.message]
    assert len(events) == 1
    assert UID not in events[0] and 'pendant' not in events[0]
    assert sum(len(t.updates) for t in harness.transactions) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case',
    [
        'threshold',
        'below_threshold',
        'low_overlap',
        'same_source',
        'primary_discarded',
        'secondary_discarded',
        'other_user',
        'processing',
        'missing_source',
        'invalid_window',
    ],
)
async def test_finalizer_does_not_link_ineligible_pairs(harness, case):
    primary, secondary = row('pendant', 'omi'), row('desktop', 'desktop', 100, 590)
    if case in {'threshold', 'below_threshold'}:
        secondary.update(
            started_at=T0 + timedelta(seconds=540 if case == 'threshold' else 550),
            finished_at=T0 + timedelta(seconds=600),
        )
    elif case == 'low_overlap':
        secondary.update(started_at=T0 + timedelta(seconds=450), finished_at=T0 + timedelta(seconds=900))
    elif case == 'same_source':
        secondary['source'] = 'omi'
    elif case == 'primary_discarded':
        primary['discarded'] = True
    elif case == 'secondary_discarded':
        secondary['discarded'] = True
    elif case == 'processing':
        primary['status'] = 'processing'
    elif case == 'missing_source':
        primary.pop('source')
    elif case == 'invalid_window':
        primary['finished_at'] = primary['started_at']
    harness.rows[path('pendant', 'other-synthetic-user' if case == 'other_user' else UID)] = primary
    harness.rows[path('desktop')] = secondary
    before = deepcopy(harness.rows)
    await finalize('desktop')
    assert harness.rows == before


@pytest.mark.asyncio
async def test_equal_durations_have_one_stable_primary(harness):
    harness.rows.update({path('a'): row('a', 'omi'), path('b'): row('b', 'desktop')})
    await finalize('a')
    await finalize('b')
    assert 'duplicate_capture_of' not in harness.rows[path('a')]['external_data']
    assert harness.rows[path('b')]['external_data']['duplicate_capture_of'] == 'a'


@pytest.mark.asyncio
@pytest.mark.parametrize('side', ['pendant', 'desktop'])
@pytest.mark.parametrize('change', ['discard', 'delete', 'window', 'status'])
async def test_transaction_fences_changes_after_discovery(harness, monkeypatch, side, change):
    harness.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    original = conversations_db.link_duplicate_capture

    def race(*args):
        if change == 'delete':
            del harness.rows[path(side)]
        elif change == 'discard':
            harness.rows[path(side)]['discarded'] = True
        elif change == 'window':
            harness.rows[path(side)]['finished_at'] += timedelta(seconds=1)
        else:
            harness.rows[path(side)]['status'] = 'processing'
        return original(*args)

    monkeypatch.setattr(conversations_db, 'link_duplicate_capture', race)
    await finalize('desktop')
    assert all('duplicate_capture_of' not in r['external_data'] for r in harness.rows.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['query', 'write', 'config'])
async def test_optional_hint_failure_preserves_finalization(harness, monkeypatch, failure):
    harness.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    fallback = MagicMock()
    monkeypatch.setattr(policy, 'record_fallback', fallback)
    if failure == 'config':
        monkeypatch.setenv('CROSS_DEVICE_DEDUP_MIN_OVERLAP_RATIO', 'nan')
    else:
        name = 'get_conversations_finished_after' if failure == 'query' else 'link_duplicate_capture'
        monkeypatch.setattr(conversations_db, name, MagicMock(side_effect=RuntimeError('must not log this')))
    assert await finalize('desktop') == finalizer.ConversationFinalizationDisposition.completed
    fallback.assert_called_once()
    assert all('duplicate_capture_of' not in r['external_data'] for r in harness.rows.values())


@pytest.mark.asyncio
async def test_thresholds_are_configurable(harness, monkeypatch):
    harness.rows.update({path('pendant'): row('pendant', 'omi'), path('desktop'): row('desktop', 'desktop', 100, 590)})
    monkeypatch.setenv('CROSS_DEVICE_DEDUP_MIN_OVERLAP_SECONDS', '500')
    await finalize('desktop')
    assert 'duplicate_capture_of' not in harness.rows[path('desktop')]['external_data']
    monkeypatch.setenv('CROSS_DEVICE_DEDUP_MIN_OVERLAP_SECONDS', '60')
    monkeypatch.setenv('CROSS_DEVICE_DEDUP_MIN_OVERLAP_RATIO', '1')
    await finalize('desktop')
    assert 'duplicate_capture_of' not in harness.rows[path('desktop')]['external_data']


@pytest.mark.asyncio
async def test_legacy_reverse_pointer_does_not_create_cycle(harness):
    primary = row('pendant', 'omi')
    primary['external_data']['duplicate_capture_of'] = 'desktop'
    harness.rows.update({path('pendant'): primary, path('desktop'): row('desktop', 'desktop', 100, 590)})
    before = deepcopy(harness.rows)
    await finalize('desktop')
    assert harness.rows == before


@pytest.mark.parametrize('persisted', [True, False])
def test_sync_processor_links_only_after_successful_completion(harness, monkeypatch, persisted):
    harness.rows.update(
        {
            path('pendant'): row('pendant', 'omi', status='processing'),
            path('desktop'): row('desktop', 'desktop', 100, 590),
        }
    )
    conversation = finalizer.deserialize_conversation(harness.rows[path('pendant')])
    monkeypatch.setattr(processor, '_enrich_meeting_context', MagicMock())
    monkeypatch.setattr(processor, '_get_structured', lambda *a, **kw: (conversation.structured, False))
    monkeypatch.setattr(processor, '_get_conversation_obj', lambda *a, **kw: conversation)
    monkeypatch.setattr(processor, '_calendar_auto_link_enabled', lambda: False)
    monkeypatch.setattr(processor, 'conversation_apps_opt_in_only', lambda: False)
    monkeypatch.setattr(processor, 'trigger_conversation_apps', MagicMock())
    monkeypatch.setattr(processor, 'submit_with_context', MagicMock())

    def persist(uid, payload):
        if persisted:
            harness.rows[path(payload['id'], uid)].update(payload)
        return persisted

    monkeypatch.setattr(processor.lifecycle_service, 'persist_processed_conversation', persist)
    processor.process_conversation(UID, 'en', conversation, is_reprocess=True, defer_memory_extraction=True)
    assert ('duplicate_capture_of' in harness.rows[path('desktop')]['external_data']) is persisted
