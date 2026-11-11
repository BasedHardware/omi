# Purchase exposure observations

This instrumentation has zero claimed conversion uplift. It establishes client exposure and checkout
observations before purchase-side experiments. `events.json` owns the eight new `Subscription …`
wire names; the prefix preserves the ingestion keep rule documented by subscription-payment-recovery.
The existing analytics transport, consent, identity and provenance behavior is unchanged.

Generate all clients with `python3 scripts/check_event_registry.py --write`. That command also checks
or regenerates the portable TypeScript/Swift allowlists through `generate_purchase_telemetry.py`.
Generated sources must not be edited by hand. Only declared enum properties cross the new event
boundary; unknown source/plan/interval values become `unknown`, and undeclared keys are dropped.
There are no URLs, checkout/session identifiers, promo/bundle codes, backend error text, usage content
or account identifiers in these event properties. Existing SDK identity is outside this property contract.

| Signal | Boundary and lifetime |
| --- | --- |
| Subscription Paywall Viewed | One committed presentation/mount of the actual sheet, grid or paywall; never an opener intent, repeated build or frame. Storefront and yearly-switch views wait for successful loading and a rendered purchasable option; loading, failed, hidden, empty and unavailable offer branches do not consume them. Collapsed tiers and unselected unavailable prices do not count. The legacy web sheet additionally requires a recognized loaded current plan; the native settings grid requires its nonempty displayed catalog. The view latch stays consumed through refreshes within that presentation. Remote Flutter web content waits for its ready message. |
| Subscription Allowance Reached | An existing authoritative allowance/quota answer, backend refusal or server-owned cap payload. Repeated snapshots deduplicate until observed recovery or observer reset. Optimistic chat deltas, unavailable/invalid allowance reads and free/on-device policy alone are excluded. |
| Subscription Allowance Block Shown | The corresponding useful block UI is mounted, independently of authoritative reach or whether a paced automatic paywall opens. An optimistic local refusal still counts its rendered block; unavailable server cause uses unknown reason. Rebuilds deduplicate. A remounted block is a new presentation. |
| Subscription Upgrade Tapped | Existing upgrade CTA intent/confirmation boundary, alongside legacy Upgrade Plan Selected; contextual navigation CTAs without a selected price use unknown plan/interval. |
| Subscription Checkout Opened | A URL has been obtained and checkout is mounted/opened. Flutter uses the committed WebView route; native macOS uses the billing sheet appearance; Electron uses ready-to-show IPC after showing the window; web and external macOS chat require a successful browser open. Getting a URL alone never counts. |
| Subscription Checkout Completed | A verified client success navigation at the configured API origin and exact terminal pathname, independently of permissive legacy flow resolution. **Not accepted payment, entitlement, fulfillment or revenue.** Emitted independently of subsequent subscription refresh/polling; a successful navigation may precede refresh lag. Cancellation, dismissal and failed checkout-page navigation never complete. Upgrade-in-place and reactivation retain Upgrade Succeeded without inventing checkout completion. |
| Subscription Restore Attempted / Result | Flutter's three existing restore actions refresh subscription state. Results inspect the fresh read/error, including swallowed request errors; stale paid state cannot produce succeeded. Only succeeded, no_entitlement and failed are currently observable. These actions have no cancellation signal, so they do not emit cancelled. |

Allowances are observations per authoritative observer and surface, not unique account-level cap hits.
The same cap can be observed on several surfaces. Locked-content previews expose only a server lock
boolean, so their block kind/reason use unknown rather than inferring a billing cause. Reopening a block can produce another exposure while
repeated snapshots within its observer do not produce another reach. There is no persistent person,
record or billing-period identifier in these properties. An unobserved recovery cannot be inferred.
Shared-budget exhaustion is `usage_budget/budget_exhausted`,
never an additional `chat/chat_quota_exhausted` for the same authoritative snapshot. Distinct transcription
and chat caps can still both be observed. Kind changes and authoritative recovery rearm their own latches.
A mounted native chat warning that becomes a hard block emits Block Shown at that rendered transition;
optimistic refusal has an unknown cause and cannot manufacture an authoritative Reached event.

Legacy resolution and verified completion observation are separate. Flutter retains its legacy prefix-based
route pop, but the new callback additionally parses and matches the configured success scheme, host,
effective port and exact path, rejecting userinfo. Electron keeps legacy outcome strings for product
callers; main verifies against main-owned VITE_OMI_API_BASE (the same configuration/default authority as
main auth), exact success path and no userinfo, and returns only a closed outcome/observedCompletion
pair internally. Preload projects the original outcome and optional verified callback; the renderer
requires observed window opening plus verified success. Callback/visibility transport failures cannot
replace the product outcome. Native macOS retains its legacy matcher and UI completionURLs; a separate
coordinator observation compares configured scheme/host/effective port/exact encoded path and rejects
userinfo. Default HTTP(S) ports normalize; success session queries are allowed but never transported in
new observation data. Legacy lookalike/prefix/port/userinfo outcomes can still resolve exactly as before
without emitting new completion telemetry. Cancellation, dismissal, failure and late callbacks cannot
turn an unverified outcome into verified completion. No return URL or identifier is added to IPC.

