"""Pass-local resolver summaries observe the real refusal paths without changing policy."""

import copy

import pytest

from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _conversation,
    _install_audio,
    _span_flags,
    _capture_shifted_conversation,
)
from utils.conversations import speaker_resolution as stage
from utils.observability import owner_recognition_diagnostics as diagnostics
from utils.observability.owner_identity_retry import identity_pass


def first(conversation):
    return conversation.owner_recognition_diagnostics['first_resolver']


@pytest.mark.parametrize('gate', ['private_cloud_disabled', 'endpoint_unconfigured'])
def test_no_audio_gates_are_distinct_and_existing_outcome_is_unchanged(env, monkeypatch, caplog, gate):
    _, diarizer = env
    conversation = _conversation([0], pcs=gate != 'private_cloud_disabled', scopes=['conn:0'])
    monkeypatch.setattr(stage, 'speaker_embedding_configured', lambda: False)
    caplog.set_level('INFO')
    with identity_pass('first'):
        assert stage.resolve_speakers_for_processing('diagnostic-user', conversation)
    assert first(conversation)['reason'] == gate
    assert first(conversation)['status'] == 'capture' and diarizer.calls == 0
    assert 'uid=diagnostic-user' in caplog.text and 'conversation=c1' in caplog.text
    assert caplog.text.count('kind=resolver_exit') == 1
    assert not conversation.transcript_segments[0].is_user


@pytest.mark.parametrize(
    'gate', ['no_proven_window', 'placement_deadline', 'global_manifest_ambiguity', 'decoded_coverage_hole']
)
def test_unavailable_resolver_refusal_is_attributable_with_zero_comparisons(env, monkeypatch, gate):
    _, diarizer = env
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0, 1] * 4, offset=180.0)
    conversation = _capture_shifted_conversation([0, 1] * 4, manifest=gate != 'no_proven_window')
    if gate == 'placement_deadline':
        monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_BUDGET_SECONDS', '0')
    if gate == 'global_manifest_ambiguity':
        duplicate = conversation.audio_files[0].model_copy(deep=True)
        duplicate.id = 'duplicate'
        conversation.audio_files.append(duplicate)
    if gate == 'decoded_coverage_hole':

        def refuse(*args, **kwargs):
            stage.resolver_reason('decoded_coverage_hole')
            return None

        monkeypatch.setattr(stage, '_verified_read_session', refuse)
    stage.resolve_speakers_for_processing('u', conversation)
    assert first(conversation)['reason'] == ('manifest_unvalidated' if gate == 'no_proven_window' else gate)
    assert conversation.speaker_resolution.status == 'unavailable' and diarizer.calls == 0


@pytest.mark.parametrize('case', ['all_short', 'partial', 'embedding_failed', 'no_owner_print'])
def test_duration_failure_coverage_and_owner_roster_remain_separate(env, monkeypatch, case):
    _, diarizer = env

    plan = [0, 0, 0]
    _install_audio(monkeypatch, plan)
    conversation = _conversation(plan, seconds=0.5 if case == 'all_short' else 4.0)
    if case == 'embedding_failed':
        diarizer.fail = True
    kwargs = {'max_embedding_attempts': 1} if case == 'partial' else {}
    stage.resolve_speakers_for_processing('u', conversation, **kwargs)
    row = first(conversation)
    assert not any(s.is_user for s in conversation.transcript_segments)
    if case == 'all_short':
        assert row['reason'] == 'all_short' and row['attempted'] == 0
    elif case == 'partial':
        assert row['reason'] == 'partial' and row['attempted'] == 1 and row['coverage'] < 0.9
        assert conversation.speaker_resolution.status == 'unavailable'
    elif case == 'embedding_failed':
        assert row['reason'] == 'embedding_failed' and row['failed'] == row['attempted'] == 3
    else:
        assert row['owner_profile_available'] == 0 and row['reason'] == 'resolved'
        assert conversation.speaker_resolution.status == 'resolved'


def test_first_diagnosis_survives_late_resolution_and_reprocessing(env, monkeypatch, caplog):
    conversation = _conversation([0], pcs=False)
    stage.resolve_speakers_for_processing('u', conversation)
    preserved = copy.deepcopy(first(conversation))
    caplog.set_level('INFO')
    with identity_pass('late'):
        stage.resolve_speakers_for_processing('u', conversation)
    assert first(conversation) == preserved
    assert "'pass': 'late'" in caplog.text
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    stage.resolve_speakers_for_processing('u', conversation)
    assert first(conversation) == preserved


def test_diagnostic_codec_or_log_failure_cannot_change_resolver_result(env, monkeypatch):
    conversation = _conversation([0], pcs=False)
    monkeypatch.setattr(
        diagnostics.contract, 'merge', lambda *args: (_ for _ in ()).throw(ValueError('metadata codec'))
    )
    monkeypatch.setattr(diagnostics.logger, 'info', lambda *args: (_ for _ in ()).throw(ValueError('sink')))
    assert stage.resolve_speakers_for_processing('u', conversation)
    assert conversation.speaker_resolution.status == 'capture'


def test_empty_and_disabled_resolver_exits_are_recorded_without_new_matching(env, monkeypatch):
    conversation = _conversation([])
    assert not stage.resolve_speakers_for_processing('u', conversation)
    assert first(conversation)['reason'] == 'empty_transcript'
    other = _conversation([0])
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    stage.resolve_speakers_for_processing('u', other)
    assert first(other)['reason'] == 'disabled'


def test_preexisting_malformed_metadata_cannot_block_resolver(env, monkeypatch):
    conversation = _conversation([0], pcs=False)
    monkeypatch.setattr(diagnostics.contract, 'normalize', lambda *args: (_ for _ in ()).throw(ValueError('codec')))
    assert stage.resolve_speakers_for_processing('u', conversation)
    assert conversation.speaker_resolution.status == 'capture'
