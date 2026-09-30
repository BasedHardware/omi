"""Per-environment conversation markers for screen frames.

Dev and prod backends share Firestore. The adjudication stamp and selection
fingerprint decide whether a client offers candidates again, so a marker one
environment wrote must never make the other skip its own pass. Legacy
top-level fields were only ever written by dev.
"""

from datetime import datetime, timezone

from google.cloud import firestore

import database.screen_frames as screen_frames_db
from database.screen_frames import LEGACY_SCREEN_FRAMES_BUCKET, frame_storage_bucket

PROD = 'based-hardware-prod-screen-frames'


class _Snapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _Ref:
    """Just enough of a Firestore document ref: merge-set, Increment, field_paths get."""

    def __init__(self):
        self.data: dict = {}

    def collection(self, _name):
        return self

    def document(self, _name):
        return self

    def set(self, payload, merge=False):
        assert merge

        def apply(target, source):
            for key, value in source.items():
                if isinstance(value, dict):
                    apply(target.setdefault(key, {}), value)
                elif isinstance(value, firestore.Increment):
                    target[key] = int(target.get(key) or 0) + value.value
                else:
                    target[key] = value

        apply(self.data, payload)

    def get(self, field_paths=None, **rpc_bounds):
        self.rpc_bounds = rpc_bounds
        return _Snapshot({key: self.data[key] for key in (field_paths or self.data) if key in self.data})


def _ref(monkeypatch, initial=None):
    ref = _Ref()
    ref.data.update(initial or {})
    monkeypatch.setattr(screen_frames_db, 'db', ref)
    return ref


def test_legacy_docs_belong_to_the_dev_bucket():
    assert LEGACY_SCREEN_FRAMES_BUCKET == 'based-hardware-dev-screen-frames'
    assert frame_storage_bucket({'id': 'f'}) == LEGACY_SCREEN_FRAMES_BUCKET
    assert frame_storage_bucket({'id': 'f', 'storage_bucket': ''}) == LEGACY_SCREEN_FRAMES_BUCKET
    assert frame_storage_bucket({'id': 'f', 'storage_bucket': PROD}) == PROD


def test_a_dev_adjudication_does_not_make_prod_skip(monkeypatch):
    # Existing conversations carry dev's legacy top-level marker.
    _ref(
        monkeypatch,
        {
            'screen_frames_adjudicated_at': datetime(2026, 9, 1, tzinfo=timezone.utc),
            'screen_frames_selection_fingerprint': 'meeting-content-v1:1:2',
            'screen_frames_revision': 4,
        },
    )

    assert screen_frames_db.get_conversation_screen_frames_adjudicated_at('u', 'c', bucket=PROD) is None
    assert screen_frames_db.get_conversation_screen_frames_selection_fingerprint('u', 'c', bucket=PROD) is None
    assert screen_frames_db.get_conversation_screen_frames_revision('u', 'c', bucket=PROD) == 0
    # Dev still reads its legacy fields unchanged.
    assert screen_frames_db.get_conversation_screen_frames_revision('u', 'c', bucket=LEGACY_SCREEN_FRAMES_BUCKET) == 4
    assert (
        screen_frames_db.get_conversation_screen_frames_selection_fingerprint(
            'u', 'c', bucket=LEGACY_SCREEN_FRAMES_BUCKET
        )
        == 'meeting-content-v1:1:2'
    )


def test_prod_markers_are_scoped_and_leave_dev_untouched(monkeypatch):
    ref = _ref(monkeypatch, {'screen_frames_revision': 4})

    stamp = screen_frames_db.mark_conversation_screen_frames_adjudicated(
        'u', 'c', selection_fingerprint='meeting-content-v1:9:9', bucket=PROD
    )
    assert screen_frames_db.bump_conversation_screen_frames_revision('u', 'c', bucket=PROD) == 1

    assert screen_frames_db.get_conversation_screen_frames_adjudicated_at('u', 'c', bucket=PROD) == stamp
    assert screen_frames_db.get_conversation_screen_frames_selection_fingerprint('u', 'c', bucket=PROD) == (
        'meeting-content-v1:9:9'
    )
    assert ref.data['screen_frames_revision'] == 4
    assert 'screen_frames_adjudicated_at' not in ref.data
    assert (
        screen_frames_db.get_conversation_screen_frames_adjudicated_at('u', 'c', bucket=LEGACY_SCREEN_FRAMES_BUCKET)
        is None
    )


def test_dev_keeps_writing_its_legacy_fields(monkeypatch):
    ref = _ref(monkeypatch)

    screen_frames_db.mark_conversation_screen_frames_adjudicated(
        'u', 'c', selection_fingerprint='fp', bucket=LEGACY_SCREEN_FRAMES_BUCKET
    )
    screen_frames_db.bump_conversation_screen_frames_revision('u', 'c', bucket=LEGACY_SCREEN_FRAMES_BUCKET)

    assert ref.data['screen_frames_selection_fingerprint'] == 'fp'
    assert ref.data['screen_frames_revision'] == 1
    assert 'screen_frames_env_state' not in ref.data


def test_a_deadline_bounds_the_marker_read_to_one_attempt(monkeypatch):
    ref = _ref(monkeypatch)
    screen_frames_db.get_conversation_screen_frames_adjudicated_at('u', 'c', bucket=PROD, rpc_timeout=3.5)
    assert ref.rpc_bounds == {'timeout': 3.5, 'retry': None}
    screen_frames_db.get_conversation_screen_frames_adjudicated_at('u', 'c', bucket=PROD)
    assert ref.rpc_bounds == {}


def test_the_marker_read_returns_stamp_and_fingerprint_for_this_bucket(monkeypatch):
    ref = _ref(
        monkeypatch, {'screen_frames_adjudicated_at': 'dev-stamp', 'screen_frames_selection_fingerprint': 'dev-fp'}
    )
    screen_frames_db.mark_conversation_screen_frames_adjudicated('u', 'c', selection_fingerprint='prod-fp', bucket=PROD)

    prod = screen_frames_db.get_conversation_screen_frames_marker('u', 'c', bucket=PROD, rpc_timeout=2.0)
    assert prod[1] == 'prod-fp' and prod[0] is not None
    assert ref.rpc_bounds == {'timeout': 2.0, 'retry': None}
    assert screen_frames_db.get_conversation_screen_frames_marker('u', 'c', bucket=LEGACY_SCREEN_FRAMES_BUCKET) == (
        'dev-stamp',
        'dev-fp',
    )
