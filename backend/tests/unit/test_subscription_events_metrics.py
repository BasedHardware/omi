"""Stripe subscription lifecycle event metric — mapping, bounds, and fail-open behavior.

Cancellations are otherwise invisible in real time (no system tracks them), so
``record_subscription_event`` in ``utils.observability.subscription_events`` is
the seam that turns ``customer.subscription.*`` webhook deliveries into the
bounded ``omi_subscription_events_total`` counter. The mapping from a raw
Stripe event to a metric event is the part most likely to silently drift, so
it is exercised here against realistic event/subscription payload shapes
rather than through the full webhook route (which needs a heavy Firestore
import chain unavailable to this test process; see
``test_stripe_webhook_none_guard.py`` for that same constraint).

Two invariants matter as much as the mapping itself: instrumentation must
never raise into the caller (a malformed payload or a resolver exception is
swallowed and logged, not propagated), and every label stays inside its
closed, low-cardinality set — never a uid, customer id, subscription id,
price id, or email.
"""

from __future__ import annotations

import logging
from pathlib import Path

from utils.metrics import OMI_SUBSCRIPTION_EVENTS
from utils.observability.subscription_events import (
    _EVENTS,
    _INTERVALS,
    _PLANS,
    _REASONS,
    _reachable_reasons,
    record_subscription_event,
)

# Real, currently-recognized catalog prices (backend/config/plan_catalog.json),
# one per plan, so plan/interval resolution is exercised against the actual
# resolver rather than a stand-in mapping.
_UNLIMITED_MONTH_PRICE = 'price_1RrxXL1F8wnoWYvwIddzR902'
_UNLIMITED_YEAR_PRICE = 'price_1RrxXL1F8wnoWYvw3kDbWmjs'
_ARCHITECT_MONTH_PRICE = 'price_1TLFXK1F8wnoWYvwG1TaUkZ3'

# A customer/uid deliberately shaped to fail the test if it ever leaked into a label.
_SECRET_CUSTOMER_ID = 'cus_SHOULD_NEVER_APPEAR'
_SECRET_UID = 'uid_SHOULD_NEVER_APPEAR'


def _price(price_id: str, interval: str = 'month') -> dict:
    return {'id': price_id, 'recurring': {'interval': interval}}


def _subscription_obj(
    *,
    price_id: str = _UNLIMITED_MONTH_PRICE,
    interval: str = 'month',
    status: str = 'active',
    cancel_at_period_end: bool = False,
    cancellation_details: dict | None = None,
) -> dict:
    return {
        'id': 'sub_test_123',
        'status': status,
        'cancel_at_period_end': cancel_at_period_end,
        'items': {'data': [{'price': _price(price_id, interval)}]},
        'cancellation_details': cancellation_details or {},
        'customer': _SECRET_CUSTOMER_ID,
        'metadata': {'uid': _SECRET_UID},
    }


def _count(**labels) -> float:
    return OMI_SUBSCRIPTION_EVENTS.labels(**labels)._value.get()


def _total() -> float:
    return sum(
        sample.value
        for family in OMI_SUBSCRIPTION_EVENTS.collect()
        for sample in family.samples
        if sample.name == 'omi_subscription_events_total'
    )


def _all_recorded_label_values() -> set[str]:
    values: set[str] = set()
    for family in OMI_SUBSCRIPTION_EVENTS.collect():
        for sample in family.samples:
            values.update(sample.labels.values())
    return values


def test_bounded_label_surface_is_exactly_event_plan_interval_reason():
    assert set(OMI_SUBSCRIPTION_EVENTS._labelnames) == {'event', 'plan', 'interval', 'reason'}


def test_created_event_maps_to_created_with_plan_and_interval():
    before = _count(event='created', plan='unlimited', interval='month', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.created',
        subscription_obj=_subscription_obj(price_id=_UNLIMITED_MONTH_PRICE, interval='month'),
    )

    assert _count(event='created', plan='unlimited', interval='month', reason='none') == before + 1


