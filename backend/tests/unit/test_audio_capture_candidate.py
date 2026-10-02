"""The capture-clock candidate window: used when every contributor recorded where the receiver heard it."""

from utils.conversations.audio_placement import candidate_window, capture_window, locate, provisional_window

ORIGIN = 1_700_000_000.0


def _conversation(*segments):
    return {'id': 'c', 'started_at': ORIGIN, 'transcript_segments': list(segments)}


def _segment(sid, start, end, cap_start=None, cap_end=None, **extra):
    segment = {'id': sid, 'start': start, 'end': end, 'speaker_id': 1, **extra}
    if cap_start is not None:
        segment.update(audio_capture_start=cap_start, audio_capture_end=cap_end)
    return segment


def test_capture_window_follows_the_receiver_clock_not_the_legacy_origin():
    # After a reconnect the provider-relative text is 1,800 s behind where the audio was captured.
    drift = 1800.0
    segment = _segment('a', 10.0, 18.0, ORIGIN + drift + 10.0, ORIGIN + drift + 18.0)
    conversation = _conversation(segment)
    assert capture_window(conversation, 12.0, 16.0) == (ORIGIN + drift + 12.0, ORIGIN + drift + 16.0)
    assert candidate_window(conversation, 12.0, 16.0) == (ORIGIN + drift + 12.0, ORIGIN + drift + 16.0)
    assert provisional_window(conversation, 12.0, 16.0) == (ORIGIN + 12.0, ORIGIN + 16.0)


def test_candidate_falls_back_to_the_legacy_origin_without_capture_fields():
    conversation = _conversation(_segment('a', 10.0, 18.0))
    assert capture_window(conversation, 10.0, 18.0) is None
    assert candidate_window(conversation, 10.0, 18.0) == (ORIGIN + 10.0, ORIGIN + 18.0)


def test_contributors_must_all_carry_a_window_and_agree_on_one_offset():
    known = _segment('a', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 114.0)
    missing = _segment('b', 14.0, 18.0)
    other_epoch = _segment('c', 14.0, 18.0, ORIGIN + 514.0, ORIGIN + 518.0)
    agreeing = _segment('d', 14.0, 18.0, ORIGIN + 114.2, ORIGIN + 118.2)
    assert capture_window(_conversation(known, missing), 10.0, 18.0) is None
    assert capture_window(_conversation(known, other_epoch), 10.0, 18.0) is None
    window = capture_window(_conversation(known, agreeing), 10.0, 18.0)
    assert window is not None and abs(window[0] - (ORIGIN + 110.0)) <= 0.25 and abs(window[1] - window[0] - 8.0) < 1e-6


def test_a_capture_window_of_the_wrong_length_or_an_unplaced_contributor_is_refused():
    stretched = _segment('a', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 130.0)
    unplaced = _segment('b', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 114.0, audio_alignment='unplaced')
    assert capture_window(_conversation(stretched), 10.0, 14.0) is None
    assert capture_window(_conversation(unplaced), 10.0, 14.0) is None


def test_explicit_contributors_override_overlap_lookup():
    inside = _segment('a', 10.0, 14.0, ORIGIN + 110.0, ORIGIN + 114.0)
    bystander = _segment('b', 11.0, 13.0)
    conversation = _conversation(inside, bystander)
    assert capture_window(conversation, 10.0, 14.0) is None
    assert capture_window(conversation, 10.0, 14.0, segments=[inside]) == (ORIGIN + 110.0, ORIGIN + 114.0)


def test_capture_fields_never_make_a_window_trusted():
    # The capture clock and the stored-chunk clock can disagree; only verified readers may use it.
    segment = _segment('a', 10.0, 18.0, ORIGIN + 110.0, ORIGIN + 118.0)
    placement = locate(_conversation(segment), 10.0, 18.0)
    assert placement.window is None and placement.reason == 'untrusted_clock'
