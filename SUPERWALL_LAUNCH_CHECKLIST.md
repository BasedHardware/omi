# Superwall IAP launch checklist

Manual steps required to ship the Superwall mobile subscription flow on top of the code on `caleb/superwall-mobile-plans`. Code-side work is done; everything below is App Store Connect / Play Console / Superwall dashboard / Firestore configuration that lives outside the repo.

Tracking issue: [BasedHardware/omi-enterprise#23](https://github.com/BasedHardware/omi-enterprise/issues/23). Architecture overview: see commit messages on the branch (`backend: Superwall webhook handler with svix signature + idempotency`, etc.).

---

## 0. Sequencing

Done in this order — each step unblocks the next:

1. Apple Paid Apps Agreement → Active (blocks everything else on iOS — without this, products stay in Missing Metadata, sandbox returns empty, Superwall paywall can't load products)
2. App Store Connect IAP products created and Ready to Submit
3. Google Play subscriptions created
4. Superwall dashboard: products imported, paywall configured, products attached to paywall, paywall published
5. Webhook configured (Superwall dashboard → backend `/v1/superwall/webhook`)
6. Firestore `app_config/plan_caps` populated with product map and feature flag
7. Sandbox test on iOS device with sandbox account
8. Sandbox test on Android with internal testing track
9. Submit binary + IAPs for App Review
10. Production rollout via Firestore flag

Skipping (1) means the rest of the work is shadow-boxing — the IAPs won't actually function in any environment until Apple's tax/banking paperwork clears.

---

## 1. Apple — App Store Connect

### 1.1 Paid Applications Agreement (account-level, blocks everything)

App Store Connect → Business → Agreements:

- [ ] Paid Applications Agreement status = **Active** (not "New", not "Pending")
- [ ] Tax forms completed (W-9 for Based Hardware INC, US-based)
- [ ] Banking info added (account, routing, holder name) — payouts go here
- [ ] Senior Officer / Financial / Tax contacts filled — can all be the same person initially

First-time setup typically takes 1–24 hours after submission. Until "Active", every paid IAP on the account stays in Missing Metadata and StoreKit returns no products.

### 1.2 Subscription Group

App Store Connect → omi app → Monetization → Subscriptions:

- [ ] Group "Omi Subscriptions" exists (already created)
- [ ] Group has localized App Name + at least one localization filled in
- [ ] All 6 products live inside this group (so Apple groups them in the Manage Subscriptions UI)

### 1.3 Products (6 auto-renewable subscriptions)

Each product needs the metadata below before it leaves "Missing Metadata":

| Product ID | Reference Name | Duration | Price |
|---|---|---|---|
| `com.omi.app.lite_monthly` | Lite Monthly | 1 month | $9.99 |
| `com.omi.app.lite_yearly` | Lite Yearly | 1 year | $79.99 |
| `com.omi.app.plus_monthly` | Plus Monthly | 1 month | $29.99 |
| `com.omi.app.plus_yearly` | Plus Yearly | 1 year | $199.99 |
| `com.omi.app.unlimited_v2_monthly` | Unlimited Monthly | 1 month | $49.99 |
| `com.omi.app.unlimited_v2_yearly` | Unlimited Yearly | 1 year | $299.99 |

Per product:

- [ ] Reference Name set
- [ ] Subscription Duration set
- [ ] Pricing tier picked + cleared for sale globally (175 countries)
- [ ] Localization (English U.S. minimum) — Display Name + Description filled in
- [ ] Review Information → Screenshot uploaded (placeholder OK at first; replace with real sandbox screenshot before App Review)
- [ ] Review Information → Notes (optional)
- [ ] Tax Category set (Match to parent app is fine)
- [ ] Status = **Ready to Submit**

Lite Monthly should also have:
- [ ] 7-day Free Trial introductory offer (per issue #23 spec)

### 1.4 App Store Server Notifications V2

App Store Connect → omi app → App Information → App Store Server Notifications:

- [ ] Production Server URL set to the URL Superwall provides (Superwall dashboard → Settings → Apple App Store integration)
- [ ] Sandbox Server URL set to the same Superwall URL (Apple sends test notifications to the sandbox URL)
- [ ] Version: V2 (default for new apps)

This is how Apple tells Superwall about renewals, cancellations, and refunds. Skipping this means renewals never reach our backend and subscriptions appear to expire after the initial period.

### 1.5 In-App Purchase capability on the App ID

Already enabled (otherwise products couldn't be created). No action needed unless the App ID is rebuilt — verify at:

- Apple Developer Portal → Certificates, Identifiers & Profiles → Identifiers → `com.friend-app-with-wearable.ios12` → Capabilities → In-App Purchase ☑

### 1.6 Sandbox testers

App Store Connect → Users and Access → Sandbox:

- [ ] At least one sandbox tester account created with a fresh email (not associated with any real Apple ID)
- [ ] Region set to United States (matches IAP availability)

On the test device:
- [ ] Settings → App Store → scroll to bottom → Sandbox Account → sign in with the tester
- [ ] First sandbox purchase prompts to "Agree to Terms" — accept once

### 1.7 Apple Small Business Program (optional)

Reduces Apple's cut from 30% to 15%. Per issue #23 / manager: enroll later, not a blocker for launch.

- [ ] (Later) Apply at https://developer.apple.com/app-store/small-business-program/

---

## 2. Google — Play Console

### 2.1 Paid app paperwork

Play Console → Setup → Payments profile:

- [ ] Distribution Agreement signed
- [ ] Payments profile linked to a Google Payments merchant account
- [ ] Tax info completed
- [ ] Bank account verified

### 2.2 Subscriptions

Play Console → omi app → Monetize → Subscriptions:

Google's model differs from Apple's: one Subscription product, multiple Base Plans. So instead of 6 products, you create 3 Subscriptions with 2 base plans each.

| Subscription ID | Base plan ID (monthly) | Base plan ID (annual) | Monthly price | Annual price |
|---|---|---|---|---|
| `com.omi.app.lite` | `monthly` | `yearly` | $9.99 | $79.99 |
| `com.omi.app.plus` | `monthly` | `yearly` | $29.99 | $199.99 |
| `com.omi.app.unlimited_v2` | `monthly` | `yearly` | $49.99 | $299.99 |

Heads up on product ID resolution: Google sends product IDs as `<sub_id>:<base_plan_id>:<offer_id>` triples (e.g. `com.omi.app.lite:monthly:sw-auto`). The backend already normalizes these — see commit `6ba1e2d12 backend: normalize Google Play product_id triple before plan resolution`.

Per subscription:
- [ ] Subscription created with localized name + benefits
- [ ] Two base plans (monthly + yearly) with the right billing period and price
- [ ] Lite has a 7-day free trial offer attached (per issue #23)
- [ ] Status = **Active**

### 2.3 Real-Time Developer Notifications (RTDN)

Play Console → omi app → Monetize → Monetization setup → Real-time developer notifications:

- [ ] Topic name set to the Pub/Sub topic Superwall provides (Superwall dashboard → Settings → Google Play integration → Pub/Sub topic)
- [ ] "Send a test notification" succeeds
- [ ] Enabled

This is how Google tells Superwall about renewals/cancellations. Without it, Android subscriptions appear stuck after the initial purchase.

### 2.4 Service account for receipt verification

Superwall needs a Google Cloud service account JSON to verify Play receipts. Two-part setup:

Google Cloud Console (in the project that owns the Pub/Sub topic):
- [ ] Create a service account dedicated to Superwall (e.g. `superwall-receipt-verifier@…iam.gserviceaccount.com`)
- [ ] Grant it the **Pub/Sub Subscriber** role on the RTDN topic
- [ ] Generate a JSON key

Play Console → Setup → API access:
- [ ] Link the same service account to the Play Console
- [ ] Grant it **View financial data, orders, and cancellation survey responses** + **Manage orders and subscriptions**

Superwall dashboard → Settings → Google Play integration:
- [ ] Upload the service account JSON
- [ ] Status flips to "Connected"

### 2.5 BILLING permission

Already declared in `app/android/app/src/main/AndroidManifest.xml` (added when superwallkit_flutter pulled in `com.android.billingclient:billing` transitively). Verify:

```bash
grep "com.android.vending.BILLING" app/android/app/src/main/AndroidManifest.xml
```

If absent, add `<uses-permission android:name="com.android.vending.BILLING" />`.

### 2.6 Internal testing track

Play Console → omi app → Testing → Internal testing:

- [ ] Internal testing track created
- [ ] At least one license tester email added (Setup → License testing)
- [ ] Test build uploaded to internal testing
- [ ] Tester accepts the opt-in link emailed to them

License testers can purchase subscriptions in test mode — Google won't charge real money but will fire the full receipt + RTDN flow.

### 2.7 Data Safety form

Play Console → omi app → App content → Data safety:

- [ ] Updated to declare Superwall data collection (anonymous user ID, purchase events, paywall views)

Skipping this is a Play Store rejection if Superwall's data practices aren't disclosed.

---

## 3. Superwall dashboard

Workspace: Mohsin Mohammed / mohsin@basedhardware.com → "Omi - Smart Meeting Notes" (project ID `22416`).

### 3.1 Products imported

Superwall → Products. Should match the App Store Connect / Play Console SKUs:

iOS (6 products):
- [x] `com.omi.app.lite_monthly` → entitlement `lite`, 7-day trial
- [x] `com.omi.app.lite_yearly` → entitlement `lite`
- [x] `com.omi.app.plus_monthly` → entitlement `plus`
- [x] `com.omi.app.plus_yearly` → entitlement `plus`
- [ ] `com.omi.app.unlimited_v2_monthly` → entitlement `unlimited_v2` (need to recreate — old `max_*` SKUs deleted)
- [ ] `com.omi.app.unlimited_v2_yearly` → entitlement `unlimited_v2` (need to recreate — old `max_*` SKUs deleted)

Android (6 products — to do):
- [ ] `com.omi.app.lite:monthly` → entitlement `lite`, 7-day trial
- [ ] `com.omi.app.lite:yearly` → entitlement `lite`
- [ ] `com.omi.app.plus:monthly` → entitlement `plus`
- [ ] `com.omi.app.plus:yearly` → entitlement `plus`
- [ ] `com.omi.app.unlimited_v2:monthly` → entitlement `unlimited_v2`
- [ ] `com.omi.app.unlimited_v2:yearly` → entitlement `unlimited_v2`

### 3.2 Entitlements

Superwall → Entitlements. Currently has duplicates from project bootstrap:

- [ ] Clean up: delete duplicate `lite` (47403, empty), delete `pro` stubs (47381, 47382, never used). Keep `lite` (47400), `plus` (47401). The existing `max` entitlement (47402) needs to be renamed to `unlimited_v2` (or deleted + recreated) to match the new internal id.

### 3.3 Paywall

Superwall → Paywalls. Currently two paywalls exist; `218361 "Lite Paywall"` is the one campaigns point at.

- [ ] Single paywall named something like "Omi Mobile Tiers" (rename the existing or create new)
- [ ] All 6 iOS products + 6 Android products attached
- [ ] Compliance copy present:
    - Auto-renew disclosure ("Subscription auto-renews unless canceled at least 24 hours before the end of the current period")
    - Privacy Policy link
    - Terms of Use link
    - Restore Purchases button or affordance
- [ ] Continue / Subscribe button has a `Purchase $products.<reference>` action (not a generic tap handler — that was the silent-fail bug we hit)
- [ ] Click **Publish** → editor confirms, dashboard shows `version: 1` and a non-null `published_at`
- [ ] Verify via API that publish succeeded:
    ```
    mcp__superwall__get_paywall id=<paywall_id>
    ```
    Expect `"published_at": "<timestamp>"` and `"version": >=1`.

### 3.4 Campaign wiring

Superwall → Campaigns. Currently `84605 "Omi mobile upgrade triggers"`.

- [ ] Placements registered: `upgrade_settings`, `chat_quota_exceeded`, `transcription_minutes_exceeded` (already done)
- [ ] Treatment variant 100% → points at the published paywall
- [ ] Audience expression: leave empty for "all users" while flag is gating client-side

If you want server-side audience targeting later (e.g., only iOS, only US), set the expression here. The client-side flag is the simpler control today.

### 3.5 Webhook endpoint

Superwall → Settings → Webhooks:

- [ ] Add endpoint URL: `https://<api-host>/v1/superwall/webhook`
- [ ] Copy the signing secret (`whsec_...`) and set as the backend env var `SUPERWALL_WEBHOOK_SECRET`
- [ ] Subscribe to the events the backend handles: `initial_purchase`, `renewal`, `cancellation`, `uncancellation`, `expiration`, `billing_issue`, `product_change`, `subscription_paused`
- [ ] Click "Send test event" → backend should respond 200 and write a row to Firestore `superwall_events/<svix_id>`

### 3.6 SDK API keys (already wired)

The Flutter app reads Superwall API keys via `envied` from `.env` / `.dev.env`:
- `SUPERWALL_API_KEY_IOS` (public key starting `pk_…`)
- `SUPERWALL_API_KEY_ANDROID` (public key starting `pk_…`)

- [ ] Both keys present in `app/.env` (prod build) and `app/.dev.env` (dev build)
- [ ] Codemagic build environment has them too (so CI builds work without local secrets)
- [ ] Cold-launch the app on a real device → device console shows `SuperwallService.initialize: configured` (only after a paywall trigger fires now, since init is lazy)

---

## 4. Backend — Firestore configuration

Doc: `app_config/plan_caps`. Already used for plan caps; we extend it with Superwall fields.

### 4.1 Product → PlanType map

```yaml
superwall_product_map:
  # iOS
  "com.omi.app.lite_monthly": "lite"
  "com.omi.app.lite_yearly":  "lite"
  "com.omi.app.plus_monthly": "plus"
  "com.omi.app.plus_yearly":  "plus"
  "com.omi.app.unlimited_v2_monthly":  "unlimited_v2"
  "com.omi.app.unlimited_v2_yearly":   "unlimited_v2"
  # Android (Play sends triples; backend normalizes them but full triples work too)
  "com.omi.app.lite": "lite"
  "com.omi.app.plus": "plus"
  "com.omi.app.unlimited_v2":  "unlimited_v2"
```

- [ ] Field populated. Without this, the webhook handler logs "unknown_product" and ignores every purchase.

### 4.2 Feature flag (the gate this work added)

```yaml
superwall_enabled: false              # global default — keep false until launch
superwall_test_uids:                  # internal testers see Superwall regardless of global flag
  - "<your_uid>"
  - "<other_internal_uid>"
```

- [ ] During testing: add your uid to `superwall_test_uids`, leave global false
- [ ] At launch: set `superwall_enabled: true`, leave or empty the test list
- [ ] Rollback: set `superwall_enabled: false`. Test uids continue to see Superwall (handy for keeping QA running while production rolls back)

Cache TTL is 60s — flag changes propagate within a minute of the next subscription fetch.

### 4.3 Backend env vars (require deploy)

- [ ] `SUPERWALL_WEBHOOK_SECRET` set to the `whsec_…` value from Superwall dashboard
- [ ] (Optional) `NEW_PLANS_MIN_MOBILE_VERSION` = the build version with the Superwall code, if you want to gate by client version too

---

## 5. Sandbox testing checklist

After the above is done, validate the full round-trip on each platform.

### iOS

- [ ] Real device (simulator can't sandbox)
- [ ] Sandbox tester signed in: Settings → App Store → Sandbox Account
- [ ] Build with the `prod` flavor (`com.friend-app-with-wearable.ios12`) — dev flavor's bundle has no products registered
- [ ] Your uid added to `superwall_test_uids` in Firestore
- [ ] Cold-launch app, navigate to Your Omi Insights → tap "Upgrade to Unlimited"
- [ ] Superwall paywall renders (not the legacy PlansSheet — confirms flag is working)
- [ ] Tap a tier → sandbox StoreKit sheet appears
- [ ] Confirm purchase → sheet dismisses with "Confirmed"
- [ ] Backend log shows the webhook hit + Firestore `users/<uid>.subscription` updated to the new plan
- [ ] App's UsageProvider re-fetches subscription → caps reflect the new plan (within ~10s)
- [ ] Test cancellation: App Store sandbox → Subscriptions → Cancel → backend gets `cancellation` event → `cancel_at_period_end: true` in Firestore
- [ ] Test restore: delete app, reinstall, sign in same uid → tap Restore Purchases → entitlement re-applied without a new charge

### Android

- [ ] Real device (emulator can sandbox if logged into a license tester account)
- [ ] License tester opted into the internal testing track
- [ ] App installed via the testing track URL (NOT a sideloaded APK — must come from Play to use Billing)
- [ ] Same flag setup as iOS
- [ ] Same flow: Upgrade → paywall → buy → webhook → Firestore → caps update
- [ ] Verify RTDN: Play Console → Subscriptions → the test purchase appears with status "Subscribed"

### Both platforms — webhook script for backend isolation

A direct curl to `/v1/superwall/webhook` with a hand-signed svix payload validates the backend independently of any app state. Useful for testing the conflict handler, edge events (billing_issue, product_change), and for developing without burning sandbox testers.

```bash
# See backend/tests/unit/test_superwall_webhook.py for the signing logic.
# Pseudocode:
#   1. Build payload JSON with type + app_user_id + product_id + expires_at
#   2. svix-id = "msg_test_<n>", svix-timestamp = now, sign over body with secret
#   3. POST to /v1/superwall/webhook with the headers
```

---

## 6. App Review submission

Once everything above passes sandbox:

### iOS submission

- [ ] Replace placeholder Review Screenshots with real screenshots from sandbox-tested paywall (each product needs its own screenshot, but they can show the same paywall)
- [ ] Update App Privacy questionnaire to declare Superwall data collection
- [ ] Add reviewer notes on the App Version page:
  - "Tap 'Upgrade to Unlimited' on the Your Omi Insights page (gear icon → Usage)"
  - "Test Apple ID sandbox account: <email> / <password>"
  - "Subscription terms shown on the paywall"
- [ ] Attach all 6 IAPs to the binary submission (App Version page → In-App Purchases and Subscriptions section → Select)
- [ ] Submit binary + IAPs together for review
- [ ] After approval, set `superwall_enabled: true` in Firestore for production rollout

### Android submission

- [ ] Internal testing track validated end-to-end
- [ ] Promote to closed testing or production
- [ ] No separate review for IAPs themselves on Play (they go live with the app)

---

## 7. Production rollout

Sequence:

1. Apple + Google: app version with Superwall code approved + live
2. Backend `app_config/plan_caps`:
   - [ ] Update `superwall_test_uids` to include any final pre-launch QA accounts
   - [ ] Flip `superwall_enabled: true`
3. Within 60s, all clients fetching `/v1/users/me/subscription` get `superwall_enabled: true` and start routing to Superwall
4. Monitor:
   - Superwall dashboard: paywall views, purchase rate, error rate
   - Backend logs: `[superwall]` warnings (signature failures, unknown products, conflict events)
   - Firestore `superwall_events/` collection: should see one doc per webhook delivery
   - PostHog: chat-quota cap-hit → paywall placement events

### Emergency disable

If something breaks:

- [ ] Set `superwall_enabled: false` in Firestore (60s propagation)
- [ ] All users immediately route back to legacy PlansSheet on next paywall trigger
- [ ] Existing Superwall subs continue to work — only the *acquisition surface* hides
- [ ] Test users in `superwall_test_uids` still see Superwall (so QA can keep validating the fix)

---

## Appendix — Reference IDs

| Thing | Value |
|---|---|
| Apple App Store ID | `6502156163` |
| iOS bundle ID | `com.friend-app-with-wearable.ios12` |
| Android package | (verify against `app/android/app/build.gradle` `applicationId`) |
| Superwall org | Mohsin Mohammed / mohsin@basedhardware.com |
| Superwall project ID | `22416` (Omi - Smart Meeting Notes) |
| Superwall iOS app ID | `44831` |
| Superwall Android app ID | `44832` |
| Backend webhook path | `POST /v1/superwall/webhook` |
| Firestore config doc | `app_config/plan_caps` |
| Firestore idempotency collection | `superwall_events` (TTL 30 days, set policy in GCP console) |
| Tracking issue | BasedHardware/omi-enterprise#23 |
| Branch | `caleb/superwall-mobile-plans` |
