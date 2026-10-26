"""Account-deletion refusals of lifecycle-event unlocks are acknowledged, not crashed.

A user deletes their account: the deletion worker acquires the account-wide
destructive-operation gate, cancels the Stripe subscription and erases the
account. Stripe then delivers the cancellation webhook for exactly that
cancellation (customer.subscription.updated/deleted), and the lifecycle arm's
unlock trio reads the same authority through ``external_write_fence`` — which
raises ``DestructiveOperationInProgress``. Before this boundary the exception
escaped the webhook as an unhandled ASGI traceback and an HTTP 500, so Stripe
kept retrying a delivery that can never succeed for days (prod backend
2026-10-25: three tracebacks per burst at
``routers/payment.py`` → ``unlock_all_conversations`` →
``database/legal_holds.py`` ``external_write_fence``). The same behavior lives
in the cancellation arm only: checkout and plan-change unlocks keep their
pinned fence→500 retry contract, because their owner may still be upgraded
behind a temporary gate.

The classification is intentionally narrow. Only the account-deletion marker
itself (read directly, the same authority the fence read) certifies that the
refusing fence is a deletion; a temporary destructive gate (an explicit memory
deletion, a legal-hold flow) and any authority read error keep the delivery
retryable. A ``billing_failed``/``cancelled`` marker can restore access and is
not classified either. Acknowledging drops only the unlock effects: the
terminal status is still projected, credits and caches are still invalidated,
and the delivery ends the retry loop.

Failure-Class: FC-account-deletion-billing-fences-living-account
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database.legal_holds import DestructiveOperationInProgress
from models.users import PlanLimits, PlanType, Subscription
from routers import payment
from utils.billing import account_fence
from utils.observability import billing_webhook

NOW = 1_900_000_000
DELETION_FENCE_MESSAGE = 'external data write blocked by account deletion'


class _FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self) -> dict:
        return dict(self._data)


class _FakeDeletionDoc:
    """Stands in for ``account_deletions/{uid}`` inside the classifier."""

    data: dict | None = None
    read_error: Exception | None = None

    def get(self):
        if _FakeDeletionDoc.read_error is not None:
            raise _FakeDeletionDoc.read_error
        return _FakeSnapshot(_FakeDeletionDoc.data is not None, _FakeDeletionDoc.data)


@pytest.fixture
def lane(monkeypatch):
    """The characterization lane's webhook harness, armed for the deletion arm."""
    state = SimpleNamespace(event=None, current=None, calls=[], stripe_obj=None)
    unlock_fences = SimpleNamespace(on=False, error=None)

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def effect(name):
        return lambda *args, **kwargs: state.calls.append((name, args))

    def conversations(uid, *args, **kwargs):
        state.calls.append(('conversations', (uid,)))
        if unlock_fences.on:
            raise unlock_fences.error or DestructiveOperationInProgress(DELETION_FENCE_MESSAGE)

    def write(uid, payload):
        state.calls.append(('write', (uid, payload)))
        state.current = Subscription.model_validate(payload)

    monkeypatch.setattr(payment, 'run_blocking', run_blocking)
    monkeypatch.setattr(payment.time, 'time', lambda: NOW)
    monkeypatch.setattr(payment.stripe_utils, 'parse_event', lambda *args: state.event)
    monkeypatch.setattr(payment, 'record_subscription_event', lambda **kwargs: None)
    monkeypatch.setattr(payment, 'get_plan_type_from_price_id', lambda price: PlanType(price.removeprefix('price_')))
    # Limits helpers are re-pinned per test: sibling suites stub utils.subscription
    # by attribute mutation, which the sys.modules-snapshot fixture cannot undo.
    monkeypatch.setattr(payment, 'get_plan_limits', lambda plan: PlanLimits(transcription_seconds=123))
    monkeypatch.setattr(payment, 'get_basic_plan_limits', lambda: PlanLimits(transcription_seconds=7))
    monkeypatch.setattr(payment.users_db, 'get_user_profile', lambda uid: {'uid': uid})
    monkeypatch.setattr(payment.users_db, 'get_existing_user_subscription', lambda uid: state.current)
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: state.current)
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', write)
    monkeypatch.setattr(payment.users_db, 'set_stripe_customer_id', effect('customer'))
    monkeypatch.setattr(payment, 'find_active_paid_subscription_for_user', lambda uid: None)
    monkeypatch.setattr(payment, 'set_credits_invalidation_signal', effect('credits'))
    monkeypatch.setattr(payment, 'clear_trial_paywall_cache', effect('trial_cache'))
    monkeypatch.setattr(payment, 'clear_fair_use_on_upgrade', effect('fair_use'))
    monkeypatch.setattr(payment.conversations_db, 'unlock_all_conversations', conversations)
    monkeypatch.setattr(payment.memories_db, 'unlock_all_memories', effect('memories'))
    monkeypatch.setattr(payment.action_items_db, 'unlock_all_action_items', effect('actions'))

    async def telemetry(*args, **kwargs):
        state.calls.append(('telemetry', ()))

    monkeypatch.setattr(billing_webhook, 'schedule_billing_webhook_events', telemetry)
    monkeypatch.setattr(
        payment.stripe.Subscription,
        'retrieve',
        lambda *args: stripe.Subscription.construct_from(state.stripe_obj, 'fixture'),
    )
    monkeypatch.setattr(account_fence, 'account_deletion_document', lambda uid: _FakeDeletionDoc())
    return state, unlock_fences


