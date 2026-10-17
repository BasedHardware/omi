# Mobile paywall and onboarding web pages

Static pages rendered inside the mobile app's webview when PostHog puts a reader in the `web`
paywall arm (`paywall-variant`) or turns on `onboarding-webview`. Editing and redeploying these
files changes what those readers see with no app release and no store review.

## Paywall

The app opens `https://omi-paywall.vercel.app/` (the `url` in the `web` arm's payload) with
`source`, `platform`, `locale`, `name`, `free_minutes`, `tier`, `year_amount`/`year_currency`,
`month_amount`/`month_currency` in the query (or `analytics=off` when the reader turned product
analytics off) and, from app builds that have it, the reader's PostHog `distinct_id` in the fragment
(`#distinct_id=…`), which never reaches the server; `track.js` keeps it for the webview session and
drops it from the visible address. It listens on the
`OmiPaywall` JavaScript channel for
`{"type":"ready"|"checkout"|"free"|"restore"|"fallback", "interval":"year"|"month"}` and calls
`window.OmiPaywallHost.onCheckout(outcome)` after checkout. The app runs the real Stripe checkout;
the page only renders. A page that errors, returns 4xx/5xx or never posts `ready` within 10 s is
replaced by the native plans sheet. The app draws its own (white) close button over the top-left
corner of every page.

- `index.html` — asks PostHog which page this reader gets (flag `web-paywall-version`, variants
  `benefits` / `steps`, experiment 486505) and opens it. Flag off or not launched → `benefits`,
  no exposure. No answer within 2.5 s → the page this device had last time, else `benefits`, no
  exposure. `?v=benefits|steps|classic` previews a page without touching the assignment.
- `benefits.html` — one page: device, headline, four benefits, plans.
- `steps.html` — three pages: the pendant with floating cards → three drawn phones → plans with
  social proof and a scrollable perks list.
- `classic.html` — the original single page (preview only, not in the split).
- `track.js` — PostHog (project 302298) events and the flag read. Events carry `paywall_version`,
  `assignment` (`flag`, `flag_off`, `cache`, `fallback`, `preview`, `local`, `direct`),
  `identified`, `source`, `platform`, `locale`, prices, `page_id` and `seconds_on_page`; with a real
  flag answer they also carry `$feature/web-paywall-version`, and the page sends the
  `$feature_flag_called` exposure. With the app's `distinct_id` the events join the reader's person
  (and `Upgrade Succeeded`); without it they are anonymous and create no person profile. Events
  are queued on the device until PostHog accepts them and resent on the next load (same uuid).

Events: `Web Paywall Viewed` (default_interval, load_ms), `Web Paywall Step Viewed` (step,
seconds_on_previous_step), `Web Paywall Plan Selected` (interval), `Web Paywall Checkout Tapped`
(interval), `Web Paywall Checkout Result` (interval, outcome: purchased|cancelled|failed|unavailable),
`Web Paywall Dismissed` (step; only from a close button the page owns), `Web Paywall Legal Tapped`
(link), `Web Paywall Scrolled` / `Web Paywall Perks Scrolled`, `Web Paywall Left` (how, step; best
effort), `Web Paywall Error`, `Web Paywall Assignment Fallback` (reason, ms).

## Running the A/B test

1. Deploy: `cd web/paywall && vercel --prod` (project `omi-paywall`). Check
   `https://omi-paywall.vercel.app/?v=benefits` and `?v=steps` in a phone-sized browser.
2. Ship an app build that passes `distinct_id` (web_paywall_page.dart). Older builds still work,
   with anonymous events only.
3. In PostHog, point readers at the web paywall: `paywall-variant` → `web` 100% (its payload
   already holds the URL and `onboarding_paywall: true`).
4. Launch experiment 486505. That turns `web-paywall-version` on and splits readers 50/50.
5. Read results in the experiment (primary: `Upgrade Succeeded`, 7 days). Prereg:
   `product/experiments/web-paywall-version.md`.

Stop: end or pause the experiment (everyone gets `benefits`), or set `paywall-variant` back to
`control` (native plans sheet). Neither needs a deploy or an app release.

## Onboarding

`onboarding.html` — first-run onboarding after sign-in and consent. Channel `OmiOnboarding`:
`ready`, `set_name`, `permission` (`notifications`|`location`|`background`), `complete`, `fallback`;
results arrive on `window.OmiOnboardingHost.onPermission(kind, status)`. Completion stays native.

Keep every page on https; the app refuses anything else.
