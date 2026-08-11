"""Path-traversal + temp-file-lifetime guards for client-uploaded files.

These exercise the production surfaces, not a copy of their logic:
  - utils.upload_temp (the shared naming/cleanup primitive)
  - routers.apps.create_app / update_app / create_persona (real handlers,
    with storage and the database stubbed out)
so removing the basename sanitize or the cleanup fails the suite.
"""

import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from routers import apps as apps_mod
from utils.upload_temp import safe_upload_filename, temp_upload_path


class _FakeUpload:
    def __init__(self, filename):
        self.filename = filename
        self.file = MagicMock()
        self.file.read.return_value = b'imgbytes'

    async def read(self):
        return b'imgbytes'


# ---------------------------------------------------------------------------
# utils.upload_temp — the shared primitive every upload route goes through
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'filename,expected',
    [
        ('logo.png', 'logo.png'),
        ('../../etc/passwd', 'passwd'),
        ('/etc/shadow', 'shadow'),
        ('../../../tmp/../../../etc/hosts', 'hosts'),
        ('', 'upload'),
        (None, 'upload'),
        ('..', 'upload'),
        ('.', 'upload'),
    ],
)
def test_safe_upload_filename_strips_directories(filename, expected):
    assert safe_upload_filename(filename) == expected


def test_safe_upload_filename_bounds_length_and_keeps_extension():
    name = safe_upload_filename('a' * 4000 + '.png')
    # UUID prefix (32 hex + '_') plus the name must fit one 255-byte component,
    # or the write fails with ENAMETOOLONG.
    assert len(f'{"0" * 32}_{name}'.encode('utf-8')) <= 255
    assert name.endswith('.png')


def test_temp_upload_path_writes_inside_the_directory_and_cleans_up(tmp_path):
    directory = tmp_path / 'apps'
    with temp_upload_path(str(directory), '../../escape.png') as path:
        with open(path, 'wb') as f:
            f.write(b'x')
        resolved = os.path.realpath(path)
        assert os.path.dirname(resolved) == os.path.realpath(str(directory))
        assert os.path.exists(path)
    assert not os.path.exists(path)
    assert os.listdir(str(directory)) == []


def test_temp_upload_path_cleans_up_when_processing_raises(tmp_path):
    directory = tmp_path / 'apps'
    with pytest.raises(RuntimeError):
        with temp_upload_path(str(directory), 'logo.png') as path:
            with open(path, 'wb') as f:
                f.write(b'x')
            raise RuntimeError('upload failed')
    assert not os.path.exists(path)


def test_temp_upload_path_is_collision_free(tmp_path):
    directory = str(tmp_path / 'apps')
    with temp_upload_path(directory, 'logo.png') as first:
        with temp_upload_path(directory, 'logo.png') as second:
            assert first != second


# ---------------------------------------------------------------------------
# routers.apps — the real handlers must use that primitive
# ---------------------------------------------------------------------------


