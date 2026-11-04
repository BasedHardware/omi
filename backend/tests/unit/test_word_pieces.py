from utils.conversations.word_pieces import drop_replayed_words, drop_repeated_word_runs, join_word_pieces
from utils.manual_speaker_assignments import merge_live_segments


def _word(id_, text, start, end=None, **extra):
    return {
        'id': id_,
        'text': text,
        'start': start,
        'end': start + 0.2 if end is None else end,
        'speaker': 'SPEAKER_00',
        'speaker_id': 1,
        'is_user': False,
        'stt_provider': 'soniox',
        'speaker_id_scope': 'sock:1',
        'speech_profile_processed': True,
        **extra,
    }


def _texts(segments):
    return [segment['text'] for segment in segments]


def test_words_join_into_one_line_across_another_providers_sentence():
    parakeet = _word('p', 'a whole sentence from the other provider', 0.3, 5.0, stt_provider='parakeet')
    joined = join_word_pieces([_word('a', 'some', 0.0), parakeet, _word('b', 'orange', 0.5), _word('c', 'spot.', 1.0)])
    assert _texts(joined) == ['some orange spot.', parakeet['text']]
    assert joined[0]['end'] == 1.2


def test_another_speaker_on_the_stream_ends_the_run():
    joined = join_word_pieces(
        [_word('a', 'one', 0.0), _word('b', 'two', 0.5, speaker='SPEAKER_01', speaker_id=2), _word('c', 'three', 1.0)]
    )
    assert _texts(joined) == ['one', 'two', 'three']


def test_gap_scope_and_long_sentence_end_a_run():
    assert len(join_word_pieces([_word('a', 'one', 0.0), _word('b', 'two', 3.5)])) == 2
    assert len(join_word_pieces([_word('a', 'one', 0.0), _word('b', 'two', 0.5, speaker_id_scope='sock:2')])) == 2
    long_sentence = 'x' * 130 + '.'
    assert len(join_word_pieces([_word('a', long_sentence, 0.0), _word('b', 'two', 0.5)])) == 2


def test_only_fresh_words_join_and_receipt_ids_stay_whole():
    stored = [_word('a', 'old', 0.0), _word('b', 'words', 0.5)]
    assert _texts(join_word_pieces([dict(s) for s in stored], joinable_ids={'c'})) == ['old', 'words']
    fresh = _word('c', 'new', 1.0)
    assert _texts(join_word_pieces([dict(s) for s in stored] + [fresh], joinable_ids={'c'})) == ['old', 'words new']
    assert _texts(join_word_pieces([dict(s) for s in stored], protected_ids={'b'})) == ['old', 'words']


def test_unplaced_and_unscoped_pieces_are_left_alone():
    assert (
        len(
            join_word_pieces(
                [_word('a', 'one', 0.0, audio_alignment='unplaced'), _word('b', 'two', 0.5, audio_alignment='unplaced')]
            )
        )
        == 2
    )
    assert (
        len(
            join_word_pieces(
                [_word('a', 'one', 0.0, speaker_id_scope=None), _word('b', 'two', 0.5, speaker_id_scope=None)]
            )
        )
        == 2
    )


def test_join_drops_disjoint_capture_proof_and_one_sided_translations():
    joined = join_word_pieces(
        [
            _word(
                'a',
                'one',
                0.0,
                audio_capture_start=10.0,
                audio_capture_end=10.2,
                translations=[{'lang': 'es', 'text': 'uno'}],
            ),
            _word('b', 'two', 0.5, audio_capture_start=10.5, audio_capture_end=10.7),
        ]
    )
    assert joined[0]['audio_capture_start'] is None and joined[0]['audio_capture_end'] is None
    assert joined[0]['translations'] == []


def test_replayed_batch_is_dropped_by_id_and_by_covered_word():
    stored = [_word('a', 'some orange spot', 0.0, 2.0)]
    again = [_word('a', 'some orange spot', 0.0, 2.0), _word('b', 'orange', 0.5), _word('c', 'fresh', 2.5)]
    assert _texts(drop_replayed_words(stored, again)) == ['fresh']


def test_same_time_word_from_another_provider_or_socket_is_not_a_replay():
    stored = [_word('a', 'some orange spot', 0.0, 2.0)]
    other = [_word('b', 'orange', 0.5, stt_provider='parakeet'), _word('c', 'orange', 0.5, speaker_id_scope='sock:2')]
    assert _texts(drop_replayed_words(stored, other)) == ['orange', 'orange']


