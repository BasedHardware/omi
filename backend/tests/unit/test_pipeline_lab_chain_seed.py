"""Pipeline lab, lane chain: snapshot -> start state (cut, strip, remap) and seed guards."""

from datetime import datetime, timezone
import json

import pytest

from testing.pipeline_lab.seed.snapshot import SnapshotError, SnapshotReader
from testing.pipeline_lab.seed.start_state import (
    SYNTHETIC_FCM_TOKEN,
    SourceUidError,
    assert_no_source_uid,
    build_start_state,
    detect_source_uid,
)
from testing.pipeline_lab.seed.synthetic import SYNTHETIC_SOURCE_UID, write_synthetic_snapshot
from testing.pipeline_lab.seed.writer import (
    RecordingSeedWriter,
    SeedTargetRefused,
    assert_lab_target,
    reset_lab_user,
    restore_times,
    seed_start_state,
)
from testing.pipeline_lab.stack import LAB_UID

DAY = '2026-03-14'
DAY_START = datetime(2026, 3, 14, tzinfo=timezone.utc)
LAB_ENV = {'FIRESTORE_EMULATOR_HOST': '127.0.0.1:8085', 'GOOGLE_CLOUD_PROJECT': 'demo-omi-local'}


@pytest.fixture
def snapshot(tmp_path):
    return SnapshotReader(write_synthetic_snapshot(tmp_path / 'snap', day=DAY, prior_days=2, per_day=3))


def test_reader_requires_a_manifest(tmp_path):
    with pytest.raises(SnapshotError):
        SnapshotReader(tmp_path)


def test_start_state_cuts_rows_at_or_after_day_start(snapshot):
    state = build_start_state(snapshot, DAY_START, day_date=DAY)
    report = state.report
    assert report.kept['conversations'] == 6 and report.cut['conversations'] == 3
    assert report.kept['memories'] == 6 and report.cut['memories'] == 3
    assert report.kept['action_items'] == 6
    # One person was created mid-day; the day's own summary is cut by date.
    assert report.kept['people'] == 1 and report.cut['people'] == 1
    assert sorted(s['date'] for s in state.daily_summaries) == ['2026-03-12', '2026-03-13']
    assert all(datetime.fromisoformat(c['created_at']) < DAY_START for c in state.conversations)
    assert report.start_state == 'approximate'


def test_start_state_strips_llm_hashes_and_byte_markers(snapshot):
    state = build_start_state(snapshot, DAY_START, day_date=DAY)
    for row in state.conversations + state.memories:
        assert not any(key.endswith(('_llm_input_hash', '_llm_output_hash')) for key in row)
        assert 'speaker_embedding' not in row
    assert state.report.hashes_stripped == 6 * 3 + 6
    assert state.report.byte_fields_dropped == 6


def test_start_state_remaps_the_source_uid_everywhere(snapshot):
    state = build_start_state(snapshot, DAY_START, day_date=DAY)
    assert_no_source_uid(state, SYNTHETIC_SOURCE_UID)
    assert all(row['uid'] == LAB_UID for row in state.conversations + state.memories + state.action_items)
    assert state.conversations[0]['external_data']['owner_ref'].startswith(f'users/{LAB_UID}/')
    assert state.profile['uid'] == LAB_UID
    assert state.report.uid_replacements > 0
    assert state.fcm_token == {
        'device_key': 'pipeline-lab-device',
        'fcm_token': SYNTHETIC_FCM_TOKEN,
        'time_zone': 'UTC',
    }


def test_source_uid_detection_is_strict():
    uids = [{'uid': 'abcdef123'}, {'uid': 'abcdef123'}, {}]  # pragma: allowlist secret
    assert detect_source_uid(uids, 'abcdef') == 'abcdef123'  # pragma: allowlist secret
    with pytest.raises(SourceUidError):
        detect_source_uid([{'uid': 'abcdef123'}, {'uid': 'zzzzzz999'}], None)  # pragma: allowlist secret
    with pytest.raises(SourceUidError):
        detect_source_uid([{'uid': 'abcdef123'}], 'qqqqqq')  # pragma: allowlist secret
    with pytest.raises(SourceUidError):
        detect_source_uid([{}], None)


