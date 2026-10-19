"""Unit tests for announcements router auth hardening, ID/query validation, and store error boundaries."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.announcements as announcements_router
from models.announcement import Announcement, AnnouncementType
from routers.announcements import (
    CreateAnnouncementRequest,
    DismissAnnouncementRequest,
    UpdateAnnouncementRequest,
    _require_announcement_id,
    _verify_admin_key,
    create_announcement_endpoint,
    delete_announcement_endpoint,
    dismiss_announcement_endpoint,
    get_announcement,
    get_announcements,
    get_changelogs,
    get_features,
    get_pending_announcements_endpoint,
    list_all_announcements,
    update_announcement_endpoint,
)


def _sample_announcement(ann_id: str = 'ann-1') -> Announcement:
    return Announcement(
        id=ann_id,
        type=AnnouncementType.ANNOUNCEMENT,
        created_at=datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc),
        content={'title': 'Hello', 'body': 'World'},
        active=True,
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
def test_require_announcement_id_rejects_invalid_identifiers(bad_id):
    with pytest.raises(HTTPException) as exc_info:
        _require_announcement_id(bad_id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Valid announcement_id is required'


def test_require_announcement_id_trims_valid_id():
    assert _require_announcement_id('  ann-2026-10  ') == 'ann-2026-10'


def test_verify_admin_key_uses_constant_time_compare_and_rejects_missing_or_blank_env(monkeypatch):
    monkeypatch.delenv('ADMIN_KEY', raising=False)
    with pytest.raises(HTTPException) as exc_info:
        _verify_admin_key('any-key')
    assert exc_info.value.status_code == 403

    monkeypatch.setenv('ADMIN_KEY', '   ')
    with pytest.raises(HTTPException) as exc_info:
        _verify_admin_key('   ')
    assert exc_info.value.status_code == 403

    monkeypatch.setenv('ADMIN_KEY', 'super-secret-admin-key')
    with patch.object(announcements_router.hmac, 'compare_digest', wraps=announcements_router.hmac.compare_digest) as m:
        _verify_admin_key('super-secret-admin-key')
        m.assert_called_once_with(b'super-secret-admin-key', b'super-secret-admin-key')

    with pytest.raises(HTTPException) as exc_info:
        _verify_admin_key('wrong-key')
    assert exc_info.value.status_code == 403


def test_get_changelogs_rejects_nonpositive_limit_and_clamps_excessive_limit():
    with pytest.raises(HTTPException) as exc_info:
        get_changelogs(from_version=None, to_version=None, max_version=None, limit=0)
    assert exc_info.value.status_code == 422

    with patch.object(announcements_router, 'get_recent_changelogs', return_value=[]) as mock_recent:
        get_changelogs(from_version='   ', to_version=None, max_version='  1.2.0  ', limit=5000)
        mock_recent.assert_called_once_with(limit=100, max_version='1.2.0')


def test_get_changelogs_trims_from_and_to_versions():
    with patch.object(announcements_router, 'get_app_changelogs', return_value=[]) as mock_range:
        get_changelogs(from_version='  1.0.0  ', to_version='  1.1.0  ', max_version=None, limit=5)
        mock_range.assert_called_once_with('1.0.0', '1.1.0')


def test_get_features_rejects_invalid_version_type_and_blank_version():
    with pytest.raises(HTTPException) as exc_info:
        get_features(version='   ', version_type='app', device_model=None)
    assert exc_info.value.status_code == 400
    assert 'version' in exc_info.value.detail

    with pytest.raises(HTTPException) as exc_info:
        get_features(version='1.0.0', version_type='desktop', device_model=None)
    assert exc_info.value.status_code == 400
    assert "version_type must be 'app' or 'firmware'" in exc_info.value.detail


def test_get_features_dispatches_trimmed_app_and_firmware_queries():
    with patch.object(announcements_router, 'get_app_features', return_value=[]) as mock_app:
        get_features(version='  1.0.5  ', version_type='  app  ', device_model=None)
        mock_app.assert_called_once_with('1.0.5')

    with patch.object(announcements_router, 'get_firmware_features', return_value=[]) as mock_fw:
        get_features(version='  2.0.1  ', version_type='  firmware  ', device_model='  Omi Glass  ')
        mock_fw.assert_called_once_with('2.0.1', 'Omi Glass')


def test_get_pending_announcements_rejects_blank_app_version():
    with pytest.raises(HTTPException) as exc_info:
        get_pending_announcements_endpoint(
            app_version='   ',
            platform='ios',
            trigger='app_launch',
            firmware_version=None,
            device_model=None,
            uid='uid-1',
        )
    assert exc_info.value.status_code == 400
    assert 'app_version' in exc_info.value.detail


def test_dismiss_announcement_validates_id_and_returns_404_when_missing():
    with pytest.raises(HTTPException) as exc_info:
        dismiss_announcement_endpoint('a/b', DismissAnnouncementRequest(cta_clicked=True), uid='uid-1')
    assert exc_info.value.status_code == 400

    with patch.object(announcements_router, 'get_announcement_by_id', return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            dismiss_announcement_endpoint('ann-missing', DismissAnnouncementRequest(cta_clicked=False), uid='uid-1')
        assert exc_info.value.status_code == 404


def test_admin_crud_validates_ids_and_trims_before_store_calls(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'admin-secret')
    ann = _sample_announcement('ann-1')

    with patch.object(announcements_router, 'get_announcement_by_id', return_value=ann) as mock_get:
        res = get_announcement('  ann-1  ', secret_key='admin-secret')
        assert res.id == 'ann-1'
        mock_get.assert_called_once_with('ann-1')

    with pytest.raises(HTTPException) as exc_info:
        create_announcement_endpoint(
            CreateAnnouncementRequest(id='bad/id', type=AnnouncementType.ANNOUNCEMENT, content={'title': 'T'}),
            secret_key='admin-secret',
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        update_announcement_endpoint(
            'ann-1',
            UpdateAnnouncementRequest(),
            secret_key='admin-secret',
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'No fields to update'


def test_all_endpoints_raise_sanitized_500_on_store_failures(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'admin-secret')
    err = RuntimeError('Firestore token=secret_abc outage')

    with patch.object(announcements_router, 'get_recent_changelogs', side_effect=err):
        with pytest.raises(HTTPException) as exc_info:
            get_changelogs(from_version=None, to_version=None, max_version=None, limit=5)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to load changelogs'

    with patch.object(announcements_router, 'get_app_features', side_effect=err):
        with pytest.raises(HTTPException) as exc_info:
            get_features(version='1.0.0', version_type='app', device_model=None)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to load features'

    with patch.object(announcements_router, 'get_general_announcements', side_effect=err):
        with pytest.raises(HTTPException) as exc_info:
            get_announcements(last_checked_at='2026-10-19T00:00:00Z')
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to load announcements'

    with patch.object(announcements_router, 'get_pending_announcements', side_effect=err):
        with pytest.raises(HTTPException) as exc_info:
            get_pending_announcements_endpoint(
                app_version='1.0.0',
                platform='ios',
                trigger='app_launch',
                firmware_version=None,
                device_model=None,
                uid='uid-1',
            )
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to load pending announcements'

    with patch.object(announcements_router, 'get_announcement_by_id', side_effect=err):
        with pytest.raises(HTTPException) as exc_info:
            dismiss_announcement_endpoint('ann-1', DismissAnnouncementRequest(), uid='uid-1')
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to dismiss announcement'

        with pytest.raises(HTTPException) as exc_info:
            get_announcement('ann-1', secret_key='admin-secret')
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to load announcement'

        with pytest.raises(HTTPException) as exc_info:
            create_announcement_endpoint(
                CreateAnnouncementRequest(id='ann-1', type=AnnouncementType.ANNOUNCEMENT, content={'title': 'T'}),
                secret_key='admin-secret',
            )
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to create announcement'

        with pytest.raises(HTTPException) as exc_info:
            update_announcement_endpoint(
                'ann-1',
                UpdateAnnouncementRequest(active=False),
                secret_key='admin-secret',
            )
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to update announcement'

        with pytest.raises(HTTPException) as exc_info:
            delete_announcement_endpoint('ann-1', secret_key='admin-secret', soft_delete=True)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to delete announcement'

    with patch.object(announcements_router, 'get_all_announcements', side_effect=err):
        with pytest.raises(HTTPException) as exc_info:
            list_all_announcements(secret_key='admin-secret', announcement_type=None, active_only=False)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to list announcements'
