from datetime import datetime, timezone
import json
import os
from unittest.mock import MagicMock, patch

from services.capture_wedge import (
    _emit,
    _isoformat_z,
    zero_session_log_filter,
    positive_session_log_filter,
    _num,
    _is_true_zero_tuple,
    zero_streak_candidates,
    positive_bytes_uids,
    read_vad_gate_metrics_entries,
    run_capture_wedge_check,
    _default_push,
)
from utils.notification_dispatch import NotificationDispatchStatus, NotificationDispatchOutcome


def test_emit(capsys):
    _emit("test_event", field1="value1", field2=123)
    captured = capsys.readouterr()
    expected = json.dumps({"event": "test_event", "field1": "value1", "field2": 123}) + "\n"
    assert captured.out == expected


def test_isoformat_z():
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert _isoformat_z(dt) == "2023-01-01T12:00:00Z"


def test_zero_session_log_filter():
    start = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2023, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    f = zero_session_log_filter(start, now)
    assert 'jsonPayload.bytes_received=0' in f
    assert 'timestamp>="2023-01-01T12:00:00Z"' in f
    assert 'timestamp<="2023-01-01T13:00:00Z"' in f


def test_positive_session_log_filter():
    start = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2023, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    f = positive_session_log_filter(["uid1", "uid2"], start, now)
    assert 'jsonPayload.bytes_received>0' in f
    assert 'jsonPayload.uid="uid1" OR jsonPayload.uid="uid2"' in f


def test_num():
    assert _num({"a": 1}, "a") == 1
    assert _num({"a": 1.5}, "a") == 1.5
    assert _num({"a": "1"}, "a") is None
    assert _num({"a": True}, "a") is None
    assert _num({}, "a") is None


def test_is_true_zero_tuple():
    assert _is_true_zero_tuple({"bytes_received": 0, "chunks_total": 0, "session_duration_sec": 0})
    assert not _is_true_zero_tuple({"bytes_received": 1, "chunks_total": 0, "session_duration_sec": 0})
    assert not _is_true_zero_tuple({"bytes_received": 0, "chunks_total": 0, "session_duration_sec": 0.1})


def test_zero_streak_candidates():
    # zero streak min is 3, assuming ZERO_STREAK_MIN=3 in capture_wedge module
    entries = [
        {
            "jsonPayload": {
                "uid": "uid1",
                "transcription_source": "omi",
                "bytes_received": 0,
                "chunks_total": 0,
                "session_duration_sec": 0,
            }
        },
        {
            "jsonPayload": {
                "uid": "uid1",
                "transcription_source": "omi",
                "bytes_received": 0,
                "chunks_total": 0,
                "session_duration_sec": 0,
            }
        },
        {
            "jsonPayload": {
                "uid": "uid1",
                "transcription_source": "omi",
                "bytes_received": 0,
                "chunks_total": 0,
                "session_duration_sec": 0,
            }
        },
        # Rejected due to onboarding_session_id
        {
            "jsonPayload": {
                "uid": "uid2",
                "onboarding_session_id": "123",
                "transcription_source": "omi",
                "bytes_received": 0,
                "chunks_total": 0,
                "session_duration_sec": 0,
            }
        },
        # Rejected due to not 'omi'
        {
            "jsonPayload": {
                "uid": "uid3",
                "transcription_source": "other",
                "bytes_received": 0,
                "chunks_total": 0,
                "session_duration_sec": 0,
            }
        },
        # Missing or invalid payload
        {},
        {"jsonPayload": "string instead of dict"},
        # Invalid uid
        {
            "jsonPayload": {
                "uid": 123,
                "transcription_source": "omi",
                "bytes_received": 0,
                "chunks_total": 0,
                "session_duration_sec": 0,
            }
        },
        {
            "jsonPayload": {
                "uid": "",
                "transcription_source": "omi",
                "bytes_received": 0,
                "chunks_total": 0,
                "session_duration_sec": 0,
            }
        },
    ]
    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        assert zero_streak_candidates(entries) == {"uid1": 3}


