"""Historical-tier (T1+) ingest through the batch projection: stamp at build, settle at finish."""

from __future__ import annotations

import time
from unittest.mock import Mock

import pytest

# build_incoming's function-level imports land in whichever test calls it first;
# import them at collection so the duration-guard call phase stays clean.
import models.conversation  # noqa: F401
import utils.conversations.deterministic_minimum  # noqa: F401
import utils.stt.pre_recorded  # noqa: F401
import utils.sync.capture  # noqa: F401
from config import historical_tier
from config.policy import resolve_stage_policy
from tests.unit.test_batch_pipeline_owner_chain_projection import SUCCESS_PAYLOAD
from tests.unit.test_batch_pipeline_projection_followup import followup, owner_claim  # noqa: F401  (fixtures)
from utils.batch_pipeline import projection, projection_followup
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.projection import build_incoming
from utils.sync import bridge


@pytest.fixture(autouse=True)
def _tier_on(monkeypatch):
    monkeypatch.delenv(historical_tier.TIER_ENABLED_ENV, raising=False)
    monkeypatch.delenv('ENRICHMENT_MAX_AGE_HOURS', raising=False)


def _batch_incoming(age_hours, **item_fields):
    item = WorkItem(
        'seg', 'sim-owner', time.time() - age_hours * 3600, 'gs://synthetic/audio', 1.0, Priority.DEEP, **item_fields
    )
    payload = {**SUCCESS_PAYLOAD, 'audio_seconds': 1.0, 'speech_seconds': 0.5}
    payload['speech_spans'] = [{'start': 0.0, 'end': 0.5}]
    payload['words'] = [{'word': 'Hello there.', 'timestamp': [0.0, 0.5]}]
    return build_incoming(item, ProjectionBinding('sim-owner', 'job', 'content', ('seg',)), payload)


def test_batch_old_capture_is_built_historical():
    incoming = _batch_incoming(80)
    assert incoming['processing_tier'] == 'historical'
    assert incoming['terminal_no_derived_effects'] is True
    assert incoming['structured']['title_provenance'] == 'historical_minimum'


@pytest.mark.parametrize('fields', [{}, {'capture_time_trust': 'untrusted'}, {'capture_clock_estimated': True}])
def test_batch_recent_or_untrusted_capture_keeps_full_processing(fields):
    incoming = _batch_incoming(2 if not fields else 80, **fields)
    assert incoming.get('processing_tier') is None
    assert incoming['structured']['title_provenance'] == 'server_minimum'


def test_the_estimated_clock_bit_stays_off_the_wire_unless_set():
    item = WorkItem('seg', 'sim-owner', 1.0, 'gs://synthetic/audio', 1.0, Priority.DEEP)
    assert 'capture_clock_estimated' not in item.to_dict()
    flagged = WorkItem(
        'seg', 'sim-owner', 1.0, 'gs://synthetic/audio', 1.0, Priority.DEEP, capture_clock_estimated=True
    )
    assert flagged.to_dict()['capture_clock_estimated'] is True
    assert WorkItem(**flagged.to_dict()) == flagged


def _finish(monkeypatch, settled):
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',))
    policy = resolve_stage_policy(binding.owner_id, 'projection')
    monkeypatch.setattr(bridge, 'finish_sync_bridges', lambda *_, **kw: 'old-row')
    projector = projection.Projector(Mock(), Mock())
    monkeypatch.setattr(projector.store, 'settle_deleted_output', Mock())
    mark = Mock()
    monkeypatch.setattr(projector.store, 'mark_enrichment', mark)
    ready = Mock(side_effect=AssertionError('acknowledgement goes through the guarded enrichment transaction'))
    monkeypatch.setattr(projector.store, 'ready', ready)
    settle = Mock(return_value=settled)
    monkeypatch.setattr(projection.historical_ingest, 'settle', settle)
    receipt = {
        'state': 'persisted',
        'conversation_id': 'old-row',
        'audio_required': False,
        'enrichment_required': True,
        'historical': True,
        'language': 'en',
    }
    projector.finish_part(Mock(segment_id='segment'), binding, receipt, None, policy=policy)
    settle.assert_called_once_with('synthetic-owner', 'old-row', producer='batch')
    return mark


def test_batch_historical_receipt_acknowledges_inside_the_guarded_enrichment_transaction(monkeypatch):
    mark = _finish(monkeypatch, True)
    mark.assert_called_once()
    assert mark.call_args.kwargs['historical_settled'] is True


def test_an_output_that_is_not_historical_keeps_its_enrichment_mark(monkeypatch):
    mark = _finish(monkeypatch, False)
    mark.assert_called_once()
    assert 'historical_settled' not in mark.call_args.kwargs


@pytest.mark.asyncio
async def test_batch_followup_acknowledges_a_historical_receipt_through_the_guard(followup, monkeypatch):
    f = followup
    settle = Mock(return_value=True)
    monkeypatch.setattr(projection_followup.historical_ingest, 'settle', settle)
    item = WorkItem(**{key: value for key, value in f.jobs['head'].items() if key in WorkItem.__dataclass_fields__})
    receipt = {**f.receipts['head'], 'historical': True}
    await f.runner.finish_part(item, f.binding, receipt, None)
    settle.assert_called_once_with('owner', 'head', producer='batch')
    f.projector.store.mark_enrichment.assert_called_once()
    assert f.projector.store.mark_enrichment.call_args.kwargs['historical_settled'] is True


@pytest.mark.asyncio
async def test_batch_followup_marks_when_an_output_is_not_historical(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup.historical_ingest, 'settle', Mock(return_value=False))
    item = WorkItem(**{key: value for key, value in f.jobs['head'].items() if key in WorkItem.__dataclass_fields__})
    receipt = {**f.receipts['head'], 'historical': True}
    await f.runner.finish_part(item, f.binding, receipt, None)
    f.projector.store.mark_enrichment.assert_called_once()
    assert 'historical_settled' not in f.projector.store.mark_enrichment.call_args.kwargs
