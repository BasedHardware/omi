"""Synthetic unit evidence continuity: no packet data, credentials or inference."""

from copy import deepcopy
from dataclasses import replace
import time

import numpy as np
import pytest

from tests.unit.test_batch_final_pass import lane, UID
from utils.conversations import speaker_resolution as stage, final_pass_batch as batch
from utils.conversations.speaker_resolution_inputs import transcript_membership
from database.batch_final_pass import ReferenceUnavailable
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from models.conversation import Conversation

REAL_RESOLVE = stage._resolve


@pytest.fixture
def original(lane, monkeypatch):
    monkeypatch.setenv('BATCH_ORIGINAL_IDENTITY_EVIDENCE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'false')
    monkeypatch.setattr(stage, '_resolve', REAL_RESOLVE)
    monkeypatch.setattr(stage, 'speaker_embedding_configured', lambda: True)
    monkeypatch.setattr(stage, '_embed_missing', lambda *a, **kw: pytest.fail('additive sentence embedding'))
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {'user': np.eye(1, 256)[0]})
    cache = {}
    calls = []
    monkeypatch.setattr(stage, 'download_speaker_embedding_cache', lambda *a: cache.get('body'))
    monkeypatch.setattr(stage, 'upload_speaker_embedding_cache', lambda *a: cache.update(body=a[-1]))

    def embed(clip, *a, **kwargs):
        calls.append(clip)
        return np.eye(1, 256)[0]

    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', embed)
    lane.conversation.audio_files = []
    return lane, cache, calls


def resolve(lane):
    assert stage.resolve_speakers_for_processing(UID, lane.conversation)
    return lane.conversation


def test_original_units_ignore_rebased_playback_and_replace_sentence_pass(original):
    lane, cache, calls = original
    before = [(s.id, s.text, s.start, s.end) for s in lane.conversation.transcript_segments]
    conversation = resolve(lane)
    assert all(s.is_user for s in conversation.transcript_segments)
    assert conversation.speaker_resolution.status == 'resolved'
    assert len(calls) == 2 and not lane.gpu  # One call per unit label; no final-pass/STT call.
    assert len({s.speaker_id for s in conversation.transcript_segments}) == 1
    assert before == [(s.id, s.text, s.start, s.end) for s in conversation.transcript_segments]
    assert sum(s.speaker_word_seconds for s in conversation.transcript_segments) == pytest.approx(10.8)
    lane.conversation = Conversation(**conversation.model_dump())
    resolve(lane)
    assert len(calls) == 2  # True pinned centroid cache hits, no extra extraction.


def test_late_unit_append_after_first_resolve_requires_current_membership(original):
    lane, cache, calls = original
    later = deepcopy(lane.conversation.transcript_segments[1:])
    lane.conversation.transcript_segments = lane.conversation.transcript_segments[:1]
    resolve(lane)
    first = deepcopy(lane.conversation.owner_recognition_diagnostics['first_resolver'])
    old_key = lane.conversation.speaker_resolution.input_membership_sha256
    lane.conversation.transcript_segments.extend(later)
    raw = lane.conversation.model_dump()
    raw.update(status='completed', updated_at='synthetic-revision')
    assert transcript_membership(raw['transcript_segments']) != old_key
    assert stage.completed_identity_retry_skip_reason(raw) is None
    resolve(lane)
    assert lane.conversation.speaker_resolution.input_membership_sha256 == transcript_membership(
        lane.conversation.transcript_segments
    )
    assert len(calls) == 2 and all(s.is_user for s in lane.conversation.transcript_segments)
    assert lane.conversation.owner_recognition_diagnostics['first_resolver'] == first
    assert lane.conversation.owner_recognition_diagnostics['current_resolver']['segments'] == 2


def test_changed_audio_generation_cannot_reuse_old_cached_centroid(original, monkeypatch):
    lane, cache, calls = original
    resolve(lane)
    lane.items['unit-a'] = replace(lane.items['unit-a'], audio_uri='gs://fake/unit-a#2')
    resolve(lane)
    assert len(calls) == 3


