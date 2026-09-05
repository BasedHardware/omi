# Pricing Scheme Touchpoint Inventory

This repo already has an in-flight catalog migration — `.github/agent-docs/plan-source-of-truth.md` and `.github/agent-docs/plan-catalog.md` — which owns plan identity, entitlement numbers, and the Stripe price/product ledger; Stripe remains the sole authority for actual dollar amounts. This document is the broader map: every place across the codebase where pricing, plan names, or feature-limit numbers surface at all, including non-architectural touchpoints (docs, tests, marketing copy, assets) that the catalog migration doesn't itself track. Within each table, hardcoded/copy items that will need a manual touch are listed above `reads_live_no_update_needed` items, which are included for completeness/confirmation only.

## Flutter mobile app (app/) — pricing, plans, and paywall

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `app/lib/l10n/app_en.arb` (line 10581) `planDeprecationMessage` (+ `app_fr.arb:2941`, other locales) | hardcoded_amount | Yes — literal "$49/mo" Operator price baked into localized copy; currently no Dart call sites found (may be dead) |
| `app/lib/l10n/app_en.arb` (line 5843) `monthlyPayoutsDescription` | hardcoded_amount | Yes, if the $10 payout threshold changes (app-developer payout copy, not subscriber pricing) |
| `app/lib/pages/settings/widgets/plans_sheet.dart` (line 2083-2094) `_tierGrantsDesktop` | config_value | Yes — client-side copy of desktop-entitled plan set; must mirror backend `DESKTOP_ENTITLED_PLAN_TYPES` |
| `app/lib/models/subscription.dart` (line 86-88) `PlanType.grantsDesktop` | config_value | Yes — second independent copy of the same desktop-entitlement mapping |
| `app/lib/models/subscription.dart` (line 77-79) doc comment | feature_limit_number | Yes (comment only) — "1500 min/month" for Plus will read stale if the real limit changes; runtime value itself is live |
| `app/test/utils/plan_pricing_test.dart` (line 17-27,47-56) | test_fixture | Yes (comments/docs) — fixtures encode today's real Plus/Unlimited/Neo prices; math functions themselves are price-agnostic |
| `app/test/unit/plans_sheet_l10n_test.dart` (line 60-63,186,193-198) | test_fixture | Yes — one assertion hardcodes formatted string "$161.91" (today's real Plus annual price) |
| `app/lib/l10n/app_en.arb` (line 10668,10676,10684) `neoSubtitle`/`operatorSubtitle`/`architectSubtitle` | plan_name_or_tier_copy | Yes, if resurrected — currently no call sites found outside generated l10n files |
| `app/lib/pages/settings/widgets/plans_sheet.dart` (line 1569,2086-2094) `tierOrder` list | plan_name_or_tier_copy | Yes — hardcoded canonical plan-ID list; new/retired plan IDs require updating this literal |
| `app/lib/pages/settings/widgets/plans_sheet.dart` plan titles/prices/features (~2043-2075, 1671-1697) | reads_live_no_update_needed | No — sourced live from backend availablePlans/planData |
| `app/lib/utils/plan_pricing.dart` (whole file); `app/lib/pages/settings/usage_page.dart` (line 1030-1059) | reads_live_no_update_needed | No — discount badges and usage/quota figures derive from live monthly/yearly unit amounts and subscription response |

## macOS desktop app (desktop/macos/)

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `desktop/macos/Desktop/Sources/MainWindow/QueryShell/QueryShellHome.swift` (line 198-206) | hardcoded_amount | Likely dead, but Yes if reachable — stale "$199/month Omi Pro" alert, plan name doesn't match any current tier |
| `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift` (line 3158,4555,5566) | hardcoded_amount | Yes — literal $50 free-tier spend cap duplicated at 3 call sites |
| `...Settings/Components/SettingsContentView+BillingHelpers.swift:34` (comment) | hardcoded_amount | Yes (comment) — "Neo ($20) \| Operator ($49) \| Architect ($200)" |
| `...BillingHelpers.swift:141-152` `planSubtitle` | feature_limit_number | Yes — fallback subtitle question counts, only shown when catalog omits `subtitle`. Now `static` for testability |
| `...BillingHelpers.swift:195-206` `planDescription` | feature_limit_number | Yes — fallback descriptions; internal inconsistency (100 vs 200 for "unlimited") fixed in this PR. Now `static` for testability |
| `...BillingHelpers.swift:243-269` `fallbackFeatures` | feature_limit_number | Yes — includes literal "~$400 of monthly AI compute" and question counts. Now `static` for testability |
| `...Sections/SettingsContentView+AccountBilling.swift:342-345` | hardcoded_amount | Fixed in this PR — was a bare "$49/mo" literal, now reads `operatorDeprecationFallbackPrice`, a single named constant |
| `...BillingHelpers.swift:182-193` `planEyebrow` | plan_name_or_tier_copy | Yes — fallback marketing eyebrow text per plan id. Now `static` for testability |
| `...BillingHelpers.swift:288-324` `planCatalog(from:)` + `normalizedPlanId` (271-286) | plan_name_or_tier_copy | Yes — fallback title mapping/keyword matching for plan display names |
| `...Sections/SettingsContentView+AccountBilling.swift:102-128` | other | Only if resurrected — dead/commented "Upgrade to Pro" card with stale marketing URL |
| `desktop/macos/Desktop/Sources/Services/APIClient/APIClient+Settings.swift` (line 370) (comment) | hardcoded_amount | Yes (comment only) — "$400/mo" example for Architect |
| `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarUsageLimiter.swift` (line 15-27) `proactiveBudgetMultiplier` | config_value | Yes, if tiers/entitlements restructured — plan-tier-keyed multiplier constants |
| `TrialBannerService.swift:88` | hardcoded_amount | Yes — "3-day premium trial" string doesn't interpolate from `trialDurationSeconds` |
| `desktop/macos/Desktop/Sources/AppState/AppState+TrialPaywall.swift` (line 121-166) (#if DEBUG) | test_fixture | Yes, if kept accurate — debug-only trial mock, not shipped to release |
| `desktop/macos/Desktop/Sources/MainWindow/SettingsSidebar.swift` (line 187-198) | plan_name_or_tier_copy | Yes — settings-search subtitles/keywords name "Operator"/"Architect"/"unlimited" |
| `desktop/macos/Desktop/Sources/MainWindow/SettingsSidebar.swift` (line 200-204) | plan_name_or_tier_copy | Yes — referral search subtitle names "Operator" |
| `desktop/macos/Desktop/Sources/MainWindow/Referrals/ReferralProgramView.swift` (line 64,69) | plan_name_or_tier_copy | Yes — referral header text hardcodes "Operator" and "one month" |
| `desktop/macos/Desktop/Tests/SubscriptionPlanCatalogMergerTests.swift` (line 1-58) | test_fixture | No — arbitrary test doubles, not real prices |
| `desktop/macos/Desktop/Tests/SubscriptionPlanPresentationTests.swift` (line 1-27) | test_fixture | No functionally, but coincidentally matches real Operator price — worth a glance |
| `desktop/macos/Desktop/Tests/SubscriptionInfoDecoderTests.swift` (line 1-186) | test_fixture | Only the deprecation-message fixture needs to track the real fallback string |
| `desktop/macos/Desktop/Tests/FloatingBarUsageLimiterTests.swift` (line 41-238) | test_fixture | Yes — quota fixtures (Architect $400 cap) should track real limits to stay meaningful |
| `desktop/macos/Desktop/Sources/VADGateService.swift` (line 483) | config_value | Yes, if Deepgram's per-minute cost changes — unrelated to Omi plan pricing |
| `...AccountBilling.swift:414,422-435,479-494` overage card | reads_live_no_update_needed | No — all figures from live `OverageInfoResponse` |
| `desktop/macos/Desktop/Sources/Services/APIClient/APIClient+Settings.swift` (line 411-609) displayName/price types | reads_live_no_update_needed | No — price fields populated live; only plan renames/new IDs touch `displayName` |
| `desktop/macos/Desktop/Sources/UsageLimitPopupView.swift` | reads_live_no_update_needed | No — generic copy, no numbers |
| `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarUsageLimiter.swift` (line 147-155) `limitDescription` | reads_live_no_update_needed | No — reads live server quota object |

## Windows desktop app (desktop/windows/)

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `desktop/windows/src/renderer/src/lib/billing.ts` (line 362-399) `PLAN_FALLBACKS` | feature_limit_number | Yes — fallback eyebrow/subtitle/description/features; 100-vs-200 "unlimited" inconsistency fixed in this PR |
| `.../components/settings/tabs/PlanUsageTab.tsx:228-230` | hardcoded_amount | Fixed in this PR — was a bare "$49/mo" literal, now reads `OPERATOR_DEPRECATION_FALLBACK_PRICE`, a single named constant |
| `desktop/windows/src/renderer/src/lib/billing.test.ts` (line 54-68,167-176,252,358-372,546-547,568) | test_fixture | Yes — full mock catalog with plan titles/prices baked into assertions |
| `desktop/windows/src/renderer/src/lib/chatQuotaGate.test.ts` (line 16,46,59,187) | test_fixture | Yes, if display names/quota model change |
| `desktop/windows/src/renderer/src/lib/billingPlans.ts` (line 94-101) `PLAN_DISPLAY_NAMES` | plan_name_or_tier_copy | Yes — client-side authority for plan display names |
| `desktop/windows/src/renderer/src/lib/billingPlans.ts` (line 20,80-86) alias/paid-ID sets | config_value | Yes, if plan IDs/aliases change |
| `desktop/windows/src/renderer/src/lib/billing.ts` (line 314-320,434-437) `PLAN_ORDER`/`canPurchasePlan` | config_value | Yes — hardcoded display order and downgrade-block business rule |
| `desktop/windows/src/renderer/src/lib/billing.ts` (line 68) `LEGACY_PLAN_TITLES` | plan_name_or_tier_copy | Only if the legacy-catalog canary titles themselves change |
| `.../components/apps/AppDetailSheet.tsx:160,279,304` | other | No — marketplace app price is live, distinct pricing surface (not subscription plans) |
| `billing.ts` fetch* functions + `PlanGrid`/`CurrentPlanCard`/`ChatUsageCard`/`OverageCard` render paths | reads_live_no_update_needed | No — plan titles, prices, usage, trial, overage all read live from backend |

## web/app/ (consumer web app) and web/admin/ (internal admin)

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `web/app/src/components/settings/SettingsPage.tsx` (line 969-975,1185) `limits` object | feature_limit_number | Yes — hardcoded Basic free-tier caps instead of reading from `UserSubscriptionResponse` |
| `SettingsPage.tsx:1171,1176-1177,1203` | feature_limit_number | Yes — literal "1,200 min" duplicated 3x for free-tier listening limit |
| `SettingsPage.tsx:1133-1135,1143,1212-1234` | plan_name_or_tier_copy | Yes — Basic-plan "what's included" marketing copy is a silent duplicate of catalog entitlements |
| `web/app/src/lib/planFeatures.ts` `DEFAULT_PLAN_FEATURES` | plan_name_or_tier_copy | Fixed in this PR — was two independent hardcoded copies (`SettingsPage.tsx` and `PlansSheet.tsx`), now one shared constant here |
| `web/app/src/types/user.ts` (line 134-147) `planDisplayName` | plan_name_or_tier_copy | Yes — must stay in sync with plan_catalog.json naming |
| `web/app/src/lib/api.ts` (line 2014-2017) `SegmentEditPlanRequiredError` | plan_name_or_tier_copy | Yes — hardcodes "Unlimited plan" as the gating tier |
| `web/app/src/app/login/LoginClient.tsx` (line 234) | plan_name_or_tier_copy | Yes — referral headline hardcodes "Operator", independent of backend grant logic |
| `web/admin/lib/stripe-subscriptions.ts` (line 49-56) `OMI_PLAN_PRODUCTS` | plan_name_or_tier_copy | Yes — sole source of plan identity for admin revenue/subscription metrics; new Stripe product invisible until added |
| `web/admin/app/api/omi/stats/subscriptions/route.ts` (line 64), `.../stats/revenue/route.ts:63` | other | Yes — both depend on the same `OMI_PLAN_PRODUCTS` map above |
| `web/admin/lib/__tests__/stripe-subscriptions.test.ts` (line 293-302) | test_fixture | Yes — independent literal array of 6 plan display names must track the map |
| `web/app/src/types/__tests__/userPlan.test.ts` (line 51-62) | test_fixture | Yes — literal array of plan IDs; adding a 7th plan requires updating |
| `web/app/src/types/user.ts` (line 65-72,96-102) `CATALOG_PLAN_IDS`/`PAID_CATALOG_PLAN_IDS` | reads_live_no_update_needed* | Yes, but this IS the canonical single-source client update point (not a stray duplicate) |
| `web/app/src/lib/api.ts` (getAvailablePlans, getUserSubscription, etc.) | reads_live_no_update_needed | No — all fetched live from backend/Stripe |
| `web/admin/.../dashboard/subscriptions/page.tsx` | reads_live_no_update_needed | No — MRR/ARR/amounts computed live |
| `web/admin/app/api/omi/stats/*` routes | reads_live_no_update_needed | No, except shared dependency on `OMI_PLAN_PRODUCTS` noted above |
| `web/app/src/lib/omiApi.generated.ts` | reads_live_no_update_needed | No, provided codegen is re-run when the backend schema changes (unverified — see gaps) |
| `web/admin/lib/utils/user-subscription.ts` | reads_live_no_update_needed | No — generic passthrough helpers |

## web/frontend/ (public omi.me marketing/marketplace Next.js site)

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `web/frontend/src/app/components/product-banner/types.ts` (line 23) `PRODUCT_INFO.price` | hardcoded_amount | Yes, if the $89 hardware price changes (device price, not subscription) |
| `web/frontend/src/app/apps/utils/metadata.ts` (line 104) | hardcoded_amount | Yes — independent duplicate of the $89 device price for SEO JSON-LD |
| `web/frontend/src/app/apps/[id]/page.tsx` (line 118) | hardcoded_amount | Yes — third independent duplicate of the $89 device price |
| `web/frontend/src/app/unlimited/page.tsx` (line 6,39,41) | plan_name_or_tier_copy | Yes — stale "Omi Unlimited" landing page name vs. current catalog naming (unlimited_v2 vs deprecated Neo) |
| `src/__tests__/wrapped-unlimited-deeplink-parity.test.mjs` | test_fixture | Yes — static string tripwire on the `/unlimited` route name, breaks if route is renamed |
| `web/frontend/src/app/apps/utils/metadata.ts` (line 214-215) `generateAppListSchema` | other | No — correctly hardcoded $0 for free-to-list marketplace apps |
| `web/frontend/src/app/create-app/page.tsx` (line 49,294,310,366,774-859) | reads_live_no_update_needed | No — third-party developer's own app-pricing form field, unrelated to Omi plans |
| `public/` images (omi_1.webp, etc.) | other | Unknown — not visually inspected for baked-in price text |
| `web/frontend/src/app/page.tsx` | reads_live_no_update_needed | No — redirects to /apps, no pricing content |

## backend/ and top-level config/ (pricing/plan catalog surface)

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `backend/config/plan_catalog.json` (line 115-570) allocations, `:12-76` allocation_profiles | feature_limit_number | Yes — this IS the canonical place to edit finite quotas/budgets |
| `backend/utils/subscription.py` (line 474-535) `get_paid_plan_definitions` | plan_name_or_tier_copy | Yes — hardcoded storefront titles/eyebrows/subtitle/description text |
| `backend/utils/subscription.py` (line 484,496) `annual_description` | hardcoded_amount | Yes — "Save ~17% with annual billing." baked into Neo/Operator copy, not computed from live Stripe ratio; lines 508 (architect), 520 (plus), 532 (unlimited_v2) say "Save with annual billing." (no percentage) |
| `backend/utils/subscription.py` (line 987-1002) `_chat_allowance_text` | config_value | Yes (via editing plan_catalog.json) — derives "$400" from catalog usd_cent value; live-read but easy to mistake for Stripe-sourced |
| `backend/routers/payment.py` (line 196) docstring example | localized_copy | Cosmetic only — illustrative comment, not runtime |
| `backend/charts/backend-listen/{dev,prod}_*_values.yaml`, `backend/charts/pusher/{dev,prod}_*_values.yaml` | config_value | Yes — Helm env vars duplicate quota overlays and Stripe price IDs for legacy plans; must update both dev+prod together |
| Chart files' `SUBSCRIPTION_LAUNCH_DATE` | config_value | Yes, if the cutover date changes — duplicated across 4 files |
| `backend/deploy/runtime_env/prod.overlay.yaml` (line 185-192), `backend/deploy/runtime_env.yaml` (line 1603-1610) | config_value | Yes — literal Plus/Unlimited-v2 Stripe price IDs (prod only), must track plan_catalog.json's recognized_stripe_prices |
| `backend/deploy/runtime_env/dev.overlay.yaml` (absence) | config_value | Confirm intentional — no dev price IDs for Plus/Unlimited-v2 today |
| `config/deployment-setting-classification.json` (line 172-175) | config_value | Yes, if new plan price env-var names are introduced (need a classification entry) |
| `backend/config/plan_catalog.json` (line 571-712) recognized_stripe_prices/products | config_value | Yes — append-only ledger; new Stripe prices for new/changed tiers must be appended here |
| `.github/agent-docs/plan-source-of-truth.md` (line 405-421) (open ledger gap) | other | Yes — pre-existing unresolved discrepancy between a test fixture and the dev ledger for Architect |
| `backend/tests/unit/test_available_plans_resilience.py` (line 19-22,111) | test_fixture | Yes, if the dev ledger gap above is resolved |
| `backend/tests/unit/test_overage_catalog.py` (line 8-16,29-42) | test_fixture | Yes — hardcoded per-plan hard-cap-vs-overage policy and quota numbers (500/$400/200) mirror catalog |
| `backend/tests/unit/test_subscription_restructure.py` (line 1-2,88-98,510-515) | test_fixture | Yes — stale $49/$400 figures in docstring, plus hardcoded display-name assertions |
| `backend/utils/subscription.py` (line 620-630,684-685) version gates | config_value | Yes, if a pricing change ships alongside a client capability gate |
| `backend/routers/payment.py` (line 478-522) price_string/unit_amount | reads_live_no_update_needed | No — live `stripe.Price.retrieve` at request time |
| `backend/utils/subscription.py` (line 1038-1039) `get_plan_display_name` | reads_live_no_update_needed | No — reads generated `PLAN_DISPLAY_NAMES` |
| `backend/config/plan_catalog_generated.py` | reads_live_no_update_needed | No — generated artifact, never hand-edited |
| `backend/utils/stripe.py`, `backend/scripts/support/find_stripe_entitlement_mismatches.py`, `backend/config/plan_catalog.py` | reads_live_no_update_needed | No — generic helpers/facades with no hardcoded literals |

## Repository documentation and agent guides

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `docs/api-reference/app-client-openapi.json` (line 50708) (from `backend/routers/payment.py` docstring) | plan_name_or_tier_copy | Yes — stale "Unlimited→Pro" example; fix the source docstring, not the generated doc |
| `web/admin/docs/data-contracts.md` (line 20) | config_value | Yes — procedural instruction to add a line to `OMI_PLAN_PRODUCTS` when launching a plan |
| `docs/doc/developer/mcp/tools.mdx` (line 225) | feature_limit_number | Yes, if the free-tier preview length changes — hardcoded "70 characters" |
| `docs/doc/developer/mcp/tools.mdx` (line 202,223), `docs/doc/developer/mcp/troubleshooting.mdx` (line 59-61) | plan_name_or_tier_copy | Only if the free/paid gating boundary itself changes — generic "paid plan" language |
| `docs/doc/developer/apps/Oauth.mdx` (line 220) | other | Only if marketplace-app monetization scope changes — separate pricing system from the 6-plan catalog |
| `.github/agent-docs/web-app-destinations.md` (line 14) | other | No — pointer doc only, no names/prices |
| `docs/api-reference/app-client-openapi.json` (other endpoint descriptions) | reads_live_no_update_needed | No — auto-generated mirrors of backend docstrings |
| `backend/AGENTS.md` (line 16) | reads_live_no_update_needed | No — describes live-validation behavior |
| `docs/doc/developer/backend/Backend_Setup.mdx` (line 86) | reads_live_no_update_needed | No — generic setup instructions |

## In-repo assets/imagery and app-store-adjacent files

| Location | Kind | Needs update when prices/tiers change? |
|---|---|---|
| `app/assets/images/neo_one.webp` | other | No (probable false positive) — appears to be device-pairing art, not the "Neo" plan; worth a quick visual double-check |
| `app/assets/images/ic_dollar.svg`, `ic_clone_plus.svg`, `ic_clone_chat.svg` | other | No — decorative icons, no baked-in numbers |
| `app/assets/competitor-logos/limitless-logo.jpg`, `app/assets/images/limitless.png` | other | No — competitor branding, unrelated to Omi pricing |
| `web/app/public/app-store-badge.svg`, `google-play-badge.png` (+ web/frontend, docs equivalents) | other | No — generic store-badge artwork |
| `.github/issue-assets/6559-gh-plan-usage*.png` | other | No — historical issue screenshots, not shipping product, unreferenced in-repo |

## Outside this repository

| Surface | Confirmed absent from repo | System of record to check |
|---|---|---|
| App Store listing copy (subtitle, description, price tier mentions) | No fastlane/, App Store Connect metadata, or `app-store`/`appstoreconnect` directories found anywhere | App Store Connect |
| Google Play listing copy (short/long description, pricing mentions) | No `play-store`/`playstore` directories or Android fastlane/metadata found | Google Play Console |
| Paid ad creative mentioning price points | No `ads/` directory anywhere in the repo | Whatever ad platform(s) run Omi's paid campaigns (e.g. Meta/Google Ads) |
| Social media copy/captions mentioning pricing | No `socials/` or marketing-copy directory anywhere in the repo | Whatever social scheduling tool the growth/marketing team uses |
| Blog/CMS content mentioning pricing | No MDX/blog content directory found under `web/frontend/src/app` or `docs/` | Whatever CMS or blog platform hosts Omi's blog, if one exists outside this repo |

## Suggested next steps

- **Done in this PR:** the two internal inconsistencies in *shipped* fallback copy (`SettingsContentView+BillingHelpers.swift` and its Windows twin `PLAN_FALLBACKS` in `billing.ts` both said 100 in one place and 200 in another for "unlimited"/Neo's monthly question count — 200 is correct per `plan_catalog.json`); the hardcoded "$49/mo" in macOS `AccountBilling.swift` and Windows `PlanUsageTab.tsx` deprecation-banner fallbacks, now each a single named constant; and the two independent copies of `web/app`'s generic `defaultFeatures` list, now `web/app/src/lib/planFeatures.ts`. The mobile ARB `planDeprecationMessage` string was deliberately left as-is — no confirmed Dart call site, and rewriting it would touch ~49 untranslated locale files.
- Do not touch actual dollar literals yet (Stripe price IDs, `usd_cent` allocations in `plan_catalog.json`, chart/env price IDs) until final tier numbers are decided — those are single-edit-point changes by design and premature edits risk drifting from the still-open Architect dev-ledger gap tracked in `plan-source-of-truth.md`.
- Resolve the open Architect dev Stripe price-ID ledger gap (`test_available_plans_resilience.py` vs `plan_catalog.json`) before shipping any new pricing that touches dev testing — verify against the dev Stripe dashboard first, per the doc's own caveat.
- Flag the stale "Unlimited→Pro" example in the `backend/routers/payment.py` docstring as a quick fix independent of the pricing rollout — it's leaking a non-existent plan name into public OpenAPI docs today.
- Before finalizing new prices, confirm whether `web/app/src/lib/omiApi.generated.ts`'s codegen step actually runs on `plan_catalog.json` changes — if it's manual, add it to the release checklist now so the rollout doesn't ship stale generated types.
- Treat the $89 hardware price and App Store/Play Store/ad/social copy as explicitly out of scope for the *subscription* pricing migration, but assign an owner to sweep the three duplicated $89 code locations and the external consoles/tools listed above in the same rollout window so nothing is silently missed.
