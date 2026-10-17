from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi import HTTPException

import database.affiliates as affiliates_db
from config import affiliate as affiliate_config
from testing.import_isolation import load_module_fresh, stub_modules
from utils.affiliates import goaffpro, service
from utils.affiliates.ref_code import validate_ref_code

AFFILIATES_ROUTER_PATH = Path(__file__).resolve().parents[2] / 'routers' / 'affiliates.py'


# ----------------------------------------------------------------------------- fakes


class _Snapshot:
    def __init__(self, data: dict[str, Any] | None):
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class _Ref:
    def __init__(self, store: dict[str, dict[str, Any]], key: str):
        self._store = store
        self._key = key

    def get(self, transaction: Any = None, field_paths: Any = None) -> _Snapshot:
        return _Snapshot(self._store.get(self._key))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        self._store[self._key] = {**self._store.get(self._key, {}), **data} if merge else dict(data)

    def delete(self) -> None:
        self._store.pop(self._key, None)


class _Collection:
    def __init__(self, store: dict[str, dict[str, Any]], name: str):
        self._store = store
        self._name = name

    def document(self, doc_id: str) -> _Ref:
        return _Ref(self._store, f'{self._name}/{doc_id}')


class _Client:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> _Collection:
        return _Collection(self.store, name)


class _Transaction:
    def set(self, ref: _Ref, data: dict[str, Any], merge: bool = False) -> None:
        ref.set(data, merge=merge)


