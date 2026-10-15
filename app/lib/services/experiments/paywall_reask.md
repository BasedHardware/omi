# Pre-registration: plans reminder on app open (`paywall-reask`)

**Question.** Free users only see the plans when they hit a limit, a locked item or open
Settings, so many never learn what the plans include. Does an occasional, unobtrusive reminder
of the plans on app open help users who want more find them, without making the app less
pleasant to use?

**Groups** (PostHog flag `paywall-reask`, variants `control` / `test`, 50/50, per user):
- `control` — no change.
- `test` — on app open (launch or back from the background), the existing plans screen
  (`PaywallRouter.openVariant`, so `paywall-variant` still picks its design; otherwise the plans
  sheet), queued in `PromptQueue` so it never appears over a recording, a call or another prompt.

**Timing** (`PaywallReask`). Shown when 2, 3, 5 and then every 7 local calendar days have passed
since the user last saw the plans from anywhere; a user who never saw them starts the timer at
their first Home visit, so never on sign-up day. At most once a day. Free plan only (`basic`,
subscription UI shown); skipped if the user upgraded before it appears.

**Who is counted.** A free user reaching a due moment. Exposure = `$feature_flag_called` with
`$feature_flag = paywall-reask`, once per user and group, at the first due moment; `control`
follows the same timing without showing anything, so both groups are counted alike.

**Primary metric.** `Upgrade Succeeded` per exposed user within 14 days of exposure.

**Guardrails.** Days with an app open in the 14 days after exposure (must not drop more than 5%
relative against control); `Upgrade Modal Dismissed` per user; `Product Error` per user. Also
read: `Paywall Opened` (source `app_open_reask`) → `Upgrade Succeeded`.

**Decision rule.** Keep it if the primary metric improves at PostHog's default confidence and
the active-days guardrail holds; stop early if active days drop more than 10% relative. Run
until each group has at least 1,000 exposed users or 21 days, whichever is later. Changing the
timing is a follow-up experiment, not a change mid-run.

**Kill switch.** Set the split to control 100% (or deactivate the flag); no release needed.

**Owner.** yinka. Created 2026-10-14. Review by 2026-11-13.
