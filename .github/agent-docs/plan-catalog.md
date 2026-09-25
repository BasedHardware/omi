# Plan catalog audience

Canonical identity, billed price identity, entitlements, allocations, and migration ownership are in
`backend/config/plan_catalog.json` and `.github/agent-docs/plan-source-of-truth.md`. This page owns only storefront audience
behavior. Do not add plan values or Stripe IDs here.

Locked purchase-catalog rules. Tests in
`backend/tests/unit/test_subscription_restructure.py` and
`app/test/utils/plan_pricing_test.dart` enforce them. Do not re-widen a
filter because a paid user "might want to resubscribe" or because the
phone sheet looks empty.

## Storefronts

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
   Operator ↔ Architect stays allowed on desktop and web.
   The upgrade API (`desktop_to_consumer_plan_change_error`) is the
   same boundary: confirmation in the app is not an exception.

3. **Annual Continue is for a real change.** Hide Continue when the user
   is already on the selected tier's annual price. Show it when they
   pick a *different* tier (e.g. annual Plus → Unlimited) or a
   monthly→annual switch on the same tier. Do not restore the old
   `!isOnAnnualPlan` hide — that blocked Plus→Unlimited for annual
   subscribers.

## Where the code lives

- Catalog filter: `backend/utils/subscription.py` → `filter_plans_for_user`
- Upgrade guard: `backend/utils/subscription.py` → `desktop_to_consumer_plan_change_error`
- Continue button: `app/lib/utils/plan_pricing.dart` → `shouldShowPlanContinueButton`
