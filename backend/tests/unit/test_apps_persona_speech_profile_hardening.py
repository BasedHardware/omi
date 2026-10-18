"""Regression tests for #21867 — apps/persona/speech-profile hardening.

Covers: temp-file basename sanitize + finally cleanup, GCS logo
orphan/destroy ordering on validation failure, partial-PATCH pricing
fallback + negative-price 422, logo/cache cleanup on delete,
approve/reject 404-before-mutate + popular cache, rated_at fallback,
locked-memory filter in persona descriptions, and person_id='null'.
"""

import os
from unittest.mock import MagicMock

import pytest

import routers.apps as apps_router
import routers.speech_profile as sp_router
import utils.apps as apps_utils

# ---------- helpers ----------


class _Upload:
    def __init__(self, name='x.png', data=b'x'):
        self.filename = name
        import io

        self.file = io.BytesIO(data)

    async def read(self):
        return self.file.getvalue()


# ---------- speech_profile: basename + finally + person_id ----------


def test_upload_profile_sanitizes_filename_and_cleans_temp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    captured = {}

    def fake_inner(path, uid):
        captured['path'] = path
        raise RuntimeError('fail')

    monkeypatch.setattr(sp_router, '_upload_profile_inner', fake_inner)
    with pytest.raises(RuntimeError):
        sp_router.upload_profile(_Upload('../../evil.wav'), uid='u1')
    # path sanitized — only basename survived
    assert captured['path'].endswith('/evil.wav') and '..' not in captured['path'].split('/')[-1]
    # temp file removed despite the failure
    assert not os.path.exists(captured['path'])


def test_get_extra_speech_profile_samples_null_person(monkeypatch):
    called = []
    monkeypatch.setattr(sp_router, 'get_additional_profile_recordings', lambda uid: called.append(uid) or [])
    monkeypatch.setattr(sp_router, 'get_user_person_speech_samples', lambda u, p: [{'p': p}])
    sp_router.get_extra_speech_profile_samples(person_id='null', uid='u')
    assert called == ['u']
    sp_router.get_extra_speech_profile_samples(person_id='p1', uid='u')
    assert called == ['u']  # person path does not hit the fallback


# ---------- update_app_review rated_at ----------


def test_update_app_review_legacy_missing_rated_at(monkeypatch):
    app = MagicMock(uid='other', private=False)
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda a, u: app)
    monkeypatch.setattr(apps_router, '_safe_app_from_dict', lambda a: app)
    monkeypatch.setattr(apps_router, 'get_specific_user_review', lambda a, u: {'score': 4, 'username': 'x'})
    saved = {}
    monkeypatch.setattr(apps_router, 'set_app_review', lambda a, u, d: saved.update(d))
    monkeypatch.setattr(apps_router, 'send_new_app_review_notification', lambda **k: None)
    req = MagicMock(score=5, review='ok', username=None)
    apps_router.update_app_review('a1', req, uid='u')
    assert saved['rated_at']  # fell back to a fresh timestamp instead of KeyError


# ---------- approve/reject 404 ordering ----------


def test_approve_app_404s_before_mutating(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'k')
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda a, u: None)
    called = []
    monkeypatch.setattr(apps_router, 'change_app_approval_status', lambda a, v: called.append(v))
    import fastapi

    with pytest.raises(fastapi.HTTPException) as exc:
        apps_router.approve_app('missing', 'u', secret_key='k')
    assert exc.value.status_code == 404
    assert not called


def test_reject_app_404s_before_mutating(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'k')
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda a, u: None)
    called = []
    monkeypatch.setattr(apps_router, 'change_app_approval_status', lambda a, v: called.append(v))
    import fastapi

    with pytest.raises(fastapi.HTTPException) as exc:
        apps_router.reject_app('missing', 'u', secret_key='k')
    assert exc.value.status_code == 404
    assert not called


def test_approve_app_invalidates_popular_cache(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'k')
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda a, u: {'name': 'app', 'is_popular': True})
    calls = {'approved': [], 'popular': 0}
    monkeypatch.setattr(apps_router, 'change_app_approval_status', lambda a, v: calls['approved'].append(v))
    monkeypatch.setattr(apps_router, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_router, 'invalidate_popular_apps_cache', lambda: calls.__setitem__('popular', 1))
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda a: None)
    monkeypatch.setattr(apps_router, 'send_notification', lambda *a: None)
    apps_router.approve_app('a1', 'u', secret_key='k')
    assert calls['popular'] == 1


# ---------- delete_app logo + popular cache ----------


def test_delete_app_removes_gcs_logo_and_popular_cache(monkeypatch):
    app = {'uid': 'u', 'approved': False, 'is_popular': True, 'image': 'https://storage.googleapis.com/bucket/logo.png'}
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda a, u: app)
    calls = {'logo': [], 'popular': 0}
    monkeypatch.setattr(apps_router, 'delete_app_logo', lambda img: calls['logo'].append(img))
    monkeypatch.setattr(apps_router, 'delete_app_from_db', lambda a: None)
    monkeypatch.setattr(apps_router, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_router, 'invalidate_popular_apps_cache', lambda: calls.__setitem__('popular', 1))
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda a: None)
    apps_router.delete_app('a1', uid='u')
    assert calls['logo'] == [app['image']]
    assert calls['popular'] == 1


# ---------- delete_persona logo + caches ----------


