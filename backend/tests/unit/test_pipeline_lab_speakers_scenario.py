"""Speakers in scenario mode (``speakers/scenario.py``, ``scenario/spec.py``, ``scenario/checks.py``): the
``speakers`` block, the ``speakers`` expect key, the scorecard's clock, the staged-unit stand-in and its receipt
rule, the stand-in note, and which STT cassettes may be committed. No stack, no model, no network."""

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from testing.pipeline_lab.scenario import checks, standins
from testing.pipeline_lab.scenario.audio import PUBLIC_CASSETTES, AudioError, _fixture_cassettes, public_audio_hashes
from testing.pipeline_lab.scenario.spec import ScenarioError, load_scenario, parse_scenario
from testing.pipeline_lab.scenario.stack import SCENARIO_DIR
from testing.pipeline_lab.speakers.scenario import LabUnit, ScenarioSpeakers, SpeakerScoring

LIBRI = '../../speakers/fixtures/public-libri'
SPEAKER_SCENARIOS = (
    'speaker_owner_and_person_finish',
    'speaker_owner_absent',
    'speaker_partial_final_pass_keeps_voices',
)


def _raw(**speakers):
    block = {
        'gallery': {'user': f'{LIBRI}/gallery_audio/user.wav', 'person-a': f'{LIBRI}/gallery_audio/person-a.wav'},
        'truth': f'{LIBRI}/conversations/owner_and_person/truth.json',
        **speakers,
    }
    return {
        'name': 'speaker_test',
        'origins': [{'id': 'O'}],
        'recordings': [
            {'id': 'B', 'origin': 'O', 'audio_file': f'{LIBRI}/conversations/owner_and_person/audio.wav'},
        ],
        'speakers': {k: v for k, v in block.items() if v is not None},
        'expect': [{'conversation_of': 'B', 'speakers': {'attribution_min': 0.9, 'voices': 2}}],
    }


def _parse(raw):
    return parse_scenario(raw, path=str(SCENARIO_DIR / 'speaker_test.json'))


# ---- the block and the expect key ---------------------------------------------------------------


def test_speakers_block_resolves_paths_and_defaults():
    scenario = _parse(_raw())
    spec = scenario.speakers
    assert spec.peer is True and spec.recording == 'B' and spec.receipts == 'recording'
    assert set(spec.gallery) == {'user', 'person-a'} and all(Path(p).is_file() for p in spec.gallery.values())
    assert Path(spec.truth).is_file()
    check = scenario.checks[0]
    assert check.fields['speakers'] == {'attribution_min': 0.9, 'voices': [2, 0]}


@pytest.mark.parametrize(
    'change, message',
    [
        ({'peer': False}, 'embeds through the peer'),
        ({'gallery': {'Person A': f'{LIBRI}/gallery_audio/user.wav'}}, 'not an identity'),
        ({'gallery': {'user': 'missing.wav'}}, 'no such file'),
        ({'receipts': 'somebody'}, 'speakers.receipts'),
        ({'recording': 'Z'}, 'speakers.recording'),
        ({'truth': None}, 'needs speakers.truth'),
        ({'colour': 'blue'}, 'unknown keys'),
    ],
)
def test_speakers_block_refuses_bad_input(change, message):
    raw = _raw()
    raw['speakers'] = {k: v for k, v in {**raw['speakers'], **change}.items() if v is not None}
    with pytest.raises(ScenarioError, match=message):
        _parse(raw)


def test_speakers_needs_a_batch_audio_recording():
    raw = _raw()
    raw['recordings'] = [{'id': 'B', 'origin': 'O', 'audio': [0, 10], 'speech': [{'at': 1, 'end': 2, 'text': 'x'}]}]
    raw['expect'] = []
    with pytest.raises(ScenarioError, match='audio_file'):
        _parse(raw)


