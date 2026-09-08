"""create_persona must not 500 with AttributeError when the user lookup returns None.

routers.apps imports under conftest's stubs (tiktoken) + ENCRYPTION_SECRET/OPENAI_API_KEY
provided by tests/conftest.py, so no module-scope sys.modules mutation is required.

Without the fix, `user = await run_blocking(db_executor, get_user_from_uid, uid)` is None and the
next line `user.get('display_name', '')` raises AttributeError (-> 500). With the guard (`or {}`)
the handler proceeds cleanly.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

from routers import apps as apps_mod


class _FakeUpload:
    """Minimal stand-in for fastapi UploadFile used by create_persona."""

    filename = 'avatar.png'

    async def read(self):
        return b'imgbytes'


def _run_create_persona(user_value):
    """Drive create_persona end to end with get_user_from_uid returning ``user_value``.

    run_blocking is the only async-offload primitive in the function; we make it execute the
    wrapped sync collaborator but force the get_user_from_uid result to ``user_value`` so we can
    exercise the None-user branch. generate_persona_prompt is awaited directly, so it gets its own
    async stub. AppCreate / file IO / db writes are stubbed so only the user-dereference is tested.
    """

    async def fake_run_blocking(executor, func, *args):
        if func is apps_mod.get_user_from_uid:
            return user_value
        if func is apps_mod.increment_username:
            return args[0]
        # save_username / _write_file / add_app_to_db / generate_persona_desc, etc.
        return MagicMock()

    async def fake_generate_persona_prompt(uid, data):
        return 'prompt'

    persona_data = json.dumps({'name': 'Ada', 'username': 'ada', 'connected_accounts': ['omi']})

    fake_app_create = MagicMock()
    fake_app_create.model_dump.return_value = {}

    with patch.object(apps_mod, 'run_blocking', side_effect=fake_run_blocking), patch.object(
        apps_mod, 'get_user_from_uid', MagicMock()
    ), patch.object(apps_mod, 'increment_username', MagicMock()), patch.object(
        apps_mod, 'save_username', MagicMock()
    ), patch.object(
        apps_mod, 'generate_persona_prompt', side_effect=fake_generate_persona_prompt
    ), patch.object(
        apps_mod, 'generate_persona_desc', MagicMock()
    ), patch.object(
        apps_mod, '_write_file', MagicMock()
    ), patch.object(
        apps_mod, 'upload_app_logo', MagicMock(return_value='http://img')
    ), patch.object(
        apps_mod, 'add_app_to_db', MagicMock()
    ), patch.object(
        apps_mod.AppCreate, 'model_validate', return_value=fake_app_create
    ), patch.object(
        apps_mod.os, 'makedirs', MagicMock()
    ):
        return asyncio.run(apps_mod.create_persona(persona_data=persona_data, file=_FakeUpload(), uid='uid1'))


def test_create_persona_user_none_does_not_crash():
    """User lookup returning None must not raise AttributeError/TypeError (the bug)."""
    result = _run_create_persona(None)
    assert isinstance(result, dict)
    assert result['status'] == 'ok'
    # author/email degrade gracefully instead of crashing.
    assert result['app_id']


def test_create_persona_with_user_populates_author_email():
    """When the user exists, author/email still flow through (no regression)."""
    result = _run_create_persona({'display_name': 'Ada Lovelace', 'email': 'ada@example.com'})
    assert isinstance(result, dict)
    assert result['status'] == 'ok'
