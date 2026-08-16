"""App-review notifications must not address users as "None".

``database.auth.get_user_from_uid`` always emits a ``display_name`` key — it is built
from ``firebase_admin``'s UserRecord, whose ``display_name`` is ``None`` for any account
created without one (email/password signup, Apple private-relay). ``dict.get(key,
default)`` only falls back when the key is *absent*, so the stored ``None`` was used
verbatim and the push title read "None reviewed Weather".

Isolation: utils/notifications.py pulls firebase_admin at import, so it is loaded through
the sanctioned Tier-2 reserve seam (stub_modules + load_module_fresh) inside a fixture.
See backend/docs/test_isolation.md.
"""

from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


@contextmanager
def _notifications_with_user(user: Any) -> Iterator[Any]:
    """Load utils.notifications with get_user_from_uid returning `user`."""
    stubs = {
        name: AutoMockModule(name)
        for name in (
            'firebase_admin',
            'firebase_admin.messaging',
            'firebase_admin.auth',
            'database.notifications',
            'database.redis_db',
            'utils.llm.notifications',
        )
    }
    stubs['database.auth'] = _module('database.auth', get_user_from_uid=lambda _uid: user)
    with stub_modules(stubs):
        yield load_module_fresh('utils.notifications', str(BACKEND_DIR / 'utils' / 'notifications.py'))


def _firebase_user(display_name: Any) -> dict:
    """Exactly the shape database.auth.get_user_from_uid returns."""
    return {
        'uid': 'u1',
        'email': 'a@b.c',
        'email_verified': True,
        'phone_number': None,
        'display_name': display_name,
        'photo_url': None,
        'disabled': False,
    }


def _capture_titles(notifications):
    sent = []
    notifications.send_notification = lambda uid, title, body, data=None: sent.append(title)
    return sent


@pytest.mark.parametrize('display_name', [None, ''])
def test_new_review_falls_back_when_the_reviewer_has_no_name(display_name):
    with _notifications_with_user(_firebase_user(display_name)) as notifications:
        titles = _capture_titles(notifications)
        notifications.send_new_app_review_notification('owner', 'reviewer', 'app1', 'Weather', 'Great!')
    assert titles == ['A user reviewed Weather']


@pytest.mark.parametrize('display_name', [None, ''])
def test_reply_falls_back_when_the_owner_has_no_name(display_name):
    with _notifications_with_user(_firebase_user(display_name)) as notifications:
        titles = _capture_titles(notifications)
        notifications.send_app_review_reply_notification('reviewer', 'owner', 'thanks!', 'app1', 'Weather')
    assert titles == ['The developer (Weather)']


def test_real_names_are_still_used():
    with _notifications_with_user(_firebase_user('Ada')) as notifications:
        titles = _capture_titles(notifications)
        notifications.send_new_app_review_notification('owner', 'reviewer', 'app1', 'Weather', 'Great!')
        notifications.send_app_review_reply_notification('reviewer', 'owner', 'thanks!', 'app1', 'Weather')
    assert titles == ['Ada reviewed Weather', 'Ada (Weather)']


def test_missing_user_record_still_falls_back():
    with _notifications_with_user(None) as notifications:
        titles = _capture_titles(notifications)
        notifications.send_new_app_review_notification('owner', 'reviewer', 'app1', 'Weather', 'Great!')
    assert titles == ['A user reviewed Weather']
