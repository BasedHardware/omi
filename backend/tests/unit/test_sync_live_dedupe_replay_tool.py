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


def test_proven_reworded_repeats_drop_and_new_speech_is_kept_at_both_skews(tmp_path):
    for skew in (40, 1200):
        sync = with_ids(
            [sync_segment(reworded(LIVE[i]), skew + i * 10.0) for i in range(7)]
            + [sync_segment(text, skew + 70.0 + i * 10.0) for i, text in enumerate(NEW)]
        )
        payload = {'live_segments': live_segments(), 'sync_segments': sync, **proof(sync)}
        result = run_replay(tmp_path, payload)
        assert result.returncode == 0, result.stderr
        out = decisions(result)
        assert [row['decision'] for row in out['segments']] == ['dropped'] * 7 + ['kept'] * 3
        assert all(row['reason'] == 'lexical_repeat:source_frame_lexical' for row in out['segments'][:7])
        assert out['totals'] == {
            'kept_segments': 3,
            'dropped_segments': 7,
            'kept_seconds': 30.0,
            'dropped_seconds': 70.0,
        }


def test_correction_prefixed_segment_is_kept_even_with_proof(tmp_path):
    sync = with_ids([sync_segment('Actually ' + LIVE[0], 40.0)])
    payload = {'live_segments': live_segments(), 'sync_segments': sync, **proof(sync)}
    result = run_replay(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert out['segments'][0]['decision'] == 'kept'
    assert out['totals']['kept_seconds'] == 10.0


def test_proven_exact_text_same_range_drops_novel_text_same_range_keeps(tmp_path):
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
        'decision': 'dropped',
        'reason': 'exact_retry',
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
        'reason': 'exact_retry',
    }


def test_oversized_incoming_abstains_and_keeps_everything(tmp_path):
    sync = with_ids([sync_segment(reworded(LIVE[i % 7]), i * 10.0 + 40) for i in range(65)])
    result = run_replay(tmp_path, {'live_segments': live_segments(), 'sync_segments': sync, **proof(sync[:64])})
    assert result.returncode == 0, result.stderr
    out = decisions(result)
    assert [row['decision'] for row in out['segments']] == ['kept'] * 65
    assert out['totals']['dropped_segments'] == 0 and out['totals']['kept_segments'] == 65


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
    assert [row['decision'] for row in out['segments']] == ['dropped', 'kept']
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