@pytest.mark.parametrize(
    'expect, message',
    [
        ({'attribution_min': 1.5}, 'a rate from 0 to 1'),
        ({'voices': [2]}, 'voices'),
        ({'voices': True}, 'voices'),
        ({'owner_words_max': -1}, 'whole number'),
        ({'loudness_min': 0.5}, 'unknown keys'),
        ({'resolution': 'maybe'}, 'speaker_resolution status'),
        ({}, 'an object of'),
    ],
)
def test_speakers_expect_key_refuses_bad_bounds(expect, message):
    raw = _raw()
    raw['expect'] = [{'conversation_of': 'B', 'speakers': expect}]
    with pytest.raises(ScenarioError, match=message):
        _parse(raw)


CARD = {
    'attribution': 0.95,
    'owner_precision': None,
    'owner_recall': 0.9,
    'named_accuracy': 0.85,
    'named_coverage': 0.5,
    'wrong_name_rate': 0.02,
    'owner_words': 0,
    'words': 100,
    'voices': 3,
    'truth_voices': 2,
}


def _row(card):
    return {
        'handle': 'abcd1234',
        'recordings': ['B'],
        'words': 100,
        'visible': True,
        'hidden_reason': None,
        'manual_end': True,
        'kind': 'conversation',
        'status': 'completed',
        'titled': True,
        'has_notes': True,
        'deleted': False,
        'speakers': card,
    }


def _check(expect):
    raw = _raw()
    raw['expect'] = [{'conversation_of': 'B', 'speakers': expect}]
    return _parse(raw).checks[0]


def test_speakers_expect_passes_within_bounds_and_names_each_miss():
    ok = checks.evaluate(_check({'attribution_min': 0.9, 'wrong_name_max': 0.05, 'voices': [2, 1]}), [_row(CARD)], 'B')
    assert ok.ok, ok.detail
    bad = checks.evaluate(
        _check({'attribution_min': 0.99, 'voices': 2, 'owner_precision_min': 0.5, 'owner_words_max': 0}),
        [_row(CARD)],
        'B',
    )
    assert not bad.ok
    assert 'attribution=0.95 (want >= 0.99)' in bad.detail
    assert 'voices=3 (want 2)' in bad.detail
    assert 'owner_precision=None' in bad.detail  # nothing to measure fails a minimum
    assert 'owner_words' not in bad.detail  # 0 <= 0 holds
    missing = checks.evaluate(_check({'attribution_min': 0.5}), [_row(None)], 'B')
    assert not missing.ok and 'no scorecard' in missing.detail


def test_speakers_expect_resolution_is_the_stored_status():
    resolved = checks.evaluate(_check({'resolution': 'resolved'}), [_row({**CARD, 'resolution': 'resolved'})], 'B')
    assert resolved.ok, resolved.detail
    unavailable = checks.evaluate(
        _check({'resolution': 'resolved'}), [_row({**CARD, 'resolution': 'unavailable'})], 'B'
    )
    assert not unavailable.ok and "resolution='unavailable' (want 'resolved')" in unavailable.detail


def test_verdict_actual_carries_the_scorecard_numbers_only_when_checked():
    with_card = checks.actual_of(_check({'attribution_min': 0.9}), [_row(CARD)], 'B')
    assert with_card['conversation']['speakers'] == CARD
    assert all(isinstance(v, (int, float)) or v is None for v in with_card['conversation']['speakers'].values())
    raw = _raw()
    raw['expect'] = [{'conversation_of': 'B', 'visible': True}]
    plain = checks.actual_of(_parse(raw).checks[0], [_row(CARD)], 'B')
    assert 'speakers' not in plain['conversation']


# ---- the scorecard's clock ------------------------------------------------------------------------


