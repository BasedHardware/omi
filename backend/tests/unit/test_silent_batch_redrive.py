"""Silent repair survives CAS replay, revision changes, and asynchronous enrichment."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from utils.batch_pipeline.speech_redrive import redrive_one
from utils.conversations.silent_redrive import is_silent_redrive
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from models.conversation_enums import ConversationSource
from utils.enrichment import callback


def test_silent_intent_is_persisted_and_cannot_change_on_replay(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    assert (
        redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'plan',
            old,
            server_flags=SERVING_ENV,
            clock=lambda: 100,
            silent=True,
        )
        == 'recovered'
    )
    assert row(client)['speech_redrive']['silent'] is True
    with pytest.raises(ProjectionBlocked):
        redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'plan',
            old,
            server_flags=SERVING_ENV,
            clock=lambda: 101,
            silent=False,
        )
    alternate.assert_called_once()


def test_projection_stamps_silence_in_same_assignment_transaction(setup):
    client, store, binding, *_ = setup
    session = ProjectionStore(store).session('bad', binding, 100)
    session.job = {'speech_redrive': {'silent': True}}
    client.rows[('batch_pipeline_prod_results', 'bad')] = {}
    conversation = ('users', binding.owner_id, 'conversations', 'target')
    client.rows[conversation] = {'sync_content_revision': 7}
    session.entry = {}
    tx = client.transaction()
    receipt = session.persist(tx, ({'id': 'target', 'sync_content_revision': 7}, False, []))
    tx._commit()
    assert receipt['silent_redrive'] is True and receipt['enrichment_required'] is True
    assert is_silent_redrive(client.rows[conversation])
    # Ordinary subsequent content is not silenced by stale repair metadata.
    client.rows[conversation]['sync_content_revision'] = 8
    assert not is_silent_redrive(client.rows[conversation])


@pytest.mark.parametrize(
    'revision,marker,expected',
    [(7, 7, True), (8, 7, False), (0, 0, False), (True, 1, False), (1, True, False), (None, None, False)],
)
def test_suppression_requires_exact_positive_integer_revision(revision, marker, expected):
    assert is_silent_redrive({'sync_content_revision': revision, 'sync_silent_redrive_revision': marker}) is expected


@pytest.mark.parametrize('silent', [True, False])
def test_enrichment_uses_durable_revision_and_never_sends_silent_creation_webhook(monkeypatch, silent):
    data = {'id': 'synthetic', 'sync_content_revision': 7, 'sync_silent_redrive_revision': 7 if silent else 6}
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *a: data)
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    conversation = SimpleNamespace(discarded=True, source=ConversationSource.limitless, client_platform='mobile')
    monkeypatch.setattr(callback, 'deserialize_conversation', lambda _: conversation)
    processed = SimpleNamespace(discarded=False)
    process = Mock(return_value=processed)
    monkeypatch.setattr(callback, 'process_conversation', process)
    webhook = Mock()
    monkeypatch.setattr(callback, 'submit_with_context', webhook)
    monkeypatch.setattr(callback, 'record_client_journey_accepted', lambda *a: None)
    monkeypatch.setattr(callback, 'record_client_journey_terminal', lambda *a: None)
    token = callback.PROCESS_CONTEXT.set(None)
    try:
        assert callback.enrich_conversation('synthetic-owner', 'synthetic', 'en') is processed
    finally:
        callback.PROCESS_CONTEXT.reset(token)
    assert process.call_args.kwargs['defer_derived_effects'] is silent
    assert webhook.call_count == (0 if silent else 1)


def test_preexisting_effects_only_delivery_cannot_bypass_silent_revision(monkeypatch):
    from utils.conversations import lazy_enrichment

    data = {'status': 'completed', 'sync_content_revision': 7, 'sync_silent_redrive_revision': 7}
    monkeypatch.setattr(lazy_enrichment.conversations_db, 'get_conversation', lambda *a: data)
    decode = Mock(side_effect=AssertionError('silent effects must not run'))
    monkeypatch.setattr(lazy_enrichment, 'deserialize_conversation', decode)
    lazy_enrichment.enrich_settled('synthetic-owner', 'synthetic', 'en')
    decode.assert_not_called()
