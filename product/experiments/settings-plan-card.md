# Pre-registration: Settings plan card A/B (`settings-plan-card`)

**Question.** Does a plan card on the Settings sheet (the plan name large, the minutes meter and a
full-width Upgrade) raise free→paid conversion compared with the Plan & Usage row that has the
meter and Upgrade under it? Settings is opened by about 40% of active readers and most Settings
upgrades start there.

**Arms** (PostHog multivariate flag `settings-plan-card`, 50/50, experience continuity on):
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

**Decision rule.** Minimum detectable effect 10% relative on the primary metric at PostHog's
default confidence. Run until each arm has at least 2,000 exposed readers or 14 days, whichever is
later. Ship the winner to 100% and delete the losing layout and this flag.

**Kill switch.** Set the split to control 100% (or deactivate the flag); every build shows the
control layout without a release.

**Owner.** yinka. Created 2026-10-15. Review by 2026-11-15.