def _deleted_subscription_event(status='canceled', sub_id='sub-current'):
    return {
        'id': 'evt-deletion-fixture',
        'created': NOW,
        'type': 'customer.subscription.deleted',
        'data': {
            'object': {
                'id': sub_id,
                'created': NOW,
                'status': status,
                'cancel_at_period_end': True,
                'metadata': {'uid': 'user-fixture'},
                'customer': 'cus-fixture',
                'items': {
                    'data': [
                        {
                            'price': {
                                'id': 'price_plus',
                                'currency': 'usd',
                                'unit_amount': 1799,
                                'recurring': {'interval': 'month'},
                            }
                        }
                    ]
                },
                'current_period_start': NOW - 100,
                'current_period_end': NOW + 100,
            }
        },
    }


def _post_webhook():
    app = FastAPI()
    app.include_router(payment.router)
    client = TestClient(app, raise_server_exceptions=False)
    return client.post('/v1/stripe/webhook', content=b'{}', headers={'stripe-signature': 'fixture'})


def _call_names(lane):
    return [name for name, _ in lane.calls]


@pytest.mark.parametrize('wipe_status', ['pending', 'retrying', 'running', 'deleting_auth', 'failed', 'completed'])
def test_deletion_wipe_refusal_is_acknowledged_without_unlocks(lane, wipe_status):
    """The cancellation webhook outliving its erased owner ends the retry loop.

    The unlock trio is skipped and nothing is raised: the terminal status is
    still projected and cache/credit invalidations still run, so Stripe's
    redeliveries stop instead of stacking ASGI tracebacks for days.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': wipe_status}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()

    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    # Unlocks stopped at the fence; the entitlement projection did not.
    assert _call_names(state) == [
        'customer',
        'conversations',
        'write',
        'telemetry',
        'credits',
        'trial_cache',
        'fair_use',
    ]
    assert state.current.plan == PlanType.plus
    assert state.current.stripe_subscription_id == 'sub-current'
    assert state.current.status.value == 'active'
    assert state.current.cancel_at_period_end is True


@pytest.mark.parametrize('wipe_status', ['billing_failed', 'cancelled'])
def test_access_restorable_markers_keep_the_delivery_retryable(lane, wipe_status):
    """A marker that can still restore access does not certify the refusal."""
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': wipe_status}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()
    assert response.status_code == 500
    assert 'success' not in response.text

    assert _call_names(state) == ['customer', 'conversations']
    assert state.current is None


@pytest.mark.parametrize('authority', ['missing', 'read_error'])
def test_unprovable_fences_stay_retryable(lane, authority):
    """No marker, or an authority that cannot answer: the retry stays with Stripe."""
    state, fences = lane
    _FakeDeletionDoc.data = None
    _FakeDeletionDoc.read_error = (
        RuntimeError('data-plane authority unavailable') if authority == 'read_error' else None
    )
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()
    assert response.status_code == 500
    assert 'success' not in response.text

    assert _call_names(state) == ['customer', 'conversations']


def test_temporary_gate_before_a_deletion_marker_keeps_retrying(lane):
    """A fence that later lifts must keep its retries: classification needs the marker.

    The gate is closed for the first delivery (no deletion marker — the fence is
    a temporary destructive gate), so the webhook propagates and Stripe holds
    the retry; once the gate lifts, the ordinary delivery unlocks and projects.
    """
    state, fences = lane
    _FakeDeletionDoc.data = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    first = _post_webhook()
    assert first.status_code == 500
    assert 'success' not in first.text
    assert _call_names(state) == ['customer', 'conversations']

    fences.on = False
    state.calls.clear()
    response = _post_webhook()
    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    assert _call_names(state) == [
        'customer',
        'conversations',
        'memories',
        'actions',
        'write',
        'telemetry',
        'credits',
        'trial_cache',
        'fair_use',
    ]
    assert state.current.plan == PlanType.plus


def test_non_fence_unlock_failure_still_propagates(lane):
    """Data-plane failures are not account refusals; the delivery stays retryable."""
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    fences.on = True
    fences.error = RuntimeError('data-plane read failed')
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()
    assert response.status_code == 500
    assert 'data-plane read failed' not in response.text

    assert _call_names(state) == ['customer', 'conversations']


def test_classifier_requires_both_fence_type_and_marker(monkeypatch):
    """Unit pins: non-fence errors are never classified; the marker is required."""
    seen_markers = []
    _FakeDeletionDoc.read_error = None
    _FakeDeletionDoc.data = None

    def fake_doc(uid):
        seen_markers.append(uid)
        return _FakeDeletionDoc()

    monkeypatch.setattr(account_fence, 'account_deletion_document', fake_doc)
    _FakeDeletionDoc.data = {'wipe_status': 'running'}

    fence_error = DestructiveOperationInProgress(DELETION_FENCE_MESSAGE)
    assert account_fence.subscription_event_unlock_refused_by_account_deletion('uid-1', fence_error) is True
    assert account_fence.subscription_event_unlock_refused_by_account_deletion('uid-1', RuntimeError('x')) is False

    _FakeDeletionDoc.data = None
    assert account_fence.subscription_event_unlock_refused_by_account_deletion('uid-1', fence_error) is False

    _FakeDeletionDoc.read_error = RuntimeError('authority down')
    assert account_fence.subscription_event_unlock_refused_by_account_deletion('uid-1', fence_error) is False
    _FakeDeletionDoc.read_error = None

    # The probe reads exactly the authority the fence read: once per fence-error
    # classification (the non-fence error is rejected before the authority is
    # touched; the read failure attempts the authority once).
    assert seen_markers == ['uid-1', 'uid-1', 'uid-1']


# ---------------------------------------------------------------------------
# Boundary pins for the whole arm: each test isolates one adjacent behavior the
# classification must not disturb, because the fixture differs from the
# characterization suite (previous subscription present, replacement adoption).
# ---------------------------------------------------------------------------


def test_adoption_requires_a_live_active_replacement_not_a_stale_row(lane):
    """A stored non-active row cannot adopt; the event downgrades without unlocks.

    Adoption needs a resolvable active paid replacement (looked up in Stripe),
    not just any different subscription id. With no replacement findable and a
    superseded event id, the paid-through grace is withheld and the projection
    downgrades to Basic without unlock effects — the fence is never consulted.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.current = Subscription(plan=PlanType.operator, stripe_subscription_id='sub-replacement')
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()

    response = _post_webhook()

    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    # A Basic projection carries no unlock/set_customer effects to fence.
    assert _call_names(state) == ['write', 'telemetry', 'credits', 'trial_cache']
    assert 'conversations' not in _call_names(state)
    assert state.current.plan == PlanType.basic