def test_deleted_event_maps_to_ended_with_cancellation_reason():
    before = _count(event='ended', plan='architect', interval='month', reason='cancellation_requested')

    record_subscription_event(
        stripe_event_type='customer.subscription.deleted',
        subscription_obj=_subscription_obj(
            price_id=_ARCHITECT_MONTH_PRICE,
            interval='month',
            status='canceled',
            cancellation_details={'reason': 'cancellation_requested'},
        ),
    )

    assert _count(event='ended', plan='architect', interval='month', reason='cancellation_requested') == before + 1


def test_deleted_event_with_no_cancellation_reason_records_none():
    before = _count(event='ended', plan='unlimited', interval='year', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.deleted',
        subscription_obj=_subscription_obj(
            price_id=_UNLIMITED_YEAR_PRICE, interval='year', status='canceled', cancellation_details=None
        ),
    )

    assert _count(event='ended', plan='unlimited', interval='year', reason='none') == before + 1


def test_updated_cancel_at_period_end_false_to_true_is_cancellation_requested():
    before = _count(event='cancellation_requested', plan='unlimited', interval='month', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_subscription_obj(cancel_at_period_end=True),
        previous_attributes={'cancel_at_period_end': False},
    )

    assert _count(event='cancellation_requested', plan='unlimited', interval='month', reason='none') == before + 1


def test_updated_cancel_at_period_end_true_to_false_is_cancellation_reverted():
    before = _count(event='cancellation_reverted', plan='unlimited', interval='month', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_subscription_obj(cancel_at_period_end=False),
        previous_attributes={'cancel_at_period_end': True},
    )

    assert _count(event='cancellation_reverted', plan='unlimited', interval='month', reason='none') == before + 1


def test_updated_status_change_to_past_due_or_unpaid_is_payment_failed():
    for new_status in ('past_due', 'unpaid'):
        before = _count(event='payment_failed', plan='unlimited', interval='month', reason='none')

        record_subscription_event(
            stripe_event_type='customer.subscription.updated',
            subscription_obj=_subscription_obj(status=new_status),
            previous_attributes={'status': 'active'},
        )

        assert (
            _count(event='payment_failed', plan='unlimited', interval='month', reason='none') == before + 1
        ), new_status


def test_updated_status_change_to_active_is_not_payment_failed():
    """A status change back to active (e.g. dunning recovery) is not itself a tracked event."""
    total_before = _total()

    record_subscription_event(
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_subscription_obj(status='active'),
        previous_attributes={'status': 'past_due'},
    )

    assert _total() == total_before


def test_updated_with_unrelated_previous_attributes_records_nothing():
    total_before = _total()

    record_subscription_event(
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_subscription_obj(),
        previous_attributes={'items': 'changed', 'default_payment_method': 'pm_old'},
    )

    assert _total() == total_before


def test_updated_with_no_previous_attributes_records_nothing():
    total_before = _total()

    record_subscription_event(
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_subscription_obj(),
        previous_attributes=None,
    )
    record_subscription_event(
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_subscription_obj(),
        previous_attributes={},
    )

    assert _total() == total_before


def test_unrelated_event_type_records_nothing():
    total_before = _total()

    record_subscription_event(
        stripe_event_type='invoice.payment_succeeded',
        subscription_obj=_subscription_obj(),
        previous_attributes={},
    )

    assert _total() == total_before


def test_unresolvable_price_id_falls_back_to_unknown_plan():
    """Plan resolution fails independently of interval: interval is read directly
    off the price object and stays known even when the price id itself is not
    in the catalog."""
    before = _count(event='created', plan='unknown', interval='month', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.created',
        subscription_obj=_subscription_obj(price_id='price_does_not_exist_in_catalog', interval='month'),
    )

    assert _count(event='created', plan='unknown', interval='month', reason='none') == before + 1


def test_missing_price_falls_back_to_unknown_plan():
    before = _count(event='created', plan='unknown', interval='unknown', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.created',
        subscription_obj={'id': 'sub_no_items', 'status': 'active', 'items': {'data': []}},
    )

    assert _count(event='created', plan='unknown', interval='unknown', reason='none') == before + 1


