from types import SimpleNamespace

import numpy as np
import pytest

from config import transcription_final_pass as flags
from models.diarization import DiarizationResult, OMI_EMBEDDING_SPACE
from models.speaker_label_provenance import project_source
from utils.conversations.final_pass_assignment import (
    assign_words,
    name_centroids,
    skip_single_speaker,
    select_live_match,
)
from utils.conversations.final_pass_remap import remap_final_record
from utils.stt.diarization_eval import score_turns
from utils.stt.speaker_match import select_speaker_match


def test_triage_requires_one_evidenced_voice_and_coverage():
    assert not skip_single_speaker(None)
    assert not skip_single_speaker(SimpleNamespace(coverage=0.5, speaker_ids={'a': 0}))
    assert not skip_single_speaker(SimpleNamespace(coverage=1, speaker_ids={'a': 0, 'b': 1}))
    assert skip_single_speaker(SimpleNamespace(coverage=1, speaker_ids={'a': 0, 'b': 0}))


def test_assignment_straddling_turns_tie_midpoint_gaps_and_point_words():
    turns = [{'start': 0, 'end': 1, 'speaker': 'a'}, {'start': 1, 'end': 2, 'speaker': 'b'}]
    intervals = [[0.5, 1.1], [0.9, 1.5], [0.5, 1.5], [2, 3], [1, 1]]
    assigned = assign_words([{'timestamp': t, 'text': 'word'} for t in intervals], turns)
    assert [w['speaker'] for w in assigned] == ['a', 'b', 'b', None, 'b']
    with pytest.raises(ValueError, match='exclusive'):
        assign_words([], [{'start': 0, 'end': 2, 'speaker': 'a'}, {'start': 1, 'end': 3, 'speaker': 'b'}])


def test_overlaps_do_not_override_exclusive_turn_assignment():
    result = DiarizationResult(
        turns=[{'start': 0, 'end': 2, 'speaker': 'a'}],
        overlaps=[{'start': 0.5, 'end': 1, 'speakers': ['a', 'b']}],
        embedding_space=OMI_EMBEDDING_SPACE,
        version='test',
        provenance={},
    )
    assert assign_words([{'timestamp': [0.5, 1], 'text': 'word'}], result.model_dump()['turns'])[0]['speaker'] == 'a'


def test_centroid_naming_uses_existing_threshold_margin_evidence_owner_arbitration():
    prints = {'user': np.array([1.0, 0]), 'person': np.array([0.0, 1])}
    centroids = {
        'a': {'embedding': [1, 0], 'evidence_seconds': 10},
        'b': {'embedding': [0, 1], 'evidence_seconds': 10},
        'short': {'embedding': [1, 0], 'evidence_seconds': 0.1},
    }
    matches = name_centroids(centroids, prints)
    assert matches['a'].person_id == 'user'
    assert matches['b'].person_id == 'person'
    assert 'short' not in matches
    assert name_centroids(centroids, prints, owner_reserved=True)['a'].person_id is None
    centroids['other'] = {'embedding': [1, 0.01], 'evidence_seconds': 10}
    assert name_centroids(centroids, prints)['a'].person_id is None
    assert project_source({'is_user': True, 'speaker_match_source': 'final_centroid'}) == 'auto'
    for row in ({'user': 0.64}, {'user': 0.66}, {'user': 0.4, 'person': 0.45}):
        assert select_live_match(row) == select_speaker_match(row)


def segment(id, **values):
    return dict(
        id=id, text='a sufficiently long synthetic sentence', start=0.0, end=4.0, is_user=False, speaker_id=0, **values
    )


@pytest.mark.parametrize('identity', [{'is_user': True}, {'is_user': False, 'person_id': 'synthetic-person'}])
def test_manual_receipts_preserved(identity):
    old, new = [segment('old')], [segment('new')]
    receipt = {'speakers': {'0': {**identity, 'generation': 1, 'source': 'manual'}}}
    patch = remap_final_record(old, new, receipt, {}, clock_offset=0)
    for key, value in identity.items():
        assert patch['transcript_segments'][0][key] == value
    assert patch['manual_speaker_assignments']['segments']['new']['generation'] == 1


