# Google Calendar read selection

Issue: #20195. This is separate from Google OAuth approval/configuration #12354.

## Authority and flow

`GET/PUT /v1/calendar/google/calendars` owns calendar discovery and explicit read
selection. Google CalendarList is paginated with `minAccessRole=reader`, including
hidden readable calendars; free/busy-only and deleted entries are excluded. The
already requested `calendar` OAuth scope covers this call; no scope is widened.

Preferences live on the Omi user document, keyed by a digest of Google's verified
primary-calendar ID. A reconnect to that Google account reuses its selection;
another Google or Omi account does not inherit it. A stale picker cannot save to
a replacement Google account. The preferences contain no tokens and are removed
with the owning user document during account deletion. A nested-field Firestore
update preserves other Google accounts and cannot recreate a deleted user.

Users who have never opted in retain primary-only reads without new provider
discovery. After opt-in, discovery failure fails closed rather than reading an
unselected primary calendar. Unavailable saved calendars remain visible and
removable, are skipped on reads, and are never silently replaced. A transient or
authentication failure is not an empty calendar. Selected-secondary access lost
between discovery and fetch is isolated from the remaining selected calendars.

All active server read callers supply the authenticated Omi owner: picker/event
reads, chat read/update/delete searches, capture gaps, automatic linking/meeting
context and failed-finalization calendar protection. Each calendar has its own
pagination cursor; results are merged chronologically with a global cap. One
multi-calendar read is bounded by a 20-second deadline.

Secondary event references encode both calendar and event ID. Primary event IDs
remain unchanged for released-client compatibility. Linking, imported evidence
dedupe and update/delete round-trip that opaque reference; URL path segments are
escaped. **New events still use primary.** Read selection never changes the
creation destination and does not remove previously imported memories.

## Client surfaces

| Surface | Selection and read path |
| --- | --- |
| Flutter iOS/Android | Settings → Integrations → Calendar settings; shared owner-fenced HTTP transport; saving invalidates in-flight/cached meeting hints |
| macOS | Apps → Calendar import panel; shared owner-authorized API client and grant reader; settings/onboarding/import/chat reads consume the same backend selection |
| Windows/Linux | Settings → Integrations → Google Calendar; same authenticated API and owner fence; server tools use the shared read authority |

The macOS cookie reader remains available only when the backend confirms that
the Omi account has no Google grant and no saved read selection. The integration
status exposes `read_selection_configured` even after disconnection; a saved or
unverifiable scope requires reconnect/error, never browser fallback.
Failure of an existing grant/status read must not silently import another
browser account's unselected calendar. The presently unreferenced
`GoogleCalendarReadAdapter` is not a serving path; future adoption must consume
this same authority rather than reintroducing a primary-only source.

## Implementation and verification checklist

- [x] Authenticated catalog and save API; per-Google-account persistence
- [x] Selected-calendar fan-out, pagination, identity and mutation routing
- [x] All active backend caller migration
- [x] Flutter, macOS and Windows/Linux selection controls
- [x] Backend calendar/linking/context regressions: 161 tests across 21 isolated files
- [x] Firestore emulator persistence/reconnect/account isolation integration: 2 tests
- [x] Flutter UI/transport: 10 tests; iPhone 16 Pro simulator loopback journey:
      primary default → multiple calendars → persisted reopen → secondary-only reads
- [x] macOS compile and 31 production transport/auth/reader/parser tests
- [x] macOS named QA app with local Auth/Firestore emulators: cancel, save,
      reload, secondary-only reads, removable inaccessible calendar, and an explicit
      Google connection entry point for legacy browser-only users
- [x] Windows/Linux typecheck, 30 UI/transport/owner-fence tests and changed-file ESLint
- [ ] Generated API/schema consumers and repository preflight
- [ ] Final diff review and exact-head CI; remain draft until required gates pass

Provider verification and backend/app releases must be recorded separately from
local synthetic tests. A synthetic provider's Personal/Workspace-shaped payloads
do not establish a live Workspace administrator policy or Google's approval.
No production calendar mutation, credential change or customer test is authorized
as part of the local verification.

## Release order and remaining qualification

Deploy the additive backend API before publishing clients that expose the picker.
Existing released clients keep their primary-only behavior until a user saves a
selection. Once saved, the shared server reads apply it to older clients too.
No existing imported memories, source recordings or connected credentials are
deleted by this change.

Before readiness, record live Personal and Workspace test-account results for
calendar discovery, selected secondary reads, reconnect and access revocation.
This verifies Google's grant/admin policy boundary; synthetic contract fixtures
do not replace it. Exact-head CI must also pass.
Customer confirmation and store/backend releases are later states, separate from
technical merge readiness.
