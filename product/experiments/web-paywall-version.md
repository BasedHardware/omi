# Pre-registration: web paywall page (`web-paywall-version`)

**Question.** Inside the web paywall, does a three-page paywall (the device, what you get, then
plans) get more free readers to buy Unlimited than a one-page paywall?

**Where it runs.** The `web` arm of `paywall-variant` loads `https://omi-paywall.vercel.app/`
(source: `web/paywall/`). `index.html` asks PostHog for this flag and opens the page:
- `benefits` — one page: device, headline, four benefits, plans.
- `steps` — three pages: promise with the device → three drawn phones → plans with social proof.
Every paywall surface that opens the `web` arm runs it (end of onboarding, chat limit, Usage page,
freemium switch, contextual plans); `source` on every event says which.

**Unit.** A reader the app identifies: the app passes its PostHog `distinct_id` in the URL fragment (never sent to the server) and the
flag buckets on it, so a reader keeps one page across visits and devices. Exposure is
`$feature_flag_called` for `web-paywall-version`, sent by the page on load and only when PostHog
answered with a variant. Readers whose flag read failed or timed out (2.5 s) see `benefits`, are
tracked with `assignment: cache|fallback`, and are not in the analysis. App builds that predate
the `distinct_id` fragment send anonymous events without person profiles; they count in the page
funnel but cannot join `Upgrade Succeeded`. Readers with product analytics off send nothing.

**Primary metric.** `Upgrade Succeeded` per exposed reader (funnel, 7-day window).

**Secondary.** `Web Paywall Checkout Tapped` per exposed reader; `Web Paywall Checkout Result`
with `outcome = purchased` per exposed reader; for `steps`, reach of `Web Paywall Step Viewed`
step 2 and 3 (where readers drop). **Guardrails:** `Web Paywall Error` per reader,
`Paywall Variant Fallback` (app replaced the page with the native sheet), `Web Paywall Assignment
Fallback` rate (flag reads failing).

**Decision rule.** Run until each page has at least 1,000 exposed readers or 14 days, whichever is
later. Ship the page with the higher primary metric at PostHog's default confidence; if neither
wins, keep `benefits` (simpler). A page whose error or fallback rate is more than 20% (relative)
above the other's is stopped regardless.

**Kill switch.** Pause or end experiment 486505 (flag off → everyone gets `benefits`, no
exposures), or set `paywall-variant` back to `control` to leave the web paywall entirely. Neither
needs an app release or a Vercel deploy.

**Owner.** yinka. Created 2026-10-15. Review by 2026-11-15. PostHog flag 964524, experiment 486505.
