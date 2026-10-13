"""Versioned first-party plans sheet. Old payment and user APIs remain unchanged."""

from datetime import datetime, timezone
import math
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
import stripe

import config.plan_catalog_generated as catalog
from database import users as users_db
from database.app_review_config import should_hide_subscription_ui
from models.users import Subscription
from models.storefront import StorefrontResponse, StorefrontUsage
from utils.other import endpoints as auth
from utils import storefront_flags, subscription as subscription_utils
from utils.observability.fallback import record_fallback
from utils.storefront import build_storefront, load_ladder

router = APIRouter()


def _degraded(from_mode: str, to_mode: str) -> None:
    record_fallback(
        component='other', from_mode=from_mode, to_mode=to_mode, reason='provider_error', outcome='degraded'
    )


def _retrieve_price(price_id: str) -> dict[str, Any]:
    try:
        return stripe.Price.retrieve(price_id).to_dict()
    except Exception:
        _degraded('storefront_price', 'hidden_price')
        raise


def _usage(uid: str, subscription: Subscription) -> StorefrontUsage:
    try:
        # W3 may provide a display-ready projection on the shared facade. Do not
        # guess units or denominators; only accept percentage/reset fields.
        projection = getattr(subscription_utils, 'get_usage_units', None)
        if callable(projection):
            snapshot = projection(uid)
            percent = snapshot.get('budget_percent') if isinstance(snapshot, dict) else None
            reset = snapshot.get('reset_at') if isinstance(snapshot, dict) else None
            if (
                isinstance(percent, (int, float))
                and not isinstance(percent, bool)
                and math.isfinite(percent)
                and percent >= 0
                and type(reset) is int
                and reset > 0
            ):
                return StorefrontUsage(kind='usage_budget', budget_percent=percent, reset_at=reset)
        if subscription.current_price_id in getattr(catalog, 'LADDER_V1_STRIPE_PRICES', []):
            return StorefrontUsage()
        # Existing legacy speech allowance; explicitly labelled so clients never
        # mistake it for the new shared-unit budget.
        limit = subscription_utils.transcription_allowance_seconds(subscription.plan)
        if limit is None or limit <= 0:
            return StorefrontUsage()
        usage = subscription_utils.get_monthly_usage_for_subscription(uid)
        used = usage.get('transcription_seconds')
        if type(used) is not int or used < 0:
            return StorefrontUsage()
        now = datetime.now(timezone.utc)
        reset = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
        return StorefrontUsage(kind='transcription', budget_percent=used * 100 / limit, reset_at=int(reset.timestamp()))
    except Exception:
        _degraded('storefront_usage', 'unavailable_usage')
        return StorefrontUsage()


@router.get('/v2/payments/plans', response_model=StorefrontResponse, tags=['payments'])
def get_storefront(
    uid: str = Depends(auth.get_current_user_uid_no_byok_validation),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
):
    if not storefront_flags.enabled():
        raise HTTPException(status_code=404, detail='Storefront is not enabled')
    if should_hide_subscription_ui(uid, x_app_platform, x_app_version):
        return StorefrontResponse(catalog_revision=catalog.CATALOG_REVISION, show_subscription_ui=False)
    # Never provision a default record from a presentation endpoint.
    subscription = users_db.get_user_valid_subscription(uid, provision=False)
    if subscription is None:
        subscription = subscription_utils.get_default_basic_subscription()
    # W3's generated declaration is absent until #21351 merges. No env prices
    # can accidentally become ladder-v1 just because they exist.
    bindings = getattr(catalog, 'LADDER_V1_STRIPE_PRICES', [])
    recognized = [
        {
            'price_id': price_id,
            'plan_id': plan.value,
            'interval': catalog.RECOGNIZED_STRIPE_PRICE_INTERVALS[price_id],
            'entitlement_version': getattr(catalog, 'RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS', {}).get(
                price_id, 'legacy'
            ),
        }
        for price_id, plan in catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items()
    ]
    return build_storefront(
        catalog_revision=catalog.CATALOG_REVISION,
        ladder=load_ladder(),
        bindings=bindings,
        recognized=recognized,
        subscription=subscription,
        retrieve_price=_retrieve_price,
        purchasable=subscription_utils.is_purchasable_price_id,
        usage=_usage(uid, subscription),
    )
