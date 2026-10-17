import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from models.affiliate import (
    AffiliateEarningsResponse,
    AffiliateLinkCredentialsRequest,
    AffiliateLinkResponse,
    AffiliateOrdersResponse,
    AffiliatePayoutAccountStatusResponse,
    AffiliatePayoutLinkResponse,
    AffiliatePayoutSetupRequest,
    AffiliatePayoutsResponse,
    AffiliateRefCodeAvailabilityResponse,
    AffiliateRefCodeUpdateRequest,
    AffiliateRefCodeUpdateResponse,
    AffiliateStatsResponse,
    AffiliateStatusResponse,
    LinkMethod,
)
from utils.affiliates import goaffpro, service
from utils.integration_telemetry import emit_posthog_event
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=['affiliate'])

read_uid = auth.with_rate_limit(auth.get_current_user_uid, 'affiliate:read')
write_uid = auth.with_rate_limit(auth.get_current_user_uid, 'affiliate:write')
link_uid = auth.with_rate_limit(auth.get_current_user_uid, 'affiliate:link', fail_closed=True)

T = TypeVar('T')

# Never 401: clients read 401 as an expired Omi session.
_LINK_REJECTION_STATUS = {
    'affiliate_taken': 409,
    'account_has_other': 409,
    'no_email_match': 404,
    'invalid_credentials': 400,
    'email_not_verified': 403,
}


@contextmanager
def _affiliate_errors() -> Iterator[None]:
    try:
        yield
    except service.AffiliateUnavailable:
        raise HTTPException(status_code=404, detail='affiliate_unavailable')
    except service.AffiliateNotLinked:
        raise HTTPException(status_code=409, detail='affiliate_not_linked')
    except service.AffiliateBlocked:
        raise HTTPException(status_code=403, detail='affiliate_blocked')
    except service.AffiliateLinkRejected as error:
        raise HTTPException(status_code=_LINK_REJECTION_STATUS.get(error.reason, 400), detail=error.reason)
    except service.PayoutSetupRejected as error:
        raise HTTPException(status_code=400, detail=error.reason)
    except goaffpro.GoAffProError:
        raise HTTPException(status_code=502, detail='affiliate_service_unavailable')
    except stripe.StripeError as error:
        logger.warning('affiliate stripe error type=%s', type(error).__name__)
        raise HTTPException(status_code=502, detail='payout_service_unavailable')


def _call(fn: Callable[[], T]) -> T:
    with _affiliate_errors():
        return fn()


def _linked(uid: str, method: LinkMethod) -> AffiliateLinkResponse:
    emit_posthog_event(uid, 'Affiliate Account Linked', {'method': method})
    return AffiliateLinkResponse(method=method, status=_call(lambda: service.status(uid)))


@router.get('/v1/affiliate/me', response_model=AffiliateStatusResponse)
def get_affiliate_status(uid: str = Depends(read_uid)) -> AffiliateStatusResponse:
    return _call(lambda: service.status(uid))


@router.post('/v1/affiliate/link/email', response_model=AffiliateLinkResponse)
def link_affiliate_by_email(uid: str = Depends(write_uid)) -> AffiliateLinkResponse:
    _call(lambda: service.link_by_email(uid))
    return _linked(uid, 'email_match')


@router.post('/v1/affiliate/link/credentials', response_model=AffiliateLinkResponse)
def link_affiliate_by_credentials(
    body: AffiliateLinkCredentialsRequest, uid: str = Depends(link_uid)
) -> AffiliateLinkResponse:
    _call(lambda: service.link_by_credentials(uid, body.email, body.password))
    return _linked(uid, 'affiliate_login')


@router.post('/v1/affiliate/join', response_model=AffiliateLinkResponse)
def join_affiliate_program(uid: str = Depends(write_uid)) -> AffiliateLinkResponse:
    _call(lambda: service.join(uid))
    return _linked(uid, 'joined')