def test_generation_changed_during_embedding_vetoes_identity_and_cache(original, monkeypatch):
    lane, cache, calls = original

    def change(clip, *a, **kw):
        calls.append(clip)
        lane.items['unit-a'] = replace(lane.items['unit-a'], privacy_generation=1)
        return np.eye(1, 256)[0]

    monkeypatch.setattr(stage, 'extract_embedding_from_bytes', change)
    conversation = resolve(lane)
    assert conversation.speaker_resolution.status == 'unavailable'
    assert not any(s.is_user for s in conversation.transcript_segments)
    assert not cache


@pytest.mark.parametrize('reason', ['skipped_shared_unit', 'skipped_merged', 'skipped_expired', 'erasure'])
def test_reference_refusals_never_fall_back_to_playback(original, monkeypatch, reason):
    lane, cache, calls = original

    def refuse(*a, **kw):
        raise (
            ReferenceUnavailable('failed_incomplete_coverage', reason)
            if reason == 'erasure'
            else ReferenceUnavailable(reason)
        )

    monkeypatch.setattr(batch, 'load_reference', refuse)
    conversation = resolve(lane)
    assert not calls and not cache and not any(s.is_user for s in conversation.transcript_segments)
    assert conversation.speaker_resolution.status == 'unavailable'


def test_privacy_fence_blocks_all_audio_reads(original, monkeypatch):
    lane, cache, calls = original

    def refuse(*a, **kw):
        raise BatchPrivacyBlocked('privacy_generation_changed')

    monkeypatch.setattr(batch, 'load_reference', refuse)
    monkeypatch.setattr(lane.artifacts, 'fetch_audio', lambda *a, **kw: pytest.fail('privacy bypass'))
    resolve(lane)
    assert not calls and not cache


def test_projection_text_mismatch_stays_unknown(original):
    lane, cache, calls = original
    lane.conversation.transcript_segments[0].text = 'Synthetic corrected sentence.'
    resolve(lane)
    assert not lane.conversation.transcript_segments[0].is_user
    assert lane.conversation.transcript_segments[1].is_user
    assert len(calls) == 1


def test_identity_thresholds_and_margin_are_unchanged(original, monkeypatch):
    lane, cache, calls = original
    # Identical enrolled owner/person vectors must still abstain on the 0.10 margin.
    monkeypatch.setattr(
        stage,
        'load_voiceprints_for_resolution',
        lambda *a, **kw: {'user': np.eye(1, 256)[0], 'person': np.eye(1, 256)[0]},
    )
    resolve(lane)
    assert not any(s.is_user or s.person_id for s in lane.conversation.transcript_segments)
    from utils.speakers.policy import FINALIZE
    from utils.stt.speaker_match import SPEAKER_MATCH_MARGIN, SPEAKER_MATCH_MIN_EVIDENCE_SECONDS

    assert FINALIZE.distance == 0.50
    assert SPEAKER_MATCH_MARGIN == 0.10 and SPEAKER_MATCH_MIN_EVIDENCE_SECONDS == 5


def test_overlapping_units_do_not_multiply_five_second_identity_evidence(original, monkeypatch):
    lane, cache, calls = original
    # Both units cover the same <5s acoustic interval, despite distinct IDs.
    lane.items['unit-b'] = replace(lane.items['unit-b'], capture_at=lane.items['unit-a'].capture_at)
    lane.payload['words'] = [dict(word='Synthetic.', timestamp=[0.2, 4.2])]
    from utils.batch_pipeline.projection_segments import projection_segments

    lane.conversation.transcript_segments = [
        s for item in lane.items.values() for s in projection_segments(item, lane.binding, lane.payload)
    ]
    resolve(lane)
    assert len(calls) == 2
    assert not any(s.is_user for s in lane.conversation.transcript_segments)


def test_distance_boundary_remains_strict(original, monkeypatch):
    lane, cache, calls = original
    owner = np.zeros(256)
    owner[:2] = [0.4999, np.sqrt(1 - 0.4999**2)]  # Just beyond 0.50, clear of float32 rounding.
    monkeypatch.setattr(stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {'user': owner})
    resolve(lane)
    assert not any(s.is_user for s in lane.conversation.transcript_segments)
    from utils.speakers.policy import FINALIZE

    assert not FINALIZE.accepts(0.50)


def test_embedding_attempt_cap_abstains_without_extra_sentence_or_final_pass(original):
    lane, cache, calls = original
    assert stage.resolve_speakers_for_processing(UID, lane.conversation, max_embedding_attempts=1)
    assert len(calls) == 1 and not lane.gpu
    assert lane.conversation.speaker_resolution.status == 'unavailable'