def test_positive_bytes_uids():
    entries = [
        {"jsonPayload": {"uid": "uid1", "bytes_received": 10}},
        {"jsonPayload": {"uid": "uid2", "bytes_received": 0}},  # not positive
        {"jsonPayload": {"uid": "uid3", "bytes_received": -1}},  # not positive
        {"jsonPayload": {"bytes_received": 10}},  # no uid
        {"jsonPayload": {"uid": "uid4"}},  # no bytes
        # Missing or invalid payload
        {},
        {"jsonPayload": "string instead of dict"},
    ]
    assert positive_bytes_uids(entries) == {"uid1"}


def test_run_capture_wedge_check_invalid_mode():
    assert run_capture_wedge_check(mode="invalid") == {'candidates': 0, 'nudged': 0, 'undeliverable': 0, 'errors': 0}


@patch('services.capture_wedge.read_vad_gate_metrics_entries')
def test_run_capture_wedge_check_no_project(mock_read):
    with patch.dict(os.environ, {}, clear=True):
        counts = run_capture_wedge_check(mode="detect", project_id="")
        assert counts == {'candidates': 0, 'nudged': 0, 'undeliverable': 0, 'errors': 1}
        mock_read.assert_not_called()


def test_run_capture_wedge_check_detect():
    mock_reader = MagicMock(return_value={'entries': [], 'truncated': False, 'errors': 0})
    counts = run_capture_wedge_check(mode="detect", project_id="test-project", entries_reader=mock_reader)
    assert counts == {'candidates': 0, 'nudged': 0, 'undeliverable': 0, 'errors': 0}


@patch('services.capture_wedge.AuthorizedSession')
@patch('google.auth.default')
def test_read_vad_gate_metrics_entries_success(mock_default, mock_session):
    mock_default.return_value = (MagicMock(), "project")
    session_instance = MagicMock()
    mock_session.return_value = session_instance

    response = MagicMock()
    response.status_code = 200
    response.json.side_effect = [
        {'entries': [{'id': 1}], 'nextPageToken': 'token1'},
        {'entries': [{'id': 2}], 'nextPageToken': ''},
    ]
    session_instance.post.return_value = response

    result = read_vad_gate_metrics_entries(project_id="test", filter_string="test")
    assert result['errors'] == 0
    assert result['truncated'] is False
    assert len(result['entries']) == 2
    assert session_instance.post.call_count == 2


@patch('services.capture_wedge.AuthorizedSession')
@patch('google.auth.default')
def test_read_vad_gate_metrics_entries_error_status(mock_default, mock_session):
    mock_default.return_value = (MagicMock(), "project")
    session_instance = MagicMock()
    mock_session.return_value = session_instance

    response = MagicMock()
    response.status_code = 500
    session_instance.post.return_value = response

    result = read_vad_gate_metrics_entries(project_id="test", filter_string="test")
    assert result['errors'] == 1
    assert result['truncated'] is False
    assert len(result['entries']) == 0


@patch('services.capture_wedge.AuthorizedSession')
@patch('google.auth.default')
def test_read_vad_gate_metrics_entries_exception(mock_default, mock_session):
    mock_default.return_value = (MagicMock(), "project")
    session_instance = MagicMock()
    mock_session.return_value = session_instance

    session_instance.post.side_effect = Exception("Network error")

    result = read_vad_gate_metrics_entries(project_id="test", filter_string="test")
    assert result['errors'] == 1
    assert result['truncated'] is False
    assert len(result['entries']) == 0


@patch('services.capture_wedge.AuthorizedSession')
@patch('google.auth.default')
def test_read_vad_gate_metrics_entries_truncation(mock_default, mock_session):
    mock_default.return_value = (MagicMock(), "project")
    session_instance = MagicMock()
    mock_session.return_value = session_instance

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'entries': [{'id': i} for i in range(10)], 'nextPageToken': 'token'}
    session_instance.post.return_value = response

    result = read_vad_gate_metrics_entries(project_id="test", filter_string="test", max_entries=5)
    assert result['errors'] == 0
    assert result['truncated'] is True
    assert len(result['entries']) == 5


