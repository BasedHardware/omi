# Plan catalog audience

Canonical identity, billed price identity, entitlements, allocations, and migration ownership are in
`backend/config/plan_catalog.json` and `.github/agent-docs/plan-source-of-truth.md`. This page owns only storefront audience
behavior. Do not add plan values or Stripe IDs here.

Locked purchase-catalog rules. Tests in
`backend/tests/unit/test_subscription_restructure.py` and
`app/test/utils/plan_pricing_test.dart` enforce them. Do not re-widen a
filter because a paid user "might want to resubscribe" or because the
phone sheet looks empty.

## Versioned ladder-v1 sheet

`GET /v2/payments/plans` retires the platform partition for adopting clients,
behind `STOREFRONT_LADDER_V1_ENABLED` (default off). The old endpoints keep the
installed-client rules below unchanged. Missing W3 ladder prices hide Plus/Pro;
Architect remains contact-only and legacy subscribers keep a current row.
While the new-buyer single-plan rule (below) is on, a buyer with no current
paid subscription on an explicit non-desktop platform (mobile or web) gets a
single-tier Omi Pro (`unlimited_v2`) v2 sheet instead of the ladder — never a
404, which the web plans panel would render as a dead "Couldn't load plans"
state. Desktop, missing/unknown platforms, and current subscribers keep the
ladder sheet.
See `backend/docs/storefront-contract.md` for schema, price admission and usage.

## Storefronts (installed-client APIs)

| Surface | Sells | Does not sell |
|---|---|---|
| Mobile (`ios` / `android`) | Plus + Unlimited (`unlimited_v2`) | Operator, Architect, Neo |
| Desktop (`macos` / `windows`) | Operator + Architect | Plus, Unlimited, Neo |
| Web | Plus + Unlimited + Operator + Architect | Neo |
| New buyer, explicit mobile or web (`ios` / `android` / `web`) | Omi Pro (`unlimited_v2`) only | Everything else |
| New buyer, missing or unknown platform | Pre-ruling catalog (unrestricted) | — |

Neo (`PlanType.unlimited`) is the deprecated pre-Plus Unlimited. It is
never a new-user SKU on any real client platform.

## Three audience rules

1. **Neo is current-Neo only.** Show Neo iff `current_plan == unlimited`
   (active or cancel-at-period-end). Do **not** key it off "has ever
   paid" / Stripe customer id. That leak put Neo on Architect and Plus
   sheets, where Plus looked strictly cheaper because Neo's simplified
   mobile card omits unlimited transcription.
   Fully churned ex-Neo users are `basic` and get Plus + Unlimited, the
   replacement catalog. Do not bring Neo back for them.

2. **Desktop plans are manage-only on mobile.** An Operator or Architect
   subscriber opening iOS/Android sees **only** their current plan
   (Active, cancel, portal). They cannot Continue onto Plus / Unlimited /
   Neo. Immediate Stripe proration would strip desktop entitlement.
   Operator ↔ Architect stays allowed on desktop and web.
   The upgrade API (`desktop_to_consumer_plan_change_error`) is the
   same boundary: confirmation in the app is not an exception.

3. **Annual Continue is for a real change.** Hide Continue when the user
   is already on the selected tier's annual price. Show it when they
   pick a *different* tier (e.g. annual Plus → Unlimited) or a
   monthly→annual switch on the same tier. Do not restore the old
   `!isOnAnnualPlan` hide — that blocked Plus→Unlimited for annual
   subscribers.

## New-buyer single-plan rule (2026-10-24 ruling)

While `NEW_BUYER_SINGLE_PLAN_ENABLED` is on (default; `false`/`0`/`off`/`no`
restores the previous catalog), a buyer with **no current paid subscription**
(`basic`) on an **explicitly known non-desktop platform** — mobile
(`ios`/`android`) or `web` — is offered **only Omi Pro** (`unlimited_v2`,
$29.99/mo / $269.91/yr, 7-day trial):

- Catalog: `filter_plans_for_user` returns only the `unlimited_v2` entries for
  those callers, on `/v1/payments/available-plans` and
  `/v1/users/me/subscription`. Catalog filtering keys off the same
  period-valid plan lookup as checkout (`get_user_valid_subscription`): a
  lapsed Operator/Architect record is a basic buyer and gets the Omi Pro
  offer, not their expired desktop SKU.
- v2 storefront: `/v2/payments/plans` serves those callers a single-tier Omi
  Pro sheet (`build_single_plan_storefront`); the web client ranks
  `unlimited_v2` on its ladder so that card can check out.
- Checkout: `new_buyer_single_plan_violation` rejects any non-`unlimited_v2`
  price for those callers with a 400; the caller cannot reach a legacy plan by
  posting its price ID. Only a current **recurring personal subscription**
  exempts a caller — an organization grant (`pi_…` PaymentIntent, or no
  subscription id) is not a personal subscription. Outcomes are counted in
  `omi_new_buyer_checkout_rejected_total{reason,plan}`: `non_omi_pro_price`
  for rejections, `unknown_platform_allowed` for legacy prices allowed because
  the platform header is missing/unknown.

Desktop platforms (`macos` / `windows` via `X-App-Platform`) are **unchanged**,
a **missing or unknown platform header keeps the pre-ruling behaviour** (every
desktop build ever shipped stamps the header on every request — macOS since
the first desktop commit d51d10136e1c, Windows since its platform-identity
hardening — but desktop compatibility outranks closing the header-less
direct-API gap), and **current subscribers keep every plan-management rule**
above, including the current-plan escape, manage-only fast paths and legacy →
ladder blocks. Legacy plan prices and entitlements are not changed by this
rule anywhere.

## Where the code lives

- Catalog filter: `backend/utils/subscription.py` → `filter_plans_for_user`
- Single-plan rule + kill switch: `backend/utils/subscription.py` →
  `new_buyer_single_plan_applies` / `new_buyer_single_plan_enabled`
- Checkout guard: `backend/utils/subscription.py` →
  `new_buyer_single_plan_violation`, routed from
  `backend/routers/payment.py` after every subscriber escape
- Omi Pro v2 sheet: `backend/utils/storefront.py` →
  `build_single_plan_storefront`, served by `backend/routers/storefront.py`
- Upgrade guard: `backend/utils/subscription.py` → `desktop_to_consumer_plan_change_error`
- Continue button: `app/lib/utils/plan_pricing.dart` → `shouldShowPlanContinueButton`
