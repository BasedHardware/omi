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
- `onboarding.html` — first-run onboarding after sign-in and consent. Channel `OmiOnboarding`:
  `ready`, `set_name`, `permission` (`notifications`|`location`|`background`), `complete`, `fallback`;
  results arrive on `window.OmiOnboardingHost.onPermission(kind, status)`. Completion stays native.

Deploy: `cd web/paywall && vercel --prod` (project `omi-paywall`, https://omi-paywall.vercel.app).
A page that errors, returns 4xx/5xx or never posts `ready` within 10 s falls back to the native UI.
Keep every page on https; the app refuses anything else.