def test_replayed_line_without_a_provider_stream_keeps_the_recovery_contract():
    stored = [{'id': 'wal-seg', 'text': 'a whole recovered line', 'start': 0.0, 'end': 2.0}]
    assert _texts(drop_replayed_words(stored, [dict(stored[0])])) == ['a whole recovered line']


def test_repeated_id_inside_one_batch_is_dropped():
    assert _texts(drop_replayed_words([], [_word('a', 'one', 0.0), _word('a', 'one', 0.0)])) == ['one']


def _line(text, start, end):
    return _word('p', text, start, end, stt_provider='parakeet')


def _run(words, start=0.0):
    return [_word(str(i), w, start + i * 0.5) for i, w in enumerate(words)]


def test_run_another_provider_already_wrote_is_dropped_even_minutes_off_the_clock():
    line = _line('did you get five percent of the company', 0.0, 5.0)
    assert drop_repeated_word_runs([line], _run('did you get five percent'.split(), start=120.0)) == []


def test_new_speech_at_the_same_moment_is_kept():
    line = _line('did you get five percent of the company', 0.0, 5.0)
    words = _run('tomorrow morning we leave early'.split())
    assert len(drop_repeated_word_runs([line], words)) == 5


def test_repeat_outside_the_window_or_from_the_same_provider_is_kept():
    line = _line('did you get five percent of the company', 0.0, 5.0)
    assert len(drop_repeated_word_runs([line], _run('did you get five percent'.split(), start=700.0))) == 5
    same = dict(line, stt_provider='soniox')
    assert len(drop_repeated_word_runs([same], _run('did you get five percent'.split()))) == 5


def test_short_run_cannot_prove_a_repeat():
    line = _line('did you get five percent of the company', 0.0, 5.0)
    assert len(drop_repeated_word_runs([line], _run('did you get five'.split()))) == 4


def test_mostly_new_run_stays_whole():
    line = _line('did you get five percent of the company', 0.0, 5.0)
    words = _run('did you get tomorrow morning we leave very early today'.split())
    assert len(drop_repeated_word_runs([line], words)) == 10


def _live_merge(persisted, fresh):
    return merge_live_segments(persisted, fresh, {}).segments


def test_live_words_behind_a_newer_line_still_join():
    stored = [_line('a later sentence from the other provider', 100.0, 110.0)]
    for i, word in enumerate(['some', 'orange', 'spot']):
        stored = _live_merge(stored, [_word(word, word, 10.0 + i * 0.2)])
    assert _texts(stored) == ['some orange spot', 'a later sentence from the other provider']


def test_live_word_after_the_tail_merges_as_before():
    stored = _live_merge([_word('a', 'some', 0.0)], [_word('b', 'orange', 0.5)])
    assert _texts(stored) == ['some orange']


def test_live_word_far_behind_every_line_stays_its_own_line():
    stored = [_word('a', 'old', 0.0), _line('a later sentence', 100.0, 110.0)]
    assert _texts(_live_merge(stored, [_word('b', 'new', 50.0)])) == ['old', 'new', 'a later sentence']


def test_live_word_joins_its_own_stream_across_another_providers_line():
    stored = [_word('a', 'some', 10.0), _line('a whole sentence from the other provider', 10.1, 14.0)]
    assert _texts(_live_merge(stored, [_word('b', 'orange', 10.5)])) == ['some orange', stored[1]['text']]


def test_live_word_from_another_speaker_does_not_anchor_on_this_speaker():
    stored = [_word('a', 'we drove to the', 10.0, 11.0), _line('a whole sentence from the other provider', 10.1, 14.0)]
    other = _word('b', 'home.', 11.5, speaker='SPEAKER_01', speaker_id=2)
    assert 'we drove to the' in _texts(_live_merge(stored, [other]))


def test_another_speaker_inside_a_stored_span_is_not_a_replay():
    stored = [_word('a', 'long stored line', 100.0, 102.0)]
    other = _word('b', 'yes', 101.0, speaker='SPEAKER_01', speaker_id=2)
    assert _texts(drop_replayed_words(stored, [other])) == ['yes']


def test_repeat_run_stops_at_a_speaker_change():
    line = _line('did you get five percent of the company', 0.0, 5.0)
    words = _run('did you get five percent of the'.split())
    words.append(_word('z', 'tomorrow', 3.6, speaker='SPEAKER_01', speaker_id=2))
    assert _texts(drop_repeated_word_runs([line], words)) == ['tomorrow']
