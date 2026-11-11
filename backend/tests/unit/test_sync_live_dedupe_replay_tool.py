"""Hermetic coverage for the offline live-dedupe replay tool.

The script runs as a bare ``python -I`` subprocess from a non-repo cwd with a
hostile provider environment: it must decide purely on local inputs, load no
Firebase/Firestore/provider modules, and fail malformed input with exit 2 and
no transcript, path or identifier leakage. All text is synthetic.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'sync_live_dedupe_replay.py'

LIVE = [
    'the quarterly planning review meeting covered agenda item one in detail',
    'the quarterly planning review meeting covered agenda item two in detail',
    'the quarterly planning review meeting covered agenda item three in detail',
    'the quarterly planning review meeting covered agenda item four in detail',
    'the quarterly planning review meeting covered agenda item five in detail',
    'the quarterly planning review meeting covered agenda item six in detail',
    'the quarterly planning review meeting covered agenda item seven in detail',
]

NEW = [
    'a genuinely new remark about weekend hiking plans with close friends',
    'the dog barked twice at the delivery driver near the front gate',
    'dinner reservations moved to eight thirty at the corner bistro tonight',
]

HOSTILE_ENV = {
    'GOOGLE_APPLICATION_CREDENTIALS': '/nonexistent/service-account.json',
    'SERVICE_ACCOUNT_JSON': '{"bogus": true}',
    'FIREBASE_CONFIG': '{"projectId": "bogus"}',
    'GCLOUD_PROJECT': 'bogus-project',
    'OPENAI_API_KEY': 'bogus-openai-key',
    'DEEPGRAM_API_KEY': 'bogus-deepgram-key',
    'REDIS_DB_HOST': '10.255.255.1',
    'HOME': '/nonexistent-home',
    'PATH': '/usr/bin:/bin',
}


def reworded(text):
    words = [token for token in text.replace('the ', '').split(' ') if token]
    return 'Um, ' + ' '.join(words).capitalize() + '!'


PROOF_ROOT = 'a1b2c3d4-1111-4222-8333-444455556666'
PROOF_SPF = 160
PROOF_FRAMES = 100000
AUDIO_ROOT = '00000000-0000-4000-8000-000000000001'


def live_segments(**per_segment):
    return [dict({'start': i * 10.0, 'end': i * 10.0 + 10.0, 'text': LIVE[i]}, **per_segment) for i in range(7)]


def sync_segment(text, start, duration=10.0, **extra):
    return dict({'start': start, 'end': start + duration, 'text': text}, **extra)


def with_ids(sync, prefix='s'):
    return [dict(row, id=row.get('id') or f'{prefix}{i}') for i, row in enumerate(sync)]


def proof(sync, frames=PROOF_FRAMES):
    """Paired sync_vad receipts plus a live run covering every receipted frame."""
    return {
        'sync_capture_evidence': {
            'version': 1,
            'capability': 'source_position',
            'coverage': 'mapped',
            'origin': 'sync_vad',
            'receipts': [
                {
                    'segment_id': row['id'],
                    'capture_root': PROOF_ROOT,
                    'clock_epoch': 7,
                    'channel': 'mono',
                    'source_start_frame': i * 1000,
                    'source_start_offset': 0,
                    'source_end_frame': i * 1000 + 999,
                    'source_end_offset': 0,
                    'rate_hz': 16000,
                    'producer_revision': 'sync_vad_stt_v1',
                }
                for i, row in enumerate(sync)
            ],
        },
        'live_capture_evidence': {
            'version': 1,
            'capability': 'source_position',
            'coverage': 'mapped',
            'origin': 'live',
            'conflicts': 0,
            'runs': [
                {
                    'capture_root': PROOF_ROOT,
                    'clock_epoch': 7,
                    'rate_hz': 16000,
                    'channel': 'mono',
                    'source_frame_start': 0,
                    'source_frame_end': frames,
                    'decoded_sample_start': 0,
                    'decoded_sample_end': frames * PROOF_SPF,
                    'samples_per_frame': PROOF_SPF,
                }
            ],
        },
    }


def audio_coverage(frame_samples, runs, **run_over):
    return {
        'live_received_ranges': (
            [
                dict(
                    {
                        'version': 1,
                        'capability': 'source_position',
                        'coverage': 'mapped',
                        'origin': 'live',
                        'conflicts': 0,
                    },
                    **run_over,
                )
            ]
            if runs is None
            else [
                dict(
                    {
                        'version': 1,
                        'capability': 'source_position',
                        'coverage': 'mapped',
                        'origin': 'live',
                        'conflicts': 0,
                        'runs': [
                            dict(
                                {
                                    'capture_root': AUDIO_ROOT,
                                    'clock_epoch': 0,
                                    'rate_hz': 16000,
                                    'channel': 'mono',
                                },
                                **run,
                            )
                            for run in runs
                        ],
                    },
                    **run_over,
                )
            ]
        ),
        'wal_frames': [
            {
                'capture_root': AUDIO_ROOT,
                'clock_epoch': 0,
                'source_frame_start': 0,
                'rate_hz': 16000,
                'channel': 'mono',
                'codec': 'pcm16',
                'frame_samples': frame_samples,
            }
        ],
    }


def run_replay(tmp_path, payload, extra_args=()):
    input_path = tmp_path / 'input.json'
    input_path.write_text(json.dumps(payload), encoding='utf-8')
    return subprocess.run(
        [sys.executable, '-I', str(SCRIPT), *extra_args, str(input_path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=dict(HOSTILE_ENV),
        timeout=60,
    )


def decisions(result):
    return json.loads(result.stdout)


def test_unproven_identical_and_reworded_repeats_are_kept(tmp_path):
    """Without paired capture evidence even identical wording keeps — no signal."""
    sync = [sync_segment(LIVE[0], 0.0), sync_segment(reworded(LIVE[1]), 10.0)]
    result = run_replay(tmp_path, {'live_segments': live_segments(), 'sync_segments': sync})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept', 'kept']
    assert out['totals'] == {'kept_segments': 2, 'dropped_segments': 0, 'kept_seconds': 20.0, 'dropped_seconds': 0.0}


def test_receipt_only_repeats_and_new_speech_are_all_kept_at_both_skews(tmp_path):
    for skew in (40, 1200):
        sync = with_ids(
            [sync_segment(reworded(LIVE[i]), skew + i * 10.0) for i in range(7)]
            + [sync_segment(text, skew + 70.0 + i * 10.0) for i, text in enumerate(NEW)]
        )
        payload = {
            'live_segments': live_segments(),
            'sync_segments': sync,
            'intake_sizes': [2, 3, 5],
            **proof(sync),
        }
        result = run_replay(tmp_path, payload)
        assert result.returncode == 0, result.stderr
        out = decisions(result)
        assert [row['decision'] for row in out['segments']] == ['kept'] * 10
        assert all(row['reason'] == 'not_proven_same_capture' for row in out['segments'])
        assert all(row['partial_audio'] is False for row in out['segments'])
        assert [intake['segment_count'] for intake in out['intakes']] == [2, 3, 5]
        assert out['totals'] == {
            'kept_segments': 10,
            'dropped_segments': 0,
            'kept_seconds': 100.0,
            'dropped_seconds': 0.0,
        }


def test_correction_prefixed_segment_is_kept_even_with_proof(tmp_path):
    sync = with_ids([sync_segment('Actually ' + LIVE[0], 40.0)])
    payload = {'live_segments': live_segments(), 'sync_segments': sync, **proof(sync)}
    result = run_replay(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['segments'][0]['decision'] == 'kept'
    assert out['totals']['kept_seconds'] == 10.0


def test_receipt_only_exact_text_same_range_is_kept(tmp_path):
    live = live_segments() + [{'start': 70.0, 'end': 73.0, 'text': 'okay see you'}]
    sync = with_ids(
        [
            sync_segment('okay see you', 70.0, duration=3.0),
            sync_segment(NEW[0], 70.0, duration=3.0),
        ]
    )
    result = run_replay(tmp_path, {'live_segments': live, 'sync_segments': sync, **proof(sync)})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['segments'][0] == {
        'index': 0,
        'start': 70.0,
        'end': 73.0,
        'decision': 'kept',
        'reason': 'not_proven_same_capture',
        'partial_audio': False,
    }
    assert out['segments'][1]['decision'] == 'kept'


def test_unproven_exact_text_same_range_is_kept(tmp_path):
    live = live_segments() + [{'start': 70.0, 'end': 73.0, 'text': 'okay see you'}]
    sync = [sync_segment('okay see you', 70.0, duration=3.0)]
    result = run_replay(tmp_path, {'live_segments': live, 'sync_segments': sync})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['segments'][0]['decision'] == 'kept'


def test_sync_scoped_live_lines_skip_lexical_but_still_exact_retry(tmp_path):
    live = live_segments(speaker_id_scope='sync:WAL-9')
    sync = [
        sync_segment(reworded(LIVE[0]), 0.0, speaker_id_scope='sync:WAL-9'),
        sync_segment(LIVE[1], 10.0, speaker_id_scope='sync:WAL-9'),
    ]
    result = run_replay(tmp_path, {'live_segments': live, 'sync_segments': sync})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['segments'][0]['decision'] == 'kept'
    assert out['segments'][1] == {
        'index': 1,
        'start': 10.0,
        'end': 20.0,
        'decision': 'dropped',
        'reason': 'exact_sync_retry',
        'partial_audio': False,
    }


def test_receipt_only_oversized_upload_keeps_everything(tmp_path):
    sync = with_ids([sync_segment(reworded(LIVE[i % 7]), i * 10.0 + 40) for i in range(65)])
    result = run_replay(tmp_path, {'live_segments': live_segments(), 'sync_segments': sync, **proof(sync[:64])})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept'] * 65
    assert all(row['reason'] == 'not_proven_same_capture' for row in out['segments'])
    sizes = [intake['segment_count'] for intake in out['intakes']]
    assert all(2 <= size <= 5 for size in sizes) and sum(sizes) == 65


@pytest.mark.parametrize('count', [65, 100])
def test_unproven_large_uploads_keep_everything(tmp_path, count):
    sync = with_ids([sync_segment(reworded(LIVE[i % 7]), i * 10.0 + 40) for i in range(count)])
    result = run_replay(tmp_path, {'live_segments': live_segments(), 'sync_segments': sync})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept'] * count
    assert out['totals']['dropped_segments'] == 0 and out['totals']['kept_segments'] == count


def test_cross_intake_same_scope_exact_retry_is_idempotent(tmp_path):
    sync = with_ids(
        [
            sync_segment('hello world sync line', 0.0, speaker_id_scope='sync:WAL-9'),
            sync_segment('different second utterance here', 10.0, speaker_id_scope='sync:WAL-9'),
            sync_segment('hello world sync line', 0.0, speaker_id_scope='sync:WAL-9'),
            sync_segment('tail filler', 30.0, speaker_id_scope='sync:WAL-9'),
        ],
        prefix='x',
    )
    result = run_replay(tmp_path, {'live_segments': [], 'sync_segments': sync, 'intake_sizes': [2]})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [intake['segment_count'] for intake in out['intakes']] == [2, 2]
    assert [row['decision'] for row in out['segments']] == ['kept', 'kept', 'dropped', 'kept']
    assert out['segments'][2]['reason'] == 'exact_sync_retry'


def test_retained_unscoped_utterances_never_become_live_lexical_windows(tmp_path):
    """One intake: a kept unscoped segment must not open a live lexical window."""
    sync = with_ids(
        [
            sync_segment('a genuinely new remark about weekend hiking plans', 0.0),
            sync_segment('Um, a genuinely new remark about weekend hiking plans!', 10.0),
        ]
    )
    payload = {
        'live_segments': [],
        'sync_segments': sync,
        'intake_sizes': [2],
        **proof([sync[1]]),
    }
    result = run_replay(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept', 'kept']
    assert out['segments'][1]['reason'] == 'not_proven_same_capture'


def test_unscoped_exact_repeats_across_intakes_get_fresh_scopes_and_stay_kept(tmp_path):
    """Identical unscoped text/range in a later intake is ordinary repetition, not a retry."""
    sync = with_ids(
        [
            sync_segment('same spoken line again', 0.0),
            sync_segment('same spoken line again', 0.0),
            sync_segment('same spoken line again', 0.0),
            sync_segment('same spoken line again', 0.0),
        ]
    )
    payload = {
        'live_segments': [],
        'sync_segments': sync,
        'intake_sizes': [2],
        **proof(sync),
    }
    result = run_replay(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept', 'kept', 'kept', 'kept']
    assert [row['segment_count'] for row in out['intakes']] == [2, 2]


@pytest.mark.parametrize('skew', [40.0, 1200.0])
def test_receipt_only_frames_keep_audio_candidates_and_the_whole_wal(tmp_path, skew):
    sync = [
        sync_segment(
            f'w{i}',
            skew + i * 0.5,
            duration=0.5,
            wal_index=0,
            source_frame_start=i,
            source_frame_end=i + 1,
        )
        for i in range(10)
    ]
    coverage = audio_coverage(
        [8000] * 10,
        [
            {
                'source_frame_start': 0,
                'source_frame_end': 7,
                'decoded_sample_start': 0,
                'decoded_sample_end': 56000,
                'samples_per_frame': 8000,
            }
        ],
    )
    result = run_replay(
        tmp_path,
        {'live_segments': [], 'sync_segments': sync, 'intake_sizes': [2, 3, 5], 'audio_coverage': coverage},
    )
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept'] * 10
    assert [row['reason'] for row in out['segments']] == ['not_proven_same_capture'] * 10
    assert all(row['partial_audio'] is False for row in out['segments'])
    assert out['audio_coverage'] == {
        'files': [
            {
                'wal_index': 0,
                'decision': 'kept',
                'kept_frame_ranges': [[0, 10]],
                'kept_seconds': 5.0,
                'dropped_seconds': 0.0,
                'context_seconds': 0.0,
            }
        ],
        'totals': {'kept_seconds': 5.0, 'dropped_seconds': 0.0, 'context_seconds': 0.0},
    }


@pytest.mark.parametrize('declared', [10, 12])
def test_declared_wal_frame_count_at_or_above_decoded_keeps_the_plan(tmp_path, declared):
    """A declared frame_count at or above the decoded prefix leaves the plan unchanged."""
    coverage = audio_coverage(
        [8000] * 10,
        [
            {
                'source_frame_start': 0,
                'source_frame_end': 7,
                'decoded_sample_start': 0,
                'decoded_sample_end': 56000,
                'samples_per_frame': 8000,
            }
        ],
    )
    coverage['wal_frames'][0]['frame_count'] = declared
    result = run_replay(tmp_path, {'live_segments': [], 'sync_segments': [], 'audio_coverage': coverage})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['audio_coverage']['files'][0]['kept_frame_ranges'] == [[0, 10]]
    assert out['audio_coverage']['totals'] == {'kept_seconds': 5.0, 'dropped_seconds': 0.0, 'context_seconds': 0.0}


@pytest.mark.parametrize('declared', [9, 0, True])
def test_declared_wal_frame_count_below_decoded_or_invalid_exits_2(tmp_path, declared):
    coverage = audio_coverage(
        [8000] * 10,
        [
            {
                'source_frame_start': 0,
                'source_frame_end': 7,
                'decoded_sample_start': 0,
                'decoded_sample_end': 56000,
                'samples_per_frame': 8000,
            }
        ],
    )
    coverage['wal_frames'][0]['frame_count'] = declared
    payload = {
        'live_segments': [],
        'sync_segments': [sync_segment('private declared-count leak text', 0.0)],
        'audio_coverage': coverage,
    }
    result = run_replay(tmp_path, payload)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert 'private declared-count leak text' not in result.stdout
    assert 'private declared-count leak text' not in result.stderr
    assert 'input.json' not in result.stdout and 'input.json' not in result.stderr


def test_receipt_only_hole_retains_the_whole_wal(tmp_path):
    coverage = audio_coverage(
        [8000] * 10,
        [
            {
                'source_frame_start': 3,
                'source_frame_end': 7,
                'decoded_sample_start': 24000,
                'decoded_sample_end': 56000,
                'samples_per_frame': 8000,
            }
        ],
    )
    result = run_replay(tmp_path, {'live_segments': [], 'sync_segments': [], 'audio_coverage': coverage})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['audio_coverage'] == {
        'files': [
            {
                'wal_index': 0,
                'decision': 'kept',
                'kept_frame_ranges': [[0, 10]],
                'kept_seconds': 5.0,
                'dropped_seconds': 0.0,
                'context_seconds': 0.0,
            }
        ],
        'totals': {'kept_seconds': 5.0, 'dropped_seconds': 0.0, 'context_seconds': 0.0},
    }


def test_fully_receipted_wal_still_retains_everything(tmp_path):
    coverage = audio_coverage(
        [8000] * 10,
        [
            {
                'source_frame_start': 0,
                'source_frame_end': 10,
                'decoded_sample_start': 0,
                'decoded_sample_end': 80000,
                'samples_per_frame': 8000,
            }
        ],
    )
    result = run_replay(tmp_path, {'live_segments': [], 'sync_segments': [], 'audio_coverage': coverage})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['audio_coverage']['files'][0]['decision'] == 'kept'
    assert out['audio_coverage']['files'][0]['kept_frame_ranges'] == [[0, 10]]


@pytest.mark.parametrize(
    ('runs_over', 'expected'),
    [
        ({'runs': None}, 'kept'),
        ({'runs': [{'capture_root': 'a1b2c3d4-1111-4222-8333-444455556666'}]}, 'kept'),
        ({'conflicts': 1}, 'abstained'),
    ],
    ids=['no_matching_envelope', 'other_capture_root', 'conflicting_evidence'],
)
def test_missing_or_conflicting_evidence_retains_all(tmp_path, runs_over, expected):
    run = {
        'capture_root': AUDIO_ROOT,
        'clock_epoch': 0,
        'rate_hz': 16000,
        'channel': 'mono',
        'source_frame_start': 0,
        'source_frame_end': 7,
        'decoded_sample_start': 0,
        'decoded_sample_end': 56000,
        'samples_per_frame': 8000,
    }
    envelope = dict(
        {
            'version': 1,
            'capability': 'source_position',
            'coverage': 'mapped',
            'origin': 'live',
            'conflicts': 0,
            'runs': [run],
        },
        **runs_over,
    )
    coverage = {
        'live_received_ranges': [envelope],
        'wal_frames': [
            {
                'capture_root': AUDIO_ROOT,
                'clock_epoch': 0,
                'source_frame_start': 0,
                'rate_hz': 16000,
                'channel': 'mono',
                'codec': 'pcm16',
                'frame_samples': [8000] * 10,
            }
        ],
    }
    result = run_replay(tmp_path, {'live_segments': [], 'sync_segments': [], 'audio_coverage': coverage})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['audio_coverage']['files'][0]['decision'] == expected
    assert out['audio_coverage']['files'][0]['kept_frame_ranges'] == [[0, 10]]
    assert out['audio_coverage']['totals'] == {'kept_seconds': 5.0, 'dropped_seconds': 0.0, 'context_seconds': 0.0}


def test_receipt_only_coverage_never_marks_a_straddling_segment_partial(tmp_path):
    sync = [
        sync_segment(
            'a straddling utterance',
            40.0,
            duration=0.3,
            wal_index=0,
            source_frame_start=40,
            source_frame_end=70,
        )
    ]
    coverage = audio_coverage(
        [160] * 100,
        [
            {
                'source_frame_start': 0,
                'source_frame_end': 70,
                'decoded_sample_start': 0,
                'decoded_sample_end': 11200,
                'samples_per_frame': 160,
            }
        ],
    )
    result = run_replay(tmp_path, {'live_segments': [], 'sync_segments': sync, 'audio_coverage': coverage})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['audio_coverage'] == {
        'files': [
            {
                'wal_index': 0,
                'decision': 'kept',
                'kept_frame_ranges': [[0, 100]],
                'kept_seconds': 1.0,
                'dropped_seconds': 0.0,
                'context_seconds': 0.0,
            }
        ],
        'totals': {'kept_seconds': 1.0, 'dropped_seconds': 0.0, 'context_seconds': 0.0},
    }
    assert out['segments'][0]['decision'] == 'kept'
    assert out['segments'][0]['reason'] == 'not_proven_same_capture'
    assert out['segments'][0]['partial_audio'] is False


@pytest.mark.parametrize(
    'segment',
    [
        {'wal_index': 0},
        {'wal_index': 0, 'source_frame_start': 0},
        {'wal_index': 1, 'source_frame_start': 0, 'source_frame_end': 1},
        {'wal_index': 0, 'source_frame_start': 9, 'source_frame_end': 11},
        {'wal_index': 0, 'source_frame_start': -1, 'source_frame_end': 1},
        {'wal_index': 0, 'source_frame_start': 2.5, 'source_frame_end': 4},
    ],
)
def test_incomplete_or_out_of_range_capture_coordinates_exit_2(tmp_path, segment):
    coverage = audio_coverage(
        [8000] * 10,
        [
            {
                'source_frame_start': 0,
                'source_frame_end': 7,
                'decoded_sample_start': 0,
                'decoded_sample_end': 56000,
                'samples_per_frame': 8000,
            }
        ],
    )
    payload = {
        'live_segments': [],
        'sync_segments': [sync_segment('leaky transcript text', 0.0, **segment)],
        'audio_coverage': coverage,
    }
    result = run_replay(tmp_path, payload)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert 'leaky transcript text' not in result.stdout and 'leaky transcript text' not in result.stderr


@pytest.fixture(scope='module')
def production_replay():
    """Chargeable test call starts after imports and replay-module load complete."""
    import importlib.util

    from config import sync_lineage, sync_live_dedupe
    from tests.unit import test_sync_lineage_dedupe_replay as helpers
    from tests.unit.test_sync_cross_job_assignment import intake

    spec = importlib.util.spec_from_file_location('replay_tool_under_test', SCRIPT)
    replay_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay_tool)
    return sync_lineage, sync_live_dedupe, helpers, intake, replay_tool


def test_cli_and_production_agree_appended_receipts_replace_live_proof(tmp_path, monkeypatch, production_replay):
    """An append persists sync receipts over the live runs; later intake repeats keep."""
    sync_lineage, live_dedupe, helpers, intake, replay_tool = production_replay
    monkeypatch.setenv(live_dedupe.SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, 'true')
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, raising=False)

    texts = [
        helpers.NEW[0],
        helpers.reworded(helpers.LIVE[0]),
        helpers.reworded(helpers.LIVE[1]),
        helpers.reworded(helpers.LIVE[2]),
    ]
    sync = with_ids([sync_segment(text, 40.0 + i * 10.0) for i, text in enumerate(texts)])
    payload = {
        'live_segments': [
            {'start': i * 10.0, 'end': i * 10.0 + 10.0, 'text': helpers.LIVE[i]} for i in range(len(helpers.LIVE))
        ],
        'sync_segments': sync,
        'intake_sizes': [2],
        **proof(sync),
    }
    cli = replay_tool.replay(payload)
    assert [row['decision'] for row in cli['segments']] == ['kept', 'kept', 'kept', 'kept']
    cli_kept_texts = [texts[i] for i, row in enumerate(cli['segments']) if row['decision'] == 'kept']

    row = helpers.live_row()
    row['capture_evidence'] = helpers.live_evidence()
    receipts = helpers.sync_evidence(['s0', 's1', 's2', 's3'])['receipts']
    store = helpers.seeded_store([row])
    appended = []
    for cursor, scope in ((0, 'sync:replay:0'), (2, 'sync:replay:1')):
        chunk = helpers.wal(40 + 10 * cursor, texts[cursor : cursor + 2])
        for i, segment in enumerate(chunk['transcript_segments']):
            segment['id'] = f's{cursor + i}'
            segment['speaker_id_scope'] = scope
        chunk['capture_evidence'] = dict(helpers.sync_evidence([]), receipts=receipts[cursor : cursor + 2])
        intake(store, chunk, target_id=helpers.LIVE_ID)
    stored = helpers.texts_of(store, helpers.LIVE_ID)
    appended = [text for text in stored if text not in helpers.LIVE]
    assert appended == cli_kept_texts
    persisted = store.rows[('users', 'u', 'conversations', helpers.LIVE_ID)]['capture_evidence']
    assert persisted.get('receipts') and 'runs' not in persisted
    assert cli['totals'] == {'kept_segments': 4, 'dropped_segments': 0, 'kept_seconds': 40.0, 'dropped_seconds': 0.0}


def test_extra_metadata_is_ignored_and_the_input_is_never_mutated(tmp_path):
    sync = with_ids(
        [
            sync_segment(reworded(LIVE[0]), 40.0, speaker='SPEAKER_00', session='meta-1'),
            sync_segment(NEW[0], 50.0, is_user=True),
        ]
    )
    input_path = tmp_path / 'input.json'
    payload = {'live_segments': live_segments(), 'sync_segments': sync, **proof(sync)}
    input_path.write_text(json.dumps(payload), encoding='utf-8')
    raw = input_path.read_bytes()
    result = run_replay(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept', 'kept']
    assert input_path.read_bytes() == raw


def test_empty_arrays_report_zero_totals(tmp_path):
    result = run_replay(tmp_path, {'live_segments': [], 'sync_segments': []})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['segments'] == []
    assert out['totals'] == {'kept_segments': 0, 'dropped_segments': 0, 'kept_seconds': 0, 'dropped_seconds': 0}


MALFORMED_PAYLOADS = [
    {'live_segments': 'not-a-list', 'sync_segments': []},
    {'live_segments': [{'start': 0, 'end': 10, 'text': 'x'}], 'sync_segments': 'nope'},
    {'live_segments': [], 'sync_segments': [{'start': '10:00', 'end': 20, 'text': 'time string'}]},
    {'live_segments': [], 'sync_segments': [{'start': 20, 'end': 10, 'text': 'reversed span'}]},
    {'live_segments': [], 'sync_segments': [{'start': 0, 'end': float('inf'), 'text': 'nonfinite end'}]},
    {'live_segments': [], 'sync_segments': [{'start': 0, 'end': float('nan'), 'text': 'nan end'}]},
    {'live_segments': [], 'sync_segments': [{'start': 0, 'end': 10}]},
    {'live_segments': [], 'sync_segments': [{'start': 0, 'end': 10, 'text': 42}]},
    {'live_segments': [], 'sync_segments': [{'start': 0, 'end': 10, 'text': 'x'}], 'sync_capture_evidence': 'nope'},
    {
        'live_segments': [{'start': 0, 'end': 10, 'text': 'x'}],
        'sync_segments': [
            {'start': 0, 'end': 10, 'text': 'y', 'id': 's0'},
            {'start': 10, 'end': 20, 'text': 'z', 'id': 's1'},
        ],
        'live_capture_evidence': 'not-an-envelope',
        'sync_capture_evidence': {
            'version': 1,
            'capability': 'source_position',
            'coverage': 'mapped',
            'origin': 'sync_vad',
            'receipts': [],
        },
    },
    {'live_segments': [], 'sync_segments': [], 'intake_sizes': []},
    {'live_segments': [], 'sync_segments': [], 'intake_sizes': [True]},
    {'live_segments': [], 'sync_segments': [], 'intake_sizes': [1]},
    {'live_segments': [], 'sync_segments': [], 'intake_sizes': [6]},
    {'live_segments': [], 'sync_segments': [], 'audio_coverage': 'not-an-object'},
    'not an object at all',
]


def test_malformed_inputs_exit_2_without_leaking_content(tmp_path):
    secrets = ('LIVE-ROW', 'WAL-1', 'time string', 'reversed span', 'nonfinite', 'nan end', '/tmp', 'input.json')
    for index, payload in enumerate(MALFORMED_PAYLOADS):
        input_path = tmp_path / f'bad-{index}.json'
        input_path.write_text(json.dumps(payload), encoding='utf-8')
        result = subprocess.run(
            [sys.executable, '-I', str(SCRIPT), str(input_path)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=dict(HOSTILE_ENV),
            timeout=60,
        )
        assert result.returncode == 2, (index, result.stdout, result.stderr)
        for leak in secrets:
            assert leak not in result.stdout and leak not in result.stderr


def test_unreadable_input_exits_2(tmp_path):
    result = subprocess.run(
        [sys.executable, '-I', str(SCRIPT), str(tmp_path / 'missing.json')],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=dict(HOSTILE_ENV),
        timeout=60,
    )
    assert result.returncode == 2
    assert 'missing.json' not in result.stderr


def test_replay_imports_no_provider_or_sdk_modules(tmp_path):
    probe = (
        'import importlib.util, sys; '
        f'spec = importlib.util.spec_from_file_location("replay_tool", r"{SCRIPT}"); '
        'module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); '
        'bad = sorted(name for name in sys.modules if any('
        'token in name for token in ("firebase", "firestore", "google", "redis", "openai", "deepgram"))); '
        'print("\\n".join(bad))'
    )
    result = subprocess.run(
        [sys.executable, '-I', '-c', probe],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=dict(HOSTILE_ENV),
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ''
