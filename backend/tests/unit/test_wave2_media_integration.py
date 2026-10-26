"""Applied V2 consumer seams: real processing, durable replay, recap and restore."""

from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import MagicMock, AsyncMock

import pytest

from tests.unit.test_process_conversation_free_tier_branch import (
    pc,
    _existing_desktop,
    _spy_managed_effects,
    _capture_all_persists,
    _load_finalizer,
    _inline_run_blocking,
)
from models.speaker_evidence import SpeakerEvidence, VoiceCluster


@pytest.mark.parametrize('kind', ['media', 'noise'])
@pytest.mark.parametrize('post_persist_failure', [False, True])
def test_classification_persists_minimum_and_restore_clears_marker(monkeypatch, pc, kind, post_persist_failure):
    from utils.conversations import relevance_media as media

    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda *_: False)
    actual_structured = pc._get_structured
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(pc, 'should_defer_desktop_processing', lambda _: False)
    pc.get_conversation_notes.reset_mock()
    monkeypatch.setattr(pc, '_get_structured', actual_structured)
    monkeypatch.setattr(pc, 'is_release_probe_uid', lambda _: False)
    conversation = _existing_desktop('media-fixture')
    conversation.transcript_segments[0].is_user = False
    conversation.transcript_segments[0].text = ' '.join(f'w{i}' for i in range(3))
    ev = SpeakerEvidence(
        status='resolved',
        policy_version='synthetic',
        clusters=[VoiceCluster(id='v0', segment_ids=[conversation.transcript_segments[0].id], speech_seconds=1)],
    )
    monkeypatch.setattr(media, '_speaker_evidence', lambda *_: ev)
    monkeypatch.setattr(media, '_boundaries', lambda *_: [])
    monkeypatch.setattr(media, '_record_boundaries', lambda *_: None)
    start = conversation.started_at
    monkeypatch.setattr(
        media,
        '_screen_rows',
        lambda *_: (
            [
                dict(timestamp=start + timedelta(seconds=n), appName='Chrome', windowTitle='Synthetic - YouTube')
                for n in range(0, 300, 30)
            ]
            if kind == 'media'
            else []
        ),
    )
    payloads = _capture_all_persists(monkeypatch, pc)
    dispositions, bundles = [], []
    pc.process_conversation(
        'synthetic',
        'en',
        conversation,
        trigger=pc.ProcessingTrigger.CAPTURE_END,
        defer_derived_effects=True,
        derived_effects_disposition_observer=dispositions.append,
        derived_effects_observer=bundles.append,
    )
    assert conversation.content_kind == kind
    assert conversation.structured.title_provenance == 'server_minimum'
    assert payloads[-1][pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] is True
    assert payloads[-1].get('sync_relevance_user_kept') is not True
    assert dispositions[-1] is pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
    assert bundles == []
    pc.get_conversation_notes.assert_not_called()
    spies['extract_memories'].assert_not_called()

    # A restore is an explicit keep choice. Reprocessing must clear both the
    # exclusion and the durable terminal marker before derived fanout resumes.
    from utils.conversations import llm_input_dedupe

    monkeypatch.setattr(pc, 'quiet_minimum', lambda *a, **k: None)
    monkeypatch.setattr(pc, 'rich_notes_inputs', lambda *a, **k: (None, None, False, [], 0))
    monkeypatch.setattr(pc, 'conversation_transcripts_for_llm', lambda *a, **k: ('w0 w1 w2', 'w0 w1 w2', {}))
    monkeypatch.setattr(pc, 'has_structural_wake_word_marker', lambda *_: False)
    monkeypatch.setattr(pc, '_fetch_dedup_candidates_for_query', lambda *a: [])
    monkeypatch.setattr(pc, 'notes_agent_inputs', lambda *a: {})
    monkeypatch.setattr(llm_input_dedupe, 'notes', lambda *a, **k: pc.Structured(title='Restored', overview='w0 w1 w2'))
    conversation.sync_relevance = 'review'
    if post_persist_failure:
        monkeypatch.setattr(pc, 'record_final', MagicMock(side_effect=RuntimeError('controlled post-persist failure')))
    outcome = (
        pytest.raises(RuntimeError, match='controlled post-persist failure') if post_persist_failure else nullcontext()
    )
    with outcome:
        pc.process_conversation(
            'synthetic',
            'en',
            conversation,
            trigger=pc.ProcessingTrigger.USER_REPROCESS,
            user_kept=True,
            defer_derived_effects=True,
            derived_effects_observer=bundles.append,
        )
    assert conversation.content_kind == 'conversation'
    assert payloads[-1][pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] is None
    # A failure after the canonical write must not expose a row whose explicit
    # keep choice can be lost on retry or relevance reassessment.
    assert payloads[-1]['sync_relevance_user_kept'] is True
    assert payloads[-1]['sync_relevance'] == 'keep'
    assert conversation.sync_relevance == 'keep'
    assert bool(bundles) is not post_persist_failure


