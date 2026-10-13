# First-party storefront presentation contract

`GET /v2/payments/plans` uses Firebase authentication (including the existing
no-BYOK-validation payment dependency). Its response is `StorefrontResponse`,
`schema_version: 1`. A new endpoint preserves installed-client wire shapes and
version gates. Clients adopting this endpoint render server order, names,
feature labels, price strings and actions without plan-specific branching.
W6 owns client rendering; these DTOs do not install the new sheet by themselves.

`STOREFRONT_LADDER_V1_ENABLED` defaults to `false`; only exact `true` admits the
new endpoint. Off returns 404 before database, App Review config or Stripe reads.
No client header enables it. Agents must not change deployment configuration.

When admitted, the existing `should_hide_subscription_ui(uid, platform, version)`
rule runs before subscription, usage or price reads. Hidden callers receive
`show_subscription_ui: false`, no tiers and no current plan. The existing rule's
platform scope is unchanged. A lookup error does not expose the sheet.

## Schema

- `catalog_revision`, `schema_version`, `show_subscription_ui`.
- `tiers[]`: unique `tier_id` (plan plus entitlement version), `plan_id`,
  `entitlement_version`, `display_name`, `tagline`, `features[]` (key, label,
  included), `prices[]`, `action`, `recommended`, `legacy`.
- `prices[]`: nullable `price_id` (Free has none), interval, currency,
  amount in minor units, formatted amount, monthly-equivalent string,
  optional annual savings (amount in minor units, percent, formatted copy).
- `next_offer_tier_id`: first offered upgrade tier, or null (never a client-computed ranking).
- `current`: plan id, nullable stored price id, legacy bool. Absent only when hidden.
- `usage`: kind (`transcription`, `usage_budget`, `unavailable`), nullable
  `budget_percent`, nullable Unix UTC `reset_at`. Never raw unit amounts.

Actions: `current`, `upgrade`, `downgrade_not_offered`, `contact`.
A current legacy row is always `current`, even when Stripe is unavailable or the
price is archived. Existing subscribers never receive an automatic migration
or an upgrade checkout from this sheet: higher tiers use contact until migration
policy is separately approved. Lower tiers are explicitly not offered.

## Contextual recommendation

Requests may pass `source` using the #21337 `Paywall Opened` vocabulary and
`trigger` (`proactive_agent`, `screen_context`, `usage_budget`, `mcp_daily_cap`).
Source describes the opening surface; trigger describes the gate on that surface.
Pro-only gates recommend Pro, including for Free callers. Free budget/MCP-cap
callers recommend Plus. Plus and all other paid callers (including legacy
subscribers priced at or above Plus) recommend Pro. Without gate context, Free
gets Plus and everyone else gets Pro. Unknown sources use the same default;
invalid triggers return 422.

`recommended` is a backend-authored badge, never a selection or checkout action.
It may appear on a current/contact tier; legacy migration actions stay contact.
If the recommended tier has no usable registered price and is hidden, no badge
is returned. `next_offer_tier_id` remains the first offered upgrade, independent
of the badge. Clients must never preselect a recommended tier.

## Prices and audience

The v2 ladder is platform independent: Free, Plus, Pro (`operator`), Architect.
Neo/Unlimited appear only as an existing subscriber's separate current row.
Legacy rows use existing-benefits copy, never ladder-v1 gate claims.

The W3 generated catalog's `LADDER_V1_STRIPE_PRICES` is the only activation list.
It joins recognized-price plan/interval/version metadata and the existing
`is_purchasable_price_id` checkout boundary. Missing W3 declarations act as an
empty list. Prices must be active, USD, recurring month/year with interval_count
1; unsupported billing shapes are omitted. No new price is inferred from env
configuration or the proposal config's amounts.

With no usable ladder-v1 price, Plus/Pro are hidden. Architect remains a visible
contact tier (no invented amount), and Free has the backend-authored zero price.
The current paid row is preserved independently of purchase availability.
This is the brief's hide-unpurchasable-tiers option, rather than selling legacy
prices with new entitlement claims. Architect does not become purchasable until
its price is explicitly registered as ladder-v1 and its amount verified.

Savings use the retrieved monthly and annual prices: `12 * monthly - annual`;
percent is that difference divided by `12 * monthly`. No savings copy is emitted
if the difference is zero/negative or a matching monthly price is unavailable.
Monthly equivalent divides the annual amount by 12, formatted to two decimals.

The old endpoints and `_platform_hidden_plans` remain unchanged for installed
clients; partition retirement happens through v2 adoption. Sixty plan/platform/cancellation
combinations compare old response bytes with the flag unset, false and true.
This deliberately does not change released-client purchase or entitlement rules.

## Usage projection seam

If W3 exposes `get_usage_units(uid)` on `utils.subscription`, the adapter accepts
its display-ready `budget_percent` and Unix `reset_at` fields. No such function
exists on current main; the seam is optional and needs W3 coordination before
activation. Ladder-v1 paid prices without that projection return unavailable
usage instead of showing a legacy transcription cap as a shared budget.
Legacy/Free callers may show the existing monthly speech allowance percentage
and next UTC calendar month reset. Provider errors omit usage with fallback telemetry.

## Dry-run proposal and Architect evidence

`backend/scripts/plan_prices_dry_run.py` is fixture driven, has no credential or
network path, and refuses `--execute` outright. The presentation config's
`proposed_prices` are tooling inputs only. The output lists exact Stripe create
arguments plus both the recognized-price registrations and activation-ID diff.
No catalog or Stripe object is modified.

Code-read findings: `plan_catalog.json` has Architect chat allocation 40,000 USD
cents ($400), an overage-enabled legacy spend limit, and proactivity monthly
reference 19,900 cents ($199), also documented in
`backend/docs/proactivity_v2/CONTRACT.md`. These are distinct policy/reference amounts, not
live Stripe price evidence. `test_overage_catalog.py`, `test_chat_quota.py`,
`ChatQuotaBannerTests.swift` and `FloatingBarUsageLimiterTests.swift` exercise the
$400 cap. `test_subscription_restructure.py`'s header and
`APIClient+Settings.swift`'s enum comment still say Architect $400/month.
No prices or legacy limits were changed. Live Stripe verification was not run:
no read-only credential path was established without reading secrets.
