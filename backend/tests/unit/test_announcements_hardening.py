"""announcements router must reject unsafe ids and never leak store errors.

`backend/routers/announcements.py` forwarded `announcement_id` / `data.id`
straight into Firestore `.document(...)` and called the data layer bare, so:

* a `/` in the id retargeted the document path, `.`/`..` and `__x__` reached
  Firestore as invalid/reserved names and surfaced as an opaque 500,
* a whitespace-only `ADMIN_KEY` was accepted when the caller sent matching
  whitespace, and a non-ASCII key raised TypeError inside compare_digest,
* `version_type` values other than 'firmware' silently returned app features,
* blank `version` / `app_version` and an unbounded `limit` were accepted,
* every store failure propagated with the raw driver message.

This suite drives the router functions directly with the data layer stubbed, so
it needs no FastAPI client, no Firestore and no network. Run with:

    PYTHONPATH=backend python3 backend/tests/unit/test_announcements_hardening.py
"""

import os
import sys
import types

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

CALLS: list = []
FAIL_WITH: BaseException | None = None
STORE_RESULT: object = None


def _record(name):
    def _fn(*args, **kwargs):
        CALLS.append((name, args, kwargs))
        if FAIL_WITH is not None:
            raise FAIL_WITH
        return STORE_RESULT

    return _fn


def _load_module_under_test() -> types.ModuleType:
    """Import ``routers/announcements.py`` with its data layer and models stubbed."""
    import importlib.util
    from pathlib import Path

    from testing.import_isolation import AutoMockModule, stub_modules

    db = AutoMockModule('database.announcements')
    for name in (
        'create_announcement',
        'deactivate_announcement',
        'delete_announcement',
        'dismiss_announcement',
        'get_all_announcements',
        'get_announcement_by_id',
        'get_app_changelogs',
        'get_app_features',
        'get_firmware_features',
        'get_general_announcements',
        'get_pending_announcements',
        'get_recent_changelogs',
        'update_announcement',
    ):
        setattr(db, name, _record(name))

    models = AutoMockModule('models.announcement')

    from pydantic import BaseModel, ConfigDict

    class _Announcement(BaseModel):
        """Pydantic model: FastAPI rejects non-BaseModel response annotations."""

        model_config = ConfigDict(extra='allow')

        id: str
        type: str
        created_at: object = None
        active: bool = True
        app_version: object = None
        firmware_version: object = None
        device_models: object = None
        expires_at: object = None
        targeting: object = None
        display: object = None
        content: dict = {}

    models.Announcement = _Announcement
    models.AnnouncementType = str
    models.Display = _Announcement
    models.Targeting = _Announcement

    auth = AutoMockModule('utils.other.endpoints')
    auth.get_current_user_uid = lambda: 'uid1'

    path = Path(__file__).resolve().parents[2] / 'routers' / 'announcements.py'
    spec = importlib.util.spec_from_file_location('_announcements_under_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with stub_modules(
        {
            'database.announcements': db,
            'models.announcement': models,
            'utils.other.endpoints': auth,
        }
    ):
        spec.loader.exec_module(module)

    return module


an = _load_module_under_test()
HTTPException = an.HTTPException


def _reset(error=None, result=None) -> None:
    global FAIL_WITH, STORE_RESULT
    CALLS.clear()
    FAIL_WITH = error
    STORE_RESULT = result


def _raises(fn, status: int):
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == status, f'expected {status}, got {exc.status_code}'
        return exc
    raise AssertionError(f'expected HTTPException {status}')


# --- announcement id validation ---------------------------------------------


def test_require_announcement_id_rejects_unsafe_values():
    for bad in ['', '   ', '.', '..', 'a/b', 'a\\b', 'x\x00y', '__name__', '__x__']:
        _raises(lambda b=bad: an._require_announcement_id(b), 400)
    _raises(lambda: an._require_announcement_id(None), 400)
    _raises(lambda: an._require_announcement_id(7), 400)


def test_require_announcement_id_rejects_oversized_ids():
    _raises(lambda: an._require_announcement_id('a' * (an.MAX_ANNOUNCEMENT_ID_BYTES + 1)), 400)


def test_require_announcement_id_accepts_and_trims_normal_ids():
    assert an._require_announcement_id(' promo-2026 ') == 'promo-2026'
    # a single leading underscore is not a reserved name
    assert an._require_announcement_id('_draft') == '_draft'


def test_traversal_id_never_reaches_the_store():
    os.environ['ADMIN_KEY'] = 'k'
    _reset(result=None)
    _raises(lambda: an.get_announcement('../../users/uid1', secret_key='k'), 400)
    assert CALLS == []


def test_delete_with_separator_id_never_reaches_the_store():
    os.environ['ADMIN_KEY'] = 'k'
    _reset(result=None)
    _raises(lambda: an.delete_announcement_endpoint('a/b', secret_key='k'), 400)
    assert CALLS == []


