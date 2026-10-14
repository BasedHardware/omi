"""Shared ignored-voice marker reconciliation: same rules for every writer.

Covers the two behaviors the review threads flagged: a tag-prompt ``Me``/
person answer must retire an exclusion marker through the same path the live
sheet uses, and a post-commit marker persistence failure must surface in the
shared fallback telemetry instead of only the log.
"""

from types import SimpleNamespace
from unittest.mock import Mock, call

import utils.ignored_voice_markers as markers


def _raw(segments, receipt):
    return {'id': 'c1', 'transcript_segments': segments, 'manual_speaker_assignments': receipt}


def test_positive_answer_retires_markers_through_the_shared_path():
    db = Mock()
    raw = _raw(
        [{'id': 's1', 'speaker_id': 4, 'is_user': False, 'person_id': 'p1'}],
        {'generation': 5, 'speakers': {'4': {'generation': 5, 'person_id': 'p1'}}},
    )
    markers.retire_exclusion_markers('u', 'c1', raw, ['s1'], speaker_id=None, voice_profiles=db)
    db.clear_ignored_voices.assert_called_once_with('u', 'c1', [4], assignment_generation=5)


def test_range_only_positive_keeps_the_marker_restorable():
    db = Mock()
    raw = _raw(
        [{'id': 's1', 'speaker_id': 4}],
        {
            'generation': 6,
            'speakers': {'4': {'generation': 2, 'rejection': {'kind': 'not_a_person'}}},
            'segments': {'s1': {'generation': 6, 'person_id': 'p1', 'segment_only': True, 'speaker_id': 4}},
        },
    )
    markers.retire_exclusion_markers('u', 'c1', raw, ['s1'], speaker_id=4, voice_profiles=db)
    db.clear_ignored_voices.assert_not_called()


def test_no_persisted_receipt_means_nothing_to_retire():
    db = Mock()
    raw = {'id': 'c1', 'transcript_segments': [{'id': 's1', 'speaker_id': 4}]}
    markers.retire_exclusion_markers('u', 'c1', raw, ['s1'], speaker_id=4, voice_profiles=db)
    db.clear_ignored_voices.assert_not_called()


def test_exclusion_records_markers_fenced_by_generation():
    db = Mock()
    raw = _raw([{'id': 's1', 'speaker_id': 4}], {'generation': 7})
    markers.record_exclusion_markers('u', 'c1', raw, ['s1'], speaker_id=None, voice_profiles=db)
    assert db.record_ignored_voice.call_count == 1
    args, kwargs = db.record_ignored_voice.call_args
    assert args[:3] == ('u', 'c1', 4)
    assert kwargs['assignment_generation'] == 7


def test_marker_persistence_failure_emits_shared_fallback_telemetry(monkeypatch):
    fallback = Mock()
    monkeypatch.setattr(markers, 'record_fallback', fallback)

    def boom(*args, **kwargs):
        raise RuntimeError('state store unavailable')

    raw = _raw([{'id': 's1', 'speaker_id': 4}], {'generation': 3})
    # Record path: fail-open but visible in the fallback metrics.
    markers.record_exclusion_markers(
        'u', 'c1', raw, ['s1'], speaker_id=None, voice_profiles=SimpleNamespace(record_ignored_voice=boom)
    )
    assert fallback.call_args_list == [
        call(
            component='speaker_assignments',
            from_mode='ignored_voice_marker',
            to_mode='receipt_only',
            reason='firestore_error',
            outcome='degraded',
            log=markers.logger,
        )
    ]

    fallback.reset_mock()
    positive = _raw(
        [{'id': 's1', 'speaker_id': 4, 'person_id': 'p1'}],
        {'generation': 4, 'speakers': {'4': {'generation': 4, 'person_id': 'p1'}}},
    )
    markers.retire_exclusion_markers(
        'u', 'c1', positive, ['s1'], speaker_id=None, voice_profiles=SimpleNamespace(clear_ignored_voices=boom)
    )
    assert fallback.call_count == 1
    assert fallback.call_args.kwargs['component'] == 'speaker_assignments'
    assert fallback.call_args.kwargs['outcome'] == 'degraded'
