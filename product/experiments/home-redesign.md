# Pre-registration: mobile Home redesign A/B (`home-redesign`)

**Question.** Does the redesigned Home (from #21711) make new and existing mobile readers record
more, come back more and upgrade more than today's Home?

**Arms** (PostHog flag `home-redesign`, id 963799, experiment 486169, 50/50 by distinct id; draft until the
build is in the stores):
- `control` — today's Home, unchanged: the Ask Omi chat bar with the round record button, the live
  recording card above the list, empty states with icons, the calendar in the
  header, locked rows that open Usage, no chat welcome or starter to-dos.
- `test` — the redesigned Home: Ask Omi beside one recording pill that carries every recording state
  (no card above the list; details in a sheet), text-only empty
  states, Omi pull-to-refresh, page actions beside the Home/Tasks switcher, locked rows that open
  the paywall in place ("Upgrade"), the Tasks tick-and-fold, a closable voice-profile card, Omi's
  first chat message, the Tasks dot and starter to-dos after onboarding.
Shared by both arms (not part of the comparison): the Activity bell and the one "on the way" row
for syncing and processing work (#21689, #21850), the
Tasks menu in the header, the Settings plan card.

**Unit.** A signed-in reader who reaches Home. Exposure = `$feature_flag_called` with
`$feature_flag = home-redesign`, once per account and arm, when Home is first shown after PostHog has
assigned the arm. The arm is saved per account: a reader never switches Home mid-session; a new
assignment applies from the next launch if Home was already on screen. An unread flag is control
and is not exposed.

**Primary metric.** Readers with ≥1 new conversation per exposed reader (funnel, 7-day window).

**Secondary / guardrails.** `Upgrade Succeeded` per exposed reader (7 days); D7 retention (any app
open 7 days after exposure); `Paywall Opened` per reader; `Product Error` per reader (crash proxy).
Break every metric down by `$feature/home-redesign`.

**Decision rule.** Minimum detectable effect 10% relative on the primary metric at PostHog's default
confidence; if `test` is worse than control by more than 20% relative on Product Error or D7
retention, switch it to 0% regardless. Run until each arm has at least 2,000 exposed readers or 14
days, whichever is later. When decided, delete the losing path (for `test` winning:
`app/lib/pages/home/legacy/`).

**Kill switch.** Set the flag to control 100% (or deactivate it); every build shows today's Home
without a release. Debug builds: `--dart-define=OMI_HOME_REDESIGN=on|off`.

**Owner.** yinka. Created 2026-10-15. Review by 2026-11-14.