# --- admin key ---------------------------------------------------------------


def test_whitespace_only_admin_key_is_rejected(monkeypatch=None):
    os.environ['ADMIN_KEY'] = '   '
    _raises(lambda: an._verify_admin_key('   '), 403)


def test_missing_admin_key_is_rejected():
    os.environ.pop('ADMIN_KEY', None)
    _raises(lambda: an._verify_admin_key('anything'), 403)


def test_wrong_key_is_rejected_and_right_key_passes():
    os.environ['ADMIN_KEY'] = ' super-secret '
    _raises(lambda: an._verify_admin_key('super-secret-x'), 403)
    an._verify_admin_key('super-secret')


def test_non_ascii_key_is_a_403_not_a_typeerror():
    os.environ['ADMIN_KEY'] = 'super-secret'
    _raises(lambda: an._verify_admin_key('süper-secret'), 403)


# --- query validation --------------------------------------------------------


def test_features_rejects_unknown_version_type_instead_of_falling_back():
    _reset(result=[])
    _raises(lambda: an.get_features(version='1.0', version_type='desktop'), 400)
    assert CALLS == []


def test_features_rejects_blank_version():
    _reset(result=[])
    _raises(lambda: an.get_features(version='   ', version_type='app'), 400)
    assert CALLS == []


def test_features_routes_both_documented_types():
    _reset(result=[])
    an.get_features(version='1.0.522', version_type='app')
    an.get_features(version='1.0.522', version_type='FIRMWARE', device_model='omi')
    assert [c[0] for c in CALLS] == ['get_app_features', 'get_firmware_features']


def test_pending_rejects_blank_app_version():
    _reset(result=[])
    _raises(
        lambda: an.get_pending_announcements_endpoint(
            app_version='  ', platform='ios', trigger='app_launch', uid='uid1'
        ),
        400,
    )
    assert CALLS == []


def test_pending_still_rejects_bad_platform_and_trigger():
    _reset(result=[])
    _raises(
        lambda: an.get_pending_announcements_endpoint(
            app_version='1.0', platform='desktop', trigger='app_launch', uid='uid1'
        ),
        400,
    )
    _raises(
        lambda: an.get_pending_announcements_endpoint(
            app_version='1.0', platform='ios', trigger='whenever', uid='uid1'
        ),
        400,
    )


def test_changelogs_clamps_limit_and_rejects_non_positive():
    _reset(result=[])
    # FastAPI's Query defaults are objects when the handler is called directly,
    # so the no-version branch needs explicit None.
    an.get_changelogs(from_version=None, to_version=None, max_version=None, limit=10**6)
    assert CALLS[-1][2]['limit'] == an.MAX_CHANGELOG_LIMIT
    _raises(lambda: an.get_changelogs(from_version=None, to_version=None, limit=0), 422)


# --- error boundaries --------------------------------------------------------


def test_store_failure_becomes_a_sanitized_500():
    _reset(error=RuntimeError('connection to 10.0.0.5:8080 refused; password=hunter2'))
    exc = _raises(lambda: an.get_announcements(last_checked_at=None), 500)
    assert 'hunter2' not in exc.detail and '10.0.0.5' not in exc.detail
    assert exc.detail == 'Announcement service unavailable'


def test_every_endpoint_is_guarded():
    os.environ['ADMIN_KEY'] = 'k'
    _reset(error=ValueError('boom'))
    calls = [
        lambda: an.get_changelogs(from_version=None, to_version=None, limit=5),
        lambda: an.get_features(version='1.0', version_type='app'),
        lambda: an.get_announcements(last_checked_at=None),
        lambda: an.get_pending_announcements_endpoint(
            app_version='1.0', platform='ios', trigger='app_launch', uid='uid1'
        ),
        lambda: an.dismiss_announcement_endpoint('promo', an.DismissAnnouncementRequest(), uid='uid1'),
        lambda: an.list_all_announcements(secret_key='k'),
        lambda: an.get_announcement('promo', secret_key='k'),
        lambda: an.update_announcement_endpoint('promo', an.UpdateAnnouncementRequest(), secret_key='k'),
        lambda: an.delete_announcement_endpoint('promo', secret_key='k'),
    ]
    for call in calls:
        _raises(call, 500)


def test_create_rejects_reserved_id_before_the_store():
    os.environ['ADMIN_KEY'] = 'k'
    _reset(result=None)
    data = an.CreateAnnouncementRequest(id='__name__', type='announcement', content={})
    _raises(lambda: an.create_announcement_endpoint(data, secret_key='k'), 400)
    assert CALLS == []


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f'PASS {test.__name__}')
        except AssertionError as exc:
            failures += 1
            print(f'FAIL {test.__name__}: {exc}')
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f'ERROR {test.__name__}: {type(exc).__name__}: {exc}')
    print(f'\n{len(tests) - failures}/{len(tests)} tests passed')
    sys.exit(1 if failures else 0)
