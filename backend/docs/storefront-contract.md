# First-party storefront presentation contract

`GET /v2/payments/plans?source=&trigger=&locale=` uses Firebase authentication
(including the existing no-BYOK-validation payment dependency), with the shared
per-UID `storefront:plans` rate limit (12 requests/minute, boost-exempt,
fail-open on Redis errors). Its response is `StorefrontResponse`,
`schema_version: 2`. Schema 1 on this route never shipped (the ladder flag
stayed off); the compatibility gate allows only that unpublished 1→2 response
replacement. Clients render server strings verbatim. Sheet chrome
(badges, toggle chrome, empty/error) stays in the client. W6 owns rendering;
these DTOs do not install the sheet by themselves.

`STOREFRONT_LADDER_V1_ENABLED` defaults to `false`; only exact `true` admits the
endpoint. Off returns 404 before database, App Review config or Stripe reads.
No client header enables it. Agents must not change deployment configuration.

When admitted, `should_hide_subscription_ui(uid, platform, version)` runs before
subscription, usage or price reads. Hidden callers receive
`show_subscription_ui: false`, no tiers and no current plan. A lookup error does
not expose the sheet.

`locale` is a BCP 47 tag. Matching is exact, then the language subtag
(`pt-BR` → `pt`, `zh-Hans` → `zh`). `nb` and `nn` use `no`. An unknown tag
uses `en`. Each locale is merged key-by-key over `en`, so a missing key keeps
the English string. Copy for every app locale lives in
`backend/config/storefront_copy_v1.json`. `pro_gates` stay the identifiers
`proactive_agent` and `screen_context`.

Dates use Babel's `MMMd` skeleton (`1. Nov.` in German, `11月1日` in Japanese).
English stays the shipped abbreviation (`Nov 1`). `resets {date}`, `/mo`, and
`/yr` are catalog strings (`dates.resets`, `dates.period_month`,
`dates.period_year`) and follow the locale. Counted phrases (months free, the
under-6 per-day line, and the hours meter line) use Babel's CLDR plural
category when that locale has a category map; otherwise they keep the one/many
pair. `{per_day}` inside `hours_lines.plus` is still a bare integer, and that
one sentence carries the hour-word for the count the plan actually shows.
Currency and number formatting are unchanged: USD `$`, a trailing ISO code
otherwise, thousands separators, and a trailing `.00` is dropped. Babel
(`babel==2.18.0`) is the date and plural dependency.

## Schema

- `catalog_revision`, `schema_version` (2), `show_subscription_ui`, `header`,
  `yearly_toggle_label`.
- `current`: `plan_id`, `name`, nullable `price_id`, nullable `interval`,
  `legacy`, `cancel_at_period_end`, `line`, nullable `legacy_note`. Absent only
  when the sheet is hidden.
- `usage`: `kind` (`usage_budget`, `transcription`, `unavailable`), nullable
  `percent`, nullable `period_id`, nullable `reset_label`, nullable
  `meter_line`, nullable `hours_left`, nullable `nudge_line`, nullable `more_label`, `pro_gates`.
  Never raw unit amounts. `more_label` is present only for `usage_budget`
  when `meter_line` is set; it is the words that open this sheet with
  `trigger=usage_budget`. It is omitted for legacy transcription usage and
  whenever there is no meter line.
- `tiers[]` in display order (recommended first, then ascending rank; while a
  cancellation is scheduled, the current tier is first, then the other ladder
  tiers by rank, and nothing is recommended): `tier_id`, `plan_id`, `name`,
  `recommended`, `is_current`, `hours_line`, `bullets`, `action`, nullable
  `cta_label`, nullable `blocked_line`, `compact`, `prices`.
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
Every `is_current` card sends `bullets: []`. The current line already says
what they have, so clients do not use `compact` to drop bullets. Legacy cards
do not repeat ladder hours; the legacy sentence is `current.legacy_note`.

