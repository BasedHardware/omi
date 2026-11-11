from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
import firebase_admin.auth
from pydantic import BaseModel

from database.referrals import claim_referral_trial
from utils.other import endpoints as auth
from utils.referrals import (
    REFERRAL_COOKIE_MAX_AGE_SECONDS,
    REFERRAL_COOKIE_NAME,
    REFERRAL_PROGRAM,
    REFERRAL_TRIAL_DAYS,
    ReferralCodeError,
    is_new_referral_account,
    referral_link,
    referral_signup_url,
    referrer_uid_from_code,
)
from utils.integration_telemetry import emit_posthog_event
from config.app_channel import is_testflight
from config.referral_campaign import campaign_preview_uid
from database import referral_campaign as campaign_db
from utils.referral_campaign import (
    campaign_enabled,
    campaign_link,
    campaign_snapshot,
    current_policy,
    decode_campaign_code,
    hardware_landing_url,
)
from utils.referral_checkout import CheckoutError, TrustedCheckoutAdapter, verified_shopify_event
from utils.executors import db_executor, run_blocking

router = APIRouter(tags=['referrals'])


class ReferralLinkResponse(BaseModel):
    referral_url: str


class ReferralClaimRequest(BaseModel):
    code: str


class ReferralClaimResponse(BaseModel):
    claimed: bool
    trial_days: int


@router.get('/v1/users/me/referral', response_model=ReferralLinkResponse)
def get_referral_link(uid: str = Depends(auth.get_current_user_uid)) -> ReferralLinkResponse:
    try:
        response = ReferralLinkResponse(referral_url=referral_link(uid))
    except ReferralCodeError as error:
        raise HTTPException(status_code=503, detail='Referral links are temporarily unavailable') from error
    emit_posthog_event(uid, 'Referral Link Issued', {'program': REFERRAL_PROGRAM})
    return response


@router.get('/r/{code}', response_class=RedirectResponse)
def capture_referral(code: str) -> RedirectResponse:
    if code.startswith('ref2.'):
        _require_campaign_ready(TrustedCheckoutAdapter())
        try:
            policy = current_policy()
            decode_campaign_code(code, policy=policy)
        except ReferralCodeError as error:
            raise HTTPException(status_code=404, detail='invalid_referral_code') from error
        return RedirectResponse(hardware_landing_url(code, policy), status_code=302)
    try:
        referrer_uid = referrer_uid_from_code(code)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    response = RedirectResponse(referral_signup_url(code), status_code=302)
    response.set_cookie(
        REFERRAL_COOKIE_NAME,
        code,
        max_age=REFERRAL_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite='lax',
        path='/',
    )
    emit_posthog_event(referrer_uid, 'Referral Link Captured', {'program': REFERRAL_PROGRAM})
    return response


@router.post('/v1/users/me/referral/claim', response_model=ReferralClaimResponse)
def claim_referral(
    body: ReferralClaimRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> ReferralClaimResponse:
    try:
        referrer_uid = referrer_uid_from_code(body.code)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='Referral link not found') from error

    user = firebase_admin.auth.get_user(uid)
    creation_timestamp = getattr(getattr(user, 'user_metadata', None), 'creation_timestamp', None)
    claimed, reason = claim_referral_trial(
        uid,
        referrer_uid,
        is_new_user=is_new_referral_account(creation_timestamp),
    )
    emit_posthog_event(
        uid,
        'Referral Claimed',
        {'program': REFERRAL_PROGRAM, 'claimed': claimed, 'reason': reason},
    )
    return ReferralClaimResponse(claimed=claimed, trial_days=REFERRAL_TRIAL_DAYS)


class CampaignSnapshotResponse(BaseModel):
    campaign_id: str
    enabled: bool
    referral_url: str | None = None
    qualified_purchases: int
    milestone_progress: int | None = None
    earned_months: int | None = None
    claimed_months: int
    claimable_months: int
    reward_status: str
    reason: str | None = None


class CampaignAttributionResponse(BaseModel):
    campaign_id: str
    state: str
    checkout_url: str
    discount_percent: int