def _capture_upload(handler, tmp_path, filename):
    """Run an upload handler and return (path handed to storage, existed then)."""
    seen = {}

    def _fake_upload_app_logo(path, _id):
        seen['path'] = path
        seen['existed'] = os.path.exists(path)
        return 'http://img'

    def _fake_write_file(path, contents):
        with open(path, 'wb') as f:
            f.write(contents)

    async def _fake_run_blocking(_executor, func, *args):
        if func is apps_mod.get_user_from_uid:
            return {'display_name': 'Ada', 'email': 'ada@example.com'}
        if func is apps_mod.increment_username:
            return args[0]
        if func in (_fake_upload_app_logo, _fake_write_file):
            return func(*args)
        return MagicMock()

    async def _fake_generate_persona_prompt(uid, data):
        return 'prompt'

    with (
        patch.object(apps_mod, 'upload_app_logo', _fake_upload_app_logo),
        patch.object(apps_mod, '_write_file', _fake_write_file),
        patch.object(apps_mod, 'run_blocking', side_effect=_fake_run_blocking),
        patch.object(apps_mod, 'get_user_from_uid', MagicMock()),
        patch.object(apps_mod, 'increment_username', MagicMock()),
        patch.object(apps_mod, 'save_username', MagicMock()),
        patch.object(apps_mod, 'generate_persona_prompt', side_effect=_fake_generate_persona_prompt),
        patch.object(apps_mod, 'generate_persona_desc', MagicMock()),
        patch.object(apps_mod, 'add_app_to_db', MagicMock()),
        patch.object(apps_mod, 'update_app_in_db', MagicMock()),
        patch.object(apps_mod, 'upsert_app_payment_link', MagicMock()),
        patch.object(apps_mod, 'delete_app_logo', MagicMock()),
        patch.object(apps_mod, '_process_chat_tools_manifest', MagicMock(side_effect=lambda _ei, d: d)),
        patch.object(
            apps_mod,
            'get_available_app_by_id',
            MagicMock(return_value={'uid': 'uid1', 'image': '', 'approved': False, 'private': True}),
        ),
        patch.object(apps_mod, 'delete_app_cache_by_id', MagicMock()),
        patch.object(apps_mod.AppCreate, 'model_validate', MagicMock(return_value=MagicMock())),
        # Keep temp files inside the test's tmp_path rather than the repo.
        patch.object(apps_mod, 'temp_upload_path', _rooted_temp_upload_path(tmp_path)),
    ):
        handler(_FakeUpload(filename))
    return seen


def _rooted_temp_upload_path(tmp_path):
    from utils.upload_temp import temp_upload_path as real

    def _wrapper(directory, filename):
        return real(os.path.join(str(tmp_path), directory), filename)

    return _wrapper


def _app_payload():
    return json.dumps(
        {
            'name': 'App',
            'description': 'd',
            'capabilities': [],
            'private': True,
            'deleted': False,
            'uid': 'uid1',
            'id': 'app-1',
        }
    )


def test_create_app_writes_uploads_inside_temp_apps_and_removes_them(tmp_path):
    seen = _capture_upload(
        lambda upload: apps_mod.create_app(app_data=_app_payload(), file=upload, uid='uid1'),
        tmp_path,
        '../../../../etc/passwd',
    )
    expected_dir = os.path.realpath(os.path.join(str(tmp_path), '_temp/apps'))
    assert os.path.dirname(os.path.realpath(seen['path'])) == expected_dir
    assert seen['existed'] is True
    # The temp file must not survive the request (uniquely-named uploads
    # otherwise accumulate until the disk fills).
    assert not os.path.exists(seen['path'])


def test_update_app_writes_uploads_inside_temp_apps_and_removes_them(tmp_path):
    seen = _capture_upload(
        lambda upload: apps_mod.update_app(app_id='app-1', app_data=_app_payload(), file=upload, uid='uid1'),
        tmp_path,
        '../../escape.png',
    )
    expected_dir = os.path.realpath(os.path.join(str(tmp_path), '_temp/apps'))
    assert os.path.dirname(os.path.realpath(seen['path'])) == expected_dir
    assert seen['existed'] is True
    assert not os.path.exists(seen['path'])


def test_create_persona_writes_uploads_inside_temp_apps_and_removes_them(tmp_path):
    persona_data = json.dumps({'name': 'Ada', 'username': 'ada', 'connected_accounts': ['omi']})
    seen = _capture_upload(
        lambda upload: asyncio.run(apps_mod.create_persona(persona_data=persona_data, file=upload, uid='uid1')),
        tmp_path,
        '../../../etc/passwd',
    )
    expected_dir = os.path.realpath(os.path.join(str(tmp_path), '_temp/apps'))
    assert os.path.dirname(os.path.realpath(seen['path'])) == expected_dir
    assert seen['existed'] is True
    assert not os.path.exists(seen['path'])
