import os
import re
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import VoiceResponse, Dial

import database.phone_calls as phone_calls_db
from utils.phone_calls import check_call_access, check_destination_allowed, get_quota_snapshot, reserve_phone_call_quota
from utils.other import endpoints as auth
from utils.other.endpoints import rate_limit_dependency
from utils.executors import critical_executor, db_executor, run_blocking
from utils.multipart import MultipartMaxPartSizeRoute, PHONE_CALL_MAX_PART_SIZE, parse_multipart_form
from utils.twilio_service import (
    generate_access_token,
    start_caller_id_verification,
    check_caller_id_verified,
    delete_caller_id,
    get_caller_id,
    validate_twilio_signature,
)

E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$')


def _redact_phone(number: str) -> str:
    """Redact a phone number for logging, showing only the last 4 digits."""
    if len(number) > 4:
        return number[:2] + '***' + number[-4:]
    return '***'


router = APIRouter(route_class=MultipartMaxPartSizeRoute)


def _say(response: VoiceResponse, message: str) -> None:
    """Wrap twilio ``VoiceResponse.say`` — its params are untyped in the SDK."""
    response.say(message)  # type: ignore[reportUnknownMemberType]  # twilio VoiceResponse.say params untyped


def _dial_number(dial: Dial, phone_number: str) -> None:
    """Wrap twilio ``Dial.number`` — its params are untyped in the SDK."""
    dial.number(phone_number)  # type: ignore[reportUnknownMemberType]  # twilio Dial.number params untyped


def _append_dial(response: VoiceResponse, dial: Dial) -> None:
    """Wrap twilio ``VoiceResponse.append`` — its params are untyped in the SDK."""
    response.append(dial)  # type: ignore[reportUnknownMemberType]  # twilio VoiceResponse.append params untyped


# ************************************************
# *********** REQUEST/RESPONSE MODELS ************
# ************************************************


class VerifyPhoneNumberRequest(BaseModel):
    phone_number: str = Field(description="Phone number in E.164 format (e.g., +15551234567)")


class VerifyPhoneNumberResponse(BaseModel):
    verification_sid: str
    phone_number: str
    validation_code: str
    status: str


class CheckVerificationRequest(BaseModel):
    phone_number: str = Field(description="Phone number in E.164 format")


class CheckVerificationResponse(BaseModel):
    verified: bool
    phone_number_id: Optional[str] = None


class PhoneNumberResponse(BaseModel):
    id: str
    phone_number: str
    friendly_name: Optional[str] = None
    verified_at: str
    is_primary: bool


class PhoneNumbersResponse(BaseModel):
    numbers: list[PhoneNumberResponse]


class PhoneMutationResponse(BaseModel):
    success: bool


class TokenResponse(BaseModel):
    access_token: str
    ttl: int
    identity: str


class RenamePhoneNumberRequest(BaseModel):
    friendly_name: str = Field(..., min_length=1, max_length=100)


# ************************************************
# ************ PHONE NUMBER ENDPOINTS ************
# ************************************************


@router.post("/v1/phone/numbers/verify", response_model=VerifyPhoneNumberResponse, tags=['phone-calls'])
def verify_phone_number(
    request: VerifyPhoneNumberRequest,
    uid: str = Depends(auth.get_current_user_uid),
    _: None = Depends(rate_limit_dependency(endpoint="phone_verify", requests_per_window=5, window_seconds=3600)),
):
    """Initiate phone number verification via Twilio caller ID validation."""
    check_call_access(uid)
    phone_number = request.phone_number.strip()
    if not E164_PATTERN.match(phone_number):
        raise HTTPException(status_code=400, detail="Phone number must be in E.164 format (e.g., +15551234567)")

    # Check if already verified
    existing = phone_calls_db.get_phone_number_by_number(uid, phone_number)
    if existing:
        raise HTTPException(status_code=409, detail="Phone number already verified")

    try:
        result = start_caller_id_verification(phone_number)
        phone_calls_db.set_pending_verification(uid, phone_number)
        return VerifyPhoneNumberResponse(**result)
    except TwilioRestException as e:
        # Error 21450: a validation request already exists for this number.
        # This could mean (a) it's already verified by another user, or (b) a verification is still pending.
        if e.code == 21450:
            caller_id_info = get_caller_id(phone_number)
            if caller_id_info:
                # Number is already verified in Twilio by someone else — block this attempt
                raise HTTPException(
                    status_code=409,
                    detail="This phone number is already registered. If you own this number and previously verified it, check your settings.",
                )
            else:
                # Number has a pending verification — not yet verified
                raise HTTPException(
                    status_code=409,
                    detail="A verification call is already in progress for this number. Please answer the call and enter the code.",
                )
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to start verification: {str(e)}")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to start verification: {str(e)}")