def test_stale_guard_preservation_ignores_the_fence_altogether(lane):
    """A preserved newer paid subscription unlocks nothing and never reaches the fence.

    The stale-downgrade shield returns before any effect; a deletion marker
    behind the account must not turn that no-op delivery into a crash or a
    classified acknowledgment.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.current = Subscription(plan=PlanType.plus, stripe_subscription_id='sub-new', current_period_end=NOW + 100)
    state.stripe_obj = _deleted_subscription_event(sub_id='sub-old')['data']['object']
    event = _deleted_subscription_event(sub_id='sub-old')
    state.event = event

    response = _post_webhook()

    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    assert _call_names(state) == []
    assert state.current.plan == PlanType.plus
    assert state.current.stripe_subscription_id == 'sub-new'


def test_stale_guard_preserved_delivery_is_still_silent_on_redelivery(lane):
    """Redelivering a shielded event re-enters the shield, never the unlock path.

    Stripe's retry of a preserved-current delivery must not drift into the
    unlock trio on the second attempt: preservation is decided from stored
    state, so both deliveries acknowledge with zero effects.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.current = Subscription(plan=PlanType.plus, stripe_subscription_id='sub-new', current_period_end=NOW + 100)
    state.stripe_obj = _deleted_subscription_event(sub_id='sub-old')['data']['object']
    state.event = _deleted_subscription_event(sub_id='sub-old')

    first = _post_webhook()
    assert first.status_code == 200
    assert _call_names(state) == []

    second = _post_webhook()
    assert second.status_code == 200
    assert _call_names(state) == []
    assert state.current.plan == PlanType.plus
    assert state.current.stripe_subscription_id == 'sub-new'


