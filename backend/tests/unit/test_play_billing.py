"""Google Play Billing: verify/bind, every RTDN state, replay, cross-account tokens, Stripe exclusivity,
the server switch and its build gate, and byte-identical responses with the switch off."""

import base64
import json
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from config import play_billing as config  # noqa: E402
from database import play_subscriptions as play_db  # noqa: E402
from models.users import PlanType, Subscription, SubscriptionStatus, UserSubscriptionResponse  # noqa: E402
from utils import play_billing  # noqa: E402

UID = 'fixture-user'
OTHER = 'fixture-other'
TOKEN = 'play-token-1'
NOW = int(time.time())
DAY = 86400
TEST_ACCOUNT_KEY = 'test-only-account-id-key-0123456789abcdef'
KEY_ENV = 'PLAY_ACCOUNT_ID_HMAC_KEY'


def _iso(seconds):
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace('+00:00', 'Z')


def resource(state='SUBSCRIPTION_STATE_ACTIVE', *, expiry=NOW + 30 * DAY, account=None, renew=True, **over):
    data = {
        'subscriptionState': state,
        'startTime': _iso(NOW - DAY),
        'acknowledgementState': 'ACKNOWLEDGEMENT_STATE_PENDING',
        'externalAccountIdentifiers': {
            'obfuscatedExternalAccountId': account or play_billing.obfuscated_account_id(UID)
        },
        'lineItems': [
            {
                'productId': 'omi_pro',
                'expiryTime': _iso(expiry),
                'autoRenewingPlan': {'autoRenewEnabled': renew},
                'offerDetails': {'basePlanId': 'monthly', 'offerId': 'trial-7d'},
            }
        ],
    }
    data.update(over)
    return data


class FakePublisher:
    def __init__(self):
        self.resources = {}
        self.acks = []
        self.fail = None

    def get_subscription(self, package_name, token):
        assert package_name == 'com.friend.ios'
        if self.fail:
            raise self.fail
        if token not in self.resources:
            raise play_billing.PurchaseNotFound()
        return self.resources[token]

    def acknowledge(self, package_name, product_id, token):
        assert (package_name, product_id) == ('com.friend.ios', 'omi_pro')
        self.acks.append(token)
        self.resources[token]['acknowledgementState'] = 'ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED'


class FakeStore:
    def __init__(self):
        self.docs = {}
        self.users = {}
        self.accounts = {}

    token_key = staticmethod(play_db.token_key)
    USER_POINTER_FIELD = play_db.USER_POINTER_FIELD
    PENDING_FIELD = play_db.PENDING_FIELD
    CUSTOMER_FIELD = play_db.CUSTOMER_FIELD
    DELETION_CONFIRMED_FIELD = play_db.DELETION_CONFIRMED_FIELD
    BOUND_FIELD = play_db.BOUND_FIELD

    @property
    def pointers(self):
        return {uid: f[self.USER_POINTER_FIELD] for uid, f in self.users.items() if f.get(self.USER_POINTER_FIELD)}

    def get_purchase(self, key):
        return dict(self.docs[key]) if key in self.docs else None

    def bind_purchase(self, key, uid, record):
        if key not in self.docs or not self.docs[key].get('uid'):
            self.docs[key] = {**self.docs.get(key, {}), **record, 'uid': uid}
            return uid
        if self.docs[key]['uid'] == uid:
            self.docs[key].update({k: v for k, v in record.items() if k != 'uid'})
        return self.docs[key]['uid']

    def record_unbound(self, key, record):
        self.docs.setdefault(key, {}).update({k: v for k, v in record.items() if k != 'uid'})

    def update_purchase(self, key, fields):
        self.docs.setdefault(key, {}).update({k: v for k, v in fields.items() if k != 'uid'})

    def purchase_keys_for_uid(self, uid):
        return [key for key, doc in self.docs.items() if doc.get('uid') == uid]

    def compare_and_set(self, key, field, value, can_replace):
        # Sequential only; the real helper's atomicity is tested against interleaved callers.
        if key not in self.docs or not can_replace(self.docs[key].get(field)):
            return False
        self.docs[key][field] = value
        return True

    def mark_once(self, key, field, value):
        return self.compare_and_set(key, field, value, lambda current: not current)

    def mark_play_history(self, uid):
        self.set_user_fields(uid, {self.BOUND_FIELD: True})

    def due_for_reconcile(self, now, limit):
        rows = [dict(v, _key=k) for k, v in self.docs.items() if v.get('next_check_at') and v['next_check_at'] <= now]
        return rows[:limit]

    def get_user_fields(self, uid):
        return dict(self.users.get(uid, {}))

    def set_user_fields(self, uid, fields):
        self.users.setdefault(uid, {}).update(fields)

    def get_user_pointer(self, uid):
        return self.users.get(uid, {}).get(self.USER_POINTER_FIELD)

    def set_user_pointer(self, uid, key):
        self.set_user_fields(uid, {self.USER_POINTER_FIELD: key})

    def remember_account(self, account, uid):
        self.accounts.setdefault(account, uid)

    def account_uid(self, account):
        return self.accounts.get(account)


