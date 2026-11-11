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
| Subscription Paywall Viewed | One committed presentation/mount of the actual sheet, grid or paywall; never an opener intent, repeated build or frame. Hidden surfaces do not count. Remote Flutter web content waits for its ready message. |
| Subscription Allowance Reached | An existing authoritative allowance/quota answer, backend refusal or server-owned cap payload. Repeated snapshots deduplicate until observed recovery or observer reset. Optimistic chat deltas, unavailable/invalid allowance reads and free/on-device policy alone are excluded. |
| Subscription Allowance Block Shown | The corresponding useful block UI is mounted, independently of whether a paced automatic paywall opens. Rebuilds deduplicate. A remounted block is a new presentation. |
| Subscription Upgrade Tapped | Existing upgrade CTA intent/confirmation boundary, alongside legacy Upgrade Plan Selected; contextual navigation CTAs without a selected price use unknown plan/interval. |
| Subscription Checkout Opened | A URL has been obtained and checkout is mounted/opened. Flutter uses the committed WebView route; native macOS uses the billing sheet appearance; Electron uses ready-to-show IPC after showing the window; web and external macOS chat require a successful browser open. Getting a URL alone never counts. |
| Subscription Checkout Completed | The existing client success-navigation boundary. **Not accepted payment, entitlement, fulfillment or revenue.** Emitted independently of subsequent subscription refresh/polling; a successful navigation may precede refresh lag. Cancellation, dismissal and failed checkout-page navigation never complete. Upgrade-in-place and reactivation retain Upgrade Succeeded without inventing checkout completion. |
| Subscription Restore Attempted / Result | Flutter's three existing restore actions refresh subscription state. Results inspect the fresh read/error, including swallowed request errors; stale paid state cannot produce succeeded. Only succeeded, no_entitlement and failed are currently observable. These actions have no cancellation signal, so they do not emit cancelled. |

Allowances are observations per authoritative observer and surface, not unique account-level cap hits.
The same cap can be observed on several surfaces. Locked-content previews expose only a server lock
boolean, so their block kind/reason use unknown rather than inferring a billing cause. Reopening a block can produce another exposure while
repeated snapshots within its observer do not produce another reach. There is no persistent person,
record or billing-period identifier in these properties. An unobserved recovery cannot be inferred.

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
  existing IPC so the main-window block observer can preserve that distinction. The existing analytics envelope labels this shared
  client as Windows even on Linux; that pre-existing enrichment is unchanged here.
- Signed-in web: legacy PlansSheet, inline settings grid, storefront/contextual plans and server chat
  budget pause. New-tab checkout has **no observable client success return**. Focus/refresh never emits
  Checkout Completed. Use authoritative server billing/invoice records and their paid/trial classification for payment analysis;
  Billing Subscription Started is a lifecycle signal and does not alone prove a charge; no server payment code changes are part of this work.

No real purchase-restore action was found in native macOS, Windows/Linux or signed-in web purchase
surfaces. Those clients emit neither restore event. No separate Linux purchase tree, native store IAP
purchase/restore implementation, or signed-in web MCP-cap block implementation was found. External
pricing pages reached from auth gates are outside these clients' checkout boundaries; opening a pricing
page is not a Checkout Opened event.

Legacy Paywall Opened, Upgrade Succeeded/Attributed and Upgrade Cancelled behavior remains intact.
Upgrade Modal Clicked/Dismissed remain legacy app-update signals and must not be used as purchase views.
The checked-in consumer is an offline presence query, not a deployed dashboard, session funnel, revenue
measurement or causal conversion estimate. Missing client events mean unobserved, not failure.
