import re

import database.phone_calls as phone_calls_db
from utils.phone_calls import check_call_access
from utils.twilio_service import start_caller_id_verification

E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$')


def _redact_phone(phone_number: str) -> str:
    return phone_number[:2] + '***' + phone_number[-4:] if len(phone_number) > 6 else '***'


def start_phone_verification_for_chat(uid: str, phone_number: str) -> str:
    number = phone_number.strip()
    if not E164_PATTERN.fullmatch(number):
        return 'Use an E.164 phone number such as +15551234567.'
    check_call_access(uid)
    if phone_calls_db.get_phone_number_by_number(uid, number):
        return f'{_redact_phone(number)} is already registered on your Omi account.'
    start_caller_id_verification(number)
    phone_calls_db.set_pending_verification(uid, number)
    return (
        f'Omi is calling {_redact_phone(number)} with a verification code. Answer it, then finish verification in Omi.'
    )
