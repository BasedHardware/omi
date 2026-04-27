import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Heavy deps must be stubbed before importing utils.stripe so the import
# does not pull in real GCP/Redis clients.
sys.modules.setdefault("stripe", MagicMock())
sys.modules.setdefault("database._client", MagicMock())
sys.modules.setdefault("database.redis_db", MagicMock())

_database_module = sys.modules.setdefault("database", types.ModuleType("database"))
_database_module.redis_db = sys.modules["database.redis_db"]

_pycountry_module = sys.modules.setdefault("pycountry", types.ModuleType("pycountry"))
_pycountry_module.countries = MagicMock()

from utils import stripe as stripe_utils  # noqa: E402


def _fake_sub(sub_id, cancel_at_period_end=False):
    sub = MagicMock()
    sub.id = sub_id
    sub.cancel_at_period_end = cancel_at_period_end
    return sub


class _FakeListing:
    """Mimic stripe.ListObject — only auto_paging_iter is used by the helper."""

    def __init__(self, items):
        self._items = items

    def auto_paging_iter(self):
        return iter(self._items)


def _setup_stripe(active=None, trialing=None, list_side_effect=None, modify_side_effect=None):
    stripe_utils.stripe.Subscription = MagicMock()

    def _list(customer, status, limit):
        if list_side_effect is not None:
            res = list_side_effect(status)
            if isinstance(res, Exception):
                raise res
            return res
        if status == 'active':
            return _FakeListing(active or [])
        if status == 'trialing':
            return _FakeListing(trialing or [])
        return _FakeListing([])

    stripe_utils.stripe.Subscription.list.side_effect = _list

    if modify_side_effect is not None:
        stripe_utils.stripe.Subscription.modify.side_effect = modify_side_effect
    else:
        stripe_utils.stripe.Subscription.modify.return_value = MagicMock()


def test_cancels_active_and_trialing_subscriptions():
    _setup_stripe(
        active=[_fake_sub('sub_a1'), _fake_sub('sub_a2')],
        trialing=[_fake_sub('sub_t1')],
    )

    result = stripe_utils.cancel_all_active_subscriptions('cus_123')

    assert result['cancelled'] == ['sub_a1', 'sub_a2', 'sub_t1']
    assert result['skipped'] == []
    assert result['errors'] == []

    modify_calls = stripe_utils.stripe.Subscription.modify.call_args_list
    assert [c.args[0] for c in modify_calls] == ['sub_a1', 'sub_a2', 'sub_t1']
    for call in modify_calls:
        assert call.kwargs == {'cancel_at_period_end': True}


def test_idempotent_when_already_scheduled_for_cancellation():
    _setup_stripe(
        active=[
            _fake_sub('sub_already', cancel_at_period_end=True),
            _fake_sub('sub_fresh'),
        ],
    )

    result = stripe_utils.cancel_all_active_subscriptions('cus_123')

    assert result['cancelled'] == ['sub_fresh']
    assert result['skipped'] == ['sub_already']
    assert result['errors'] == []
    # The already-scheduled sub must not be modified again.
    modified_ids = [c.args[0] for c in stripe_utils.stripe.Subscription.modify.call_args_list]
    assert 'sub_already' not in modified_ids


def test_per_subscription_modify_failure_is_captured_and_loop_continues():
    def _modify(sub_id, cancel_at_period_end):
        if sub_id == 'sub_bad':
            raise RuntimeError('stripe 500 on sub_bad')
        return MagicMock()

    _setup_stripe(
        active=[_fake_sub('sub_ok1'), _fake_sub('sub_bad'), _fake_sub('sub_ok2')],
        modify_side_effect=_modify,
    )

    result = stripe_utils.cancel_all_active_subscriptions('cus_123')

    assert result['cancelled'] == ['sub_ok1', 'sub_ok2']
    assert result['skipped'] == []
    assert result['errors'] == [{'context': 'sub_bad', 'err': 'stripe 500 on sub_bad'}]


def test_list_call_failure_for_one_status_does_not_block_the_other():
    def _list(status):
        if status == 'active':
            raise RuntimeError('stripe outage on active list')
        return _FakeListing([_fake_sub('sub_t1')])

    _setup_stripe(list_side_effect=_list)

    result = stripe_utils.cancel_all_active_subscriptions('cus_123')

    assert result['cancelled'] == ['sub_t1']
    assert result['skipped'] == []
    assert result['errors'] == [{'context': 'list:active', 'err': 'stripe outage on active list'}]


def test_no_subscriptions_returns_empty_lists():
    _setup_stripe()

    result = stripe_utils.cancel_all_active_subscriptions('cus_empty')

    assert result == {'cancelled': [], 'skipped': [], 'errors': []}
    stripe_utils.stripe.Subscription.modify.assert_not_called()


def test_pagination_via_auto_paging_iter_processes_all_pages():
    # 45 active subs across what would be multiple pages — we don't care about
    # page boundaries here, only that auto_paging_iter is the iteration source
    # and every sub is processed exactly once.
    many = [_fake_sub(f'sub_{i}') for i in range(45)]
    _setup_stripe(active=many)

    result = stripe_utils.cancel_all_active_subscriptions('cus_big')

    assert len(result['cancelled']) == 45
    assert result['cancelled'] == [f'sub_{i}' for i in range(45)]
    assert stripe_utils.stripe.Subscription.modify.call_count == 45


def test_uniform_error_shape_across_both_failure_paths():
    """Caller (routers/users.py) only calls sanitize(str(...)) on errors —
    both shapes must be uniform {'context': str, 'err': str}."""

    def _list(status):
        if status == 'trialing':
            raise RuntimeError('list trialing failed')
        return _FakeListing([_fake_sub('sub_x')])

    def _modify(sub_id, cancel_at_period_end):
        raise RuntimeError(f'modify {sub_id} failed')

    _setup_stripe(list_side_effect=_list, modify_side_effect=_modify)

    result = stripe_utils.cancel_all_active_subscriptions('cus_mixed')

    assert result['cancelled'] == []
    for entry in result['errors']:
        assert set(entry.keys()) == {'context', 'err'}
        assert isinstance(entry['context'], str)
        assert isinstance(entry['err'], str)

    contexts = sorted(e['context'] for e in result['errors'])
    assert contexts == ['list:trialing', 'sub_x']
