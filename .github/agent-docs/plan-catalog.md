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

**Omi Pro (`unlimited_v2`) is the only plan sold, on every platform** (Nik ruling 2026-10-26,
extending the 2026-10-24 new-buyer rule). Plus, Pro/Operator, Architect and Neo are retired:
a caller sees Omi Pro plus their own current plan, if it is a retired one, so they can manage,
cancel, or move to Omi Pro. Omi Pro grants full desktop. `NEW_BUYER_SINGLE_PLAN_ENABLED=false`
restores the per-platform catalog below.

Per-platform catalog (kill switch off only):

| Surface | Sells | Does not sell |
|---|---|---|
| Mobile (`ios` / `android`) | Plus + Unlimited (`unlimited_v2`) | Operator, Architect, Neo |
| Desktop (`macos` / `windows`) | Operator + Architect | Plus, Unlimited, Neo |
| Web | Plus + Unlimited + Operator + Architect | Neo |

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
   Exception (2026-10-26): Omi Pro (`unlimited_v2`) also grants desktop, so
   the mobile sheet allows the switch onto it.
   Operator ↔ Architect stays allowed on desktop and web.
   The upgrade API (`desktop_to_consumer_plan_change_error`) is the
   same boundary: confirmation in the app is not an exception.

3. **Annual Continue is for a real change.** Hide Continue when the user
   is already on the selected tier's annual price. Show it when they
   pick a *different* tier (e.g. annual Plus → Unlimited) or a
   monthly→annual switch on the same tier. Do not restore the old
   `!isOnAnnualPlan` hide — that blocked Plus→Unlimited for annual
   subscribers.

## Omi Pro only (2026-10-26 ruling)

While `NEW_BUYER_SINGLE_PLAN_ENABLED` is on (default; `false`/`0`/`off`/`no`
restores the per-platform catalog), Omi Pro (`unlimited_v2`) is the only plan
sold, on every platform including desktop and missing/unknown platform headers:

- Catalog: `filter_plans_for_user` returns Omi Pro plus the caller's own
  current plan on `/v1/payments/available-plans` and `/v1/users/me/subscription`.
  It keys off the period-valid plan lookup (`get_user_valid_subscription`): a
  lapsed retired-plan record is a basic buyer and gets only the Omi Pro offer.
- v2 storefront: `/v2/payments/plans` serves a basic caller a single-tier Omi Pro
  sheet (`build_single_plan_storefront`).
- Checkout: `new_buyer_single_plan_violation` rejects any non-`unlimited_v2`
  price with a 400 unless the caller has a current **recurring personal
  subscription** on that same plan (an organization grant is not one). Counted
  in `omi_new_buyer_checkout_rejected_total{reason="non_omi_pro_price",plan}`.
- Plan changes: `retired_plan_change_error` allows only a move to Omi Pro or an
  interval change within the current plan.
- Desktop: Omi Pro's catalog row is `desktop_full`, so it is in
  `DESKTOP_ENTITLED_PLAN_TYPES`. Operator/Architect subscribers can move to it.
- Referrals grant 30 days of Omi Pro; the chat-at-cap upgrade button points to
  Omi Pro.

Catalog `storefronts` keep their per-platform values: they also drive the
released-client wire remap (`MOBILE_PLAN_TYPES`), so emptying them would send
old builds plan values they cannot decode. Retirement is the `lifecycle:
deprecated` marker plus the rules above.

## Where the code lives

- Catalog filter: `backend/utils/subscription.py` → `filter_plans_for_user`
- Single-plan rule + kill switch: `backend/utils/subscription.py` →
  `new_buyer_single_plan_applies` / `new_buyer_single_plan_enabled`
- Plan-change guard: `backend/utils/subscription.py` → `retired_plan_change_error`
- Checkout guard: `backend/utils/subscription.py` →
  `new_buyer_single_plan_violation`, routed from
  `backend/routers/payment.py` after every subscriber escape
- Omi Pro v2 sheet: `backend/utils/storefront.py` →
  `build_single_plan_storefront`, served by `backend/routers/storefront.py`
- Upgrade guard: `backend/utils/subscription.py` → `desktop_to_consumer_plan_change_error`
- Continue button: `app/lib/utils/plan_pricing.dart` → `shouldShowPlanContinueButton`


## Existing subscriptions billed in JPY

The recognition ledger alone never makes a retained price purchasable.
`management_currency_prices` in the canonical catalog explicitly permits the
existing JPY Plus/Unlimited prices for managing an existing JPY subscription.
The resolver checks Stripe currency, active state, interval, mode and entitlement
version against the currently configured plan. It does not convert an amount,
create a Price, offer ladder-v1 entitlements through a legacy Price, or enable
new Checkout for a retained price. The exact current JPY price may reactivate
its own pending cancellation without opening another subscription.

The v1 sheet advertises `X-Omi-Billing-Currency: 1` once it can render the
additive `currency` and `billing_total` fields through the generated wire DTO.
Older sheets must update before receiving non-USD offers: their annual summary
hardcodes USD. A stale USD target is rejected before schedule release or any
plan/entitlement write. Stripe remains the source of amounts; production price
availability and the affected account need an authorized read after deployment.

Verification checklist: currency-aware catalog → selected exact ID → immediate
change and paid invoice; annual schedule keeps JPY in both phases; stale USD,
inactive/wrong-mode offers and payment decline preserve the paid subscription;
exact-price reactivation creates no additional subscription. The opt-in sandbox
runner is `backend/tests/integration/billing/test_jpy_plan_changes_stripe.py`;
its module docstring gives the explicit provider-test command. Unit and mobile
regressions cover the installed-client contract separately. Backend deployment
must precede enabling the currency-aware mobile release. No production Stripe
catalog mutation is included in the code change.