class FakeUsers:
    def __init__(self):
        self.rows = {}
        self.writes = []
        self.customers = {}

    def get_user_subscription(self, uid):
        return Subscription.model_validate(self.rows.get(uid, {'plan': 'basic'}))

    def get_user_valid_subscription(self, uid, **_):
        sub = self.get_user_subscription(uid)
        if sub.plan == PlanType.basic:
            return sub
        if sub.current_period_end and sub.current_period_end >= int(time.time()):
            return sub
        return Subscription()

    def update_user_subscription(self, uid, data):
        self.rows[uid] = dict(data)
        self.writes.append((uid, dict(data)))

    def get_stripe_customer_id(self, uid):
        return self.customers.get(uid)


@pytest.fixture
def env(monkeypatch):
    store, users, publisher = FakeStore(), FakeUsers(), FakePublisher()
    effects = []
    monkeypatch.setattr(play_billing, 'play_db', store)
    monkeypatch.setattr(play_billing, 'users_db', users)
    monkeypatch.setattr(play_billing, '_publisher', publisher)
    monkeypatch.setattr(play_billing, 'account_deletion_blocks_user_work', lambda uid: False)
    monkeypatch.setattr(
        play_billing, 'redis_db', SimpleNamespace(set_credits_invalidation_signal=lambda uid: effects.append('credits'))
    )
    for name, label in (
        ('conversations_db', 'unlock_all_conversations'),
        ('memories_db', 'unlock_all_memories'),
        ('action_items_db', 'unlock_all_action_items'),
    ):
        monkeypatch.setattr(
            play_billing, name, SimpleNamespace(**{label: lambda uid, label=label: effects.append(label)})
        )
    monkeypatch.setattr(play_billing, 'clear_fair_use_on_upgrade', lambda uid: effects.append('fair_use'))
    stripe_subs = []

    def stripe_list(limit=10, status=None, **_):
        # Like Stripe: one page in ``data``, every page through auto_paging_iter, default list hides ended ones.
        shown = [s for s in stripe_subs if status == 'all' or s.get('status') not in ('canceled', 'incomplete_expired')]
        wrapped = [SimpleNamespace(to_dict=lambda s=s: s) for s in shown]
        return SimpleNamespace(data=wrapped[:limit], auto_paging_iter=lambda: iter(wrapped))

    monkeypatch.setattr(play_billing.stripe.Subscription, 'list', stripe_list)
    for name in list(os.environ):
        if name.startswith('PLAY_') or name in (config.ANDROID_BILLING_ENV, config.MIN_BUILD_ENV):
            monkeypatch.delenv(name)
    monkeypatch.setenv(config.ACCOUNT_ID_KEY_ENV, TEST_ACCOUNT_KEY)
    return SimpleNamespace(store=store, users=users, publisher=publisher, effects=effects, stripe_subs=stripe_subs)


def _row(env, uid=UID):
    return env.users.get_user_subscription(uid)


def _verify(uid=UID, token=TOKEN):
    return play_billing.verify_and_bind(uid, token, 'omi_pro')


# ---- verify and bind -----------------------------------------------------------------------


def test_active_purchase_acknowledges_binds_and_grants_omi_pro(env):
    env.publisher.resources[TOKEN] = resource()
    result = _verify()
    assert result.status == 'active'
    assert env.publisher.acks == [TOKEN]
    row = _row(env)
    assert (row.plan, row.status, row.provider) == (PlanType.unlimited_v2, SubscriptionStatus.active, 'play')
    assert row.current_period_end == NOW + 30 * DAY and row.cancel_at_period_end is False
    assert row.stripe_subscription_id is None
    # Same side effects as a Stripe Omi Pro upgrade.
    assert env.effects == [
        'credits',
        'unlock_all_conversations',
        'unlock_all_memories',
        'unlock_all_action_items',
        'fair_use',
    ]
    doc = env.store.docs[play_db.token_key(TOKEN)]
    assert doc['uid'] == UID and doc['base_plan_id'] == 'monthly' and doc['auto_renewing'] is True
    assert doc['obfuscated_account_id'] == play_billing.obfuscated_account_id(UID)
    assert env.store.pointers[UID] == play_db.token_key(TOKEN)


