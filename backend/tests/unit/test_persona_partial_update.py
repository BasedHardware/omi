"""A persona PATCH must only touch the fields the caller sent.

`PATCH /v1/personas/{id}` unconditionally did two destructive things with
whatever payload arrived:

1. `save_username(data['username'], uid)` — a KeyError for any partial payload,
   and a handle re-claim for every full one.
2. `data['description'] = generate_persona_desc(uid, data['name'])` — an LLM
   call on every save that overwrote the stored description even when nothing
   about the name had changed, so a user-written description could not survive
   an unrelated edit.

Together they made partial editing impossible, which is why the web client
shipped its Persona page read-only.

Seam: `routers.apps.update_persona` is awaited directly with its collaborators
patched — no HTTP client, no Firestore, no LLM.
"""

import asyncio
import json

import pytest

import routers.apps as apps_router

EXISTING = {
    'id': 'persona-1',
    'uid': 'uid-1',
    'name': 'Ada',
    'username': 'ada',
    'description': 'A description the user wrote themselves.',
    'category': 'personality-emulation',
    'capabilities': ['persona'],
    'connected_accounts': [],
    'approved': True,
    'private': False,
    'image': '',
}


@pytest.fixture
def calls(monkeypatch):
    """Patch the write/LLM collaborators and record what they were asked to do."""
    recorded = {'usernames': [], 'descriptions': 0, 'updates': []}

    async def _run_blocking(executor, fn, *args):
        return fn(*args)

    def _save_username(username, uid):
        recorded['usernames'].append((username, uid))

    def _generate_desc(uid, name):
        recorded['descriptions'] += 1
        return f'generated for {name}'

    monkeypatch.setattr(apps_router, 'run_blocking', _run_blocking)
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda pid, uid: dict(EXISTING))
    monkeypatch.setattr(apps_router, 'save_username', _save_username)
    monkeypatch.setattr(apps_router, 'generate_persona_desc', _generate_desc)
    monkeypatch.setattr(apps_router, 'update_app_in_db', lambda data: recorded['updates'].append(data))
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda pid: None)
    monkeypatch.setattr(apps_router, 'invalidate_approved_apps_cache', lambda: None)
    return recorded


def _patch(payload):
    return asyncio.run(
        apps_router.update_persona('persona-1', persona_data=json.dumps(payload), file=None, uid='uid-1')
    )


def test_a_title_only_edit_does_not_reclaim_the_handle(calls):
    _patch({'name': 'Ada Lovelace'})

    assert calls['usernames'] == []


def test_a_partial_payload_without_a_username_does_not_raise(calls):
    # The old code did data['username'] unconditionally, so this was a KeyError.
    result = _patch({'name': 'Ada Lovelace'})

    assert result['status'] == 'ok'


def test_an_unchanged_name_keeps_the_stored_description(calls):
    _patch({'name': 'Ada'})

    assert calls['descriptions'] == 0
    assert 'description' not in calls['updates'][0] or calls['updates'][0]['description'] == EXISTING['description']


def test_a_changed_name_regenerates_the_description(calls):
    _patch({'name': 'Ada Lovelace'})

    assert calls['descriptions'] == 1
    assert calls['updates'][0]['description'] == 'generated for Ada Lovelace'


def test_a_caller_supplied_description_is_not_overwritten(calls):
    _patch({'name': 'Ada Lovelace', 'description': 'Mine, not the model’s.'})

    assert calls['descriptions'] == 0
    assert calls['updates'][0]['description'] == 'Mine, not the model’s.'


def test_an_explicitly_cleared_description_is_not_regenerated(calls):
    """Clearing the description is a field the caller sent; presence, not truthiness, decides."""
    _patch({'name': 'Ada Lovelace', 'description': ''})

    assert calls['descriptions'] == 0
    assert calls['updates'][0]['description'] == ''


def test_an_unchanged_username_is_not_reclaimed(calls):
    """Released clients resend the whole persona; that must not re-save the handle."""
    _patch({'name': 'Ada', 'username': 'ada'})

    assert calls['usernames'] == []


def test_a_changed_username_is_claimed(calls):
    _patch({'username': 'adalovelace'})

    assert calls['usernames'] == [('adalovelace', 'uid-1')]


def test_an_omitted_username_is_not_written_back(calls):
    _patch({'name': 'Ada Lovelace'})

    written = calls['updates'][0]
    assert written['id'] == 'persona-1'
    assert 'username' not in written
    assert 'updated_at' in written


def test_a_persona_owned_by_someone_else_is_rejected(monkeypatch, calls):
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda pid, uid: {**EXISTING, 'uid': 'someone-else'})

    with pytest.raises(apps_router.HTTPException) as excinfo:
        _patch({'name': 'Ada Lovelace'})

    assert excinfo.value.status_code == 403
