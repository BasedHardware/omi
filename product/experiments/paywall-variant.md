# Pre-registration: mobile paywall A/B (`paywall-variant`)

**Question.** Does a redesigned paywall raise free→paid conversion on mobile? Today about 20% of
free mobile readers who see a paywall ever upgrade; Pocket and Plaud report around 50%.

**Arms** (PostHog multivariate flag `paywall-variant`, id 957521, experience continuity on):
- `control` — the shipped `PlansSheet`, unchanged.
- `outline` — native port of the soft paywall from PR #21412 (Graphite direction), plus one
  placement at the end of first-run onboarding (`onboarding_paywall: true`).
- `web` — a webview paywall whose page is the variant (payload `url`), same onboarding placement.
- `trial` — native free-trial paywall (feature carousel, dated timeline, month/year, "Start for
  $0.00"); its placement is once right after sign-up and consent (`onboarding_paywall: true`), and
  checkout passes `trial_days: 7`, which the backend honors only for a first-time subscriber.
New designs join as new arms; the split is set in PostHog, never in code.

**Unit.** A free reader who is shown a paywall. Exposure = `$feature_flag_called` with
`$feature_flag = paywall-variant`, emitted once per arm per app process by `PaywallRouter` at the
moment a variant (or control) paywall opens. Paid readers and App Review builds never enter.

**Primary metric.** `Upgrade Succeeded` per exposed reader (funnel, 7-day window).

**Secondary / guardrails.** New MRR (`Billing Subscription Started`, sum `mrr_cents`);
`Paywall Opened → Upgrade Succeeded`; `Upgrade Modal Dismissed` per reader; `Product Error` per
reader (crash proxy); `Paywall Variant Fallback` per reader (web page failures). Dashboard 2207880
breaks every metric down by `$feature/paywall-variant`.

**Decision rule.** Minimum detectable effect 10% relative on the primary metric at PostHog's
default confidence; an arm whose Product Error or fallback rate is worse than control by more
than 20% relative is switched to 0% regardless of conversion. Run until each arm has at least
2,000 exposed readers or 14 days, whichever is later.

**Kill switch.** Set the flag's split to control 100% (or deactivate the flag); every build
falls back to the shipped sheet without a release.

**Owner.** nik. Created 2026-10-13. Review by 2026-11-12.
