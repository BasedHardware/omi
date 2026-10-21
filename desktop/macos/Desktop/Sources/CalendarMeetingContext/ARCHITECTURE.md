# Calendar meeting context and meeting briefs

`SystemCalendarMeetingContextService` reads nearby local calendar events (read-only)
so a recorded meeting can carry its calendar identity. `MeetingMemoryBriefComposer`
turns that identity into an opt-in pilot card on the Conversations page: before an
upcoming event, it shows a decision, the user's open follow-up and/or an open
question from a prior matched meeting. Every line opens its cited transcript
segments. `MeetingFollowUpDraftComposer` prepares an editable, copy-only draft from
cited user-owned actions; nothing is ever sent.

## Matching and omission

- Match the same system-calendar event ID, or an exactly normalized title of at
  least 8 characters plus a shared attendee email. Shorter, generic titles
  ("Sync", "1:1") need the exact event ID. Never match on an AI title alone.
- Facts come only from cited summary sections and cited, user-owned, incomplete
  action items. Unsettled, disputed, future or hypothetical lines are omitted;
  a negation scoping the agreed action ("agreed not to ask") is still a decision.
  No cited fact means no card.
- The feature is off by default. The Calendar prompt is raised only from the
  settings toggle; background refreshes never prompt or upload calendar data.

## Evidence status

| Claim | Status |
|---|---|
| Matching, omission, citation focus, rendering, owner fencing, draft safety | Unit/rendering tests |
| Calendar entitlement in development and release signing inputs | `tests/test-prepare-local-dev-entitlements.sh`, `plutil` |
| Live card + source jump for a real calendar event against production | Verified once, controlled: a scripted meeting during a real call (`.agent-artifacts/ui-evidence/20824/003`, `004`) |
| Live "You owe" line from a production user-owned action item | Not verified live; the controlled run produced no user-owned action item |
| Usefulness on organic meetings (helpful / not / annoying) | Not measured; no pilot data yet |

The controlled run proves the end-to-end path works. It is not evidence of how
useful briefs are on real meetings.

## Pilot checklist

- [x] Opt-in setting, settings-initiated Calendar prompt, read-only brief path.
- [x] Source-linked facts with conservative omission; copy-only follow-up draft.
- [x] Controlled live card and source navigation against production.
- [ ] Human decision: approve the opt-in Conversations-page pilot.
- [ ] Human decision: approve the Calendar permission posture and the
      `com.apple.security.personal-information.calendars` release entitlement.
- [ ] Human decision: accept the short-title exact-event-ID matching policy.
- [ ] Live verification of a user-owned follow-up line on a real meeting.
- [ ] Organic pilot measurement (helpful / not helpful / annoying, wrong matches)
      before any change to default exposure.
