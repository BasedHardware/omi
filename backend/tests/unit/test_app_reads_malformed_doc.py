"""Stored app docs that are partial must not 500 the app reads that #19584 did not cover.

#19584 moved `GET /v1/apps/{app_id}` onto `App.deserialize_safe`, but two gaps remained:

  * `GET /v1/conversations/{id}/suggested-apps` still built `App(**app_data)`, so one
    malformed suggested app failed the whole response;
  * the availability helpers in `utils.apps` index `app['private']` on the raw doc before
    any route can deserialize it, so a doc without the field raised `KeyError`, including
    for the app's own owner.

Firestore's marketplace queries match `private == False` / `private == True`, and both
skip a doc without the field, so such an app was never public. The helpers therefore
treat a missing `private` as private: the owner (and testers) still see it, nobody else.
"""

from unittest.mock import MagicMock, patch

import utils.apps as apps_utils
from routers import conversations as conversations_router


def _app_doc(app_id='app_valid', **overrides):
    doc = {
        'id': app_id,
        'name': 'Test App',
        'category': 'productivity',
        'author': 'Tester',
        'description': 'A valid test application',
        'image': 'https://example.com/icon.png',
        'capabilities': ['chat'],
        'approved': True,
        'private': False,
        'uid': 'owner',
    }
    doc.update(overrides)
    return doc


def _without_private(doc):
    return {key: value for key, value in doc.items() if key != 'private'}


def _suggested_apps(app_docs):
    conversation = MagicMock()
    conversation.suggested_summarization_apps = list(app_docs)
    with patch.object(conversations_router, '_get_valid_conversation_by_id', return_value={}), patch.object(
        conversations_router, 'deserialize_conversation', return_value=conversation
    ), patch.object(
        apps_utils, 'get_available_app_by_id_with_reviews', side_effect=lambda app_id, uid: dict(app_docs[app_id])
    ), patch.object(
        apps_utils, 'get_is_user_paid_app', return_value=False
    ):
        return conversations_router.get_conversation_suggested_apps('conversation-1', uid='viewer')


def test_one_malformed_suggested_app_is_skipped_not_a_500():
    response = _suggested_apps({'good': _app_doc('good'), 'legacy': {'id': 'legacy', 'private': False}})

    assert [app['id'] for app in response['suggested_apps']] == ['good']


def _with_reviews(doc, uid):
    with patch.object(apps_utils, 'get_app_by_id_db', return_value=dict(doc)), patch.object(
        apps_utils, 'get_app_money_made_amount', return_value=0
    ), patch.object(apps_utils, 'get_app_usage_count', return_value=0), patch.object(
        apps_utils, 'get_app_reviews', return_value={}
    ), patch.object(
        apps_utils, 'is_tester', return_value=False
    ), patch.object(
        apps_utils, 'get_enabled_apps', return_value=[]
    ), patch.object(
        apps_utils, 'get_apps_installs_count', return_value={}
    ):
        return apps_utils.get_available_app_by_id_with_reviews('app_valid', uid)


def test_an_app_without_private_is_still_readable_by_its_owner():
    app = _with_reviews(_without_private(_app_doc()), uid='owner')

    assert app is not None and app['id'] == 'app_valid'
    assert app['money_made'] is None and app['usage_count'] is None


def test_an_app_without_private_is_hidden_from_other_users():
    assert _with_reviews(_without_private(_app_doc()), uid='someone-else') is None


def test_a_public_app_keeps_its_public_stats():
    app = _with_reviews(_app_doc(), uid='someone-else')

    assert app['money_made'] == 0 and app['usage_count'] == 0


def _available(doc, uid, cached=None):
    with patch.object(apps_utils, 'get_app_cache_by_id', return_value=cached), patch.object(
        apps_utils, 'get_app_by_id_db', return_value=dict(doc)
    ), patch.object(apps_utils, 'set_app_cache_by_id'), patch.object(apps_utils, 'is_tester', return_value=False):
        return apps_utils.get_available_app_by_id('app_valid', uid)


def test_the_availability_check_treats_a_missing_private_as_private():
    legacy = _without_private(_app_doc())

    assert _available(legacy, uid='owner')['id'] == 'app_valid'
    assert _available(legacy, uid='someone-else') is None


def test_a_cached_app_without_private_is_treated_the_same_way():
    legacy = _without_private(_app_doc())

    assert _available(legacy, uid='owner', cached=dict(legacy))['id'] == 'app_valid'
    assert _available(legacy, uid='someone-else', cached=dict(legacy)) is None