def test_basic_downgrade_with_unpaid_status_still_projects_through_the_fence(lane):
    """An unpaid (not canceled) snapshot downgrades to Basic and projects fine."""
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event(status='unpaid')['data']['object']
    state.event = _deleted_subscription_event(status='unpaid')
    state.current = None

    response = _post_webhook()

    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    # No unlock effects exist for a Basic projection; the downgrade persists.
    assert _call_names(state) == ['write', 'telemetry', 'credits', 'trial_cache']
    assert state.current.plan == PlanType.basic


def test_grace_period_event_behind_the_marker_keeps_the_paid_label(lane):
    """A paid-through canceled event keeps the grace label behind the fence.

    The paid-through grace (FC-early-terminal-strips-paid-period) projects the
    paid plan with cancel_at_period_end true; the fence drops the unlocks but
    must not strip the grace label, or the stored row would downgrade the
    customer immediately instead of at period end.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()

    assert response.status_code == 200
    assert state.current.plan == PlanType.plus
    assert state.current.cancel_at_period_end is True
    assert state.current.current_period_end == NOW + 100


def test_paid_event_still_invalidates_caches_behind_the_marker(lane):
    """Cache and credit invalidations survive the fence classification.

    A cached paid label or a stale credits snapshot must not outlive the
    acknowledged event: only the unlock writes are dropped, so the delivery
    stays coherent for the read path even though its content writes are moot.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()

    assert response.status_code == 200
    calls = _call_names(state)
    assert 'credits' in calls
    assert 'trial_cache' in calls
    assert 'write' in calls
    assert 'memories' not in calls
    assert 'actions' not in calls


def test_updated_event_is_classified_like_deleted(lane):
    """customer.subscription.updated carries the same unlock effects, same classification.

    Stripe's cancellation surfaces as updated (at-period-end) or deleted
    (immediate); the fence classification keys on the refusal, not the event
    name, so both lifecycle events end their retry loops.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    event = _deleted_subscription_event()
    event['type'] = 'customer.subscription.updated'
    state.event = event
    state.current = None

    response = _post_webhook()

    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    assert _call_names(state)[:2] == ['customer', 'conversations']
    assert 'write' in _call_names(state)
    assert 'memories' not in _call_names(state)
    assert 'actions' not in _call_names(state)


def test_memories_unlock_alone_failing_is_not_classified(lane, monkeypatch):
    """A fence at the second unlock still propagates — the arm owns the trio's head.

    Only the first unlock failure reaches the classifier in this delivery; the
    memories unlock raising means the conversations unlock already passed the
    fence, so the marker probe cannot certify the account is deleted.
    """
    state, fences = lane

    def memories_fenced(uid, *args, **kwargs):
        state.calls.append(('memories', (uid,)))
        raise DestructiveOperationInProgress(DELETION_FENCE_MESSAGE)

    monkeypatch.setattr(payment.memories_db, 'unlock_all_memories', memories_fenced)
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()

    # conversations passed (no fence), memories raised inside the same try, so
    # the classifier is consulted — and the marker says deletion — meaning the
    # delivery still acknowledges without re-running the earlier unlocks.
    assert response.status_code == 200
    assert _call_names(state) == [
        'customer',
        'conversations',
        'memories',
        'write',
        'telemetry',
        'credits',
        'trial_cache',
        'fair_use',
    ]


def test_authority_probe_failure_is_visible_but_never_fatal(lane):
    """The classifier's probe warning never turns into a webhook failure."""
    state, fences = lane
    _FakeDeletionDoc.read_error = RuntimeError('authority unavailable mid-wipe')
    _FakeDeletionDoc.data = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = None

    response = _post_webhook()

    assert response.status_code == 500
    assert _call_names(state) == ['customer', 'conversations']
    _FakeDeletionDoc.read_error = None