Same tier, monthly, and not cancel-scheduled: the current card is
`action: checkout` with tier `cta_label: null`. Only its yearly price is
offered, with price-level `cta_label` `Switch to yearly · save {saving}`
(`saving` is 12× the monthly amount minus the annual amount, formatted in the
price currency). A price-level `cta_label` overrides the tier label. The
monthly price is not on that card. That yearly price's `headline` stays the
user's current monthly price (`$19.99/month`); the yearly offer is only the
`subline` and the price CTA. The card does not adopt the yearly-equivalent
headline while the interval toggle reads Monthly. Same tier, annual: the
monthly price is never offered, the card stays `action: current`, and there
is no price CTA.

`compact` is true when the current card has no tier button and no price CTA.
It is also true for the Free card on a cancel-scheduled paid sheet (plain
card: no bullets, no CTA).

`cancel_at_period_end` on a non-legacy paid plan offers checkout only on the
current tier, with tier `cta_label` `Resubscribe` and only that tier's current
`price_id`. `yearly_toggle_label` is null. There is no switch-to-yearly
label, no recommended badge, and the current tier is first. The sheet then
lists every other ladder tier by rank, lower and higher, including Free.
Every non-current tier is `action: none`, `cta_label: null`, and
`blocked_line: "Resubscribe first to change plans"`. Free is that plain card:
`compact: true`, `bullets: []`, `action: none`, and the same blocked line.
The header is `Your {Plan} plan ends {date}` and the current line is
`You're on {Plan} · {$price}/mo` (yearly: `{$price}/yr`). Free cancellation
does not open checkout. Legacy cancellation still has no checkout anywhere
and still omits Free. Neo and Unlimited are unchanged.

Paid plans that are not cancel-scheduled, including annual and legacy, omit
the Free tier from `tiers`. Free is not sent to them with `action: none` or
a blocked line. A Free subscriber still receives Free as the current card.
Its price headline is `$0`.

Pro (`operator`) omits Architect on settings, on the 80% budget surface, and
on every other trigger. The exhausted surface is the existing budget state:
`trigger=usage_budget` with usage percent at least 100, the same split that
selects the header `You've used all of this month's usage`. Below 100, or
with no percent, that trigger is the 80% surface and Architect stays hidden.
There is no separate cap trigger. On the exhausted surface Architect is
`recommended` and `action: checkout` (`Upgrade to Architect`). A Pro user
whose usage is already at 100 still does not see Architect when the sheet
was opened from another trigger. Plus keeps Pro as the recommended tier and
still lists Architect. Cancel-scheduled Pro lists Architect as a blocked
card, not as checkout. Legacy Pro never receives that checkout.

If the current card has no prices, including when the current Stripe price
cannot be retrieved, `action` is `current` and `cta_label` is null. That card
is never `checkout` with `prices: []`.

If the current price cannot be retrieved, `current.interval` is null and the
current card offers no prices, so a yearly subscriber is not shown a monthly
price.

`months_free` copy uses `1 month free` when the count is 1 and `{n} months free`
otherwise, in both the yearly subline and `yearly_toggle_label`. A locale with
`months_free_plural` selects the CLDR category for that count instead.

Pro-only triggers recommend Pro, including for Free. Free budget and MCP-cap
callers recommend Plus. Other paid callers below Pro recommend Pro. Architect
receives no badge. Pro receives a badge only on the exhausted surface above,
and the badge is Architect. Unknown sources use the default header. Invalid
triggers return 422. A legacy subscriber's header is always `Your plan`.

## Prices, hours, and usage

Only active USD recurring month/year prices with `interval_count` 1 are sold.
The current archived price is still shown. With no usable ladder price, Plus
and Pro are hidden. Architect stays visible with `action: none`, except a Pro
subscriber who is not cancel-scheduled and not on the exhausted surface: that
sheet omits Architect entirely. Free is the zero price with headline `$0`.
No amount is copied out of env or `proposed_prices`.