def test_price_resolver_raising_unexpected_exception_falls_back_to_unknown(monkeypatch):
    from utils.observability import subscription_events

    def _boom(_price_id):
        raise RuntimeError('stripe catalog exploded')

    monkeypatch.setattr(subscription_events, 'resolve_stripe_price_plan', _boom)
    before = _count(event='created', plan='unknown', interval='month', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.created',
        subscription_obj=_subscription_obj(price_id=_UNLIMITED_MONTH_PRICE, interval='month'),
    )

    assert _count(event='created', plan='unknown', interval='month', reason='none') == before + 1


def test_unrecognized_cancellation_reason_falls_back_to_none():
    before = _count(event='ended', plan='unlimited', interval='month', reason='none')

    record_subscription_event(
        stripe_event_type='customer.subscription.deleted',
        subscription_obj=_subscription_obj(
            status='canceled', cancellation_details={'reason': 'some_future_stripe_reason'}
        ),
    )

    assert _count(event='ended', plan='unlimited', interval='month', reason='none') == before + 1


def test_none_subscription_object_does_not_raise(caplog):
    total_before = _total()

    with caplog.at_level(logging.WARNING):
        record_subscription_event(stripe_event_type='customer.subscription.created', subscription_obj=None)

    # A created event with no subscription data still resolves to created/unknown/unknown/none.
    assert _total() == total_before + 1


def test_malformed_non_mapping_subscription_object_does_not_raise(caplog):
    total_before = _total()

    with caplog.at_level(logging.WARNING, logger='utils.observability.subscription_events'):
        record_subscription_event(
            stripe_event_type='customer.subscription.updated',
            subscription_obj='not-a-mapping',
            previous_attributes={'cancel_at_period_end': False},
        )

    assert _total() == total_before
    assert any('subscription_event_record_failed' in record.message for record in caplog.records)


def test_malformed_items_shape_does_not_raise():
    total_before = _total()

    record_subscription_event(
        stripe_event_type='customer.subscription.created',
        subscription_obj={'id': 'sub_x', 'status': 'active', 'items': 'not-a-dict'},
    )

    # Falls back to unknown/unknown rather than raising.
    assert _total() == total_before + 1


def test_no_uid_or_customer_id_ever_appears_in_a_recorded_label():
    record_subscription_event(
        stripe_event_type='customer.subscription.created',
        subscription_obj=_subscription_obj(price_id=_UNLIMITED_MONTH_PRICE),
    )
    record_subscription_event(
        stripe_event_type='customer.subscription.deleted',
        subscription_obj=_subscription_obj(
            price_id=_ARCHITECT_MONTH_PRICE, status='canceled', cancellation_details={'reason': 'payment_failure'}
        ),
    )

    recorded_values = _all_recorded_label_values()
    assert _SECRET_CUSTOMER_ID not in recorded_values
    assert _SECRET_UID not in recorded_values
    assert 'sub_test_123' not in recorded_values
    assert _UNLIMITED_MONTH_PRICE not in recorded_values
    assert _ARCHITECT_MONTH_PRICE not in recorded_values


def test_all_recorded_labels_stay_within_the_bounded_sets():
    allowed_events = {'created', 'cancellation_requested', 'cancellation_reverted', 'ended', 'payment_failed'}
    allowed_plans = {'basic', 'unlimited', 'architect', 'operator', 'plus', 'unlimited_v2', 'unknown'}
    allowed_intervals = {'month', 'year', 'unknown'}
    allowed_reasons = {'cancellation_requested', 'payment_failure', 'payment_disputed', 'none'}

    for family in OMI_SUBSCRIPTION_EVENTS.collect():
        for sample in family.samples:
            if sample.name != 'omi_subscription_events_total':
                continue
            assert sample.labels['event'] in allowed_events
            assert sample.labels['plan'] in allowed_plans
            assert sample.labels['interval'] in allowed_intervals
            assert sample.labels['reason'] in allowed_reasons


# ---------------------------------------------------------------------------
# routers/payment.py cannot be imported in this test process — it pulls in the
# full Firestore/firebase_admin chain (see test_stripe_webhook_none_guard.py).
# The wiring into the customer.subscription.* branch is verified at source
# level instead: the recorder is imported and called inside that branch with
# both the raw Stripe event type and previous_attributes.
# ---------------------------------------------------------------------------