def test_classifier_does_not_touch_the_authority_for_other_exceptions(monkeypatch):
    """Non-fence exceptions never pay the authority read cost."""
    probes = []

    def fake_doc(uid):
        probes.append(uid)
        raise AssertionError('authority must not be read for a non-fence error')

    monkeypatch.setattr(account_fence, 'account_deletion_document', fake_doc)
    assert account_fence.subscription_event_unlock_refused_by_account_deletion('uid-1', RuntimeError('x')) is False
    assert account_fence.subscription_event_unlock_refused_by_account_deletion('uid-1', ValueError('y')) is False
    assert probes == []


def test_terminal_fences_map_to_true_while_missing_maps_to_false(monkeypatch):
    """Truth table pin: every blocking wipe status classifies; absent does not."""
    for wipe_status, expected in [
        ('pending', True),
        ('retrying', True),
        ('running', True),
        ('deleting_auth', True),
        ('failed', True),
        ('completed', True),
        ('billing_failed', False),
        ('cancelled', False),
    ]:
        _FakeDeletionDoc.read_error = None
        _FakeDeletionDoc.data = {'wipe_status': wipe_status}
        monkeypatch.setattr(account_fence, 'account_deletion_document', lambda uid: _FakeDeletionDoc())
        got = account_fence.account_deletion_fence_is_terminal('uid-1')
        assert got is expected, f'wipe_status={wipe_status}: got {got}, expected {expected}'


def test_deleted_event_without_uid_metadata_has_no_effects(lane, monkeypatch):
    """No owner anywhere: the arm exits before any effect, fence or not."""
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'running'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    event = _deleted_subscription_event()
    event['data']['object']['metadata'] = {}
    # Customer lookup misses too, so the arm returns before any effect. The
    # lookup is a Firestore query (not a point read), so it must be stubbed.
    monkeypatch.setattr(payment.users_db, 'get_user_by_stripe_customer_id', lambda customer_id: None)
    state.event = event
    state.current = None

    response = _post_webhook()

    assert response.status_code == 200
    assert _call_names(state) == []


def test_classifier_is_total_over_marker_payloads(monkeypatch):
    """Malformed marker payloads degrade to False, never raise."""
    _FakeDeletionDoc.read_error = None
    monkeypatch.setattr(account_fence, 'account_deletion_document', lambda uid: _FakeDeletionDoc())
    for payload in [None, {}, {'wipe_status': None}]:
        _FakeDeletionDoc.data = payload
        got = account_fence.account_deletion_fence_is_terminal('uid-1')
        assert got is False, f'payload={payload!r} classified {got}'


def test_empty_locked_content_and_fenced_unlock_is_still_acknowledged(lane):
    """A fenced account downgrading to Basic never unlocks — nothing to classify.

    With a stored Basic row and a superseded canceled snapshot, the decision
    projects Basic with no unlock effects at all: the fence is never consulted,
    the delivery acknowledges cleanly, and the downgrade persists.
    """
    state, fences = lane
    _FakeDeletionDoc.data = {'wipe_status': 'completed'}
    _FakeDeletionDoc.read_error = None
    fences.on = True
    state.stripe_obj = _deleted_subscription_event()['data']['object']
    state.event = _deleted_subscription_event()
    state.current = Subscription(plan=PlanType.basic, stripe_subscription_id='sub-old')

    response = _post_webhook()

    assert response.status_code == 200
    assert response.json()['status'] == 'success'
    # A Basic projection carries no unlock/set_customer effects to fence.
    assert _call_names(state) == ['write', 'telemetry', 'credits', 'trial_cache']
    assert 'conversations' not in _call_names(state)
    assert state.current.plan == PlanType.basic
