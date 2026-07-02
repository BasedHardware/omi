from types import SimpleNamespace

from utils.conversations.analytics import build_conversation_analytics


def _seg(text, start, end, is_user=False, person_id=None, speaker_id=None, speaker=None):
    return SimpleNamespace(
        text=text, start=start, end=end, is_user=is_user, person_id=person_id, speaker_id=speaker_id, speaker=speaker
    )


def _conv(segments, id='c1'):
    return SimpleNamespace(id=id, transcript_segments=segments)


def test_per_speaker_talk_time_words_and_wpm():
    # 10 words over 30 seconds -> 20 words per minute.
    conv = _conv([_seg('one two three four five six seven eight nine ten', 0, 30, person_id='a')])
    r = build_conversation_analytics(conv, {'a': 'Alice'})
    assert r.conversation_id == 'c1'
    assert r.speaker_count == 1
    s = r.speakers[0]
    assert s.speaker == 'Alice' and s.person_id == 'a'
    assert s.talk_seconds == 30.0
    assert s.word_count == 10
    assert s.words_per_minute == 20.0
    assert s.talk_share == 1.0


def test_user_segments_labeled_you():
    conv = _conv([_seg('hi there', 0, 6, is_user=True)])
    r = build_conversation_analytics(conv, {})
    assert r.speakers[0].speaker == 'You'
    assert r.speakers[0].is_user is True


def test_unidentified_speaker_uses_diarization_label():
    conv = _conv([_seg('hello', 0, 6, speaker_id=2)])
    r = build_conversation_analytics(conv, {})
    assert r.speakers[0].speaker == 'Speaker 2'
    assert r.speakers[0].person_id is None


def test_unknown_person_name_falls_back():
    conv = _conv([_seg('hi', 0, 6, person_id='ghost')])
    r = build_conversation_analytics(conv, {})
    assert r.speakers[0].speaker == 'Unknown'


def test_ordered_by_talk_time_with_totals_and_shares():
    conv = _conv(
        [
            _seg('a b', 0, 5, person_id='q'),  # 5s, 2 words
            _seg('c d e f', 0, 20, person_id='c'),  # 20s, 4 words
        ]
    )
    r = build_conversation_analytics(conv, {'q': 'Quiet', 'c': 'Chatty'})
    assert [s.speaker for s in r.speakers] == ['Chatty', 'Quiet']
    assert r.total_seconds == 25.0
    assert r.total_words == 6
    assert r.speaker_count == 2
    assert abs(sum(s.talk_share for s in r.speakers) - 1.0) < 0.01


def test_same_speaker_across_segments_accumulates():
    conv = _conv(
        [
            _seg('one two', 0, 6, person_id='a'),
            _seg('three four five', 10, 16, person_id='a'),
        ]
    )
    r = build_conversation_analytics(conv, {'a': 'Alice'})
    assert r.speaker_count == 1
    assert r.speakers[0].talk_seconds == 12.0
    assert r.speakers[0].word_count == 5


def test_zero_duration_segment_does_not_divide_by_zero():
    conv = _conv([_seg('hi', 5, 5, person_id='a')])
    r = build_conversation_analytics(conv, {'a': 'Alice'})
    assert r.speakers[0].talk_seconds == 0.0
    assert r.speakers[0].words_per_minute == 0.0
    assert r.words_per_minute == 0.0


def test_empty_conversation():
    r = build_conversation_analytics(_conv([]), {})
    assert r.speaker_count == 0
    assert r.total_seconds == 0.0
    assert r.total_words == 0
    assert r.speakers == []