def test_translations_and_summary_references_preserved():
    old = [segment('old', translations=[{'lang': 'fr', 'text': 'synthetic translation'}])]
    patch = remap_final_record(old, [segment('new')], {}, {'notes': [{'source_segment_ids': ['old']}]}, clock_offset=0)
    assert patch['transcript_segments'][0]['translations'] == old[0]['translations']
    assert patch['structured']['notes'][0]['source_segment_ids'] == ['new']


def test_edited_is_user_false_preserved_without_receipt():
    old = [segment('old', speaker_label_source='manual')]
    new = [segment('new')]
    new[0]['is_user'] = True
    patch = remap_final_record(old, new, {}, {}, clock_offset=0)
    assert patch['transcript_segments'][0]['is_user'] is False
    assert patch['transcript_segments'][0]['speaker_match_source'] is None


def test_translation_split_fails_closed():
    old = [segment('old', translations=[{'lang': 'fr', 'text': 'synthetic'}])]
    new = [
        dict(id='a', start=0, end=2, text='a sufficiently long'),
        dict(id='b', start=2, end=4, text='synthetic sentence'),
    ]
    with pytest.raises(ValueError, match='translation'):
        remap_final_record(old, new, {}, {}, clock_offset=0)


def test_flags_default_off_and_independent_sync_authority(monkeypatch):
    for key in (
        'TRANSCRIPTION_FINAL_PASS_DIARIZER',
        'TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE',
        'TRANSCRIPTION_FINAL_PASS_PERCENT',
        'TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST',
    ):
        monkeypatch.delenv(key, raising=False)
    assert not flags.enabled_for('synthetic')
    assert not flags.authoritative_for('synthetic')
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_DIARIZER', 'pyannote_shadow')
    assert not flags.enabled_for('synthetic')
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST', 'synthetic')
    assert flags.enabled_for('synthetic')
    assert not flags.authoritative_for('synthetic')


def test_eval_permutation_fragmentation_and_missing_words():
    truth = [
        {'start': 0, 'end': 1, 'speaker': 'a'},
        {'start': 1, 'end': 2, 'speaker': 'a'},
        {'start': 2, 'end': 3, 'speaker': 'b'},
        {'start': 3, 'end': 4, 'speaker': 'unsure'},
    ]
    turns = [
        {'start': 0, 'end': 1, 'speaker': 'x'},
        {'start': 1, 'end': 2, 'speaker': 'y'},
        {'start': 2, 'end': 3, 'speaker': 'z'},
    ]
    result = score_turns(truth, turns)
    assert result['words'] == 3 and result['truth_speakers'] == 2 and result['predicted_speakers'] == 3
    assert result['accuracy_1to1'] == 2 / 3 and result['accuracy_many_to_1'] == 1
    assert score_turns(truth, [])['accuracy_1to1'] == 0


def test_shared_pipeline_selects_backend_stamps_provenance_and_abstains_in_other_space(monkeypatch):
    from utils.conversations import final_pass_pyannote as pipeline

    result = DiarizationResult(
        turns=[{'start': 0, 'end': 3, 'speaker': 'x'}],
        centroids={'x': {'embedding': [1, 0], 'evidence_seconds': 10}},
        embedding_space=OMI_EMBEDDING_SPACE,
        version='synthetic-1',
        provenance={'backend': 'pyannote'},
    )
    backend = SimpleNamespace(diarize=lambda *_a, **_kw: result)
    monkeypatch.setattr(pipeline, 'get_diarizer_backend', lambda: backend)
    words = [
        {'timestamp': [0, 1], 'speaker': 'a', 'text': 'synthetic'},
        {'timestamp': [1, 2], 'speaker': 'b', 'text': 'fixture'},
    ]
    roster = {'user': {'embedding': np.array([1, 0])}}
    segments, outcome = pipeline.run_final_pass(
        b'', words, None, roster, deadline=float('inf'), conversation_id='fixture'
    )
    assert outcome['outcome'] == 'diarized'
    assert segments[0].is_user and segments[0].speaker_label_source == 'auto'
    assert segments[0].speaker_id_scope == 'final:pyannote'
    assert segments[0].speaker_match_source == 'final_centroid:synthetic-1'
    result.embedding_space = 'nemotron-internal-unqualified'
    segments, outcome = pipeline.run_final_pass(
        b'', words, None, roster, deadline=float('inf'), conversation_id='fixture'
    )
    assert not segments[0].is_user
    assert outcome['naming_outcome'] == 'incompatible_space'