def test_explicit_short_source_uid_is_refused(snapshot):
    with pytest.raises(SourceUidError):
        build_start_state(snapshot, DAY_START, day_date=DAY, source_uid='abc')
    with pytest.raises(ValueError):
        build_start_state(snapshot, datetime(2026, 3, 14), day_date=DAY)


def test_recording_writer_and_seed_report(snapshot):
    state = build_start_state(snapshot, DAY_START, day_date=DAY)
    writer = RecordingSeedWriter()
    report = seed_start_state(state, writer, reset=lambda: 7)
    assert report['reset_deleted'] == 7
    assert report['written']['conversations'] == 6 and report['written']['fcm_tokens'] == 1
    json.dumps(report)  # serializable for run.json


def test_restore_times_is_field_aware():
    row = restore_times(
        {
            'created_at': '2026-03-13T09:00:00+00:00',
            'title': '2026-03-13T09:00:00',
            'nested': [{'due_at': '2026-03-15T00:00:00Z'}],
        }
    )
    assert isinstance(row['created_at'], datetime)
    assert row['title'] == '2026-03-13T09:00:00'
    assert row['nested'][0]['due_at'] == datetime(2026, 3, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'uid,env,project',
    [
        ('someone-real', LAB_ENV, 'demo-omi-local'),
        (LAB_UID, {**LAB_ENV, 'FIRESTORE_EMULATOR_HOST': 'firestore.googleapis.com:443'}, 'demo-omi-local'),
        (LAB_UID, {'GOOGLE_CLOUD_PROJECT': 'demo-omi-local'}, 'demo-omi-local'),
        (LAB_UID, LAB_ENV, 'based-hardware'),
    ],
)
def test_lab_target_guard_refuses_anything_but_the_lab_user_on_an_emulator(uid, env, project):
    with pytest.raises(SeedTargetRefused):
        assert_lab_target(uid, environ=env, project=project)


class _Doc:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.reference = self
        self.id = path[-1]

    def collections(self):
        names = {
            p[len(self.path)] for p in self.store if len(p) > len(self.path) + 1 and p[: len(self.path)] == self.path
        }
        return [_Collection(self.store, self.path + (name,)) for name in sorted(names)]

    def delete(self):
        self.store.discard(self.path)


class _Collection:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self._limit = None

    def document(self, name):
        return _Doc(self.store, self.path + (name,))

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        docs = sorted(
            {
                p[: len(self.path) + 1]
                for p in self.store
                if p[: len(self.path)] == self.path and len(p) > len(self.path)
            }
        )
        return [_Doc(self.store, d) for d in docs[: self._limit]]


class _Client:
    project = 'demo-omi-local'

    def __init__(self, paths):
        self.store = set(paths)

    def collection(self, name):
        return _Collection(self.store, (name,))


def test_reset_deletes_only_the_lab_user_tree():
    client = _Client(
        {
            ('users', LAB_UID),
            ('users', LAB_UID, 'conversations', 'c1'),
            ('users', LAB_UID, 'conversations', 'c1', 'photos', 'p1'),
            ('users', LAB_UID, 'memories', 'm1'),
            ('users', 'other-user', 'conversations', 'c9'),
        }
    )
    deleted = reset_lab_user(client, environ=LAB_ENV)
    assert deleted == 4
    assert client.store == {('users', 'other-user', 'conversations', 'c9')}
    with pytest.raises(SeedTargetRefused):
        reset_lab_user(client, 'other-user', environ=LAB_ENV)
    assert client.store == {('users', 'other-user', 'conversations', 'c9')}