def _require_campaign_ready(adapter):
    if not campaign_enabled():
        raise HTTPException(status_code=503, detail='campaign_disabled')
    if not adapter.ready:
        raise HTTPException(status_code=503, detail='checkout_activation_required')


def _campaign_error(error):
    reason = str(error)
    known = {
        'self_referral',
        'attribution_conflict',
        'account_unavailable',
        'buyer_already_bound',
        'checkout_binding_conflict',
        'campaign_expired',
        'policy_version_conflict',
    }
    if reason in known:
        return HTTPException(status_code=409, detail=reason)
    return HTTPException(status_code=503, detail='checkout_unavailable')


@router.get('/v2/users/me/referral/campaign', response_model=CampaignSnapshotResponse)
def get_campaign(request: Request, uid: str = Depends(auth.get_current_user_uid_readonly)):
    adapter = TrustedCheckoutAdapter()
    enabled = campaign_enabled() and adapter.ready
    # Read-only snapshot for team uids and TestFlight builds; the header is a client assertion.
    preview = not enabled and (campaign_preview_uid(uid) or is_testflight(request))
    if not enabled and not preview:
        return campaign_snapshot(
            {}, enabled=False, reason='campaign_disabled' if not campaign_enabled() else 'checkout_activation_required'
        )
    try:
        return campaign_snapshot(
            campaign_db.read_campaign(uid, preview=preview),
            enabled=True,
            referral_url=campaign_link(uid),
            reason='preview' if preview else None,
        )
    except ReferralCodeError as error:
        raise HTTPException(status_code=503, detail='checkout_activation_required') from error


@router.post('/v2/users/me/referral/campaign/claim', response_model=CampaignSnapshotResponse)
def claim_campaign(request: Request, uid: str = Depends(auth.get_current_user_uid_readonly)):
    # Disabled or preview claim returns the read-only snapshot and never writes.
    if not campaign_enabled() or not TrustedCheckoutAdapter().ready:
        return get_campaign(request, uid)
    try:
        state, reason = campaign_db.claim_months(uid)
        result = campaign_snapshot(state, enabled=True, referral_url=campaign_link(uid), reason=reason)
        if reason == 'pending_paid_subscription':
            result['reward_status'] = reason
        return result
    except campaign_db.CampaignError as error:
        raise _campaign_error(error) from error


@router.post('/v2/users/me/referral/campaign/attribution', response_model=CampaignAttributionResponse)
def attribute_campaign(body: ReferralClaimRequest, uid: str = Depends(auth.get_current_user_uid_readonly)):
    adapter = TrustedCheckoutAdapter()
    _require_campaign_ready(adapter)
    policy = current_policy()
    try:
        referrer = decode_campaign_code(body.code, policy=policy)
    except ReferralCodeError as error:
        raise HTTPException(status_code=404, detail='invalid_referral_code') from error
    try:
        attribution = campaign_db.attribute(uid, referrer, policy=policy)
        receipt = adapter.create(attribution, policy)
        campaign_db.bind_checkout(uid, receipt, policy=policy)
    except (campaign_db.CampaignError, CheckoutError) as error:
        raise _campaign_error(error) from error
    return {
        'campaign_id': policy.campaign_id,
        'state': 'attributed',
        'checkout_url': receipt['checkout_url'],
        'discount_percent': 10,
    }


@router.post('/v2/referrals/shopify/webhook')
async def campaign_shopify_webhook(request: Request):
    adapter = TrustedCheckoutAdapter()
    _require_campaign_ready(adapter)
    policy = current_policy()
    raw = await request.body()
    try:
        evidence = verified_shopify_event(raw, request.headers, adapter.settings, policy)
    except CheckoutError as error:
        raise HTTPException(status_code=401, detail='invalid_shopify_event') from error
    try:
        result = await run_blocking(db_executor, campaign_db.settle_order, evidence, policy=policy)
    except campaign_db.CampaignError as error:
        raise _campaign_error(error) from error
    return {'state': result['state']}