def test_single_triage_skips_remote_backend_but_still_names_centroid(monkeypatch):
    from utils.conversations import final_pass_pyannote as pipeline

    monkeypatch.setattr(pipeline, 'get_diarizer_backend', lambda: pytest.fail('remote backend must not run'))
    resolution = SimpleNamespace(coverage=1, speaker_ids={'old': 0})
    old = SimpleNamespace(id='old', start=0, end=6)
    segments, outcome = pipeline.run_final_pass(
        b'',
        [{'timestamp': [0, 6], 'text': 'synthetic', 'speaker': 'a'}],
        resolution,
        {'user': {'embedding': np.array([1, 0])}},
        deadline=float('inf'),
        conversation_id='fixture',
        segments=[old],
        vectors={'old': np.array([1, 0])},
    )
    assert outcome['outcome'] == 'skipped_single'
    assert segments[0].is_user


def test_backend_config_switches_without_code_change(monkeypatch):
    from utils.stt.diarization import get_diarizer_backend, LegacyAHC, HttpDiarizer

    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_BACKEND', 'legacy_ahc')
    assert isinstance(get_diarizer_backend(), LegacyAHC)
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_BACKEND', 'nemotron')
    assert isinstance(get_diarizer_backend(), HttpDiarizer)
    monkeypatch.setenv('TRANSCRIPTION_FINAL_PASS_BACKEND', 'typo')
    with pytest.raises(ValueError):
        get_diarizer_backend()


def test_activity_fallback_keeps_overlap_separate():
    from utils.stt.diarization_turns import exclusive_from_activity, overlap_regions

    activity = [{'start': 0, 'end': 4, 'speaker': 'a'}, {'start': 1, 'end': 2, 'speaker': 'b'}]
    assert exclusive_from_activity(activity) == [{'start': 0, 'end': 4, 'speaker': 'a'}]
    assert overlap_regions(activity) == [{'start': 1, 'end': 2, 'speakers': ['a', 'b']}]


def test_sync_adapter_uses_same_assignment_pipeline_and_raw_word_clock(monkeypatch):
    import io
    import wave
    from models.transcript_segment import TranscriptSegment
    from utils.conversations import final_pass_sync as sync
    from utils.conversations import final_pass_pyannote as pipeline

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\x01\x00' * 160000)
    monkeypatch.setattr(sync, 'speaker_embedding_configured', lambda: False)
    result = DiarizationResult(
        turns=[{'start': 2, 'end': 6, 'speaker': 'x'}],
        centroids={'x': {'embedding': [1, 0], 'evidence_seconds': 10}},
        embedding_space=OMI_EMBEDDING_SPACE,
        version='synthetic',
        provenance={'backend': 'pyannote'},
    )
    monkeypatch.setattr(pipeline, 'get_diarizer_backend', lambda: SimpleNamespace(diarize=lambda *_a, **_kw: result))
    old = TranscriptSegment(text='synthetic', start=0, end=4, is_user=False)
    segments, outcome = sync.run_sync_final_pass(
        'fixture',
        buffer.getvalue(),
        [{'timestamp': [2, 6], 'text': 'synthetic', 'speaker': 'provider'}],
        [old],
        {'user': {'embedding': np.array([1, 0])}},
        scope='sync:fixture',
        owner_reserved=False,
    )
    assert outcome['outcome'] == 'diarized'
    assert segments[0].start == 2 and segments[0].end == 6 and segments[0].is_user
    assert old.start == 0
