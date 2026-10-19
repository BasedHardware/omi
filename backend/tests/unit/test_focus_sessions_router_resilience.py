"""Unit tests for focus_sessions router validation, input normalization, and store error boundaries."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.focus_sessions as focus_router
from routers.focus_sessions import (
    CreateFocusSessionRequest,
    _require_session_id,
    create_focus_session,
    delete_focus_session,
    get_focus_sessions,
    get_focus_stats,
    list_screen_activity,
    screen_activity_summary,
)


@pytest.mark.parametrize(
    'bad_id',
    [
        '',
        '   ',
        '\t\n',
        '.',
        '..',
        ' . ',
        ' .. ',
        'a/b',
        '__reserved__',
        'x' * 1501,
    ],
)
def test_require_session_id_rejects_invalid_identifiers(bad_id):
    with pytest.raises(HTTPException) as exc_info:
        _require_session_id(bad_id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Valid session_id is required'


def test_require_session_id_trims_valid_identifier():
    assert _require_session_id('  sess-abc-123  ') == 'sess-abc-123'


@pytest.mark.parametrize('blank_value', ['   ', '\t', '\n  '])
def test_create_focus_session_rejects_whitespace_only_app_or_site(blank_value):
    req = CreateFocusSessionRequest(
        status='focused',
        app_or_site=blank_value,
        description='Writing unit tests',
    )
    with pytest.raises(HTTPException) as exc_info:
        create_focus_session(req, uid='uid-1')
    assert exc_info.value.status_code == 400
    assert 'app_or_site' in exc_info.value.detail


@pytest.mark.parametrize('blank_value', ['   ', '\t', '\n  '])
def test_create_focus_session_rejects_whitespace_only_description(blank_value):
    req = CreateFocusSessionRequest(
        status='distracted',
        app_or_site='YouTube',
        description=blank_value,
    )
    with pytest.raises(HTTPException) as exc_info:
        create_focus_session(req, uid='uid-1')
    assert exc_info.value.status_code == 400
    assert 'description' in exc_info.value.detail


def test_create_focus_session_strips_fields_and_normalizes_blank_message():
    req = CreateFocusSessionRequest(
        status='focused',
        app_or_site='  VS Code  ',
        description='  Implementing router resilience  ',
        message='   ',
        duration_seconds=300,
    )
    fake_doc = {
        'id': 'sess-1',
        'status': 'focused',
        'app_or_site': 'VS Code',
        'description': 'Implementing router resilience',
        'message': None,
        'created_at': datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc),
        'duration_seconds': 300,
    }
    with patch.object(focus_router.focus_sessions_db, 'create_focus_session', return_value=fake_doc) as mock_create:
        res = create_focus_session(req, uid='uid-1')

    assert res == fake_doc
    mock_create.assert_called_once_with(
        'uid-1',
        status='focused',
        app_or_site='VS Code',
        description='Implementing router resilience',
        message=None,
        duration_seconds=300,
    )


def test_create_focus_session_raises_sanitized_500_on_store_failure():
    req = CreateFocusSessionRequest(
        status='focused',
        app_or_site='VS Code',
        description='Coding',
    )
    with patch.object(
        focus_router.focus_sessions_db,
        'create_focus_session',
        side_effect=RuntimeError('Firestore error Bearer secret_token_123'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            create_focus_session(req, uid='uid-1')

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Failed to create focus session'


def test_get_focus_sessions_raises_sanitized_500_on_store_failure():
    with patch.object(
        focus_router.focus_sessions_db,
        'get_focus_sessions',
        side_effect=RuntimeError('Firestore timeout'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            get_focus_sessions(limit=50, offset=0, date='2026-10-19', uid='uid-1')

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Failed to load focus sessions'


def test_delete_focus_session_returns_404_when_not_found():
    with patch.object(focus_router.focus_sessions_db, 'delete_focus_session', return_value=False) as mock_del:
        with pytest.raises(HTTPException) as exc_info:
            delete_focus_session('  sess-missing  ', uid='uid-1')

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'Focus session not found'
    mock_del.assert_called_once_with('uid-1', 'sess-missing')


def test_delete_focus_session_returns_ok_when_deleted():
    with patch.object(focus_router.focus_sessions_db, 'delete_focus_session', return_value=True) as mock_del:
        res = delete_focus_session('  sess-123  ', uid='uid-1')

    assert res == {'status': 'ok'}
    mock_del.assert_called_once_with('uid-1', 'sess-123')


def test_delete_focus_session_raises_sanitized_500_on_store_failure():
    with patch.object(
        focus_router.focus_sessions_db,
        'delete_focus_session',
        side_effect=RuntimeError('Firestore write error'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            delete_focus_session('sess-123', uid='uid-1')

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Failed to delete focus session'


def test_get_focus_stats_raises_sanitized_500_on_store_failure():
    with patch.object(
        focus_router.focus_sessions_db,
        'get_focus_stats',
        side_effect=RuntimeError('Firestore query error'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            get_focus_stats(date='2026-10-19', uid='uid-1')

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Failed to load focus stats'


def test_list_screen_activity_normalizes_blank_app_filter_and_trims_valid_filter():
    with patch.object(focus_router.screen_activity_db, 'get_screen_activity', return_value=[]) as mock_list:
        res = list_screen_activity(date='2026-10-19', app_filter='   ', limit=100, uid='uid-1')
        assert res == []
        assert mock_list.call_args.kwargs['app_filter'] is None

        list_screen_activity(date='2026-10-19', app_filter='  Chrome  ', limit=100, uid='uid-1')
        assert mock_list.call_args.kwargs['app_filter'] == 'Chrome'


def test_list_screen_activity_raises_sanitized_500_on_store_failure():
    with patch.object(
        focus_router.screen_activity_db,
        'get_screen_activity',
        side_effect=RuntimeError('Screen activity DB down'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            list_screen_activity(date='2026-10-19', app_filter=None, limit=100, uid='uid-1')

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Failed to load screen activity'


def test_screen_activity_summary_raises_sanitized_500_on_store_failure():
    with patch.object(
        focus_router.screen_activity_db,
        'get_screen_activity_summary',
        side_effect=RuntimeError('Screen activity summary DB down'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            screen_activity_summary(date='2026-10-19', uid='uid-1')

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Failed to load screen activity summary'