@pytest.fixture
def fake_db(monkeypatch):
    client = _Client()
    monkeypatch.setattr(affiliates_db.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(affiliates_db, 'run_transactional', lambda _client, fn: fn(_Transaction()))
    monkeypatch.setattr(affiliates_db, 'get_customer_firestore_client', lambda: client)
    return client


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('AFFILIATE_NATIVE_ENABLED', 'true')
    monkeypatch.setenv('AFFILIATE_NATIVE_UID_ALLOWLIST', 'uid-1,uid-2')
    monkeypatch.setenv('AFFILIATE_NATIVE_PERCENT', '0')
    monkeypatch.setenv('GOAFFPRO_ACCESS_TOKEN', 'admin-token')
    monkeypatch.setenv('GOAFFPRO_PUBLIC_TOKEN', 'public-token')


def _identity(monkeypatch, email='person@example.com', verified=True, name='Person'):
    monkeypatch.setattr(
        service, '_identity', lambda uid: service.OmiIdentity(email=email, email_verified=verified, name=name)
    )


# ----------------------------------------------------------------------------- ref code


@pytest.mark.parametrize('code', ['jane', 'lifesaver-co', 'omi-jane', 'Jane_Doe2'])
def test_ref_code_accepts_brand_neutral_codes(code):
    result = validate_ref_code(code)
    assert result.ok
    assert result.normalized == code.lower()


@pytest.mark.parametrize(
    ('code', 'reason'),
    [
        ('ab', 'length'),
        ('a' * 33, 'length'),
        ('1jane', 'format'),
        ('jane doe', 'format'),
        ('save', 'blocked'),
        ('save20', 'blocked'),
        ('omi', 'blocked'),
        ('omisupport', 'blocked'),
        ('omi-team', 'blocked'),
        ('test', 'blocked'),
    ],
)
def test_ref_code_rejects_discount_brand_and_malformed_codes(code, reason):
    result = validate_ref_code(code)
    assert not result.ok
    assert result.reason == reason


# ----------------------------------------------------------------------------- rollout gate


def test_native_page_is_off_by_default_and_without_tokens(monkeypatch):
    monkeypatch.delenv('AFFILIATE_NATIVE_ENABLED', raising=False)
    assert not affiliate_config.native_enabled('uid-1')
    monkeypatch.setenv('AFFILIATE_NATIVE_ENABLED', 'true')
    monkeypatch.setenv('AFFILIATE_NATIVE_UID_ALLOWLIST', 'uid-1')
    monkeypatch.delenv('GOAFFPRO_ACCESS_TOKEN', raising=False)
    monkeypatch.delenv('GOAFFPRO_PUBLIC_TOKEN', raising=False)
    assert not affiliate_config.native_enabled('uid-1')


def test_native_page_admits_allowlist_and_full_percent_only(enabled, monkeypatch):
    assert affiliate_config.native_enabled('uid-1')
    assert not affiliate_config.native_enabled('someone-else')
    monkeypatch.setenv('AFFILIATE_NATIVE_PERCENT', '100')
    assert affiliate_config.native_enabled('someone-else')
    monkeypatch.setenv('AFFILIATE_NATIVE_PERCENT', 'nan-ish')
    assert not affiliate_config.native_enabled('someone-else')


# ----------------------------------------------------------------------------- link storage


def test_link_is_one_to_one_between_accounts_and_affiliates(fake_db):
    assert affiliates_db.link_affiliate('uid-1', '42', 'email_match') == 'linked'
    assert affiliates_db.get_linked_affiliate_id('uid-1') == '42'
    assert affiliates_db.link_affiliate('uid-1', '42', 'email_match') == 'already_linked'
    assert affiliates_db.link_affiliate('uid-2', '42', 'affiliate_login') == 'affiliate_taken'
    assert affiliates_db.link_affiliate('uid-1', '43', 'joined') == 'account_has_other'
    assert fake_db.store['affiliate_links/42']['uid'] == 'uid-1'


def test_account_deletion_releases_the_affiliate_for_relinking(fake_db):
    affiliates_db.link_affiliate('uid-1', '42', 'email_match')
    affiliates_db.delete_affiliate_link('uid-1')
    assert 'affiliate_links/42' not in fake_db.store
    assert affiliates_db.link_affiliate('uid-2', '42', 'affiliate_login') == 'linked'


# ----------------------------------------------------------------------------- service


def test_status_reports_unavailable_when_rollout_excludes_uid(monkeypatch):
    monkeypatch.delenv('AFFILIATE_NATIVE_ENABLED', raising=False)
    result = service.status('uid-1')
    assert result.native_enabled is False
    assert result.state == 'unavailable'


def test_status_offers_email_match_only_for_verified_email(enabled, fake_db, monkeypatch):
    monkeypatch.setattr(goaffpro, 'find_affiliate_by_email', lambda email: {'id': 7, 'status': 'approved'})
    _identity(monkeypatch, verified=True)
    assert service.status('uid-1').email_match_available is True
    _identity(monkeypatch, verified=False)
    assert service.status('uid-1').email_match_available is False


def test_linked_status_returns_profile_with_referral_link(enabled, fake_db, monkeypatch):
    affiliates_db.link_affiliate('uid-1', '7', 'email_match')
    monkeypatch.setattr(
        goaffpro,
        'get_affiliate',
        lambda affiliate_id, fields='': {'id': 7, 'status': 'approved', 'ref_code': 'JANE', 'coupon': 'JANE10'},
    )
    result = service.status('uid-1')
    assert result.state == 'linked'
    assert result.profile is not None
    assert result.profile.referral_url == 'https://www.omi.me/?ref=JANE'
    assert result.profile.coupon == 'JANE10'


def test_blocked_affiliate_never_sees_data(enabled, fake_db, monkeypatch):
    affiliates_db.link_affiliate('uid-1', '7', 'email_match')
    monkeypatch.setattr(goaffpro, 'get_affiliate', lambda affiliate_id, fields='': {'id': 7, 'status': 'Blocked'})
    assert service.status('uid-1').state == 'blocked'
    with pytest.raises(service.AffiliateBlocked):
        service.stats('uid-1')


def test_link_by_email_requires_a_verified_match(enabled, fake_db, monkeypatch):
    _identity(monkeypatch, verified=False)
    monkeypatch.setattr(goaffpro, 'find_affiliate_by_email', lambda email: {'id': 7, 'status': 'approved'})
    with pytest.raises(service.AffiliateLinkRejected, match='no_email_match'):
        service.link_by_email('uid-1')
    _identity(monkeypatch, verified=True)
    service.link_by_email('uid-1')
    assert affiliates_db.get_linked_affiliate_id('uid-1') == '7'


def test_link_by_credentials_rejects_wrong_password_without_lookup(enabled, fake_db, monkeypatch):
    lookups: list[str] = []
    monkeypatch.setattr(goaffpro, 'verify_credentials', lambda email, password: False)
    monkeypatch.setattr(goaffpro, 'find_affiliate_by_email', lambda email: lookups.append(email))
    with pytest.raises(service.AffiliateLinkRejected, match='invalid_credentials'):
        service.link_by_credentials('uid-1', 'Aff@Example.com', 'wrong')
    assert lookups == []


def test_link_by_credentials_links_the_affiliate_behind_a_different_email(enabled, fake_db, monkeypatch):
    monkeypatch.setattr(goaffpro, 'verify_credentials', lambda email, password: email == 'aff@example.com')
    monkeypatch.setattr(goaffpro, 'find_affiliate_by_email', lambda email: {'id': 9, 'status': 'approved'})
    service.link_by_credentials('uid-1', ' Aff@Example.com ', 'secret')
    assert affiliates_db.get_linked_affiliate_id('uid-1') == '9'


def test_affiliate_already_linked_elsewhere_cannot_be_claimed(enabled, fake_db, monkeypatch):
    affiliates_db.link_affiliate('uid-1', '9', 'email_match')
    monkeypatch.setattr(goaffpro, 'verify_credentials', lambda email, password: True)
    monkeypatch.setattr(goaffpro, 'find_affiliate_by_email', lambda email: {'id': 9, 'status': 'approved'})
    with pytest.raises(service.AffiliateLinkRejected, match='affiliate_taken'):
        service.link_by_credentials('uid-2', 'aff@example.com', 'secret')


def test_join_reuses_an_existing_affiliate_instead_of_duplicating(enabled, fake_db, monkeypatch):
    _identity(monkeypatch)
    created: list[str] = []
    monkeypatch.setattr(goaffpro, 'find_affiliate_by_email', lambda email: {'id': 5, 'status': 'approved'})
    monkeypatch.setattr(goaffpro, 'create_affiliate', lambda name, email: created.append(email) or '6')
    service.join('uid-1')
    assert created == []
    assert affiliates_db.get_linked_affiliate_id('uid-1') == '5'


def test_join_creates_an_approved_affiliate_from_the_omi_account(enabled, fake_db, monkeypatch):
    _identity(monkeypatch, email='new@example.com', name='New Person')
    created: list[tuple[str, str]] = []
    monkeypatch.setattr(goaffpro, 'find_affiliate_by_email', lambda email: None)
    monkeypatch.setattr(goaffpro, 'create_affiliate', lambda name, email: created.append((name, email)) or '6')
    service.join('uid-1')
    assert created == [('New Person', 'new@example.com')]
    assert fake_db.store['users/uid-1']['affiliate']['method'] == 'joined'


def test_join_requires_a_verified_email(enabled, fake_db, monkeypatch):
    _identity(monkeypatch, verified=False)
    with pytest.raises(service.AffiliateLinkRejected, match='email_not_verified'):
        service.join('uid-1')


def test_stats_combine_sale_and_other_commission(enabled, fake_db, monkeypatch):
    affiliates_db.link_affiliate('uid-1', '7', 'email_match')
    monkeypatch.setattr(goaffpro, 'get_affiliate', lambda affiliate_id, fields='': {'id': 7, 'status': 'approved'})

    def user_get(affiliate_id, path, params=None):
        if path == '/sdk/user/stats/aggregate':
            return {
                'data': [
                    {
                        'total_sales': '3',
                        'revenue_generated': '300.5',
                        'sale_commission_earned': '30',
                        'other_commission_earned': '5',
                        'commission_paid': '10',
                    }
                ]
            }
        return {'count': 120}

    monkeypatch.setattr(goaffpro, 'user_get', user_get)
    result = service.stats('uid-1')
    assert (result.total_orders, result.total_clicks) == (3, 120)
    assert (result.total_commission, result.paid_commission, result.unpaid_commission) == (35.0, 10.0, 25.0)


def test_update_ref_code_rejects_taken_codes(enabled, fake_db, monkeypatch):
    affiliates_db.link_affiliate('uid-1', '7', 'email_match')
    monkeypatch.setattr(
        goaffpro, 'get_affiliate', lambda affiliate_id, fields='': {'id': 7, 'status': 'approved', 'ref_code': 'OLD'}
    )
    monkeypatch.setattr(goaffpro, 'ref_code_taken_by_other', lambda code, affiliate_id: True)
    with pytest.raises(service.RefCodeRejected) as error:
        service.update_ref_code('uid-1', 'jane')
    assert error.value.conflict


def test_payout_setup_requires_country_for_a_new_account(enabled, fake_db, monkeypatch):
    affiliates_db.link_affiliate('uid-1', '7', 'email_match')
    monkeypatch.setattr(goaffpro, 'get_affiliate', lambda affiliate_id, fields='': {'id': 7, 'status': 'approved'})
    monkeypatch.setattr(goaffpro, 'user_get', lambda affiliate_id, path, params=None: {'user': {'payment_details': {}}})
    with pytest.raises(service.PayoutSetupRejected, match='country_required'):
        service.payout_setup_link('uid-1', None)


# ----------------------------------------------------------------------------- router


_ROUTER: list[ModuleType] = []


@contextmanager
def _loaded_router() -> Iterator[ModuleType]:
    # Loaded once: a fresh reload re-registers process-wide Prometheus collectors.
    if not _ROUTER:
        endpoints = ModuleType('utils.other.endpoints')
        endpoints.get_current_user_uid = lambda: 'uid-1'
        endpoints.with_rate_limit = lambda dependency, policy_name, **kwargs: dependency
        with stub_modules({'utils.other.endpoints': endpoints}):
            _ROUTER.append(load_module_fresh('routers.affiliates', str(AFFILIATES_ROUTER_PATH)))
    yield _ROUTER[0]


@pytest.mark.parametrize(
    ('error', 'status_code', 'detail'),
    [
        (service.AffiliateUnavailable(), 404, 'affiliate_unavailable'),
        (service.AffiliateNotLinked(), 409, 'affiliate_not_linked'),
        (service.AffiliateBlocked(), 403, 'affiliate_blocked'),
        (service.AffiliateLinkRejected('invalid_credentials'), 400, 'invalid_credentials'),
        (service.AffiliateLinkRejected('affiliate_taken'), 409, 'affiliate_taken'),
        (goaffpro.GoAffProError(500, 'admin_get'), 502, 'affiliate_service_unavailable'),
    ],
)
def test_router_maps_service_errors_without_leaking_provider_detail(monkeypatch, error, status_code, detail):
    with _loaded_router() as router:

        def raise_error(uid):
            raise error

        monkeypatch.setattr(router.service, 'stats', raise_error)
        with pytest.raises(HTTPException) as raised:
            router.get_affiliate_stats(uid='uid-1')
    assert raised.value.status_code == status_code
    assert raised.value.detail == detail


def test_router_credentials_link_never_echoes_the_password(monkeypatch):
    with _loaded_router() as router:
        seen: list[tuple[str, str, str]] = []
        monkeypatch.setattr(router.service, 'link_by_credentials', lambda uid, e, p: seen.append((uid, e, p)))
        monkeypatch.setattr(
            router.service,
            'status',
            lambda uid: router.AffiliateStatusResponse(native_enabled=True, state='linked'),
        )
        monkeypatch.setattr(router, 'emit_posthog_event', lambda *args: None)
        body = router.AffiliateLinkCredentialsRequest(email='aff@example.com', password='hunter2')
        response = router.link_affiliate_by_credentials(body, uid='uid-1')
    assert seen == [('uid-1', 'aff@example.com', 'hunter2')]
    assert 'hunter2' not in response.model_dump_json()
    assert response.method == 'affiliate_login'


def test_goaffpro_blocked_status_is_case_insensitive():
    assert goaffpro.is_blocked('Suspended')
    assert not goaffpro.is_blocked('approved')
    assert not goaffpro.is_blocked(None)


def test_goaffpro_login_tokens_are_cached_server_side(monkeypatch):
    calls: list[str] = []
    goaffpro._login_tokens.clear()
    monkeypatch.setattr(
        goaffpro, 'get_affiliate', lambda affiliate_id, fields='': calls.append(affiliate_id) or {'login_token': 'tok'}
    )
    assert goaffpro.login_token('7') == 'tok'
    assert goaffpro.login_token('7') == 'tok'
    assert calls == ['7']
    goaffpro._login_tokens.clear()


def test_service_identity_uses_firebase_verified_email(monkeypatch):
    user = SimpleNamespace(email='Person@Example.com', email_verified=True, display_name='')
    monkeypatch.setattr(service.firebase_admin.auth, 'get_user', lambda uid: user)
    identity = service._identity('uid-1')
    assert identity == service.OmiIdentity(email='person@example.com', email_verified=True, name='person')