Verified completion additionally requires main-frame authority. Flutter uses NavigationRequest.isMainFrame;
native macOS forwards WKNavigationAction.targetFrame?.isMainFrame and treats a missing target as unknown.
Electron will-redirect uses the installed event details isMainFrame flag, or the explicit deprecated fourth
argument when details lack the field; unknown/subframe redirects never verify completion. Its will-navigate
and did-navigate events are documented main-frame-only. Legacy subframe success can still pop/resolve
as before, but consumes the existing terminal lifetime without emitting new completion; a later main-frame
callback cannot retroactively verify it. This observation guard changes no checkout UI or payment authority.
See [Electron webContents navigation events](https://www.electronjs.org/docs/latest/api/web-contents).

Desktop popup block observations describe presentation, including optimistic local chat refusal while
the latest server snapshot still allows use. They deduplicate per presentation and use unknown reason
when no authoritative exhaustion cause exists; they never create an authoritative reach. Remounting
after dismissal counts another block. Server reach observations and quota/allowance gates are unchanged.

## Platform coverage

- Flutter (iOS/Android): shared native PlansSheet including storefront rendering; trial, outline and
  embedded-web variants; trial upsell, monthly fallback and yearly-switch confirmation. Native sheet
  and paywall variants share PaymentWebView checkout boundaries. Restore is server refresh, not store IAP.
  Subscription allowance, chat refusal/budget pause, server-locked conversation/memory/held-recording
  previews and MCP cap entry supply allowance observations/blocks.
- macOS: legacy settings plans and storefront/contextual sheets; usage-limit popup, chat quota banner,
  chat budget pause and Claude auth purchase gate. WKWebView success is separate from entitlement
  polling. External chat checkout opens in a browser and has no client completion return signal.
- Windows/Linux: the same Electron code covers both platforms. Settings plans, usage-limit popup and
  Claude auth gate are observed. Main-process checkout visibility is sent to the invoking renderer;
  the existing purchase guard permits one checkout at a time. Authoritative server quota snapshots
  are distinct from optimistic local refusal. The bar forwards a bounded authority boolean on its
  existing IPC so the main-window block observer can preserve that distinction. New purchase events use
  the Electron preload runtime platform: windows/Windows, linux/Linux or unknown/unknown. The legacy
  event envelope and the existing `omi-windows` library identifier retain continuity.
- Signed-in web: legacy PlansSheet, inline settings grid, storefront/contextual plans and server chat
  budget pause. New-tab checkout observes a static message from the existing backend success landing
  page, accepting only the configured API origin and the exact opened WindowProxy. The captured closed
  plan/interval/source dimensions are used once with `client_navigation_completed`; this observes
  navigation, not accepted payment. The cancel page sends a distinct static terminal message. Neither
  message contains checkout/account data. Wrong origin/window/payload, duplicate/late returns, closed
  windows and unopened popups cannot complete. Observers expire after 30 minutes or parent page exit.
  Focus/refresh never emits Checkout Completed. Opener isolation, popup blocking, API-origin mismatch,
  parent navigation or returns after expiry leave completion unobserved. The observer is optional and
  fail-open; landing-page content and payment/read/write logic are unchanged. Use authoritative server
  billing/invoice records and their paid/trial classification for payment analysis; Billing Subscription
  Started is a lifecycle signal and does not alone prove a charge.

No real purchase-restore action was found in native macOS, Windows/Linux or signed-in web purchase
surfaces. Those clients emit neither restore event. No separate Linux purchase tree, native store IAP
purchase/restore implementation, or signed-in web MCP-cap block implementation was found. External
pricing pages reached from auth gates are outside these clients' checkout boundaries; opening a pricing
page is not a Checkout Opened event.

Legacy Paywall Opened, Upgrade Succeeded/Attributed and Upgrade Cancelled behavior remains intact.
Upgrade Modal Clicked/Dismissed remain legacy app-update signals and must not be used as purchase views.
The checked-in consumer is an offline presence query, not a deployed dashboard, session funnel, revenue
measurement or causal conversion estimate. Missing client events mean unobserved, not failure.

The Electron trial-expiry card is a reminder, not an allowance block: it reports server trial expiry under the distinct trial dimension and a bounded View Plans intent, but never Allowance Block Shown. The new settings plan view requires the actual nonempty, server-visible catalog render branch; the legacy settings impression remains unchanged. A committed render is not proof of eye attention or viewport dwell.

## Focused test entry points

`web/app`'s existing `bun run build` first runs `bun run test:purchase-exposure`: the
hermetic plans/storefront, presentation/privacy and checkout-return regressions. This is
code-owned wiring into the existing build entry; local success is not exact-head CI proof.
`desktop/macos/scripts/run-swift-ci.sh --test` invokes `tests/purchase-exposure/run.sh`
before the SwiftPM suites. The standalone harness removes its temporary binaries/modules.
Windows unit tests retain inert API/Firebase values and a socket guard. Only the existing
explicit `OMI_E2E=1` live opt-in removes those test overrides/setup; configuration regressions
inspect both modes without loading credentials, running live E2E or making network calls.

These source corrections have 0pp direct conversion effect and no lift forecast. A view is per
mounted presentation, not a unique eligible pendant buyer. Eligible baseline N still requires
served platform/version receipts and authoritative non-subscriber, paired-device and allowance
eligibility. This source/test work establishes none of serving, baseline N, placement or lift.