def test_scorecard_moves_segment_clocks_onto_the_audio_clock():
    t0 = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)
    truth = {
        'turns': [{'start': 0.0, 'end': 4.0, 'speaker': 'owner'}, {'start': 4.0, 'end': 8.0, 'speaker': 'p'}],
        'identities': {'owner': 'user', 'p': 'p'},
    }
    words = [{'start': t + 0.2, 'end': t + 0.6, 'text': 'w'} for t in range(8)]
    scoring = SpeakerScoring(truth=truth, words=words, audio_start=t0, label='B')
    started = t0 + timedelta(seconds=1.0)  # the conversation starts at the first word, 1 s into the audio
    segments = [
        {'start': -1.0, 'end': 3.0, 'speaker_id': 0, 'is_user': True},  # audio 0-4
        {'start': 3.0, 'end': 7.0, 'speaker_id': 1, 'person_id': 'p'},  # audio 4-8
    ]
    card = scoring.card({'started_at': started, 'transcript_segments': segments})
    assert card['attribution'] == 1.0 and card['named_accuracy'] == 1.0 and card['owner_recall'] == 1.0
    as_text = scoring.card({'started_at': started.isoformat().replace('+00:00', 'Z'), 'transcript_segments': segments})
    assert as_text == card  # a stored row read back with an ISO string clock scores the same
    assert card['resolution'] is None
    stored = {'started_at': started, 'transcript_segments': segments, 'speaker_resolution': {'status': 'resolved'}}
    assert scoring.card(stored)['resolution'] == 'resolved'
    unshifted = scoring.card({'started_at': t0, 'transcript_segments': segments})
    assert unshifted['attribution'] < 1.0  # without the shift the turns sit a second early
    assert scoring.card({'transcript_segments': segments}) is None


# ---- the staged-unit stand-in ----------------------------------------------------------------------


def _unit(segment_id='lab-scn-b-0', recording='scn-b'):
    from config.policy import ProjectionPolicy
    from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem

    item = WorkItem(
        segment_id, 'local-dev-user', 0.0, f'lab://{segment_id}', 1.0, Priority.FRESH, conversation_id=recording
    )
    binding = ProjectionBinding('local-dev-user', 'job', 'content', (segment_id,), record_origin=True)
    return LabUnit(item, binding, ProjectionPolicy(), {'words': [], 'audio_seconds': 1.0}, b'RIFF-wav', recording)


@pytest.mark.parametrize('receipts', ['recording', 'processed'])
def test_stand_in_answers_staged_reads_and_keeps_the_receipt_rule(receipts):
    from database.batch_final_pass import ReferenceUnavailable
    from utils.conversations import final_pass_batch

    speakers = ScenarioSpeakers(mode='replay', peer=None, receipts=receipts)
    unit = _unit()
    speakers.register_unit(unit)
    with ExitStack() as stack:
        speakers.install(stack)
        store = final_pass_batch.FirestoreStore(f'batch_pipeline_{final_pass_batch.current_stage()}')
        reference = final_pass_batch.load_reference(store, 'local-dev-user', unit.item.segment_id, 'scn-b')
        assert reference == (unit.item, unit.uri, unit.binding, unit.policy)
        artifacts = final_pass_batch.artifacts_for(store)
        assert artifacts.load_result(unit.item, unit.uri) is unit.payload
        assert artifacts.fetch_audio(unit.item) == unit.wav
        with pytest.raises(ReferenceUnavailable) as missing:
            final_pass_batch.load_reference(store, 'local-dev-user', 'lab-other-0', 'scn-b')
        assert missing.value.reason == 'no_job'
        if receipts == 'recording':
            with pytest.raises(ReferenceUnavailable) as merged:
                final_pass_batch.load_reference(store, 'local-dev-user', unit.item.segment_id, 'v3-derived')
            assert merged.value.outcome == 'skipped_merged'
        else:
            assert final_pass_batch.load_reference(store, 'local-dev-user', unit.item.segment_id, 'v3-derived')
    assert final_pass_batch.load_reference is not None  # restored on exit
    counts = speakers.summary()['counts']
    assert counts['stand_in_load_result'] == 1 and counts['stand_in_fetch_audio'] == 1
    assert counts.get('stand_in_load_reference_skipped_merged', 0) == (1 if receipts == 'recording' else 0)


