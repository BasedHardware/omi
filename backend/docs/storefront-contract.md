# First-party storefront presentation contract

`GET /v2/payments/plans?source=&trigger=&locale=` uses Firebase authentication
(including the existing no-BYOK-validation payment dependency), with the shared
per-UID `storefront:plans` rate limit (12 requests/minute, boost-exempt,
fail-open on Redis errors). Its response is `StorefrontResponse`,
`schema_version: 2`. Clients render server strings verbatim. Sheet chrome
(badges, toggle chrome, empty/error) stays in the client. W6 owns rendering;
these DTOs do not install the sheet by themselves.

`STOREFRONT_LADDER_V1_ENABLED` defaults to `false`; only exact `true` admits the
endpoint. Off returns 404 before database, App Review config or Stripe reads.
No client header enables it. Agents must not change deployment configuration.

When admitted, `should_hide_subscription_ui(uid, platform, version)` runs before
subscription, usage or price reads. Hidden callers receive
`show_subscription_ui: false`, no tiers and no current plan. A lookup error does
not expose the sheet.

`locale` is accepted and falls back to `en`. Copy lives in
`backend/config/storefront_copy_v1.json`.

## Schema

- `catalog_revision`, `schema_version` (2), `show_subscription_ui`, `header`,
  `yearly_toggle_label`.
- `current`: `plan_id`, `name`, nullable `price_id`, nullable `interval`,
  `legacy`, `cancel_at_period_end`, `line`, nullable `legacy_note`. Absent only
  when the sheet is hidden.
- `usage`: `kind` (`usage_budget`, `transcription`, `unavailable`), nullable
  `percent`, nullable `period_id`, nullable `reset_label`, nullable
  `meter_line`, nullable `nudge_line`, `pro_gates`. Never raw unit amounts.
- `tiers[]` in display order (recommended first, then ascending rank; while a
  cancellation is scheduled, the current tier is first and nothing is
  recommended): `tier_id`, `plan_id`, `name`, `recommended`, `is_current`,
  `hours_line`, `bullets`, `action`, nullable `cta_label`, nullable
  `blocked_line`, `compact`, `prices`.
- `prices[]`: nullable `price_id`, `interval`, `amount_minor`, `currency`,
  `headline`, nullable `subline`, nullable `renewal_line`, `months_free` only
  when the live yearly price gives at least one free month, and `cta_label`
  only when that price overrides the tier button.

Actions: `checkout`, `current`, `none`. `recommended` is a badge, never a
selection or a checkout.

## Policy

Rank is `basic < plus < operator < architect`. Neo (`unlimited`) and Unlimited
(`unlimited_v2`) have no rank. A non-free plan is legacy when it has no ladder
rank or its stored price is not in `LADDER_V1_STRIPE_PRICES`.

Legacy subscribers get no `checkout` on any card, including when cancellation
is scheduled. Neo/Unlimited may see Pro and Architect as higher offers with
`action: none`. Lower tiers are `none`. Each current plan id has one card.
Legacy cards do not repeat ladder hours or bullets; the legacy sentence is
`current.legacy_note`.

Same tier: an annual subscriber is not offered the monthly price. A monthly
subscriber may still see the annual price. That yearly price carries
`cta_label` `Switch to yearly · save {saving}` (`saving` is 12× the monthly
amount minus the annual amount, formatted in the price currency). The tier
button stays empty, so the current plan never says `Get {Plan}`. The current
card sets `compact` when it has no tier button and no price CTA; the client
drops bullets. A price CTA or Resubscribe leaves `compact` false and still
sends no extra tagline.

`cancel_at_period_end` on a non-legacy paid plan offers checkout only on the
current tier, with tier `cta_label` `Resubscribe` on its current price. Every
other tier is `action: none`, `cta_label: null`, and
`blocked_line: "Resubscribe first to change plans"`. There is no switch-to-yearly
label, no recommended badge, and the current tier is first. The header is
`Your {Plan} plan ends {date}` and the current line is
`You're on {Plan} · {$price}/mo` (yearly: `{$price}/yr`). Free cancellation does
not open checkout. Legacy cancellation still has no checkout anywhere.

`months_free` copy uses `1 month free` when the count is 1 and `{n} months free`
otherwise, in both the yearly subline and `yearly_toggle_label`.

Pro-only triggers recommend Pro, including for Free. Free budget and MCP-cap
callers recommend Plus. Other paid callers below Pro recommend Pro. Pro and
Architect receive no badge. Unknown sources use the default header. Invalid
triggers return 422. A legacy subscriber's header is always `Your plan`.

## Prices, hours, and usage

Only active USD recurring month/year prices with `interval_count` 1 are sold.
The current archived price is still shown. With no usable ladder price, Plus
and Pro are hidden and Architect stays visible with `action: none`. Free is the
zero monthly price. No amount is copied out of env or `proposed_prices`.

`months_free` is `floor(12 − annual/monthly)` when that value is at least 1.
`yearly_toggle_label` uses the smallest such value across tiers, or null.
Yearly headlines are the annual amount divided by 12, half-up to cents.

Recording hours are `floor_to_nice(budget × 0.85 / 130)`. Free is fixed at 15.
Budgets are the plan-catalog usage units when the catalog declares them, and
otherwise the rate card in the copy config (Plus 16360, Pro 44090, Architect
189463). `units_per_recorded_hour` is provisional; replace it with the shadow
ledger p50 (#21369). Meter hours apply that definition to remaining units.
The client does not hardcode hours.

Price reads use `stripe_price:{price_id}` with a 24-hour TTL. Cache failures
stay fail-open. Provider errors omit the price and record fallback telemetry.

If `get_usage_units(uid)` exists, its `budget_percent` and Unix `reset_at` are
accepted only for Free or ladder-v1 subscribers. Legacy callers keep the speech
allowance (`kind: transcription`) or `unavailable` when that allowance is
absent. Ladder-v1 callers without the projection return `unavailable` rather
than a speech cap labelled as the shared budget.

The v1 payment endpoints are unchanged. This route does not write Stripe or
grant entitlements.
