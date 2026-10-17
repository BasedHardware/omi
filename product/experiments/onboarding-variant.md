# Pre-registration: mobile first-run onboarding A/B/C (`onboarding-variant`)

**Question.** Which first-run onboarding gets more new mobile readers to finish onboarding and to
pay: today's steps, a device-first onboarding, or one that ends in a first real conversation?

**Arms** (PostHog multivariate flag `onboarding-variant`, id 961069, experience continuity on):
- `control` — the shipped native steps, unchanged.
- `reid` — Reid's device-first onboarding (PR #21412 prototype) rendered from a web page after
  sign-in and consent (payload `url`); a page that errors or never reports ready falls back to
  control.
- `yinka` — Yinka's onboarding (PR #21445): Name → Permissions → Language → Connect Omi → a first
  real conversation with its summary and to-dos, the paywall and a rating ask, native.
New designs join as new arms; the split is set in PostHog, never in code.

**Unit.** A signed-in reader who reaches the steps after consent. Exposure = `Onboarding Variant
Shown` (property `$feature/onboarding-variant`), emitted once by the onboarding wrapper at the
moment the arm is entered; an unread flag counts as control.

**Primary metrics.** `Onboarding Completed` per exposed reader (funnel, 7-day window) and
`Upgrade Succeeded` per exposed reader (funnel, 7-day window).

**Secondary / guardrails.** `Paywall Variant Shown` per reader; new MRR (`Billing Subscription
Started`, sum `mrr_cents`); `Conversation Processing Completed` per reader (first conversation);
`Product Error` per reader (crash proxy). Dashboard 2212642 breaks the funnel down by
`$feature/onboarding-variant`; experiment 484222 holds the significance stats.

**Decision rule.** Minimum detectable effect 10% relative on the primary metrics at PostHog's
default confidence; an arm whose Product Error rate is worse than control by more than 20%
relative, or whose completion is worse than control by more than 20% relative, is switched to 0%
regardless of conversion. Run until each arm has at least 2,000 exposed readers or 14 days,
whichever is later.

**Kill switch.** Set the flag's split to control 100% (or deactivate the flag); every build
falls back to the shipped steps without a release.

**Owner.** nik. Created 2026-10-14. Review by 2026-11-13.
