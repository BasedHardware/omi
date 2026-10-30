"""Synthetic privacy, clock, and blinding contracts for local review tools."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.diarization_eval import prep_speaker_task as prep
from scripts.diarization_eval import build_viewer as viewer
from scripts.diarization_eval import cluster_speaker_task as cluster_tool


def fixture(tmp_path):
    audio = tmp_path / 'fiction.wav'
    audio.write_bytes(b'synthetic')
    return {
        'recordings': [
            {
                'id': 'fiction',
                't0': 100,
                'dur': 8,
                'media': str(audio),
                'words': [{'start': 0.2, 'end': 1, 'text': 'Hello', 'truth': 'Person'}],
            }
        ]
    }


def runs():
    return {
        'recordings': [
            {
                'id': 'fiction',
                'status': 'ok',
                'clock': 'crop',
                'provenance': {'production_path': True, 'adapter': 'synthetic'},
                'turns': [{'start': 0.2, 'end': 1, 'speaker': 'speaker_0', 'text': 'Hello'}],
            }
        ]
    }


def test_import_closed_labels_preserves_clock_and_exclusions(tmp_path):
    archive = tmp_path / 'archive'
    (archive / 'build').mkdir(parents=True)
    source = {
        't0': 100,
        'dur': 30,
        'words': [{'s': i, 'e': i + 0.5, 'w': 'fiction', 't': 'untrusted', 'pyannote': 'voice'} for i in range(5)],
    }
    (archive / 'build' / 'conv_fiction.json').write_text(json.dumps(source))
    (archive / 'build' / 'truth.json').write_text(json.dumps({'fiction': ['Person', 'Unsure', 'noise', 'mixed', None]}))
    result = prep.prepare(archive, tmp_path / 'private' / 'reference.json')
    recording = result['recordings'][0]
    assert (recording['t0'], recording['dur']) == (100, 30)
    assert [w['start'] for w in recording['words']] == list(range(5))
    assert [w['truth'] for w in recording['words']] == ['Person', None, None, None, None]
    assert (tmp_path / 'private' / 'reference.json').stat().st_mode & 0o777 == 0o600
    assert (tmp_path / 'private').stat().st_mode & 0o777 == 0o700


def test_join_is_strict_and_excluded_words_break_adjacency():
    words = [
        {'start': 0, 'end': 1, 'text': 'a', 'truth': 'P'},
        {'start': 2.999, 'end': 3, 'text': 'b', 'truth': 'P'},
        {'start': 5, 'end': 6, 'text': 'c', 'truth': 'P'},
        {'start': 6, 'end': 6.1, 'text': 'noise', 'truth': None},
        {'start': 6.2, 'end': 7, 'text': 'd', 'truth': 'P'},
    ]
    assert [r['text'] for r in viewer.joined_reference(words)] == ['a b', 'c', 'd']


def test_prepare_segments_use_diarizer_changes_not_truth():
    words = [{'start': i, 'end': i + 0.5, 'diarizer': str(i // 2), 'truth': 'P'} for i in range(4)]
    assert [(s['w0'], s['w1']) for s in prep.make_segments(words)] == [(0, 2), (2, 4)]
    assert prep.make_segments([]) == []


def test_missing_production_keeps_task_pending(tmp_path):
    result = viewer.build(fixture(tmp_path), None, tmp_path / 'task')
    assert result == {'pending': True, 'items': 0, 'recordings': 1}
    assert (tmp_path / 'task' / 'items.jsonl').read_text() == ''
    assert 'pending' in json.loads((tmp_path / 'task' / 'task.yaml').read_text())


def test_nonproduction_outputs_cannot_populate_task(tmp_path):
    data = runs()
    data['recordings'][0]['provenance']['production_path'] = False
    assert viewer.build(fixture(tmp_path), data, tmp_path / 'task')['pending']


def test_capture_clock_is_rebased_only_for_production():
    data = runs()['recordings'][0]
    data['clock'] = 'capture'
    data['turns'][0].update(start=100.2, end=101)
    assert viewer.production_turns(data, 100)[0]['start'] == pytest.approx(0.2)


def test_persisted_numeric_voice_zero_and_other_channels_remain_distinct():
    data = {
        'clock': 'crop',
        'turns': [
            {'start': 0, 'end': 1, 'text': 'synthetic', 'speaker_id': 0, 'speaker_id_scope': 'unit'},
            {'start': 1, 'end': 2, 'text': 'example', 'speaker_id': 1, 'speaker_id_scope': 'unit'},
        ],
    }
    rows = viewer.production_turns(data, 0)
    assert [r['name'] for r in rows] == ['Speaker 0', 'Speaker 1']
    assert rows[0]['speaker'] != rows[1]['speaker']


def test_populated_pairs_are_balanced_and_provenance_hidden(tmp_path, monkeypatch):
    letters_tool = tmp_path / 'synthetic-letters.js'

    def letters(command, **options):
        assert command == [
            'node',
            str(letters_tool),
            '--variants',
            'production,reference',
            '--ids',
            'recording-1-section-1,recording-1-section-2',
            '--seed',
            'task',
        ]
        assert options == {'check': True, 'capture_output': True, 'text': True}
        return SimpleNamespace(
            stdout='\n'.join(
                json.dumps(row)
                for row in [
                    {'item_id': 'recording-1-section-1', 'letters': {'A': 'production', 'B': 'reference'}},
                    {'item_id': 'recording-1-section-2', 'letters': {'A': 'reference', 'B': 'production'}},
                ]
            )
        )

    monkeypatch.setattr(viewer.subprocess, 'run', letters)
    reference = fixture(tmp_path)
    result = viewer.build(reference, runs(), tmp_path / 'task', section_seconds=4, letters_tool=letters_tool)
    assert result['items'] == 2
    cards = [json.loads(line) for line in (tmp_path / 'task' / 'items.jsonl').read_text().splitlines()]
    assert [c['hidden']['production_letter'] for c in cards] in [['A', 'B'], ['B', 'A']]
    for card in cards:
        assert [s['label'] for s in card['content']['sides']] == ['A', 'B']
        visible = {k: v for k, v in card.items() if k not in ('hidden', 'stratum')}
        assert 'production' not in json.dumps(visible)
        assert 'reference' not in json.dumps(visible)
    assert (tmp_path / 'task' / 'hidden' / 'provenance.json').stat().st_mode & 0o777 == 0o600


def test_no_rebuild_after_human_judgments(tmp_path):
    task = tmp_path / 'task'
    (task / 'labels').mkdir(parents=True)
    with pytest.raises(ValueError, match='existing judgments'):
        viewer.build(fixture(tmp_path), runs(), task)


def test_private_output_refuses_git_checkout(tmp_path):
    (tmp_path / '.git').write_text('gitdir: fictional')
    with pytest.raises(ValueError, match='outside a Git checkout'):
        prep.private_dir(tmp_path / 'private')


def test_review_groups_never_become_identities(tmp_path):
    pytest.importorskip('scipy')
    reference = fixture(tmp_path)
    reference['recordings'][0]['segments'] = [{'start': 0, 'end': 1}, {'start': 2, 'end': 3}]
    result = cluster_tool.cluster(reference, tmp_path / 'groups.json', embed=lambda *_: [1, 0])
    assert result['automatic_identity'] is False
    assert result['threshold'] == 0.5
    assert {r['review_group'] for r in result['recordings'][0]['segments']} == {'review-0'}
    assert 'truth' not in json.dumps(result)


def test_enrollment_reserves_first_clean_span_without_other_labels():
    words = [
        {'start': 0, 'end': 4, 'truth': 'P'},
        {'start': 4, 'end': 5, 'truth': 'Q'},
        {'start': 5, 'end': 8, 'truth': 'P'},
        {'start': 8, 'end': 11, 'truth': 'P'},
        {'start': 11, 'end': 20, 'truth': 'P'},
    ]
    assert prep.reserve_enrollment(words) == [{'start': 5, 'end': 11, 'truth': 'P'}]


def test_manifest_exact_name_matching_and_private_enrollment(tmp_path):
    archive = tmp_path / 'archive'
    (archive / 'build').mkdir(parents=True)
    labels = ['You', 'You', 'Person', 'Person', 'Unknown', 'Unknown']
    words = [{'s': i * 3, 'e': (i + 1) * 3, 'w': 'fiction'} for i in range(6)]
    (archive / 'build' / 'truth.json').write_text(json.dumps({'fiction': labels}))
    (archive / 'build' / 'conv_fiction.json').write_text(json.dumps({'t0': 77, 'dur': 18, 'words': words}))
    audio = tmp_path / 'audio'
    audio.mkdir()
    (audio / 'source-fiction.wav').write_bytes(b'synthetic')
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'profile.json').write_text(json.dumps({'speaker_embedding': [1, 0]}))
    (snapshot / 'people.json').write_text(
        json.dumps(
            [
                {
                    'id': 'p1',
                    'name': 'person',
                    'speaker_embedding': [1, 0],
                    'speech_samples': ['fiction'],
                    'speech_samples_version': 3,
                },
                {
                    'id': 'p2',
                    'name': 'Unknown',
                    'speaker_embedding': [0, 1],
                    'speech_samples': ['fiction'],
                    'speech_samples_version': 3,
                    'is_dismissed': True,
                },
            ]
        )
    )
    result = prep.create_manifest(archive, [audio], snapshot, tmp_path / 'private' / 'corpus.json')
    recording = result['recordings'][0]
    assert recording['identity_table'] == {'You': {'is_user': True}, 'Person': {'person_id': 'p1'}}
    assert len(recording['enrollment_spans']) == 3
    assert len(recording['words']) == 6  # The main denominator is never silently reduced.
    assert recording['t0'] == 77
