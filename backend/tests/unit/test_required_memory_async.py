"""Owed normalization borrows separate leaf pools and preserves retry results."""

from types import SimpleNamespace
import threading

import pytest

from utils.memory import canonical_required_processing as processing
from utils.memory import short_term_promotion as maintenance
from utils.memory.promotion_flex import PromotionFlexDeferred
from models.memory_apply import MemoryControlState


@pytest.mark.asyncio
async def test_required_model_wait_does_not_occupy_the_database_executor(monkeypatch):
    calls = []
    row = SimpleNamespace(memory_id='synthetic-required')
    context = (row, object(), 'lease', object())

    def mark(name):
        calls.append((name, threading.current_thread().name))

    def list_items(*_, **__):
        mark('list')
        return [row]

    def claim(*_, **__):
        mark('claim')
        return processing.RequiredProcessingAttempt(context=context)

    processed = object()

    def normalize(item):
        assert item is row
        mark('normalize')
        return processed

    def settle(uid, current, **kwargs):
        assert current is context and kwargs['processed'] is processed
        mark('settle')
        return processing.RequiredMemoryProcessingResult(memory_id=row.memory_id, processed=True, attempted=True)

    monkeypatch.setattr(processing, 'list_pending_required_processing_items', list_items)
    monkeypatch.setattr(processing, '_begin_required_processing', claim)
    monkeypatch.setattr(processing, '_settle_required_processing', settle)
    report = await processing.run_required_memory_processing_async(
        'synthetic-owner', db_client=object(), processor=normalize
    )
    assert report.processed_memory_ids == [row.memory_id] and report.attempted_count == 1
    assert [name for name, _ in calls] == ['list', 'claim', 'normalize', 'settle']
    assert all(thread.startswith('llm') if name == 'normalize' else thread.startswith('db') for name, thread in calls)


@pytest.mark.asyncio
async def test_deferral_is_settled_before_the_page_stops(monkeypatch):
    row = SimpleNamespace(memory_id='synthetic-required')
    context = (row, object(), 'lease', object())
    monkeypatch.setattr(processing, 'list_pending_required_processing_items', lambda *_, **__: [row, row])
    monkeypatch.setattr(
        processing, '_begin_required_processing', lambda *_, **__: processing.RequiredProcessingAttempt(context=context)
    )
    settled = []

    def normalize(item):
        raise PromotionFlexDeferred('capacity')

    def settle(uid, current, **kwargs):
        assert isinstance(kwargs['error'], PromotionFlexDeferred)
        settled.append(current)
        return processing.RequiredMemoryProcessingResult(
            memory_id=row.memory_id, attempted=True, retryable=True, error_code='flex_deferred'
        )

    monkeypatch.setattr(processing, '_settle_required_processing', settle)
    with pytest.raises(PromotionFlexDeferred):
        await processing.run_required_memory_processing_async(
            'synthetic-owner', db_client=object(), processor=normalize
        )
    assert settled == [context]


@pytest.mark.asyncio
async def test_zero_limit_does_not_query_or_claim(monkeypatch):
    def forbidden(*_, **__):
        raise AssertionError('zero budget must not query')

    monkeypatch.setattr(processing, 'list_pending_required_processing_items', forbidden)
    result = await processing.run_required_memory_processing_async(
        'synthetic-owner', db_client=object(), processor=forbidden, limit=0
    )
    assert result.attempted_count == 0


@pytest.mark.asyncio
async def test_skipped_lease_does_not_call_the_model(monkeypatch):
    row = SimpleNamespace(memory_id='synthetic-required')
    monkeypatch.setattr(processing, 'list_pending_required_processing_items', lambda *_, **__: [row])
    monkeypatch.setattr(
        processing,
        '_begin_required_processing',
        lambda *_, **__: processing.RequiredProcessingAttempt(
            result=processing.RequiredMemoryProcessingResult(memory_id=row.memory_id, skipped_reason='leased')
        ),
    )

    def forbidden(*_, **__):
        raise AssertionError('another worker owns the lease')

    result = await processing.run_required_memory_processing_async(
        'synthetic-owner', db_client=object(), processor=forbidden
    )
    assert result.skipped_memory_ids == [row.memory_id] and result.attempted_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('writer_mode', ['compatibility', 'ledger'])
async def test_async_host_drains_before_and_after_only_the_owned_intake_phases(monkeypatch, writer_mode):
    order = []
    uid = 'synthetic-maintenance'
    monkeypatch.setattr(
        maintenance,
        'ensure_canonical_apply_control_state',
        lambda *_, **__: MemoryControlState(
            uid=uid, writer_mode=writer_mode, head_commit_id='head0', account_generation=1, source_generation=1
        ),
    )

    def tick(**kwargs):
        assert kwargs['config'].limit == 1
        assert threading.current_thread().name.startswith('db')
        order.append('outbox')
        return {'delivered_count': 1, 'leased_count': 0}

    monkeypatch.setattr(maintenance, 'run_canonical_memory_outbox_worker_tick', tick)

    async def required(*_, **__):
        order.append('required')
        return processing.RequiredMemoryProcessingReport(uid=uid)

    monkeypatch.setattr(maintenance, 'run_required_memory_processing_async', required)

    def ttl(*_, **kwargs):
        assert kwargs['limit'] == 25
        order.append('ttl')
        return maintenance.CanonicalShortTermLifecycleReport(uid=uid)

    def complete(*_, **kwargs):
        order.append('complete')
        return maintenance.RequiredIntakeCompletion(uid=uid)

    monkeypatch.setattr(maintenance, 'run_canonical_short_term_ttl_lifecycle', ttl)
    monkeypatch.setattr(maintenance, 'complete_required_intake', complete)
    result = await maintenance.run_canonical_short_term_maintenance_async(
        uid, db_client=object(), run_id='async-host', required_processor=lambda _: None, required_processing_limit=25
    )
    assert order == (
        ['outbox', 'required', 'ttl', 'complete', 'outbox'] if writer_mode == 'compatibility' else ['outbox', 'outbox']
    )
    assert result.outbox['delivered_count'] == 2