def test_token_replay_by_the_same_user_is_idempotent(env):
    env.publisher.resources[TOKEN] = resource()
    _verify()
    assert _verify().status == 'active'
    assert env.publisher.acks == [TOKEN]  # already acknowledged: no second ack
    assert len(env.store.docs) == 1


def test_token_bound_to_another_uid_is_refused(env):
    env.publisher.resources[TOKEN] = resource(account=None)
    env.publisher.resources[TOKEN]['externalAccountIdentifiers'] = {}
    _verify(uid=OTHER)
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify(uid=UID)
    assert (error.value.http_status, error.value.code) == (409, 'purchase_owned_elsewhere')
    assert _row(env).plan == PlanType.basic


def test_purchase_started_for_another_account_is_refused(env):
    env.publisher.resources[TOKEN] = resource(account=play_billing.obfuscated_account_id(OTHER))
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert error.value.code == 'purchase_owned_elsewhere'
    assert env.publisher.acks == [] and env.users.writes == []


def test_wrong_product_or_base_plan_is_refused(env):
    with pytest.raises(play_billing.PlayBillingError):
        play_billing.verify_and_bind(UID, TOKEN, 'other_product')
    bad = resource()
    bad['lineItems'][0]['offerDetails']['basePlanId'] = 'weekly'
    env.publisher.resources[TOKEN] = bad
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert error.value.code == 'unknown_product'


def test_unknown_token_is_a_client_error_and_google_outage_is_retryable(env):
    with pytest.raises(play_billing.PlayBillingError) as missing:
        _verify()
    assert missing.value.http_status == 400
    env.publisher.fail = RuntimeError('timeout')
    with pytest.raises(play_billing.PlayBillingError) as outage:
        _verify()
    assert outage.value.http_status == 503


def test_live_stripe_subscription_blocks_play_binding(env):
    env.users.rows[UID] = Subscription(
        plan=PlanType.unlimited_v2, current_period_end=NOW + 10 * DAY, stripe_subscription_id='sub_1'
    ).model_dump()
    env.publisher.resources[TOKEN] = resource()
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert (error.value.http_status, error.value.code) == (409, 'stripe_subscription_active')
    assert env.publisher.acks == []  # unacknowledged: Google refunds it automatically
    assert len(env.users.writes) == 0


def test_stripe_subscription_found_only_in_stripe_blocks_binding(env):
    env.users.customers[UID] = 'cus_1'
    env.stripe_subs.append({'status': 'past_due', 'metadata': {'uid': UID}})
    env.publisher.resources[TOKEN] = resource()
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert error.value.code == 'stripe_subscription_active'


def test_pending_purchase_binds_without_access_or_acknowledgement(env):
    env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_PENDING')
    assert _verify().status == 'pending'
    assert env.publisher.acks == [] and env.users.writes == []
    assert env.store.docs[play_db.token_key(TOKEN)]['uid'] == UID


def test_deletion_fenced_account_cannot_bind(env, monkeypatch):
    monkeypatch.setattr(play_billing, 'account_deletion_blocks_user_work', lambda uid: True)
    env.publisher.resources[TOKEN] = resource()
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert error.value.code == 'account_deletion_pending'


# ---- real-time developer notifications -----------------------------------------------------


def _notify(kind=None, token=TOKEN, voided=False, order=None):
    note = {'packageName': 'com.friend.ios'}
    if voided:
        note['voidedPurchaseNotification'] = {'purchaseToken': token, 'productType': 1}
        if order:
            note['voidedPurchaseNotification']['orderId'] = order
    else:
        note['subscriptionNotification'] = {'notificationType': kind or 2, 'purchaseToken': token}
    return play_billing.handle_developer_notification(note)


@pytest.fixture
def subscribed(env):
    env.publisher.resources[TOKEN] = resource()
    _verify()
    env.effects.clear()
    return env


