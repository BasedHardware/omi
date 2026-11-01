"""Quality corpus helpers and the #22358 / #22368 paired-run gates (pure parts; GPU runs on staging)."""

import json

import numpy as np
import pytest

from scripts.parity import scorers  # noqa: F401  (loads scipy/jiwer at collection, not in a timed call)
from testing.quality_corpus import corpus, paired_flight_batching as flight, paired_short_speech as short
from testing.quality_corpus.audio import (
    Turn,
    crop_words,
    merge_turns,
    parse_ami_words,
    parse_rttm,
    quiet_bed,
    speaker_at,
)
from testing.quality_corpus.chain import wav_bytes, wav_seconds

PROD = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'


def test_prod_revision_constants_match_the_worker_pin():
    source = open('diarizer/batch_pipeline_startup.py').read()
    assert f"DIARIZER_REVISION = '{PROD}'" in source
    assert short.PROD_DIARIZER_REVISION == flight.PROD_DIARIZER_REVISION == PROD


def test_rttm_and_ami_parsers():
    turns = parse_rttm('SPEAKER f 1 1.00 0.50 <NA> <NA> spk1 <NA> <NA>\nSPEAKER g 1 0 1 <NA> <NA> x <NA> <NA>\n', 'f')
    assert turns == [Turn(1.0, 1.5, 'spk1')]
    xml = (
        '<nite:root xmlns:nite="http://nite.sourceforge.net/"><w starttime="1.0" endtime="1.4">Hi</w>'
        '<w starttime="1.4" endtime="1.4" punc="true">.</w><w>untimed</w></nite:root>'
    )
    assert parse_ami_words({'A': xml}) == [{'text': 'Hi', 'start': 1.0, 'end': 1.4, 'speaker': 'A'}]
    cropped = crop_words([{'text': 'a', 'start': 9.9, 'end': 10.3, 'speaker': 'A'}], 10.0, 20.0)
    assert cropped == [{'text': 'a', 'start': 0.0, 'end': pytest.approx(0.3), 'speaker': 'A'}]


def test_merge_turns_and_speaker_at():
    merged = merge_turns([Turn(0, 0.4, 'A'), Turn(0.5, 0.9, 'A'), Turn(2.0, 2.5, 'A'), Turn(0.6, 1.0, 'B')])
    assert merged == [Turn(0, 0.9, 'A'), Turn(0.6, 1.0, 'B'), Turn(2.0, 2.5, 'A')]
    assert speaker_at(merged, 0.3) == 'A' and speaker_at(merged, 0.7) is None and speaker_at(merged, 1.5) is None


def test_wav_roundtrip_and_quiet_bed_level():
    bed = quiet_bed(2.0, seed=1)
    assert abs(20 * np.log10(np.sqrt(np.mean(bed**2)))) == pytest.approx(55, abs=0.5)
    assert wav_seconds(wav_bytes(bed)) == pytest.approx(2.0)


def test_isolated_turns_and_excerpt_plan_respect_the_gate_shape():
    turns = {
        's': [
            Turn(0.0, 1.0, 'A'),
            Turn(3.0, 3.5, 'B'),
            Turn(6.0, 6.6, 'A'),
            Turn(9.0, 9.4, 'B'),
            Turn(12.0, 12.5, 'A'),
            Turn(12.6, 13.0, 'B'),
        ]
    }
    isolated = short.isolated_turns(turns['s'], 0.4, 2.0, isolation=0.25)
    assert Turn(12.0, 12.5, 'A') not in isolated and Turn(3.0, 3.5, 'B') in isolated
    specs = short.plan_excerpts(turns, seed=1, max_per_kind=10, isolation=0.25)
    kinds = {s['kind'] for s in specs}
    assert kinds == {'single', 'burst_same', 'burst_diff'}
    for spec in specs:
        if spec['pause'] is not None:
            assert spec['pause'] <= 0.5
            assert sum(e - s for _, s, e in spec['parts']) + spec['pause'] <= 2.0 + 1e-9
    assert all(len(set(s['speakers'])) == 2 for s in specs if s['kind'] == 'burst_diff')


def test_render_unit_places_excerpt_inside_a_30s_bed():
    audio = {'s': np.ones(16000 * 4, dtype=np.float32) * 0.5}
    unit = short.render_unit({'parts': [('s', 1.0, 1.5), ('s', 2.0, 2.4)], 'pause': 0.25}, audio, seed=3)
    assert len(unit) == 30 * 16000
    loud = np.flatnonzero(np.abs(unit) > 0.1)
    assert (loud[-1] - loud[0] + 1) / 16000 == pytest.approx(0.5 + 0.25 + 0.4, abs=0.01)


def unit(kind='single', fired=True, off_speakers=1, ref_speakers=1, identical=True):
    return {
        'kind': kind,
        'pause': None if kind == 'single' else 0.5,
        'fired': fired,
        'off_word_speakers': off_speakers,
        'reference_speakers': ref_speakers,
        'words': 3,
        'words_identical': identical,
    }


