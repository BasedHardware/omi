"""Both phone-verification entry points share one registration contract.

The chat tool used to call Twilio directly, skipping the route's per-user attempt
budget and the 21450 mapping, so a user could buy extra (billable) verification
calls and get an opaque failure instead of "already in progress".
"""

import pytest
from twilio.base.exceptions import TwilioRestException

import utils.phone_registration as pr


@pytest.fixture(autouse=True)
def _isolated_limit_store(monkeypatch):
    monkeypatch.setattr(pr.endpoints, 'cached', {})
    monkeypatch.setattr(pr, 'check_call_access', lambda uid: None)
    monkeypatch.setattr(pr.phone_calls_db, 'get_phone_number_by_number', lambda uid, number: None)
    monkeypatch.setattr(pr.phone_calls_db, 'set_pending_verification', lambda uid, number: None)


def _count_twilio_calls(monkeypatch):
    calls = []

    def _start(number):
        calls.append(number)
        return {
            'verification_sid': 'VA1',
            'phone_number': number,
            'validation_code': '123456',
            'status': 'pending',
        }

    monkeypatch.setattr(pr, 'start_caller_id_verification', _start)
    return calls


def test_chat_path_is_bounded_by_the_same_attempt_budget(monkeypatch):
    calls = _count_twilio_calls(monkeypatch)

    replies = [pr.start_phone_verification_for_chat('uid1', '+15551234567') for _ in range(8)]

    assert len(calls) == pr.PHONE_VERIFY_REQUESTS_PER_WINDOW
    assert 'Too many verification attempts' in replies[-1]


def test_budget_is_per_user(monkeypatch):
    calls = _count_twilio_calls(monkeypatch)

    for _ in range(pr.PHONE_VERIFY_REQUESTS_PER_WINDOW):
        pr.start_phone_verification_for_chat('uid1', '+15551234567')
    pr.start_phone_verification_for_chat('uid2', '+15551234567')

    assert len(calls) == pr.PHONE_VERIFY_REQUESTS_PER_WINDOW + 1


def test_pending_verification_is_reported_not_swallowed(monkeypatch):
    def _start(number):
        raise TwilioRestException(status=400, uri='/x', code=21450, msg='already exists')

    monkeypatch.setattr(pr, 'start_caller_id_verification', _start)
    monkeypatch.setattr(pr, 'get_caller_id', lambda number: None)

    reply = pr.start_phone_verification_for_chat('uid1', '+15551234567')

    assert 'already in progress' in reply


def test_number_verified_elsewhere_is_reported(monkeypatch):
    def _start(number):
        raise TwilioRestException(status=400, uri='/x', code=21450, msg='already exists')

    monkeypatch.setattr(pr, 'start_caller_id_verification', _start)
    monkeypatch.setattr(pr, 'get_caller_id', lambda number: {'sid': 'PN1'})

    reply = pr.start_phone_verification_for_chat('uid1', '+15551234567')

    assert 'already registered' in reply


@pytest.mark.parametrize('number', ['+1555١٢٣٤٥٦٧', '+١٥٥٥١٢٣٤٥٦٧'])
def test_non_ascii_digits_are_rejected_before_twilio(monkeypatch, number):
    calls = _count_twilio_calls(monkeypatch)

    reply = pr.start_phone_verification_for_chat('uid1', number)

    assert calls == []
    assert 'E.164' in reply


def test_ascii_number_still_accepted(monkeypatch):
    calls = _count_twilio_calls(monkeypatch)

    reply = pr.start_phone_verification_for_chat('uid1', '+15551234567')

    assert calls == ['+15551234567']
    assert 'verification code' in reply
