from decimal import Decimal

import pytest

from config import Settings
from payment.ledger import EXECUTING, Ledger, LimitExceeded
from payment.policy import Action, Source, SpendingPolicy, format_usd, to_micro

URL = "https://api.example.com/data"


def make_policy(**overrides):
    values = {"max_per_payment_usd": "5", "daily_limit_usd": "20", "auto_approve_usd": "1", "_env_file": None}
    return SpendingPolicy(Settings(**{**values, **overrides}))


def usd(value):
    return to_micro(Decimal(value))


def test_voice_always_needs_confirmation():
    assert make_policy().evaluate(usd("0.01"), URL, 0, Source.VOICE).action is Action.CONFIRM


def test_chat_under_threshold_is_auto_approved():
    assert make_policy().evaluate(usd("1"), URL, 0, Source.CHAT).action is Action.ALLOW


def test_chat_over_threshold_needs_confirmation():
    assert make_policy().evaluate(usd("1.01"), URL, 0, Source.CHAT).action is Action.CONFIRM


def test_default_config_confirms_every_chat_payment():
    policy = SpendingPolicy(Settings(_env_file=None))
    assert policy.evaluate(usd("0.01"), URL, 0, Source.CHAT).action is Action.CONFIRM


def test_confirmed_payment_is_allowed():
    assert make_policy().evaluate(usd("5"), URL, 0, Source.VOICE, confirmed=True).action is Action.ALLOW


def test_per_payment_limit_denies_even_when_confirmed():
    decision = make_policy().evaluate(usd("5.01"), URL, 0, Source.CHAT, confirmed=True)
    assert decision.action is Action.DENY
    assert "per-payment" in decision.reason


def test_daily_limit_boundary():
    policy = make_policy()
    assert policy.evaluate(usd("5"), URL, usd("15"), Source.CHAT, confirmed=True).action is Action.ALLOW
    denied = policy.evaluate(usd("5"), URL, usd("15.01"), Source.CHAT, confirmed=True)
    assert denied.action is Action.DENY
    assert "$4.99" in denied.reason


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_non_positive_amount_denied(amount):
    assert make_policy().evaluate(usd(amount), URL, 0, Source.CHAT).action is Action.DENY


def test_http_target_denied():
    assert make_policy().evaluate(usd("1"), "http://api.example.com", 0, Source.CHAT).action is Action.DENY


def test_domain_allowlist():
    policy = make_policy(allowed_domains="example.com")
    assert policy.evaluate(usd("1"), URL, 0, Source.CHAT).action is Action.ALLOW
    assert policy.evaluate(usd("1"), "https://example.com.evil.io", 0, Source.CHAT).action is Action.DENY
    assert policy.evaluate(usd("1"), "https://notexample.com", 0, Source.CHAT).action is Action.DENY


def test_format_usd():
    assert format_usd(usd("5")) == "$5.00"
    assert format_usd(usd("2.5")) == "$2.50"
    assert format_usd(1) == "$0.000001"


@pytest.fixture
def ledger(tmp_path):
    return Ledger(str(tmp_path / "ledger.db"))


def allow(*_):
    return None


def daily_cap(limit):
    return lambda amount, _target, spent: "over" if spent + amount > limit else None


def test_code_is_single_use(ledger):
    ledger.create_pending("u", 100, URL, "", "voice", "123456", 300)
    assert ledger.claim("u", "123456", allow).status == EXECUTING
    assert ledger.claim("u", "123456", allow) is None


def test_code_is_bound_to_its_user(ledger):
    ledger.create_pending("u", 100, URL, "", "voice", "123456", 300)
    assert ledger.claim("someone-else", "123456", allow) is None


def test_expired_code_rejected(ledger):
    ledger.create_pending("u", 100, URL, "", "voice", "123456", -1)
    assert ledger.claim("u", "123456", allow) is None


def test_repeated_wrong_codes_cancel_pending(ledger):
    ledger.create_pending("u", 100, URL, "", "voice", "123456", 300)
    for _ in range(5):
        assert ledger.claim("u", "000000", allow) is None
    assert ledger.claim("u", "123456", allow) is None


def test_duplicate_pending_not_created(ledger):
    assert ledger.create_pending("u", 100, URL, "", "voice", "111111", 300)
    assert ledger.create_pending("u", 100, URL, "", "voice", "222222", 300) is None


def test_spend_counts_executing_and_unknown_but_not_failed(ledger):
    first = ledger.reserve("u", 100, URL, "", "chat", allow)
    second = ledger.reserve("u", 200, URL, "", "chat", allow)
    third = ledger.reserve("u", 400, URL, "", "chat", allow)
    ledger.finish(first.id, "unknown")
    ledger.finish(second.id, "failed")
    ledger.finish(third.id, "settled", "0xabc")
    assert ledger.spent_today("u") == 500


def test_reserve_enforces_cap(ledger):
    ledger.reserve("u", 900, URL, "", "chat", daily_cap(1000))
    with pytest.raises(LimitExceeded):
        ledger.reserve("u", 200, URL, "", "chat", daily_cap(1000))


def test_cancel_only_affects_own_pending(ledger):
    ledger.create_pending("u", 100, URL, "", "voice", "111111", 300)
    assert ledger.cancel_pending("other") == 0
    assert ledger.cancel_pending("u") == 1