def _payment_router_source() -> str:
    return (Path(__file__).resolve().parents[2] / 'routers' / 'payment.py').read_text(encoding='utf-8')


def test_webhook_imports_the_subscription_event_recorder():
    source = _payment_router_source()
    assert 'from utils.observability.subscription_events import record_subscription_event' in source


def test_webhook_calls_the_recorder_inside_the_subscription_event_branch():
    source = _payment_router_source()
    branch_marker = "'customer.subscription.created',\n    ]:"
    branch_start = source.index(branch_marker) + len(branch_marker)
    # Look at the handler body immediately following the type-check block, before
    # the next top-level branch, so the call is confirmed inside this branch
    # rather than merely present somewhere later in the file.
    next_branch = source.index("if event['type'] in [", branch_start)
    branch_body = source[branch_start:next_branch]

    assert 'record_subscription_event(' in branch_body
    assert "stripe_event_type=event['type']" in branch_body
    assert "previous_attributes=event.get('data', {}).get('previous_attributes')" in branch_body


# ---------------------------------------------------------------------------
# Born-at-zero. A Counter child does not exist until its first ``.inc()``, so an
# uninitialized labelled series is first scraped already holding 1 and is never
# observed at 0. ``increase()``/``rate()`` measure movement inside the query
# window, so a series that appears at 1 and stays there contributes exactly 0 —
# the first event for a label combination is invisible to every panel and rule
# built on them. Subscription events are rare enough, and ``plan`` x
# ``interval`` x one process per Cloud Run instance wide enough, that almost
# every event is the first for its combination.
# ---------------------------------------------------------------------------

_PLUS_YEAR_PRICE = 'price_1TuHCw1F8wnoWYvwZvKu86sI'

_Series = tuple[str, str, str, str]


def _exported_series() -> dict[_Series, float]:
    return {
        (
            sample.labels['event'],
            sample.labels['plan'],
            sample.labels['interval'],
            sample.labels['reason'],
        ): sample.value
        for family in OMI_SUBSCRIPTION_EVENTS.collect()
        for sample in family.samples
        if sample.name == 'omi_subscription_events_total'
    }


def _reachable_series() -> set[_Series]:
    return {
        (event, plan, interval, reason)
        for event in _EVENTS
        for plan in _PLANS
        for interval in _INTERVALS
        for reason in _reachable_reasons(event)
    }


def test_every_reachable_label_combination_is_exported_before_its_first_event():
    exported = set(_exported_series())

    missing = sorted(_reachable_series() - exported)
    assert missing == [], (
        'These label combinations have no series until their first event, so that first event '
        f'would be invisible to increase(): {missing}'
    )


def test_zero_initialization_stays_inside_the_space_recording_can_emit():
    exported = set(_exported_series())
    reachable = _reachable_series()

    # 4 reason-free events x 7 plans x 3 intervals, plus `ended` x 7 x 3 x 4 reasons.
    assert len(reachable) == 168
    # Both the initialization and the recording path read the same label sets,
    # so neither can grow a combination the other does not know about.
    assert exported - reachable == set()


def test_only_ended_can_ever_carry_a_cancellation_reason():
    for event in _EVENTS:
        if event == 'ended':
            assert set(_reachable_reasons(event)) == set(_REASONS)
        else:
            assert _reachable_reasons(event) == ('none',)


def test_a_first_event_steps_a_series_that_was_already_exported_at_zero():
    """The shape increase() needs: a step up from an existing sample, not an appearance at 1."""

    series: _Series = ('cancellation_requested', 'plus', 'year', 'none')
    before = _exported_series()
    assert series in before

    record_subscription_event(
        stripe_event_type='customer.subscription.updated',
        subscription_obj=_subscription_obj(
            price_id=_PLUS_YEAR_PRICE,
            interval='year',
            cancel_at_period_end=True,
        ),
        previous_attributes={'cancel_at_period_end': False},
    )

    assert _exported_series()[series] == before[series] + 1