@router.post("/v1/phone/numbers/verify/check", response_model=CheckVerificationResponse, tags=['phone-calls'])
def check_phone_verification(
    request: CheckVerificationRequest,
    uid: str = Depends(auth.get_current_user_uid),
    _rate_limit: Any = Depends(
        rate_limit_dependency(endpoint="phone_verify_check", requests_per_window=30, window_seconds=60)
    ),
):
    """Check if a phone number has been verified. Poll this endpoint every 2s (60s timeout)."""
    check_call_access(uid)
    phone_number = request.phone_number.strip()

    # Check if already stored locally (avoid duplicates from repeated polling)
    existing = phone_calls_db.get_phone_number_by_number(uid, phone_number)
    if existing:
        return CheckVerificationResponse(verified=True, phone_number_id=existing['id'])

    # Verify this user initiated the verification (prevent cross-user claiming)
    pending_uid = phone_calls_db.get_pending_verification_uid(phone_number)
    if pending_uid != uid:
        return CheckVerificationResponse(verified=False)

    verified = check_caller_id_verified(phone_number)
    if not verified:
        return CheckVerificationResponse(verified=False)

    # Store the verified number
    caller_id_info = get_caller_id(phone_number)
    existing_numbers = phone_calls_db.get_phone_numbers(uid)

    phone_number_id = str(uuid.uuid4())
    phone_number_data: Dict[str, Any] = {
        'id': phone_number_id,
        'phone_number': phone_number,
        'friendly_name': caller_id_info.get('friendly_name') if caller_id_info else None,
        'twilio_sid': caller_id_info.get('sid') if caller_id_info else None,
        'verified_at': datetime.now(timezone.utc).isoformat(),
        'is_primary': len(existing_numbers) == 0,
    }
    phone_calls_db.upsert_phone_number(uid, phone_number_data)
    phone_calls_db.delete_pending_verification(phone_number)

    return CheckVerificationResponse(verified=True, phone_number_id=phone_number_id)


@router.get("/v1/phone/numbers", response_model=PhoneNumbersResponse, tags=['phone-calls'])
def list_phone_numbers(uid: str = Depends(auth.get_current_user_uid)):
    """List all verified phone numbers for the user."""
    check_call_access(uid)
    numbers = phone_calls_db.get_phone_numbers(uid)
    return {'numbers': numbers}


