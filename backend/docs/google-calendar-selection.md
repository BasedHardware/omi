# Google Calendar read selection

Issue: #20195. This is separate from Google OAuth approval/configuration #12354.

## Authority and flow

`GET/PUT /v1/calendar/google/calendars` owns calendar discovery and explicit read
selection. Google CalendarList is paginated with `minAccessRole=reader`, including
hidden readable calendars; free/busy-only and deleted entries are excluded. The
already requested `calendar` OAuth scope covers this call; no scope is widened.
Narrowing Calendar to `calendar.events.readonly` plus
`calendar.calendarlist.readonly` (added by explicit incremental consent) belongs
to the dedicated Calendar project/client work, not this change; until then this
selection rides the consent bundle users already granted.

Both routes are rate limited per Omi user at 10 requests/minute
(`google_calendar:selection`). Each read enumerates up to 20 CalendarList pages
before fanning out, so an unthrottled poller could drain the shared OAuth
client's Calendar quota. Opted-in event reads additionally use the bounded
metadata cache described below.

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

## Discovery quota and freshness

Opted-in event reads cache only verified primary/calendar IDs for 30 seconds per
process, bounded to 20,000 calendar IDs (including primary-entry overhead).
Cache keys digest the Omi owner, current access token and current persisted
selection. No raw token, calendar title, event or stale preference is cached.
Preferences are read on every operation: saving a different selection invalidates
the key in every worker, while a refreshed/reconnected grant has a new token key.
An explicit catalog refresh/save bypasses and invalidates the local read cache.
Discovery errors never serve stale data. Event requests always go to Google;
403/404/410 on a secondary calendar excludes it and evicts local discovery metadata.
Google remains the authorization boundary even during the 30-second metadata TTL.

GET and PUT catalog routes share the Redis-backed `google_calendar:selection` budget of
10 requests per UID per minute, exempt from event-wide rate-limit boosts.
Exhaustion returns 429 with Retry-After before any Google call. Redis failure
fails open, preserving the incoming maintainer change and the shared first-party
endpoint policy; the quota cap is unavailable during that outage. Existing
operational shadow-mode override still applies. The cache
reduces repeated conversation-read discovery, while this fleet-wide rate limit
bounds manual refresh/save traffic. Simultaneous cold misses may each discover;
the cache does not claim cross-worker single-flight or replace Google quota limits.

`writerWithoutPrivateAccess` remains readable: it is documented in Google's
[CalendarList accessRole contract](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList).
Google hides private-event details for this role; Omi does not broaden that access.

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
- [x] Generated API/schema consumers and repository preflight; 14 schema
      inventory and 29 Dart-generator/UTF-8 contract tests
- [x] Per-user rate limit on the catalog and save routes
- [ ] Final combined diff review and exact-head CI; the new follow-up must
      pass before readiness. Live qualification follows the recorded decision below

Provider verification and backend/app releases must be recorded separately from
local synthetic tests. A synthetic provider's Personal/Workspace-shaped payloads
do not establish a live Workspace administrator policy or Google's approval.
No production calendar mutation, credential change or customer test is authorized
as part of the local verification.

## Release order and remaining qualification

November 12 follow-up checks:
- [x] Cache expiry, owner/grant/selection separation, revocation and error/no-stale-data regressions
- [x] Shared route rate budget, 429 Retry-After and documented first-party fail-open behavior on limiter outage
- [x] Production routes with real local Firestore persistence and synthetic provider revocation
- [ ] Current follow-up commit CI

Deploy the additive backend API before publishing clients that expose the picker.
Existing released clients keep their primary-only behavior until a user saves a
selection. Once saved, the shared server reads apply it to older clients too.
No existing imported memories, source recordings or connected credentials are
deleted by this change.

## Deferred live provider qualification

Maintainer decision, 2026-11-12: live Personal and Workspace provider
qualification moves to the first client build that exposes the picker instead of
blocking this backend merge.

Why that is bounded:

- The consent request is unchanged — same OAuth client, same scopes, same
  redirect. This change adds no new Google surface, so it cannot change a
  Workspace administrator's app-access decision. That boundary is exactly as
  verified as the existing Calendar integration.
- No released client calls `PUT /v1/calendar/google/calendars`, so the additive
  API is unreachable and every user without a saved selection keeps the
  unchanged primary-only read path.
- Discovery, per-calendar access loss, grant loss and reconnect are covered by
  hermetic and Firestore-emulator tests. What those cannot prove is a live
  Google grant and a live Workspace policy decision.

This PR also contains picker UI, so the first exposing desktop/mobile build must
complete this qualification before release; the automatic desktop Beta train
must not be mistaken for provider verification. No live result is claimed here.

The first dogfood build therefore performs: connect, discover, save two
calendars, read a secondary-only event, reconnect, and remove a calendar whose
access was revoked. Record the result here when that build exists.

Exact-head CI must pass before merge. Customer confirmation and store/backend
releases are later states, separate from technical merge readiness.