@patch('services.capture_wedge.dispatch_notification')
def test_default_push(mock_dispatch):
    # Delivery success
    mock_dispatch.return_value = NotificationDispatchOutcome(
        status=NotificationDispatchStatus.DISPATCHED,
        delivered=True,
    )
    assert _default_push("uid", "title", "body", {}) == 1

    # Not dispatched
    mock_dispatch.return_value = NotificationDispatchOutcome(
        status=NotificationDispatchStatus.FAILED,
        delivered=False,
    )
    assert _default_push("uid", "title", "body", {}) == 0

    # Dispatched but not delivered (e.g. APNs issue)
    mock_dispatch.return_value = NotificationDispatchOutcome(
        status=NotificationDispatchStatus.DISPATCHED,
        delivered=False,
    )
    assert _default_push("uid", "title", "body", {}) == 0


def test_run_capture_wedge_check_zero_read_error():
    mock_reader = MagicMock(side_effect=Exception("Error"))
    counts = run_capture_wedge_check(mode="detect", project_id="test", entries_reader=mock_reader)
    assert counts['errors'] == 1


def test_run_capture_wedge_check_zero_read_truncated():
    mock_reader = MagicMock(return_value={'entries': [], 'truncated': True, 'errors': 0})
    counts = run_capture_wedge_check(mode="detect", project_id="test", entries_reader=mock_reader)
    assert counts['errors'] == 1


def test_run_capture_wedge_check_oversized_candidates():
    # Force max candidates check to fail by mocking zero_streak_candidates
    mock_reader = MagicMock(return_value={'entries': [{'id': 1}], 'truncated': False, 'errors': 0})
    with patch('services.capture_wedge.zero_streak_candidates', return_value={f'uid{i}': 5 for i in range(101)}):
        with patch('services.capture_wedge.MAX_CANDIDATES_PER_TICK', 100):
            counts = run_capture_wedge_check(mode="detect", project_id="test", entries_reader=mock_reader)
            assert counts['errors'] == 1


def test_run_capture_wedge_check_positive_read_error():
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            raise Exception("Positive read error")

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(mode="detect", project_id="test", entries_reader=mock_reader_func)
        assert counts['errors'] == 1


def test_run_capture_wedge_check_positive_read_truncated():
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': True, 'errors': 0}

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(mode="detect", project_id="test", entries_reader=mock_reader_func)
        assert counts['errors'] == 1


@patch('services.capture_wedge.capture_wedge_state')
def test_run_capture_wedge_check_full_flow(mock_state):
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            # uid1 has 3 true zero
            # uid2 has 3 true zero
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    },
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    },
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    },
                    {
                        'jsonPayload': {
                            'uid': 'uid2',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    },
                    {
                        'jsonPayload': {
                            'uid': 'uid2',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    },
                    {
                        'jsonPayload': {
                            'uid': 'uid2',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    },
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            # uid2 delivered positive bytes
            return {
                'entries': [{'jsonPayload': {'uid': 'uid2', 'bytes_received': 10}}],
                'truncated': False,
                'errors': 0,
            }

    mock_push = MagicMock(return_value=1)

    mock_state.claim_wedge_first_seen.return_value = True
    mock_state.claim_wedge_nudge_cooldown.return_value = True

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="heal", project_id="test", entries_reader=mock_reader_func, send_push=mock_push, dry_run=False
        )

        # Only uid1 should be a candidate
        assert counts['candidates'] == 1
        assert counts['nudged'] == 1
        assert counts['undeliverable'] == 0
        assert counts['errors'] == 0
        mock_push.assert_called_once()


@patch('services.capture_wedge.capture_wedge_state')
def test_run_capture_wedge_check_nudge_errors(mock_state):
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': False, 'errors': 0}

    # Test push exception
    mock_push = MagicMock(side_effect=Exception("Push error"))
    mock_state.claim_wedge_first_seen.return_value = True
    mock_state.claim_wedge_nudge_cooldown.return_value = True

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="heal",
            project_id="test",
            entries_reader=mock_reader_func,
            send_push=mock_push,
        )
        assert counts['errors'] == 1
        assert counts['undeliverable'] == 1


@patch('services.capture_wedge.capture_wedge_state')
def test_run_capture_wedge_check_cooldown(mock_state):
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': False, 'errors': 0}

    mock_push = MagicMock(return_value=1)

    mock_state.claim_wedge_first_seen.return_value = True
    # Cooldown block
    mock_state.claim_wedge_nudge_cooldown.return_value = False

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="heal",
            project_id="test",
            entries_reader=mock_reader_func,
            send_push=mock_push,
        )

        assert counts['candidates'] == 1
        assert counts['nudged'] == 0
        mock_push.assert_not_called()