@router.delete("/v1/phone/numbers/{phone_number_id}", response_model=PhoneMutationResponse, tags=['phone-calls'])
def remove_phone_number(phone_number_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Remove a verified phone number."""
    check_call_access(uid)
    phone_number = phone_calls_db.get_phone_number(uid, phone_number_id)
    if not phone_number:
        raise HTTPException(status_code=404, detail="Phone number not found")

    # Delete from Twilio if we have the SID
    twilio_sid = phone_number.get('twilio_sid')
    if twilio_sid:
        delete_caller_id(twilio_sid)

    phone_calls_db.delete_phone_number(uid, phone_number_id)
    return {'success': True}


@router.post("/v1/phone/numbers/{phone_number_id}/primary", response_model=PhoneNumberResponse, tags=['phone-calls'])
def make_phone_number_primary(phone_number_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Set a verified number as the user's primary outbound caller ID."""
    check_call_access(uid)
    if not phone_calls_db.set_primary_phone_number(uid, phone_number_id):
        raise HTTPException(status_code=404, detail="Phone number not found")
    return phone_calls_db.get_phone_number(uid, phone_number_id)


@router.patch("/v1/phone/numbers/{phone_number_id}", response_model=PhoneNumberResponse, tags=['phone-calls'])
def rename_phone_number(
    phone_number_id: str,
    request: RenamePhoneNumberRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Rename a verified phone number's friendly_name label."""
    check_call_access(uid)
    if not phone_calls_db.rename_phone_number(uid, phone_number_id, request.friendly_name.strip()):
        raise HTTPException(status_code=404, detail="Phone number not found")
    return phone_calls_db.get_phone_number(uid, phone_number_id)


# ************************************************
# ************** TOKEN ENDPOINT ******************
# ************************************************


@router.post("/v1/phone/token", response_model=TokenResponse, tags=['phone-calls'])
def get_phone_token(uid: str = Depends(auth.get_current_user_uid)):
    """Generate a Twilio access token for making VoIP calls."""
    check_call_access(uid)
    # Verify user has at least one verified number
    primary = phone_calls_db.get_primary_phone_number(uid)
    if not primary:
        raise HTTPException(status_code=400, detail="No verified phone number found. Verify a number first.")

    try:
        token_data = generate_access_token(uid)
        return TokenResponse(**token_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")


# ************************************************
# ************** TWIML WEBHOOK ******************
# ************************************************


@router.post("/v1/phone/twiml", tags=['phone-calls'], response_class=Response)
async def twiml_voice_webhook(request: Request):
    """
    TwiML webhook called by Twilio when a VoIP call is initiated from the client SDK.

    Twilio POSTs form data with params set by ConnectOptions (To, CallId).
    The 'From' field is the SDK identity (uid), NOT a phone number.
    We look up the user's verified caller ID from the database.
    """
    # Validate Twilio signature
    signature = request.headers.get('X-Twilio-Signature', '')
    base_api_url = os.getenv('BASE_API_URL', '').rstrip('/')
    if base_api_url:
        url = f"{base_api_url}{request.url.path}"
    else:
        url = str(request.url)
    form_data = await parse_multipart_form(request, max_part_size=PHONE_CALL_MAX_PART_SIZE)
    params = dict(form_data)

    if not validate_twilio_signature(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    to_number_raw: object = form_data.get('To', '')
    to_number: str = to_number_raw if isinstance(to_number_raw, str) else ''
    caller_identity_raw: object = form_data.get('From', '')  # This is the uid (SDK identity)
    caller_identity: str = caller_identity_raw if isinstance(caller_identity_raw, str) else ''
    call_id_raw: object = form_data.get('CallId', '')
    call_id: str = call_id_raw if isinstance(call_id_raw, str) else ''

    print(f"twiml_voice_webhook: To={_redact_phone(to_number)}, From(identity)=***, CallId={call_id}")

    response = VoiceResponse()

    if not to_number:
        _say(response, 'No destination number provided. Goodbye.')
        return Response(content=str(response), media_type='text/xml')

    # Resolve the caller's verified phone number from their uid
    # The 'From' field contains the identity we set in generate_access_token (the uid)
    # Strip 'client:' prefix if present (Twilio prepends it to SDK identities)
    uid = caller_identity.replace('client:', '')
    caller_number = None

    if uid:
        # Offloaded: the Firestore read is sync and blocks the event loop in this async handler.
        primary = await run_blocking(db_executor, phone_calls_db.get_primary_phone_number, uid)
        if primary:
            caller_number = primary.get('phone_number')

    if not caller_number:
        print(f"twiml_voice_webhook: no verified caller ID found for uid=***")
        _say(response, 'No verified caller ID found. Please verify a phone number first.')
        return Response(content=str(response), media_type='text/xml')

    # Ensure clean E.164 format (remove all whitespace, dashes, parens, dots)
    caller_number = re.sub(r'[\s\-\(\).]+', '', caller_number)
    to_number = re.sub(r'[\s\-\(\).]+', '', to_number)

    # Validate destination number format
    if not E164_PATTERN.match(to_number):
        _say(response, 'Invalid destination number format. Goodbye.')
        return Response(content=str(response), media_type='text/xml')

    # Final quota + destination check before placing the call. Free-tier users
    # on exhausted monthly buckets or disallowed destinations are turned away
    # here so Twilio never actually dials; we then refuse to count the attempt.
    snapshot = await run_blocking(db_executor, get_quota_snapshot, uid)
    if not snapshot.has_access:
        _say(response, 'Monthly phone call limit reached. Goodbye.')
        return Response(content=str(response), media_type='text/xml')
    try:
        check_destination_allowed(snapshot, to_number)
    except HTTPException:
        _say(response, 'This destination is not available on your plan. Goodbye.')
        return Response(content=str(response), media_type='text/xml')

    # Verify the number is still a valid outgoing caller ID in Twilio
    is_verified = await run_blocking(critical_executor, check_caller_id_verified, caller_number)
    print(
        f"twiml_voice_webhook: caller_id={_redact_phone(caller_number)}, verified_in_twilio={is_verified}, to={_redact_phone(to_number)}"
    )

    if not is_verified:
        print(f"twiml_voice_webhook: caller_id {_redact_phone(caller_number)} is NOT verified in Twilio!")
        _say(response, 'Your caller ID is not verified. Please re-verify your phone number.')
        return Response(content=str(response), media_type='text/xml')

    # Reserve quota immediately before handing Twilio the dial instructions.
    # The reservation is atomic so concurrent TwiML requests cannot all pass
    # the same stale quota snapshot.
    if not snapshot.is_paid:
        snapshot = await run_blocking(db_executor, reserve_phone_call_quota, uid)
        if not snapshot.has_access:
            _say(response, 'Monthly phone call limit reached. Goodbye.')
            return Response(content=str(response), media_type='text/xml')

    dial_kwargs: Dict[str, Any] = {'caller_id': caller_number}
    if snapshot.max_duration_seconds and snapshot.max_duration_seconds > 0:
        dial_kwargs['time_limit'] = int(snapshot.max_duration_seconds)
    dial = Dial(**dial_kwargs)
    _dial_number(dial, to_number)
    _append_dial(response, dial)

    return Response(content=str(response), media_type='text/xml')
