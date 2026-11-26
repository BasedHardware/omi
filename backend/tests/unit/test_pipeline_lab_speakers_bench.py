"""Speaker bench: stored labels placed by text, scoped scoring, silver consensus. Synthetic data only."""

from testing.pipeline_lab.speakers import bench, score, silver


def _words(text, start=0.0, step=0.5):
    return [{'start': start + i * step, 'end': start + i * step + 0.4, 'text': w} for i, w in enumerate(text.split())]


def test_stored_labels_are_placed_by_text_not_by_their_clock():
    words = _words('hello there how are you today fine thanks')
    # Stored clocks are far from the audio clock (production's are, measured on an owner corpus).
    segments = [
        {'text': 'hello there how are you', 'start': 500.0, 'end': 502.0, 'is_user': True, 'speaker_id': 0},
        {'text': 'today fine thanks', 'start': 900.0, 'end': 901.0, 'person_id': 'p1', 'speaker_id': 1},
    ]
    turns = bench.stored_turns(words, segments)
    assert [t['is_user'] for t in turns] == [True, False]
    assert turns[0]['start'] == 0.0 and turns[1]['person_id'] == 'p1'
    assert turns[0]['end'] <= turns[1]['start']


def test_words_between_two_aligned_words_of_one_segment_take_it():
    words = _words('alpha beta gamma delta')
    turns = bench.stored_turns(words, [{'text': 'alpha xxx delta', 'is_user': True, 'speaker_id': 0}])
    assert len(turns) == 1 and turns[0]['start'] == 0.0 and turns[0]['end'] >= words[-1]['end'] - 1e-6


def test_owned_words_and_scoped_scoring_ignore_audio_the_conversation_does_not_own():
    words = _words('one two three four five six')
    segments = [{'text': 'four five six', 'is_user': True, 'speaker_id': 0}]
    owned = bench.owned_words(words, segments)
    assert owned == {3, 4, 5}
    truth = {'turns': [{'start': 0, 'end': 10, 'speaker': 'a'}], 'identities': {'a': 'user'}}
    predicted = bench.stored_turns(words, segments)
    whole = score.score_conversation(words, truth, predicted)
    scoped = score.score_conversation(words, truth, predicted, owned)
    assert whole['words'] == 6 and whole['owner_recall'] == 0.5
    assert scoped['words'] == 3 and scoped['owner_recall'] == 1.0 and scoped['owner_precision'] == 1.0


def test_unknown_silver_identity_counts_for_attribution_only():
    words = _words('a b c d')
    truth = {'turns': [{'start': 0, 'end': 10, 'speaker': 's0'}], 'identities': {'s0': '?'}}
    predicted = [{'start': 0, 'end': 10, 'speaker_id': 0, 'is_user': True}]
    card = score.score_conversation(words, truth, predicted)
    assert card['attribution'] == 1.0
    assert card['owner_claimed'] == 0 and card['wrong_name_words'] == 0


def test_silver_keeps_only_words_both_diarizers_agree_on():
    primary = ['A', 'A', 'B', 'B', None]
    reference = ['x', 'x', 'y', 'x', 'y']  # x -> A, y -> B after Hungarian mapping
    assert silver.consensus(primary, reference) == ['A', 'A', 'B', silver.UNSURE, silver.UNSURE]


def test_silver_turns_are_exclusive_and_cover_each_word():
    words = [{'start': 0.0, 'end': 0.6}, {'start': 0.5, 'end': 1.0}, {'start': 3.0, 'end': 3.4}]
    turns = silver.to_turns(words, ['A', 'B', 'B'])
    assert [t['speaker'] for t in turns] == ['A', 'B', 'B']
    assert all(a['end'] <= b['start'] for a, b in zip(turns, turns[1:]))


def test_arm_spec_parses_name_backend_engine_and_env():
    arm = bench.Arm.parse('tight@/tmp/tree:final_pass:A=1,B=2')
    assert (arm.name, arm.backend.name, arm.engine, arm.env) == ('tight', 'tree', 'final_pass', {'A': '1', 'B': '2'})
    assert bench.Arm.parse('base').env == {}


def test_gates_fail_on_missing_or_out_of_range_metrics():
    report = {'arms': {'base': {'pooled': {'attribution': 0.8, 'wrong_name_rate': 0.02}}}}
    assert bench.check_gates(report, ['base.attribution>=0.75', 'base.wrong_name_rate<=0.05']) == []
    failures = bench.check_gates(report, ['base.attribution>=0.9', 'base.owner_recall>=0.5'])
    assert len(failures) == 2