`months_free` is `floor(12 − annual/monthly)` when that value is at least 1.
`yearly_toggle_label` uses the smallest such value across tiers, or null. It
is also null while a non-legacy paid cancellation is scheduled.
Yearly headlines are the annual amount divided by 12, half-up to the
currency's minor unit (USD: cents), except the same-tier monthly-to-yearly
switch card, whose headline stays the current monthly price.

Every price, saving, subline, and current line uses one formatter. USD is
`$` plus the amount; other currencies keep a trailing ISO code. Thousands
separators always apply. A whole major unit omits a trailing `.00`
(`$199/month`, `$1,990 billed yearly`, `save $398`,
`You're on Architect · $199/mo`). A non-zero fraction keeps its decimals
(`$19.99`, `$16.66`, `$39.98`, `$499.90`). Zero-decimal currencies (JPY and
Stripe's other zero-decimal codes) are not divided by 100. Free stays `$0`.

Recording hours are `floor_to_nice(budget × 0.85 / 130)`. Free is fixed at 15.
Budgets are the plan-catalog usage units when the catalog declares them, and
otherwise the rate card in the copy config (Plus 16360, Pro 44090, Architect
189463). `units_per_recorded_hour` is provisional; replace it with the shadow
ledger p50 (#21369). Meter hours apply that definition to remaining units.
Hours appear only from 80% to below 100%.
`hours_left` is set only in that band when the estimate is positive, so a client can localize the wording while the backend stays authoritative for the number; it is omitted otherwise, including at the cap.
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

## Flagged ladder cutover additions

The configuration-backed six lookup-key bindings and additive `at_cap` copy
payload are defined in [ladder-v1-cutover.md](ladder-v1-cutover.md). The field is
absent on the dark path. Clients render it verbatim and continue using the
existing `usage_budget` trigger at 80% and 100%. Daily API nudge/reset metadata
uses `mcp_daily_cap`; no new trigger enum is required.

Integrated ladder additions remain optional in schema 2: `prices[].confirm_lines`
contains backend-owned monthly→yearly confirmation lines (only for a valid same-tier
switch with known period end). All first-party clients show them before any billing call.
`usage.pro_gates` is empty unless backend Pro enforcement applies to this account;
`usage.mcp_cap_reached=true` is emitted only after a read of the daily cap for a
ladder account with daily enforcement on. Settings visits never consume a request.
Mobile's 80% banner sends `trigger=usage_budget`; `budget_80` remains a source/key only.
The `pro_budget80` golden pins Architect's absence at 80% across clients.
Mobile renders `at_cap` strings verbatim, reads/writes the capability-gated monthly
choice, then enables on-device processing or opens the usage-budget upgrade surface.

With `LADDER_V1_BUDGET_ENFORCEMENT_ENABLED`, exhausted Free and ladder-v1
accounts receive additive `chat_at_cap` in the v2 storefront and chat-quota
payloads. Chat admission returns the same state in a 402 detail. It contains
`state=paused`, backend-owned `title`, `body`, `reset_line`, Unix-seconds
`reset_at`, `trigger=usage_budget`, and nullable `upgrade_plan`/`upgrade_label`.
Free offers Plus, Plus offers Pro, Pro offers Architect only at the cap, and
Architect waits for reset. Clients render these strings at the composer and
open the contextual plans sheet with `usage_budget`. Expiry or a fresh payload
without this state releases the composer; the server independently admits every
send. Legacy prices and disabled enforcement do not emit the storefront state.
Capture, held content and on-device transcription/summaries continue. There is
no fallback chat model or capped fallback allowance (David's October 14 evening
ruling supersedes ladder decision 7).

The chat-quota response sets `uses_shared_budget=true` for flagged ladder/Free
accounts at every percentage. Clients use the server `allowed` value there;
legacy question counters and optimistic question deltas do not decide admission.
The marker and pause state are omitted on the legacy/flag-off quota response.
