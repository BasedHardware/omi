import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from config.conversation_smart_merge import QUESTION_VERSION
from scripts import smart_merge_overlap_replay as replay_tool
from utils.conversations.smart_merge_policy import fragment_of
from utils.conversations.smart_merge_state import build_state, state_sha256

T0 = datetime(2026, 10, 5, tzinfo=timezone.utc)
SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'smart_merge_overlap_replay.py'


def card(cid, start, end, **extra):
    return {
        'id': cid,
        'source': 'omi',
        'client_device_id': 'synthetic-device',
        'created_at': (T0 + timedelta(minutes=start)).isoformat(),
        'started_at': (T0 + timedelta(minutes=start)).isoformat(),
        'finished_at': (T0 + timedelta(minutes=end)).isoformat(),
        'status': 'completed',
        'discarded': False,
        'structured': {'title': cid, 'overview': 'synthetic overview'},
        'transcript_segments': [{'start': 0.0, 'end': (end - start) * 60.0, 'text': ' '.join(['synthetic'] * 30)}],
        **extra,
    }


def fixture():
    return {
        'schema_version': 1,
        'timezone': 'UTC',
        'conversations': [
            card('p', 0, 5),
            card('duplicate', 7, 16, sync_live_target=False, sync_content_revision=1),
            card('n', 10, 15),
        ],
        'evaluations': [
            {
                'conversation_id': 'n',
                'preceding_ids': ['duplicate', 'p'],
                'capture_end': True,
                'uid_allowed': True,
                'mode': 'merge',
            }
        ],
    }


def scored(payload, p_same):
    p = replay_tool._decode(payload['conversations'][0])
    n = replay_tool._decode(payload['conversations'][2])
    state = build_state(
        source='omi',
        a=fragment_of(p),
        a_segments=p['transcript_segments'],
        b=fragment_of(n),
        b_segments=n['transcript_segments'],
        stretch=[],
        tz=ZoneInfo('UTC'),
    )
    payload['evaluations'][0]['scores'] = [
        {
            'candidate_id': 'p',
            'question_version': QUESTION_VERSION,
            'state_sha256': state_sha256(state),
            'p_same': p_same,
        }
    ]
    return payload


def test_local_snapshot_reports_changed_candidate_without_inventing_a_score():
    payload = fixture()
    before = copy.deepcopy(payload)
    row = replay_tool.replay(payload)[0]
    assert row['old']['predecessor'] == 'duplicate'
    assert row['old']['reason'] == 'gap_out_of_window'
    assert row['new']['predecessor'] == 'p'
    assert row['new']['predecessor_skipped_overlap'] == 1
    assert row['new']['decision'] == 'indeterminate'
    assert row['new']['reason'] == 'score_missing'
    assert payload == before


@pytest.mark.parametrize(
    'score,decision,reason',
    [(0.34, 'kept', 'jev_different'), (0.35, 'would_merge', 'jev_same'), (None, 'kept', 'jev_unavailable')],
)
def test_exported_score_requires_exact_pair_and_state(score, decision, reason):
    payload = scored(fixture(), score)
    row = replay_tool.replay(payload)[0]['new']
    assert (row['decision'], row['reason']) == (decision, reason)
    for key in ('candidate_id', 'state_sha256', 'question_version'):
        altered = copy.deepcopy(payload)
        altered['evaluations'][0]['scores'][0][key] = 'not-the-evaluated-input'
        assert replay_tool.replay(altered)[0]['new']['reason'] == 'score_missing'


def test_replay_stretch_ignores_the_skipped_duplicate():
    payload = fixture()
    payload['conversations'][1]['started_at'] = (T0 - timedelta(minutes=1)).isoformat()
    row = replay_tool.replay(scored(payload, 0.35))[0]['new']
    assert row['predecessor'] == 'p'
    assert row['stretch_count'] == 0
    assert row['decision'] == 'would_merge'


def test_pending_refresh_is_not_a_predicted_merge():
    payload = scored(fixture(), 0.9)
    payload['conversations'][0]['smart_merge'] = {'role': 'survivor', 'revision': 2, 'refreshed_revision': 1}
    assert replay_tool.replay(payload)[0]['new']['reason'] == 'refresh_required'
    payload['evaluations'][0]['mode'] = 'shadow'
    assert replay_tool.replay(payload)[0]['new']['reason'] == 'predecessor_refresh_pending'


def test_sticky_score_is_reused_only_for_matching_predecessor():
    payload = fixture()
    payload['conversations'][2]['smart_merge_decision'] = {
        'candidate_id': 'duplicate',
        'question_version': QUESTION_VERSION,
        'p_same': 1.0,
    }
    assert replay_tool.replay(payload)[0]['new']['reason'] == 'score_missing'
    payload['conversations'][2]['smart_merge_decision']['candidate_id'] = 'p'
    assert replay_tool.replay(payload)[0]['new']['decision'] == 'would_merge'


def test_same_capture_does_not_change_the_replay():
    payload = fixture()
    payload['conversations'][1].pop('sync_content_revision')
    payload['conversations'][1].pop('sync_live_target')
    row = replay_tool.replay(payload)[0]
    assert row['old'] == row['new']


def test_user_admission_input_is_honored_before_selection():
    payload = fixture()
    payload['evaluations'][0]['uid_allowed'] = False
    row = replay_tool.replay(payload)[0]
    assert row['old'] == row['new']
    assert row['new']['reason'] == 'uid_not_allowed'
    assert row['new']['predecessor'] is None


@pytest.mark.parametrize('bad', ['order', 'naive_time', 'duplicate_ids', 'missing_transcript'])
def test_invalid_exports_fail_instead_of_reporting_plausible_decisions(bad):
    payload = fixture()
    if bad == 'order':
        payload['evaluations'][0]['preceding_ids'].reverse()
    elif bad == 'naive_time':
        payload['conversations'][0]['started_at'] = '2026-10-05T00:00:00'
    elif bad == 'duplicate_ids':
        payload['evaluations'][0]['preceding_ids'] = ['p', 'p']
    else:
        payload['conversations'][0].pop('transcript_segments')
    with pytest.raises(ValueError):
        replay_tool.replay(payload)


def test_cli_is_stdlib_only_and_has_no_service_imports(tmp_path):
    export = tmp_path / 'synthetic.json'
    export.write_text(json.dumps(scored(fixture(), 0.35)), encoding='utf-8')
    command = [sys.executable, '-I', '-S', str(SCRIPT), str(export)]
    completed = subprocess.run(
        command,
        cwd=tmp_path,
        env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent'},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)['new']['decision'] == 'would_merge'
    export.write_text('{"sensitive-synthetic-input": "not a valid export"}', encoding='utf-8')
    invalid = subprocess.run(
        command,
        cwd=tmp_path,
        env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent'},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert invalid.returncode == 2
    assert invalid.stdout == ''
    assert 'sensitive-synthetic-input' not in invalid.stderr
    assert str(export) not in invalid.stderr