@patch('services.capture_wedge.capture_wedge_state')
def test_run_capture_wedge_check_allowlist(mock_state):
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': False, 'errors': 0}

    mock_push = MagicMock(return_value=1)
    mock_state.claim_wedge_first_seen.return_value = True
    mock_state.claim_wedge_nudge_cooldown.return_value = True

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        # uid1 not in allowlist
        counts = run_capture_wedge_check(
            mode="heal",
            project_id="test",
            entries_reader=mock_reader_func,
            send_push=mock_push,
            uid_allowlist=frozenset(["uid2"]),
        )

        assert counts['candidates'] == 1
        assert counts['nudged'] == 0
        mock_push.assert_not_called()


@patch('services.capture_wedge.capture_wedge_state')
def test_run_capture_wedge_check_state_errors(mock_state):
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': False, 'errors': 0}

    mock_push = MagicMock()

    # Exception during first seen claim
    mock_state.claim_wedge_first_seen.side_effect = Exception("DB Error")

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="heal",
            project_id="test",
            entries_reader=mock_reader_func,
            send_push=mock_push,
        )
        # We continue after first seen error, so candidate still tries to nudge
        assert counts['errors'] >= 1

    mock_state.claim_wedge_first_seen.side_effect = None
    mock_state.claim_wedge_first_seen.return_value = True

    # Exception during cooldown claim
    mock_state.claim_wedge_nudge_cooldown.side_effect = Exception("DB Error")
    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="heal",
            project_id="test",
            entries_reader=mock_reader_func,
            send_push=mock_push,
        )
        assert counts['errors'] >= 1
        mock_push.assert_not_called()


def test_run_capture_wedge_check_dry_run():
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': False, 'errors': 0}

    mock_push = MagicMock()

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="heal", project_id="test", entries_reader=mock_reader_func, send_push=mock_push, dry_run=True
        )
        assert counts['candidates'] == 1
        assert counts['nudged'] == 0
        mock_push.assert_not_called()


@patch('services.capture_wedge.capture_wedge_state')
def test_run_capture_wedge_check_first_seen_not_claimed(mock_state):
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': False, 'errors': 0}

    mock_push = MagicMock(return_value=1)

    # First seen is false (already seen)
    mock_state.claim_wedge_first_seen.return_value = False
    mock_state.claim_wedge_nudge_cooldown.return_value = True

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="heal", project_id="test", entries_reader=mock_reader_func, send_push=mock_push, dry_run=False
        )

        assert counts['candidates'] == 1
        assert counts['nudged'] == 1


@patch('services.capture_wedge.capture_wedge_state')
def test_run_capture_wedge_check_detect_only(mock_state):
    def mock_reader_func(project_id, filter_string, **kwargs):
        if 'bytes_received=0' in filter_string:
            return {
                'entries': [
                    {
                        'jsonPayload': {
                            'uid': 'uid1',
                            'transcription_source': 'omi',
                            'bytes_received': 0,
                            'chunks_total': 0,
                            'session_duration_sec': 0,
                        }
                    }
                    for _ in range(3)
                ],
                'truncated': False,
                'errors': 0,
            }
        else:
            return {'entries': [], 'truncated': False, 'errors': 0}

    mock_push = MagicMock(return_value=1)

    mock_state.claim_wedge_first_seen.return_value = True

    with patch('services.capture_wedge.ZERO_STREAK_MIN', 3):
        counts = run_capture_wedge_check(
            mode="detect", project_id="test", entries_reader=mock_reader_func, send_push=mock_push, dry_run=False
        )

        assert counts['candidates'] == 1
        assert counts['nudged'] == 0
