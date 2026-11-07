# Pre-registration: Settings plan card A/B (`settings-plan-card`)

**Question.** Does a plan card on the Settings sheet (the plan name large, the minutes meter and a
full-width Upgrade) raise free→paid conversion compared with the Plan & Usage row that has the
meter and Upgrade under it? Settings is opened by about 40% of active readers and most Settings
upgrades start there.

**Arms** (PostHog multivariate flag `settings-plan-card`, id 963589, experiment 486057, 50/50, split by
distinct id; draft until this build is in the stores):
- `control`: the Plan & Usage row, then the minutes meter and a full-width Upgrade.
- `card`: a plan card with a small "Plan & Usage" label, the plan name in large type, the minutes
  meter and line, then a full-width Upgrade; tapping the card outside Upgrade opens Plan & Usage.
Both arms open the same paywall (`openUpgradePaywall`, source `usage_page`), so `paywall-variant`
picks the design in either arm.

**Unit.** A Free or Plus reader who opens Settings. Exposure = `$feature_flag_called` with
`$feature_flag = settings-plan-card`, once per identity and arm, when the section is drawn for a
Free or Plus reader. Readers on other plans, readers with subscription UI hidden, and readers whose
arm is a fallback (no identity, unread flag, unknown variant) are never counted.

**Primary metric.** `Upgrade Succeeded` per exposed reader (funnel, 7-day window).

**Secondary / guardrails.** `Paywall Variant Shown` with `source = usage_page` per exposed reader
(Upgrade taps); `Upgrade Plan Selected` per exposed reader; Plan & Usage page opens per exposed
reader; `Product Error` per reader.

**Sample size.** About 6,800 readers open Settings in 30 days and about 8% of them upgrade in
that window (PostHog, 2026-10-15); most are Free. That is roughly 3,000 exposed readers per arm per
month, enough to detect a change of about 25% relative (8% to 10%) at 95% confidence and 80% power,
not a 10% one.

**Decision rule.** Run 4 weeks from launch (at least 3,000 exposed readers per arm), then read the
primary metric at PostHog's default confidence. Ship `card` only if it wins on the primary metric
without a worse guardrail; a flat result keeps control (the smaller change). Delete the losing
layout and this flag.

**Kill switch.** Set the split to control 100% (or deactivate the flag); every build shows the
control layout without a release.

**Owner.** yinka. Created 2026-10-15. Review by 2026-11-15.