def test_renewal_extends_the_period(subscribed):
    subscribed.publisher.resources[TOKEN] = resource(expiry=NOW + 60 * DAY)
    assert _notify(2) == 'active'
    assert _row(subscribed).current_period_end == NOW + 60 * DAY


def test_grace_period_keeps_access(subscribed):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_IN_GRACE_PERIOD', expiry=NOW + 3 * DAY)
    assert _notify(6) == 'active'
    assert _row(subscribed).plan == PlanType.unlimited_v2


def test_cancel_keeps_access_until_expiry(subscribed):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_CANCELED', renew=False)
    assert _notify(3) == 'active'
    row = _row(subscribed)
    assert row.plan == PlanType.unlimited_v2 and row.cancel_at_period_end is True


@pytest.mark.parametrize(
    'state,kind',
    [
        ('SUBSCRIPTION_STATE_ON_HOLD', 5),
        ('SUBSCRIPTION_STATE_PAUSED', 10),
        ('SUBSCRIPTION_STATE_EXPIRED', 13),
    ],
)
def test_on_hold_pause_and_expiry_remove_access(subscribed, state, kind):
    subscribed.publisher.resources[TOKEN] = resource(state)
    assert _notify(kind) == 'revoked'
    row = _row(subscribed)
    assert row.plan == PlanType.basic and row.provider is None


def test_revoke_removes_access_even_if_google_still_reads_active(subscribed):
    assert _notify(12) == 'revoked'
    assert _row(subscribed).plan == PlanType.basic


def test_refund_voided_purchase_removes_access(subscribed):
    assert _notify(voided=True) == 'revoked'
    assert _row(subscribed).plan == PlanType.basic
    doc = subscribed.store.docs[play_db.token_key(TOKEN)]
    assert doc['revoked_through'] == NOW + 30 * DAY  # the refunded period
    assert doc['next_check_at'] is not None  # Google may still renew it; keep reading


def test_resubscribe_after_on_hold_restores_access(subscribed):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_ON_HOLD')
    _notify(5)
    subscribed.publisher.resources[TOKEN] = resource(expiry=NOW + 30 * DAY)
    assert _notify(1) == 'active'  # SUBSCRIPTION_RECOVERED
    assert _row(subscribed).plan == PlanType.unlimited_v2


def test_resubscribe_with_new_linked_token_moves_the_entitlement(subscribed):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED')
    _notify(13)
    subscribed.publisher.resources['play-token-2'] = resource(linkedPurchaseToken=TOKEN)
    assert _verify(token='play-token-2').status == 'active'
    assert subscribed.store.pointers[UID] == play_db.token_key('play-token-2')
    # A late notification for the old token never downgrades the new one.
    assert _notify(13) == 'inactive'
    assert _row(subscribed).plan == PlanType.unlimited_v2


def test_linked_token_owned_by_another_account_is_refused(subscribed):
    subscribed.publisher.resources['play-token-2'] = resource(
        linkedPurchaseToken=TOKEN, account=play_billing.obfuscated_account_id(OTHER)
    )
    subscribed.publisher.resources['play-token-2']['externalAccountIdentifiers'] = {}
    with pytest.raises(play_billing.PlayBillingError):
        _verify(uid=OTHER, token='play-token-2')


def test_play_expiry_never_downgrades_a_later_stripe_subscription(subscribed):
    subscribed.users.rows[UID] = Subscription(
        plan=PlanType.unlimited_v2, current_period_end=NOW + 20 * DAY, stripe_subscription_id='sub_9'
    ).model_dump()
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED')
    assert _notify(13) == 'inactive'
    assert _row(subscribed).stripe_subscription_id == 'sub_9'


def test_notification_for_unclaimed_token_is_kept_for_later_binding(env):
    env.publisher.resources[TOKEN] = resource()
    assert _notify(4) == 'unbound'
    assert env.users.writes == []
    assert _verify().status == 'active'


def test_other_package_and_test_notifications_are_ignored(env):
    assert play_billing.handle_developer_notification({'packageName': 'x'}) == 'ignored_package'
    assert play_billing.handle_developer_notification({'packageName': 'com.friend.ios', 'testNotification': {}}) == (
        'test'
    )


def test_reconcile_rereads_due_purchases(subscribed):
    key = play_db.token_key(TOKEN)
    subscribed.store.docs[key]['next_check_at'] = NOW - 1
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED')
    assert play_billing.reconcile_due() == {'revoked': 1}
    assert _row(subscribed).plan == PlanType.basic
    assert subscribed.store.docs[key]['next_check_at'] is None  # terminal: no further checks


