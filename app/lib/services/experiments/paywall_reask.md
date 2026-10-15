# Pre-registration: paywall re-ask on app open (`paywall-reask`)

**Question.** Free readers keep opening Omi but rarely meet a paywall, because every paywall
today waits for a limit, a locked item or a Settings tap. Does offering the plans again on app
open, spaced out so it doesn't nag, raise free→paid conversion without driving readers away?

**Arms** (PostHog flag `paywall-reask`, experiment with variants `control` / `test`, 50/50,
user-based):
- `control` — nothing new.
- `test` — on app open (launch or back from the background), the paywall the reader would get
  anywhere else (`PaywallRouter.openVariant`, so `paywall-variant` still picks its design; control gets the
  plans sheet), queued in
  `PromptQueue` (never over a recording, a call or another prompt).

**Schedule** (`PaywallReask`). Due when 2, 3, 5 and then every 7 local calendar days have
passed since the last paywall the reader saw from any source; a reader who never saw one starts
the clock at their first Home visit, so never on onboarding day. At most one per day. Free plan
only (`basic`, subscription UI shown); dropped if the reader subscribed before it shows.

**Unit.** A free reader with a due moment. Exposure = `$feature_flag_called` with
`$feature_flag = paywall-reask`, once per reader and arm, at the first due moment; control
advances the same schedule without showing anything, so both arms are counted alike.

**Primary metric.** `Upgrade Succeeded` per exposed reader within 14 days of exposure.

**Secondary / guardrails.** `Paywall Opened` (source `app_open_reask`) → `Upgrade Succeeded`;
`Upgrade Modal Dismissed` per reader; days with an app open in the 14 days after exposure (must
not drop more than 5% relative against control); `Product Error` per reader.

**Decision rule.** Ship to 100% if the primary metric improves at PostHog's default confidence
and the active-days guardrail holds; stop early if active days drop more than 10% relative.
Run until each arm has at least 1,000 exposed readers or 21 days, whichever is later. Tuning the
gaps is a follow-up experiment, not a change mid-run.

**Kill switch.** Set the split to control 100% (or deactivate the flag); no release needed.

**Owner.** yinka. Created 2026-10-14. Review by 2026-11-13.