@pytest.mark.anyio
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_completed_media_replay_does_not_run_derived_effects(monkeypatch, pc, anyio_backend):
    finalizer = _load_finalizer()
    conversation = _existing_desktop('media-fixture')
    conversation.content_kind = 'media'

    async def load(*_):
        return None, {pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD: True}, conversation

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', load)
    monkeypatch.setattr(finalizer, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalizer, 'warm_rollout_cohorts', AsyncMock())
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda _: None)
    monkeypatch.setattr(finalizer, 'finalization_pending', lambda *_: False)
    monkeypatch.setattr(finalizer, 'is_donor', lambda _: False)
    monkeypatch.setattr(
        finalizer.lifecycle_service, 'claim_finalization_fanout', lambda *_: {'status': 'claimed', 'fanout_key': 'key'}
    )
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', MagicMock(return_value=True))
    monkeypatch.setattr(finalizer, '_maybe_start_shadow', lambda *_: None)
    monkeypatch.setattr(finalizer, 'schedule_person_voice_learning_retry', lambda *_: None)
    monkeypatch.setattr(finalizer, 'smart_merge_step', AsyncMock(return_value=False))
    for name in ['process_conversation', 'extract_memories']:
        monkeypatch.setattr(finalizer, name, MagicMock(side_effect=AssertionError('media effects escaped')))
    for name in ['trigger_external_integrations']:
        monkeypatch.setattr(finalizer, name, AsyncMock(side_effect=AssertionError('media effects escaped')))
    monkeypatch.setattr(finalizer, 'record_finalized_meeting_receipt', MagicMock())
    monkeypatch.setattr(finalizer, 'link_duplicate_captures', MagicMock())
    monkeypatch.setattr(finalizer, '_save_summary_vector_fail_soft', MagicMock())
    monkeypatch.setattr(finalizer, '_episode_after_finalization', AsyncMock())
    monkeypatch.setattr(
        finalizer,
        'resolve_frame_request_authority',
        AsyncMock(return_value=type('Disabled', (), dict(enabled=False, account_generation=None))()),
    )
    result = await finalizer.finalize_persisted_conversation(
        'synthetic', 'media-fixture', finalization_job_id='fixture-job', dispatch_generation=1, lease_epoch=2
    )
    assert result.value == 'completed'


@pytest.mark.parametrize('kind', ['media', 'noise'])
def test_memory_and_action_item_public_boundaries_skip_excluded(monkeypatch, pc, kind):
    from types import SimpleNamespace

    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    monkeypatch.setattr(pc, '_extract_memories', MagicMock(side_effect=AssertionError('memory formation escaped')))
    conversation = SimpleNamespace(content_kind=kind, structured=None)
    assert pc.extract_memories('synthetic', conversation) is None
    assert pc._save_action_items('synthetic', conversation) is None
    pc._extract_memories.assert_not_called()
