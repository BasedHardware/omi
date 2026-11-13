# Home task card, variant C (2026-10-08)

Applies to iOS (omi-native, source of truth) and Android identically. Replaces the DecisionCard
look for task cards in "Needs you" (memory review and agent run cards keep theirs for now).

## Layout (one compact row card)
- Card: `DS.Palette.card`, continuous radius 22, no stroke, padding 14 all around, 12 between cards.
- Leading: entity picture 40 pt, vertically centered (`EntityVisual`):
  1. Brand logo only from hard signals: a known service named in the task text (Gmail, Slack,
     Notion, ...; bundled marks where the app ships one), or a company e-mail domain among the
     conversation's people (summary participants, then calendar attendees). Never freemail
     (gmail.com, icloud.com, ...) or placeholders (example.com, *.test). Never guessed from a name.
     Logo: `https://img.logo.dev/<domain>?token=<pk>&size=128&format=png&fallback=404` on a white
     rounded-square plate with a hairline; on load failure fall back to (3)/(4). Cache to disk.
  2. Person the task names (first name of a conversation person appears in the task): monogram
     circle with a soft two-tone gradient (hue from the name hash).
  3. The conversation's emoji on a rounded square tinted by category (12 % light, 18 % dark).
  4. A category glyph on `DS.Palette.fill`.
- Middle: title (body, medium weight, max 2 lines), then one meta line: 6 pt status dot + status
  text (footnote semibold, kicker color: overdue = live, due today = warning, due soon = inkSecondary,
  someone waits = warning, suggestion = agent) + " · " + source ("Pricing sync · Wed", or
  "Pricing sync +1" for a merged card; no "From:").
- Trailing: the magic button, a 36 pt circle: `sparkles` in agent blue on `agentSoft` when Omi can
  take over (`canTakeOver`), else `checkmark` in ink on `fill` (marks done).

## Interactions
- Tap the card: the task's detail (iOS `TaskDetailSheet(task:onHandOver:)`; Android a faithful port).
- Tap the magic button: Omi starts right away (no preview sheet): the same start the hand-over sheet's
  primary button does (`agent` start work + the recommendation decision `doNow`). Haptic success-light.
  While the run is active the card stays and changes in place: the button becomes a small spinning
  ring in agent blue, the meta line reads "● Omi is on it" in agent blue (dot pulses). Tapping the
  card then opens the hand-over sheet in its progress state. When the run finishes, the card is
  replaced by the existing "Done by Omi" / "Needs you" run cards.
  The checkmark variant completes the task (as "Done" did), with the success haptic.
- Swipe the card from left to right: it slides out and is snoozed to tomorrow ("Later", same as the
  old Later pill), with an undo toast at the bottom ("Moved to Later" + "Undo"). Right swipe only:
  Home is the first page, so nothing else uses that direction; a left drag still pages to Chat.
  Threshold ~35 % of the width or a fast fling; below it the card springs back. Reduce Motion: no
  slide, just fade.
- Long press: the existing menu (Mark done, Omi takes over, Later / Back to Needs you, Open
  conversation, Not a task).
- Strings: reuse existing keys only (nativeForYouLater, nativeOmiTakesOver, undo, ...). For
  "Omi is on it" use an existing key if one fits (search native.json / ARB, e.g. agent working
  strings); otherwise add ONE new native key `nativeOmiIsOnIt` (en + de) in omi-native's native.json.
