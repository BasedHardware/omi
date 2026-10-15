"""Projection binding validation and provider-free retry/publication guards."""

from dataclasses import replace
from unittest.mock import Mock

from google.api_core.exceptions import Aborted, InvalidArgument
import pytest

from utils.batch_pipeline.contracts import ProjectionBinding
from database.batch_pipeline_projection import ProjectionStore


@pytest.fixture
def binding():
    return ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',))


@pytest.mark.parametrize(
    'field,value',
    [
        ('segment_ids', ()),
        ('segment_ids', ('same', 'same')),
        ('segment_ids', tuple(str(n) for n in range(129))),
        ('owner_id', ''),
        ('content_id', 'path/id'),
        ('data_protection_level', 'e2ee'),
        ('run_token', 'without-epoch'),
        ('privacy_generation', -1),
    ],
)
def test_invalid_projection_binding_refused(binding, field, value):
    with pytest.raises(ValueError):
        replace(binding, **{field: value})


def test_read_contention_retry_uses_fresh_transactions_when_enabled(monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    from database import firestore_transaction_retry

    actual = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast(*args, **kwargs):
        return actual(*args, **kwargs, sleep=lambda _: None)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast)
    client = Mock()
    client.transaction.side_effect = [object(), object()]
    operation = Mock(side_effect=[Aborted('synthetic'), 'persisted'])
    store = ProjectionStore(Mock(client=client))
    assert store.run(operation) == 'persisted'
    assert operation.call_args_list[0] != operation.call_args_list[1]


def test_read_contention_default_off_and_non_contention_never_replayed(monkeypatch):
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    client = Mock()
    operation = Mock(side_effect=Aborted('synthetic'))
    store = ProjectionStore(Mock(client=client))
    with pytest.raises(Aborted):
        store.run(operation)
    assert operation.call_count == 1
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    operation = Mock(side_effect=InvalidArgument('not contention'))
    with pytest.raises(InvalidArgument):
        store.run(operation)
    assert operation.call_count == 1


def test_custom_enrichment_mutation_cannot_bypass_runtime_stage_guard(monkeypatch):
    from utils.sync import reprocess

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    mutate = Mock()
    with pytest.raises(RuntimeError, match='production or a Firestore emulator'):
        reprocess.mark('synthetic-owner', 'conversation', 'en', mutate=mutate)
    mutate.assert_not_called()


@pytest.mark.parametrize(
    'spans',
    [
        None,
        [],
        [{'start': 2, 'end': 1}],
        [{'start': 0, 'end': float('nan')}],
        [{'start': -1, 'end': 1}],
        [{'start': 0, 'end': 5}],
        [{'start': 0, 'end': 2}, {'start': 1, 'end': 3}],
    ],
)
def test_original_vad_span_contract_rejects_invalid_or_noncanonical_union(spans):
    from utils.batch_pipeline.contracts import projection_speech_spans

    with pytest.raises(ValueError):
        projection_speech_spans({'speech_spans': spans, 'speech_seconds': 2}, 4)


def test_original_vad_union_must_agree_with_speech_metering():
    from utils.batch_pipeline.contracts import projection_speech_spans

    payload = {'speech_spans': [{'start': 0, 'end': 1}, {'start': 150, 'end': 151}], 'speech_seconds': 2}
    assert projection_speech_spans(payload, 160) == payload['speech_spans']
    payload['speech_seconds'] = 3
    with pytest.raises(ValueError, match='accounting'):
        projection_speech_spans(payload, 160)


def test_production_result_cannot_invent_vad_groups_from_transcript_gaps():
    from utils.batch_pipeline.contracts import WorkItem, Priority
    from utils.batch_pipeline.projection_parts import split_result

    item = WorkItem(
        'segment', 'synthetic-owner', 0, 'gs://synthetic/wav', 200, Priority.FRESH, requires_compute_admission=True
    )
    payload = {'audio_seconds': 200, 'words': [{'word': 'Text.', 'timestamp': [0, 1]}]}
    with pytest.raises(ValueError, match='speech_spans'):
        split_result(item, payload)