# ---- switch, build gate, wire shape --------------------------------------------------------


@pytest.mark.parametrize(
    'environ,platform,build,expected',
    [
        ({}, 'android', '9999', False),
        ({'ANDROID_BILLING': 'stripe', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1700'}, 'android', '9999', False),
        ({'ANDROID_BILLING': 'play'}, 'android', '9999', False),  # no minimum build: nobody qualifies
        (
            {'ANDROID_BILLING': 'play', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1700', KEY_ENV: TEST_ACCOUNT_KEY},
            'android',
            '1699',
            False,
        ),
        (
            {'ANDROID_BILLING': 'play', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1700', KEY_ENV: TEST_ACCOUNT_KEY},
            'android',
            '1700',
            True,
        ),
        (
            {'ANDROID_BILLING': 'play', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1700', KEY_ENV: TEST_ACCOUNT_KEY},
            'ios',
            '9999',
            False,
        ),
        (
            {'ANDROID_BILLING': 'play', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1700', KEY_ENV: TEST_ACCOUNT_KEY},
            'android',
            None,
            False,
        ),
        (
            {'ANDROID_BILLING': 'play', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1700', KEY_ENV: TEST_ACCOUNT_KEY},
            'android',
            'abc',
            False,
        ),
    ],
)
def test_switch_and_minimum_build(environ, platform, build, expected):
    assert config.client_uses_play(platform, build, UID, environ=environ) is expected


PLAY_ON = {'ANDROID_PLAY_BILLING_MIN_BUILD': '1700', 'PLAY_ACCOUNT_ID_HMAC_KEY': TEST_ACCOUNT_KEY}


def test_cohort_puts_one_user_on_play_while_everyone_else_stays_on_stripe():
    environ = {**PLAY_ON, 'ANDROID_PLAY_BILLING_COHORT': f'uid:{UID}'}
    assert config.client_uses_play('android', '1700', UID, environ=environ) is True
    assert config.client_uses_play('android', '1700', OTHER, environ=environ) is False
    assert config.client_uses_play('android', '1699', UID, environ=environ) is False  # build gate still applies
    assert config.client_uses_play('ios', '1700', UID, environ=environ) is False
    assert config.client_uses_play(
        'android', '1700', UID, environ={**environ, 'ANDROID_PLAY_BILLING_COHORT': 'junk'}
    ) is (False)
    assert config.client_uses_play(
        'android', '1700', OTHER, environ={**PLAY_ON, 'ANDROID_PLAY_BILLING_COHORT': 'pct:100'}
    )


def test_rollout_cohort_document_admits_a_user(monkeypatch):
    from config import rollout_cohorts

    seen = []

    def member(uid, name):
        seen.append(name)
        if uid == OTHER:
            raise rollout_cohorts.RolloutCohortUnavailable('down')
        return uid == UID

    monkeypatch.setattr(config.rollout_cohorts, 'in_rollout_cohort', member)
    assert config.client_uses_play('android', '1700', UID, environ=PLAY_ON) is True
    assert config.client_uses_play('android', '1700', OTHER, environ=PLAY_ON) is False  # unknown: Stripe
    assert seen == ['android-play-billing', 'android-play-billing']
    assert 'android-play-billing' in rollout_cohorts.COHORT_ENVS


@pytest.mark.parametrize('product', sorted(config.LEGACY_PRODUCT_IDS))
def test_legacy_products_are_never_granted(env, product):
    with pytest.raises(play_billing.PlayBillingError) as error:
        play_billing.verify_and_bind(UID, TOKEN, product)
    assert error.value.code == 'legacy_product'
    legacy = resource()
    legacy['lineItems'][0]['productId'] = product
    env.publisher.resources[TOKEN] = legacy
    with pytest.raises(play_billing.PlayBillingError) as restored:
        _verify()
    assert restored.value.code == 'legacy_product'
    env.store.docs[play_db.token_key(TOKEN)] = {'uid': UID}
    assert _notify(4) == 'legacy_product'
    assert env.users.writes == [] and env.publisher.acks == []


@pytest.mark.parametrize(
    'kind,state,access',
    [
        (1, 'SUBSCRIPTION_STATE_ACTIVE', True),  # RECOVERED
        (2, 'SUBSCRIPTION_STATE_ACTIVE', True),  # RENEWED
        (3, 'SUBSCRIPTION_STATE_CANCELED', True),  # CANCELED: paid through expiry
        (4, 'SUBSCRIPTION_STATE_ACTIVE', True),  # PURCHASED
        (5, 'SUBSCRIPTION_STATE_ON_HOLD', False),  # ON_HOLD
        (6, 'SUBSCRIPTION_STATE_IN_GRACE_PERIOD', True),  # IN_GRACE_PERIOD
        (7, 'SUBSCRIPTION_STATE_ACTIVE', True),  # RESTARTED
        (8, 'SUBSCRIPTION_STATE_ACTIVE', True),  # PRICE_CHANGE_CONFIRMED
        (9, 'SUBSCRIPTION_STATE_ACTIVE', True),  # DEFERRED
        (10, 'SUBSCRIPTION_STATE_PAUSED', False),  # PAUSED
        (11, 'SUBSCRIPTION_STATE_ACTIVE', True),  # PAUSE_SCHEDULE_CHANGED
        (12, 'SUBSCRIPTION_STATE_ACTIVE', False),  # REVOKED: removed even if Google still reads active
        (13, 'SUBSCRIPTION_STATE_EXPIRED', False),  # EXPIRED
        (20, 'SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED', False),  # PENDING_PURCHASE_CANCELED
    ],
)
def test_every_notification_type_maps_to_access_without_the_app(subscribed, kind, state, access):
    subscribed.publisher.resources[TOKEN] = resource(state, expiry=NOW + 40 * DAY, renew=kind != 3)
    _notify(kind)
    row = _row(subscribed)
    assert (row.plan == PlanType.unlimited_v2) is access
    if access:
        assert row.current_period_end == NOW + 40 * DAY


def test_account_id_is_a_keyed_hmac_and_play_stays_off_without_the_key():
    environ = {'ANDROID_BILLING': 'play', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1700'}
    assert config.client_uses_play('android', '1700', UID, environ=environ) is False
    with pytest.raises(config.AccountIdKeyMissing):
        config.obfuscated_account_id(UID, environ)
    keyed = config.obfuscated_account_id(UID, {KEY_ENV: TEST_ACCOUNT_KEY})
    other_key = config.obfuscated_account_id(UID, {KEY_ENV: TEST_ACCOUNT_KEY[::-1]})
    import hashlib

    assert keyed != other_key and len(keyed) == 64
    assert keyed != hashlib.sha256(f'omi-play-account:{UID}'.encode()).hexdigest()  # not derivable from the uid
    assert config.client_uses_play('android', '1700', UID, environ={**environ, KEY_ENV: 'short'}) is False


def test_stripe_rows_serialize_exactly_as_before():
    legacy = Subscription(plan=PlanType.unlimited_v2, stripe_subscription_id='sub_1', current_period_end=NOW)
    assert 'provider' not in legacy.model_dump()
    assert 'provider' not in json.loads(legacy.model_dump_json())
    play = Subscription(plan=PlanType.unlimited_v2, provider='play')
    assert play.model_dump()['provider'] == 'play'


def test_subscription_response_omits_play_billing_when_unset(env):
    response = UserSubscriptionResponse(
        subscription=Subscription(),
        transcription_seconds_used=0,
        transcription_seconds_limit=0,
        words_transcribed_used=0,
        words_transcribed_limit=0,
        insights_gained_used=0,
        insights_gained_limit=0,
    )
    assert 'play_billing' not in json.loads(response.model_dump_json())
    response.play_billing = play_billing.client_config(UID)
    block = json.loads(response.model_dump_json())['play_billing']
    assert block == {
        'product_id': 'omi_pro',
        'base_plans': [{'id': 'monthly', 'interval': 'month'}, {'id': 'yearly', 'interval': 'year'}],
        'trial_offer_id': 'trial-7d',
        'obfuscated_account_id': play_billing.obfuscated_account_id(UID),
    }
    assert len(block['obfuscated_account_id']) == 64


def _byok_subscription_json(monkeypatch, platform, build):
    from fastapi import Request
    from routers import users

    monkeypatch.setattr(users.users_db, 'is_byok_active', lambda _uid: True)
    monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: True)
    monkeypatch.setattr(users.users_db, 'get_user_valid_subscription', lambda *a, **k: None)
    monkeypatch.setattr(users.play_subscriptions_db, 'remember_account_once', lambda *a: None)
    response = users.get_user_subscription_endpoint(
        request=Request({'type': 'http', 'headers': []}),
        uid=UID,
        x_app_platform=platform,
        x_app_version='1.0.600',
        x_app_build=build,
    )
    return response.model_dump_json()


@pytest.fixture
def warm_subscription_route(monkeypatch, env):
    """Import the router and serve one response in setup, so the test's CPU budget measures the switch."""
    _byok_subscription_json(monkeypatch, 'ios', '1')


def test_switch_off_subscription_route_is_byte_identical(monkeypatch, env, warm_subscription_route):
    baseline = _byok_subscription_json(monkeypatch, 'android', '9999')
    assert 'play_billing' not in baseline
    monkeypatch.setenv('ANDROID_PLAY_BILLING_MIN_BUILD', '1700')
    assert _byok_subscription_json(monkeypatch, 'android', '9999') == baseline  # mode still stripe
    monkeypatch.setenv('ANDROID_PLAY_BILLING_COHORT', f'uid:{OTHER}')
    assert _byok_subscription_json(monkeypatch, 'android', '9999') == baseline  # not in the cohort
    monkeypatch.setenv('ANDROID_PLAY_BILLING_COHORT', f'uid:{UID}')
    assert 'play_billing' in _byok_subscription_json(monkeypatch, 'android', '9999')  # test account only
    monkeypatch.delenv('ANDROID_PLAY_BILLING_COHORT')
    monkeypatch.setenv('ANDROID_BILLING', 'play')
    assert _byok_subscription_json(monkeypatch, 'android', '1699') == baseline  # old build keeps Stripe
    assert _byok_subscription_json(monkeypatch, 'ios', '9999') == baseline
    on = json.loads(_byok_subscription_json(monkeypatch, 'android', '1700'))
    assert on['play_billing']['product_id'] == 'omi_pro'
    # A Play build can always redeem a prepaid code (test_play_prepaid_code_entry.py).
    assert on['prepaid_code_redeem'] is True
    assert {k: v for k, v in on.items() if k not in ('play_billing', 'prepaid_code_redeem')} == json.loads(baseline)


@pytest.fixture(scope='module')
def prod_play_env():
    """The rendered prod backend values, parsed in setup (the file is large)."""
    import yaml
    from pathlib import Path

    rendered = yaml.safe_load((Path(__file__).parents[2] / 'deploy' / 'runtime_env.yaml').read_text())
    env = rendered['environments']['prod']['cloud_run']['services']['backend']['env']
    keys = ('ANDROID_BILLING', 'ANDROID_PLAY_BILLING_MIN_BUILD', 'ANDROID_PLAY_BILLING_COHORT')
    return {key: str(env[key]['value']) for key in keys}


def test_deployed_prod_values_send_nobody_to_play_without_the_rollout_cohort(
    monkeypatch, env, warm_subscription_route, prod_play_env
):
    prod = prod_play_env
    assert prod == {
        'ANDROID_BILLING': 'stripe',
        'ANDROID_PLAY_BILLING_MIN_BUILD': '1617',
        'ANDROID_PLAY_BILLING_COHORT': '',
    }
    environ = {**prod, KEY_ENV: TEST_ACCOUNT_KEY}
    for build in ('1617', '9999'):
        assert config.client_uses_play('android', build, UID, environ) is False
    # The android-play-billing rollout cohort alone admits a test uid, on 1617 and later only.
    with monkeypatch.context() as patch:
        patch.setattr(
            config.rollout_cohorts, 'in_rollout_cohort', lambda uid, name: uid == UID and name == 'android-play-billing'
        )
        assert config.client_uses_play('android', '1617', UID, environ) is True
        assert config.client_uses_play('android', '1616', UID, environ) is False
        assert config.client_uses_play('android', '9999', OTHER, environ) is False
    # Switch-off response stays byte-identical under the deployed values.
    baseline = _byok_subscription_json(monkeypatch, 'android', '9999')
    for key, value in prod.items():
        monkeypatch.setenv(key, value)
    for build in ('1617', '9999'):
        assert _byok_subscription_json(monkeypatch, 'android', build) == baseline
    assert 'play_billing' not in baseline


def test_play_subscriber_cannot_open_stripe_checkout(monkeypatch):
    from utils import subscription as subscription_utils

    row = Subscription(plan=PlanType.unlimited_v2, current_period_end=NOW + DAY, provider='play')
    monkeypatch.setattr(subscription_utils.users_db, 'get_user_valid_subscription', lambda *a, **k: row)
    allowed, reason = subscription_utils.can_user_make_payment(UID, 'price_any')
    assert allowed is False and 'Google Play' in reason


# ---- routes and storage --------------------------------------------------------------------


@pytest.fixture(scope='module')
def play_routes():
    from routers import play_billing as routes

    return routes


def test_rtdn_route_requires_google_push_identity_and_decodes_message(monkeypatch, env, play_routes):
    from fastapi import HTTPException, Request
    from routers import play_billing as routes

    body = {'message': {'data': base64.b64encode(json.dumps({'packageName': 'x'}).encode()).decode()}}
    with pytest.raises(HTTPException) as unconfigured:
        routes.play_rtdn(Request({'type': 'http', 'headers': []}), body)
    assert unconfigured.value.status_code == 403
    monkeypatch.setattr(routes, 'verify_configured_cloud_tasks_oidc', lambda request, audience, invoker_sa: 0)
    assert routes.play_rtdn(Request({'type': 'http', 'headers': []}), body).status == 'ignored_package'
    with pytest.raises(HTTPException) as malformed:
        routes.play_rtdn(Request({'type': 'http', 'headers': []}), {'message': {'data': '!!'}})
    assert malformed.value.status_code == 400


def test_rtdn_route_asks_pubsub_to_retry_when_google_is_down(monkeypatch, env):
    from fastapi import HTTPException, Request
    from routers import play_billing as routes

    monkeypatch.setattr(routes, 'verify_configured_cloud_tasks_oidc', lambda request, audience, invoker_sa: 0)

    def outage(_note):
        raise play_billing.PlayBillingError(503, 'play_unavailable', 'down')

    monkeypatch.setattr(routes.play_billing, 'handle_developer_notification', outage)
    body = {'message': {'data': base64.b64encode(b'{}').decode()}}
    with pytest.raises(HTTPException) as error:
        routes.play_rtdn(Request({'type': 'http', 'headers': []}), body)
    assert error.value.status_code == 503


class _Doc:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def create(self, data):
        from google.api_core.exceptions import AlreadyExists

        if self.key in self.store:
            raise AlreadyExists('exists')
        self.store[self.key] = dict(data)

    def get(self, *_):
        data = self.store.get(self.key)
        return SimpleNamespace(exists=data is not None, to_dict=lambda: dict(data) if data else None, id=self.key)

    def set(self, data, merge=False):
        self.store[self.key] = {**self.store.get(self.key, {}), **data} if merge else dict(data)


class _Client:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return SimpleNamespace(document=lambda key: _Doc(self.store, (name, key)))


def test_bind_purchase_create_is_exclusive_per_token():
    client = _Client()
    key = play_db.token_key(TOKEN)
    assert play_db.bind_purchase(key, UID, {'state': 'A'}, firestore_client=client) == UID
    assert play_db.bind_purchase(key, OTHER, {'state': 'B'}, firestore_client=client) == UID
    assert client.store[(play_db.COLLECTION, key)] == {'state': 'A', 'uid': UID}
    assert play_db.bind_purchase(key, UID, {'state': 'C', 'uid': OTHER}, firestore_client=client) == UID
    assert client.store[(play_db.COLLECTION, key)]['uid'] == UID


def test_publisher_rest_urls_and_missing_token_mapping():
    from urllib.parse import quote

    calls = []

    class Session:
        def get(self, url, timeout):
            calls.append(('GET', url))
            return SimpleNamespace(status_code=404 if 'missing' in url else 200, json=lambda: {'ok': 1})

        def post(self, url, json, timeout):
            calls.append(('POST', url))
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    client = object.__new__(play_billing._GooglePublisher)
    client._session = Session()
    client._quote = lambda value: quote(value, safe='')
    base = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.friend.ios'
    with pytest.raises(play_billing.PurchaseNotFound):
        client.get_subscription('com.friend.ios', 'missing/token')
    client.acknowledge('com.friend.ios', 'omi_pro', 'tok')
    assert calls == [
        ('GET', f'{base}/purchases/subscriptionsv2/tokens/missing%2Ftoken'),
        ('POST', f'{base}/purchases/subscriptions/omi_pro/tokens/tok:acknowledge'),
    ]
