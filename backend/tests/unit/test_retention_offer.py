"""Cancel-flow stay offer: 50% off 3 monthly invoices, once per Stripe customer."""

import copy
import os
import threading

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import utils.retention_offer as ro  # noqa: E402


def _sub(**over):
    sub = {
        'id': 'sub_1',
        'customer': 'cus_1',
        'status': 'active',
        'schedule': None,
        'discount': None,
        'discounts': [],
        'items': {
            'data': [
                {'quantity': 1, 'price': {'unit_amount': 2999, 'currency': 'usd', 'recurring': {'interval': 'month'}}}
            ]
        },
    }
    sub.update(over)
    return sub


def _customer(used=False):
    return {'id': 'cus_1', 'metadata': {ro.USED_METADATA_KEY: 'sub_old'} if used else {}}


def test_monthly_paid_subscription_is_eligible_with_half_price():
    offer = ro.evaluate(_sub(), _customer())
    assert offer.eligible
    assert (offer.regular_amount, offer.discounted_amount, offer.currency) == (2999, 1499, 'usd')
    assert (offer.percent_off, offer.duration_months) == (50, 3)


@pytest.mark.parametrize(
    'sub,customer,reason',
    [
        (None, _customer(), 'no_subscription'),
        (_sub(status='trialing'), _customer(), 'status'),
        (_sub(status='canceled'), _customer(), 'status'),
        (_sub(schedule='sub_sched_1'), _customer(), 'scheduled_change'),
        (_sub(discounts=['di_1']), _customer(), 'already_discounted'),
        (_sub(), _customer(used=True), 'already_used'),
        (
            _sub(items={'data': [{'price': {'unit_amount': 26991, 'currency': 'usd', 'recurring': {'interval': 'year'}}}]}),
            _customer(),
            'not_monthly',
        ),
        (
            _sub(items={'data': [{'price': {'unit_amount': 0, 'currency': 'usd', 'recurring': {'interval': 'month'}}}]}),
            _customer(),
            'free_price',
        ),
    ],
)
def test_ineligible_cases(sub, customer, reason):
    offer = ro.evaluate(sub, customer)
    assert not offer.eligible and offer.reason == reason


def test_lookup_failure_hides_the_offer(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('stripe down')

    monkeypatch.setattr(ro.stripe.Subscription, 'retrieve', boom)
    assert ro.get_offer('sub_1').reason == 'unavailable'
    assert ro.get_offer(None).reason == 'no_subscription'


class _FakeStripe:
    """Shared in-memory Stripe + Redis for accept(): subscriptions, customers, coupons, lock keys."""

    def __init__(self, monkeypatch, subs, used_by=None):
        self.subs = {s['id']: s for s in subs}
        self.customers = {'cus_1': {'id': 'cus_1', 'metadata': {ro.USED_METADATA_KEY: used_by} if used_by else {}}}
        self.coupons = {}
        self.locks = set()
        self.lock_guard = threading.Lock()
        self.calls = []
        self.fail_customer_modify = False
        self.before_customer_read = None
        monkeypatch.setattr(ro.stripe.Subscription, 'retrieve', self.sub_retrieve)
        monkeypatch.setattr(ro.stripe.Subscription, 'modify', self.sub_modify)
        monkeypatch.setattr(ro.stripe.Customer, 'retrieve', self.cus_retrieve)
        monkeypatch.setattr(ro.stripe.Customer, 'modify', self.cus_modify)
        monkeypatch.setattr(ro.stripe.Coupon, 'retrieve', self.coupon_retrieve)
        monkeypatch.setattr(ro.stripe.Coupon, 'create', lambda **kw: self.coupons.setdefault(kw['id'], kw))
        monkeypatch.setattr(ro, '_acquire_lock', self.acquire)
        monkeypatch.setattr(ro, '_release_lock', lambda cid: self.locks.discard(cid))

    def acquire(self, cid):
        with self.lock_guard:
            if cid in self.locks:
                return False
            self.locks.add(cid)
            return True

    def sub_retrieve(self, sid, **kw):
        return copy.deepcopy(self.subs[sid])

    def sub_modify(self, sid, **kw):
        self.calls.append(('sub', sid, kw))
        sub = self.subs[sid]
        if 'discounts' in kw:
            sub['discounts'] = [{'id': 'di_' + sid, 'source': {'coupon': {'id': kw['discounts'][0]['coupon']}}}]
        if 'cancel_at_period_end' in kw:
            sub['cancel_at_period_end'] = kw['cancel_at_period_end']

    def cus_retrieve(self, cid, **kw):
        if self.before_customer_read:
            self.before_customer_read()
        return copy.deepcopy(self.customers[cid])

    def cus_modify(self, cid, **kw):
        self.calls.append(('cus', cid, kw))
        if self.fail_customer_modify:
            raise RuntimeError('stripe 500')
        self.customers[cid]['metadata'].update(kw['metadata'])

    def coupon_retrieve(self, cid):
        if cid not in self.coupons:
            raise ro.stripe.error.InvalidRequestError('No such coupon', 'id')
        return self.coupons[cid]

    def discounted(self):
        return sorted(sid for sid, s in self.subs.items() if s.get('discounts'))


def test_accept_claims_customer_then_discounts_and_clears_cancel(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub(cancel_at_period_end=True)])

    offer = ro.accept('sub_1')

    assert offer.eligible
    assert [c[0] for c in fake.calls] == ['cus', 'sub']  # claim before discount
    assert fake.customers['cus_1']['metadata'][ro.USED_METADATA_KEY] == 'sub_1'
    assert fake.subs['sub_1']['cancel_at_period_end'] is False and fake.discounted() == ['sub_1']
    assert fake.calls[1][2]['idempotency_key'] == 'retention-apply-sub_1'
    assert fake.coupons[ro.COUPON_ID]['percent_off'] == 50 and fake.locks == set()