def test_delete_persona_removes_logo_and_caches(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'k')
    persona = {'approved': True, 'image': 'https://storage.googleapis.com/bucket/p.png'}
    monkeypatch.setattr(apps_router, 'get_persona_by_id_db', lambda p: persona)
    calls = {'logo': [], 'approved': 0, 'cache': []}
    monkeypatch.setattr(apps_router, 'delete_app_logo', lambda img: calls['logo'].append(img))
    monkeypatch.setattr(apps_router, 'delete_persona_db', lambda p: None)
    monkeypatch.setattr(apps_router, 'invalidate_approved_apps_cache', lambda: calls.__setitem__('approved', 1))
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda i: calls['cache'].append(i))
    apps_router.delete_persona('p1', secret_key='k')
    assert calls['logo'] == [persona['image']]
    assert calls['approved'] == 1
    assert calls['cache'] == ['p1']


# ---------- generate_persona_desc locked filter ----------


def test_generate_persona_desc_filters_locked(monkeypatch):
    locked = MagicMock()
    locked.is_locked = True
    open_m = MagicMock()
    open_m.is_locked = False
    open_m.dict.return_value = {'content': 'ok'}
    svc = MagicMock()
    svc.read.return_value = [locked, open_m]
    monkeypatch.setattr(apps_utils, 'MemoryService', lambda db_client=None: svc)
    got = {}
    monkeypatch.setattr(apps_utils, 'generate_persona_description', lambda ms, n: got.update(m=ms) or 'desc')
    monkeypatch.setattr(apps_utils, 'track_usage', lambda *a, **k: __import__('contextlib').nullcontext())
    out = apps_utils.generate_persona_desc('u', 'name')
    assert got['m'] == [{'content': 'ok'}]
    assert out == 'desc'


# ---------- update_app: pricing fallback + negative price + logo ordering ----------


def _patch_update_app_env(monkeypatch, stored=None):
    app = dict(stored or {'uid': 'u', 'image': '', 'approved': False})
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda a, u: app)
    monkeypatch.setattr(apps_router, 'parse_form_json', lambda t, d, n: dict(d))
    monkeypatch.setattr(apps_router, 'update_app_in_db', lambda d: None)
    monkeypatch.setattr(apps_router, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda a: None)
    monkeypatch.setattr(apps_router, 'backfill_app_home_url_from_auth_steps', lambda e: None)
    calls = {}
    monkeypatch.setattr(apps_router, 'upsert_app_payment_link', lambda *a, **k: calls.setdefault('pay', a))
    return app, calls


def test_update_app_partial_patch_keeps_stored_pricing(monkeypatch):
    app, calls = _patch_update_app_env(
        monkeypatch, stored={'uid': 'u', 'is_paid': True, 'price': 9.99, 'payment_plan': 'monthly', 'approved': False}
    )
    # AppUpdate validate may complain about missing requireds — monkeypatch it
    monkeypatch.setattr(
        apps_router,
        'AppUpdate',
        MagicMock(model_validate=lambda d: MagicMock(model_dump=lambda exclude_unset=True: {'name': 'x'})),
    )
    monkeypatch.setattr(apps_router, '_process_chat_tools_manifest', lambda e, d: d)
    apps_router.update_app('a1', app_data={'name': 'x'}, file=None, uid='u')
    paid, price, plan = calls['pay'][1], calls['pay'][2], calls['pay'][3]
    assert paid is True and price == 9.99 and plan == 'monthly'


def test_update_app_rejects_negative_price(monkeypatch):
    _patch_update_app_env(monkeypatch)
    monkeypatch.setattr(
        apps_router,
        'AppUpdate',
        MagicMock(model_validate=lambda d: MagicMock(model_dump=lambda exclude_unset=True: {'price': -1})),
    )
    import fastapi

    with pytest.raises(fastapi.HTTPException) as exc:
        apps_router.update_app('a1', app_data={'price': -1.0}, file=None, uid='u')
    assert exc.value.status_code == 422


def test_update_app_does_not_destroy_old_logo_on_422(monkeypatch):
    stored = {'uid': 'u', 'image': 'https://storage.googleapis.com/b/old.png', 'approved': False}
    _patch_update_app_env(monkeypatch, stored=stored)
    monkeypatch.setattr(apps_router, 'upload_app_logo', lambda p, a: 'https://storage.googleapis.com/b/new.png')
    deleted = []
    monkeypatch.setattr(apps_router, 'delete_app_logo', lambda img: deleted.append(img))

    class BadModel:
        @staticmethod
        def model_validate(d):
            raise apps_router.ValidationError.from_exception_data('AppUpdate', [])

    monkeypatch.setattr(apps_router, 'AppUpdate', BadModel)
    import fastapi

    with pytest.raises(fastapi.HTTPException):
        apps_router.update_app('a1', app_data={'name': 'x'}, file=_Upload(), uid='u')
    assert deleted == []


def test_delete_persona_without_image_does_not_touch_gcs(monkeypatch):
    """Legacy persona rows carry no image key — delete must not call GCS."""
    monkeypatch.setenv('ADMIN_KEY', 'k')
    monkeypatch.setattr(apps_router, 'get_persona_by_id_db', lambda p: {'approved': False})
    calls = {'logo': []}
    monkeypatch.setattr(apps_router, 'delete_app_logo', lambda img: calls['logo'].append(img))
    monkeypatch.setattr(apps_router, 'delete_persona_db', lambda p: None)
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda i: None)
    apps_router.delete_persona('p-legacy', secret_key='k')
    assert calls['logo'] == []
