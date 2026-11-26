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


def test_arm_output_is_owner_only_even_under_a_permissive_umask(tmp_path, monkeypatch):
    import json
    import os
    import stat

    from testing.pipeline_lab.speakers import arm_runner

    monkeypatch.setitem(arm_runner.ENGINES, 'echo', lambda conversation, gallery: {'key': conversation['key']})
    out = tmp_path / 'out.jsonl'
    job = tmp_path / 'job.json'
    job.write_text(json.dumps({'engine': 'echo', 'conversations': [{'key': 'k'}], 'out': str(out)}))
    previous = os.umask(0o022)
    try:
        assert arm_runner.main([str(job)]) == 0
    finally:
        os.umask(previous)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_scoped_speaker_count_ignores_voices_outside_the_conversation():
    words = _words('one two three four five six')
    truth = {'turns': [{'start': 0, 'end': 10, 'speaker': 'a'}], 'identities': {'a': 'user'}}
    predicted = [
        {'start': 0.0, 'end': 1.4, 'speaker_id': 0, 'speaker_id_scope': 's', 'is_user': False},
        {'start': 1.5, 'end': 3.0, 'speaker_id': 1, 'speaker_id_scope': 's', 'is_user': True},
    ]
    owned = {3, 4, 5}
    assert score.score_conversation(words, truth, predicted)['predicted_voices'] == 2
    assert score.score_conversation(words, truth, predicted, owned)['predicted_voices'] == 1


def test_silver_places_manual_corrections_by_text_not_by_the_stored_clock():
    from testing.pipeline_lab.speakers.corpus import Conversation

    words = _words('alpha beta gamma delta epsilon zeta')
    labels = ['A', 'A', 'A', 'B', 'B', 'B']
    production = {
        'segment_clock_offset': -500.0,  # a clock that would put every stored segment far from its words
        'segments': [
            {'text': 'alpha beta gamma', 'start': 900, 'end': 901, 'speaker_label_source': 'auto'},
            {'text': 'delta epsilon zeta', 'start': 1, 'end': 2, 'speaker_label_source': 'manual', 'is_user': True},
        ],
    }
    conversation = Conversation(key='k', path=None, production=production)
    assert silver.manual_overrides(conversation, words, labels) == {'B': 'user'}


def test_stored_labels_align_in_non_latin_scripts():
    words = _words('привет как дела 你好 世界')
    segments = [{'text': 'Привет как дела', 'is_user': True, 'speaker_id': 0}, {'text': '你好 世界', 'speaker_id': 1}]
    turns = bench.stored_turns(words, segments)
    assert [t['is_user'] for t in turns] == [True, False]
    assert bench.owned_words(words, segments) == {0, 1, 2, 3, 4}


def test_uncertain_silver_voices_do_not_dilute_identity_rates():
    words = _words('a b c d e f g h i j')
    truth = {
        'turns': [{'start': 0, 'end': 0.45, 'speaker': 'known'}, {'start': 0.45, 'end': 10, 'speaker': 'uncertain'}],
        'identities': {'known': None, 'uncertain': '?'},
    }
    predicted = [{'start': 0, 'end': 10, 'speaker_id': 0, 'speaker_id_scope': 's', 'person_id': 'p1'}]
    card = score.score_conversation(words, truth, predicted)
    assert card['words'] == 10 and card['identity_words'] == 1
    assert card['wrong_name_rate'] == 1.0  # not 0.1: the one judgeable word was wrongly named
    allunsure = {'turns': [{'start': 0, 'end': 10, 'speaker': 'u'}], 'identities': {'u': '?'}}
    assert score.score_conversation(words, allunsure, predicted)['wrong_name_rate'] is None


def test_v3_export_reads_chunks_under_the_source_recording(monkeypatch):
    from types import SimpleNamespace

    from testing.pipeline_lab.speakers import owner_export
    from utils.other import storage

    holders = []
    monkeypatch.setattr(
        storage, 'list_audio_chunks', lambda uid, holder: holders.append(holder) or [{'timestamp': 1.0}]
    )
    monkeypatch.setattr(storage, 'download_audio_chunks_and_merge', lambda *a, **k: b'\x01\x00' * 160)
    row = {
        'id': 'derived',
        'started_at': '2026-11-26T00:00:00+00:00',
        'audio_files': [
            {'id': 'af', 'recording_id': 'rec', 'started_at': '2026-11-26T00:00:00+00:00', 'chunk_timestamps': [1.0]}
        ],
    }
    assert owner_export.conversation_pcm('uid', row) == b'\x01\x00' * 160
    assert holders == ['rec']


def test_conflicting_manual_corrections_leave_the_voice_uncertain():
    from testing.pipeline_lab.speakers.corpus import Conversation

    words = _words('alpha beta gamma delta')
    production = {
        'segments': [
            {'text': 'alpha beta', 'speaker_label_source': 'manual', 'is_user': True},
            {'text': 'gamma delta', 'speaker_label_source': 'manual', 'person_id': 'p1'},
        ]
    }
    conversation = Conversation(key='k', path=None, production=production)
    assert silver.manual_overrides(conversation, words, ['A', 'A', 'A', 'A']) == {'A': silver.UNKNOWN}


def test_gap_sentinel_words_are_abstentions_not_a_voice():
    words = _words('a b c d')
    truth = {'turns': [{'start': 0, 'end': 10, 'speaker': 'x'}], 'identities': {'x': 'user'}}
    gaps = [{'start': 0, 'end': 10, 'speaker': None, 'speaker_id': 99, 'speaker_id_scope': 'final:pyannote:c'}]
    card = score.score_conversation(words, truth, gaps)
    assert card['attribution'] == 0.0 and card['predicted_voices'] == 0


def test_failed_final_pass_is_an_arm_error(monkeypatch, tmp_path):
    from testing.pipeline_lab.speakers import arm_runner
    from utils.conversations import final_pass_pyannote

    monkeypatch.setattr(final_pass_pyannote, 'run_final_pass', lambda *a, **k: (None, {'outcome': 'failed:service'}))
    monkeypatch.setattr(arm_runner, 'run_final_pass', final_pass_pyannote.run_final_pass)
    pcm = tmp_path / 'a.pcm'
    pcm.write_bytes(b'\0\0' * 1600)
    result = arm_runner.final_pass({'key': 'k', 'pcm_path': str(pcm), 'words': []}, {})
    assert result['error'] == 'final_pass failed:service' and 'segments' not in result
