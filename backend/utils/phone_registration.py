import json
import re
import time

import database.phone_calls as phone_calls_db
from utils.other import endpoints
from utils.phone_calls import check_call_access

# TwilioRestException comes from twilio_service, which already resolves it behind a
# fallback: the SDK's `twilio.base` subpackage is not importable in every
# environment, and importing it raw here broke unrelated suites at collection.
from utils.twilio_service import TwilioRestException, get_caller_id, start_caller_id_verification

E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$', re.ASCII)

PHONE_VERIFY_REQUESTS_PER_WINDOW = 5
PHONE_VERIFY_WINDOW_SECONDS = 3600


class PhoneVerificationError(Exception):
    """A phone-registration attempt that both the HTTP route and the chat tool must reject the same way."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _enforce_phone_verify_limit(uid: str) -> None:
    key = f"rate_limit:phone_verify:uid:{uid}"
    now = int(time.time())
    current = None
    # Per-user attempt budget, kept in the same in-process store the HTTP rate-limit
    # dependency uses so both entry points draw down one shared window.
    raw = endpoints.cached.get(key)
    if raw:
        try:
            current = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            current = None

    if current and now - current.get("timestamp", 0) < PHONE_VERIFY_WINDOW_SECONDS:
        remaining = current.get("remaining", 0)
        timestamp = current.get("timestamp", now)
        if remaining <= 0:
            raise PhoneVerificationError(429, "Too many verification attempts. Try again later.")
    else:
        remaining = PHONE_VERIFY_REQUESTS_PER_WINDOW
        timestamp = now

    endpoints.store_rate_limit(key, json.dumps({"timestamp": timestamp, "remaining": remaining - 1}))


def _redact_phone(phone_number: str) -> str:
    return phone_number[:2] + '***' + phone_number[-4:] if len(phone_number) > 6 else '***'


def register_phone_verification(uid: str, phone_number: str) -> dict:
    """Start Twilio caller-id verification for `uid`.

    Single owner of the verification contract: E.164 shape, call access, the per-user
    attempt budget, duplicate registration, and the Twilio 21450 mapping. Both the HTTP
    route and the chat tool go through here so a caller cannot buy extra Twilio calls by
    choosing the other entry point. Raises PhoneVerificationError for every rejection.
    """
    number = phone_number.strip()
    if not E164_PATTERN.fullmatch(number):
        raise PhoneVerificationError(400, "Phone number must be in E.164 format (e.g., +15551234567)")

    check_call_access(uid)
    _enforce_phone_verify_limit(uid)

    if phone_calls_db.get_phone_number_by_number(uid, number):
        raise PhoneVerificationError(409, "Phone number already verified")

    try:
        result = start_caller_id_verification(number)
    except TwilioRestException as e:
        # Error 21450: a validation request already exists for this number.
        # This could mean (a) it's already verified by another user, or (b) a verification is still pending.
        # getattr, matching twilio_service: TwilioRestException is typed
        # type[BaseException] because it resolves to a fallback class when the
        # SDK subpackage is missing, so the attribute is not statically known.
        if getattr(e, 'code', None) == 21450:
            if get_caller_id(number):
                raise PhoneVerificationError(
                    409,
                    "This phone number is already registered. If you own this number and previously verified it, check your settings.",
                )
            raise PhoneVerificationError(
                409,
                "A verification call is already in progress for this number. Please answer the call and enter the code.",
            )
        raise

    phone_calls_db.set_pending_verification(uid, number)
    return result


def start_phone_verification_for_chat(uid: str, phone_number: str) -> str:
    number = phone_number.strip()
    try:
        register_phone_verification(uid, number)
    except PhoneVerificationError as e:
        if e.status_code == 400:
            return 'Use an E.164 phone number such as +15551234567.'
        if e.status_code == 409 and 'already verified' in e.detail:
            return f'{_redact_phone(number)} is already registered on your Omi account.'
        return e.detail
    return (
        f'Omi is calling {_redact_phone(number)} with a verification code. Answer it, then finish verification in Omi.'
    )