def test_manual_excerpt_stays_authoritative(original):
    lane, cache, calls = original
    sid = lane.conversation.transcript_segments[0].id
    lane.receipts.update(segments={sid: dict(is_user=False, person_id='synthetic-manual')})
    resolve(lane)
    assert lane.conversation.transcript_segments[0].person_id == 'synthetic-manual'
    assert lane.conversation.transcript_segments[0].speaker_label_source == 'manual'


def test_word_time_metadata_is_storage_only(original):
    lane, cache, calls = original
    conversation = resolve(lane)
    assert 'speaker_word_seconds' in conversation.model_dump()['transcript_segments'][0]
    assert 'speaker_word_seconds' not in conversation.model_dump(mode='json')['transcript_segments'][0]
    assert conversation.model_dump()['speaker_resolution']['input_membership_sha256']
    assert 'input_membership_sha256' not in conversation.model_dump(mode='json')['speaker_resolution']
    assert 'input_membership_sha256' not in conversation.speaker_resolution.model_json_schema()['properties']


def test_mixed_live_and_wal_unit_provenance_uses_each_original_pair(original):
    lane, cache, calls = original
    from utils.batch_pipeline.projection_segments import projection_segments

    for unit, store in (('unit-a', 'batch'), ('unit-b', 'sync')):
        lane.items[unit] = replace(lane.items[unit], timing_store=store)
    lane.conversation.transcript_segments = [
        s for item in lane.items.values() for s in projection_segments(item, lane.binding, lane.payload)
    ]
    for i, segment in enumerate(lane.conversation.transcript_segments):
        segment.start += 200 + i * 200
        segment.end += 200 + i * 200
    resolve(lane)
    assert len(calls) == 2 and all(s.is_user for s in lane.conversation.transcript_segments)
    assert {s.provider_speaker['timing_store'] for s in lane.conversation.transcript_segments} == {'batch', 'sync'}


def test_sync_off_source_binding_cannot_become_durable_sync_on_evidence(original, monkeypatch):
    lane, cache, calls = original
    reference = batch.load_reference

    def sync_off_reference(*args, **kwargs):
        item, uri, binding, policy = reference(*args, **kwargs)
        return item, uri, replace(binding, private_cloud_sync_enabled=False), policy

    monkeypatch.setattr(batch, 'load_reference', sync_off_reference)
    resolve(lane)
    assert not calls and not cache
    assert not any(s.is_user for s in lane.conversation.transcript_segments)


def test_terminal_final_pass_snapshot_cannot_certify_late_membership(original):
    lane, cache, calls = original
    later = deepcopy(lane.conversation.transcript_segments[1:])
    lane.conversation.transcript_segments = lane.conversation.transcript_segments[:1]
    resolve(lane)
    assert lane.conversation.speaker_resolution.status == 'resolved'
    lane.conversation.transcript_segments.extend(later)
    assert stage.resolve_speakers_for_processing(
        UID, lane.conversation, skip_automatic=True, final_pass_runner=lambda *a, **kw: None
    )
    assert len(calls) == 1
    assert lane.conversation.speaker_resolution.status == 'unavailable'
    assert lane.conversation.speaker_resolution.input_membership_sha256 == transcript_membership(
        lane.conversation.transcript_segments
    )


def test_stale_membership_resets_only_typed_speaker_result_when_inference_is_skipped(original):
    lane, cache, calls = original
    later = deepcopy(lane.conversation.transcript_segments[1:])
    lane.conversation.transcript_segments = lane.conversation.transcript_segments[:1]
    resolve(lane)
    conversation = lane.conversation
    conversation.speaker_resolution.version = 7
    lifecycle_status = conversation.status
    conversation.transcript_segments.extend(later)
    assert stage.resolve_speakers_for_processing(UID, conversation, skip_automatic=True)
    assert conversation.status == lifecycle_status
    assert conversation.speaker_resolution.status == 'unavailable'
    assert conversation.speaker_resolution.version == 7
    assert conversation.speaker_resolution.participant_speaker_ids == []
    assert conversation.speaker_resolution.input_membership_sha256 == transcript_membership(
        conversation.transcript_segments
    )
    assert len(calls) == 1
