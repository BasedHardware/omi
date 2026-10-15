# Mobile paywall and onboarding web pages

Static pages rendered inside the mobile app's webview when PostHog puts a reader in the `web`
paywall arm (`paywall-variant`) or turns on `onboarding-webview`. Editing and redeploying these
files changes what those readers see with no app release and no store review.

- `index.html` — paywall. The app opens it with `source`, `platform`, `locale`, `name`,
  `free_minutes`, `tier`, `year_amount`/`year_currency`, `month_amount`/`month_currency` query
  parameters and listens on the `OmiPaywall` JavaScript channel for
  `{"type":"ready"|"checkout"|"free"|"restore"|"fallback", "interval":"year"|"month"}`.
  The app runs the real Stripe checkout; the page only renders. It may define
  `window.OmiPaywallHost.onCheckout(outcome)`.
- `index.html` — picks the reader's paywall version once (`VERSIONS` weights, default
  `benefits` 50 / `steps` 50), remembers it on the device, and opens that page with the app's
  query parameters. `?v=benefits|steps|classic` previews a version without changing the assignment.
  Change the split by editing `VERSIONS`; readers keep the version they already got.
- `benefits.html` — one page: device, headline, four benefits, plans.
- `steps.html` — three pages: promise with device → what you get (swipeable app screenshots) →
  plans with device and social proof.
- `classic.html` — the original single page (not in the split).
- `track.js` — sends events straight to PostHog (project 302298) with `paywall_version`. The page
  does not know who the reader is: events use an anonymous id kept on the device and create no
  person profiles, so results compare versions on the paywall and at checkout, not what readers
  do after paying. Events are queued on the device until PostHog accepts them and resent on the
  next load with the same uuid. Events: `Web Paywall Viewed`, `Web Paywall Step Viewed` (step),
  `Web Paywall Slide Viewed` (slide), `Web Paywall Plan Selected` (interval),
  `Web Paywall Checkout Tapped` (interval), `Web Paywall Checkout Result` (interval, outcome:
  purchased|cancelled|failed|unavailable), `Web Paywall Dismissed` (only from a close button the
  page owns; the app's own close button sits over the top-left corner and is not seen here).
- `onboarding.html` — first-run onboarding after sign-in and consent. Channel `OmiOnboarding`:
  `ready`, `set_name`, `permission` (`notifications`|`location`|`background`), `complete`, `fallback`;
  results arrive on `window.OmiOnboardingHost.onPermission(kind, status)`. Completion stays native.

Deploy: `cd web/paywall && vercel --prod` (project `omi-paywall`, https://omi-paywall.vercel.app).
A page that errors, returns 4xx/5xx or never posts `ready` within 10 s falls back to the native UI.
Keep every page on https; the app refuses anything else.
