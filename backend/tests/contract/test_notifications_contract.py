"""Dual-backend contract for push registration and cleanup (ADR-0044 facade + ADR-0002 store port).

`database/notifications.py` decides who receives a push, and it decides it with the two shapes covered
here — in the variant that matters most for this module: **across users**.

    collection_group   remove_invalid_token / remove_bulk_tokens sweep every user's `fcm_tokens`
                       subcollection to purge a dead token; get_users_endpoints_in_timezones sweeps
                       every user's UnifiedPush endpoints filtered by time zone, and remove_bulk_endpoints
                       sweeps them unfiltered. A parent the group query misses is a user whose dead token
                       is never purged — or, on the fan-out, a user who silently stops being notified.
    batch              remove_bulk_tokens deletes the matched documents per chunk, re-opening a batch
                       every 500 operations.

Both consequences are quiet: nothing fails, somebody just stops getting notifications, or a dead token
is retried forever. That is what makes them worth proving on the backend we deploy rather than assuming.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def fleet(bind_store):
    """Three users with one FCM token each, plus one user with two devices."""
    run = uuid.uuid4().hex[:8]
    uids = [f'push{i}-{run}' for i in range(3)]
    paths: list[str] = []

    def _token(uid: str, device: str, token: str):
        path = f'users/{uid}/fcm_tokens/{device}'
        bind_store.set(path, {'token': token, 'device_key': device, 'time_zone': 'Europe/Rome'})
        paths.append(path)

    for index, uid in enumerate(uids):
        _token(uid, 'phone', f'tok-{index}-{run}')
    _token(uids[0], 'tablet', f'tok-extra-{run}')

    yield {'uids': uids, 'run': run, 'store': bind_store, 'paths': paths}

    for path in paths:
        bind_store.delete(path)


def _exists(store, path) -> bool:
    stored = store.get(path)
    return stored is not None and stored.exists


# --- collection group: the cross-user sweep ---------------------------------------------------------


def test_a_dead_token_is_purged_from_whichever_user_holds_it(fleet):
    """The point of the group query. The token belongs to the THIRD user; a parent-scoped query would
    find nothing and the dead token would be retried on every future send, forever."""
    import database.notifications as notifications_db

    target = f"tok-2-{fleet['run']}"

    notifications_db.remove_invalid_token(target)

    assert not _exists(fleet['store'], f"users/{fleet['uids'][2]}/fcm_tokens/phone")
    assert _exists(fleet['store'], f"users/{fleet['uids'][0]}/fcm_tokens/phone"), 'only the dead one goes'


def test_purging_a_token_nobody_holds_is_a_no_op(fleet):
    """It runs on every 404/410 from the transport, including for tokens already cleaned up."""
    import database.notifications as notifications_db

    notifications_db.remove_invalid_token(f"never-registered-{fleet['run']}")

    for uid in fleet['uids']:
        assert _exists(fleet['store'], f'users/{uid}/fcm_tokens/phone')


def test_a_bulk_purge_reaches_every_user_and_every_device(fleet):
    """`in` over the group, then a batch delete. Two of the three users lose their phone token and the
    first also loses its tablet — the sweep must not stop at the first parent that matches."""
    import database.notifications as notifications_db

    notifications_db.remove_bulk_tokens([f"tok-0-{fleet['run']}", f"tok-2-{fleet['run']}", f"tok-extra-{fleet['run']}"])

    assert not _exists(fleet['store'], f"users/{fleet['uids'][0]}/fcm_tokens/phone")
    assert not _exists(fleet['store'], f"users/{fleet['uids'][0]}/fcm_tokens/tablet")
    assert not _exists(fleet['store'], f"users/{fleet['uids'][2]}/fcm_tokens/phone")
    assert _exists(fleet['store'], f"users/{fleet['uids'][1]}/fcm_tokens/phone"), 'the live token survives'


def test_a_bulk_purge_of_nothing_touches_nothing(fleet):
    import database.notifications as notifications_db

    notifications_db.remove_bulk_tokens([])

    for uid in fleet['uids']:
        assert _exists(fleet['store'], f'users/{uid}/fcm_tokens/phone')


def test_a_bulk_purge_larger_than_one_IN_chunk_still_reaches_everyone(fleet):
    """Firestore rejects an `in` with more than 30 values, so the module chunks. The token that matters
    is deliberately placed in the SECOND chunk: a build that only queried the first would leave it
    behind, and the caller cannot tell — the function returns None either way."""
    import database.notifications as notifications_db

    filler = [f'absent-{index}-{fleet["run"]}' for index in range(35)]

    notifications_db.remove_bulk_tokens(filler + [f"tok-1-{fleet['run']}"])

    assert not _exists(fleet['store'], f"users/{fleet['uids'][1]}/fcm_tokens/phone")


# --- collection group: the UnifiedPush fan-out ------------------------------------------------------


@pytest.fixture
def endpoints(bind_store):
    """UnifiedPush endpoints for three users, two in one time zone and one elsewhere."""
    run = uuid.uuid4().hex[:8]
    uids = [f'up{i}-{run}' for i in range(3)]
    paths: list[str] = []

    for index, uid in enumerate(uids):
        path = f'users/{uid}/unifiedpush_endpoints/phone'
        bind_store.set(
            path,
            {
                'endpoint': f'https://ntfy.invalid/{uid}',
                'device_key': 'phone',
                'time_zone': 'Europe/Rome' if index < 2 else 'America/New_York',
            },
        )
        paths.append(path)

    yield {'uids': uids, 'run': run, 'store': bind_store}

    for path in paths:
        bind_store.delete(path)


def test_the_timezone_fanout_finds_every_user_in_that_zone(endpoints):
    """The morning fan-out. A parent the group query misses is a user who silently stops being
    notified — no error anywhere, they just stop hearing from the product."""
    import database.notifications as notifications_db

    found = notifications_db.get_users_endpoints_in_timezones(['Europe/Rome'])

    urls = {endpoint.url for endpoint in found}
    assert f"https://ntfy.invalid/{endpoints['uids'][0]}" in urls
    assert f"https://ntfy.invalid/{endpoints['uids'][1]}" in urls
    assert f"https://ntfy.invalid/{endpoints['uids'][2]}" not in urls, 'the other zone must not be woken'


def test_an_empty_timezone_list_fans_out_to_nobody(endpoints):
    """A guard worth having on both backends: an unfiltered group query here would notify everyone."""
    import database.notifications as notifications_db

    assert notifications_db.get_users_endpoints_in_timezones([]) == []


def test_a_dead_endpoint_is_purged_from_every_user_that_registered_it(endpoints):
    """The same distributor URL can be registered by several devices; retiring it must purge all of
    them, so the unfiltered group sweep has to reach every parent."""
    import database.notifications as notifications_db

    shared = 'https://ntfy.invalid/shared'
    for uid in endpoints['uids'][:2]:
        endpoints['store'].set(
            f'users/{uid}/unifiedpush_endpoints/second',
            {'endpoint': shared, 'device_key': 'second', 'time_zone': 'Europe/Rome'},
        )

    try:
        notifications_db.remove_bulk_endpoints([shared])

        for uid in endpoints['uids'][:2]:
            assert not _exists(endpoints['store'], f'users/{uid}/unifiedpush_endpoints/second')
        assert _exists(endpoints['store'], f"users/{endpoints['uids'][0]}/unifiedpush_endpoints/phone")
    finally:
        for uid in endpoints['uids'][:2]:
            endpoints['store'].delete(f'users/{uid}/unifiedpush_endpoints/second')


def test_registering_an_endpoint_mirrors_the_timezone_onto_the_user(endpoints):
    """Parity with save_token, and the reason the fan-out works for UnifiedPush-only users: the
    timezone queries read the user doc, so an endpoint whose zone never reached it is unreachable."""
    import database.notifications as notifications_db

    uid = f"up-new-{endpoints['run']}"
    try:
        notifications_db.save_endpoint(
            uid, {'endpoint': 'https://ntfy.invalid/new', 'device_key': 'phone', 'time_zone': 'Europe/Rome'}
        )

        (stored,) = notifications_db.get_all_endpoints(uid)
        assert stored.url == 'https://ntfy.invalid/new'
        user = endpoints['store'].get(f'users/{uid}')
        assert user.exists and user.data.get('time_zone') == 'Europe/Rome'
    finally:
        endpoints['store'].delete(f'users/{uid}/unifiedpush_endpoints/phone')
        endpoints['store'].delete(f'users/{uid}')