def test_speaker_note_says_what_ran_and_names_the_counterfactual():
    block = {
        'mode': 'replay',
        'gallery': ['person-a', 'user'],
        'counts': {
            'batch_lane_diarizations': 1,
            'gallery_embeddings': 2,
            'stand_in_load_reference': 3,
            'stand_in_load_result': 1,
            'stand_in_fetch_audio': 1,
        },
        'resolver_reasons': {'resolved': 1},
        'final_pass': ['success'],
        'receipts': 'processed',
        'cassette_outcomes': {'/v2/diarization': {'hit': 2}},
    }
    note = standins.speaker_note(block)
    assert 'cassettes only' in note and '/v2/diarization hit x2' in note
    assert 'HttpDiarizer' in note and 'set_user_speaker_embedding' in note and 'paid plan' in note
    assert 'resolved x1' in note and 'returned success' in note
    assert 'load_reference x3' in note and 'Counterfactual' in note
    production = standins.speaker_note(
        {**block, 'receipts': 'recording', 'counts': {'stand_in_load_reference_skipped_merged': 2}}
    )
    assert 'Counterfactual' not in production and '2 read(s) for another conversation' in production
    notes = standins.stand_in_notes({'stand_ins': {}, 'speakers': block})
    assert [n['name'] for n in notes] == ['speakers', 'outline_model']


# ---- committed scenarios and cassettes -----------------------------------------------------------


@pytest.mark.parametrize('name', SPEAKER_SCENARIOS)
def test_committed_speaker_scenarios_are_budgeted_and_score_against_truth(name):
    scenario = load_scenario(SCENARIO_DIR / f'{name}.json')
    assert scenario.speakers is not None and scenario.speakers.truth and scenario.speakers.gallery
    assert any('speakers' in check.fields for check in scenario.checks)
    assert {'reads', 'writes', 'noop_writes', 'vendor_calls'} <= set(scenario.budget)
    assert all(Path(path).is_file() for path in (*scenario.speakers.gallery.values(), scenario.speakers.truth))


def test_committed_public_cassettes_are_local_cassettes_of_committed_public_audio():
    cassettes = _fixture_cassettes(PUBLIC_CASSETTES, public=True)
    assert cassettes and {c.source for c in cassettes} == {'local'}
    hashes = public_audio_hashes()
    assert all(c.key.audio_sha256 in hashes for c in cassettes)
    assert all((c.source_detail or {}).get('windows') == 'vad' for c in cassettes)


def test_a_local_cassette_of_other_audio_may_not_be_committed(tmp_path):
    from testing.pipeline_lab.cassette.format import Cassette, CassetteKey, Word

    key = CassetteKey.for_audio(b'\1\0' * 1600, provider='parakeet_local', model='m', language='en', vocabulary=[])
    cassette = Cassette(key, 0.1, [Word(0.0, 0.1, 'synthetic')], source='local')
    target = tmp_path / key.digest[:2] / f'{key.digest}.json'
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(cassette.to_json()))
    with pytest.raises(AudioError, match='not a committed public corpus file'):
        _fixture_cassettes(tmp_path, public=True)
    with pytest.raises(AudioError, match='only synthetic'):
        _fixture_cassettes(tmp_path)


def test_compare_metric_reports_each_speaker_scenarios_scorecard(tmp_path):
    from testing.pipeline_lab.speakers.compare_metrics import speaker_metrics

    (tmp_path / 'verdict.json').write_text(json.dumps({'scenarios': [{'name': 'spk'}, {'name': 'plain'}]}))
    for name, result in (
        (
            'spk',
            {
                'speakers': {'final_pass': ['success']},
                'conversations': [
                    {'speakers': {**CARD, 'words': 10}},
                    {'speakers': {**CARD, 'resolution': 'resolved'}},
                    {'recordings': ['C']},
                ],
            },
        ),
        ('plain', {'conversations': [{'recordings': ['B']}]}),
    ):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'result.json').write_text(json.dumps(result))
    values = speaker_metrics(tmp_path)
    assert values['spk.attribution'] == 0.95 and values['spk.words'] == 100  # the card with the most words
    assert values['spk.final_pass'] == 'success'
    assert values['spk.resolution'] == 'resolved'
    assert 'spk.owner_precision' not in values  # null: nothing to measure
    assert not any(key.startswith('plain.') for key in values)