def test_second_subscription_of_same_customer_is_refused(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub(), _sub(id='sub_2')])
    ro.accept('sub_1')
    with pytest.raises(ValueError, match='already_used'):
        ro.accept('sub_2')
    assert fake.discounted() == ['sub_1']


def test_concurrent_redemptions_for_one_customer_discount_only_one(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub(), _sub(id='sub_2')])
    both_started = threading.Barrier(2, timeout=5)
    results = {}

    def run(sid):
        try:
            both_started.wait()
            results[sid] = ro.accept(sid).reason
        except ValueError as exc:
            results[sid] = str(exc)

    threads = [threading.Thread(target=run, args=(sid,)) for sid in ('sub_1', 'sub_2')]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(fake.discounted()) == 1
    winner = fake.discounted()[0]
    loser = 'sub_2' if winner == 'sub_1' else 'sub_1'
    assert results[winner] == 'eligible' and results[loser] in ('in_progress', 'already_used')
    # A later retry by the loser is still refused, and the winner's retry does not reapply.
    with pytest.raises(ValueError, match='already_used'):
        ro.accept(loser)
    assert ro.accept(winner).reason == 'already_applied'
    assert len(fake.discounted()) == 1


def test_lock_held_by_another_worker_refuses_without_writes(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub()])
    fake.locks.add('cus_1')
    with pytest.raises(ValueError, match='in_progress'):
        ro.accept('sub_1')
    assert fake.calls == []


def test_retry_after_discount_failure_finishes_the_same_claim(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub()])
    real_modify = fake.sub_modify

    def discount_fails(sid, **kw):
        raise RuntimeError('stripe 500')

    monkeypatch.setattr(ro.stripe.Subscription, 'modify', discount_fails)
    with pytest.raises(RuntimeError):
        ro.accept('sub_1')
    assert fake.customers['cus_1']['metadata'][ro.USED_METADATA_KEY] == 'sub_1' and fake.discounted() == []
    assert fake.locks == set()

    monkeypatch.setattr(ro.stripe.Subscription, 'modify', real_modify)
    assert ro.accept('sub_1').eligible and fake.discounted() == ['sub_1']
    assert ro.get_offer('sub_1').reason == 'already_discounted'


def test_retry_after_claim_write_failure_recovers(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub()])
    fake.fail_customer_modify = True
    with pytest.raises(RuntimeError):
        ro.accept('sub_1')
    assert fake.discounted() == [] and fake.locks == set()

    fake.fail_customer_modify = False
    assert ro.accept('sub_1').eligible and fake.discounted() == ['sub_1']


def test_retry_after_lost_success_response_is_a_no_op(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub()])
    ro.accept('sub_1')
    fake.calls.clear()
    assert ro.accept('sub_1').reason == 'already_applied'
    assert fake.calls == []


def test_discounted_without_claim_reconciles_the_claim(monkeypatch):
    applied = _sub(discounts=[{'id': 'di_1', 'source': {'coupon': {'id': ro.COUPON_ID}}}], cancel_at_period_end=True)
    fake = _FakeStripe(monkeypatch, [applied])
    assert ro.accept('sub_1').reason == 'already_applied'
    assert fake.customers['cus_1']['metadata'][ro.USED_METADATA_KEY] == 'sub_1'
    assert fake.subs['sub_1']['cancel_at_period_end'] is False


def test_claimed_by_another_subscription_is_refused_without_writes(monkeypatch):
    fake = _FakeStripe(monkeypatch, [_sub()], used_by='sub_old')
    with pytest.raises(ValueError, match='already_used'):
        ro.accept('sub_1')
    assert fake.calls == []