IDENTITY = {'diarizer_revision': PROD, 'device': 'NVIDIA L4'}


def test_short_speech_gate_pass_fail_and_insufficient():
    units = [unit()] * 150 + [unit('burst_same')] * 30 + [unit('burst_diff', ref_speakers=2)] * 30
    assert short.evaluate(units, IDENTITY, min_fired=200, min_fired_bursts=50)['status'] == 'pass'
    bad = units + [unit('burst_diff', off_speakers=2, ref_speakers=2)]
    result = short.evaluate(bad, IDENTITY, min_fired=200, min_fired_bursts=50)
    assert result['status'] == 'fail' and result['disagreements'] == 1
    assert result['by_kind']['burst_diff']['fired_full_multi_speaker'] == 1
    assert (
        short.evaluate(units[:100], IDENTITY, min_fired=200, min_fired_bursts=50)['status'] == 'insufficient_evidence'
    )
    # A unit the gate does not fire on can never be a disagreement.
    quiet = units + [unit(fired=False, off_speakers=3)]
    assert short.evaluate(quiet, IDENTITY, min_fired=200, min_fired_bursts=50)['status'] == 'pass'


def test_short_speech_gate_refuses_wrong_revision_device_or_changed_words():
    units = [unit()] * 250 + [unit('burst_same')] * 60
    for identity in ({**IDENTITY, 'diarizer_revision': '8a52737'}, {**IDENTITY, 'device': 'Tesla T4'}):
        assert short.evaluate(units, identity, min_fired=200, min_fired_bursts=50)['status'] == 'fail'
    assert short.evaluate(units + [unit(identical=False)], IDENTITY, min_fired=200, min_fired_bursts=50)[
        'failures'
    ] == ['words_differ_between_passes']


def qualify_receipt(**changes):
    receipt = {
        'diarizer_revision': PROD,
        'model_batch_size': 8,
        'device': 'NVIDIA L4',
        'gate': {
            'status': 'pass',
            'multispeaker_units': 6,
            'thresholds': {'min_agreement': 0.99, 'max_peak_ratio': 1.1, 'min_multispeaker_units': 5},
        },
    }
    receipt.update(changes)
    return receipt


def test_flight_qualify_receipt_is_reverified_independently():
    assert flight.verify_qualify_receipt(qualify_receipt()) == []
    assert flight.verify_qualify_receipt(qualify_receipt(diarizer_revision='8a52737')) == ['qualify_revision_not_prod']
    assert flight.verify_qualify_receipt(qualify_receipt(model_batch_size=16)) == ['qualify_batch_pin_not_8']
    assert flight.verify_qualify_receipt(qualify_receipt(device='Tesla T4')) == ['qualify_device_not_l4']
    loose = qualify_receipt()
    loose['gate'] = {
        **loose['gate'],
        'thresholds': {'min_agreement': 0.95, 'max_peak_ratio': 1.1, 'min_multispeaker_units': 5},
    }
    assert flight.verify_qualify_receipt(loose) == ['qualify_thresholds_loosened']


def words(labels):
    return [{'text': f'w{i}', 'start': float(i), 'end': i + 0.5, 'speaker': s} for i, s in enumerate(labels)]


def test_flight_chain_pair_maps_labels_and_gates():
    same = flight.pair_unit(words(['A', 'B', 'A', 'B']), words(['X', 'Y', 'X', 'Y']))
    assert same['label_agreement'] == 1.0 and same['words_identical']
    flipped = flight.pair_unit(words(['A'] * 99 + ['B'] * 101), words(['X'] * 98 + ['Y'] * 102))
    assert flipped['label_agreement'] == pytest.approx(0.995)
    assert flight.evaluate_chain_pair([same] * 5)['status'] == 'pass'
    assert flight.evaluate_chain_pair([same] * 4)['status'] == 'insufficient_evidence'
    drift = flight.pair_unit(words(['A'] * 90 + ['B'] * 10), words(['X'] * 80 + ['Y'] * 20))
    assert flight.evaluate_chain_pair([same] * 5 + [drift])['failures'] == ['chain_label_agreement_below_limit']


def test_flight_combined_verdict():
    passing = {'status': 'pass'}
    assert flight.combine([], passing) == ('pass', 0)
    assert flight.combine(['qualify_insufficient_evidence'], passing) == ('insufficient_evidence', 2)
    assert flight.combine(['qualify_revision_not_prod'], passing) == ('fail', 1)
    assert flight.combine([], {'status': 'fail'}) == ('fail', 1)


