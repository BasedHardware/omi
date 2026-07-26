from types import SimpleNamespace

import pytest

from database import conversation_finalization_jobs as jobs_db
from utils.conversations import enrichment_plan


def test_required_effect_contract_matches_durable_ledger():
    assert enrichment_plan.PLAN_VERSION == jobs_db.FINALIZATION_FANOUT_PLAN_VERSION
    assert enrichment_plan.REQUIRED_EFFECT_KEYS == jobs_db.REQUIRED_EFFECT_KEYS


def _effect(key, effects):
    return next(effect for effect in effects if effect.key == key)


def _conversation():
    return SimpleNamespace(
        id='conversation-1',
        transcript_segments=[{'text': 'persisted transcript'}],
        started_at=None,
        created_at=None,
    )


def test_strict_plan_blocks_structured_vector_before_leaf_call_when_store_is_missing(monkeypatch):
    conversation = _conversation()
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', None)
    monkeypatch.setattr(
        enrichment_plan,
        'save_structured_vector',
        lambda *_: (_ for _ in ()).throw(AssertionError('structured vector leaf executed')),
    )

    effects = enrichment_plan.required_enrichment_effects('uid-1', conversation)
    with pytest.raises(enrichment_plan.RequiredEnrichmentUnavailable) as raised:
        _effect('structured_vector', effects).execute()

    assert str(raised.value) == enrichment_plan.REQUIRED_ENRICHMENT_UNAVAILABLE_CODE


def test_disabled_transcript_index_is_a_completed_noop_without_vector_store(monkeypatch):
    conversation = _conversation()
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', None)
    monkeypatch.setattr(enrichment_plan, 'TRANSCRIPT_CHUNK_INDEXING_ENABLED', False)
    monkeypatch.setattr(
        enrichment_plan,
        'save_transcript_chunk_vectors',
        lambda *_: (_ for _ in ()).throw(AssertionError('disabled transcript index executed')),
    )

    effects = enrichment_plan.required_enrichment_effects('uid-1', conversation)
    _effect('transcript_vectors', effects).execute()


def test_strict_plan_blocks_enabled_transcript_index_before_leaf_call_when_store_is_missing(monkeypatch):
    conversation = _conversation()
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', None)
    monkeypatch.setattr(enrichment_plan, 'TRANSCRIPT_CHUNK_INDEXING_ENABLED', True)
    monkeypatch.setattr(
        enrichment_plan,
        'save_transcript_chunk_vectors',
        lambda *_: (_ for _ in ()).throw(AssertionError('transcript vector leaf executed')),
    )

    effects = enrichment_plan.required_enrichment_effects('uid-1', conversation)
    with pytest.raises(enrichment_plan.RequiredEnrichmentUnavailable) as raised:
        _effect('transcript_vectors', effects).execute()

    assert str(raised.value) == enrichment_plan.REQUIRED_ENRICHMENT_UNAVAILABLE_CODE


def test_available_vector_store_runs_real_plan_wrappers_in_order(monkeypatch):
    calls = []
    conversation = _conversation()
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', object())
    monkeypatch.setattr(enrichment_plan, 'TRANSCRIPT_CHUNK_INDEXING_ENABLED', True)
    monkeypatch.setattr(enrichment_plan, 'save_structured_vector', lambda *_: calls.append('structured_vector'))
    monkeypatch.setattr(enrichment_plan, 'save_transcript_chunk_vectors', lambda *_: calls.append('transcript_vectors'))

    effects = enrichment_plan.required_enrichment_effects('uid-1', conversation)
    assert tuple(effect.key for effect in effects) == enrichment_plan.REQUIRED_EFFECT_KEYS
    for effect in effects:
        effect.execute()

    assert calls == list(enrichment_plan.REQUIRED_EFFECT_KEYS)


def test_optional_store_plan_invokes_vector_leaves_when_store_is_missing(monkeypatch):
    calls = []
    conversation = _conversation()
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', None)
    monkeypatch.setattr(enrichment_plan, 'TRANSCRIPT_CHUNK_INDEXING_ENABLED', True)
    monkeypatch.setattr(enrichment_plan, 'save_structured_vector', lambda *_: calls.append('structured_vector'))
    monkeypatch.setattr(enrichment_plan, 'save_transcript_chunk_vectors', lambda *_: calls.append('transcript_vectors'))

    effects = enrichment_plan.required_enrichment_effects('uid-1', conversation, require_vector_store=False)
    for effect in effects:
        effect.execute()

    assert calls == list(enrichment_plan.REQUIRED_EFFECT_KEYS)


def test_cleanup_removes_both_vector_sets_with_strict_failure_reporting(monkeypatch):
    calls = []
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', object())
    monkeypatch.setattr(
        enrichment_plan.vector_db,
        'delete_finalization_enrichment_vectors',
        lambda uid, conversation_id, generation_id, count: calls.append(
            ('enrichment_vectors', uid, conversation_id, generation_id, count)
        ),
    )

    enrichment_plan.cleanup_required_enrichment(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-1',
        transcript_vector_count=3,
        require_vector_store=True,
    )

    assert calls == [
        ('enrichment_vectors', 'uid-1', 'conversation-1', 'generation-1', 3),
    ]


def test_cleanup_keeps_v1_optional_store_compatibility_but_v2_fails_closed(monkeypatch):
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', None)

    enrichment_plan.cleanup_required_enrichment(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-1',
        transcript_vector_count=0,
        require_vector_store=False,
    )
    with pytest.raises(enrichment_plan.RequiredEnrichmentUnavailable):
        enrichment_plan.cleanup_required_enrichment(
            'uid-1',
            'conversation-1',
            finalization_vector_generation_id='generation-1',
            transcript_vector_count=0,
            require_vector_store=True,
        )


@pytest.mark.parametrize(
    ('stored_count', 'runtime_enabled', 'transcript_called'),
    ((0, True, False), (1, False, True)),
)
def test_persisted_transcript_plan_overrides_runtime_flag(
    monkeypatch,
    stored_count,
    runtime_enabled,
    transcript_called,
):
    calls = []
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', object())
    monkeypatch.setattr(enrichment_plan, 'TRANSCRIPT_CHUNK_INDEXING_ENABLED', runtime_enabled)
    monkeypatch.setattr(enrichment_plan, 'save_transcript_chunk_vectors', lambda *_: calls.append('transcript'))

    effects = enrichment_plan.required_enrichment_effects(
        'uid-1',
        _conversation(),
        transcript_vector_count=stored_count,
    )
    _effect('transcript_vectors', effects).execute()

    assert bool(calls) is transcript_called


def test_persisted_transcript_count_drift_fails_before_provider_mutation(monkeypatch):
    writer = pytest.fail
    monkeypatch.setattr(enrichment_plan.vector_db, 'index', object())
    monkeypatch.setattr(
        enrichment_plan,
        'save_transcript_chunk_vectors',
        lambda *_: writer('transcript provider writer must not run after plan drift'),
    )

    effects = enrichment_plan.required_enrichment_effects(
        'uid-1',
        _conversation(),
        transcript_vector_count=2,
    )

    with pytest.raises(RuntimeError, match='transcript_vector_plan_changed'):
        _effect('transcript_vectors', effects).execute()