@router.get('/v1/affiliate/stats', response_model=AffiliateStatsResponse)
def get_affiliate_stats(uid: str = Depends(read_uid)) -> AffiliateStatsResponse:
    return _call(lambda: service.stats(uid))


@router.get('/v1/affiliate/orders', response_model=AffiliateOrdersResponse)
def get_affiliate_orders(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10000),
    uid: str = Depends(read_uid),
) -> AffiliateOrdersResponse:
    return _call(lambda: service.orders(uid, limit, offset))


@router.get('/v1/affiliate/earnings', response_model=AffiliateEarningsResponse)
def get_affiliate_earnings(uid: str = Depends(read_uid)) -> AffiliateEarningsResponse:
    return _call(lambda: service.earnings(uid))


@router.get('/v1/affiliate/payouts', response_model=AffiliatePayoutsResponse)
def get_affiliate_payouts(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10000),
    uid: str = Depends(read_uid),
) -> AffiliatePayoutsResponse:
    return _call(lambda: service.payouts(uid, limit, offset))


@router.get('/v1/affiliate/ref-code', response_model=AffiliateRefCodeAvailabilityResponse)
def check_affiliate_ref_code(
    code: str = Query(min_length=1, max_length=64), uid: str = Depends(read_uid)
) -> AffiliateRefCodeAvailabilityResponse:
    return _call(lambda: service.ref_code_availability(uid, code))


@router.patch('/v1/affiliate/ref-code', response_model=AffiliateRefCodeUpdateResponse)
def update_affiliate_ref_code(
    body: AffiliateRefCodeUpdateRequest, uid: str = Depends(write_uid)
) -> AffiliateRefCodeUpdateResponse:
    try:
        response = _call(lambda: service.update_ref_code(uid, body.ref_code))
    except service.RefCodeRejected as error:
        raise HTTPException(status_code=409 if error.conflict else 400, detail=error.message)
    if not response.unchanged:
        emit_posthog_event(uid, 'Affiliate Ref Code Changed', {})
    return response


@router.get('/v1/affiliate/payouts/account', response_model=AffiliatePayoutAccountStatusResponse)
def get_affiliate_payout_account(uid: str = Depends(read_uid)) -> AffiliatePayoutAccountStatusResponse:
    return _call(lambda: service.payout_account_status(uid))


@router.post('/v1/affiliate/payouts/setup', response_model=AffiliatePayoutLinkResponse)
def start_affiliate_payout_setup(
    body: AffiliatePayoutSetupRequest, uid: str = Depends(write_uid)
) -> AffiliatePayoutLinkResponse:
    url = _call(lambda: service.payout_setup_link(uid, body.country))
    emit_posthog_event(uid, 'Affiliate Payout Setup Started', {})
    return AffiliatePayoutLinkResponse(url=url)


@router.post('/v1/affiliate/payouts/dashboard', response_model=AffiliatePayoutLinkResponse)
def open_affiliate_payout_dashboard(uid: str = Depends(write_uid)) -> AffiliatePayoutLinkResponse:
    return AffiliatePayoutLinkResponse(url=_call(lambda: service.payout_dashboard_link(uid)))


def _landing(title: str, message: str) -> HTMLResponse:
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html><head><title>{title}</title><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;display:flex;flex-direction:column;
align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;box-sizing:border-box;text-align:center">
<h1 style="font-size:22px">{title}</h1><p style="color:#666;max-width:480px;line-height:1.5">{message}</p></body></html>"""
    )


# Stripe redirects the browser here; neither page reads or reveals account state.
@router.get('/v1/affiliate/payouts/stripe-return', response_class=HTMLResponse, include_in_schema=False)
def affiliate_stripe_return() -> HTMLResponse:
    return _landing('Payout setup', 'You can close this window and return to Omi to check your payout status.')


@router.get('/v1/affiliate/payouts/stripe-refresh', response_class=HTMLResponse, include_in_schema=False)
def affiliate_stripe_refresh() -> HTMLResponse:
    return _landing('Link expired', 'This setup link has expired. Return to Omi and tap Set up payouts again.')