def test_corpus_score_aggregates_without_text(tmp_path):
    units = tmp_path / 'built'
    (units / 'refs').mkdir(parents=True)
    index = {
        'ami-x': {'use': ['wer', 'speaker'], 'seconds': 3600.0},
        'silence-00': {'use': ['silence'], 'seconds': 60.0},
    }
    (units / 'index.json').write_text(json.dumps(index))
    ref_words = [
        {'text': 'hello', 'start': 0.0, 'end': 0.5, 'speaker': 'A'},
        {'text': 'there', 'start': 1.0, 'end': 1.5, 'speaker': 'B'},
    ]
    (units / 'refs' / 'ami-x.json').write_text(
        json.dumps({'use': ['wer', 'speaker'], 'text': 'hello there', 'words': ref_words})
    )
    (units / 'refs' / 'silence-00.json').write_text(json.dumps({'use': ['silence']}))
    batch = tmp_path / 'batch'
    batch.mkdir()
    (batch / 'ami-x.json').write_text(
        json.dumps(
            {
                'words': [
                    {'text': 'hello', 'start': 0.0, 'end': 0.5, 'speaker': 'S1'},
                    {'text': 'their', 'start': 1.0, 'end': 1.5, 'speaker': 'S2'},
                ]
            }
        )
    )
    (batch / 'silence-00.json').write_text(
        json.dumps({'words': [{'text': 'uh', 'start': 1, 'end': 2, 'speaker': 'S1'}]})
    )
    scores = corpus.score(units, batch, None, None, pinned=True)
    assert scores['corpus_minutes'] == 60.0
    batch_scores = scores['pipelines']['batch']
    # One substitution plus the filler emitted on the silence bed.
    assert batch_scores['wer']['errors'] == 2 and batch_scores['wer']['reference_words'] == 2
    assert batch_scores['speaker'] == {'words': 2, 'correct_1to1': 2, 'accuracy_1to1': 1.0}
    assert batch_scores['silence_inserted_words'] == 1
    assert 'hello' not in json.dumps(scores)


def test_corpus_score_charges_silence_insertions_and_counts_missing_units(tmp_path):
    units = tmp_path / 'built'
    (units / 'refs').mkdir(parents=True)
    index = {
        'libri-a': {'use': ['wer'], 'seconds': 1800.0},
        'libri-b': {'use': ['wer'], 'seconds': 1800.0},
        'silence-00': {'use': ['silence'], 'seconds': 60.0},
    }
    (units / 'index.json').write_text(json.dumps(index))
    for unit in ('libri-a', 'libri-b'):
        (units / 'refs' / f'{unit}.json').write_text(json.dumps({'use': ['wer'], 'text': 'one two'}))
    (units / 'refs' / 'silence-00.json').write_text(json.dumps({'use': ['silence']}))
    batch = tmp_path / 'batch'
    batch.mkdir()
    (batch / 'libri-a.json').write_text(json.dumps({'words': [{'text': 'one two', 'start': 0, 'end': 1}]}))
    silence = [{'text': 'ghost words', 'start': 0, 'end': 1}, {'text': 'uh', 'start': 1, 'end': 2}]
    (batch / 'silence-00.json').write_text(json.dumps({'words': silence}))
    side = corpus.score(units, batch, None, None, pinned=True)['pipelines']['batch']
    assert side['missing_units'] == 1 and side['scored_wer_minutes'] == 30.0
    # Three tokens on the silence bed, filler included, are insertion errors in the pooled WER.
    assert side['wer']['errors'] == 3 and side['wer']['reference_words'] == 2
    assert side['wer']['wer'] == 1.5


def test_paired_run_job_fails_on_gate_failure_and_unknown_run():
    script = (corpus.HERE / 'k8s' / 'paired-run-job.yaml').read_text()
    assert script.count('|| gate=$?') == 2 and 'echo "exit=$?"' not in script
    assert script.rstrip().count('exit "$gate"') == 1
    assert script.index('*)') < script.index('esac') and 'exit 64' in script


def test_manifest_meets_the_row1_sixty_minute_floor():
    manifest = json.loads(corpus.MANIFEST.read_text())
    wer_minutes = sum(g['minutes'] for g in manifest['groups'] if 'wer' in g['use'])
    assert wer_minutes >= 60
    assert all(u.startswith('https://') for u in corpus.source_urls(manifest).values())


def test_fetch_refuses_unpinned_and_mismatched_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, 'LOCK', tmp_path / 'lock.json')
    monkeypatch.setattr(corpus, 'source_urls', lambda manifest: {'src/a.bin': 'https://example.invalid/a.bin'})

    class Body:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            import io

            return io.BytesIO(self.payload)

        def __exit__(self, *exc):
            return False

    opener = lambda url, timeout: Body(b'abc')  # noqa: E731
    with pytest.raises(corpus.CorpusError, match='unpinned'):
        corpus.fetch(tmp_path / 'cache', pin=False, opener=opener)
    lock = corpus.fetch(tmp_path / 'cache', pin=True, opener=opener)
    assert lock['sha256']['src/a.bin'] == corpus.sha256_file(tmp_path / 'cache' / 'src/a.bin')
    (tmp_path / 'cache' / 'src/a.bin').write_bytes(b'tampered')
    with pytest.raises(corpus.CorpusError, match='mismatch'):
        corpus.fetch(tmp_path / 'cache', pin=False, opener=opener)
